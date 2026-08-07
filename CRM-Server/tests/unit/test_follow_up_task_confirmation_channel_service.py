from datetime import datetime, timedelta

import pytest
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.crud.sales_commitment import follow_up_task_crud
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_vector_document import CustomerVectorDocument
from app.models.sales_commitment import (
    DueAtGranularity,
    FollowUpTask,
    FollowUpTaskConfirmationCase,
    FollowUpTaskConfirmationPromptDelivery,
    FollowUpTaskConfirmationPromptStatus,
    FollowUpTaskConfirmationResolutionAction,
    FollowUpTaskEvent,
    FollowUpTaskProjectionRun,
    FollowUpTaskSourceType,
    FollowUpTaskStatus,
    SalesCommitment,
)
from app.schemas.sales_commitment import FollowUpTaskInternalCreate
from app.services.follow_up_task_confirmation_channel_service import (
    FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION,
    FOLLOW_UP_CONFIRMATION_PROMPT_EVENT,
    FollowUpTaskConfirmationChannelService,
)
from app.services.follow_up_task_confirmation_service import FollowUpTaskConfirmationService
from app.services.follow_up_task_reconciliation_evaluation_service import FollowUpTaskReconciliationDecision
from app.services.follow_up_task_transition_plan_service import FollowUpTaskTransitionPlanService
from app.services.task_reconciliation_service import TaskReconciliationCandidate, TaskReconciliationCandidateSet


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _skip_sqlite_indexes(conn, cursor, statement, parameters, context, executemany):
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
    _seed_customer_and_activity(session)
    session.commit()
    yield session
    session.close()
    engine.dispose()


def _seed_customer_and_activity(db_session) -> None:
    db_session.add_all([
        Customer(
            id=1,
            public_id="cus_11111111111111111111111111111111",
            team_id=1,
            account_name="测试客户",
            city="上海",
            owner_id="9",
            creator_id="9",
        ),
        CustomerActivity(
            id=101,
            team_id=1,
            customer_id=1,
            activity_kind="PHONE_FOLLOW_UP",
            source_content="客户说预算还没进展。",
            summary="客户预算还没进展。",
            occurred_at=datetime(2026, 8, 6, 10, 0, 0),
            owner_id="2",
            creator_id="2",
        ),
    ])


def _create_task(
    db_session,
    *,
    task_hash: str = "task-hash",
    title: str = "确认客户预算是否通过",
    owner_id: str = "2",
) -> FollowUpTask:
    return follow_up_task_crud.create(
        db_session,
        FollowUpTaskInternalCreate(
            team_id=1,
            customer_id=1,
            owner_id=owner_id,
            creator_id=owner_id,
            title=title,
            description="客户说本周确认预算。",
            status=FollowUpTaskStatus.OPEN,
            due_at=datetime(2026, 8, 5, 10, 0, 0),
            due_at_text="本周三",
            due_at_granularity=DueAtGranularity.DATETIME,
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_activity_id=101,
            source_public_id="act_11111111111111111111111111111111",
            confidence=0.91,
            evidence_json={"quote": "客户说本周确认预算"},
            task_hash=task_hash,
        ),
    )


def _candidate(task: FollowUpTask) -> TaskReconciliationCandidate:
    return TaskReconciliationCandidate(
        public_id=task.public_id,
        owner_id=task.owner_id,
        title=task.title,
        description=task.description,
        due_at=task.due_at.isoformat(),
        due_at_text=task.due_at_text,
        due_at_granularity=task.due_at_granularity,
        due_at_timezone=task.due_at_timezone,
        source_type=task.source_type,
        source_public_id=task.source_public_id,
        confidence=task.confidence,
        candidate_reasons=("same_customer", "open_task", "due_window", "same_owner"),
        auto_transition_eligible=True,
        confirmation_required_reason=None,
    )


def _create_confirmation_case(
    db_session,
    task: FollowUpTask,
    *,
    source_activity_public_id: str = "act_22222222222222222222222222222222",
    source_activity_id: int | None = None,
) -> FollowUpTaskConfirmationCase:
    plan = FollowUpTaskTransitionPlanService().plan(
        FollowUpTaskReconciliationDecision(
            decision="COMPLETE",
            task_public_id=task.public_id,
            candidate_public_ids=(task.public_id,),
            confidence=0.62,
            evidence_terms=("预算",),
        ),
        TaskReconciliationCandidateSet(
            items=[_candidate(task)],
            total=1,
            filters={"activity_owner_id": task.owner_id},
            usage_policy={
                "state_source": "mysql.crm_follow_up_tasks",
                "mutation": "forbidden",
                "cross_owner": "confirmation_only",
            },
        ),
        source_activity_public_id=source_activity_public_id,
        plan_source="unit_test_plan",
    )
    return FollowUpTaskConfirmationService().create_case_from_plan_action(
        db_session,
        team_id=1,
        task=task,
        plan=plan,
        action=plan.actions[0],
        actor_id=task.owner_id,
        source_activity_id=source_activity_id,
        source_public_id=source_activity_public_id,
    ).case


def test_prompt_next_pending_case_records_delivery_and_interaction(db_session):
    task = _create_task(db_session)
    case = _create_confirmation_case(db_session, task)
    now = datetime(2026, 8, 6, 11, 0, 0)

    event = FollowUpTaskConfirmationChannelService().prompt_next_pending_case(
        db_session,
        team_id=1,
        user_id=2,
        channel="web",
        provider=None,
        agent_session_id=33,
        now=now,
    )

    db_session.refresh(case)
    delivery = db_session.query(FollowUpTaskConfirmationPromptDelivery).one()
    interaction = event["interaction"]

    assert event["event"] == FOLLOW_UP_CONFIRMATION_PROMPT_EVENT
    assert event["case_public_id"] == case.public_id
    assert event["delivery"]["public_id"] == delivery.public_id
    assert interaction["business_action"] == FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION
    assert interaction["payload"]["case_public_id"] == case.public_id
    assert interaction["choices"][0]["metadata"]["follow_up_confirmation_case_public_id"] == case.public_id
    assert delivery.status == FollowUpTaskConfirmationPromptStatus.SENT
    assert delivery.owner_id == "2"
    assert delivery.channel == "web"
    assert delivery.agent_session_id == 33
    assert delivery.payload_json["case_public_id"] == case.public_id
    assert case.prompt_count == 1
    assert case.last_prompted_at == now


def test_prompt_cases_by_public_ids_prompts_requested_owner_cases_without_owner_cooldown(db_session):
    first_task = _create_task(db_session, task_hash="task-hash-1", title="确认客户预算是否通过")
    second_task = _create_task(db_session, task_hash="task-hash-2", title="确认客户采购联系时间")
    other_owner_task = _create_task(
        db_session,
        task_hash="task-hash-3",
        title="确认客户合同盖章",
        owner_id="8",
    )
    first_case = _create_confirmation_case(
        db_session,
        first_task,
        source_activity_id=190,
        source_activity_public_id="act_33333333333333333333333333333333",
    )
    second_case = _create_confirmation_case(
        db_session,
        second_task,
        source_activity_id=190,
        source_activity_public_id="act_33333333333333333333333333333333",
    )
    other_owner_case = _create_confirmation_case(
        db_session,
        other_owner_task,
        source_activity_id=190,
        source_activity_public_id="act_33333333333333333333333333333333",
    )
    now = datetime(2026, 8, 6, 11, 30, 0)
    service = FollowUpTaskConfirmationChannelService(prompt_cooldown=timedelta(days=1))

    events = service.prompt_cases_by_public_ids(
        db_session,
        team_id=1,
        user_id=2,
        case_public_ids=[
            first_case.public_id,
            second_case.public_id,
            first_case.public_id,
            other_owner_case.public_id,
            "fuc_missing",
        ],
        channel="im",
        provider="feishu",
        agent_session_id=44,
        now=now,
    )

    db_session.refresh(first_case)
    db_session.refresh(second_case)
    db_session.refresh(other_owner_case)
    deliveries = (
        db_session.query(FollowUpTaskConfirmationPromptDelivery)
        .order_by(FollowUpTaskConfirmationPromptDelivery.id.asc())
        .all()
    )

    assert [event["case_public_id"] for event in events] == [first_case.public_id, second_case.public_id]
    assert [delivery.case_id for delivery in deliveries] == [first_case.id, second_case.id]
    assert all(delivery.channel == "im" for delivery in deliveries)
    assert all(delivery.provider == "feishu" for delivery in deliveries)
    assert all(delivery.agent_session_id == 44 for delivery in deliveries)
    assert first_case.prompt_count == 1
    assert second_case.prompt_count == 1
    assert other_owner_case.prompt_count == 0
    assert first_case.last_prompted_at == now
    assert second_case.last_prompted_at == now


def test_prompt_cases_by_public_ids_respects_case_cooldown(db_session):
    task = _create_task(db_session)
    case = _create_confirmation_case(
        db_session,
        task,
        source_activity_id=190,
        source_activity_public_id="act_33333333333333333333333333333333",
    )
    service = FollowUpTaskConfirmationChannelService(prompt_cooldown=timedelta(hours=4))

    first_events = service.prompt_cases_by_public_ids(
        db_session,
        team_id=1,
        user_id=2,
        case_public_ids=[case.public_id],
        channel="web",
        now=datetime(2026, 8, 6, 11, 0, 0),
    )
    second_events = service.prompt_cases_by_public_ids(
        db_session,
        team_id=1,
        user_id=2,
        case_public_ids=[case.public_id],
        channel="web",
        now=datetime(2026, 8, 6, 12, 0, 0),
    )

    db_session.refresh(case)

    assert [event["case_public_id"] for event in first_events] == [case.public_id]
    assert second_events == []
    assert case.prompt_count == 1
    assert db_session.query(FollowUpTaskConfirmationPromptDelivery).count() == 1


def test_prompt_cases_by_public_ids_respects_case_prompt_limit(db_session):
    task = _create_task(db_session)
    case = _create_confirmation_case(
        db_session,
        task,
        source_activity_id=190,
        source_activity_public_id="act_33333333333333333333333333333333",
    )
    service = FollowUpTaskConfirmationChannelService(
        prompt_cooldown=timedelta(seconds=0),
        max_prompts_per_case=1,
    )

    first_events = service.prompt_cases_by_public_ids(
        db_session,
        team_id=1,
        user_id=2,
        case_public_ids=[case.public_id],
        channel="web",
        now=datetime(2026, 8, 6, 11, 0, 0),
    )
    second_events = service.prompt_cases_by_public_ids(
        db_session,
        team_id=1,
        user_id=2,
        case_public_ids=[case.public_id],
        channel="web",
        now=datetime(2026, 8, 6, 13, 0, 0),
    )

    db_session.refresh(case)

    assert [event["case_public_id"] for event in first_events] == [case.public_id]
    assert second_events == []
    assert case.prompt_count == 1
    assert db_session.query(FollowUpTaskConfirmationPromptDelivery).count() == 1


def test_prompt_next_pending_case_applies_owner_level_cross_channel_cooldown(db_session):
    first_task = _create_task(db_session, task_hash="task-hash-1", title="确认客户预算是否通过")
    second_task = _create_task(db_session, task_hash="task-hash-2", title="确认客户试用是否安排")
    _create_confirmation_case(db_session, first_task)
    _create_confirmation_case(db_session, second_task)
    service = FollowUpTaskConfirmationChannelService(prompt_cooldown=timedelta(hours=4))

    first_event = service.prompt_next_pending_case(
        db_session,
        team_id=1,
        user_id=2,
        channel="web",
        agent_session_id=33,
        now=datetime(2026, 8, 6, 11, 0, 0),
    )
    second_event = service.prompt_next_pending_case(
        db_session,
        team_id=1,
        user_id=2,
        channel="im",
        provider="feishu",
        agent_session_id=44,
        now=datetime(2026, 8, 6, 12, 0, 0),
    )

    assert first_event is not None
    assert second_event is None
    assert db_session.query(FollowUpTaskConfirmationPromptDelivery).count() == 1


def test_prompt_next_pending_case_respects_case_prompt_limit(db_session):
    task = _create_task(db_session)
    case = _create_confirmation_case(db_session, task)
    service = FollowUpTaskConfirmationChannelService(
        prompt_cooldown=timedelta(hours=1),
        max_prompts_per_case=1,
    )

    first_event = service.prompt_next_pending_case(
        db_session,
        team_id=1,
        user_id=2,
        channel="web",
        agent_session_id=33,
        now=datetime(2026, 8, 6, 11, 0, 0),
    )
    second_event = service.prompt_next_pending_case(
        db_session,
        team_id=1,
        user_id=2,
        channel="web",
        agent_session_id=33,
        now=datetime(2026, 8, 6, 13, 0, 0),
    )

    db_session.refresh(case)

    assert first_event is not None
    assert second_event is None
    assert case.prompt_count == 1
    assert db_session.query(FollowUpTaskConfirmationPromptDelivery).count() == 1


def test_resolve_bound_reply_applies_confirmation_case(db_session):
    task = _create_task(db_session)
    case = _create_confirmation_case(db_session, task)

    event = FollowUpTaskConfirmationChannelService().resolve_bound_reply(
        db_session,
        team_id=1,
        user_id=2,
        case_public_id=case.public_id,
        reply_text="已完成",
    )

    db_session.refresh(task)
    db_session.refresh(case)

    assert event["event"] == "follow_up_task_confirmation_case_resolved"
    assert event["case"]["public_id"] == case.public_id
    assert event["decision"]["action"] == FollowUpTaskConfirmationResolutionAction.COMPLETE
    assert event["application"]["status"] == "APPLIED"
    assert task.status == FollowUpTaskStatus.COMPLETED
