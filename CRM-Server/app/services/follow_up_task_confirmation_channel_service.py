"""Channel-safe facade for follow-up task confirmation cases."""

from __future__ import annotations

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
        limit: int = 20,
    ) -> dict[str, Any]:
        cases, total = follow_up_task_confirmation_case_crud.list_pending_for_owner(
            db,
            team_id=team_id,
            owner_id=str(user_id),
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

    def preview_reply_decision(
        self,
        reply_text: str,
        *,
        base_date: datetime | None = None,
    ) -> FollowUpTaskConfirmationReplyDecision:
        return self.confirmation_service.interpret_reply(reply_text, base_date=base_date)

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

        task = follow_up_task_crud.get_by_id(db, case.task_id, team_id=team_id)
        customer = self._customers_by_id(db, team_id=team_id, customer_ids=[case.customer_id]).get(case.customer_id)
        event = self._prompt_event(case, task=task, customer=customer)
        interaction = event["interaction"]
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
            payload_json={
                "event": event["event"],
                "case_public_id": case.public_id,
                "task_public_id": task.public_id if task is not None else None,
                "customer_public_id": customer.public_id if customer is not None else None,
            },
            prompted_at=resolved_now,
            commit=False,
        )
        follow_up_task_confirmation_case_crud.mark_prompted(
            db,
            case,
            prompted_at=resolved_now,
            commit=False,
        )
        if commit:
            db.commit()
            db.refresh(case)
            db.refresh(delivery)
        event["delivery"] = self._delivery_payload(delivery)
        return event

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
            if int(case.prompt_count or 0) >= self.max_prompts_per_case:
                continue
            recent_case_delivery = self.prompt_delivery_crud.latest_for_case_since(
                db,
                team_id=team_id,
                case_id=case.id,
                since=cooldown_since,
            )
            if recent_case_delivery is None:
                return case
        return None

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
        case_payload = payload.get("case")
        if payload.get("assistant_follow_up_prompt") and isinstance(case_payload, dict):
            event["interaction"] = self._prompt_interaction_for_case_payload(
                case_payload,
                str(payload["assistant_follow_up_prompt"]),
            )
        return event

    def resolve_bound_reply(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        case_public_id: str,
        reply_text: str,
    ) -> dict[str, Any]:
        result = self.resolve_reply(
            db,
            team_id=team_id,
            user_id=user_id,
            case_public_id=case_public_id,
            reply_text=reply_text,
        )
        return self._resolution_event(result)

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
            "prompted_at": delivery.prompted_at.isoformat() if delivery.prompted_at else None,
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
