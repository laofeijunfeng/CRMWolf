"""Customer intelligence LangGraph subgraph.

This graph is the runtime boundary for customer intelligence updates. It keeps
business writes deterministic while allowing LLM-backed nodes to propose
structured customer facts. Checkpointed state, Store memory, fact persistence,
and user-readable trace projection all stay behind this typed contract.
"""

from __future__ import annotations

import operator
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, AsyncGenerator, Literal, Protocol, TypeAlias, TypedDict, cast

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.services.agent.checkpointer import (
    agent_checkpoint_saver,
    is_checkpoint_storage_error,
    with_checkpoint_unavailable_fallback_event,
)
from app.services.agent.state import internal_graph_start_event, merge_turn_scoped_events, visible_graph_events
from app.services.agent.types import coerce_json_dict
from app.services.customer_brief_service import customer_brief_service
from app.services.customer_context_answer_service import (
    customer_context_answer_service,
)
from app.services.customer_fact_extraction_service import (
    CustomerFactExtractionResult,
    CustomerFactExtractionService,
    customer_fact_extraction_service,
)
from app.services.customer_fact_service import (
    CustomerFactCandidateInput,
    CustomerFactInput,
    CustomerFactReviewAuditInput,
    CustomerFactService,
    CustomerFactSourceInput,
    CustomerFactType,
    customer_fact_service,
)
from app.services.customer_intelligence_context_service import (
    CustomerIntelligenceContextService,
    customer_intelligence_context_service,
)
from app.services.customer_intelligence_event_service import CustomerIntelligenceEvent
from app.services.customer_intelligence_trace_service import visible_trace_events
from app.services.customer_memory_store_service import (
    CUSTOMER_MEMORY_FACTS,
    CUSTOMER_MEMORY_RETRIEVAL,
    CUSTOMER_MEMORY_SUMMARIES,
    CustomerMemoryStoreService,
    customer_memory_store_service,
)
from app.services.customer_profile_service import customer_profile_service

CUSTOMER_INTELLIGENCE_CHECKPOINT_NS = "crm_agent_customer_intelligence"

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
JSONDict: TypeAlias = dict[str, JSONValue]

CustomerIntelligenceRoute = Literal[
    "answer_context",
    "refresh_profile",
    "refresh_brief",
    "write_memory",
    "skip",
]
FactAction: TypeAlias = Literal["upsert", "review", "ignore"]
FactReviewDecision: TypeAlias = Literal["APPROVED", "REJECTED", "CANCELLED"]


class CustomerIntelligenceGraphState(TypedDict, total=False):
    team_id: int
    user_id: int
    session_id: int
    event: JSONDict
    query_text: str
    customer_context: JSONDict
    customer_memory: JSONDict
    extracted_customer_facts: list[JSONDict]
    customer_fact_review: JSONDict
    resume_payload: JSONDict
    persisted_customer_fact_refs: list[JSONDict]
    profile_refresh_result: JSONDict
    brief_refresh_result: JSONDict
    customer_context_answer: JSONDict
    assistant_content: str
    retrieval_state: JSONDict
    refresh_plan: JSONDict
    route: CustomerIntelligenceRoute
    visible_trace: Annotated[list[JSONDict], operator.add]
    events: Annotated[list[JSONDict], merge_turn_scoped_events]
    errors: Annotated[list[JSONDict], operator.add]


class CustomerIntelligenceGraphInput(TypedDict, total=False):
    # Deprecated compatibility hook. Production callers should let graph nodes
    # acquire short sessions so execution does not hold one transaction across
    # multiple LangGraph nodes and business side effects.
    db: Session
    team_id: int
    user_id: int
    session_id: int
    event: CustomerIntelligenceEvent
    query_text: str
    events: list[JSONDict]
    resume_payload: JSONDict


class CustomerIntelligenceGraphResult(CustomerIntelligenceGraphState, total=False):
    pass


class CustomerIntelligenceGraphStreamChunk(TypedDict, total=False):
    kind: Literal["event", "result"]
    event: JSONDict
    result: CustomerIntelligenceGraphResult


class CustomerIntelligenceResumeInput(TypedDict, total=False):
    # Deprecated compatibility hook. Production callers should not pass
    # request-scoped sessions into checkpointed graph execution.
    db: Session
    team_id: int
    user_id: int
    session_id: int
    event_key: str
    resume_payload: JSONDict


class CustomerProfileRefreshService(Protocol):
    async def generate_profile(
        self,
        customer_id: int,
        account_name: str,
        source_lead_id: int | None = None,
        team_id: int | None = None,
    ) -> JSONDict:
        pass


class CustomerBriefRefreshService(Protocol):
    async def generate_brief(self, customer_id: int, team_id: int) -> JSONDict:
        pass


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
    db: Session | None = None
    team_id: int = 0
    user_id: int = 0
    session_id: int = 0


def build_customer_intelligence_thread_id(*, team_id: int, user_id: int, session_id: int, event_key: str) -> str:
    return f"crm_agent_customer_intelligence:{team_id}:{user_id}:{session_id}:{event_key}"


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
                user_id=user_id,
                session_id=session_id,
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
        fact_extraction_service: CustomerFactExtractionService | None = None,
        fact_service: CustomerFactService | None = None,
        profile_refresh_service: CustomerProfileRefreshService | None = None,
        brief_refresh_service: CustomerBriefRefreshService | None = None,
        answer_service: CustomerContextAnswerGenerationService | None = None,
        checkpointer: object | None = None,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        self.context_service = context_service or customer_intelligence_context_service
        self.memory_store_service = memory_store_service or customer_memory_store_service
        self.fact_extraction_service = fact_extraction_service or customer_fact_extraction_service
        self.fact_service = fact_service or customer_fact_service
        self.profile_refresh_service = profile_refresh_service or cast(
            CustomerProfileRefreshService,
            customer_profile_service,
        )
        self.brief_refresh_service = brief_refresh_service or cast(
            CustomerBriefRefreshService,
            customer_brief_service,
        )
        self.answer_service = answer_service or cast(
            CustomerContextAnswerGenerationService,
            customer_context_answer_service,
        )
        self._session_factory = session_factory
        self._checkpoint_enabled = checkpointer is not None
        self._graph = self._build_graph(checkpointer)
        self._fallback_graph = self._build_graph(None)

    @contextmanager
    def _db_scope(self, context: CustomerIntelligenceRuntimeContext) -> Iterator[Session]:
        if context.db is not None:
            yield context.db
            return
        db = self._session_factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _build_graph(self, checkpointer: object | None):
        graph = StateGraph(
            CustomerIntelligenceGraphState,
            context_schema=CustomerIntelligenceRuntimeContext,
        )
        graph.add_node("normalize_event", self._normalize_event)
        graph.add_node("load_customer_context", self._load_customer_context)
        graph.add_node("retrieve_memory", self._retrieve_memory)
        graph.add_node("plan_refresh", self._plan_refresh)
        graph.add_node("extract_facts", self._extract_facts)
        graph.add_node("review_facts", self._review_facts)
        graph.add_node("wait_fact_review", self._wait_fact_review)
        graph.add_node("persist_facts", self._persist_facts)
        graph.add_node("refresh_profile_fields", self._refresh_profile_fields)
        graph.add_node("refresh_brief_fields", self._refresh_brief_fields)
        graph.add_node("answer_context", self._answer_context)
        graph.add_node("write_memory", self._write_memory)
        graph.add_node("emit_trace", self._emit_trace)
        graph.add_edge(START, "normalize_event")
        graph.add_conditional_edges(
            "normalize_event",
            self._route_after_normalize,
            {
                "load_context": "load_customer_context",
                "skip": "emit_trace",
            },
        )
        graph.add_edge("load_customer_context", "retrieve_memory")
        graph.add_edge("retrieve_memory", "plan_refresh")
        graph.add_conditional_edges(
            "plan_refresh",
            self._route_after_plan,
            {
                "extract_facts": "extract_facts",
                "write_memory": "write_memory",
                "answer_context": "answer_context",
                "emit_trace": "emit_trace",
            },
        )
        graph.add_edge("extract_facts", "review_facts")
        graph.add_conditional_edges(
            "review_facts",
            self._route_after_review_facts,
            {
                "wait_fact_review": "wait_fact_review",
                "persist_facts": "persist_facts",
            },
        )
        graph.add_edge("wait_fact_review", "persist_facts")
        graph.add_conditional_edges(
            "persist_facts",
            self._route_after_persist_facts,
            {
                "refresh_profile_fields": "refresh_profile_fields",
                "refresh_brief_fields": "refresh_brief_fields",
                "write_memory": "write_memory",
            },
        )
        graph.add_edge("refresh_profile_fields", "refresh_brief_fields")
        graph.add_edge("refresh_brief_fields", "write_memory")
        graph.add_edge("answer_context", "emit_trace")
        graph.add_edge("write_memory", "emit_trace")
        graph.add_edge("emit_trace", END)
        if checkpointer is None:
            return graph.compile()
        return graph.compile(checkpointer=checkpointer)

    async def run(self, input_state: CustomerIntelligenceGraphInput) -> CustomerIntelligenceGraphResult:
        checkpoint_state = _checkpoint_state_from_input(input_state)
        context = _runtime_context_from_input(input_state)
        config = build_customer_intelligence_graph_config(
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
            event_key=_event_key(checkpoint_state),
        )
        try:
            return _with_visible_events(await self._graph.ainvoke(checkpoint_state, config, context=context))
        except SQLAlchemyError as exc:
            if not self._checkpoint_enabled or not is_checkpoint_storage_error(exc):
                raise
            result = _with_visible_events(await self._fallback_graph.ainvoke(checkpoint_state, config, context=context))
            return with_checkpoint_unavailable_fallback_event(
                result,
                runtime="crm_agent_customer_intelligence",
                graph=CUSTOMER_INTELLIGENCE_CHECKPOINT_NS,
            )

    async def stream_run(
        self,
        input_state: CustomerIntelligenceGraphInput,
    ) -> AsyncGenerator[CustomerIntelligenceGraphStreamChunk, None]:
        checkpoint_state = _checkpoint_state_from_input(input_state)
        context = _runtime_context_from_input(input_state)
        config = build_customer_intelligence_graph_config(
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
            event_key=_event_key(checkpoint_state),
        )
        try:
            async for chunk in self._stream_graph_run(self._graph, checkpoint_state, context, config):
                yield chunk
        except SQLAlchemyError as exc:
            if not self._checkpoint_enabled or not is_checkpoint_storage_error(exc):
                raise
            fallback_event = with_checkpoint_unavailable_fallback_event(
                {"events": []},
                runtime="crm_agent_customer_intelligence",
                graph=CUSTOMER_INTELLIGENCE_CHECKPOINT_NS,
            ).get("events", [])
            for event in fallback_event:
                yield {"kind": "event", "event": coerce_json_dict(event)}
            async for chunk in self._stream_graph_run(self._fallback_graph, checkpoint_state, context, config):
                yield chunk

    async def resume_review(self, input_state: CustomerIntelligenceResumeInput) -> CustomerIntelligenceGraphResult:
        context = CustomerIntelligenceRuntimeContext(
            db=input_state.get("db"),
            team_id=int(input_state.get("team_id") or 0),
            user_id=int(input_state.get("user_id") or 0),
            session_id=int(input_state.get("session_id") or 0),
        )
        event_key = str(input_state.get("event_key") or "")
        config = build_customer_intelligence_graph_config(
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
            event_key=event_key,
        )
        return await self._graph.ainvoke(
            Command(resume=coerce_json_dict(input_state.get("resume_payload"))),
            config,
            context=context,
        )

    async def stream_resume_review(
        self,
        input_state: CustomerIntelligenceResumeInput,
    ) -> AsyncGenerator[CustomerIntelligenceGraphStreamChunk, None]:
        context = CustomerIntelligenceRuntimeContext(
            db=input_state.get("db"),
            team_id=int(input_state.get("team_id") or 0),
            user_id=int(input_state.get("user_id") or 0),
            session_id=int(input_state.get("session_id") or 0),
        )
        event_key = str(input_state.get("event_key") or "")
        config = build_customer_intelligence_graph_config(
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
            event_key=event_key,
        )
        command = Command(resume=coerce_json_dict(input_state.get("resume_payload")))
        async for chunk in self._stream_graph_run(self._graph, command, context, config):
            yield chunk

    async def _stream_graph_run(
        self,
        graph: object,
        checkpoint_state: CustomerIntelligenceGraphState | Command,
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
        state_object = cast(dict[str, object], state)
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
            return _result_with_interrupts(streamed_state, stream_interrupts)
        try:
            snapshot = await graph.aget_state(config)
        except (AttributeError, RuntimeError, ValueError):
            return _result_with_interrupts(streamed_state, stream_interrupts)
        values = getattr(snapshot, "values", None)
        if not isinstance(values, dict):
            return _result_with_interrupts(streamed_state, stream_interrupts)
        result = _result_with_interrupts(
            _merge_final_stream_state(
                streamed_state=streamed_state,
                checkpoint_values=cast(dict[str, object], values),
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
        runtime: Runtime[CustomerIntelligenceRuntimeContext],
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

    def _route_after_normalize(self, state: CustomerIntelligenceGraphState) -> str:
        event = coerce_json_dict(state.get("event"))
        if not event.get("customer_id") or not event.get("team_id"):
            return "skip"
        return "load_context"

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
            with self._db_scope(context) as db:
                customer_context = self.context_service.build_context(
                    db,
                    team_id=team_id,
                    customer_id=customer_id,
                    query_text=state.get("query_text") or _query_text_from_event(event),
                    evidence_limit=10,
                ).to_agent_payload()
        except Exception as exc:
            return {
                "errors": [{
                    "event": "customer_intelligence_context_failed",
                    "message": exc.__class__.__name__,
                }],
                "visible_trace": [_trace_step("读取客户上下文", "未能读取客户上下文")],
            }
        retrieval = coerce_json_dict(customer_context.get("retrieval"))
        return {
            "customer_context": customer_context,
            "retrieval_state": retrieval,
            "visible_trace": [_trace_step("读取客户上下文", _context_loaded_label(customer_context))],
            "events": [{
                "event": "customer_intelligence_context_loaded",
                "customer_id": customer_id,
                "retrieval_status": retrieval.get("status"),
            }],
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
            with self._db_scope(context) as db:
                memory_payload = self.memory_store_service.build_context_payload(
                    db,
                    tenant_id=tenant_id,
                    customer_id=customer_id,
                    limit=20,
                )
        except Exception as exc:
            return {
                "customer_memory": {},
                "events": [{
                    "event": "customer_intelligence_memory_skipped",
                    "reason": exc.__class__.__name__,
                }],
            }
        return {
            "customer_memory": memory_payload,
            "visible_trace": [_trace_step("读取客户记忆", _memory_loaded_label(memory_payload))],
            "events": [{"event": "customer_intelligence_memory_loaded", "customer_id": customer_id}],
        }

    def _plan_refresh(
        self,
        state: CustomerIntelligenceGraphState,
        runtime: Runtime[CustomerIntelligenceRuntimeContext],
    ) -> CustomerIntelligenceGraphState:
        event = coerce_json_dict(state.get("event"))
        trigger_type = str(event.get("trigger_type") or "")
        route = _route_for_event(event)
        refresh_plan = {
            "route": route,
            "requires_llm_extraction": route in {"refresh_profile", "refresh_brief", "write_memory"},
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
        if route in {"refresh_profile", "refresh_brief", "write_memory"}:
            refresh_plan = coerce_json_dict(state.get("refresh_plan"))
            if refresh_plan.get("requires_llm_extraction") is True:
                return "extract_facts"
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
                "visible_trace": [_trace_step("生成客户回答", "客户资料不足，暂时无法整理回答")],
            }

        try:
            with self._db_scope(context) as db:
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
                "errors": [{
                    "event": "customer_context_answer_failed",
                    "message": exc.__class__.__name__,
                }],
                "visible_trace": [_trace_step("生成客户回答", "客户回答暂不可用")],
            }

        result = _answer_result_payload(getattr(envelope, "result", {}))
        answer = str(result.get("answer") or "").strip()
        if not answer:
            return {
                "customer_context_answer": result,
                "events": [{"event": "customer_context_answer_empty"}],
                "visible_trace": [_trace_step("生成客户回答", "客户资料不足，暂时无法整理回答")],
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
            "events": [{
                "event": "customer_context_answer_generated",
                "confidence": answer_payload["confidence"],
                "answer_mode": answer_payload["answer_mode"],
                "source": answer_payload["source"],
                "used_sections": answer_payload["used_sections"],
                "citations_count": citations_count,
                "retrieval_status": retrieval.get("status"),
                "retrieval_top_score": retrieval.get("top_score"),
                "semantic_evidence_count": _json_list_len(customer_context.get("semantic_evidence")),
            }],
        }

    async def _extract_facts(
        self,
        state: CustomerIntelligenceGraphState,
        runtime: Runtime[CustomerIntelligenceRuntimeContext],
    ) -> CustomerIntelligenceGraphState:
        context = runtime.context
        event = coerce_json_dict(state.get("event"))
        customer_context = coerce_json_dict(state.get("customer_context"))
        customer_memory = coerce_json_dict(state.get("customer_memory"))
        team_id = _positive_int(event.get("team_id")) or context.team_id
        if team_id <= 0 or not customer_context:
            return {
                "extracted_customer_facts": [],
                "events": [{"event": "customer_intelligence_fact_extraction_skipped", "reason": "context_unavailable"}],
                "visible_trace": [_trace_step("提炼客户事实", "缺少可提炼的客户上下文")],
            }

        try:
            with self._db_scope(context) as db:
                result = await self.fact_extraction_service.extract(
                    db,
                    team_id=team_id,
                    event=event,
                    customer_context=customer_context,
                    customer_memory=customer_memory,
                )
        except Exception as exc:
            return {
                "extracted_customer_facts": [],
                "errors": [{
                    "event": "customer_intelligence_fact_extraction_failed",
                    "message": exc.__class__.__name__,
                }],
                "visible_trace": [_trace_step("提炼客户事实", "客户事实提炼暂不可用，已继续处理客户记忆")],
            }

        facts = _extractable_facts(result)
        return {
            "extracted_customer_facts": facts,
            "visible_trace": [_trace_step("提炼客户事实", _fact_extraction_label(facts))],
            "events": [{
                "event": "customer_intelligence_facts_extracted",
                "fact_count": len(facts),
                "summary": result.summary,
            }],
        }

    def _review_facts(
        self,
        state: CustomerIntelligenceGraphState,
        runtime: Runtime[CustomerIntelligenceRuntimeContext],
    ) -> CustomerIntelligenceGraphState:
        facts = [
            self._assessed_fact_candidate(fact, state=state)
            for fact in _json_object_list(state.get("extracted_customer_facts"))
        ]
        review_facts = [fact for fact in facts if fact.get("action") == "review"]
        if not review_facts:
            return {
                "extracted_customer_facts": facts,
                "customer_fact_review": {"status": "not_required", "candidates": []},
                "events": [{"event": "customer_intelligence_fact_review_not_required"}],
            }
        review_payload = _fact_review_payload(state, review_facts)
        return {
            "extracted_customer_facts": facts,
            "customer_fact_review": review_payload,
            "visible_trace": [_trace_step("复核客户事实", _fact_review_label(review_facts))],
            "events": [{
                "event": "customer_intelligence_fact_review_required",
                "candidate_count": len(review_facts),
            }],
        }

    def _route_after_review_facts(self, state: CustomerIntelligenceGraphState) -> str:
        review = coerce_json_dict(state.get("customer_fact_review"))
        if review.get("status") == "required" and self._checkpoint_enabled:
            return "wait_fact_review"
        return "persist_facts"

    def _wait_fact_review(
        self,
        state: CustomerIntelligenceGraphState,
        runtime: Runtime[CustomerIntelligenceRuntimeContext],
    ) -> CustomerIntelligenceGraphState:
        review = coerce_json_dict(state.get("customer_fact_review"))
        if review.get("status") != "required":
            return {}
        resume_payload = coerce_json_dict(interrupt(review))
        updated_facts = _facts_after_review_resume(
            facts=_json_object_list(state.get("extracted_customer_facts")),
            review=review,
            resume_payload=resume_payload,
        )
        return {
            "resume_payload": resume_payload,
            "extracted_customer_facts": updated_facts,
            "customer_fact_review": {
                **review,
                "status": "resolved",
                "resume_action": str(resume_payload.get("action") or ""),
            },
            "visible_trace": [_trace_step("复核客户事实", _fact_review_resume_label(resume_payload))],
            "events": [{
                "event": "customer_intelligence_fact_review_resumed",
                "resume_action": str(resume_payload.get("action") or ""),
            }],
        }

    def _assessed_fact_candidate(self, fact: JSONDict, *, state: CustomerIntelligenceGraphState) -> JSONDict:
        fact_type = str(fact.get("fact_type") or "").strip()
        content = str(fact.get("content") or "").strip()
        if fact_type not in _customer_fact_types() or not content:
            return {**fact, "action": "ignore", "assessment_reason": "invalid_fact_candidate"}
        assessment = self.fact_service.assess_candidate_against_context(
            candidate=CustomerFactCandidateInput(
                fact_type=cast(CustomerFactType, fact_type),
                subject=_optional_text(fact.get("subject")),
                content=content,
                confidence=_float_value(fact.get("confidence")),
                action=cast(FactAction, str(fact.get("action") or "upsert"))
                if str(fact.get("action") or "upsert") in {"upsert", "review", "ignore"}
                else "review",
                reason=_optional_text(fact.get("reason")),
                evidence_quote=_optional_text(fact.get("evidence_quote")),
            ),
            existing_facts=_existing_customer_facts(state),
        )
        updates: JSONDict = {
            "action": assessment.action,
            "assessment_reason": assessment.reason,
        }
        if assessment.existing_fact_id is not None:
            updates["existing_fact_id"] = assessment.existing_fact_id
        if assessment.existing_version is not None:
            updates["existing_version"] = assessment.existing_version
        if assessment.existing_content:
            updates["existing_content"] = assessment.existing_content
        if assessment.existing_confidence is not None:
            updates["existing_confidence"] = assessment.existing_confidence
        if assessment.conflict_reason:
            updates["conflict_reason"] = assessment.conflict_reason
        return {**fact, **updates}

    def _persist_facts(
        self,
        state: CustomerIntelligenceGraphState,
        runtime: Runtime[CustomerIntelligenceRuntimeContext],
    ) -> CustomerIntelligenceGraphState:
        context = runtime.context
        event = coerce_json_dict(state.get("event"))
        facts = _json_object_list(state.get("extracted_customer_facts"))
        customer_id = _positive_int(event.get("customer_id"))
        team_id = _positive_int(event.get("team_id")) or context.team_id
        tenant_id = _positive_int(event.get("tenant_id")) or team_id
        if customer_id is None or team_id <= 0 or tenant_id <= 0:
            return {
                "persisted_customer_fact_refs": [],
                "events": [{"event": "customer_intelligence_fact_persist_skipped", "reason": "invalid_customer_event"}],
            }

        source = coerce_json_dict(event.get("source"))
        persisted_refs: list[JSONDict] = []
        review_count = 0
        try:
            with self._db_scope(context) as db:
                for fact in facts:
                    action = str(fact.get("action") or "upsert")
                    if action == "review":
                        review_count += 1
                        continue
                    if action == "ignore" and fact.get("review_decision"):
                        self._record_fact_review_audit(
                            db,
                            fact=fact,
                            event=event,
                            tenant_id=tenant_id,
                            team_id=team_id,
                            customer_id=customer_id,
                            reviewer_id=context.user_id,
                            fact_id=None,
                        )
                        continue
                    if action != "upsert":
                        continue
                    content = str(fact.get("content") or "").strip()
                    fact_type = str(fact.get("fact_type") or "").strip()
                    if not content or fact_type not in _customer_fact_types():
                        continue
                    persisted = self.fact_service.upsert_fact(
                        db,
                        CustomerFactInput(
                            tenant_id=tenant_id,
                            team_id=team_id,
                            customer_id=customer_id,
                            fact_type=cast(CustomerFactType, fact_type),
                            subject=_optional_text(fact.get("subject")),
                            content=content,
                            confidence=_float_value(fact.get("confidence")),
                            occurred_at=_occurred_at(event),
                            source=CustomerFactSourceInput(
                                source_type=str(source.get("source_type") or event.get("trigger_type") or "customer_intelligence_event"),
                                source_object_id=str(source.get("source_object_id") or event.get("event_key") or ""),
                                business_object_type=_optional_text(source.get("business_object_type")),
                                business_object_id=_optional_text(source.get("business_object_id")),
                                evidence_id=_primary_evidence_id(state),
                                quote=_optional_text(fact.get("evidence_quote")),
                            ),
                        ),
                    )
                    persisted_refs.append({
                        "fact_id": int(persisted.id),
                        "version": int(getattr(persisted, "version", 1) or 1),
                        "fact_type": fact_type,
                        "subject": _optional_text(fact.get("subject")),
                        "confidence": _float_value(fact.get("confidence")),
                    })
                    if fact.get("review_decision"):
                        self._record_fact_review_audit(
                            db,
                            fact=fact,
                            event=event,
                            tenant_id=tenant_id,
                            team_id=team_id,
                            customer_id=customer_id,
                            reviewer_id=context.user_id,
                            fact_id=int(persisted.id),
                        )
        except Exception as exc:
            return {
                "persisted_customer_fact_refs": [],
                "errors": [{
                    "event": "customer_intelligence_fact_persist_failed",
                    "message": exc.__class__.__name__,
                }],
                "visible_trace": [_trace_step("沉淀客户事实", "客户事实暂未沉淀")],
            }

        return {
            "persisted_customer_fact_refs": persisted_refs,
            "visible_trace": [_trace_step("沉淀客户事实", _fact_persist_label(persisted_refs, review_count))],
            "events": [{
                "event": "customer_intelligence_facts_persisted",
                "persisted_count": len(persisted_refs),
                "review_count": review_count,
            }],
        }

    def _record_fact_review_audit(
        self,
        db: Session,
        *,
        fact: JSONDict,
        event: JSONDict,
        tenant_id: int,
        team_id: int,
        customer_id: int,
        reviewer_id: int,
        fact_id: int | None,
    ) -> None:
        fact_type = str(fact.get("fact_type") or "").strip()
        content = str(fact.get("content") or "").strip()
        decision = _review_decision_value(fact)
        if fact_type not in _customer_fact_types() or not content or decision is None:
            return
        resume_payload = coerce_json_dict(fact.get("resume_payload"))
        self.fact_service.record_review_decision(
            db,
            CustomerFactReviewAuditInput(
                tenant_id=tenant_id,
                team_id=team_id,
                customer_id=customer_id,
                event_key=str(event.get("event_key") or ""),
                fact_type=cast(CustomerFactType, fact_type),
                subject=_optional_text(fact.get("subject")),
                content=content,
                confidence=_float_value(fact.get("confidence")),
                decision=decision,
                reviewer_id=reviewer_id if reviewer_id > 0 else None,
                decision_source=_optional_text(resume_payload.get("source")),
                reason=_optional_text(fact.get("reason")),
                conflict_reason=_optional_text(fact.get("conflict_reason")),
                evidence_quote=_optional_text(fact.get("evidence_quote")),
                fact_id=fact_id,
                existing_fact_id=_positive_int(fact.get("existing_fact_id")),
                existing_version=_positive_int(fact.get("existing_version")),
            ),
        )

    def _route_after_persist_facts(self, state: CustomerIntelligenceGraphState) -> str:
        route = state.get("route")
        if route == "refresh_profile":
            return "refresh_profile_fields"
        if route == "refresh_brief":
            return "refresh_brief_fields"
        return "write_memory"

    async def _refresh_profile_fields(
        self,
        state: CustomerIntelligenceGraphState,
        runtime: Runtime[CustomerIntelligenceRuntimeContext],
    ) -> CustomerIntelligenceGraphState:
        event = coerce_json_dict(state.get("event"))
        customer_context = coerce_json_dict(state.get("customer_context"))
        customer_id = _positive_int(event.get("customer_id"))
        team_id = _positive_int(event.get("team_id")) or runtime.context.team_id
        account_name = _customer_account_name(customer_context)
        source_lead_id = _customer_source_lead_id(customer_context)
        if customer_id is None or team_id <= 0 or not account_name:
            return {
                "profile_refresh_result": {"success": False, "error": "invalid_customer_context"},
                "errors": [{"event": "customer_profile_refresh_failed", "message": "invalid_customer_context"}],
                "visible_trace": [_trace_step("刷新客户档案", "客户档案刷新缺少必要上下文")],
            }

        result = coerce_json_dict(await self.profile_refresh_service.generate_profile(
            customer_id=customer_id,
            account_name=account_name,
            source_lead_id=source_lead_id,
            team_id=team_id,
        ))
        if result.get("success") is not True:
            return {
                "profile_refresh_result": result,
                "errors": [{
                    "event": "customer_profile_refresh_failed",
                    "message": str(result.get("error") or "unknown_error"),
                }],
                "visible_trace": [_trace_step("刷新客户档案", "客户档案暂未刷新成功，已继续处理客户概况")],
            }
        return {
            "profile_refresh_result": result,
            "visible_trace": [_trace_step("刷新客户档案", "已刷新客户基础档案")],
            "events": [{"event": "customer_profile_refreshed", "customer_id": customer_id}],
        }

    async def _refresh_brief_fields(
        self,
        state: CustomerIntelligenceGraphState,
        runtime: Runtime[CustomerIntelligenceRuntimeContext],
    ) -> CustomerIntelligenceGraphState:
        event = coerce_json_dict(state.get("event"))
        customer_id = _positive_int(event.get("customer_id"))
        team_id = _positive_int(event.get("team_id")) or runtime.context.team_id
        if customer_id is None or team_id <= 0:
            return {
                "brief_refresh_result": {"success": False, "error": "invalid_customer_event"},
                "errors": [{"event": "customer_brief_refresh_failed", "message": "invalid_customer_event"}],
                "visible_trace": [_trace_step("刷新客户概况", "客户概况刷新缺少必要信息")],
            }

        result = coerce_json_dict(await self.brief_refresh_service.generate_brief(
            customer_id=customer_id,
            team_id=team_id,
        ))
        if result.get("success") is not True:
            return {
                "brief_refresh_result": result,
                "errors": [{
                    "event": "customer_brief_refresh_failed",
                    "message": str(result.get("error") or "unknown_error"),
                }],
                "visible_trace": [_trace_step("刷新客户概况", "客户概况暂未刷新成功，已继续更新客户记忆")],
            }
        return {
            "brief_refresh_result": result,
            "visible_trace": [_trace_step("刷新客户概况", "已刷新销售侧客户概况")],
            "events": [{"event": "customer_brief_refreshed", "customer_id": customer_id}],
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
            with self._db_scope(context) as db:
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
                fact_index = _fact_index_from_state(state, customer_context)
                if fact_index:
                    self.memory_store_service.upsert_fact_index(
                        db,
                        tenant_id=tenant_id,
                        customer_id=customer_id,
                        key="latest_customer_fact_refs",
                        value=fact_index,
                    )
                db.flush()
        except Exception as exc:
            return {
                "errors": [{
                    "event": "customer_intelligence_memory_write_failed",
                    "message": exc.__class__.__name__,
                }],
                "visible_trace": [_trace_step("更新客户记忆", "客户记忆暂未更新")],
            }
        return {
            "visible_trace": [_trace_step("更新客户记忆", "已沉淀客户摘要和证据索引")],
            "events": [{
                "event": "customer_intelligence_memory_written",
                "customer_id": customer_id,
                "sections": _written_memory_sections(retrieval_index=bool(retrieval_index), fact_index=bool(fact_index)),
            }],
        }

    def _emit_trace(
        self,
        state: CustomerIntelligenceGraphState,
        runtime: Runtime[CustomerIntelligenceRuntimeContext],
    ) -> CustomerIntelligenceGraphState:
        return {
            "events": [{
                "event": "customer_intelligence_trace_ready",
                "visible_trace": state.get("visible_trace") or [],
            }]
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
        "extracted_customer_facts": [],
        "customer_fact_review": {},
        "resume_payload": {},
        "persisted_customer_fact_refs": [],
        "profile_refresh_result": {},
        "brief_refresh_result": {},
        "customer_context_answer": {},
        "assistant_content": "",
        "retrieval_state": {},
        "refresh_plan": {},
        "route": "skip",
        "visible_trace": [],
        "events": [
            internal_graph_start_event("customer_intelligence_graph_invocation_started"),
            *[coerce_json_dict(event) for event in prior_events if isinstance(event, dict)],
        ],
        "errors": [],
    }


def _with_visible_events(result: CustomerIntelligenceGraphResult) -> CustomerIntelligenceGraphResult:
    projected: CustomerIntelligenceGraphResult = dict(result)
    projected["events"] = visible_graph_events(projected.get("events"))
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
    return cast(CustomerIntelligenceGraphState, merged)


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
        db=input_state.get("db"),
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


def _route_for_event(event: JSONDict) -> CustomerIntelligenceRoute:
    trigger_type = str(event.get("trigger_type") or "")
    if trigger_type in {
        "manual_refresh_requested",
        "customer_intelligence_batch_rebuild_requested",
        "customer_intelligence_historical_backfill_requested",
    }:
        payload = coerce_json_dict(event.get("payload"))
        refresh_scope = str(payload.get("refresh_scope") or "full")
        if refresh_scope == "brief":
            return "refresh_brief"
        return "refresh_profile"
    return _route_for_trigger(trigger_type)


def _route_for_trigger(trigger_type: str) -> CustomerIntelligenceRoute:
    if trigger_type == "agent_customer_question":
        return "answer_context"
    if trigger_type in {"customer_created", "customer_converted_from_lead"}:
        return "refresh_profile"
    if trigger_type == "customer_profile_generated":
        return "write_memory"
    if trigger_type == "customer_brief_generated":
        return "write_memory"
    if trigger_type in {
        "customer_activity_created",
        "customer_activity_updated",
        "customer_activity_deleted",
        "customer_contact_created",
        "customer_contact_updated",
        "customer_contact_deleted",
        "customer_business_object_created",
        "customer_business_object_updated",
        "customer_business_object_deleted",
        "deal_journey_event_recorded",
    }:
        return "refresh_brief"
    return "skip"


def _target_sections(route: CustomerIntelligenceRoute) -> list[str]:
    if route == "answer_context":
        return ["customer_context"]
    if route == "refresh_profile":
        return ["base_profile", "dynamic_brief", "memory"]
    if route == "refresh_brief":
        return ["dynamic_brief", "memory"]
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
        "customer_profile_generated": "识别到客户档案更新",
        "customer_brief_generated": "识别到客户概况更新",
        "deal_journey_event_recorded": "识别到业务流程进展",
        "manual_refresh_requested": "识别到手动刷新请求",
        "customer_intelligence_batch_rebuild_requested": "识别到批量重建请求",
        "customer_intelligence_historical_backfill_requested": "识别到历史客户补档任务",
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


def _customer_account_name(customer_context: JSONDict) -> str:
    strong_context = coerce_json_dict(customer_context.get("strong_context"))
    customer = coerce_json_dict(strong_context.get("customer"))
    account_name = customer.get("account_name")
    if isinstance(account_name, str):
        return account_name.strip()
    return ""


def _customer_source_lead_id(customer_context: JSONDict) -> int | None:
    strong_context = coerce_json_dict(customer_context.get("strong_context"))
    customer = coerce_json_dict(strong_context.get("customer"))
    return _positive_int(customer.get("source_lead_id"))


def _existing_customer_facts(state: CustomerIntelligenceGraphState) -> list[JSONDict]:
    customer_context = coerce_json_dict(state.get("customer_context"))
    strong_context = coerce_json_dict(customer_context.get("strong_context"))
    return _json_object_list(strong_context.get("customer_facts"))


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
        return "本次只需要支撑客户问答，不自动刷新档案"
    if route == "refresh_profile":
        if trigger_type in {"customer_created", "customer_converted_from_lead"}:
            return "客户生命周期发生变化，需要生成客户档案和销售概况"
        if trigger_type == "customer_intelligence_batch_rebuild_requested":
            return "批量重建任务触发，需要重建客户档案和销售概况"
        if trigger_type == "customer_intelligence_historical_backfill_requested":
            return "系统发现历史客户存在业务数据但缺少智能档案，需要自动补齐客户档案和销售概况"
        return "用户主动刷新，允许重建客户基础档案和销售概况"
    if route == "refresh_brief":
        return "业务动态发生变化，优先刷新销售动态和客户记忆"
    if route == "write_memory":
        return "生成结果已产生，作为客户长期记忆和语义证据索引"
    return f"暂不处理该客户智能事件: {trigger_type}"


def _refresh_plan_label(refresh_plan: JSONDict) -> str:
    route = cast(CustomerIntelligenceRoute, refresh_plan.get("route") or "skip")
    labels = {
        "answer_context": "准备用于回答客户问题",
        "refresh_profile": "准备刷新客户档案和客户概况",
        "refresh_brief": "准备刷新客户概况和客户记忆",
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
        return f"已基于客户档案、业务上下文和检索证据整理回答，置信度 {confidence:.0%}"
    if answer_mode == "degraded":
        return f"已基于客户强事实降级整理回答，检索状态 {retrieval_status or '不可用'}，置信度 {confidence:.0%}"
    if answer_mode == "insufficient":
        return f"客户资料不足，已标记缺失上下文，置信度 {confidence:.0%}"
    return f"已整理客户回答，置信度 {confidence:.0%}"


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
    return cast(CustomerIntelligenceGraphResult, result_object)


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
        refs.append({
            "evidence_id": str(evidence_id),
            "source_type": str(evidence.get("source_type") or ""),
            "business_object_type": str(evidence.get("business_object_type") or ""),
            "business_object_id": str(evidence.get("business_object_id") or ""),
            "score": evidence.get("score") if isinstance(evidence.get("score"), int | float) else None,
            "title": str(evidence.get("title") or ""),
        })
    if not refs:
        return {}
    return {
        "evidence_refs": refs,
        "source": "qdrant",
        "policy": "只保存证据引用，不复制向量文本",
    }


def _fact_index_from_context(customer_context: JSONDict) -> JSONDict:
    strong_context = coerce_json_dict(customer_context.get("strong_context"))
    customer_facts = strong_context.get("customer_facts")
    if not isinstance(customer_facts, list):
        return {}
    refs: list[JSONDict] = []
    for item in customer_facts[:20]:
        fact = coerce_json_dict(item)
        fact_id = fact.get("id")
        if not isinstance(fact_id, int):
            continue
        refs.append({
            "fact_id": fact_id,
            "fact_type": str(fact.get("fact_type") or ""),
            "subject": str(fact.get("subject") or ""),
            "confidence": fact.get("confidence") if isinstance(fact.get("confidence"), int | float) else None,
        })
    if not refs:
        return {}
    return {
        "fact_refs": refs,
        "source": "mysql",
        "policy": "只保存事实引用，不复制完整业务事实",
    }


def _fact_index_from_state(state: CustomerIntelligenceGraphState, customer_context: JSONDict) -> JSONDict:
    context_index = _fact_index_from_context(customer_context)
    persisted_refs = _json_object_list(state.get("persisted_customer_fact_refs"))
    if not persisted_refs:
        return context_index

    refs_by_id: dict[int, JSONDict] = {}
    for ref in _json_object_list(context_index.get("fact_refs")):
        fact_id = ref.get("fact_id")
        if isinstance(fact_id, int):
            refs_by_id[fact_id] = ref
    for ref in persisted_refs:
        fact_id = ref.get("fact_id")
        if isinstance(fact_id, int):
            refs_by_id[fact_id] = ref
    return {
        "fact_refs": list(refs_by_id.values())[:20],
        "source": "mysql",
        "policy": "只保存事实引用，不复制完整业务事实",
    }


def _written_memory_sections(*, retrieval_index: bool, fact_index: bool) -> list[str]:
    sections = [CUSTOMER_MEMORY_SUMMARIES]
    if retrieval_index:
        sections.append(CUSTOMER_MEMORY_RETRIEVAL)
    if fact_index:
        sections.append(CUSTOMER_MEMORY_FACTS)
    return sections


def _json_list(value: object) -> list[JSONValue]:
    if not isinstance(value, list):
        return []
    return [item if isinstance(item, str | int | float | bool) or item is None else str(item) for item in value]


def _json_object_list(value: object) -> list[JSONDict]:
    if not isinstance(value, list):
        return []
    return [coerce_json_dict(item) for item in value if isinstance(item, dict)]


def _json_list_len(value: object) -> int:
    return len(value) if isinstance(value, list) else 0


def _extractable_facts(result: CustomerFactExtractionResult) -> list[JSONDict]:
    facts: list[JSONDict] = []
    for fact in result.facts:
        payload = fact.model_dump(mode="json", exclude_none=True)
        if payload.get("action") == "ignore":
            continue
        facts.append(payload)
    return facts


def _json_object_list(value: object) -> list[JSONDict]:
    if not isinstance(value, list):
        return []
    items: list[JSONDict] = []
    for item in value:
        if isinstance(item, dict):
            items.append(coerce_json_dict(item))
    return items


def _customer_fact_types() -> set[str]:
    return {
        "alias",
        "need",
        "budget",
        "risk",
        "stage",
        "stakeholder_attitude",
        "competitor",
        "next_step",
        "preference",
        "summary",
    }


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _float_value(value: object) -> float:
    if isinstance(value, int | float):
        return max(0.0, min(1.0, float(value)))
    if isinstance(value, str):
        try:
            return max(0.0, min(1.0, float(value.strip())))
        except ValueError:
            return 0.0
    return 0.0


def _occurred_at(event: JSONDict) -> datetime | None:
    occurred_at = event.get("occurred_at")
    if not isinstance(occurred_at, str) or not occurred_at.strip():
        return None
    try:
        return datetime.fromisoformat(occurred_at)
    except ValueError:
        return None


def _primary_evidence_id(state: CustomerIntelligenceGraphState) -> str | None:
    retrieval_state = coerce_json_dict(state.get("retrieval_state"))
    if retrieval_state.get("status") != "ok":
        return None
    customer_context = coerce_json_dict(state.get("customer_context"))
    evidence_items = customer_context.get("semantic_evidence")
    if not isinstance(evidence_items, list) or not evidence_items:
        return None
    evidence = coerce_json_dict(evidence_items[0])
    evidence_id = evidence.get("evidence_id") or evidence.get("document_key") or evidence.get("id")
    return str(evidence_id) if evidence_id else None


def _fact_extraction_label(facts: list[JSONDict]) -> str:
    if not facts:
        return "本次没有发现需要新增沉淀的客户事实"
    upsert_count = sum(1 for fact in facts if fact.get("action") == "upsert")
    review_count = sum(1 for fact in facts if fact.get("action") == "review")
    if review_count and upsert_count:
        return f"提炼出 {upsert_count} 条可沉淀事实，{review_count} 条需复核事实"
    if review_count:
        return f"提炼出 {review_count} 条需复核事实"
    return f"提炼出 {upsert_count} 条可沉淀事实"


def _fact_persist_label(persisted_refs: list[JSONDict], review_count: int) -> str:
    if persisted_refs and review_count:
        return f"已沉淀 {len(persisted_refs)} 条客户事实，{review_count} 条保留复核"
    if persisted_refs:
        return f"已沉淀 {len(persisted_refs)} 条客户事实"
    if review_count:
        return f"{review_count} 条事实需要复核，暂不自动沉淀"
    return "没有需要沉淀的客户事实"


def _fact_review_payload(state: CustomerIntelligenceGraphState, review_facts: list[JSONDict]) -> JSONDict:
    event = coerce_json_dict(state.get("event"))
    customer_context = coerce_json_dict(state.get("customer_context"))
    strong_context = coerce_json_dict(customer_context.get("strong_context"))
    customer = coerce_json_dict(strong_context.get("customer"))
    customer_name = _optional_text(customer.get("account_name")) or "该客户"
    candidates = [_fact_review_candidate(fact, index=index) for index, fact in enumerate(review_facts, start=1)]
    return {
        "schema_version": "agent.interrupt.v1",
        "type": "confirm",
        "reason": "user_input_required",
        "business_action": "review_customer_facts",
        "status": "required",
        "allowed_resume_actions": ["approve", "reject", "cancel"],
        "target_refs": [{"type": "customer", "id": int(event.get("customer_id") or 0), "name": customer_name}],
        "draft_payload": {
            "customer_name": customer_name,
            "candidate_count": len(candidates),
            "candidates": candidates,
        },
        "interaction": {
            "schema_version": "agent.interrupt.v1",
            "interaction_id": str(event.get("event_key") or "customer_fact_review"),
            "type": "confirm",
            "business_action": "review_customer_facts",
            "status": "waiting_confirmation",
            "title": "确认是否沉淀客户事实",
            "prompt": _fact_review_prompt(customer_name=customer_name, candidates=candidates),
            "payload": {
                "customer_name": customer_name,
                "candidates": candidates,
            },
            "allow_free_text": False,
            "allow_cancel": True,
            "submit_label": "确认沉淀",
        },
        "source_event": "customer_fact_review_required",
    }


def _fact_review_candidate(fact: JSONDict, *, index: int) -> JSONDict:
    candidate: JSONDict = {
        "index": index,
        "type_label": _fact_type_label(str(fact.get("fact_type") or "")),
        "subject": _optional_text(fact.get("subject")),
        "content": str(fact.get("content") or "").strip(),
        "confidence": _float_value(fact.get("confidence")),
        "evidence_quote": _optional_text(fact.get("evidence_quote")),
        "reason": _optional_text(fact.get("reason")),
    }
    if fact.get("existing_content"):
        candidate["existing_content"] = str(fact.get("existing_content") or "")
    if fact.get("existing_version"):
        candidate["existing_version"] = _positive_int(fact.get("existing_version"))
    if fact.get("conflict_reason"):
        candidate["conflict_reason"] = str(fact.get("conflict_reason") or "")
    return candidate


def _fact_review_prompt(*, customer_name: str, candidates: list[JSONDict]) -> str:
    preview_items = []
    for candidate in candidates[:3]:
        subject = _optional_text(candidate.get("subject"))
        subject_text = f"「{subject}」" if subject else str(candidate.get("type_label") or "客户事实")
        preview_items.append(f"{subject_text}: {candidate.get('content')}")
    preview = "；".join(preview_items)
    return f"我从「{customer_name}」的最新动态里发现 {len(candidates)} 条需要确认的客户事实：{preview}。是否沉淀到客户智能档案？"


def _fact_type_label(fact_type: str) -> str:
    labels = {
        "alias": "常用称呼",
        "need": "客户需求",
        "budget": "预算",
        "risk": "风险",
        "stage": "阶段状态",
        "stakeholder_attitude": "关键人态度",
        "competitor": "竞品",
        "next_step": "下一步",
        "preference": "偏好",
        "summary": "摘要",
    }
    return labels.get(fact_type, "客户事实")


def _facts_after_review_resume(
    *,
    facts: list[JSONDict],
    review: JSONDict,
    resume_payload: JSONDict,
) -> list[JSONDict]:
    action = str(resume_payload.get("action") or "")
    if action != "approve":
        decision = "REJECTED" if action == "reject" else "CANCELLED"
        return [
            {
                **fact,
                "action": "ignore",
                "review_decision": decision,
                "resume_payload": resume_payload,
            } if fact.get("action") == "review" else fact
            for fact in facts
        ]
    reviewed_keys = _review_candidate_keys(review)
    updated: list[JSONDict] = []
    for fact in facts:
        if fact.get("action") == "review" and _fact_review_key(fact) in reviewed_keys:
            updated.append({
                **fact,
                "action": "upsert",
                "review_approved": True,
                "review_decision": "APPROVED",
                "resume_payload": resume_payload,
            })
        else:
            updated.append(fact)
    return updated


def _review_candidate_keys(review: JSONDict) -> set[tuple[str, str, str]]:
    draft_payload = coerce_json_dict(review.get("draft_payload"))
    candidates = _json_object_list(draft_payload.get("candidates"))
    return {
        (
            str(candidate.get("type_label") or ""),
            str(candidate.get("subject") or ""),
            str(candidate.get("content") or ""),
        )
        for candidate in candidates
    }


def _fact_review_key(fact: JSONDict) -> tuple[str, str, str]:
    return (
        _fact_type_label(str(fact.get("fact_type") or "")),
        str(fact.get("subject") or ""),
        str(fact.get("content") or ""),
    )


def _fact_review_label(review_facts: list[JSONDict]) -> str:
    return f"{len(review_facts)} 条客户事实需要确认后再沉淀"


def _fact_review_resume_label(resume_payload: JSONDict) -> str:
    action = str(resume_payload.get("action") or "")
    if action == "approve":
        return "已确认沉淀候选客户事实"
    if action == "reject":
        return "已放弃沉淀候选客户事实"
    return "已取消本次客户事实复核"


def _review_decision_value(fact: JSONDict) -> FactReviewDecision | None:
    decision = str(fact.get("review_decision") or "")
    if decision in {"APPROVED", "REJECTED", "CANCELLED"}:
        return cast(FactReviewDecision, decision)
    return None


customer_intelligence_graph_service = CustomerIntelligenceGraphService(checkpointer=agent_checkpoint_saver)
