"""Dedicated, durable workflow for publishing customer profile projections.

This module is deliberately separate from the historical customer-intelligence
conversation graph.  A profile refresh is a system workflow: it consumes a
customer context snapshot, optionally maintains structured facts, builds a
versioned projection, validates it, and publishes it.  It never writes the
retired Customer columns.
"""

from __future__ import annotations

import operator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Literal, Protocol, TypeAlias, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.database import SessionLocal
from app.schemas.customer_profile import CustomerProfileSections  # noqa: TC001
from app.services.agent.checkpointer import agent_checkpoint_saver
from app.services.agent.types import JSONDict, coerce_json_dict
from app.services.customer_fact_extraction_service import (
    customer_fact_extraction_service,
)
from app.services.customer_fact_service import (
    CustomerFactCandidateInput,
    CustomerFactInput,
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
    CustomerMemoryStoreService,
    customer_memory_store_service,
)
from app.services.customer_profile_projection_service import (
    PROFILE_WORKFLOW_OWNER,
    CustomerProfileProjectionDraft,
    CustomerProfileProjectionService,
    customer_profile_projection_service,
    publication_result_payload,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Iterator

    from langchain_core.runnables import RunnableConfig
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.runtime import Runtime
    from sqlalchemy.orm import Session



CUSTOMER_PROFILE_WORKFLOW_NAMESPACE = "crm_agent_customer_profile_projection"
CUSTOMER_PROFILE_WORKFLOW_STATE_VERSION = "v1"
CUSTOMER_PROFILE_WORKFLOW_GRAPH_VERSION = "customer-profile-v2"

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
WorkflowJSONDict: TypeAlias = dict[str, JSONValue]


class CustomerProfileContextSnapshot(BaseModel):
    """Typed seam between database context loading and profile projection."""

    model_config = ConfigDict(extra="forbid")

    customer_context: dict[str, object] = Field(default_factory=dict)
    customer_memory: dict[str, object] = Field(default_factory=dict)
    source_watermark: dict[str, object] = Field(default_factory=dict)


class CustomerProfileNarrativeDraft(BaseModel):
    """Typed seam from projection composition to validation/publication."""

    model_config = ConfigDict(extra="forbid")

    sections: CustomerProfileSections
    evidence_refs: list[dict[str, object]] = Field(default_factory=list)
    source_watermark: dict[str, object] = Field(default_factory=dict)
    fact_watermark: int = 0
    journey_watermark: int = 0
    task_watermark: int = 0
    commitment_watermark: int = 0
    source_event_key: str | None = None
    graph_version: str = CUSTOMER_PROFILE_WORKFLOW_GRAPH_VERSION
    target_sections: tuple[str, ...] = ()

    def to_projection_draft(self) -> CustomerProfileProjectionDraft:
        # ``model_dump`` recursively serializes nested Pydantic models.  That is
        # correct for checkpoint/JSON boundaries, but ``CustomerProfileProjectionDraft``
        # is consumed by the publication service, whose partial-section merge
        # relies on the typed ``CustomerProfileSections.model_copy`` contract.
        # Re-hydrate the nested model at this seam instead of leaking a dict into
        # the publication layer.
        payload = self.model_dump()
        payload["sections"] = self.sections
        return CustomerProfileProjectionDraft(**payload)


class CustomerProfilePublicationResult(BaseModel):
    """Stable result contract consumed by run audit and operation progress."""

    success: bool
    published: bool = False
    publication_status: str = "FAILED"
    deduplicated: bool = False
    profile_version: int | None = None
    profile_version_public_id: str | None = None
    profile_version_id: str | None = None
    input_watermark: dict[str, object] = Field(default_factory=dict)
    evidence_count: int = 0
    fact_changes: int = 0
    # ``target_sections`` describes the requested calculation scope;
    # ``changed_sections`` describes the actual diff from the previous
    # published projection.
    target_sections: list[str] = Field(default_factory=list)
    changed_sections: list[str] = Field(default_factory=list)
    stale_after_run: bool = False
    error_code: str | None = None
    error: str | None = None
    quality_report: dict[str, object] = Field(default_factory=dict)


class CustomerProfileProjectionState(TypedDict, total=False):
    team_id: int
    user_id: int
    session_id: int
    run_id: int
    event: WorkflowJSONDict
    customer_context: WorkflowJSONDict
    customer_memory: WorkflowJSONDict
    extracted_customer_facts: list[WorkflowJSONDict]
    persisted_customer_fact_refs: list[WorkflowJSONDict]
    profile_projection_draft: WorkflowJSONDict
    profile_validation: WorkflowJSONDict
    profile_quality_report: WorkflowJSONDict
    profile_projection_result: WorkflowJSONDict
    route: Literal["refresh_profile"]
    visible_trace: Annotated[list[JSONDict], operator.add]
    events: Annotated[list[JSONDict], operator.add]
    errors: Annotated[list[JSONDict], operator.add]


class CustomerProfileProjectionInput(TypedDict, total=False):
    team_id: int
    user_id: int
    session_id: int
    run_id: int
    event: CustomerIntelligenceEvent
    resume_existing_execution: bool


class CustomerProfileProjectionRequest(BaseModel):
    """Validated application input for one durable profile projection run.

    LangGraph state remains a TypedDict because it is a graph-internal shape.
    The public workflow seam uses this model first so missing identifiers,
    malformed flags, and accidental extra fields fail before a checkpoint or a
    database transaction is touched.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    team_id: int | None = Field(default=None, gt=0)
    user_id: int = Field(default=0, ge=0)
    session_id: int = Field(default=0, ge=0)
    run_id: int = Field(..., gt=0)
    event: object
    resume_existing_execution: bool = False

    @field_validator("event")
    @classmethod
    def _require_event(cls, value: object) -> object:
        if not isinstance(value, CustomerIntelligenceEvent):
            raise ValueError("customer profile projection requires an event")
        return value


class CustomerProfileProjectionResult(CustomerProfileProjectionState, total=False):
    pass


class CustomerProfileFactExtractor(Protocol):
    async def extract(
        self,
        db: Session,
        *,
        team_id: int,
        event: JSONDict,
        customer_context: JSONDict,
        customer_memory: JSONDict,
    ) -> object:
        pass


class CustomerProfileFactWriter(Protocol):
    def assess_candidate_against_context(
        self,
        *,
        candidate: CustomerFactCandidateInput,
        existing_facts: list[JSONDict],
    ) -> object:
        """Return the deterministic decision for one extracted fact."""

    def upsert_fact(self, db: Session, fact_input: CustomerFactInput) -> object:
        """Persist an already-approved fact candidate."""


@dataclass
class CustomerProfileProjectionRuntimeContext:
    team_id: int = 0
    user_id: int = 0
    session_id: int = 0


def build_customer_profile_thread_id(*, team_id: int, customer_id: int, run_id: int) -> str:
    """Return a stable per-customer/run checkpoint identity."""

    return f"customer-profile:{team_id}:{customer_id}:run:{run_id}"


def build_customer_profile_graph_config(
    *, team_id: int, user_id: int, session_id: int, customer_id: int, run_id: int
) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": build_customer_profile_thread_id(team_id=team_id, customer_id=customer_id, run_id=run_id)
        },
        "metadata": {
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "customer_id": customer_id,
            "run_id": run_id,
            "runtime": "crm_agent",
            "runtime_namespace": CUSTOMER_PROFILE_WORKFLOW_NAMESPACE,
            "checkpoint_namespace": CUSTOMER_PROFILE_WORKFLOW_NAMESPACE,
            "workflow": "customer_profile_projection",
            "workflow_state_version": CUSTOMER_PROFILE_WORKFLOW_STATE_VERSION,
            "graph_version": CUSTOMER_PROFILE_WORKFLOW_GRAPH_VERSION,
        },
    }


class CustomerProfileProjectionGraphService:
    """Deep module owning the profile refresh workflow behind one small seam."""

    def __init__(
        self,
        *,
        context_service: CustomerIntelligenceContextService | None = None,
        memory_store_service: CustomerMemoryStoreService | None = None,
        fact_extraction_service: CustomerProfileFactExtractor | None = None,
        fact_service: CustomerProfileFactWriter | None = None,
        projection_service: CustomerProfileProjectionService | None = None,
        checkpointer: object | None,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        self.context_service = context_service or customer_intelligence_context_service
        self.memory_store_service = memory_store_service or customer_memory_store_service
        self.fact_extraction_service = fact_extraction_service or customer_fact_extraction_service
        self.fact_service = fact_service or customer_fact_service
        self.projection_service = projection_service or customer_profile_projection_service
        if checkpointer is None:
            raise ValueError("customer profile projection workflow requires a checkpointer")
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

    def _build_graph(self, checkpointer: object) -> CompiledStateGraph:
        graph = StateGraph(CustomerProfileProjectionState, context_schema=CustomerProfileProjectionRuntimeContext)
        graph.add_node("load_customer_context", self._load_customer_context)
        graph.add_node("load_memory", self._load_memory)
        graph.add_node("extract_fact_candidates", self._extract_fact_candidates)
        graph.add_node("persist_fact_candidates", self._persist_fact_candidates)
        graph.add_node("compose_profile_draft", self._compose_profile_draft)
        graph.add_node("validate_profile_draft", self._validate_profile_draft)
        graph.add_node("publish_profile_projection", self._publish_profile_projection)
        graph.add_edge(START, "load_customer_context")
        graph.add_edge("load_customer_context", "load_memory")
        graph.add_edge("load_memory", "extract_fact_candidates")
        graph.add_edge("extract_fact_candidates", "persist_fact_candidates")
        graph.add_edge("persist_fact_candidates", "compose_profile_draft")
        graph.add_edge("compose_profile_draft", "validate_profile_draft")
        graph.add_edge("validate_profile_draft", "publish_profile_projection")
        graph.add_edge("publish_profile_projection", END)
        return graph.compile(checkpointer=checkpointer)

    async def stream_events(
        self, input_state: CustomerProfileProjectionInput
    ) -> AsyncGenerator[dict[str, object], None]:
        request = _validate_projection_request(input_state)
        event = request.event
        customer_id = _positive_int(event.customer_id)
        input_team_id = request.team_id
        event_team_id = _positive_int(event.team_id)
        event_tenant_id = _positive_int(event.tenant_id)
        team_id = input_team_id or event_team_id
        if customer_id is None or team_id is None:
            raise ValueError("customer profile projection requires team_id, customer_id and run_id")
        if input_team_id is not None and input_team_id != event_team_id:
            raise ValueError("customer profile projection team_id does not match event")
        if event_tenant_id != event_team_id:
            raise ValueError("customer profile projection tenant_id does not match event team_id")
        context = CustomerProfileProjectionRuntimeContext(
            team_id=team_id,
            user_id=request.user_id,
            session_id=request.session_id,
        )
        config = build_customer_profile_graph_config(
            team_id=team_id,
            user_id=context.user_id,
            session_id=context.session_id,
            customer_id=customer_id,
            run_id=request.run_id,
        )
        checkpoint_input: CustomerProfileProjectionState | None = _input_state(request, event)
        if request.resume_existing_execution:
            snapshot = await self._graph.aget_state(config)
            if getattr(snapshot, "next", ()):
                checkpoint_input = None
        async for chunk in self._stream_graph_run(checkpoint_input, context, config):
            yield chunk

    async def _stream_graph_run(
        self,
        checkpoint_input: CustomerProfileProjectionState | None,
        context: CustomerProfileProjectionRuntimeContext,
        config: RunnableConfig,
    ) -> AsyncGenerator[dict[str, object], None]:
        state: CustomerProfileProjectionState = {}
        emitted = 0
        async for update in self._graph.astream(checkpoint_input, config, context=context, stream_mode="updates"):
            if not isinstance(update, dict):
                continue
            for node_update in update.values():
                if not isinstance(node_update, dict):
                    continue
                _merge_state(state, cast("CustomerProfileProjectionState", node_update))
                trace = _visible_events(state.get("visible_trace"))
                for event in trace[emitted:]:
                    yield {"kind": "event", "event": event}
                emitted = len(trace)
        snapshot = await self._graph.aget_state(config)
        values = getattr(snapshot, "values", None)
        if not isinstance(values, dict):
            raise RuntimeError("customer profile projection checkpoint final state is unavailable")
        result = cast("CustomerProfileProjectionResult", {**state, **values})
        yield {"kind": "result", "result": result}

    def _load_customer_context(
        self, state: CustomerProfileProjectionState, runtime: object
    ) -> CustomerProfileProjectionState:
        ctx = cast("Runtime[CustomerProfileProjectionRuntimeContext]", runtime).context
        event = coerce_json_dict(state.get("event"))
        customer_id = _positive_int(event.get("customer_id"))
        if customer_id is None or ctx.team_id <= 0:
            raise ValueError("invalid customer profile event")
        with self._db_scope() as db:
            payload = self.context_service.build_context(
                db, team_id=ctx.team_id, customer_id=customer_id, query_text="", evidence_limit=20
            ).to_agent_payload()
        return {
            "customer_context": payload,
            "visible_trace": [_trace("读取客户事实、业务旅程和业务记录", "客户档案上下文已加载")],
            "events": [{"event": "customer_profile_context_loaded", "customer_id": customer_id}],
        }

    def _load_memory(self, state: CustomerProfileProjectionState, runtime: object) -> CustomerProfileProjectionState:
        ctx = cast("Runtime[CustomerProfileProjectionRuntimeContext]", runtime).context
        event = coerce_json_dict(state.get("event"))
        customer_id = _positive_int(event.get("customer_id"))
        if customer_id is None or ctx.team_id <= 0:
            return {"customer_memory": {}}
        with self._db_scope() as db:
            memory = self.memory_store_service.build_context_payload(
                db, tenant_id=ctx.team_id, customer_id=customer_id, limit=20
            )
        return {
            "customer_memory": memory,
            "visible_trace": [_trace("读取档案历史依据", "历史记忆已加载")],
            "events": [{"event": "customer_profile_memory_loaded", "customer_id": customer_id}],
        }

    async def _extract_fact_candidates(
        self, state: CustomerProfileProjectionState, runtime: object
    ) -> CustomerProfileProjectionState:
        ctx = cast("Runtime[CustomerProfileProjectionRuntimeContext]", runtime).context
        event = coerce_json_dict(state.get("event"))
        customer_context = coerce_json_dict(state.get("customer_context"))
        if not customer_context:
            return {"extracted_customer_facts": []}
        try:
            with self._db_scope() as db:
                extraction = await self.fact_extraction_service.extract(
                    db,
                    team_id=ctx.team_id,
                    event=event,
                    customer_context=customer_context,
                    customer_memory=coerce_json_dict(state.get("customer_memory")),
                )
        except Exception as exc:
            return {
                "extracted_customer_facts": [],
                "errors": [{"event": "customer_profile_fact_extraction_failed", "message": exc.__class__.__name__}],
                "visible_trace": [_trace("提炼客户事实", "事实提炼暂不可用，继续使用已有业务记录形成档案")],  # noqa: RUF001
            }
        facts = []
        for fact in getattr(extraction, "facts", []) or []:
            payload = fact.model_dump(mode="json") if hasattr(fact, "model_dump") else coerce_json_dict(fact)
            if payload.get("action", "upsert") != "ignore":
                facts.append(payload)
        return {
            "extracted_customer_facts": facts,
            "visible_trace": [_trace("提炼客户事实", f"识别到 {len(facts)} 条可沉淀事实")],
            "events": [{"event": "customer_profile_fact_candidates_extracted", "count": len(facts)}],
        }

    def _persist_fact_candidates(
        self, state: CustomerProfileProjectionState, runtime: object
    ) -> CustomerProfileProjectionState:
        ctx = cast("Runtime[CustomerProfileProjectionRuntimeContext]", runtime).context
        event = coerce_json_dict(state.get("event"))
        source = coerce_json_dict(event.get("source"))
        customer_id = _positive_int(event.get("customer_id"))
        if customer_id is None:
            return {"persisted_customer_fact_refs": []}
        persisted: list[JSONDict] = []
        errors: list[JSONDict] = []
        customer_context = coerce_json_dict(state.get("customer_context"))
        evidence_registry = _build_evidence_registry(customer_context)
        strong_context = coerce_json_dict(customer_context.get("strong_context"))
        existing_facts = _json_dict_list(strong_context.get("customer_facts"))
        seen_candidate_keys: set[str] = set()
        with self._db_scope() as db:
            for fact in state.get("extracted_customer_facts", []):
                fact_type = str(fact.get("fact_type") or "")
                content = str(fact.get("content") or "").strip()
                if not content or fact_type not in _FACT_TYPES:
                    continue
                candidate_key = _fact_candidate_key(fact_type=fact_type, subject=fact.get("subject"))
                if candidate_key in seen_candidate_keys:
                    errors.append(
                        {
                            "event": "customer_profile_fact_candidate_ignored",
                            "reason": "duplicate_candidate",
                            "fact_type": fact_type,
                            "subject": _text(fact.get("subject")),
                        }
                    )
                    continue
                seen_candidate_keys.add(candidate_key)
                evidence_key, evidence = _resolve_fact_evidence(fact, evidence_registry)
                if evidence_key is None or evidence is None:
                    errors.append(
                        {
                            "event": "customer_profile_fact_evidence_rejected",
                            "reason": "candidate_evidence_not_in_context",
                        }
                    )
                    continue
                assessment = self.fact_service.assess_candidate_against_context(
                    candidate=CustomerFactCandidateInput(
                        fact_type=cast("CustomerFactType", fact_type),
                        subject=_text(fact.get("subject")),
                        content=content,
                        confidence=_confidence(fact.get("confidence")),
                        action=cast("Literal['upsert', 'ignore']", str(fact.get("action") or "upsert")),
                        evidence_quote=_text(fact.get("evidence_quote")),
                        reason=_text(fact.get("reason")),
                    ),
                    existing_facts=existing_facts,
                )
                if assessment.action != "upsert":
                    errors.append(
                        {
                            "event": "customer_profile_fact_candidate_ignored",
                            "reason": assessment.reason,
                            "fact_type": fact_type,
                            "subject": _text(fact.get("subject")),
                        }
                    )
                    continue
                item = self.fact_service.upsert_fact(
                    db,
                    CustomerFactInput(
                        tenant_id=ctx.team_id,
                        team_id=ctx.team_id,
                        customer_id=customer_id,
                        fact_type=cast("CustomerFactType", fact_type),
                        subject=_text(fact.get("subject")),
                        content=content,
                        confidence=_confidence(fact.get("confidence")),
                        occurred_at=_occurred_at(event),
                        source=CustomerFactSourceInput(
                            source_type=str(
                                evidence.get("source_type")
                                or source.get("source_type")
                                or event.get("trigger_type")
                                or "customer_profile_projection"
                            ),
                            source_object_id=str(
                                evidence.get("source_id")
                                or source.get("source_object_id")
                                or event.get("event_key")
                                or evidence_key
                            ),
                            evidence_id=evidence_key,
                            quote=_text(fact.get("evidence_quote")),
                        ),
                    ),
                )
                persisted.append({"fact_id": int(item.id), "fact_type": fact_type})
        return {
            "persisted_customer_fact_refs": persisted,
            "errors": errors,
            "events": [
                {
                    "event": "customer_profile_facts_persisted",
                    "count": len(persisted),
                    "rejected_count": len(errors),
                }
            ],
        }

    def _compose_profile_draft(
        self,
        state: CustomerProfileProjectionState,
        runtime: object,  # noqa: ARG002
    ) -> CustomerProfileProjectionState:
        event = coerce_json_dict(state.get("event"))
        snapshot = CustomerProfileContextSnapshot(
            customer_context=coerce_json_dict(state.get("customer_context")),
            customer_memory=coerce_json_dict(state.get("customer_memory")),
            source_watermark=coerce_json_dict(
                coerce_json_dict(state.get("customer_context")).get("source_watermark")
            ),
        )
        plan = _target_sections(event)
        draft = self.projection_service.draft_from_context(
            context=snapshot.customer_context,
            source_event_key=str(event.get("event_key") or "") or None,
            source_watermark=snapshot.source_watermark,
            target_sections=tuple(plan),
        )
        typed = CustomerProfileNarrativeDraft(
            sections=draft.sections,
            evidence_refs=draft.evidence_refs,
            source_watermark=draft.source_watermark,
            fact_watermark=draft.fact_watermark,
            journey_watermark=draft.journey_watermark,
            task_watermark=draft.task_watermark,
            commitment_watermark=draft.commitment_watermark,
            source_event_key=draft.source_event_key,
            graph_version=CUSTOMER_PROFILE_WORKFLOW_GRAPH_VERSION,
            target_sections=draft.target_sections,
        )
        return {
            "profile_projection_draft": typed.model_dump(mode="json"),
            "visible_trace": [_trace("形成客户档案草稿", "客户当前情况、业务旅程和跟进过程已整理")],
            "events": [{"event": "customer_profile_draft_composed", "sections": plan}],
        }

    def _validate_profile_draft(
        self,
        state: CustomerProfileProjectionState,
        runtime: object,  # noqa: ARG002
    ) -> CustomerProfileProjectionState:
        draft = CustomerProfileNarrativeDraft.model_validate(state.get("profile_projection_draft"))
        projection_draft = draft.to_projection_draft()
        assessment = self.projection_service.assess_draft(projection_draft)
        quality_report = assessment.quality_report
        return {
            "profile_validation": {"valid": True},
            "profile_quality_report": quality_report.as_json(),
            "visible_trace": [_trace("校验客户档案", "档案结构和证据引用已通过校验")],
            "events": [
                {
                    "event": "customer_profile_draft_validated",
                    "quality_warning_count": len(quality_report.issues),
                }
            ],
        }

    def _publish_profile_projection(
        self, state: CustomerProfileProjectionState, runtime: object
    ) -> CustomerProfileProjectionState:
        ctx = cast("Runtime[CustomerProfileProjectionRuntimeContext]", runtime).context
        event = coerce_json_dict(state.get("event"))
        customer_id = _positive_int(event.get("customer_id"))
        if customer_id is None:
            raise ValueError("invalid customer profile event")
        draft = CustomerProfileNarrativeDraft.model_validate(state.get("profile_projection_draft"))
        with self._db_scope() as db:
            publication = self.projection_service.publish(
                db,
                team_id=ctx.team_id,
                customer_id=customer_id,
                draft=draft.to_projection_draft(),
                run_id=_positive_int(state.get("run_id")),
                publication_owner=PROFILE_WORKFLOW_OWNER,
            )
            result = CustomerProfilePublicationResult(
                **publication_result_payload(
                    publication,
                    draft=draft.to_projection_draft(),
                    fact_changes=len(state.get("persisted_customer_fact_refs") or []),
                )
            )
        return {
            "profile_projection_result": result.model_dump(mode="json"),
            "visible_trace": [_trace("发布客户档案", f"客户档案已发布第 {result.profile_version} 版")],
            "events": [{"event": "customer_profile_projection_published", **result.model_dump(mode="json")}],
        }


def _validate_projection_request(input_state: CustomerProfileProjectionInput) -> CustomerProfileProjectionRequest:
    try:
        return CustomerProfileProjectionRequest.model_validate(dict(input_state))
    except ValidationError as exc:
        raise ValueError("invalid customer profile projection input") from exc


def _input_state(
    input_state: CustomerProfileProjectionRequest, event: CustomerIntelligenceEvent
) -> CustomerProfileProjectionState:
    return {
        "team_id": int(input_state.team_id or event.team_id),
        "user_id": input_state.user_id,
        "session_id": input_state.session_id,
        "run_id": input_state.run_id,
        "event": event.to_dict(),
        "route": "refresh_profile",
    }


def _merge_state(state: CustomerProfileProjectionState, update: CustomerProfileProjectionState) -> None:
    target = cast("dict[str, object]", state)
    for key, value in update.items():
        if key in {"visible_trace", "events", "errors"} and isinstance(value, list):
            current = state.get(key)
            target[key] = [*(current if isinstance(current, list) else []), *value]
        else:
            target[key] = value


def _visible_events(value: object) -> list[JSONDict]:
    return [coerce_json_dict(item) for item in visible_trace_events(value)]


def _trace(title: str, detail: str) -> JSONDict:
    return {"title": title, "content": detail, "message": detail}


def _positive_int(value: object) -> int | None:
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.strip().isdigit() and int(value.strip()) > 0:
        return int(value.strip())
    return None


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _confidence(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value or 0)))
    except (TypeError, ValueError):
        return 0.0


def _occurred_at(event: JSONDict) -> datetime | None:
    value = event.get("occurred_at")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _build_evidence_registry(context: JSONDict) -> dict[str, JSONDict]:
    """Index only evidence present in the permission-filtered context."""

    registry: dict[str, JSONDict] = {}

    def add(key: object, source_type: object, source_id: object) -> None:
        normalized_key = _text(key)
        if not normalized_key or normalized_key in registry:
            return
        registry[normalized_key] = {
            "source_type": _text(source_type) or "semantic_evidence",
            "source_id": source_id,
        }

    for item in _json_dict_list(context.get("semantic_evidence")):
        add(
            item.get("evidence_key") or item.get("evidence_id") or item.get("source_key") or item.get("id"),
            item.get("source_type"),
            item.get("source_id") or item.get("source_object_id") or item.get("id"),
        )

    strong = coerce_json_dict(context.get("strong_context"))
    for kind, source_type, collection_key, id_key in (
        ("activity", "customer_activity", "recent_activities", "id"),
        ("journey_event", "deal_journey_event", "deal_journey_events", "id"),
        ("task", "follow_up_task", "recorded_follow_ups", "task_id"),
        ("commitment", "sales_commitment", "sales_commitments", "id"),
        ("fact", "customer_fact", "customer_facts", "id"),
        ("opportunity", "opportunity", "opportunities", "id"),
        ("contract", "contract", "contracts", "id"),
    ):
        for item in _json_dict_list(strong.get(collection_key)):
            source_id = item.get(id_key) or item.get("id")
            if source_id is not None:
                add(f"{kind}:{source_id}", source_type, source_id)

    return registry


def _resolve_fact_evidence(
    fact: JSONDict, evidence_registry: dict[str, JSONDict]
) -> tuple[str | None, JSONDict | None]:
    for raw_key in _json_list(fact.get("evidence_keys")):
        key = _text(raw_key)
        evidence = evidence_registry.get(key)
        if evidence is not None:
            return key, evidence
    return None, None


def _fact_candidate_key(*, fact_type: str, subject: object) -> str:
    """Return the deterministic identity used to deduplicate one extraction batch."""

    normalized_type = " ".join(str(fact_type).split()).casefold()
    normalized_subject = " ".join(str(subject or "").split()).casefold()
    return f"{normalized_type}:{normalized_subject}"


def _json_dict_list(value: object) -> list[JSONDict]:
    if not isinstance(value, list):
        return []
    return [coerce_json_dict(item) for item in value if isinstance(item, dict)]


def _json_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


_FACT_TYPES = {
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


def _target_sections(event: JSONDict) -> list[str]:
    trigger = str(event.get("trigger_type") or "")
    if trigger in {
        "customer_created",
        "customer_converted_from_lead",
        "manual_refresh_requested",
        "customer_intelligence_batch_rebuild_requested",
        "customer_intelligence_historical_backfill_requested",
        "customer_intelligence_reconciliation_requested",
    }:
        return [
            "current_situation",
            "current_journeys",
            "important_changes",
            "long_term_context",
            "follow_up_process",
            "recorded_follow_ups",
        ]
    if trigger.startswith("customer_contact_"):
        return ["long_term_context", "important_changes"]
    if trigger in {"deal_journey_event_recorded", "deal_journey_association_changed"} or trigger.startswith(
        "customer_business_object_"
    ):
        payload = coerce_json_dict(event.get("payload"))
        # Customer creation is a full bootstrap even though it uses the same
        # business-object event family as later master-data updates.
        if (
            trigger == "customer_business_object_created"
            and payload.get("object_type") == "customer"
            and payload.get("refresh_scope") == "full"
        ):
            return [
                "current_situation",
                "current_journeys",
                "important_changes",
                "long_term_context",
                "follow_up_process",
                "recorded_follow_ups",
            ]
        return ["current_situation", "current_journeys", "important_changes", "recorded_follow_ups"]
    return ["current_situation", "current_journeys", "important_changes", "follow_up_process", "recorded_follow_ups"]


customer_profile_projection_graph_service = CustomerProfileProjectionGraphService(checkpointer=agent_checkpoint_saver)
