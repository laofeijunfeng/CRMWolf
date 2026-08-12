"""LangGraph-native root runtime foundation for CRM Agent turns."""

from __future__ import annotations

import asyncio
import logging

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

from app.core.database import SessionLocal
from app.crud.agent import agent_session_crud, agent_task_crud, agent_workflow_action_crud
from app.services.agent import (
    action_plan,
    action_workflow,
    agent_copy,
    execution_trace,
    interactions,
    task_display,
    task_execution,
    workflow_action_ledger,
)
from app.services.agent.business_interaction_planner import (
    BusinessInteractionPlanner,
    business_interaction_planner,
)
from app.services.agent.checkpointer import agent_checkpoint_saver
from app.services.agent.confirmed_task_graph import (
    ConfirmedTaskGraphService,
)
from app.services.agent.confirmed_task_graph import (
    confirmed_task_graph_service as default_confirmed_task_graph_service,
)
from app.services.agent.customer_intelligence_graph import (
    CustomerIntelligenceGraphService,
)
from app.services.agent.customer_intelligence_graph import (
    customer_intelligence_graph_service as default_customer_intelligence_graph_service,
)
from app.services.agent.customer_intelligence_trigger import (
    AgentCustomerIntelligenceTurn,
    CustomerIntelligenceTriggerPolicy,
)
from app.services.agent.customer_intelligence_trigger import (
    customer_intelligence_trigger_policy as default_customer_intelligence_trigger_policy,
)
from app.services.agent.follow_up_confirmation_graph import (
    FollowUpConfirmationGraphService,
)
from app.services.agent.graph import crm_agent_graph_service
from app.services.agent.input import AgentTurnInput
from app.services.agent.interrupts import (
    AgentInterruptPayload,
    AgentResumePayload,
    interrupt_from_waiting_event,
    interrupt_from_waiting_task,
    interrupt_payload_from_json,
    validate_resume_payload,
)
from app.services.agent.new_flow_effects import (
    NewFlowGraphRunner,
    NewFlowGraphStreamer,
    NewFlowSideEffectContext,
    NewFlowSideEffectHandler,
)
from app.services.agent.new_flow_effects import (
    new_flow_side_effect_handler as default_new_flow_side_effect_handler,
)
from app.services.agent.pending_effects import (
    PendingTaskSideEffectContext,
    PendingTaskSideEffectHandler,
)
from app.services.agent.pending_effects import (
    pending_task_side_effect_handler as default_pending_task_side_effect_handler,
)
from app.services.agent.pending_graph import PendingTaskGraphService, pending_task_graph_service
from app.services.agent.post_write_effects import merge_post_write_effects, normalize_post_write_effects
from app.services.agent.state import (
    AgentRootRuntimeSideEffects,
    AgentRuntimeApplicationAction,
    AgentRuntimeContext,
    AgentRuntimeInvokeResult,
    AgentRuntimeState,
    AgentRuntimeStateHistoryItem,
    AgentRuntimeTurnOutput,
    PendingTaskGraphResult,
    PendingTaskGraphSideEffects,
)
from app.services.agent.turn_intent import AgentTurnIntentRouter, agent_turn_intent_router
from app.services.agent.types import JSONDict, JSONList, coerce_json_dict, coerce_json_value
from app.services.customer_intelligence_event_service import (
    CUSTOMER_INTELLIGENCE_COMMITTED_EVENT_TRIGGER_TYPES,
    CUSTOMER_INTELLIGENCE_INLINE_TRIGGER_TYPES,
)
from app.services.customer_intelligence_refresh_service import (
    AgentAsyncOperationBinding,
    CustomerIntelligenceRefreshService,
)
from app.services.customer_intelligence_refresh_service import (
    customer_intelligence_refresh_service as default_customer_intelligence_refresh_service,
)
from app.services.customer_intelligence_trace_service import visible_trace_events
from app.services.follow_up_task_confirmation_channel_service import (
    FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION,
    FOLLOW_UP_CONFIRMATION_PROMPT_EVENT,
    FOLLOW_UP_CONFIRMATION_RESOLVED_EVENT,
    follow_up_task_confirmation_channel_service,
)

AGENT_CHECKPOINT_NS = "crm_agent"
logger = logging.getLogger(__name__)


def build_agent_thread_id(*, team_id: int, user_id: int, session_id: int, session_key: str | None = None) -> str:
    """Return the stable LangGraph thread id for one CRM Agent session."""

    key = session_key or str(session_id)
    return f"crm_agent:{team_id}:{user_id}:{session_id}:{key}"


def build_agent_graph_config(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    session_key: str | None = None,
) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": build_agent_thread_id(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                session_key=session_key,
            ),
        },
        "metadata": {
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "session_key": session_key,
            "runtime": "crm_agent_root",
            "runtime_namespace": AGENT_CHECKPOINT_NS,
        },
    }


class AgentRootRuntime:
    """Persistent root graph boundary for the CRM Agent.

    It establishes the serializable state, thread/checkpoint contract, human
    interruption boundary, pending-task subgraph routing, and new-flow handoff.
    """

    def __init__(
        self,
        *,
        checkpointer=agent_checkpoint_saver,
        pending_graph_service: PendingTaskGraphService | None = None,
        new_flow_graph_service: NewFlowGraphStreamer | None = None,
        new_flow_side_effect_handler: NewFlowSideEffectHandler | None = None,
        confirmed_task_graph_service: ConfirmedTaskGraphService | None = None,
        pending_task_side_effect_handler: PendingTaskSideEffectHandler | None = None,
        customer_intelligence_graph_service: CustomerIntelligenceGraphService | None = None,
        customer_intelligence_trigger_policy: CustomerIntelligenceTriggerPolicy | None = None,
        customer_intelligence_refresh_service: CustomerIntelligenceRefreshService | None = None,
        turn_intent_router: AgentTurnIntentRouter | None = None,
        confirmation_channel_service=None,
        follow_up_confirmation_graph_service: FollowUpConfirmationGraphService | None = None,
        interaction_planner: BusinessInteractionPlanner | None = None,
    ) -> None:
        self.pending_graph_service = pending_graph_service or pending_task_graph_service
        self.new_flow_graph_service = new_flow_graph_service or crm_agent_graph_service
        self.new_flow_side_effect_handler = new_flow_side_effect_handler or default_new_flow_side_effect_handler
        self.confirmed_task_graph_service = confirmed_task_graph_service or default_confirmed_task_graph_service
        self.pending_task_side_effect_handler = (
            pending_task_side_effect_handler or default_pending_task_side_effect_handler
        )
        self.customer_intelligence_graph_service = (
            customer_intelligence_graph_service or default_customer_intelligence_graph_service
        )
        self.customer_intelligence_trigger_policy = (
            customer_intelligence_trigger_policy or default_customer_intelligence_trigger_policy
        )
        self.customer_intelligence_refresh_service = (
            customer_intelligence_refresh_service or default_customer_intelligence_refresh_service
        )
        self.turn_intent_router = turn_intent_router or agent_turn_intent_router
        self.confirmation_channel_service = confirmation_channel_service or follow_up_task_confirmation_channel_service
        self.follow_up_confirmation_graph_service = (
            follow_up_confirmation_graph_service
            or FollowUpConfirmationGraphService(channel_service=self.confirmation_channel_service)
        )
        self.interaction_planner = interaction_planner or business_interaction_planner
        self._graph = self._build_graph(checkpointer)

    def _build_graph(self, checkpointer):
        graph = StateGraph(AgentRuntimeState, context_schema=AgentRuntimeContext)
        graph.add_node("start_turn", self._start_turn)
        graph.add_node("interrupt_route_marker", self._interrupt_route_marker)
        graph.add_node("wait_for_interrupt_resume", self._wait_for_interrupt_resume)
        graph.add_node("resume_route_marker", self._resume_route_marker)
        graph.add_node("pending_task_subgraph", self._run_pending_task_subgraph)
        graph.add_node("pending_task_effects", self._apply_pending_task_effects)
        graph.add_node("new_flow_route_marker", self._new_flow_route_marker)
        graph.add_node("decide_application_action", self._decide_application_action)
        graph.add_node("new_flow_graph", self._run_new_flow_graph)
        graph.add_node("customer_intelligence_graph", self._run_customer_intelligence_graph)
        graph.add_node("confirmed_task_execution", self._run_confirmed_task_execution)
        graph.add_node("no_pending_confirmation", self._run_no_pending_confirmation)
        graph.add_node("reconcile_pending_business_interactions", self._reconcile_pending_business_interactions)
        graph.add_node("resolve_follow_up_confirmation", self._resolve_follow_up_confirmation)
        graph.add_node(
            "discard_unexposed_follow_up_confirmation",
            self._discard_unexposed_follow_up_confirmation,
        )
        graph.add_node("generated_interrupt_wait", self._wait_for_interrupt_resume)
        graph.add_node("finish_turn", self._finish_turn)
        graph.add_edge(START, "start_turn")
        graph.add_conditional_edges(
            "start_turn",
            self._route_after_start,
            {
                "interrupt": "interrupt_route_marker",
                "pending_task_subgraph": "pending_task_subgraph",
                "new_flow_graph": "new_flow_route_marker",
            },
        )
        graph.add_edge("interrupt_route_marker", "wait_for_interrupt_resume")
        graph.add_edge("wait_for_interrupt_resume", "resume_route_marker")
        graph.add_conditional_edges(
            "resume_route_marker",
            self._route_after_interrupt_resume,
            {
                "pending_task_subgraph": "pending_task_subgraph",
                "customer_intelligence_graph": "customer_intelligence_graph",
                "follow_up_confirmation": "resolve_follow_up_confirmation",
                "discard_follow_up_confirmation": "discard_unexposed_follow_up_confirmation",
                "finish": "decide_application_action",
            },
        )
        graph.add_edge("pending_task_subgraph", "pending_task_effects")
        graph.add_edge("pending_task_effects", "decide_application_action")
        graph.add_edge("new_flow_route_marker", "decide_application_action")
        graph.add_conditional_edges(
            "decide_application_action",
            self._route_after_application_action,
            {
                "new_flow_graph": "new_flow_graph",
                "confirmed_task_execution": "confirmed_task_execution",
                "no_pending_confirmation": "no_pending_confirmation",
                "generated_interrupt_wait": "generated_interrupt_wait",
                "finish": "reconcile_pending_business_interactions",
            },
        )
        graph.add_conditional_edges(
            "new_flow_graph",
            self._route_after_graph_output,
            {
                "generated_interrupt_wait": "generated_interrupt_wait",
                "customer_intelligence_graph": "customer_intelligence_graph",
                "finish": "reconcile_pending_business_interactions",
            },
        )
        graph.add_conditional_edges(
            "customer_intelligence_graph",
            self._route_after_customer_intelligence_graph,
            {
                "generated_interrupt_wait": "generated_interrupt_wait",
                "finish": "reconcile_pending_business_interactions",
            },
        )
        graph.add_conditional_edges(
            "confirmed_task_execution",
            self._route_after_confirmed_task_execution,
            {
                "customer_intelligence_graph": "customer_intelligence_graph",
                "finish": "reconcile_pending_business_interactions",
            },
        )
        graph.add_edge("no_pending_confirmation", "reconcile_pending_business_interactions")
        graph.add_edge("resolve_follow_up_confirmation", "reconcile_pending_business_interactions")
        graph.add_edge("discard_unexposed_follow_up_confirmation", "finish_turn")
        graph.add_conditional_edges(
            "reconcile_pending_business_interactions",
            self._route_after_pending_business_interactions,
            {
                "generated_interrupt_wait": "generated_interrupt_wait",
                "finish": "finish_turn",
            },
        )
        graph.add_edge("generated_interrupt_wait", "resume_route_marker")
        graph.add_edge("finish_turn", END)
        return graph.compile(checkpointer=checkpointer)

    async def checkpoint_turn_start(
        self,
        state: AgentRuntimeState,
        *,
        context: AgentRuntimeContext | None = None,
    ) -> AgentRuntimeInvokeResult:
        config = build_agent_graph_config(
            team_id=state["team_id"],
            user_id=state["user_id"],
            session_id=state["session_id"],
            session_key=state.get("session_key"),
        )
        result = await self._graph.ainvoke(
            state,
            config,
            context=context,
        )
        snapshot = await self._graph.aget_state(config)
        root_interrupt = _new_snapshot_interrupt_payload(snapshot, previous_interrupt_ids=set())
        if root_interrupt:
            projected = await self._publish_checkpointed_follow_up_projection(
                root_interrupt,
                context=context,
            )
            if not projected:
                return await self._discard_checkpointed_follow_up_projection(
                    config=config,
                    context=context,
                )
            result["current_interrupt"] = root_interrupt
            return result
        initial_interrupt = interrupt_payload_from_json(state.get("current_interrupt"))
        if state.get("pending_task_requested"):
            if initial_interrupt:
                bubbled_interrupt = _snapshot_interrupt_payload_except(
                    snapshot,
                    resumed_interrupt=initial_interrupt,
                )
            else:
                bubbled_interrupt = _new_snapshot_interrupt_payload(
                    snapshot,
                    previous_interrupt_ids=set(),
                )
            if bubbled_interrupt:
                projected = await self._publish_checkpointed_follow_up_projection(
                    bubbled_interrupt,
                    context=context,
                )
                if not projected:
                    return await self._discard_checkpointed_follow_up_projection(
                        config=config,
                        context=context,
                    )
                return await self._project_bubbled_pending_interrupt(
                    bubbled_interrupt,
                    snapshot=snapshot,
                    context=context,
                    config=config,
                )
        return result

    async def has_pending_interrupt(
        self,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        session_key: str | None = None,
    ) -> bool:
        snapshot = await self._graph.aget_state(
            build_agent_graph_config(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                session_key=session_key,
            ),
        )
        return bool(snapshot.interrupts)

    async def current_interrupt(
        self,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        session_key: str | None = None,
    ) -> AgentInterruptPayload | None:
        snapshot = await self._graph.aget_state(
            build_agent_graph_config(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                session_key=session_key,
            ),
        )
        values = _snapshot_values(snapshot)
        return interrupt_payload_from_json(values.get("current_interrupt"))

    async def current_checkpoint_state(
        self,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        session_key: str | None = None,
    ) -> JSONDict:
        snapshot = await self._graph.aget_state(
            build_agent_graph_config(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                session_key=session_key,
            ),
        )
        return _snapshot_values(snapshot)

    async def _checkpoint_values_for_turn(
        self,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        session_key: str | None = None,
    ) -> JSONDict:
        if hasattr(self, "_graph"):
            return await self.current_checkpoint_state(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                session_key=session_key,
            )
        current_interrupt = await self.current_interrupt(
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            session_key=session_key,
        )
        if current_interrupt:
            return {"current_interrupt": current_interrupt}
        return {}

    async def run_turn(
        self,
        *,
        turn_input: AgentTurnInput,
        content: str,
        team_id: int,
        user_id: int,
        session_id: int,
        session_key: str,
        current_customer: JSONDict,
        context: AgentRuntimeContext,
    ) -> AgentRuntimeInvokeResult:
        checkpoint_values = await self._checkpoint_values_for_turn(
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            session_key=session_key,
        )
        checkpoint_interrupt = interrupt_payload_from_json(checkpoint_values.get("current_interrupt"))
        if checkpoint_interrupt is not None:
            checkpoint_interrupt = await self._discard_stale_follow_up_confirmation_before_turn(
                checkpoint_interrupt=checkpoint_interrupt,
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                session_key=session_key,
                context=context,
            )
        if checkpoint_interrupt is None:
            structured_action_result = await self._handle_structured_business_action_turn(
                turn_input=turn_input,
                content=content,
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                current_customer=current_customer,
                context=context,
            )
            if structured_action_result is not None:
                return structured_action_result
        runtime_current_interrupt = checkpoint_interrupt
        if checkpoint_interrupt:
            _align_context_task_to_interrupt(context, checkpoint_interrupt)
        initial_state = _turn_start_state(
            turn_input=turn_input,
            content=content,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            session_key=session_key,
            current_interrupt=runtime_current_interrupt,
            suspended_candidates=_suspended_candidates_from_state(checkpoint_values),
            current_customer=current_customer,
            context=context,
        )
        if not runtime_current_interrupt:
            return await self.checkpoint_turn_start(initial_state, context=context)

        has_pending_interrupt = await self.has_pending_interrupt(
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            session_key=session_key,
        )
        if not has_pending_interrupt:
            await self.checkpoint_turn_start(initial_state, context=context)
        turn_intent_result = await self.turn_intent_router.route_resume(
            context.db,
            team_id=team_id,
            user_id=user_id,
            session=context.session,
            turn_input=turn_input,
            current_interrupt=runtime_current_interrupt,
            active_task=context.task,
            suspended_candidates=initial_state.get("suspended_candidates") or [],
        )
        turn_intent_event: JSONDict = {
            "event": "turn_intent_classified",
            "intent": turn_intent_result.decision.intent,
            "confidence": turn_intent_result.decision.confidence,
            "target_task_id": turn_intent_result.decision.target_task_id,
            "normalized_action": turn_intent_result.decision.normalized_action,
            "resume_action": turn_intent_result.resume_payload.get("action"),
            "reason": turn_intent_result.decision.reason,
            "source": turn_intent_result.source,
        }
        context.side_effects.pending_task_events.append(turn_intent_event)
        await _publish_event(context, turn_intent_event)
        return await self.resume_interrupt(
            resume_payload=turn_intent_result.resume_payload,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            session_key=session_key,
            context=context,
            current_interrupt=runtime_current_interrupt,
        )

    async def _discard_stale_follow_up_confirmation_before_turn(
        self,
        *,
        checkpoint_interrupt: AgentInterruptPayload,
        team_id: int,
        user_id: int,
        session_id: int,
        session_key: str,
        context: AgentRuntimeContext,
    ) -> AgentInterruptPayload | None:
        case_public_id = _follow_up_confirmation_case_public_id(checkpoint_interrupt)
        if case_public_id is None or context.db is None:
            return checkpoint_interrupt
        try:
            is_pending = self.confirmation_channel_service.is_case_pending_for_owner(
                context.db,
                team_id=team_id,
                user_id=user_id,
                case_public_id=case_public_id,
            )
        except Exception:
            logger.exception("Follow-up confirmation interrupt revalidation failed")
            return checkpoint_interrupt
        if is_pending:
            return checkpoint_interrupt

        await self._discard_stale_follow_up_confirmation_interrupt(
            case_public_id=case_public_id,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            session_key=session_key,
            context=context,
        )
        event = {
            "event": "follow_up_task_confirmation_stale_interrupt_discarded",
            "case_public_id": case_public_id,
            "reason": "case_not_pending_for_owner",
        }
        context.side_effects.business_interaction_events.append(event)
        await _publish_event(context, event)
        return None

    async def _discard_stale_follow_up_confirmation_interrupt(
        self,
        *,
        case_public_id: str,
        team_id: int,
        user_id: int,
        session_id: int,
        session_key: str,
        context: AgentRuntimeContext,
    ) -> None:
        config = build_agent_graph_config(
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            session_key=session_key,
        )
        await self._graph.ainvoke(
            Command(
                resume={
                    "action": "cancel",
                    "metadata": {
                        "business_action": FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION,
                        "case_public_id": case_public_id,
                        "follow_up_confirmation_discard_reason": "stale_case",
                    },
                }
            ),
            config,
            context=context,
        )
        context.side_effects.current_interrupt = None

    async def _handle_structured_business_action_turn(
        self,
        *,
        turn_input: AgentTurnInput,
        content: str,
        team_id: int,
        user_id: int,
        session_id: int,
        current_customer: JSONDict,
        context: AgentRuntimeContext,
    ) -> AgentRuntimeInvokeResult | None:
        action_type = _structured_business_action_type_from_turn(turn_input)
        if action_type != "resolve_follow_up_task_confirmation_case":
            return None
        case_public_id = _structured_follow_up_confirmation_case_public_id_from_turn(turn_input)
        if not case_public_id:
            return None

        workflow = action_workflow.required_write_contract(
            action=action_type,
            source=action_workflow.SOURCE_EXPLICIT_USER_REQUEST,
        )
        action_id = str(workflow["action_id"])
        payload: JSONDict = {
            "case_id": case_public_id,
            "reply_text": content,
        }
        envelope = task_execution.ActionExecutionEnvelope(
            action_id=action_id,
            action_type=action_type,
            workflow=workflow,
            payload=payload,
            customer=current_customer,
            session_id=session_id,
            task_key=action_id,
        )
        workflow_action_ledger.mark_action_running(
            context.db,
            workflow=workflow,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            task_id=None,
            source_type=workflow_action_ledger.SOURCE_PENDING_RESUME,
            payload=payload,
            target_type="follow_up_confirmation_case",
            target_id=None,
            reason="structured_business_action",
        )
        execution = await task_execution.execute_action_envelope(
            context.db,
            envelope,
            session=context.session,
            team_id=team_id,
            user_id=user_id,
            authorization=context.authorization or "",
            event_sink=context.event_sink,
        )
        tool_result = execution.tool_result
        tool_event = coerce_json_dict(tool_result.to_event()) if tool_result else {}
        events: list[JSONDict] = [
            {
                "event": "structured_business_action_started",
                "action_type": action_type,
                "action_id": action_id,
                "case_public_id": case_public_id,
            },
            *execution.progress_events,
        ]
        if tool_event:
            events.append(tool_event)
        if tool_result and tool_result.success:
            result_payload = coerce_json_dict(tool_result.data)
            resolved_event = _follow_up_confirmation_resolved_event_from_tool_result(
                result_payload,
                case_public_id=case_public_id,
            )
            assistant_content = str(
                resolved_event.get("content") or result_payload.get("content") or agent_copy.generic_completed()
            )
            events.append(resolved_event)
            events.append(
                {
                    "event": "action_completed",
                    "action_id": action_id,
                    "action_type": action_type,
                }
            )
            workflow_action_ledger.mark_action_executed(
                context.db,
                workflow=workflow,
                team_id=team_id,
                user_id=user_id,
                result=result_payload,
                task_id=None,
            )
            await _publish_events(context, events)
            context.side_effects.new_flow_events.extend(events)
            context.side_effects.new_flow_assistant_content = assistant_content
            return coerce_json_dict(
                {
                    "application_action": "run_new_flow",
                    "events": events,
                    "assistant_content": assistant_content,
                    "structured_business_action": {
                        "action_type": action_type,
                        "action_id": action_id,
                        "case_public_id": case_public_id,
                        "status": "executed",
                    },
                }
            )

        error_message = tool_result.error_message if tool_result else f"暂不支持的执行动作：{action_type}"
        events.append(
            {
                "event": "action_failed",
                "action_id": action_id,
                "action_type": action_type,
                "reason": error_message,
            }
        )
        workflow_action_ledger.mark_action_failed(
            context.db,
            workflow=workflow,
            team_id=team_id,
            user_id=user_id,
            error_message=error_message,
            task_id=None,
            result=tool_event or {"success": False, "error": error_message},
        )
        assistant_content = f"执行失败：{error_message}"
        await _publish_events(context, events)
        context.side_effects.new_flow_events.extend(events)
        context.side_effects.new_flow_assistant_content = assistant_content
        return coerce_json_dict(
            {
                "application_action": "run_new_flow",
                "events": events,
                "assistant_content": assistant_content,
                "structured_business_action": {
                    "action_type": action_type,
                    "action_id": action_id,
                    "case_public_id": case_public_id,
                    "status": "failed",
                    "reason": error_message,
                },
            }
        )

    async def checkpoint_state_at(
        self,
        *,
        checkpoint_id: str,
        team_id: int,
        user_id: int,
        session_id: int,
        session_key: str | None = None,
    ) -> JSONDict:
        snapshot = await self._graph.aget_state(
            _config_with_checkpoint_id(
                build_agent_graph_config(
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session_id,
                    session_key=session_key,
                ),
                checkpoint_id=checkpoint_id,
            ),
        )
        return coerce_json_dict(snapshot.values)

    async def state_history(
        self,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        session_key: str | None = None,
        before_checkpoint_id: str | None = None,
        limit: int | None = None,
    ) -> list[AgentRuntimeStateHistoryItem]:
        config = build_agent_graph_config(
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            session_key=session_key,
        )
        before_config = (
            _config_with_checkpoint_id(config, checkpoint_id=before_checkpoint_id) if before_checkpoint_id else None
        )
        history: list[AgentRuntimeStateHistoryItem] = []
        async for snapshot in self._graph.aget_state_history(
            config,
            before=before_config,
            limit=limit,
        ):
            history.append(_state_history_item(snapshot))
        return history

    async def resume_interrupt(
        self,
        *,
        resume_payload: AgentResumePayload,
        team_id: int,
        user_id: int,
        session_id: int,
        session_key: str | None = None,
        context: AgentRuntimeContext | None = None,
        current_interrupt: AgentInterruptPayload | None = None,
    ) -> AgentRuntimeInvokeResult:
        interrupt_payload = current_interrupt or await self.current_interrupt(
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            session_key=session_key,
        )
        if not interrupt_payload:
            raise ValueError("cannot resume agent runtime without an active interrupt")
        validate_resume_payload(resume_payload, current_interrupt=interrupt_payload)
        config = build_agent_graph_config(
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            session_key=session_key,
        )
        result = await self._graph.ainvoke(
            Command(resume=resume_payload),
            config,
            context=context,
        )
        return await self._continue_ready_nodes_after_resume(
            result,
            config=config,
            context=context,
            resumed_interrupt=interrupt_payload,
        )

    async def _continue_ready_nodes_after_resume(
        self,
        result: AgentRuntimeInvokeResult,
        *,
        config: RunnableConfig,
        context: AgentRuntimeContext | None,
        resumed_interrupt: AgentInterruptPayload,
    ) -> AgentRuntimeInvokeResult:
        """Continue a resumed root graph until it reaches END or a new interrupt."""

        current_result = result
        for _ in range(8):
            snapshot = await self._graph.aget_state(config)
            bubbled_interrupt = _snapshot_interrupt_payload_except(snapshot, resumed_interrupt=resumed_interrupt)
            if bubbled_interrupt:
                projected = await self._publish_checkpointed_follow_up_projection(
                    bubbled_interrupt,
                    context=context,
                )
                if not projected:
                    return await self._discard_checkpointed_follow_up_projection(
                        config=config,
                        context=context,
                    )
                return await self._project_bubbled_pending_interrupt(
                    bubbled_interrupt,
                    snapshot=snapshot,
                    context=context,
                    config=config,
                )
            interrupt_ids = _snapshot_interrupt_ids(snapshot)
            if not _snapshot_has_next_nodes(snapshot):
                if getattr(snapshot, "interrupts", ()):
                    return coerce_json_dict(getattr(snapshot, "values", None))
                return current_result
            current_result = await self._graph.ainvoke(None, config, context=context)
            next_snapshot = await self._graph.aget_state(config)
            bubbled_interrupt = _new_snapshot_interrupt_payload(next_snapshot, previous_interrupt_ids=interrupt_ids)
            if bubbled_interrupt:
                projected = await self._publish_checkpointed_follow_up_projection(
                    bubbled_interrupt,
                    context=context,
                )
                if not projected:
                    return await self._discard_checkpointed_follow_up_projection(
                        config=config,
                        context=context,
                    )
                return await self._project_bubbled_pending_interrupt(
                    bubbled_interrupt,
                    snapshot=next_snapshot,
                    context=context,
                    config=config,
                )
        return current_result

    async def _publish_checkpointed_follow_up_projection(
        self,
        interrupt_payload: AgentInterruptPayload,
        *,
        context: AgentRuntimeContext | None,
    ) -> bool:
        """Expose a confirmation only after its native interrupt is checkpoint-visible."""

        if context is None or context.db is None or interrupt_payload.get("reason") != "follow_up_task_confirmation":
            return True
        interaction = coerce_json_dict(interrupt_payload.get("interaction"))
        payload = coerce_json_dict(interaction.get("payload"))
        prompt_key = payload.get("prompt_delivery_key")
        if not isinstance(prompt_key, str) or not prompt_key:
            return True
        try:
            projection = self.follow_up_confirmation_graph_service.mark_projected(
                context.db,
                team_id=context.team_id,
                prompt_key=prompt_key,
            )
            projection_status = (
                projection.get("status") if isinstance(projection, dict) else getattr(projection, "status", None)
            )
            if projection_status != "PROJECTED":
                raise RuntimeError(
                    f"projection acknowledgement did not reach PROJECTED: {projection_status or 'MISSING'}"
                )
        except Exception as exc:
            logger.exception("Follow-up confirmation projection acknowledgement failed")
            rollback = getattr(context.db, "rollback", None)
            if callable(rollback):
                rollback()
            try:
                self.follow_up_confirmation_graph_service.mark_projection_failed(
                    context.db,
                    team_id=context.team_id,
                    prompt_key=prompt_key,
                    error_message=str(exc),
                )
            except Exception:
                logger.exception("Follow-up confirmation projection acknowledgement audit failed")
            event = {
                "event": "follow_up_task_confirmation_projection_ack_failed",
                "prompt_key": prompt_key,
                "reason": str(exc),
            }
            context.side_effects.business_interaction_events.append(event)
            await _publish_event(context, event)
            return False

        prompt_event = {
            "event": FOLLOW_UP_CONFIRMATION_PROMPT_EVENT,
            "content": str(
                interaction.get("prompt")
                or (payload.get("case", {}).get("question_text") if isinstance(payload.get("case"), dict) else "")
                or ""
            ),
            "content_format": "text",
            "case_public_id": payload.get("case_public_id"),
            "cases": [payload["case"]] if isinstance(payload.get("case"), dict) else [],
            "interaction": interaction,
        }
        if any(
            event.get("event") == FOLLOW_UP_CONFIRMATION_PROMPT_EVENT
            and coerce_json_dict(event.get("interaction")).get("interaction_id") == interaction.get("interaction_id")
            for event in context.side_effects.business_interaction_events
        ):
            return True
        context.side_effects.business_interaction_events.append(prompt_event)
        prompt_content = prompt_event.get("content")
        if isinstance(prompt_content, str) and prompt_content:
            context.side_effects.business_interaction_assistant_content = prompt_content
        await _publish_event(context, prompt_event)
        return True

    async def _discard_checkpointed_follow_up_projection(
        self,
        *,
        config: RunnableConfig,
        context: AgentRuntimeContext | None,
    ) -> AgentRuntimeInvokeResult:
        """Resume an unexposed interrupt internally so user input cannot bind to it."""

        return await self._graph.ainvoke(
            Command(
                resume={
                    "action": "cancel",
                    "metadata": {
                        "business_action": FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION,
                        "projection_ack_failed": True,
                    },
                }
            ),
            config,
            context=context,
        )

    async def _project_bubbled_pending_interrupt(
        self,
        interrupt_payload: AgentInterruptPayload,
        *,
        snapshot: object,
        context: AgentRuntimeContext | None,
        config: RunnableConfig,
    ) -> AgentRuntimeInvokeResult:
        """Project a native child-graph interrupt into the root turn output."""

        state: AgentRuntimeInvokeResult = {}
        state.update(coerce_json_dict(getattr(snapshot, "values", None)))
        task_projection = _interrupt_task_projection(interrupt_payload)
        snapshot_interrupts = _snapshot_interrupt_items(snapshot)
        if not snapshot_interrupts:
            await self._graph.aupdate_state(
                config,
                {
                    "current_interrupt": interrupt_payload,
                    "pending_task_requested": True,
                    "task_projection": task_projection,
                },
            )
        pending_result = _pending_graph_result_from_bubbled_interrupt(interrupt_payload)
        state.update(
            {
                "application_action": "pending_handled",
                "pending_task_handled": True,
                "pending_task_result": _pending_task_result_projection(pending_result),
                "assistant_content": pending_result.get("assistant_content"),
                "current_interrupt": interrupt_payload,
                "task_projection": task_projection,
                "events": [
                    *[event for event in state.get("events", []) if isinstance(event, dict)],
                    {
                        "event": "agent_root_pending_task_interrupt_bubbled",
                        "source_event": interrupt_payload.get("source_event"),
                    },
                ],
            }
        )
        if snapshot_interrupts:
            state["__interrupt__"] = snapshot_interrupts
        if context and context.db and context.session:
            if not context.task:
                task_id = _interrupt_task_projection_id(interrupt_payload)
                if task_id is not None:
                    context.task = agent_task_crud.get_by_id(
                        context.db,
                        task_id,
                        team_id=context.team_id,
                        user_id=context.user_id,
                    )
            pending_side_effects = PendingTaskGraphSideEffects(task=context.task)
            result = self.pending_task_side_effect_handler.apply(
                pending_result,
                PendingTaskSideEffectContext(
                    db=context.db,
                    session=context.session,
                    team_id=context.team_id,
                    user_id=context.user_id,
                    task=context.task,
                    switch_notice=context.switch_notice,
                    graph_side_effects=pending_side_effects,
                ),
            )
            context.task = result.task
            context.side_effects.pending_task_result = pending_result
            context.side_effects.pending_task_graph_side_effects = pending_side_effects
            context.side_effects.pending_task_events.extend(result.events)
            await _publish_events(context, result.events)
            context.side_effects.pending_task_assistant_content = (
                result.assistant_content if isinstance(result.assistant_content, str) else None
            )
            context.side_effects.pending_task_switch_notice = result.switch_notice
            context.side_effects.current_interrupt = result.current_interrupt or interrupt_payload
        return state

    def _start_turn(self, state: AgentRuntimeState) -> AgentRuntimeState:
        return {
            "runtime_status": "started",
            "application_action": "finish",
            "pending_task_handled": False,
            "pending_task_result": {},
            "new_flow_result": {},
            "post_write_effects": {},
            "resume_payload": {},
            "assistant_content": None,
            "switch_notice": None,
            "deferred_final_events": [],
            "follow_up_confirmation_projection_suppressed": False,
            "follow_up_confirmation_discard_reason": None,
            "events": [
                {
                    "event": "agent_root_graph_started",
                    "thread_id": build_agent_thread_id(
                        team_id=state["team_id"],
                        user_id=state["user_id"],
                        session_id=state["session_id"],
                        session_key=state.get("session_key"),
                    ),
                }
            ],
        }

    def _route_after_start(self, state: AgentRuntimeState) -> str:
        if state.get("current_interrupt"):
            return "interrupt"
        if state.get("pending_task_requested"):
            return "pending_task_subgraph"
        return "new_flow_graph"

    def _interrupt_route_marker(self, state: AgentRuntimeState) -> AgentRuntimeState:
        return self._route_event("interrupt", state)

    def _wait_for_interrupt_resume(
        self,
        state: AgentRuntimeState,
        runtime: Runtime[AgentRuntimeContext],
    ) -> AgentRuntimeState:
        resume_payload = interrupt(state["current_interrupt"])
        resume_payload_json = coerce_json_dict(resume_payload)
        metadata = coerce_json_dict(resume_payload_json.get("metadata"))
        active_interrupt = interrupt_payload_from_json(state.get("current_interrupt")) or {}
        if active_interrupt.get("reason") == "follow_up_task_confirmation":
            interaction = coerce_json_dict(active_interrupt.get("interaction"))
            interaction_payload = coerce_json_dict(interaction.get("payload"))
            case_public_id = interaction_payload.get("case_public_id")
            if isinstance(case_public_id, str) and case_public_id:
                metadata.setdefault("case_public_id", case_public_id)
                metadata.setdefault("follow_up_confirmation_case_public_id", case_public_id)
            metadata.setdefault("business_action", FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION)
            resume_payload_json["business_action"] = FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION
            resume_payload_json["interrupt_reason"] = "follow_up_task_confirmation"
            resume_payload_json["metadata"] = metadata
        turn_intent = coerce_json_dict(metadata.get("turn_intent"))
        projection_ack_failed = metadata.get("projection_ack_failed") is True
        discard_reason = metadata.get("follow_up_confirmation_discard_reason")
        should_discard_follow_up_confirmation = projection_ack_failed or isinstance(discard_reason, str)
        update: AgentRuntimeState = {
            "runtime_status": "resumed",
            "current_interrupt": None,
            "resume_payload": resume_payload_json,
            "turn_intent": turn_intent,
            "follow_up_confirmation_projection_suppressed": should_discard_follow_up_confirmation,
            "follow_up_confirmation_discard_reason": (discard_reason if isinstance(discard_reason, str) else None),
            "events": [
                {
                    "event": "agent_root_interrupt_resumed",
                    "resume_action": resume_payload_json.get("action"),
                    "turn_intent": turn_intent.get("intent"),
                    "turn_intent_confidence": turn_intent.get("confidence"),
                }
            ],
        }
        if (runtime.context and runtime.context.task) or _resume_task_projection_id(
            update.get("resume_payload")
        ) is not None:
            update["pending_task_requested"] = True
        return update

    def _route_after_interrupt_resume(self, state: AgentRuntimeState) -> str:
        if state.get("follow_up_confirmation_projection_suppressed"):
            return "discard_follow_up_confirmation"
        if _is_follow_up_confirmation_resume(state.get("resume_payload")):
            return "follow_up_confirmation"
        if _is_customer_intelligence_resume(state.get("resume_payload")):
            return "customer_intelligence_graph"
        if state.get("pending_task_requested"):
            return "pending_task_subgraph"
        return "finish"

    def _resume_route_marker(self, state: AgentRuntimeState) -> AgentRuntimeState:
        return self._route_event("resume", state)

    async def _run_pending_task_subgraph(
        self,
        state: AgentRuntimeState,
        runtime: Runtime[AgentRuntimeContext],
    ) -> AgentRuntimeState:
        context = runtime.context
        pending_branch_event = _step_event(
            "pending_task_branch",
            "started",
            "进入待确认或待补充流程",
        )
        context.side_effects.pending_task_events.append(pending_branch_event)
        await _publish_event(context, pending_branch_event)
        if not context.task and context.db:
            task_id = _pending_task_id_from_state(state)
            if task_id is not None:
                context.task = agent_task_crud.get_by_id(
                    context.db,
                    task_id,
                    team_id=context.team_id,
                    user_id=context.user_id,
                )
        if not context.db or not context.session or not context.turn_input:
            return {
                "route": "pending_task_subgraph",
                "pending_task_result": {"handled": False, "available": False},
                "events": [
                    {
                        "event": "agent_root_pending_task_subgraph_unavailable",
                        "reason": "missing_runtime_context",
                    }
                ],
            }
        pending_side_effects = PendingTaskGraphSideEffects(
            task=context.task,
            event_sink=context.event_sink,
        )
        pending_graph_input = {
            "db": context.db,
            "session": context.session,
            "task": context.task,
            "turn_input": context.turn_input,
            "content": context.content,
            "team_id": context.team_id,
            "user_id": context.user_id,
            "session_id": context.session_id,
            "authorization": context.authorization,
            "resume_payload": state.get("resume_payload") or {},
            "suspended_candidates": state.get("suspended_candidates") or [],
            "events": [],
        }
        run_with_trace = getattr(self.pending_graph_service, "run_with_trace", None)
        if callable(run_with_trace):
            result = await run_with_trace(pending_graph_input, side_effects=pending_side_effects)
        else:
            result = await self.pending_graph_service.run(pending_graph_input, side_effects=pending_side_effects)
        context.task = pending_side_effects.task
        context.side_effects.pending_task_result = result
        context.side_effects.pending_task_graph_side_effects = pending_side_effects
        return {
            "route": "pending_task_subgraph",
            "pending_task_result": _pending_task_result_projection(result),
            "events": [
                {
                    "event": "agent_root_pending_task_subgraph_completed",
                    "handled": bool(result.get("handled")),
                    "has_task": bool(result.get("has_active_task") or result.get("task_projection")),
                    "event_count": len(result.get("events", [])),
                }
            ],
        }

    async def _apply_pending_task_effects(
        self,
        state: AgentRuntimeState,
        runtime: Runtime[AgentRuntimeContext],
    ) -> AgentRuntimeState:
        context = runtime.context
        if not context.db or not context.session:
            return {
                "events": [
                    {
                        "event": "agent_root_pending_task_effects_unavailable",
                        "reason": "missing_runtime_context",
                    }
                ],
            }
        pending_result = context.side_effects.pending_task_result
        if not pending_result:
            return {
                "events": [
                    {
                        "event": "agent_root_pending_task_effects_skipped",
                        "reason": "empty_pending_result",
                    }
                ],
            }
        result = self.pending_task_side_effect_handler.apply(
            pending_result,
            PendingTaskSideEffectContext(
                db=context.db,
                session=context.session,
                team_id=context.team_id,
                user_id=context.user_id,
                task=context.task,
                switch_notice=context.switch_notice,
                graph_side_effects=context.side_effects.pending_task_graph_side_effects,
            ),
        )
        context.task = result.task
        context.switch_notice = result.switch_notice
        context.side_effects.pending_task_events.extend(result.events)
        await _publish_events(
            context,
            _unstreamed_pending_effect_events(result.events, streamed_pending_steps=bool(context.event_sink)),
        )
        context.side_effects.pending_task_assistant_content = result.assistant_content
        context.side_effects.pending_task_switch_notice = result.switch_notice
        current_interrupt = result.current_interrupt
        context.side_effects.current_interrupt = current_interrupt
        suspended_task = (
            context.side_effects.pending_task_graph_side_effects.suspended_task
            if context.side_effects.pending_task_graph_side_effects
            else None
        )
        suspended_candidates = _updated_suspended_candidates(
            state.get("suspended_candidates"),
            suspended_task=suspended_task,
        )
        update: AgentRuntimeState = {
            "current_interrupt": current_interrupt,
            "suspended_candidates": suspended_candidates,
            "events": [
                {
                    "event": "agent_root_pending_task_effects_applied",
                    "event_count": len(result.events),
                    "has_assistant_content": bool(result.assistant_content),
                    "has_switch_notice": bool(result.switch_notice),
                    "has_interrupt": bool(current_interrupt),
                }
            ],
        }
        if result.assistant_content:
            update["assistant_content"] = result.assistant_content
        if result.switch_notice:
            update["switch_notice"] = result.switch_notice
        if current_interrupt:
            update["task_projection"] = _interrupt_task_projection(current_interrupt)
        return update

    def _new_flow_route_marker(self, state: AgentRuntimeState) -> AgentRuntimeState:
        return self._route_event("new_flow_graph", state)

    def _decide_application_action(self, state: AgentRuntimeState) -> AgentRuntimeState:
        action = decide_application_action(state)
        pending_result = state.get("pending_task_result") or {}
        update: AgentRuntimeState = {
            "application_action": action,
            "pending_task_handled": action == "pending_handled",
            "events": [
                {
                    "event": "agent_root_application_action_decided",
                    "application_action": action,
                }
            ],
        }
        assistant_content = pending_result.get("assistant_content")
        if isinstance(assistant_content, str):
            update["assistant_content"] = assistant_content
        switch_notice = pending_result.get("switch_notice")
        if isinstance(switch_notice, str):
            update["switch_notice"] = switch_notice
        return update

    def _route_after_application_action(self, state: AgentRuntimeState) -> str:
        if state.get("application_action") == "execute_confirmed_task":
            return "confirmed_task_execution"
        if state.get("application_action") == "no_pending_confirmation":
            return "no_pending_confirmation"
        if state.get("current_interrupt"):
            return "generated_interrupt_wait"
        if state.get("application_action") == "run_new_flow":
            return "new_flow_graph"
        return "finish"

    def _route_after_graph_output(self, state: AgentRuntimeState) -> str:
        if state.get("current_interrupt"):
            return "generated_interrupt_wait"
        if state.get("customer_intelligence_requested"):
            return "customer_intelligence_graph"
        return "finish"

    def _should_run_customer_intelligence_inline(self, state: AgentRuntimeState, event: object | None) -> bool:
        if _is_customer_intelligence_resume(state.get("resume_payload")):
            return True
        trigger_type = _customer_intelligence_trigger_type(event)
        if trigger_type in CUSTOMER_INTELLIGENCE_INLINE_TRIGGER_TYPES:
            return True
        return trigger_type not in CUSTOMER_INTELLIGENCE_COMMITTED_EVENT_TRIGGER_TYPES

    async def _schedule_customer_intelligence_refresh(
        self,
        runtime: Runtime[AgentRuntimeContext],
        event: object,
    ) -> AgentRuntimeState:
        context = runtime.context
        trigger_type = _customer_intelligence_trigger_type(event)
        event_key = _customer_intelligence_event_key(event)
        customer_id = _customer_intelligence_customer_id(event)
        scheduled_event: JSONDict = {
            "event": "agent_root_customer_intelligence_refresh_scheduled",
            "mode": "background",
            "trigger_type": trigger_type,
            "event_key": event_key,
            "customer_id": customer_id,
        }
        if isinstance(context.user_message_id, int):
            scheduled_event["source_user_message_id"] = context.user_message_id
        result_projection: JSONDict = {
            "handled": True,
            "mode": "background",
            "scheduled": False,
            "trigger_type": trigger_type,
            "event_key": event_key,
            "customer_id": customer_id,
        }
        if isinstance(context.user_message_id, int):
            result_projection["source_user_message_id"] = context.user_message_id

        try:
            request = await self.customer_intelligence_refresh_service.trigger_committed_event_refresh(
                context.db,
                event=event,
                scope="brief",
                agent_binding=AgentAsyncOperationBinding(
                    team_id=context.team_id,
                    user_id=context.user_id,
                    session_id=context.session_id,
                    source_user_message_id=context.user_message_id,
                ),
            )
        except Exception as exc:
            logger.exception(
                "Agent 客户智能后台刷新调度失败，已隔离为非阻塞后置效果: team_id=%s, session_id=%s, trigger_type=%s",
                context.team_id,
                context.session_id,
                trigger_type,
            )
            failed_event = {
                **scheduled_event,
                "event": "agent_root_customer_intelligence_refresh_schedule_failed",
                "reason": str(exc),
            }
            context.side_effects.customer_intelligence_events.append(failed_event)
            await _publish_event(context, failed_event)
            return {
                "customer_intelligence_requested": False,
                "customer_intelligence_result": {
                    **result_projection,
                    "handled": False,
                    "reason": "background_refresh_schedule_failed",
                },
                "events": [failed_event],
            }

        scheduled = bool(getattr(request, "scheduled", False))
        request_id = getattr(request, "request_id", None)
        scheduled_event["scheduled"] = scheduled
        if isinstance(request_id, str):
            scheduled_event["request_id"] = request_id
            result_projection["request_id"] = request_id
        operation_public_id = getattr(request, "operation_public_id", None)
        if isinstance(operation_public_id, str) and operation_public_id:
            scheduled_event["operation_public_id"] = operation_public_id
            result_projection["operation_public_id"] = operation_public_id
        result_projection["scheduled"] = scheduled
        result_projection["scope"] = str(getattr(request, "scope", "brief") or "brief")
        delivery_event = scheduled_event
        if not scheduled:
            schedule_error = str(getattr(request, "schedule_error", "") or "")
            delivery_event = {
                **scheduled_event,
                "event": "agent_root_customer_intelligence_refresh_schedule_failed",
                "reason": schedule_error or "background_refresh_not_scheduled",
            }
            result_projection["handled"] = False
            result_projection["reason"] = "background_refresh_schedule_failed"
            if schedule_error:
                result_projection["schedule_error"] = schedule_error
        context.side_effects.customer_intelligence_events.append(delivery_event)
        context.side_effects.customer_intelligence_result = result_projection
        await _publish_event(context, delivery_event)
        return {
            "customer_intelligence_requested": False,
            "customer_intelligence_event": _customer_intelligence_event_projection(event),
            "customer_intelligence_result": result_projection,
            "events": [delivery_event],
        }

    async def _run_customer_intelligence_graph(
        self,
        state: AgentRuntimeState,
        runtime: Runtime[AgentRuntimeContext],
    ) -> AgentRuntimeState:
        context = runtime.context
        event_object = context.customer_intelligence_event
        if not self._should_run_customer_intelligence_inline(state, event_object):
            if not context.db:
                return {
                    "customer_intelligence_requested": False,
                    "customer_intelligence_result": {
                        "handled": False,
                        "reason": "missing_runtime_context",
                    },
                    "events": [
                        {
                            "event": "agent_root_customer_intelligence_refresh_unavailable",
                            "reason": "missing_runtime_context",
                        }
                    ],
                }
            if event_object is None:
                return {
                    "customer_intelligence_requested": False,
                    "customer_intelligence_result": {"handled": False, "reason": "missing_event"},
                    "events": [
                        {
                            "event": "agent_root_customer_intelligence_skipped",
                            "reason": "missing_event",
                        }
                    ],
                }
            return await self._schedule_customer_intelligence_refresh(runtime, event_object)

        started_event = _step_event(
            "customer_intelligence",
            "started",
            "更新客户智能档案",
        )
        context.side_effects.customer_intelligence_events.append(started_event)
        await _publish_event(context, started_event)
        if not context.db:
            return {
                "customer_intelligence_result": {"handled": False, "reason": "missing_runtime_context"},
                "events": [
                    {
                        "event": "agent_root_customer_intelligence_unavailable",
                        "reason": "missing_runtime_context",
                    }
                ],
            }

        streamed_customer_intelligence_trace = False
        try:
            if _is_customer_intelligence_resume(state.get("resume_payload")):
                event_key = _customer_intelligence_event_key_from_state(state)
                if not event_key:
                    return {
                        "customer_intelligence_result": {"handled": False, "reason": "missing_event_key"},
                        "events": [
                            {
                                "event": "agent_root_customer_intelligence_resume_skipped",
                                "reason": "missing_event_key",
                            }
                        ],
                    }
                graph_input = {
                    "team_id": context.team_id,
                    "user_id": context.user_id,
                    "session_id": context.session_id,
                    "event_key": event_key,
                    "resume_payload": state.get("resume_payload") or {},
                }
                stream_resume_review = getattr(self.customer_intelligence_graph_service, "stream_resume_review", None)
                if callable(stream_resume_review):
                    result = {}
                    async for chunk in stream_resume_review(graph_input):
                        if not isinstance(chunk, dict):
                            continue
                        if chunk.get("kind") == "event":
                            event = coerce_json_dict(chunk.get("event"))
                            streamed_customer_intelligence_trace = True
                            context.side_effects.customer_intelligence_events.append(event)
                            await _publish_event(context, event)
                        elif chunk.get("kind") == "result" and isinstance(chunk.get("result"), dict):
                            result = chunk["result"]
                else:
                    result = await self.customer_intelligence_graph_service.resume_review(graph_input)
            else:
                if event_object is None:
                    return {
                        "customer_intelligence_requested": False,
                        "customer_intelligence_result": {"handled": False, "reason": "missing_event"},
                        "events": [
                            {
                                "event": "agent_root_customer_intelligence_skipped",
                                "reason": "missing_event",
                            }
                        ],
                    }
                graph_input = {
                    "team_id": context.team_id,
                    "user_id": context.user_id,
                    "session_id": context.session_id,
                    "event": event_object,
                }
                stream_run = getattr(self.customer_intelligence_graph_service, "stream_run", None)
                if callable(stream_run):
                    result = {}
                    async for chunk in stream_run(graph_input):
                        if not isinstance(chunk, dict):
                            continue
                        if chunk.get("kind") == "event":
                            event = coerce_json_dict(chunk.get("event"))
                            streamed_customer_intelligence_trace = True
                            context.side_effects.customer_intelligence_events.append(event)
                            await _publish_event(context, event)
                        elif chunk.get("kind") == "result" and isinstance(chunk.get("result"), dict):
                            result = chunk["result"]
                else:
                    result = await self.customer_intelligence_graph_service.run(graph_input)
        except Exception as exc:
            logger.exception(
                "Agent 客户智能后置刷新失败，已隔离为非阻塞后置效果: team_id=%s, session_id=%s",
                context.team_id,
                context.session_id,
            )
            failed_event = {
                "event": "agent_root_customer_intelligence_graph_failed",
                "reason": str(exc),
            }
            context.side_effects.customer_intelligence_events.append(failed_event)
            await _publish_event(context, failed_event)
            return {
                "customer_intelligence_requested": False,
                "customer_intelligence_result": {
                    "handled": False,
                    "reason": "customer_intelligence_graph_failed",
                },
                "events": [failed_event],
            }

        projected_result = _customer_intelligence_result_projection(result)
        output_events = _unstreamed_customer_intelligence_output_events(
            result,
            streamed_trace_events=streamed_customer_intelligence_trace,
        )
        await _publish_events(context, output_events)
        context.side_effects.customer_intelligence_events.extend(output_events)
        context.side_effects.customer_intelligence_result = result
        assistant_content = _customer_intelligence_assistant_content(result)
        if assistant_content:
            context.side_effects.customer_intelligence_assistant_content = assistant_content
        current_interrupt = _customer_intelligence_interrupt_from_result(result)
        if current_interrupt:
            context.side_effects.current_interrupt = current_interrupt

        update: AgentRuntimeState = {
            "customer_intelligence_requested": False,
            "customer_intelligence_event": coerce_json_dict(result.get("event")),
            "customer_intelligence_result": projected_result,
            "current_interrupt": current_interrupt,
            "events": [
                {
                    "event": "agent_root_customer_intelligence_graph_completed",
                    "has_interrupt": bool(current_interrupt),
                    "event_count": len(output_events),
                }
            ],
        }
        if assistant_content:
            update["assistant_content"] = assistant_content
        return update

    def _route_after_customer_intelligence_graph(self, state: AgentRuntimeState) -> str:
        if state.get("current_interrupt"):
            return "generated_interrupt_wait"
        return "finish"

    async def _run_new_flow_graph(
        self,
        state: AgentRuntimeState,
        runtime: Runtime[AgentRuntimeContext],
    ) -> AgentRuntimeState:
        context = runtime.context
        new_flow_branch_event = _step_event(
            "new_flow_branch",
            "started",
            "处理新的业务输入",
        )
        context.side_effects.new_flow_events.append(new_flow_branch_event)
        await _publish_event(context, new_flow_branch_event)
        if not context.db or not context.session:
            return {
                "events": [
                    {
                        "event": "agent_root_new_flow_unavailable",
                        "reason": "missing_runtime_context",
                    }
                ],
            }

        switch_notice = state.get("switch_notice")
        assistant_content = state.get("assistant_content")
        side_effect_context = NewFlowSideEffectContext(
            db=context.db,
            session=context.session,
            team_id=context.team_id,
            user_id=context.user_id,
            switch_notice=switch_notice if isinstance(switch_notice, str) else context.switch_notice,
            assistant_content=assistant_content if isinstance(assistant_content, str) else None,
        )
        session_context = getattr(context.session, "context_json", None)
        if not isinstance(session_context, dict):
            session_context = {}
        graph_input = {
            "db": context.db,
            "team_id": context.team_id,
            "user_id": context.user_id,
            "session_id": context.session_id,
            "session_context": session_context,
            "content": context.content,
            "authorization": context.authorization or "",
        }
        event_count = 0
        review_event_count = 0
        deferred_final_events: list[JSONDict] = []
        stream_events = getattr(self.new_flow_graph_service, "stream_events", None)
        if callable(stream_events):
            async for event in stream_events(graph_input):
                processed_event = await self.new_flow_side_effect_handler.apply_async(
                    coerce_json_dict(event),
                    side_effect_context,
                )
                review_event_count = await self._publish_new_review_events(
                    context,
                    side_effect_context,
                    review_event_count,
                )
                if processed_event.get("event") == "final":
                    deferred_final_events.append(processed_event)
                elif _should_emit_new_flow_event(processed_event, side_effect_context):
                    context.side_effects.new_flow_events.append(processed_event)
                    await _publish_event(context, processed_event)
                    event_count += 1
        elif isinstance(self.new_flow_graph_service, NewFlowGraphRunner):
            result = await self.new_flow_graph_service.run(graph_input)
            for event in result.get("events", []):
                processed_event = await self.new_flow_side_effect_handler.apply_async(
                    coerce_json_dict(event),
                    side_effect_context,
                )
                review_event_count = await self._publish_new_review_events(
                    context,
                    side_effect_context,
                    review_event_count,
                )
                if processed_event.get("event") == "final":
                    deferred_final_events.append(processed_event)
                elif _should_emit_new_flow_event(processed_event, side_effect_context):
                    context.side_effects.new_flow_events.append(processed_event)
                    await _publish_event(context, processed_event)
                    event_count += 1

        auto_execute_result = await self._run_new_flow_auto_execute_tasks(
            context,
            side_effect_context,
        )
        customer_intelligence_event = self._customer_intelligence_event_from_new_flow(
            context,
            side_effect_context,
        )

        assistant_content = auto_execute_result.get("assistant_content") or side_effect_context.assistant_content
        current_interrupt = auto_execute_result.get("current_interrupt") or side_effect_context.current_interrupt
        post_write_effects = merge_post_write_effects(
            state.get("post_write_effects"),
            auto_execute_result,
            context.side_effects.new_flow_events,
        )
        publish_deferred_final = _should_publish_deferred_new_flow_final(
            deferred_final_events,
            customer_intelligence_requested=customer_intelligence_event is not None,
            current_interrupt=current_interrupt,
            context=side_effect_context,
        )
        defer_final_for_business_arbitration = _should_defer_new_flow_final_for_business_arbitration(
            deferred_final_events,
            customer_intelligence_requested=customer_intelligence_event is not None,
            current_interrupt=current_interrupt,
            context=side_effect_context,
        )
        if publish_deferred_final:
            for final_event in deferred_final_events:
                context.side_effects.new_flow_events.append(final_event)
                await _publish_event(context, final_event)
                event_count += 1
        deferred_final_projection = deferred_final_events if defer_final_for_business_arbitration else []
        if deferred_final_projection:
            # Keep the graph-result event count stable even though publication is
            # postponed until the root interaction planner has selected a target.
            event_count += len(deferred_final_projection)
        if current_interrupt:
            context.side_effects.current_interrupt = current_interrupt
        if isinstance(assistant_content, str):
            context.side_effects.new_flow_assistant_content = assistant_content
            update: AgentRuntimeState = {
                "assistant_content": assistant_content,
                "current_interrupt": current_interrupt,
                "customer_intelligence_requested": customer_intelligence_event is not None,
                "post_write_effects": post_write_effects,
                "deferred_final_events": deferred_final_projection,
                "new_flow_result": _new_flow_result_projection(
                    event_count=event_count,
                    assistant_content=assistant_content,
                    current_interrupt=current_interrupt,
                ),
                "events": [
                    {
                        "event": "agent_root_new_flow_graph_completed",
                        "event_count": event_count,
                        "has_assistant_content": True,
                        "has_interrupt": bool(current_interrupt),
                    }
                ],
            }
            if current_interrupt:
                update["task_projection"] = _interrupt_task_projection(current_interrupt)
            return update
        update = {
            "current_interrupt": current_interrupt,
            "customer_intelligence_requested": customer_intelligence_event is not None,
            "post_write_effects": post_write_effects,
            "deferred_final_events": deferred_final_projection,
            "new_flow_result": _new_flow_result_projection(
                event_count=event_count,
                assistant_content=None,
                current_interrupt=current_interrupt,
            ),
            "events": [
                {
                    "event": "agent_root_new_flow_graph_completed",
                    "event_count": event_count,
                    "has_assistant_content": False,
                    "has_interrupt": bool(current_interrupt),
                }
            ],
        }
        if current_interrupt:
            update["task_projection"] = _interrupt_task_projection(current_interrupt)
        return update

    def _customer_intelligence_event_from_new_flow(
        self,
        context: AgentRuntimeContext,
        side_effect_context: NewFlowSideEffectContext,
    ) -> object | None:
        if context.customer_intelligence_event is not None or context.user_message_id is None:
            return context.customer_intelligence_event
        event = self.customer_intelligence_trigger_policy.from_new_flow_events(
            context.side_effects.new_flow_events,
            turn=AgentCustomerIntelligenceTurn(
                team_id=context.team_id,
                user_id=context.user_id,
                session_id=context.session_id,
                message_id=context.user_message_id,
                content=context.content,
            ),
        )
        if event is not None:
            context.customer_intelligence_event = event
        return event

    async def _publish_new_review_events(
        self,
        context: AgentRuntimeContext,
        side_effect_context: NewFlowSideEffectContext,
        published_count: int,
    ) -> int:
        review_events = side_effect_context.review_events or []
        new_events = review_events[published_count:]
        for event in new_events:
            context.side_effects.new_flow_events.append(event)
            await _publish_event(context, event)
        return published_count + len(new_events)

    async def _run_new_flow_auto_execute_tasks(
        self,
        context: AgentRuntimeContext,
        side_effect_context: NewFlowSideEffectContext,
    ) -> JSONDict:
        tasks = side_effect_context.auto_execute_tasks or []
        plan_items = _auto_execute_plan_items(side_effect_context, tasks=tasks)
        if not plan_items:
            return {}
        assistant_content: str | None = None
        current_interrupt: AgentInterruptPayload | None = None
        emitted_event_count = 0
        post_write_effects = normalize_post_write_effects(None)
        initial_plan = action_plan.build_action_execution_plan(plan_items)
        ledger_state = _auto_execute_ledger_state(
            context,
            action_ids=_plan_action_ids_for_ledger(initial_plan),
        )
        satisfied_action_ids = set(ledger_state.get("satisfied_action_ids", []))
        running_action_ids = set(ledger_state.get("running_action_ids", []))
        terminal_action_ids = set(ledger_state.get("terminal_action_ids", []))
        executed_action_count = 0
        last_mode = "none"
        for _ in range(len(plan_items) + 1):
            plan = action_plan.build_action_execution_plan(
                plan_items,
                satisfied_action_ids=satisfied_action_ids,
                running_action_ids=running_action_ids,
                terminal_action_ids=terminal_action_ids,
            )
            plan_event = {
                "event": "agent_root_auto_execute_plan_built",
                **plan.summary(),
            }
            context.side_effects.new_flow_events.append(plan_event)
            await _publish_event(context, plan_event)
            emitted_event_count += 1
            if plan.blocked_nodes:
                _mark_auto_execute_nodes_blocked(context, plan.blocked_nodes)
            if not plan.ready_nodes:
                if plan.blocked_nodes:
                    blocked_event = {
                        "event": "agent_root_auto_execute_plan_blocked",
                        "blocked_actions": [
                            {
                                "action_id": node.action_id,
                                "action_type": node.action_type,
                                "task_id": node.task_id,
                                "reason": node.blocked_reason,
                            }
                            for node in plan.blocked_nodes
                        ],
                    }
                    context.side_effects.new_flow_events.append(blocked_event)
                    await _publish_event(context, blocked_event)
                    emitted_event_count += 1
                break
            blocked_taskless_nodes = tuple(
                node for node in plan.ready_nodes if node.task is None and not _can_direct_execute_action_node(node)
            )
            if blocked_taskless_nodes:
                blocked_taskless_nodes = _auto_execute_nodes_with_blocked_reason(
                    blocked_taskless_nodes,
                    "missing_task_projection",
                )
                _mark_auto_execute_nodes_blocked(
                    context,
                    blocked_taskless_nodes,
                )
                blocked_event = {
                    "event": "agent_root_auto_execute_plan_blocked",
                    "blocked_actions": [
                        {
                            "action_id": node.action_id,
                            "action_type": node.action_type,
                            "task_id": node.task_id,
                            "reason": node.blocked_reason,
                        }
                        for node in blocked_taskless_nodes
                    ],
                }
                context.side_effects.new_flow_events.append(blocked_event)
                await _publish_event(context, blocked_event)
                emitted_event_count += 1
                break
            ready_nodes = plan.ready_nodes
            authorization_blocked_nodes = _auto_execute_nodes_requiring_authorization(
                ready_nodes,
                authorization=context.authorization,
            )
            if authorization_blocked_nodes:
                _mark_auto_execute_nodes_blocked(context, authorization_blocked_nodes)
                terminal_action_ids.update(node.action_id for node in authorization_blocked_nodes)
                blocked_action_ids = {node.action_id for node in authorization_blocked_nodes}
                blocked_event = {
                    "event": "agent_root_auto_execute_plan_blocked",
                    "blocked_actions": [
                        {
                            "action_id": node.action_id,
                            "action_type": node.action_type,
                            "task_id": node.task_id,
                            "reason": node.blocked_reason,
                        }
                        for node in authorization_blocked_nodes
                    ],
                }
                context.side_effects.new_flow_events.append(blocked_event)
                await _publish_event(context, blocked_event)
                emitted_event_count += 1
                ready_nodes = tuple(node for node in ready_nodes if node.action_id not in blocked_action_ids)
                if not ready_nodes:
                    continue
            execution_blocked_nodes = _auto_execute_nodes_blocked_by_execution_contract(ready_nodes)
            if execution_blocked_nodes:
                _mark_auto_execute_nodes_blocked(context, execution_blocked_nodes)
                terminal_action_ids.update(node.action_id for node in execution_blocked_nodes)
                blocked_action_ids = {node.action_id for node in execution_blocked_nodes}
                blocked_event = {
                    "event": "agent_root_auto_execute_plan_blocked",
                    "blocked_actions": [
                        {
                            "action_id": node.action_id,
                            "action_type": node.action_type,
                            "task_id": node.task_id,
                            "reason": node.blocked_reason,
                        }
                        for node in execution_blocked_nodes
                    ],
                }
                context.side_effects.new_flow_events.append(blocked_event)
                await _publish_event(context, blocked_event)
                emitted_event_count += 1
                ready_nodes = tuple(node for node in ready_nodes if node.action_id not in blocked_action_ids)
                if not ready_nodes:
                    continue
            executable_nodes = _select_auto_execute_nodes_for_batch(ready_nodes)
            _mark_auto_execute_nodes_running(context, executable_nodes)
            if len(executable_nodes) > 1:
                branch = await self._run_new_flow_auto_execute_nodes_parallel(context, list(executable_nodes))
                last_mode = str(branch.get("mode") or "parallel_isolated")
            else:
                branch = await self._run_new_flow_auto_execute_node_in_context(
                    context,
                    executable_nodes[0],
                    include_graph_progress_events=not bool(context.event_sink),
                )
                context.side_effects.new_flow_events.extend(branch["events"])
                last_mode = str(branch.get("mode") or "single_in_context")
            emitted_event_count += int(branch.get("emitted_event_count") or 0)
            post_write_effects = merge_post_write_effects(post_write_effects, branch)
            self._customer_intelligence_event_from_confirmed_tool_result(context, branch.get("tool_result") or {})
            result = coerce_json_dict(branch.get("result"))
            result_content = result.get("assistant_content") or branch.get("assistant_content")
            if isinstance(result_content, str):
                assistant_content = result_content
            branch_interrupt = branch.get("current_interrupt")
            if isinstance(branch_interrupt, dict):
                current_interrupt = branch_interrupt
            successful_task_ids = {int(item) for item in branch.get("completed_task_ids", []) if isinstance(item, int)}
            if len(executable_nodes) == 1 and not successful_task_ids and _auto_execute_branch_completed(branch):
                task_id = executable_nodes[0].task_id
                if task_id is not None:
                    successful_task_ids.add(task_id)
            successful_action_ids = {
                str(item) for item in branch.get("completed_action_ids", []) if isinstance(item, str) and item
            }
            failed_action_ids = {
                str(item) for item in branch.get("failed_action_ids", []) if isinstance(item, str) and item
            }
            if (
                len(executable_nodes) == 1
                and not successful_action_ids
                and not successful_task_ids
                and _auto_execute_branch_failed(branch)
            ):
                failed_action_ids.add(executable_nodes[0].action_id)
            new_terminal_failed_action_ids = failed_action_ids - terminal_action_ids
            if new_terminal_failed_action_ids:
                terminal_action_ids.update(new_terminal_failed_action_ids)
            newly_completed = [
                node.action_id
                for node in executable_nodes
                if node.action_id in successful_action_ids or node.task_id in successful_task_ids
            ]
            if not newly_completed and not new_terminal_failed_action_ids:
                break
            satisfied_action_ids.update(newly_completed)
            executed_action_count += len(newly_completed)
            if current_interrupt:
                break
            if executed_action_count >= len(plan_items):
                break
        return coerce_json_dict(
            {
                "event": "agent_root_new_flow_auto_execution_completed",
                "mode": last_mode,
                "emitted_event_count": emitted_event_count,
                "executed_action_count": executed_action_count,
                "assistant_content": assistant_content,
                "current_interrupt": current_interrupt,
                "post_write_effects": post_write_effects,
            }
        )

    async def retry_workflow_action(
        self,
        *,
        db: object,
        action: object,
        session: object | None,
        team_id: int,
        user_id: int,
        authorization: str = "",
        retry_source: str = workflow_action_ledger.SOURCE_MANUAL_RETRY,
        reason: str | None = None,
        event_sink=None,
    ) -> object:
        """Retry one durable workflow action through the normal action planner.

        The retry endpoint should not become a second mutation path. This method
        first restores the action state in the ledger, then replays only actions
        whose original workflow policy allows automatic execution. Confirmation
        required actions stay WAITING_USER and must resume through HITL.
        """

        prepared_action = workflow_action_ledger.prepare_action_retry(
            db,
            action,
            retry_source=retry_source,
            reason=reason,
        )
        if not _workflow_action_is_auto_executable(prepared_action):
            return prepared_action
        prepared_item = action_plan.item_from_ledger_action(prepared_action)
        workflow = action_workflow.workflow_from_mapping(prepared_item.workflow if prepared_item else None)
        if session is None:
            if workflow:
                return (
                    workflow_action_ledger.mark_action_blocked(
                        db,
                        workflow=workflow,
                        team_id=team_id,
                        user_id=user_id,
                        session_id=_optional_int(getattr(prepared_action, "session_id", None)),
                        task_id=_optional_int(getattr(prepared_action, "task_id", None)),
                        source_type=workflow_action_ledger.SOURCE_MANUAL_RETRY,
                        payload=coerce_json_dict(getattr(prepared_action, "payload_json", None)),
                        target_type=_optional_str(getattr(prepared_action, "target_type", None)),
                        target_id=_optional_int(getattr(prepared_action, "target_id", None)),
                        reason="retry_blocked:missing_session_context",
                    )
                    or prepared_action
                )
            return prepared_action

        workflow_id = _optional_str(getattr(prepared_action, "workflow_id", None))
        if not workflow_id:
            return prepared_action
        workflow_actions = agent_workflow_action_crud.list_by_workflow(
            db,
            workflow_id,
            team_id=team_id,
            user_id=user_id,
            include_system_actions=True,
        )
        plan_items = _retryable_workflow_plan_items(workflow_actions)
        if not plan_items:
            return prepared_action
        side_effects = AgentRootRuntimeSideEffects()
        session_id = _optional_int(getattr(session, "id", None)) or _optional_int(
            getattr(prepared_action, "session_id", None)
        )
        context = AgentRuntimeContext(
            db=db,
            session=session,
            turn_input=AgentTurnInput(
                content="",
                source="api",
                metadata={
                    "workflow_id": workflow_id,
                    "action_id": getattr(prepared_action, "action_id", None),
                    "retry_source": retry_source,
                },
            ),
            content="",
            team_id=team_id,
            user_id=user_id,
            session_id=session_id or 0,
            authorization=authorization,
            side_effects=side_effects,
            event_sink=event_sink,
        )
        side_effect_context = NewFlowSideEffectContext(
            db=db,
            session=session,
            team_id=team_id,
            user_id=user_id,
            auto_execute_actions=plan_items,
        )
        await self._run_new_flow_auto_execute_tasks(context, side_effect_context)
        refreshed_action = agent_workflow_action_crud.get_by_workflow_action(
            db,
            workflow_id=workflow_id,
            action_id=str(getattr(prepared_action, "action_id", "")),
            team_id=team_id,
            user_id=user_id,
            include_system_actions=True,
        )
        return refreshed_action or prepared_action

    async def retry_workflow(
        self,
        *,
        db: object,
        workflow_id: str,
        actions: list[object],
        session: object | None,
        team_id: int,
        user_id: int,
        authorization: str = "",
        retry_source: str = workflow_action_ledger.SOURCE_MANUAL_RETRY,
        reason: str | None = None,
        event_sink=None,
    ) -> list[object]:
        """Recover retryable workflow actions, then replay auto actions via DAG.

        This is intentionally not a full workflow rerun. Already executed
        actions remain satisfied, HITL actions remain waiting for a resume, and
        only failed/blocked actions are moved back into recoverable states.
        """

        prepared_actions: list[object] = []
        for action in actions:
            if not _workflow_action_is_retryable(action):
                continue
            prepared_actions.append(
                workflow_action_ledger.prepare_action_retry(
                    db,
                    action,
                    retry_source=retry_source,
                    reason=reason,
                )
            )
        if not prepared_actions:
            raise ValueError("No retryable workflow actions found")

        if not any(_workflow_action_is_auto_executable(action) for action in prepared_actions):
            return agent_workflow_action_crud.list_by_workflow(
                db,
                workflow_id,
                team_id=team_id,
                user_id=user_id,
                include_system_actions=True,
            )

        auto_workflow = _first_auto_executable_workflow(prepared_actions)
        if session is None:
            if auto_workflow:
                workflow_action_ledger.mark_action_blocked(
                    db,
                    workflow=auto_workflow,
                    team_id=team_id,
                    user_id=user_id,
                    session_id=_optional_int(getattr(prepared_actions[0], "session_id", None)),
                    task_id=_optional_int(getattr(prepared_actions[0], "task_id", None)),
                    source_type=workflow_action_ledger.SOURCE_MANUAL_RETRY,
                    payload=coerce_json_dict(getattr(prepared_actions[0], "payload_json", None)),
                    target_type=_optional_str(getattr(prepared_actions[0], "target_type", None)),
                    target_id=_optional_int(getattr(prepared_actions[0], "target_id", None)),
                    reason="retry_blocked:missing_session_context",
                )
            return agent_workflow_action_crud.list_by_workflow(
                db,
                workflow_id,
                team_id=team_id,
                user_id=user_id,
                include_system_actions=True,
            )

        refreshed_actions = agent_workflow_action_crud.list_by_workflow(
            db,
            workflow_id,
            team_id=team_id,
            user_id=user_id,
            include_system_actions=True,
        )
        plan_items = _retryable_workflow_plan_items(refreshed_actions)
        if plan_items:
            side_effects = AgentRootRuntimeSideEffects()
            session_id = _optional_int(getattr(session, "id", None)) or _optional_int(
                getattr(prepared_actions[0], "session_id", None)
            )
            context = AgentRuntimeContext(
                db=db,
                session=session,
                turn_input=AgentTurnInput(
                    content="",
                    source="api",
                    metadata={
                        "workflow_id": workflow_id,
                        "retry_source": retry_source,
                        "retry_scope": "workflow",
                    },
                ),
                content="",
                team_id=team_id,
                user_id=user_id,
                session_id=session_id or 0,
                authorization=authorization,
                side_effects=side_effects,
                event_sink=event_sink,
            )
            side_effect_context = NewFlowSideEffectContext(
                db=db,
                session=session,
                team_id=team_id,
                user_id=user_id,
                auto_execute_actions=plan_items,
            )
            await self._run_new_flow_auto_execute_tasks(context, side_effect_context)
        return agent_workflow_action_crud.list_by_workflow(
            db,
            workflow_id,
            team_id=team_id,
            user_id=user_id,
            include_system_actions=True,
        )

    async def _run_new_flow_auto_execute_task_in_context(
        self,
        context: AgentRuntimeContext,
        task: object,
        *,
        include_graph_progress_events: bool,
    ) -> JSONDict:
        started_event = _step_event(
            "auto_execute_task",
            "started",
            task_display.readable_execution_label(_task_action(task)) or "执行业务操作",
        )
        await _publish_event(context, started_event)
        result = await self.confirmed_task_graph_service.run(
            {
                "db": context.db,
                "session": context.session,
                "task": task,
                "team_id": context.team_id,
                "user_id": context.user_id,
                "session_id": context.session_id,
                "authorization": context.authorization or "",
                "channel": context.turn_input.source if context.turn_input else "web",
                "provider": context.turn_input.provider if context.turn_input else None,
                "events": [],
                "event_sink": context.event_sink,
            }
        )
        output_events = execution_trace.confirmed_task_execution_events(
            task=task,
            graph_events=result.get("events", []),
            output_events=result.get("output_events", []),
            include_graph_progress_events=include_graph_progress_events,
        )
        await _publish_events(context, output_events)
        assistant_content = result.get("assistant_content")
        current_interrupt = _next_task_interrupt_from_output_events_for_context(
            output_events,
            context=context,
            assistant_content=assistant_content if isinstance(assistant_content, str) else "",
        )
        return coerce_json_dict(
            {
                "result": result,
                "tool_result": result.get("tool_result") or {},
                "post_write_effects": normalize_post_write_effects(result.get("tool_result")),
                "events": [started_event, *output_events],
                "emitted_event_count": len(output_events) + 1,
                "assistant_content": assistant_content,
                "current_interrupt": current_interrupt,
            }
        )

    async def _run_new_flow_auto_execute_node_in_context(
        self,
        context: AgentRuntimeContext,
        node: action_plan.ActionPlanNode,
        *,
        include_graph_progress_events: bool,
    ) -> JSONDict:
        if node.task is not None:
            branch = await self._run_new_flow_auto_execute_task_in_context(
                context,
                node.task,
                include_graph_progress_events=include_graph_progress_events,
            )
            if _auto_execute_branch_completed(branch):
                branch.setdefault("completed_action_ids", [node.action_id])
            return coerce_json_dict(branch)
        return await self._run_new_flow_auto_execute_action_in_context(context, node)

    async def _run_new_flow_auto_execute_action_in_context(
        self,
        context: AgentRuntimeContext,
        node: action_plan.ActionPlanNode,
    ) -> JSONDict:
        envelope = task_execution.execution_envelope_from_plan_node(node)
        started_event = _step_event(
            "auto_execute_action",
            "started",
            task_display.readable_execution_label(envelope.action_type) or "执行业务操作",
        )
        await _publish_event(context, started_event)
        execution = await task_execution.execute_action_envelope(
            context.db,
            envelope,
            session=context.session,
            team_id=context.team_id,
            user_id=context.user_id,
            authorization=context.authorization or "",
            event_sink=context.event_sink,
        )
        tool_result = execution.tool_result
        tool_event = coerce_json_dict(tool_result.to_event()) if tool_result else {}
        output_events: list[JSONDict] = [started_event, *execution.progress_events]
        if tool_event:
            output_events.append(tool_event)
        if tool_result and tool_result.success:
            assistant_content = _direct_action_success_content(envelope.action_type)
            workflow_action_ledger.mark_action_executed(
                context.db,
                workflow=envelope.workflow,
                team_id=context.team_id,
                user_id=context.user_id,
                result=tool_result.data if isinstance(tool_result.data, dict) else {"data": tool_result.data},
                task_id=None,
            )
            output_events.append(
                {
                    "event": "action_completed",
                    "action_id": envelope.action_id,
                    "action_type": envelope.action_type,
                }
            )
            await _publish_events(context, output_events[1:])
            return coerce_json_dict(
                {
                    "result": {"execution_status": "completed", "assistant_content": assistant_content},
                    "tool_result": tool_event,
                    "post_write_effects": normalize_post_write_effects(tool_event),
                    "events": output_events,
                    "emitted_event_count": len(output_events),
                    "assistant_content": assistant_content,
                    "completed_action_ids": [node.action_id],
                    "mode": "single_action_in_context",
                }
            )
        error_message = tool_result.error_message if tool_result else f"暂不支持的执行动作：{envelope.action_type}"
        workflow_action_ledger.mark_action_failed(
            context.db,
            workflow=envelope.workflow,
            team_id=context.team_id,
            user_id=context.user_id,
            task_id=None,
            error_message=error_message,
            result=tool_event or {"success": False, "error": error_message},
        )
        output_events.append(
            {
                "event": "action_failed",
                "action_id": envelope.action_id,
                "action_type": envelope.action_type,
                "reason": error_message,
            }
        )
        await _publish_events(context, output_events[1:])
        return coerce_json_dict(
            {
                "result": {"execution_status": "failed", "assistant_content": f"执行失败：{error_message}"},
                "tool_result": tool_event,
                "post_write_effects": normalize_post_write_effects(tool_event),
                "events": output_events,
                "emitted_event_count": len(output_events),
                "assistant_content": f"执行失败：{error_message}",
                "failed_action_ids": [node.action_id],
                "mode": "single_action_in_context",
            }
        )

    async def _run_new_flow_auto_execute_tasks_parallel(
        self,
        context: AgentRuntimeContext,
        tasks: list[object],
    ) -> JSONDict:
        branch_inputs = [
            _auto_execute_branch_input(
                task,
                session_id=context.session_id,
                team_id=context.team_id,
                user_id=context.user_id,
                authorization=context.authorization or "",
                channel=context.turn_input.source if context.turn_input else "web",
                provider=context.turn_input.provider if context.turn_input else None,
            )
            for task in tasks
        ]
        if any(item is None for item in branch_inputs):
            assistant_content: str | None = None
            current_interrupt: AgentInterruptPayload | None = None
            emitted_event_count = 0
            completed_task_ids: list[int] = []
            for task in tasks:
                branch = await self._run_new_flow_auto_execute_task_in_context(
                    context,
                    task,
                    include_graph_progress_events=not bool(context.event_sink),
                )
                context.side_effects.new_flow_events.extend(branch["events"])
                emitted_event_count += int(branch.get("emitted_event_count") or 0)
                self._customer_intelligence_event_from_confirmed_tool_result(context, branch.get("tool_result") or {})
                if isinstance(branch.get("assistant_content"), str):
                    assistant_content = branch["assistant_content"]
                branch_interrupt = branch.get("current_interrupt")
                if isinstance(branch_interrupt, dict):
                    current_interrupt = branch_interrupt
                task_id = _optional_int(getattr(task, "id", None))
                if task_id is not None and _auto_execute_branch_completed(branch):
                    completed_task_ids.append(task_id)
            return coerce_json_dict(
                {
                    "event": "agent_root_new_flow_auto_execution_completed",
                    "mode": "serial_fallback",
                    "emitted_event_count": emitted_event_count,
                    "completed_task_ids": completed_task_ids,
                    "assistant_content": assistant_content,
                    "current_interrupt": current_interrupt,
                }
            )

        started_event = _step_event("auto_execute_tasks_parallel", "started", f"并行执行 {len(tasks)} 个低风险业务操作")
        context.side_effects.new_flow_events.append(started_event)
        await _publish_event(context, started_event)
        branch_results = await asyncio.gather(
            *[
                self._run_new_flow_auto_execute_task_isolated(coerce_json_dict(item))
                for item in branch_inputs
                if item is not None
            ],
            return_exceptions=True,
        )
        assistant_content: str | None = None
        current_interrupt: AgentInterruptPayload | None = None
        post_write_effects = normalize_post_write_effects(None)
        emitted_event_count = 1
        completed_task_ids: list[int] = []
        failed_task_ids: list[int] = []
        for branch_input, branch_result in zip(branch_inputs, branch_results, strict=False):
            branch_input_json = coerce_json_dict(branch_input)
            task_id = _optional_int(branch_input_json.get("task_id"))
            if isinstance(branch_result, Exception):
                event = {
                    "event": "agent_root_auto_execute_branch_failed",
                    "task_id": task_id,
                    "reason": str(branch_result),
                }
                if task_id is not None:
                    failed_task_ids.append(task_id)
                context.side_effects.new_flow_events.append(event)
                await _publish_event(context, event)
                emitted_event_count += 1
                continue
            branch = coerce_json_dict(branch_result)
            post_write_effects = merge_post_write_effects(post_write_effects, branch)
            events = [event for event in branch.get("events", []) if isinstance(event, dict)]
            context.side_effects.new_flow_events.extend(events)
            await _publish_events(context, events)
            emitted_event_count += int(branch.get("emitted_event_count") or len(events))
            self._customer_intelligence_event_from_confirmed_tool_result(context, branch.get("tool_result") or {})
            if task_id is not None and _auto_execute_branch_completed(branch):
                completed_task_ids.append(task_id)
            elif task_id is not None:
                failed_task_ids.append(task_id)
                event = {
                    "event": "agent_root_auto_execute_branch_incomplete",
                    "task_id": task_id,
                    "reason": "missing_success_signal",
                }
                context.side_effects.new_flow_events.append(event)
                await _publish_event(context, event)
                emitted_event_count += 1
            if isinstance(branch.get("assistant_content"), str):
                assistant_content = branch["assistant_content"]
            branch_interrupt = branch.get("current_interrupt")
            if isinstance(branch_interrupt, dict):
                current_interrupt = branch_interrupt
        completed_event = _step_event(
            "auto_execute_tasks_parallel", "completed", f"并行执行完成 {len(tasks)} 个低风险业务操作"
        )
        context.side_effects.new_flow_events.append(completed_event)
        await _publish_event(context, completed_event)
        emitted_event_count += 1
        return coerce_json_dict(
            {
                "event": "agent_root_new_flow_auto_execution_completed",
                "mode": "parallel_isolated",
                "emitted_event_count": emitted_event_count,
                "completed_task_ids": completed_task_ids,
                "failed_task_ids": failed_task_ids,
                "assistant_content": assistant_content,
                "current_interrupt": current_interrupt,
                "post_write_effects": post_write_effects,
            }
        )

    async def _run_new_flow_auto_execute_nodes_parallel(
        self,
        context: AgentRuntimeContext,
        nodes: list[action_plan.ActionPlanNode],
    ) -> JSONDict:
        if all(node.task is not None for node in nodes):
            branch = await self._run_new_flow_auto_execute_tasks_parallel(
                context,
                [node.task for node in nodes if node.task is not None],
            )
            completed_task_ids = {int(item) for item in branch.get("completed_task_ids", []) if isinstance(item, int)}
            failed_task_ids = {int(item) for item in branch.get("failed_task_ids", []) if isinstance(item, int)}
            branch["completed_action_ids"] = [node.action_id for node in nodes if node.task_id in completed_task_ids]
            branch["failed_action_ids"] = [node.action_id for node in nodes if node.task_id in failed_task_ids]
            return coerce_json_dict(branch)

        branch_inputs = [
            _auto_execute_node_branch_input(
                node,
                session_id=context.session_id,
                team_id=context.team_id,
                user_id=context.user_id,
                authorization=context.authorization or "",
                channel=context.turn_input.source if context.turn_input else "web",
                provider=context.turn_input.provider if context.turn_input else None,
            )
            for node in nodes
        ]
        if any(item is None for item in branch_inputs):
            assistant_content: str | None = None
            current_interrupt: AgentInterruptPayload | None = None
            emitted_event_count = 0
            completed_action_ids: list[str] = []
            for node in nodes:
                branch = await self._run_new_flow_auto_execute_node_in_context(
                    context,
                    node,
                    include_graph_progress_events=not bool(context.event_sink),
                )
                context.side_effects.new_flow_events.extend(branch["events"])
                emitted_event_count += int(branch.get("emitted_event_count") or 0)
                self._customer_intelligence_event_from_confirmed_tool_result(context, branch.get("tool_result") or {})
                if isinstance(branch.get("assistant_content"), str):
                    assistant_content = branch["assistant_content"]
                branch_interrupt = branch.get("current_interrupt")
                if isinstance(branch_interrupt, dict):
                    current_interrupt = branch_interrupt
                completed_action_ids.extend(
                    [item for item in branch.get("completed_action_ids", []) if isinstance(item, str)]
                )
                if current_interrupt:
                    break
            return coerce_json_dict(
                {
                    "event": "agent_root_new_flow_auto_execution_completed",
                    "mode": "serial_node_fallback",
                    "emitted_event_count": emitted_event_count,
                    "completed_action_ids": completed_action_ids,
                    "assistant_content": assistant_content,
                    "current_interrupt": current_interrupt,
                }
            )

        started_event = _step_event(
            "auto_execute_actions_parallel", "started", f"并行执行 {len(nodes)} 个低风险业务动作"
        )
        context.side_effects.new_flow_events.append(started_event)
        await _publish_event(context, started_event)
        branch_results = await asyncio.gather(
            *[
                self._run_new_flow_auto_execute_node_isolated(coerce_json_dict(item))
                for item in branch_inputs
                if item is not None
            ],
            return_exceptions=True,
        )
        assistant_content: str | None = None
        current_interrupt: AgentInterruptPayload | None = None
        post_write_effects = normalize_post_write_effects(None)
        emitted_event_count = 1
        completed_action_ids: list[str] = []
        completed_task_ids: list[int] = []
        failed_action_ids: list[str] = []
        failed_task_ids: list[int] = []
        nodes_by_action_id = {node.action_id: node for node in nodes}
        for branch_input, branch_result in zip(branch_inputs, branch_results, strict=False):
            branch_input_json = coerce_json_dict(branch_input)
            action_id = _optional_str(branch_input_json.get("action_id"))
            task_id = _optional_int(branch_input_json.get("task_id"))
            if isinstance(branch_result, Exception):
                if action_id:
                    failed_action_ids.append(action_id)
                    node = nodes_by_action_id.get(action_id)
                    if node is not None:
                        _mark_auto_execute_node_failed(context, node, str(branch_result))
                if task_id is not None:
                    failed_task_ids.append(task_id)
                event = {
                    "event": "agent_root_auto_execute_branch_failed",
                    "task_id": task_id,
                    "action_id": action_id,
                    "reason": str(branch_result),
                }
                context.side_effects.new_flow_events.append(event)
                await _publish_event(context, event)
                emitted_event_count += 1
                continue
            branch = coerce_json_dict(branch_result)
            post_write_effects = merge_post_write_effects(post_write_effects, branch)
            events = [event for event in branch.get("events", []) if isinstance(event, dict)]
            context.side_effects.new_flow_events.extend(events)
            await _publish_events(context, events)
            emitted_event_count += int(branch.get("emitted_event_count") or len(events))
            self._customer_intelligence_event_from_confirmed_tool_result(context, branch.get("tool_result") or {})
            completed_action_ids.extend(
                [item for item in branch.get("completed_action_ids", []) if isinstance(item, str)]
            )
            completed_task_ids.extend([item for item in branch.get("completed_task_ids", []) if isinstance(item, int)])
            failed_action_ids.extend([item for item in branch.get("failed_action_ids", []) if isinstance(item, str)])
            failed_task_ids.extend([item for item in branch.get("failed_task_ids", []) if isinstance(item, int)])
            if isinstance(branch.get("assistant_content"), str):
                assistant_content = branch["assistant_content"]
            branch_interrupt = branch.get("current_interrupt")
            if isinstance(branch_interrupt, dict):
                current_interrupt = branch_interrupt
        completed_event = _step_event(
            "auto_execute_actions_parallel", "completed", f"并行执行完成 {len(nodes)} 个低风险业务动作"
        )
        context.side_effects.new_flow_events.append(completed_event)
        await _publish_event(context, completed_event)
        emitted_event_count += 1
        return coerce_json_dict(
            {
                "event": "agent_root_new_flow_auto_execution_completed",
                "mode": "parallel_isolated",
                "emitted_event_count": emitted_event_count,
                "completed_action_ids": completed_action_ids,
                "completed_task_ids": completed_task_ids,
                "failed_action_ids": failed_action_ids,
                "failed_task_ids": failed_task_ids,
                "assistant_content": assistant_content,
                "current_interrupt": current_interrupt,
                "post_write_effects": post_write_effects,
            }
        )

    async def _run_new_flow_auto_execute_node_isolated(self, branch_input: JSONDict) -> JSONDict:
        if branch_input.get("node_kind") == "task":
            branch = await self._run_new_flow_auto_execute_task_isolated(branch_input)
            action_id = _optional_str(branch_input.get("action_id"))
            if action_id and _auto_execute_branch_completed(branch):
                branch["completed_action_ids"] = [action_id]
            return coerce_json_dict(branch)
        return await self._run_new_flow_auto_execute_action_isolated(branch_input)

    async def _run_new_flow_auto_execute_action_isolated(self, branch_input: JSONDict) -> JSONDict:
        session_id = _optional_int(branch_input.get("session_id"))
        if session_id is None:
            raise ValueError("auto execute action branch requires session_id")
        db = SessionLocal()
        try:
            session = agent_session_crud.get_by_id(
                db,
                session_id,
                team_id=int(branch_input["team_id"]),
                user_id=int(branch_input["user_id"]),
            )
            if session is None:
                raise ValueError("auto execute action branch could not reload session")
            envelope = task_execution.ActionExecutionEnvelope(
                action_id=str(branch_input["action_id"]),
                action_type=str(branch_input["action_type"]),
                workflow=coerce_json_dict(branch_input.get("workflow")),
                payload=coerce_json_dict(branch_input.get("payload")),
                customer=coerce_json_dict(branch_input.get("customer")),
                task_key=_optional_str(branch_input.get("task_key")),
                session_id=session_id,
                target_type=_optional_str(branch_input.get("target_type")),
                target_id=_optional_int(branch_input.get("target_id")),
            )
            execution = await task_execution.execute_action_envelope(
                db,
                envelope,
                session=session,
                team_id=int(branch_input["team_id"]),
                user_id=int(branch_input["user_id"]),
                authorization=str(branch_input.get("authorization") or ""),
                event_sink=None,
            )
            tool_result = execution.tool_result
            tool_event = coerce_json_dict(tool_result.to_event()) if tool_result else {}
            started_event = _step_event(
                "auto_execute_action",
                "started",
                task_display.readable_execution_label(envelope.action_type) or "执行业务操作",
            )
            events = [started_event, *execution.progress_events]
            if tool_event:
                events.append(tool_event)
            if tool_result and tool_result.success:
                assistant_content = _direct_action_success_content(envelope.action_type)
                workflow_action_ledger.mark_action_executed(
                    db,
                    workflow=envelope.workflow,
                    team_id=int(branch_input["team_id"]),
                    user_id=int(branch_input["user_id"]),
                    result=tool_result.data if isinstance(tool_result.data, dict) else {"data": tool_result.data},
                    task_id=None,
                )
                events.append(
                    {
                        "event": "action_completed",
                        "action_id": envelope.action_id,
                        "action_type": envelope.action_type,
                    }
                )
                return coerce_json_dict(
                    {
                        "result": {"execution_status": "completed", "assistant_content": assistant_content},
                        "tool_result": tool_event,
                        "post_write_effects": normalize_post_write_effects(tool_event),
                        "events": events,
                        "emitted_event_count": len(events),
                        "assistant_content": assistant_content,
                        "completed_action_ids": [envelope.action_id],
                    }
                )
            error_message = tool_result.error_message if tool_result else f"暂不支持的执行动作：{envelope.action_type}"
            workflow_action_ledger.mark_action_failed(
                db,
                workflow=envelope.workflow,
                team_id=int(branch_input["team_id"]),
                user_id=int(branch_input["user_id"]),
                task_id=None,
                error_message=error_message,
                result=tool_event or {"success": False, "error": error_message},
            )
            events.append(
                {
                    "event": "action_failed",
                    "action_id": envelope.action_id,
                    "action_type": envelope.action_type,
                    "reason": error_message,
                }
            )
            return coerce_json_dict(
                {
                    "result": {"execution_status": "failed", "assistant_content": f"执行失败：{error_message}"},
                    "tool_result": tool_event,
                    "post_write_effects": normalize_post_write_effects(tool_event),
                    "events": events,
                    "emitted_event_count": len(events),
                    "assistant_content": f"执行失败：{error_message}",
                    "failed_action_ids": [envelope.action_id],
                }
            )
        finally:
            db.close()

    async def _run_new_flow_auto_execute_task_isolated(self, branch_input: JSONDict) -> JSONDict:
        task_id = _optional_int(branch_input.get("task_id"))
        session_id = _optional_int(branch_input.get("session_id"))
        if task_id is None or session_id is None:
            raise ValueError("auto execute branch requires task_id and session_id")
        db = SessionLocal()
        task: object | None = None
        try:
            session = agent_session_crud.get_by_id(
                db,
                session_id,
                team_id=int(branch_input["team_id"]),
                user_id=int(branch_input["user_id"]),
            )
            task = agent_task_crud.get_by_id(
                db,
                task_id,
                team_id=int(branch_input["team_id"]),
                user_id=int(branch_input["user_id"]),
            )
            if session is None or task is None:
                raise ValueError("auto execute branch could not reload session/task")
            result = await self.confirmed_task_graph_service.run(
                {
                    "db": db,
                    "session": session,
                    "task": task,
                    "team_id": int(branch_input["team_id"]),
                    "user_id": int(branch_input["user_id"]),
                    "session_id": session_id,
                    "authorization": str(branch_input.get("authorization") or ""),
                    "channel": str(branch_input.get("channel") or "web"),
                    "provider": branch_input.get("provider"),
                    "events": [],
                    "event_sink": None,
                }
            )
            output_events = execution_trace.confirmed_task_execution_events(
                task=task,
                graph_events=result.get("events", []),
                output_events=result.get("output_events", []),
                include_graph_progress_events=True,
            )
            assistant_content = result.get("assistant_content")
            return coerce_json_dict(
                {
                    "result": result,
                    "tool_result": result.get("tool_result") or {},
                    "post_write_effects": normalize_post_write_effects(result.get("tool_result")),
                    "events": [
                        _step_event(
                            "auto_execute_task",
                            "started",
                            task_display.readable_execution_label(_task_action(task)) or "执行业务操作",
                        ),
                        *output_events,
                    ],
                    "emitted_event_count": len(output_events) + 1,
                    "assistant_content": assistant_content,
                    "current_interrupt": None,
                }
            )
        except Exception as exc:
            workflow = action_workflow.workflow_from_task_state(getattr(task, "state_json", None))
            if workflow:
                try:
                    workflow_action_ledger.mark_action_failed(
                        db,
                        workflow=workflow,
                        team_id=int(branch_input["team_id"]),
                        user_id=int(branch_input["user_id"]),
                        task_id=task_id,
                        error_message=str(exc),
                        result={"success": False, "error": str(exc)},
                    )
                except Exception:
                    logger.exception(
                        "Agent 并行自动执行分支失败后写入 Action Ledger 失败: task_id=%s",
                        task_id,
                    )
            raise
        finally:
            db.close()

    async def _run_confirmed_task_execution(
        self,
        state: AgentRuntimeState,
        runtime: Runtime[AgentRuntimeContext],
    ) -> AgentRuntimeState:
        context = runtime.context
        confirmed_branch_event = _step_event(
            "confirmed_task_branch",
            "started",
            "继续上一步待确认操作",
        )
        context.side_effects.confirmed_task_events.append(confirmed_branch_event)
        await _publish_event(context, confirmed_branch_event)
        if not context.db or not context.session or not context.task:
            return {
                "events": [
                    {
                        "event": "agent_root_confirmed_task_execution_unavailable",
                        "reason": "missing_runtime_context",
                    }
                ],
            }
        result = await self.confirmed_task_graph_service.run(
            {
                "db": context.db,
                "session": context.session,
                "task": context.task,
                "team_id": context.team_id,
                "user_id": context.user_id,
                "session_id": context.session_id,
                "authorization": context.authorization or "",
                "channel": context.turn_input.source if context.turn_input else "web",
                "provider": context.turn_input.provider if context.turn_input else None,
                "events": [],
                "event_sink": context.event_sink,
            }
        )
        output_events = execution_trace.confirmed_task_execution_events(
            task=context.task,
            graph_events=result.get("events", []),
            output_events=result.get("output_events", []),
            include_graph_progress_events=not bool(context.event_sink),
        )
        task_event = coerce_json_dict(result.get("task_event"))
        assistant_content = result.get("assistant_content")
        current_interrupt = _next_task_interrupt_from_output_events(
            output_events,
            runtime=runtime,
            assistant_content=assistant_content if isinstance(assistant_content, str) else "",
        )
        context.side_effects.confirmed_task_result = result
        context.side_effects.confirmed_task_events.extend(output_events)
        await _publish_events(context, output_events)
        context.side_effects.current_interrupt = current_interrupt
        customer_intelligence_event = self._customer_intelligence_event_from_confirmed_tool_result(
            context,
            result.get("tool_result") or {},
        )
        if isinstance(assistant_content, str):
            context.side_effects.confirmed_task_assistant_content = assistant_content
        update: AgentRuntimeState = {
            "assistant_content": assistant_content if isinstance(assistant_content, str) else None,
            "current_interrupt": current_interrupt,
            "customer_intelligence_requested": customer_intelligence_event is not None,
            "post_write_effects": merge_post_write_effects(
                state.get("post_write_effects"),
                result.get("tool_result"),
                output_events,
            ),
            "events": [
                {
                    "event": "agent_root_confirmed_task_subgraph_completed",
                    "emitted_event_count": len(output_events),
                    "task_event": task_event.get("event"),
                    "execution_status": result.get("execution_status"),
                    "has_next_interrupt": bool(current_interrupt),
                }
            ],
        }
        if current_interrupt:
            update["task_projection"] = _interrupt_task_projection(current_interrupt)
        return update

    def _customer_intelligence_event_from_confirmed_tool_result(
        self,
        context: AgentRuntimeContext,
        tool_result: object,
    ) -> object | None:
        if context.customer_intelligence_event is not None:
            return context.customer_intelligence_event
        try:
            event = self.customer_intelligence_trigger_policy.from_confirmed_tool_result(
                context.db,
                coerce_json_dict(tool_result),
                team_id=context.team_id,
            )
        except Exception:
            logger.exception(
                "Agent 确认任务客户智能触发失败，已隔离为非阻塞后置效果: team_id=%s, session_id=%s",
                context.team_id,
                context.session_id,
            )
            context.side_effects.customer_intelligence_events.append(
                {
                    "event": "agent_root_customer_intelligence_trigger_failed",
                    "source": "confirmed_tool_result",
                }
            )
            return None
        if event is not None:
            context.customer_intelligence_event = event
        return event

    def _route_after_confirmed_task_execution(self, state: AgentRuntimeState) -> str:
        if state.get("current_interrupt"):
            return "finish"
        if state.get("customer_intelligence_requested"):
            return "customer_intelligence_graph"
        return "finish"

    async def _reconcile_pending_business_interactions(
        self,
        state: AgentRuntimeState,
        runtime: Runtime[AgentRuntimeContext],
    ) -> AgentRuntimeState:
        context = runtime.context
        if state.get("current_interrupt"):
            return {}
        effects = normalize_post_write_effects(state.get("post_write_effects"))
        case_public_ids = effects.get("follow_up_confirmation_case_public_ids") or []
        if context is None:
            return {"post_write_effects": effects}
        if context.db is None:
            final_events = await self._publish_deferred_final_events(state, context=context)
            return {
                "post_write_effects": effects,
                "deferred_final_events": [],
                **({"assistant_content": _last_event_content(final_events)} if final_events else {}),
            }
        # Durable-inbox compensation requires a real persistence boundary. Some
        # graph-only invocations intentionally carry an opaque placeholder DB;
        # when there are no explicit post-write case ids, publish the ordinary
        # final after arbitration instead of treating the placeholder as a DB.
        if not case_public_ids and not callable(getattr(context.db, "query", None)):
            final_events = await self._publish_deferred_final_events(state, context=context)
            return {
                "post_write_effects": effects,
                "deferred_final_events": [],
                **({"assistant_content": _last_event_content(final_events)} if final_events else {}),
            }
        interaction_scope = build_agent_thread_id(
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
            session_key=state.get("session_key"),
        )
        try:
            prompt_event = await self.follow_up_confirmation_graph_service.prepare(
                db=context.db,
                team_id=context.team_id,
                user_id=context.user_id,
                case_public_ids=case_public_ids,
                interaction_scope=interaction_scope,
                include_owner_inbox_fallback=True,
            )
        except Exception as exc:
            logger.exception("Follow-up confirmation projection failed")
            rollback = getattr(context.db, "rollback", None)
            if callable(rollback):
                rollback()
            try:
                self.confirmation_channel_service.record_projection_failure_by_public_ids(
                    context.db,
                    team_id=context.team_id,
                    user_id=context.user_id,
                    case_public_ids=case_public_ids,
                    interaction_scope=interaction_scope,
                    error_message=str(exc),
                )
            except Exception:
                logger.exception("Follow-up confirmation projection failure audit could not be persisted")
            event = {
                "event": "follow_up_task_confirmation_projection_failed",
                "case_public_ids": case_public_ids,
                "reason": str(exc),
            }
            context.side_effects.business_interaction_events.append(event)
            await _publish_event(context, event)
            final_events = await self._publish_deferred_final_events(state, context=context)
            return {
                "events": [event],
                "post_write_effects": effects,
                "deferred_final_events": [],
                **({"assistant_content": _last_event_content(final_events)} if final_events else {}),
            }
        if not prompt_event:
            event = {
                "event": "follow_up_task_confirmation_projection_skipped",
                "case_public_ids": case_public_ids,
                "reason": "no_owner_scoped_pending_case",
            }
            context.side_effects.business_interaction_events.append(event)
            await _publish_event(context, event)
            final_events = await self._publish_deferred_final_events(state, context=context)
            return {
                "events": [event],
                "post_write_effects": effects,
                "deferred_final_events": [],
                **({"assistant_content": _last_event_content(final_events)} if final_events else {}),
            }
        prompt_json = coerce_json_dict(prompt_event)
        interaction_plan = self.interaction_planner.plan(
            semantic=coerce_json_dict(state.get("semantic")),
            business_context=coerce_json_dict(state.get("current_customer")),
            suggestions={},
            current_interrupt=interrupt_payload_from_json(state.get("current_interrupt")),
            pending_task_projection=coerce_json_dict(state.get("task_projection")),
            tool_capability={"follow_up_confirmation": True},
            follow_up_confirmation_candidate=prompt_json,
        )
        if interaction_plan.action != "follow_up_confirmation":
            event = {
                "event": "follow_up_task_confirmation_projection_deferred",
                "case_public_ids": case_public_ids,
                "reason": interaction_plan.reason,
            }
            context.side_effects.business_interaction_events.append(event)
            await _publish_event(context, event)
            return {"events": [event], "post_write_effects": effects, "deferred_final_events": []}
        prompt_json = interaction_plan.candidate
        interaction = coerce_json_dict(prompt_json.get("interaction"))
        waiting_event = {
            "event": FOLLOW_UP_CONFIRMATION_PROMPT_EVENT,
            "business_action": FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION,
            "payload": coerce_json_dict(interaction.get("payload")),
            "content": str(prompt_json.get("content") or ""),
        }
        current_interrupt = interrupt_from_waiting_event(waiting_event, interaction=interaction)
        context.side_effects.current_interrupt = current_interrupt
        prompt_content = prompt_json.get("content")
        return {
            "current_interrupt": current_interrupt,
            "post_write_effects": effects,
            "deferred_final_events": [],
            "assistant_content": prompt_content if isinstance(prompt_content, str) else None,
            "events": [
                {
                    "event": "agent_root_follow_up_confirmation_projected",
                    "case_public_id": prompt_json.get("case_public_id"),
                    "interaction_id": interaction.get("interaction_id"),
                }
            ],
        }

    async def _publish_deferred_final_events(
        self,
        state: AgentRuntimeState,
        *,
        context: AgentRuntimeContext,
    ) -> list[JSONDict]:
        events = [
            coerce_json_dict(event) for event in state.get("deferred_final_events", []) if isinstance(event, dict)
        ]
        for event in events:
            context.side_effects.new_flow_events.append(event)
            await _publish_event(context, event)
        return events

    def _route_after_pending_business_interactions(self, state: AgentRuntimeState) -> str:
        return "generated_interrupt_wait" if state.get("current_interrupt") else "finish"

    def _discard_unexposed_follow_up_confirmation(
        self,
        state: AgentRuntimeState,
        runtime: Runtime[AgentRuntimeContext],
    ) -> AgentRuntimeState:
        """Clear a checkpointed prompt that never became user-visible."""

        if runtime.context:
            runtime.context.side_effects.current_interrupt = None
        discard_reason = state.get("follow_up_confirmation_discard_reason")
        event_name = (
            "agent_root_follow_up_confirmation_stale_interrupt_discarded"
            if discard_reason == "stale_case"
            else "agent_root_follow_up_confirmation_projection_discarded"
        )
        return {
            "current_interrupt": None,
            "assistant_content": None,
            "follow_up_confirmation_projection_suppressed": False,
            "follow_up_confirmation_discard_reason": None,
            "events": [
                {
                    "event": event_name,
                    "reason": discard_reason,
                }
            ],
        }

    async def _resolve_follow_up_confirmation(
        self,
        state: AgentRuntimeState,
        runtime: Runtime[AgentRuntimeContext],
    ) -> AgentRuntimeState:
        context = runtime.context
        resume_payload = coerce_json_dict(state.get("resume_payload"))
        metadata = coerce_json_dict(resume_payload.get("metadata"))
        case_public_id = metadata.get("case_public_id") or metadata.get("follow_up_confirmation_case_public_id")
        reply_text = str(resume_payload.get("content") or metadata.get("selected_value") or "").strip()
        if not isinstance(case_public_id, str) or not case_public_id or not reply_text or not context.db:
            event = {
                "event": "follow_up_task_confirmation_resolution_skipped",
                "reason": "missing_case_reply_or_runtime_context",
            }
            context.side_effects.business_interaction_events.append(event)
            await _publish_event(context, event)
            return {"events": [event], "post_write_effects": {}}
        try:
            resolved_event = await self.follow_up_confirmation_graph_service.resolve(
                db=context.db,
                team_id=context.team_id,
                user_id=context.user_id,
                case_public_id=case_public_id,
                reply_text=reply_text,
            )
        except Exception as exc:
            logger.exception("Follow-up confirmation resolution failed")
            resolved_event = {
                "event": "follow_up_task_confirmation_resolution_failed",
                "case_public_id": case_public_id,
                "reason": str(exc),
                "content": "这项跟进确认暂时处理失败，请稍后在确认中心重试。",
            }
        content = resolved_event.get("content")
        next_interrupt: AgentInterruptPayload | None = None
        follow_up_prompt = resolved_event.get("assistant_follow_up_prompt")
        if isinstance(follow_up_prompt, str) and follow_up_prompt:
            case_payload = coerce_json_dict(resolved_event.get("case"))
            unresolved_reply_count = case_payload.get("unresolved_reply_count")
            retry_number = unresolved_reply_count if isinstance(unresolved_reply_count, int) else 1
            interaction_scope = (
                f"{build_agent_thread_id(team_id=context.team_id, user_id=context.user_id, session_id=context.session_id, session_key=state.get('session_key'))}"
                f":clarification:{retry_number}"
            )
            prompt_event = await self.follow_up_confirmation_graph_service.prepare(
                db=context.db,
                team_id=context.team_id,
                user_id=context.user_id,
                case_public_ids=[case_public_id],
                interaction_scope=interaction_scope,
                include_owner_inbox_fallback=False,
                prompt_override=follow_up_prompt,
                reason_code="ROOT_GRAPH_CLARIFICATION_PLANNED",
            )
            next_interaction = coerce_json_dict(prompt_event.get("interaction"))
            if next_interaction:
                waiting_event = {
                    "event": FOLLOW_UP_CONFIRMATION_PROMPT_EVENT,
                    "business_action": FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION,
                    "payload": coerce_json_dict(next_interaction.get("payload")),
                    "content": follow_up_prompt,
                }
                next_interrupt = interrupt_from_waiting_event(waiting_event, interaction=next_interaction)
                context.side_effects.current_interrupt = next_interrupt
        else:
            context.side_effects.business_interaction_events.append(resolved_event)
            if isinstance(content, str):
                context.side_effects.business_interaction_assistant_content = content
            await _publish_event(context, resolved_event)
        return {
            "assistant_content": content if isinstance(content, str) else None,
            "current_interrupt": next_interrupt,
            "post_write_effects": {},
            "events": [
                {
                    "event": "agent_root_follow_up_confirmation_resolved",
                    "case_public_id": case_public_id,
                    "needs_retry": next_interrupt is not None,
                }
            ],
        }

    async def _run_no_pending_confirmation(
        self,
        state: AgentRuntimeState,
        runtime: Runtime[AgentRuntimeContext],
    ) -> AgentRuntimeState:
        assistant_content = agent_copy.no_pending_confirmation()
        event: JSONDict = {"event": "final", "content": assistant_content}
        if runtime.context:
            runtime.context.side_effects.no_pending_confirmation_events.append(event)
            runtime.context.side_effects.no_pending_confirmation_assistant_content = assistant_content
            await _publish_event(runtime.context, event)
        return {
            "assistant_content": assistant_content,
            "events": [
                {
                    "event": "agent_root_no_pending_confirmation_completed",
                    "has_assistant_content": True,
                }
            ],
        }

    def _route_event(self, route: str, state: AgentRuntimeState) -> AgentRuntimeState:
        return {
            "route": route,
            "events": [
                {
                    "event": "agent_root_route_selected",
                    "route": route,
                    "has_interrupt": bool(state.get("current_interrupt")),
                }
            ],
        }

    def _finish_turn(self, state: AgentRuntimeState) -> AgentRuntimeState:
        return {
            "runtime_status": "checkpointed",
            "events": [{"event": "agent_root_graph_checkpointed"}],
        }


agent_root_runtime = AgentRootRuntime()


def project_turn_output(
    state: AgentRuntimeState,
    side_effects: AgentRootRuntimeSideEffects,
) -> AgentRuntimeTurnOutput:
    """Project root graph side effects into the application event stream."""

    action = state.get("application_action")
    if action == "pending_handled":
        return AgentRuntimeTurnOutput(
            events=[*side_effects.pending_task_events, *side_effects.business_interaction_events],
            assistant_content=(
                side_effects.business_interaction_assistant_content
                or side_effects.pending_task_assistant_content
                or _assistant_content_from_state(state)
            ),
            switch_notice=side_effects.pending_task_switch_notice or _switch_notice_from_state(state),
        )
    if action == "execute_confirmed_task":
        return AgentRuntimeTurnOutput(
            events=[
                *side_effects.pending_task_events,
                *side_effects.confirmed_task_events,
                *side_effects.customer_intelligence_events,
                *side_effects.business_interaction_events,
            ],
            assistant_content=(
                side_effects.business_interaction_assistant_content
                or side_effects.confirmed_task_assistant_content
                or _assistant_content_from_state(state)
            ),
            switch_notice=_switch_notice_from_state(state),
        )
    if action == "no_pending_confirmation":
        return AgentRuntimeTurnOutput(
            events=[*side_effects.no_pending_confirmation_events, *side_effects.business_interaction_events],
            assistant_content=(
                side_effects.business_interaction_assistant_content
                or side_effects.no_pending_confirmation_assistant_content
                or _assistant_content_from_state(state)
            ),
            switch_notice=_switch_notice_from_state(state),
        )
    return AgentRuntimeTurnOutput(
        events=[
            *side_effects.pending_task_events,
            *side_effects.new_flow_events,
            *side_effects.customer_intelligence_events,
            *side_effects.business_interaction_events,
        ],
        assistant_content=(
            side_effects.business_interaction_assistant_content
            or side_effects.customer_intelligence_assistant_content
            or side_effects.new_flow_assistant_content
            or _assistant_content_from_state(state)
        ),
        switch_notice=side_effects.pending_task_switch_notice or _switch_notice_from_state(state),
    )


def decide_application_action(state: AgentRuntimeState) -> AgentRuntimeApplicationAction:
    pending_result = state.get("pending_task_result") or {}
    if bool(pending_result.get("handled")):
        return "pending_handled"
    if bool(pending_result.get("has_task")) or bool(state.get("pending_task_requested")):
        confirmation_decision = coerce_json_dict(pending_result.get("confirmation_decision"))
        if confirmation_decision.get("intent") == "confirm":
            return "execute_confirmed_task"
        return "run_new_flow"
    if state.get("turn_kind") == "confirm" or _is_confirmation_text(state.get("content") or ""):
        return "no_pending_confirmation"
    return "run_new_flow"


def _last_event_content(events: list[JSONDict]) -> str | None:
    for event in reversed(events):
        content = event.get("content")
        if isinstance(content, str) and content:
            return content
    return None


def _assistant_content_from_state(state: AgentRuntimeState) -> str | None:
    assistant_content = state.get("assistant_content")
    return assistant_content if isinstance(assistant_content, str) else None


def _switch_notice_from_state(state: AgentRuntimeState) -> str | None:
    switch_notice = state.get("switch_notice")
    return switch_notice if isinstance(switch_notice, str) else None


async def _publish_event(
    context: AgentRuntimeContext,
    event: JSONDict,
) -> None:
    if context.event_sink:
        await context.event_sink(coerce_json_dict(event))


async def _publish_events(
    context: AgentRuntimeContext,
    events: list[JSONDict],
) -> None:
    for event in events:
        await _publish_event(context, event)


def _step_event(step: str, status: str, content: str) -> JSONDict:
    return {
        "event": "agent_step",
        "step": step,
        "status": status,
        "content": content,
    }


def _unstreamed_pending_effect_events(
    events: list[JSONDict],
    *,
    streamed_pending_steps: bool,
) -> list[JSONDict]:
    if not streamed_pending_steps:
        return list(events)
    return [event for event in events if event.get("event") != "agent_step"]


def _pending_task_result_projection(result: object) -> JSONDict:
    if not isinstance(result, dict):
        return {"handled": False}
    task_projection = coerce_json_dict(result.get("task_projection"))
    projection: JSONDict = {
        "handled": bool(result.get("handled")),
        "has_task": bool(result.get("has_active_task") or task_projection),
        "has_suspended_task": bool(result.get("suspended_task_id")),
        "remember_pending_task": bool(result.get("remember_pending_task")),
        "event_count": len(result.get("events", [])) if isinstance(result.get("events"), list) else 0,
    }
    assistant_content = result.get("assistant_content")
    if isinstance(assistant_content, str):
        projection["assistant_content"] = assistant_content
    switch_notice = result.get("switch_notice")
    if isinstance(switch_notice, str):
        projection["switch_notice"] = switch_notice
    clear_pending_task_id = result.get("clear_pending_task_id")
    if isinstance(clear_pending_task_id, int):
        projection["clear_pending_task_id"] = clear_pending_task_id
    confirmation_decision = _decision_projection(result.get("confirmation_decision"))
    if confirmation_decision:
        projection["confirmation_decision"] = confirmation_decision
    if task_projection:
        projection["task"] = task_projection
    suspended_task_id = result.get("suspended_task_id")
    if isinstance(suspended_task_id, int):
        projection["suspended_task"] = {"id": suspended_task_id}
    return projection


def _new_flow_result_projection(
    *,
    event_count: int,
    assistant_content: str | None,
    current_interrupt: AgentInterruptPayload | None,
) -> JSONDict:
    projection: JSONDict = {
        "handled": True,
        "event_count": event_count,
        "has_assistant_content": bool(assistant_content),
        "has_interrupt": bool(current_interrupt),
    }
    if assistant_content:
        projection["assistant_content"] = assistant_content
    if current_interrupt:
        projection["interrupt"] = current_interrupt
        task_projection_id = current_interrupt.get("task_projection_id")
        if isinstance(task_projection_id, int):
            projection["task_projection_id"] = task_projection_id
        task_projection_key = current_interrupt.get("task_projection_key")
        if isinstance(task_projection_key, str):
            projection["task_projection_key"] = task_projection_key
    return projection


def _customer_intelligence_result_projection(result: object) -> JSONDict:
    if not isinstance(result, dict):
        return {"handled": False}
    projection: JSONDict = {
        "handled": True,
        "route": str(result.get("route") or ""),
        "has_interrupt": bool(_customer_intelligence_interrupt_from_result(result)),
        "has_assistant_content": bool(_customer_intelligence_assistant_content(result)),
        "persisted_fact_count": len(result.get("persisted_customer_fact_refs", []))
        if isinstance(result.get("persisted_customer_fact_refs"), list)
        else 0,
        "event_count": len(result.get("events", [])) if isinstance(result.get("events"), list) else 0,
    }
    event = coerce_json_dict(result.get("event"))
    event_key = event.get("event_key")
    if isinstance(event_key, str):
        projection["event_key"] = event_key
    review = coerce_json_dict(result.get("customer_fact_review"))
    if review:
        projection["customer_fact_review"] = {
            "status": str(review.get("status") or ""),
            "candidate_count": len(review.get("candidates", [])) if isinstance(review.get("candidates"), list) else 0,
        }
    return projection


def _customer_intelligence_output_events(result: object) -> list[JSONDict]:
    if not isinstance(result, dict):
        return []
    events = _customer_intelligence_trace_events(result)
    assistant_content = _customer_intelligence_assistant_content(result)
    if assistant_content:
        events.append(
            {
                "event": "final",
                "content": assistant_content,
                "content_format": _customer_intelligence_content_format(result),
            }
        )
    return events


def _unstreamed_customer_intelligence_output_events(
    result: object,
    *,
    streamed_trace_events: bool,
) -> list[JSONDict]:
    events = _customer_intelligence_output_events(result)
    if not streamed_trace_events:
        return events
    return [event for event in events if event.get("event") != "agent_step"]


def _customer_intelligence_trace_events(result: object) -> list[JSONDict]:
    return visible_trace_events(result)


def _customer_intelligence_assistant_content(result: object) -> str | None:
    if not isinstance(result, dict):
        return None
    interrupt_payload = _customer_intelligence_interrupt_from_result(result)
    if interrupt_payload:
        return _interrupt_assistant_content(interrupt_payload)
    route = result.get("route")
    if route == "answer_context":
        answer = coerce_json_dict(result.get("customer_context_answer")).get("answer")
        if isinstance(answer, str) and answer.strip():
            return answer.strip()
        assistant_content = result.get("assistant_content")
        if isinstance(assistant_content, str) and assistant_content.strip():
            return assistant_content.strip()
        return agent_copy.customer_context_answer_unavailable()
    persisted_refs = result.get("persisted_customer_fact_refs")
    if isinstance(persisted_refs, list) and persisted_refs:
        return f"客户智能档案已更新，沉淀了 {len(persisted_refs)} 条客户事实。"
    review = coerce_json_dict(result.get("customer_fact_review"))
    if review.get("status") == "resolved":
        action = review.get("resume_action")
        if action == "approve":
            return "已按确认更新客户智能档案。"
        return "已跳过本次客户事实沉淀。"
    return None


def _customer_intelligence_content_format(result: object) -> str:
    if not isinstance(result, dict):
        return "text"
    return "markdown" if result.get("route") == "answer_context" else "text"


def _customer_intelligence_interrupt_from_result(result: object) -> AgentInterruptPayload | None:
    if not isinstance(result, dict):
        return None
    interrupt_items = result.get("__interrupt__")
    if isinstance(interrupt_items, list):
        for item in interrupt_items:
            payload = interrupt_payload_from_json(getattr(item, "value", item))
            if payload:
                runtime_events = _customer_intelligence_trace_events(result)
                if runtime_events:
                    payload["runtime_events"] = runtime_events
                return payload
    review = interrupt_payload_from_json(result.get("customer_fact_review"))
    if review and review.get("status") == "required":
        return review
    return None


def _is_customer_intelligence_resume(resume_payload: object) -> bool:
    payload = coerce_json_dict(resume_payload)
    return payload.get("business_action") == "review_customer_facts"


def _customer_intelligence_event_key_from_state(state: AgentRuntimeState) -> str | None:
    event = coerce_json_dict(state.get("customer_intelligence_event"))
    event_key = event.get("event_key")
    if isinstance(event_key, str) and event_key:
        return event_key
    result = coerce_json_dict(state.get("customer_intelligence_result"))
    event_key = result.get("event_key")
    return event_key if isinstance(event_key, str) and event_key else None


def _customer_intelligence_trigger_type(event: object | None) -> str:
    if event is None:
        return ""
    trigger_type = getattr(event, "trigger_type", None)
    if isinstance(trigger_type, str):
        return trigger_type
    event_dict = coerce_json_dict(event)
    trigger_type = event_dict.get("trigger_type")
    return trigger_type if isinstance(trigger_type, str) else ""


def _customer_intelligence_event_key(event: object | None) -> str | None:
    if event is None:
        return None
    event_key = getattr(event, "event_key", None)
    if isinstance(event_key, str) and event_key:
        return event_key
    event_dict = coerce_json_dict(event)
    event_key = event_dict.get("event_key")
    return event_key if isinstance(event_key, str) and event_key else None


def _customer_intelligence_customer_id(event: object | None) -> int | None:
    if event is None:
        return None
    customer_id = getattr(event, "customer_id", None)
    if isinstance(customer_id, int):
        return customer_id
    event_dict = coerce_json_dict(event)
    customer_id = event_dict.get("customer_id")
    return customer_id if isinstance(customer_id, int) else None


def _customer_intelligence_event_projection(event: object | None) -> JSONDict:
    if event is None:
        return {}
    to_dict = getattr(event, "to_dict", None)
    if callable(to_dict):
        return coerce_json_dict(to_dict())
    event_dict = coerce_json_dict(event)
    if event_dict:
        return event_dict
    projection: JSONDict = {}
    event_key = _customer_intelligence_event_key(event)
    trigger_type = _customer_intelligence_trigger_type(event)
    customer_id = _customer_intelligence_customer_id(event)
    if event_key:
        projection["event_key"] = event_key
    if trigger_type:
        projection["trigger_type"] = trigger_type
    if customer_id is not None:
        projection["customer_id"] = customer_id
    return projection


def _task_projection(task: object) -> JSONDict:
    projection: JSONDict = {}
    for key in ("id", "task_key", "status", "intent", "target_type", "target_id"):
        value = getattr(task, key, None)
        if value is not None:
            projection[key] = coerce_json_value(value)
    return projection


def _align_context_task_to_interrupt(
    context: AgentRuntimeContext,
    interrupt_payload: AgentInterruptPayload,
) -> None:
    task_id = _interrupt_task_projection_id(interrupt_payload)
    if task_id is None or not context.db:
        return
    current_task_id = getattr(context.task, "id", None)
    if current_task_id == task_id:
        return
    checkpoint_task = agent_task_crud.get_by_id(
        context.db,
        task_id,
        team_id=context.team_id,
        user_id=context.user_id,
    )
    if checkpoint_task:
        context.task = checkpoint_task


def _turn_start_state(
    *,
    turn_input: AgentTurnInput,
    content: str,
    team_id: int,
    user_id: int,
    session_id: int,
    session_key: str,
    current_interrupt: AgentInterruptPayload | None,
    suspended_candidates: list[JSONDict],
    current_customer: JSONDict,
    context: AgentRuntimeContext,
) -> AgentRuntimeState:
    task_projection = _task_projection(context.task) if context.task else {}
    return {
        "team_id": team_id,
        "user_id": user_id,
        "session_id": session_id,
        "session_key": session_key,
        "channel": turn_input.source,
        "content": content,
        "turn_kind": turn_input.kind.value,
        "current_interrupt": current_interrupt,
        "task_projection": task_projection,
        "suspended_candidates": suspended_candidates,
        "pending_task_requested": current_interrupt is not None or bool(suspended_candidates),
        "customer_intelligence_requested": context.customer_intelligence_event is not None,
        "current_customer": current_customer,
    }


def _decision_projection(decision: object) -> JSONDict:
    if decision is None:
        return {}
    model_dump = getattr(decision, "model_dump", None)
    if callable(model_dump):
        return coerce_json_dict(model_dump())
    if isinstance(decision, dict):
        return coerce_json_dict(decision)
    return {}


def _pending_task_id_from_state(state: AgentRuntimeState) -> int | None:
    resume_task_id = _resume_task_projection_id(state.get("resume_payload"))
    if resume_task_id is not None:
        return resume_task_id
    task_projection = coerce_json_dict(state.get("task_projection"))
    value = task_projection.get("id")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _should_emit_new_flow_event(event: JSONDict, context: NewFlowSideEffectContext) -> bool:
    if event.get("event") != "final":
        return True
    return not (context.auto_execute_tasks or context.auto_execute_actions)


def _should_publish_deferred_new_flow_final(
    events: list[JSONDict],
    *,
    customer_intelligence_requested: bool,
    current_interrupt: AgentInterruptPayload | None,
    context: NewFlowSideEffectContext,
) -> bool:
    if not events or not _should_emit_new_flow_event({"event": "final"}, context):
        return False
    # A final that expresses the already-selected interrupt may be emitted now.
    # Ordinary finals are held until durable business-interaction arbitration.
    return bool(current_interrupt) and not customer_intelligence_requested


def _should_defer_new_flow_final_for_business_arbitration(
    events: list[JSONDict],
    *,
    customer_intelligence_requested: bool,
    current_interrupt: AgentInterruptPayload | None,
    context: NewFlowSideEffectContext,
) -> bool:
    if not events or not _should_emit_new_flow_event({"event": "final"}, context):
        return False
    return not customer_intelligence_requested and current_interrupt is None


def _task_action(task: object) -> str | None:
    state_json = getattr(task, "state_json", None)
    state = coerce_json_dict(state_json)
    action = state.get("action")
    return action if isinstance(action, str) else None


def _plan_action_ids_for_ledger(plan: action_plan.ActionExecutionPlan) -> list[str]:
    action_ids: set[str] = set()
    for node in plan.nodes:
        if node.action_id:
            action_ids.add(node.action_id)
        action_ids.update(node.depends_on)
    return sorted(action_ids)


def _auto_execute_ledger_state(
    context: AgentRuntimeContext,
    *,
    action_ids: list[str],
) -> JSONDict:
    if not context.db or not action_ids:
        return {}
    try:
        return workflow_action_ledger.execution_state_for_action_ids(
            context.db,
            action_ids=action_ids,
            team_id=context.team_id,
            user_id=context.user_id,
            include_system_actions=True,
        )
    except Exception:
        logger.exception(
            "Agent 自动执行读取 Action Ledger 状态失败，已降级为本轮内存计划: team_id=%s, session_id=%s",
            context.team_id,
            context.session_id,
        )
        return {}


def _auto_execute_plan_items(
    side_effect_context: NewFlowSideEffectContext,
    *,
    tasks: list[object],
) -> list[action_plan.ActionPlanItem]:
    action_items = [
        item
        for item in (getattr(side_effect_context, "auto_execute_actions", None) or [])
        if isinstance(item, action_plan.ActionPlanItem)
    ]
    if action_items:
        return action_items
    return action_plan.items_from_tasks(list(tasks))


def _retryable_workflow_plan_items(actions: list[object]) -> list[action_plan.ActionPlanItem]:
    items: list[action_plan.ActionPlanItem] = []
    for action in actions:
        if not _workflow_action_is_auto_executable(action):
            continue
        item = action_plan.item_from_ledger_action(action)
        if item is not None:
            items.append(item)
    return items


def _workflow_action_is_auto_executable(action: object) -> bool:
    return (
        _optional_str(getattr(action, "execution_policy", None)) == action_workflow.EXECUTION_AUTO_EXECUTE
        or _optional_str(getattr(action, "scope", None)) == action_workflow.SCOPE_DERIVED_AUTOMATION
    )


def _workflow_action_is_retryable(action: object) -> bool:
    return _optional_str(getattr(action, "status", None)) in {"FAILED", "BLOCKED"}


def _first_auto_executable_workflow(actions: list[object]) -> JSONDict:
    for action in actions:
        if not _workflow_action_is_auto_executable(action):
            continue
        item = action_plan.item_from_ledger_action(action)
        if item is not None:
            return action_workflow.workflow_from_mapping(item.workflow)
    return {}


def _mark_auto_execute_nodes_running(
    context: AgentRuntimeContext,
    nodes: tuple[action_plan.ActionPlanNode, ...],
) -> None:
    _mark_auto_execute_nodes_status(context, nodes, status="running")


def _mark_auto_execute_nodes_blocked(
    context: AgentRuntimeContext,
    nodes: tuple[action_plan.ActionPlanNode, ...],
) -> None:
    _mark_auto_execute_nodes_status(context, nodes, status="blocked")


def _mark_auto_execute_node_failed(
    context: AgentRuntimeContext,
    node: action_plan.ActionPlanNode,
    error_message: str,
) -> None:
    if not context.db or not hasattr(context.db, "query"):
        return
    workflow = action_workflow.workflow_from_mapping(node.workflow)
    if not workflow and node.task is not None:
        workflow = action_workflow.workflow_from_task_state(getattr(node.task, "state_json", None))
    if not workflow:
        return
    try:
        workflow_action_ledger.mark_action_failed(
            context.db,
            workflow=workflow,
            team_id=context.team_id,
            user_id=context.user_id,
            task_id=node.task_id,
            error_message=error_message,
            result={"success": False, "error": error_message},
        )
    except Exception:
        logger.exception(
            "Agent 自动执行分支失败后写入 Action Ledger 失败: action_id=%s, team_id=%s, session_id=%s",
            node.action_id,
            context.team_id,
            context.session_id,
        )


def _auto_execute_nodes_with_blocked_reason(
    nodes: tuple[action_plan.ActionPlanNode, ...],
    reason: str,
) -> tuple[action_plan.ActionPlanNode, ...]:
    return tuple(
        action_plan.ActionPlanNode(
            action_id=node.action_id,
            action_type=node.action_type,
            workflow=node.workflow,
            payload=node.payload,
            task=node.task,
            task_id=node.task_id,
            target_type=node.target_type,
            target_id=node.target_id,
            depends_on=node.depends_on,
            parallel_group=node.parallel_group,
            terminal=node.terminal,
            blocked_reason=node.blocked_reason or reason,
        )
        for node in nodes
    )


def _auto_execute_nodes_requiring_authorization(
    nodes: tuple[action_plan.ActionPlanNode, ...],
    *,
    authorization: str | None,
) -> tuple[action_plan.ActionPlanNode, ...]:
    if isinstance(authorization, str) and authorization.strip():
        return ()
    return _auto_execute_nodes_with_blocked_reason(
        tuple(node for node in nodes if action_workflow.action_requires_user_authorization(node.action_type)),
        "missing_authorization",
    )


def _auto_execute_nodes_blocked_by_execution_contract(
    nodes: tuple[action_plan.ActionPlanNode, ...],
) -> tuple[action_plan.ActionPlanNode, ...]:
    blocked: list[action_plan.ActionPlanNode] = []
    for node in nodes:
        if node.task is not None:
            continue
        reason = task_execution.action_execution_blocking_reason(task_execution.execution_envelope_from_plan_node(node))
        if not reason:
            continue
        blocked.append(
            action_plan.ActionPlanNode(
                action_id=node.action_id,
                action_type=node.action_type,
                workflow=node.workflow,
                payload=node.payload,
                task=node.task,
                task_id=node.task_id,
                target_type=node.target_type,
                target_id=node.target_id,
                depends_on=node.depends_on,
                parallel_group=node.parallel_group,
                terminal=node.terminal,
                blocked_reason=reason,
            )
        )
    return tuple(blocked)


def _select_auto_execute_nodes_for_batch(
    nodes: tuple[action_plan.ActionPlanNode, ...],
) -> tuple[action_plan.ActionPlanNode, ...]:
    if len(nodes) <= 1:
        return nodes
    parallel_safe_nodes = tuple(node for node in nodes if action_workflow.action_is_parallel_safe(node.action_type))
    if len(parallel_safe_nodes) > 1:
        return parallel_safe_nodes
    return (nodes[0],)


def _mark_auto_execute_nodes_status(
    context: AgentRuntimeContext,
    nodes: tuple[action_plan.ActionPlanNode, ...],
    *,
    status: str,
) -> None:
    if not context.db or not hasattr(context.db, "query") or not nodes:
        return
    for node in nodes:
        workflow = action_workflow.workflow_from_mapping(node.workflow)
        if not workflow and node.task is not None:
            workflow = action_workflow.workflow_from_task_state(getattr(node.task, "state_json", None))
        if not workflow:
            continue
        try:
            common = {
                "workflow": workflow,
                "team_id": context.team_id,
                "user_id": context.user_id,
                "session_id": context.session_id,
                "task_id": node.task_id,
                "source_type": workflow_action_ledger.SOURCE_AGENT_PLANNING,
                "payload": node.payload,
                "target_type": node.target_type,
                "target_id": node.target_id,
            }
            if status == "running":
                workflow_action_ledger.mark_action_running(
                    context.db,
                    **common,
                    reason="AUTO_EXECUTION_READY",
                )
            elif status == "blocked":
                workflow_action_ledger.mark_action_blocked(
                    context.db,
                    **common,
                    reason=node.blocked_reason or "AUTO_EXECUTION_BLOCKED",
                )
        except Exception:
            logger.exception(
                "Agent 自动执行写入 Action Ledger 状态失败: action_id=%s, status=%s, team_id=%s, session_id=%s",
                node.action_id,
                status,
                context.team_id,
                context.session_id,
            )


def _auto_execute_branch_input(
    task: object,
    *,
    session_id: int,
    team_id: int,
    user_id: int,
    authorization: str,
    channel: str,
    provider: object | None,
) -> JSONDict | None:
    task_id = _optional_int(getattr(task, "id", None))
    if task_id is None:
        return None
    return {
        "task_id": task_id,
        "session_id": session_id,
        "team_id": team_id,
        "user_id": user_id,
        "authorization": authorization,
        "channel": channel,
        "provider": coerce_json_value(provider),
    }


def _auto_execute_node_branch_input(
    node: action_plan.ActionPlanNode,
    *,
    session_id: int,
    team_id: int,
    user_id: int,
    authorization: str,
    channel: str,
    provider: object | None,
) -> JSONDict | None:
    if node.task is not None:
        branch_input = _auto_execute_branch_input(
            node.task,
            session_id=session_id,
            team_id=team_id,
            user_id=user_id,
            authorization=authorization,
            channel=channel,
            provider=provider,
        )
        if branch_input is None:
            return None
        branch_input["node_kind"] = "task"
        branch_input["action_id"] = node.action_id
        return branch_input
    if not _can_direct_execute_action_node(node):
        return None
    envelope = task_execution.execution_envelope_from_plan_node(node)
    return {
        "node_kind": "action",
        "action_id": envelope.action_id,
        "action_type": envelope.action_type,
        "workflow": envelope.workflow,
        "payload": envelope.payload,
        "customer": envelope.customer,
        "task_key": envelope.task_key,
        "session_id": session_id,
        "team_id": team_id,
        "user_id": user_id,
        "authorization": authorization,
        "channel": channel,
        "provider": coerce_json_value(provider),
        "target_type": envelope.target_type,
        "target_id": envelope.target_id,
    }


def _can_direct_execute_action_node(node: action_plan.ActionPlanNode) -> bool:
    if node.task is not None:
        return True
    return task_execution.can_direct_execute_action_envelope(task_execution.execution_envelope_from_plan_node(node))


def _direct_action_success_content(action_type: object) -> str:
    if action_type == "create_customer_activity":
        return agent_copy.customer_activity_created()
    if action_type == "transition_follow_up_task":
        return "任务状态已更新。"
    return agent_copy.generic_completed()


def _auto_execute_branch_completed(branch: object) -> bool:
    branch_json = coerce_json_dict(branch)
    tool_result = coerce_json_dict(branch_json.get("tool_result"))
    if tool_result.get("success") is True:
        return True
    result = coerce_json_dict(branch_json.get("result"))
    if result.get("execution_status") == "completed":
        return True
    events = branch_json.get("events")
    if isinstance(events, list):
        return any(isinstance(event, dict) and event.get("event") == "task_completed" for event in events)
    return False


def _auto_execute_branch_failed(branch: object) -> bool:
    branch_json = coerce_json_dict(branch)
    tool_result = coerce_json_dict(branch_json.get("tool_result"))
    if tool_result.get("success") is False and any(
        isinstance(tool_result.get(key), str) and str(tool_result.get(key)).strip()
        for key in ("error", "error_message", "reason")
    ):
        return True
    result = coerce_json_dict(branch_json.get("result"))
    if result.get("execution_status") == "failed":
        return True
    events = branch_json.get("events")
    if isinstance(events, list):
        return any(
            isinstance(event, dict) and event.get("event") in {"task_failed", "action_failed"} for event in events
        )
    return False


def _optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _next_task_interrupt_from_output_events(
    output_events: list[JSONDict],
    *,
    runtime: Runtime[AgentRuntimeContext],
    assistant_content: str,
) -> AgentInterruptPayload | None:
    next_task_id = _next_task_id_from_output_events(output_events)
    context = runtime.context
    return _next_task_interrupt_from_output_events_for_context(
        output_events,
        context=context,
        assistant_content=assistant_content,
        next_task_id=next_task_id,
    )


def _next_task_interrupt_from_output_events_for_context(
    output_events: list[JSONDict],
    *,
    context: AgentRuntimeContext,
    assistant_content: str,
    next_task_id: int | None = None,
) -> AgentInterruptPayload | None:
    task_id = next_task_id if next_task_id is not None else _next_task_id_from_output_events(output_events)
    if task_id is None or not context.db:
        return None
    next_task = agent_task_crud.get_by_id(
        context.db,
        task_id,
        team_id=context.team_id,
        user_id=context.user_id,
    )
    if not next_task:
        return None
    context.task = next_task
    interaction = _next_task_interaction_from_output_events(output_events)
    if not interaction:
        interaction = interactions._pending_task_interaction(
            next_task,
            assistant_content,
            db=context.db,
            team_id=context.team_id,
        )
    return interrupt_from_waiting_task(next_task, interaction=interaction)


def _next_task_id_from_output_events(output_events: list[JSONDict]) -> int | None:
    for event in output_events:
        raw_id = event.get("next_task_id")
        if isinstance(raw_id, int):
            return raw_id
        if isinstance(raw_id, str):
            try:
                return int(raw_id)
            except ValueError:
                return None
    return None


def _next_task_interaction_from_output_events(output_events: list[JSONDict]) -> JSONDict:
    for event in output_events:
        interaction = coerce_json_dict(event.get("interaction"))
        if interaction:
            return interaction
    return {}


def _resume_task_projection_id(resume_payload: object) -> int | None:
    payload = coerce_json_dict(resume_payload)
    value = payload.get("task_projection_id")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _pending_graph_result_from_bubbled_interrupt(interrupt_payload: AgentInterruptPayload) -> PendingTaskGraphResult:
    assistant_content = _interrupt_assistant_content(interrupt_payload)
    source_event = interrupt_payload.get("source_event")
    event_name = source_event if isinstance(source_event, str) and source_event else "interaction_required"
    event: JSONDict = {
        "event": event_name,
        "content": assistant_content,
    }
    task_id = _interrupt_task_projection_id(interrupt_payload)
    if task_id is not None:
        event["task_id"] = task_id
    draft_payload = coerce_json_dict(interrupt_payload.get("draft_payload"))
    if draft_payload:
        event["payload"] = draft_payload
    interaction = coerce_json_dict(interrupt_payload.get("interaction"))
    if interaction:
        event["interaction"] = interaction
    runtime_events = _interrupt_runtime_events(interrupt_payload)
    if runtime_events:
        return {
            "handled": True,
            "has_active_task": task_id is not None,
            "remember_pending_task": task_id is not None,
            "assistant_content": assistant_content,
            "current_interrupt": interrupt_payload,
            "events": runtime_events,
        }
    return {
        "handled": True,
        "has_active_task": task_id is not None,
        "remember_pending_task": task_id is not None,
        "assistant_content": assistant_content,
        "current_interrupt": interrupt_payload,
        "events": [event, {"event": "final", "content": assistant_content}],
    }


def _interrupt_assistant_content(interrupt_payload: AgentInterruptPayload) -> str:
    interaction = coerce_json_dict(interrupt_payload.get("interaction"))
    prompt = interaction.get("prompt")
    if isinstance(prompt, str) and prompt:
        return prompt
    draft_payload = coerce_json_dict(interrupt_payload.get("draft_payload"))
    content = draft_payload.get("content")
    if isinstance(content, str) and content:
        return content
    return "请补充信息。"


def _interrupt_runtime_events(interrupt_payload: AgentInterruptPayload) -> list[JSONDict]:
    events = interrupt_payload.get("runtime_events")
    if not isinstance(events, list):
        return []
    return [coerce_json_dict(event) for event in events if isinstance(event, dict)]


def _interrupt_task_projection(interrupt_payload: AgentInterruptPayload) -> JSONDict:
    projection: JSONDict = {}
    task_id = _interrupt_task_projection_id(interrupt_payload)
    if task_id is not None:
        projection["id"] = task_id
    task_key = interrupt_payload.get("task_projection_key")
    if isinstance(task_key, str):
        projection["task_key"] = task_key
    return projection


def _suspended_candidates_from_state(state: object) -> list[JSONDict]:
    values = coerce_json_dict(state)
    candidates = values.get("suspended_candidates")
    if not isinstance(candidates, list):
        return []
    return [coerce_json_dict(candidate) for candidate in candidates if isinstance(candidate, dict)][:5]


def _updated_suspended_candidates(
    candidates: object,
    *,
    suspended_task: object | None,
) -> list[JSONDict]:
    current_candidates = _suspended_candidates_from_state({"suspended_candidates": candidates})
    suspended_candidate = _suspended_task_candidate_projection(suspended_task)
    if not suspended_candidate:
        return current_candidates
    suspended_id = suspended_candidate.get("id")
    remaining = [candidate for candidate in current_candidates if candidate.get("id") != suspended_id]
    return [suspended_candidate, *remaining][:5]


def _suspended_task_candidate_projection(task: object | None) -> JSONDict:
    if not task:
        return {}
    state = coerce_json_dict(getattr(task, "state_json", None))
    task_input = coerce_json_dict(getattr(task, "input_json", None))
    nested_payload = task_input.get("payload")
    payload = coerce_json_dict(nested_payload) if isinstance(nested_payload, dict) else task_input
    customer = coerce_json_dict(payload.get("customer")) or coerce_json_dict(state.get("customer"))
    missing_fields = (
        _json_list_values(state.get("missing_fields"))
        or _json_list_values(task_input.get("missing_fields"))
        or _json_list_values(payload.get("missing_fields"))
    )
    projection: JSONDict = {
        "state": state,
        "input": task_input,
        "missing_fields": missing_fields,
    }
    for key in ("id", "intent", "target_type", "target_id", "summary"):
        value = getattr(task, key, None)
        if value is not None:
            projection[key] = coerce_json_value(value)
    status = getattr(task, "status", None)
    if status is not None:
        projection["status"] = coerce_json_value(getattr(status, "value", status))
    action = state.get("action") or task_input.get("action")
    if action is not None:
        projection["action"] = coerce_json_value(action)
    projection["display_summary"] = task_display.pending_task_display_summary(
        action=action,
        summary=getattr(task, "summary", None),
        intent=getattr(task, "intent", None),
        state={key: value for key, value in state.items()},
        task_input={key: value for key, value in task_input.items()},
        payload={key: value for key, value in payload.items()},
        customer={key: value for key, value in customer.items()},
        missing_fields=missing_fields,
    )
    customer_name = customer.get("account_name") or customer.get("name") or state.get("customer_name")
    if customer_name is not None:
        projection["customer_name"] = coerce_json_value(customer_name)
    created_time = getattr(task, "created_time", None)
    if created_time is not None:
        projection["created_time"] = coerce_json_value(created_time)
    updated_time = getattr(task, "updated_time", None)
    if updated_time is not None:
        projection["updated_time"] = coerce_json_value(updated_time)
    return projection


def _json_list_values(value: object) -> JSONList:
    if not isinstance(value, list):
        return []
    return [coerce_json_value(item) for item in value]


def _interrupt_task_projection_id(interrupt_payload: AgentInterruptPayload) -> int | None:
    value = interrupt_payload.get("task_projection_id")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    interaction = coerce_json_dict(interrupt_payload.get("interaction"))
    interaction_task_id = interaction.get("task_id")
    if isinstance(interaction_task_id, int):
        return interaction_task_id
    if isinstance(interaction_task_id, str):
        try:
            return int(interaction_task_id)
        except ValueError:
            return None
    return None


def _new_snapshot_interrupt_payload(
    snapshot: object,
    *,
    previous_interrupt_ids: set[str],
) -> AgentInterruptPayload | None:
    for interrupt_item in _snapshot_interrupt_items(snapshot):
        interrupt_id = _interrupt_item_id(interrupt_item)
        if interrupt_id and interrupt_id in previous_interrupt_ids:
            continue
        payload = coerce_json_dict(getattr(interrupt_item, "value", interrupt_item))
        if payload:
            return payload
    return None


def _snapshot_values(snapshot: object) -> JSONDict:
    values = coerce_json_dict(getattr(snapshot, "values", None))
    active_interrupt = _new_snapshot_interrupt_payload(snapshot, previous_interrupt_ids=set())
    if active_interrupt:
        values["current_interrupt"] = active_interrupt
    return values


def _snapshot_interrupt_payload_except(
    snapshot: object,
    *,
    resumed_interrupt: AgentInterruptPayload,
) -> AgentInterruptPayload | None:
    for interrupt_item in _snapshot_interrupt_items(snapshot):
        payload = coerce_json_dict(getattr(interrupt_item, "value", interrupt_item))
        if payload and not _same_interrupt_payload(payload, resumed_interrupt):
            return payload
    return None


def _same_interrupt_payload(left: JSONDict, right: JSONDict) -> bool:
    left_interaction_id = _interrupt_interaction_id(left)
    right_interaction_id = _interrupt_interaction_id(right)
    if left_interaction_id and right_interaction_id and left_interaction_id != right_interaction_id:
        return False
    return (
        left.get("type") == right.get("type")
        and left.get("reason") == right.get("reason")
        and left.get("business_action") == right.get("business_action")
        and left.get("source_event") == right.get("source_event")
        and _interrupt_task_projection_id(left) == _interrupt_task_projection_id(right)
    )


def _interrupt_interaction_id(interrupt_payload: JSONDict) -> str | None:
    interaction = coerce_json_dict(interrupt_payload.get("interaction"))
    interaction_id = interaction.get("interaction_id")
    return interaction_id if isinstance(interaction_id, str) and interaction_id else None


def _snapshot_interrupt_ids(snapshot: object) -> set[str]:
    interrupt_ids: set[str] = set()
    for interrupt_item in _snapshot_interrupt_items(snapshot):
        interrupt_id = _interrupt_item_id(interrupt_item)
        if interrupt_id:
            interrupt_ids.add(interrupt_id)
    return interrupt_ids


def _snapshot_interrupt_items(snapshot: object) -> list[object]:
    interrupts = getattr(snapshot, "interrupts", None)
    if not isinstance(interrupts, tuple | list):
        return []
    return list(interrupts)


def _interrupt_item_id(interrupt_item: object) -> str | None:
    value = getattr(interrupt_item, "id", None)
    return value if isinstance(value, str) else None


def _is_follow_up_confirmation_resume(value: object) -> bool:
    payload = coerce_json_dict(value)
    metadata = coerce_json_dict(payload.get("metadata"))
    return (
        payload.get("interrupt_reason") == "follow_up_task_confirmation"
        or payload.get("business_action") == FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION
        or metadata.get("business_action") == FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION
        or bool(metadata.get("follow_up_confirmation_case_public_id"))
    )


def _is_confirmation_text(content: str) -> bool:
    normalized = content.strip().lower()
    return normalized in {"是", "确认", "可以", "执行", "好的", "好", "yes", "y", "ok"}


def _config_with_checkpoint_id(config: RunnableConfig, *, checkpoint_id: str) -> RunnableConfig:
    configurable = coerce_json_dict(config.get("configurable"))
    configurable["checkpoint_id"] = checkpoint_id
    return {
        **config,
        "configurable": configurable,
    }


def _snapshot_has_next_nodes(snapshot: object) -> bool:
    next_nodes = getattr(snapshot, "next", ())
    return bool(next_nodes)


def _state_history_item(snapshot: object) -> AgentRuntimeStateHistoryItem:
    values = _root_state_history_values(coerce_json_dict(getattr(snapshot, "values", None)))
    config = coerce_json_dict(getattr(snapshot, "config", None))
    parent_config = coerce_json_dict(getattr(snapshot, "parent_config", None))
    configurable = coerce_json_dict(config.get("configurable"))
    parent_configurable = coerce_json_dict(parent_config.get("configurable"))
    metadata = coerce_json_dict(getattr(snapshot, "metadata", None))
    item: AgentRuntimeStateHistoryItem = {
        "next_nodes": _string_list(getattr(snapshot, "next", None)),
        "has_interrupt": bool(getattr(snapshot, "interrupts", None)),
        "interrupts": _interrupt_history_values(getattr(snapshot, "interrupts", None)),
        "values": values,
    }
    checkpoint_id = configurable.get("checkpoint_id")
    if isinstance(checkpoint_id, str):
        item["checkpoint_id"] = checkpoint_id
    parent_checkpoint_id = parent_configurable.get("checkpoint_id")
    if isinstance(parent_checkpoint_id, str):
        item["parent_checkpoint_id"] = parent_checkpoint_id
    thread_id = configurable.get("thread_id")
    if isinstance(thread_id, str):
        item["thread_id"] = thread_id
    checkpoint_ns = configurable.get("checkpoint_ns")
    if isinstance(checkpoint_ns, str):
        item["checkpoint_ns"] = checkpoint_ns
    created_at = getattr(snapshot, "created_at", None)
    if isinstance(created_at, str):
        item["created_at"] = created_at
    source = metadata.get("source")
    if isinstance(source, str):
        item["source"] = source
    step = metadata.get("step")
    if isinstance(step, int):
        item["step"] = step
    return item


def _root_state_history_values(values: JSONDict) -> JSONDict:
    projected: JSONDict = {}
    for key in (
        "team_id",
        "user_id",
        "session_id",
        "session_key",
        "channel",
        "content",
        "turn_kind",
        "runtime_status",
        "route",
        "application_action",
        "pending_task_handled",
        "current_customer",
        "current_interrupt",
        "task_projection",
        "suspended_candidates",
        "resume_payload",
        "pending_task_result",
        "new_flow_result",
        "customer_intelligence_requested",
        "customer_intelligence_event",
        "customer_intelligence_result",
        "assistant_content",
        "switch_notice",
        "events",
    ):
        if key in values:
            projected[key] = values[key]
    return projected


def _interrupt_history_values(interrupts: object) -> list[JSONDict]:
    if not isinstance(interrupts, tuple | list):
        return []
    projected: list[JSONDict] = []
    for interrupt_item in interrupts:
        value = getattr(interrupt_item, "value", interrupt_item)
        interrupt_payload = coerce_json_dict(value)
        if interrupt_payload:
            projected.append(interrupt_payload)
    return projected


def _follow_up_confirmation_case_public_id(
    interrupt_payload: AgentInterruptPayload,
) -> str | None:
    if interrupt_payload.get("reason") != "follow_up_task_confirmation":
        return None
    interaction = coerce_json_dict(interrupt_payload.get("interaction"))
    payload = coerce_json_dict(interaction.get("payload"))
    case_public_id = payload.get("case_public_id")
    if isinstance(case_public_id, str) and case_public_id.strip():
        return case_public_id.strip()
    return None


def _structured_business_action_type_from_turn(turn_input: AgentTurnInput) -> str | None:
    metadata = coerce_json_dict(turn_input.metadata)
    action_values = (
        metadata.get("business_action"),
        metadata.get("action"),
        metadata.get("resume_action"),
    )
    for value in action_values:
        if value == "resolve_follow_up_task_confirmation_case":
            return "resolve_follow_up_task_confirmation_case"
        if value == "follow_up_task_confirmation_reply":
            return "resolve_follow_up_task_confirmation_case"
    return None


def _structured_follow_up_confirmation_case_public_id_from_turn(
    turn_input: AgentTurnInput,
) -> str | None:
    if _structured_business_action_type_from_turn(turn_input) != "resolve_follow_up_task_confirmation_case":
        return None
    metadata = coerce_json_dict(turn_input.metadata)
    for key in ("case_public_id", "follow_up_confirmation_case_public_id"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _follow_up_confirmation_resolved_event_from_tool_result(
    result_payload: JSONDict,
    *,
    case_public_id: str,
) -> JSONDict:
    event = coerce_json_dict(result_payload)
    event.setdefault("event", FOLLOW_UP_CONFIRMATION_RESOLVED_EVENT)
    event.setdefault("case_public_id", case_public_id)
    event.setdefault("content_format", "text")
    if not isinstance(event.get("content"), str) or not str(event.get("content")).strip():
        event["content"] = agent_copy.generic_completed()
    return event


def _string_list(value: object) -> list[str]:
    if not isinstance(value, tuple | list):
        return []
    return [item for item in value if isinstance(item, str)]
