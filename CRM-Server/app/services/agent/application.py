"""Application service for CRM AI Agent turns.

This module owns channel-independent Agent turn orchestration. HTTP and IM
adapters should call this service and only translate the returned events to
their transport format.
"""
from __future__ import annotations

from typing import Any, AsyncGenerator, Optional

from fastapi import HTTPException

from app.core.database import SessionLocal
from app.crud.agent import agent_message_crud, agent_session_crud
from app.models.agent import AgentMessageRole
from app.schemas.agent import AgentMessageCreate, AgentSessionCreate
from app.services.agent import (
    agent_copy,
    crm_agent_graph_service,
    interactions,
    session_state,
)
from app.services.agent.confirmed_task_runtime import agent_confirmed_task_runtime
from app.services.agent.input import AgentTurnInput
from app.services.agent.new_flow_runtime import agent_new_flow_runtime
from app.services.agent.pending_graph import pending_task_graph_service


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
    ) -> AsyncGenerator[dict[str, Any], None]:
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
            trace_events: list[dict] = []

            def emit(event: dict[str, Any]) -> dict[str, Any]:
                event = interactions._with_interaction(event, db=db, team_id=team_id)
                interactions._append_trace_event(trace_events, event)
                return event

            task = session_state._get_current_waiting_task(db, session, team_id, user_id)
            switch_notice = None
            pending_interruption_handled = False
            confirmation_decision = None

            suspended_pending_tasks = (session.context_json or {}).get("suspended_pending_tasks")
            should_run_pending_graph = bool(task) or bool(suspended_pending_tasks)
            pending_graph_state = {}
            if should_run_pending_graph:
                pending_graph_state = await pending_task_graph_service.run({
                    "db": db,
                    "session": session,
                    "task": task,
                    "turn_input": agent_turn_input,
                    "content": content,
                    "team_id": team_id,
                    "user_id": user_id,
                    "session_id": session.id,
                    "authorization": authorization,
                    "events": [],
                })
            if pending_graph_state.get("task") or pending_graph_state.get("handled") or pending_graph_state.get("events"):
                if pending_graph_state.get("suspended_task"):
                    session_state._suspend_pending_task(
                        db,
                        session,
                        pending_graph_state["suspended_task"],
                        pending_graph_state.get("suspend_reason") or "用户开启了新的业务流程",
                    )
                task = pending_graph_state.get("task")
                if pending_graph_state.get("selected_customer"):
                    session_state._remember_current_customer(db, session, pending_graph_state["selected_customer"])
                if pending_graph_state.get("remember_pending_task"):
                    session_state._remember_pending_task(db, session, task)
                if pending_graph_state.get("clear_pending_task_id"):
                    session_state._clear_pending_task(db, session, pending_graph_state["clear_pending_task_id"])
                switch_notice = pending_graph_state.get("switch_notice")
                confirmation_decision = pending_graph_state.get("confirmation_decision")
                assistant_content = pending_graph_state.get("assistant_content")
                pending_interruption_handled = bool(pending_graph_state.get("handled"))
                for pending_event in pending_graph_state.get("events", []):
                    yield emit(pending_event)

            if pending_interruption_handled:
                pass
            elif task:
                if confirmation_decision and confirmation_decision.intent == "confirm":
                    execution = await agent_confirmed_task_runtime.execute(
                        db,
                        task,
                        session=session,
                        team_id=team_id,
                        user_id=user_id,
                        authorization=authorization,
                    )
                    assistant_content = execution.assistant_content
                    if execution.tool_event:
                        yield emit(execution.tool_event)
                    yield emit(execution.task_event)
                    yield emit({"event": "final", "content": assistant_content})
                elif session_state._is_confirmation(content):
                    assistant_content = agent_copy.no_pending_confirmation()
                    yield emit({"event": "final", "content": assistant_content})
                else:
                    assistant_ref = {"content": assistant_content}
                    async for event in agent_new_flow_runtime.stream_events(
                        db,
                        session=session,
                        team_id=team_id,
                        user_id=user_id,
                        content=content,
                        authorization=authorization,
                        switch_notice=switch_notice,
                        assistant_ref=assistant_ref,
                        graph_service=crm_agent_graph_service,
                    ):
                        yield emit(event)
                    assistant_content = assistant_ref["content"]
            elif session_state._is_confirmation(content):
                assistant_content = agent_copy.no_pending_confirmation()
                yield emit({"event": "final", "content": assistant_content})
            else:
                assistant_ref = {"content": assistant_content}
                async for event in agent_new_flow_runtime.stream_events(
                    db,
                    session=session,
                    team_id=team_id,
                    user_id=user_id,
                    content=content,
                    authorization=authorization,
                    switch_notice=switch_notice,
                    assistant_ref=assistant_ref,
                    graph_service=crm_agent_graph_service,
                ):
                    yield emit(event)
                assistant_content = assistant_ref["content"]

            if not assistant_content:
                assistant_content = agent_copy.generic_completed()

            assistant_message = agent_message_crud.create(
                db,
                AgentMessageCreate(
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session.id,
                    role=AgentMessageRole.ASSISTANT,
                    event_type="assistant_message",
                    content=assistant_content,
                    payload_json={"source": "langgraph", "trace_events": trace_events},
                ),
            )
            yield {
                "event": "message",
                "role": AgentMessageRole.ASSISTANT,
                "message_id": assistant_message.id,
                "content": assistant_content,
            }
            yield {"event": "done", "session_id": session.id}
        except HTTPException as exc:
            yield {"event": "error", "message": exc.detail, "status_code": exc.status_code}
        except Exception as exc:
            yield {"event": "error", "message": agent_copy.service_error(str(exc))}
        finally:
            db.close()


agent_application_service = AgentApplicationService()
