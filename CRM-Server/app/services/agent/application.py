"""Application service for CRM AI Agent turns.

This module owns channel-independent Agent turn orchestration. HTTP and IM
adapters should call this service and only translate the returned events to
their transport format.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator, Optional

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import SessionLocal
from app.crud.agent import agent_message_crud, agent_session_crud
from app.models.agent import AgentMessageRole
from app.schemas.agent import AgentMessageCreate, AgentSessionCreate
from app.services.agent import (
    agent_copy,
    interactions,
    session_projection,
    session_state,
)
from app.services.agent.checkpoint_fallback_runtime import agent_checkpoint_fallback_runtime
from app.services.agent.checkpointer import is_checkpoint_storage_error
from app.services.agent.input import AgentTurnInput
from app.services.agent.root_runtime import agent_root_runtime, project_turn_output
from app.services.agent.state import (
    AgentApplicationRuntimeResult,
    AgentRootRuntimeSideEffects,
    AgentRuntimeContext,
)
from app.services.agent.types import JSONDict, coerce_json_dict

logger = logging.getLogger(__name__)


class AgentApplicationService:
    """Channel-independent Agent turn runner."""

    async def stream_chat_events(
        self,
        *,
        content: str,
        team_id: int,
        user_id: int,
        authorization: str,
        session_id: Optional[int] = None,
        session_key: Optional[str] = None,
        turn_input: Optional[AgentTurnInput] = None,
    ) -> AsyncGenerator[JSONDict, None]:
        db = SessionLocal()
        try:
            agent_turn_input = turn_input or AgentTurnInput.text(content)
            content = agent_turn_input.content
            if session_id or session_key:
                session = session_state._get_owned_session(
                    db,
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session_id,
                    session_key=session_key,
                )
            else:
                session = agent_session_crud.create(
                    db,
                    AgentSessionCreate(
                        session_key=session_state._new_session_key(),
                        team_id=team_id,
                        user_id=user_id,
                        title=content[:50],
                    ),
                )

            yield {
                "event": "session",
                "session_id": session.id,
                "session_key": session.session_key,
            }

            user_message = agent_message_crud.create(
                db,
                AgentMessageCreate(
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session.id,
                    role=AgentMessageRole.USER,
                    event_type="user_message",
                    content=content,
                ),
            )
            yield {
                "event": "message",
                "role": AgentMessageRole.USER,
                "message_id": user_message.id,
                "content": user_message.content,
            }

            assistant_content = None
            trace_events: list[JSONDict] = []
            runtime_event_queue: asyncio.Queue[JSONDict] = asyncio.Queue()
            streamed_event_count = 0
            streamed_final_content: str | None = None
            streamed_final_content_format: str | None = None

            def emit(event: JSONDict) -> JSONDict:
                event = interactions._with_interaction(event, db=db, team_id=team_id)
                interactions._append_trace_event(trace_events, event)
                return coerce_json_dict(event)

            async def publish_runtime_event(event: JSONDict) -> None:
                nonlocal streamed_event_count, streamed_final_content, streamed_final_content_format
                if event.get("event") == "final":
                    content = event.get("content")
                    if isinstance(content, str) and content.strip():
                        streamed_final_content = content
                    streamed_final_content_format = _normalize_content_format(event.get("content_format"))
                streamed_event_count += 1
                await runtime_event_queue.put(coerce_json_dict(event))

            runtime_session_projection = session_projection.project_session_runtime(session)
            runtime_side_effects = AgentRootRuntimeSideEffects()
            runtime_context = AgentRuntimeContext(
                db=db,
                session=session,
                task=None,
                turn_input=agent_turn_input,
                content=content,
                team_id=team_id,
                user_id=user_id,
                session_id=session.id,
                user_message_id=user_message.id,
                authorization=authorization,
                switch_notice=None,
                side_effects=runtime_side_effects,
                event_sink=publish_runtime_event,
            )

            runtime_task = asyncio.create_task(
                self._run_root_runtime_for_turn(
                    agent_turn_input=agent_turn_input,
                    content=content,
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session.id,
                    session_key=session.session_key,
                    current_customer=runtime_session_projection.current_customer,
                    runtime_context=runtime_context,
                )
            )
            while not runtime_task.done():
                try:
                    runtime_event = await asyncio.wait_for(runtime_event_queue.get(), timeout=0.05)
                except asyncio.TimeoutError:
                    continue
                yield emit(runtime_event)
            runtime_result = await runtime_task
            while not runtime_event_queue.empty():
                yield emit(runtime_event_queue.get_nowait())
            runtime_state = runtime_result.state
            for runtime_event in runtime_state.get("events", []):
                interactions._append_trace_event(
                    trace_events,
                    interactions._with_interaction(runtime_event, db=db, team_id=team_id),
                )

            if runtime_result.checkpoint_unavailable:
                runtime_result = await agent_checkpoint_fallback_runtime.run(
                    db=db,
                    session=session,
                    task=None,
                    turn_input=agent_turn_input,
                    content=content,
                    team_id=team_id,
                    user_id=user_id,
                    authorization=authorization,
                )
                runtime_state = runtime_result.state

            if streamed_event_count == 0:
                for output_event in runtime_result.turn_output.events:
                    yield emit(output_event)

            assistant_value = (
                streamed_final_content
                or runtime_result.turn_output.assistant_content
                or runtime_state.get("assistant_content")
            )
            assistant_content = assistant_value if isinstance(assistant_value, str) else None
            assistant_content_format = (
                streamed_final_content_format
                or _content_format_from_events(runtime_result.turn_output.events)
                or _content_format_from_events(runtime_state.get("events", []))
                or "text"
            )

            if not assistant_content:
                assistant_content = agent_copy.generic_completed()
                assistant_content_format = "text"

            assistant_message = agent_message_crud.create(
                db,
                AgentMessageCreate(
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session.id,
                    role=AgentMessageRole.ASSISTANT,
                    event_type="assistant_message",
                    content=assistant_content,
                    payload_json={
                        "source": "langgraph",
                        "trace_events": trace_events,
                        "content_format": assistant_content_format,
                    },
                ),
            )
            yield {
                "event": "message",
                "role": AgentMessageRole.ASSISTANT,
                "message_id": assistant_message.id,
                "content": assistant_content,
                "content_format": assistant_content_format,
            }
            yield {"event": "done", "session_id": session.id}
        except HTTPException as exc:
            yield {"event": "error", "message": exc.detail, "status_code": exc.status_code}
        except Exception as exc:
            yield {"event": "error", "message": agent_copy.service_error(str(exc))}
        finally:
            db.close()

    async def _run_root_runtime_for_turn(
        self,
        *,
        agent_turn_input: AgentTurnInput,
        content: str,
        team_id: int,
        user_id: int,
        session_id: int,
        session_key: str,
        current_customer: JSONDict,
        runtime_context: AgentRuntimeContext,
    ) -> AgentApplicationRuntimeResult:
        try:
            runtime_state = await agent_root_runtime.run_turn(
                turn_input=agent_turn_input,
                content=content,
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                session_key=session_key,
                current_customer=current_customer,
                context=runtime_context,
            )
            return AgentApplicationRuntimeResult(
                state=runtime_state,
                turn_output=project_turn_output(runtime_state, runtime_context.side_effects),
                pending_task_result=runtime_context.side_effects.pending_task_result or {},
            )
        except SQLAlchemyError as exc:
            if not is_checkpoint_storage_error(exc):
                raise
            logger.warning("Agent root graph checkpoint is unavailable", exc_info=True)
            return AgentApplicationRuntimeResult(checkpoint_unavailable=True)


agent_application_service = AgentApplicationService()


def _normalize_content_format(value: object) -> str | None:
    if value == "markdown":
        return "markdown"
    if value == "text":
        return "text"
    return None


def _content_format_from_events(events: object) -> str | None:
    if not isinstance(events, list):
        return None
    for event in reversed(events):
        if not isinstance(event, dict) or event.get("event") != "final":
            continue
        normalized = _normalize_content_format(event.get("content_format"))
        if normalized:
            return normalized
    return None
