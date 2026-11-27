"""Freeze a scored draft, then consume that exact customer-activity command."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

from sqlalchemy.exc import SQLAlchemyError

from app.models.assistant import AssistantAction, AssistantTask, AssistantTaskStatus, AssistantWaitingType
from app.services.assistant.contracts import (
    ActivityWriteConfirmation,
    DraftField,
    TaskAuthority,
    TaskDraft,
    TaskWaiting,
)
from app.services.assistant.failure_contract import ACTIVITY_COMMIT_UNKNOWN_MESSAGE
from app.services.assistant.task_operations import activity_commit_is_unknown
from app.services.assistant.task_state import (
    TaskStateConflictError,
    TaskUpdate,
    apply_task_update,
    load_authority,
)
from app.utils.public_id import generate_public_id

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

# ruff: noqa: RUF001

CONFIRM_PROMPT = "确认后写入这条客户活动？"
RECONCILE_WRITTEN_MESSAGE = "已核对：客户活动已写入，正在继续后续整理。"
RECONCILE_NOT_WRITTEN_MESSAGE = "已核对：上次确认未写入客户活动，已恢复确认卡片，可继续确认、修改或取消。"
RECONCILE_NOOP_MESSAGE = "当前任务无需核对。"
ActivityReconcileOutcome = Literal["WRITTEN", "NOT_WRITTEN", "STILL_UNKNOWN", "NOOP"]


@dataclass(frozen=True)
class ActivityReconcileResult:
    outcome: ActivityReconcileOutcome
    task: AssistantTask
    message: str
    followup_turn_id: int | None = None
    followup_turn_public_id: str | None = None


def build_confirmation_waiting_from_command(
    task: AssistantTask,
    command: dict[str, object],
) -> TaskWaiting:
    """Build a fresh CONFIRMATION waiting envelope for an existing frozen command."""
    return TaskWaiting(
        type=AssistantWaitingType.CONFIRMATION,
        field="activity_write",
        action_id=generate_public_id("awa"),
        question_id=f"q_confirm_{task.public_id}_{task.version}",
        prompt=CONFIRM_PROMPT,
        fingerprint=str(command["fingerprint"]),
        confirmation_payload=ActivityWriteConfirmation.model_validate(
            {
                "kind": "activity_write",
                "preview": _activity_preview(command),
            }
        ),
    )
_ACTIVITY_PREVIEW_KEYS = (
    "customer_name",
    "activity_kind",
    "title",
    "summary",
    "content_json",
    "source_content",
    "score",
    "score_reason",
    "next_action",
    "next_follow_time",
    "next_follow_time_text",
    "next_follow_time_granularity",
    "channel_status",
    "channel_status_label",
    "channel_source_text",
    "channel_options",
    "ignored_noise_summary",
)


def _activity_preview(command: dict[str, object]) -> dict[str, object]:
    from app.services.assistant.follow_up_context import CONTEXT_COMMAND_KEYS

    return {key: command[key] for key in (*_ACTIVITY_PREVIEW_KEYS, *CONTEXT_COMMAND_KEYS) if key in command}


@dataclass(frozen=True)
class FollowUpProjectionReceipt:
    status: Literal["QUEUED", "COMPLETED", "SKIPPED", "FAILED", "EXHAUSTED"]
    job_public_id: str | None = None
    projection_run_id: int | None = None
    task_public_id: str | None = None
    skip_reason: str | None = None
    error_message: str | None = None


_PROJECTION_STATUS_MAP: dict[str, Literal["QUEUED", "COMPLETED", "SKIPPED", "FAILED", "EXHAUSTED"]] = {
    "QUEUED": "QUEUED",
    "RUNNING": "QUEUED",
    "COMPLETED": "COMPLETED",
    "SKIPPED": "SKIPPED",
    "FAILED": "FAILED",
    "EXHAUSTED": "EXHAUSTED",
}


def normalize_projection_status(raw: str) -> Literal["QUEUED", "COMPLETED", "SKIPPED", "FAILED", "EXHAUSTED"]:
    return _PROJECTION_STATUS_MAP.get(raw, "QUEUED")

@dataclass(frozen=True)
class WriteActivityResult:
    success: bool
    activity_public_id: str | None
    error_code: str | None
    customer_id: int | None = None
    follow_up_projection: FollowUpProjectionReceipt | None = None


class ActivityWriter(Protocol):
    async def write_activity(
        self, db: Session, *, task: AssistantTask, command: dict[str, object]
    ) -> WriteActivityResult: ...


def command_fingerprint(command: dict[str, object]) -> str:
    """Only immutable business intent participates in the signed card identity."""
    payload = {key: value for key, value in command.items() if key not in {"fingerprint", "execution_status"}}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_activity_confirmation(
    task: AssistantTask,
    *,
    draft: TaskDraft,
    customer: object,
    next_follow_time: datetime | None = None,
    next_follow_time_granularity: str = "UNKNOWN",
    context_card: dict[str, object] | None = None,
) -> tuple[dict[str, object], TaskWaiting]:
    """Build the frozen command and its signed card without touching the task row."""

    from app.crud.customer_activity import customer_activity_crud
    from app.services.assistant.activity_channel import CANONICAL_KINDS, MEETING_KINDS
    from app.services.assistant.activity_edit import edited_activity_summary
    from app.services.assistant.noise import ignored_noise_summary

    if draft.quality_score.status != "CANDIDATE" or not draft.score_reason:
        raise ValueError("activity cannot be confirmed without a final quality score")
    score = int(draft.quality_score.value or 0)
    if score < 60 or not draft.source_segments or not draft.content_json:
        raise ValueError("activity cannot be confirmed without a passing, complete draft")
    kind = draft.channel_kind if draft.channel_kind in CANONICAL_KINDS else None
    channel_status = draft.channel_status or ("recognized" if kind is not None else "required")
    if task.activity_kind in MEETING_KINDS and kind is None and draft.channel_status is None:
        kind = task.activity_kind
        channel_status = "recognized"
    if channel_status == "required":
        kind = None
    source_content = "\n".join(draft.source_segments)
    next_action = None if draft.next_action.status == "EXPLICITLY_NONE" else draft.next_action.value
    next_follow_time_text = (draft.next_follow_time.value or "").strip()
    command: dict[str, object] = {
        "team_id": task.team_id,
        "user_id": task.user_id,
        "customer_public_id": customer.public_id,
        "customer_name": customer.account_name,
        "activity_kind": kind,
        "content_json": draft.content_json,
        "source_segments": draft.source_segments,
        "source_content": source_content,
        "title": customer_activity_crud.build_title(kind, draft.content_json) if kind is not None else None,
        "summary": edited_activity_summary(draft.content_json)
        or customer_activity_crud.build_summary(kind or "OTHER_FOLLOW_UP", draft.content_json, source_content),
        "channel_status": channel_status,
        "channel_status_label": draft.channel_status_label
        or ("未识别 · 需要确认" if channel_status == "required" else None),
        "channel_source_text": draft.channel_source_text,
        "channel_options": list(draft.channel_options),
        "channel_origin_label": draft.channel_origin_label,
        "next_action": next_action,
        "next_follow_time_text": next_follow_time_text,
        "next_follow_time": next_follow_time.isoformat() if next_follow_time is not None else None,
        "next_follow_time_granularity": next_follow_time_granularity,
        "score": score,
        "score_reason": draft.score_reason,
        "score_detail": draft.score_detail,
        "model_metadata": {
            "model_name": draft.score_detail.get("model_name"),
            "structured_output": draft.score_detail.get("structured_output"),
            "structuring_model_name": draft.score_detail.get("structuring_model_name"),
        },
        "ignored_noise_summary": ignored_noise_summary(draft),
        "rubric_version": "customer_activity_ai.rules",
        "draft_version": task.version,
        "submission_id": generate_public_id("asub"),
    }
    if context_card:
        from app.services.assistant.follow_up_context import CONTEXT_COMMAND_KEYS

        for key in CONTEXT_COMMAND_KEYS:
            if key in context_card:
                command[key] = context_card[key]
    command["fingerprint"] = command_fingerprint(command)
    command["execution_status"] = "PENDING"
    waiting = build_confirmation_waiting_from_command(task, command)
    return command, waiting


def persist_activity_confirmation(
    db: Session,
    task: AssistantTask,
    *,
    draft: TaskDraft,
    command: dict[str, object],
    waiting: TaskWaiting,
    action_name: str = "freeze_activity",
    action_input: dict[str, object] | None = None,
    context_authority: dict[str, object] | None = None,
    clear_opportunity: bool = False,
) -> tuple[AssistantTask, TaskWaiting]:
    """Publish the draft, authority and signed card in a single compare-and-swap."""

    authority_payload: dict[str, object] = {
        "customer_public_id": str(command["customer_public_id"]),
        "opportunity_public_id": load_authority(task).opportunity_public_id,
        "opportunity_stage_name": load_authority(task).opportunity_stage_name,
        "frozen_activity_command": command,
    }
    if context_authority:
        authority_payload.update({key: value for key, value in context_authority.items() if value is not None})
    result = apply_task_update(
        db,
        task,
        TaskUpdate(
            draft=draft,
            authority=TaskAuthority.model_validate(authority_payload),
            clear_follow_up_opportunity=clear_opportunity,
            waiting=waiting,
            action_actor="SYSTEM",
            action_name=action_name,
            action_input=action_input or {},
            action_result={
                "fingerprint": command["fingerprint"],
                "submission_id": command["submission_id"],
                "confirmation": waiting.model_dump(mode="json"),
            },
            event_type="meeting_card"
            if task.activity_kind in {"ONLINE_MEETING", "OFFLINE_MEETING"}
            else "follow_up_card",
            event_key=f"card:{waiting.action_id}",
            correlation_id=waiting.action_id,
        ),
    )
    return result.task, TaskWaiting.model_validate(
        {
            **waiting.model_dump(),
            "action_id": result.task.waiting_json["action_id"],
            "expected_version": result.task.version,
        }
    )


def freeze_confirmation(
    db: Session,
    task: AssistantTask,
    *,
    customer: object,
    next_follow_time: datetime | None = None,
    next_follow_time_granularity: str = "UNKNOWN",
    context_card: dict[str, object] | None = None,
) -> tuple[AssistantTask, TaskWaiting]:
    draft = TaskDraft.model_validate(task.draft_json or {})
    command, waiting = build_activity_confirmation(
        task,
        draft=draft,
        customer=customer,
        next_follow_time=next_follow_time,
        next_follow_time_granularity=next_follow_time_granularity,
        context_card=context_card,
    )
    return persist_activity_confirmation(db, task, draft=draft, command=command, waiting=waiting)


def _projection_receipt_fields(projection: FollowUpProjectionReceipt | None) -> dict[str, object]:
    return {
        "follow_up_projection_status": projection.status if projection else None,
        "follow_up_projection_job_public_id": projection.job_public_id if projection else None,
        "follow_up_projection_run_id": projection.projection_run_id if projection else None,
        "follow_up_projection_task_public_id": projection.task_public_id if projection else None,
        "follow_up_projection_skip_reason": projection.skip_reason if projection else None,
        "follow_up_projection_error_message": projection.error_message if projection else None,
    }


def _confirmation_receipt_message(projection: FollowUpProjectionReceipt | None) -> str:
    if projection is None:
        return "活动已写入"
    if projection.status == "QUEUED":
        return "活动已写入，跟进任务待生成"
    if projection.status == "COMPLETED":
        return "活动已写入，跟进任务已生成" if projection.task_public_id else "活动已写入，无需生成跟进任务"
    if projection.status == "SKIPPED":
        return "活动已写入，无需生成跟进任务"
    if projection.status in {"FAILED", "EXHAUSTED"}:
        return "活动已写入，跟进任务投影失败"
    return "活动已写入"


async def execute_confirmation(
    db: Session, task: AssistantTask, *, writer: ActivityWriter
) -> tuple[AssistantTask, str]:
    """Stage the canonical activity and receipt in the caller's one transaction."""
    command = load_authority(task).frozen_activity_command
    waiting = task.waiting_json.get("payload") if task.waiting_json else None
    if isinstance(command, dict) and command.get("channel_status") == "required":
        raise ValueError("activity kind must be selected before confirmation")
    if (
        not isinstance(command, dict)
        or command.get("execution_status") != "PENDING"
        or command.get("fingerprint") != command_fingerprint(command)
        or not isinstance(waiting, dict)
        or waiting.get("fingerprint") != command["fingerprint"]
    ):
        raise ValueError("confirmation does not match the frozen activity")
    write = await writer.write_activity(db, task=task, command=command)
    if not write.success:
        result = apply_task_update(
            db,
            task,
            TaskUpdate(
                clear_waiting=True,
                error_code=write.error_code or "ACTIVITY_WRITE_FAILED",
                authority=TaskAuthority(frozen_activity_command={**command, "execution_status": "REJECTED"}),
                action_actor="SYSTEM",
                action_name="reject_activity_write",
                action_result={"accepted": False, "code": write.error_code},
            ),
        )
        return result.task, "本次确认未写入客户活动；请检查客户权限或重新整理稿件。"
    settled, receipt_message = settle_activity_confirmation_receipt(
        db,
        task,
        command=command,
        activity_public_id=str(write.activity_public_id),
        customer_id=write.customer_id,
        projection=write.follow_up_projection,
        action_actor="USER",
        action_name="confirm_write",
        action_result={
            "label": "确认",
            "activity_public_id": write.activity_public_id,
            "submission_id": command["submission_id"],
            "confirmation": waiting,
            "draft": task.draft_json or {},
            "activity_kind": task.activity_kind,
            **_projection_receipt_fields(write.follow_up_projection),
        },
        event_type="user_choice",
        event_key=f"choice:{command['submission_id']}",
        correlation_id=str(waiting.get("action_id") or ""),
        require_no_active_turn=False,
        clear_error_code=False,
    )
    return settled, receipt_message


def settle_activity_confirmation_receipt(
    db: Session,
    task: AssistantTask,
    *,
    command: dict[str, object],
    activity_public_id: str,
    customer_id: int | None,
    projection: FollowUpProjectionReceipt | None,
    action_actor: Literal["USER", "SYSTEM"],
    action_name: str,
    action_result: dict[str, object],
    event_type: str | None = None,
    event_key: str | None = None,
    correlation_id: str | None = None,
    require_no_active_turn: bool = False,
    clear_error_code: bool = False,
) -> tuple[AssistantTask, str]:
    """Persist authoritative activity receipt and show_write_receipt in caller's transaction."""
    submission_id = str(command["submission_id"])
    already_committed = any(item.get("kind") == "customer_activity" for item in task.committed_json or [])
    draft_update = None
    if not already_committed:
        current_draft = TaskDraft.model_validate(task.draft_json or {})
        draft_update = current_draft.model_copy(
            update={
                "content": DraftField(
                    status="ACCEPTED",
                    value=current_draft.content.value,
                ),
            }
        )
    committed_entries: list[dict[str, object]] | None = (
        None
        if already_committed
        else [
            {
                "kind": "customer_activity",
                "public_id": activity_public_id,
                "customer_id": customer_id,
                "customer_public_id": str(command["customer_public_id"]),
            }
        ]
    )
    result = apply_task_update(
        db,
        task,
        TaskUpdate(
            require_no_active_turn=require_no_active_turn,
            clear_waiting=True,
            clear_error_code=clear_error_code,
            draft=draft_update,
            authority=TaskAuthority(
                customer_public_id=str(command["customer_public_id"]),
                activity_public_id=activity_public_id,
                confirmation_receipt=submission_id,
                frozen_activity_command={**command, "execution_status": "SUCCEEDED"},
            ),
            append_committed=committed_entries,
            action_actor=action_actor,
            action_name=action_name,
            action_result=action_result,
            event_type=event_type,
            event_key=event_key,
            correlation_id=correlation_id,
        ),
    )
    receipt_message = _confirmation_receipt_message(projection)
    existing_receipt = (
        db.query(AssistantAction.id)
        .filter_by(
            team_id=result.task.team_id,
            task_id=result.task.id,
            event_key=f"receipt:{submission_id}",
        )
        .first()
    )
    if existing_receipt is None:
        result = apply_task_update(
            db,
            result.task,
            TaskUpdate(
                require_no_active_turn=require_no_active_turn,
                action_actor="SYSTEM",
                action_name="show_write_receipt",
                action_result={
                    "label": receipt_message,
                    "activity_public_id": activity_public_id,
                    **_projection_receipt_fields(projection),
                },
                event_type="receipt",
                event_key=f"receipt:{submission_id}",
                correlation_id=correlation_id,
            ),
        )
    return result.task, receipt_message


def revise_frozen_activity_kind(db: Session, task: AssistantTask, kind: str) -> tuple[AssistantTask, TaskWaiting]:
    """Replace only the frozen activity kind. Content, score and context stay put."""

    from app.services.assistant.activity_channel import CANONICAL_KINDS, MEETING_KINDS
    from app.services.customer_activity_kinds import get_activity_kind_meta

    command = load_authority(task).frozen_activity_command
    if not isinstance(command, dict) or command.get("execution_status") != "PENDING":
        raise ValueError("activity kind can only be revised before writing")
    options = command.get("channel_options")
    if not isinstance(options, list) or kind not in options or kind not in CANONICAL_KINDS:
        raise ValueError("activity kind is not one of the issued options")
    meta = get_activity_kind_meta(kind)
    label = str(meta["label"])
    updated = dict(command)
    previous = updated.get("channel_status")
    origin = updated.get("channel_origin_label")
    if previous == "required":
        status = "selected"
        status_label = "已选择"
        source_text = f"你选择：{label}"
    else:
        status = "revised"
        status_label = "已手动修正"
        origin_label = origin if isinstance(origin, str) and origin.strip() else "原类型"
        source_text = f"原始识别：{origin_label} · 你修改为{label}"
        if not isinstance(origin, str) or not origin.strip():
            updated["channel_origin_label"] = label
    updated["activity_kind"] = kind
    updated["channel_status"] = status
    updated["channel_status_label"] = status_label
    updated["channel_source_text"] = source_text
    if meta["category"] == "FOLLOW_UP":
        updated["title"] = label
    updated.pop("fingerprint", None)
    updated["fingerprint"] = command_fingerprint(updated)
    draft = TaskDraft.model_validate(task.draft_json or {}).model_copy(
        update={
            "channel_status": status,
            "channel_kind": kind,
            "channel_source": "user",
            "channel_status_label": status_label,
            "channel_source_text": source_text,
            "channel_origin_label": updated.get("channel_origin_label"),
        }
    )
    waiting = TaskWaiting(
        type=AssistantWaitingType.CONFIRMATION,
        field="activity_write",
        question_id=f"q_confirm_{task.public_id}_{task.version}",
        prompt=CONFIRM_PROMPT,
        fingerprint=updated["fingerprint"],
        confirmation_payload={
            "kind": "activity_write",
            "preview": _activity_preview(updated),
        },
    )
    authority = load_authority(task).model_copy(update={"frozen_activity_command": updated})
    result = apply_task_update(
        db,
        task,
        TaskUpdate(
            draft=draft,
            activity_kind=kind if kind in MEETING_KINDS else None,
            authority=authority,
            waiting=waiting,
            action_actor="USER",
            action_name="revise_activity_kind",
            action_input={"kind": kind},
            action_result={"accepted": True, "kind": kind, "fingerprint": updated["fingerprint"]},
            event_type="user_choice",
            event_key=f"kind:{updated['fingerprint'][:24]}",
            correlation_id=waiting.action_id,
        ),
    )
    return result.task, TaskWaiting.model_validate(
        {
            **waiting.model_dump(),
            "action_id": result.task.waiting_json["action_id"],
            "expected_version": result.task.version,
        }
    )


def restore_activity_confirmation(
    db: Session,
    task: AssistantTask,
    *,
    action_name: str = "cancel_activity_edit",
) -> tuple[AssistantTask, TaskWaiting]:
    """Restore an unchanged pending activity command under a fresh action id.

    Cancelling an edit never rebuilds or re-scores the draft. The frozen command,
    customer authority, source provenance, and its business ``draft_version``
    remain byte-for-byte unchanged; only the confirmation envelope is re-signed.
    """

    command = load_authority(task).frozen_activity_command
    waiting_payload = (task.waiting_json or {}).get("payload")
    if (
        task.waiting_type not in {AssistantWaitingType.CONFIRMATION_EDIT, AssistantWaitingType.CONFIRMATION}
        or task.waiting_field != "activity_write"
        or not isinstance(waiting_payload, dict)
        or not isinstance(command, dict)
        or command.get("execution_status") != "PENDING"
    ):
        raise ValueError("activity edit can only be cancelled for a pending frozen activity")
    fingerprint = command.get("fingerprint")
    if not isinstance(fingerprint, str) or fingerprint != command_fingerprint(command):
        raise ValueError("frozen activity fingerprint is invalid")
    waiting_fingerprint = waiting_payload.get("fingerprint")
    if waiting_fingerprint != fingerprint and (
        task.waiting_type == AssistantWaitingType.CONFIRMATION or waiting_fingerprint is not None
    ):
        raise ValueError("confirmation does not match the frozen activity")
    waiting = build_confirmation_waiting_from_command(task, command)
    result = apply_task_update(
        db,
        task,
        TaskUpdate(
            waiting=waiting,
            preserve_version=True,
            action_actor="USER",
            action_name=action_name,
            action_result={
                "restored": True,
                "fingerprint": fingerprint,
                "confirmation": waiting.model_dump(mode="json"),
            },
            event_type=(
                "meeting_card" if task.activity_kind in {"ONLINE_MEETING", "OFFLINE_MEETING"} else "follow_up_card"
            ),
            event_key=f"card:{waiting.action_id}",
            correlation_id=waiting.action_id,
        ),
    )
    return result.task, TaskWaiting.model_validate(
        {
            **waiting.model_dump(),
            "action_id": result.task.waiting_json["action_id"],
            "expected_version": result.task.version,
        }
    )


def _read_existing_projection_receipt(
    db: Session,
    *,
    team_id: int,
    activity_id: int,
    activity_revision: int,
) -> FollowUpProjectionReceipt | None:
    """Read existing follow-up projection job status without triggering any write."""
    from app.crud.assistant_follow_up_projection_job import assistant_follow_up_projection_job_crud
    from app.crud.sales_commitment import follow_up_task_crud
    from app.models.sales_commitment import FollowUpTaskProjectionTrigger

    try:
        job = assistant_follow_up_projection_job_crud.get_by_identity(
            db,
            team_id=team_id,
            activity_id=activity_id,
            activity_revision=activity_revision,
            trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_CREATED_DETERMINISTIC,
        )
    except SQLAlchemyError:
        return None
    if job is None:
        return None
    raw_details = job.result_json
    details: dict[str, object] = raw_details if isinstance(raw_details, dict) else {}
    task_ids: list[int] = []
    for key in ("created_task_ids", "updated_task_ids"):
        raw_ids = details.get(key)
        if isinstance(raw_ids, list):
            task_ids.extend(value for value in raw_ids if isinstance(value, int))
    try:
        public_task_ids = (
            follow_up_task_crud.list_public_ids_by_ids(db, team_id=team_id, task_ids=task_ids)
            if task_ids
            else []
        )
    except SQLAlchemyError:
        public_task_ids = []
    receipt_status = normalize_projection_status(str(job.status))
    raw_run_id = details.get("projection_run_id")
    raw_skip_reason = details.get("skip_reason")
    error_text = details.get("error")
    fallback_error = job.error_message
    return FollowUpProjectionReceipt(
        status=receipt_status,
        job_public_id=str(job.public_id),
        projection_run_id=raw_run_id if isinstance(raw_run_id, int) else None,
        task_public_id=public_task_ids[0] if public_task_ids else None,
        skip_reason=raw_skip_reason if isinstance(raw_skip_reason, str) else None,
        error_message=(
            error_text
            if isinstance(error_text, str)
            else (str(fallback_error) if fallback_error is not None else None)
        ),
    )


def _mark_unknown_activity_actions_resolved(
    db: Session,
    *,
    task: AssistantTask,
    status: Literal["RECONCILED", "RECONCILED_NOT_WRITTEN"],
    actor_type: str,
    actor_id: int | str | None,
    reason: str | None,
    activity_public_id: str | None = None,
) -> None:
    """Resolve open `activity_commit_unknown` actions for this task; tolerates historical tasks with none."""
    rows = (
        db.query(AssistantAction)
        .filter(
            AssistantAction.team_id == task.team_id,
            AssistantAction.task_id == task.id,
            AssistantAction.action == "activity_commit_unknown",
        )
        .all()
    )
    for row in rows:
        result = dict(row.result_json or {})
        if result.get("status") in {"RECONCILED", "RECONCILED_NOT_WRITTEN"}:
            continue
        result["status"] = status
        result["reconciled_by_type"] = actor_type
        if actor_id is not None:
            result["reconciled_by"] = actor_id
        if reason:
            result["reconcile_reason"] = reason
        if activity_public_id is not None:
            result["activity_public_id"] = activity_public_id
        row.result_json = result
    db.flush()


def reconcile_unknown_activity(
    db: Session,
    task: AssistantTask,
    *,
    actor_type: Literal["USER", "OPERATOR", "SYSTEM"],
    actor_id: int | str | None = None,
    reason: str | None = None,
    expected_decision: Literal["SUCCEEDED", "REJECTED"] | None = None,
) -> ActivityReconcileResult:
    """Deterministically reconcile an UNKNOWN_COMMIT_RESULT customer-activity task via read-only readback.

    The caller owns `db.commit()` and MUST call `schedule_turn(result.followup_turn_id)`
    only after committing when `result.followup_turn_id is not None`.
    """
    from app.models.customer import Customer
    from app.services.assistant.turns import create_continue_proposals_followup_turn
    from app.services.customer_activity_write_service import customer_activity_write_service

    if (
        task.status != AssistantTaskStatus.ACTIVE
        or not activity_commit_is_unknown(task)
        or task.active_turn_id is not None
    ):
        if expected_decision is not None:
            raise TaskStateConflictError("当前任务不能裁决此命令。")
        return ActivityReconcileResult(outcome="NOOP", task=task, message=RECONCILE_NOOP_MESSAGE)

    command = load_authority(task).frozen_activity_command
    if (
        not isinstance(command, dict)
        or command.get("team_id") != task.team_id
        or command.get("user_id") != task.user_id
        or not isinstance(command.get("submission_id"), str)
        or not str(command["submission_id"]).strip()
        or not isinstance(command.get("fingerprint"), str)
        or command.get("fingerprint") != command_fingerprint(command)
        or not isinstance(command.get("customer_public_id"), str)
        or not str(command["customer_public_id"]).strip()
    ):
        if expected_decision is not None:
            raise TaskStateConflictError("缺少可核对的冻结活动命令，结果仍待核对。")
        return ActivityReconcileResult(
            outcome="STILL_UNKNOWN",
            task=task,
            message=ACTIVITY_COMMIT_UNKNOWN_MESSAGE,
        )

    submission_id = str(command["submission_id"])
    expected_fingerprint = str(command["fingerprint"])
    customer_public_id = str(command["customer_public_id"])
    try:
        existing = customer_activity_write_service.activity_crud.get_by_submission_id(
            db,
            team_id=int(task.team_id),
            submission_id=submission_id,
        )
    except SQLAlchemyError as exc:
        if expected_decision is not None:
            raise TaskStateConflictError("核对查询失败，结果仍待核对。") from exc
        return ActivityReconcileResult(
            outcome="STILL_UNKNOWN",
            task=task,
            message=ACTIVITY_COMMIT_UNKNOWN_MESSAGE,
        )

    if existing is not None:
        if (
            existing.submission_source != "ASSISTANT_2"
            or existing.submission_fingerprint != expected_fingerprint
        ):
            if expected_decision is not None:
                raise TaskStateConflictError("活动记录指纹不匹配，结果仍待核对。")
            return ActivityReconcileResult(
                outcome="STILL_UNKNOWN",
                task=task,
                message=ACTIVITY_COMMIT_UNKNOWN_MESSAGE,
            )
        if existing.customer_id is None:
            if expected_decision is not None:
                raise TaskStateConflictError("活动记录归属客户缺失，结果仍待核对。")
            return ActivityReconcileResult(
                outcome="STILL_UNKNOWN",
                task=task,
                message=ACTIVITY_COMMIT_UNKNOWN_MESSAGE,
            )
        try:
            customer_row = (
                db.query(Customer.id)
                .filter(
                    Customer.team_id == task.team_id,
                    Customer.public_id == customer_public_id,
                )
                .one_or_none()
            )
        except SQLAlchemyError as exc:
            if expected_decision is not None:
                raise TaskStateConflictError("核对客户归属失败，结果仍待核对。") from exc
            return ActivityReconcileResult(
                outcome="STILL_UNKNOWN",
                task=task,
                message=ACTIVITY_COMMIT_UNKNOWN_MESSAGE,
            )
        if customer_row is None or int(existing.customer_id) != int(customer_row[0]):
            if expected_decision is not None:
                raise TaskStateConflictError("活动记录归属客户不匹配，结果仍待核对。")
            return ActivityReconcileResult(
                outcome="STILL_UNKNOWN",
                task=task,
                message=ACTIVITY_COMMIT_UNKNOWN_MESSAGE,
            )
        if expected_decision == "REJECTED":
            raise TaskStateConflictError("目标系统已存在该客户活动记录，不能裁决为未写入。")

        projection = _read_existing_projection_receipt(
            db,
            team_id=int(task.team_id),
            activity_id=int(existing.id),
            activity_revision=int(existing.activity_revision or 1),
        )
        try:
            settled, _ = settle_activity_confirmation_receipt(
                db,
                task,
                command=command,
                activity_public_id=str(existing.id),
                customer_id=int(existing.customer_id) if existing.customer_id is not None else None,
                projection=projection,
                action_actor="SYSTEM",
                action_name="reconcile_activity_commit",
                action_result={
                    "outcome": "WRITTEN",
                    "activity_public_id": str(existing.id),
                    "submission_id": submission_id,
                    "actor_type": actor_type,
                    "actor_id": actor_id,
                    "reason": reason,
                    **_projection_receipt_fields(projection),
                },
                require_no_active_turn=True,
                clear_error_code=True,
            )
        except TaskStateConflictError:
            if expected_decision is not None:
                raise
            db.refresh(task)
            if not activity_commit_is_unknown(task):
                return ActivityReconcileResult(outcome="NOOP", task=task, message=RECONCILE_NOOP_MESSAGE)
            raise
        _mark_unknown_activity_actions_resolved(
            db,
            task=settled,
            status="RECONCILED",
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            activity_public_id=str(existing.id),
        )
        followup = create_continue_proposals_followup_turn(db, settled)
        db.refresh(settled)
        from app.crud.assistant_conversation import owned_conversation
        from app.models.assistant_conversation import AssistantConversationEntry
        from app.services.assistant.presentation import task_view
        from app.services.assistant.turns import fingerprint as conversation_fingerprint

        conversation = owned_conversation(db, team_id=int(settled.team_id), user_id=int(settled.user_id))
        if conversation is not None:
            reconcile_command: dict[str, object] = {
                "operation": "reconcile_activity",
                "waiting_field": "activity_write",
                "submission_id": submission_id,
                "activity_public_id": str(existing.id),
                "actor_type": actor_type,
            }
            db.add(
                AssistantConversationEntry(
                    conversation_id=conversation.id,
                    team_id=settled.team_id,
                    user_id=settled.user_id,
                    client_request_id=f"reconcile-{settled.public_id}-{followup.public_id}",
                    input_fingerprint=conversation_fingerprint(reconcile_command),
                    user_text="",
                    command_json=reconcile_command,
                    decision_json={},
                    state="READY",
                    task_public_id=settled.public_id,
                    turn_public_id=followup.public_id,
                    reply_text=RECONCILE_WRITTEN_MESSAGE,
                    task_snapshot_json=task_view(settled, db).model_dump(mode="json"),
                )
            )
            db.flush()
        return ActivityReconcileResult(
            outcome="WRITTEN",
            task=settled,
            message=RECONCILE_WRITTEN_MESSAGE,
            followup_turn_id=followup.id,
            followup_turn_public_id=followup.public_id,
        )

    if expected_decision == "SUCCEEDED":
        raise TaskStateConflictError("未查到该客户活动写入记录，不能裁决为已写入。")

    restored_command = {**command, "execution_status": "PENDING"}
    rebuilt_waiting = build_confirmation_waiting_from_command(task, restored_command)
    try:
        updated = apply_task_update(
            db,
            task,
            TaskUpdate(
                require_no_active_turn=True,
                clear_error_code=True,
                waiting=rebuilt_waiting,
                authority=TaskAuthority(frozen_activity_command=restored_command),
                action_actor="SYSTEM",
                action_name="reconcile_activity_commit",
                action_result={
                    "outcome": "NOT_WRITTEN",
                    "submission_id": submission_id,
                    "fingerprint": expected_fingerprint,
                    "actor_type": actor_type,
                    "actor_id": actor_id,
                    "reason": reason,
                    "confirmation": rebuilt_waiting.model_dump(mode="json"),
                },
                event_type=(
                    "meeting_card"
                    if task.activity_kind in {"ONLINE_MEETING", "OFFLINE_MEETING"}
                    else "follow_up_card"
                ),
                event_key=f"card:{rebuilt_waiting.action_id}",
                correlation_id=rebuilt_waiting.action_id,
            ),
        ).task
    except TaskStateConflictError:
        if expected_decision is not None:
            raise
        db.refresh(task)
        if not activity_commit_is_unknown(task):
            return ActivityReconcileResult(outcome="NOOP", task=task, message=RECONCILE_NOOP_MESSAGE)
        raise
    _mark_unknown_activity_actions_resolved(
        db,
        task=updated,
        status="RECONCILED_NOT_WRITTEN",
        actor_type=actor_type,
        actor_id=actor_id,
        reason=reason,
    )
    return ActivityReconcileResult(
        outcome="NOT_WRITTEN",
        task=updated,
        message=RECONCILE_NOT_WRITTEN_MESSAGE,
    )
