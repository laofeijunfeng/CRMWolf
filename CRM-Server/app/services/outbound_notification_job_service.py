"""Durable outbox for in-request Feishu notifications."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.crud.approval import approval_crud
from app.crud.outbound_notification_job import outbound_notification_job_crud
from app.crud.role import role_crud
from app.models.approval import Approval, ApprovalStatus
from app.models.outbound_notification_job import (
    OutboundNotificationEventType,
    OutboundNotificationJob,
    OutboundNotificationJobStatus,
)
from app.services.approval_adapter import (
    get_adapter,
    get_approval_action_path,
    get_approval_card_fields,
    get_approval_customer_name,
    get_approval_type_name,
)
from app.services.feishu_notification import feishu_notification_service
from app.utils.time import business_now

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)

_PENDING_OR_REMINDER = frozenset(
    {
        OutboundNotificationEventType.APPROVAL_PENDING,
        OutboundNotificationEventType.APPROVAL_REMINDER,
    }
)


class OutboundNotificationJobRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_public_id: str
    team_id: int


class OutboundNotificationJobService:
    """Owns enqueue, execution, retry and recovery of outbound notifications."""

    def enqueue_in_transaction(
        self,
        db: Session,
        *,
        team_id: int,
        event_type: str,
        idempotency_key: str,
        recipient_user_ids: list[int],
        business_type: str,
        business_id: int,
        approval_id: int | None = None,
        node_id: int | None = None,
        actor_id: str | None = None,
        payload_json: dict[str, object] | None = None,
    ) -> OutboundNotificationJobRequest | None:
        """Write the durable job in the caller's transaction. Does not commit."""

        recipients = _int_ids(recipient_user_ids)
        if not recipients:
            return None
        job = outbound_notification_job_crud.enqueue(
            db,
            team_id=team_id,
            event_type=event_type,
            idempotency_key=idempotency_key,
            recipient_user_ids=recipients,
            business_type=business_type,
            business_id=business_id,
            approval_id=approval_id,
            node_id=node_id,
            actor_id=actor_id,
            payload_json=payload_json or {},
            commit=False,
        )
        return OutboundNotificationJobRequest(
            job_public_id=str(job.public_id),
            team_id=int(job.team_id),
        )

    def enqueue_after_commit(
        self,
        db: Session,
        *,
        team_id: int,
        event_type: str,
        idempotency_key: str,
        recipient_user_ids: list[int],
        business_type: str,
        business_id: int,
        approval_id: int | None = None,
        node_id: int | None = None,
        actor_id: str | None = None,
        payload_json: dict[str, object] | None = None,
    ) -> OutboundNotificationJobRequest | None:
        """Persist a job after the source CRUD already committed, then leave kick to the caller."""

        request = self.enqueue_in_transaction(
            db,
            team_id=team_id,
            event_type=event_type,
            idempotency_key=idempotency_key,
            recipient_user_ids=recipient_user_ids,
            business_type=business_type,
            business_id=business_id,
            approval_id=approval_id,
            node_id=node_id,
            actor_id=actor_id,
            payload_json=payload_json,
        )
        if request is None:
            return None
        db.commit()
        return request

    def enqueue_business_event(
        self,
        db: Session,
        *,
        team_id: int,
        event_type: str,
        business_type: str,
        business_id: int,
        recipient_user_ids: list[int] | int | str | None,
        actor_id: str | None = None,
        payload_json: dict[str, object] | None = None,
        idempotency_key: str | None = None,
        commit: bool = False,
    ) -> OutboundNotificationJobRequest | None:
        """Enqueue a non-approval business notification. Snapshot copy lives in payload_json."""

        if event_type not in OutboundNotificationEventType.BUSINESS:
            raise ValueError(f"不支持的业务通知事件: {event_type}")
        recipients = _normalize_recipient_ids(recipient_user_ids)
        key = idempotency_key or f"{team_id}:{event_type}:{business_type}:{int(business_id)}:{uuid4().hex}"
        kwargs = {
            "team_id": team_id,
            "event_type": event_type,
            "idempotency_key": key,
            "recipient_user_ids": recipients,
            "business_type": business_type,
            "business_id": int(business_id),
            "actor_id": actor_id,
            "payload_json": payload_json or {},
        }
        if commit:
            return self.enqueue_after_commit(db, **kwargs)
        return self.enqueue_in_transaction(db, **kwargs)

    def queue_committed(
        self,
        db: Session,
        *,
        team_id: int,
        event_type: str,
        business_type: str,
        business_id: int,
        recipient_user_ids: list[int] | int | str | None,
        actor_id: str | None = None,
        payload_json: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> OutboundNotificationJobRequest | None:
        """Persist a business notification after the source CRUD already committed, then kick."""

        try:
            request = self.enqueue_business_event(
                db,
                team_id=team_id,
                event_type=event_type,
                business_type=business_type,
                business_id=business_id,
                recipient_user_ids=recipient_user_ids,
                actor_id=actor_id,
                payload_json=payload_json,
                idempotency_key=idempotency_key,
                commit=True,
            )
            self.kick(request)
            return request
        except Exception:
            logger.exception(
                "出站通知入队失败: event=%s business=%s/%s",
                event_type,
                business_type,
                business_id,
            )
            return None

    def enqueue_pending_for_approval(
        self,
        db: Session,
        *,
        approval: Approval,
        team_id: int,
        actor_id: str | None = None,
        recipient_user_ids: list[int] | None = None,
    ) -> OutboundNotificationJobRequest | None:
        node = approval.current_node
        node_id = int(approval.current_node_id) if approval.current_node_id is not None else None
        recipients = recipient_user_ids if recipient_user_ids is not None else self._notification_user_ids(db, node, team_id)
        if node_id is None:
            return None
        return self.enqueue_in_transaction(
            db,
            team_id=team_id,
            event_type=OutboundNotificationEventType.APPROVAL_PENDING,
            idempotency_key=self._pending_idempotency_key(team_id, int(approval.id), node_id),
            recipient_user_ids=recipients,
            business_type=str(approval.business_type),
            business_id=int(approval.business_id),
            approval_id=int(approval.id),
            node_id=node_id,
            actor_id=actor_id,
        )

    def enqueue_approved(
        self,
        db: Session,
        *,
        approval: Approval,
        team_id: int,
        actor_id: str | None = None,
        button_path: str | None = None,
    ) -> OutboundNotificationJobRequest | None:
        submitter_id = _optional_int(approval.submitter_id)
        if submitter_id is None:
            return None
        return self.enqueue_in_transaction(
            db,
            team_id=team_id,
            event_type=OutboundNotificationEventType.APPROVAL_APPROVED,
            idempotency_key=f"{team_id}:{OutboundNotificationEventType.APPROVAL_APPROVED}:{int(approval.id)}",
            recipient_user_ids=[submitter_id],
            business_type=str(approval.business_type),
            business_id=int(approval.business_id),
            approval_id=int(approval.id),
            actor_id=actor_id,
            payload_json={"button_path": button_path or get_approval_action_path(str(approval.business_type))},
        )

    def enqueue_rejected(
        self,
        db: Session,
        *,
        approval: Approval,
        team_id: int,
        reject_reason: str,
        actor_id: str | None = None,
        button_path: str | None = None,
    ) -> OutboundNotificationJobRequest | None:
        submitter_id = _optional_int(approval.submitter_id)
        if submitter_id is None:
            return None
        return self.enqueue_in_transaction(
            db,
            team_id=team_id,
            event_type=OutboundNotificationEventType.APPROVAL_REJECTED,
            idempotency_key=f"{team_id}:{OutboundNotificationEventType.APPROVAL_REJECTED}:{int(approval.id)}",
            recipient_user_ids=[submitter_id],
            business_type=str(approval.business_type),
            business_id=int(approval.business_id),
            approval_id=int(approval.id),
            actor_id=actor_id,
            payload_json={
                "reject_reason": reject_reason,
                "button_path": button_path or get_approval_action_path(str(approval.business_type)),
            },
        )

    def enqueue_cancelled(
        self,
        db: Session,
        *,
        approval: Approval,
        team_id: int,
        actor_id: str | None = None,
        actor_name: str | None = None,
        recipient_user_ids: list[int] | None = None,
    ) -> OutboundNotificationJobRequest | None:
        recipients = (
            recipient_user_ids
            if recipient_user_ids is not None
            else self._notification_user_ids(db, approval.current_node, team_id)
        )
        return self.enqueue_in_transaction(
            db,
            team_id=team_id,
            event_type=OutboundNotificationEventType.APPROVAL_CANCELLED,
            idempotency_key=f"{team_id}:{OutboundNotificationEventType.APPROVAL_CANCELLED}:{int(approval.id)}",
            recipient_user_ids=recipients,
            business_type=str(approval.business_type),
            business_id=int(approval.business_id),
            approval_id=int(approval.id),
            node_id=int(approval.current_node_id) if approval.current_node_id is not None else None,
            actor_id=actor_id,
            payload_json={"actor_name": actor_name or ""},
        )

    def enqueue_issued(
        self,
        db: Session,
        *,
        team_id: int,
        business_type: str,
        business_id: int,
        recipient_user_id: int,
        actor_id: str | None = None,
        approval_id: int | None = None,
        button_path: str | None = None,
    ) -> OutboundNotificationJobRequest | None:
        return self.enqueue_in_transaction(
            db,
            team_id=team_id,
            event_type=OutboundNotificationEventType.APPROVAL_ISSUED,
            idempotency_key=f"{team_id}:issued:{business_type}:{int(business_id)}",
            recipient_user_ids=[int(recipient_user_id)],
            business_type=business_type,
            business_id=int(business_id),
            approval_id=approval_id,
            actor_id=actor_id,
            payload_json={"button_path": button_path or get_approval_action_path(business_type)},
        )

    def enqueue_reminder(
        self,
        db: Session,
        *,
        approval: Approval,
        team_id: int,
        actor_id: str | None = None,
        recipient_user_ids: list[int] | None = None,
    ) -> OutboundNotificationJobRequest | None:
        node = approval.current_node
        node_id = int(approval.current_node_id) if approval.current_node_id is not None else None
        recipients = recipient_user_ids if recipient_user_ids is not None else self._notification_user_ids(db, node, team_id)
        if node_id is None:
            return None
        return self.enqueue_in_transaction(
            db,
            team_id=team_id,
            event_type=OutboundNotificationEventType.APPROVAL_REMINDER,
            idempotency_key=f"{team_id}:reminder:{int(approval.id)}:{node_id}:{uuid4().hex}",
            recipient_user_ids=recipients,
            business_type=str(approval.business_type),
            business_id=int(approval.business_id),
            approval_id=int(approval.id),
            node_id=node_id,
            actor_id=actor_id,
        )

    def requeue_pending(
        self,
        db: Session,
        *,
        approval: Approval,
        team_id: int,
        actor_id: str | None = None,
    ) -> OutboundNotificationJobRequest | None:
        node_id = int(approval.current_node_id) if approval.current_node_id is not None else None
        recipients = self._notification_user_ids(db, approval.current_node, team_id)
        if node_id is None or not recipients:
            return None
        idempotency_key = self._pending_idempotency_key(team_id, int(approval.id), node_id)
        existing = outbound_notification_job_crud.get_by_idempotency_key(
            db,
            team_id=team_id,
            idempotency_key=idempotency_key,
        )
        if existing is None:
            return self.enqueue_pending_for_approval(
                db,
                approval=approval,
                team_id=team_id,
                actor_id=actor_id,
                recipient_user_ids=recipients,
            )
        if existing.status in {OutboundNotificationJobStatus.QUEUED, OutboundNotificationJobStatus.RUNNING}:
            return OutboundNotificationJobRequest(
                job_public_id=str(existing.public_id),
                team_id=int(existing.team_id),
            )
        if existing.status in {OutboundNotificationJobStatus.FAILED, OutboundNotificationJobStatus.EXHAUSTED}:
            reset = outbound_notification_job_crud.reset_for_retry(
                db,
                team_id=team_id,
                public_id=str(existing.public_id),
                recipient_user_ids=recipients,
                commit=False,
            )
            if reset is None:
                return None
            return OutboundNotificationJobRequest(
                job_public_id=str(reset.public_id),
                team_id=int(reset.team_id),
            )
        return self.enqueue_in_transaction(
            db,
            team_id=team_id,
            event_type=OutboundNotificationEventType.APPROVAL_PENDING,
            idempotency_key=f"{idempotency_key}:resend:{uuid4().hex}",
            recipient_user_ids=recipients,
            business_type=str(approval.business_type),
            business_id=int(approval.business_id),
            approval_id=int(approval.id),
            node_id=node_id,
            actor_id=actor_id,
        )

    def kick(self, request: OutboundNotificationJobRequest | None) -> None:
        """Best-effort latency optimization; durable recovery remains authoritative."""

        if request is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("当前线程没有运行中的事件循环, 出站通知任务交由恢复器执行")
            return

        task = loop.create_task(self._run_guarded(request))
        task.add_done_callback(self._consume_task_exception)

    def commit_and_kick(self, db: Session, request: OutboundNotificationJobRequest | None) -> None:
        if request is None:
            return
        db.commit()
        self.kick(request)

    async def run(self, request: OutboundNotificationJobRequest) -> dict[str, object]:
        settings = get_settings()
        lease_token = uuid4().hex
        claimed_at = business_now()
        lease_expires_at = claimed_at + timedelta(seconds=max(30, settings.OUTBOUND_NOTIFICATION_LEASE_SECONDS))
        max_attempts = max(1, settings.OUTBOUND_NOTIFICATION_MAX_ATTEMPTS)
        db = SessionLocal()
        try:
            existing = outbound_notification_job_crud.get_by_public_id(
                db,
                team_id=request.team_id,
                public_id=request.job_public_id,
            )
            if existing is None:
                raise ValueError("出站通知任务不存在")
            if existing.status in OutboundNotificationJobStatus.TERMINAL:
                return dict(existing.result_json or {})
            if int(existing.attempt_count or 0) >= max_attempts:
                terminal_result = self._retries_exhausted_result(existing, error_message=existing.error_message)
                finalized = outbound_notification_job_crud.finalize_retries_exhausted(
                    db,
                    team_id=request.team_id,
                    public_id=request.job_public_id,
                    max_attempts=max_attempts,
                    result_json=terminal_result,
                    now=claimed_at,
                )
                if finalized is not None and finalized.status in OutboundNotificationJobStatus.TERMINAL:
                    return dict(finalized.result_json or terminal_result)
                return self._busy_result(existing)
            job = outbound_notification_job_crud.claim_for_execution(
                db,
                team_id=request.team_id,
                public_id=request.job_public_id,
                lease_token=lease_token,
                lease_expires_at=lease_expires_at,
                max_attempts=max_attempts,
                now=claimed_at,
            )
            if job is None:
                return self._busy_result(existing)
            job_data = self._snapshot_job(job)
        finally:
            db.close()

        try:
            send_db = SessionLocal()
            try:
                result = await self._deliver(send_db, job_data)
            finally:
                send_db.close()
        except Exception as exc:
            failure_result = await self._record_failure(
                request,
                lease_token=lease_token,
                job_data=job_data,
                exc=exc,
            )
            if failure_result is not None:
                return failure_result
            raise

        persist_db = SessionLocal()
        try:
            skip_reason = str(result.get("skip_reason") or "").strip()
            updated = outbound_notification_job_crud.mark_completed_if_lease_owner(
                persist_db,
                team_id=request.team_id,
                public_id=request.job_public_id,
                lease_token=lease_token,
                result_json=result,
                skipped=bool(skip_reason),
            )
            if updated is None:
                logger.warning("出站通知任务执行结果因租约已变更被忽略: job=%s", request.job_public_id)
                return self._lease_lost_result(job_data)
            return result
        finally:
            persist_db.close()

    async def _run_guarded(self, request: OutboundNotificationJobRequest) -> None:
        try:
            await self.run(request)
        except Exception:
            logger.exception("出站通知任务即时执行失败: job=%s", request.job_public_id)

    async def _record_failure(
        self,
        request: OutboundNotificationJobRequest,
        *,
        lease_token: str,
        job_data: dict[str, Any],
        exc: Exception,
    ) -> dict[str, object] | None:
        settings = get_settings()
        max_attempts = max(1, settings.OUTBOUND_NOTIFICATION_MAX_ATTEMPTS)
        attempt_count = int(job_data.get("attempt_count") or 1)
        db = SessionLocal()
        try:
            if attempt_count >= max_attempts:
                result = self._retries_exhausted_result(job_data, error_message=str(exc))
                updated = outbound_notification_job_crud.mark_exhausted_if_lease_owner(
                    db,
                    team_id=request.team_id,
                    public_id=request.job_public_id,
                    lease_token=lease_token,
                    result_json=result,
                    error_message=str(exc),
                )
                if updated is not None:
                    return result
            else:
                updated = outbound_notification_job_crud.mark_failed_if_lease_owner(
                    db,
                    team_id=request.team_id,
                    public_id=request.job_public_id,
                    lease_token=lease_token,
                    error_message=str(exc),
                    next_attempt_at=self._next_attempt_at(attempt_count),
                )
                if updated is not None:
                    return self._failed_result(job_data, error_message=str(exc))
            logger.warning("出站通知任务失败结果因租约已变更被忽略: job=%s", request.job_public_id)
            return self._lease_lost_result(job_data)
        finally:
            db.close()

    async def _deliver(self, db: Session, job_data: dict[str, Any]) -> dict[str, object]:
        event_type = str(job_data["event_type"])
        if event_type in OutboundNotificationEventType.BUSINESS:
            return await self._deliver_business_event(db, job_data)

        skip_reason = self._pending_skip_reason(db, job_data)
        if skip_reason:
            return self._skipped_result(job_data, skip_reason)

        card = self._rebuild_card(db, job_data)
        if card is None:
            return self._skipped_result(job_data, "ENTITY_NOT_FOUND")

        recipients = _int_ids(job_data.get("recipient_user_ids"))
        if not recipients:
            return self._skipped_result(job_data, "NO_RECIPIENTS")

        event_type = str(job_data["event_type"])
        payload = _payload_dict(job_data.get("payload_json"))
        if event_type == OutboundNotificationEventType.APPROVAL_PENDING:
            notification_result = await feishu_notification_service.notify_approval_pending(
                db=db,
                team_id=int(job_data["team_id"]),
                user_ids=recipients,
                **card,
            )
        elif event_type == OutboundNotificationEventType.APPROVAL_APPROVED:
            notification_result = await feishu_notification_service.notify_approval_approved(
                db=db,
                team_id=int(job_data["team_id"]),
                user_id=recipients[0],
                entity_type=card["entity_type"],
                entity_name=card["entity_name"],
                business_id=card["business_id"],
                detail_fields=card["detail_fields"],
                button_path=_optional_str(payload.get("button_path")) or get_approval_action_path(card["entity_type"]),
            )
        elif event_type == OutboundNotificationEventType.APPROVAL_REJECTED:
            notification_result = await feishu_notification_service.notify_approval_rejected(
                db=db,
                team_id=int(job_data["team_id"]),
                user_id=recipients[0],
                entity_type=card["entity_type"],
                entity_name=card["entity_name"],
                reject_reason=_optional_str(payload.get("reject_reason")) or "无",
                business_id=card["business_id"],
                detail_fields=card["detail_fields"],
                button_path=_optional_str(payload.get("button_path")) or get_approval_action_path(card["entity_type"]),
            )
        elif event_type == OutboundNotificationEventType.APPROVAL_CANCELLED:
            notification_result = await feishu_notification_service.notify_approval_cancelled(
                db=db,
                team_id=int(job_data["team_id"]),
                user_ids=recipients,
                entity_type=card["entity_type"],
                entity_name=card["entity_name"],
                submitter_name=_optional_str(payload.get("actor_name")) or card.get("submitter_name"),
                approval_type_name=card["approval_type_name"],
                detail_fields=card["detail_fields"],
            )
        elif event_type == OutboundNotificationEventType.APPROVAL_ISSUED:
            notification_result = await feishu_notification_service.notify_approval_issued(
                db=db,
                team_id=int(job_data["team_id"]),
                user_id=recipients[0],
                entity_type=card["entity_type"],
                entity_name=card["entity_name"],
                detail_fields=card["detail_fields"],
                button_path=_optional_str(payload.get("button_path")),
            )
        elif event_type == OutboundNotificationEventType.APPROVAL_REMINDER:
            notification_result = await feishu_notification_service.notify_approval_reminder(
                db=db,
                team_id=int(job_data["team_id"]),
                user_ids=recipients,
                entity_type=card["entity_type"],
                entity_name=card["entity_name"],
                node_name=card["node_name"],
                business_id=card["business_id"],
                submitter_name=card.get("submitter_name"),
                approval_type_name=card["approval_type_name"],
                detail_fields=card["detail_fields"],
            )
        else:
            return self._skipped_result(job_data, "UNKNOWN_EVENT_TYPE")

        return {
            "success": True,
            "busy": False,
            "retryable": False,
            "execution_status": "COMPLETED",
            "event_type": event_type,
            "skip_reason": None,
            "error": None,
            "notification_result": dict(notification_result),
        }

    async def _deliver_business_event(self, db: Session, job_data: dict[str, Any]) -> dict[str, object]:
        recipients = _int_ids(job_data.get("recipient_user_ids"))
        if not recipients:
            return self._skipped_result(job_data, "NO_RECIPIENTS")

        event_type = str(job_data["event_type"])
        payload = _payload_dict(job_data.get("payload_json"))
        notification_result = await self._send_business_notification(
            db,
            team_id=int(job_data["team_id"]),
            event_type=event_type,
            recipients=recipients,
            payload=payload,
        )
        if notification_result is None:
            return self._skipped_result(job_data, "UNKNOWN_EVENT_TYPE")
        return {
            "success": True,
            "busy": False,
            "retryable": False,
            "execution_status": "COMPLETED",
            "event_type": event_type,
            "skip_reason": None,
            "error": None,
            "notification_result": dict(notification_result),
        }

    async def _send_business_notification(
        self,
        db: Session,
        *,
        team_id: int,
        event_type: str,
        recipients: list[int],
        payload: dict[str, object],
    ) -> dict[str, int] | None:
        account_name = _optional_str(payload.get("account_name")) or _optional_str(payload.get("customer_name")) or ""
        if event_type == OutboundNotificationEventType.ACCOUNT_CREATED:
            return await feishu_notification_service.notify_account_created(
                db,
                team_id,
                recipients,
                account_name=account_name,
                contact_name=_optional_str(payload.get("contact_name")) or "",
            )
        if event_type == OutboundNotificationEventType.ACCOUNT_STATUS_WON:
            return await feishu_notification_service.notify_account_status_won(
                db,
                team_id,
                recipients,
                account_name=account_name,
            )
        if event_type == OutboundNotificationEventType.ACCOUNT_STATUS_LOST:
            return await feishu_notification_service.notify_account_status_lost(
                db,
                team_id,
                recipients,
                account_name=account_name,
            )
        if event_type == OutboundNotificationEventType.CUSTOMER_RETURNED:
            return await feishu_notification_service.notify_customer_returned(
                db,
                team_id,
                recipients,
                account_name=account_name,
                return_reason=_optional_str(payload.get("return_reason")) or "",
                previous_owner=_optional_str(payload.get("previous_owner")),
            )
        if event_type == OutboundNotificationEventType.LEAD_CLAIMED:
            return await feishu_notification_service.notify_lead_claimed(
                db,
                team_id,
                recipients,
                lead_name=_optional_str(payload.get("lead_name")) or "",
            )
        if event_type == OutboundNotificationEventType.LEAD_ASSIGNED:
            return await feishu_notification_service.notify_lead_assigned(
                db,
                team_id,
                recipients,
                lead_name=_optional_str(payload.get("lead_name")) or "",
                contact_name=_optional_str(payload.get("contact_name")) or "",
                contact_phone=_optional_str(payload.get("contact_phone")) or "",
            )
        if event_type == OutboundNotificationEventType.OPPORTUNITY_WON:
            return await feishu_notification_service.notify_opportunity_won(
                db,
                team_id,
                recipients,
                opportunity_name=_optional_str(payload.get("opportunity_name")) or "",
                customer_name=account_name,
                actual_amount=payload.get("actual_amount") or 0,
            )
        if event_type == OutboundNotificationEventType.OPPORTUNITY_LOST:
            return await feishu_notification_service.notify_opportunity_lost(
                db,
                team_id,
                recipients,
                opportunity_name=_optional_str(payload.get("opportunity_name")) or "",
                customer_name=account_name,
                loss_reason=_optional_str(payload.get("loss_reason")) or "",
            )
        return None

    def _pending_skip_reason(self, db: Session, job_data: dict[str, Any]) -> str | None:
        event_type = str(job_data["event_type"])
        if event_type not in _PENDING_OR_REMINDER:
            return None
        approval_id = job_data.get("approval_id")
        if approval_id is None:
            return "APPROVAL_MISSING"
        approval = approval_crud.get_by_id(db, int(approval_id), int(job_data["team_id"]))
        if approval is None:
            return "APPROVAL_MISSING"
        if approval.status != ApprovalStatus.PENDING:
            return "APPROVAL_NOT_PENDING"
        job_node_id = job_data.get("node_id")
        if job_node_id is not None and int(approval.current_node_id or 0) != int(job_node_id):
            return "NODE_CHANGED"
        return None

    def _rebuild_card(self, db: Session, job_data: dict[str, Any]) -> dict[str, Any] | None:
        business_type = str(job_data["business_type"])
        business_id = int(job_data["business_id"])
        adapter = get_adapter(business_type)
        entity = adapter.get_entity(db, business_id, int(job_data["team_id"]))
        if entity is None:
            return None
        approval = None
        if job_data.get("approval_id") is not None:
            approval = approval_crud.get_by_id(db, int(job_data["approval_id"]), int(job_data["team_id"]))
        current_node = getattr(approval, "current_node", None) if approval is not None else None
        payload = _payload_dict(job_data.get("payload_json"))
        entity_name = adapter.get_name(entity) or _optional_str(payload.get("entity_name")) or f"{business_type}#{business_id}"
        return {
            "entity_type": business_type,
            "entity_name": entity_name,
            "flow_name": approval.flow.flow_name if approval is not None and approval.flow else "",
            "node_name": current_node.node_name if current_node is not None else "",
            "business_id": business_id,
            "submitter_name": approval.submitter_name if approval is not None else None,
            "approval_type_name": get_approval_type_name(business_type),
            "customer_name": get_approval_customer_name(db, business_type, entity),
            "detail_fields": get_approval_card_fields(db, business_type, entity),
        }

    def _notification_user_ids(self, db: Session, node: Any, team_id: int) -> list[int]:
        if not node or not getattr(node, "approve_role", None):
            return []
        role = role_crud.get_by_code(db, node.approve_role)
        if not role:
            logger.warning("审批通知跳过：审批角色不存在（role=%s, team_id=%s）", node.approve_role, team_id)
            return []
        approvers = role_crud.get_role_users(db, role.id, team_id)
        notify_user_ids = getattr(node, "notify_user_ids", None) or []
        if notify_user_ids:
            notify_id_set = {int(user_id) for user_id in notify_user_ids}
            approvers = [user for user in approvers if int(user.id) in notify_id_set]
        user_ids = [int(user.id) for user in approvers]
        if not user_ids:
            logger.warning(
                "审批通知跳过：审批角色无可通知成员（role=%s, team_id=%s）",
                node.approve_role,
                team_id,
            )
        return user_ids

    @staticmethod
    def _pending_idempotency_key(team_id: int, approval_id: int, node_id: int) -> str:
        return f"{team_id}:pending:{approval_id}:{node_id}"

    @staticmethod
    def _snapshot_job(job: OutboundNotificationJob) -> dict[str, Any]:
        return {
            "public_id": str(job.public_id),
            "team_id": int(job.team_id),
            "event_type": str(job.event_type),
            "approval_id": int(job.approval_id) if job.approval_id is not None else None,
            "node_id": int(job.node_id) if job.node_id is not None else None,
            "business_type": str(job.business_type),
            "business_id": int(job.business_id),
            "actor_id": str(job.actor_id) if job.actor_id is not None else None,
            "recipient_user_ids": _int_ids(job.recipient_user_ids),
            "payload_json": _payload_dict(job.payload_json),
            "attempt_count": int(job.attempt_count or 1),
        }

    @staticmethod
    def _next_attempt_at(attempt_count: int | None) -> datetime:
        settings = get_settings()
        base = max(1, settings.OUTBOUND_NOTIFICATION_RETRY_BASE_SECONDS)
        exponent = max(0, int(attempt_count or 1) - 1)
        return business_now() + timedelta(seconds=base * (2**exponent))

    @staticmethod
    def _result_base(job: OutboundNotificationJob | dict[str, Any]) -> dict[str, object]:
        if isinstance(job, dict):
            event_type = job.get("event_type")
        else:
            event_type = job.event_type
        return {
            "success": False,
            "busy": False,
            "retryable": False,
            "execution_status": "FAILED",
            "event_type": event_type,
            "skip_reason": None,
            "error": None,
            "notification_result": None,
        }

    def _retries_exhausted_result(
        self,
        job: OutboundNotificationJob | dict[str, Any],
        *,
        error_message: str | None,
    ) -> dict[str, object]:
        result = self._result_base(job)
        result.update(
            {
                "retryable": False,
                "execution_status": "RETRIES_EXHAUSTED",
                "error": error_message or "outbound notification retries exhausted",
            }
        )
        return result

    def _busy_result(self, job: OutboundNotificationJob | dict[str, Any]) -> dict[str, object]:
        result = self._result_base(job)
        result.update({"busy": True, "execution_status": "BUSY"})
        return result

    def _lease_lost_result(self, job: OutboundNotificationJob | dict[str, Any]) -> dict[str, object]:
        result = self._result_base(job)
        result.update(
            {
                "execution_status": "LEASE_LOST",
                "error": "execution lease ownership changed before persistence",
            }
        )
        return result

    def _failed_result(self, job: OutboundNotificationJob | dict[str, Any], *, error_message: str) -> dict[str, object]:
        result = self._result_base(job)
        result.update({"retryable": True, "execution_status": "FAILED", "error": error_message})
        return result

    def _skipped_result(self, job: OutboundNotificationJob | dict[str, Any], reason: str) -> dict[str, object]:
        result = self._result_base(job)
        result.update({"success": True, "execution_status": "SKIPPED", "skip_reason": reason})
        return result

    @staticmethod
    def _consume_task_exception(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        try:
            task.exception()
        except Exception:
            logger.exception("出站通知后台任务回调失败")


def _normalize_recipient_ids(values: object) -> list[int]:
    if values is None:
        return []
    if isinstance(values, (str, int)):
        return _int_ids([values])
    return _int_ids(values)


def _int_ids(values: object) -> list[int]:
    if not isinstance(values, list):
        return []
    result: list[int] = []
    for value in values:
        parsed = _optional_int(value)
        if parsed is not None and parsed not in result:
            result.append(parsed)
    return result


def _payload_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


outbound_notification_job_service = OutboundNotificationJobService()
