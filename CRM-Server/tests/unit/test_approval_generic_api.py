"""Task A6：通用审批 API 端点单元测试。

覆盖：
- POST /v1/approvals/INVOICE/{id}/submit —— 发票提交审批 → 200 + status=PENDING
- POST /v1/approvals/UNKNOWN/1/submit —— 非法 entity_type → 400
- POST /v1/approvals/INVOICE/{id}/approve —— 发票审批通过 → 200 + D3 端点回写
  reviewer_id / review_comment（不扩适配器签名，端点直接补两字段）
- POST /v1/approvals/INVOICE/{id}/approve 非当前节点角色 → 403
- POST /v1/approvals/bulk-approve —— 逐条独立事务，部分成功汇总
- GET  /v1/approvals/INVOICE/{id}/detail —— 返回审批实例
- POST /v1/approvals/INVOICE/{id}/cancel —— 仅提交人可撤回
"""
import pytest
from datetime import datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.types import BigInteger
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# SQLite 把 BigInteger 编译为 INTEGER，确保 BigInteger 主键在 SQLite 上能自增。
# 仅作用于 sqlite 方言，不影响 MySQL 真实引擎。
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
from app.models.invoice import (
    InvoiceApplication, InvoiceApplicationStatus, InvoiceType,
)
from app.models.user import User, UserStatus
from app.models.role import Role
from app.models.user_role import UserRole


# ---------- DB fixtures ---------------------------------------------------

@pytest.fixture(scope="function")
def db_session():
    """内存 SQLite，仅创建本测试需要的表（避免触发全模型级联建表）。

    用 StaticPool 共享同一 in-memory 连接，跨线程（FastAPI 请求与 fixture
    setup 在不同线程）也能见同样表。否则 :memory: 默认按连接隔离，TestClient
    请求里的 db session 会进入空库导致 "no such table"。
    """
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
    """构造只挂 approvals router 的最小 FastAPI app，依赖全部覆盖到 db_session。"""
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
    """真实写入一条 ACTIVE 用户，供 approve 端点的 current_user.id（int）使用。"""
    u = User(
        email="finance@example.com",
        name="财务张",
        status=UserStatus.ACTIVE,
    )
    db_session.add(u)
    db_session.commit()
    return u


def _current_user_stub():
    """轻量 user stub —— 端点只用 .id / .name / .status。"""
    class _U:
        id = 1
        name = "财务张"
        status = "active"
    return _U()


# ---------- 种子 fixtures --------------------------------------------------

@pytest.fixture
def seed_invoice_flow_with_finance_node(db_session):
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
def seed_finance_role_and_link(db_session, current_user_rec):
    """创建 FINANCE 角色并把 current_user 关联到 team_id=1。"""
    role = Role(name="财务", code="FINANCE")
    db_session.add(role)
    db_session.flush()
    db_session.add(UserRole(user_id=current_user_rec.id, role_id=role.id, team_id=1))
    db_session.commit()
    return role


@pytest.fixture
def seed_invoice_draft(db_session, current_user_rec):
    """一条 DRAFT 发票申请，applicant=当前用户。"""
    inv = InvoiceApplication(
        team_id=1,
        application_number="INV-2026-001",
        customer_id=1,
        contract_id=1,
        opportunity_id=1,
        payment_plan_id=1,
        invoice_amount=Decimal("5000"),
        invoice_type=InvoiceType.VAT_NORMAL,
        status=InvoiceApplicationStatus.DRAFT,
        applicant_id=str(current_user_rec.id),
        invoice_title_type="COMPANY",
        invoice_title_text="测试公司",
        invoice_taxpayer_id="91110000XXXXXXX",
    )
    db_session.add(inv)
    db_session.commit()
    return inv


# ---------- Step 1: submit invoice approval + invalid entity_type ----------

def test_submit_invoice_approval(client, seed_invoice_draft, seed_invoice_flow_with_finance_node):
    r = client.post(
        f"/v1/approvals/INVOICE/{seed_invoice_draft.id}/submit",
        json={"comment": "请审批"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "PENDING"
    assert "approval_id" in body


def test_invalid_entity_type_rejected(client):
    r = client.post("/v1/approvals/UNKNOWN/1/submit", json={"comment": ""})
    assert r.status_code in (400, 422)


# ---------- approve: D3 端点回写 reviewer_id / review_comment --------------

def test_approve_invoice_writes_reviewer_via_endpoint(
    db_session, client, seed_invoice_draft, seed_invoice_flow_with_finance_node,
    seed_finance_role_and_link, current_user_rec,
):
    # 先提交
    r = client.post(
        f"/v1/approvals/INVOICE/{seed_invoice_draft.id}/submit",
        json={"comment": "请审批"},
    )
    assert r.status_code == 200, r.text
    approval_id = r.json()["approval_id"]

    # 取提交后的 updated_time 做乐观锁
    ap = db_session.query(Approval).filter(Approval.id == approval_id).one()
    updated_time = ap.updated_time

    # 审批通过 —— 端点回写 reviewer_id / review_comment
    r = client.post(
        f"/v1/approvals/INVOICE/{seed_invoice_draft.id}/approve",
        json={
            "action": "APPROVE",
            "comment": "同意开票",
            "updated_time": updated_time.isoformat() if updated_time else None,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "APPROVED"

    # 验证 D3 端点回写：发票 reviewer_id / review_comment 已写
    db_session.expire_all()
    inv = db_session.query(InvoiceApplication).filter(
        InvoiceApplication.id == seed_invoice_draft.id
    ).one()
    assert inv.reviewer_id == str(current_user_rec.id)
    assert inv.review_comment == "同意开票"


def test_approve_rejects_non_matching_role(
    db_session, client, seed_invoice_draft, seed_invoice_flow_with_finance_node,
    current_user_rec,
):
    """角色不匹配时 403。"""
    # 不创建 FINANCE 角色 —— current_user 无任何角色
    r = client.post(
        f"/v1/approvals/INVOICE/{seed_invoice_draft.id}/submit",
        json={"comment": "请审批"},
    )
    assert r.status_code == 200, r.text

    r = client.post(
        f"/v1/approvals/INVOICE/{seed_invoice_draft.id}/approve",
        json={"action": "APPROVE", "comment": "同意", "updated_time": None},
    )
    assert r.status_code == 403, r.text


# ---------- cancel: 仅提交人可撤回 ----------------------------------------

def test_cancel_by_submitter(
    db_session, client, seed_invoice_draft, seed_invoice_flow_with_finance_node,
):
    # submitter = current_user（applicant_id = current_user.id）
    r = client.post(
        f"/v1/approvals/INVOICE/{seed_invoice_draft.id}/submit",
        json={"comment": "请审批"},
    )
    assert r.status_code == 200, r.text

    r = client.post(f"/v1/approvals/INVOICE/{seed_invoice_draft.id}/cancel")
    assert r.status_code == 200, r.text
    assert "撤回" in r.json()["message"]


# ---------- detail ---------------------------------------------------------

def test_detail_returns_approval(
    db_session, client, seed_invoice_draft, seed_invoice_flow_with_finance_node,
):
    r = client.post(
        f"/v1/approvals/INVOICE/{seed_invoice_draft.id}/submit",
        json={"comment": "请审批"},
    )
    assert r.status_code == 200, r.text
    approval_id = r.json()["approval_id"]

    r = client.get(f"/v1/approvals/INVOICE/{seed_invoice_draft.id}/detail")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == approval_id
    assert body["status"] == "PENDING"


def test_detail_not_found(client):
    r = client.get("/v1/approvals/INVOICE/999999/detail")
    assert r.status_code == 404, r.text


# ---------- E6 bulk-approve: 逐条独立事务 + 部分成功汇总 -------------------

def test_bulk_approve_partial_success(
    db_session, client, seed_invoice_draft, seed_invoice_flow_with_finance_node,
    seed_finance_role_and_link, current_user_rec,
):
    """逐条独立事务：一条成功 + 一条不存在汇总失败。"""
    # 第 1 条：提交一份发票
    r = client.post(
        f"/v1/approvals/INVOICE/{seed_invoice_draft.id}/submit",
        json={"comment": "请审批"},
    )
    assert r.status_code == 200, r.text
    ap = db_session.query(Approval).filter(
        Approval.business_id == seed_invoice_draft.id,
        Approval.business_type == BusinessType.INVOICE,
    ).one()
    updated_time = ap.updated_time

    # 第 2 条 ID 不存在 —— 应计入 failed
    r = client.post(
        "/v1/approvals/bulk-approve",
        json={
            "entity_type": "INVOICE",
            "ids": [seed_invoice_draft.id, 888888],
            "action": "APPROVE",
            "comment": "批量通过",
            "updated_times": {
                str(seed_invoice_draft.id): updated_time.isoformat() if updated_time else "",
            },
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success_count"] == 1
    assert len(body["failed"]) == 1
    assert body["failed"][0]["id"] == 888888


def test_bulk_approve_invalid_entity_type(client):
    r = client.post(
        "/v1/approvals/bulk-approve",
        json={"entity_type": "UNKNOWN", "ids": [1], "action": "APPROVE", "comment": ""},
    )
    assert r.status_code == 400