"""Freeze a scored draft, then consume that exact customer-activity command."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

from app.models.assistant import AssistantTask, AssistantWaitingType
from app.services.assistant.contracts import (
    ActivityWriteConfirmation,
    DraftField,
    TaskAuthority,
    TaskDraft,
    TaskWaiting,
)
from app.services.assistant.task_state import TaskUpdate, apply_task_update, load_authority
from app.utils.public_id import generate_public_id

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

# ruff: noqa: RUF001

CONFIRM_PROMPT = "确认后写入这条客户活动？"
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
    waiting = TaskWaiting(
        type=AssistantWaitingType.CONFIRMATION,
        field="activity_write",
        action_id=generate_public_id("awa"),
        question_id=f"q_confirm_{task.public_id}_{task.version}",
        prompt=CONFIRM_PROMPT,
        fingerprint=command["fingerprint"],
        confirmation_payload={
            "kind": "activity_write",
            "preview": _activity_preview(command),
        },
    )
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
    result = apply_task_update(
        db,
        task,
        TaskUpdate(
            clear_waiting=True,
            draft=TaskDraft.model_validate(task.draft_json or {}).model_copy(
                update={
                    "content": DraftField(
                        status="ACCEPTED", value=TaskDraft.model_validate(task.draft_json or {}).content.value
                    ),
                }
            ),
            authority=TaskAuthority(
                customer_public_id=str(command["customer_public_id"]),
                activity_public_id=write.activity_public_id,
                confirmation_receipt=str(command["submission_id"]),
                frozen_activity_command={**command, "execution_status": "SUCCEEDED"},
            ),
            append_committed=[
                {"kind": "customer_activity", "public_id": write.activity_public_id,
                 "customer_id": write.customer_id, "customer_public_id": str(command["customer_public_id"])}
            ],
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
        ),
    )
    receipt_message = _confirmation_receipt_message(write.follow_up_projection)
    apply_task_update(
        db,
        result.task,
        TaskUpdate(
            action_actor="SYSTEM",
            action_name="show_write_receipt",
            action_result={
                "label": receipt_message,
                "activity_public_id": write.activity_public_id,
                **_projection_receipt_fields(write.follow_up_projection),
            },
            event_type="receipt",
            event_key=f"receipt:{command['submission_id']}",
            correlation_id=str(waiting.get("action_id") or ""),
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
    waiting = TaskWaiting(
        type="CONFIRMATION",
        field="activity_write",
        action_id=generate_public_id("awa"),
        question_id=f"q_confirm_{task.public_id}_{task.version}",
        prompt=CONFIRM_PROMPT,
        fingerprint=fingerprint,
        confirmation_payload=ActivityWriteConfirmation.model_validate({
            "kind": "activity_write",
            "preview": _activity_preview(command),
        }),
    )
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
