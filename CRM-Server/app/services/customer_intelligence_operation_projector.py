"""Materialize durable customer-intelligence runs into Agent UI operations.

The customer-intelligence run is the authoritative execution record. Agent
operations are a late-bindable, replayable projection and must never determine
whether the graph runs or reaches a terminal state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import and_, or_

from app.models.agent_async_operation import AgentAsyncOperation
from app.models.customer_intelligence_run import CustomerIntelligenceRun
from app.services.agent.async_operation_service import (
    TERMINAL_OPERATION_STATUSES,
    AgentAsyncOperationService,
    agent_async_operation_service,
)
from app.services.customer_intelligence_run_service import (
    TERMINAL_RUN_STATUSES,
    CustomerIntelligenceRunService,
    customer_intelligence_run_service,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class CustomerIntelligenceProjectionReconciliation:
    candidates: int
    projected: int


class CustomerIntelligenceOperationProjector:
    """Own the consistency seam between authoritative runs and UI projections."""

    def __init__(
        self,
        *,
        run_service: CustomerIntelligenceRunService | None = None,
        operation_service: AgentAsyncOperationService | None = None,
    ) -> None:
        self.run_service = run_service or customer_intelligence_run_service
        self.operation_service = operation_service or agent_async_operation_service

    def project_run(
        self,
        db: Session,
        *,
        run: CustomerIntelligenceRun,
        operation_public_id: str | None = None,
    ) -> AgentAsyncOperation | None:
        operation = self.operation_service.get_for_update(
            db,
            team_id=int(run.team_id),
            request_id=str(run.request_id),
            operation_public_id=operation_public_id,
        )
        if operation is None:
            return None
        return self.operation_service.project_customer_intelligence_run(db, operation, run)

    def project_request(
        self,
        db: Session,
        *,
        team_id: int,
        request_id: str,
        operation_public_id: str | None = None,
    ) -> AgentAsyncOperation | None:
        run = self.run_service.get_by_request_id(
            db,
            team_id=team_id,
            request_id=request_id,
        )
        if run is None:
            return None
        return self.project_run(
            db,
            run=run,
            operation_public_id=operation_public_id,
        )

    def reconcile(
        self,
        db: Session,
        *,
        team_id: int,
        limit: int = 200,
    ) -> CustomerIntelligenceProjectionReconciliation:
        """Repair projections that lag their authoritative run snapshot.

        Terminal/non-terminal mismatches are always candidates, even when a
        late binding made the operation row newer than the completed run.
        """

        query = (
            db.query(CustomerIntelligenceRun, AgentAsyncOperation)
            .join(
                AgentAsyncOperation,
                and_(
                    AgentAsyncOperation.team_id == CustomerIntelligenceRun.team_id,
                    AgentAsyncOperation.request_id == CustomerIntelligenceRun.request_id,
                ),
            )
            .filter(AgentAsyncOperation.operation_type == "customer_intelligence_refresh")
            .filter(
                or_(
                    CustomerIntelligenceRun.updated_time > AgentAsyncOperation.updated_time,
                    and_(
                        CustomerIntelligenceRun.status.in_(TERMINAL_RUN_STATUSES),
                        AgentAsyncOperation.status.notin_(TERMINAL_OPERATION_STATUSES),
                    ),
                )
            )
        )
        query = query.filter(CustomerIntelligenceRun.team_id == team_id)
        pairs = (
            query.order_by(CustomerIntelligenceRun.updated_time.asc(), CustomerIntelligenceRun.id.asc())
            .limit(max(1, min(limit, 1000)))
            .all()
        )
        projected = 0
        for run, operation in pairs:
            result = self.project_run(
                db,
                run=run,
                operation_public_id=str(operation.public_id),
            )
            if result is not None:
                projected += 1
        return CustomerIntelligenceProjectionReconciliation(
            candidates=len(pairs),
            projected=projected,
        )


customer_intelligence_operation_projector = CustomerIntelligenceOperationProjector()
