"""Stable runner seam around the customer initial-enrichment graph."""

from __future__ import annotations

from typing import Protocol

from app.services.agent.customer_initial_enrichment_graph import (
    CustomerInitialEnrichmentRequest,
    CustomerInitialEnrichmentResult,
    customer_initial_enrichment_graph_service,
)


class CustomerInitialEnrichmentGraphRunner(Protocol):
    async def run(
        self, request: CustomerInitialEnrichmentRequest
    ) -> CustomerInitialEnrichmentResult: ...


class CustomerInitialEnrichmentWorkflow:
    def __init__(self, *, graph_service: CustomerInitialEnrichmentGraphRunner | None = None) -> None:
        self.graph_service = graph_service or customer_initial_enrichment_graph_service

    async def run(
        self, request: CustomerInitialEnrichmentRequest
    ) -> CustomerInitialEnrichmentResult:
        return await self.graph_service.run(request)


customer_initial_enrichment_workflow = CustomerInitialEnrichmentWorkflow()
