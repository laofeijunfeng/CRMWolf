"""LangGraph-native orchestration for complete, grounded CRM work summaries."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, RetryPolicy
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from app.services.agent.checkpointer import (
    agent_checkpoint_saver,
    is_checkpoint_storage_error,
)
from app.services.work_summary_grounding import CitationResolver
from app.services.work_summary_models import (
    DEFAULT_WORK_SUMMARY_PAGE_SIZE,
    DEFAULT_WORK_SUMMARY_SYNTHESIS_CHUNK_BUDGET,
    WorkSummaryCoverage,
    WorkSummaryFactPage,
    WorkSummaryOutcome,
    WorkSummaryQuery,
    WorkSummaryStopReason,
)
from app.services.work_summary_narrative_service import WorkSummaryNarrativeService
from app.services.work_summary_service import WorkSummaryService

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from langgraph.errors import NodeError
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.runtime import Runtime

    from app.services.agent.types import JSONDict

WORK_SUMMARY_CHECKPOINT_NS = "crm_agent_work_summary"
DEFAULT_PAGE_SIZE = DEFAULT_WORK_SUMMARY_PAGE_SIZE
DEFAULT_MAX_FACTS_PER_SUMMARY = 500
DEFAULT_MAX_PAGES = 10
DEFAULT_CHUNK_SIZE = 25


class WorkSummaryGraphRequest(BaseModel):
    """Public application seam for one isolated work-summary workflow run."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    db: object
    team_id: int
    user_id: int
    session_id: int
    question: str
    invocation_id: str = Field(
        default_factory=lambda: uuid4().hex,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    window: str = "this_week"
    customer_public_id: str | None = None
    include_tasks: bool = True
    include_activities: bool = True
    include_business_events: bool = True
    start_at: str | None = None
    end_at: str | None = None


class WorkSummaryFactService(Protocol):
    def fetch_page(
        self,
        db: object,
        *,
        query: WorkSummaryQuery,
        cursor: str | None,
    ) -> WorkSummaryFactPage: ...


class WorkSummaryGraphState(TypedDict, total=False):
    query: dict[str, Any]
    cursor: str | None
    facts: list[dict[str, Any]]
    available_total: int
    pages_fetched: int
    source_counts: dict[str, int]
    source_total_counts: dict[str, int]
    source_status: dict[str, str]
    filters: dict[str, Any]
    stop_reason: WorkSummaryStopReason
    chunk_index: int
    chunk_results: list[dict[str, Any]]
    outcome: dict[str, Any]


@dataclass
class WorkSummaryRuntimeContext:
    db: object
    question: str
    team_id: int


class WorkSummaryGraphService:
    """Owns pagination, checkpointed state, grounding, coverage, and rendering."""

    def __init__(
        self,
        *,
        fact_service: WorkSummaryFactService | None = None,
        narrative_service: WorkSummaryNarrativeService | None = None,
        citation_resolver: CitationResolver | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_facts_per_summary: int = DEFAULT_MAX_FACTS_PER_SUMMARY,
        max_pages: int = DEFAULT_MAX_PAGES,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        checkpointer: object | None = None,
    ) -> None:
        self.citation_resolver = citation_resolver or CitationResolver()
        self.fact_service = fact_service or WorkSummaryService()
        self.narrative_service = narrative_service or WorkSummaryNarrativeService(
            citation_resolver=self.citation_resolver
        )
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size 必须在 1 到 100 之间")
        if max_facts_per_summary < 1:
            raise ValueError("max_facts_per_summary 必须大于 0")
        if max_pages < 1:
            raise ValueError("max_pages 必须大于 0")
        self.page_size = page_size
        self.max_facts_per_summary = max_facts_per_summary
        self.max_pages = max_pages
        if chunk_size < 1:
            raise ValueError("chunk_size 必须大于 0")
        required_chunks = (max_facts_per_summary + chunk_size - 1) // chunk_size
        if required_chunks > DEFAULT_WORK_SUMMARY_SYNTHESIS_CHUNK_BUDGET:
            raise ValueError(
                "工作总结配置超出 synthesis chunk budget；"
                "请增大 chunk_size 或降低 max_facts_per_summary"
            )
        self.chunk_size = chunk_size
        self._checkpoint_enabled = checkpointer is not None
        self._graph = self._build_graph(checkpointer)
        self._fallback_graph = self._build_graph(None)

    def _build_graph(self, checkpointer: object | None) -> CompiledStateGraph:
        graph = StateGraph(WorkSummaryGraphState, context_schema=WorkSummaryRuntimeContext)
        graph.add_node(
            "fetch_fact_page",
            self._fetch_fact_page,
            retry_policy=RetryPolicy(
                initial_interval=0.1,
                backoff_factor=2.0,
                max_interval=0.5,
                max_attempts=3,
                jitter=False,
                retry_on=SQLAlchemyError,
            ),
            error_handler=self._handle_fetch_error,
            destinations=("summarize_work_chunk",),
        )
        graph.add_node("summarize_work_chunk", self._summarize_work_chunk)
        graph.add_node("synthesize_snapshot", self._synthesize_snapshot)
        graph.add_edge(START, "fetch_fact_page")
        graph.add_conditional_edges(
            "fetch_fact_page",
            self._route_after_fetch,
            {
                "fetch_more": "fetch_fact_page",
                "summarize_chunk": "summarize_work_chunk",
                "synthesize": "synthesize_snapshot",
            },
        )
        graph.add_conditional_edges(
            "summarize_work_chunk",
            self._route_after_chunk,
            {
                "summarize_chunk": "summarize_work_chunk",
                "synthesize": "synthesize_snapshot",
            },
        )
        graph.add_edge("synthesize_snapshot", END)
        if checkpointer is None:
            return graph.compile()
        return graph.compile(checkpointer=checkpointer)

    async def run(self, request: WorkSummaryGraphRequest) -> WorkSummaryOutcome:
        query = WorkSummaryQuery(
            team_id=request.team_id,
            user_id=request.user_id,
            window=request.window,
            customer_public_id=request.customer_public_id,
            include_tasks=request.include_tasks,
            include_activities=request.include_activities,
            include_business_events=request.include_business_events,
            start_at=request.start_at,
            end_at=request.end_at,
            page_size=self.page_size,
        )
        state: WorkSummaryGraphState = {
            "query": query.model_dump(),
            "cursor": None,
            "facts": [],
            "available_total": 0,
            "pages_fetched": 0,
            "source_counts": {},
            "source_total_counts": {},
            "source_status": {},
            "filters": {},
            "chunk_index": 0,
            "chunk_results": [],
        }
        context = WorkSummaryRuntimeContext(
            db=request.db,
            question=request.question,
            team_id=request.team_id,
        )
        config = build_work_summary_graph_config(
            team_id=request.team_id,
            user_id=request.user_id,
            session_id=request.session_id,
            invocation_id=request.invocation_id,
        )
        try:
            result = await self._graph.ainvoke(state, config, context=context)
        except SQLAlchemyError as exc:
            if not self._checkpoint_enabled or not is_checkpoint_storage_error(exc):
                raise
            result = await self._fallback_graph.ainvoke(state, config, context=context)
        return WorkSummaryOutcome.model_validate(result.get("outcome") or {})

    def _fetch_fact_page(
        self,
        state: WorkSummaryGraphState,
        runtime: Runtime[WorkSummaryRuntimeContext],
    ) -> WorkSummaryGraphState:
        query = WorkSummaryQuery.model_validate(state.get("query") or {})
        page = self.fact_service.fetch_page(
            runtime.context.db,
            query=query,
            cursor=state.get("cursor"),
        )
        existing = list(state.get("facts") or [])
        remaining = max(self.max_facts_per_summary - len(existing), 0)
        accepted = page.items[:remaining]
        facts = [*existing, *accepted]
        pages_fetched = int(state.get("pages_fetched") or 0) + 1

        stop_reason: WorkSummaryStopReason | None = None
        if len(accepted) < len(page.items) or (len(facts) >= self.max_facts_per_summary and page.next_cursor):
            stop_reason = "fact_budget_exceeded"
            next_cursor = None
        elif page.next_cursor and pages_fetched >= self.max_pages:
            stop_reason = "page_budget_exceeded"
            next_cursor = None
        elif page.next_cursor:
            next_cursor = page.next_cursor
        else:
            stop_reason = "all_facts_collected"
            next_cursor = None

        snapshot_query = query
        if not state.get("facts") and page.filters.get("starts_at") and page.filters.get("ends_at"):
            snapshot_query = query.model_copy(update={
                "window": "custom",
                "start_at": str(page.filters["starts_at"]),
                "end_at": str(page.filters["ends_at"]),
            })

        update: WorkSummaryGraphState = {
            "query": snapshot_query.model_dump(),
            "facts": facts,
            "available_total": page.available_total,
            "cursor": next_cursor,
            "pages_fetched": pages_fetched,
            "source_counts": _merge_counts(state.get("source_counts") or {}, page.source_counts),
            "source_total_counts": page.source_total_counts,
            "source_status": page.source_status,
            "filters": page.filters,
        }
        if stop_reason is not None:
            update["stop_reason"] = stop_reason
        return update

    def _handle_fetch_error(
        self,
        state: WorkSummaryGraphState,
        error: NodeError,
    ) -> Command[Literal["summarize_work_chunk"]]:
        if not isinstance(error.error, SQLAlchemyError) or not state.get("facts"):
            raise error.error
        source_status = dict(state.get("source_status") or {})
        source_status["work_summary_fact_source"] = "failed"
        return Command(
            update={
                "cursor": None,
                "stop_reason": "source_failed",
                "source_status": source_status,
            },
            goto="summarize_work_chunk",
        )

    def _route_after_fetch(
        self,
        state: WorkSummaryGraphState,
    ) -> Literal["fetch_more", "summarize_chunk", "synthesize"]:
        if state.get("cursor"):
            return "fetch_more"
        return "summarize_chunk" if state.get("facts") else "synthesize"

    async def _summarize_work_chunk(
        self,
        state: WorkSummaryGraphState,
        runtime: Runtime[WorkSummaryRuntimeContext],
    ) -> WorkSummaryGraphState:
        facts = list(state.get("facts") or [])
        chunk_index = int(state.get("chunk_index") or 0)
        chunk = facts[chunk_index : chunk_index + self.chunk_size]
        if not chunk:
            return {}
        narrative = await self.narrative_service.summarize_with_metadata(
            runtime.context.db,
            team_id=runtime.context.team_id,
            question=runtime.context.question,
            work_facts={
                "items": chunk,
                "available_total": len(chunk),
                "truncated": False,
                "pagination": {"truncated": False, "available_total": len(chunk)},
                "source_counts": _counts_for_facts(chunk),
                "source_total_counts": state.get("source_total_counts") or {},
                "source_status": state.get("source_status") or {},
                "filters": state.get("filters") or {},
            },
        )
        chunk_results = list(state.get("chunk_results") or [])
        chunk_results.append({
            "result": narrative.result.model_dump(),
            "summary_source": narrative.summary_source,
            "model": narrative.model,
            "fallback_reason": narrative.fallback_reason,
            "fallback_error": narrative.fallback_error,
        })
        return {
            "chunk_index": chunk_index + len(chunk),
            "chunk_results": chunk_results,
        }

    def _route_after_chunk(
        self,
        state: WorkSummaryGraphState,
    ) -> Literal["summarize_chunk", "synthesize"]:
        return (
            "summarize_chunk"
            if int(state.get("chunk_index") or 0) < len(state.get("facts") or [])
            else "synthesize"
        )

    async def _synthesize_snapshot(
        self,
        state: WorkSummaryGraphState,
        runtime: Runtime[WorkSummaryRuntimeContext],
    ) -> WorkSummaryGraphState:
        from app.services.agent.schemas import WorkSummaryNarrativeResult

        facts = list(state.get("facts") or [])
        available_total = int(state.get("available_total") or len(facts))
        stop_reason = state.get("stop_reason") or "all_facts_collected"
        complete = stop_reason == "all_facts_collected" and len(facts) >= available_total
        work_facts = {
            "items": facts,
            "available_total": available_total,
            "truncated": not complete,
            "pagination": {
                "truncated": not complete,
                "available_total": available_total,
                "retrieved_total": len(facts),
            },
            "source_counts": state.get("source_counts") or {},
            "source_total_counts": state.get("source_total_counts") or {},
            "source_status": state.get("source_status") or {},
            "filters": state.get("filters") or {},
        }
        chunk_envelopes = list(state.get("chunk_results") or [])
        chunk_results = [
            WorkSummaryNarrativeResult.model_validate(envelope.get("result") or {})
            for envelope in chunk_envelopes
        ]
        if not chunk_results:
            narrative = await self.narrative_service.summarize_with_metadata(
                runtime.context.db,
                team_id=runtime.context.team_id,
                question=runtime.context.question,
                work_facts=work_facts,
            )
        elif len(chunk_results) == 1:
            envelope = chunk_envelopes[0]
            from app.services.work_summary_narrative_service import WorkSummaryNarrativeEnvelope

            narrative = WorkSummaryNarrativeEnvelope(
                result=chunk_results[0],
                summary_source=str(envelope.get("summary_source") or "deterministic_work_summary_fallback"),
                model=_optional_text(envelope.get("model")),
                fallback_reason=_optional_text(envelope.get("fallback_reason")),
                fallback_error=_optional_text(envelope.get("fallback_error")),
            )
        else:
            narrative = await self.narrative_service.synthesize_chunks_with_metadata(
                runtime.context.db,
                team_id=runtime.context.team_id,
                question=runtime.context.question,
                chunk_results=chunk_results,
                work_facts=work_facts,
            )
        resolved = self.citation_resolver.resolve(
            highlights=list(narrative.result.highlights),
            customer_summaries=list(narrative.result.customer_summaries),
            facts=facts,
        )
        coverage = WorkSummaryCoverage(
            available_total=available_total,
            retrieved_total=len(facts),
            summarized_total=len(facts),
            referenced_total=len(resolved.citations),
            pages_fetched=int(state.get("pages_fetched") or 0),
            complete=complete,
            stop_reason=stop_reason,
        )
        outcome = WorkSummaryOutcome(
            answer=_render_answer(narrative.result.answer, coverage),
            highlights=resolved.highlights,
            customer_summaries=resolved.customer_summaries,
            citations=resolved.citations,
            coverage=coverage,
            confidence=narrative.result.confidence,
            summary_source=(
                "langchain_structured_output"
                if narrative.summary_source == "langchain_structured_output"
                else "deterministic_fallback"
            ),
            model=narrative.model,
            fallback_reason=narrative.fallback_reason,
            fallback_error=narrative.fallback_error,
        )
        return {"outcome": outcome.model_dump()}


def build_work_summary_graph_config(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    invocation_id: str,
) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": (
                f"crm_agent_work_summary:{team_id}:{user_id}:{session_id}:{invocation_id}"
            ),
        },
        "metadata": {
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "runtime": "crm_agent_work_summary",
            "runtime_namespace": WORK_SUMMARY_CHECKPOINT_NS,
        },
    }


def _render_answer(answer: str, coverage: WorkSummaryCoverage) -> str:
    text = str(answer or "").strip()
    if coverage.complete:
        return text
    if coverage.stop_reason == "source_failed":
        coverage_notice = (
            f"> 数据读取中断，本次总结覆盖了 {coverage.summarized_total} 条可确认事实；"
            f"当前时间范围内共 {coverage.available_total} 条，结果并非完整总结。"
        )
    else:
        coverage_notice = (
            f"> 本次总结仅覆盖前 {coverage.summarized_total} 条可确认事实；"
            f"当前时间范围内共 {coverage.available_total} 条，结果并非完整总结。"
        )
    if not text:
        return coverage_notice
    return f"{text}\n\n{coverage_notice}"


def _merge_counts(current: dict[str, int], incoming: dict[str, int]) -> dict[str, int]:
    merged = dict(current)
    for key, value in incoming.items():
        merged[key] = merged.get(key, 0) + int(value)
    return merged


def _counts_for_facts(facts: list[JSONDict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for fact in facts:
        fact_type = str(fact.get("fact_type") or "unknown")
        counts[fact_type] = counts.get(fact_type, 0) + 1
    return counts


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


work_summary_graph_service = WorkSummaryGraphService(checkpointer=agent_checkpoint_saver)
