"""Confirmation case management for unsafe follow-up task transitions."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol

from app.crud.sales_commitment import follow_up_task_confirmation_case_crud
from app.models.sales_commitment import (
    FollowUpTaskConfirmationResolutionAction,
    FollowUpTaskConfirmationStatus,
)
from app.schemas.sales_commitment import FollowUpTaskConfirmationCaseInternalCreate
from app.services.follow_up_parser import follow_up_parser_service
from app.services.follow_up_task_transition_plan_service import (
    FollowUpTaskTransitionAction,
    FollowUpTaskTransitionActionType,
    FollowUpTaskTransitionPlan,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.sales_commitment import FollowUpTask, FollowUpTaskConfirmationCase


class FollowUpTaskConfirmationCaseCrudProtocol(Protocol):
    def get_pending_by_hash(
        self,
        db: Session,
        *,
        team_id: int,
        confirmation_hash: str,
    ) -> FollowUpTaskConfirmationCase | None: ...

    def get_by_public_id(
        self,
        db: Session,
        public_id: str,
        team_id: int | None = None,
    ) -> FollowUpTaskConfirmationCase | None: ...

    def create(
        self,
        db: Session,
        obj_in: FollowUpTaskConfirmationCaseInternalCreate | dict[str, object],
        *,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCase: ...

    def mark_prompted(
        self,
        db: Session,
        db_obj: FollowUpTaskConfirmationCase,
        *,
        prompted_at: datetime | None = None,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCase: ...

    def record_unresolved_reply(
        self,
        db: Session,
        db_obj: FollowUpTaskConfirmationCase,
        *,
        reply_text: str,
        actor_id: str,
        replied_at: datetime | None = None,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCase: ...

    def resolve(
        self,
        db: Session,
        db_obj: FollowUpTaskConfirmationCase,
        *,
        resolved_action: str,
        resolved_by_id: str,
        resolution_text: str,
        resolved_due_at: datetime | None = None,
        resolved_due_at_text: str | None = None,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCase: ...

    def mark_expired(
        self,
        db: Session,
        db_obj: FollowUpTaskConfirmationCase,
        *,
        expired_at: datetime | None = None,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCase: ...


DEFAULT_CONFIRMATION_CASE_TTL_DAYS = 14


@dataclass(frozen=True)
class FollowUpTaskConfirmationCaseResult:
    case: FollowUpTaskConfirmationCase
    created: bool
    confirmation_hash: str


@dataclass(frozen=True)
class FollowUpTaskConfirmationReplyDecision:
    action: str
    confidence: float
    reason: str
    proposed_due_at: datetime | None = None
    proposed_due_at_text: str | None = None

    @property
    def resolved(self) -> bool:
        return self.action != FollowUpTaskConfirmationResolutionAction.UNKNOWN


class FollowUpTaskConfirmationService:
    """Creates confirmation cases and interprets user replies without mutating task state."""

    def __init__(
        self,
        *,
        confirmation_case_crud: FollowUpTaskConfirmationCaseCrudProtocol = follow_up_task_confirmation_case_crud,
    ) -> None:
        self.confirmation_case_crud = confirmation_case_crud

    def create_case_from_plan_action(
        self,
        db: Session,
        *,
        team_id: int,
        task: FollowUpTask,
        plan: FollowUpTaskTransitionPlan,
        action: FollowUpTaskTransitionAction,
        actor_id: str,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCaseResult:
        if not action.requires_confirmation:
            raise ValueError("confirmation case requires a confirmation action")
        confirmation_hash = self._confirmation_hash(team_id=team_id, task=task, plan=plan, action=action)
        existing = self.confirmation_case_crud.get_pending_by_hash(
            db,
            team_id=team_id,
            confirmation_hash=confirmation_hash,
        )
        if existing is not None:
            return FollowUpTaskConfirmationCaseResult(
                case=existing,
                created=False,
                confirmation_hash=confirmation_hash,
            )

        case = self.confirmation_case_crud.create(
            db,
            FollowUpTaskConfirmationCaseInternalCreate(
                team_id=team_id,
                task_id=task.id,
                customer_id=task.customer_id,
                owner_id=task.owner_id,
                creator_id=actor_id,
                suggested_action=self._suggested_action(plan, action),
                confirmation_hash=confirmation_hash,
                question_text=self._question_text(task=task, plan=plan, action=action),
                source_activity_id=task.source_activity_id,
                source_public_id=action.source_activity_public_id or task.source_public_id,
                source_plan_json=plan.to_dict(),
                expires_at=self._default_expires_at(),
            ),
            commit=commit,
        )
        return FollowUpTaskConfirmationCaseResult(case=case, created=True, confirmation_hash=confirmation_hash)

    def mark_prompted(
        self,
        db: Session,
        *,
        case: FollowUpTaskConfirmationCase,
        prompted_at: datetime | None = None,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCase:
        return self.confirmation_case_crud.mark_prompted(
            db,
            case,
            prompted_at=prompted_at,
            commit=commit,
        )

    def interpret_reply(
        self,
        reply_text: str,
        *,
        base_date: datetime | None = None,
    ) -> FollowUpTaskConfirmationReplyDecision:
        text = self._normalize_text(reply_text)
        if not text:
            return FollowUpTaskConfirmationReplyDecision(
                action=FollowUpTaskConfirmationResolutionAction.UNKNOWN,
                confidence=0.0,
                reason="EMPTY_REPLY",
            )

        if self._contains_any(text, ("不用管", "不管了", "取消", "不用跟", "不用再跟", "不需要跟")):
            return FollowUpTaskConfirmationReplyDecision(
                action=FollowUpTaskConfirmationResolutionAction.CANCEL,
                confidence=0.92,
                reason="DIRECT_CANCEL_TEXT",
            )

        proposed_due_at = self._parse_due_at_text(reply_text, base_date=base_date)
        delay_terms = ("下周", "明天", "后天", "天后", "日后", "周后", "再说", "再看", "再联系")
        if proposed_due_at is not None and self._contains_any(text, delay_terms):
            return FollowUpTaskConfirmationReplyDecision(
                action=FollowUpTaskConfirmationResolutionAction.DELAY,
                confidence=0.88,
                reason="DELAY_TIME_TEXT",
                proposed_due_at=proposed_due_at,
                proposed_due_at_text=reply_text.strip(),
            )

        if self._contains_any(text, ("先放着", "先保留", "保留", "还没有进展", "没进展", "继续跟", "继续跟进")):
            return FollowUpTaskConfirmationReplyDecision(
                action=FollowUpTaskConfirmationResolutionAction.KEEP_OPEN,
                confidence=0.86,
                reason="KEEP_OPEN_TEXT",
            )

        if self._contains_any(text, ("完成", "已确认", "已经确认", "确认了", "搞定", "通过了", "已处理")):
            return FollowUpTaskConfirmationReplyDecision(
                action=FollowUpTaskConfirmationResolutionAction.COMPLETE,
                confidence=0.9,
                reason="DIRECT_COMPLETE_TEXT",
            )

        return FollowUpTaskConfirmationReplyDecision(
            action=FollowUpTaskConfirmationResolutionAction.UNKNOWN,
            confidence=0.0,
            reason="UNRECOGNIZED_REPLY",
        )

    def resolve_case_from_reply(
        self,
        db: Session,
        *,
        team_id: int,
        case_public_id: str,
        actor_id: str,
        reply_text: str,
        base_date: datetime | None = None,
        commit: bool = True,
    ) -> tuple[FollowUpTaskConfirmationCase | None, FollowUpTaskConfirmationReplyDecision]:
        case = self.confirmation_case_crud.get_by_public_id(db, case_public_id, team_id=team_id)
        decision = self.interpret_reply(reply_text, base_date=base_date)
        if case is None or case.status != FollowUpTaskConfirmationStatus.PENDING:
            return case, decision
        if self._is_expired(case, now=base_date):
            expired = self.confirmation_case_crud.mark_expired(
                db,
                case,
                expired_at=base_date,
                commit=commit,
            )
            return expired, decision
        if not decision.resolved:
            traced = self.confirmation_case_crud.record_unresolved_reply(
                db,
                case,
                reply_text=reply_text,
                actor_id=actor_id,
                replied_at=base_date,
                commit=commit,
            )
            return traced, decision

        resolved = self.confirmation_case_crud.resolve(
            db,
            case,
            resolved_action=decision.action,
            resolved_by_id=actor_id,
            resolution_text=reply_text,
            resolved_due_at=decision.proposed_due_at,
            resolved_due_at_text=decision.proposed_due_at_text,
            commit=commit,
        )
        return resolved, decision

    def _default_expires_at(self) -> datetime:
        return business_now() + timedelta(days=DEFAULT_CONFIRMATION_CASE_TTL_DAYS)

    def _is_expired(self, case: FollowUpTaskConfirmationCase, *, now: datetime | None = None) -> bool:
        return case.expires_at is not None and case.expires_at <= (now or business_now())

    def _confirmation_hash(
        self,
        *,
        team_id: int,
        task: FollowUpTask,
        plan: FollowUpTaskTransitionPlan,
        action: FollowUpTaskTransitionAction,
    ) -> str:
        raw = "|".join(
            [
                str(team_id),
                task.public_id,
                plan.decision.decision,
                action.task_public_id or "",
                action.source_activity_public_id or "",
                action.proposed_due_at or "",
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _suggested_action(
        self,
        plan: FollowUpTaskTransitionPlan,
        action: FollowUpTaskTransitionAction,
    ) -> str:
        if action.action != FollowUpTaskTransitionActionType.ASK_CONFIRMATION:
            return action.action
        if plan.decision.decision in {
            FollowUpTaskConfirmationResolutionAction.COMPLETE,
            FollowUpTaskConfirmationResolutionAction.DELAY,
            FollowUpTaskConfirmationResolutionAction.CANCEL,
            FollowUpTaskConfirmationResolutionAction.KEEP_OPEN,
        }:
            return plan.decision.decision
        return FollowUpTaskConfirmationResolutionAction.UNKNOWN

    def _question_text(
        self,
        *,
        task: FollowUpTask,
        plan: FollowUpTaskTransitionPlan,
        action: FollowUpTaskTransitionAction,
    ) -> str:
        title = task.title or "这项跟进任务"
        suggested_action = self._suggested_action(plan, action)
        if suggested_action == FollowUpTaskConfirmationResolutionAction.COMPLETE:
            return f"上次安排的「{title}」这次是否已经完成?"
        if suggested_action == FollowUpTaskConfirmationResolutionAction.DELAY:
            return f"上次安排的「{title}」是否需要延期?"
        if suggested_action == FollowUpTaskConfirmationResolutionAction.CANCEL:
            return f"上次安排的「{title}」是否不需要继续跟进?"
        return f"上次安排的「{title}」现在怎么处理?"

    def _normalize_text(self, value: str) -> str:
        return str(value or "").strip().lower().replace(" ", "")

    def _parse_due_at_text(self, value: str, *, base_date: datetime | None) -> datetime | None:
        weekday_match = re.search(r"下周([一二三四五六七日天])", value)
        if weekday_match and base_date is not None:
            weekday_map = {
                "一": 0,
                "二": 1,
                "三": 2,
                "四": 3,
                "五": 4,
                "六": 5,
                "七": 6,
                "日": 6,
                "天": 6,
            }
            target_weekday = weekday_map[weekday_match.group(1)]
            days_to_add = target_weekday - base_date.weekday() + 7
            if days_to_add <= 0:
                days_to_add += 7
            return base_date + timedelta(days=days_to_add)
        return follow_up_parser_service.parse_relative_time(value, base_date=base_date)

    def _contains_any(self, text: str, terms: tuple[str, ...]) -> bool:
        return any(term in text for term in terms)


follow_up_task_confirmation_service = FollowUpTaskConfirmationService()
