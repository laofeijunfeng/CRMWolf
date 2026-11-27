"""Human-readable projection of immutable assistant action evidence."""
# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import ValidationError

from app.schemas.assistant import AssistantTaskView
from app.schemas.assistant_conversation import ConversationMessage, ConversationProjection
from app.services.assistant.contracts import TaskDraft, TaskWaiting

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.models.assistant import AssistantAction, AssistantTask
    from app.schemas.assistant import SubmitInputRequest
    from app.services.assistant.contracts import ProfileProposalItem

KIND_LABELS = {
    "FOLLOW_UP": "普通跟进",
    "PHONE_FOLLOW_UP": "电话跟进",
    "WECHAT_FOLLOW_UP": "微信跟进",
    "EMAIL_FOLLOW_UP": "邮件跟进",
    "VISIT_FOLLOW_UP": "拜访跟进",
    "OTHER_FOLLOW_UP": "其他跟进",
    "ONLINE_MEETING": "线上会议",
    "OFFLINE_MEETING": "线下会议",
}
FIELD_LABELS = {
    "customer": "客户名称",
    "content": "沟通内容",
    "next_action": "下一步行动",
    "next_follow_time": "下次跟进时间",
    "meeting_subject": "会议主题",
    "participants": "参会人",
}
REJECT_REASON_LABELS = {
    "wrong_customer": "客户不对",
    "wrong_content": "内容不对",
    "should_not_record": "不该记录",
    "other": "其他",
}


def _candidate_label(waiting: TaskWaiting | None, choice: str | None) -> str | None:
    if waiting is None or not choice:
        return None
    for candidate in waiting.candidates:
        if candidate.get("id") != choice:
            continue
        label = candidate.get("label")
        if isinstance(label, str) and label.strip():
            return label.strip()
        account_name = candidate.get("account_name")
        if isinstance(account_name, str) and account_name.strip():
            return account_name.strip()
    return None


def _profile_proposal_label(
    choice: str | None,
    waiting: TaskWaiting,
    profile_proposals: Sequence[ProfileProposalItem] | None,
) -> str:
    if choice == "none":
        return _candidate_label(waiting, choice) or "都不需要"
    if isinstance(choice, str) and ":" in choice:
        action, raw_index = choice.split(":", 1)
        if action in {"go", "skip"} and raw_index.isdigit():
            action_label = _candidate_label(waiting, choice) or ("去补充" if action == "go" else "不保存")
            idx = int(raw_index)
            if profile_proposals is not None and 0 <= idx < len(profile_proposals):
                from app.services.assistant.entity_forms import module_for

                item = profile_proposals[idx]
                row_label = module_for(item.kind).LABEL
                summary = item.summary.removeprefix(f"{row_label}：").removeprefix(f"{row_label}:").strip()
                group = f"{row_label}：{summary or item.summary}"
                if len(group) > 40:
                    group = group[:40]
                return f"{action_label}：{group}"
            return action_label
    return _candidate_label(waiting, choice) or "选择"


def _disposition_label(payload: SubmitInputRequest, waiting: TaskWaiting | None) -> str:
    choices = payload.choices or []
    if not choices:
        return "本周不再提示" if payload.suppress_week else "暂不标记完成"
    titles = [label for item_id in choices if (label := _candidate_label(waiting, item_id))]
    if len(choices) == 1 and len(titles) == 1:
        base = f"标记完成：{titles[0]}"
    elif titles:
        base = f"标记完成 {len(choices)} 项：{titles[0]} 等"
    else:
        base = f"标记完成 {len(choices)} 项"
    return f"{base} · 本周不再提示" if payload.suppress_week else base


def command_label(
    payload: SubmitInputRequest,
    waiting: TaskWaiting | None,
    *,
    profile_proposals: Sequence[ProfileProposalItem] | None = None,
) -> str:
    if payload.kind == "cancel":
        return "算了，不记了"
    if payload.kind == "revise_activity_kind":
        label = KIND_LABELS.get(payload.choice or "")
        return f"改为{label}" if label else "修改活动类型"
    if payload.kind == "confirm":
        if payload.choice == "confirm":
            if (
                waiting is not None
                and waiting.confirmation_payload is not None
                and waiting.confirmation_payload.kind == "activity_write"
            ):
                return "确认写入"
            return "确认"
        reason = REJECT_REASON_LABELS.get(payload.reason or "")
        return f"取消（{reason}）" if reason else "取消"
    if payload.kind == "request_edit":
        return "修改内容"
    if payload.kind == "submit_form":
        if payload.choice == "cancel":
            return "取消修改" if waiting is not None and waiting.type == "CONFIRMATION_EDIT" else "取消"
        if payload.choice == "defer":
            return "稍后补充"
        return "提交"
    if (waiting is not None and waiting.type == "FOLLOW_UP_DISPOSITION") or payload.choices is not None:
        return _disposition_label(payload, waiting)
    if waiting is not None and waiting.type == "PROFILE_PROPOSALS":
        return _profile_proposal_label(payload.choice, waiting, profile_proposals)
    if waiting is not None and waiting.type == "ENTITY_DEFERRED":
        matched = _candidate_label(waiting, payload.choice)
        if matched:
            return matched
        if payload.choice == "resume":
            return "继续填写"
        if payload.choice == "cancel":
            return "不要了"
        return "选择"
    if waiting is not None and waiting.type == "OBJECT_SELECTION":
        matched = _candidate_label(waiting, payload.choice)
        if matched:
            return matched
        if isinstance(payload.text, str) and payload.text.strip():
            return payload.text.strip()
        if waiting.field == "opportunity":
            return "选择商机"
        if waiting.field == "intent":
            return "选择意图"
        return "选择客户"
    if waiting is not None and waiting.type == "ACTIVITY_KIND":
        return KIND_LABELS.get(payload.choice or "") or _candidate_label(waiting, payload.choice) or "选择活动类型"
    if waiting is not None and waiting.field == "temporal_choice":
        matched = _candidate_label(waiting, payload.choice)
        if matched:
            return matched
        if isinstance(payload.text, str) and payload.text.strip():
            return payload.text.strip()
        return "选择时间"
    if payload.choice == "EXPLICITLY_NONE":
        text = payload.text.strip() if isinstance(payload.text, str) else ""
        return text or "暂无下一步行动"
    text = payload.text.strip() if isinstance(payload.text, str) else ""
    if text:
        return text
    matched = _candidate_label(waiting, payload.choice)
    if matched:
        return matched
    return "选择"


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
                    task_kind=task.task_kind,
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
                text = "这条历史结果暂时无法显示"
        elif action.event_type == "receipt" and isinstance(data.get("activity_public_id"), str):
            text = data.get("label")
        elif action.actor == "USER":
            role = "user"
            text = action.input_json.get("text") or data.get("label")
            if action.action in {"change_kind", "select_activity_kind", "revise_activity_kind"}:
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
                    projection=ConversationProjection(activity_public_id=data["activity_public_id"])
                    if action.event_type == "receipt" and isinstance(data.get("activity_public_id"), str)
                    and data["activity_public_id"]
                    else None,
                )
            )
    return result
