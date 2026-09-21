"""Pure compute graph for one customer initial-enrichment attempt."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field

from app.core.database import SessionLocal
from app.services.agent.checkpointer import agent_checkpoint_saver
from app.services.customer_enrichment_context_service import CustomerEnrichmentContextService
from app.services.customer_enrichment_contracts import (
    CustomerEnrichmentDecision,
    CustomerEnrichmentInferenceResult,
)
from app.services.customer_enrichment_inference_service import CustomerEnrichmentInferenceService
from app.services.customer_enrichment_plan import (
    ACTIVE_CUSTOMER_ENRICHMENT_PLAN,
    CustomerEnrichmentFieldRegistry,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from langchain_core.runnables import RunnableConfig
    from langgraph.graph.state import CompiledStateGraph
    from sqlalchemy.orm import Session



class CustomerInitialEnrichmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    team_id: int = Field(gt=0)
    customer_id: int = Field(gt=0)
    plan_version: str = Field(min_length=1, max_length=64)
    requested_fields: tuple[str, ...] = Field(min_length=1, max_length=20)
    run_id: str = Field(min_length=1, max_length=100)
    thread_id: str = Field(min_length=1, max_length=240)


class CustomerInitialEnrichmentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    customer_id: int
    expected_version: int
    decisions: tuple[CustomerEnrichmentDecision, ...] = ()
    skip_reason: str | None = None


class CustomerInitialEnrichmentState(TypedDict, total=False):
    request: dict[str, object]
    context: dict[str, object]
    expected_version: int
    missing_fields: list[str]
    inferred_decisions: list[dict[str, object]]
    result: dict[str, object]


class CustomerInitialEnrichmentGraphService:
    """Compute validated enrichment decisions without mutating customer or job rows."""

    def __init__(
        self,
        *,
        context_service: CustomerEnrichmentContextService | None = None,
        inference_service: CustomerEnrichmentInferenceService | None = None,
        field_registry: CustomerEnrichmentFieldRegistry | None = None,
        checkpointer: object | None,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        if checkpointer is None:
            raise ValueError("customer initial enrichment workflow requires a checkpointer")
        self.context_service = context_service or CustomerEnrichmentContextService()
        self.inference_service = inference_service or CustomerEnrichmentInferenceService()
        self.field_registry = field_registry or CustomerEnrichmentFieldRegistry()
        self._session_factory = session_factory
        self._graph = self._build_graph(checkpointer)

    def _build_graph(self, checkpointer: object) -> CompiledStateGraph:
        graph = StateGraph(CustomerInitialEnrichmentState)
        graph.add_node("load_context", self._load_context)
        graph.add_node("collect_missing_fields", self._collect_missing_fields)
        graph.add_node("infer_fields", self._infer_fields)
        graph.add_node("validate_decisions", self._validate_decisions)
        graph.add_edge(START, "load_context")
        graph.add_edge("load_context", "collect_missing_fields")
        graph.add_conditional_edges(
            "collect_missing_fields",
            self._route_after_collect,
            {"no_missing": END, "infer": "infer_fields"},
        )
        graph.add_edge("infer_fields", "validate_decisions")
        graph.add_edge("validate_decisions", END)
        return graph.compile(checkpointer=checkpointer)

    async def run(self, request: CustomerInitialEnrichmentRequest) -> CustomerInitialEnrichmentResult:
        if request.plan_version != ACTIVE_CUSTOMER_ENRICHMENT_PLAN.version:
            raise ValueError(f"unsupported customer enrichment plan: {request.plan_version}")
        state: CustomerInitialEnrichmentState = {"request": request.model_dump(mode="json")}
        config: RunnableConfig = {
            "configurable": {"thread_id": request.thread_id},
            "metadata": {
                "team_id": request.team_id,
                "customer_id": request.customer_id,
                "run_id": request.run_id,
                "workflow": "customer_initial_enrichment",
                "plan_version": request.plan_version,
            },
        }
        final_state = await self._graph.ainvoke(state, config)
        return CustomerInitialEnrichmentResult.model_validate(final_state.get("result") or {})

    def _load_context(self, state: CustomerInitialEnrichmentState) -> CustomerInitialEnrichmentState:
        request = CustomerInitialEnrichmentRequest.model_validate(state.get("request") or {})
        db = self._session_factory()
        try:
            context = self.context_service.build(
                db,
                team_id=request.team_id,
                customer_id=request.customer_id,
                fields=request.requested_fields,
            )
        finally:
            db.close()
        customer = context.get("customer")
        if not isinstance(customer, dict) or not isinstance(customer.get("version"), int):
            raise ValueError("customer enrichment context is missing customer version")
        return {"context": context, "expected_version": int(customer["version"])}

    def _collect_missing_fields(self, state: CustomerInitialEnrichmentState) -> CustomerInitialEnrichmentState:
        request = CustomerInitialEnrichmentRequest.model_validate(state.get("request") or {})
        context = state.get("context") or {}
        customer = context.get("customer")
        if not isinstance(customer, dict):
            raise ValueError("customer enrichment context is missing customer")

        missing: list[str] = []
        for field in request.requested_fields:
            handler = self.field_registry.get(field)
            value = customer.get(handler.field_key)
            if self.field_registry.is_missing(field, value):
                missing.append(field)
        if missing:
            return {"missing_fields": missing}
        return {
            "missing_fields": [],
            "result": CustomerInitialEnrichmentResult(
                customer_id=request.customer_id,
                expected_version=int(state["expected_version"]),
                skip_reason="NO_MISSING_FIELDS",
            ).model_dump(mode="json"),
        }

    @staticmethod
    def _route_after_collect(state: CustomerInitialEnrichmentState) -> str:
        return "infer" if state.get("missing_fields") else "no_missing"

    async def _infer_fields(self, state: CustomerInitialEnrichmentState) -> CustomerInitialEnrichmentState:
        request = CustomerInitialEnrichmentRequest.model_validate(state.get("request") or {})
        missing_fields = tuple(state.get("missing_fields") or ())
        db = self._session_factory()
        try:
            inference = await self.inference_service.infer(
                db,
                team_id=request.team_id,
                context=state.get("context") or {},
                requested_fields=missing_fields,
            )
        finally:
            db.close()
        return {"inferred_decisions": inference.model_dump(mode="json")["decisions"]}

    def _validate_decisions(self, state: CustomerInitialEnrichmentState) -> CustomerInitialEnrichmentState:
        request = CustomerInitialEnrichmentRequest.model_validate(state.get("request") or {})
        inference = CustomerEnrichmentInferenceResult.model_validate(
            {"decisions": state.get("inferred_decisions") or []}
        )
        missing_fields = tuple(state.get("missing_fields") or ())
        decision_fields = tuple(decision.field for decision in inference.decisions)
        if len(set(decision_fields)) != len(decision_fields):
            raise ValueError("customer enrichment decisions contain duplicate fields")
        if len(decision_fields) != len(missing_fields) or set(decision_fields) != set(missing_fields):
            raise ValueError("customer enrichment decisions do not match missing fields")
        for field in decision_fields:
            self.field_registry.get(field)
        result = CustomerInitialEnrichmentResult(
            customer_id=request.customer_id,
            expected_version=int(state["expected_version"]),
            decisions=tuple(inference.decisions),
        )
        return {"result": result.model_dump(mode="json")}


customer_initial_enrichment_graph_service = CustomerInitialEnrichmentGraphService(
    checkpointer=agent_checkpoint_saver
)
