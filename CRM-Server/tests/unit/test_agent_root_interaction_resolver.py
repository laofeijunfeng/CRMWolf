"""Tests for authoritative Root interaction action claims."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.agent import AgentMessage, AgentMessageRole, AgentSession
from app.models.agent_persistence import AgentUIAction
from app.schemas.agent_persistence import AgentUIActionRegistration
from app.services.agent.orchestrator.contracts import (
    InteractionTurnInput,
    RootContextSnapshot,
    RootRuntimeContext,
    RootTurnInput,
    WorkflowContinuation,
    WorkflowRef,
)
from app.services.agent.orchestrator.errors import InteractionResolutionUnavailableError
from app.services.agent.orchestrator.interaction import DatabaseInteractionResolver
from app.services.agent.ui.actions import AgentUIActionRepository


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def _database():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            AgentSession.__table__,
            AgentMessage.__table__,
            AgentUIAction.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine)
    return engine, session_factory


def _continuation(workflow_ref: WorkflowRef) -> WorkflowContinuation:
    return WorkflowContinuation(
        workflow_ref=workflow_ref,
        parent_checkpoint_id=f"cp_root_{workflow_ref.workflow_id}",
        subgraph_checkpoint_ns=f"workflow_subgraph:{workflow_ref.workflow_id}",
        subgraph_checkpoint_id=f"cp_workflow_{workflow_ref.workflow_id}",
    )


def _seed_confirmation_action(
    session_factory,
    *,
    workflow_ref: WorkflowRef,
    valid_continuation: bool = True,
) -> int:
    db = session_factory()
    try:
        session = AgentSession(session_key="root-interaction", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.ASSISTANT,
            content="请确认",
        )
        db.add(message)
        db.flush()
        AgentUIActionRepository().register(
            db,
            AgentUIActionRegistration(
                public_id="act_root_confirm",
                team_id=1,
                user_id=2,
                session_id=session.id,
                message_id=message.id,
                action_type="submit_interaction",
                target={
                    "interaction_type": "confirmation",
                    "workflow_continuation": (
                        _continuation(workflow_ref).model_dump(mode="json")
                        if valid_continuation
                        else {"workflow_ref": workflow_ref.model_dump(mode="json")}
                    ),
                    "selection_mode": "single",
                    "choices": [
                        {"value": "confirm", "label": "确认", "disabled": False},
                        {"value": "cancel", "label": "取消", "disabled": False},
                    ],
                    "business_action": "confirm_follow_up",
                    "payload": {"task_id": 91},
                },
                consumption_mode="ONE_SHOT",
            ),
        )
        session_id = int(session.id)
        db.commit()
        return session_id
    finally:
        db.close()


def _turn(*, session_id: int, client_request_id: str | None = None, choice: str = "confirm") -> RootTurnInput:
    return RootTurnInput(
        team_id=1,
        user_id=2,
        session_id=session_id,
        client_request_id=client_request_id or str(uuid4()),
        input=InteractionTurnInput(
            type="interaction",
            action_id="act_root_confirm",
            values={"choice": choice, "task_id": 999},
        ),
    )


async def test_database_interaction_resolver_commits_claim_before_workflow_resume() -> None:
    engine, session_factory = _database()
    try:
        workflow_ref = WorkflowRef(workflow_id="wf_follow_up", interrupt_id="int_confirm")
        session_id = _seed_confirmation_action(session_factory, workflow_ref=workflow_ref)
        resolver = DatabaseInteractionResolver(session_factory=session_factory)
        request_id = str(uuid4())

        resolution = await resolver.resolve(
            turn=_turn(session_id=session_id, client_request_id=request_id),
            context=RootContextSnapshot(),
            runtime=RootRuntimeContext(),
        )

        assert resolution.status == "RESOLVED"
        assert resolution.resolved_action is not None
        assert resolution.resolved_action.continuation == _continuation(workflow_ref)
        assert resolution.resolved_action.claim_outcome == "ACQUIRED"
        assert resolution.resolved_action.resume_payload == {
            "kind": "confirm",
            "content": "确认",
            "source": "web",
            "provider": None,
            "metadata": {
                "business_action": "confirm_follow_up",
                "payload": {"task_id": 91},
            },
        }

        verification_db = session_factory()
        try:
            action = verification_db.query(AgentUIAction).one()
            assert action.status == "CONSUMING"
            assert action.consumed_request_id == request_id
        finally:
            verification_db.close()
    finally:
        engine.dispose()


async def test_database_interaction_resolver_rejects_a_second_submission_after_committed_claim() -> None:
    engine, session_factory = _database()
    try:
        workflow_ref = WorkflowRef(workflow_id="wf_follow_up", interrupt_id="int_confirm")
        session_id = _seed_confirmation_action(session_factory, workflow_ref=workflow_ref)
        resolver = DatabaseInteractionResolver(session_factory=session_factory)

        first = await resolver.resolve(
            turn=_turn(session_id=session_id, client_request_id=str(uuid4())),
            context=RootContextSnapshot(),
            runtime=RootRuntimeContext(),
        )
        second = await resolver.resolve(
            turn=_turn(session_id=session_id, client_request_id=str(uuid4()), choice="cancel"),
            context=RootContextSnapshot(),
            runtime=RootRuntimeContext(),
        )

        assert first.status == "RESOLVED"
        assert second.status == "REJECTED"
        assert second.reason_code == "ACTION_ALREADY_CONSUMED"
        assert second.resolved_action is None

        verification_db = session_factory()
        try:
            assert verification_db.query(AgentUIAction).one().status == "CONSUMING"
        finally:
            verification_db.close()
    finally:
        engine.dispose()


async def test_database_interaction_resolver_rejects_invalid_continuation_and_releases_claim() -> None:
    engine, session_factory = _database()
    try:
        bound_ref = WorkflowRef(workflow_id="wf_bound", interrupt_id="int_bound")
        session_id = _seed_confirmation_action(
            session_factory,
            workflow_ref=bound_ref,
            valid_continuation=False,
        )
        resolver = DatabaseInteractionResolver(session_factory=session_factory)

        resolution = await resolver.resolve(
            turn=_turn(session_id=session_id),
            context=RootContextSnapshot(),
            runtime=RootRuntimeContext(),
        )

        assert resolution.status == "REJECTED"
        assert resolution.reason_code == "ACTION_WORKFLOW_BINDING_INVALID"
        assert resolution.resolved_action is None
        verification_db = session_factory()
        try:
            action = verification_db.query(AgentUIAction).one()
            assert action.status == "ACTIVE"
            assert action.consumed_request_id is None
        finally:
            verification_db.close()
    finally:
        engine.dispose()


async def test_database_interaction_resolver_rejects_invalid_values_and_releases_claim() -> None:
    engine, session_factory = _database()
    try:
        workflow_ref = WorkflowRef(workflow_id="wf_follow_up", interrupt_id="int_confirm")
        session_id = _seed_confirmation_action(session_factory, workflow_ref=workflow_ref)
        resolver = DatabaseInteractionResolver(session_factory=session_factory)

        resolution = await resolver.resolve(
            turn=_turn(session_id=session_id, choice="unsupported"),
            context=RootContextSnapshot(),
            runtime=RootRuntimeContext(),
        )

        assert resolution.status == "REJECTED"
        assert resolution.reason_code == "ACTION_VALUES_INVALID"
        verification_db = session_factory()
        try:
            action = verification_db.query(AgentUIAction).one()
            assert action.status == "ACTIVE"
            assert action.consumed_request_id is None
        finally:
            verification_db.close()
    finally:
        engine.dispose()


async def test_database_interaction_resolver_fails_closed_when_claim_transaction_is_unavailable() -> None:
    def unavailable_session_factory():
        raise RuntimeError("database unavailable")

    resolver = DatabaseInteractionResolver(session_factory=unavailable_session_factory)

    try:
        await resolver.resolve(
            turn=_turn(session_id=1),
            context=RootContextSnapshot(),
            runtime=RootRuntimeContext(),
        )
    except InteractionResolutionUnavailableError:
        pass
    else:
        raise AssertionError("unavailable action ledger must fail closed")
