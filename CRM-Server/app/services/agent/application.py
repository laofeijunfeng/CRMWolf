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
from app.models.agent import AgentMessageRole, AgentTaskStatus
from app.schemas.agent import AgentMessageCreate, AgentSessionCreate
from app.services.agent import (
    crm_agent_graph_service,
    customer_fields,
    customer_related_fields,
    follow_up_fields,
    interactions,
    lead_fields,
    opportunity_fields,
    payment_fields,
    selection,
    session_state,
    task_execution,
    task_factory,
)
from app.services.agent.confirmation_intent import agent_confirmation_intent_service
from app.services.agent.input import AgentTurnInput


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
            if task and not agent_confirmation_intent_service.is_executable_confirmation_task(task) and session_state._is_rejection(content):
                session_state._suspend_pending_task(db, session, task, "用户选择先不处理。")
                session_state._clear_pending_task(db, session, task.id)
                assistant_content = "好的，这一步先放着。"
                pending_interruption_handled = True
                yield emit({
                    "event": "task_cancelled",
                    "task_id": task.id,
                    "content": assistant_content,
                })
                yield emit({"event": "final", "content": assistant_content})
            elif task and agent_confirmation_intent_service.is_executable_confirmation_task(task):
                confirmation_decision = await agent_confirmation_intent_service.assess(
                    db,
                    team_id=team_id,
                    turn_input=agent_turn_input,
                    task=task,
                    memory=session_state._memory_snapshot_for_session(session, task),
                )
                yield emit({
                    "event": "confirmation_intent_assessed",
                    "task_id": task.id,
                    "intent": confirmation_decision.intent,
                    "confidence": confirmation_decision.confidence,
                    "reason": confirmation_decision.reason,
                })
                if confirmation_decision.intent == "reject":
                    session_state._suspend_pending_task(db, session, task, "用户选择先不处理。")
                    session_state._clear_pending_task(db, session, task.id)
                    assistant_content = "好的，这一步先放着。"
                    pending_interruption_handled = True
                    yield emit({
                        "event": "task_cancelled",
                        "task_id": task.id,
                        "content": assistant_content,
                    })
                    yield emit({"event": "final", "content": assistant_content})
                elif confirmation_decision.intent == "unknown":
                    interruption_decision = await session_state._assess_pending_interruption(
                        db,
                        team_id=team_id,
                        session=session,
                        task=task,
                        user_message=content,
                    )
                    yield emit({
                        "event": "pending_interruption_assessed",
                        "decision": interruption_decision.decision,
                        "confidence": interruption_decision.confidence,
                        "detected_customer_name": interruption_decision.detected_customer_name,
                        "detected_intent": interruption_decision.detected_intent,
                        "reason": interruption_decision.reason,
                    })
                    if session_state._is_high_confidence_new_flow(interruption_decision):
                        customer_name = interruption_decision.detected_customer_name or "新的客户"
                        switch_notice = f"这条看起来是在说「{customer_name}」，和刚才的待处理任务不是同一个流程。我先切过来处理。"
                        suspended_task_id = task.id
                        session_state._suspend_pending_task(
                            db,
                            session,
                            task,
                            interruption_decision.reason or "用户开启了新的业务流程",
                        )
                        task = None
                        yield emit({
                            "event": "pending_task_interrupted",
                            "content": switch_notice,
                            "suspended_task_id": suspended_task_id,
                        })
                    elif session_state._is_ambiguous_pending_interruption(interruption_decision):
                        assistant_content = interruption_decision.question or "这句像是新流程，也可能是在补刚才的任务。你要我切到新流程，还是继续刚才的任务？"
                        pending_interruption_handled = True
                        yield emit({
                            "event": "pending_interruption_confirmation_required",
                            "task_id": task.id,
                            "content": assistant_content,
                            "decision": interruption_decision.model_dump(),
                        })
                        yield emit({"event": "final", "content": assistant_content})
                    else:
                        assistant_content = "请明确回复「确认」或「取消」，也可以重新描述新的需求。"
                        pending_interruption_handled = True
                        yield emit({
                            "event": "confirmation_intent_unknown",
                            "task_id": task.id,
                            "content": assistant_content,
                        })
                        yield emit({"event": "final", "content": assistant_content})

            if pending_interruption_handled:
                pass
            elif task and follow_up_fields._is_follow_up_quality_fields_task(task):
                ready, assistant_content = await follow_up_fields._apply_follow_up_quality_fields(db, task, content)
                session_state._remember_pending_task(db, session, task)
                yield emit({
                    "event": "confirmation_required" if ready else "follow_up_quality_required",
                    "task_id": task.id,
                    "content": assistant_content,
                    "payload": task.input_json or {},
                })
                yield emit({"event": "final", "content": assistant_content})
            elif task and follow_up_fields._is_lead_follow_up_quality_fields_task(task):
                ready, assistant_content = await follow_up_fields._apply_lead_follow_up_quality_fields(db, task, content)
                session_state._remember_pending_task(db, session, task)
                yield emit({
                    "event": "confirmation_required" if ready else "follow_up_quality_required",
                    "task_id": task.id,
                    "content": assistant_content,
                    "payload": task.input_json or {},
                })
                yield emit({"event": "final", "content": assistant_content})
            elif task and customer_related_fields._is_contact_fields_task(task):
                ready, assistant_content = await customer_related_fields._apply_contact_fields(db, task, content)
                session_state._remember_pending_task(db, session, task)
                yield emit({
                    "event": "confirmation_required" if ready else "contact_fields_required",
                    "task_id": task.id,
                    "content": assistant_content,
                    "payload": task.input_json or {},
                })
                yield emit({"event": "final", "content": assistant_content})
            elif task and opportunity_fields._is_opportunity_fields_task(task):
                ready, assistant_content = await opportunity_fields._apply_opportunity_fields(db, task, content)
                session_state._remember_pending_task(db, session, task)
                yield emit({
                    "event": "confirmation_required" if ready else "opportunity_fields_required",
                    "task_id": task.id,
                    "content": assistant_content,
                    "payload": task.input_json or {},
                })
                yield emit({"event": "final", "content": assistant_content})
            elif task and customer_related_fields._is_invoice_title_fields_task(task):
                ready, assistant_content = await customer_related_fields._apply_invoice_title_fields(db, task, content)
                session_state._remember_pending_task(db, session, task)
                yield emit({
                    "event": "confirmation_required" if ready else "invoice_title_fields_required",
                    "task_id": task.id,
                    "content": assistant_content,
                    "payload": task.input_json or {},
                })
                yield emit({"event": "final", "content": assistant_content})
            elif task and customer_related_fields._is_deployment_info_fields_task(task):
                ready, assistant_content = await customer_related_fields._apply_deployment_info_fields(db, task, content)
                session_state._remember_pending_task(db, session, task)
                yield emit({
                    "event": "confirmation_required" if ready else "deployment_info_fields_required",
                    "task_id": task.id,
                    "content": assistant_content,
                    "payload": task.input_json or {},
                })
                yield emit({"event": "final", "content": assistant_content})
            elif task and customer_related_fields._is_customer_member_fields_task(task):
                ready, assistant_content = await customer_related_fields._apply_customer_member_fields(db, task, content)
                session_state._remember_pending_task(db, session, task)
                yield emit({
                    "event": "confirmation_required" if ready else "customer_member_fields_required",
                    "task_id": task.id,
                    "content": assistant_content,
                    "payload": task.input_json or {},
                })
                yield emit({"event": "final", "content": assistant_content})
            elif task and payment_fields._is_payment_fields_task(task):
                ready, assistant_content = await payment_fields._apply_payment_fields(db, task, content)
                session_state._remember_pending_task(db, session, task)
                yield emit({
                    "event": "confirmation_required" if ready else "payment_fields_required",
                    "task_id": task.id,
                    "content": assistant_content,
                    "payload": task.input_json or {},
                })
                yield emit({"event": "final", "content": assistant_content})
            elif task and lead_fields._is_lead_fields_task(task):
                ready, assistant_content = await lead_fields._apply_lead_fields(db, task, content)
                session_state._remember_pending_task(db, session, task)
                yield emit({
                    "event": "confirmation_required" if ready else "lead_fields_required",
                    "task_id": task.id,
                    "content": assistant_content,
                    "payload": task.input_json or {},
                })
                yield emit({"event": "final", "content": assistant_content})
            elif task and customer_fields._is_customer_fields_task(task):
                ready, assistant_content = await customer_fields._apply_customer_fields(db, task, content)
                session_state._remember_pending_task(db, session, task)
                yield emit({
                    "event": "confirmation_required" if ready else "customer_fields_required",
                    "task_id": task.id,
                    "content": assistant_content,
                    "payload": task.input_json or {},
                })
                yield emit({"event": "final", "content": assistant_content})
            elif task and selection._is_business_selection_task(task):
                selected, assistant_content = selection._apply_business_selection(db, task, content)
                session_state._remember_pending_task(db, session, task)
                yield emit({
                    "event": "business_selected" if selected else "business_selection_failed",
                    "task_id": task.id,
                    "content": assistant_content,
                    "selected": selected,
                })
                yield emit({"event": "final", "content": assistant_content})
            elif task and selection._is_customer_selection_task(task):
                customer, assistant_content = await selection._apply_customer_selection(
                    db,
                    task,
                    content,
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session.id,
                    authorization=authorization,
                )
                if customer:
                    session_state._remember_current_customer(db, session, customer)
                    if task.status == AgentTaskStatus.WAITING_USER:
                        session_state._remember_pending_task(db, session, task)
                    else:
                        session_state._clear_pending_task(db, session, task.id)
                    yield emit({
                        "event": "customer_selected",
                        "task_id": task.id,
                        "customer": customer,
                        "content": assistant_content,
                    })
                else:
                    yield emit({
                        "event": "customer_selection_failed",
                        "task_id": task.id,
                        "content": assistant_content,
                    })
                yield emit({"event": "final", "content": assistant_content})
            elif task and confirmation_decision and confirmation_decision.intent == "confirm":
                if task:
                    result, assistant_content = await task_execution._execute_waiting_task(
                        db,
                        task,
                        session=session,
                        team_id=team_id,
                        user_id=user_id,
                        authorization=authorization,
                    )
                    if result:
                        yield emit(result.to_event())
                    if result and result.success:
                        session_state._clear_pending_task(db, session, task.id)
                    task_event = {
                        "event": "task_completed" if result and result.success else "task_failed",
                        "task_id": task.id,
                        "content": assistant_content,
                    }
                    task_action = (task.state_json or {}).get("action")
                    next_task = (
                        session_state._get_current_waiting_task(db, session, team_id, user_id)
                        if result and result.success and interactions._should_offer_next_pending_task(task_action)
                        else None
                    )
                    if next_task and next_task.id != task.id:
                        task_event["next_task_id"] = next_task.id
                        task_event["interaction"] = interactions._pending_task_confirmation_interaction(assistant_content)
                    yield emit(task_event)
                    yield emit({"event": "final", "content": assistant_content})
                else:
                    assistant_content = "当前没有等待确认的操作。"
                    yield emit({"event": "final", "content": assistant_content})
            elif session_state._is_confirmation(content):
                assistant_content = "当前没有等待确认的操作。"
                yield emit({"event": "final", "content": assistant_content})
            else:
                async for event in crm_agent_graph_service.stream_events({
                    "db": db,
                    "team_id": team_id,
                    "user_id": user_id,
                    "session_id": session.id,
                    "session_context": session.context_json or {},
                    "content": content,
                    "authorization": authorization,
                }):
                    if event.get("event") in {
                        "confirmation_required",
                        "customer_selection_required",
                        "contact_fields_required",
                        "invoice_title_fields_required",
                        "deployment_info_fields_required",
                        "customer_member_fields_required",
                        "payment_fields_required",
                        "lead_fields_required",
                        "customer_fields_required",
                        "opportunity_fields_required",
                        "follow_up_quality_required",
                        "business_selection_required",
                    }:
                        task_factory._create_waiting_task_from_event(db, event, team_id, user_id, session)
                    if event.get("event") == "business_context_loaded":
                        session_state._remember_current_customer(db, session, event.get("customer"))
                    if event.get("event") == "final":
                        assistant_content = event.get("content")
                        if switch_notice and assistant_content:
                            event = {**event, "content": f"{switch_notice}\n\n{assistant_content}"}
                            assistant_content = event["content"]
                    yield emit(event)

            if not assistant_content:
                assistant_content = "Agent 已完成处理。"

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
            yield {"event": "error", "message": f"Agent服务异常：{str(exc)}"}
        finally:
            db.close()


agent_application_service = AgentApplicationService()
