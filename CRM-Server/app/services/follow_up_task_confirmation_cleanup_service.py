"""Cleanup service for stale follow-up task confirmation cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.crud.sales_commitment import follow_up_task_confirmation_case_crud
from app.models.sales_commitment import FollowUpTaskConfirmationStatus
from app.utils.time import business_now

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

    from app.models.sales_commitment import FollowUpTaskConfirmationCase


class FollowUpTaskConfirmationCaseCleanupCrudProtocol(Protocol):
    def list_expired_pending(
        self,
        db: Session,
        *,
        team_id: int | None = None,
        before: datetime | None = None,
        skip: int = 0,
        limit: int = 500,
    ) -> tuple[list[FollowUpTaskConfirmationCase], int]: ...

    def mark_expired(
        self,
        db: Session,
        db_obj: FollowUpTaskConfirmationCase,
        *,
        expired_at: datetime | None = None,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCase: ...

    def list_pending_by_task(
        self,
        db: Session,
        *,
        team_id: int,
        task_id: int,
        skip: int = 0,
        limit: int = 500,
    ) -> tuple[list[FollowUpTaskConfirmationCase], int]: ...

    def list_pending_by_source_activity(
        self,
        db: Session,
        *,
        team_id: int,
        source_activity_id: int,
        skip: int = 0,
        limit: int = 500,
    ) -> tuple[list[FollowUpTaskConfirmationCase], int]: ...

    def mark_cancelled(
        self,
        db: Session,
        db_obj: FollowUpTaskConfirmationCase,
        *,
        cancelled_at: datetime | None = None,
        cancelled_by_id: str | None = None,
        cancelled_reason: str,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCase: ...


class FollowUpTaskConfirmationCancelReason:
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_CANCELLED = "TASK_CANCELLED"
    SOURCE_ACTIVITY_DELETED = "SOURCE_ACTIVITY_DELETED"
    SOURCE_ACTIVITY_REVISION_CONTRACT_INVALID = "SOURCE_ACTIVITY_REVISION_CONTRACT_INVALID"
    SOURCE_NEXT_STEP_REMOVED = "SOURCE_NEXT_STEP_REMOVED"
    SOURCE_TASK_SUPERSEDED = "SOURCE_TASK_SUPERSEDED"
    SOURCE_ACTIVITY_REVISION_SUPERSEDED = "SOURCE_ACTIVITY_REVISION_SUPERSEDED"


@dataclass(frozen=True)
class FollowUpTaskConfirmationCleanupResult:
    expired_count: int
    scanned_count: int
    total_expired_pending: int
    expired_case_public_ids: tuple[str, ...]
    cancelled_count: int = 0
    cancelled_case_public_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "expired_count": self.expired_count,
            "cancelled_count": self.cancelled_count,
            "scanned_count": self.scanned_count,
            "total_expired_pending": self.total_expired_pending,
            "expired_case_public_ids": list(self.expired_case_public_ids),
            "cancelled_case_public_ids": list(self.cancelled_case_public_ids),
        }


class FollowUpTaskConfirmationCleanupService:
    """Expires pending confirmation cases whose reply window has elapsed."""

    def __init__(
        self,
        *,
        confirmation_case_crud: FollowUpTaskConfirmationCaseCleanupCrudProtocol = (
            follow_up_task_confirmation_case_crud
        ),
    ) -> None:
        self.confirmation_case_crud = confirmation_case_crud

    def expire_pending_cases(
        self,
        db: Session,
        *,
        team_id: int | None = None,
        before: datetime | None = None,
        limit: int = 500,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCleanupResult:
        resolved_before = before or business_now()
        cases, total = self.confirmation_case_crud.list_expired_pending(
            db,
            team_id=team_id,
            before=resolved_before,
            limit=limit,
        )
        expired_public_ids: list[str] = []
        for case in cases:
            if case.status != FollowUpTaskConfirmationStatus.PENDING:
                continue
            self.confirmation_case_crud.mark_expired(
                db,
                case,
                expired_at=resolved_before,
                commit=False,
            )
            expired_public_ids.append(case.public_id)

        if commit and expired_public_ids:
            db.commit()

        return FollowUpTaskConfirmationCleanupResult(
            expired_count=len(expired_public_ids),
            cancelled_count=0,
            scanned_count=len(cases),
            total_expired_pending=total,
            expired_case_public_ids=tuple(expired_public_ids),
            cancelled_case_public_ids=(),
        )

    def cancel_pending_cases_for_task(
        self,
        db: Session,
        *,
        team_id: int,
        task_id: int,
        actor_id: str | None = None,
        reason: str,
        cancelled_at: datetime | None = None,
        limit: int = 500,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCleanupResult:
        cases, total = self.confirmation_case_crud.list_pending_by_task(
            db,
            team_id=team_id,
            task_id=task_id,
            limit=limit,
        )
        return self._cancel_cases(
            db,
            cases=cases,
            total=total,
            actor_id=actor_id,
            reason=reason,
            cancelled_at=cancelled_at,
            commit=commit,
        )

    def cancel_pending_cases_for_source_activity(
        self,
        db: Session,
        *,
        team_id: int,
        source_activity_id: int,
        actor_id: str | None = None,
        reason: str,
        cancelled_at: datetime | None = None,
        limit: int = 500,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCleanupResult:
        cases, total = self.confirmation_case_crud.list_pending_by_source_activity(
            db,
            team_id=team_id,
            source_activity_id=source_activity_id,
            limit=limit,
        )
        return self._cancel_cases(
            db,
            cases=cases,
            total=total,
            actor_id=actor_id,
            reason=reason,
            cancelled_at=cancelled_at,
            commit=commit,
        )

    def _cancel_cases(
        self,
        db: Session,
        *,
        cases: list[FollowUpTaskConfirmationCase],
        total: int,
        actor_id: str | None,
        reason: str,
        cancelled_at: datetime | None,
        commit: bool,
    ) -> FollowUpTaskConfirmationCleanupResult:
        resolved_cancelled_at = cancelled_at or business_now()
        cancelled_public_ids: list[str] = []
        for case in cases:
            if case.status != FollowUpTaskConfirmationStatus.PENDING:
                continue
            self.confirmation_case_crud.mark_cancelled(
                db,
                case,
                cancelled_at=resolved_cancelled_at,
                cancelled_by_id=actor_id,
                cancelled_reason=reason,
                commit=False,
            )
            cancelled_public_ids.append(case.public_id)

        if commit and cancelled_public_ids:
            db.commit()

        return FollowUpTaskConfirmationCleanupResult(
            expired_count=0,
            cancelled_count=len(cancelled_public_ids),
            scanned_count=len(cases),
            total_expired_pending=0,
            expired_case_public_ids=(),
            cancelled_case_public_ids=tuple(cancelled_public_ids),
        )


follow_up_task_confirmation_cleanup_service = FollowUpTaskConfirmationCleanupService()
