"""Project one assistant conversation message into crm.agent.ui.v1.

The assistant task remains the authority. This module only builds the read
model the Web UI is allowed to render.
"""
# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING, Literal, cast

from pydantic import ValidationError

from app.schemas.assistant_conversation import ConversationBoundary, ConversationMessage
from app.services.agent.ui.markdown import contains_raw_html, project_agent_markdown_to_plain_text
from app.services.agent.ui.schemas import (
    ActionResultBlock,
    AgentErrorCode,
    AgentUIAction,
    AgentUIEnvelope,
    AgentUIMetadata,
    ErrorBlock,
    InteractionBlock,
    InteractionConfirmationFact,
    InteractionField,
    InteractionOption,
    NoticeBlock,
    OpenFollowUpDispositionCardItem,
    RetryAction,
    TextBlock,
)
from app.services.assistant.failure_contract import (
    ORGANIZE_FAILURE_MESSAGE,
    QUALITY_GATE_FAILURE_MESSAGE,
    QUALITY_GATE_FAILURE_TITLE,
    ROOT_RETRYABLE_FAILURE_CODES,
    is_root_failure_code,
    root_failure_code,
    root_failure_presentation,
)

if TYPE_CHECKING:
    from app.schemas.assistant import AssistantTaskView
    from app.services.assistant.contracts import ActivityPreview, TaskDraft, TaskWaiting

_RAW_HTML_RE = re.compile(r"<(?:[A-Za-z][^>]*|/[A-Za-z][^>]*|![^>]*|\?[^>]*)>")
_FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_UNAVAILABLE = "这条结果暂时无法显示，原记录仍保留。"
_UNKNOWN_TEXT = "客户活动写入结果待核对。请先刷新或查询结果，不要重复提交。"

_ASSISTANT_ERROR_CODES: frozenset[str] = frozenset(
    {
        "AI_UNAVAILABLE",
        "QUALITY_NOT_PASSED",
        "CUSTOMER_NOT_FOUND",
        "CRM_WRITE_REJECTED",
        "UNKNOWN_ACTION_NOMINATED",
        "UNKNOWN_COMMIT_RESULT",
        "CONFIGURATION_ERROR",
        "STATE_CONFLICT",
        "RETRYABLE_DEPENDENCY_FAILURE",
        "INTERNAL_ERROR",
        "PERMISSION_DENIED",
        "ACTION_EXPIRED",
        "ACTION_INVALID",
        "ACTION_ALREADY_CONSUMED",
        "UPSTREAM_TIMEOUT",
        "UPSTREAM_UNAVAILABLE",
        "MODEL_OUTPUT_INVALID",
        "STRUCTURING_UNAVAILABLE",
        "QUALITY_GATE_UNAVAILABLE",
    }
)
_ERROR_TITLES: dict[str, str] = {
    "CUSTOMER_NOT_FOUND": "尚未写入",
    "CRM_WRITE_REJECTED": "写入未完成",
    "STATE_CONFLICT": "这张卡片状态已变化",
    "UNKNOWN_COMMIT_RESULT": "结果待核对",
}
_KIND_LABELS: dict[str, str] = {
    "FOLLOW_UP": "跟进",
    "PHONE_FOLLOW_UP": "电话跟进",
    "WECHAT_FOLLOW_UP": "微信跟进",
    "EMAIL_FOLLOW_UP": "邮件跟进",
    "VISIT_FOLLOW_UP": "拜访跟进",
    "OTHER_FOLLOW_UP": "其他跟进",
    "ONLINE_MEETING": "线上会议",
    "OFFLINE_MEETING": "线下会议",
}
_FIELD_LABELS: dict[str, str] = {
    "customer": "客户名称",
    "content": "沟通内容",
    "next_action": "下一步行动",
    "next_follow_time": "下次跟进时间",
    "temporal_choice": "下次跟进时间",
}
_ACTIVITY_KIND_OPTIONS: tuple[tuple[str, str, str], ...] = (
    ("ONLINE_MEETING", "线上会议", "远程沟通"),
    ("OFFLINE_MEETING", "线下会议", "面谈拜访"),
    ("FOLLOW_UP", "普通跟进", "电话/微信"),
)
_PROPOSAL_LABELS: dict[str, str] = {
    "opportunity_create": "创建商机",
    "opportunity_stage": "推进商机",
    "follow_up_task": "更新跟进任务",
    "follow_up_task_create": "创建跟进任务",
    "customer_fact": "写入客户事实",
}


def finalize_assistant_ui(
    messages: list[ConversationMessage],
    *,
    focused_task: AssistantTaskView | None,
    pending_choice: ConversationBoundary | None,
) -> None:
    """Attach one envelope to every assistant message. User bubbles stay text."""

    _ensure_current_waiting(messages, focused_task)
    live_id = _live_waiting_message_id(messages, focused_task)
    for message in messages:
        if message.role != "assistant":
            message.ui = None
            continue
        active_waiting = message.id == live_id
        active_boundary = (
            message.boundary is not None
            and pending_choice is not None
            and message.boundary.entry_id == pending_choice.entry_id
        )
        try:
            message.ui = project_assistant_message(
                message,
                active_waiting=active_waiting,
                active_boundary=active_boundary,
            )
        except (ValidationError, ValueError):
            message.ui = _failure_envelope(message, code="INTERNAL_ERROR", retryable=False, text=_UNAVAILABLE)



def _ensure_current_waiting(messages: list[ConversationMessage], focused_task: AssistantTaskView | None) -> None:
    """Keep the authoritative wait on the page even when history has not caught up."""

    if focused_task is None or focused_task.status != "ACTIVE" or focused_task.waiting is None:
        return
    if _live_waiting_message_id(messages, focused_task) is not None:
        return
    waiting = focused_task.waiting
    action = waiting.action_id or waiting.question_id
    messages.append(
        ConversationMessage(
            id=f"current:{focused_task.public_id}:{focused_task.version}:{action}",
            role="assistant",
            text=waiting.prompt,
            at=focused_task.last_modified_time or "1970-01-01T00:00:00",
            task=focused_task,
        )
    )


def project_assistant_message(
    message: ConversationMessage,
    *,
    active_waiting: bool,
    active_boundary: bool,
) -> AgentUIEnvelope:
    """Build the only Web-visible blocks for one assistant message."""

    if message.outcome == "failure":
        return _project_failure(message)
    disposition = _project_disposition(message, active_waiting=active_waiting)
    if disposition is not None:
        return disposition
    if message.outcome == "activity_written":
        return _envelope(message, (_result_block(message),), route="WORKFLOW")
    if message.boundary is not None:
        return _envelope(
            message,
            (_boundary_block(message, active=active_boundary),),
            route="CLARIFY",
        )
    waiting = message.task.waiting if message.task is not None else None
    if waiting is not None:
        blocks = _waiting_blocks(message, waiting, active=active_waiting)
        return _envelope(message, blocks, route="WORKFLOW")
    text = _plain(message.text) or _UNAVAILABLE
    return _envelope(message, (_text_block(text),), route="WORKFLOW" if message.task else "CHITCHAT")


def _project_failure(message: ConversationMessage) -> AgentUIEnvelope:
    code = message.error_code if message.error_code in _ASSISTANT_ERROR_CODES else "INTERNAL_ERROR"
    text = _plain(message.text) or _UNAVAILABLE
    if code == "UNKNOWN_COMMIT_RESULT":
        notice = NoticeBlock(
            id="b_notice_1",
            type="notice",
            tone="warning",
            title="结果待核对",
            text=text or _UNKNOWN_TEXT,
        )
        return _envelope(message, (notice,), route="WORKFLOW", state="final")
    actions: tuple[AgentUIAction, ...] = ()
    trace_id = _reply_entry_id(message.id)
    retryable = False
    title = _ERROR_TITLES.get(code, "遇到问题" if code == "INTERNAL_ERROR" else "这次没处理成")
    if is_root_failure_code(code) and trace_id is not None:
        failure = root_failure_code(code)
        presentation = root_failure_presentation(failure)
        title = presentation.title
        text = presentation.message
        retryable = message.retryable is True and failure in ROOT_RETRYABLE_FAILURE_CODES
        if retryable:
            actions = (RetryAction(type="retry", action_id=f"retry:{trace_id}", label="重试"),)
    elif code in {"STRUCTURING_UNAVAILABLE", "QUALITY_GATE_UNAVAILABLE"}:
        title = "评估未完成" if code == "QUALITY_GATE_UNAVAILABLE" or "质量评估" in text else "整理未完成"
        retryable = message.retryable is True
        trace_id = None
    elif is_root_failure_code(code):
        # Turn-event organize/quality failures reuse the root codes but must not
        # offer the root entry retry or replace the saved-content sentence.
        failure = root_failure_code(code)
        if "质量评估" in text or text == QUALITY_GATE_FAILURE_MESSAGE:
            title = QUALITY_GATE_FAILURE_TITLE
        elif "活动类型判断" in text:
            title = "活动类型判断未完成"
        else:
            title = "整理未完成"
            text = text or ORGANIZE_FAILURE_MESSAGE
        retryable = message.retryable is True and failure in ROOT_RETRYABLE_FAILURE_CODES
        trace_id = None
    error = ErrorBlock(
        id="b_error_1",
        type="error",
        code=_as_error_code(code),
        title=title,
        message=text,
        retryable=retryable,
        trace_id=trace_id,
    )
    return _envelope(message, (error,), route="WORKFLOW", state="failed", actions=actions)


def _reply_entry_id(message_id: str) -> str | None:
    suffix = ":reply"
    if not message_id.endswith(suffix):
        return None
    entry_id = message_id[: -len(suffix)]
    if not entry_id or len(entry_id) > 128:
        return None
    return entry_id



def _project_disposition(message: ConversationMessage, *, active_waiting: bool) -> AgentUIEnvelope | None:
    task = message.task
    if task is None or not isinstance(task.follow_up_disposition, dict):
        return None
    waiting = task.waiting
    showing = message.outcome == "follow_up_disposition" or (
        waiting is not None and waiting.type == "FOLLOW_UP_DISPOSITION"
    )
    if not showing:
        return None
    payload = task.follow_up_disposition
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        notice = NoticeBlock(
            id="b_notice_disposition",
            type="notice",
            tone="warning" if payload.get("status") in {"OVERFLOW", "QUERY_FAILED"} else "info",
            title="历史跟进任务",
            text=_plain(message.text) or _UNAVAILABLE,
        )
        return _envelope(message, (notice,), route="WORKFLOW")
    active = active_waiting and waiting is not None and waiting.type == "FOLLOW_UP_DISPOSITION"
    current = next((item for item in items if isinstance(item, dict) and item.get("state") == "current"), None)
    options = []
    if active and current is not None:
        item_id = str(current.get("item_id") or "")
        options = [
            InteractionOption(value=f"{item_id}:complete", label="已完成", description="标记此任务完成"),
            InteractionOption(value=f"{item_id}:hold", label="先放着", description="保持未完成"),
            InteractionOption(value=f"{item_id}:skip", label="不管了", description="仅跳过本次"),
        ]
    elif not active:
        options = [
            InteractionOption(value="complete", label="已完成", disabled=True),
            InteractionOption(value="hold", label="先放着", disabled=True),
            InteractionOption(value="skip", label="不管了", disabled=True),
        ]
    if not options:
        options = [
            InteractionOption(value="complete", label="已完成", disabled=True),
            InteractionOption(value="hold", label="先放着", disabled=True),
            InteractionOption(value="skip", label="不管了", disabled=True),
        ]
        active = False
    cards = []
    for item in items:
        if not isinstance(item, dict):
            continue
        cards.append(OpenFollowUpDispositionCardItem(
            item_id=str(item.get("item_id") or ""),
            title=str(item.get("title") or "跟进任务"),
            owner_line=item.get("owner_line") if isinstance(item.get("owner_line"), str) else None,
            related=bool(item.get("related")),
            evidence_quote=item.get("evidence_quote") if isinstance(item.get("evidence_quote"), str) else None,
            evidence_reason=item.get("evidence_reason") if isinstance(item.get("evidence_reason"), str) else None,
            state=item.get("state") if item.get("state") in {
                "current", "waiting", "complete", "hold", "skip", "failed", "unknown",
            } else "waiting",
            result_title=item.get("result_title") if isinstance(item.get("result_title"), str) else None,
            result_message=item.get("result_message") if isinstance(item.get("result_message"), str) else None,
        ))
    total = payload.get("total") if isinstance(payload.get("total"), int) else len(cards)
    customer = payload.get("customer_name") or ""
    kind = payload.get("activity_kind_label") or ""
    detail = " · ".join(part for part in (str(customer), str(kind)) if part)
    notice = NoticeBlock(
        id="b_notice_written",
        type="notice",
        tone="success",
        title="本次跟进已写入",
        text=detail or "本次跟进已写入",
    )
    prompt = _plain(waiting.prompt) if waiting is not None and waiting.type == "FOLLOW_UP_DISPOSITION" else (
        _plain(message.text) or f"还发现 {total} 条未完成的历史任务，请逐条处理。"
    )
    interaction = InteractionBlock(
        id="b_interaction_1",
        type="interaction",
        interaction_id=_interaction_id(message),
        interaction_type="choice",
        business_action="settle_follow_up_disposition",
        presentation="OPEN_FOLLOW_UP_DISPOSITION",
        state="ACTIVE" if active else "READ_ONLY",
        prompt=prompt,
        options=options,
        disposition_items=cards,
        selection_mode="single",
        min_selections=1,
        max_selections=1,
        submit_on_select=active,
        submit_action_id=_action_id(waiting) if active and waiting is not None else None,
    )
    blocks: list[TextBlock | NoticeBlock | InteractionBlock] = [notice, interaction]
    if not active and _plain(message.text) and _plain(message.text) != prompt:
        blocks.append(_text_block(_plain(message.text)))
    return _envelope(message, tuple(blocks), route="WORKFLOW")


def _waiting_blocks(
    message: ConversationMessage,
    waiting: TaskWaiting,
    *,
    active: bool,
) -> tuple[TextBlock | NoticeBlock | InteractionBlock, ...]:
    prompt = _plain(waiting.prompt) or _plain(message.text) or _UNAVAILABLE
    interaction = _waiting_interaction(message, waiting, prompt=prompt, active=active)
    blocks: list[TextBlock | NoticeBlock | InteractionBlock] = []
    prose = _plain(message.text)
    if prose and prose != prompt:
        blocks.append(_text_block(prose))
    if message.task is not None and waiting.type == "FIELD":
        notice = _accepted_notice(message.task.draft)
        if notice is not None:
            blocks.append(notice)
    blocks.append(interaction)
    return tuple(blocks)


def _waiting_interaction(
    message: ConversationMessage,
    waiting: TaskWaiting,
    *,
    prompt: str,
    active: bool,
) -> InteractionBlock:
    action_id = _action_id(waiting)
    if waiting.type == "CONFIRMATION" and waiting.confirmation_payload is not None:
        return _confirmation(message, waiting, prompt=prompt, active=active, action_id=action_id)
    if waiting.type == "ACTIVITY_KIND":
        return _choice(
            message,
            prompt=prompt,
            active=active,
            action_id=action_id,
            business_action="select_activity_kind",
            options=[
                InteractionOption(value=value, label=label, description=description)
                for value, label, description in _ACTIVITY_KIND_OPTIONS
            ],
        )
    if waiting.type == "OBJECT_SELECTION" or (waiting.type == "FIELD" and waiting.field == "temporal_choice"):
        options = _candidate_options(waiting.candidates)
        if options:
            business_action = (
                "resolve_temporal_choice"
                if waiting.field == "temporal_choice"
                else "select_opportunity"
                if waiting.field == "opportunity"
                else "select_customer"
            )
            return _choice(
                message,
                prompt=prompt,
                active=active,
                action_id=action_id,
                business_action=business_action,
                options=options,
            )
    return _text_input(message, waiting, prompt=prompt, active=active, action_id=action_id)


def _confirmation(
    message: ConversationMessage,
    waiting: TaskWaiting,
    *,
    prompt: str,
    active: bool,
    action_id: str,
) -> InteractionBlock:
    payload = waiting.confirmation_payload
    assert payload is not None
    confirm_disabled = False
    if payload.kind == "activity_write":
        business_action = "confirm_activity_write"
        facts = _activity_facts(payload.preview, editable=active)
        confirm_label = "确认写入"
        confirm_disabled = payload.preview.channel_status == "required"
    else:
        business_action = "confirm_proposal"
        facts = _proposal_facts(payload.proposal_kind, payload.candidate.evidence_quote)
        confirm_label = "确认"
    return InteractionBlock(
        id="b_interaction_1",
        type="interaction",
        interaction_id=_interaction_id(message),
        interaction_type="confirmation",
        business_action=business_action,
        state="ACTIVE" if active else "READ_ONLY",
        prompt=prompt,
        facts=facts,
        options=[
            InteractionOption(
                value="confirm",
                label=confirm_label,
                disabled=confirm_disabled,
                description="先选择活动类型" if confirm_disabled else None,
            ),
            InteractionOption(value="cancel", label="取消"),
        ],
        selection_mode="single",
        submit_on_select=True,
        submit_action_id=action_id if active else None,
    )


def _activity_facts(preview: ActivityPreview, *, editable: bool) -> list[InteractionConfirmationFact]:
    facts: list[InteractionConfirmationFact] = []
    kind_label = _KIND_LABELS.get(preview.activity_kind or "", "") or "请选择本次活动的主渠道"
    _add_fact(facts, "customer", "客户", preview.customer_name, group="write")
    if preview.title and preview.title != kind_label:
        _add_fact(facts, "title", "标题", preview.title, group="write")
    _add_fact(facts, "summary", "摘要", preview.summary, group="write")
    participants = _participants(preview.content_json)
    _add_fact(facts, "participants", "参会角色", participants, group="write")
    if preview.next_action:
        _add_fact(facts, "next_action", "下一步", preview.next_action, group="write")
    elif preview.activity_kind in {"ONLINE_MEETING", "OFFLINE_MEETING"}:
        _add_fact(facts, "next_action", "下一步", "未提供行动项", group="write")
    from app.services.assistant.temporal_evidence import confirmation_time_labels

    commitment_line, follow_override = confirmation_time_labels(preview.content_json)
    _add_fact(facts, "customer_commitment", "客户承诺", commitment_line, group="write")
    follow_time = follow_override or preview.next_follow_time_text or preview.next_follow_time
    _add_fact(facts, "next_follow_time", "跟进时间", follow_time, group="write")
    status_label = "历史冻结" if not editable and preview.activity_kind else preview.channel_status_label
    options = [
        InteractionOption(value=kind, label=_KIND_LABELS[kind])
        for kind in preview.channel_options
        if editable and kind in _KIND_LABELS
    ]
    _add_fact(
        facts, "activity_kind", "活动类型", kind_label, group="activity_kind",
        status_label=status_label, source=preview.channel_source_text, options=options,
    )
    if preview.change_signal:
        _add_fact(
            facts, "change_signal", "客户上下文判断", preview.change_signal, group="context",
            source=preview.change_summary,
        )
        if preview.opportunity_name:
            stage = f" · {preview.opportunity_stage}" if preview.opportunity_stage else ""
            _add_fact(facts, "opportunity", "关联商机", f"{preview.opportunity_name}{stage}", group="context")
        evidence = [
            " ".join(part for part in (item.occurred_at, item.summary) if part)
            for item in preview.context_evidence[:3]
        ]
        if evidence:
            _add_fact(facts, "context_evidence", "依据", "；".join(evidence), group="context")
    _add_fact(facts, "score", "内容质量", f"{preview.score} / 100", group="score")
    _add_fact(facts, "score_reason", "评分依据", preview.score_reason, group="score")
    return facts[:20]


def _proposal_facts(kind: str, evidence: str) -> list[InteractionConfirmationFact]:
    facts: list[InteractionConfirmationFact] = []
    _add_fact(facts, "proposal", "建议", _PROPOSAL_LABELS.get(kind, kind))
    _add_fact(facts, "evidence", "证据", evidence)
    return facts


def _participants(content_json: dict[str, object]) -> str | None:
    value = content_json.get("participants")
    if not isinstance(value, dict):
        return None
    parts: list[str] = []
    for key, label in (("internal", "我方"), ("customer", "客户方")):
        names = value.get(key)
        if not isinstance(names, list):
            continue
        known = [name.strip() for name in names if isinstance(name, str) and name.strip()]
        if known:
            parts.append(f"{label}：{'、'.join(known)}")
    return "；".join(parts) or None


def _choice(
    message: ConversationMessage,
    *,
    prompt: str,
    active: bool,
    action_id: str,
    business_action: str,
    options: list[InteractionOption],
) -> InteractionBlock:
    return InteractionBlock(
        id="b_interaction_1",
        type="interaction",
        interaction_id=_interaction_id(message),
        interaction_type="choice",
        business_action=business_action,
        state="ACTIVE" if active else "READ_ONLY",
        prompt=prompt,
        options=options,
        selection_mode="single",
        min_selections=1,
        max_selections=1,
        submit_on_select=True,
        submit_action_id=action_id if active else None,
    )


def _text_input(
    message: ConversationMessage,
    waiting: TaskWaiting,
    *,
    prompt: str,
    active: bool,
    action_id: str,
) -> InteractionBlock:
    field_name = waiting.field or "answer"
    key = field_name if _FIELD_KEY_RE.fullmatch(field_name) else "answer"
    label = _FIELD_LABELS.get(field_name, "补充内容")
    placeholder = "例如 2026-10-30" if field_name == "temporal_choice" else None
    return InteractionBlock(
        id="b_interaction_1",
        type="interaction",
        interaction_id=_interaction_id(message),
        interaction_type="text_input",
        business_action="collect_field",
        state="ACTIVE" if active else "READ_ONLY",
        prompt=prompt,
        fields=[
            InteractionField(
                key=key,
                label=label,
                field_type="text",
                required=True,
                placeholder=placeholder,
                min_length=1,
                max_length=2000,
            )
        ],
        allow_blank=False,
        submit_label="提交",
        submit_action_id=action_id if active else None,
    )


def _boundary_block(message: ConversationMessage, *, active: bool) -> InteractionBlock:
    boundary = message.boundary
    assert boundary is not None
    prompt = _plain(boundary.prompt) or _plain(message.text) or _UNAVAILABLE
    entry_id = boundary.entry_id[:100]
    return _choice(
        message,
        prompt=prompt,
        active=active,
        action_id=f"boundary:{entry_id}",
        business_action="assistant_boundary",
        options=[
            InteractionOption(value="CONTINUE", label="接着刚才"),
            InteractionOption(value="NEW", label="另记一件"),
        ],
    )


def _accepted_notice(draft: TaskDraft) -> NoticeBlock | None:
    parts: list[str] = []
    if draft.customer.status == "ACCEPTED" and (draft.customer.value or "").strip():
        parts.append(f"客户：{draft.customer.value}")
    if draft.content.status == "ACCEPTED" and (draft.content.value or "").strip():
        parts.append("正文：已整理")
    if draft.next_action.status == "ACCEPTED" and (draft.next_action.value or "").strip():
        parts.append("下一步：已确认")
    if not parts:
        return None
    return NoticeBlock(id="b_notice_1", type="notice", tone="info", title="已确认", text="、".join(parts))


def _result_block(message: ConversationMessage) -> ActionResultBlock:
    text = _plain(message.text) or "活动已写入"
    if text == "已记录这条客户活动。":
        text = "活动已写入"
    return ActionResultBlock(
        id="b_result_1",
        type="action_result",
        action_id=_clip(message.id, 128),
        status="SUCCESS",
        title="活动已写入",
        message=text,
    )


def _text_block(text: str) -> TextBlock:
    return TextBlock(id="b_text_1", type="text", format="plain", text=text)


def _failure_envelope(
    message: ConversationMessage,
    *,
    code: AgentErrorCode,
    retryable: bool,
    text: str,
) -> AgentUIEnvelope:
    error = ErrorBlock(
        id="b_error_1",
        type="error",
        code=code,
        title="遇到问题" if code == "INTERNAL_ERROR" else "这次没处理成",
        message=text,
        retryable=retryable,
    )
    return _envelope(message, (error,), route="WORKFLOW", state="failed")


def _envelope(
    message: ConversationMessage,
    blocks: tuple[TextBlock | NoticeBlock | InteractionBlock | ErrorBlock | ActionResultBlock, ...],
    *,
    route: Literal["QUERY", "WORKFLOW", "CLARIFY", "CHITCHAT"] | None,
    state: Literal["streaming", "final", "failed"] = "final",
    actions: tuple[AgentUIAction, ...] = (),
) -> AgentUIEnvelope:
    label = _accessibility(blocks)
    return AgentUIEnvelope(
        schema_version="crm.agent.ui.v1",
        message_id=_message_number(message.id),
        turn_id=_clip(message.id, 128),
        role="assistant",
        state=state,
        blocks=list(blocks),
        suggested_actions=list(actions),
        metadata=AgentUIMetadata(display="MESSAGE", route=route, accessibility_label=label),
    )


def _candidate_options(candidates: list[dict[str, object]]) -> list[InteractionOption]:
    options: list[InteractionOption] = []
    seen: set[str] = set()
    for candidate in candidates:
        raw_id = candidate.get("id")
        if not isinstance(raw_id, str) or not raw_id.strip() or len(raw_id) > 64:
            continue
        if raw_id in seen:
            continue
        label = candidate.get("label")
        if not isinstance(label, str) or not label.strip():
            label = candidate.get("account_name")
        if not isinstance(label, str) or not label.strip():
            continue
        seen.add(raw_id)
        options.append(InteractionOption(value=raw_id, label=_clip(label.strip(), 200)))
        if len(options) == 50:
            break
    return options


def _add_fact(
    facts: list[InteractionConfirmationFact],
    key: str,
    label: str,
    value: str | None,
    *,
    group: Literal["write", "activity_kind", "context", "score"] = "write",
    status_label: str | None = None,
    source: str | None = None,
    options: list[InteractionOption] | None = None,
) -> None:
    if value is None:
        return
    text = _plain(value)
    if not text:
        return
    facts.append(
        InteractionConfirmationFact(
            key=key,
            label=label,
            value=_clip(text, 10000),
            group=group,
            status_label=status_label,
            source=_clip(source, 1000) if source else None,
            options=options or [],
        )
    )


def _action_id(waiting: TaskWaiting) -> str:
    if waiting.action_id:
        return _clip(waiting.action_id, 128)
    return _clip(f"wait:{waiting.question_id}", 128)


def _interaction_id(message: ConversationMessage) -> str:
    return _clip(f"ix:{message.id}", 128)


def _live_waiting_message_id(
    messages: list[ConversationMessage],
    focused_task: AssistantTaskView | None,
) -> str | None:
    if focused_task is None or focused_task.status != "ACTIVE" or focused_task.waiting is None:
        return None
    current = focused_task.waiting
    live_id: str | None = None
    for message in messages:
        task = message.task
        waiting = task.waiting if task is not None else None
        if task is None or waiting is None or task.public_id != focused_task.public_id:
            continue
        if (
            waiting.action_id == current.action_id
            and waiting.expected_version == current.expected_version
            and waiting.question_id == current.question_id
        ):
            live_id = message.id
    return live_id


def _plain(value: str | None) -> str:
    if value is None:
        return ""
    text = project_agent_markdown_to_plain_text(value).strip()
    if contains_raw_html(text):
        text = _RAW_HTML_RE.sub("", text).strip()
    return text


def _accessibility(blocks: tuple[object, ...]) -> str:
    parts: list[str] = []
    for block in blocks:
        if isinstance(block, TextBlock):
            parts.append(block.text)
        elif isinstance(block, InteractionBlock):
            parts.append(block.prompt)
        elif isinstance(block, ErrorBlock):
            parts.append(block.title)
            parts.append(block.message)
        elif isinstance(block, NoticeBlock):
            if block.title:
                parts.append(block.title)
            parts.append(block.text)
        elif isinstance(block, ActionResultBlock):
            parts.append(block.title)
            parts.append(block.message)
    label = " ".join(part for part in parts if part).strip()
    return _clip(label or _UNAVAILABLE, 10000)


def _message_number(message_id: str) -> int:
    digest = int.from_bytes(hashlib.sha256(message_id.encode()).digest()[:4], "big") & 0x7FFFFFFF
    return digest or 1


def _clip(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit]


def _as_error_code(code: str) -> AgentErrorCode:
    if code not in _ASSISTANT_ERROR_CODES:
        return "INTERNAL_ERROR"
    return cast("AgentErrorCode", code)
