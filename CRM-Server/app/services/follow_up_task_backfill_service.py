from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.customer_activity import CustomerActivity
from app.models.sales_commitment import FollowUpTaskProjectionTrigger
from app.services.follow_up_task_projection_service import (
    FollowUpTaskProjectionResult,
    FollowUpTaskProjectionSkipReason,
    follow_up_task_projection_service,
)
from app.utils.time import business_now


@dataclass(frozen=True)
class FollowUpTaskBackfillResult:
    dry_run: bool
    team_id: int | None
    days: int
    cutoff: datetime
    scanned_activity_count: int = 0
    selected_group_count: int = 0
    duplicate_group_activity_count: int = 0
    missing_owner_count: int = 0
    skipped_no_owner_count: int = 0
    skipped_no_due_at_count: int = 0
    would_project_count: int = 0
    projection_run_ids: list[int] = field(default_factory=list)
    created_task_count: int = 0
    updated_task_count: int = 0
    cancelled_task_count: int = 0
    created_commitment_count: int = 0
    updated_commitment_count: int = 0
    skipped_projection_count: int = 0
    failed_projection_count: int = 0
    projection_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "team_id": self.team_id,
            "days": self.days,
            "cutoff": self.cutoff.isoformat(),
            "scanned_activity_count": self.scanned_activity_count,
            "selected_group_count": self.selected_group_count,
            "duplicate_group_activity_count": self.duplicate_group_activity_count,
            "missing_owner_count": self.missing_owner_count,
            "skipped_no_owner_count": self.skipped_no_owner_count,
            "skipped_no_due_at_count": self.skipped_no_due_at_count,
            "would_project_count": self.would_project_count,
            "projection_run_ids": self.projection_run_ids,
            "created_task_count": self.created_task_count,
            "updated_task_count": self.updated_task_count,
            "cancelled_task_count": self.cancelled_task_count,
            "created_commitment_count": self.created_commitment_count,
            "updated_commitment_count": self.updated_commitment_count,
            "skipped_projection_count": self.skipped_projection_count,
            "failed_projection_count": self.failed_projection_count,
            "projection_errors": self.projection_errors,
        }


class FollowUpTaskBackfillService:
    def backfill_customer_activities(
        self,
        db: Session,
        *,
        team_id: int | None = None,
        days: int = 90,
        limit: int = 1000,
        dry_run: bool = True,
        actor_id: str | None = None,
        now: datetime | None = None,
        commit: bool = True,
    ) -> FollowUpTaskBackfillResult:
        if days <= 0:
            raise ValueError("days 必须大于 0")
        if limit <= 0:
            raise ValueError("limit 必须大于 0")

        anchor_now = now or business_now()
        cutoff = anchor_now - timedelta(days=days)
        activities = self._load_recent_activities(
            db,
            team_id=team_id,
            cutoff=cutoff,
            limit=limit,
        )
        selected, duplicate_group_count, missing_owner_count, skipped_no_owner_count = self._select_latest_per_group(activities)
        skipped_no_due_at_count = sum(1 for activity in selected if activity.next_follow_time is None)
        projectable = [activity for activity in selected if activity.next_follow_time is not None]

        if dry_run:
            return FollowUpTaskBackfillResult(
                dry_run=True,
                team_id=team_id,
                days=days,
                cutoff=cutoff,
                scanned_activity_count=len(activities),
                selected_group_count=len(selected),
                duplicate_group_activity_count=duplicate_group_count,
                missing_owner_count=missing_owner_count,
                skipped_no_owner_count=skipped_no_owner_count,
                skipped_no_due_at_count=skipped_no_due_at_count,
                would_project_count=len(projectable),
            )

        projection_results: list[FollowUpTaskProjectionResult] = []
        for activity in projectable:
            if not activity.owner_id:
                activity.owner_id = activity.creator_id
                db.flush()
            projection_results.append(
                follow_up_task_projection_service.run_activity_projection(
                    db,
                    activity_id=activity.id,
                    trigger_type=FollowUpTaskProjectionTrigger.HISTORICAL_BACKFILL,
                    actor_id=actor_id or activity.owner_id,
                    activity_snapshot=activity,
                    commit=False,
                )
            )

        if commit:
            db.commit()

        return self._summarize_results(
            dry_run=False,
            team_id=team_id,
            days=days,
            cutoff=cutoff,
            scanned_activity_count=len(activities),
            selected_group_count=len(selected),
            duplicate_group_count=duplicate_group_count,
            missing_owner_count=missing_owner_count,
            skipped_no_owner_count=skipped_no_owner_count,
            skipped_no_due_at_count=skipped_no_due_at_count,
            projection_results=projection_results,
        )

    def _load_recent_activities(
        self,
        db: Session,
        *,
        team_id: int | None,
        cutoff: datetime,
        limit: int,
    ) -> list[CustomerActivity]:
        query = db.query(CustomerActivity).filter(
            CustomerActivity.customer_id.isnot(None),
            CustomerActivity.occurred_at >= cutoff,
        )
        if team_id is not None:
            query = query.filter(CustomerActivity.team_id == team_id)
        return (
            query.order_by(CustomerActivity.occurred_at.desc(), CustomerActivity.id.desc())
            .limit(limit)
            .all()
        )

    def _select_latest_per_group(
        self,
        activities: list[CustomerActivity],
    ) -> tuple[list[CustomerActivity], int, int, int]:
        selected_by_group: dict[tuple[int, int, str], CustomerActivity] = {}
        duplicate_group_count = 0
        missing_owner_count = 0
        skipped_no_owner_count = 0

        for activity in activities:
            owner_id = activity.owner_id or activity.creator_id
            if not activity.owner_id and activity.creator_id:
                missing_owner_count += 1
            if not owner_id:
                skipped_no_owner_count += 1
                continue
            group_key = (activity.team_id, activity.customer_id, str(owner_id))
            if group_key in selected_by_group:
                duplicate_group_count += 1
                continue
            selected_by_group[group_key] = activity

        return list(selected_by_group.values()), duplicate_group_count, missing_owner_count, skipped_no_owner_count

    def _summarize_results(
        self,
        *,
        dry_run: bool,
        team_id: int | None,
        days: int,
        cutoff: datetime,
        scanned_activity_count: int,
        selected_group_count: int,
        duplicate_group_count: int,
        missing_owner_count: int,
        skipped_no_owner_count: int,
        skipped_no_due_at_count: int,
        projection_results: list[FollowUpTaskProjectionResult],
    ) -> FollowUpTaskBackfillResult:
        projection_run_ids = [
            result.projection_run_id
            for result in projection_results
            if result.projection_run_id is not None
        ]
        projection_errors = [
            result.error_message
            for result in projection_results
            if result.error_message
        ]
        return FollowUpTaskBackfillResult(
            dry_run=dry_run,
            team_id=team_id,
            days=days,
            cutoff=cutoff,
            scanned_activity_count=scanned_activity_count,
            selected_group_count=selected_group_count,
            duplicate_group_activity_count=duplicate_group_count,
            missing_owner_count=missing_owner_count,
            skipped_no_owner_count=skipped_no_owner_count,
            skipped_no_due_at_count=skipped_no_due_at_count,
            would_project_count=len(projection_results),
            projection_run_ids=projection_run_ids,
            created_task_count=sum(len(result.created_task_ids) for result in projection_results),
            updated_task_count=sum(len(result.updated_task_ids) for result in projection_results),
            cancelled_task_count=sum(len(result.cancelled_task_ids) for result in projection_results),
            created_commitment_count=sum(len(result.created_commitment_ids) for result in projection_results),
            updated_commitment_count=sum(len(result.updated_commitment_ids) for result in projection_results),
            skipped_projection_count=sum(
                1
                for result in projection_results
                if result.skip_reason
                and result.skip_reason
                not in {
                    FollowUpTaskProjectionSkipReason.ACTIVITY_NOT_FOUND,
                }
            ),
            failed_projection_count=sum(1 for result in projection_results if result.error_message),
            projection_errors=projection_errors,
        )


follow_up_task_backfill_service = FollowUpTaskBackfillService()
