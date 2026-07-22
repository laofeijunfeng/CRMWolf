"""Task A6 / M-3：通用审批 API 端点单元测试。

覆盖：
- POST /v1/approvals/INVOICE/{id}/submit —— 发票提交审批 → 200 + status=PENDING
- POST /v1/approvals/UNKNOWN/1/submit —— 非法 entity_type → 400
- POST /v1/approvals/INVOICE/{id}/approve —— 发票审批通过 → 200 + D3 端点回写
  reviewer_id / review_comment（不扩适配器签名，端点直接补两字段）
- POST /v1/approvals/INVOICE/{id}/approve 非当前节点角色 → 403
- POST /v1/approvals/bulk-approve —— 逐条独立事务，部分成功汇总
- GET  /v1/approvals/INVOICE/{id}/detail —— 返回审批实例
- POST /v1/approvals/INVOICE/{id}/cancel —— 仅提交人可撤回

M-3：payment/invoice 的 :approve:own 自审校验真正生效。
- PAYMENT 自审：submitter==approver 无 payment:approve:own → 403；有 → 通过
- INVOICE 自审：applicant==approver 无 invoice:approve:own → 403；有 → 通过
- 非自审（submitter!=approver）→ 不需 :approve:own，角色校验通过即可
- bulk-approve 自审 403 → failed 条目 reason=detail 文案
"""
import pytest
from datetime import datetime, timedelta, date
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
from app.constants.approval_phase import ApprovalPhase
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
from app.models.payment import PaymentRecord, PaymentConfirmationStatus
from app.models.user import User, UserStatus
from app.models.role import Role
from app.models.user_role import UserRole
from app.models.permission import Permission
from app.models.role_permission import RolePermission


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
        Permission.__table__,
        RolePermission.__table__,
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


def _grant_perm_code(db, role, code, *, resource="x", action="approve", scope="own"):
    """给角色授予一个权限码（建 Permission + RolePermission 行）。

    permission_crud.get_user_permissions 通过 UserRole -> RolePermission -> Permission
    联表取用户权限码，所以必须同时建 Permission 行与 RolePermission 关联。
    """
    perm = Permission(name=code, code=code, resource=resource, action=action, scope=scope)
    db.add(perm)
    db.flush()
    db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.commit()
    return perm


@pytest.fixture
def grant_invoice_approve_own(seed_finance_role_and_link, db_session):
    """给 FINANCE 角色授予 invoice:approve:own —— 让自审批能通过。

    既有 D3 reviewer 回写 / bulk 自审 / 乐观锁冲突等用例的发票 applicant
    都是 current_user，M-3 后自审需 :approve:own，故这些用例需此 fixture。
    """
    return _grant_perm_code(
        db_session, seed_finance_role_and_link, "invoice:approve:own",
        resource="invoice", action="approve", scope="own",
    )


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


@pytest.fixture
def seed_invoice_draft_other_submitter(db_session):
    """一条 DRAFT 发票申请，applicant=他人（非 current_user）—— 用于非自审用例。

    applicant_id 用数字字符串（"9999"）以兼容通知层 int(submitter_id) 转换；
    与 current_user.id（=1）不同即可触发"非自审"路径。
    """
    inv = InvoiceApplication(
        team_id=1,
        application_number="INV-2026-OTHER",
        customer_id=1,
        contract_id=1,
        opportunity_id=1,
        payment_plan_id=1,
        invoice_amount=Decimal("5000"),
        invoice_type=InvoiceType.VAT_NORMAL,
        status=InvoiceApplicationStatus.DRAFT,
        applicant_id="9999",
        invoice_title_type="COMPANY",
        invoice_title_text="测试公司",
        invoice_taxpayer_id="91110000XXXXXXX",
    )
    db_session.add(inv)
    db_session.commit()
    return inv


# ---------- PAYMENT fixtures（M-3） ---------------------------------------

@pytest.fixture
def seed_payment_flow_with_director_node(db_session):
    """PAYMENT 类型审批流程 + 1 个 SALES_DIRECTOR 节点。"""
    flow = ApprovalFlow(
        team_id=1,
        flow_name="回款审批",
        flow_code="PAYMENT_FLOW",
        business_type=BusinessType.PAYMENT,
        is_active=1,
    )
    db_session.add(flow)
    db_session.flush()
    node = ApprovalNode(
        team_id=1,
        flow_id=flow.id,
        node_name="销售总监审批",
        node_code="SALES_DIRECTOR",
        node_order=1,
        approve_role="SALES_DIRECTOR",
        is_required=1,
    )
    db_session.add(node)
    db_session.commit()
    return flow, node


@pytest.fixture
def seed_sales_director_role_and_link(db_session, current_user_rec):
    """创建 SALES_DIRECTOR 角色并把 current_user 关联到 team_id=1（不授任何权限码）。"""
    role = Role(name="销售总监", code="SALES_DIRECTOR")
    db_session.add(role)
    db_session.flush()
    db_session.add(UserRole(user_id=current_user_rec.id, role_id=role.id, team_id=1))
    db_session.commit()
    return role


@pytest.fixture
def seed_payment_record_self(db_session, current_user_rec):
    """一条 PENDING 回款登记，creator=当前用户（自审场景）。"""
    pr = PaymentRecord(
        team_id=1,
        payment_plan_id=1,
        actual_amount=Decimal("5000"),
        payment_date=date(2026, 7, 1),
        creator_id=str(current_user_rec.id),
        creator_name="财务张",
        confirmation_status=PaymentConfirmationStatus.PENDING,
    )
    db_session.add(pr)
    db_session.commit()
    return pr


@pytest.fixture
def seed_payment_record_other(db_session):
    """一条 PENDING 回款登记，creator=他人（非自审场景）。"""
    pr = PaymentRecord(
        team_id=1,
        payment_plan_id=1,
        actual_amount=Decimal("5000"),
        payment_date=date(2026, 7, 1),
        creator_id="other_user",
        creator_name="他人",
        confirmation_status=PaymentConfirmationStatus.PENDING,
    )
    db_session.add(pr)
    db_session.commit()
    return pr


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
    assert seed_invoice_draft.approval_phase == ApprovalPhase.PENDING_REVIEW


def test_invalid_entity_type_rejected(client):
    r = client.post("/v1/approvals/UNKNOWN/1/submit", json={"comment": ""})
    assert r.status_code in (400, 422)


# ---------- approve: D3 端点回写 reviewer_id / review_comment --------------

def test_approve_invoice_writes_reviewer_via_endpoint(
    db_session, client, seed_invoice_draft, seed_invoice_flow_with_finance_node,
    seed_finance_role_and_link, grant_invoice_approve_own, current_user_rec,
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
    seed_finance_role_and_link, grant_invoice_approve_own, current_user_rec,
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


def test_bulk_approve_optimistic_lock_conflict(
    db_session, client, seed_invoice_draft, seed_invoice_flow_with_finance_node,
    seed_finance_role_and_link, grant_invoice_approve_own, current_user_rec,
):
    """E6 乐观锁冲突：审批已被他人处理 → failed reason='已被他人处理'。

    构造一条 INVOICE 审批，先由"他人"直接 approve（updated_time 变化、status=APPROVED），
    再用旧的 updated_time 调 bulk-approve → approval_crud.approve 检测 updated_time 不匹配，
    raise ValueError("审批已被其他用户处理") → bulk 端点映射 reason="已被他人处理"。
    """
    from app.crud.approval import approval_crud
    from app.schemas.approval import ApprovalActionRequest as _AAR
    from app.models.approval import ApprovalAction as _AA

    # 1. 提交发票审批
    r = client.post(
        f"/v1/approvals/INVOICE/{seed_invoice_draft.id}/submit",
        json={"comment": "请审批"},
    )
    assert r.status_code == 200, r.text
    ap = db_session.query(Approval).filter(
        Approval.business_id == seed_invoice_draft.id,
        Approval.business_type == BusinessType.INVOICE,
    ).one()
    original_updated_time = ap.updated_time

    # 2. 模拟"他人先审了"：直接 approve（status=APPROVED）
    req_other = _AAR(
        action=_AA.APPROVE, comment="他人先审了",
        updated_time=original_updated_time,
    )
    approval_crud.approve(
        db_session, ap, req_other,
        approver_id="other_user", approver_name="他人",
    )
    db_session.refresh(ap)
    assert ap.status == ApprovalStatus.APPROVED

    # SQLite 秒级精度下 onupdate 可能不产生新时间戳——手动 +1s 模拟真实 DB
    # 的 updated_time 变化，保证 bulk-approve 传入的旧时间戳与当前值不匹配，
    # 从而触发乐观锁冲突（approval_crud.approve 内的 updated_time 比对）。
    if ap.updated_time == original_updated_time:
        ap.updated_time = original_updated_time + timedelta(seconds=1)
        db_session.commit()
        db_session.refresh(ap)
    assert ap.updated_time != original_updated_time

    # 3. bulk-approve 仍用旧的 updated_time → 乐观锁冲突 → reason="已被他人处理"
    r = client.post(
        "/v1/approvals/bulk-approve",
        json={
            "entity_type": "INVOICE",
            "ids": [seed_invoice_draft.id],
            "action": "APPROVE",
            "comment": "批量通过",
            "updated_times": {
                str(seed_invoice_draft.id): (
                    original_updated_time.isoformat()
                    if original_updated_time else ""
                ),
            },
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success_count"] == 0
    assert len(body["failed"]) == 1
    assert body["failed"][0]["id"] == seed_invoice_draft.id
    assert body["failed"][0]["reason"] == "已被他人处理"


# ---------- M-3: payment/invoice :approve:own 自审校验真正生效 ---------------

def test_approve_invoice_self_without_own_perm_403(
    db_session, client, seed_invoice_draft, seed_invoice_flow_with_finance_node,
    seed_finance_role_and_link,
):
    """INVOICE 自审：applicant==approver 且无 invoice:approve:own → 403。

    FINANCE 角色校验通过，但发票 applicant_id == current_user.id 触发自审，
    缺 invoice:approve:own 权限码 → 403「您没有权限审批自己创建的发票」。
    """
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
    assert r.json()["detail"] == "您没有权限审批自己创建的发票"


def test_approve_invoice_self_with_own_perm_passes(
    db_session, client, seed_invoice_draft, seed_invoice_flow_with_finance_node,
    seed_finance_role_and_link, grant_invoice_approve_own,
):
    """INVOICE 自审：applicant==approver 且有 invoice:approve:own → 200。"""
    r = client.post(
        f"/v1/approvals/INVOICE/{seed_invoice_draft.id}/submit",
        json={"comment": "请审批"},
    )
    assert r.status_code == 200, r.text
    ap = db_session.query(Approval).filter(
        Approval.business_id == seed_invoice_draft.id,
        Approval.business_type == BusinessType.INVOICE,
    ).one()

    r = client.post(
        f"/v1/approvals/INVOICE/{seed_invoice_draft.id}/approve",
        json={
            "action": "APPROVE",
            "comment": "同意开票",
            "updated_time": ap.updated_time.isoformat() if ap.updated_time else None,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "APPROVED"


def test_approve_payment_self_without_own_perm_403(
    db_session, client, seed_payment_record_self,
    seed_payment_flow_with_director_node, seed_sales_director_role_and_link,
):
    """PAYMENT 自审：creator==approver 且无 payment:approve:own → 403。

    SALES_DIRECTOR 角色校验通过，但回款 creator_id == current_user.id 触发自审，
    缺 payment:approve:own 权限码 → 403「您没有权限审批自己创建的回款」。
    """
    r = client.post(
        f"/v1/approvals/PAYMENT/{seed_payment_record_self.id}/submit",
        json={"comment": "请审批"},
    )
    assert r.status_code == 200, r.text

    r = client.post(
        f"/v1/approvals/PAYMENT/{seed_payment_record_self.id}/approve",
        json={"action": "APPROVE", "comment": "同意", "updated_time": None},
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "您没有权限审批自己创建的回款"


def test_approve_payment_self_with_own_perm_passes(
    db_session, client, seed_payment_record_self,
    seed_payment_flow_with_director_node, seed_sales_director_role_and_link,
):
    """PAYMENT 自审：creator==approver 且有 payment:approve:own → 200。"""
    # 授予 payment:approve:own
    _grant_perm_code(
        db_session, seed_sales_director_role_and_link, "payment:approve:own",
        resource="payment", action="approve", scope="own",
    )

    r = client.post(
        f"/v1/approvals/PAYMENT/{seed_payment_record_self.id}/submit",
        json={"comment": "请审批"},
    )
    assert r.status_code == 200, r.text
    ap = db_session.query(Approval).filter(
        Approval.business_id == seed_payment_record_self.id,
        Approval.business_type == BusinessType.PAYMENT,
    ).one()

    r = client.post(
        f"/v1/approvals/PAYMENT/{seed_payment_record_self.id}/approve",
        json={
            "action": "APPROVE",
            "comment": "确认入账",
            "updated_time": ap.updated_time.isoformat() if ap.updated_time else None,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "APPROVED"


def test_approve_non_self_no_own_perm_passes(
    db_session, client, seed_invoice_draft_other_submitter,
    seed_invoice_flow_with_finance_node, seed_finance_role_and_link,
):
    """非自审：submitter!=approver → 不需 :approve:own，角色校验通过即可 → 200。

    发票 applicant_id="other_user" != current_user.id，不触发自审校验，
    即便没有 invoice:approve:own 也能审批（沿用既有角色校验）。
    """
    r = client.post(
        f"/v1/approvals/INVOICE/{seed_invoice_draft_other_submitter.id}/submit",
        json={"comment": "请审批"},
    )
    assert r.status_code == 200, r.text
    ap = db_session.query(Approval).filter(
        Approval.business_id == seed_invoice_draft_other_submitter.id,
        Approval.business_type == BusinessType.INVOICE,
    ).one()

    r = client.post(
        f"/v1/approvals/INVOICE/{seed_invoice_draft_other_submitter.id}/approve",
        json={
            "action": "APPROVE",
            "comment": "同意开票",
            "updated_time": ap.updated_time.isoformat() if ap.updated_time else None,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "APPROVED"


def test_bulk_approve_payment_self_without_own_perm_fails(
    db_session, client, seed_payment_record_self,
    seed_payment_flow_with_director_node, seed_sales_director_role_and_link,
):
    """bulk-approve PAYMENT 自审无 payment:approve:own → failed 条目 reason=detail 文案。

    验证 bulk_approve 泛化自审校验：helper 抛 HTTPException → 转 ValueError →
    计入 failed，reason 为「您没有权限审批自己创建的回款」。
    """
    r = client.post(
        f"/v1/approvals/PAYMENT/{seed_payment_record_self.id}/submit",
        json={"comment": "请审批"},
    )
    assert r.status_code == 200, r.text
    ap = db_session.query(Approval).filter(
        Approval.business_id == seed_payment_record_self.id,
        Approval.business_type == BusinessType.PAYMENT,
    ).one()

    r = client.post(
        "/v1/approvals/bulk-approve",
        json={
            "entity_type": "PAYMENT",
            "ids": [seed_payment_record_self.id],
            "action": "APPROVE",
            "comment": "批量通过",
            "updated_times": {
                str(seed_payment_record_self.id): (
                    ap.updated_time.isoformat() if ap.updated_time else ""
                ),
            },
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success_count"] == 0
    assert len(body["failed"]) == 1
    assert body["failed"][0]["id"] == seed_payment_record_self.id
    assert body["failed"][0]["reason"] == "您没有权限审批自己创建的回款"
