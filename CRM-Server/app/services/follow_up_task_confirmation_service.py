"""Confirmation case management for unsafe follow-up task transitions."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol

from app.crud.sales_commitment import follow_up_task_confirmation_case_crud, follow_up_task_crud
from app.models.sales_commitment import (
    FollowUpTaskConfirmationResolutionAction,
    FollowUpTaskConfirmationStatus,
)
from app.schemas.sales_commitment import FollowUpTaskConfirmationCaseInternalCreate
from app.services.follow_up_confirmation_case_lifecycle_service import (
    FollowUpConfirmationCaseLifecycleService,
    follow_up_confirmation_case_lifecycle_service,
)
from app.services.follow_up_parser import follow_up_parser_service
from app.services.follow_up_task_confirmation_cleanup_service import FollowUpTaskConfirmationCancelReason
from app.services.follow_up_task_confirmation_questions import build_follow_up_task_confirmation_question
from app.services.follow_up_task_transition_plan_service import (
    FollowUpTaskTransitionAction,
    FollowUpTaskTransitionActionType,
    FollowUpTaskTransitionPlan,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.sales_commitment import FollowUpTask, FollowUpTaskConfirmationCase


class FollowUpTaskCrudProtocol(Protocol):
    def get_by_id_for_update(
        self,
        db: Session,
        *,
        task_id: int,
        team_id: int,
    ) -> FollowUpTask | None: ...


class FollowUpTaskConfirmationCaseCrudProtocol(Protocol):
    def get_by_public_id(
        self,
        db: Session,
        public_id: str,
        team_id: int | None = None,
    ) -> FollowUpTaskConfirmationCase | None: ...

    def get_by_public_id_for_update(
        self,
        db: Session,
        *,
        public_id: str,
        team_id: int,
    ) -> FollowUpTaskConfirmationCase | None: ...

    def create(
        self,
        db: Session,
        obj_in: FollowUpTaskConfirmationCaseInternalCreate | dict[str, object],
        *,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCase: ...

    def update(
        self,
        db: Session,
        db_obj: FollowUpTaskConfirmationCase,
        obj_in: dict[str, object],
        *,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCase: ...

    def list_pending_by_task_for_update(
        self,
        db: Session,
        *,
        team_id: int,
        task_id: int,
    ) -> list[FollowUpTaskConfirmationCase]: ...

    def list_pending_by_source_activity(
        self,
        db: Session,
        *,
        team_id: int,
        source_activity_id: int,
        skip: int = 0,
        limit: int = 500,
    ) -> tuple[list[FollowUpTaskConfirmationCase], int]: ...

    def mark_cancelled(
        self,
        db: Session,
        db_obj: FollowUpTaskConfirmationCase,
        *,
        cancelled_at: datetime | None = None,
        cancelled_by_id: str | None = None,
        cancelled_reason: str,
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
        task_crud: FollowUpTaskCrudProtocol = follow_up_task_crud,
        case_lifecycle: FollowUpConfirmationCaseLifecycleService | None = None,
    ) -> None:
        self.confirmation_case_crud = confirmation_case_crud
        self.task_crud = task_crud
        self.case_lifecycle = case_lifecycle or (
            follow_up_confirmation_case_lifecycle_service
            if confirmation_case_crud is follow_up_task_confirmation_case_crud
            else FollowUpConfirmationCaseLifecycleService(
                case_crud=confirmation_case_crud,
                action_repository=None,
            )
        )

    def create_case_from_plan_action(
        self,
        db: Session,
        *,
        team_id: int,
        task: FollowUpTask,
        plan: FollowUpTaskTransitionPlan,
        action: FollowUpTaskTransitionAction,
        actor_id: str,
        source_activity_id: int | None = None,
        source_activity_revision: int | None = None,
        source_public_id: str | None = None,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCaseResult:
        if not action.requires_confirmation:
            raise ValueError("confirmation case requires a confirmation action")

        locked_task = self.task_crud.get_by_id_for_update(
            db,
            task_id=task.id,
            team_id=team_id,
        )
        if locked_task is None:
            raise ValueError("follow-up task not found")

        confirmation_hash = self._confirmation_hash(
            team_id=team_id,
            task=locked_task,
            plan=plan,
            action=action,
            source_activity_revision=source_activity_revision,
        )
        create_payload = self._create_payload(
            team_id=team_id,
            task=locked_task,
            plan=plan,
            action=action,
            actor_id=actor_id,
            confirmation_hash=confirmation_hash,
            source_activity_id=source_activity_id,
            source_activity_revision=source_activity_revision,
            source_public_id=source_public_id,
        )
        pending_cases = self.confirmation_case_crud.list_pending_by_task_for_update(
            db,
            team_id=team_id,
            task_id=locked_task.id,
        )
        if pending_cases:
            case = next(
                (item for item in pending_cases if item.confirmation_hash == confirmation_hash),
                pending_cases[-1],
            )
            for duplicate_case in pending_cases:
                if duplicate_case.id == case.id:
                    continue
                self.case_lifecycle.cancel_locked_case(
                    db,
                    team_id=team_id,
                    case=duplicate_case,
                    cancelled_by_id=actor_id,
                    reason=FollowUpTaskConfirmationCancelReason.DUPLICATE_ACTIVE_CASE_SUPERSEDED,
                    commit=False,
                )
            case = self._maybe_upgrade_pending_case(
                db,
                case,
                incoming=create_payload.model_dump(),
                incoming_confidence=action.confidence,
                commit=False,
            )
            if commit:
                db.commit()
                db.refresh(case)
            return FollowUpTaskConfirmationCaseResult(
                case=case,
                created=False,
                confirmation_hash=case.confirmation_hash,
            )

        case = self.confirmation_case_crud.create(
            db,
            create_payload,
            commit=False,
        )
        if commit:
            db.commit()
            db.refresh(case)
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
        postpone_terms = ("下周", "明天", "后天", "天后", "日后", "周后", "再说", "再看", "再联系")
        if proposed_due_at is not None and self._contains_any(text, postpone_terms):
            return FollowUpTaskConfirmationReplyDecision(
                action=FollowUpTaskConfirmationResolutionAction.POSTPONE,
                confidence=0.88,
                reason="POSTPONE_TIME_TEXT",
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
        case = self.confirmation_case_crud.get_by_public_id_for_update(
            db,
            public_id=case_public_id,
            team_id=team_id,
        )
        decision = self.interpret_reply(reply_text, base_date=base_date)
        if case is None or case.status != FollowUpTaskConfirmationStatus.PENDING:
            return case, decision
        if self._is_expired(case, now=base_date):
            expired = self.case_lifecycle.expire_locked_case(
                db,
                team_id=team_id,
                case=case,
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

    def _create_payload(
        self,
        *,
        team_id: int,
        task: FollowUpTask,
        plan: FollowUpTaskTransitionPlan,
        action: FollowUpTaskTransitionAction,
        actor_id: str,
        confirmation_hash: str,
        source_activity_id: int | None,
        source_activity_revision: int | None,
        source_public_id: str | None,
    ) -> FollowUpTaskConfirmationCaseInternalCreate:
        return FollowUpTaskConfirmationCaseInternalCreate(
            team_id=team_id,
            task_id=task.id,
            customer_id=task.customer_id,
            owner_id=task.owner_id,
            creator_id=actor_id,
            suggested_action=self._suggested_action(plan, action),
            confirmation_hash=confirmation_hash,
            question_text=self._question_text(task=task, plan=plan, action=action),
            source_activity_id=source_activity_id,
            source_activity_revision=source_activity_revision,
            source_public_id=source_public_id or action.source_activity_public_id or task.source_public_id,
            source_plan_json={
                **plan.to_dict(),
                "confirmation_source": {
                    "source_activity_id": source_activity_id,
                    "source_activity_revision": source_activity_revision,
                    "source_public_id": source_public_id,
                    "task_source_activity_id": task.source_activity_id,
                    "task_source_public_id": task.source_public_id,
                },
            },
            expires_at=self._default_expires_at(),
        )

    def _maybe_upgrade_pending_case(
        self,
        db: Session,
        case: FollowUpTaskConfirmationCase,
        *,
        incoming: dict[str, Any],
        incoming_confidence: float,
        commit: bool,
    ) -> FollowUpTaskConfirmationCase:
        current_strength = self._case_strength(case.suggested_action)
        incoming_strength = self._case_strength(str(incoming.get("suggested_action") or ""))
        current_confidence = self._case_confidence(case)
        should_upgrade = incoming_strength > current_strength or (
            incoming_strength == current_strength and incoming_confidence > current_confidence
        )
        updates: dict[str, Any] = {}
        if should_upgrade:
            updates.update(
                {
                    "suggested_action": incoming["suggested_action"],
                    "question_text": incoming["question_text"],
                    "source_plan_json": incoming["source_plan_json"],
                }
            )

        # Rebase the still-pending Case onto the latest activity that raised the
        # same task. Agent projection can then surface the authoritative Case in
        # the new session without creating a second Case.
        if incoming.get("source_activity_id") is not None:
            updates.update(
                {
                    "source_activity_id": incoming["source_activity_id"],
                    "source_activity_revision": incoming["source_activity_revision"],
                    "source_public_id": incoming["source_public_id"],
                    "expires_at": incoming["expires_at"],
                }
            )

        if not updates:
            return case
        return self.confirmation_case_crud.update(
            db,
            case,
            updates,
            commit=commit,
        )

    @staticmethod
    def _case_strength(action: str | None) -> int:
        return {
            FollowUpTaskConfirmationResolutionAction.COMPLETE: 4,
            FollowUpTaskConfirmationResolutionAction.POSTPONE: 4,
            FollowUpTaskConfirmationResolutionAction.CANCEL: 4,
            FollowUpTaskConfirmationResolutionAction.KEEP_OPEN: 3,
            FollowUpTaskConfirmationResolutionAction.UNKNOWN: 1,
        }.get(str(action or ""), 0)

    @staticmethod
    def _case_confidence(case: FollowUpTaskConfirmationCase) -> float:
        source_plan_json = case.source_plan_json
        if not isinstance(source_plan_json, dict):
            return 0.0
        actions = source_plan_json.get("actions")
        if not isinstance(actions, list):
            return 0.0
        task_public_id = str(getattr(getattr(case, "task", None), "public_id", "") or "")
        for action in actions:
            if not isinstance(action, dict) or action.get("task_public_id") != task_public_id:
                continue
            try:
                return float(action.get("confidence") or 0.0)
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    def _is_expired(self, case: FollowUpTaskConfirmationCase, *, now: datetime | None = None) -> bool:
        return case.expires_at is not None and case.expires_at <= (now or business_now())

    def _confirmation_hash(
        self,
        *,
        team_id: int,
        task: FollowUpTask,
        plan: FollowUpTaskTransitionPlan,
        action: FollowUpTaskTransitionAction,
        source_activity_revision: int | None,
    ) -> str:
        identity_parts = [
            str(team_id),
            task.public_id,
            self._suggested_action(plan, action),
            action.task_public_id or "",
            action.source_activity_public_id or "",
            action.proposed_due_at or "",
        ]
        if source_activity_revision is not None:
            identity_parts.append(f"activity_revision:{source_activity_revision}")
        raw = "|".join(identity_parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _suggested_action(
        self,
        plan: FollowUpTaskTransitionPlan,
        action: FollowUpTaskTransitionAction,
    ) -> str:
        if action.action != FollowUpTaskTransitionActionType.ASK_CONFIRMATION:
            return action.action
        task_decision = next(
            (
                item
                for item in plan.decision.task_decisions
                if item.task_public_id == action.task_public_id
            ),
            None,
        )
        if task_decision is not None and task_decision.decision in {
            FollowUpTaskConfirmationResolutionAction.COMPLETE,
            FollowUpTaskConfirmationResolutionAction.POSTPONE,
            FollowUpTaskConfirmationResolutionAction.CANCEL,
            FollowUpTaskConfirmationResolutionAction.KEEP_OPEN,
        }:
            return task_decision.decision
        return FollowUpTaskConfirmationResolutionAction.UNKNOWN

    def _question_text(
        self,
        *,
        task: FollowUpTask,
        plan: FollowUpTaskTransitionPlan,
        action: FollowUpTaskTransitionAction,
    ) -> str:
        del plan, action
        return build_follow_up_task_confirmation_question(
            task_label=self._task_label(task),
            title=task.title or "这项跟进任务",
        )

    def _task_label(self, task: FollowUpTask) -> str:
        due_at = getattr(task, "due_at", None)
        if due_at is None:
            return "待办"
        return f"{due_at.month} 月 {due_at.day} 号待办"

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
