"""Task C3：通用审批列表端点 GET /v1/approvals 单元测试。

覆盖：
- tab=pending：仅返 current_node.approve_role IN 当前用户角色集 + status=PENDING 的审批（E2）
- tab=processed：仅返 当前用户作为审批人留下过 APPROVE/REJECT 记录的审批（排除 SUBMIT）
- tab=submitted：仅返 submitter_id == 当前用户 的审批
- 跨 team 不返（team_id 隔离）
- overdue_hours：PENDING 行算对（now - created_time）/3600
- pending_count：任意 tab 响应都携带（待我审批总数）
- business_type 过滤生效
- entity 摘要（application_number/entity_name/entity_amount）按 business_type 内存 join
"""
import json

import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.types import BigInteger
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# SQLite 把 BigInteger 编译为 INTEGER，确保 BigInteger 主键在 SQLite 上能自增。
@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import Base
from app.constants.business_types import BusinessType
from app.core import deps
from app.api.approvals import router as approvals_router

from app.models.approval import (
    Approval, ApprovalRecord, ApprovalFlow, ApprovalNode,
    ApprovalStatus, ApprovalAction,
)
from app.models.contract import Contract, ContractStatus
from app.models.invoice import InvoiceApplication, InvoiceApplicationStatus, InvoiceType
from app.models.opportunity import Opportunity
from app.models.payment import PaymentRecord, PaymentConfirmationStatus
from app.models.user import User, UserStatus
from app.models.role import Role
from app.models.user_role import UserRole


# ---------- DB fixtures ---------------------------------------------------

@pytest.fixture(scope="function")
def db_session():
    """内存 SQLite，StaticPool 共享连接跨线程可见。"""
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        User.__table__,
        Role.__table__,
        UserRole.__table__,
        Contract.__table__,
        InvoiceApplication.__table__,
        PaymentRecord.__table__,
        ApprovalFlow.__table__,
        ApprovalNode.__table__,
        Approval.__table__,
        ApprovalRecord.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    with engine.begin() as conn:
        conn.exec_driver_sql("""
            CREATE TABLE crm_opportunities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                public_id VARCHAR(64) NOT NULL UNIQUE,
                team_id INTEGER NOT NULL,
                opportunity_number VARCHAR(50) NOT NULL,
                opportunity_name VARCHAR(255) NOT NULL,
                customer_id INTEGER NOT NULL,
                procurement_method_id INTEGER,
                current_stage_snapshot_id INTEGER,
                current_stage_name VARCHAR(100),
                current_win_probability INTEGER,
                current_stage_entered_at DATETIME,
                deal_journey_id INTEGER,
                total_amount NUMERIC(12, 2) NOT NULL,
                user_count INTEGER NOT NULL,
                unit_price NUMERIC(10, 2) NOT NULL,
                license_type VARCHAR(20) NOT NULL,
                subscription_years INTEGER,
                purchase_type VARCHAR(20) NOT NULL,
                decision_maker_count INTEGER,
                expected_closing_date DATE NOT NULL,
                procurement_stage_id INTEGER,
                win_probability INTEGER NOT NULL DEFAULT 0,
                owner_id VARCHAR(100) NOT NULL,
                status INTEGER NOT NULL DEFAULT 0,
                approval_phase VARCHAR(20) NOT NULL DEFAULT 'draft',
                loss_reason VARCHAR(500),
                actual_amount NUMERIC(12, 2),
                actual_closing_date DATE,
                creator_id VARCHAR(100) NOT NULL,
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                last_modified_time DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                version INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.exec_driver_sql("""
            CREATE TABLE crm_invoice_reissue_applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                application_number VARCHAR(50),
                invoice_title_text VARCHAR(255),
                invoice_amount NUMERIC(12, 2)
            )
        """)
        conn.exec_driver_sql("""
            CREATE TABLE crm_license_applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                application_number VARCHAR(50),
                license_type VARCHAR(20)
            )
        """)
        conn.exec_driver_sql("""
            CREATE TABLE crm_contract_payment_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                contract_id INTEGER NOT NULL
            )
        """)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture(scope="function")
def app(db_session):
    app_ = FastAPI()
    app_.include_router(approvals_router)
    app_.dependency_overrides[deps.get_db] = lambda: db_session
    app_.dependency_overrides[deps.get_current_active_user] = lambda: _current_user_stub()
    app_.dependency_overrides[deps.get_current_user_team] = lambda: 1
    yield app_
    app_.dependency_overrides.clear()


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def current_user_rec(db_session):
    """真实写入一条 ACTIVE 用户（team 1），供 role_crud.get_user_roles 取角色。"""
    u = User(email="finance@example.com", name="财务张", status=UserStatus.ACTIVE)
    db_session.add(u)
    db_session.commit()
    return u


def _current_user_stub():
    class _U:
        id = 1
        name = "财务张"
        status = "active"
    return _U()


# ---------- 种子 fixtures --------------------------------------------------

@pytest.fixture
def seed_finance_role(db_session, current_user_rec):
    """创建 FINANCE 角色并把 current_user 关联到 team_id=1。"""
    role = Role(name="财务", code="FINANCE")
    db_session.add(role)
    db_session.flush()
    db_session.add(UserRole(user_id=current_user_rec.id, role_id=role.id, team_id=1))
    db_session.commit()
    return role


@pytest.fixture
def seed_invoice_flow(db_session):
    """INVOICE 类型审批流程 + 1 个 FINANCE 节点。"""
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
    db_session.commit()
    return flow, node


@pytest.fixture
def seed_invoice_flow_team2(db_session):
    """team_id=2 的 INVOICE 审批流程 + FINANCE 节点（跨 team 隔离测试用）。"""
    flow = ApprovalFlow(
        team_id=2,
        flow_name="发票审批-T2",
        flow_code="INVOICE_FLOW_T2",
        business_type=BusinessType.INVOICE,
        is_active=1,
    )
    db_session.add(flow)
    db_session.flush()
    node = ApprovalNode(
        team_id=2,
        flow_id=flow.id,
        node_name="财务审批-T2",
        node_code="FINANCE_T2",
        node_order=1,
        approve_role="FINANCE",
        is_required=1,
    )
    db_session.add(node)
    db_session.commit()
    return flow, node


def _make_invoice(db_session, team_id=1, status=InvoiceApplicationStatus.DRAFT):
    inv = InvoiceApplication(
        team_id=team_id,
        application_number=f"INV-{team_id}-{db_session.query(InvoiceApplication).count() + 1}",
        customer_id=1,
        contract_id=1,
        opportunity_id=1,
        payment_plan_id=1,
        invoice_amount=Decimal("5000"),
        invoice_type=InvoiceType.VAT_NORMAL,
        status=status,
        applicant_id="1",
        invoice_title_type="COMPANY",
        invoice_title_text="测试公司",
        invoice_taxpayer_id="91110000XXXXXXX",
    )
    db_session.add(inv)
    db_session.commit()
    return inv


def _make_opportunity(db_session, team_id=1):
    opp = Opportunity(
        team_id=team_id,
        opportunity_number=f"OPP20260803{db_session.query(Opportunity).count() + 1:04d}",
        opportunity_name="统一编号商机",
        customer_id=1,
        total_amount=Decimal("66000"),
        user_count=66,
        unit_price=Decimal("1000"),
        license_type="SUBSCRIPTION",
        subscription_years=1,
        purchase_type="NEW",
        expected_closing_date=datetime.now().date(),
        owner_id="1",
        creator_id="1",
    )
    db_session.add(opp)
    db_session.commit()
    return opp


def _make_approval(
    db_session,
    business_type,
    business_id,
    team_id,
    node,
    submitter_id="1",
    submitter_name="申请人",
    status=ApprovalStatus.PENDING,
    created_time=None,
):
    ap = Approval(
        business_type=business_type,
        business_id=business_id,
        contract_id=business_id if business_type == BusinessType.CONTRACT else None,
        flow_id=node.flow_id,
        team_id=team_id,
        current_node_id=node.id,
        status=status,
        submitter_id=submitter_id,
        submitter_name=submitter_name,
    )
    if created_time is not None:
        ap.created_time = created_time
        ap.updated_time = created_time
    db_session.add(ap)
    db_session.flush()
    db_session.add(ApprovalRecord(
        approval_id=ap.id,
        node_id=node.id,
        approver_id=submitter_id,
        approver_name=submitter_name,
        action=ApprovalAction.SUBMIT,
        comment=None,
        team_id=team_id,
    ))
    db_session.commit()
    return ap


def _add_approve_record(db_session, approval, node, approver_id, approver_name):
    """给已存在审批实例追加一条 APPROVE 记录（模拟 processed tab 数据）。"""
    db_session.add(ApprovalRecord(
        approval_id=approval.id,
        node_id=node.id,
        approver_id=approver_id,
        approver_name=approver_name,
        action=ApprovalAction.APPROVE,
        comment="同意",
        team_id=approval.team_id,
    ))
    db_session.commit()


# ---------- tab=pending：E2 角色过滤 --------------------------------------

def test_pending_tab_returns_only_role_matched(
    client, db_session, seed_invoice_flow, seed_finance_role,
):
    """pending tab：仅返 current_node.approve_role IN 当前用户角色集 + PENDING 的审批。"""
    flow, node = seed_invoice_flow
    inv1 = _make_invoice(db_session, team_id=1)
    _make_approval(db_session, BusinessType.INVOICE, inv1.id, 1, node)

    r = client.get("/v1/approvals?tab=pending")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["business_type"] == "INVOICE"
    assert body["items"][0]["business_id"] == inv1.id
    assert body["items"][0]["status"] == "PENDING"
    # pending 行 → overdue_hours 应为数值（>=0）
    assert body["items"][0]["overdue_hours"] is not None
    assert body["items"][0]["overdue_hours"] >= 0
    # pending_count == pending tab total
    assert body["pending_count"] == 1


def test_pending_tab_excludes_when_no_role(client, db_session, seed_invoice_flow):
    """无 FINANCE 角色 → pending tab 不返任何行，pending_count=0。"""
    flow, node = seed_invoice_flow
    inv = _make_invoice(db_session, team_id=1)
    _make_approval(db_session, BusinessType.INVOICE, inv.id, 1, node)

    r = client.get("/v1/approvals?tab=pending")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 0
    assert body["pending_count"] == 0


def test_pending_tab_excludes_non_pending(
    client, db_session, seed_invoice_flow, seed_finance_role,
):
    """pending tab 仅返 PENDING；APPROVED/REJECTED/CANCELLED 不返。"""
    flow, node = seed_invoice_flow
    inv = _make_invoice(db_session, team_id=1)
    _make_approval(
        db_session, BusinessType.INVOICE, inv.id, 1, node,
        status=ApprovalStatus.APPROVED,
    )
    r = client.get("/v1/approvals?tab=pending")
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 0


# ---------- tab=processed：我已处理（APPROVE/REJECT 记录，排除 SUBMIT）----

def test_processed_tab_returns_only_approver_records(
    client, db_session, seed_invoice_flow, seed_finance_role, current_user_rec,
):
    """processed tab：仅返当前用户留下过 APPROVE/REJECT 记录的审批（排除 SUBMIT）。"""
    flow, node = seed_invoice_flow
    inv = _make_invoice(db_session, team_id=1)
    ap = _make_approval(db_session, BusinessType.INVOICE, inv.id, 1, node)
    # 追加一条 APPROVE 记录由 current_user 完成
    _add_approve_record(
        db_session, ap, node, str(current_user_rec.id), current_user_rec.name
    )

    r = client.get("/v1/approvals?tab=processed")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["business_id"] == inv.id


def test_processed_tab_excludes_submit_only(
    client, db_session, seed_invoice_flow, seed_finance_role,
):
    """只有 SUBMIT 记录（自己提交的）的审批不出现在 processed tab。"""
    flow, node = seed_invoice_flow
    inv = _make_invoice(db_session, team_id=1)
    # submitter_id='1' == current_user → 仅 SUBMIT 记录
    _make_approval(db_session, BusinessType.INVOICE, inv.id, 1, node, submitter_id="1")

    r = client.get("/v1/approvals?tab=processed")
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 0


# ---------- tab=submitted：我提交的（所有状态）----------------------------

def test_submitted_tab_returns_user_submissions_all_status(
    client, db_session, seed_invoice_flow, seed_finance_role,
):
    """submitted tab：仅返 submitter_id == 当前用户 的审批，含所有状态。"""
    flow, node = seed_invoice_flow
    # 自己提交 + 已通过
    inv1 = _make_invoice(db_session, team_id=1)
    _make_approval(
        db_session, BusinessType.INVOICE, inv1.id, 1, node,
        submitter_id="1", status=ApprovalStatus.APPROVED,
    )
    # 自己提交 + 已驳回
    inv2 = _make_invoice(db_session, team_id=1)
    _make_approval(
        db_session, BusinessType.INVOICE, inv2.id, 1, node,
        submitter_id="1", status=ApprovalStatus.REJECTED,
    )
    # 他人提交 —— 不应出现
    inv3 = _make_invoice(db_session, team_id=1)
    _make_approval(
        db_session, BusinessType.INVOICE, inv3.id, 1, node,
        submitter_id="999", status=ApprovalStatus.PENDING,
    )

    r = client.get("/v1/approvals?tab=submitted")
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [it["business_id"] for it in body["items"]]
    assert inv1.id in ids
    assert inv2.id in ids
    assert inv3.id not in ids
    assert body["total"] == 2


# ---------- 跨 team 隔离 ---------------------------------------------------

def test_cross_team_isolation(
    client, db_session, seed_invoice_flow_team2, seed_finance_role,
):
    """team_id=1 的请求看不到 team_id=2 的审批（即使角色相同）。"""
    flow_t2, node_t2 = seed_invoice_flow_team2
    inv_t2 = _make_invoice(db_session, team_id=2)
    _make_approval(
        db_session, BusinessType.INVOICE, inv_t2.id, 2, node_t2,
        submitter_id="1", status=ApprovalStatus.PENDING,
    )

    # 当前请求 team_id=1（fixture override）
    r = client.get("/v1/approvals?tab=pending")
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [it["business_id"] for it in body["items"]]
    assert inv_t2.id not in ids
    assert body["total"] == 0

    r = client.get("/v1/approvals?tab=submitted")
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [it["business_id"] for it in body["items"]]
    assert inv_t2.id not in ids
    assert body["total"] == 0


# ---------- overdue_hours 计算 --------------------------------------------

def test_overdue_hours_computed_for_pending(
    client, db_session, seed_invoice_flow, seed_finance_role,
):
    """PENDING 行 overdue_hours = (now - created_time)/3600，非 PENDING 行为 None。"""
    flow, node = seed_invoice_flow
    inv = _make_invoice(db_session, team_id=1)
    # 创建时间设为 3 天前 → overdue_hours ≈ 72
    old_time = datetime.now() - timedelta(hours=72)
    _make_approval(
        db_session, BusinessType.INVOICE, inv.id, 1, node,
        created_time=old_time, status=ApprovalStatus.PENDING,
    )

    r = client.get("/v1/approvals?tab=pending")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    oh = body["items"][0]["overdue_hours"]
    assert oh is not None
    # 允许 ±2 小时误差（测试运行耗时）
    assert 70 <= oh <= 73


def test_overdue_hours_none_for_non_pending(
    client, db_session, seed_invoice_flow, seed_finance_role,
):
    """非 PENDING 行 overdue_hours 为 None（submitted tab 看已通过审批）。"""
    flow, node = seed_invoice_flow
    inv = _make_invoice(db_session, team_id=1)
    _make_approval(
        db_session, BusinessType.INVOICE, inv.id, 1, node,
        submitter_id="1", status=ApprovalStatus.APPROVED,
    )
    r = client.get("/v1/approvals?tab=submitted")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["items"][0]["overdue_hours"] is None


# ---------- pending_count 任意 tab 都携带 ---------------------------------

def test_pending_count_carried_in_all_tabs(
    client, db_session, seed_invoice_flow, seed_finance_role,
):
    """任意 tab 响应都附 pending_count（待我审批总数），供侧边栏徽章。"""
    flow, node = seed_invoice_flow
    # 2 条 pending
    inv1 = _make_invoice(db_session, team_id=1)
    _make_approval(db_session, BusinessType.INVOICE, inv1.id, 1, node)
    inv2 = _make_invoice(db_session, team_id=1)
    _make_approval(db_session, BusinessType.INVOICE, inv2.id, 1, node)

    for tab in ("pending", "processed", "submitted"):
        r = client.get(f"/v1/approvals?tab={tab}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["pending_count"] == 2, f"tab={tab} pending_count should be 2"


# ---------- business_type 过滤 ---------------------------------------------

def test_business_type_filter(
    client, db_session, seed_invoice_flow, seed_finance_role,
):
    """business_type=INVOICE 过滤生效，仅返 INVOICE 行。"""
    flow, node = seed_invoice_flow
    inv = _make_invoice(db_session, team_id=1)
    _make_approval(db_session, BusinessType.INVOICE, inv.id, 1, node)

    r = client.get("/v1/approvals?tab=pending&business_type=INVOICE")
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1

    r = client.get("/v1/approvals?tab=pending&business_type=CONTRACT")
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 0


def test_invalid_business_type_rejected(client):
    r = client.get("/v1/approvals?tab=pending&business_type=UNKNOWN")
    assert r.status_code == 400


def test_invalid_tab_rejected(client):
    r = client.get("/v1/approvals?tab=invalid")
    assert r.status_code == 400


# ---------- entity 摘要内存 join ------------------------------------------

def test_entity_summary_invoice_join(
    client, db_session, seed_invoice_flow, seed_finance_role,
):
    """INVOICE 行的 application_number/entity_name/entity_amount 由内存 join 填充。"""
    flow, node = seed_invoice_flow
    inv = _make_invoice(db_session, team_id=1)
    _make_approval(db_session, BusinessType.INVOICE, inv.id, 1, node)

    r = client.get("/v1/approvals?tab=pending")
    assert r.status_code == 200, r.text
    item = r.json()["items"][0]
    assert item["application_number"] == inv.application_number
    assert item["entity_name"] == "测试公司"
    assert item["entity_amount"] == 5000.0


def test_entity_summary_payment_join(
    client, db_session, seed_invoice_flow, seed_finance_role,
):
    """PAYMENT 行 application_number=PAY-{id}，entity_amount=actual_amount，entity_name=None。"""
    flow, node = seed_invoice_flow
    pr = PaymentRecord(
        team_id=1,
        record_number="",
        payment_plan_id=1,
        actual_amount=Decimal("12000"),
        payment_date=datetime.now().date(),
        creator_id="1",
        creator_name="登记人",
        confirmation_status=PaymentConfirmationStatus.PENDING,
    )
    db_session.add(pr)
    db_session.commit()
    _make_approval(db_session, BusinessType.PAYMENT, pr.id, 1, node)

    r = client.get("/v1/approvals?tab=pending")
    assert r.status_code == 200, r.text
    item = next(it for it in r.json()["items"] if it["business_type"] == "PAYMENT")
    assert item["application_number"] == f"PAY-{pr.id}"
    assert item["entity_name"] is None
    assert item["entity_amount"] == 12000.0


def test_payment_application_number_fallback_is_filterable_on_sqlite(
    client, db_session, seed_invoice_flow, seed_finance_role,
):
    """PAY-{id} fallback must compile on every supported SQLAlchemy dialect."""
    _flow, node = seed_invoice_flow
    record = PaymentRecord(
        team_id=1,
        record_number="",
        payment_plan_id=1,
        actual_amount=Decimal("12000"),
        payment_date=datetime.now().date(),
        creator_id="1",
        creator_name="登记人",
        confirmation_status=PaymentConfirmationStatus.PENDING,
    )
    db_session.add(record)
    db_session.commit()
    _make_approval(db_session, BusinessType.PAYMENT, record.id, 1, node)

    response = client.get(
        "/v1/approvals",
        params={
            "tab": "pending",
            "filters": json.dumps([
                {
                    "field": "application_number",
                    "op": "eq",
                    "value": f"PAY-{record.id}",
                },
            ]),
            "sorts": "[]",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["application_number"] == f"PAY-{record.id}"


def test_entity_summary_contract_join(
    client, db_session, seed_invoice_flow, seed_finance_role,
):
    """CONTRACT 行 application_number=contract_number，entity_name=contract_name，entity_amount=total_amount。"""
    flow, node = seed_invoice_flow
    c = Contract(
        team_id=1,
        contract_number="CON-2026-001",
        contract_name="某合同",
        customer_id=1,
        opportunity_id=1,
        signing_contact_id=1,
        user_count=10,
        total_amount=Decimal("88888"),
        license_type="SUBSCRIPTION",
        standard_unit_price=Decimal("8888"),
        status=ContractStatus.PENDING_REVIEW,
        owner_id="1",
        creator_id="1",
    )
    db_session.add(c)
    db_session.commit()
    _make_approval(db_session, BusinessType.CONTRACT, c.id, 1, node)

    r = client.get("/v1/approvals?tab=pending")
    assert r.status_code == 200, r.text
    item = next(it for it in r.json()["items"] if it["business_type"] == "CONTRACT")
    assert item["application_number"] == "CON-2026-001"
    assert item["entity_name"] == "某合同"
    assert item["entity_amount"] == 88888.0


def test_entity_summary_opportunity_uses_persisted_number(
    client, db_session, seed_invoice_flow, seed_finance_role,
):
    """OPPORTUNITY 行的 application_number 来自 crm_opportunities.opportunity_number。"""
    flow, node = seed_invoice_flow
    opp = _make_opportunity(db_session, team_id=1)
    _make_approval(db_session, BusinessType.OPPORTUNITY, opp.id, 1, node)

    r = client.get("/v1/approvals?tab=pending")
    assert r.status_code == 200, r.text
    item = next(it for it in r.json()["items"] if it["business_type"] == "OPPORTUNITY")
    assert item["application_number"] == opp.opportunity_number
    assert item["entity_name"] == "统一编号商机"
    assert item["entity_amount"] == 66000.0


# ---------- 统一字段目录协议 -----------------------------------------------

def test_unified_query_filters_and_sorts_derived_summary_fields(
    client, db_session, seed_invoice_flow, seed_finance_role,
):
    """摘要字段必须在 SQL 层参与全量筛选、排序和分页。"""
    _flow, node = seed_invoice_flow

    first = _make_invoice(db_session, team_id=1)
    first.invoice_title_text = "甲公司"
    first.invoice_amount = Decimal("5000")
    db_session.commit()
    _make_approval(db_session, BusinessType.INVOICE, first.id, 1, node)

    second = _make_invoice(db_session, team_id=1)
    second.invoice_title_text = "乙公司"
    second.invoice_amount = Decimal("9000")
    db_session.commit()
    _make_approval(db_session, BusinessType.INVOICE, second.id, 1, node)

    response = client.get(
        "/v1/approvals",
        params={
            "tab": "pending",
            "filters": json.dumps([
                {"field": "entity_name", "op": "contains", "value": "公司"},
            ]),
            "sorts": json.dumps([
                {"field": "entity_amount", "direction": "desc"},
            ]),
            "page": 1,
            "page_size": 1,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 2
    assert [item["entity_name"] for item in payload["items"]] == ["乙公司"]
    assert payload["items"][0]["entity_amount"] == 9000.0


def test_unified_query_does_not_read_summary_from_another_team(
    client, db_session, seed_invoice_flow, seed_finance_role,
):
    """审批派生字段只能读取审批所属团队的业务实体。"""
    _flow, node = seed_invoice_flow
    foreign_invoice = _make_invoice(db_session, team_id=2)
    foreign_invoice.invoice_title_text = "跨团队机密公司"
    db_session.commit()
    _make_approval(db_session, BusinessType.INVOICE, foreign_invoice.id, 1, node)

    response = client.get(
        "/v1/approvals",
        params={
            "tab": "pending",
            "filters": json.dumps([
                {"field": "entity_name", "op": "contains", "value": "机密"},
            ]),
            "sorts": "[]",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 0
    assert response.json()["items"] == []


def test_unified_query_does_not_mix_or_validate_legacy_filters(
    client, db_session, seed_invoice_flow, seed_finance_role,
):
    """显式统一协议只保留 tab/权限 scope，不叠加旧业务筛选参数。"""
    _flow, node = seed_invoice_flow
    invoice = _make_invoice(db_session, team_id=1)
    _make_approval(db_session, BusinessType.INVOICE, invoice.id, 1, node)

    response = client.get(
        "/v1/approvals",
        params={
            "tab": "pending",
            "business_type": "CONTRACT",
            "status": ApprovalStatus.REJECTED,
            "submitter_name": "不存在的提交人",
            "filters": "[]",
            "sorts": "[]",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert [item["business_type"] for item in response.json()["items"]] == [BusinessType.INVOICE]


def test_unified_query_rejects_unknown_approval_field(
    client, db_session, seed_invoice_flow, seed_finance_role,
):
    """未知字段不能静默忽略，HTTP 边界统一返回 400。"""
    _flow, node = seed_invoice_flow
    invoice = _make_invoice(db_session, team_id=1)
    _make_approval(db_session, BusinessType.INVOICE, invoice.id, 1, node)

    response = client.get(
        "/v1/approvals",
        params={
            "tab": "pending",
            "filters": json.dumps([
                {"field": "missing_field", "op": "eq", "value": "x"},
            ]),
            "sorts": "[]",
        },
    )

    assert response.status_code == 400
    assert "missing_field" in response.json()["detail"]


def test_pending_empty_sorts_defaults_to_overdue_hours_desc(
    client, db_session, seed_invoice_flow, seed_finance_role,
):
    """pending 显式新协议未选排序时，仍按超时小时数倒序。"""
    _flow, node = seed_invoice_flow
    now = datetime.now()

    recent = _make_invoice(db_session, team_id=1)
    recent_approval = _make_approval(
        db_session,
        BusinessType.INVOICE,
        recent.id,
        1,
        node,
        created_time=now - timedelta(hours=2),
    )
    overdue = _make_invoice(db_session, team_id=1)
    overdue_approval = _make_approval(
        db_session,
        BusinessType.INVOICE,
        overdue.id,
        1,
        node,
        created_time=now - timedelta(hours=30),
    )

    response = client.get(
        "/v1/approvals",
        params={"tab": "pending", "filters": "[]", "sorts": "[]"},
    )

    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["items"]] == [
        overdue_approval.id,
        recent_approval.id,
    ]
