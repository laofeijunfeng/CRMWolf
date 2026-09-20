from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.services.agent.customer_initial_enrichment_graph import (
    CustomerInitialEnrichmentGraphService,
    CustomerInitialEnrichmentRequest,
)
from app.services.customer_enrichment_context_service import CustomerEnrichmentSkip
from app.services.customer_enrichment_contracts import (
    CustomerEnrichmentDecision,
    CustomerEnrichmentInferenceResult,
)


class FakeSession:
    def close(self) -> None:
        pass


class FakeContextService:
    def __init__(self, *, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def build(self, db, team_id: int, customer_id: int, fields: tuple[str, ...]):
        self.calls.append(
            {
                "db": db,
                "team_id": team_id,
                "customer_id": customer_id,
                "fields": fields,
            }
        )
        return self.payload


class MissingCustomerContextService:
    def build(self, db, team_id: int, customer_id: int, fields: tuple[str, ...]):
        del db, team_id, customer_id, fields
        raise CustomerEnrichmentSkip("CUSTOMER_NOT_FOUND")


class FakeInferenceService:
    def __init__(self, *, result: CustomerEnrichmentInferenceResult | None = None) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def infer(
        self,
        db,
        team_id: int,
        context: dict[str, object],
        requested_fields: tuple[str, ...],
    ) -> CustomerEnrichmentInferenceResult:
        self.calls.append(
            {
                "db": db,
                "team_id": team_id,
                "context": context,
                "requested_fields": requested_fields,
            }
        )
        assert self.result is not None
        return self.result


def _request() -> CustomerInitialEnrichmentRequest:
    return CustomerInitialEnrichmentRequest(
        team_id=2,
        customer_id=101,
        plan_version="customer-initial-v1",
        requested_fields=("industry",),
        run_id="run-1",
        thread_id="customer-enrichment:2:101:customer-initial-v1",
    )


@pytest.mark.asyncio
async def test_graph_skips_without_calling_inference_when_no_fields_missing():
    context = FakeContextService(payload={"customer": {"version": 4, "industry": "finance"}})
    inference = FakeInferenceService()
    graph = CustomerInitialEnrichmentGraphService(
        context_service=context,
        inference_service=inference,
        checkpointer=InMemorySaver(),
        session_factory=FakeSession,
    )

    result = await graph.run(_request())

    assert result.skip_reason == "NO_MISSING_FIELDS"
    assert result.expected_version == 4
    assert inference.calls == []


@pytest.mark.asyncio
async def test_graph_returns_validated_decisions_for_missing_industry():
    decision = CustomerEnrichmentDecision(field="industry", value="internet_saas", reason="软件研发")
    context = FakeContextService(payload={"customer": {"version": 4, "industry": None}})
    inference = FakeInferenceService(result=CustomerEnrichmentInferenceResult(decisions=[decision]))
    graph = CustomerInitialEnrichmentGraphService(
        context_service=context,
        inference_service=inference,
        checkpointer=InMemorySaver(),
        session_factory=FakeSession,
    )

    result = await graph.run(_request())

    assert result.expected_version == 4
    assert result.decisions == (decision,)
    assert inference.calls[0]["requested_fields"] == ("industry",)


@pytest.mark.asyncio
async def test_graph_treats_blank_industry_as_missing():
    decision = CustomerEnrichmentDecision(field="industry", value="internet_saas", reason="软件研发")
    context = FakeContextService(payload={"customer": {"version": 4, "industry": "  \t"}})
    inference = FakeInferenceService(result=CustomerEnrichmentInferenceResult(decisions=[decision]))
    graph = CustomerInitialEnrichmentGraphService(
        context_service=context,
        inference_service=inference,
        checkpointer=InMemorySaver(),
        session_factory=FakeSession,
    )

    result = await graph.run(_request())

    assert result.decisions == (decision,)
    assert inference.calls[0]["requested_fields"] == ("industry",)


@pytest.mark.asyncio
async def test_graph_propagates_deleted_customer_skip_without_inference():
    inference = FakeInferenceService()
    graph = CustomerInitialEnrichmentGraphService(
        context_service=MissingCustomerContextService(),
        inference_service=inference,
        checkpointer=InMemorySaver(),
        session_factory=FakeSession,
    )

    with pytest.raises(CustomerEnrichmentSkip) as exc:
        await graph.run(_request())

    assert exc.value.reason == "CUSTOMER_NOT_FOUND"
    assert inference.calls == []
