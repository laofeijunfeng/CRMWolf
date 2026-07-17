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
