"""Channel-safe facade for follow-up task confirmation cases."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from app.crud.sales_commitment import (
    FollowUpTaskConfirmationPromptDeliveryCRUD,
    follow_up_task_confirmation_case_crud,
    follow_up_task_confirmation_prompt_delivery_crud,
    follow_up_task_crud,
)
from app.models.customer import Customer
from app.models.sales_commitment import (
    FollowUpTask,
    FollowUpTaskConfirmationCase,
    FollowUpTaskConfirmationPromptDelivery,
    FollowUpTaskConfirmationPromptStatus,
    FollowUpTaskConfirmationStatus,
)
from app.services.agent.interaction_contract import (
    INTERACTION_TYPE_CHOICE,
    STATUS_WAITING_USER_INPUT,
    build_interaction,
)
from app.services.follow_up_task_confirmation_application_service import (
    FollowUpTaskConfirmationApplicationService,
    follow_up_task_confirmation_application_service,
)
from app.services.follow_up_task_confirmation_service import (
    FollowUpTaskConfirmationReplyDecision,
    FollowUpTaskConfirmationService,
    follow_up_task_confirmation_service,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION = "resolve_follow_up_task_confirmation_case"
FOLLOW_UP_CONFIRMATION_PROMPT_EVENT = "follow_up_task_confirmation_case_prompt"
FOLLOW_UP_CONFIRMATION_RESOLVED_EVENT = "follow_up_task_confirmation_case_resolved"
DEFAULT_PROMPT_COOLDOWN = timedelta(hours=4)
DEFAULT_MAX_PROMPTS_PER_CASE = 3


class FollowUpTaskConfirmationChannelService:
    """Shared business entrypoint for Web Agent, IM, and future channel adapters."""

    def __init__(
        self,
        *,
        application_service: FollowUpTaskConfirmationApplicationService = (
            follow_up_task_confirmation_application_service
        ),
        confirmation_service: FollowUpTaskConfirmationService = follow_up_task_confirmation_service,
        prompt_delivery_crud: FollowUpTaskConfirmationPromptDeliveryCRUD = (
            follow_up_task_confirmation_prompt_delivery_crud
        ),
        prompt_cooldown: timedelta = DEFAULT_PROMPT_COOLDOWN,
        max_prompts_per_case: int = DEFAULT_MAX_PROMPTS_PER_CASE,
    ) -> None:
        self.application_service = application_service
        self.confirmation_service = confirmation_service
        self.prompt_delivery_crud = prompt_delivery_crud
        self.prompt_cooldown = prompt_cooldown
        self.max_prompts_per_case = max_prompts_per_case

    def list_pending_cases(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
    ) -> dict[str, Any]:
        cases, total = follow_up_task_confirmation_case_crud.list_pending_for_owner(
            db,
            team_id=team_id,
            owner_id=str(user_id),
            skip=skip,
            limit=limit,
        )
        tasks_by_id = {
            task.id: task
            for task in [follow_up_task_crud.get_by_id(db, case.task_id, team_id=team_id) for case in cases]
            if task is not None
        }
        customers_by_id = self._customers_by_id(
            db,
            team_id=team_id,
            customer_ids=[case.customer_id for case in cases],
        )
        return {
            "items": [
                self._case_payload(
                    case,
                    task=tasks_by_id.get(case.task_id),
                    customer=customers_by_id.get(case.customer_id),
                )
                for case in cases
            ],
            "total": total,
            "skip": skip,
            "limit": limit,
            "filters": {
                "status": FollowUpTaskConfirmationStatus.PENDING,
                "owner_scope": "mine",
            },
            "usage_policy": {
                "case_state_source": "mysql.crm_follow_up_task_confirmation_cases",
                "task_state_source": "mysql.crm_follow_up_tasks",
                "rule": "确认Case只展示给任务归属人; 应用结果仍由确认应用服务做二次校验.",
            },
        }

    def is_case_pending_for_owner(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        case_public_id: str,
    ) -> bool:
        """Revalidate an Agent interrupt against the durable owner-scoped inbox."""

        case = follow_up_task_confirmation_case_crud.get_by_public_id(
            db,
            case_public_id,
            team_id=team_id,
        )
        if case is None or case.owner_id != str(user_id):
            return False
        if case.status != FollowUpTaskConfirmationStatus.PENDING:
            return False
        return case.expires_at is None or case.expires_at > business_now()

    def resolve_reply(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        case_public_id: str,
        reply_text: str,
    ) -> dict[str, Any]:
        case, decision, application = self.application_service.resolve_reply_and_apply(
            db,
            team_id=team_id,
            case_public_id=case_public_id,
            actor_id=str(user_id),
            reply_text=reply_text,
        )
        task = (
            follow_up_task_crud.get_by_public_id(db, application.task_public_id, team_id)
            if application.task_public_id
            else None
        )
        return {
            "case": self._case_payload(case, task=task, customer=None) if case is not None else None,
            "decision": {
                "action": decision.action,
                "confidence": decision.confidence,
                "reason": decision.reason,
                "resolved": decision.resolved,
                "proposed_due_at": decision.proposed_due_at.isoformat() if decision.proposed_due_at else None,
                "proposed_due_at_text": decision.proposed_due_at_text,
            },
            "application": application.to_dict(),
            "assistant_follow_up_prompt": self._assistant_follow_up_prompt(decision.resolved),
            "usage_policy": {
                "mutation_gate": "follow_up_task_confirmation_application_service",
                "rule": "用户自然语言回复只解析为确认意图; 真正任务状态变更必须通过确认应用服务和迁移执行器.",
            },
        }

    def resolve_reply_event(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        case_public_id: str,
        reply_text: str,
    ) -> dict[str, Any]:
        """Resolve through the application service and project a channel event."""

        return self._resolution_event(
            self.resolve_reply(
                db,
                team_id=team_id,
                user_id=user_id,
                case_public_id=case_public_id,
                reply_text=reply_text,
            )
        )

    def preview_reply_decision(
        self,
        reply_text: str,
        *,
        base_date: datetime | None = None,
    ) -> FollowUpTaskConfirmationReplyDecision:
        return self.confirmation_service.interpret_reply(reply_text, base_date=base_date)

    def prepare_case_prompt_by_public_ids(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        case_public_ids: list[str],
        interaction_scope: str,
        prompt_override: str | None = None,
        reason_code: str = "ROOT_GRAPH_INTERRUPT_PLANNED",
    ) -> dict[str, Any] | None:
        """Build one owner-scoped pending interaction without claiming delivery."""

        owner_id = str(user_id)
        seen: set[str] = set()
        for case_public_id in case_public_ids:
            if not case_public_id or case_public_id in seen:
                continue
            seen.add(case_public_id)
            case = follow_up_task_confirmation_case_crud.get_by_public_id(
                db,
                case_public_id,
                team_id=team_id,
            )
            if case is None:
                continue
            interaction_id = self._stable_interaction_id(
                case_public_id=case.public_id,
                interaction_scope=interaction_scope,
            )
            prompt_key = self._projection_prompt_key(
                case_public_id=case.public_id,
                interaction_scope=interaction_scope,
            )
            if case.owner_id != owner_id:
                self._record_projection_attempt(
                    db,
                    case=case,
                    owner_id=owner_id,
                    interaction_id=interaction_id,
                    prompt_key=prompt_key,
                    interaction_scope=interaction_scope,
                    status=FollowUpTaskConfirmationPromptStatus.SKIPPED,
                    reason_code="OWNER_MISMATCH",
                )
                continue
            if case.status != FollowUpTaskConfirmationStatus.PENDING:
                self._record_projection_attempt(
                    db,
                    case=case,
                    owner_id=owner_id,
                    interaction_id=interaction_id,
                    prompt_key=prompt_key,
                    interaction_scope=interaction_scope,
                    status=FollowUpTaskConfirmationPromptStatus.SKIPPED,
                    reason_code=f"CASE_NOT_PENDING_{case.status}",
                )
                continue
            task = follow_up_task_crud.get_by_id(db, case.task_id, team_id=team_id)
            customer = self._customers_by_id(
                db,
                team_id=team_id,
                customer_ids=[case.customer_id],
            ).get(case.customer_id)
            event = self._prompt_event(case, task=task, customer=customer)
            interaction = event.get("interaction")
            if prompt_override:
                event["content"] = prompt_override
                if isinstance(interaction, dict):
                    interaction["prompt"] = prompt_override
            if isinstance(interaction, dict):
                interaction["interaction_id"] = interaction_id
            delivery = self._record_projection_attempt(
                db,
                case=case,
                owner_id=owner_id,
                interaction_id=interaction_id,
                prompt_key=prompt_key,
                interaction_scope=interaction_scope,
                status=FollowUpTaskConfirmationPromptStatus.QUEUED,
                reason_code=reason_code,
            )
            if isinstance(interaction, dict):
                payload = interaction.get("payload")
                if not isinstance(payload, dict):
                    payload = {}
                    interaction["payload"] = payload
                payload["prompt_delivery_key"] = prompt_key
            event["delivery"] = {
                **self._delivery_payload(delivery),
                "status": delivery.status,
                "reason_code": delivery.reason_code,
                "interaction_scope": interaction_scope,
                "prompt_key": prompt_key,
            }
            return event
        return None

    def mark_projection_projected(
        self,
        db: Session,
        *,
        team_id: int,
        prompt_key: str,
    ) -> FollowUpTaskConfirmationPromptDelivery | None:
        """Acknowledge projection only after the Root Graph checkpoint exposes the interrupt."""

        delivery = self.prompt_delivery_crud.get_by_prompt_key(
            db,
            team_id=team_id,
            prompt_key=prompt_key,
        )
        if delivery is None:
            return None
        if delivery.status == FollowUpTaskConfirmationPromptStatus.PROJECTED:
            return delivery
        if delivery.status != FollowUpTaskConfirmationPromptStatus.QUEUED:
            return delivery
        return self.prompt_delivery_crud.update_attempt_status(
            db,
            delivery,
            status=FollowUpTaskConfirmationPromptStatus.PROJECTED,
            reason_code="ROOT_GRAPH_INTERRUPT_CHECKPOINTED",
        )

    def mark_projection_failed(
        self,
        db: Session,
        *,
        team_id: int,
        prompt_key: str,
        error_message: str,
    ) -> FollowUpTaskConfirmationPromptDelivery | None:
        """Record an acknowledgement/audit failure for a checkpoint-visible prompt."""

        delivery = self.prompt_delivery_crud.get_by_prompt_key(
            db,
            team_id=team_id,
            prompt_key=prompt_key,
        )
        if delivery is None:
            return None
        return self.prompt_delivery_crud.update_attempt_status(
            db,
            delivery,
            status=FollowUpTaskConfirmationPromptStatus.FAILED,
            reason_code="ROOT_GRAPH_PROJECTION_ACK_FAILED",
            error_message=error_message[:2000],
        )

    def record_projection_failure_by_public_ids(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        case_public_ids: list[str],
        interaction_scope: str,
        error_message: str,
    ) -> list[FollowUpTaskConfirmationPromptDelivery]:
        """Persist owner-scoped failed Root Graph projection attempts when the DB is still available."""

        owner_id = str(user_id)
        deliveries: list[FollowUpTaskConfirmationPromptDelivery] = []
        seen: set[str] = set()
        for case_public_id in case_public_ids:
            if not case_public_id or case_public_id in seen:
                continue
            seen.add(case_public_id)
            case = follow_up_task_confirmation_case_crud.get_by_public_id(
                db,
                case_public_id,
                team_id=team_id,
            )
            if case is None or case.owner_id != owner_id:
                continue
            interaction_id = self._stable_interaction_id(
                case_public_id=case.public_id,
                interaction_scope=interaction_scope,
            )
            prompt_key = self._projection_prompt_key(
                case_public_id=case.public_id,
                interaction_scope=interaction_scope,
            )
            queued = self.prompt_delivery_crud.get_by_prompt_key(
                db,
                team_id=case.team_id,
                prompt_key=prompt_key,
            )
            if queued is not None and queued.status == FollowUpTaskConfirmationPromptStatus.QUEUED:
                deliveries.append(self.prompt_delivery_crud.update_attempt_status(
                    db,
                    queued,
                    status=FollowUpTaskConfirmationPromptStatus.FAILED,
                    reason_code="ROOT_GRAPH_PROJECTION_FAILED",
                    error_message=error_message[:2000],
                ))
                continue
            deliveries.append(self.prompt_delivery_crud.create_attempt(
                db,
                team_id=case.team_id,
                case_id=case.id,
                owner_id=owner_id,
                channel="agent",
                provider="langgraph",
                agent_session_id=None,
                interaction_id=interaction_id,
                prompt_key=prompt_key,
                status=FollowUpTaskConfirmationPromptStatus.FAILED,
                reason_code="ROOT_GRAPH_PROJECTION_FAILED",
                error_message=error_message[:2000],
                payload_json={
                    "case_public_id": case.public_id,
                    "interaction_scope": interaction_scope,
                },
                thread_id=interaction_scope,
            ))
        return deliveries

    def _record_projection_attempt(
        self,
        db: Session,
        *,
        case: FollowUpTaskConfirmationCase,
        owner_id: str,
        interaction_id: str,
        prompt_key: str,
        interaction_scope: str,
        status: str,
        reason_code: str,
    ) -> FollowUpTaskConfirmationPromptDelivery:
        existing = self.prompt_delivery_crud.get_by_prompt_key(
            db,
            team_id=case.team_id,
            prompt_key=prompt_key,
        )
        if (
            existing is not None
            and existing.status == FollowUpTaskConfirmationPromptStatus.FAILED
            and status == FollowUpTaskConfirmationPromptStatus.QUEUED
        ):
            return self.prompt_delivery_crud.update_attempt_status(
                db,
                existing,
                status=FollowUpTaskConfirmationPromptStatus.QUEUED,
                reason_code=reason_code,
                error_message=None,
                attempted_at=business_now(),
                delivered_at=None,
            )
        return self.prompt_delivery_crud.create_attempt(
            db,
            team_id=case.team_id,
            case_id=case.id,
            owner_id=owner_id,
            channel="agent",
            provider="langgraph",
            agent_session_id=None,
            interaction_id=interaction_id,
            prompt_key=prompt_key,
            status=status,
            reason_code=reason_code,
            payload_json={
                "case_public_id": case.public_id,
                "interaction_scope": interaction_scope,
            },
            thread_id=interaction_scope,
        )

    def prompt_next_pending_case(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        channel: str,
        provider: str | None = None,
        agent_session_id: int | None = None,
        now: datetime | None = None,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        resolved_now = now or business_now()
        case = self._select_prompt_case(
            db,
            team_id=team_id,
            owner_id=str(user_id),
            now=resolved_now,
        )
        if case is None:
            return None

        return self._deliver_prompt(
            db,
            team_id=team_id,
            case=case,
            channel=channel,
            provider=provider,
            agent_session_id=agent_session_id,
            prompted_at=resolved_now,
            commit=commit,
        )

    def prompt_cases_by_public_ids(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        case_public_ids: list[str],
        channel: str,
        provider: str | None = None,
        agent_session_id: int | None = None,
        now: datetime | None = None,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        resolved_now = now or business_now()
        events: list[dict[str, Any]] = []
        seen: set[str] = set()
        owner_id = str(user_id)
        for case_public_id in case_public_ids:
            if not case_public_id or case_public_id in seen:
                continue
            seen.add(case_public_id)
            case = follow_up_task_confirmation_case_crud.get_by_public_id(
                db,
                str(case_public_id),
                team_id=team_id,
            )
            if case is None:
                continue
            if case.status != FollowUpTaskConfirmationStatus.PENDING or case.owner_id != owner_id:
                continue
            if not self._case_prompt_allowed(
                db,
                team_id=team_id,
                case=case,
                now=resolved_now,
            ):
                continue
            events.append(
                self._deliver_prompt(
                    db,
                    team_id=team_id,
                    case=case,
                    channel=channel,
                    provider=provider,
                    agent_session_id=agent_session_id,
                    prompted_at=resolved_now,
                    prompt_scope="current_activity",
                    commit=False,
                )
            )
        if commit and events:
            db.commit()
        return events

    def _select_prompt_case(
        self,
        db: Session,
        *,
        team_id: int,
        owner_id: str,
        now: datetime,
    ) -> FollowUpTaskConfirmationCase | None:
        cooldown_since = now - self.prompt_cooldown
        recent_owner_delivery = self.prompt_delivery_crud.latest_for_owner_since(
            db,
            team_id=team_id,
            owner_id=owner_id,
            since=cooldown_since,
        )
        if recent_owner_delivery is not None:
            return None

        cases, _ = follow_up_task_confirmation_case_crud.list_pending_for_owner(
            db,
            team_id=team_id,
            owner_id=owner_id,
            limit=20,
            now=now,
        )
        for case in cases:
            if self._case_prompt_allowed(db, team_id=team_id, case=case, now=now):
                return case
        return None

    def _case_prompt_allowed(
        self,
        db: Session,
        *,
        team_id: int,
        case: FollowUpTaskConfirmationCase,
        now: datetime,
    ) -> bool:
        if int(case.prompt_count or 0) >= self.max_prompts_per_case:
            return False
        recent_case_delivery = self.prompt_delivery_crud.latest_for_case_since(
            db,
            team_id=team_id,
            case_id=case.id,
            since=now - self.prompt_cooldown,
        )
        return recent_case_delivery is None

    def _deliver_prompt(
        self,
        db: Session,
        *,
        team_id: int,
        case: FollowUpTaskConfirmationCase,
        channel: str,
        provider: str | None,
        agent_session_id: int | None,
        prompted_at: datetime,
        prompt_scope: str | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        task = follow_up_task_crud.get_by_id(db, case.task_id, team_id=team_id)
        customer = self._customers_by_id(db, team_id=team_id, customer_ids=[case.customer_id]).get(case.customer_id)
        event = self._prompt_event(case, task=task, customer=customer)
        interaction = event["interaction"]
        payload_json = {
            "event": event["event"],
            "case_public_id": case.public_id,
            "task_public_id": task.public_id if task is not None else None,
            "customer_public_id": customer.public_id if customer is not None else None,
        }
        if prompt_scope:
            payload_json["prompt_scope"] = prompt_scope
        prompt_key = f"{case.public_id}:{interaction['interaction_id']}"
        delivery = self.prompt_delivery_crud.create_sent(
            db,
            team_id=team_id,
            case_id=case.id,
            owner_id=case.owner_id,
            channel=channel,
            provider=provider,
            agent_session_id=agent_session_id,
            interaction_id=str(interaction["interaction_id"]),
            prompt_key=prompt_key,
            payload_json=payload_json,
            prompted_at=prompted_at,
            commit=False,
        )
        follow_up_task_confirmation_case_crud.mark_prompted(
            db,
            case,
            prompted_at=prompted_at,
            commit=False,
        )
        if commit:
            db.commit()
            db.refresh(case)
            db.refresh(delivery)
        event["delivery"] = self._delivery_payload(delivery)
        return event

    def _prompt_event(
        self,
        case: FollowUpTaskConfirmationCase,
        *,
        task: FollowUpTask | None,
        customer: Customer | None,
    ) -> dict[str, Any]:
        case_payload = self._case_payload(case, task=task, customer=customer)
        prompt = self._prompt_text(case_payload)
        interaction = build_interaction(
            event_name=FOLLOW_UP_CONFIRMATION_PROMPT_EVENT,
            interaction_type=INTERACTION_TYPE_CHOICE,
            prompt=prompt,
            status=STATUS_WAITING_USER_INPUT,
            title="确认跟进进展",
            business_action=FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION,
            payload={
                "case_public_id": case.public_id,
                "case": case_payload,
                "reply_binding": "follow_up_task_confirmation_case",
            },
            choices=[
                self._reply_choice("已完成", case.public_id),
                self._reply_choice("先放着", case.public_id),
                self._reply_choice("不管了", case.public_id),
            ],
        )
        return {
            "event": FOLLOW_UP_CONFIRMATION_PROMPT_EVENT,
            "content": prompt,
            "content_format": "text",
            "case_public_id": case.public_id,
            "cases": [case_payload],
            "interaction": interaction,
            "usage_policy": {
                "channel_contract": "agent.interaction.v1",
                "reply_binding": "case_public_id",
                "frequency_source": "mysql.crm_follow_up_task_confirmation_prompt_deliveries",
                "rule": "同一用户跨渠道共享频控; 渠道只展示和回传回复, 不承载任务状态变更逻辑.",
            },
        }

    @staticmethod
    def _projection_prompt_key(*, case_public_id: str, interaction_scope: str) -> str:
        """Return a bounded idempotency key while preserving the full scope in thread_id."""

        digest = hashlib.sha256(f"{case_public_id}:{interaction_scope}".encode()).hexdigest()
        return f"projection:{digest}"

    @staticmethod
    def _stable_interaction_id(*, case_public_id: str, interaction_scope: str) -> str:
        digest = hashlib.sha256(f"{case_public_id}:{interaction_scope}".encode()).hexdigest()[:32]
        return f"int_fuc_{digest}"

    def _resolution_event(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        content = self._resolution_text(payload)
        event = {
            "event": FOLLOW_UP_CONFIRMATION_RESOLVED_EVENT,
            "content": content,
            "content_format": "text",
            **payload,
        }
        return event

    def _case_payload(
        self,
        case: FollowUpTaskConfirmationCase,
        *,
        task: FollowUpTask | None,
        customer: Customer | None,
    ) -> dict[str, Any]:
        return {
            "id": case.public_id,
            "public_id": case.public_id,
            "status": case.status,
            "question_text": case.question_text,
            "suggested_action": case.suggested_action,
            "owner_id": case.owner_id,
            "creator_id": case.creator_id,
            "customer": self._customer_payload(customer),
            "task": self._task_payload(task),
            "expires_at": case.expires_at.isoformat() if case.expires_at else None,
            "prompt_count": case.prompt_count,
            "last_prompted_at": case.last_prompted_at.isoformat() if case.last_prompted_at else None,
            "unresolved_reply_count": case.unresolved_reply_count,
            "last_unresolved_reply_text": case.last_unresolved_reply_text,
            "last_unresolved_reply_at": (
                case.last_unresolved_reply_at.isoformat() if case.last_unresolved_reply_at else None
            ),
            "resolved_action": case.resolved_action,
            "resolved_due_at": case.resolved_due_at.isoformat() if case.resolved_due_at else None,
            "resolved_due_at_text": case.resolved_due_at_text,
            "expired_at": case.expired_at.isoformat() if case.expired_at else None,
            "application_status": case.application_status,
            "application_skip_reason": case.application_skip_reason,
            "applied_at": case.applied_at.isoformat() if case.applied_at else None,
            "created_time": case.created_time.isoformat() if case.created_time else None,
        }

    @staticmethod
    def _assistant_follow_up_prompt(resolved: bool) -> str | None:
        if resolved:
            return None
        return (
            "我还不能判断这项跟进是已完成、延期、取消, 还是先保留。请直接回复例如: 已完成、先放着、不管了、下周五再说。"
        )

    def _prompt_interaction_for_case_payload(self, case_payload: dict[str, Any], prompt: str) -> dict[str, object]:
        case_public_id = str(case_payload["public_id"])
        return build_interaction(
            event_name=FOLLOW_UP_CONFIRMATION_PROMPT_EVENT,
            interaction_type=INTERACTION_TYPE_CHOICE,
            prompt=prompt,
            status=STATUS_WAITING_USER_INPUT,
            title="确认跟进进展",
            business_action=FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION,
            payload={
                "case_public_id": case_public_id,
                "case": case_payload,
                "reply_binding": "follow_up_task_confirmation_case",
            },
            choices=[
                self._reply_choice("已完成", case_public_id),
                self._reply_choice("先放着", case_public_id),
                self._reply_choice("不管了", case_public_id),
            ],
        )

    @staticmethod
    def _reply_choice(label: str, case_public_id: str) -> dict[str, object]:
        return {
            "label": label,
            "value": label,
            "metadata": {
                "business_action": FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION,
                "selected_value": label,
                "case_public_id": case_public_id,
                "follow_up_confirmation_case_public_id": case_public_id,
            },
        }

    @staticmethod
    def _prompt_text(case_payload: dict[str, Any]) -> str:
        task = case_payload.get("task") if isinstance(case_payload.get("task"), dict) else {}
        customer = case_payload.get("customer") if isinstance(case_payload.get("customer"), dict) else {}
        customer_name = str(customer.get("account_name") or customer.get("name") or "这个客户")
        task_title = str(task.get("title") or "上次跟进")
        question = str(case_payload.get("question_text") or "")
        return f"你有一项上次跟进需要确认: {customer_name} - {task_title}. {question}"

    @staticmethod
    def _resolution_text(payload: dict[str, Any]) -> str:
        decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
        application = payload.get("application") if isinstance(payload.get("application"), dict) else {}
        if payload.get("assistant_follow_up_prompt"):
            return str(payload["assistant_follow_up_prompt"])
        if application.get("status") == "APPLIED":
            action = decision.get("action")
            if action == "COMPLETE":
                return "已确认完成, 并更新了这项跟进任务。"
            if action == "DELAY":
                return "已确认延期, 并更新了这项跟进任务。"
            if action == "CANCEL":
                return "已确认取消, 并更新了这项跟进任务。"
            return "已确认, 并更新了这项跟进任务。"
        if application.get("skip_reason") == "KEEP_OPEN_NO_MUTATION":
            return "好的, 这项跟进先保留。"
        if application.get("skip_reason") == "CONFIRMATION_CASE_NOT_RESOLVED":
            return "这项确认还没有明确处理结果, 我暂时没有修改任务。"
        return "已记录你的回复。"

    @staticmethod
    def _delivery_payload(delivery: FollowUpTaskConfirmationPromptDelivery) -> dict[str, Any]:
        return {
            "id": delivery.public_id,
            "public_id": delivery.public_id,
            "channel": delivery.channel,
            "provider": delivery.provider,
            "agent_session_id": delivery.agent_session_id,
            "interaction_id": delivery.interaction_id,
            "status": delivery.status,
            "reason_code": delivery.reason_code,
            "prompted_at": delivery.prompted_at.isoformat() if delivery.prompted_at else None,
            "attempted_at": delivery.attempted_at.isoformat() if delivery.attempted_at else None,
            "delivered_at": delivery.delivered_at.isoformat() if delivery.delivered_at else None,
        }

    @staticmethod
    def _task_payload(task: FollowUpTask | None) -> dict[str, Any] | None:
        if task is None:
            return None
        return {
            "id": task.public_id,
            "public_id": task.public_id,
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "due_at": task.due_at.isoformat() if task.due_at else None,
            "due_at_text": task.due_at_text,
            "source_type": task.source_type,
            "source_public_id": task.source_public_id,
        }

    @staticmethod
    def _customer_payload(customer: Customer | None) -> dict[str, Any] | None:
        if customer is None:
            return None
        return {
            "id": customer.public_id,
            "public_id": customer.public_id,
            "name": customer.account_name,
            "account_name": customer.account_name,
        }

    @staticmethod
    def _customers_by_id(db: Session, *, team_id: int, customer_ids: list[int]) -> dict[int, Customer]:
        ids = list(dict.fromkeys(customer_id for customer_id in customer_ids if customer_id))
        if not ids:
            return {}
        rows = db.query(Customer).filter(Customer.team_id == team_id, Customer.id.in_(ids)).all()
        return {customer.id: customer for customer in rows}


follow_up_task_confirmation_channel_service = FollowUpTaskConfirmationChannelService()
