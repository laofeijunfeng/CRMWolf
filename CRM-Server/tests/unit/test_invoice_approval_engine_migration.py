"""Task B2：发票审批迁移到通用引擎的单元测试。

覆盖（对齐 brief 的三条契约）:
- E7-1: 旧发票经通用 submit → approve 后 status=APPROVED，mark_issued 可执行并切到 ISSUED。
- E7-2: mark_issued 在无 Approval / Approval 仍 PENDING 时阻断（依赖引擎审批通过）。
- E7-3: 旧 POST /v1/invoice-applications/{id}/review 端点硬废弃 → 404。

测试通过直接调 approval_crud + invoice_application_crud（绕过 HTTP 权限层），
保证引擎/单据状态机正确，由 C1/C2/C5 阶段再覆盖端到端权限层。
"""
import pytest
from datetime import datetime
from types import SimpleNamespace

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
from app.core import deps
from app.api.invoices import invoice_router

from app.constants.business_types import BusinessType
from app.crud.approval import approval_crud, approval_flow_crud
from app.crud.invoice import invoice_application_crud
from app.models.approval import (
    Approval, ApprovalRecord, ApprovalFlow, ApprovalNode,
    ApprovalStatus,
)
from app.models.invoice import (
    InvoiceApplication, InvoiceApplicationStatus, InvoiceType,
)
from app.models.user import User, UserStatus
from app.schemas.approval import ApprovalActionRequest


# ---------- DB fixtures ----------------------------------------------------

@pytest.fixture(scope="function")
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        User.__table__,
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


def _current_user_stub():
    class _U:
        id = 1
        name = "财务张"
        status = "active"
    return _U()


@pytest.fixture
def patched_perms(monkeypatch):
    """注入当前用户具备的权限码集合（绕过 permissions 表查询）。"""
    def _set(perms):
        def _fake(db, user_id, team_id=None):
            return [SimpleNamespace(code=p) for p in perms]
        monkeypatch.setattr("app.core.deps.permission_crud.get_user_permissions", _fake)
    return _set


@pytest.fixture
def app(db_session):
    app_ = FastAPI()
    # invoice_router 自带 prefix=/invoice-applications；外层加 /v1 对齐 app/main.py 注册路径
    app_.include_router(invoice_router, prefix="/v1")
    app_.dependency_overrides[deps.get_db] = lambda: db_session
    app_.dependency_overrides[deps.get_current_active_user] = lambda: _current_user_stub()
    app_.dependency_overrides[deps.get_current_user_team] = lambda: 1
    yield app_
    app_.dependency_overrides.clear()


@pytest.fixture
def client(app):
    # raise_server_exceptions=False：旧 /review 端点删除前，handler 内部
    # _populate_application_info 会查 crm_customers 等表（本测试只建 invoice/approval
    # 表），server 抛 OperationalError → TestClient 映射 500。删除后路由不存在 → 404。
    # 两种态都可被 `assert status_code == 404` 区分（500≠404 失败、404 通过）。
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---------- 种子 fixtures --------------------------------------------------

@pytest.fixture
def seed_invoice_draft(db_session):
    """一条 DRAFT 发票申请，team_id=1。"""
    inv = InvoiceApplication(
        team_id=1,
        application_number="INV-2026-0001",
        customer_id=1,
        contract_id=1,
        opportunity_id=1,
        payment_plan_id=1,
        invoice_amount=10000,
        invoice_type=InvoiceType.VAT_NORMAL,
        status=InvoiceApplicationStatus.DRAFT,
        applicant_id="1",
        invoice_title_type="COMPANY",
        invoice_title_text="测试公司",
        invoice_taxpayer_id="91110000ABC",
    )
    db_session.add(inv)
    db_session.commit()
    return inv


@pytest.fixture
def seed_invoice_pending_review(db_session):
    """一条 PENDING_REVIEW 发票，用于测旧 /review 端点 404。"""
    inv = InvoiceApplication(
        team_id=1,
        application_number="INV-2026-PEND-0001",
        customer_id=1,
        contract_id=1,
        opportunity_id=1,
        payment_plan_id=1,
        invoice_amount=20000,
        invoice_type=InvoiceType.VAT_NORMAL,
        status=InvoiceApplicationStatus.PENDING_REVIEW,
        applicant_id="1",
        invoice_title_type="COMPANY",
        invoice_title_text="测试公司",
        invoice_taxpayer_id="91110000ABC",
    )
    db_session.add(inv)
    db_session.commit()
    return inv


@pytest.fixture
def seed_flow_invoice(db_session):
    """一条 INVOICE 类型审批流程 + 单节点（approve_role=FINANCE）。"""
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


# ---------- E7-1: 经通用 submit→approve 后 APPROVED + mark_issued 可执行 ----

def test_invoice_via_engine_becomes_approved(
    db_session, seed_invoice_draft, seed_flow_invoice,
):
    flow, _node = seed_flow_invoice

    # 通用 submit：建 Approval(PENDING) + on_submit 切 invoice.status=PENDING_REVIEW
    ap = approval_crud.create_approval_generic(
        db_session, BusinessType.INVOICE,
        seed_invoice_draft.id, seed_invoice_draft.team_id,
        flow, "1", "申请人",
    )
    assert ap.status == ApprovalStatus.PENDING

    db_session.expire_all()
    inv = db_session.query(InvoiceApplication).filter(
        InvoiceApplication.id == seed_invoice_draft.id
    ).one()
    assert inv.status == InvoiceApplicationStatus.PENDING_REVIEW

    # 通用 approve： approval.status=APPROVED + 适配器 on_approved 写 invoice.status=APPROVED
    ap = approval_crud.approve(
        db_session, ap,
        ApprovalActionRequest(action="APPROVE", comment="ok"),
        "2", "财务张",
    )
    assert ap.status == ApprovalStatus.APPROVED

    db_session.expire_all()
    inv = db_session.query(InvoiceApplication).filter(
        InvoiceApplication.id == seed_invoice_draft.id
    ).one()
    assert inv.status == InvoiceApplicationStatus.APPROVED
    assert inv.reviewed_time is not None  # 适配器 on_approved 回写快照

    # mark_issued：依赖引擎 Approval.status==APPROVED，可执行
    issued = invoice_application_crud.mark_issued(
        db_session, seed_invoice_draft.id, team_id=seed_invoice_draft.team_id,
    )
    db_session.refresh(issued)
    assert issued.status == InvoiceApplicationStatus.ISSUED


# ---------- E7-2a: 无 Approval 时 mark_issued 阻断 ----------------------------

def test_mark_issued_blocked_without_approval(db_session, seed_invoice_draft):
    # 强制发票先置 APPROVED，但不建 Approval → mark_issued 必须仍阻断
    seed_invoice_draft.status = InvoiceApplicationStatus.APPROVED
    db_session.commit()

    with pytest.raises(ValueError, match="发票未通过审批"):
        invoice_application_crud.mark_issued(
            db_session, seed_invoice_draft.id, team_id=seed_invoice_draft.team_id,
        )


# ---------- E7-2b: Approval 仍 PENDING 时 mark_issued 阻断 --------------------

def test_mark_issued_blocked_when_approval_pending(
    db_session, seed_invoice_draft, seed_flow_invoice,
):
    flow, _ = seed_flow_invoice
    approval_crud.create_approval_generic(
        db_session, BusinessType.INVOICE,
        seed_invoice_draft.id, seed_invoice_draft.team_id,
        flow, "1", "申请人",
    )  # Approval.status=PENDING，invoice.status=PENDING_REVIEW

    with pytest.raises(ValueError, match="发票未通过审批"):
        invoice_application_crud.mark_issued(
            db_session, seed_invoice_draft.id, team_id=seed_invoice_draft.team_id,
        )


# ---------- E7-3: 旧 /review 端点硬废弃 → 404 -------------------------------

def test_legacy_review_endpoint_removed(client, seed_invoice_pending_review, patched_perms):
    # 注入 invoice:approve 权限，避免 require_permission 在权限层就 403/500 干扰。
    # 端点删除前：路由存在 → 进入 handler 走 review CRUD → 200。
    # 端点删除后：路由不存在 → FastAPI 返 404（测试期望值）。
    patched_perms(["invoice:approve"])
    r = client.post(
        f"/v1/invoice-applications/{seed_invoice_pending_review.id}/review",
        json={"action": "approve", "comment": ""},
    )
    # 路由已删除（硬废弃） → FastAPI 返 404
    assert r.status_code == 404, r.text