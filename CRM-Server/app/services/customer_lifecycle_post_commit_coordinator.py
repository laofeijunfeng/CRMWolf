"""Coordinate durable customer creation receipts and best-effort worker kicks."""

from __future__ import annotations

import logging
from contextlib import nullcontext
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import TYPE_CHECKING, Literal

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.customer_business_object_intelligence_service import (
    CustomerBusinessObjectIntelligenceService,
    customer_business_object_intelligence_service,
)
from app.services.customer_enrichment_contracts import (
    CustomerEnrichmentJobRequest,
    CustomerEnrichmentPurpose,
)
from app.services.customer_enrichment_job_service import (
    CustomerEnrichmentJobService,
    customer_enrichment_job_service,
)
from app.services.customer_enrichment_plan import (
    ACTIVE_CUSTOMER_ENRICHMENT_PLAN,
    CustomerEnrichmentFieldRegistry,
)
from app.services.customer_intelligence_refresh_service import (
    CustomerIntelligenceCommittedEventRequest,
    CustomerIntelligenceRefreshService,
    customer_intelligence_refresh_service,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
CustomerLifecycleTrigger = Literal["customer_created", "customer_converted_from_lead"]


@dataclass(frozen=True)
class CustomerLifecyclePostCommitWork:
    enrichment_request: CustomerEnrichmentJobRequest | None
    profile_request: CustomerIntelligenceCommittedEventRequest | None
    warnings: tuple[str, ...] = ()
    profile_kick_pending: bool = True


class CustomerLifecyclePostCommitCoordinator:
    """Register independent durable receipts before or immediately after commit."""

    def __init__(
        self,
        *,
        job_service: CustomerEnrichmentJobService | object | None = None,
        intelligence_service: CustomerBusinessObjectIntelligenceService | object | None = None,
        profile_refresh_service: CustomerIntelligenceRefreshService | object | None = None,
        session_factory: Callable[[], Session] = SessionLocal,
        settle_seconds: int | None = None,
        profile_gate_max_seconds: int | None = None,
        max_attempts: int | None = None,
        field_registry: CustomerEnrichmentFieldRegistry | None = None,
    ) -> None:
        settings = get_settings()
        self.job_service = job_service or customer_enrichment_job_service
        self.intelligence_service = intelligence_service or customer_business_object_intelligence_service
        self.profile_refresh_service = profile_refresh_service or customer_intelligence_refresh_service
        self.field_registry = field_registry or CustomerEnrichmentFieldRegistry()
        self._session_factory = session_factory
        self.settle_seconds = max(
            0,
            int(
                settings.CUSTOMER_INITIAL_ENRICHMENT_SETTLE_SECONDS
                if settle_seconds is None
                else settle_seconds
            ),
        )
        self.profile_gate_max_seconds = max(
            0,
            int(
                settings.CUSTOMER_INITIAL_ENRICHMENT_PROFILE_GATE_MAX_SECONDS
                if profile_gate_max_seconds is None
                else profile_gate_max_seconds
            ),
        )
        self.max_attempts = max(
            1,
            int(
                settings.CUSTOMER_INITIAL_ENRICHMENT_MAX_ATTEMPTS
                if max_attempts is None
                else max_attempts
            ),
        )

    def prepare_in_transaction(
        self,
        db: Session,
        *,
        customer: object,
        actor_id: str | None,
        trigger_type: CustomerLifecycleTrigger,
        source_lead_id: int | None = None,
    ) -> CustomerLifecyclePostCommitWork:
        warnings: list[str] = []
        enrichment_request = None
        profile_request = None

        if self._fields_missing(customer):
            try:
                with self._savepoint(db):
                    enrichment_request = self._ensure_enrichment(db, customer=customer)
            except Exception as exc:
                warnings.append(self._warning("客户初始补全登记失败", exc))
                logger.exception("客户初始补全登记失败，将由恢复任务补偿")

        try:
            with self._savepoint(db):
                profile_request = self.intelligence_service.enqueue_customer_lifecycle_refresh(
                    db,
                    customer=customer,
                    actor_id=actor_id,
                    trigger_type=trigger_type,
                    source_lead_id=source_lead_id,
                    scope="full",
                )
                self._append_request_warning(
                    warnings,
                    prefix="客户档案刷新登记失败",
                    request=profile_request,
                )
        except Exception as exc:
            warnings.append(self._warning("客户档案刷新登记失败", exc))
            logger.exception("客户档案刷新登记失败，将由对账任务补偿")

        return CustomerLifecyclePostCommitWork(
            enrichment_request=enrichment_request,
            profile_request=profile_request,
            warnings=tuple(warnings),
        )

    def enqueue_after_commit(
        self,
        *,
        customer: object,
        actor_id: str | None,
        trigger_type: CustomerLifecycleTrigger,
        source_lead_id: int | None = None,
    ) -> CustomerLifecyclePostCommitWork:
        warnings: list[str] = []
        enrichment_request = None
        profile_request = None

        if self._fields_missing(customer):
            db = None
            try:
                db = self._session_factory()
                enrichment_request = self._ensure_enrichment(db, customer=customer)
                db.commit()
            except Exception as exc:
                if db is not None:
                    db.rollback()
                warnings.append(self._warning("客户初始补全登记失败", exc))
                logger.exception("提交后客户初始补全登记失败，将由恢复任务补偿")
            finally:
                if db is not None:
                    db.close()

        try:
            profile_request = self.intelligence_service.enqueue_customer_lifecycle_refresh_after_commit(
                customer=customer,
                actor_id=actor_id,
                trigger_type=trigger_type,
                source_lead_id=source_lead_id,
                scope="full",
            )
            self._append_request_warning(
                warnings,
                prefix="客户档案刷新登记失败",
                request=profile_request,
            )
        except Exception as exc:
            warnings.append(self._warning("客户档案刷新登记失败", exc))
            logger.exception("提交后客户档案刷新登记失败，将由对账任务补偿")

        return CustomerLifecyclePostCommitWork(
            enrichment_request=enrichment_request,
            profile_request=profile_request,
            profile_kick_pending=False,
            warnings=tuple(warnings),
        )

    def kick(self, work: CustomerLifecyclePostCommitWork) -> tuple[str, ...]:
        warnings = list(work.warnings)
        if work.enrichment_request is not None:
            try:
                self.job_service.kick(work.enrichment_request)
            except Exception as exc:
                warnings.append(self._warning("客户初始补全唤醒失败", exc))
                logger.exception(
                    "客户初始补全唤醒失败，将由恢复任务执行: job=%s",
                    work.enrichment_request.job_public_id,
                )
        if work.profile_kick_pending and work.profile_request is not None:
            try:
                profile_request = work.profile_request
                if not profile_request.kick_required and profile_request.scheduled:
                    profile_request = replace(profile_request, kick_required=True)
                self.profile_refresh_service.kick_committed_event_refresh(profile_request)
            except Exception as exc:
                warnings.append(self._warning("客户档案刷新唤醒失败", exc))
                logger.exception(
                    "客户档案刷新唤醒失败，将由恢复任务执行: request=%s",
                    work.profile_request.request_id,
                )
        return tuple(warnings)

    def _ensure_enrichment(
        self,
        db: Session,
        *,
        customer: object,
    ) -> CustomerEnrichmentJobRequest:
        team_id = self._required_positive_int(customer, "team_id")
        customer_id = self._required_positive_int(customer, "id")
        now = business_now()
        available_at = now + timedelta(seconds=self.settle_seconds)
        profile_gate_deadline_at = available_at + timedelta(seconds=self.profile_gate_max_seconds)
        ensure = getattr(self.job_service, "ensure", None)
        if not callable(ensure):
            ensure = self.job_service.job_crud.ensure
        job = ensure(
            db,
            team_id=team_id,
            customer_id=customer_id,
            purpose=CustomerEnrichmentPurpose.INITIAL_CREATION.value,
            plan_version=ACTIVE_CUSTOMER_ENRICHMENT_PLAN.version,
            requested_fields=list(ACTIVE_CUSTOMER_ENRICHMENT_PLAN.fields),
            available_at=available_at,
            profile_gate_deadline_at=profile_gate_deadline_at,
            max_attempts=self.max_attempts,
            commit=False,
        )
        return CustomerEnrichmentJobRequest(team_id=team_id, job_public_id=str(job.public_id))

    def _fields_missing(self, customer: object) -> bool:
        return any(
            self.field_registry.is_missing(field, getattr(customer, field, None))
            for field in ACTIVE_CUSTOMER_ENRICHMENT_PLAN.fields
        )

    @staticmethod
    def _savepoint(db: Session) -> AbstractContextManager[object]:
        begin_nested = getattr(db, "begin_nested", None)
        return begin_nested() if callable(begin_nested) else nullcontext()

    @staticmethod
    def _required_positive_int(value: object, attribute: str) -> int:
        resolved = getattr(value, attribute, None)
        if isinstance(resolved, bool) or not isinstance(resolved, int) or resolved <= 0:
            raise ValueError(f"客户生命周期缺少有效 {attribute}")
        return resolved

    @staticmethod
    def _append_request_warning(
        warnings: list[str],
        *,
        prefix: str,
        request: object,
    ) -> None:
        schedule_error = getattr(request, "schedule_error", None)
        if schedule_error:
            warnings.append(f"{prefix}: {schedule_error}")

    @staticmethod
    def _warning(prefix: str, exc: Exception) -> str:
        return f"{prefix}: {type(exc).__name__}: {exc}"


customer_lifecycle_post_commit_coordinator = CustomerLifecyclePostCommitCoordinator()
