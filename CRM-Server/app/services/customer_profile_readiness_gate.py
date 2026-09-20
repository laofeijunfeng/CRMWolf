"""Persistent readiness gate between initial enrichment and profile projection."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from app.crud.customer_enrichment_job import (
    CustomerEnrichmentJobCRUD,
    customer_enrichment_job_crud,
)
from app.services.customer_enrichment_contracts import CustomerEnrichmentPurpose
from app.services.customer_enrichment_plan import ACTIVE_CUSTOMER_ENRICHMENT_PLAN
from app.services.customer_intelligence_run_service import (
    CustomerIntelligenceRunService,
    customer_intelligence_run_service,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.customer_intelligence_run import CustomerIntelligenceRun
    from app.services.customer_intelligence_event_service import CustomerIntelligenceEvent


class CustomerProfileReadinessGate:
    """Defer profile runs until the first initial-enrichment attempt settles."""

    def __init__(
        self,
        *,
        job_crud: CustomerEnrichmentJobCRUD | None = None,
        run_service: CustomerIntelligenceRunService | None = None,
    ) -> None:
        self.job_crud = job_crud or customer_enrichment_job_crud
        self.run_service = run_service or customer_intelligence_run_service

    def defer_if_needed(
        self,
        db: Session,
        *,
        event: CustomerIntelligenceEvent,
        run: CustomerIntelligenceRun,
        now: datetime,
    ) -> datetime | None:
        job = self.job_crud.get_by_identity(
            db,
            team_id=event.team_id,
            customer_id=event.customer_id,
            plan_version=ACTIVE_CUSTOMER_ENRICHMENT_PLAN.version,
        )
        if job is None:
            return None
        if str(job.purpose) != CustomerEnrichmentPurpose.INITIAL_CREATION.value:
            return None
        if job.first_attempt_finished_at is not None:
            return None
        deadline = job.profile_gate_deadline_at
        if deadline is None:
            return None
        if deadline <= now:
            if job.profile_gate_timed_out_at is None:
                job.profile_gate_timed_out_at = now
                db.add(job)
                db.flush()
            return None

        not_before_at = min(deadline, now + timedelta(seconds=5))
        self.run_service.defer_until(
            db,
            team_id=event.team_id,
            run_id=int(run.id),
            not_before_at=not_before_at,
        )
        return not_before_at


customer_profile_readiness_gate = CustomerProfileReadinessGate()
