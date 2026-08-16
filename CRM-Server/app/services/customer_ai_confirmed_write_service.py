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
from typing import Any, cast

from sqlalchemy.orm import Session

from app.crud.agent import AgentIdempotencyKeyCRUD, agent_idempotency_key_crud
from app.crud.customer_activity import CustomerActivityCRUD, customer_activity_crud
from app.models.agent import AgentIdempotencyStatus
from app.models.customer_activity import CustomerActivity
from app.models.sales_commitment import FollowUpTaskProjectionTrigger
from app.schemas.agent import AgentIdempotencyKeyCreate, AgentIdempotencyKeyUpdate
from app.schemas.customer_activity import CustomerActivityCreate
from app.services.agent.temporal import agent_temporal_resolver
from app.services.customer_activity_kinds import infer_activity_kind
from app.services.customer_activity_processing_service import (
    CustomerActivityProcessingService,
    customer_activity_processing_service,
)
from app.services.customer_activity_post_commit_job_service import CustomerActivityPostCommitJobRequest
from app.services.customer_activity_write_service import (
    CustomerActivityWriteResult,
    CustomerActivityWriteService,
    customer_activity_write_service,
)
from app.services.customer_intelligence_event_service import (
    CustomerIntelligenceEventService,
    customer_intelligence_event_service,
)
from app.services.customer_intelligence_refresh_service import (
    CustomerIntelligenceCommittedEventRequest,
    CustomerIntelligenceRefreshScope,
)
from app.services.customer_intelligence_run_service import (
    CustomerIntelligenceRunService,
    customer_intelligence_run_service,
)
from app.utils.time import business_now


@dataclass(frozen=True)
class ConfirmedAIActivityWriteResult:
    activity: CustomerActivity
    next_follow_time_iso: str | None
    idempotency_key: str
    durable_work: CustomerActivityWriteResult | None = None
    idempotent_replay: bool = False


class CustomerAIConfirmedWriteService:
    def __init__(
        self,
        *,
        activity_write_service: CustomerActivityWriteService | None = None,
        activity_crud: CustomerActivityCRUD | None = None,
        processing_service: CustomerActivityProcessingService | None = None,
        idempotency_crud: AgentIdempotencyKeyCRUD | None = None,
        intelligence_run_service: CustomerIntelligenceRunService | None = None,
        intelligence_event_service: CustomerIntelligenceEventService | None = None,
    ) -> None:
        self.activity_write_service = activity_write_service or customer_activity_write_service
        self.activity_crud = activity_crud or customer_activity_crud
        self.processing_service = processing_service or customer_activity_processing_service
        self.idempotency_crud = idempotency_crud or agent_idempotency_key_crud
        self.intelligence_run_service = intelligence_run_service or customer_intelligence_run_service
        self.intelligence_event_service = intelligence_event_service or customer_intelligence_event_service

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
        idempotency = self.idempotency_crud.get_or_create(
            db,
            AgentIdempotencyKeyCreate(
                team_id=team_id,
                user_id=normalized_user_id,
                action_key=action_key,
                request_hash=request_hash,
            ),
            commit=False,
        )
        if idempotency.status == AgentIdempotencyStatus.SUCCESS:
            activity = self._activity_from_idempotency_result(db, idempotency.result_json, team_id)
            if activity is not None:
                durable_work = self._durable_work_from_idempotency_result(
                    db,
                    result_json=idempotency.result_json,
                    activity=activity,
                    team_id=team_id,
                )
                return ConfirmedAIActivityWriteResult(
                    activity=activity,
                    next_follow_time_iso=next_follow_time_iso,
                    idempotency_key=action_key,
                    durable_work=durable_work,
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
            def complete_idempotency(write_result: CustomerActivityWriteResult) -> None:
                intelligence = write_result.customer_intelligence_request
                result_json = {
                    "activity_id": write_result.activity.id,
                    "activity_revision": write_result.activity_revision,
                    "customer_public_id": customer_public_id,
                    "next_follow_time": next_follow_time_iso,
                    "source_type": "manual_ai_confirmed",
                    "post_commit_job_public_id": (
                        write_result.post_commit_job.job_public_id
                        if write_result.post_commit_job is not None
                        else None
                    ),
                    "customer_intelligence_request_id": (
                        intelligence.request_id if intelligence is not None else None
                    ),
                    "customer_intelligence_scope": (
                        intelligence.scope if intelligence is not None else None
                    ),
                    "customer_intelligence_event": (
                        intelligence.event.to_dict() if intelligence is not None else None
                    ),
                }
                self.idempotency_crud.update(
                    db,
                    idempotency,
                    AgentIdempotencyKeyUpdate(
                        status=AgentIdempotencyStatus.SUCCESS,
                        result_json=result_json,
                        error_message=None,
                    ),
                    commit=False,
                )

            write_result = self.activity_write_service.create(
                db,
                obj_in=activity_create,
                customer_id=customer_id,
                creator_id=str(normalized_user_id),
                owner_id=str(normalized_user_id),
                team_id=team_id,
                operator_name=operator_name,
                post_commit_trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_CREATED_DETERMINISTIC,
                actor_id=str(normalized_user_id),
                before_commit=complete_idempotency,
            )
            self.activity_write_service.kick(write_result)
            await self.processing_service.trigger_processing(write_result.activity.id, team_id)
            return ConfirmedAIActivityWriteResult(
                activity=write_result.activity,
                next_follow_time_iso=next_follow_time_iso,
                idempotency_key=action_key,
                durable_work=write_result,
            )
        except Exception as exc:
            self._record_failure_after_rollback(
                db,
                team_id=team_id,
                user_id=normalized_user_id,
                action_key=action_key,
                error_message=str(exc),
            )
            raise


    def _record_failure_after_rollback(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        action_key: str,
        error_message: str,
    ) -> None:
        try:
            record = self.idempotency_crud.get_by_action_key(db, team_id, user_id, action_key)
            if record is None or record.status == AgentIdempotencyStatus.SUCCESS:
                return
            self.idempotency_crud.update(
                db,
                record,
                AgentIdempotencyKeyUpdate(
                    status=AgentIdempotencyStatus.FAILED,
                    error_message=error_message[:2000],
                ),
            )
        except Exception:
            db.rollback()

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
        return self.activity_crud.get_by_id(db, activity_id, team_id)

    def _durable_work_from_idempotency_result(
        self,
        db: Session,
        *,
        result_json: dict[str, Any] | None,
        activity: CustomerActivity,
        team_id: int,
    ) -> CustomerActivityWriteResult | None:
        if not result_json:
            return None
        activity_revision = result_json.get("activity_revision")
        if not isinstance(activity_revision, int):
            activity_revision = int(getattr(activity, "post_commit_revision", None) or 1)

        post_commit_job = None
        post_commit_job_public_id = result_json.get("post_commit_job_public_id")
        if isinstance(post_commit_job_public_id, str) and post_commit_job_public_id:
            post_commit_job = CustomerActivityPostCommitJobRequest(
                job_public_id=post_commit_job_public_id,
                team_id=team_id,
            )

        intelligence_request = None
        request_id = result_json.get("customer_intelligence_request_id")
        if isinstance(request_id, str) and request_id:
            run = self.intelligence_run_service.get_by_request_id(
                db,
                team_id=team_id,
                request_id=request_id,
            )
            if run is None or int(run.customer_id) != int(activity.customer_id):
                raise ValueError("幂等回放的客户智能运行不存在或客户不匹配")
            event_json = run.event_json if isinstance(run.event_json, dict) else {}
            event = self.intelligence_event_service.from_dict(event_json)
            if event is None or int(event.team_id) != int(team_id) or int(event.tenant_id) != int(team_id):
                raise ValueError("幂等回放的客户智能事件快照无效")
            scope = str(run.scope)
            if scope not in {"full", "brief"}:
                raise ValueError("幂等回放的客户智能刷新范围无效")
            intelligence_request = CustomerIntelligenceCommittedEventRequest(
                request_id=request_id,
                event=event,
                scope=cast(CustomerIntelligenceRefreshScope, scope),
                scheduled=True,
                kick_required=False,
            )

        return CustomerActivityWriteResult(
            activity=activity,
            activity_revision=activity_revision,
            post_commit_job=post_commit_job,
            customer_intelligence_request=intelligence_request,
        )

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
