"""LangGraph fallback runtime used when root checkpoint storage is unavailable."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.services.agent import agent_copy
from app.services.agent.checkpointer import checkpoint_unavailable_fallback_event
from app.services.agent.confirmed_task_graph import (
    ConfirmedTaskGraphService,
    confirmed_task_graph_service as default_confirmed_task_graph_service,
)
from app.services.agent.graph import crm_agent_graph_service
from app.services.agent.input import AgentTurnInput
from app.services.agent.new_flow_effects import (
    NewFlowGraphStreamer,
    NewFlowSideEffectContext,
    NewFlowSideEffectHandler,
    new_flow_side_effect_handler,
)
from app.services.agent.pending_effects import PendingTaskSideEffectContext, pending_task_side_effect_handler
from app.services.agent.pending_graph import PendingTaskGraphService, pending_task_graph_service
from app.services.agent.root_runtime import build_agent_graph_config, decide_application_action
from app.services.agent.state import (
    AgentApplicationRuntimeResult,
    AgentRuntimeApplicationAction,
    AgentRuntimeContext,
    AgentRuntimeState,
    AgentRuntimeTurnOutput,
    PendingTaskGraphResult,
    PendingTaskGraphSideEffects,
)
from app.services.agent.types import JSONDict, coerce_json_dict


class CheckpointFallbackNewFlowAdapter:
    """Runs the normal new-flow graph only inside checkpoint outage fallback."""

    def __init__(
        self,
        *,
        side_effect_handler: NewFlowSideEffectHandler | None = None,
    ) -> None:
        self.side_effect_handler = side_effect_handler or new_flow_side_effect_handler

    async def stream_events(
        self,
        db: object,
        *,
        session: object,
        team_id: int,
        user_id: int,
        content: str,
        authorization: str,
        switch_notice: str | None,
        assistant_ref: dict[str, object],
        graph_service: NewFlowGraphStreamer | None = None,
    ):
        graph = graph_service or crm_agent_graph_service
        side_effect_context = NewFlowSideEffectContext(
            db=db,
            session=session,
            team_id=team_id,
            user_id=user_id,
            switch_notice=switch_notice,
            assistant_content=assistant_ref.get("content") if isinstance(assistant_ref.get("content"), str) else None,
        )
        session_id = getattr(session, "id", 0)
        session_context = getattr(session, "context_json", None)
        if not isinstance(session_context, dict):
            session_context = {}
        async for event in graph.stream_events({
            "db": db,
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id if isinstance(session_id, int) else 0,
            "session_context": session_context,
            "content": content,
            "authorization": authorization,
        }):
            processed_event = self.side_effect_handler.apply(event, side_effect_context)
            assistant_ref["content"] = side_effect_context.assistant_content
            yield processed_event


class AgentCheckpointFallbackRuntime:
    """Explicit no-checkpointer runtime for checkpoint storage outages.

    This is not the normal source of runtime truth. It only keeps the outage
    path out of the application layer and makes the degraded branch structure
    observable through LangGraph nodes.
    """

    def __init__(
        self,
        *,
        pending_graph_service: PendingTaskGraphService | None = None,
        confirmed_task_graph_service: ConfirmedTaskGraphService | None = None,
        new_flow_adapter: CheckpointFallbackNewFlowAdapter | None = None,
    ) -> None:
        self.pending_graph_service = pending_graph_service or pending_task_graph_service
        self.confirmed_task_graph_service = confirmed_task_graph_service or default_confirmed_task_graph_service
        self.new_flow_adapter = new_flow_adapter or CheckpointFallbackNewFlowAdapter()
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentRuntimeState, context_schema=AgentRuntimeContext)
        graph.add_node("start_fallback", self._start_fallback)
        graph.add_node("pending_task_subgraph", self._run_pending_task_subgraph)
        graph.add_node("decide_application_action", self._decide_application_action)
        graph.add_node("confirmed_task_execution", self._run_confirmed_task_execution)
        graph.add_node("no_pending_confirmation", self._run_no_pending_confirmation)
        graph.add_node("new_flow_fallback", self._run_new_flow_fallback)
        graph.add_node("checkpoint_write_blocked", self._checkpoint_write_blocked)
        graph.add_node("finish_fallback", self._finish_fallback)
        graph.add_edge(START, "start_fallback")
        graph.add_conditional_edges(
            "start_fallback",
            self._route_after_start,
            {
                "pending_task_subgraph": "pending_task_subgraph",
                "decide_application_action": "decide_application_action",
            },
        )
        graph.add_edge("pending_task_subgraph", "decide_application_action")
        graph.add_conditional_edges(
            "decide_application_action",
            self._route_after_application_action,
            {
                "confirmed_task_execution": "checkpoint_write_blocked",
                "no_pending_confirmation": "no_pending_confirmation",
                "new_flow_fallback": "checkpoint_write_blocked",
                "finish_fallback": "finish_fallback",
            },
        )
        graph.add_edge("confirmed_task_execution", "finish_fallback")
        graph.add_edge("no_pending_confirmation", "finish_fallback")
        graph.add_edge("new_flow_fallback", "finish_fallback")
        graph.add_edge("checkpoint_write_blocked", "finish_fallback")
        graph.add_edge("finish_fallback", END)
        return graph.compile()

    async def run(
        self,
        *,
        db: object,
        session: object,
        task: object | None,
        turn_input: AgentTurnInput,
        content: str,
        team_id: int,
        user_id: int,
        authorization: str,
    ) -> AgentApplicationRuntimeResult:
        context = AgentRuntimeContext(
            db=db,
            session=session,
            task=task,
            turn_input=turn_input,
            content=content,
            team_id=team_id,
            user_id=user_id,
            session_id=_session_id(session),
            authorization=authorization,
        )
        state: AgentRuntimeState = {
            "team_id": team_id,
            "user_id": user_id,
            "session_id": _session_id(session),
            "session_key": _session_key(session),
            "channel": turn_input.source,
            "content": content,
            "turn_kind": turn_input.kind.value,
            "pending_task_requested": bool(task),
            "checkpoint_unavailable": True,
            "fallback_reason": "checkpoint_storage_error",
        }
        result = await self._graph.ainvoke(
            state,
            build_agent_graph_config(
                team_id=team_id,
                user_id=user_id,
                session_id=_session_id(session),
                session_key=_session_key(session),
            ),
            context=context,
        )
        events = _event_list(result.get("events"))
        assistant_content = _string(result.get("assistant_content"))
        return AgentApplicationRuntimeResult(
            state=result,
            turn_output=AgentRuntimeTurnOutput(
                events=events,
                assistant_content=assistant_content,
                switch_notice=_string(result.get("switch_notice")),
            ),
            pending_task_result=coerce_json_dict(result.get("pending_task_result")),
            checkpoint_unavailable=True,
        )

    def _start_fallback(self, state: AgentRuntimeState) -> AgentRuntimeState:
        return {
            "runtime_status": "checkpoint_unavailable_fallback_started",
            "events": [_root_fallback_event()],
        }

    def _route_after_start(self, state: AgentRuntimeState) -> str:
        if state.get("pending_task_requested"):
            return "pending_task_subgraph"
        return "decide_application_action"

    async def _run_pending_task_subgraph(
        self,
        state: AgentRuntimeState,
        runtime: Runtime[AgentRuntimeContext],
    ) -> AgentRuntimeState:
        context = runtime.context
        pending_side_effects = PendingTaskGraphSideEffects(task=context.task)
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
            "events": [],
        }
        run_with_trace = getattr(self.pending_graph_service, "run_with_trace", None)
        if callable(run_with_trace):
            pending_graph_state = await run_with_trace(pending_graph_input, side_effects=pending_side_effects)
        else:
            pending_graph_state = await self.pending_graph_service.run(
                pending_graph_input,
                side_effects=pending_side_effects,
            )
        context.task = pending_side_effects.task
        pending_effects = pending_task_side_effect_handler.apply(
            pending_graph_state,
            PendingTaskSideEffectContext(
                db=context.db,
                session=context.session,
                team_id=context.team_id,
                user_id=context.user_id,
                task=context.task,
                switch_notice=_string(state.get("switch_notice")),
                graph_side_effects=pending_side_effects,
            ),
        )
        context.task = pending_effects.task
        return {
            "pending_task_result": _pending_task_result_projection(pending_graph_state),
            "assistant_content": pending_effects.assistant_content,
            "switch_notice": pending_effects.switch_notice,
            "events": _event_list(pending_effects.events),
        }

    def _decide_application_action(self, state: AgentRuntimeState, runtime: Runtime[AgentRuntimeContext]) -> AgentRuntimeState:
        pending_result = coerce_json_dict(state.get("pending_task_result"))
        action = _fallback_application_action(
            content=state.get("content") or runtime.context.content,
            turn_input=runtime.context.turn_input,
            task=runtime.context.task,
            pending_graph_state=pending_result,
        )
        return {
            "application_action": action,
            "events": [{
                "event": "agent_root_checkpoint_fallback_action_decided",
                "application_action": action,
            }],
        }

    def _route_after_application_action(self, state: AgentRuntimeState) -> str:
        action = state.get("application_action")
        if action == "execute_confirmed_task":
            return "confirmed_task_execution"
        if action == "no_pending_confirmation":
            return "no_pending_confirmation"
        if action == "run_new_flow":
            return "new_flow_fallback"
        return "finish_fallback"

    async def _run_confirmed_task_execution(
        self,
        state: AgentRuntimeState,
        runtime: Runtime[AgentRuntimeContext],
    ) -> AgentRuntimeState:
        context = runtime.context
        if not context.task:
            return {}
        confirmed_graph_state = await self.confirmed_task_graph_service.run({
            "db": context.db,
            "session": context.session,
            "task": context.task,
            "team_id": context.team_id,
            "user_id": context.user_id,
            "session_id": context.session_id,
            "authorization": context.authorization,
            "events": _event_list(state.get("events")),
        })
        return {
            "assistant_content": _string(confirmed_graph_state.get("assistant_content")),
            "events": _event_list(confirmed_graph_state.get("output_events")),
        }

    def _run_no_pending_confirmation(self, state: AgentRuntimeState) -> AgentRuntimeState:
        assistant_content = agent_copy.no_pending_confirmation()
        return {
            "assistant_content": assistant_content,
            "events": [{"event": "final", "content": assistant_content}],
        }

    async def _run_new_flow_fallback(
        self,
        state: AgentRuntimeState,
        runtime: Runtime[AgentRuntimeContext],
    ) -> AgentRuntimeState:
        context = runtime.context
        assistant_ref: dict[str, object] = {}
        assistant_content = _string(state.get("assistant_content"))
        if assistant_content:
            assistant_ref["content"] = assistant_content
        output_events: list[JSONDict] = []
        async for event in self.new_flow_adapter.stream_events(
            context.db,
            session=context.session,
            team_id=context.team_id,
            user_id=context.user_id,
            content=context.content,
            authorization=context.authorization,
            switch_notice=_string(state.get("switch_notice")),
            assistant_ref=assistant_ref,
            graph_service=crm_agent_graph_service,
        ):
            output_events.append(event)
        return {
            "assistant_content": _string(assistant_ref.get("content")),
            "events": output_events,
        }

    def _checkpoint_write_blocked(self, state: AgentRuntimeState) -> AgentRuntimeState:
        assistant_content = (
            "当前 Agent checkpoint 存储不可用。为避免绕过审计、幂等和恢复机制，本轮业务写入已暂停；"
            "请稍后重试。"
        )
        return {
            "runtime_status": "checkpoint_unavailable_write_blocked",
            "assistant_content": assistant_content,
            "events": [
                {
                    "event": "agent_root_checkpoint_write_blocked",
                    "content": assistant_content,
                    "application_action": state.get("application_action") or "run_new_flow",
                    "checkpoint_unavailable": True,
                    "fallback_reason": "checkpoint_storage_error",
                },
                {"event": "final", "content": assistant_content},
            ],
        }

    def _finish_fallback(self, state: AgentRuntimeState) -> AgentRuntimeState:
        runtime_status = state.get("runtime_status")
        return {
            "runtime_status": runtime_status or "checkpoint_unavailable_fallback_finished",
            "events": [{
                "event": "agent_root_checkpoint_fallback_finished",
                "application_action": state.get("application_action") or "finish",
            }],
        }


def _root_fallback_event() -> JSONDict:
    event = checkpoint_unavailable_fallback_event(
        runtime="crm_agent_root",
        graph="crm_agent",
    )
    event["event"] = "agent_root_checkpoint_unavailable_fallback_started"
    event["content"] = "Agent root checkpoint storage is unavailable; using explicit no-checkpointer fallback."
    return event


def _fallback_application_action(
    *,
    content: str,
    turn_input: AgentTurnInput | None,
    task: object | None,
    pending_graph_state: PendingTaskGraphResult,
) -> AgentRuntimeApplicationAction:
    confirmation_decision = pending_graph_state.get("confirmation_decision")
    return decide_application_action({
        "content": content,
        "turn_kind": turn_input.kind.value if turn_input else "text",
        "pending_task_requested": bool(task),
        "pending_task_result": {
            "handled": bool(pending_graph_state.get("handled")),
            "has_task": bool(
                pending_graph_state.get("has_active_task")
                or pending_graph_state.get("task_projection")
            ),
            "confirmation_decision": coerce_json_dict(
                confirmation_decision.model_dump()
                if confirmation_decision and hasattr(confirmation_decision, "model_dump")
                else confirmation_decision
            ),
        },
    })


def _pending_task_result_projection(result: object) -> PendingTaskGraphResult:
    if not isinstance(result, dict):
        return {}
    projection = coerce_json_dict(result)
    confirmation_decision = result.get("confirmation_decision")
    if confirmation_decision and hasattr(confirmation_decision, "model_dump"):
        projection["confirmation_decision"] = coerce_json_dict(confirmation_decision.model_dump())
    return projection


def _event_list(value: object) -> list[JSONDict]:
    if not isinstance(value, list):
        return []
    return [coerce_json_dict(event) for event in value if isinstance(event, dict)]


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _session_id(session: object) -> int:
    value = getattr(session, "id", 0)
    return value if isinstance(value, int) else 0


def _session_key(session: object) -> str:
    value = getattr(session, "session_key", "")
    return value if isinstance(value, str) else ""


agent_checkpoint_fallback_runtime = AgentCheckpointFallbackRuntime()
