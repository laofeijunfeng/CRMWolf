"""Freeze a scored draft, then consume that exact customer-activity command."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.models.assistant import AssistantTask, AssistantWaitingType
from app.services.assistant.contracts import DraftField, TaskAuthority, TaskDraft, TaskWaiting
from app.services.assistant.task_state import TaskUpdate, apply_task_update, load_authority
from app.utils.public_id import generate_public_id

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

# ruff: noqa: RUF001

CONFIRM_PROMPT = "确认后写入这条客户活动？"


@dataclass(frozen=True)
class WriteActivityResult:
    success: bool
    activity_public_id: str | None
    error_code: str | None
    customer_id: int | None = None


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


def freeze_confirmation(
    db: Session,
    task: AssistantTask,
    *,
    customer: object,
    next_follow_time: datetime | None = None,
    next_follow_time_granularity: str = "UNKNOWN",
) -> tuple[AssistantTask, TaskWaiting]:
    from app.crud.customer_activity import customer_activity_crud
    from app.services.customer_activity_kinds import get_activity_kind_meta

    draft = TaskDraft.model_validate(task.draft_json or {})
    if draft.quality_score.status != "CANDIDATE" or not draft.score_reason:
        raise ValueError("activity cannot be confirmed without a final quality score")
    score = int(draft.quality_score.value or 0)
    if score < 60 or not draft.source_segments or not draft.content_json:
        raise ValueError("activity cannot be confirmed without a passing, complete draft")
    kind = get_activity_kind_meta(task.activity_kind or "FOLLOW_UP")["value"]
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
        "title": customer_activity_crud.build_title(kind, draft.content_json),
        "summary": customer_activity_crud.build_summary(kind, draft.content_json, source_content),
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
        "rubric_version": "customer_activity_ai.rules",
        "draft_version": task.version,
        "submission_id": generate_public_id("asub"),
    }
    command["fingerprint"] = command_fingerprint(command)
    command["execution_status"] = "PENDING"
    waiting = TaskWaiting(
        type=AssistantWaitingType.CONFIRMATION,
        field="activity_write",
        question_id=f"q_confirm_{task.public_id}_{task.version}",
        prompt=CONFIRM_PROMPT,
        fingerprint=command["fingerprint"],
        confirmation_payload={
            "kind": "activity_write",
            "preview": {
                key: command[key]
                for key in (
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
                )
            },
        },
    )
    persisted_waiting = waiting.model_dump(mode="json")
    result = apply_task_update(
        db,
        task,
        TaskUpdate(
            draft=draft,
            authority=TaskAuthority(customer_public_id=customer.public_id, frozen_activity_command=command),
            waiting=waiting,
            action_actor="SYSTEM",
            action_name="freeze_activity",
            action_result={
                "fingerprint": command["fingerprint"],
                "submission_id": command["submission_id"],
                "confirmation": persisted_waiting,
            },
            event_type="meeting_card"
            if task.activity_kind in {"ONLINE_MEETING", "OFFLINE_MEETING"}
            else "follow_up_card",
            event_key=f"card:{waiting.action_id or 'pending'}",
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


async def execute_confirmation(
    db: Session, task: AssistantTask, *, writer: ActivityWriter
) -> tuple[AssistantTask, str]:
    """Stage the canonical activity and receipt in the caller's one transaction."""
    command = load_authority(task).frozen_activity_command
    waiting = task.waiting_json.get("payload") if task.waiting_json else None
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
                {"kind": "customer_activity", "public_id": write.activity_public_id, "customer_id": write.customer_id}
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
            },
            event_type="user_choice",
            event_key=f"choice:{command['submission_id']}",
            correlation_id=str(waiting.get("action_id") or ""),
        ),
    )
    apply_task_update(
        db,
        result.task,
        TaskUpdate(
            action_actor="SYSTEM",
            action_name="show_write_receipt",
            action_result={"label": "已记录这条客户活动。", "activity_public_id": write.activity_public_id},
            event_type="receipt",
            event_key=f"receipt:{command['submission_id']}",
            correlation_id=str(waiting.get("action_id") or ""),
        ),
    )
    return result.task, "已记录这条客户活动。"
