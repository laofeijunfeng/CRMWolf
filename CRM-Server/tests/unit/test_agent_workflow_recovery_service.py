"""Tests for controlled Agent workflow recovery."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.crud.agent import agent_session_crud, agent_workflow_action_crud
from app.models.agent import AgentSession, AgentWorkflowAction, AgentWorkflowActionStatus
from app.schemas.agent import AgentSessionCreate, AgentWorkflowActionCreate
from app.services.agent import action_workflow
from app.services.agent.workflow_recovery_policy import evaluate_background_recovery_policy
from app.services.agent.workflow_recovery_service import AgentWorkflowRecoveryService


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


class FakeRuntime:
    def __init__(self) -> None:
        self.calls = []

    async def retry_workflow(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs["actions"]


def _db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[AgentSession.__table__, AgentWorkflowAction.__table__])
    Session = sessionmaker(bind=engine)
    return engine, Session()


def _create_session(db, *, session_key: str = "session-001", user_id: int = 2):
    return agent_session_crud.create(
        db,
        AgentSessionCreate(
            session_key=session_key,
            team_id=1,
            user_id=user_id,
            title="Agent",
        ),
    )


def _create_action(
    db,
    *,
    workflow_id: str = "wf_001",
    action_id: str = "act_001",
    action_type: str = "refresh_customer_profile",
    status: str = AgentWorkflowActionStatus.FAILED,
    scope: str = action_workflow.SCOPE_DERIVED_AUTOMATION,
    execution_policy: str = action_workflow.EXECUTION_AUTO_EXECUTE,
    team_id: int = 1,
    session_id: int | None = 1,
    user_id: int | None = 2,
):
    return agent_workflow_action_crud.create(
        db,
        AgentWorkflowActionCreate(
            workflow_id=workflow_id,
            action_id=action_id,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            source_type="agent_planning",
            action_type=action_type,
            status=status,
            scope=scope,
            source=action_workflow.SOURCE_SYSTEM_AUTOMATION,
            execution_policy=execution_policy,
            on_reject=action_workflow.ON_REJECT_ASK_CLARIFICATION,
            blocking=False,
        ),
    )


async def test_workflow_recovery_dry_run_classifies_safe_actions_without_runtime_call():
    engine, db = _db_session()
    try:
        session = _create_session(db)
        _create_action(db, session_id=session.id)
        runtime = FakeRuntime()
        service = AgentWorkflowRecoveryService(runtime=runtime)  # type: ignore[arg-type]

        result = await service.recover_once(
            db,
            dry_run=True,
            safe_action_types=["refresh_customer_profile"],
        )

        assert result["eligible_workflows"] == 1
        assert result["retried_workflows"] == 0
        assert result["dry_run"] is True
        assert runtime.calls == []
    finally:
        db.close()
        engine.dispose()


async def test_workflow_recovery_skips_confirmation_actions_even_when_retryable():
    engine, db = _db_session()
    try:
        session = _create_session(db)
        _create_action(
            db,
            session_id=session.id,
            action_type="create_opportunity",
            scope=action_workflow.SCOPE_OPTIONAL_SUGGESTION,
            execution_policy=action_workflow.EXECUTION_REQUIRES_CONFIRMATION,
        )
        runtime = FakeRuntime()
        service = AgentWorkflowRecoveryService(runtime=runtime)  # type: ignore[arg-type]

        result = await service.recover_once(
            db,
            dry_run=False,
            safe_action_types=["create_opportunity"],
        )

        assert result["eligible_workflows"] == 0
        assert result["skipped"]["waiting_user"] == 1
        decision = result["decisions"][0]
        assert decision["policy_reasons"]["policy_requires_confirmation"] == 1
        assert runtime.calls == []
    finally:
        db.close()
        engine.dispose()


async def test_workflow_recovery_delegates_safe_workflow_to_root_runtime():
    engine, db = _db_session()
    try:
        session = _create_session(db)
        _create_action(db, session_id=session.id)
        runtime = FakeRuntime()
        service = AgentWorkflowRecoveryService(runtime=runtime)  # type: ignore[arg-type]

        result = await service.recover_once(
            db,
            dry_run=False,
            safe_action_types=["refresh_customer_profile"],
        )

        assert result["eligible_workflows"] == 1
        assert result["retried_workflows"] == 1
        assert len(runtime.calls) == 1
        assert runtime.calls[0]["authorization"] == ""
        assert runtime.calls[0]["retry_source"] == "background_recovery"
    finally:
        db.close()
        engine.dispose()


async def test_workflow_recovery_rejects_allowlisted_action_without_recovery_capability():
    engine, db = _db_session()
    try:
        session = _create_session(db)
        _create_action(
            db,
            session_id=session.id,
            action_type="unknown_internal_action",
        )

        decision = evaluate_background_recovery_policy(
            _create_action(
                db,
                action_id="act_unknown_2",
                session_id=session.id,
                action_type="unknown_internal_action",
            ),
            safe_action_types=["unknown_internal_action"],
        )

        assert decision.allowed is False
        assert decision.reason == "background_recovery_not_allowed"
    finally:
        db.close()
        engine.dispose()


async def test_workflow_recovery_delegates_only_safe_retryable_actions():
    engine, db = _db_session()
    try:
        session = _create_session(db)
        safe = _create_action(db, session_id=session.id)
        _create_action(
            db,
            action_id="act_unsafe",
            action_type="create_customer_activity",
            session_id=session.id,
        )
        runtime = FakeRuntime()
        service = AgentWorkflowRecoveryService(runtime=runtime)  # type: ignore[arg-type]

        result = await service.recover_once(
            db,
            dry_run=False,
            safe_action_types=["refresh_customer_profile", "create_customer_activity"],
        )

        assert result["eligible_workflows"] == 1
        assert result["retried_workflows"] == 1
        assert [action.action_id for action in runtime.calls[0]["actions"]] == [safe.action_id]
        decision = result["decisions"][0]
        assert decision["policy_reasons"]["user_authorization_required"] == 1
    finally:
        db.close()
        engine.dispose()


async def test_workflow_recovery_resolves_owner_from_system_action_workflow():
    engine, db = _db_session()
    try:
        session = _create_session(db)
        _create_action(
            db,
            action_id="act_parent",
            status=AgentWorkflowActionStatus.EXECUTED,
            scope=action_workflow.SCOPE_REQUIRED_WRITE,
            execution_policy=action_workflow.EXECUTION_REQUIRES_CONFIRMATION,
            session_id=session.id,
            user_id=2,
        )
        _create_action(
            db,
            action_id="act_system_safe",
            status=AgentWorkflowActionStatus.FAILED,
            session_id=session.id,
            user_id=None,
        )
        runtime = FakeRuntime()
        service = AgentWorkflowRecoveryService(runtime=runtime)  # type: ignore[arg-type]

        result = await service.recover_once(
            db,
            dry_run=False,
            safe_action_types=["refresh_customer_profile"],
            team_id=1,
            user_id=2,
        )

        assert result["eligible_workflows"] == 1
        assert result["retried_workflows"] == 1
        assert runtime.calls[0]["user_id"] == 2
        assert [action.action_id for action in runtime.calls[0]["actions"]] == ["act_system_safe"]
    finally:
        db.close()
        engine.dispose()


async def test_workflow_recovery_skips_multi_session_workflow():
    engine, db = _db_session()
    try:
        first = _create_session(db, session_key="session-001")
        second = _create_session(db, session_key="session-002")
        _create_action(db, session_id=first.id)
        _create_action(db, action_id="act_002", status=AgentWorkflowActionStatus.BLOCKED, session_id=second.id)
        runtime = FakeRuntime()
        service = AgentWorkflowRecoveryService(runtime=runtime)  # type: ignore[arg-type]

        result = await service.recover_once(
            db,
            dry_run=False,
            safe_action_types=["refresh_customer_profile"],
        )

        assert result["eligible_workflows"] == 0
        assert result["skipped"]["multiple_sessions"] == 1
        assert runtime.calls == []
    finally:
        db.close()
        engine.dispose()


async def test_workflow_recovery_skips_cross_team_workflow_without_crashing_batch():
    engine, db = _db_session()
    try:
        _create_action(db, workflow_id="wf_cross_team", action_id="act_team_1", team_id=1, session_id=None, user_id=2)
        _create_action(db, workflow_id="wf_cross_team", action_id="act_team_2", team_id=2, session_id=None, user_id=3)
        runtime = FakeRuntime()
        service = AgentWorkflowRecoveryService(runtime=runtime)  # type: ignore[arg-type]

        result = await service.recover_once(
            db,
            dry_run=False,
            safe_action_types=["refresh_customer_profile"],
        )

        assert result["eligible_workflows"] == 0
        assert result["skipped"]["multiple_teams"] == 1
        assert result["policy_reasons"] == {}
        assert runtime.calls == []
    finally:
        db.close()
        engine.dispose()


async def test_workflow_recovery_policy_rejects_required_write_even_when_allowlisted():
    engine, db = _db_session()
    try:
        session = _create_session(db)
        action = _create_action(
            db,
            session_id=session.id,
            action_type="create_opportunity",
            scope=action_workflow.SCOPE_REQUIRED_WRITE,
            execution_policy=action_workflow.EXECUTION_AUTO_EXECUTE,
        )

        decision = evaluate_background_recovery_policy(action, safe_action_types=["create_opportunity"])

        assert decision.allowed is False
        assert decision.reason == "scope_not_derived_automation"
        assert decision.execution_mode == "dry_run_only"
    finally:
        db.close()
        engine.dispose()


async def test_workflow_recovery_policy_rejects_user_authorized_write_actions():
    engine, db = _db_session()
    try:
        session = _create_session(db)
        action = _create_action(
            db,
            session_id=session.id,
            action_type="transition_follow_up_task",
            scope=action_workflow.SCOPE_DERIVED_AUTOMATION,
            execution_policy=action_workflow.EXECUTION_AUTO_EXECUTE,
        )

        decision = evaluate_background_recovery_policy(action, safe_action_types=["transition_follow_up_task"])

        assert decision.allowed is False
        assert decision.reason == "user_authorization_required"
        assert decision.requires_user_authorization is True
    finally:
        db.close()
        engine.dispose()


async def test_workflow_recovery_reports_policy_reason_for_unallowlisted_action():
    engine, db = _db_session()
    try:
        session = _create_session(db)
        _create_action(db, session_id=session.id, action_type="refresh_customer_profile")
        runtime = FakeRuntime()
        service = AgentWorkflowRecoveryService(runtime=runtime)  # type: ignore[arg-type]

        result = await service.recover_once(db, dry_run=True, safe_action_types=[])

        assert result["eligible_workflows"] == 0
        assert result["skipped"]["no_safe_action"] == 1
        assert result["policy_reasons"]["action_type_not_allowlisted"] == 1
        decision = result["decisions"][0]
        assert decision["policy_reasons"]["action_type_not_allowlisted"] == 1
        assert decision["retryable_action_policies"][0]["execution_mode"] == "dry_run_only"
    finally:
        db.close()
        engine.dispose()
