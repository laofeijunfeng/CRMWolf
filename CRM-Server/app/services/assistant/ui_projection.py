"""Project one assistant conversation message into crm.agent.ui.v1.

The assistant task remains the authority. This module only builds the read
model the Web UI is allowed to render.
"""
# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

import hashlib
import re
from datetime import datetime
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
from app.services.assistant.activity_channel import CANONICAL_KINDS, kind_choice_candidates
from app.services.assistant.failure_contract import (
    ORGANIZE_FAILURE_MESSAGE,
    QUALITY_GATE_FAILURE_MESSAGE,
    QUALITY_GATE_FAILURE_TITLE,
    ROOT_RETRYABLE_FAILURE_CODES,
    is_root_failure_code,
    root_failure_code,
    root_failure_presentation,
)
from app.services.customer_activity_kinds import ACTIVITY_KIND_META

if TYPE_CHECKING:
    from app.schemas.assistant import AssistantTaskView
    from app.services.assistant.contracts import ActivityPreview, TaskDraft, TaskWaiting

_RAW_HTML_RE = re.compile(r"<(?:[A-Za-z][^>]*|/[A-Za-z][^>]*|![^>]*|\?[^>]*)>")
_FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_UNAVAILABLE = "这条结果暂时无法显示"
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
        "REQUEST_PROTOCOL_ERROR",
        "AUTHENTICATION_ERROR",
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
    **{kind: str(meta["label"]) for kind, meta in ACTIVITY_KIND_META.items()},
}
_FIELD_LABELS: dict[str, str] = {
    "customer": "客户名称",
    "content": "沟通内容",
    "next_action": "下一步行动",
    "next_follow_time": "下次跟进时间",
    "temporal_choice": "补充内容",
}
_TEMPORAL_LABELS: dict[str, str] = {
    "DATE": "下次跟进日期",
    "MONTH": "日期月份",
    "ROLE": "时间归属",
    "STATUS": "完成状态",
    "PRIMARY": "主跟进行动",
}
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
    """Attach UI envelopes, except for user text and host-only completion boundaries."""

    _ensure_current_waiting(messages, focused_task)
    _normalize_task_completions(messages)
    live_id = _live_waiting_message_id(messages, focused_task)
    submitted_kind = _resolved_activity_kind(focused_task)
    receipts = _disposition_receipts(messages, live_id)
    for message in messages:
        if message.role != "assistant":
            message.ui = None
            continue
        receipt = receipts.get(message.id)
        if receipt is not None:
            message.ui = _envelope(message, (receipt,), route="WORKFLOW")
            continue
        active_waiting = message.id == live_id
        active_boundary = (
            message.boundary is not None
            and pending_choice is not None
            and message.boundary.entry_id == pending_choice.entry_id
        )
        same_task = (
            focused_task is not None and message.task is not None and message.task.public_id == focused_task.public_id
        )
        try:
            message.ui = project_assistant_message(
                message,
                active_waiting=active_waiting,
                active_boundary=active_boundary,
                submitted_kind=submitted_kind if same_task else None,
            )
        except (ValidationError, ValueError):
            message.ui = _failure_envelope(message, code="INTERNAL_ERROR", retryable=False, text=_UNAVAILABLE)


def _is_task_completion(message: ConversationMessage) -> bool:
    """Only this message's authoritative snapshot can establish normal completion."""
    return (
        message.role == "assistant"
        and message.task is not None
        and message.task.status == "COMPLETED"
        and message.task.waiting is None
        and message.boundary is None
        and message.outcome in {"task_completed", "activity_written", "follow_up_disposition"}
        and message.outcome != "failure"
        and message.error_code is None
    )


def _is_completion_only(message: ConversationMessage) -> bool:
    return _is_task_completion(message) and message.outcome not in {"activity_written", "follow_up_disposition"}


def _normalize_task_completions(messages: list[ConversationMessage]) -> None:
    """Keep business results, replacing terminal prose with one read-model boundary per task."""
    last_completed: dict[str, int] = {}
    for index, message in enumerate(messages):
        if _is_task_completion(message) and message.task is not None:
            last_completed[message.task.public_id] = index
    if not last_completed:
        return
    completion_sources = {task_id: messages[index] for task_id, index in last_completed.items()}
    for index, message in enumerate(messages):
        task = message.task
        if (
            task is not None
            and task.public_id in last_completed
            and message.role == "assistant"
            and message.outcome in {"activity_written", "follow_up_disposition"}
        ):
            last_completed[task.public_id] = max(last_completed[task.public_id], index)
    normalized: list[ConversationMessage] = []
    for index, message in enumerate(messages):
        if not _is_completion_only(message):
            normalized.append(message)
        task = message.task
        if task is not None and last_completed.get(task.public_id) == index:
            source = completion_sources[task.public_id]
            normalized.append(
                ConversationMessage(
                    id=f"completion:{task.public_id}",
                    role="assistant",
                    text="本次任务已完成",
                    at=source.at,
                    task=source.task,
                    outcome="task_completed",
                )
            )
    messages[:] = normalized


_SETTLED_LABELS = {
    "complete": "已完成",
    "hold": "先放着",
    "skip": "不管了",
    "unknown": "结果待核对",
    "failed": "未能完成",
}


def _disposition_items(message: ConversationMessage) -> list[dict[str, object]] | None:
    """Items of a message `_project_disposition` would render as a card; None otherwise."""

    task = message.task
    if message.role != "assistant" or message.outcome == "failure" or task is None:
        return None
    payload = task.follow_up_disposition
    if not isinstance(payload, dict):
        return None
    waiting = task.waiting
    if message.outcome != "follow_up_disposition" and (waiting is None or waiting.type != "FOLLOW_UP_DISPOSITION"):
        return None
    items = payload.get("items")
    if not isinstance(items, list):
        return None
    cards = [item for item in items if isinstance(item, dict)]
    return cards or None


def _disposition_receipts(messages: list[ConversationMessage], live_id: str | None) -> dict[str, NoticeBlock]:
    """One disposition round shows one full card; every earlier message in it becomes a one-line receipt."""

    groups: list[list[tuple[ConversationMessage, list[dict[str, object]]]]] = []
    open_groups: dict[tuple[object, ...], int] = {}
    for message in messages:
        items = _disposition_items(message)
        if items is None or message.task is None:
            continue
        key = (message.task.public_id, *((item.get("item_id"), item.get("title")) for item in items))
        offer = all(item.get("state") in {"current", "waiting"} for item in items)
        if offer or key not in open_groups:
            open_groups[key] = len(groups)
            groups.append([])
        groups[open_groups[key]].append((message, items))
    receipts: dict[str, NoticeBlock] = {}
    for group in groups:
        full = next((index for index, (message, _) in enumerate(group) if message.id == live_id), len(group) - 1)
        latest = {item.get("item_id"): item for item in group[full][1]}
        for index, (message, items) in enumerate(group):
            if index == full:
                continue
            own = next((item for item in items if item.get("state") == "current"), None)
            if own is None:
                continue
            title = str(own.get("title") or "跟进任务")
            label = _receipt_label(latest.get(own.get("item_id"))) or _receipt_label(own) or "已处理"
            short = title if len(title) <= 24 else f"{title[:24]}…"
            receipts[message.id] = NoticeBlock(
                id="b_notice_receipt",
                type="notice",
                tone="info",
                text=f"{label} · {short}",
            )
    return receipts


def _receipt_label(item: dict[str, object] | None) -> str | None:
    if item is None:
        return None
    state = item.get("state")
    if not isinstance(state, str) or state not in _SETTLED_LABELS:
        return None
    title = item.get("result_title")
    return title if isinstance(title, str) and title else _SETTLED_LABELS[state]


def _resolved_activity_kind(focused_task: AssistantTaskView | None) -> str | None:
    """The concrete kind the user already fixed on the focused task, if any."""

    if focused_task is None:
        return None
    waiting = focused_task.waiting
    payload = waiting.confirmation_payload if waiting is not None else None
    preview = payload.preview if payload is not None and payload.kind == "activity_write" else None
    for kind in (preview.activity_kind if preview is not None else None, focused_task.draft.channel_kind):
        if kind in CANONICAL_KINDS:
            return kind
    return None


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
    submitted_kind: str | None = None,
) -> AgentUIEnvelope | None:
    """Build Web-visible blocks, or leave a normal completion to the host."""

    if message.outcome == "failure":
        return _project_failure(message)
    if _is_completion_only(message):
        return None
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
        blocks = _waiting_blocks(message, waiting, active=active_waiting, submitted_kind=submitted_kind)
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
        if code in {"REQUEST_PROTOCOL_ERROR", "AUTHENTICATION_ERROR"}:
            presentation = root_failure_presentation(failure)
            title = presentation.title
            text = presentation.message
        elif "质量评估" in text or text == QUALITY_GATE_FAILURE_MESSAGE:
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
    active = active and current is not None
    item_id = str(current.get("item_id") or "") if active and current is not None else ""
    options = [
        InteractionOption(value=f"{item_id}:{value}" if active else value, label=label, disabled=not active)
        for value, label in (("complete", "已完成"), ("hold", "先放着"), ("skip", "不管了"))
    ]
    cards = []
    for item in items:
        if not isinstance(item, dict):
            continue
        cards.append(
            OpenFollowUpDispositionCardItem(
                item_id=str(item.get("item_id") or ""),
                title=str(item.get("title") or "跟进任务"),
                owner_line=_owner_line(item.get("owner_line")),
                related=bool(item.get("related")),
                evidence_quote=item.get("evidence_quote") if isinstance(item.get("evidence_quote"), str) else None,
                evidence_reason=None,
                state=item.get("state")
                if item.get("state")
                in {
                    "current",
                    "waiting",
                    "complete",
                    "hold",
                    "skip",
                    "failed",
                    "unknown",
                }
                else "waiting",
                result_title=item.get("result_title") if isinstance(item.get("result_title"), str) else None,
                result_message=item.get("result_message") if isinstance(item.get("result_message"), str) else None,
            )
        )
    customer = payload.get("customer_name") or ""
    kind = payload.get("activity_kind_label") or ""
    detail = " · ".join(part for part in (str(customer), str(kind)) if part)
    notice = NoticeBlock(
        id="b_notice_written",
        type="notice",
        tone="success",
        title="本次跟进已写入",
        text=detail or "已写入",
    )
    summary = _plain(message.text) if not active and payload.get("status") == "DONE" else ""
    interaction = InteractionBlock(
        id="b_interaction_1",
        type="interaction",
        interaction_id=_interaction_id(message),
        interaction_type="choice",
        business_action="settle_follow_up_disposition",
        presentation="OPEN_FOLLOW_UP_DISPOSITION",
        state="ACTIVE" if active else "READ_ONLY",
        prompt="历史跟进任务",
        hint=summary[:400] or None,
        options=options,
        disposition_items=cards,
        selection_mode="single",
        min_selections=1,
        max_selections=1,
        submit_on_select=active,
        submit_action_id=_action_id(waiting) if active and waiting is not None else None,
    )
    return _envelope(message, (notice, interaction), route="WORKFLOW")


def _owner_line(raw: object) -> str | None:
    """Drop the owner when it is the viewer; old rows stored a 负责人 prefix."""

    if not isinstance(raw, str):
        return None
    text = raw.removeprefix("负责人：我 · ")
    if text == "负责人：我":
        return None
    return text.removeprefix("负责人：") or None


def _waiting_blocks(
    message: ConversationMessage,
    waiting: TaskWaiting,
    *,
    active: bool,
    submitted_kind: str | None = None,
) -> tuple[TextBlock | NoticeBlock | InteractionBlock, ...]:
    prompt = _plain(waiting.prompt) or _plain(message.text) or _UNAVAILABLE
    interaction = _waiting_interaction(message, waiting, prompt=prompt, active=active, submitted_kind=submitted_kind)
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
    submitted_kind: str | None = None,
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
            options=_activity_kind_options(waiting),
            hint=waiting.hint,
            submitted=None if active else submitted_kind,
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
    _add_communication_time_fact(facts, preview.content_json)
    if preview.next_action:
        _add_fact(facts, "next_action", "下一步", preview.next_action, group="write")
    elif preview.activity_kind in {"ONLINE_MEETING", "OFFLINE_MEETING"}:
        _add_fact(facts, "next_action", "下一步", "未提供行动项", group="write")
    from app.services.assistant.temporal_evidence import confirmation_time_labels

    commitment_line, follow_override = confirmation_time_labels(preview.content_json)
    _add_fact(facts, "customer_commitment", "客户承诺", commitment_line, group="write")
    if not _add_follow_time_fact(facts, preview):
        follow_time = follow_override or preview.next_follow_time_text or preview.next_follow_time
        _add_fact(facts, "next_follow_time", "跟进时间", follow_time, group="write")
    legacy_label = preview.channel_status_label or ""
    status_label = (
        "历史"
        if not editable and preview.activity_kind
        else ("已识别" if legacy_label in _LEGACY_ORIGINS else preview.channel_status_label)
    )
    options = [
        InteractionOption(value=kind, label=_KIND_LABELS[kind])
        for kind in preview.channel_options
        if editable and kind in _KIND_LABELS
    ]
    _add_fact(
        facts,
        "activity_kind",
        "活动类型",
        kind_label,
        group="activity_kind",
        status_label=status_label,
        source=_kind_source(preview, legacy_label),
        options=options,
    )
    comparison = preview.comparison
    if comparison:
        _add_fact(facts, "change_summary", "具体变化", comparison.summary, group="context")
        _add_fact(
            facts, "comparison_current", "本次原话", comparison.current.quote,
            group="context", source="本次记录原话",
        )
        previous_source = " · ".join(
            part for part in (comparison.previous.source_type, comparison.previous.occurred_at) if part
        )
        _add_fact(
            facts, "comparison_previous", "历史来源摘要", comparison.previous.quote,
            group="context", source=previous_source,
        )
    elif preview.context_evidence:
        evidence = [
            " · ".join(part for part in (item.source_type, item.occurred_at, item.summary) if part)
            for item in preview.context_evidence[:3]
        ]
        _add_fact(facts, "context_evidence", "历史来源摘要", "；".join(evidence), group="context")
    if preview.opportunity_name:
        stage = f" · {preview.opportunity_stage}" if preview.opportunity_stage else ""
        _add_fact(facts, "opportunity", "参考商机", f"{preview.opportunity_name}{stage}", group="context")
    notices = list(dict.fromkeys(
        text for value in (preview.context_status, preview.change_summary, *preview.context_notices)
        if (text := _plain(value))
    ))
    _add_fact(facts, "context_status", "参考说明", "；".join(notices), group="context")
    _add_fact(facts, "ignored_noise", "已忽略", preview.ignored_noise_summary, group="context")
    _add_fact(facts, "score", "内容质量", f"{preview.score} / 100", group="score")
    _add_fact(facts, "score_reason", "评分依据", preview.score_reason, group="score")
    # At most ten business/type facts, three comparison facts and five detail facts.
    # Optional notices share one fact; no terminal slice may discard frozen business data.
    return facts


# Persisted previews carry the pre-CRM-78 recognition labels, which named the origin.
_LEGACY_ORIGINS = {"AI 已识别 · 高置信度": "AI", "已识别 · 词表兜底": "词表"}


def _kind_source(preview: ActivityPreview, legacy_label: str) -> str | None:
    """Required kinds quote the original text; recognised kinds keep their origin."""

    if preview.channel_status == "required":
        from app.services.assistant.activity_channel import kind_hint

        return kind_hint(preview.source_content) or preview.channel_source_text
    text = preview.channel_source_text
    origin = _LEGACY_ORIGINS.get(legacy_label)
    if text and origin and not text.startswith(origin):
        return f"{origin} · {text}"
    return text


_WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
_DEFAULT_FOLLOW_UP_HOUR = 9


def _format_temporal_date(at: datetime, *, include_time: bool) -> str:
    label = f"{at.year}年{at.month}月{at.day}日（{_WEEKDAYS[at.weekday()]}）"
    return f"{label}{at:%H:%M}" if include_time else label


def _add_communication_time_fact(facts: list[InteractionConfirmationFact], content_json: dict[str, object]) -> None:
    bundle = content_json.get("temporal_evidence")
    if not isinstance(bundle, dict) or bundle.get("version") != "temporal-evidence-v1":
        return
    raw_mentions = bundle.get("mentions")
    if not isinstance(raw_mentions, list):
        return
    from app.services.assistant.temporal_evidence import StoredMention

    for raw in raw_mentions:
        mention = StoredMention.model_validate(raw)
        if not mention.communication_time or mention.state != "ACTIVE" or mention.resolved_at is None:
            continue
        _add_fact(
            facts,
            "communication_time",
            "沟通时间",
            _format_temporal_date(mention.resolved_at, include_time=mention.granularity == "DATETIME"),
            group="write",
            source=f"原话：“{_plain(mention.raw_text)}”",
        )
        return


def _follow_time_source(preview: ActivityPreview, raw: str) -> str | None:
    parts = [f"原话：“{raw}”"] if raw else []
    bundle = preview.content_json.get("temporal_evidence")
    if isinstance(bundle, dict) and isinstance(bundle.get("mentions"), list):
        from app.services.assistant.temporal_evidence import StoredMention

        mentions = [StoredMention.model_validate(item) for item in bundle["mentions"]]
        primary_id = bundle.get("primary_action_id")
        candidates = [
            item
            for item in mentions
            if item.state == "ACTIVE"
            and item.role == "SALES_FOLLOW_UP"
            and item.correction_of
            and item.resolved_at is not None
            and preview.next_follow_time is not None
            and item.resolved_at.date().isoformat() == preview.next_follow_time[:10]
            and (primary_id is None or item.action_id == primary_id)
        ]
        if len(candidates) == 1:
            current = candidates[0]
            previous = next((item for item in mentions if item.mention_id == current.correction_of), None)
            if previous is not None and previous.resolved_at is not None:
                parts.append(
                    f"已将当前动作日期从 {previous.resolved_at.year}年{previous.resolved_at.month}月"
                    f"{previous.resolved_at.day}日"
                    f"改为 {current.resolved_at.year}年{current.resolved_at.month}月{current.resolved_at.day}日。"
                )
    return "；".join(parts) or None


def _add_follow_time_fact(facts: list[InteractionConfirmationFact], preview: ActivityPreview) -> bool:
    """Show the frozen write instant itself; the spoken phrase is only its evidence."""

    if preview.next_follow_time is None or preview.next_follow_time_granularity not in {"DATE", "DATETIME"}:
        return False
    try:
        at = datetime.fromisoformat(preview.next_follow_time)
    except ValueError:
        return False
    defaulted = preview.next_follow_time_granularity == "DATE" and (at.hour, at.minute, at.second) == (
        _DEFAULT_FOLLOW_UP_HOUR,
        0,
        0,
    )
    raw = _plain(preview.next_follow_time_text or "")
    _add_fact(
        facts,
        "next_follow_time",
        "跟进时间",
        _format_temporal_date(at, include_time=True),
        group="write",
        status_label="默认时刻" if defaulted else None,
        source=_follow_time_source(preview, raw),
    )
    return True


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
    hint: str | None = None,
    submitted: str | None = None,
) -> InteractionBlock:
    settled = submitted is not None
    return InteractionBlock(
        id="b_interaction_1",
        type="interaction",
        interaction_id=_interaction_id(message),
        interaction_type="choice",
        business_action=business_action,
        state="ACTIVE" if active else "SUBMITTED" if settled else "READ_ONLY",
        prompt=prompt,
        options=options,
        hint=hint,
        selection_mode="single",
        min_selections=1,
        max_selections=1,
        submit_on_select=True,
        submitted_values={"choice": submitted} if settled and not active else None,
        submit_action_id=action_id if active else None,
    )


def _activity_kind_options(waiting: TaskWaiting) -> list[InteractionOption]:
    """The 7 concrete kinds the server issued with this waiting."""

    source = waiting.candidates or kind_choice_candidates()
    options: list[InteractionOption] = []
    for candidate in source:
        value = candidate.get("id")
        label = candidate.get("label")
        if not isinstance(value, str) or not value or not isinstance(label, str) or not label:
            continue
        description = candidate.get("description")
        group = candidate.get("group")
        options.append(
            InteractionOption(
                value=value,
                label=label,
                description=description if isinstance(description, str) and description else None,
                group=group if isinstance(group, str) and group else None,
            )
        )
    return options


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
    target = waiting.temporal_target
    label = (
        _TEMPORAL_LABELS.get(target.reason, "补充内容")
        if target is not None
        else _FIELD_LABELS.get(field_name, "补充内容")
    )
    placeholder = None
    if target is not None:
        placeholder = {
            "DATE": "例如 2026-10-30",
            "MONTH": "例如 2026 年 12 月",
            "ROLE": "例如 客户完成时间，或我下次联系时间",
            "STATUS": "例如 已经完成，或计划联系",
            "PRIMARY": "请从当前行动中选择主跟进行动",
        }.get(target.reason)
    elif field_name == "temporal_choice":
        placeholder = "请按当前问题补充信息"
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
    return ActionResultBlock(
        id="b_result_1",
        type="action_result",
        action_id=_clip(message.id, 128),
        status="SUCCESS",
        title="活动已写入",
        message=_result_message(message),
    )


def _accepted_value(field: object) -> str:
    status = getattr(field, "status", None)
    value = getattr(field, "value", None)
    if status != "ACCEPTED":
        return ""
    return _plain(value) if isinstance(value, str) else ""


def _result_message(message: ConversationMessage) -> str:
    """Facts already on the write snapshot. Never a second success sentence."""

    task = message.task
    if task is None:
        return "客户活动"
    lines: list[str] = []
    customer = _accepted_value(task.draft.customer)
    if customer:
        lines.append(f"客户：{customer}")
    kind = _KIND_LABELS.get(task.activity_kind or "")
    if kind:
        lines.append(f"活动类型：{kind}")
    next_action = _accepted_value(task.draft.next_action)
    if next_action:
        lines.append(f"下一步：{next_action}")
    return "\n".join(lines) if lines else "客户活动"


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
