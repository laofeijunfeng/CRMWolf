"""Attach durable follow-up confirmations to their originating Agent messages."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.crud.sales_commitment import follow_up_task_confirmation_prompt_delivery_crud
from app.models.agent import AgentMessage, AgentMessageRole
from app.models.agent_async_operation import AgentAsyncOperation
from app.models.customer_activity_post_commit_job import CustomerActivityPostCommitJob
from app.models.sales_commitment import FollowUpTaskConfirmationCase

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class FollowUpTaskConfirmationAgentMessageCardService:
    """Backfill non-intrusive message cards without duplicating confirmation cases."""

    def ensure_session_cards(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        commit: bool = True,
    ) -> int:
        """Attach all safely attributable historical cards for one Agent session."""

        operations = (
            db.query(AgentAsyncOperation)
            .filter(
                AgentAsyncOperation.team_id == team_id,
                AgentAsyncOperation.user_id == user_id,
                AgentAsyncOperation.session_id == session_id,
                AgentAsyncOperation.operation_type == "customer_activity_post_commit",
                AgentAsyncOperation.resource_type == "customer_activity",
                AgentAsyncOperation.source_assistant_message_id.is_not(None),
            )
            .order_by(AgentAsyncOperation.id.asc())
            .all()
        )
        created_count = 0
        for operation in operations:
            created_count += self._ensure_operation_cards(db, operation=operation)
        if created_count and commit:
            db.commit()
        return created_count

    def ensure_job_cards(
        self,
        db: Session,
        *,
        job: CustomerActivityPostCommitJob,
        commit: bool = True,
    ) -> int:
        """Attach cards for a freshly completed job when its source message is known."""

        operations = (
            db.query(AgentAsyncOperation)
            .filter(
                AgentAsyncOperation.team_id == int(job.team_id),
                AgentAsyncOperation.request_id == str(job.public_id),
                AgentAsyncOperation.operation_type == "customer_activity_post_commit",
                AgentAsyncOperation.resource_type == "customer_activity",
                AgentAsyncOperation.resource_id == int(job.activity_id),
                AgentAsyncOperation.source_assistant_message_id.is_not(None),
            )
            .order_by(AgentAsyncOperation.id.asc())
            .all()
        )
        created_count = 0
        for operation in operations:
            created_count += self._ensure_operation_cards(db, operation=operation, job=job)
        if created_count and commit:
            db.commit()
        return created_count

    def _ensure_operation_cards(
        self,
        db: Session,
        *,
        operation: AgentAsyncOperation,
        job: CustomerActivityPostCommitJob | None = None,
    ) -> int:
        assistant_message_id = operation.source_assistant_message_id
        session_id = operation.session_id
        if assistant_message_id is None or session_id is None or operation.resource_id is None:
            return 0
        if job is None:
            job = (
                db.query(CustomerActivityPostCommitJob)
                .filter(
                    CustomerActivityPostCommitJob.team_id == int(operation.team_id),
                    CustomerActivityPostCommitJob.public_id == str(operation.request_id),
                    CustomerActivityPostCommitJob.activity_id == int(operation.resource_id),
                )
                .one_or_none()
            )
        if job is None:
            return 0
        assistant_message = (
            db.query(AgentMessage)
            .filter(
                AgentMessage.id == int(assistant_message_id),
                AgentMessage.team_id == int(operation.team_id),
                AgentMessage.user_id == int(operation.user_id),
                AgentMessage.session_id == int(session_id),
                AgentMessage.role == AgentMessageRole.ASSISTANT,
            )
            .one_or_none()
        )
        if assistant_message is None:
            return 0

        cases = (
            db.query(FollowUpTaskConfirmationCase)
            .filter(
                FollowUpTaskConfirmationCase.team_id == int(operation.team_id),
                FollowUpTaskConfirmationCase.owner_id == str(operation.user_id),
                FollowUpTaskConfirmationCase.source_activity_id == int(job.activity_id),
                FollowUpTaskConfirmationCase.source_activity_revision == int(job.activity_revision),
            )
            .order_by(FollowUpTaskConfirmationCase.id.asc())
            .all()
        )
        created_count = 0
        for confirmation_case in cases:
            prompt_key = (
                f"agent-message-card:{operation.team_id}:{confirmation_case.id}:{assistant_message.id}"
            )
            existing = follow_up_task_confirmation_prompt_delivery_crud.get_by_prompt_key(
                db,
                team_id=int(operation.team_id),
                prompt_key=prompt_key,
            )
            follow_up_task_confirmation_prompt_delivery_crud.ensure_agent_message_card(
                db,
                team_id=int(operation.team_id),
                case_id=int(confirmation_case.id),
                owner_id=str(operation.user_id),
                agent_session_id=int(session_id),
                assistant_message_id=int(assistant_message.id),
                source_activity_id=int(job.activity_id),
                expected_activity_revision=int(job.activity_revision),
                commit=False,
            )
            if existing is None:
                created_count += 1
        return created_count


follow_up_task_confirmation_agent_message_card_service = FollowUpTaskConfirmationAgentMessageCardService()
