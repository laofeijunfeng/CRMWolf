#!/usr/bin/env python3
"""
Task 1.4: PaymentRecord List Endpoint with approval_status filtering

测试覆盖：
- GET /v1/payments/payment-records 返回 items + total + pending_approval_me_count
- approval_status=pending_submit 筛选（无 approval_id + confirmation_status=PENDING）
- approval_status=pending_approval 筛选（有 approval_id + approval.status=PENDING）
- approval_status=approved 筛选（confirmation_status=CONFIRMED）
- approval_status=rejected 筛选（approval.status=REJECTED）
- pending_approval_me_count 计算逻辑
"""
import pytest
from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.types import BigInteger
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# SQLite 把 BigInteger 编译为 INTEGER
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
    ApprovalStatus,
)
from app.models.contract import Contract, ContractStatus
from app.models.payment import (
    PaymentPlan, PaymentRecord, PaymentPlanStatus, PaymentConfirmationStatus,
)
from app.models.user import User, UserStatus
from app.models.role import Role
from app.models.user_role import UserRole

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
        Role.__table__,
        UserRole.__table__,
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
    """构造 permission_crud.get_user_permissions 的桩"""
    def _fake_get_user_permissions(db, user_id, team_id=None):
        return [SimpleNamespace(code=p) for p in perms]
    return _fake_get_user_permissions


def _role_stub(roles):
    """构造 role_crud.get_user_roles 的桩"""
    def _fake_get_user_roles(db, user_id, team_id=None):
        return [SimpleNamespace(code=r) for r in roles]
    return _fake_get_user_roles


@pytest.fixture
def patched_deps(monkeypatch):
    """返回一个 setter，测试中按需打桩权限和角色"""
    def _set(perms, roles=None):
        monkeypatch.setattr(
            "app.core.deps.permission_crud.get_user_permissions",
            _perm_stub(perms),
        )
        if roles:
            monkeypatch.setattr(
                "app.crud.role.role_crud.get_user_roles",
                _role_stub(roles),
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
    """当前用户记录"""
    u = User(email="finance@example.com", name="财务张", status=UserStatus.ACTIVE)
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def role_finance(db_session):
    """FINANCE 角色"""
    r = Role(name="财务", code="FINANCE")
    db_session.add(r)
    db_session.commit()
    return r


@pytest.fixture
def user_role_finance(db_session, current_user_rec, role_finance):
    """用户-角色关联"""
    ur = UserRole(user_id=current_user_rec.id, role_id=role_finance.id, team_id=1)
    db_session.add(ur)
    db_session.commit()
    return ur


@pytest.fixture
def seed_contract_plan(db_session):
    """Contract + PaymentPlan（不创建 Customer 表，仅使用 customer_id 字段）"""
    contract = Contract(
        team_id=1,
        contract_number="C-2026-001",
        contract_name="测试合同",
        customer_id=1,  # Dummy ID - Customer table not created
        opportunity_id=1,
        signing_contact_id=1,
        user_count=10,
        total_amount=100000,
        license_type="SUBSCRIPTION",
        standard_unit_price=10000,
        status=ContractStatus.SIGNED,
        creator_id="1",
    )
    db_session.add(contract)
    db_session.flush()

    plan = PaymentPlan(
        team_id=1,
        contract_id=contract.id,
        stage_name="首付款",
        planned_amount=50000,
        due_date=date(2026, 8, 1),
        status=PaymentPlanStatus.PENDING,
    )
    db_session.add(plan)
    db_session.commit()
    return contract, plan


@pytest.fixture
def seed_payment_flow(db_session):
    """PAYMENT 类型审批流程 + 单节点"""
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


@pytest.fixture
def seed_payment_records(db_session, seed_contract_plan, seed_payment_flow, current_user_rec):
    """创建多种状态的回款记录"""
    _contract, plan = seed_contract_plan
    flow, node = seed_payment_flow

    records = []

    # 1. pending_submit：无 approval_id，confirmation_status=PENDING
    rec1 = PaymentRecord(
        team_id=1,
        payment_plan_id=plan.id,
        actual_amount=10000,
        payment_date=date(2026, 7, 1),
        creator_id="1",
        creator_name="销售李",
        confirmation_status=PaymentConfirmationStatus.PENDING,
        approval_id=None,
    )
    db_session.add(rec1)
    db_session.flush()
    records.append(("pending_submit", rec1))

    # 2. pending_approval：有 approval_id，approval.status=PENDING
    rec2 = PaymentRecord(
        team_id=1,
        payment_plan_id=plan.id,
        actual_amount=20000,
        payment_date=date(2026, 7, 2),
        creator_id="1",
        creator_name="销售李",
        confirmation_status=PaymentConfirmationStatus.PENDING,
    )
    db_session.add(rec2)
    db_session.flush()

    approval2 = Approval(
        team_id=1,
        business_type=BusinessType.PAYMENT,
        business_id=rec2.id,
        flow_id=flow.id,
        current_node_id=node.id,
        status=ApprovalStatus.PENDING,
        submitter_id="1",
        submitter_name="销售李",
    )
    db_session.add(approval2)
    db_session.flush()
    rec2.approval_id = approval2.id
    db_session.commit()
    records.append(("pending_approval", rec2))

    # 3. approved：confirmation_status=CONFIRMED
    rec3 = PaymentRecord(
        team_id=1,
        payment_plan_id=plan.id,
        actual_amount=30000,
        payment_date=date(2026, 7, 3),
        creator_id="1",
        creator_name="销售李",
        confirmation_status=PaymentConfirmationStatus.CONFIRMED,
        confirmed_by=str(current_user_rec.id),
        confirmed_by_name="财务张",
    )
    db_session.add(rec3)
    db_session.commit()
    records.append(("approved", rec3))

    # 4. rejected：approval.status=REJECTED
    rec4 = PaymentRecord(
        team_id=1,
        payment_plan_id=plan.id,
        actual_amount=5000,
        payment_date=date(2026, 7, 4),
        creator_id="1",
        creator_name="销售李",
        confirmation_status=PaymentConfirmationStatus.PENDING,
    )
    db_session.add(rec4)
    db_session.flush()

    approval4 = Approval(
        team_id=1,
        business_type=BusinessType.PAYMENT,
        business_id=rec4.id,
        flow_id=flow.id,
        current_node_id=node.id,
        status=ApprovalStatus.REJECTED,
        submitter_id="1",
        submitter_name="销售李",
    )
    db_session.add(approval4)
    db_session.flush()
    rec4.approval_id = approval4.id
    db_session.commit()
    records.append(("rejected", rec4))

    return records


# ---------- Tests ----------------------------------------------------------

def test_payment_record_list_all(client, patched_deps):
    """Test PaymentRecord list endpoint returns all records"""
    patched_deps(["payment:view"])
    response = client.get("/v1/payments/payment-records")
    assert response.status_code == 200, response.text
    data = response.json()

    assert "items" in data
    assert "total" in data
    assert "pending_approval_me_count" in data


def test_payment_record_list_includes_record_number(
    client, patched_deps, monkeypatch
):
    """回款记录列表应返回数据库中已生成的 PAY 编号"""
    patched_deps(["payment:view:all"])
    record = SimpleNamespace(
        id=1,
        payment_plan_id=1,
        record_number="PAY202607130001",
        actual_amount=10000,
        payment_date=date(2026, 7, 13),
        proof_attachment=None,
        notes=None,
        creator_id="1",
        creator_name="销售李",
        confirmation_status=PaymentConfirmationStatus.PENDING,
        created_time=datetime(2026, 7, 13, 10, 0, 0),
        approval_id=None,
        approval=None,
        payment_plan=None,
    )
    monkeypatch.setattr(
        "app.api.payments.payment_record_crud.list_records",
        lambda *args, **kwargs: ([record], 1),
    )
    monkeypatch.setattr(
        "app.api.payments.query_pending_approval_me",
        lambda *args, **kwargs: 0,
    )

    response = client.get("/v1/payments/payment-records")
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["record_number"] == record.record_number


def test_payment_record_list_filter_pending_submit(
    client, seed_payment_records, patched_deps
):
    """Test filtering by pending_submit approval status"""
    patched_deps(["payment:view"])
    response = client.get("/v1/payments/payment-records?approval_status=pending_submit")
    assert response.status_code == 200, response.text
    data = response.json()

    # pending_submit：无 approval_id 且 confirmation_status=PENDING
    for item in data["items"]:
        assert item.get("approval_id") is None
        assert item.get("confirmation_status") == "PENDING"


def test_payment_record_list_filter_pending_approval(
    client, seed_payment_records, patched_deps
):
    """Test filtering by pending_approval approval status"""
    patched_deps(["payment:view"])
    response = client.get("/v1/payments/payment-records?approval_status=pending_approval")
    assert response.status_code == 200, response.text
    data = response.json()

    # pending_approval：有 approval_id 且 approval.status=PENDING
    for item in data["items"]:
        assert item.get("approval_id") is not None
        # approval info should be included
        if item.get("approval"):
            assert item["approval"]["status"] == "PENDING"


def test_payment_record_list_filter_approved(
    client, seed_payment_records, patched_deps
):
    """Test filtering by approved status"""
    patched_deps(["payment:view"])
    response = client.get("/v1/payments/payment-records?approval_status=approved")
    assert response.status_code == 200, response.text
    data = response.json()

    # approved：confirmation_status=CONFIRMED
    for item in data["items"]:
        assert item.get("confirmation_status") == "CONFIRMED"


def test_payment_record_list_filter_rejected(
    client, seed_payment_records, patched_deps
):
    """Test filtering by rejected status"""
    patched_deps(["payment:view"])
    response = client.get("/v1/payments/payment-records?approval_status=rejected")
    assert response.status_code == 200, response.text
    data = response.json()

    # rejected：approval.status=REJECTED
    for item in data["items"]:
        if item.get("approval"):
            assert item["approval"]["status"] == "REJECTED"


def test_payment_record_list_pending_approval_me_count(
    client, seed_payment_records, patched_deps, user_role_finance
):
    """Test pending_approval_me_count calculation"""
    patched_deps(["payment:view"], ["FINANCE"])
    response = client.get("/v1/payments/payment-records")
    assert response.status_code == 200, response.text
    data = response.json()

    # pending_approval_me_count should be a number >= 0
    assert isinstance(data["pending_approval_me_count"], int)
    assert data["pending_approval_me_count"] >= 0

    # With FINANCE role and pending_approval record, should count at least 1
    # (seed_payment_records has one pending_approval record)
    assert data["pending_approval_me_count"] >= 1


def test_payment_record_list_includes_approval_info(
    client, seed_payment_records, patched_deps
):
    """Test that approval info is included in response"""
    patched_deps(["payment:view"])
    response = client.get("/v1/payments/payment-records")
    assert response.status_code == 200, response.text
    data = response.json()

    # Items with approval_id should have approval info
    for item in data["items"]:
        if item.get("approval_id") is not None:
            assert "approval" in item
            approval = item["approval"]
            assert "id" in approval
            assert "status" in approval