"""Reconcile customer source watermarks with published profile projections.

Business writes and the durable customer-intelligence run are not always able
to share one transaction yet.  This read-side reconciliation closes that
post-commit crash window: it compares the current business snapshot with the
watermark captured by the last published profile and creates an idempotent
refresh intent when the snapshot is newer, regressed, or missing.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING

from app.crud.customer_profile_projection import customer_profile_projection_crud
from app.models.customer import Customer
from app.services.customer_intelligence_context_service import (
    CustomerIntelligenceContextService,
    customer_intelligence_context_service,
)
from app.services.customer_intelligence_event_service import (
    CustomerIntelligenceEventService,
    customer_intelligence_event_service,
)
from app.services.customer_intelligence_refresh_service import (
    CustomerIntelligenceCommittedEventRequest,
    CustomerIntelligenceRefreshService,
    customer_intelligence_refresh_service,
)
from app.services.customer_intelligence_run_service import (
    CustomerIntelligenceRunService,
    customer_intelligence_run_service,
)
from app.services.customer_profile_projection_service import (
    CustomerProfileProjectionService,
    customer_profile_projection_service,
)
from app.services.customer_profile_watermark_service import (
    CustomerProfileWatermarkService,
    WatermarkComparison,
    customer_profile_watermark_service,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CustomerIntelligenceReconciliationResult:
    """One bounded reconciliation page result."""

    success: bool
    scanned: int
    stale: int
    scheduled: int
    skipped: int
    errors: int
    customer_ids: list[int]
    scheduled_customer_ids: list[int]
    error_customer_ids: list[int]
    next_customer_id: int | None
    dry_run: bool = False


class CustomerIntelligenceReconciliationService:
    """Detect and enqueue refreshes for business changes missed by events."""

    def __init__(
        self,
        *,
        context_service: CustomerIntelligenceContextService | None = None,
        event_service: CustomerIntelligenceEventService | None = None,
        refresh_service: CustomerIntelligenceRefreshService | None = None,
        run_service: CustomerIntelligenceRunService | None = None,
        projection_service: CustomerProfileProjectionService | None = None,
        watermark_service: CustomerProfileWatermarkService | None = None,
    ) -> None:
        self.context_service = context_service or customer_intelligence_context_service
        self.event_service = event_service or customer_intelligence_event_service
        self.refresh_service = refresh_service or customer_intelligence_refresh_service
        self.run_service = run_service or customer_intelligence_run_service
        self.projection_service = projection_service or customer_profile_projection_service
        self.watermark_service = watermark_service or customer_profile_watermark_service

    def reconcile_once(
        self,
        db: Session,
        *,
        team_id: int | None = None,
        limit: int = 50,
        after_customer_id: int | None = None,
        dry_run: bool = False,
    ) -> CustomerIntelligenceReconciliationResult:
        """Reconcile one stable customer-ID page without committing the session.

        The caller owns the transaction.  This makes the service usable from
        both a scheduler and an administrative dry-run endpoint, while the
        scheduler can commit the complete page atomically.
        """

        page_size = max(1, min(int(limit), 200))
        query = db.query(Customer)
        if team_id is not None:
            query = query.filter(Customer.team_id == int(team_id))
        if after_customer_id is not None:
            query = query.filter(Customer.id > int(after_customer_id))
        customers = query.order_by(Customer.id.asc()).limit(page_size).all()

        customer_ids: list[int] = []
        scheduled_customer_ids: list[int] = []
        error_customer_ids: list[int] = []
        stale_count = 0
        scheduled_count = 0
        skipped_count = 0
        error_count = 0

        for customer in customers:
            customer_id = int(customer.id)
            customer_ids.append(customer_id)
            owning_team_id = int(customer.team_id)
            try:
                comparison, needs_refresh, source_watermark = self._inspect_customer(
                    db,
                    team_id=owning_team_id,
                    customer_id=customer_id,
                )
                if not needs_refresh:
                    skipped_count += 1
                    continue
                stale_count += 1
                if dry_run:
                    continue
                if self.run_service.has_active_for_customer(
                    db,
                    team_id=owning_team_id,
                    customer_id=customer_id,
                ):
                    # The existing full/partial run will read the latest
                    # source snapshot when it executes; do not enqueue one
                    # reconciliation run per scheduler tick.
                    skipped_count += 1
                    continue

                with db.begin_nested():
                    event = self.event_service.reconciliation_requested(
                        team_id=owning_team_id,
                        customer_id=customer_id,
                        source_version=_watermark_hash(source_watermark),
                        occurred_at=business_now(),
                        payload={
                            "refresh_scope": "full",
                            "advanced_keys": list(comparison.advanced_keys),
                            "regressed_keys": list(comparison.regressed_keys),
                            "missing_keys": list(comparison.missing_keys),
                            "source_watermark": source_watermark,
                        },
                    )
                    self.projection_service.mark_stale(
                        db,
                        team_id=owning_team_id,
                        customer_id=customer_id,
                        source_watermark=source_watermark,
                        reason="对账发现业务水位高于档案已处理水位",
                    )
                    request = self.refresh_service.enqueue_committed_event_refresh(
                        db,
                        event=event,
                        scope="full",
                    )
                self._record_schedule(request, scheduled_customer_ids, customer_id)
                scheduled_count += 1
            except Exception:
                error_count += 1
                error_customer_ids.append(customer_id)
                logger.exception(
                    "客户智能档案对账失败: team_id=%s, customer_id=%s",
                    owning_team_id,
                    customer_id,
                )

        next_customer_id = int(customers[-1].id) if len(customers) == page_size else None
        return CustomerIntelligenceReconciliationResult(
            success=error_count == 0,
            scanned=len(customers),
            stale=stale_count,
            scheduled=scheduled_count,
            skipped=skipped_count,
            errors=error_count,
            customer_ids=customer_ids,
            scheduled_customer_ids=scheduled_customer_ids,
            error_customer_ids=error_customer_ids,
            next_customer_id=next_customer_id,
            dry_run=dry_run,
        )

    def _inspect_customer(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
    ) -> tuple[WatermarkComparison, bool, dict[str, object]]:
        context = self.context_service.build_context(
            db,
            team_id=team_id,
            customer_id=customer_id,
            evidence_limit=0,
        )
        source_watermark = _json_object(context.source_watermark)
        current = customer_profile_projection_crud.get_current(
            db,
            team_id=team_id,
            customer_id=customer_id,
        )
        if current is None or current.current_profile_version_id is None:
            return (
                WatermarkComparison(is_behind=False, advanced_keys=tuple(sorted(source_watermark))),
                True,
                source_watermark,
            )
        version = customer_profile_projection_crud.get_current_version(
            db,
            team_id=team_id,
            customer_id=customer_id,
            current=current,
        )
        if version is None:
            return (
                WatermarkComparison(is_behind=False, advanced_keys=tuple(sorted(source_watermark))),
                True,
                source_watermark,
            )
        known_watermark = _json_object(version.source_watermark_json)
        comparison = self.watermark_service.compare(source_watermark, known_watermark)
        needs_refresh = bool(
            comparison.advanced_keys
            or comparison.regressed_keys
            or comparison.missing_keys
        )
        return comparison, needs_refresh, source_watermark

    @staticmethod
    def _record_schedule(
        request: CustomerIntelligenceCommittedEventRequest,
        scheduled_customer_ids: list[int],
        customer_id: int,
    ) -> None:
        if request.scheduled:
            scheduled_customer_ids.append(customer_id)


def _json_object(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _watermark_hash(watermark: dict[str, object]) -> str:
    canonical = json.dumps(watermark, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


customer_intelligence_reconciliation_service = CustomerIntelligenceReconciliationService()
