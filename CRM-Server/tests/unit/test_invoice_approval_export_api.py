"""Invoice and approval export API tests (Task 9)."""

import io
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable
from sqlalchemy.types import BigInteger

from app.api.approvals import router as approvals_router
from app.api.invoices import invoice_router
from app.core import deps
from app.models.approval import Approval, ApprovalAction, ApprovalFlow, ApprovalNode, ApprovalRecord, ApprovalStatus
from app.models.contract import Contract
from app.models.customer import Customer, CustomerMember
from app.models.invoice import (
    InvoiceApplication,
    InvoiceApplicationStatus,
    InvoiceRedOffset,
    InvoiceReissueApplication,
    InvoiceReissueApplicationStatus,
    InvoiceType,
)
from app.models.opportunity import Opportunity
from app.models.payment import PaymentPlan, PaymentPlanStatus
from app.models.role import Role
from app.models.user import User, UserStatus
from app.models.user_role import UserRole
from app.constants.business_types import BusinessType


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        User.__table__,
        Role.__table__,
        UserRole.__table__,
        Customer.__table__,
        CustomerMember.__table__,
        Opportunity.__table__,
        Contract.__table__,
        PaymentPlan.__table__,
        InvoiceApplication.__table__,
        InvoiceReissueApplication.__table__,
        InvoiceRedOffset.__table__,
        ApprovalFlow.__table__,
        ApprovalNode.__table__,
        Approval.__table__,
        ApprovalRecord.__table__,
    ]
    with engine.begin() as connection:
        for table in tables:
            connection.execute(CreateTable(table))
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def client(db_session, monkeypatch):
    import app.api.invoices as invoices_module
    import app.api.approvals as approvals_module

    test_session_factory = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr(invoices_module, "SessionLocal", test_session_factory, raising=False)
    monkeypatch.setattr(approvals_module, "SessionLocal", test_session_factory, raising=False)

    app = FastAPI()
    app.include_router(invoice_router, prefix="/v1")
    app.include_router(approvals_router)
    app.dependency_overrides[deps.get_db] = lambda: db_session
    app.dependency_overrides[deps.get_current_user_team] = lambda: 1
    app.dependency_overrides[deps.get_current_active_user] = lambda: SimpleNamespace(
        id=1,
        name="财务张",
        status="active",
        email="finance@example.com",
    )

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def _grant(monkeypatch, *codes: str) -> None:
    from app.crud.permission import permission_crud

    monkeypatch.setattr(
        permission_crud,
        "get_user_permissions",
        lambda *args, **kwargs: [SimpleNamespace(code=code) for code in codes],
    )


def _workbook_rows(response) -> list[tuple]:
    workbook = load_workbook(io.BytesIO(response.content), read_only=True)
    return list(workbook.active.values)


def _seed_user(db_session, user_id: int = 1, name: str = "财务张") -> None:
    if db_session.query(User).filter_by(id=user_id).first() is None:
        db_session.add(User(id=user_id, email=f"user{user_id}@example.com", name=name, status=UserStatus.ACTIVE))


def _seed_graph(db_session, *, owner_id: str = "1", graph_id: int = 1) -> None:
    user_id = int(owner_id)
    _seed_user(db_session, user_id=user_id, name=f"用户{owner_id}")
    if db_session.query(Customer).filter_by(id=graph_id).first() is None:
        db_session.add(Customer(
            id=graph_id,
            team_id=1,
            public_id=f"cus_{graph_id:032d}",
            account_name=f"客户{owner_id}",
            city="上海",
            owner_id=owner_id,
            creator_id=owner_id,
        ))
    if db_session.query(Opportunity).filter_by(id=graph_id).first() is None:
        db_session.add(Opportunity(
            id=graph_id,
            public_id=f"opp_{graph_id:032d}",
            team_id=1,
            opportunity_number=f"OPP-{graph_id:03d}",
            opportunity_name=f"商机{owner_id}",
            customer_id=graph_id,
            total_amount=Decimal("1000"),
            user_count=10,
            unit_price=Decimal("100"),
            license_type="SUBSCRIPTION",
            purchase_type="NEW",
            expected_closing_date=date(2026, 12, 31),
            owner_id=owner_id,
            creator_id=owner_id,
        ))
    if db_session.query(Contract).filter_by(id=graph_id).first() is None:
        db_session.add(Contract(
            id=graph_id,
            team_id=1,
            contract_number=f"CT-{graph_id:03d}",
            contract_name=f"合同{owner_id}",
            customer_id=graph_id,
            opportunity_id=graph_id,
            user_count=10,
            total_amount=Decimal("1000"),
            license_type="SUBSCRIPTION",
            standard_unit_price=Decimal("100"),
            owner_id=owner_id,
            creator_id=owner_id,
        ))
    if db_session.query(PaymentPlan).filter_by(id=graph_id).first() is None:
        db_session.add(PaymentPlan(
            id=graph_id,
            team_id=1,
            contract_id=graph_id,
            plan_number=f"PP-{graph_id:03d}",
            stage_name="首付款",
            planned_amount=Decimal("1000"),
            due_date=date(2026, 9, 10),
            status=PaymentPlanStatus.PENDING,
        ))


def _seed_invoice(db_session, **overrides) -> InvoiceApplication:
    defaults = {
        "team_id": 1,
        "application_number": "INV-001",
        "customer_id": 1,
        "contract_id": 1,
        "opportunity_id": 1,
        "payment_plan_id": 1,
        "invoice_amount": Decimal("800.00"),
        "invoice_type": InvoiceType.VAT_NORMAL,
        "status": InvoiceApplicationStatus.ISSUED,
        "applicant_id": "1",
        "invoice_title_id": 1,
        "invoice_title_type": "COMPANY",
        "invoice_title_text": "测试抬头",
        "invoice_taxpayer_id": "TAX-001",
        "created_time": datetime(2026, 8, 10, 9, 0, 0),
        "last_modified_time": datetime(2026, 8, 10, 9, 0, 0),
    }
    defaults.update(overrides)
    application = InvoiceApplication(**defaults)
    db_session.add(application)
    return application


def _seed_finance_role(db_session, user_id: int = 1) -> ApprovalNode:
    role = Role(code="FINANCE", name="财务", description="财务")
    db_session.add(role)
    db_session.flush()
    db_session.add(UserRole(user_id=user_id, role_id=role.id, team_id=1))
    flow = ApprovalFlow(
        team_id=1,
        flow_name="发票审批",
        flow_code="INVOICE_FLOW",
        business_type=BusinessType.INVOICE,
        is_active=1,
    )
    db_session.add(flow)
    db_session.flush()
    node = ApprovalNode(
        team_id=1,
        flow_id=flow.id,
        node_name="财务审批",
        node_code="FINANCE",
        node_order=1,
        approve_role="FINANCE",
        is_required=1,
    )
    db_session.add(node)
    db_session.flush()
    return node


def _seed_approval(db_session, node: ApprovalNode, **overrides) -> Approval:
    defaults = {
        "business_type": BusinessType.INVOICE,
        "business_id": 1,
        "flow_id": node.flow_id,
        "team_id": 1,
        "current_node_id": node.id,
        "status": ApprovalStatus.PENDING,
        "submitter_id": "1",
        "submitter_name": "财务张",
        "created_time": datetime(2026, 8, 10, 9, 0, 0),
        "updated_time": datetime(2026, 8, 10, 9, 0, 0),
    }
    defaults.update(overrides)
    approval = Approval(**defaults)
    db_session.add(approval)
    db_session.flush()
    db_session.add(ApprovalRecord(
        approval_id=approval.id,
        node_id=node.id,
        approver_id=defaults["submitter_id"],
        approver_name=defaults["submitter_name"],
        action=ApprovalAction.SUBMIT,
        comment=None,
        team_id=1,
    ))
    return approval

def _seed_completed_reissue(db_session, original: InvoiceApplication, **overrides) -> InvoiceReissueApplication:
    defaults = {
        "team_id": 1,
        "application_number": "INVR-001",
        "original_invoice_application_id": original.id,
        "applicant_id": "1",
        "reason": "抬头错误",
        "status": InvoiceReissueApplicationStatus.COMPLETED,
        "approval_phase": "approved",
        "invoice_title_type": "COMPANY",
        "invoice_title_text": "新抬头",
        "invoice_taxpayer_id": "TAX-NEW",
        "invoice_amount": original.invoice_amount,
        "invoice_type": InvoiceType.VAT_NORMAL,
        "new_invoice_file_path": "invoices/reissue-new.pdf",
        "new_invoice_number": "REISSUE-NO-1",
        "completed_time": datetime(2026, 8, 20, 9, 0, 0),
        "created_time": datetime(2026, 8, 19, 9, 0, 0),
        "last_modified_time": datetime(2026, 8, 20, 9, 0, 0),
    }
    defaults.update(overrides)
    reissue = InvoiceReissueApplication(**defaults)
    db_session.add(reissue)
    return reissue



def test_invoice_export_requires_permission_and_keeps_view_own_customer_scope(
    client,
    db_session,
    monkeypatch,
):
    _grant(monkeypatch, "invoice:view:own", "customer:view:own")
    _seed_graph(db_session, owner_id="1", graph_id=1)
    _seed_graph(db_session, owner_id="2", graph_id=2)
    _seed_invoice(db_session, application_number="INV-MINE", customer_id=1, applicant_id="1")
    _seed_invoice(db_session, application_number="INV-OTHER", customer_id=2, applicant_id="2")
    db_session.commit()

    denied = client.post("/v1/invoice-applications/export", json={
        "fields": ["application_number"],
        "tab": "all",
        "filters": [],
        "sorts": [],
    })
    assert denied.status_code == 403

    _grant(monkeypatch, "invoice:export", "invoice:view:own", "customer:view:own")
    allowed = client.post("/v1/invoice-applications/export", json={
        "fields": ["application_number"],
        "tab": "all",
        "filters": [],
        "sorts": [],
    })
    assert allowed.status_code == 200
    rows = _workbook_rows(allowed)
    assert rows[0] == ("申请单号",)
    assert [row[0] for row in rows[1:]] == ["INV-MINE"]


def test_invoice_export_maps_invoiced_tab_and_writes_formula_safe_title(
    client,
    db_session,
    monkeypatch,
):
    _grant(monkeypatch, "invoice:export", "invoice:view:all")
    _seed_graph(db_session)
    _seed_invoice(
        db_session,
        application_number="INV-PENDING",
        status=InvoiceApplicationStatus.PENDING_REVIEW,
        invoice_title_text="普通抬头",
        created_time=datetime(2026, 8, 9, 9, 0, 0),
    )
    _seed_invoice(
        db_session,
        application_number="INV-ISSUED",
        status=InvoiceApplicationStatus.ISSUED,
        invoice_title_text="=SUM(1,2)",
        invoice_amount=Decimal("1234.50"),
        created_time=datetime(2026, 8, 11, 9, 0, 0),
    )
    db_session.commit()

    response = client.post("/v1/invoice-applications/export", json={
        "fields": ["application_number", "invoice_title_text", "status", "invoice_amount"],
        "tab": "invoiced",
        "filters": [],
        "sorts": [],
    })

    assert response.status_code == 200
    rows = _workbook_rows(response)
    assert rows[0] == ("申请单号", "开票抬头", "状态", "开票金额")
    assert [row[0] for row in rows[1:]] == ["INV-ISSUED"]
    assert rows[1][1] == "'=SUM(1,2)"
    assert rows[1][2] == "已开票"
    assert rows[1][3] == 1234.5


def test_approval_export_keeps_pending_role_scope(client, db_session, monkeypatch):
    _grant(monkeypatch, "approval:export")
    _seed_user(db_session)
    node = _seed_finance_role(db_session)
    other_flow = ApprovalFlow(
        team_id=1,
        flow_name="销售审批",
        flow_code="SALES_FLOW",
        business_type=BusinessType.INVOICE,
        is_active=1,
    )
    db_session.add(other_flow)
    db_session.flush()
    sales_node = ApprovalNode(
        team_id=1,
        flow_id=other_flow.id,
        node_name="销售审批",
        node_code="SALES",
        node_order=1,
        approve_role="SALES",
        is_required=1,
    )
    db_session.add(sales_node)
    db_session.flush()
    _seed_graph(db_session, owner_id="1", graph_id=11)
    mine_invoice = _seed_invoice(db_session, application_number="INV-MINE-11", customer_id=11, contract_id=11, opportunity_id=11, payment_plan_id=11)
    db_session.flush()
    mine = _seed_approval(db_session, node, business_id=mine_invoice.id)
    _seed_approval(db_session, sales_node, business_id=12)
    db_session.commit()

    response = client.post("/v1/approvals/export", json={
        "fields": ["application_number", "status"],
        "tab": "pending",
        "filters": [],
        "sorts": [],
    })

    assert response.status_code == 200
    rows = _workbook_rows(response)
    assert rows[0] == ("单号", "状态")
    assert len(rows) == 2
    assert rows[1][0] == "INV-MINE-11"
    assert rows[1][1] == "审批中"
    assert mine.business_id == mine_invoice.id



def test_approval_export_keeps_processed_and_submitted_scope(client, db_session, monkeypatch):
    _grant(monkeypatch, "approval:export")
    _seed_user(db_session)
    node = _seed_finance_role(db_session)
    _seed_graph(db_session, owner_id="1", graph_id=21)
    _seed_graph(db_session, owner_id="2", graph_id=22)
    submitted_invoice = _seed_invoice(
        db_session,
        application_number="INV-SUB-21",
        customer_id=21,
        contract_id=21,
        opportunity_id=21,
        payment_plan_id=21,
    )
    processed_invoice = _seed_invoice(
        db_session,
        application_number="INV-PROC-22",
        customer_id=22,
        contract_id=22,
        opportunity_id=22,
        payment_plan_id=22,
    )
    db_session.flush()
    _seed_approval(
        db_session,
        node,
        business_id=submitted_invoice.id,
        status=ApprovalStatus.APPROVED,
        submitter_id="1",
    )
    processed = _seed_approval(
        db_session,
        node,
        business_id=processed_invoice.id,
        status=ApprovalStatus.APPROVED,
        submitter_id="2",
        submitter_name="他人",
    )
    db_session.add(ApprovalRecord(
        approval_id=processed.id,
        node_id=node.id,
        approver_id="1",
        approver_name="财务张",
        action=ApprovalAction.APPROVE,
        comment=None,
        team_id=1,
    ))
    db_session.commit()

    submitted_response = client.post("/v1/approvals/export", json={
        "fields": ["application_number"],
        "tab": "submitted",
        "filters": [],
        "sorts": [],
    })
    processed_response = client.post("/v1/approvals/export", json={
        "fields": ["application_number"],
        "tab": "processed",
        "filters": [],
        "sorts": [],
    })

    assert submitted_response.status_code == 200
    assert processed_response.status_code == 200
    submitted_rows = _workbook_rows(submitted_response)
    processed_rows = _workbook_rows(processed_response)
    assert [row[0] for row in submitted_rows[1:]] == ["INV-SUB-21"]
    assert len(processed_rows) == 2
    assert processed_rows[1][0] == "INV-PROC-22"


def test_invoice_and_approval_exports_write_all_matching_rows(client, db_session, monkeypatch):
    _grant(monkeypatch, "invoice:export", "invoice:view:all", "approval:export")
    _seed_graph(db_session)
    node = _seed_finance_role(db_session)
    for index in range(76):
        _seed_invoice(
            db_session,
            application_number=f"INV-{index:02d}",
            status=InvoiceApplicationStatus.PENDING_REVIEW,
            created_time=datetime(2026, 8, 1, 9, 0, 0) + timedelta(minutes=index),
        )
        _seed_approval(
            db_session,
            node,
            business_id=index + 1,
            created_time=datetime(2026, 8, 1, 9, 0, 0) + timedelta(minutes=index),
        )
    db_session.commit()

    invoice_response = client.post("/v1/invoice-applications/export", json={
        "fields": ["application_number"],
        "tab": "pending",
        "filters": [],
        "sorts": [],
    })
    approval_response = client.post("/v1/approvals/export", json={
        "fields": ["application_number"],
        "tab": "pending",
        "filters": [],
        "sorts": [],
    })

    assert invoice_response.status_code == 200
    assert approval_response.status_code == 200
    invoice_rows = _workbook_rows(invoice_response)
    approval_rows = _workbook_rows(approval_response)
    assert len(invoice_rows) == 77
    assert len(approval_rows) == 77
    assert invoice_rows[1][0] == "INV-75"
    assert invoice_rows[76][0] == "INV-00"


def test_invoice_list_projects_current_reissue_file_for_download(client, db_session, monkeypatch):
    _grant(monkeypatch, "invoice:view:all")
    _seed_graph(db_session)
    original = _seed_invoice(
        db_session,
        application_number="INV-REISSUE",
        invoice_file_path="invoices/original.pdf",
        invoice_number="OLD-NO-1",
        status=InvoiceApplicationStatus.ISSUED,
    )
    db_session.flush()
    reissue = _seed_completed_reissue(db_session, original)
    db_session.commit()

    response = client.get("/v1/invoice-applications")
    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["application_number"] == "INV-REISSUE"
    assert item["current_invoice_file_kind"] == "reissue_new"
    assert item["current_invoice_file_path"] == "invoices/reissue-new.pdf"
    assert item["current_invoice_number"] == "REISSUE-NO-1"
    assert item["current_reissue_id"] == reissue.id
    assert item["customer_id"] == "cus_00000000000000000000000000000001"


def test_approval_export_blanks_internal_id_application_number_fallback(client, db_session, monkeypatch):
    _grant(monkeypatch, "approval:export")
    _seed_user(db_session)
    node = _seed_finance_role(db_session)
    approval = _seed_approval(db_session, node, business_id=99)
    db_session.commit()

    response = client.post("/v1/approvals/export", json={
        "fields": ["application_number", "status"],
        "tab": "pending",
        "filters": [],
        "sorts": [],
    })
    assert response.status_code == 200
    rows = _workbook_rows(response)
    assert len(rows) == 2
    assert rows[1][0] in {None, ""}
    assert rows[1][0] not in {f"INV-{approval.business_id}", f"INVOICE-{approval.business_id}"}
    assert rows[1][1] == "审批中"


def test_invoice_and_approval_export_unknown_filter_returns_400(client, monkeypatch):
    _grant(monkeypatch, "invoice:export", "invoice:view:all", "approval:export")
    unknown_filter = [{"field": "missing", "op": "eq", "value": "x"}]

    invoice_response = client.post("/v1/invoice-applications/export", json={
        "fields": ["application_number"],
        "tab": "all",
        "filters": unknown_filter,
        "sorts": [],
    })
    approval_response = client.post("/v1/approvals/export", json={
        "fields": ["application_number"],
        "tab": "pending",
        "filters": unknown_filter,
        "sorts": [],
    })

    assert invoice_response.status_code == 400, invoice_response.text
    assert "未知筛选字段" in invoice_response.text
    assert approval_response.status_code == 400, approval_response.text
    assert "未知筛选字段" in approval_response.text
