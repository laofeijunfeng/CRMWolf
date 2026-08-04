"""LangGraph-native root runtime foundation for CRM Agent turns."""
from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

from app.crud.agent import agent_task_crud
from app.services.agent import agent_copy, execution_trace, interactions, task_display
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
from app.services.agent.graph import crm_agent_graph_service
from app.services.agent.input import AgentTurnInput
from app.services.agent.interrupts import (
    AgentInterruptPayload,
    AgentResumePayload,
    interrupt_from_waiting_task,
    interrupt_payload_from_json,
    resume_payload_from_turn_input,
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
from app.services.agent.types import JSONDict, JSONList, coerce_json_dict, coerce_json_value
from app.services.customer_intelligence_trace_service import visible_trace_events

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
                "finish": "finish_turn",
            },
        )
        graph.add_conditional_edges(
            "new_flow_graph",
            self._route_after_graph_output,
            {
                "generated_interrupt_wait": "generated_interrupt_wait",
                "customer_intelligence_graph": "customer_intelligence_graph",
                "finish": "finish_turn",
            },
        )
        graph.add_conditional_edges(
            "customer_intelligence_graph",
            self._route_after_customer_intelligence_graph,
            {
                "generated_interrupt_wait": "generated_interrupt_wait",
                "finish": "finish_turn",
            },
        )
        graph.add_conditional_edges(
            "confirmed_task_execution",
            self._route_after_confirmed_task_execution,
            {
                "customer_intelligence_graph": "customer_intelligence_graph",
                "finish": "finish_turn",
            },
        )
        graph.add_edge("no_pending_confirmation", "finish_turn")
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
        return await self.resume_interrupt(
            resume_payload=resume_payload_from_turn_input(
                turn_input,
                current_interrupt=runtime_current_interrupt,
            ),
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            session_key=session_key,
            context=context,
            current_interrupt=runtime_current_interrupt,
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
            _config_with_checkpoint_id(config, checkpoint_id=before_checkpoint_id)
            if before_checkpoint_id
            else None
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
                return await self._project_bubbled_pending_interrupt(
                    bubbled_interrupt,
                    snapshot=next_snapshot,
                    context=context,
                    config=config,
                )
        return current_result

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
        state.update({
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
        })
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
            "resume_payload": {},
            "assistant_content": None,
            "switch_notice": None,
            "events": [{
                "event": "agent_root_graph_started",
                "thread_id": build_agent_thread_id(
                    team_id=state["team_id"],
                    user_id=state["user_id"],
                    session_id=state["session_id"],
                    session_key=state.get("session_key"),
                ),
            }],
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
        update: AgentRuntimeState = {
            "runtime_status": "resumed",
            "current_interrupt": None,
            "resume_payload": coerce_json_dict(resume_payload),
            "events": [{
                "event": "agent_root_interrupt_resumed",
                "resume_action": coerce_json_dict(resume_payload).get("action"),
            }],
        }
        if runtime.context and runtime.context.task:
            update["pending_task_requested"] = True
        elif _resume_task_projection_id(update.get("resume_payload")) is not None:
            update["pending_task_requested"] = True
        return update

    def _route_after_interrupt_resume(self, state: AgentRuntimeState) -> str:
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
                "events": [{
                    "event": "agent_root_pending_task_subgraph_unavailable",
                    "reason": "missing_runtime_context",
                }],
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
            "events": [{
                "event": "agent_root_pending_task_subgraph_completed",
                "handled": bool(result.get("handled")),
                "has_task": bool(result.get("has_active_task") or result.get("task_projection")),
                "event_count": len(result.get("events", [])),
            }],
        }

    async def _apply_pending_task_effects(
        self,
        state: AgentRuntimeState,
        runtime: Runtime[AgentRuntimeContext],
    ) -> AgentRuntimeState:
        context = runtime.context
        if not context.db or not context.session:
            return {
                "events": [{
                    "event": "agent_root_pending_task_effects_unavailable",
                    "reason": "missing_runtime_context",
                }],
            }
        pending_result = context.side_effects.pending_task_result
        if not pending_result:
            return {
                "events": [{
                    "event": "agent_root_pending_task_effects_skipped",
                    "reason": "empty_pending_result",
                }],
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
            "events": [{
                "event": "agent_root_pending_task_effects_applied",
                "event_count": len(result.events),
                "has_assistant_content": bool(result.assistant_content),
                "has_switch_notice": bool(result.switch_notice),
                "has_interrupt": bool(current_interrupt),
            }],
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
            "events": [{
                "event": "agent_root_application_action_decided",
                "application_action": action,
            }],
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

    async def _run_customer_intelligence_graph(
        self,
        state: AgentRuntimeState,
        runtime: Runtime[AgentRuntimeContext],
    ) -> AgentRuntimeState:
        context = runtime.context
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
                "events": [{
                    "event": "agent_root_customer_intelligence_unavailable",
                    "reason": "missing_runtime_context",
                }],
            }

        streamed_customer_intelligence_trace = False
        if _is_customer_intelligence_resume(state.get("resume_payload")):
            event_key = _customer_intelligence_event_key_from_state(state)
            if not event_key:
                return {
                    "customer_intelligence_result": {"handled": False, "reason": "missing_event_key"},
                    "events": [{
                        "event": "agent_root_customer_intelligence_resume_skipped",
                        "reason": "missing_event_key",
                    }],
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
            event_object = context.customer_intelligence_event
            if event_object is None:
                return {
                    "customer_intelligence_requested": False,
                    "customer_intelligence_result": {"handled": False, "reason": "missing_event"},
                    "events": [{
                        "event": "agent_root_customer_intelligence_skipped",
                        "reason": "missing_event",
                    }],
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
            "events": [{
                "event": "agent_root_customer_intelligence_graph_completed",
                "has_interrupt": bool(current_interrupt),
                "event_count": len(output_events),
            }],
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
                "events": [{
                    "event": "agent_root_new_flow_unavailable",
                    "reason": "missing_runtime_context",
                }],
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
        if _should_publish_deferred_new_flow_final(
            deferred_final_events,
            customer_intelligence_requested=customer_intelligence_event is not None,
            current_interrupt=current_interrupt,
            context=side_effect_context,
        ):
            for final_event in deferred_final_events:
                context.side_effects.new_flow_events.append(final_event)
                await _publish_event(context, final_event)
                event_count += 1
        if current_interrupt:
            context.side_effects.current_interrupt = current_interrupt
        if isinstance(assistant_content, str):
            context.side_effects.new_flow_assistant_content = assistant_content
            update: AgentRuntimeState = {
                "assistant_content": assistant_content,
                "current_interrupt": current_interrupt,
                "customer_intelligence_requested": customer_intelligence_event is not None,
                "new_flow_result": _new_flow_result_projection(
                    event_count=event_count,
                    assistant_content=assistant_content,
                    current_interrupt=current_interrupt,
                ),
                "events": [{
                    "event": "agent_root_new_flow_graph_completed",
                    "event_count": event_count,
                    "has_assistant_content": True,
                    "has_interrupt": bool(current_interrupt),
                }],
            }
            if current_interrupt:
                update["task_projection"] = _interrupt_task_projection(current_interrupt)
            return update
        update = {
            "current_interrupt": current_interrupt,
            "customer_intelligence_requested": customer_intelligence_event is not None,
            "new_flow_result": _new_flow_result_projection(
                event_count=event_count,
                assistant_content=None,
                current_interrupt=current_interrupt,
            ),
            "events": [{
                "event": "agent_root_new_flow_graph_completed",
                "event_count": event_count,
                "has_assistant_content": False,
                "has_interrupt": bool(current_interrupt),
            }],
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
        if not tasks:
            return {}
        assistant_content: str | None = None
        current_interrupt: AgentInterruptPayload | None = None
        emitted_event_count = 0
        for task in tasks:
            started_event = _step_event(
                "auto_execute_task",
                "started",
                task_display.readable_execution_label(_task_action(task)) or "执行业务操作",
            )
            context.side_effects.new_flow_events.append(started_event)
            await _publish_event(context, started_event)
            result = await self.confirmed_task_graph_service.run({
                "db": context.db,
                "session": context.session,
                "task": task,
                "team_id": context.team_id,
                "user_id": context.user_id,
                "session_id": context.session_id,
                "authorization": context.authorization or "",
                "events": [],
                "event_sink": context.event_sink,
            })
            output_events = execution_trace.confirmed_task_execution_events(
                task=task,
                graph_events=result.get("events", []),
                output_events=result.get("output_events", []),
                include_graph_progress_events=not bool(context.event_sink),
            )
            await _publish_events(context, output_events)
            context.side_effects.new_flow_events.extend(output_events)
            emitted_event_count += len(output_events) + 1
            self._customer_intelligence_event_from_confirmed_tool_result(
                context,
                result.get("tool_result") or {},
            )
            result_content = result.get("assistant_content")
            if isinstance(result_content, str):
                assistant_content = result_content
            current_interrupt = _next_task_interrupt_from_output_events_for_context(
                output_events,
                context=context,
                assistant_content=assistant_content or "",
            )
        return coerce_json_dict({
            "event": "agent_root_new_flow_auto_execution_completed",
            "emitted_event_count": emitted_event_count,
            "assistant_content": assistant_content,
            "current_interrupt": current_interrupt,
        })

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
                "events": [{
                    "event": "agent_root_confirmed_task_execution_unavailable",
                    "reason": "missing_runtime_context",
                }],
            }
        result = await self.confirmed_task_graph_service.run({
            "db": context.db,
            "session": context.session,
            "task": context.task,
            "team_id": context.team_id,
            "user_id": context.user_id,
            "session_id": context.session_id,
            "authorization": context.authorization or "",
            "events": [],
            "event_sink": context.event_sink,
        })
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
            "events": [{
                "event": "agent_root_confirmed_task_subgraph_completed",
                "emitted_event_count": len(output_events),
                "task_event": task_event.get("event"),
                "execution_status": result.get("execution_status"),
                "has_next_interrupt": bool(current_interrupt),
            }],
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
            context.side_effects.customer_intelligence_events.append({
                "event": "agent_root_customer_intelligence_trigger_failed",
                "source": "confirmed_tool_result",
            })
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
            "events": [{
                "event": "agent_root_no_pending_confirmation_completed",
                "has_assistant_content": True,
            }],
        }

    def _route_event(self, route: str, state: AgentRuntimeState) -> AgentRuntimeState:
        return {
            "route": route,
            "events": [{
                "event": "agent_root_route_selected",
                "route": route,
                "has_interrupt": bool(state.get("current_interrupt")),
            }],
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
            events=list(side_effects.pending_task_events),
            assistant_content=side_effects.pending_task_assistant_content or _assistant_content_from_state(state),
            switch_notice=side_effects.pending_task_switch_notice or _switch_notice_from_state(state),
        )
    if action == "execute_confirmed_task":
        return AgentRuntimeTurnOutput(
            events=[
                *side_effects.pending_task_events,
                *side_effects.confirmed_task_events,
                *side_effects.customer_intelligence_events,
            ],
            assistant_content=side_effects.confirmed_task_assistant_content or _assistant_content_from_state(state),
            switch_notice=_switch_notice_from_state(state),
        )
    if action == "no_pending_confirmation":
        return AgentRuntimeTurnOutput(
            events=list(side_effects.no_pending_confirmation_events),
            assistant_content=(
                side_effects.no_pending_confirmation_assistant_content
                or _assistant_content_from_state(state)
            ),
            switch_notice=_switch_notice_from_state(state),
        )
    return AgentRuntimeTurnOutput(
        events=[
            *side_effects.pending_task_events,
            *side_effects.new_flow_events,
            *side_effects.customer_intelligence_events,
        ],
        assistant_content=(
            side_effects.customer_intelligence_assistant_content
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
        events.append({
            "event": "final",
            "content": assistant_content,
            "content_format": _customer_intelligence_content_format(result),
        })
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
    return not bool(context.auto_execute_tasks)


def _should_publish_deferred_new_flow_final(
    events: list[JSONDict],
    *,
    customer_intelligence_requested: bool,
    current_interrupt: AgentInterruptPayload | None,
    context: NewFlowSideEffectContext,
) -> bool:
    if not events:
        return False
    if not _should_emit_new_flow_event({"event": "final"}, context):
        return False
    if current_interrupt:
        return True
    return not customer_intelligence_requested


def _task_action(task: object) -> str | None:
    state_json = getattr(task, "state_json", None)
    state = coerce_json_dict(state_json)
    action = state.get("action")
    return action if isinstance(action, str) else None


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
    remaining = [
        candidate
        for candidate in current_candidates
        if candidate.get("id") != suspended_id
    ]
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


def _string_list(value: object) -> list[str]:
    if not isinstance(value, tuple | list):
        return []
    return [item for item in value if isinstance(item, str)]
