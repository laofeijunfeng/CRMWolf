"""Read-only candidate retrieval for follow-up task reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from time import perf_counter
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, func, not_, or_

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from app.crud.sales_commitment import follow_up_task_reconciliation_run_crud
from app.models.customer_activity import CustomerActivity
from app.models.sales_commitment import FollowUpTask, FollowUpTaskSourceType, FollowUpTaskStatus
from app.utils.time import business_now

DEFAULT_RECONCILIATION_LOOKBACK_DAYS = 90
DEFAULT_RECONCILIATION_LOOKAHEAD_DAYS = 30


@dataclass(frozen=True)
class TaskReconciliationCandidate:
    """A public-id-only task candidate for semantic reconciliation."""

    public_id: str
    owner_id: str
    title: str
    description: str | None
    due_at: str | None
    due_at_text: str | None
    due_at_granularity: str | None
    due_at_timezone: str | None
    source_type: str | None
    source_public_id: str | None
    confidence: float
    candidate_reasons: tuple[str, ...]
    auto_transition_eligible: bool
    confirmation_required_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "public_id": self.public_id,
            "id": self.public_id,
            "owner_id": self.owner_id,
            "title": self.title,
            "description": self.description,
            "due_at": self.due_at,
            "due_at_text": self.due_at_text,
            "due_at_granularity": self.due_at_granularity,
            "due_at_timezone": self.due_at_timezone,
            "source_type": self.source_type,
            "source_public_id": self.source_public_id,
            "confidence": self.confidence,
            "candidate_reasons": list(self.candidate_reasons),
            "auto_transition_eligible": self.auto_transition_eligible,
            "confirmation_required_reason": self.confirmation_required_reason,
        }


@dataclass(frozen=True)
class TaskReconciliationCandidateSet:
    """Read-only candidate retrieval output for rules, vector rerank, or LLM match."""

    items: list[TaskReconciliationCandidate]
    total: int
    filters: dict[str, Any]
    usage_policy: dict[str, str]
    run_public_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "total": self.total,
            "filters": self.filters,
            "usage_policy": self.usage_policy,
            "run_public_id": self.run_public_id,
        }


class TaskReconciliationService:
    """Retrieves candidate tasks for later semantic matching without mutating task state."""

    def list_candidates_for_activity(
        self,
        db: Session,
        *,
        team_id: int,
        activity_id: int,
        include_cross_owner: bool = False,
        anchor_at: datetime | None = None,
        lookback_days: int = DEFAULT_RECONCILIATION_LOOKBACK_DAYS,
        lookahead_days: int = DEFAULT_RECONCILIATION_LOOKAHEAD_DAYS,
        limit: int = 20,
    ) -> TaskReconciliationCandidateSet:
        activity = (
            db.query(CustomerActivity)
            .filter(CustomerActivity.team_id == team_id, CustomerActivity.id == activity_id)
            .first()
        )
        if activity is None:
            raise ValueError("客户活动不存在")
        if activity.customer_id is None:
            raise ValueError("客户活动缺少客户")
        if not activity.owner_id:
            raise ValueError("客户活动缺少归属人")

        return self.list_candidates(
            db,
            team_id=team_id,
            customer_id=activity.customer_id,
            activity_owner_id=activity.owner_id,
            actor_id=activity.creator_id,
            source_activity_id=activity.id,
            source_public_id=getattr(activity, "public_id", None),
            include_cross_owner=include_cross_owner,
            anchor_at=anchor_at or activity.occurred_at,
            lookback_days=lookback_days,
            lookahead_days=lookahead_days,
            limit=limit,
        )

    def list_candidates(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        activity_owner_id: str,
        actor_id: str | None = None,
        source_activity_id: int | None = None,
        source_public_id: str | None = None,
        include_cross_owner: bool = False,
        anchor_at: datetime | None = None,
        lookback_days: int = DEFAULT_RECONCILIATION_LOOKBACK_DAYS,
        lookahead_days: int = DEFAULT_RECONCILIATION_LOOKAHEAD_DAYS,
        limit: int = 20,
    ) -> TaskReconciliationCandidateSet:
        started_at = business_now()
        started_monotonic = perf_counter()
        anchor = anchor_at or business_now()
        starts_at = anchor - timedelta(days=lookback_days)
        ends_at = anchor + timedelta(days=lookahead_days)

        query = db.query(FollowUpTask).filter(
            FollowUpTask.team_id == team_id,
            FollowUpTask.customer_id == customer_id,
            FollowUpTask.status == FollowUpTaskStatus.OPEN,
            FollowUpTask.due_at >= starts_at,
            FollowUpTask.due_at <= ends_at,
        )
        if not include_cross_owner:
            query = query.filter(FollowUpTask.owner_id == activity_owner_id)
        current_source_filters = []
        if source_activity_id is not None:
            current_source_filters.append(func.coalesce(FollowUpTask.source_activity_id, -1) == source_activity_id)
        if source_public_id:
            current_source_filters.append(func.coalesce(FollowUpTask.source_public_id, "") == source_public_id)
        if current_source_filters:
            query = query.filter(
                not_(
                    and_(
                        FollowUpTask.source_type == FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
                        or_(*current_source_filters),
                    )
                )
            )

        rows = (
            query.order_by(
                FollowUpTask.owner_id != activity_owner_id,
                FollowUpTask.due_at.asc(),
                FollowUpTask.id.asc(),
            )
            .limit(limit)
            .all()
        )
        items = [
            self._candidate_payload(
                task,
                activity_owner_id=activity_owner_id,
            )
            for task in rows
        ]
        filters = {
            "team_id": team_id,
            "customer_id": customer_id,
            "activity_owner_id": activity_owner_id,
            "include_cross_owner": include_cross_owner,
            "status": FollowUpTaskStatus.OPEN,
            "due_at_start": starts_at.isoformat(),
            "due_at_end": ends_at.isoformat(),
            "limit": limit,
            "excluded_current_source": bool(current_source_filters),
        }
        usage_policy = {
            "state_source": "mysql.crm_follow_up_tasks",
            "mutation": "forbidden",
            "cross_owner": "confirmation_only",
        }
        run = follow_up_task_reconciliation_run_crud.record_success(
            db,
            team_id=team_id,
            customer_id=customer_id,
            owner_id=activity_owner_id,
            actor_id=actor_id,
            source_activity_id=source_activity_id,
            source_public_id=source_public_id,
            include_cross_owner=include_cross_owner,
            lookback_days=lookback_days,
            lookahead_days=lookahead_days,
            limit=limit,
            candidate_public_ids=[item.public_id for item in items],
            filters_json=filters,
            usage_policy_json=usage_policy,
            anchor_at=anchor,
            duration_ms=int((perf_counter() - started_monotonic) * 1000),
            started_at=started_at,
        )
        return TaskReconciliationCandidateSet(
            items=items,
            total=len(rows),
            filters=filters,
            usage_policy=usage_policy,
            run_public_id=run.public_id,
        )

    def _candidate_payload(
        self,
        task: FollowUpTask,
        *,
        activity_owner_id: str,
    ) -> TaskReconciliationCandidate:
        is_same_owner = task.owner_id == activity_owner_id
        reasons = ["same_customer", "open_task", "due_window"]
        if is_same_owner:
            reasons.append("same_owner")
        else:
            reasons.append("cross_owner_confirmation_only")
        return TaskReconciliationCandidate(
            public_id=task.public_id,
            owner_id=task.owner_id,
            title=task.title,
            description=task.description,
            due_at=task.due_at.isoformat() if task.due_at else None,
            due_at_text=task.due_at_text,
            due_at_granularity=task.due_at_granularity,
            due_at_timezone=task.due_at_timezone,
            source_type=task.source_type,
            source_public_id=task.source_public_id,
            confidence=task.confidence,
            candidate_reasons=tuple(reasons),
            auto_transition_eligible=is_same_owner,
            confirmation_required_reason=None if is_same_owner else "CROSS_OWNER",
        )


task_reconciliation_service = TaskReconciliationService()
