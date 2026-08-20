"""Attach follow-up confirmations to the Agent turn that originated an activity."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.crud.customer_activity_agent_origin import customer_activity_agent_origin_crud
from app.crud.sales_commitment import follow_up_task_confirmation_prompt_delivery_crud
from app.models.agent import AgentMessage, AgentMessageRole
from app.models.sales_commitment import FollowUpTaskConfirmationCase
from app.services.customer_activity_agent_origin_service import customer_activity_agent_origin_service

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.customer_activity_agent_origin import CustomerActivityAgentOrigin
    from app.models.customer_activity_post_commit_job import CustomerActivityPostCommitJob


class FollowUpTaskConfirmationAgentMessageCardService:
    """Project existing confirmation cases as non-intrusive Agent message cards.

    A card is a second presentation of the same confirmation case shown in
    customer tracking. Its message attribution comes from the immutable activity
    origin; it must not depend on the revision that happened to create the case.
    """

    def ensure_session_cards(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        commit: bool = True,
    ) -> int:
        """Backfill safe legacy origins, then attach all cards for this session."""

        origin_count = customer_activity_agent_origin_service.ensure_session_origins(
            db,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
        )
        origins = customer_activity_agent_origin_crud.list_by_session(
            db,
            team_id=team_id,
            owner_id=str(user_id),
            agent_session_id=session_id,
        )
        created_count = sum(self._ensure_origin_cards(db, origin=origin) for origin in origins)
        if (origin_count or created_count) and commit:
            db.commit()
        return created_count

    def ensure_job_cards(
        self,
        db: Session,
        *,
        job: CustomerActivityPostCommitJob,
        commit: bool = True,
    ) -> int:
        """Attach cards for a completed job when its activity already has an origin."""

        origin = customer_activity_agent_origin_crud.get_by_activity(
            db,
            team_id=int(job.team_id),
            activity_id=int(job.activity_id),
        )
        if origin is None:
            return 0
        created_count = self._ensure_origin_cards(db, origin=origin)
        if created_count and commit:
            db.commit()
        return created_count

    def _ensure_origin_cards(
        self,
        db: Session,
        *,
        origin: CustomerActivityAgentOrigin,
    ) -> int:
        try:
            owner_user_id = int(origin.owner_id)
        except (TypeError, ValueError):
            return 0
        assistant_message = (
            db.query(AgentMessage)
            .filter(
                AgentMessage.id == int(origin.source_assistant_message_id),
                AgentMessage.team_id == int(origin.team_id),
                AgentMessage.user_id == owner_user_id,
                AgentMessage.session_id == int(origin.agent_session_id),
                AgentMessage.role == AgentMessageRole.ASSISTANT,
            )
            .one_or_none()
        )
        if assistant_message is None:
            return 0

        cases = (
            db.query(FollowUpTaskConfirmationCase)
            .filter(
                FollowUpTaskConfirmationCase.team_id == int(origin.team_id),
                FollowUpTaskConfirmationCase.owner_id == str(origin.owner_id),
                FollowUpTaskConfirmationCase.source_activity_id == int(origin.activity_id),
            )
            .order_by(FollowUpTaskConfirmationCase.id.asc())
            .all()
        )
        created_count = 0
        for confirmation_case in cases:
            prompt_key = f"agent-message-card:{origin.team_id}:{confirmation_case.id}:{assistant_message.id}"
            existing = follow_up_task_confirmation_prompt_delivery_crud.get_by_prompt_key(
                db,
                team_id=int(origin.team_id),
                prompt_key=prompt_key,
            )
            follow_up_task_confirmation_prompt_delivery_crud.ensure_agent_message_card(
                db,
                team_id=int(origin.team_id),
                case_id=int(confirmation_case.id),
                owner_id=str(origin.owner_id),
                agent_session_id=int(origin.agent_session_id),
                assistant_message_id=int(assistant_message.id),
                source_activity_id=int(origin.activity_id),
                expected_activity_revision=(
                    int(confirmation_case.source_activity_revision)
                    if confirmation_case.source_activity_revision is not None
                    else None
                ),
                commit=False,
            )
            if existing is None:
                created_count += 1
        return created_count


follow_up_task_confirmation_agent_message_card_service = FollowUpTaskConfirmationAgentMessageCardService()
