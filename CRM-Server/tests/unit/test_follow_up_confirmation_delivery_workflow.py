from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.crud.sales_commitment import FollowUpTaskConfirmationPromptDeliveryCRUD, follow_up_task_crud
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_vector_document import CustomerVectorDocument
from app.models.sales_commitment import (
    DueAtGranularity,
    FollowUpTask,
    FollowUpTaskConfirmationCase,
    FollowUpTaskConfirmationPromptDelivery,
    FollowUpTaskConfirmationPromptStatus,
    FollowUpTaskConfirmationStatus,
    FollowUpTaskEvent,
    FollowUpTaskProjectionRun,
    FollowUpTaskSourceType,
    FollowUpTaskStatus,
    SalesCommitment,
)
from app.schemas.sales_commitment import FollowUpTaskInternalCreate
from app.services.follow_up_confirmation_delivery_projection import FollowUpConfirmationDeliveryProjection
from app.services.follow_up_confirmation_delivery_workflow import (
    ConfirmationDeliveryInput,
    ConfirmationDispatchResult,
    FollowUpConfirmationDeliveryWorkflow,
)
from app.services.follow_up_task_confirmation_service import FollowUpTaskConfirmationService
from app.services.follow_up_task_reconciliation_evaluation_service import FollowUpTaskReconciliationDecision
from app.services.follow_up_task_transition_plan_service import FollowUpTaskTransitionPlanService
from app.services.task_reconciliation_service import TaskReconciliationCandidate, TaskReconciliationCandidateSet
from app.tasks.follow_up_confirmation_delivery_recovery import FollowUpConfirmationDeliveryRecoveryScheduler


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def db_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _skip_indexes(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("CREATE INDEX"):
            return "SELECT 1", ()
        return statement, parameters

    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerActivity.__table__,
            CustomerVectorDocument.__table__,
            SalesCommitment.__table__,
            FollowUpTask.__table__,
            FollowUpTaskEvent.__table__,
            FollowUpTaskProjectionRun.__table__,
            FollowUpTaskConfirmationCase.__table__,
            FollowUpTaskConfirmationPromptDelivery.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(
        Customer(
            id=1,
            public_id="cus_delivery",
            team_id=1,
            account_name="测试客户",
            city="上海",
            owner_id="2",
            creator_id="2",
        )
    )
    session.add(
        CustomerActivity(
            id=212,
            team_id=1,
            customer_id=1,
            activity_kind="OTHER",
            source_content="已反馈资料",
            summary="已反馈资料",
            occurred_at=datetime(2026, 8, 12, 10),
            owner_id="2",
            creator_id="2",
        )
    )
    session.commit()
    session.info["session_factory"] = Session
    yield session
    session.close()
    engine.dispose()


def _case(db):
    task = follow_up_task_crud.create(
        db,
        FollowUpTaskInternalCreate(
            team_id=1,
            customer_id=1,
            owner_id="2",
            creator_id="2",
            title="反馈资料",
            description="反馈资料",
            status=FollowUpTaskStatus.OPEN,
            due_at=datetime(2026, 8, 12, 9),
            due_at_text="今天",
            due_at_granularity=DueAtGranularity.DATETIME,
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_activity_id=212,
            confidence=0.96,
            evidence_json={},
            task_hash="delivery-task",
        ),
    )
    candidate = TaskReconciliationCandidate(
        public_id=task.public_id,
        owner_id="2",
        title=task.title,
        description=task.description,
        due_at=task.due_at.isoformat(),
        due_at_text=task.due_at_text,
        due_at_granularity=task.due_at_granularity,
        due_at_timezone=task.due_at_timezone,
        source_type=task.source_type,
        source_public_id=task.source_public_id,
        confidence=task.confidence,
        candidate_reasons=("same_customer",),
        auto_transition_eligible=True,
        confirmation_required_reason=None,
    )
    plan = FollowUpTaskTransitionPlanService().plan(
        FollowUpTaskReconciliationDecision(
            decision="COMPLETE", task_public_id=task.public_id, candidate_public_ids=(task.public_id,), confidence=0.96
        ),
        TaskReconciliationCandidateSet(items=[candidate], total=1, filters={}, usage_policy={}),
        source_activity_public_id="act_212",
        plan_source="test",
    )
    return (
        FollowUpTaskConfirmationService()
        .create_case_from_plan_action(
            db,
            team_id=1,
            task=task,
            plan=plan,
            action=plan.actions[0],
            actor_id="2",
            source_activity_id=212,
            source_activity_revision=1,
            source_public_id="act_212",
        )
        .case
    )


def test_recovery_delivery_id_does_not_change_langgraph_thread_identity():
    initial = ConfirmationDeliveryInput(
        case_public_id="fuc_recovery_identity",
        team_id=1,
        owner_id="2",
        channel="web",
        provider="confirmation_center",
        source_activity_id=212,
        expected_activity_revision=1,
    )
    recovery = initial.model_copy(
        update={
            "delivery_public_id": "fcp_durable_delivery",
            "idempotency_key": "follow-up-confirmation:fcp_durable_delivery",
        }
    )

    assert FollowUpConfirmationDeliveryWorkflow.prompt_key(initial) == (
        FollowUpConfirmationDeliveryWorkflow.prompt_key(recovery)
    )
    assert FollowUpConfirmationDeliveryWorkflow.thread_id(initial) == (
        FollowUpConfirmationDeliveryWorkflow.thread_id(recovery)
    )


def test_delivery_identity_is_scoped_to_source_activity_revision():
    revision_one = ConfirmationDeliveryInput(
        case_public_id="fuc_revision_identity",
        team_id=1,
        owner_id="2",
        channel="web",
        provider="confirmation_center",
        source_activity_id=212,
        expected_activity_revision=1,
    )
    revision_two = revision_one.model_copy(update={"expected_activity_revision": 2})

    assert FollowUpConfirmationDeliveryWorkflow.prompt_key(revision_one) != (
        FollowUpConfirmationDeliveryWorkflow.prompt_key(revision_two)
    )
    assert FollowUpConfirmationDeliveryWorkflow.thread_id(revision_one) != (
        FollowUpConfirmationDeliveryWorkflow.thread_id(revision_two)
    )


class SuccessfulAdapter:
    async def dispatch(self, request, *, prompt):
        return ConfirmationDispatchResult.sent(provider_message_id=f"inbox:{request.case_public_id}")


class FailedAdapter:
    async def dispatch(self, request, *, prompt):
        return ConfirmationDispatchResult.failed("TEMPORARY_UNAVAILABLE", "temporary")


class RevisionSupersedingAdapter:
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self.request = None

    async def dispatch(self, request, *, prompt):
        self.request = request
        session = self.session_factory()
        try:
            activity = session.query(CustomerActivity).filter_by(id=212, team_id=1).one()
            activity.post_commit_revision = 2
            session.commit()
        finally:
            session.close()
        return ConfirmationDispatchResult.sent(provider_message_id=f"inbox:{request.case_public_id}")


@pytest.mark.asyncio
async def test_delivery_is_queued_before_dispatch_and_sent_only_after_adapter_ack(db_session):
    case = _case(db_session)
    workflow = FollowUpConfirmationDeliveryWorkflow(
        adapters={"web": SuccessfulAdapter()},
        projection=FollowUpConfirmationDeliveryProjection(session_factory=db_session.info["session_factory"]),
        checkpointer=None,
    )
    result = await workflow.run(
        ConfirmationDeliveryInput(
            case_public_id=case.public_id,
            team_id=1,
            owner_id="2",
            channel="web",
            provider="confirmation_center",
            origin_turn_id="activity:212",
        )
    )
    db_session.expire_all()
    delivery = db_session.query(FollowUpTaskConfirmationPromptDelivery).one()
    refreshed_case = db_session.query(FollowUpTaskConfirmationCase).filter_by(id=case.id).one()
    assert result["status"] == FollowUpTaskConfirmationPromptStatus.SENT
    assert delivery.status == FollowUpTaskConfirmationPromptStatus.SENT
    assert delivery.provider_message_id == f"inbox:{case.public_id}"
    assert delivery.attempt_count == 1
    assert refreshed_case.prompt_count == 1
    assert refreshed_case.last_prompted_at is not None


@pytest.mark.asyncio
async def test_dispatch_uses_durable_delivery_id_as_provider_idempotency_key(db_session):
    case = _case(db_session)
    adapter = RevisionSupersedingAdapter(db_session.info["session_factory"])
    workflow = _workflow_for_session(db_session, adapter)

    await workflow.run(
        ConfirmationDeliveryInput(
            case_public_id=case.public_id,
            team_id=1,
            owner_id="2",
            channel="web",
            provider="confirmation_center",
            source_activity_id=212,
            expected_activity_revision=1,
        )
    )

    delivery = db_session.query(FollowUpTaskConfirmationPromptDelivery).one()
    assert adapter.request is not None
    assert adapter.request.delivery_public_id == delivery.public_id
    assert adapter.request.idempotency_key == f"follow-up-confirmation:{delivery.public_id}"


@pytest.mark.asyncio
async def test_revision_superseded_after_claim_is_audited_as_sent_stale_after_dispatch(db_session):
    case = _case(db_session)
    adapter = RevisionSupersedingAdapter(db_session.info["session_factory"])
    workflow = _workflow_for_session(db_session, adapter)

    result = await workflow.run(
        ConfirmationDeliveryInput(
            case_public_id=case.public_id,
            team_id=1,
            owner_id="2",
            channel="web",
            provider="confirmation_center",
            source_activity_id=212,
            expected_activity_revision=1,
        )
    )

    db_session.expire_all()
    delivery = db_session.query(FollowUpTaskConfirmationPromptDelivery).one()
    refreshed_case = db_session.query(FollowUpTaskConfirmationCase).filter_by(id=case.id).one()
    assert result["execution_status"] == "ACKNOWLEDGED_STALE_AFTER_DISPATCH"
    assert result["status"] == FollowUpTaskConfirmationPromptStatus.SENT
    assert result["reason_code"] == "SENT_STALE_SUPERSEDED_ACTIVITY_REVISION"
    assert delivery.status == FollowUpTaskConfirmationPromptStatus.SENT
    assert delivery.reason_code == "SENT_STALE_SUPERSEDED_ACTIVITY_REVISION"
    assert delivery.provider_message_id == f"inbox:{case.public_id}"
    assert refreshed_case.status == "CANCELLED"
    assert refreshed_case.cancelled_reason == "SOURCE_ACTIVITY_REVISION_SUPERSEDED"
    assert refreshed_case.prompt_count == 1


class RevisionSupersedingFailedAdapter(RevisionSupersedingAdapter):
    async def dispatch(self, request, *, prompt):
        await super().dispatch(request, prompt=prompt)
        return ConfirmationDispatchResult.failed("TEMPORARY_UNAVAILABLE", "temporary")


@pytest.mark.asyncio
async def test_failed_dispatch_after_revision_superseded_is_terminally_skipped(db_session):
    case = _case(db_session)
    adapter = RevisionSupersedingFailedAdapter(db_session.info["session_factory"])
    workflow = _workflow_for_session(db_session, adapter)

    result = await workflow.run(
        ConfirmationDeliveryInput(
            case_public_id=case.public_id,
            team_id=1,
            owner_id="2",
            channel="web",
            provider="confirmation_center",
            source_activity_id=212,
            expected_activity_revision=1,
        )
    )

    db_session.expire_all()
    delivery = db_session.query(FollowUpTaskConfirmationPromptDelivery).one()
    refreshed_case = db_session.query(FollowUpTaskConfirmationCase).filter_by(id=case.id).one()
    assert result["status"] == FollowUpTaskConfirmationPromptStatus.SKIPPED
    assert result["execution_status"] == "ACKNOWLEDGED_STALE_AFTER_DISPATCH"
    assert delivery.status == FollowUpTaskConfirmationPromptStatus.SKIPPED
    assert delivery.reason_code == "SKIPPED_STALE_SUPERSEDED_ACTIVITY_REVISION"
    assert delivery.next_attempt_at is None
    assert refreshed_case.status == "CANCELLED"
    assert refreshed_case.prompt_count == 0


@pytest.mark.asyncio
async def test_failed_dispatch_is_audited_without_claiming_user_delivery(db_session):
    case = _case(db_session)
    workflow = FollowUpConfirmationDeliveryWorkflow(
        adapters={"web": FailedAdapter()},
        projection=FollowUpConfirmationDeliveryProjection(session_factory=db_session.info["session_factory"]),
        checkpointer=None,
    )
    result = await workflow.run(
        ConfirmationDeliveryInput(
            case_public_id=case.public_id,
            team_id=1,
            owner_id="2",
            channel="web",
            provider="confirmation_center",
        )
    )
    db_session.expire_all()
    delivery = db_session.query(FollowUpTaskConfirmationPromptDelivery).one()
    refreshed_case = db_session.query(FollowUpTaskConfirmationCase).filter_by(id=case.id).one()
    assert result["status"] == FollowUpTaskConfirmationPromptStatus.FAILED
    assert delivery.status == FollowUpTaskConfirmationPromptStatus.FAILED
    assert delivery.reason_code == "TEMPORARY_UNAVAILABLE"
    assert delivery.next_attempt_at is not None
    assert refreshed_case.prompt_count == 0


@pytest.mark.asyncio
async def test_delivery_fences_superseded_source_activity_revision_before_dispatch(db_session):
    case = _case(db_session)
    activity = db_session.query(CustomerActivity).filter_by(id=212, team_id=1).one()
    activity.post_commit_revision = 2
    db_session.commit()
    adapter = CountingAdapter()
    workflow = FollowUpConfirmationDeliveryWorkflow(
        adapters={"web": adapter},
        projection=FollowUpConfirmationDeliveryProjection(session_factory=db_session.info["session_factory"]),
        checkpointer=None,
    )

    result = await workflow.run(
        ConfirmationDeliveryInput(
            case_public_id=case.public_id,
            team_id=1,
            owner_id="2",
            channel="web",
            provider="confirmation_center",
            source_activity_id=212,
            expected_activity_revision=1,
        )
    )

    db_session.expire_all()
    delivery = db_session.query(FollowUpTaskConfirmationPromptDelivery).one()
    refreshed_case = db_session.query(FollowUpTaskConfirmationCase).filter_by(id=case.id).one()
    assert adapter.calls == 0
    assert result["status"] == FollowUpTaskConfirmationPromptStatus.SKIPPED
    assert result["reason_code"] == "SUPERSEDED_ACTIVITY_REVISION"
    assert delivery.status == FollowUpTaskConfirmationPromptStatus.SKIPPED
    assert delivery.reason_code == "SUPERSEDED_ACTIVITY_REVISION"
    assert delivery.source_activity_id == 212
    assert delivery.expected_activity_revision == 1
    assert refreshed_case.status == "CANCELLED"
    assert refreshed_case.cancelled_reason == "SOURCE_ACTIVITY_REVISION_SUPERSEDED"
    assert refreshed_case.prompt_count == 0
    assert refreshed_case.last_prompted_at is None


@pytest.mark.asyncio
async def test_delivery_cancels_case_when_source_activity_was_deleted(db_session):
    case = _case(db_session)
    activity = db_session.query(CustomerActivity).filter_by(id=212, team_id=1).one()
    db_session.delete(activity)
    db_session.commit()
    adapter = CountingAdapter()
    workflow = FollowUpConfirmationDeliveryWorkflow(
        adapters={"web": adapter},
        projection=FollowUpConfirmationDeliveryProjection(session_factory=db_session.info["session_factory"]),
        checkpointer=None,
    )

    result = await workflow.run(
        ConfirmationDeliveryInput(
            case_public_id=case.public_id,
            team_id=1,
            owner_id="2",
            channel="web",
            provider="confirmation_center",
            source_activity_id=212,
            expected_activity_revision=1,
        )
    )

    db_session.expire_all()
    delivery = db_session.query(FollowUpTaskConfirmationPromptDelivery).one()
    refreshed_case = db_session.query(FollowUpTaskConfirmationCase).filter_by(id=case.id).one()
    assert adapter.calls == 0
    assert result["status"] == FollowUpTaskConfirmationPromptStatus.SKIPPED
    assert result["reason_code"] == "ACTIVITY_NOT_FOUND"
    assert delivery.status == FollowUpTaskConfirmationPromptStatus.SKIPPED
    assert delivery.reason_code == "ACTIVITY_NOT_FOUND"
    assert refreshed_case.status == "CANCELLED"
    assert refreshed_case.cancelled_reason == "SOURCE_ACTIVITY_DELETED"
    assert refreshed_case.prompt_count == 0


@pytest.mark.asyncio
async def test_activity_bound_case_without_revision_fails_closed(db_session):
    case = _case(db_session)
    case.source_activity_revision = None
    db_session.commit()
    adapter = CountingAdapter()
    workflow = _workflow_for_session(db_session, adapter)

    result = await workflow.run(
        ConfirmationDeliveryInput(
            case_public_id=case.public_id,
            team_id=1,
            owner_id="2",
            channel="web",
            provider="confirmation_center",
            source_activity_id=212,
            expected_activity_revision=None,
        )
    )

    db_session.expire_all()
    delivery = db_session.query(FollowUpTaskConfirmationPromptDelivery).one()
    refreshed_case = db_session.query(FollowUpTaskConfirmationCase).filter_by(id=case.id).one()
    assert adapter.calls == 0
    assert result["status"] == FollowUpTaskConfirmationPromptStatus.SKIPPED
    assert result["reason_code"] == "SOURCE_ACTIVITY_REVISION_MISSING"
    assert delivery.status == FollowUpTaskConfirmationPromptStatus.SKIPPED
    assert delivery.reason_code == "SOURCE_ACTIVITY_REVISION_MISSING"
    assert refreshed_case.status == FollowUpTaskConfirmationStatus.CANCELLED
    assert refreshed_case.cancelled_reason == "SOURCE_ACTIVITY_REVISION_CONTRACT_INVALID"


@pytest.mark.asyncio
async def test_recovery_rehydrates_persisted_source_activity_revision_contract(db_session, monkeypatch):
    case = _case(db_session)
    workflow = FollowUpConfirmationDeliveryWorkflow(
        adapters={"web": SuccessfulAdapter()},
        projection=FollowUpConfirmationDeliveryProjection(session_factory=db_session.info["session_factory"]),
        checkpointer=None,
    )
    request = ConfirmationDeliveryInput(
        case_public_id=case.public_id,
        team_id=1,
        owner_id="2",
        channel="web",
        provider="confirmation_center",
        source_activity_id=212,
        expected_activity_revision=1,
    )
    workflow.projection.ensure_and_validate(
        request,
        prompt_key=workflow.prompt_key(request),
        thread_id=workflow.thread_id(request),
    )
    captured = []

    async def _capture(recovered_request):
        captured.append(recovered_request)
        return {"status": "SENT"}

    monkeypatch.setattr(
        "app.tasks.follow_up_confirmation_delivery_recovery.SessionLocal",
        db_session.info["session_factory"],
    )
    monkeypatch.setattr(
        "app.tasks.follow_up_confirmation_delivery_recovery.follow_up_confirmation_delivery_workflow.run",
        _capture,
    )

    result = await FollowUpConfirmationDeliveryRecoveryScheduler().recover_once(limit=10)

    assert result == {
        "scanned": 1,
        "recovered": 1,
        "skipped": 0,
        "failed": 0,
        "exhausted": 0,
        "ambiguous": 0,
        "deferred": 0,
    }
    assert len(captured) == 1
    assert captured[0].source_activity_id == 212
    assert captured[0].expected_activity_revision == 1


@pytest.mark.asyncio
async def test_recovery_reports_ambiguous_visibility_separately_from_failure(db_session, monkeypatch):
    case = _case(db_session)
    workflow = _workflow_for_session(db_session, CountingAdapter())
    request = ConfirmationDeliveryInput(
        case_public_id=case.public_id,
        team_id=1,
        owner_id="2",
        channel="web",
        provider="confirmation_center",
    )
    workflow.projection.ensure_and_validate(
        request,
        prompt_key=workflow.prompt_key(request),
        thread_id=workflow.thread_id(request),
    )

    async def _ambiguous(_request):
        return {"status": FollowUpTaskConfirmationPromptStatus.AMBIGUOUS, "execution_status": "AMBIGUOUS"}

    monkeypatch.setattr(
        "app.tasks.follow_up_confirmation_delivery_recovery.SessionLocal",
        db_session.info["session_factory"],
    )
    monkeypatch.setattr(
        "app.tasks.follow_up_confirmation_delivery_recovery.follow_up_confirmation_delivery_workflow.run",
        _ambiguous,
    )

    result = await FollowUpConfirmationDeliveryRecoveryScheduler().recover_once(limit=10)

    assert result == {
        "scanned": 1,
        "recovered": 0,
        "skipped": 0,
        "failed": 0,
        "exhausted": 0,
        "ambiguous": 1,
        "deferred": 0,
    }


@pytest.mark.asyncio
async def test_recovery_terminalizes_legacy_delivery_with_source_contract_mismatch(db_session):
    case = _case(db_session)
    adapter = CountingAdapter()
    workflow = _workflow_for_session(db_session, adapter)
    request = ConfirmationDeliveryInput(
        case_public_id=case.public_id,
        team_id=1,
        owner_id="2",
        channel="web",
        provider="confirmation_center",
        source_activity_id=212,
        expected_activity_revision=1,
    )
    queued = workflow.projection.ensure_and_validate(
        request,
        prompt_key=workflow.prompt_key(request),
        thread_id=workflow.thread_id(request),
    )
    delivery = (
        db_session.query(FollowUpTaskConfirmationPromptDelivery)
        .filter_by(public_id=queued.delivery_public_id)
        .one()
    )
    delivery.source_activity_id = None
    delivery.expected_activity_revision = None
    db_session.commit()

    result = await workflow.run(
        request.model_copy(
            update={
                "delivery_public_id": delivery.public_id,
                "source_activity_id": None,
                "expected_activity_revision": None,
            }
        )
    )

    db_session.expire_all()
    refreshed = (
        db_session.query(FollowUpTaskConfirmationPromptDelivery)
        .filter_by(id=delivery.id)
        .one()
    )
    recovery_candidates = FollowUpTaskConfirmationPromptDeliveryCRUD().list_system_recovery_candidates(
        db_session,
        max_attempts=3,
        limit=10,
    )
    assert adapter.calls == 0
    assert result["status"] == FollowUpTaskConfirmationPromptStatus.SKIPPED
    assert result["reason_code"] == "DELIVERY_SOURCE_ACTIVITY_MISMATCH"
    assert refreshed.status == FollowUpTaskConfirmationPromptStatus.SKIPPED
    assert refreshed.reason_code == "DELIVERY_SOURCE_ACTIVITY_MISMATCH"
    assert recovery_candidates == []


@pytest.mark.asyncio
async def test_duplicate_delivery_run_is_idempotent(db_session):
    case = _case(db_session)
    workflow = FollowUpConfirmationDeliveryWorkflow(
        adapters={"web": SuccessfulAdapter()},
        projection=FollowUpConfirmationDeliveryProjection(session_factory=db_session.info["session_factory"]),
        checkpointer=None,
    )
    request = ConfirmationDeliveryInput(
        case_public_id=case.public_id, team_id=1, owner_id="2", channel="web", provider="confirmation_center"
    )
    await workflow.run(request)
    await workflow.run(request)
    db_session.expire_all()
    assert db_session.query(FollowUpTaskConfirmationPromptDelivery).count() == 1
    assert db_session.query(FollowUpTaskConfirmationCase).filter_by(id=case.id).one().prompt_count == 1


class CountingAdapter:
    def __init__(self, result: ConfirmationDispatchResult | None = None) -> None:
        self.calls = 0
        self.result = result or ConfirmationDispatchResult.sent(provider_message_id="provider:visible")

    async def dispatch(self, request, *, prompt):
        self.calls += 1
        return self.result


def _workflow_for_session(db_session, adapter, *, delivery_crud=None):
    projection_kwargs = {"session_factory": db_session.info["session_factory"]}
    if delivery_crud is not None:
        projection_kwargs["delivery_crud"] = delivery_crud
    return FollowUpConfirmationDeliveryWorkflow(
        adapters={"web": adapter},
        projection=FollowUpConfirmationDeliveryProjection(**projection_kwargs),
        checkpointer=None,
    )


@pytest.mark.asyncio
async def test_owner_mismatch_is_durably_skipped_and_never_dispatched(db_session):
    case = _case(db_session)
    adapter = CountingAdapter()
    workflow = _workflow_for_session(db_session, adapter)

    result = await workflow.run(
        ConfirmationDeliveryInput(
            case_public_id=case.public_id,
            team_id=1,
            owner_id="different-owner",
            channel="web",
            provider="confirmation_center",
        )
    )

    db_session.expire_all()
    delivery = db_session.query(FollowUpTaskConfirmationPromptDelivery).one()
    assert result["status"] == FollowUpTaskConfirmationPromptStatus.SKIPPED
    assert result["reason_code"] == "OWNER_MISMATCH"
    assert delivery.status == FollowUpTaskConfirmationPromptStatus.SKIPPED
    assert delivery.reason_code == "OWNER_MISMATCH"
    assert adapter.calls == 0


@pytest.mark.asyncio
async def test_live_delivery_lease_returns_busy_without_dispatch(db_session):
    from app.utils.time import business_now

    case = _case(db_session)
    adapter = CountingAdapter()
    workflow = _workflow_for_session(db_session, adapter)
    request = ConfirmationDeliveryInput(
        case_public_id=case.public_id,
        team_id=1,
        owner_id="2",
        channel="web",
        provider="confirmation_center",
    )
    projection_result = workflow.projection.ensure_and_validate(
        request,
        prompt_key=workflow.prompt_key(request),
        thread_id=workflow.thread_id(request),
    )
    delivery = db_session.query(FollowUpTaskConfirmationPromptDelivery).filter_by(
        public_id=projection_result.delivery_public_id
    ).one()
    delivery.lease_token = "other-worker"
    delivery.lease_expires_at = business_now() + timedelta(minutes=5)
    db_session.commit()

    result = await workflow.run(request)

    assert result["execution_status"] == "BUSY"
    assert result["reason_code"] == "DELIVERY_LEASE_BUSY"
    assert adapter.calls == 0


class MissingProviderAckAdapter:
    async def dispatch(self, request, *, prompt):
        return ConfirmationDispatchResult(status="SENT", reason_code="CHANNEL_ACKNOWLEDGED")


@pytest.mark.asyncio
async def test_sent_without_provider_message_id_is_terminal_ambiguous(db_session):
    case = _case(db_session)
    workflow = _workflow_for_session(db_session, MissingProviderAckAdapter())

    result = await workflow.run(
        ConfirmationDeliveryInput(
            case_public_id=case.public_id,
            team_id=1,
            owner_id="2",
            channel="web",
            provider="confirmation_center",
        )
    )

    db_session.expire_all()
    delivery = db_session.query(FollowUpTaskConfirmationPromptDelivery).one()
    refreshed_case = db_session.query(FollowUpTaskConfirmationCase).filter_by(id=case.id).one()
    assert result["status"] == FollowUpTaskConfirmationPromptStatus.AMBIGUOUS
    assert result["execution_status"] == "AMBIGUOUS"
    assert delivery.status == FollowUpTaskConfirmationPromptStatus.AMBIGUOUS
    assert delivery.reason_code == "PROVIDER_ACK_MISSING"
    assert delivery.next_attempt_at is None
    assert delivery.lease_token is None
    assert refreshed_case.prompt_count == 0

    recoverable = FollowUpTaskConfirmationPromptDeliveryCRUD().list_system_recovery_candidates(
        db_session,
        now=datetime(2026, 8, 16, 10, 0),
        max_attempts=5,
        limit=10,
    )
    assert recoverable == []


@pytest.mark.asyncio
async def test_ambiguous_delivery_is_not_dispatched_again_on_replay(db_session):
    case = _case(db_session)
    request = ConfirmationDeliveryInput(
        case_public_id=case.public_id,
        team_id=1,
        owner_id="2",
        channel="web",
        provider="confirmation_center",
    )
    first = _workflow_for_session(db_session, MissingProviderAckAdapter())
    await first.run(request)

    retry_adapter = CountingAdapter()
    replay = _workflow_for_session(db_session, retry_adapter)
    result = await replay.run(request)

    db_session.expire_all()
    delivery = db_session.query(FollowUpTaskConfirmationPromptDelivery).one()
    assert result["status"] == FollowUpTaskConfirmationPromptStatus.AMBIGUOUS
    assert delivery.status == FollowUpTaskConfirmationPromptStatus.AMBIGUOUS
    assert retry_adapter.calls == 0


@pytest.mark.asyncio
async def test_cross_team_request_cannot_create_or_update_delivery(db_session):
    case = _case(db_session)
    adapter = CountingAdapter()
    workflow = _workflow_for_session(db_session, adapter)

    result = await workflow.run(
        ConfirmationDeliveryInput(
            case_public_id=case.public_id,
            team_id=999,
            owner_id="2",
            channel="web",
            provider="confirmation_center",
        )
    )

    assert result["status"] == FollowUpTaskConfirmationPromptStatus.SKIPPED
    assert result["reason_code"] == "CASE_NOT_FOUND"
    assert db_session.query(FollowUpTaskConfirmationPromptDelivery).count() == 0
    assert adapter.calls == 0


class LeaseStealingAdapter:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def dispatch(self, request, *, prompt):
        del prompt
        session = self.session_factory()
        try:
            delivery = session.query(FollowUpTaskConfirmationPromptDelivery).filter_by(
                public_id=request.delivery_public_id
            ).one()
            delivery.lease_token = "other-worker"
            session.commit()
        finally:
            session.close()
        return ConfirmationDispatchResult.sent(provider_message_id=f"inbox:{request.case_public_id}")


@pytest.mark.asyncio
async def test_lost_acknowledgement_lease_never_reports_sent(db_session):
    case = _case(db_session)
    workflow = _workflow_for_session(
        db_session,
        LeaseStealingAdapter(db_session.info["session_factory"]),
    )

    result = await workflow.run(
        ConfirmationDeliveryInput(
            case_public_id=case.public_id,
            team_id=1,
            owner_id="2",
            channel="web",
            provider="confirmation_center",
        )
    )

    db_session.expire_all()
    delivery = db_session.query(FollowUpTaskConfirmationPromptDelivery).one()
    refreshed_case = db_session.query(FollowUpTaskConfirmationCase).filter_by(id=case.id).one()
    assert result["execution_status"] == "LEASE_LOST"
    assert result["status"] == delivery.status == FollowUpTaskConfirmationPromptStatus.QUEUED
    assert delivery.provider_message_id is None
    assert refreshed_case.prompt_count == 0


def test_recovery_scan_includes_expired_max_attempt_delivery_for_terminalization(db_session):
    case = _case(db_session)
    workflow = _workflow_for_session(db_session, CountingAdapter())
    request = ConfirmationDeliveryInput(
        case_public_id=case.public_id,
        team_id=1,
        owner_id="2",
        channel="web",
        provider="confirmation_center",
    )
    ensured = workflow.projection.ensure_and_validate(
        request,
        prompt_key=workflow.prompt_key(request),
        thread_id=workflow.thread_id(request),
    )
    delivery = db_session.query(FollowUpTaskConfirmationPromptDelivery).filter_by(
        public_id=ensured.delivery_public_id
    ).one()
    delivery.attempt_count = 5
    delivery.lease_token = "crashed-worker"
    delivery.lease_expires_at = datetime(2026, 8, 15, 10, 0)
    db_session.commit()

    rows = FollowUpTaskConfirmationPromptDeliveryCRUD().list_system_recovery_candidates(
        db_session,
        now=datetime(2026, 8, 16, 10, 0),
        max_attempts=5,
        limit=10,
    )

    assert [row.delivery_public_id for row in rows] == [delivery.public_id]
    assert rows[0].team_id == 1
    assert rows[0].case_public_id == case.public_id


def test_recovery_scan_uses_case_identity_instead_of_payload_snapshot(db_session):
    case = _case(db_session)
    workflow = _workflow_for_session(db_session, CountingAdapter())
    request = ConfirmationDeliveryInput(
        case_public_id=case.public_id,
        team_id=1,
        owner_id="2",
        channel="web",
        provider="confirmation_center",
    )
    ensured = workflow.projection.ensure_and_validate(
        request,
        prompt_key=workflow.prompt_key(request),
        thread_id=workflow.thread_id(request),
    )
    delivery = db_session.query(FollowUpTaskConfirmationPromptDelivery).filter_by(
        public_id=ensured.delivery_public_id
    ).one()
    delivery.payload_json = {}
    db_session.commit()

    rows = FollowUpTaskConfirmationPromptDeliveryCRUD().list_system_recovery_candidates(
        db_session,
        now=datetime(2026, 8, 16, 10, 0),
        max_attempts=5,
        limit=10,
    )

    assert [row.delivery_public_id for row in rows] == [delivery.public_id]
    assert rows[0].case_public_id == case.public_id


@pytest.mark.asyncio
async def test_exhausted_delivery_is_terminal_and_records_explicit_reason(db_session):
    case = _case(db_session)
    adapter = CountingAdapter()
    workflow = _workflow_for_session(db_session, adapter)
    request = ConfirmationDeliveryInput(
        case_public_id=case.public_id,
        team_id=1,
        owner_id="2",
        channel="web",
        provider="confirmation_center",
    )
    ensured = workflow.projection.ensure_and_validate(
        request,
        prompt_key=workflow.prompt_key(request),
        thread_id=workflow.thread_id(request),
    )
    delivery = db_session.query(FollowUpTaskConfirmationPromptDelivery).filter_by(
        public_id=ensured.delivery_public_id
    ).one()
    delivery.status = FollowUpTaskConfirmationPromptStatus.FAILED
    delivery.attempt_count = 5
    delivery.reason_code = "TEMPORARY_UNAVAILABLE"
    delivery.error_message = "temporary"
    delivery.next_attempt_at = None
    db_session.commit()

    result = await workflow.run(request)

    db_session.expire_all()
    persisted = db_session.query(FollowUpTaskConfirmationPromptDelivery).filter_by(id=delivery.id).one()
    assert result["execution_status"] == "RETRIES_EXHAUSTED"
    assert result["reason_code"] == "DELIVERY_RETRIES_EXHAUSTED"
    assert persisted.status == FollowUpTaskConfirmationPromptStatus.EXHAUSTED
    assert persisted.reason_code == "DELIVERY_RETRIES_EXHAUSTED"
    assert persisted.next_attempt_at is None
    assert persisted.lease_token is None
    assert adapter.calls == 0

    recoverable = FollowUpTaskConfirmationPromptDeliveryCRUD().list_system_recovery_candidates(
        db_session,
        now=datetime(2026, 8, 16, 10, 0),
        max_attempts=5,
        limit=10,
    )
    assert recoverable == []


@pytest.mark.asyncio
async def test_last_failed_delivery_attempt_becomes_terminal_immediately(db_session):
    case = _case(db_session)
    adapter = CountingAdapter(ConfirmationDispatchResult.failed("TEMPORARY_UNAVAILABLE", "temporary"))
    workflow = _workflow_for_session(db_session, adapter)
    request = ConfirmationDeliveryInput(
        case_public_id=case.public_id,
        team_id=1,
        owner_id="2",
        channel="web",
        provider="confirmation_center",
    )
    ensured = workflow.projection.ensure_and_validate(
        request,
        prompt_key=workflow.prompt_key(request),
        thread_id=workflow.thread_id(request),
    )
    delivery = db_session.query(FollowUpTaskConfirmationPromptDelivery).filter_by(
        public_id=ensured.delivery_public_id
    ).one()
    delivery.attempt_count = 4
    db_session.commit()

    result = await workflow.run(request)

    db_session.expire_all()
    persisted = db_session.query(FollowUpTaskConfirmationPromptDelivery).filter_by(id=delivery.id).one()
    assert result["execution_status"] == "RETRIES_EXHAUSTED"
    assert result["reason_code"] == "DELIVERY_RETRIES_EXHAUSTED"
    assert persisted.status == FollowUpTaskConfirmationPromptStatus.EXHAUSTED
    assert persisted.attempt_count == 5
    assert persisted.reason_code == "DELIVERY_RETRIES_EXHAUSTED"
    assert persisted.next_attempt_at is None
    assert persisted.lease_token is None
    assert adapter.calls == 1
