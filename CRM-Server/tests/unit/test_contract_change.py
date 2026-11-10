"""CRM-96 contract amount change: request, approval and history behavior."""
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


from app.constants.approval_phase import ApprovalPhase  # noqa: E402
from app.constants.business_types import ALL_BUSINESS_TYPES, BusinessType  # noqa: E402
from app.core.database import Base  # noqa: E402
from app.crud.approval import approval_crud  # noqa: E402
from app.models.approval import (  # noqa: E402
    Approval,
    ApprovalAction,
    ApprovalFlow,
    ApprovalNode,
    ApprovalRecord,
    ApprovalStatus,
)
from app.models.contract import Contract, ContractStatus  # noqa: E402
from app.models.contract_change import ContractChangeRequest  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress  # noqa: E402
from app.models.invoice import InvoiceApplication, InvoiceApplicationStatus  # noqa: E402
from app.models.payment import PaymentPlan, PaymentRecord  # noqa: E402
from app.schemas.approval import ApprovalActionRequest  # noqa: E402
from app.services import approval_transaction_manager as manager_module  # noqa: E402
from app.services import contract_change as contract_change_module  # noqa: E402
from app.services.approval_transaction_manager import approval_transaction_manager  # noqa: E402
from app.services.contract_change import (  # noqa: E402
    ContractChangeAttachment,
    ContractChangeError,
    ContractNotFoundError,
    contract_change_service,
)
from app.services.file_storage import FileStorageService  # noqa: E402

TEAM_ID = 1
OTHER_TEAM_ID = 2
CREATOR_ID = "7"
PENDING_MESSAGE = "已有一条变更在审批中，审批结束前不能再次发起"


@pytest.fixture
def db_session(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        Customer.__table__,
        CustomerLegacySourceProgress.__table__,
        Contract.__table__,
        ApprovalFlow.__table__,
        ApprovalNode.__table__,
        Approval.__table__,
        ApprovalRecord.__table__,
        ContractChangeRequest.__table__,
        PaymentPlan.__table__,
        PaymentRecord.__table__,
        InvoiceApplication.__table__,
    ]
    customer_index = next(index for index in Customer.__table__.indexes if index.name == "idx_team_id")
    Customer.__table__.indexes.discard(customer_index)
    try:
        Base.metadata.create_all(engine, tables=tables)
    finally:
        Customer.__table__.indexes.add(customer_index)
    monkeypatch.setattr(
        manager_module.outbound_notification_job_service,
        "enqueue_pending_for_approval",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(contract_change_module, "file_storage_service", FileStorageService(base_dir=str(tmp_path)))
    session = sessionmaker(bind=engine)()
    session.add(Customer(id=1, team_id=TEAM_ID, account_name="测试客户", city="北京", creator_id="u1"))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_flow(db, *, team_id=TEAM_ID, min_amount=1, max_amount=1_000_000, flow_code="CON_FLOW", nodes=1):
    flow = ApprovalFlow(
        team_id=team_id,
        flow_name=f"合同审批-{flow_code}",
        flow_code=flow_code,
        business_type=BusinessType.CONTRACT,
        min_amount=min_amount,
        max_amount=max_amount,
        is_active=1,
    )
    db.add(flow)
    db.flush()
    for order in range(1, nodes + 1):
        db.add(ApprovalNode(
            team_id=team_id,
            flow_id=flow.id,
            node_name=f"节点{order}",
            node_code=f"{flow_code}_N{order}",
            node_order=order,
            approve_role="SALES_DIRECTOR",
            is_required=1,
        ))
    db.commit()
    return flow


def _make_contract(db, *, team_id=TEAM_ID, total_amount="100000.00", contract_number="CON-CHG-001", **overrides):
    values = dict(
        team_id=team_id,
        contract_number=contract_number,
        contract_name=f"变更测试合同-{contract_number}",
        customer_id=1,
        opportunity_id=1,
        signing_contact_id=1,
        user_count=10,
        total_amount=Decimal(total_amount),
        license_type="SUBSCRIPTION",
        subscription_years=2,
        standard_unit_price=Decimal("5000.00"),
        status=ContractStatus.SIGNED,
        approval_phase=ApprovalPhase.APPROVED.value,
        owner_id=CREATOR_ID,
        creator_id=CREATOR_ID,
    )
    values.update(overrides)
    contract = Contract(**values)
    db.add(contract)
    db.commit()
    db.refresh(contract)
    return contract


def _make_plan(db, contract, *, planned_amount, plan_number="PLAN-1", team_id=TEAM_ID):
    plan = PaymentPlan(
        team_id=team_id,
        contract_id=contract.id,
        plan_number=plan_number,
        stage_name="首付款",
        planned_amount=Decimal(planned_amount),
        due_date=date(2026, 12, 1),
    )
    db.add(plan)
    db.commit()
    return plan


def _make_payment(db, plan, *, amount, record_number="REC-1", phase=ApprovalPhase.APPROVED.value):
    db.add(PaymentRecord(
        team_id=plan.team_id,
        record_number=record_number,
        payment_plan_id=plan.id,
        actual_amount=Decimal(amount),
        payment_date=date(2026, 11, 1),
        creator_id=CREATOR_ID,
        approval_phase=phase,
    ))
    db.commit()


def _make_invoice(db, contract, plan, *, amount, status=InvoiceApplicationStatus.ISSUED, number="INV-1"):
    db.add(InvoiceApplication(
        team_id=contract.team_id,
        application_number=number,
        customer_id=contract.customer_id,
        contract_id=contract.id,
        opportunity_id=1,
        payment_plan_id=plan.id,
        invoice_amount=Decimal(amount),
        invoice_type="VAT_NORMAL",
        status=status,
        applicant_id=CREATOR_ID,
        invoice_title_type="COMPANY",
        invoice_title_text="测试客户",
        invoice_taxpayer_id="91110000000000000X",
    ))
    db.commit()


def _request(db, contract, *, amount="125000.00", actor_id=CREATOR_ID, team_id=TEAM_ID, attachment=None):
    return contract_change_service.create_request(
        db,
        team_id=team_id,
        contract_id=contract.id,
        actor_id=actor_id,
        actor_name="申请人",
        new_amount=Decimal(amount),
        reason="客户扩容",
        attachment=attachment,
    )


def _decide(db, change, action):
    approval = approval_crud.get_pending_by_entity(db, BusinessType.CONTRACT_CHANGE, change.id, TEAM_ID)
    assert approval is not None
    request = ApprovalActionRequest(action=action, comment="意见", updated_time=approval.updated_time)
    return approval_crud.approve(db, approval, request, approver_id="9", approver_name="审批人")


# ---------- request ---------------------------------------------------------

def test_request_keeps_contract_unchanged_while_pending(db_session):
    _make_flow(db_session)
    contract = _make_contract(db_session)

    change = _request(db_session, contract)

    db_session.refresh(contract)
    assert change.approval_phase == ApprovalPhase.PENDING_REVIEW.value
    assert change.change_items_json == [
        {"key": "contract_amount", "old_value": "100000.00", "new_value": "125000.00"},
    ]
    assert contract.total_amount == Decimal("100000.00")
    assert contract.standard_unit_price == Decimal("5000.00")
    assert contract.approval_phase == ApprovalPhase.APPROVED.value
    assert contract.status == ContractStatus.SIGNED
    assert contract_change_service.get_pending(db_session, TEAM_ID, contract.id).id == change.id


def test_request_reuses_contract_flow_without_touching_contract_approvals(db_session):
    flow = _make_flow(db_session)
    contract = _make_contract(db_session)

    change = _request(db_session, contract)

    approvals = db_session.query(Approval).all()
    assert len(approvals) == 1
    assert approvals[0].business_type == BusinessType.CONTRACT_CHANGE
    assert approvals[0].business_id == change.id
    assert approvals[0].flow_id == flow.id
    assert approvals[0].contract_id is None
    assert approval_crud.get_by_entity(db_session, BusinessType.CONTRACT, contract.id, TEAM_ID) is None
    assert BusinessType.CONTRACT_CHANGE not in ALL_BUSINESS_TYPES


def test_flow_matching_uses_larger_of_old_and_new_amount(db_session):
    _make_flow(db_session, min_amount=1, max_amount=100_000, flow_code="SMALL")
    large = _make_flow(db_session, min_amount=100_001, max_amount=1_000_000, flow_code="LARGE")
    contract = _make_contract(db_session, total_amount="200000.00")

    change = _request(db_session, contract, amount="90000.00")

    approval = approval_crud.get_pending_by_entity(db_session, BusinessType.CONTRACT_CHANGE, change.id, TEAM_ID)
    assert approval.flow_id == large.id


def test_request_without_matching_flow_leaves_no_change(db_session):
    contract = _make_contract(db_session)

    with pytest.raises(ContractChangeError, match="合同审批流程"):
        _request(db_session, contract)

    assert db_session.query(ContractChangeRequest).count() == 0


@pytest.mark.parametrize(
    ("overrides", "actor_id"),
    [
        ({}, "8"),
        ({"approval_phase": ApprovalPhase.PENDING_REVIEW.value, "status": ContractStatus.PENDING_REVIEW}, CREATOR_ID),
        ({"status": ContractStatus.TERMINATED}, CREATOR_ID),
    ],
    ids=["not-creator", "not-approved", "terminated"],
)
def test_ineligible_requests_are_rejected(db_session, overrides, actor_id):
    _make_flow(db_session)
    contract = _make_contract(db_session, **overrides)

    with pytest.raises(ContractChangeError):
        _request(db_session, contract, actor_id=actor_id)

    assert db_session.query(ContractChangeRequest).count() == 0


def test_other_team_and_deleted_contracts_are_not_found(db_session):
    _make_flow(db_session)
    _make_flow(db_session, team_id=OTHER_TEAM_ID, flow_code="OTHER")
    contract = _make_contract(db_session)
    deleted = _make_contract(db_session, contract_number="CON-DEL", deleted_at=datetime(2026, 11, 1))

    with pytest.raises(ContractNotFoundError):
        _request(db_session, contract, team_id=OTHER_TEAM_ID)
    with pytest.raises(ContractNotFoundError):
        _request(db_session, deleted)
    assert contract_change_service.list_history(db_session, OTHER_TEAM_ID, contract.id) == []


@pytest.mark.parametrize("amount", ["0", "-1", "100000.00"])
def test_amount_must_be_positive_and_different(db_session, amount):
    _make_flow(db_session)
    contract = _make_contract(db_session)

    with pytest.raises(ContractChangeError):
        _request(db_session, contract, amount=amount)


def test_amount_cannot_drop_below_any_financial_floor(db_session):
    _make_flow(db_session)
    contract = _make_contract(db_session)
    plan = _make_plan(db_session, contract, planned_amount="80000.00")
    _make_payment(db_session, plan, amount="60000.00")
    _make_payment(db_session, plan, amount="99999.00", record_number="REC-PENDING", phase=ApprovalPhase.PENDING_REVIEW.value)
    _make_invoice(db_session, contract, plan, amount="70000.00")
    _make_invoice(db_session, contract, plan, amount="99999.00", status=InvoiceApplicationStatus.APPROVED, number="INV-NOT-ISSUED")

    snapshot = contract_change_service.get_financial_snapshot(db_session, TEAM_ID, contract.id)
    assert (snapshot.paid_amount, snapshot.invoiced_amount, snapshot.planned_amount, snapshot.floor_amount) == (
        Decimal("60000.00"), Decimal("70000.00"), Decimal("80000.00"), Decimal("80000.00"),
    )
    with pytest.raises(ContractChangeError, match="回款计划"):
        _request(db_session, contract, amount="79999.99")

    change = _request(db_session, contract, amount="80000.00")
    assert change.approval_phase == ApprovalPhase.PENDING_REVIEW.value


def test_invoiced_floor_is_named(db_session):
    _make_flow(db_session)
    contract = _make_contract(db_session)
    plan = _make_plan(db_session, contract, planned_amount="10.00")
    _make_invoice(db_session, contract, plan, amount="50000.00")

    with pytest.raises(ContractChangeError, match="已开票"):
        _request(db_session, contract, amount="40000.00")


def test_second_request_is_blocked_while_one_is_pending(db_session):
    _make_flow(db_session)
    contract = _make_contract(db_session)
    _request(db_session, contract)

    with pytest.raises(ContractChangeError, match=PENDING_MESSAGE):
        _request(db_session, contract, amount="130000.00")

    assert db_session.query(ContractChangeRequest).count() == 1


def test_attachment_is_optional_but_limited_to_pdf_or_docx(db_session):
    _make_flow(db_session)
    contract = _make_contract(db_session)

    with pytest.raises(ContractChangeError, match="不允许的文件类型"):
        _request(db_session, contract, attachment=ContractChangeAttachment("变更.png", b"x", "image/png"))
    oversized = ContractChangeAttachment("变更.pdf", b"x" * (10 * 1024 * 1024 + 1), "application/pdf")
    with pytest.raises(ContractChangeError, match="文件过大"):
        _request(db_session, contract, attachment=oversized)
    assert db_session.query(ContractChangeRequest).count() == 0

    change = _request(db_session, contract, attachment=ContractChangeAttachment("变更.docx", b"doc", "application/msword"))
    assert change.attachment_name == "变更.docx"
    assert change.attachment_size == 3
    assert contract_change_module.file_storage_service.file_exists(change.attachment_path)


def test_failed_request_removes_saved_attachment(db_session, tmp_path):
    contract = _make_contract(db_session)  # no flow configured

    with pytest.raises(ContractChangeError):
        _request(db_session, contract, attachment=ContractChangeAttachment("变更.pdf", b"pdf", "application/pdf"))

    assert not any(path.is_file() for path in tmp_path.rglob("*"))


# ---------- approval --------------------------------------------------------

def test_final_approval_applies_amount_and_recalculates_price(db_session):
    _make_flow(db_session, nodes=2)
    contract = _make_contract(db_session)
    change = _request(db_session, contract)

    _decide(db_session, change, ApprovalAction.APPROVE)
    db_session.refresh(contract)
    assert contract.total_amount == Decimal("100000.00")
    assert contract_change_service.get_pending(db_session, TEAM_ID, contract.id) is not None

    _decide(db_session, change, ApprovalAction.APPROVE)
    db_session.refresh(contract)
    db_session.refresh(change)
    assert change.approval_phase == ApprovalPhase.APPROVED.value
    assert contract.total_amount == Decimal("125000.00")
    assert contract.standard_unit_price == Decimal("6250.00")
    assert contract.status == ContractStatus.SIGNED
    assert contract.approval_phase == ApprovalPhase.APPROVED.value
    assert contract_change_service.get_pending(db_session, TEAM_ID, contract.id) is None
    second = _request(db_session, contract, amount="130000.00")
    assert second.change_items_json[0]["old_value"] == "125000.00"


def test_rejection_keeps_contract_and_history_and_allows_new_request(db_session):
    _make_flow(db_session)
    contract = _make_contract(db_session)
    rejected = _request(db_session, contract)

    _decide(db_session, rejected, ApprovalAction.REJECT)
    db_session.refresh(contract)
    assert contract.total_amount == Decimal("100000.00")
    assert contract.standard_unit_price == Decimal("5000.00")

    retry = _request(db_session, contract, amount="110000.00")
    history = contract_change_service.list_history(db_session, TEAM_ID, contract.id)
    assert [item.id for item in history] == [retry.id, rejected.id]
    assert history[1].approval_phase == ApprovalPhase.REJECTED.value
    assert history[1].change_items_json[0]["new_value"] == "125000.00"


def test_final_approval_rechecks_floor_and_commits_nothing(db_session):
    _make_flow(db_session)
    contract = _make_contract(db_session)
    change = _request(db_session, contract, amount="90000.00")
    plan = _make_plan(db_session, contract, planned_amount="95000.00")
    assert plan.id is not None

    with pytest.raises(ValueError, match="回款计划"):
        _decide(db_session, change, ApprovalAction.APPROVE)
    db_session.rollback()

    db_session.refresh(contract)
    db_session.refresh(change)
    assert contract.total_amount == Decimal("100000.00")
    assert change.approval_phase == ApprovalPhase.PENDING_REVIEW.value
    approval = approval_crud.get_pending_by_entity(db_session, BusinessType.CONTRACT_CHANGE, change.id, TEAM_ID)
    assert approval.status == ApprovalStatus.PENDING


def test_change_approval_cannot_be_withdrawn_or_resubmitted(db_session):
    _make_flow(db_session)
    contract = _make_contract(db_session)
    change = _request(db_session, contract)
    approval = approval_crud.get_pending_by_entity(db_session, BusinessType.CONTRACT_CHANGE, change.id, TEAM_ID)

    with pytest.raises(ValueError):
        approval_crud.cancel(db_session, approval, user_id=CREATOR_ID)
    _approval, error = approval_transaction_manager.submit_for_approval(
        db_session, BusinessType.CONTRACT_CHANGE, change.id, TEAM_ID, CREATOR_ID, "申请人",
    )

    assert error
    db_session.refresh(approval)
    db_session.refresh(change)
    assert approval.status == ApprovalStatus.PENDING
    assert change.approval_phase == ApprovalPhase.PENDING_REVIEW.value
