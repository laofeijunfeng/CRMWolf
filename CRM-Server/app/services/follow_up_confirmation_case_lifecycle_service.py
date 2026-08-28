"""Transactional lifecycle for follow-up confirmation Cases and projections."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.crud.sales_commitment import follow_up_task_confirmation_case_crud
from app.models.sales_commitment import FollowUpTaskConfirmationStatus
from app.utils.time import business_now

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

    from app.models.sales_commitment import FollowUpTaskConfirmationCase
    from app.services.agent.ui.actions import AgentUIActionRepository


class FollowUpConfirmationCaseLifecycleService:
    """Keep the authoritative Case and its Agent UI projections consistent."""

    def __init__(
        self,
        *,
        case_crud: object = follow_up_task_confirmation_case_crud,
        action_repository: AgentUIActionRepository | None = None,
        enable_action_projection: bool = False,
    ) -> None:
        self.case_crud = case_crud
        self.action_repository = action_repository
        self._enable_action_projection = enable_action_projection

    def _action_repository(self) -> AgentUIActionRepository | None:
        if not self._enable_action_projection:
            return None
        if self.action_repository is None:
            from app.services.agent.ui.actions import AgentUIActionRepository

            self.action_repository = AgentUIActionRepository()
        return self.action_repository

    def expire_locked_case(
        self,
        db: Session,
        *,
        team_id: int,
        case: FollowUpTaskConfirmationCase,
        reason: str = "CASE_EXPIRED",
        expired_at: datetime | None = None,
        commit: bool = False,
    ) -> FollowUpTaskConfirmationCase:
        """Expire a caller-locked Case and invalidate its live UI actions."""

        if case.status != FollowUpTaskConfirmationStatus.PENDING:
            return case

        effective_time = expired_at or business_now()
        updated = self.case_crud.mark_expired(
            db,
            case,
            expired_at=effective_time,
            commit=False,
        )
        action_repository = self._action_repository()
        if action_repository is not None:
            action_repository.revoke_for_follow_up_confirmation_case(
                db,
                team_id=team_id,
                case_public_id=str(case.public_id),
                reason=reason,
                now=effective_time,
            )
        if commit:
            db.commit()
        return updated

    def cancel_locked_case(
        self,
        db: Session,
        *,
        team_id: int,
        case: FollowUpTaskConfirmationCase,
        reason: str,
        cancelled_at: datetime | None = None,
        cancelled_by_id: str | None = None,
        commit: bool = False,
    ) -> FollowUpTaskConfirmationCase:
        """Cancel a caller-locked Case and revoke all live UI actions.

        Callers that select Cases with ``FOR UPDATE`` should use this method so
        the business transition and projection invalidation share one
        transaction.  Terminal Cases are idempotent and are never rewritten.
        """

        if case.status != FollowUpTaskConfirmationStatus.PENDING:
            return case

        effective_time = cancelled_at or business_now()
        updated = self.case_crud.mark_cancelled(
            db,
            case,
            cancelled_at=effective_time,
            cancelled_by_id=cancelled_by_id,
            cancelled_reason=reason,
            commit=False,
        )
        action_repository = self._action_repository()
        if action_repository is not None:
            action_repository.revoke_for_follow_up_confirmation_case(
                db,
                team_id=team_id,
                case_public_id=str(case.public_id),
                reason=reason,
                now=effective_time,
            )
        if commit:
            db.commit()
        return updated


follow_up_confirmation_case_lifecycle_service = FollowUpConfirmationCaseLifecycleService(
    enable_action_projection=True
)
