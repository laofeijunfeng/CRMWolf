"""Confirmed AI-assisted lead writes."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.crud.agent import agent_idempotency_key_crud
from app.crud.lead import lead_follow_up_crud
from app.models.agent import AgentIdempotencyStatus
from app.models.lead import FollowUpMethod, LeadFollowUp
from app.schemas.agent import AgentIdempotencyKeyCreate, AgentIdempotencyKeyUpdate
from app.schemas.lead import LeadFollowUpCreate
from app.services.agent.temporal import agent_temporal_resolver
from app.utils.time import business_now


@dataclass(frozen=True)
class ConfirmedAILeadFollowUpWriteResult:
    follow_up: LeadFollowUp
    next_follow_time_iso: str | None
    idempotency_key: str
    idempotent_replay: bool = False


class LeadAIConfirmedWriteService:
    async def create_lead_follow_up(
        self,
        *,
        db: Session,
        lead_id: int,
        lead_public_id: str,
        team_id: int,
        user_id: int | str,
        content: str,
        method: FollowUpMethod = FollowUpMethod.OTHER,
        next_action: str | None = None,
        next_follow_time_text: str | None = None,
        operator_name: str | None = None,
        action_namespace: str = "lead_follow_up",
    ) -> ConfirmedAILeadFollowUpWriteResult:
        normalized_user_id = int(user_id)
        normalized_content = content.strip()
        resolved_next_follow_time = self._resolve_next_follow_time(next_follow_time_text)
        next_follow_time_iso = resolved_next_follow_time.isoformat() if resolved_next_follow_time else None
        action_key = self._build_action_key(
            namespace=action_namespace,
            team_id=team_id,
            user_id=normalized_user_id,
            lead_public_id=lead_public_id,
            content=normalized_content,
            method=method.value if hasattr(method, "value") else str(method),
            next_action=next_action,
            next_follow_time_text=next_follow_time_text,
            next_follow_time_iso=next_follow_time_iso,
        )
        request_hash = self._hash_json(
            {
                "lead_public_id": lead_public_id,
                "content": normalized_content,
                "method": method.value if hasattr(method, "value") else str(method),
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
            follow_up = self._follow_up_from_idempotency_result(db, idempotency.result_json)
            if follow_up is not None and follow_up.team_id == team_id:
                return ConfirmedAILeadFollowUpWriteResult(
                    follow_up=follow_up,
                    next_follow_time_iso=next_follow_time_iso,
                    idempotency_key=action_key,
                    idempotent_replay=True,
                )

        try:
            follow_up_create = LeadFollowUpCreate(
                content=normalized_content,
                method=method,
                next_action=next_action,
                next_follow_time=resolved_next_follow_time,
            )
            follow_up = lead_follow_up_crud.create(
                db=db,
                obj_in=follow_up_create,
                lead_id=lead_id,
                creator_id=str(normalized_user_id),
                team_id=team_id,
                operator_name=operator_name,
            )
            result_json = {
                "follow_up_id": follow_up.id,
                "lead_public_id": lead_public_id,
                "next_follow_time": next_follow_time_iso,
                "source_type": "manual_ai_confirmed",
            }
            agent_idempotency_key_crud.update(
                db,
                idempotency,
                AgentIdempotencyKeyUpdate(status=AgentIdempotencyStatus.SUCCESS, result_json=result_json),
            )
            return ConfirmedAILeadFollowUpWriteResult(
                follow_up=follow_up,
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

    def _follow_up_from_idempotency_result(
        self,
        db: Session,
        result_json: dict[str, Any] | None,
    ) -> LeadFollowUp | None:
        if not result_json:
            return None
        follow_up_id = result_json.get("follow_up_id")
        if not isinstance(follow_up_id, int):
            return None
        return lead_follow_up_crud.get_by_id(db, follow_up_id)

    def _build_action_key(
        self,
        *,
        namespace: str,
        team_id: int,
        user_id: int,
        lead_public_id: str,
        content: str,
        method: str,
        next_action: str | None,
        next_follow_time_text: str | None,
        next_follow_time_iso: str | None,
    ) -> str:
        digest = self._hash_json(
            {
                "namespace": namespace,
                "team_id": team_id,
                "user_id": user_id,
                "lead_public_id": lead_public_id,
                "content": content,
                "method": method,
                "next_action": next_action,
                "next_follow_time_text": next_follow_time_text,
                "next_follow_time_iso": next_follow_time_iso,
            }
        )
        return f"manual_ai_confirmed:{namespace}:{digest[:32]}"

    def _hash_json(self, value: dict[str, Any]) -> str:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


lead_ai_confirmed_write_service = LeadAIConfirmedWriteService()
