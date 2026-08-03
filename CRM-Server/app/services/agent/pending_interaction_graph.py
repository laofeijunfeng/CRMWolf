"""LangGraph subgraph for pending-task interaction handling."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Annotated, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from sqlalchemy.exc import SQLAlchemyError

from app.services.agent import (
    choice_resolution,
    customer_fields,
    customer_related_fields,
    follow_up_fields,
    lead_fields,
    opportunity_fields,
    payment_fields,
    selection,
)
from app.services.agent.checkpointer import (
    agent_checkpoint_saver,
    checkpoint_unavailable_fallback_event,
    is_checkpoint_storage_error,
)
from app.models.agent import AgentTaskStatus
from app.services.agent.state import PendingTaskTurnResult, internal_graph_start_event, merge_turn_scoped_events
from app.services.agent.types import JSONDict, JSONValue, coerce_json_dict, coerce_json_value


PENDING_INTERACTION_CHECKPOINT_NS = "crm_agent_pending_interaction"
FieldPredicate = Callable[[object], bool]
FieldCollector = Callable[[object, object, str], Awaitable[tuple[bool, str]]]
FieldCollectorFactory = Callable[[], FieldCollector]


class PendingInteractionGraphState(TypedDict, total=False):
    team_id: int
    user_id: int
    session_id: int
    task_projection: JSONDict
    content: str
    interaction_route: str
    field_result: JSONDict
    business_choice_result: JSONDict
    customer_choice_result: JSONDict
    result_projection: JSONDict
    events: Annotated[list[JSONDict], merge_turn_scoped_events]


class PendingInteractionGraphInput(TypedDict, total=False):
    db: object
    task: object
    content: str
    team_id: int
    user_id: int
    session_id: int
    authorization: str
    interaction_metadata: JSONDict
    events: list[JSONDict]


@dataclass
class PendingInteractionGraphSideEffects:
    result: PendingTaskTurnResult | None = None


@dataclass
class PendingInteractionRuntimeContext:
    db: object | None = None
    task: object | None = None
    content: str = ""
    team_id: int = 0
    user_id: int = 0
    session_id: int = 0
    authorization: str | None = None
    interaction_metadata: JSONDict = field(default_factory=dict)
    side_effects: PendingInteractionGraphSideEffects = field(default_factory=PendingInteractionGraphSideEffects)


PendingInteractionNode = Callable[
    [PendingInteractionGraphState, Runtime[PendingInteractionRuntimeContext]],
    Awaitable[PendingInteractionGraphState],
]


@dataclass(frozen=True)
class FieldInteractionSpec:
    route: str
    node_name: str
    predicate: FieldPredicate
    collector_factory: FieldCollectorFactory
    pending_event: str


FIELD_INTERACTION_SPECS: tuple[FieldInteractionSpec, ...] = (
    FieldInteractionSpec(
        route="follow_up_quality_fields",
        node_name="collect_follow_up_quality_fields",
        predicate=follow_up_fields._is_follow_up_quality_fields_task,
        collector_factory=lambda: follow_up_fields._apply_follow_up_quality_fields,
        pending_event="follow_up_quality_required",
    ),
    FieldInteractionSpec(
        route="lead_follow_up_quality_fields",
        node_name="collect_lead_follow_up_quality_fields",
        predicate=follow_up_fields._is_lead_follow_up_quality_fields_task,
        collector_factory=lambda: follow_up_fields._apply_lead_follow_up_quality_fields,
        pending_event="follow_up_quality_required",
    ),
    FieldInteractionSpec(
        route="contact_fields",
        node_name="collect_contact_fields",
        predicate=customer_related_fields._is_contact_fields_task,
        collector_factory=lambda: customer_related_fields._apply_contact_fields,
        pending_event="contact_fields_required",
    ),
    FieldInteractionSpec(
        route="opportunity_fields",
        node_name="collect_opportunity_fields",
        predicate=opportunity_fields._is_opportunity_fields_task,
        collector_factory=lambda: opportunity_fields._apply_opportunity_fields,
        pending_event="opportunity_fields_required",
    ),
    FieldInteractionSpec(
        route="invoice_title_fields",
        node_name="collect_invoice_title_fields",
        predicate=customer_related_fields._is_invoice_title_fields_task,
        collector_factory=lambda: customer_related_fields._apply_invoice_title_fields,
        pending_event="invoice_title_fields_required",
    ),
    FieldInteractionSpec(
        route="deployment_info_fields",
        node_name="collect_deployment_info_fields",
        predicate=customer_related_fields._is_deployment_info_fields_task,
        collector_factory=lambda: customer_related_fields._apply_deployment_info_fields,
        pending_event="deployment_info_fields_required",
    ),
    FieldInteractionSpec(
        route="customer_member_fields",
        node_name="collect_customer_member_fields",
        predicate=customer_related_fields._is_customer_member_fields_task,
        collector_factory=lambda: customer_related_fields._apply_customer_member_fields,
        pending_event="customer_member_fields_required",
    ),
    FieldInteractionSpec(
        route="payment_fields",
        node_name="collect_payment_fields",
        predicate=payment_fields._is_payment_fields_task,
        collector_factory=lambda: payment_fields._apply_payment_fields,
        pending_event="payment_fields_required",
    ),
    FieldInteractionSpec(
        route="lead_fields",
        node_name="collect_lead_fields",
        predicate=lead_fields._is_lead_fields_task,
        collector_factory=lambda: lead_fields._apply_lead_fields,
        pending_event="lead_fields_required",
    ),
    FieldInteractionSpec(
        route="customer_fields",
        node_name="collect_customer_fields",
        predicate=customer_fields._is_customer_fields_task,
        collector_factory=lambda: customer_fields._apply_customer_fields,
        pending_event="customer_fields_required",
    ),
)
FIELD_INTERACTION_ROUTES = frozenset(spec.route for spec in FIELD_INTERACTION_SPECS)
FIELD_INTERACTION_NODE_BY_ROUTE = {spec.route: spec.node_name for spec in FIELD_INTERACTION_SPECS}


class PendingInteractionGraphService:
    """Handles pending-task field and choice interactions as a checkpointed graph."""

    def __init__(self, *, checkpointer: object | None = None) -> None:
        self._checkpoint_enabled = checkpointer is not None
        self._graph = self._build_graph(checkpointer)
        self._fallback_graph = self._build_graph(None)

    def _build_graph(self, checkpointer: object | None):
        graph = StateGraph(PendingInteractionGraphState, context_schema=PendingInteractionRuntimeContext)
        graph.add_node("classify_interaction", self._classify_interaction)
        for spec in FIELD_INTERACTION_SPECS:
            graph.add_node(spec.node_name, self._field_interaction_node(spec))
        graph.add_node("select_business", self._select_business)
        graph.add_node("select_customer", self._select_customer)
        graph.add_edge(START, "classify_interaction")
        graph.add_conditional_edges(
            "classify_interaction",
            self._route_after_classification,
            {
                **FIELD_INTERACTION_NODE_BY_ROUTE,
                "business_choice": "select_business",
                "customer_choice": "select_customer",
                "end": END,
            },
        )
        for spec in FIELD_INTERACTION_SPECS:
            graph.add_edge(spec.node_name, END)
        graph.add_edge("select_business", END)
        graph.add_edge("select_customer", END)
        if checkpointer is None:
            return graph.compile()
        return graph.compile(checkpointer=checkpointer)

    async def run(self, input_state: PendingInteractionGraphInput) -> PendingTaskTurnResult:
        checkpoint_state = _checkpoint_state_from_input(input_state)
        side_effects = PendingInteractionGraphSideEffects()
        context = _runtime_context_from_input(input_state, side_effects)
        config = build_pending_interaction_graph_config(
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
            task_id=_optional_object_id(context.task),
        )
        try:
            await self._graph.ainvoke(checkpoint_state, config, context=context)
        except SQLAlchemyError as exc:
            if not self._checkpoint_enabled or not is_checkpoint_storage_error(exc):
                raise
            fallback_side_effects = PendingInteractionGraphSideEffects()
            fallback_context = _runtime_context_from_input(input_state, fallback_side_effects)
            await self._fallback_graph.ainvoke(checkpoint_state, config, context=fallback_context)
            side_effects = fallback_side_effects
            result = side_effects.result or PendingTaskTurnResult(handled=False)
            result.events = [
                checkpoint_unavailable_fallback_event(
                    runtime="crm_agent_pending_interaction",
                    graph=PENDING_INTERACTION_CHECKPOINT_NS,
                ),
                *result.events,
            ]
            return result
        return side_effects.result or PendingTaskTurnResult(handled=False)

    def _classify_interaction(
        self,
        state: PendingInteractionGraphState,
        runtime: Runtime[PendingInteractionRuntimeContext],
    ) -> PendingInteractionGraphState:
        context = runtime.context
        if not context.task:
            return {"interaction_route": "end"}
        for spec in FIELD_INTERACTION_SPECS:
            if spec.predicate(context.task):
                return {"interaction_route": spec.route}
        if selection._is_business_selection_task(context.task):
            return {"interaction_route": "business_choice"}
        if selection._is_customer_selection_task(context.task):
            return {"interaction_route": "customer_choice"}
        return {"interaction_route": "end"}

    def _route_after_classification(self, state: PendingInteractionGraphState) -> str:
        route = state.get("interaction_route")
        if route in FIELD_INTERACTION_ROUTES or route in {"business_choice", "customer_choice"}:
            return route
        return "end"

    def _field_interaction_node(self, spec: FieldInteractionSpec) -> PendingInteractionNode:
        async def node(
            state: PendingInteractionGraphState,
            runtime: Runtime[PendingInteractionRuntimeContext],
        ) -> PendingInteractionGraphState:
            return await self._apply_field_node(runtime, spec.collector_factory(), spec.pending_event)

        return node

    async def _apply_field_node(
        self,
        runtime: Runtime[PendingInteractionRuntimeContext],
        collector: FieldCollector,
        pending_event: str,
    ) -> PendingInteractionGraphState:
        context = runtime.context
        result = PendingTaskTurnResult(handled=False)
        if context.task:
            ready, assistant_content = await collector(
                context.db,
                context.task,
                choice_resolution.append_structured_form_values(context.content, context.interaction_metadata),
            )
            result = _field_collection_result(context.task, ready, assistant_content, pending_event)
            context.side_effects.result = result
        return {
            "field_result": _result_projection(result),
            "result_projection": _result_projection(result),
            "events": _events(result.events),
        }

    async def _select_business(
        self,
        state: PendingInteractionGraphState,
        runtime: Runtime[PendingInteractionRuntimeContext],
    ) -> PendingInteractionGraphState:
        context = runtime.context
        result = PendingTaskTurnResult(handled=False)
        if context.task:
            selected, assistant_content = await selection._apply_business_selection(
                context.db,
                context.task,
                context.content,
                team_id=context.team_id,
                user_id=context.user_id,
                session_id=context.session_id,
                metadata=context.interaction_metadata,
            )
            result = PendingTaskTurnResult(
                handled=True,
                assistant_content=assistant_content,
                remember_pending_task=True,
                events=[
                    {
                        "event": "business_selected" if selected else "business_selection_failed",
                        "task_id": getattr(context.task, "id", None),
                        "content": assistant_content,
                        "selected": selected,
                    },
                    {"event": "final", "content": assistant_content},
                ],
            )
        context.side_effects.result = result
        return {
            "business_choice_result": _result_projection(result),
            "result_projection": _result_projection(result),
            "events": _events(result.events),
        }

    async def _select_customer(
        self,
        state: PendingInteractionGraphState,
        runtime: Runtime[PendingInteractionRuntimeContext],
    ) -> PendingInteractionGraphState:
        context = runtime.context
        result = PendingTaskTurnResult(handled=False)
        if context.task:
            customer, assistant_content = await selection._apply_customer_selection(
                context.db,
                context.task,
                context.content,
                team_id=context.team_id,
                user_id=context.user_id,
                session_id=context.session_id,
                authorization=context.authorization or "",
                metadata=context.interaction_metadata,
            )
            if customer:
                waiting_user = getattr(context.task, "status", None) == AgentTaskStatus.WAITING_USER
                result = PendingTaskTurnResult(
                    handled=True,
                    assistant_content=assistant_content,
                    selected_customer=coerce_json_dict(customer),
                    remember_pending_task=waiting_user,
                    clear_pending_task_id=None if waiting_user else _optional_object_id(context.task),
                    events=[
                        {
                            "event": "customer_selected",
                            "task_id": getattr(context.task, "id", None),
                            "customer": coerce_json_value(customer),
                            "content": assistant_content,
                        },
                        {"event": "final", "content": assistant_content},
                    ],
                )
            else:
                result = PendingTaskTurnResult(
                    handled=True,
                    assistant_content=assistant_content,
                    events=[
                        {
                            "event": "customer_selection_failed",
                            "task_id": getattr(context.task, "id", None),
                            "content": assistant_content,
                        },
                        {"event": "final", "content": assistant_content},
                    ],
                )
        context.side_effects.result = result
        return {
            "customer_choice_result": _result_projection(result),
            "result_projection": _result_projection(result),
            "events": _events(result.events),
        }


def build_pending_interaction_graph_config(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    task_id: int | None = None,
) -> RunnableConfig:
    task_key = str(task_id) if task_id is not None else "task"
    return {
        "configurable": {"thread_id": f"crm_agent_pending_interaction:{team_id}:{user_id}:{session_id}:{task_key}"},
        "metadata": {
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "task_id": task_id,
            "runtime": "crm_agent_pending_interaction",
            "runtime_namespace": PENDING_INTERACTION_CHECKPOINT_NS,
        },
    }


def _checkpoint_state_from_input(input_state: PendingInteractionGraphInput) -> PendingInteractionGraphState:
    state: PendingInteractionGraphState = {
        "team_id": int(input_state.get("team_id") or 0),
        "user_id": int(input_state.get("user_id") or 0),
        "session_id": int(input_state.get("session_id") or 0),
        "task_projection": _task_projection(input_state.get("task")),
        "content": str(input_state.get("content") or ""),
        "interaction_metadata": coerce_json_dict(input_state.get("interaction_metadata")),
        "events": [internal_graph_start_event("pending_interaction_graph_invocation_started")],
    }
    state["events"].extend(_events(input_state.get("events") or []))
    return state


def _runtime_context_from_input(
    input_state: PendingInteractionGraphInput,
    side_effects: PendingInteractionGraphSideEffects,
) -> PendingInteractionRuntimeContext:
    return PendingInteractionRuntimeContext(
        db=input_state.get("db"),
        task=input_state.get("task"),
        content=str(input_state.get("content") or ""),
        team_id=int(input_state.get("team_id") or 0),
        user_id=int(input_state.get("user_id") or 0),
        session_id=int(input_state.get("session_id") or 0),
        authorization=input_state.get("authorization"),
        interaction_metadata=coerce_json_dict(input_state.get("interaction_metadata")),
        side_effects=side_effects,
    )


def _result_projection(result: PendingTaskTurnResult) -> JSONDict:
    return {
        "handled": result.handled,
        "has_assistant_content": bool(result.assistant_content),
        "remember_pending_task": result.remember_pending_task,
        "clear_pending_task_id": coerce_json_value(result.clear_pending_task_id),
        "selected_customer": coerce_json_value(result.selected_customer),
        "event_count": len(result.events),
    }


def _field_collection_result(
    task: object,
    ready: bool,
    assistant_content: str,
    pending_event: str,
) -> PendingTaskTurnResult:
    return PendingTaskTurnResult(
        handled=True,
        assistant_content=assistant_content,
        remember_pending_task=True,
        events=[
            {
                "event": "confirmation_required" if ready else pending_event,
                "task_id": getattr(task, "id", None),
                "content": assistant_content,
                "payload": getattr(task, "input_json", None) or {},
            },
            {"event": "final", "content": assistant_content},
        ],
    )


def _task_projection(task: object) -> JSONDict:
    if not task:
        return {}
    projection: JSONDict = {}
    for key in ("id", "task_key", "status", "intent", "target_type", "target_id"):
        value = getattr(task, key, None)
        if value is not None:
            projection[key] = coerce_json_value(value)
    return projection


def _optional_object_id(value: object) -> int | None:
    raw_id = getattr(value, "id", None)
    if raw_id is None:
        return None
    try:
        return int(raw_id)
    except (TypeError, ValueError):
        return None


def _events(events: object) -> list[JSONDict]:
    if not isinstance(events, list):
        return []
    return [coerce_json_dict(event) for event in events if isinstance(event, dict)]


pending_interaction_graph_service = PendingInteractionGraphService(checkpointer=agent_checkpoint_saver)
