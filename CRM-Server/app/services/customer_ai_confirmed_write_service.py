"""Confirmed AI-assisted CRM writes.

This service is for non-chat MagicWand style flows where the user has reviewed
an AI parse result and explicitly submitted it. It keeps those writes on one
audited/idempotent boundary instead of letting each API/parser create CRM
records with its own rules.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.crud.agent import agent_idempotency_key_crud
from app.crud.customer_activity import customer_activity_crud
from app.models.agent import AgentIdempotencyStatus
from app.models.customer_activity import CustomerActivity
from app.models.sales_commitment import FollowUpTaskProjectionTrigger
from app.schemas.agent import AgentIdempotencyKeyCreate, AgentIdempotencyKeyUpdate
from app.schemas.customer_activity import CustomerActivityCreate
from app.services.agent.temporal import agent_temporal_resolver
from app.services.customer_activity_kinds import infer_activity_kind
from app.services.customer_activity_processing_service import customer_activity_processing_service
from app.utils.time import business_now


@dataclass(frozen=True)
class ConfirmedAIActivityWriteResult:
    activity: CustomerActivity
    next_follow_time_iso: str | None
    idempotency_key: str
    idempotent_replay: bool = False


class CustomerAIConfirmedWriteService:
    async def create_customer_activity(
        self,
        *,
        db: Session,
        customer_id: int,
        customer_public_id: str,
        team_id: int,
        user_id: int | str,
        content: str,
        method: str | None = None,
        next_action: str | None = None,
        next_follow_time_text: str | None = None,
        activity_kind: str | None = None,
        operator_name: str | None = None,
        action_namespace: str = "customer_activity",
    ) -> ConfirmedAIActivityWriteResult:
        normalized_user_id = int(user_id)
        normalized_content = content.strip()
        resolved_next_follow_time = self._resolve_next_follow_time(next_follow_time_text)
        next_follow_time_iso = resolved_next_follow_time.isoformat() if resolved_next_follow_time else None
        resolved_activity_kind = activity_kind or infer_activity_kind(method, normalized_content)
        action_key = self._build_action_key(
            namespace=action_namespace,
            team_id=team_id,
            user_id=normalized_user_id,
            customer_public_id=customer_public_id,
            activity_kind=resolved_activity_kind,
            content=normalized_content,
            next_action=next_action,
            next_follow_time_text=next_follow_time_text,
            next_follow_time_iso=next_follow_time_iso,
        )
        request_hash = self._hash_json(
            {
                "customer_public_id": customer_public_id,
                "activity_kind": resolved_activity_kind,
                "content": normalized_content,
                "method": method,
                "next_action": next_action,
                "next_follow_time_text": next_follow_time_text,
                "next_follow_time_iso": next_follow_time_iso,
                "source_type": "manual_ai_confirmed",
            }
        )
        idempotency = agent_idempotency_key_crud.get_or_create(
            db,
            AgentIdempotencyKeyCreate(
                team_id=team_id,
                user_id=normalized_user_id,
                action_key=action_key,
                request_hash=request_hash,
            ),
        )
        if idempotency.status == AgentIdempotencyStatus.SUCCESS:
            activity = self._activity_from_idempotency_result(db, idempotency.result_json, team_id)
            if activity is not None:
                return ConfirmedAIActivityWriteResult(
                    activity=activity,
                    next_follow_time_iso=next_follow_time_iso,
                    idempotency_key=action_key,
                    idempotent_replay=True,
                )

        try:
            activity_create = CustomerActivityCreate(
                activity_kind=resolved_activity_kind,
                source_content=normalized_content,
                next_action=next_action,
                next_follow_time=resolved_next_follow_time,
                next_follow_time_source="AI_EXTRACTED" if resolved_next_follow_time else None,
            )
            activity = customer_activity_crud.create(
                db=db,
                obj_in=activity_create,
                customer_id=customer_id,
                creator_id=str(normalized_user_id),
                owner_id=str(normalized_user_id),
                team_id=team_id,
                operator_name=operator_name,
            )
            await customer_activity_processing_service.trigger_post_commit_workflow(
                activity_id=activity.id,
                team_id=team_id,
                trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_CREATED_DETERMINISTIC,
                actor_id=str(normalized_user_id),
            )
            await customer_activity_processing_service.trigger_processing(activity.id, team_id)
            result_json = {
                "activity_id": activity.id,
                "customer_public_id": customer_public_id,
                "next_follow_time": next_follow_time_iso,
                "source_type": "manual_ai_confirmed",
            }
            agent_idempotency_key_crud.update(
                db,
                idempotency,
                AgentIdempotencyKeyUpdate(status=AgentIdempotencyStatus.SUCCESS, result_json=result_json),
            )
            return ConfirmedAIActivityWriteResult(
                activity=activity,
                next_follow_time_iso=next_follow_time_iso,
                idempotency_key=action_key,
            )
        except Exception as exc:
            agent_idempotency_key_crud.update(
                db,
                idempotency,
                AgentIdempotencyKeyUpdate(status=AgentIdempotencyStatus.FAILED, error_message=str(exc)),
            )
            raise

    def _resolve_next_follow_time(self, raw_text: str | None) -> datetime | None:
        if not raw_text:
            return None
        resolved = agent_temporal_resolver.resolve_follow_up_time_text(
            raw_text,
            base_datetime=business_now(),
        )
        if not resolved:
            return None
        return datetime.fromisoformat(resolved)

    def _activity_from_idempotency_result(
        self,
        db: Session,
        result_json: dict[str, Any] | None,
        team_id: int,
    ) -> CustomerActivity | None:
        if not result_json:
            return None
        activity_id = result_json.get("activity_id")
        if not isinstance(activity_id, int):
            return None
        return customer_activity_crud.get_by_id(db, activity_id, team_id)

    def _build_action_key(
        self,
        *,
        namespace: str,
        team_id: int,
        user_id: int,
        customer_public_id: str,
        activity_kind: str,
        content: str,
        next_action: str | None,
        next_follow_time_text: str | None,
        next_follow_time_iso: str | None,
    ) -> str:
        digest = self._hash_json(
            {
                "namespace": namespace,
                "team_id": team_id,
                "user_id": user_id,
                "customer_public_id": customer_public_id,
                "activity_kind": activity_kind,
                "content": content,
                "next_action": next_action,
                "next_follow_time_text": next_follow_time_text,
                "next_follow_time_iso": next_follow_time_iso,
            }
        )
        return f"manual_ai_confirmed:{namespace}:{digest[:32]}"

    def _hash_json(self, value: dict[str, Any]) -> str:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


customer_ai_confirmed_write_service = CustomerAIConfirmedWriteService()
