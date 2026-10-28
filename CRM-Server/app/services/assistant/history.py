"""Human-readable projection of immutable assistant action evidence."""
# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import ValidationError

from app.schemas.assistant import AssistantTaskView
from app.schemas.assistant_conversation import ConversationMessage
from app.services.assistant.contracts import TaskDraft, TaskWaiting

if TYPE_CHECKING:
    from app.models.assistant import AssistantAction, AssistantTask
    from app.schemas.assistant import SubmitInputRequest

KIND_LABELS = {"FOLLOW_UP": "普通跟进", "ONLINE_MEETING": "线上会议", "OFFLINE_MEETING": "线下会议"}
FIELD_LABELS = {
    "customer": "客户名称",
    "content": "沟通内容",
    "next_action": "下一步行动",
    "next_follow_time": "下次跟进时间",
    "meeting_subject": "会议主题",
    "participants": "参会人",
}


def command_label(payload: SubmitInputRequest, waiting: TaskWaiting | None) -> str:
    if payload.kind == "cancel":
        return "算了，不记了"
    if payload.kind == "confirm":
        return "确认" if payload.choice == "confirm" else "取消"
    if waiting and waiting.type == "OBJECT_SELECTION":
        for candidate in waiting.candidates:
            if candidate.get("id") == payload.choice and isinstance(candidate.get("account_name"), str):
                return str(candidate["account_name"])
        return "选择客户"
    if waiting and waiting.type == "ACTIVITY_KIND":
        return KIND_LABELS.get(payload.choice or "", "选择活动类型")
    if waiting and waiting.field == "temporal_choice":
        for candidate in waiting.candidates:
            label = candidate.get("label")
            if candidate.get("id") == payload.choice and isinstance(label, str) and label.strip():
                return label
        if isinstance(payload.text, str) and payload.text.strip():
            return payload.text.strip()
        return "选择"
    if payload.choice == "EXPLICITLY_NONE":
        return payload.text or "暂无下一步行动"
    return payload.text or "选择"


def legacy_messages(task: AssistantTask, actions: list[AssistantAction], prefix: str) -> list[ConversationMessage]:
    result: list[ConversationMessage] = []
    for action in actions:
        data = action.result_json
        text = data.get("prompt")
        role: Literal['user', 'assistant'] = "assistant"
        frozen = None
        if action.event_type in {"follow_up_card", "meeting_card"}:
            try:
                waiting = TaskWaiting.model_validate(data.get("confirmation"))
                if waiting.confirmation_payload is None:
                    raise ValueError("missing frozen confirmation")
                # Do not turn the mutable current draft into a historical confirmation.
                frozen = AssistantTaskView(
                    public_id=task.public_id,
                    status="ACTIVE",
                    goal=task.goal,
                    activity_kind=task.activity_kind,
                    draft=TaskDraft(),
                    waiting=waiting,
                    committed=[],
                    budget_steps=0,
                    budget_max_steps=task.budget_max_steps,
                    version=0,
                )
                text = waiting.prompt
            except (ValidationError, ValueError):
                text = "这条历史结果暂时无法显示，原记录仍保留。"
        elif action.event_type == "receipt" and isinstance(data.get("activity_public_id"), str):
            text = data.get("label")
        elif action.actor == "USER":
            role = "user"
            text = action.input_json.get("text") or data.get("label")
            if action.action in {"change_kind", "select_activity_kind"}:
                text = KIND_LABELS.get(str(action.input_json.get("kind")), "选择活动类型")
            elif action.action == "submit_field" and isinstance(text, str):
                label = FIELD_LABELS.get(str(action.input_json.get("field")), "补充内容")
                text = f"{label}：{text}"
            elif action.action == "select_customer":
                # The old audit did not store a customer label; never expose an opaque ID.
                text = "已选择客户"
        if isinstance(text, str) and text:
            result.append(
                ConversationMessage(
                    id=f"{prefix}:legacy:{action.public_id}",
                    role=role,
                    text=text,
                    at=action.created_time.isoformat(),
                    task=frozen,
                    outcome="activity_written"
                    if action.event_type == "receipt" and data.get("activity_public_id")
                    else None,
                )
            )
    return result
