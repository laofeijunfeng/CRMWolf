"""Repair drift in durable customer initial-enrichment state."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from app.core.config import get_settings
from app.crud.customer_enrichment_job import CustomerEnrichmentJobCRUD, customer_enrichment_job_crud
from app.models.customer import Customer
from app.services.customer_enrichment_contracts import (
    CustomerEnrichmentJobStatus,
    CustomerEnrichmentPurpose,
)
from app.services.customer_enrichment_plan import ACTIVE_CUSTOMER_ENRICHMENT_PLAN
from app.services.customer_enrichment_profile_coordinator import (
    CustomerEnrichmentProfileCoordinator,
    customer_enrichment_profile_coordinator,
)
from app.services.customer_intelligence_run_service import (
    CustomerIntelligenceRunService,
    customer_intelligence_run_service,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

    from app.models.customer_enrichment_job import CustomerEnrichmentJob

logger = logging.getLogger(__name__)
_TERMINAL_SUCCESS = {
    CustomerEnrichmentJobStatus.COMPLETED.value,
    CustomerEnrichmentJobStatus.SKIPPED.value,
}


@dataclass(frozen=True)
class CustomerEnrichmentReconciliationResult:
    scanned: int
    jobs_created: int
    gates_released: int
    refreshes_repaired: int
    errors: int
    next_customer_id: int | None
    dry_run: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CustomerEnrichmentReconciliationService:
    def __init__(
        self,
        *,
        job_crud: CustomerEnrichmentJobCRUD | None = None,
        run_service: CustomerIntelligenceRunService | None = None,
        profile_coordinator: CustomerEnrichmentProfileCoordinator | None = None,
        max_attempts: int | None = None,
    ) -> None:
        self.job_crud = job_crud or customer_enrichment_job_crud
        self.run_service = run_service or customer_intelligence_run_service
        self.profile_coordinator = profile_coordinator or customer_enrichment_profile_coordinator
        self.max_attempts = max_attempts

    def reconcile_once(
        self,
        db: Session,
        *,
        team_id: int | None = None,
        limit: int,
        after_customer_id: int | None = None,
        dry_run: bool = False,
    ) -> CustomerEnrichmentReconciliationResult:
        page_size = max(1, int(limit))
        query = db.query(Customer).order_by(Customer.id.asc())
        if team_id is not None:
            query = query.filter(Customer.team_id == team_id)
        if after_customer_id is not None:
            query = query.filter(Customer.id > after_customer_id)
        customers = query.limit(page_size).all()

        jobs_created = 0
        gates_released = 0
        refreshes_repaired = 0
        errors = 0
        now = business_now()
        max_attempts = self._resolved_max_attempts()

        for customer in customers:
            customer_jobs_created = 0
            customer_gates_released = 0
            customer_refreshes_repaired = 0
            try:
                with db.begin_nested():
                    job = self.job_crud.get_by_identity(
                        db,
                        team_id=int(customer.team_id),
                        customer_id=int(customer.id),
                        plan_version=ACTIVE_CUSTOMER_ENRICHMENT_PLAN.version,
                    )
                    if job is None and self._fields_missing(customer):
                        customer_jobs_created = 1
                        if not dry_run:
                            job = self.job_crud.ensure(
                                db,
                                team_id=int(customer.team_id),
                                customer_id=int(customer.id),
                                purpose=CustomerEnrichmentPurpose.HISTORICAL_BACKFILL.value,
                                plan_version=ACTIVE_CUSTOMER_ENRICHMENT_PLAN.version,
                                requested_fields=list(ACTIVE_CUSTOMER_ENRICHMENT_PLAN.fields),
                                available_at=now,
                                profile_gate_deadline_at=None,
                                max_attempts=max_attempts,
                                commit=False,
                            )

                    if job is not None and self._gate_should_release(job, now=now):
                        if dry_run:
                            customer_gates_released = self.run_service.count_deferred_for_customer(
                                db,
                                team_id=int(job.team_id),
                                customer_id=int(job.customer_id),
                            )
                        else:
                            released = self.run_service.release_deferred_for_customer(
                                db,
                                team_id=int(job.team_id),
                                customer_id=int(job.customer_id),
                            )
                            deadline_timed_out = (
                                str(job.purpose) == CustomerEnrichmentPurpose.INITIAL_CREATION.value
                                and job.first_attempt_finished_at is None
                                and job.profile_gate_deadline_at is not None
                                and job.profile_gate_deadline_at <= now
                            )
                            if released:
                                customer_gates_released = len(released)
                                if deadline_timed_out and job.profile_gate_timed_out_at is None:
                                    job.profile_gate_timed_out_at = now
                                    db.add(job)
                                    db.flush()
                                if self._receipt_should_repair(job):
                                    job.profile_refresh_request_id = f"released:{released[0]}"
                                    job.profile_refresh_enqueued_at = now
                                    db.add(job)
                                    db.flush()
                                    customer_refreshes_repaired = 1
                    receipt_missing = job is not None and self._receipt_should_repair(job)
                    if receipt_missing and (
                        dry_run
                        or self.profile_coordinator.repair_missing_profile_receipt(
                            db,
                            job=job,
                            now=now,
                        )
                    ):
                        customer_refreshes_repaired = 1
                jobs_created += customer_jobs_created
                gates_released += customer_gates_released
                refreshes_repaired += customer_refreshes_repaired
            except Exception:
                errors += 1
                logger.exception(
                    "客户初始补全对账失败: team_id=%s customer_id=%s",
                    getattr(customer, "team_id", None),
                    getattr(customer, "id", None),
                )

        return CustomerEnrichmentReconciliationResult(
            scanned=len(customers),
            jobs_created=jobs_created,
            gates_released=gates_released,
            refreshes_repaired=refreshes_repaired,
            errors=errors,
            next_customer_id=int(customers[-1].id) if customers else None,
            dry_run=dry_run,
        )

    def _resolved_max_attempts(self) -> int:
        if self.max_attempts is not None:
            return max(1, int(self.max_attempts))
        return max(1, int(get_settings().CUSTOMER_INITIAL_ENRICHMENT_MAX_ATTEMPTS))

    @staticmethod
    def _fields_missing(customer: Customer) -> bool:
        for field in ACTIVE_CUSTOMER_ENRICHMENT_PLAN.fields:
            value = getattr(customer, field, None)
            if value is None or (isinstance(value, str) and not value.strip()):
                return True
        return False

    @staticmethod
    def _gate_should_release(job: CustomerEnrichmentJob, *, now: datetime) -> bool:
        if job.first_attempt_finished_at is not None:
            return True
        deadline = job.profile_gate_deadline_at
        return deadline is not None and deadline <= now

    @staticmethod
    def _receipt_should_repair(job: CustomerEnrichmentJob) -> bool:
        return (
            str(job.status) in _TERMINAL_SUCCESS
            and not str(job.profile_refresh_request_id or "").strip()
        )


customer_enrichment_reconciliation_service = CustomerEnrichmentReconciliationService()
