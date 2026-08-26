"""MySQL concurrency coverage for authoritative Root interaction claims."""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest

from app.core.database import SessionLocal, engine
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
from app.services.agent.orchestrator.interaction import DatabaseInteractionResolver
from app.services.agent.ui.actions import AgentUIActionRepository

pytestmark = pytest.mark.integration


def _mysql_integration_enabled() -> bool:
    return os.getenv("RUN_MYSQL_INTEGRATION") == "1" and engine.dialect.name == "mysql"


def _continuation(workflow_ref: WorkflowRef) -> WorkflowContinuation:
    return WorkflowContinuation(
        workflow_ref=workflow_ref,
        parent_checkpoint_id=f"cp_root_{workflow_ref.workflow_id}",
        subgraph_checkpoint_ns=f"workflow_subgraph:{workflow_ref.workflow_id}",
        subgraph_checkpoint_id=f"cp_workflow_{workflow_ref.workflow_id}",
    )


def _seed_confirmation_action(*, suffix: str) -> tuple[int, str]:
    db = SessionLocal()
    try:
        workflow_ref = WorkflowRef(
            workflow_id=f"wf_follow_up_{suffix}",
            interrupt_id=f"int_confirm_{suffix}",
        )
        session = AgentSession(
            session_key=f"agent-claim:{suffix}",
            team_id=1,
            user_id=1,
        )
        db.add(session)
        db.flush()
        message = AgentMessage(
            team_id=1,
            user_id=1,
            session_id=session.id,
            role=AgentMessageRole.ASSISTANT,
            content="请确认",
        )
        db.add(message)
        db.flush()
        action = AgentUIActionRepository().register(
            db,
            AgentUIActionRegistration(
                public_id=f"act_root_confirm_{suffix}",
                team_id=1,
                user_id=1,
                session_id=session.id,
                message_id=message.id,
                action_type="submit_interaction",
                target={
                    "interaction_type": "confirmation",
                    "workflow_continuation": _continuation(workflow_ref).model_dump(mode="json"),
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
        public_id = action.public_id
        db.commit()
        return session_id, public_id
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _turn(*, session_id: int, action_id: str, request_id: str) -> RootTurnInput:
    return RootTurnInput(
        team_id=1,
        user_id=1,
        session_id=session_id,
        client_request_id=request_id,
        input=InteractionTurnInput(
            type="interaction",
            action_id=action_id,
            values={"choice": "confirm"},
        ),
    )


def _cleanup_session(session_id: int) -> None:
    db = SessionLocal()
    try:
        session = db.get(AgentSession, session_id)
        if session is not None:
            db.delete(session)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@pytest.mark.skipif(not _mysql_integration_enabled(), reason="requires RUN_MYSQL_INTEGRATION=1 and MySQL")
def test_root_resolver_commits_one_claim_before_any_workflow_side_effect() -> None:
    suffix = uuid4().hex
    session_id, action_id = _seed_confirmation_action(suffix=suffix)
    barrier = Barrier(2)

    def resolve(request_id: str) -> tuple[str, str | None]:
        barrier.wait(timeout=10)
        result = asyncio.run(
            DatabaseInteractionResolver().resolve(
                turn=_turn(session_id=session_id, action_id=action_id, request_id=request_id),
                context=RootContextSnapshot(),
                runtime=RootRuntimeContext(),
            )
        )
        return result.status, result.reason_code

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(resolve, [str(uuid4()), str(uuid4())]))

        assert sorted(results) == [
            ("REJECTED", "ACTION_ALREADY_CONSUMED"),
            ("RESOLVED", "STRUCTURED_WORKFLOW_CONTINUATION"),
        ]

        db = SessionLocal()
        try:
            action = db.query(AgentUIAction).filter(AgentUIAction.public_id == action_id).one()
            assert action.status == "CONSUMING"
            assert action.consumed_request_id is not None
        finally:
            db.close()
    finally:
        _cleanup_session(session_id)
