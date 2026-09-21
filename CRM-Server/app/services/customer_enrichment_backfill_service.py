"""Register historical customer-enrichment jobs for customers missing industry."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy import exists

from app.core.config import get_settings
from app.crud.customer_enrichment_job import CustomerEnrichmentJobCRUD, customer_enrichment_job_crud
from app.models.customer import Customer
from app.models.customer_enrichment_job import CustomerEnrichmentJob
from app.services.customer_enrichment_contracts import CustomerEnrichmentPurpose
from app.services.customer_enrichment_plan import (
    ACTIVE_CUSTOMER_ENRICHMENT_PLAN,
    CustomerEnrichmentFieldRegistry,
    CustomerEnrichmentPlan,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class CustomerEnrichmentBackfillResult:
    success: bool
    scanned: int
    eligible: int
    scheduled: int
    skipped: int
    customer_ids: list[int] = field(default_factory=list)
    next_customer_id: int | None = None
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CustomerEnrichmentBackfillService:
    def __init__(
        self,
        *,
        job_crud: CustomerEnrichmentJobCRUD | None = None,
        plan: CustomerEnrichmentPlan | None = None,
        field_registry: CustomerEnrichmentFieldRegistry | None = None,
    ) -> None:
        self.job_crud = job_crud or customer_enrichment_job_crud
        self.plan = plan or ACTIVE_CUSTOMER_ENRICHMENT_PLAN
        self.field_registry = field_registry or CustomerEnrichmentFieldRegistry()

    def scan_and_ensure(
        self,
        db: Session,
        *,
        team_id: int | None = None,
        limit: int,
        after_customer_id: int | None = None,
        dry_run: bool = False,
    ) -> CustomerEnrichmentBackfillResult:
        if not self.plan.backfill_enabled:
            return CustomerEnrichmentBackfillResult(
                success=True,
                scanned=0,
                eligible=0,
                scheduled=0,
                skipped=0,
                dry_run=dry_run,
            )
        page_size = max(1, int(limit))
        current_plan_job = exists().where(
            CustomerEnrichmentJob.team_id == Customer.team_id,
            CustomerEnrichmentJob.customer_id == Customer.id,
            CustomerEnrichmentJob.plan_version == self.plan.version,
        )
        query = db.query(Customer.id, Customer.team_id).filter(
            self.field_registry.missing_condition("industry"),
            ~current_plan_job,
        )
        if team_id is not None:
            query = query.filter(Customer.team_id == team_id)
        if after_customer_id is not None:
            query = query.filter(Customer.id > after_customer_id)
        rows = query.order_by(Customer.id.asc()).limit(page_size).all()

        customer_ids = [int(row.id) for row in rows]
        next_customer_id = customer_ids[-1] if customer_ids else None
        if dry_run:
            return CustomerEnrichmentBackfillResult(
                success=True,
                scanned=len(rows),
                eligible=len(rows),
                scheduled=0,
                skipped=0,
                customer_ids=customer_ids,
                next_customer_id=next_customer_id,
                dry_run=True,
            )

        settings = get_settings()
        now = business_now()
        for row in rows:
            self.job_crud.ensure(
                db,
                team_id=int(row.team_id),
                customer_id=int(row.id),
                purpose=CustomerEnrichmentPurpose.HISTORICAL_BACKFILL.value,
                plan_version=self.plan.version,
                requested_fields=list(self.plan.fields),
                available_at=now,
                profile_gate_deadline_at=None,
                max_attempts=max(1, int(settings.CUSTOMER_INITIAL_ENRICHMENT_MAX_ATTEMPTS)),
                commit=False,
            )

        return CustomerEnrichmentBackfillResult(
            success=True,
            scanned=len(rows),
            eligible=len(rows),
            scheduled=len(rows),
            skipped=0,
            customer_ids=customer_ids,
            next_customer_id=next_customer_id,
            dry_run=False,
        )


customer_enrichment_backfill_service = CustomerEnrichmentBackfillService()
