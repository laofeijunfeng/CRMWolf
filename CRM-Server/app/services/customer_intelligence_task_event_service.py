"""Publish follow-up task lifecycle events to Customer Intelligence.

Follow-up tasks are a projection of customer activity, but their lifecycle is
still meaningful evidence for a customer profile (for example, a promised
follow-up was completed or cancelled).  This module is the single seam used by
both activity projection and interactive task transitions so neither path can
silently bypass the durable Customer Intelligence run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.services.customer_intelligence_event_publication_service import (
    CustomerIntelligenceEventPublicationService,
    customer_intelligence_event_publication_service,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.sales_commitment import FollowUpTask, FollowUpTaskEvent
    from app.services.customer_intelligence_event_service import CustomerIntelligenceEvent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CustomerIntelligenceTaskEventPublishResult:
    """Outcome of publishing one task event to the durable refresh boundary."""

    event: CustomerIntelligenceEvent | None
    error: str | None = None


class CustomerIntelligenceTaskEventService:
    """Build and durably register Customer Intelligence events for task events."""

    def __init__(
        self,
        *,
        publication_service: CustomerIntelligenceEventPublicationService | None = None,
    ) -> None:
        self.publication_service = publication_service or customer_intelligence_event_publication_service

    def build_event(
        self,
        *,
        task: FollowUpTask,
        task_event: FollowUpTaskEvent,
    ) -> tuple[CustomerIntelligenceEvent | None, str | None]:
        try:
            from app.services.customer_intelligence_event_service import customer_intelligence_event_service

            return customer_intelligence_event_service.from_follow_up_task_event(task, task_event), None
        except Exception as exc:  # pragma: no cover - defensive boundary
            error = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "构造客户智能任务事件失败: team_id=%s customer_id=%s task_id=%s task_event_id=%s",
                getattr(task, "team_id", None),
                getattr(task, "customer_id", None),
                getattr(task, "id", None),
                getattr(task_event, "id", None),
            )
            return None, error

    def publish(
        self,
        db: Session,
        *,
        task: FollowUpTask,
        task_event: FollowUpTaskEvent,
        scope: str = "partial",
    ) -> CustomerIntelligenceTaskEventPublishResult:
        """Register a task event without allowing read-model failures to abort writes.

        The task and task-event rows are the source-of-truth business write.
        Durable refresh registration is isolated in a savepoint: a missing
        queue/table or transient persistence failure is observable and can be
        repaired by reconciliation, but must not roll back the task projection.
        """

        event, error = self.build_event(task=task, task_event=task_event)
        if event is None:
            return CustomerIntelligenceTaskEventPublishResult(event=None, error=error)

        error = self.persist_event(db, event=event, scope=scope)
        return CustomerIntelligenceTaskEventPublishResult(event=event, error=error)

    def kick_after_commit(
        self,
        *,
        event: CustomerIntelligenceEvent | None,
        scope: str = "partial",
    ) -> str | None:
        """Kick a previously persisted task event after its source commit.

        Persistence and liveness are deliberately separate operations: the
        business transaction calls ``persist_event`` before commit, while the
        caller invokes this method only after commit. Keeping the scheduler
        dependency here gives task lifecycle code one deep seam for event
        construction, durable registration, and post-commit execution.
        """

        return self.publication_service.kick_after_commit(event=event, scope=scope)

    def persist_event(
        self,
        db: Session,
        *,
        event: CustomerIntelligenceEvent | None,
        scope: str = "partial",
    ) -> str | None:
        """Persist a previously-built event inside an isolated savepoint."""

        return self.publication_service.persist_in_transaction(db, event=event, scope=scope)


customer_intelligence_task_event_service = CustomerIntelligenceTaskEventService()
