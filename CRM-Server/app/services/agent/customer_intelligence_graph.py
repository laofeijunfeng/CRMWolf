"""Customer intelligence LangGraph subgraph.

The graph loads customer context and memory to answer questions or record
committed business events in memory. It checkpoints execution and streams a
user-readable trace.
"""

from __future__ import annotations

import operator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Literal, Protocol, TypeAlias, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from app.core.database import SessionLocal
from app.services.agent.checkpointer import agent_checkpoint_saver
from app.services.agent.types import coerce_json_dict
from app.services.customer_context_answer_service import (
    customer_context_answer_service,
)
from app.services.customer_intelligence_context_service import (
    CustomerIntelligenceContextService,
    customer_intelligence_context_service,
)
from app.services.customer_intelligence_event_service import (
    CUSTOMER_INTELLIGENCE_COMMITTED_EVENT_TRIGGER_TYPES,
    CustomerIntelligenceEvent,
)
from app.services.customer_intelligence_trace_service import visible_trace_events
from app.services.customer_memory_store_service import (
    CUSTOMER_MEMORY_RETRIEVAL,
    CUSTOMER_MEMORY_SUMMARIES,
    CustomerMemoryStoreService,
    customer_memory_store_service,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Iterator

    from langchain_core.runnables import RunnableConfig
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.runtime import Runtime
    from sqlalchemy.orm import Session

CUSTOMER_INTELLIGENCE_CHECKPOINT_NS = "crm_agent_customer_intelligence"

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
JSONDict: TypeAlias = dict[str, JSONValue]

CustomerIntelligenceRoute = Literal[
    "answer_context",
    "write_memory",
    "skip",
]


_CUSTOMER_INTELLIGENCE_EVENT_RESET = "customer_intelligence_graph_invocation_started"


def merge_turn_scoped_events(left: list[JSONDict], right: list[JSONDict]) -> list[JSONDict]:
    """Keep checkpointed customer-intelligence events scoped to one invocation."""

    if right and right[0].get("event") == _CUSTOMER_INTELLIGENCE_EVENT_RESET:
        return list(right)
    return [*left, *right]


def internal_graph_start_event(event_name: str) -> JSONDict:
    return {"event": event_name, "internal": True}


def visible_graph_events(events: object) -> list[JSONDict]:
    if not isinstance(events, list):
        return []
    return [
        event
        for event in events
        if isinstance(event, dict) and event.get("event") != _CUSTOMER_INTELLIGENCE_EVENT_RESET
    ]


class CustomerIntelligenceGraphState(TypedDict, total=False):
    team_id: int
    user_id: int
    session_id: int
    event: JSONDict
    query_text: str
    customer_context: JSONDict
    customer_memory: JSONDict
    customer_context_answer: JSONDict
    assistant_content: str
    refresh_plan: JSONDict
    route: CustomerIntelligenceRoute
    visible_trace: Annotated[list[JSONDict], operator.add]
    events: Annotated[list[JSONDict], merge_turn_scoped_events]
    errors: Annotated[list[JSONDict], merge_turn_scoped_events]


class CustomerIntelligenceGraphInput(TypedDict, total=False):
    team_id: int
    user_id: int
    session_id: int
    event: CustomerIntelligenceEvent
    event_key: str
    query_text: str
    events: list[JSONDict]
    resume_existing_execution: bool


class CustomerIntelligenceGraphResult(CustomerIntelligenceGraphState, total=False):
    pass


class CustomerIntelligenceGraphStreamChunk(TypedDict, total=False):
    kind: Literal["event", "result"]
    event: JSONDict
    result: CustomerIntelligenceGraphResult



class CustomerContextAnswerGenerationService(Protocol):
    async def answer_with_metadata(
        self,
        db: Session,
        *,
        team_id: int,
        question: str,
        customer_context: JSONDict,
        customer_memory: JSONDict,
    ) -> object:
        pass


@dataclass
class CustomerIntelligenceRuntimeContext:
    team_id: int = 0
    user_id: int = 0
    session_id: int = 0


def build_customer_intelligence_thread_id(*, team_id: int, event_key: str) -> str:
    """Return the durable execution identity for one customer-intelligence event.

    Agent sessions and messages may be attached after execution starts, so they
    are observability metadata rather than part of checkpoint identity.
    """

    return f"crm_agent_customer_intelligence:{team_id}:{event_key}"


def build_customer_intelligence_graph_config(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    event_key: str,
) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": build_customer_intelligence_thread_id(
                team_id=team_id,
                event_key=event_key,
            ),
        },
        "metadata": {
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "event_key": event_key,
            "runtime": "crm_agent_customer_intelligence",
            "runtime_namespace": CUSTOMER_INTELLIGENCE_CHECKPOINT_NS,
        },
    }


class CustomerIntelligenceGraphService:
    def __init__(
        self,
        *,
        context_service: CustomerIntelligenceContextService | None = None,
        memory_store_service: CustomerMemoryStoreService | None = None,
        answer_service: CustomerContextAnswerGenerationService | None = None,
        checkpointer: object | None,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        self.context_service = context_service or customer_intelligence_context_service
        self.memory_store_service = memory_store_service or customer_memory_store_service
        self.answer_service = answer_service or cast(
            "CustomerContextAnswerGenerationService",
            customer_context_answer_service,
        )
        if checkpointer is None:
            raise ValueError("customer intelligence graph requires a checkpointer")
        self._session_factory = session_factory
        self._graph = self._build_graph(checkpointer)

    @contextmanager
    def _db_scope(self) -> Iterator[Session]:
        db = self._session_factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _build_graph(
        self,
        checkpointer: object,
    ) -> CompiledStateGraph[
        CustomerIntelligenceGraphState,
        CustomerIntelligenceRuntimeContext,
        CustomerIntelligenceGraphState,
        CustomerIntelligenceGraphState,
    ]:
        graph = StateGraph(
            CustomerIntelligenceGraphState,
            context_schema=CustomerIntelligenceRuntimeContext,
        )
        graph.add_node("normalize_event", self._normalize_event)
        graph.add_node("load_customer_context", self._load_customer_context)
        graph.add_node("retrieve_memory", self._retrieve_memory)
        graph.add_node("plan_refresh", self._plan_refresh)
        graph.add_node("answer_context", self._answer_context)
        graph.add_node("write_memory", self._write_memory)
        graph.add_node("emit_trace", self._emit_trace)
        graph.add_edge(START, "normalize_event")
        graph.add_conditional_edges(
            "normalize_event",
            self._route_after_normalize,
            {
                "load_context": "load_customer_context",
                "retrieve_memory": "retrieve_memory",
                "skip": "emit_trace",
            },
        )
        graph.add_edge(["load_customer_context", "retrieve_memory"], "plan_refresh")
        graph.add_conditional_edges(
            "plan_refresh",
            self._route_after_plan,
            {
                "write_memory": "write_memory",
                "answer_context": "answer_context",
                "emit_trace": "emit_trace",
            },
        )
        graph.add_edge("answer_context", "emit_trace")
        graph.add_edge("write_memory", "emit_trace")
        graph.add_edge("emit_trace", END)
        return graph.compile(checkpointer=checkpointer)

    async def stream_events(
        self,
        input_state: CustomerIntelligenceGraphInput,
    ) -> AsyncGenerator[CustomerIntelligenceGraphStreamChunk, None]:
        context = _runtime_context_from_input(input_state)
        event = input_state.get("event")
        if not isinstance(event, CustomerIntelligenceEvent):
            raise ValueError("customer intelligence execution requires an event")
        if _is_profile_refresh_event(event.to_dict()):
            raise ValueError(
                "客户档案更新必须通过 CustomerProfileProjectionWorkflow 执行"
            )
        checkpoint_state = _checkpoint_state_from_input(input_state)
        event_key = _event_key(checkpoint_state)
        graph_input: CustomerIntelligenceGraphState | None = checkpoint_state
        config = build_customer_intelligence_graph_config(
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
            event_key=event_key,
        )
        if input_state.get("resume_existing_execution") is True:
            snapshot = await self._graph.aget_state(config)
            if getattr(snapshot, "next", ()):
                graph_input = None
        async for chunk in self._stream_graph_run(self._graph, graph_input, context, config):
            yield chunk

    async def _stream_graph_run(
        self,
        graph: object,
        checkpoint_state: CustomerIntelligenceGraphState | None,
        context: CustomerIntelligenceRuntimeContext,
        config: RunnableConfig,
    ) -> AsyncGenerator[CustomerIntelligenceGraphStreamChunk, None]:
        if not hasattr(graph, "astream"):
            result = await graph.ainvoke(checkpoint_state, config, context=context)
            result = _with_visible_events(result)
            for event in visible_trace_events(result):
                yield {"kind": "event", "event": event}
            yield {"kind": "result", "result": result}
            return

        state: CustomerIntelligenceGraphState = {}
        emitted_trace_count = 0
        stream_interrupts: object | None = None
        async for stream_chunk in graph.astream(checkpoint_state, config, context=context, stream_mode="updates"):
            if not isinstance(stream_chunk, dict):
                continue
            if "__interrupt__" in stream_chunk:
                stream_interrupts = stream_chunk["__interrupt__"]
            for update in stream_chunk.values():
                if not isinstance(update, dict):
                    continue
                self._merge_stream_update(state, update)
                new_events = visible_trace_events(state)[emitted_trace_count:]
                for event in new_events:
                    yield {"kind": "event", "event": event}
                emitted_trace_count += len(new_events)

        result = await self._final_stream_state(graph, config, state, stream_interrupts)
        yield {"kind": "result", "result": _with_visible_events(result)}

    @staticmethod
    def _merge_stream_update(
        state: CustomerIntelligenceGraphState,
        update: CustomerIntelligenceGraphState,
    ) -> None:
        state_object = cast("dict[str, object]", state)
        for key, value in update.items():
            if key in {"visible_trace", "events", "errors"} and isinstance(value, list):
                current = state.get(key)
                if isinstance(current, list):
                    state_object[key] = [*current, *value]
                else:
                    state_object[key] = list(value)
                continue
            state_object[key] = value

    @staticmethod
    async def _final_stream_state(
        graph: object,
        config: RunnableConfig,
        streamed_state: CustomerIntelligenceGraphState,
        stream_interrupts: object | None,
    ) -> CustomerIntelligenceGraphResult:
        if not hasattr(graph, "aget_state"):
            raise RuntimeError("customer intelligence checkpoint state reader is unavailable")
        snapshot = await graph.aget_state(config)
        values = getattr(snapshot, "values", None)
        if not isinstance(values, dict):
            raise RuntimeError("customer intelligence checkpoint final state is unavailable")
        result = _result_with_interrupts(
            _merge_final_stream_state(
                streamed_state=streamed_state,
                checkpoint_values=cast("dict[str, object]", values),
            ),
            stream_interrupts,
        )
        interrupts = getattr(snapshot, "interrupts", None)
        if interrupts:
            return _result_with_interrupts(result, interrupts)
        return result

    def _normalize_event(
        self,
        state: CustomerIntelligenceGraphState,
        runtime: Runtime[CustomerIntelligenceRuntimeContext],  # noqa: ARG002
    ) -> CustomerIntelligenceGraphState:
        event = coerce_json_dict(state.get("event"))
        if not event:
            return {
                "route": "skip",
                "errors": [{"event": "customer_intelligence_event_missing"}],
                "visible_trace": [_trace_step("理解触发来源", "未识别到可处理的客户事件")],
            }
        return {
            "event": event,
            "visible_trace": [_trace_step("理解触发来源", _trigger_label(event))],
            "events": [{"event": "customer_intelligence_event_normalized", "trigger_type": event.get("trigger_type")}],
        }

    def _route_after_normalize(self, state: CustomerIntelligenceGraphState) -> str | list[str]:
        event = coerce_json_dict(state.get("event"))
        if not event.get("customer_id") or not event.get("team_id"):
            return "skip"
        return ["load_context", "retrieve_memory"]








    def _load_customer_context(
        self,
        state: CustomerIntelligenceGraphState,
        runtime: Runtime[CustomerIntelligenceRuntimeContext],
    ) -> CustomerIntelligenceGraphState:
        context = runtime.context
        event = coerce_json_dict(state.get("event"))
        customer_id = _positive_int(event.get("customer_id"))
        team_id = _positive_int(event.get("team_id")) or context.team_id
        if customer_id is None or team_id <= 0:
            return {
                "errors": [{"event": "customer_intelligence_context_failed", "message": "invalid_customer_event"}],
                "visible_trace": [_trace_step("读取客户上下文", "客户事件缺少必要信息")],
            }

        try:
            with self._db_scope() as db:
                customer_context = self.context_service.build_context(
                    db,
                    team_id=team_id,
                    customer_id=customer_id,
                    query_text=state.get("query_text") or _query_text_from_event(event),
                    evidence_limit=10,
                ).to_agent_payload()
        except Exception as exc:
            return {
                "errors": [
                    {
                        "event": "customer_intelligence_context_failed",
                        "message": exc.__class__.__name__,
                    }
                ],
                "visible_trace": [_trace_step("读取客户上下文", "未能读取客户上下文")],
            }
        retrieval = coerce_json_dict(customer_context.get("retrieval"))
        return {
            "customer_context": customer_context,
            "visible_trace": [_trace_step("读取客户上下文", _context_loaded_label(customer_context))],
            "events": [
                {
                    "event": "customer_intelligence_context_loaded",
                    "customer_id": customer_id,
                    "retrieval_status": retrieval.get("status"),
                }
            ],
        }

    def _retrieve_memory(
        self,
        state: CustomerIntelligenceGraphState,
        runtime: Runtime[CustomerIntelligenceRuntimeContext],
    ) -> CustomerIntelligenceGraphState:
        context = runtime.context
        event = coerce_json_dict(state.get("event"))
        customer_id = _positive_int(event.get("customer_id"))
        tenant_id = _positive_int(event.get("tenant_id")) or _positive_int(event.get("team_id")) or context.team_id
        if customer_id is None or tenant_id <= 0:
            return {
                "customer_memory": {},
                "events": [{"event": "customer_intelligence_memory_skipped", "reason": "invalid_customer_event"}],
            }
        try:
            with self._db_scope() as db:
                memory_payload = self.memory_store_service.build_context_payload(
                    db,
                    tenant_id=tenant_id,
                    customer_id=customer_id,
                    limit=20,
                )
        except Exception as exc:
            return {
                "customer_memory": {},
                "events": [
                    {
                        "event": "customer_intelligence_memory_skipped",
                        "reason": exc.__class__.__name__,
                    }
                ],
            }
        return {
            "customer_memory": memory_payload,
            "visible_trace": [_trace_step("读取客户记忆", _memory_loaded_label(memory_payload))],
            "events": [{"event": "customer_intelligence_memory_loaded", "customer_id": customer_id}],
        }

    def _plan_refresh(
        self,
        state: CustomerIntelligenceGraphState,
        runtime: Runtime[CustomerIntelligenceRuntimeContext],  # noqa: ARG002
    ) -> CustomerIntelligenceGraphState:
        event = coerce_json_dict(state.get("event"))
        trigger_type = str(event.get("trigger_type") or "")
        route = _route_for_event(event)
        refresh_plan = {
            "route": route,
            "requires_llm_extraction": False,
            "requires_review": False,
            "target_sections": _target_sections(route),
            "reason": _plan_reason(trigger_type, route),
        }
        return {
            "route": route,
            "refresh_plan": refresh_plan,
            "visible_trace": [_trace_step("制定更新计划", _refresh_plan_label(refresh_plan))],
            "events": [{"event": "customer_intelligence_refresh_planned", "route": route}],
        }

    def _route_after_plan(self, state: CustomerIntelligenceGraphState) -> str:
        route = state.get("route")
        if route == "write_memory":
            return "write_memory"
        if route == "answer_context":
            return "answer_context"
        return "emit_trace"

    async def _answer_context(
        self,
        state: CustomerIntelligenceGraphState,
        runtime: Runtime[CustomerIntelligenceRuntimeContext],
    ) -> CustomerIntelligenceGraphState:
        context = runtime.context
        event = coerce_json_dict(state.get("event"))
        customer_context = coerce_json_dict(state.get("customer_context"))
        customer_memory = coerce_json_dict(state.get("customer_memory"))
        question = str(state.get("query_text") or _query_text_from_event(event) or "").strip()
        team_id = _positive_int(event.get("team_id")) or context.team_id
        if team_id <= 0 or not customer_context:
            return {
                "customer_context_answer": {},
                "errors": [{"event": "customer_context_answer_failed", "message": "context_unavailable"}],
                "visible_trace": [_trace_step("生成客户回答", "客户资料不足，暂时无法整理回答")],  # noqa: RUF001
            }

        try:
            with self._db_scope() as db:
                envelope = await self.answer_service.answer_with_metadata(
                    db,
                    team_id=team_id,
                    question=question,
                    customer_context=customer_context,
                    customer_memory=customer_memory,
                )
        except Exception as exc:
            return {
                "customer_context_answer": {},
                "errors": [
                    {
                        "event": "customer_context_answer_failed",
                        "message": exc.__class__.__name__,
                    }
                ],
                "visible_trace": [_trace_step("生成客户回答", "客户回答暂不可用")],
            }

        result = _answer_result_payload(getattr(envelope, "result", {}))
        answer = str(result.get("answer") or "").strip()
        if not answer:
            return {
                "customer_context_answer": result,
                "events": [{"event": "customer_context_answer_empty"}],
                "visible_trace": [_trace_step("生成客户回答", "客户资料不足，暂时无法整理回答")],  # noqa: RUF001
            }

        answer_payload: JSONDict = {
            "answer": answer,
            "confidence": result.get("confidence") if isinstance(result.get("confidence"), int | float) else 0.0,
            "used_sections": _json_list(result.get("used_sections")),
            "missing_context": _json_list(result.get("missing_context")),
            "answer_mode": str(result.get("answer_mode") or "fallback"),
            "citations": _json_object_list(result.get("citations")),
            "source": str(getattr(envelope, "answer_source", "") or ""),
            "model": str(getattr(envelope, "model", "") or ""),
        }
        retrieval = coerce_json_dict(customer_context.get("retrieval"))
        if retrieval:
            answer_payload["retrieval"] = retrieval
        fallback_reason = getattr(envelope, "fallback_reason", None)
        if isinstance(fallback_reason, str) and fallback_reason:
            answer_payload["fallback_reason"] = fallback_reason
        citations_count = len(answer_payload["citations"]) if isinstance(answer_payload["citations"], list) else 0
        return {
            "customer_context_answer": answer_payload,
            "assistant_content": answer,
            "visible_trace": [_trace_step("生成客户回答", _context_answer_label(answer_payload))],
            "events": [
                {
                    "event": "customer_context_answer_generated",
                    "confidence": answer_payload["confidence"],
                    "answer_mode": answer_payload["answer_mode"],
                    "source": answer_payload["source"],
                    "used_sections": answer_payload["used_sections"],
                    "citations_count": citations_count,
                    "retrieval_status": retrieval.get("status"),
                    "retrieval_top_score": retrieval.get("top_score"),
                    "semantic_evidence_count": _json_list_len(customer_context.get("semantic_evidence")),
                }
            ],
        }

    def _write_memory(
        self,
        state: CustomerIntelligenceGraphState,
        runtime: Runtime[CustomerIntelligenceRuntimeContext],
    ) -> CustomerIntelligenceGraphState:
        context = runtime.context
        event = coerce_json_dict(state.get("event"))
        customer_context = coerce_json_dict(state.get("customer_context"))
        customer_id = _positive_int(event.get("customer_id"))
        tenant_id = _positive_int(event.get("tenant_id")) or _positive_int(event.get("team_id")) or context.team_id
        if customer_id is None or tenant_id <= 0:
            return {
                "errors": [{"event": "customer_intelligence_memory_write_failed", "message": "invalid_customer_event"}],
                "visible_trace": [_trace_step("更新客户记忆", "客户事件缺少必要信息")],
            }

        try:
            with self._db_scope() as db:
                self.memory_store_service.upsert_summary(
                    db,
                    tenant_id=tenant_id,
                    customer_id=customer_id,
                    key="latest_customer_intelligence_event",
                    value=_summary_memory_from_state(state),
                )
                retrieval_index = _retrieval_index_from_context(customer_context)
                if retrieval_index:
                    self.memory_store_service.upsert_retrieval_index(
                        db,
                        tenant_id=tenant_id,
                        customer_id=customer_id,
                        key="latest_evidence_refs",
                        value=retrieval_index,
                    )
                db.flush()
        except Exception as exc:
            return {
                "errors": [
                    {
                        "event": "customer_intelligence_memory_write_failed",
                        "message": exc.__class__.__name__,
                    }
                ],
                "visible_trace": [_trace_step("更新客户记忆", "客户记忆暂未更新")],
            }
        return {
            "visible_trace": [_trace_step("更新客户记忆", "已沉淀客户摘要和证据索引")],
            "events": [
                {
                    "event": "customer_intelligence_memory_written",
                    "customer_id": customer_id,
                    "sections": _written_memory_sections(retrieval_index=bool(retrieval_index)),
                }
            ],
        }

    def _emit_trace(
        self,
        state: CustomerIntelligenceGraphState,
        runtime: Runtime[CustomerIntelligenceRuntimeContext],  # noqa: ARG002
    ) -> CustomerIntelligenceGraphState:
        return {
            "events": [
                {
                    "event": "customer_intelligence_trace_ready",
                    "visible_trace": state.get("visible_trace") or [],
                }
            ]
        }








def _checkpoint_state_from_input(input_state: CustomerIntelligenceGraphInput) -> CustomerIntelligenceGraphState:
    event = input_state.get("event")
    event_payload = event.to_dict() if isinstance(event, CustomerIntelligenceEvent) else {}
    prior_events = input_state.get("events") if isinstance(input_state.get("events"), list) else []
    return {
        "team_id": int(input_state.get("team_id") or event_payload.get("team_id") or 0),
        "user_id": int(input_state.get("user_id") or 0),
        "session_id": int(input_state.get("session_id") or 0),
        "event": event_payload,
        "query_text": str(input_state.get("query_text") or event_payload.get("summary") or ""),
        "customer_context": {},
        "customer_memory": {},
        "customer_context_answer": {},
        "assistant_content": "",
        "refresh_plan": {},
        "route": "skip",
        "visible_trace": [],
        "events": [
            internal_graph_start_event("customer_intelligence_graph_invocation_started"),
            *[coerce_json_dict(event) for event in prior_events if isinstance(event, dict)],
        ],
        "errors": [internal_graph_start_event("customer_intelligence_graph_invocation_started")],
    }


def _with_visible_events(result: CustomerIntelligenceGraphResult) -> CustomerIntelligenceGraphResult:
    projected: CustomerIntelligenceGraphResult = dict(result)
    projected["events"] = visible_graph_events(projected.get("events"))
    projected["errors"] = visible_graph_events(projected.get("errors"))
    return projected


def _merge_final_stream_state(
    *,
    streamed_state: CustomerIntelligenceGraphState,
    checkpoint_values: dict[str, object],
) -> CustomerIntelligenceGraphState:
    merged: dict[str, object] = dict(streamed_state)
    for key, value in checkpoint_values.items():
        streamed_value = merged.get(key)
        if _should_keep_streamed_final_value(streamed_value, value):
            continue
        merged[key] = value
    return cast("CustomerIntelligenceGraphState", merged)


def _should_keep_streamed_final_value(streamed_value: object, checkpoint_value: object) -> bool:
    if streamed_value is None:
        return False
    if checkpoint_value is None:
        return True
    if isinstance(checkpoint_value, str):
        return not checkpoint_value.strip() and isinstance(streamed_value, str) and bool(streamed_value.strip())
    if isinstance(checkpoint_value, list):
        return not checkpoint_value and isinstance(streamed_value, list) and bool(streamed_value)
    if isinstance(checkpoint_value, dict):
        return not checkpoint_value and isinstance(streamed_value, dict) and bool(streamed_value)
    return False


def _runtime_context_from_input(input_state: CustomerIntelligenceGraphInput) -> CustomerIntelligenceRuntimeContext:
    return CustomerIntelligenceRuntimeContext(
        team_id=int(input_state.get("team_id") or 0),
        user_id=int(input_state.get("user_id") or 0),
        session_id=int(input_state.get("session_id") or 0),
    )


def _event_key(state: CustomerIntelligenceGraphState) -> str:
    event = coerce_json_dict(state.get("event"))
    event_key = event.get("event_key")
    return event_key if isinstance(event_key, str) and event_key else "unknown"


def _positive_int(value: object) -> int | None:
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


_PROFILE_REFRESH_TRIGGER_TYPES = frozenset({
    "manual_refresh_requested",
    "customer_intelligence_batch_rebuild_requested",
    "customer_intelligence_historical_backfill_requested",
    "customer_intelligence_reconciliation_requested",
    "customer_created",
    "customer_converted_from_lead",
})


def _is_profile_refresh_event(event: JSONDict) -> bool:
    return str(event.get("trigger_type") or "") in _PROFILE_REFRESH_TRIGGER_TYPES


def _route_for_event(event: JSONDict) -> CustomerIntelligenceRoute:
    return _route_for_trigger(str(event.get("trigger_type") or ""))


def _route_for_trigger(trigger_type: str) -> CustomerIntelligenceRoute:
    if trigger_type == "agent_customer_question":
        return "answer_context"
    if trigger_type in CUSTOMER_INTELLIGENCE_COMMITTED_EVENT_TRIGGER_TYPES:
        return "write_memory"
    return "skip"


def _target_sections(route: CustomerIntelligenceRoute) -> list[str]:
    if route == "answer_context":
        return ["customer_context"]
    if route == "write_memory":
        return ["memory"]
    return []






def _query_text_from_event(event: JSONDict) -> str:
    summary = event.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary
    payload = coerce_json_dict(event.get("payload"))
    question = payload.get("question")
    if isinstance(question, str) and question.strip():
        return question
    return str(event.get("trigger_type") or "")


def _trigger_label(event: JSONDict) -> str:
    labels = {
        "customer_created": "识别到新建客户",
        "customer_converted_from_lead": "识别到线索转客户",
        "customer_activity_created": "识别到新的客户跟进",
        "customer_activity_updated": "识别到客户跟进更新",
        "customer_activity_deleted": "识别到客户跟进删除",
        "customer_contact_created": "识别到新的客户联系人",
        "customer_contact_updated": "识别到客户联系人更新",
        "customer_contact_deleted": "识别到客户联系人删除",
        "customer_business_object_created": "识别到新的业务信息",
        "customer_business_object_updated": "识别到业务信息更新",
        "customer_business_object_deleted": "识别到业务信息删除",
                "deal_journey_event_recorded": "识别到业务流程进展",
        "manual_refresh_requested": "识别到手动刷新请求",
        "customer_intelligence_batch_rebuild_requested": "识别到批量重建请求",
        "customer_intelligence_historical_backfill_requested": "识别到历史客户补档任务",
        "customer_intelligence_reconciliation_requested": "对账发现客户档案存在未纳入的业务变化",
        "agent_customer_question": "识别到客户信息查询",
    }
    trigger_type = str(event.get("trigger_type") or "")
    return labels.get(trigger_type, "识别到客户相关事件")


def _context_loaded_label(customer_context: JSONDict) -> str:
    strong_context = coerce_json_dict(customer_context.get("strong_context"))
    customer = coerce_json_dict(strong_context.get("customer"))
    customer_name = customer.get("account_name")
    if isinstance(customer_name, str) and customer_name:
        return f"已读取「{customer_name}」的客户、商机、合同、回款和近期活动"
    return "已读取客户上下文"


def _memory_loaded_label(customer_memory: JSONDict) -> str:
    summaries = customer_memory.get("summaries")
    preferences = customer_memory.get("preferences")
    retrieval = customer_memory.get("retrieval")
    count = _json_list_len(summaries) + _json_list_len(preferences) + _json_list_len(retrieval)
    if count <= 0:
        return "暂无可复用的客户长期记忆"
    return f"已读取 {count} 条客户长期记忆"


def _plan_reason(trigger_type: str, route: CustomerIntelligenceRoute) -> str:
    if route == "answer_context":
        return "本次只需要支撑客户问答，不自动刷新档案"  # noqa: RUF001
    if route == "write_memory":
        return "生成结果已产生，作为客户长期记忆和语义证据索引"  # noqa: RUF001
    return f"暂不处理该客户智能事件: {trigger_type}"


def _refresh_plan_label(refresh_plan: JSONDict) -> str:
    route = cast("CustomerIntelligenceRoute", refresh_plan.get("route") or "skip")
    labels = {
        "answer_context": "准备用于回答客户问题",
        "write_memory": "准备沉淀为客户记忆",
        "skip": "本次不需要刷新客户档案",
    }
    return labels[route]


def _context_answer_label(answer_payload: JSONDict) -> str:
    confidence = _float_value(answer_payload.get("confidence"))
    answer_mode = str(answer_payload.get("answer_mode") or "")
    citations = _json_list(answer_payload.get("citations"))
    retrieval = coerce_json_dict(answer_payload.get("retrieval"))
    retrieval_status = retrieval.get("status")
    if answer_mode == "grounded" and citations:
        return f"已基于客户档案、业务上下文和检索证据整理回答，置信度 {confidence:.0%}"  # noqa: RUF001
    if answer_mode == "degraded":
        return f"已基于客户强事实降级整理回答，检索状态 {retrieval_status or '不可用'}，置信度 {confidence:.0%}"  # noqa: RUF001
    if answer_mode == "insufficient":
        return f"客户资料不足，已标记缺失上下文，置信度 {confidence:.0%}"  # noqa: RUF001
    return f"已整理客户回答，置信度 {confidence:.0%}"  # noqa: RUF001


def _answer_result_payload(result: object) -> JSONDict:
    model_dump = getattr(result, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(mode="json", exclude_none=True)
        return coerce_json_dict(payload)
    return coerce_json_dict(result)


def _trace_step(title: str, detail: str) -> JSONDict:
    return {"event": "customer_intelligence_step", "title": title, "content": detail}


def _result_with_interrupts(
    state: CustomerIntelligenceGraphState,
    interrupts: object | None,
) -> CustomerIntelligenceGraphResult:
    result_object: dict[str, object] = dict(state)
    if interrupts:
        result_object["__interrupt__"] = interrupts
    return cast("CustomerIntelligenceGraphResult", result_object)


def _summary_memory_from_state(state: CustomerIntelligenceGraphState) -> JSONDict:
    event = coerce_json_dict(state.get("event"))
    refresh_plan = coerce_json_dict(state.get("refresh_plan"))
    source = coerce_json_dict(event.get("source"))
    return {
        "trigger_type": str(event.get("trigger_type") or ""),
        "summary": str(event.get("summary") or ""),
        "route": str(refresh_plan.get("route") or state.get("route") or "skip"),
        "target_sections": _json_list(refresh_plan.get("target_sections")),
        "source": {
            "source_type": str(source.get("source_type") or ""),
            "source_object_id": str(source.get("source_object_id") or ""),
            "business_object_type": str(source.get("business_object_type") or ""),
            "business_object_id": str(source.get("business_object_id") or ""),
        },
        "event_key": str(event.get("event_key") or ""),
        "thread_id": str(event.get("thread_id") or ""),
    }


def _retrieval_index_from_context(customer_context: JSONDict) -> JSONDict:
    evidence_items = customer_context.get("semantic_evidence")
    if not isinstance(evidence_items, list):
        return {}
    refs: list[JSONDict] = []
    for item in evidence_items[:10]:
        evidence = coerce_json_dict(item)
        evidence_id = evidence.get("evidence_id") or evidence.get("document_key") or evidence.get("id")
        if not evidence_id:
            continue
        refs.append(
            {
                "evidence_id": str(evidence_id),
                "source_type": str(evidence.get("source_type") or ""),
                "business_object_type": str(evidence.get("business_object_type") or ""),
                "business_object_id": str(evidence.get("business_object_id") or ""),
                "score": evidence.get("score") if isinstance(evidence.get("score"), int | float) else None,
                "title": str(evidence.get("title") or ""),
            }
        )
    if not refs:
        return {}
    return {
        "evidence_refs": refs,
        "source": "qdrant",
        "policy": "只保存证据引用，不复制向量文本",  # noqa: RUF001
    }


def _written_memory_sections(*, retrieval_index: bool) -> list[JSONValue]:
    sections: list[JSONValue] = [CUSTOMER_MEMORY_SUMMARIES]
    if retrieval_index:
        sections.append(CUSTOMER_MEMORY_RETRIEVAL)
    return sections


def _json_list(value: object) -> list[JSONValue]:
    if not isinstance(value, list):
        return []
    return [item if isinstance(item, str | int | float | bool) or item is None else str(item) for item in value]


def _json_list_len(value: object) -> int:
    return len(value) if isinstance(value, list) else 0


def _json_object_list(value: object) -> list[JSONDict]:
    if not isinstance(value, list):
        return []
    items: list[JSONDict] = []
    for item in value:
        if isinstance(item, dict):
            items.append(coerce_json_dict(item))
    return items


def _float_value(value: object) -> float:
    if isinstance(value, int | float):
        return max(0.0, min(1.0, float(value)))
    if isinstance(value, str):
        try:
            return max(0.0, min(1.0, float(value.strip())))
        except ValueError:
            return 0.0
    return 0.0


customer_intelligence_graph_service = CustomerIntelligenceGraphService(checkpointer=agent_checkpoint_saver)
