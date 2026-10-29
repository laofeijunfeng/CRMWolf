"""Server-owned disposition of open follow-up tasks after a follow-up write.

The model does not nominate relevance or choose a task action. The task row
holds the frozen batch; the card is only a projection.
"""
# ruff: noqa: RUF001

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING

from sqlalchemy import or_, true
from sqlalchemy.exc import SQLAlchemyError

from app.models.assistant import AssistantTask, AssistantWaitingType
from app.models.sales_commitment import FollowUpTask, FollowUpTaskStatus
from app.services.assistant.activity_channel import FOLLOW_UP_KINDS
from app.services.assistant.contracts import TaskWaiting
from app.services.assistant.crm_proposal_commands import source_activity
from app.services.assistant.task_state import TaskUpdate, apply_task_update, load_authority

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session


MAX_CANDIDATES = 100
GENERIC_FRAGMENTS = frozenset({
    "跟进客户",
    "联系客户",
    "客户跟进",
    "跟进一下",
    "继续跟进",
    "客户沟通",
})

@dataclass(frozen=True)
class DispositionOutcome:
    task: AssistantTask
    message: str
    start_followup: bool


def public_disposition(task: AssistantTask) -> dict[str, object] | None:
    """Read-only card payload. Server fields such as owner ids stay in authority."""

    batch = _batch(task)
    if batch is None:
        return None
    items = batch.get("items")
    if not isinstance(items, list):
        return None
    current = next((item for item in items if isinstance(item, dict) and item.get("disposition") is None), None)
    projected: list[dict[str, object]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        disposition = item.get("disposition")
        if disposition is None and item is current:
            state = "current"
        elif disposition is None:
            state = "waiting"
        else:
            state = str(disposition)
        projected.append({
            "item_id": item.get("item_id"),
            "title": item.get("title"),
            "owner_line": item.get("owner_line"),
            "related": bool(item.get("related")),
            "evidence_quote": item.get("evidence_quote"),
            "evidence_reason": item.get("evidence_reason"),
            "state": state,
            "result_title": item.get("result_title"),
            "result_message": item.get("result_message"),
        })
    current_index = None
    if isinstance(current, dict):
        current_index = next(
            index for index, item in enumerate(projected, start=1) if item["item_id"] == current.get("item_id")
        )
    return {
        "status": batch.get("status"),
        "customer_name": batch.get("customer_name") or "",
        "activity_kind_label": batch.get("activity_kind_label") or "",
        "total": len(projected),
        "current_index": current_index,
        "items": projected,
    }


def relate_title(title: str, source: str) -> tuple[str, str, str] | None:
    """Return phrase, exact source quote, and reason when the title is explicitly in the source."""

    cleaned = title.strip()
    if len(cleaned) < 4 or not source:
        return None
    for length in range(len(cleaned), 3, -1):
        for start in range(0, len(cleaned) - length + 1):
            phrase = cleaned[start:start + length]
            if phrase in GENERIC_FRAGMENTS or phrase not in source:
                continue
            quote = _quote(source, phrase)
            if phrase not in quote or quote not in source:
                continue
            reason = f"本次跟进与任务均明确提到“{phrase}”，且属于同一客户。"
            return phrase, quote, reason
    return None


async def advance_open_follow_up(db: Session, task: AssistantTask) -> DispositionOutcome | None:
    """Offer the frozen batch, or return None so the existing proposal chain continues."""

    batch = _batch(task)
    if batch is not None and batch.get("status") in {"DONE", "OVERFLOW", "QUERY_FAILED"}:
        return None
    if batch is not None and batch.get("status") == "ACTIVE":
        return _restore(db, task, batch)
    activity = source_activity(db, task)
    if activity is None or activity.activity_kind not in FOLLOW_UP_KINDS:
        return None
    try:
        built = _build_batch(db, task, activity)
    except (PermissionError, SQLAlchemyError):
        return _record_terminal(
            db,
            task,
            {
                "status": "QUERY_FAILED",
                "activity_id": activity.id,
                "customer_name": "",
                "activity_kind_label": "",
                "items": [],
            },
            "历史任务暂时无法核对，本次没有改动这些任务。已写入的跟进仍然保留。",
            start_followup=False,
        )
    if built is None:
        return _record_terminal(
            db,
            task,
            {
                "status": "OVERFLOW",
                "activity_id": activity.id,
                "activity_revision": activity.activity_revision,
                "source_sha256": _source_hash(activity.source_content or ""),
                "customer_name": _customer_name(db, task, activity.customer_id),
                "activity_kind_label": _kind_label(activity.activity_kind),
                "items": [],
            },
            "未完成的历史任务超过 100 条，无法安全逐条展示，本次没有列出部分清单。已写入的跟进仍然保留。",
            start_followup=True,
        )
    if not built["items"]:
        built["status"] = "DONE"
        _save_batch(db, task, built, waiting=None, action_name="skip_open_follow_up_batch")
        return None
    waiting = _waiting_for(task, built)
    result = _save_batch(db, task, built, waiting=waiting, action_name="offer_open_follow_up_batch")
    return DispositionOutcome(result, waiting.prompt, False)


async def settle_open_follow_up(db: Session, task: AssistantTask, choice: str) -> DispositionOutcome:
    batch = _batch(task)
    if batch is None or batch.get("status") != "ACTIVE":
        raise ValueError("没有可处理的历史跟进任务")
    items = [item for item in batch.get("items", []) if isinstance(item, dict)]
    current = next((item for item in items if item.get("disposition") is None), None)
    if current is None:
        raise ValueError("历史跟进任务已经处理完")
    item_id, action = _split_choice(choice)
    if item_id != current.get("item_id") or action not in {"complete", "hold", "skip"}:
        raise ValueError("请选择当前这一条历史任务的处理")
    failure = _revalidate(db, task, batch, current)
    if failure is not None:
        _observe(current, "failed", failure[0], failure[1])
    elif action == "complete":
        _apply_complete(db, task, batch, current)
    elif action == "hold":
        _observe(current, "hold", "先放着", "任务保持未完成，日期不变。本轮继续处理下一条。")
    else:
        _observe(current, "skip", "本次已跳过", "你选择了“不管了”。任务保持未完成，未来仍可能提示，不记录为无关。")
    batch["items"] = items
    receipts = _receipt_for(current)
    pending = next((item for item in items if item.get("disposition") is None), None)
    if pending is not None:
        waiting = _waiting_for(task, batch)
        result = _save_batch(
            db,
            task,
            batch,
            waiting=waiting,
            action_name=f"settle_open_follow_up_{action}",
            action_input={"choice": choice, "item_id": item_id},
            append_committed=receipts,
        )
        return DispositionOutcome(result, str(current.get("result_message") or waiting.prompt), False)
    batch["status"] = "DONE"
    message = _summary(items)
    result = _save_batch(
        db,
        task,
        batch,
        waiting=None,
        action_name=f"settle_open_follow_up_{action}",
        action_input={"choice": choice, "item_id": item_id},
        append_committed=receipts,
    )
    return DispositionOutcome(result, message, True)


def _apply_complete(db: Session, task: AssistantTask, batch: dict[str, object], item: dict[str, object]) -> None:
    failure = _revalidate(db, task, batch, item)
    if failure is not None:
        title, message = failure
        _observe(item, "failed", title, message)
        return
    from app.services.follow_up_task_reconciliation_evaluation_service import (
        FollowUpTaskReconciliationDecision,
        FollowUpTaskReconciliationTaskDecision,
    )
    from app.services.follow_up_task_transition_execution_service import (
        FollowUpTaskTransitionExecutionStatus,
        follow_up_task_transition_execution_service,
    )
    from app.services.follow_up_task_transition_plan_service import (
        FollowUpTaskTransitionAction,
        FollowUpTaskTransitionPlan,
    )

    target = str(item["task_public_id"])
    action = FollowUpTaskTransitionAction(
        action="COMPLETE",
        task_public_id=target,
        confidence=1.0,
        executable=True,
        requires_confirmation=False,
        reason="assistant_open_follow_up_disposition",
        evidence_terms=(str(item.get("evidence_quote") or item.get("title") or ""),),
        source_activity_public_id=str(batch.get("activity_id") or ""),
    )
    plan = FollowUpTaskTransitionPlan(
        decision=FollowUpTaskReconciliationDecision(
            candidate_public_ids=(target,),
            task_decisions=(FollowUpTaskReconciliationTaskDecision(
                decision="COMPLETE", confidence=1.0, task_public_id=target,
            ),),
        ),
        actions=(action,),
        plan_source="assistant_open_follow_up_disposition",
    )
    result = follow_up_task_transition_execution_service.execute_action(
        db,
        team_id=task.team_id,
        action=action,
        plan=plan,
        actor_id=str(task.user_id),
        expected_owner_id=str(item.get("owner_id") or ""),
        commit=False,
    )
    row = _task_row(db, task, target)
    if (
        result.status == FollowUpTaskTransitionExecutionStatus.EXECUTED
        and row is not None
        and row.status == FollowUpTaskStatus.COMPLETED
    ):
        _observe(item, "complete", "已完成", "任务已标记完成，不再重复提交。")
        return
    if result.status == FollowUpTaskTransitionExecutionStatus.EXECUTED or row is None:
        _observe(
            item,
            "unknown",
            "结果待核对",
            "如果提交后无法确认结果，只显示“结果待核对”，不再次提供“已完成”按钮，避免重复执行。",
        )
        return
    if result.skip_reason == "TASK_NOT_OPEN":
        _observe(item, "failed", "任务已由其他流程处理", "最新状态已不是未完成。本次未重复执行，请以任务最新状态为准。")
        return
    _observe(item, "failed", "任务更新失败", "任务服务未接受本次更新，任务未完成。已写入的跟进与其他成功结果保持不变。")


def _revalidate(
    db: Session, task: AssistantTask, batch: dict[str, object], item: dict[str, object],
) -> tuple[str, str] | None:
    activity = source_activity(db, task)
    if (
        activity is None
        or activity.id != batch.get("activity_id")
        or activity.activity_revision != batch.get("activity_revision")
        or _source_hash(activity.source_content or "") != batch.get("source_sha256")
    ):
        return ("关联依据已失效", "原关联徽标已撤下，本次未修改任务。失效依据不能继续授权本次动作。")
    fresh = relate_title(str(item.get("title") or ""), activity.source_content or "")
    related_now = fresh is not None
    if related_now != bool(item.get("related")):
        return ("关联依据已失效", "原关联徽标已撤下，本次未修改任务。失效依据不能继续授权本次动作。")
    if related_now and fresh is not None and fresh[1] != item.get("evidence_quote"):
        return ("关联依据已失效", "原关联徽标已撤下，本次未修改任务。失效依据不能继续授权本次动作。")
    row = _task_row(db, task, str(item.get("task_public_id") or ""))
    if row is None or row.customer_id != activity.customer_id:
        return ("任务已由其他流程处理", "最新状态已不是未完成。本次未重复执行，请以任务最新状态为准。")
    if not _can_operate(db, task, row):
        return ("你已没有此任务的操作权限", "本次未修改任务。其他可操作任务不受影响，不尝试绕过权限。")
    if row.status != FollowUpTaskStatus.OPEN or _stamp(row.updated_time) != item.get("updated_time"):
        return ("任务已由其他流程处理", "最新状态已不是未完成。本次未重复执行，请以任务最新状态为准。")
    if row.owner_id != item.get("owner_id"):
        return ("任务已由其他流程处理", "最新状态已不是未完成。本次未重复执行，请以任务最新状态为准。")
    return None


def _build_batch(db: Session, task: AssistantTask, activity: object) -> dict[str, object] | None:
    codes = _permission_codes(db, task)
    privileged = bool(codes.intersection({"follow_up_task:operate:all", "follow_up_task:edit:all"}))
    operable_filter = true() if privileged else FollowUpTask.owner_id == str(task.user_id)
    rows = (
        db.query(FollowUpTask)
        .filter(
            FollowUpTask.team_id == task.team_id,
            FollowUpTask.customer_id == activity.customer_id,
            FollowUpTask.status == FollowUpTaskStatus.OPEN,
            or_(FollowUpTask.source_activity_id.is_(None), FollowUpTask.source_activity_id != activity.id),
            operable_filter,
        )
        .order_by(FollowUpTask.due_at.asc(), FollowUpTask.id.asc())
        .limit(MAX_CANDIDATES + 1)
        .all()
    )
    operable = [row for row in rows if _can_operate(db, task, row, codes)]
    if len(rows) > MAX_CANDIDATES or len(operable) > MAX_CANDIDATES:
        return None
    source = activity.source_content or ""
    items: list[dict[str, object]] = []
    for index, row in enumerate(operable, start=1):
        related = relate_title(row.title or "", source)
        items.append({
            "item_id": f"i{index}",
            "task_public_id": row.public_id,
            "title": row.title,
            "owner_id": row.owner_id,
            "owner_line": _owner_line(db, task, row),
            "updated_time": _stamp(row.updated_time),
            "related": related is not None,
            "evidence_phrase": related[0] if related else None,
            "evidence_quote": related[1] if related else None,
            "evidence_reason": related[2] if related else None,
            "disposition": None,
            "result_title": None,
            "result_message": None,
            "idempotency_key": f"follow_up_disposition:{task.public_id}:i{index}:complete",
        })
    return {
        "status": "ACTIVE",
        "activity_id": activity.id,
        "activity_revision": activity.activity_revision,
        "source_sha256": _source_hash(source),
        "customer_name": _customer_name(db, task, activity.customer_id),
        "activity_kind_label": _kind_label(activity.activity_kind),
        "items": items,
    }


def _restore(db: Session, task: AssistantTask, batch: dict[str, object]) -> DispositionOutcome:
    waiting = _waiting_for(task, batch)
    result = _save_batch(db, task, batch, waiting=waiting, action_name="restore_open_follow_up_batch")
    return DispositionOutcome(result, waiting.prompt, False)


def _record_terminal(
    db: Session,
    task: AssistantTask,
    batch: dict[str, object],
    message: str,
    *,
    start_followup: bool,
) -> DispositionOutcome:
    result = _save_batch(db, task, batch, waiting=None, action_name="close_open_follow_up_batch")
    return DispositionOutcome(result, message, start_followup)


def _save_batch(
    db: Session,
    task: AssistantTask,
    batch: dict[str, object],
    *,
    waiting: TaskWaiting | None,
    action_name: str,
    action_input: dict[str, object] | None = None,
    append_committed: list[dict[str, object]] | None = None,
) -> AssistantTask:
    authority = load_authority(task).model_copy(update={"open_follow_up_batch": batch})
    result = apply_task_update(
        db,
        task,
        TaskUpdate(
            authority=authority,
            waiting=waiting,
            clear_waiting=waiting is None,
            append_committed=append_committed,
            action_actor="SYSTEM" if action_name.startswith(("offer", "restore", "skip", "close")) else "USER",
            action_name=action_name,
            action_input=action_input or {"status": batch.get("status"), "count": len(batch.get("items") or [])},
            action_result={"status": batch.get("status")},
        ),
    )
    return result.task


def _waiting_for(task: AssistantTask, batch: dict[str, object]) -> TaskWaiting:
    items = [item for item in batch.get("items", []) if isinstance(item, dict)]
    current = next(item for item in items if item.get("disposition") is None)
    item_id = str(current["item_id"])
    total = len(items)
    prompt = f"还发现 {total} 条未完成的历史任务，请逐条处理。"
    return TaskWaiting(
        type=AssistantWaitingType.FOLLOW_UP_DISPOSITION,
        field="follow_up_disposition",
        question_id=f"q_fut_{task.public_id}_{item_id}",
        prompt=prompt,
        candidates=[
            {"id": f"{item_id}:complete", "label": "已完成"},
            {"id": f"{item_id}:hold", "label": "先放着"},
            {"id": f"{item_id}:skip", "label": "不管了"},
        ],
    )


def _batch(task: AssistantTask) -> dict[str, object] | None:
    raw = (task.authority_json or {}).get("open_follow_up_batch")
    if not isinstance(raw, dict):
        return None
    return raw


def _permission_codes(db: Session, task: AssistantTask) -> set[str]:
    from app.services.assistant.crm_proposal_commands import _permissions

    return _permissions(db, task)


def _can_operate(db: Session, task: AssistantTask, row: FollowUpTask, codes: set[str] | None = None) -> bool:
    if row.owner_id == str(task.user_id):
        return True
    granted = codes if codes is not None else _permission_codes(db, task)
    return bool(granted.intersection({"follow_up_task:operate:all", "follow_up_task:edit:all"}))


def _task_row(db: Session, task: AssistantTask, public_id: str) -> FollowUpTask | None:
    if not public_id:
        return None
    return (
        db.query(FollowUpTask)
        .filter(FollowUpTask.team_id == task.team_id, FollowUpTask.public_id == public_id)
        .one_or_none()
    )


def _customer_name(db: Session, task: AssistantTask, customer_id: int | None) -> str:
    if customer_id is None:
        return ""
    from app.models.customer import Customer

    try:
        customer = (
            db.query(Customer)
            .filter(Customer.id == customer_id, Customer.team_id == task.team_id)
            .one_or_none()
        )
    except SQLAlchemyError:
        return ""
    return customer.account_name if customer is not None and customer.account_name else ""


def _kind_label(kind: str) -> str:
    from app.services.customer_activity_kinds import get_activity_kind_meta

    meta = get_activity_kind_meta(kind)
    label = meta.get("label") if isinstance(meta, dict) else ""
    return str(label or "")


def _owner_line(db: Session, task: AssistantTask, row: FollowUpTask) -> str:
    due = f"计划 {row.due_at.month} 月 {row.due_at.day} 日" if row.due_at is not None else ""
    if row.owner_id == str(task.user_id):
        who = "负责人：我"
    else:
        who = _other_owner(db, row.owner_id)
        if not who:
            return due
    return f"{who} · {due}" if due else who


def _other_owner(db: Session, owner_id: str) -> str:
    try:
        user_id = int(owner_id)
    except (TypeError, ValueError):
        return ""
    from app.models.user import User

    try:
        user = db.query(User).filter(User.id == user_id).one_or_none()
    except SQLAlchemyError:
        return ""
    if user is None or not getattr(user, "name", None):
        return ""
    return f"负责人：{user.name}"


def _observe(item: dict[str, object], disposition: str, title: str, message: str) -> None:
    item["disposition"] = disposition
    item["result_title"] = title
    item["result_message"] = message
    if disposition == "failed":
        item["related"] = False if title == "关联依据已失效" else item.get("related")


def _summary(items: list[dict[str, object]]) -> str:
    counts = {name: sum(item.get("disposition") == name for item in items) for name in ("complete", "hold", "skip")}
    failed = sum(item.get("disposition") in {"failed", "unknown"} for item in items)
    text = (
        f"本轮历史任务已逐条处理。{counts['complete']} 条已完成，{counts['hold']} 条先放着，"
        f"{counts['skip']} 条本次跳过。未完成的任务保持原状；本次跟进已成功保留。"
    )
    if failed:
        text += f"另有 {failed} 条未能处理。"
    return text


def _receipt_for(item: dict[str, object]) -> list[dict[str, object]] | None:
    if item.get("disposition") != "complete" or not item.get("task_public_id") or not item.get("idempotency_key"):
        return None
    return [{
        "kind": "follow_up_task",
        "public_id": item["task_public_id"],
        "proposal_key": item["idempotency_key"],
    }]


def _split_choice(choice: str) -> tuple[str, str]:
    item_id, separator, action = choice.partition(":")
    if not separator:
        return "", ""
    return item_id, action


def _source_hash(source: str) -> str:
    return sha256(source.encode()).hexdigest()


def _quote(source: str, phrase: str) -> str:
    index = source.find(phrase)
    if index < 0:
        return phrase
    boundaries = [source.rfind(mark, 0, index) for mark in "。！？\n"]
    boundary = max(boundaries)
    start = 0 if boundary < 0 else boundary + 1
    endings = [source.find(mark, index + len(phrase)) for mark in "。！？\n"]
    endings = [found for found in endings if found >= 0]
    end = min(endings) + 1 if endings else len(source)
    quote = source[start:end].strip()
    if phrase in quote and quote in source and len(quote) <= 80:
        return quote
    if len(phrase) > 80 and phrase in source:
        return phrase
    left = max(0, index - 20)
    right = min(len(source), index + len(phrase) + 20)
    window = source[left:right].strip()
    if phrase in window and window in source:
        return window[:80] if len(window) > 80 and phrase in window[:80] else window
    return phrase


def _stamp(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.replace(microsecond=0).isoformat()
