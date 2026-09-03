"""Durable Agent-only opportunity suggestion execution.

The job is deliberately a read/reasoning boundary: it never creates an
opportunity and never moves an opportunity stage.  Those actions are resumed
through separate, user-visible Agent interactions after this job completes.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.crud.customer import customer_crud
from app.crud.customer_opportunity_suggestion_job import (
    CustomerOpportunitySuggestionJobCRUD,
    customer_opportunity_suggestion_job_crud,
)
from app.crud.procurement import procurement_stage_template_crud
from app.models.customer_activity import CustomerActivity
from app.models.opportunity import Opportunity, OpportunityStatus
from app.services.agent.schemas import AgentBusinessSuggestion, AgentSemanticParseResult
from app.services.agent.suggestion import (
    AgentSuggestionEnvelope,
    AgentSuggestionGenerator,
    agent_suggestion_generator,
)
from app.services.ai_task_limiter import ai_generation_semaphore
from app.services.customer_activity_contracts import (
    CustomerActivitySubmissionSource,
    CustomerActivitySuggestionJobStatus,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

    from app.models.customer import Customer
    from app.models.customer_opportunity_suggestion_job import CustomerOpportunitySuggestionJob

logger = logging.getLogger(__name__)
_TERMINAL = {
    CustomerActivitySuggestionJobStatus.COMPLETED.value,
    CustomerActivitySuggestionJobStatus.SKIPPED.value,
    CustomerActivitySuggestionJobStatus.EXHAUSTED.value,
}


class CustomerOpportunitySuggestionJobRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_public_id: str
    team_id: int


class CustomerOpportunitySuggestionJobRunResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_public_id: str
    activity_id: int
    execution_status: str
    success: bool
    retryable: bool = False
    skip_reason: str | None = None
    error: str | None = None
    decision: str | None = None
    suggestion: dict[str, Any] | None = None
    silent_reason: str | None = None


class CustomerOpportunitySuggestionJobService:
    def __init__(
        self,
        *,
        job_crud: CustomerOpportunitySuggestionJobCRUD | None = None,
        suggestion_generator: AgentSuggestionGenerator | None = None,
    ) -> None:
        self.job_crud = job_crud or customer_opportunity_suggestion_job_crud
        self.suggestion_generator = suggestion_generator or agent_suggestion_generator

    def enqueue_in_transaction(
        self,
        db: Session,
        *,
        activity: CustomerActivity,
    ) -> CustomerOpportunitySuggestionJobRequest | None:
        if str(activity.submission_source) != CustomerActivitySubmissionSource.AGENT.value:
            return None
        job = self.job_crud.enqueue(
            db,
            team_id=int(activity.team_id),
            activity_id=int(activity.id),
            activity_revision=int(activity.activity_revision or 1),
            submission_source=CustomerActivitySubmissionSource.AGENT.value,
            commit=False,
        )
        return CustomerOpportunitySuggestionJobRequest(
            job_public_id=str(job.public_id),
            team_id=int(job.team_id),
        )

    async def run(self, request: CustomerOpportunitySuggestionJobRequest) -> CustomerOpportunitySuggestionJobRunResult:
        settings = get_settings()
        max_attempts = max(1, settings.CUSTOMER_ACTIVITY_SUGGESTION_JOB_MAX_ATTEMPTS)
        now = business_now()
        lease_token = uuid4().hex
        lease_expires_at = now + timedelta(seconds=max(30, settings.CUSTOMER_ACTIVITY_SUGGESTION_JOB_LEASE_SECONDS))

        db = SessionLocal()
        try:
            existing = self.job_crud.get_by_public_id(db, team_id=request.team_id, public_id=request.job_public_id)
            if existing is None:
                raise ValueError("客户商机建议任务不存在")
            if existing.status in _TERMINAL:
                return self._persisted_result(existing, request)
            if int(existing.attempt_count or 0) >= max_attempts:
                exhausted = self._result(
                    request,
                    activity_id=int(existing.activity_id),
                    execution_status=CustomerActivitySuggestionJobStatus.EXHAUSTED.value,
                    success=False,
                    error=existing.error_message or "商机建议任务重试次数已耗尽",
                )
                self.job_crud.mark_exhausted_if_attempts_exceeded(
                    db,
                    team_id=request.team_id,
                    public_id=request.job_public_id,
                    max_attempts=max_attempts,
                    result_json=exhausted.model_dump(mode="json"),
                    error_message=exhausted.error or "商机建议任务重试次数已耗尽",
                    commit=True,
                )
                return exhausted
            job = self.job_crud.claim_for_execution(
                db,
                team_id=request.team_id,
                public_id=request.job_public_id,
                lease_token=lease_token,
                lease_expires_at=lease_expires_at,
                max_attempts=max_attempts,
                now=now,
                commit=False,
            )
            if job is None:
                return self._result(
                    request,
                    activity_id=int(existing.activity_id),
                    execution_status="BUSY",
                    success=False,
                    retryable=True,
                )
            activity = (
                db.query(CustomerActivity)
                .filter(
                    CustomerActivity.id == int(job.activity_id),
                    CustomerActivity.team_id == int(job.team_id),
                )
                .one_or_none()
            )
            skip_reason = self._preflight_skip_reason(job=job, activity=activity)
            if skip_reason:
                return self._mark_skipped(db, request=request, job=job, lease_token=lease_token, reason=skip_reason)
            job_data = {
                "activity_id": int(job.activity_id),
                "activity_revision": int(job.activity_revision),
                "attempt_count": int(job.attempt_count),
                "activity": self._activity_data(activity),
                "customer_id": int(activity.customer_id),
                "team_id": int(activity.team_id),
            }
            # Persist the claim before doing any potentially failing context
            # assembly.  A failure after this point can safely transition the
            # leased job to RETRY_PENDING/EXHAUSTED in a fresh session.
            db.commit()
        finally:
            db.close()

        try:
            context_db = SessionLocal()
            try:
                job_data["context"] = self._build_customer_context(
                    context_db,
                    customer_id=int(job_data["customer_id"]),
                    team_id=int(job_data["team_id"]),
                )
            finally:
                context_db.close()
        except Exception as exc:
            logger.exception("客户商机建议任务准备阶段失败: job=%s", request.job_public_id)
            return await self._record_failure(
                request,
                lease_token=lease_token,
                activity_id=int(job_data["activity_id"]),
                attempt_count=int(job_data["attempt_count"]),
                exc=exc,
            )

        try:
            semantic = self._semantic_from_activity(job_data["activity"])
            suggestion_db = SessionLocal()
            try:
                async with ai_generation_semaphore:
                    envelope = await self.suggestion_generator.generate_with_metadata(
                        suggestion_db,
                        team_id=request.team_id,
                        user_message=str(job_data["activity"].get("source_content") or ""),
                        semantic_result=semantic,
                        customer_context=job_data["context"],
                    )
            finally:
                suggestion_db.close()
            result = self._decision_result(request, job_data, envelope)
            db = SessionLocal()
            try:
                updated = self.job_crud.mark_completed_if_lease_owner(
                    db,
                    team_id=request.team_id,
                    public_id=request.job_public_id,
                    lease_token=lease_token,
                    result_json=result.model_dump(mode="json"),
                    skipped=False,
                )
                if updated is None:
                    return self._lease_lost_result(request, int(job_data["activity_id"]))
            finally:
                db.close()
            return result
        except Exception as exc:
            logger.exception("客户商机建议任务执行失败: job=%s", request.job_public_id)
            return await self._record_failure(
                request,
                lease_token=lease_token,
                activity_id=int(job_data["activity_id"]),
                attempt_count=int(job_data["attempt_count"]),
                exc=exc,
            )

    async def _record_failure(
        self,
        request: CustomerOpportunitySuggestionJobRequest,
        *,
        lease_token: str,
        activity_id: int,
        attempt_count: int,
        exc: Exception,
    ) -> CustomerOpportunitySuggestionJobRunResult:
        settings = get_settings()
        error = str(exc)[:4000]
        db = SessionLocal()
        try:
            if attempt_count >= max(1, settings.CUSTOMER_ACTIVITY_SUGGESTION_JOB_MAX_ATTEMPTS):
                result = self._result(
                    request,
                    activity_id=activity_id,
                    execution_status=CustomerActivitySuggestionJobStatus.EXHAUSTED.value,
                    success=False,
                    error=error,
                )
                updated = self.job_crud.mark_exhausted_if_lease_owner(
                    db,
                    team_id=request.team_id,
                    public_id=request.job_public_id,
                    lease_token=lease_token,
                    result_json=result.model_dump(mode="json"),
                    error_message=error,
                )
            else:
                updated = self.job_crud.mark_retry_pending_if_lease_owner(
                    db,
                    team_id=request.team_id,
                    public_id=request.job_public_id,
                    lease_token=lease_token,
                    error_message=error,
                    next_attempt_at=self._next_attempt_at(attempt_count),
                )
                result = self._result(
                    request,
                    activity_id=activity_id,
                    execution_status=CustomerActivitySuggestionJobStatus.RETRY_PENDING.value,
                    success=False,
                    retryable=True,
                    error=error,
                )
            if updated is None:
                return self._lease_lost_result(request, activity_id)
            return result
        finally:
            db.close()

    def _decision_result(
        self,
        request: CustomerOpportunitySuggestionJobRequest,
        job_data: dict[str, Any],
        envelope: AgentSuggestionEnvelope,
    ) -> CustomerOpportunitySuggestionJobRunResult:
        allowed = {"CREATE_OPPORTUNITY", "MOVE_OPPORTUNITY_STAGE", "NO_ACTION"}
        suggestions = [item for item in envelope.result.suggestions if item.action in allowed]
        active_opportunities = [
            item
            for item in job_data["context"].get("opportunities", [])
            if self._is_active_opportunity_status(item.get("status"))
        ]
        for item in suggestions:
            if (
                item.action == "CREATE_OPPORTUNITY"
                and item.confidence >= 0.85
                and self._matches_existing_opportunity(item, active_opportunities)
            ):
                return self._result(
                    request,
                    activity_id=int(job_data["activity_id"]),
                    execution_status=CustomerActivitySuggestionJobStatus.COMPLETED.value,
                    success=True,
                    decision="NO_ACTION",
                    silent_reason="HIGH_CONFIDENCE_EXISTING_OPPORTUNITY",
                )
        selected = suggestions[0] if suggestions else None
        if selected is None:
            return self._result(
                request,
                activity_id=int(job_data["activity_id"]),
                execution_status=CustomerActivitySuggestionJobStatus.COMPLETED.value,
                success=True,
                decision="NO_ACTION",
            )
        return self._result(
            request,
            activity_id=int(job_data["activity_id"]),
            execution_status=CustomerActivitySuggestionJobStatus.COMPLETED.value,
            success=True,
            decision=selected.action,
            suggestion=selected.model_dump(mode="json"),
        )

    @classmethod
    def _matches_existing_opportunity(
        cls, suggestion: AgentBusinessSuggestion, opportunities: list[dict[str, Any]]
    ) -> bool:
        """Return true only for a high-confidence, non-destructive duplicate.

        The model normally returns ``related_object_id`` from the supplied
        opportunity context.  The payload fallback handles models that omit
        that field but still echo enough structured business identity.  It is
        intentionally conservative: weak/partial matches remain visible to
        the Agent instead of being silently discarded.
        """

        payload = suggestion.execution_payload or {}
        related_id = suggestion.related_object_id or payload.get("opportunity_id")
        if related_id is not None:
            return any(
                str(item.get("id")) == str(related_id) or str(item.get("public_id")) == str(related_id)
                for item in opportunities
            )

        name = cls._normalised_text(payload.get("opportunity_name"))
        if name and any(name == cls._normalised_text(item.get("opportunity_name")) for item in opportunities):
            return True

        comparable_fields = (
            "purchase_type",
            "license_type",
            "user_count",
            "total_amount",
        )
        for item in opportunities:
            matches = sum(
                1
                for field in comparable_fields
                if cls._business_values_match(payload.get(field), item.get(field), field=field)
            )
            if matches >= 2:
                return True
        return False

    @staticmethod
    def _normalised_text(value: object) -> str:
        return "".join(str(value or "").strip().lower().split())

    @staticmethod
    def _business_values_match(left: object, right: object, *, field: str) -> bool:
        if left in (None, "") or right in (None, ""):
            return False
        if field in {"user_count", "total_amount"}:
            try:
                return abs(float(left) - float(right)) < 0.01
            except (TypeError, ValueError):
                return False
        return str(left).strip().upper() == str(right).strip().upper()

    @staticmethod
    def _is_active_opportunity_status(value: object) -> bool:
        if hasattr(value, "value"):
            value = value.value
        normalized = str(value).strip().upper()
        return normalized in {
            str(OpportunityStatus.FOLLOWING.value),
            OpportunityStatus.FOLLOWING.name,
            f"{OpportunityStatus.__name__.upper()}.{OpportunityStatus.FOLLOWING.name}",
        }

    def _build_customer_context(
        self,
        db: Session,
        *,
        customer_id: int,
        team_id: int,
    ) -> dict[str, Any]:
        customer = customer_crud.get_by_id(db, customer_id, team_id)
        opportunities = (
            db.query(Opportunity)
            .filter(Opportunity.team_id == team_id, Opportunity.customer_id == customer_id)
            .order_by(Opportunity.created_time.desc())
            .all()
        )
        opportunity_items = [self._opportunity_data(item) for item in opportunities]
        active_stage_context = []
        for opportunity in opportunities:
            if not self._is_active_opportunity_status(opportunity.status) or not opportunity.procurement_method_id:
                continue
            stages = procurement_stage_template_crud.get_by_method(
                db, int(opportunity.procurement_method_id), int(opportunity.team_id)
            )
            current_snapshot_id = getattr(opportunity, "current_stage_snapshot_id", None)
            current_template_id = None
            if current_snapshot_id:
                row = db.execute(
                    __import__("sqlalchemy").text(
                        "SELECT procurement_stage_template_id FROM crm_opportunity_stage_snapshots WHERE id = :id"
                    ),
                    {"id": current_snapshot_id},
                ).first()
                current_template_id = row[0] if row else None
            active_stage_context.append(
                {
                    "opportunity": self._opportunity_data(opportunity),
                    "procurement_stages": [
                        {
                            "id": int(stage.id),
                            "stage_name": stage.stage_name,
                            "win_probability": stage.win_probability,
                            "sort_order": stage.sort_order,
                            "is_current": current_template_id is not None and int(stage.id) == int(current_template_id),
                            "is_default_start": bool(stage.is_default_start),
                            "can_skip": bool(stage.can_skip),
                        }
                        for stage in stages
                    ],
                }
            )
        return {
            "customer": self._customer_data(customer),
            "opportunities": opportunity_items,
            "active_opportunity_stage_context": active_stage_context,
            "contracts": [],
            "payment_plans": [],
            "deployment_infos": [],
        }

    @staticmethod
    def _customer_data(customer: Customer | None) -> dict[str, Any] | None:
        if customer is None:
            return None
        return {
            "id": customer.public_id,
            "public_id": customer.public_id,
            "account_name": customer.account_name,
            "industry": customer.industry,
            "city": customer.city,
            "company_scale": customer.company_scale,
            "status": customer.status,
        }

    @staticmethod
    def _opportunity_data(opportunity: Opportunity) -> dict[str, Any]:
        return {
            "id": opportunity.public_id,
            "public_id": opportunity.public_id,
            "opportunity_name": opportunity.opportunity_name,
            "status": opportunity.status.value if hasattr(opportunity.status, "value") else opportunity.status,
            "approval_phase": str(opportunity.approval_phase or "").lower(),
            "procurement_method_id": opportunity.procurement_method_id,
            "license_type": (
                opportunity.license_type.value
                if hasattr(opportunity.license_type, "value")
                else opportunity.license_type
            ),
            "subscription_years": opportunity.subscription_years,
            "current_stage_name": opportunity.current_stage_name,
            "current_win_probability": opportunity.current_win_probability,
            "total_amount": float(opportunity.total_amount) if opportunity.total_amount is not None else None,
            "user_count": opportunity.user_count,
            "purchase_type": opportunity.purchase_type,
        }

    @staticmethod
    def _activity_data(activity: CustomerActivity) -> dict[str, Any]:
        content = activity.content_json
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                content = {}
        return {
            "id": int(activity.id),
            "activity_kind": activity.activity_kind,
            "title": activity.title,
            "source_content": activity.source_content,
            "content_json": content if isinstance(content, dict) else {},
            "summary": activity.summary,
            "next_action": activity.next_action,
            "next_follow_time": activity.next_follow_time,
        }

    @staticmethod
    def _semantic_from_activity(activity: dict[str, Any]) -> AgentSemanticParseResult:
        return AgentSemanticParseResult.model_validate(
            {
                "intent": "CUSTOMER_ACTIVITY",
                "intent_confidence": 1.0,
                "follow_up": {
                    "content": activity.get("source_content"),
                    "next_action": activity.get("next_action"),
                },
            }
        )

    @staticmethod
    def _preflight_skip_reason(
        *, job: CustomerOpportunitySuggestionJob, activity: CustomerActivity | None
    ) -> str | None:
        if activity is None:
            return "SOURCE_ACTIVITY_DELETED"
        if int(activity.activity_revision or 1) != int(job.activity_revision):
            return "SUPERSEDED_ACTIVITY_REVISION"
        if str(activity.submission_source) != CustomerActivitySubmissionSource.AGENT.value:
            return "INVALID_SUBMISSION_SOURCE"
        return None

    def _mark_skipped(
        self,
        db: Session,
        *,
        request: CustomerOpportunitySuggestionJobRequest,
        job: CustomerOpportunitySuggestionJob,
        lease_token: str,
        reason: str,
    ) -> CustomerOpportunitySuggestionJobRunResult:
        result = self._result(
            request,
            activity_id=int(job.activity_id),
            execution_status=CustomerActivitySuggestionJobStatus.SKIPPED.value,
            success=True,
            skip_reason=reason,
        )
        updated = self.job_crud.mark_completed_if_lease_owner(
            db,
            team_id=request.team_id,
            public_id=request.job_public_id,
            lease_token=lease_token,
            result_json=result.model_dump(mode="json"),
            skipped=True,
        )
        if updated is None:
            return self._lease_lost_result(request, int(job.activity_id))
        return result

    @staticmethod
    def _next_attempt_at(attempt_count: int) -> datetime:
        settings = get_settings()
        base = max(1, settings.CUSTOMER_ACTIVITY_SUGGESTION_JOB_RETRY_BASE_SECONDS)
        return business_now() + timedelta(seconds=base * (2 ** max(0, attempt_count - 1)))

    @staticmethod
    def _result(
        request: CustomerOpportunitySuggestionJobRequest,
        *,
        activity_id: int,
        execution_status: str,
        success: bool,
        retryable: bool = False,
        skip_reason: str | None = None,
        error: str | None = None,
        decision: str | None = None,
        suggestion: dict[str, Any] | None = None,
        silent_reason: str | None = None,
    ) -> CustomerOpportunitySuggestionJobRunResult:
        return CustomerOpportunitySuggestionJobRunResult(
            job_public_id=request.job_public_id,
            activity_id=activity_id,
            execution_status=execution_status,
            success=success,
            retryable=retryable,
            skip_reason=skip_reason,
            error=error,
            decision=decision,
            suggestion=suggestion,
            silent_reason=silent_reason,
        )

    @classmethod
    def _persisted_result(
        cls, job: CustomerOpportunitySuggestionJob, request: CustomerOpportunitySuggestionJobRequest
    ) -> CustomerOpportunitySuggestionJobRunResult:
        if isinstance(job.result_json, dict):
            try:
                return CustomerOpportunitySuggestionJobRunResult.model_validate(job.result_json)
            except Exception:
                pass
        return cls._result(
            request,
            activity_id=int(job.activity_id),
            execution_status=str(job.status),
            success=job.status
            in {CustomerActivitySuggestionJobStatus.COMPLETED.value, CustomerActivitySuggestionJobStatus.SKIPPED.value},
            error=job.error_message,
        )

    @staticmethod
    def _lease_lost_result(
        request: CustomerOpportunitySuggestionJobRequest, activity_id: int
    ) -> CustomerOpportunitySuggestionJobRunResult:
        return CustomerOpportunitySuggestionJobRunResult(
            job_public_id=request.job_public_id,
            activity_id=activity_id,
            execution_status="LEASE_LOST",
            success=False,
            retryable=True,
            error="execution lease ownership changed before persistence",
        )

    def kick(self, request: CustomerOpportunitySuggestionJobRequest | None) -> None:
        if request is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(self._run_guarded(request))
        task.add_done_callback(self._consume_task_exception)

    async def _run_guarded(self, request: CustomerOpportunitySuggestionJobRequest) -> None:
        try:
            await self.run(request)
        except Exception:
            logger.exception("客户商机建议任务即时执行失败: job=%s", request.job_public_id)

    @staticmethod
    def _consume_task_exception(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        try:
            task.exception()
        except Exception:
            logger.exception("客户商机建议后台任务回调失败")


customer_opportunity_suggestion_job_service = CustomerOpportunitySuggestionJobService()
