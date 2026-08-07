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
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.crud.agent import agent_message_crud, agent_session_crud
from app.models.agent import AgentMessage, AgentMessageRole
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
from app.services.follow_up_task_confirmation_channel_service import (
    FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION,
    FOLLOW_UP_CONFIRMATION_PROMPT_EVENT,
    follow_up_task_confirmation_channel_service,
)

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
        session = None
        user_message = None
        trace_events: list[JSONDict] = []
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

            bound_confirmation_event = self._resolve_bound_follow_up_confirmation_reply(
                db,
                team_id=team_id,
                user_id=user_id,
                session_id=session.id,
                content=content,
                turn_input=agent_turn_input,
            )
            if bound_confirmation_event is not None:
                emitted_event = coerce_json_dict(bound_confirmation_event)
                interactions._append_trace_event(trace_events, emitted_event)
                yield emitted_event
                assistant_message = agent_message_crud.create(
                    db,
                    AgentMessageCreate(
                        team_id=team_id,
                        user_id=user_id,
                        session_id=session.id,
                        role=AgentMessageRole.ASSISTANT,
                        event_type="assistant_message",
                        content=str(emitted_event.get("content") or agent_copy.generic_completed()),
                        payload_json={
                            "source": "follow_up_task_confirmation_reply",
                            "trace_events": trace_events,
                            "content_format": emitted_event.get("content_format") or "text",
                        },
                    ),
                )
                yield {
                    "event": "message",
                    "role": AgentMessageRole.ASSISTANT,
                    "message_id": assistant_message.id,
                    "content": assistant_message.content,
                    "content_format": emitted_event.get("content_format") or "text",
                }
                yield {"event": "done", "session_id": session.id}
                return

            assistant_content = None
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
            error_content = agent_copy.service_error(str(exc))
            assistant_message = self._persist_runtime_error_message(
                db,
                team_id=team_id,
                user_id=user_id,
                session_id=getattr(session, "id", None),
                user_message_id=getattr(user_message, "id", None),
                content=error_content,
                trace_events=trace_events,
            )
            if assistant_message is not None:
                yield {
                    "event": "message",
                    "role": AgentMessageRole.ASSISTANT,
                    "message_id": assistant_message.id,
                    "content": assistant_message.content,
                    "content_format": "text",
                }
            yield {"event": "error", "message": error_content}
        finally:
            db.close()

    def _persist_runtime_error_message(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int | None,
        user_message_id: int | None,
        content: str,
        trace_events: list[JSONDict],
    ) -> AgentMessage | None:
        if not isinstance(session_id, int) or not isinstance(user_message_id, int):
            return None
        try:
            db.rollback()
            return agent_message_crud.create(
                db,
                AgentMessageCreate(
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session_id,
                    role=AgentMessageRole.ASSISTANT,
                    event_type="assistant_message",
                    content=content,
                    payload_json={
                        "source": "runtime_error_fallback",
                        "recovered_for_user_message_id": user_message_id,
                        "trace_events": trace_events,
                        "content_format": "text",
                    },
                ),
            )
        except Exception:
            logger.exception(
                "Agent runtime error fallback message persistence failed: team_id=%s session_id=%s",
                team_id,
                session_id,
            )
            return None

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

    def _resolve_bound_follow_up_confirmation_reply(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        content: str,
        turn_input: AgentTurnInput,
    ) -> JSONDict | None:
        case_public_id = _case_public_id_from_turn_metadata(turn_input.metadata)
        explicit_binding = case_public_id is not None
        if case_public_id is None:
            latest_interaction = _latest_follow_up_confirmation_interaction(
                db,
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
            )
            case_public_id = _case_public_id_from_interaction(latest_interaction)
            if case_public_id is None:
                return None
            decision = follow_up_task_confirmation_channel_service.preview_reply_decision(content)
            if not decision.resolved:
                return None

        try:
            return coerce_json_dict(
                follow_up_task_confirmation_channel_service.resolve_bound_reply(
                    db,
                    team_id=team_id,
                    user_id=user_id,
                    case_public_id=case_public_id,
                    reply_text=content,
                )
            )
        except SQLAlchemyError:
            db.rollback()
            logger.exception(
                "Follow-up confirmation reply binding failed: team_id=%s user_id=%s case_public_id=%s explicit=%s",
                team_id,
                user_id,
                case_public_id,
                explicit_binding,
            )
            return None

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


def _case_public_id_from_turn_metadata(metadata: object) -> str | None:
    if not isinstance(metadata, dict):
        return None
    for key in ("case_public_id", "follow_up_confirmation_case_public_id"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _latest_follow_up_confirmation_interaction(
    db: Session,
    *,
    team_id: int,
    user_id: int,
    session_id: int,
) -> dict[str, object] | None:
    messages = (
        db.query(AgentMessage)
        .filter(
            AgentMessage.session_id == session_id,
            AgentMessage.team_id == team_id,
            AgentMessage.user_id == user_id,
            AgentMessage.role == AgentMessageRole.ASSISTANT,
        )
        .order_by(AgentMessage.created_time.desc(), AgentMessage.id.desc())
        .limit(5)
        .all()
    )
    for message in messages:
        payload = message.payload_json if isinstance(message.payload_json, dict) else {}
        trace_events = payload.get("trace_events") if isinstance(payload.get("trace_events"), list) else []
        for event in reversed(trace_events):
            if not isinstance(event, dict):
                continue
            if event.get("event") != FOLLOW_UP_CONFIRMATION_PROMPT_EVENT:
                continue
            interaction = event.get("interaction")
            if _is_waiting_follow_up_confirmation_interaction(interaction):
                return interaction
    return None


def _is_waiting_follow_up_confirmation_interaction(interaction: object) -> bool:
    if not isinstance(interaction, dict):
        return False
    return (
        interaction.get("business_action") == FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION
        and interaction.get("status") in {None, "waiting_user_input", "waiting_confirmation"}
        and _case_public_id_from_interaction(interaction) is not None
    )


def _case_public_id_from_interaction(interaction: object) -> str | None:
    if not isinstance(interaction, dict):
        return None
    payload = interaction.get("payload")
    if not isinstance(payload, dict):
        return None
    value = payload.get("case_public_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    case = payload.get("case")
    if isinstance(case, dict):
        case_public_id = case.get("public_id") or case.get("id")
        if isinstance(case_public_id, str) and case_public_id.strip():
            return case_public_id.strip()
    return None
