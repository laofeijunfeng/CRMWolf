"""Application service for CRM AI Agent turns.

This module owns channel-independent Agent turn orchestration. HTTP and IM
adapters should call this service and only translate the returned events to
their transport format.
"""
from __future__ import annotations

import asyncio
import logging
from collections import Counter
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
from app.services.agent.async_operation_service import agent_async_operation_service
from app.services.agent.state import (
    AgentApplicationRuntimeResult,
    AgentRootRuntimeSideEffects,
    AgentRuntimeContext,
)
from app.services.agent.types import JSONDict, coerce_json_dict
from app.services.customer_intelligence_refresh_service import (
    AgentAsyncOperationBinding,
    CustomerIntelligenceCommittedEventRequest,
    CustomerIntelligenceRefreshService,
    customer_intelligence_refresh_service,
)
from app.services.follow_up_task_confirmation_channel_service import (
    FollowUpTaskConfirmationChannelService,
    follow_up_task_confirmation_channel_service,
)

logger = logging.getLogger(__name__)


class AgentApplicationService:
    """Channel-independent Agent turn runner and visibility transaction boundary."""

    def __init__(
        self,
        *,
        customer_intelligence_service: CustomerIntelligenceRefreshService | None = None,
        confirmation_channel_service: FollowUpTaskConfirmationChannelService | None = None,
    ) -> None:
        self.customer_intelligence_service = (
            customer_intelligence_service or customer_intelligence_refresh_service
        )
        self.confirmation_channel_service = (
            confirmation_channel_service or follow_up_task_confirmation_channel_service
        )

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
        close_db_in_finally = True
        session = None
        user_message = None
        runtime_task: asyncio.Task[AgentApplicationRuntimeResult] | None = None
        runtime_event_queue: asyncio.Queue[JSONDict] | None = None
        streamed_event_count = 0
        streamed_final_content: str | None = None
        streamed_final_content_format: str | None = None
        assistant_message_persisted = False
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

            assistant_content = None
            runtime_event_queue = asyncio.Queue()

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
            runtime_result = await self._runtime_result_or_checkpoint_fallback(
                db=db,
                session=session,
                runtime_task=runtime_task,
                turn_input=agent_turn_input,
                content=content,
                team_id=team_id,
                user_id=user_id,
                authorization=authorization,
            )
            while not runtime_event_queue.empty():
                yield emit(runtime_event_queue.get_nowait())
            runtime_state = self._collect_runtime_trace_events(
                db=db,
                team_id=team_id,
                runtime_result=runtime_result,
                runtime_event_queue=runtime_event_queue,
                trace_events=trace_events,
            )

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

            observability_event = self._build_turn_observability_event(
                trace_events=trace_events,
                assistant_content=assistant_content,
                assistant_content_format=assistant_content_format,
            )
            interactions._append_trace_event(
                trace_events,
                interactions._with_interaction(observability_event, db=db, team_id=team_id),
            )

            assistant_message = self._persist_runtime_success_message(
                db,
                team_id=team_id,
                user_id=user_id,
                session_id=session.id,
                user_message_id=user_message.id,
                content=assistant_content,
                content_format=assistant_content_format,
                trace_events=trace_events,
                source="langgraph",
                visibility_channel=agent_turn_input.source,
                runtime_state=runtime_state,
                turn_observability=coerce_json_dict(observability_event.get("summary")),
            )
            assistant_message_persisted = True
            yield observability_event
            yield {
                "event": "message",
                "role": AgentMessageRole.ASSISTANT,
                "message_id": assistant_message.id,
                "content": assistant_content,
                "content_format": assistant_content_format,
            }
            yield {"event": "done", "session_id": session.id}
        except (asyncio.CancelledError, GeneratorExit):
            if (
                runtime_task is not None
                and runtime_event_queue is not None
                and session is not None
                and user_message is not None
                and not assistant_message_persisted
            ):
                close_db_in_finally = False
                asyncio.create_task(
                    self._finalize_cancelled_stream_turn(
                        db=db,
                        runtime_task=runtime_task,
                        runtime_event_queue=runtime_event_queue,
                        session=session,
                        turn_input=agent_turn_input,
                        content=content,
                        team_id=team_id,
                        user_id=user_id,
                        user_message_id=user_message.id,
                        authorization=authorization,
                        trace_events=trace_events,
                        streamed_event_count=streamed_event_count,
                        streamed_final_content=streamed_final_content,
                        streamed_final_content_format=streamed_final_content_format,
                    )
                )
            raise
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
            if close_db_in_finally:
                db.close()

    async def _runtime_result_or_checkpoint_fallback(
        self,
        *,
        db: Session,
        session: object,
        runtime_task: asyncio.Task[AgentApplicationRuntimeResult],
        turn_input: AgentTurnInput,
        content: str,
        team_id: int,
        user_id: int,
        authorization: str,
    ) -> AgentApplicationRuntimeResult:
        runtime_result = await runtime_task
        if not runtime_result.checkpoint_unavailable:
            return runtime_result
        return await agent_checkpoint_fallback_runtime.run(
            db=db,
            session=session,
            task=None,
            turn_input=turn_input,
            content=content,
            team_id=team_id,
            user_id=user_id,
            authorization=authorization,
        )

    def _collect_runtime_trace_events(
        self,
        *,
        db: Session,
        team_id: int,
        runtime_result: AgentApplicationRuntimeResult,
        runtime_event_queue: asyncio.Queue[JSONDict],
        trace_events: list[JSONDict],
    ) -> JSONDict:
        while not runtime_event_queue.empty():
            runtime_event = runtime_event_queue.get_nowait()
            interactions._append_trace_event(
                trace_events,
                interactions._with_interaction(runtime_event, db=db, team_id=team_id),
            )
        runtime_state = runtime_result.state
        for runtime_event in runtime_state.get("events", []):
            interactions._append_trace_event(
                trace_events,
                interactions._with_interaction(runtime_event, db=db, team_id=team_id),
            )
        return runtime_state

    def _persist_runtime_success_message(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        user_message_id: int,
        content: str,
        content_format: str,
        trace_events: list[JSONDict],
        source: str,
        visibility_channel: str,
        runtime_state: JSONDict,
        turn_observability: JSONDict | None = None,
    ) -> AgentMessage:
        existing = self._find_persisted_assistant_for_user_message(
            db,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            user_message_id=user_message_id,
        )
        message = existing
        if message is None:
            message = agent_message_crud.create(
                db,
                AgentMessageCreate(
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session_id,
                    role=AgentMessageRole.ASSISTANT,
                    event_type="assistant_message",
                    content=content,
                    payload_json={
                        "source": source,
                        "for_user_message_id": user_message_id,
                        "trace_events": trace_events,
                        "content_format": content_format,
                        "turn_observability": turn_observability or {},
                    },
                ),
                commit=False,
            )
        self._acknowledge_visible_confirmation_deliveries(
            db,
            team_id=team_id,
            assistant_message=message,
            trace_events=trace_events,
            visibility_channel=visibility_channel,
            commit=False,
        )
        kick_requests: tuple[CustomerIntelligenceCommittedEventRequest, ...] = ()
        try:
            with db.begin_nested():
                kick_requests = self._project_customer_intelligence_operations_to_assistant_message(
                    db,
                    runtime_state=runtime_state,
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session_id,
                    user_message_id=user_message_id,
                    assistant_message_id=int(message.id),
                )
        except Exception as exc:
            logger.exception(
                "Agent 客户智能异步操作投影失败: team_id=%s, session_id=%s, user_message_id=%s",
                team_id,
                session_id,
                user_message_id,
            )
            trace_events.append(
                {
                    "event": "agent_customer_intelligence_projection_failed",
                    "reason": str(exc),
                }
            )
            payload = message.payload_json if isinstance(message.payload_json, dict) else {}
            message.payload_json = {**payload, "trace_events": trace_events}
            db.add(message)
        try:
            agent_async_operation_service.bind_customer_activity_post_commit_assistant_message(
                db,
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                source_user_message_id=user_message_id,
                source_assistant_message_id=int(message.id),
            )
        except Exception:
            logger.exception(
                "绑定跟进任务对账到助手消息失败: team_id=%s, session_id=%s, user_message_id=%s",
                team_id,
                session_id,
                user_message_id,
            )
        db.commit()
        db.refresh(message)
        for request in kick_requests:
            if not request.kick_required:
                continue
            try:
                self.customer_intelligence_service.kick_committed_event_refresh(request)
            except Exception:
                logger.exception(
                    "Agent 客户智能异步操作 kick 失败，等待 durable recovery: request_id=%s",
                    request.request_id,
                )
        return message

    def _acknowledge_visible_confirmation_deliveries(
        self,
        db: Session,
        *,
        team_id: int,
        assistant_message: AgentMessage,
        trace_events: list[JSONDict],
        visibility_channel: str,
        commit: bool = True,
    ) -> None:
        # CRM message persistence is a user-visibility acknowledgement only for the Web channel.
        # IM adapters must acknowledge after their provider returns the actual response message ID.
        if visibility_channel != "web":
            return
        prompt_keys: set[str] = set()
        for event in trace_events:
            interaction = event.get("interaction")
            if not isinstance(interaction, dict):
                continue
            payload = interaction.get("payload")
            if not isinstance(payload, dict):
                continue
            prompt_key = payload.get("prompt_delivery_key")
            if isinstance(prompt_key, str) and prompt_key:
                prompt_keys.add(prompt_key)
        for prompt_key in prompt_keys:
            self.confirmation_channel_service.acknowledge_web_message_visible(
                db,
                team_id=team_id,
                prompt_key=prompt_key,
                provider_message_id=f"agent_message:{assistant_message.id}",
                commit=commit,
            )

    def _project_customer_intelligence_operations_to_assistant_message(
        self,
        db: Session,
        *,
        runtime_state: JSONDict,
        team_id: int,
        user_id: int,
        session_id: int,
        user_message_id: int,
        assistant_message_id: int,
    ) -> tuple[CustomerIntelligenceCommittedEventRequest, ...]:
        """Project exact durable work in the assistant-message transaction.

        The returned requests may be kicked only after the caller commits.
        Replays bind the same operation and terminal or leased runs naturally
        return ``kick_required=False``.
        """

        request_ids = list(_customer_intelligence_request_ids(runtime_state))
        if not request_ids:
            intent = coerce_json_dict(runtime_state.get("customer_intelligence_schedule_intent"))
            event_payload = coerce_json_dict(intent.get("event"))
            event = self.customer_intelligence_service.event_service.from_dict(event_payload)
            if event is None:
                if intent:
                    raise ValueError("客户智能调度 intent 事件快照无效")
                return ()
            if int(event.team_id) != int(team_id) or int(event.tenant_id) != int(team_id):
                raise ValueError("客户智能调度 intent 团队不匹配")
            scope = str(intent.get("scope") or "brief")
            if scope not in {"full", "brief"}:
                raise ValueError("客户智能调度 intent scope 无效")
            queued = self.customer_intelligence_service.enqueue_committed_event_refresh(
                db,
                event=event,
                scope=scope,
            )
            request_ids.append(queued.request_id)

        return self.customer_intelligence_service.bind_committed_events_to_agent(
            db,
            team_id=team_id,
            request_ids=request_ids,
            binding=AgentAsyncOperationBinding(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                source_user_message_id=user_message_id,
                source_assistant_message_id=assistant_message_id,
            ),
        )

    def _build_turn_observability_event(
        self,
        *,
        trace_events: list[JSONDict],
        assistant_content: str,
        assistant_content_format: str,
    ) -> JSONDict:
        return {
            "event": "agent_turn_observability",
            "summary": _build_turn_observability_summary(
                trace_events=trace_events,
                assistant_content=assistant_content,
                assistant_content_format=assistant_content_format,
            ),
        }

    def _find_persisted_assistant_for_user_message(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        user_message_id: int,
    ) -> AgentMessage | None:
        messages, _ = agent_message_crud.list_by_session(
            db,
            session_id=session_id,
            team_id=team_id,
            user_id=user_id,
            limit=20,
        )
        for message in reversed(messages):
            if message.role != AgentMessageRole.ASSISTANT:
                continue
            payload = message.payload_json if isinstance(message.payload_json, dict) else {}
            if payload.get("for_user_message_id") == user_message_id:
                return message
        return None

    async def _finalize_cancelled_stream_turn(
        self,
        *,
        db: Session,
        runtime_task: asyncio.Task[AgentApplicationRuntimeResult],
        runtime_event_queue: asyncio.Queue[JSONDict],
        session: object,
        turn_input: AgentTurnInput,
        content: str,
        team_id: int,
        user_id: int,
        user_message_id: int,
        authorization: str,
        trace_events: list[JSONDict],
        streamed_event_count: int,
        streamed_final_content: str | None,
        streamed_final_content_format: str | None,
    ) -> None:
        try:
            runtime_result = await self._runtime_result_or_checkpoint_fallback(
                db=db,
                session=session,
                runtime_task=runtime_task,
                turn_input=turn_input,
                content=content,
                team_id=team_id,
                user_id=user_id,
                authorization=authorization,
            )
            runtime_state = self._collect_runtime_trace_events(
                db=db,
                team_id=team_id,
                runtime_result=runtime_result,
                runtime_event_queue=runtime_event_queue,
                trace_events=trace_events,
            )
            if streamed_event_count == 0:
                for output_event in runtime_result.turn_output.events:
                    interactions._append_trace_event(
                        trace_events,
                        interactions._with_interaction(output_event, db=db, team_id=team_id),
                    )

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

            observability_event = self._build_turn_observability_event(
                trace_events=trace_events,
                assistant_content=assistant_content,
                assistant_content_format=assistant_content_format,
            )
            interactions._append_trace_event(
                trace_events,
                interactions._with_interaction(observability_event, db=db, team_id=team_id),
            )

            self._persist_runtime_success_message(
                db,
                team_id=team_id,
                user_id=user_id,
                session_id=session.id,
                user_message_id=user_message_id,
                content=assistant_content,
                content_format=assistant_content_format,
                trace_events=trace_events,
                source="langgraph_stream_cancelled_finalizer",
                visibility_channel=turn_input.source,
                runtime_state=runtime_state,
                turn_observability=coerce_json_dict(observability_event.get("summary")),
            )
        except Exception:
            logger.exception(
                "Agent stream cancellation finalizer failed: team_id=%s session_id=%s user_message_id=%s",
                team_id,
                getattr(session, "id", None),
                user_message_id,
            )
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

agent_application_service = AgentApplicationService()


def _customer_intelligence_request_ids(runtime_state: JSONDict) -> tuple[str, ...]:
    requests = runtime_state.get("customer_intelligence_requests")
    if not isinstance(requests, list):
        return ()
    request_ids: list[str] = []
    seen: set[str] = set()
    for item in requests:
        if not isinstance(item, dict):
            continue
        request_id = item.get("request_id")
        if not isinstance(request_id, str):
            continue
        request_id = request_id.strip()
        if not request_id or request_id in seen:
            continue
        seen.add(request_id)
        request_ids.append(request_id)
    return tuple(request_ids)


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


def _build_turn_observability_summary(
    *,
    trace_events: list[JSONDict],
    assistant_content: str,
    assistant_content_format: str,
) -> JSONDict:
    event_names = [str(event.get("event")) for event in trace_events if event.get("event")]
    tool_events = [event for event in trace_events if event.get("event") == "tool_result"]
    read_tool_events = [event for event in trace_events if event.get("event") == "agent_read_tool_executed"]
    semantic_event = _last_event(trace_events, "semantic_parsed")
    final_event = _last_event(trace_events, "final")
    customer_candidates_event = _last_event(trace_events, "customer_candidates")
    search_event = _last_tool_event(tool_events, "search_customers")
    context_event = _last_tool_event(tool_events, "get_customer_context")

    tool_names = [str(event.get("tool_name")) for event in tool_events if event.get("tool_name")]
    successful_tools = [
        str(event.get("tool_name"))
        for event in tool_events
        if event.get("tool_name") and event.get("success") is True
    ]
    failed_tools = [
        str(event.get("tool_name"))
        for event in tool_events
        if event.get("tool_name") and event.get("success") is False
    ]
    read_tool_names = [str(event.get("tool_name")) for event in read_tool_events if event.get("tool_name")]
    workflow_events = [
        event
        for event in trace_events
        if isinstance(event.get("workflow_id"), str) or isinstance(event.get("action_id"), str)
    ]

    summary: JSONDict = {
        "schema_version": "agent.turn_observability.v1",
        "event_count": len(trace_events),
        "event_counts": dict(Counter(event_names)),
        "assistant": {
            "content_format": assistant_content_format,
            "content_length": len(assistant_content),
            "empty": not bool(assistant_content.strip()),
        },
        "semantic": _semantic_summary(semantic_event),
        "customer_resolution": _customer_resolution_summary(
            customer_candidates_event=customer_candidates_event,
            search_event=search_event,
        ),
        "retrieval": _retrieval_summary(search_event=search_event, context_event=context_event),
        "tools": {
            "called": tool_names,
            "successful": successful_tools,
            "failed": failed_tools,
            "idempotent_replay_count": sum(1 for event in tool_events if event.get("idempotent_replay") is True),
        },
        "read_tools": {
            "called": read_tool_names,
            "query_types": [
                str(event.get("query_type"))
                for event in read_tool_events
                if event.get("query_type")
            ],
            "successful": [
                str(event.get("tool_name"))
                for event in read_tool_events
                if event.get("tool_name") and event.get("success") is True
            ],
            "failed": [
                str(event.get("tool_name"))
                for event in read_tool_events
                if event.get("tool_name") and event.get("success") is False
            ],
        },
        "workflow": _workflow_summary(workflow_events),
        "quality_flags": [],
        "final": {
            "intent": final_event.get("intent") if final_event else None,
            "tool_execution_enabled": final_event.get("tool_execution_enabled") if final_event else None,
        },
    }
    summary["quality_flags"] = _turn_quality_flags(summary)
    return summary


def _last_event(events: list[JSONDict], event_name: str) -> JSONDict | None:
    for event in reversed(events):
        if event.get("event") == event_name:
            return event
    return None


def _last_tool_event(events: list[JSONDict], tool_name: str) -> JSONDict | None:
    for event in reversed(events):
        if event.get("tool_name") == tool_name:
            return event
    return None


def _semantic_summary(event: JSONDict | None) -> JSONDict:
    if not event:
        return {
            "intent": None,
            "technical_intent": None,
            "confidence": None,
            "parse_source": None,
            "need_clarification": None,
        }
    return {
        "intent": event.get("intent"),
        "technical_intent": event.get("technical_intent"),
        "intent_label": event.get("intent_label"),
        "confidence": event.get("confidence"),
        "parse_source": event.get("parse_source"),
        "model": event.get("model"),
        "need_clarification": event.get("need_clarification"),
        "fallback_reason": event.get("fallback_reason"),
        "fallback_error": event.get("fallback_error"),
    }


def _customer_resolution_summary(
    *,
    customer_candidates_event: JSONDict | None,
    search_event: JSONDict | None,
) -> JSONDict:
    candidates = customer_candidates_event.get("customers") if customer_candidates_event else None
    if not isinstance(candidates, list):
        candidates = []
    search_data = coerce_json_dict(search_event.get("data")) if search_event else {}
    retrieval = coerce_json_dict(search_data.get("retrieval"))
    return {
        "candidate_count": len(candidates),
        "selected_customer_id": _first_candidate_value(candidates, "id"),
        "selected_customer_name": _first_candidate_value(candidates, "account_name"),
        "identity_status": retrieval.get("identity_status"),
        "identity_strategy": retrieval.get("identity_strategy"),
        "identity_decision": retrieval.get("identity_decision"),
        "identity_candidate_count": retrieval.get("identity_candidate_count"),
        "identity_related_count": retrieval.get("identity_related_count"),
        "semantic_related_customer_count": retrieval.get("semantic_related_customer_count"),
    }


def _retrieval_summary(*, search_event: JSONDict | None, context_event: JSONDict | None) -> JSONDict:
    search_data = coerce_json_dict(search_event.get("data")) if search_event else {}
    search_retrieval = coerce_json_dict(search_data.get("retrieval"))
    context_data = coerce_json_dict(context_event.get("data")) if context_event else {}
    context_retrieval = coerce_json_dict(context_data.get("retrieval"))
    semantic_evidence = context_data.get("semantic_evidence")
    return {
        "customer_search": {
            "mode": search_retrieval.get("mode"),
            "lexical_status": search_retrieval.get("lexical_status"),
            "alias_status": search_retrieval.get("alias_status"),
            "semantic_status": search_retrieval.get("semantic_status"),
            "semantic_source": search_retrieval.get("semantic_source"),
            "semantic_candidate_count": search_retrieval.get("semantic_candidate_count"),
        },
        "customer_context": {
            "called": context_event is not None,
            "retrieval_status": context_retrieval.get("status") or context_retrieval.get("retrieval_status"),
            "semantic_evidence_count": len(semantic_evidence) if isinstance(semantic_evidence, list) else None,
            "top_score": context_retrieval.get("top_score"),
        },
    }


def _workflow_summary(events: list[JSONDict]) -> JSONDict:
    workflow_ids = sorted({str(event.get("workflow_id")) for event in events if event.get("workflow_id")})
    action_ids = sorted({str(event.get("action_id")) for event in events if event.get("action_id")})
    statuses = Counter(
        str(event.get("status"))
        for event in events
        if event.get("status") and (event.get("workflow_id") or event.get("action_id"))
    )
    return {
        "workflow_ids": workflow_ids,
        "action_ids": action_ids,
        "status_counts": dict(statuses),
    }


def _turn_quality_flags(summary: JSONDict) -> list[str]:
    flags: list[str] = []
    semantic = coerce_json_dict(summary.get("semantic"))
    customer_resolution = coerce_json_dict(summary.get("customer_resolution"))
    retrieval = coerce_json_dict(summary.get("retrieval"))
    tools = coerce_json_dict(summary.get("tools"))
    read_tools = coerce_json_dict(summary.get("read_tools"))
    assistant = coerce_json_dict(summary.get("assistant"))

    if assistant.get("empty") is True:
        flags.append("assistant_response_empty")
    if semantic.get("intent") == "CRM_READ_QUERY" and not tools.get("successful") and not read_tools.get("successful"):
        flags.append("read_query_without_successful_business_tool")
    if (
        semantic.get("intent") == "CRM_READ_QUERY"
        and customer_resolution.get("candidate_count") == 1
        and not read_tools.get("successful")
        and not coerce_json_dict(retrieval.get("customer_context")).get("called")
    ):
        flags.append("resolved_customer_read_without_context_or_read_tool")
    if _as_int(customer_resolution.get("candidate_count")) and _as_int(customer_resolution.get("candidate_count")) > 1:
        flags.append("multiple_customer_candidates")
    if _as_int(customer_resolution.get("identity_related_count")) and _as_int(customer_resolution.get("identity_related_count")) > 5:
        flags.append("semantic_related_customer_noise_high")
    if tools.get("failed") or read_tools.get("failed"):
        flags.append("tool_failure_seen")
    if semantic.get("fallback_error"):
        flags.append("semantic_parse_fallback_error")
    return flags


def _first_candidate_value(candidates: list[object], key: str) -> object:
    if not candidates:
        return None
    first = candidates[0]
    if not isinstance(first, dict):
        return None
    return first.get(key)


def _as_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None
