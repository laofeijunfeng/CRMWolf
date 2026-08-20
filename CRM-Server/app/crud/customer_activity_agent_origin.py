"""Persistence helpers for immutable customer-activity Agent origins."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError

from app.models.customer_activity_agent_origin import CustomerActivityAgentOrigin

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class CustomerActivityAgentOriginCRUD:
    def get_by_activity(
        self,
        db: Session,
        *,
        team_id: int,
        activity_id: int,
    ) -> CustomerActivityAgentOrigin | None:
        return (
            db.query(CustomerActivityAgentOrigin)
            .filter(
                CustomerActivityAgentOrigin.team_id == team_id,
                CustomerActivityAgentOrigin.activity_id == activity_id,
            )
            .one_or_none()
        )

    def list_by_session(
        self,
        db: Session,
        *,
        team_id: int,
        owner_id: str,
        agent_session_id: int,
    ) -> list[CustomerActivityAgentOrigin]:
        return (
            db.query(CustomerActivityAgentOrigin)
            .filter(
                CustomerActivityAgentOrigin.team_id == team_id,
                CustomerActivityAgentOrigin.owner_id == owner_id,
                CustomerActivityAgentOrigin.agent_session_id == agent_session_id,
            )
            .order_by(CustomerActivityAgentOrigin.id.asc())
            .all()
        )

    def ensure(
        self,
        db: Session,
        *,
        team_id: int,
        activity_id: int,
        owner_id: str,
        agent_session_id: int,
        source_user_message_id: int | None,
        source_assistant_message_id: int,
        agent_operation_public_id: str,
    ) -> CustomerActivityAgentOrigin | None:
        """Create an origin once, without replacing conflicting causal history."""

        candidate = CustomerActivityAgentOrigin(
            team_id=team_id,
            activity_id=activity_id,
            owner_id=owner_id,
            agent_session_id=agent_session_id,
            source_user_message_id=source_user_message_id,
            source_assistant_message_id=source_assistant_message_id,
            agent_operation_public_id=agent_operation_public_id,
        )
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
            return candidate
        except IntegrityError:
            existing = self.get_by_activity(db, team_id=team_id, activity_id=activity_id)
            if existing is None or not self.matches_source(
                existing,
                owner_id=owner_id,
                agent_session_id=agent_session_id,
                source_user_message_id=source_user_message_id,
                source_assistant_message_id=source_assistant_message_id,
            ):
                return None
            return existing

    @staticmethod
    def matches_source(
        origin: CustomerActivityAgentOrigin,
        *,
        owner_id: str,
        agent_session_id: int,
        source_user_message_id: int | None,
        source_assistant_message_id: int,
    ) -> bool:
        return (
            str(origin.owner_id) == owner_id
            and int(origin.agent_session_id) == agent_session_id
            and origin.source_user_message_id == source_user_message_id
            and int(origin.source_assistant_message_id) == source_assistant_message_id
        )


customer_activity_agent_origin_crud = CustomerActivityAgentOriginCRUD()
