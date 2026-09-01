"""Application workflow seam for customer profile projection runs.

The graph owns node orchestration and checkpoint state.  This module owns the
workflow boundary used by refresh workers so callers do not depend on a
compiled LangGraph instance or accidentally route profile refreshes through the
general customer-intelligence conversation graph.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from app.services.agent.customer_profile_projection_graph import (
    CustomerProfileProjectionInput,
    customer_profile_projection_graph_service,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class CustomerProfileProjectionWorkflowRunner(Protocol):
    async def stream_events(
        self, input_state: CustomerProfileProjectionInput
    ) -> AsyncGenerator[dict[str, object], None]:
        """Execute or resume one durable profile projection run."""


class CustomerProfileProjectionWorkflow:
    """Stable workflow boundary around the dedicated profile projection graph."""

    def __init__(
        self,
        *,
        graph_service: CustomerProfileProjectionWorkflowRunner | None = None,
    ) -> None:
        self.graph_service = graph_service or customer_profile_projection_graph_service

    async def stream_events(
        self, input_state: CustomerProfileProjectionInput
    ) -> AsyncGenerator[dict[str, object], None]:
        async for chunk in self.graph_service.stream_events(input_state):
            yield chunk


customer_profile_projection_workflow = CustomerProfileProjectionWorkflow()
