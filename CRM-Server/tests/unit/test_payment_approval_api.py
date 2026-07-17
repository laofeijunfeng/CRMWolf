"""Task B1：回款审批 & 财务确认 API 端点单元测试。

覆盖：
- POST /v1/payments/records/{id}/submit-approval 匹配到流 → 建 Approval + status=PENDING，
  回款 confirmation_status 仍 PENDING（on_submit 语义：PENDING→PENDING）。
- POST /v1/payments/records/{id}/submit-approval 未匹配流（决策1：PAYMENT 返 (None,None)）→
  不建 Approval + 返回 status=NO_FLOW + 回款保持 PENDING（E5 直通财务确认语义）。
- POST /v1/payments/records/{id}/confirm action=confirm → confirmation_status=CONFIRMED +
  confirmed_by 写入当前财务用户。
- 两端点 404（回款记录不存在 / 跨 team）。
"""
import pytest

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
from app.api.payments import router as payments_router

from app.constants.business_types import BusinessType
from app.models.approval import (
    Approval, ApprovalRecord, ApprovalFlow, ApprovalNode,
)
from app.models.contract import Contract, ContractStatus
from app.models.payment import (
    PaymentPlan, PaymentRecord, PaymentPlanStatus, PaymentConfirmationStatus,
)
from app.models.user import User, UserStatus

from types import SimpleNamespace


# ---------- DB fixtures ----------------------------------------------------

@pytest.fixture(scope="function")
def db_session():
    """内存 SQLite + StaticPool（跨线程共享），仅建本测试所需表。"""
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        User.__table__,
        Contract.__table__,
        PaymentPlan.__table__,
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


def _perm_stub(perms):
    """构造一个替换 permission_crud.get_user_permissions 的桩，返回含 .code 的对象。"""
    def _fake_get_user_permissions(db, user_id, team_id=None):
        return [SimpleNamespace(code=p) for p in perms]
    return _fake_get_user_permissions


@pytest.fixture
def patched_perms(monkeypatch):
    """返回一个setter，测试中按需打桩当前用户具备的权限码集合。"""
    def _set(perms):
        # 修补 deps 模块里 import 的 permission_crud 句柄（闭包实际调用点）
        monkeypatch.setattr(
            "app.core.deps.permission_crud.get_user_permissions",
            _perm_stub(perms),
        )
    return _set


@pytest.fixture
def app(db_session):
    app_ = FastAPI()
    app_.include_router(payments_router)
    app_.dependency_overrides[deps.get_db] = lambda: db_session
    app_.dependency_overrides[deps.get_current_active_user] = lambda: _current_user_stub()
    app_.dependency_overrides[deps.get_current_user_team] = lambda: 1
    yield app_
    app_.dependency_overrides.clear()


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def _current_user_stub():
    class _U:
        id = 1
        name = "财务张"
        status = "active"
    return _U()


# ---------- 种子 fixtures --------------------------------------------------

@pytest.fixture
def current_user_rec(db_session):
    u = User(email="finance@example.com", name="财务张", status=UserStatus.ACTIVE)
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def seed_contract_plan(db_session):
    """一条 Contract + PaymentPlan，team_id=1。"""
    contract = Contract(
        team_id=1,
        contract_number="C-2026-001",
        contract_name="测试合同",
        customer_id=1,
        opportunity_id=1,
        signing_contact_id=1,
        user_count=10,
        total_amount=100000,
        license_type="SUBSCRIPTION",
        standard_unit_price=10000,
        status=ContractStatus.SIGNED,
        owner_id="1",
        creator_id="1",
    )
    db_session.add(contract)
    db_session.flush()

    plan = PaymentPlan(
        team_id=1,
        contract_id=contract.id,
        stage_name="首付款",
        planned_amount=50000,
        due_date=__import__("datetime").date(2026, 8, 1),
        status=PaymentPlanStatus.PENDING,
    )
    db_session.add(plan)
    db_session.commit()
    return contract, plan


@pytest.fixture
def seed_payment_record(db_session, seed_contract_plan):
    _contract, plan = seed_contract_plan
    record = PaymentRecord(
        team_id=1,
        payment_plan_id=plan.id,
        actual_amount=50000,
        payment_date=__import__("datetime").date(2026, 7, 1),
        creator_id="1",
        creator_name="销售李",
        confirmation_status=PaymentConfirmationStatus.PENDING,
    )
    db_session.add(record)
    db_session.commit()
    return record


@pytest.fixture
def seed_payment_flow(db_session):
    """一条 PAYMENT 类型审批流程 + 单节点。"""
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
        node_name="财务确认",
        node_code="FINANCE",
        node_order=1,
        approve_role="FINANCE",
        is_required=1,
    )
    db_session.add(node)
    db_session.commit()
    return flow, node


# ---------- Step 1: submit-approval 匹配到流 -------------------------------

def test_submit_approval_matched_flow_creates_approval(
    db_session, client, seed_payment_record, seed_payment_flow, patched_perms,
):
    patched_perms(["payment:submit"])
    r = client.post(f"/v1/payments/records/{seed_payment_record.id}/submit-approval")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["approval_id"] is not None
    assert body["status"] == "PENDING"

    # 审批实例已建
    ap = db_session.query(Approval).filter(
        Approval.business_type == BusinessType.PAYMENT,
        Approval.business_id == seed_payment_record.id,
    ).one()
    assert ap.status == "PENDING"

    # E5 / on_submit 语义：回款 confirmation_status 仍 PENDING（未自动 CONFIRMED）
    db_session.expire_all()
    rec = db_session.query(PaymentRecord).filter(
        PaymentRecord.id == seed_payment_record.id
    ).one()
    assert rec.confirmation_status == PaymentConfirmationStatus.PENDING


# ---------- Step 2: submit-approval 未匹配流（E5 直通财务确认）---------------

def test_submit_approval_no_flow_returns_no_flow(
    db_session, client, seed_payment_record, patched_perms,
):
    # 不 seed 任何 PAYMENT 流 → match_flow_generic 返 (None, None)（决策1）
    patched_perms(["payment:submit"])
    r = client.post(f"/v1/payments/records/{seed_payment_record.id}/submit-approval")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["approval_id"] is None
    assert body["status"] == "NO_FLOW"
    assert "财务确认" in body["message"]

    # 不建任何 Approval
    cnt = db_session.query(Approval).filter(
        Approval.business_type == BusinessType.PAYMENT,
        Approval.business_id == seed_payment_record.id,
    ).count()
    assert cnt == 0

    # 回款保持 PENDING（免审批直通财务确认，非自动 CONFIRMED）
    db_session.expire_all()
    rec = db_session.query(PaymentRecord).filter(
        PaymentRecord.id == seed_payment_record.id
    ).one()
    assert rec.confirmation_status == PaymentConfirmationStatus.PENDING


# ---------- Step 3: confirm action=confirm 写入字段 -----------------------

def test_confirm_action_confirm_writes_fields(
    db_session, client, seed_payment_record, patched_perms, current_user_rec,
):
    patched_perms(["payment:confirm"])
    r = client.post(
        f"/v1/payments/records/{seed_payment_record.id}/confirm",
        json={"action": "confirm", "notes": "已到账"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["confirmation_status"] == "CONFIRMED"

    db_session.expire_all()
    rec = db_session.query(PaymentRecord).filter(
        PaymentRecord.id == seed_payment_record.id
    ).one()
    assert rec.confirmation_status == PaymentConfirmationStatus.CONFIRMED
    assert rec.confirmed_by == str(current_user_rec.id)
    assert rec.confirmed_by_name == "财务张"
    assert rec.confirmation_notes == "已到账"


# ---------- Step 4: 404 ---------------------------------------------------

def test_submit_approval_not_found(client, patched_perms):
    patched_perms(["payment:submit"])
    r = client.post("/v1/payments/records/999999/submit-approval")
    assert r.status_code == 404, r.text


def test_confirm_not_found(client, patched_perms):
    patched_perms(["payment:confirm"])
    r = client.post(
        "/v1/payments/records/999999/confirm",
        json={"action": "confirm"},
    )
    assert r.status_code == 404, r.text


def test_confirm_dispute_writes_disputed(
    db_session, client, seed_payment_record, patched_perms, current_user_rec,
):
    patched_perms(["payment:confirm"])
    r = client.post(
        f"/v1/payments/records/{seed_payment_record.id}/confirm",
        json={"action": "dispute", "notes": "金额不符"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["confirmation_status"] == "DISPUTED"

    db_session.expire_all()
    rec = db_session.query(PaymentRecord).filter(
        PaymentRecord.id == seed_payment_record.id
    ).one()
    assert rec.confirmation_status == PaymentConfirmationStatus.DISPUTED
    assert rec.confirmed_by == str(current_user_rec.id)
