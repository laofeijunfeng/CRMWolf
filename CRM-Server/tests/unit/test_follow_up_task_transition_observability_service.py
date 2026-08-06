import json
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
from app.models.sales_commitment import (
    DueAtGranularity,
    FollowUpTask,
    FollowUpTaskConfirmationCase,
    FollowUpTaskConfirmationPromptDelivery,
    FollowUpTaskConfirmationPromptStatus,
    FollowUpTaskConfirmationResolutionAction,
    FollowUpTaskConfirmationStatus,
    FollowUpTaskEvent,
    FollowUpTaskEventType,
    FollowUpTaskLLMMatcherRun,
    FollowUpTaskReconciliationEvaluationRun,
    FollowUpTaskReconciliationRun,
    FollowUpTaskSourceType,
    FollowUpTaskStatus,
    FollowUpTaskTransitionPolicyDecisionLog,
    SalesCommitment,
)
from app.schemas.sales_commitment import FollowUpTaskInternalCreate
from app.services.follow_up_task_transition_observability_service import (
    follow_up_task_transition_observability_service,
)


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
            SalesCommitment.__table__,
            FollowUpTask.__table__,
            FollowUpTaskEvent.__table__,
            FollowUpTaskConfirmationCase.__table__,
            FollowUpTaskConfirmationPromptDelivery.__table__,
            FollowUpTaskTransitionPolicyDecisionLog.__table__,
            FollowUpTaskReconciliationRun.__table__,
            FollowUpTaskLLMMatcherRun.__table__,
            FollowUpTaskReconciliationEvaluationRun.__table__,
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
    db_session.add_all(
        [
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
                source_content="客户说预算已经通过。",
                summary="客户预算已通过。",
                occurred_at=datetime(2026, 8, 6, 10, 0, 0),
                owner_id="2",
                creator_id="2",
            ),
        ]
    )


def _create_task(db_session, *, owner_id: str = "2", task_hash: str = "task-hash") -> FollowUpTask:
    return follow_up_task_crud.create(
        db_session,
        FollowUpTaskInternalCreate(
            team_id=1,
            customer_id=1,
            owner_id=owner_id,
            creator_id=owner_id,
            title="确认客户预算是否通过",
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


def _add_transition_event(
    db_session,
    task: FollowUpTask,
    *,
    created_time: datetime,
    event_type: str = FollowUpTaskEventType.COMPLETED,
    execution_kind: str = "automatic",
    action: str = "COMPLETE",
    decision: str = "COMPLETE",
    confidence: float = 0.94,
) -> FollowUpTaskEvent:
    event = FollowUpTaskEvent(
        team_id=task.team_id,
        task_id=task.id,
        event_type=event_type,
        actor_id=task.owner_id,
        source_type=task.source_type,
        source_activity_id=task.source_activity_id,
        source_public_id=task.source_public_id,
        previous_status=FollowUpTaskStatus.OPEN,
        new_status=FollowUpTaskStatus.COMPLETED,
        payload_json={
            "reason": "RECONCILIATION_TRANSITION_PLAN_EXECUTED",
            "plan_source": "unit_test_plan" if execution_kind == "automatic" else "confirmation_case_reply",
            "execution_kind": execution_kind,
            "action": action,
            "task_public_id": task.public_id,
            "confidence": confidence,
            "decision": decision,
            "rollback": {"type": "REOPEN", "previous_status": FollowUpTaskStatus.OPEN},
        },
        created_time=created_time,
    )
    db_session.add(event)
    db_session.flush()
    return event


def _add_rollback_event(
    db_session,
    task: FollowUpTask,
    *,
    rolled_back_event_public_id: str,
    created_time: datetime,
) -> FollowUpTaskEvent:
    event = FollowUpTaskEvent(
        team_id=task.team_id,
        task_id=task.id,
        event_type=FollowUpTaskEventType.REOPENED,
        actor_id=task.owner_id,
        source_type=task.source_type,
        source_activity_id=task.source_activity_id,
        source_public_id=task.source_public_id,
        previous_status=FollowUpTaskStatus.COMPLETED,
        new_status=FollowUpTaskStatus.OPEN,
        payload_json={
            "reason": "RECONCILIATION_TRANSITION_ROLLBACK",
            "rolled_back_event_public_id": rolled_back_event_public_id,
            "rolled_back_action": "COMPLETE",
            "task_public_id": task.public_id,
        },
        created_time=created_time,
    )
    db_session.add(event)
    db_session.flush()
    return event


def _add_confirmation_case(
    db_session,
    task: FollowUpTask,
    *,
    created_time: datetime,
    status: str = FollowUpTaskConfirmationStatus.PENDING,
    suggested_action: str = FollowUpTaskConfirmationResolutionAction.COMPLETE,
    resolved_action: str | None = None,
    resolved_at: datetime | None = None,
    application_status: str | None = None,
    application_skip_reason: str | None = None,
    unresolved_reply_count: int = 0,
) -> FollowUpTaskConfirmationCase:
    case = FollowUpTaskConfirmationCase(
        team_id=task.team_id,
        task_id=task.id,
        customer_id=task.customer_id,
        owner_id=task.owner_id,
        creator_id=task.owner_id,
        status=status,
        suggested_action=suggested_action,
        confirmation_hash=f"case-hash-{task.task_hash}-{created_time.isoformat()}",
        question_text="这个任务要继续保留、延期，还是取消？",
        source_activity_id=task.source_activity_id,
        source_public_id=task.source_public_id,
        resolved_action=resolved_action,
        resolved_by_id=task.owner_id if resolved_action else None,
        resolved_at=resolved_at,
        application_status=application_status,
        application_skip_reason=application_skip_reason,
        applied_by_id=task.owner_id if application_status else None,
        applied_at=resolved_at if application_status else None,
        unresolved_reply_count=unresolved_reply_count,
        created_time=created_time,
    )
    db_session.add(case)
    db_session.flush()
    return case


def _add_prompt_delivery(
    db_session,
    case: FollowUpTaskConfirmationCase,
    *,
    prompted_at: datetime,
    channel: str = "web",
    provider: str | None = "web-agent",
) -> FollowUpTaskConfirmationPromptDelivery:
    delivery = FollowUpTaskConfirmationPromptDelivery(
        team_id=case.team_id,
        case_id=case.id,
        owner_id=case.owner_id,
        channel=channel,
        provider=provider,
        agent_session_id=1001,
        interaction_id=f"interaction-{channel}-{prompted_at.isoformat()}",
        prompt_key=f"{case.public_id}:{channel}:{prompted_at.isoformat()}",
        status=FollowUpTaskConfirmationPromptStatus.SENT,
        payload_json={"case_public_id": case.public_id},
        prompted_at=prompted_at,
    )
    db_session.add(delivery)
    db_session.flush()
    return delivery


def _add_policy_decision(
    db_session,
    task: FollowUpTask,
    *,
    created_time: datetime,
    allowed: bool,
    reason: str,
    action: str = "COMPLETE",
    enabled: bool = True,
    config_errors_json: list[str] | None = None,
) -> FollowUpTaskTransitionPolicyDecisionLog:
    decision = FollowUpTaskTransitionPolicyDecisionLog(
        team_id=task.team_id,
        owner_id=task.owner_id,
        actor_id=task.owner_id,
        task_id=task.id,
        source_type=task.source_type,
        source_activity_id=task.source_activity_id,
        source_public_id=task.source_public_id,
        action=action,
        allowed=allowed,
        reason=reason,
        enabled=enabled,
        owner_allowlist_configured=True,
        allowed_actions_json=["COMPLETE", "DELAY"],
        config_errors_json=config_errors_json,
        policy_result_json={
            "allowed": allowed,
            "reason": reason,
            "task_public_id": task.public_id,
        },
        context_json={"task_public_id": task.public_id},
        created_time=created_time,
    )
    db_session.add(decision)
    db_session.flush()
    return decision


def _add_reconciliation_run(
    db_session,
    task: FollowUpTask,
    *,
    created_time: datetime,
    status: str = "SUCCESS",
    skip_reason: str | None = None,
    include_cross_owner: bool = False,
    candidate_count: int = 1,
) -> FollowUpTaskReconciliationRun:
    run = FollowUpTaskReconciliationRun(
        team_id=task.team_id,
        customer_id=task.customer_id,
        owner_id=task.owner_id,
        actor_id=task.owner_id,
        source_activity_id=task.source_activity_id,
        source_public_id=task.source_public_id,
        status=status,
        skip_reason=skip_reason,
        include_cross_owner=include_cross_owner,
        lookback_days=90,
        lookahead_days=30,
        limit=20,
        candidate_count=candidate_count,
        candidate_public_ids_json=[task.public_id] if candidate_count else [],
        filters_json={"activity_owner_id": task.owner_id},
        usage_policy_json={"mutation": "forbidden"},
        duration_ms=12,
        anchor_at=created_time,
        started_at=created_time,
        finished_at=created_time,
        created_time=created_time,
    )
    db_session.add(run)
    db_session.flush()
    return run


def _add_llm_matcher_run(
    db_session,
    task: FollowUpTask,
    *,
    created_time: datetime,
    status: str = "SUCCESS",
    source: str = "langchain_structured_output",
    decision: str = "COMPLETE",
    needs_confirmation: bool = False,
    schema_error_type: str | None = None,
    evaluation_failures_json: list[str] | None = None,
) -> FollowUpTaskLLMMatcherRun:
    run = FollowUpTaskLLMMatcherRun(
        team_id=task.team_id,
        owner_id=task.owner_id,
        actor_id=task.owner_id,
        source_activity_id=task.source_activity_id,
        source_public_id=task.source_public_id,
        status=status,
        source=source,
        decision=decision,
        task_public_id=task.public_id,
        candidate_public_ids_json=[task.public_id],
        confidence=0.94,
        needs_confirmation=needs_confirmation,
        forbid_auto_reasons_json=[],
        evidence_terms_json=["预算已经通过"],
        referenced_source_public_ids_json=[task.source_public_id] if task.source_public_id else [],
        evaluation_failures_json=evaluation_failures_json,
        model_name="test-model",
        structured_output_strategy="tool",
        schema_error_type=schema_error_type,
        schema_error_message="invalid structured output" if schema_error_type else None,
        duration_ms=320,
        started_at=created_time,
        finished_at=created_time,
        created_time=created_time,
    )
    db_session.add(run)
    db_session.flush()
    return run


def _add_evaluation_run(
    db_session,
    *,
    created_time: datetime,
    team_id: int | None = 1,
    ok: bool = False,
) -> FollowUpTaskReconciliationEvaluationRun:
    run = FollowUpTaskReconciliationEvaluationRun(
        team_id=team_id,
        suite_name="unit_golden",
        fixture_path="tests/fixtures/follow_up_task_reconciliation_golden_cases.json",
        fixture_hash="fixture-hash",
        status="SUCCESS",
        ok=ok,
        total_cases=5,
        passed_cases=4 if ok is False else 5,
        failed_cases=1 if ok is False else 0,
        false_close_count=1 if ok is False else 0,
        false_close_rate=0.2 if ok is False else 0.0,
        false_delay_count=0,
        false_delay_rate=0.0,
        missed_confirmation_count=1 if ok is False else 0,
        missed_confirmation_rate=0.2 if ok is False else 0.0,
        over_confirmation_count=0,
        over_confirmation_rate=0.0,
        metrics_json={
            "false_close": {"count": 1 if ok is False else 0, "rate": 0.2 if ok is False else 0.0},
            "false_delay": {"count": 0, "rate": 0.0},
            "missed_confirmation": {"count": 1 if ok is False else 0, "rate": 0.2 if ok is False else 0.0},
            "over_confirmation": {"count": 0, "rate": 0.0},
        },
        duration_ms=17,
        started_at=created_time,
        finished_at=created_time,
        created_time=created_time,
    )
    db_session.add(run)
    db_session.flush()
    return run


def test_observability_summary_counts_transition_confirmation_and_prompt_facts(db_session):
    start_at = datetime(2026, 8, 6, 0, 0, 0)
    end_at = start_at + timedelta(days=1)
    task = _create_task(db_session)
    automatic_event = _add_transition_event(db_session, task, created_time=start_at + timedelta(hours=9))
    _add_transition_event(
        db_session,
        task,
        created_time=start_at + timedelta(hours=10),
        event_type=FollowUpTaskEventType.UPDATED,
        execution_kind="manual_confirmation",
        action="DELAY",
        decision="DELAY",
        confidence=1.0,
    )
    _add_rollback_event(
        db_session,
        task,
        rolled_back_event_public_id=automatic_event.public_id,
        created_time=start_at + timedelta(hours=11),
    )
    pending_case = _add_confirmation_case(
        db_session,
        task,
        created_time=start_at + timedelta(hours=8),
        suggested_action=FollowUpTaskConfirmationResolutionAction.DELAY,
        unresolved_reply_count=2,
    )
    _add_confirmation_case(
        db_session,
        task,
        created_time=start_at + timedelta(hours=7),
        status=FollowUpTaskConfirmationStatus.RESOLVED,
        suggested_action=FollowUpTaskConfirmationResolutionAction.COMPLETE,
        resolved_action=FollowUpTaskConfirmationResolutionAction.COMPLETE,
        resolved_at=start_at + timedelta(hours=10, minutes=30),
        application_status="APPLIED",
    )
    _add_prompt_delivery(db_session, pending_case, prompted_at=start_at + timedelta(hours=8), channel="web")
    _add_prompt_delivery(
        db_session,
        pending_case,
        prompted_at=start_at + timedelta(hours=9),
        channel="im",
        provider="lark",
    )
    _add_policy_decision(
        db_session,
        task,
        created_time=start_at + timedelta(hours=9),
        allowed=True,
        reason="ALLOWED",
    )
    _add_policy_decision(
        db_session,
        task,
        created_time=start_at + timedelta(hours=10),
        allowed=False,
        reason="ACTION_NOT_ALLOWED",
        action="DELAY",
    )
    _add_policy_decision(
        db_session,
        task,
        created_time=start_at + timedelta(hours=11),
        allowed=False,
        reason="CONFIG_INVALID",
        enabled=False,
        config_errors_json=["follow_up_task_auto_transition_enabled:expected_bool"],
    )
    _add_reconciliation_run(db_session, task, created_time=start_at + timedelta(hours=9))
    _add_reconciliation_run(
        db_session,
        task,
        created_time=start_at + timedelta(hours=10),
        status="SKIPPED",
        skip_reason="NO_OPEN_CANDIDATES",
        include_cross_owner=True,
        candidate_count=0,
    )
    _add_llm_matcher_run(db_session, task, created_time=start_at + timedelta(hours=9))
    _add_llm_matcher_run(
        db_session,
        task,
        created_time=start_at + timedelta(hours=10),
        status="FAILED",
        source="structured_output_error",
        decision="KEEP_OPEN",
        schema_error_type="AgentLangChainStructuredOutputError",
        evaluation_failures_json=["schema_error"],
    )
    evaluation_run = _add_evaluation_run(db_session, created_time=start_at + timedelta(hours=12))
    db_session.commit()

    summary = follow_up_task_transition_observability_service.summarize(
        db_session,
        team_id=1,
        start_at=start_at,
        end_at=end_at,
        owner_id="2",
    ).to_dict()

    assert summary["transition_events"]["transition_events"] == 2
    assert summary["transition_events"]["automatic_transition_events"] == 1
    assert summary["transition_events"]["manual_confirmation_transition_events"] == 1
    assert summary["transition_events"]["rollback_events"] == 1
    assert summary["transition_events"]["automatic_by_action"] == {"COMPLETE": 1}
    assert summary["transition_events"]["manual_confirmation_by_action"] == {"DELAY": 1}
    assert summary["transition_events"]["rollback_by_action"] == {"COMPLETE": 1}
    assert summary["transition_events"]["transition_ratio"]["automatic_percent"] == 0.5
    assert summary["transition_events"]["rollback_event_public_ids"][0].startswith("fte_")
    assert summary["confirmation_cases"]["created_cases"] == 2
    assert summary["confirmation_cases"]["resolved_cases"] == 1
    assert summary["confirmation_cases"]["created_by_suggested_action"] == {"COMPLETE": 1, "DELAY": 1}
    assert summary["confirmation_cases"]["resolved_by_action"] == {"COMPLETE": 1}
    assert summary["confirmation_cases"]["application_by_status"] == {"APPLIED": 1}
    assert summary["confirmation_cases"]["unresolved_reply_total"] == 2
    assert summary["prompt_deliveries"]["total_deliveries"] == 2
    assert summary["prompt_deliveries"]["by_channel"] == {"im": 1, "web": 1}
    assert summary["prompt_deliveries"]["by_provider"] == {"lark": 1, "web-agent": 1}
    assert summary["policy_decisions"]["total_decisions"] == 3
    assert summary["policy_decisions"]["allowed_decisions"] == 1
    assert summary["policy_decisions"]["blocked_decisions"] == 2
    assert summary["policy_decisions"]["allow_ratio"]["allowed_percent"] == 0.3333
    assert summary["policy_decisions"]["by_reason"] == {
        "ACTION_NOT_ALLOWED": 1,
        "ALLOWED": 1,
        "CONFIG_INVALID": 1,
    }
    assert summary["policy_decisions"]["by_action"] == {"COMPLETE": 2, "DELAY": 1}
    assert summary["policy_decisions"]["by_enabled"] == {"false": 1, "true": 2}
    assert summary["policy_decisions"]["config_error_total"] == 1
    assert summary["reconciliation_runs"]["total_runs"] == 2
    assert summary["reconciliation_runs"]["by_status"] == {"SKIPPED": 1, "SUCCESS": 1}
    assert summary["reconciliation_runs"]["by_include_cross_owner"] == {"false": 1, "true": 1}
    assert summary["reconciliation_runs"]["candidate_count_total"] == 1
    assert summary["llm_matcher_runs"]["total_runs"] == 2
    assert summary["llm_matcher_runs"]["by_status"] == {"FAILED": 1, "SUCCESS": 1}
    assert summary["llm_matcher_runs"]["by_schema_error_type"] == {
        "AgentLangChainStructuredOutputError": 1,
        "UNKNOWN": 1,
    }
    assert summary["llm_matcher_runs"]["schema_error_total"] == 1
    assert summary["llm_matcher_runs"]["evaluation_failure_total"] == 1
    assert summary["evaluation_runs"]["total_runs"] == 1
    assert summary["evaluation_runs"]["by_status"] == {"SUCCESS": 1}
    assert summary["evaluation_runs"]["by_ok"] == {"false": 1}
    assert summary["evaluation_runs"]["quality_gate_failures"] == 1
    assert summary["evaluation_runs"]["case_count_total"] == 5
    assert summary["evaluation_runs"]["failed_case_count_total"] == 1
    assert summary["evaluation_runs"]["false_close_count_total"] == 1
    assert summary["evaluation_runs"]["missed_confirmation_count_total"] == 1
    assert summary["evaluation_runs"]["latest_run"]["id"] == evaluation_run.public_id
    assert summary["evaluation_runs"]["latest_run"]["false_close_rate"] == 0.2
    assert "feature_flag_hit" not in {gap["metric"] for gap in summary["metric_gaps"]}
    assert summary["metric_gaps"] == []


def test_observability_summary_filters_by_window_and_owner(db_session):
    start_at = datetime(2026, 8, 6, 0, 0, 0)
    end_at = start_at + timedelta(days=1)
    owner_task = _create_task(db_session, owner_id="2", task_hash="owner-task")
    other_owner_task = _create_task(db_session, owner_id="3", task_hash="other-owner-task")
    owner_case = _add_confirmation_case(db_session, owner_task, created_time=start_at + timedelta(hours=8))
    _add_transition_event(db_session, owner_task, created_time=start_at + timedelta(hours=8))
    _add_prompt_delivery(db_session, owner_case, prompted_at=start_at + timedelta(hours=8))
    _add_policy_decision(
        db_session,
        owner_task,
        created_time=start_at + timedelta(hours=8),
        allowed=True,
        reason="ALLOWED",
    )
    _add_reconciliation_run(db_session, owner_task, created_time=start_at + timedelta(hours=8))
    _add_llm_matcher_run(db_session, owner_task, created_time=start_at + timedelta(hours=8))
    _add_evaluation_run(db_session, created_time=start_at + timedelta(hours=8), team_id=None, ok=True)
    _add_transition_event(db_session, other_owner_task, created_time=start_at + timedelta(hours=9))
    _add_confirmation_case(db_session, other_owner_task, created_time=start_at + timedelta(hours=9))
    _add_policy_decision(
        db_session,
        other_owner_task,
        created_time=start_at + timedelta(hours=9),
        allowed=False,
        reason="OWNER_NOT_ALLOWED",
    )
    _add_reconciliation_run(db_session, other_owner_task, created_time=start_at + timedelta(hours=9))
    _add_llm_matcher_run(db_session, other_owner_task, created_time=start_at + timedelta(hours=9))
    _add_transition_event(db_session, owner_task, created_time=start_at - timedelta(minutes=1))
    _add_transition_event(db_session, owner_task, created_time=end_at)
    _add_policy_decision(
        db_session,
        owner_task,
        created_time=start_at - timedelta(minutes=1),
        allowed=True,
        reason="ALLOWED",
    )
    _add_policy_decision(
        db_session,
        owner_task,
        created_time=end_at,
        allowed=True,
        reason="ALLOWED",
    )
    db_session.commit()

    summary = follow_up_task_transition_observability_service.summarize(
        db_session,
        team_id=1,
        start_at=start_at,
        end_at=end_at,
        owner_id="2",
    )

    data = summary.to_dict()
    assert data["transition_events"]["transition_events"] == 1
    assert data["confirmation_cases"]["created_cases"] == 1
    assert data["prompt_deliveries"]["total_deliveries"] == 1
    assert data["policy_decisions"]["total_decisions"] == 1
    assert data["reconciliation_runs"]["total_runs"] == 1
    assert data["llm_matcher_runs"]["total_runs"] == 1
    assert data["evaluation_runs"]["total_runs"] == 1
    assert data["evaluation_runs"]["by_ok"] == {"true": 1}
    assert data["owner_id"] == "2"


def test_observability_summary_does_not_expose_internal_ids(db_session):
    start_at = datetime(2026, 8, 6, 0, 0, 0)
    end_at = start_at + timedelta(days=1)
    task = _create_task(db_session)
    automatic_event = _add_transition_event(db_session, task, created_time=start_at + timedelta(hours=9))
    _add_rollback_event(
        db_session,
        task,
        rolled_back_event_public_id=automatic_event.public_id,
        created_time=start_at + timedelta(hours=10),
    )
    _add_policy_decision(
        db_session,
        task,
        created_time=start_at + timedelta(hours=8),
        allowed=False,
        reason="CONFIG_INVALID",
        config_errors_json=["follow_up_task_auto_transition_enabled:expected_bool"],
    )
    _add_reconciliation_run(db_session, task, created_time=start_at + timedelta(hours=8))
    _add_llm_matcher_run(
        db_session,
        task,
        created_time=start_at + timedelta(hours=8),
        status="FAILED",
        source="structured_output_error",
        decision="KEEP_OPEN",
        schema_error_type="AgentLangChainStructuredOutputError",
    )
    db_session.commit()

    summary = follow_up_task_transition_observability_service.summarize(
        db_session,
        team_id=1,
        start_at=start_at,
        end_at=end_at,
    ).to_dict()
    serialized = json.dumps(summary, ensure_ascii=False)

    assert "\"task_id\"" not in serialized
    assert "\"case_id\"" not in serialized
    assert "\"source_activity_id\"" not in serialized
    assert "\"event_id\"" not in serialized
    assert automatic_event.public_id not in summary["transition_events"]["rollback_event_public_ids"]
