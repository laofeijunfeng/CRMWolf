"""Project one assistant conversation message into crm.agent.ui.v1.

The assistant task remains the authority. This module only builds the read
model the Web UI is allowed to render.
"""
# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import TYPE_CHECKING, Literal, NamedTuple, TypeGuard, cast

from pydantic import ValidationError

from app.schemas.assistant_conversation import (
    ConversationBoundary,
    ConversationDispositionProjection,
    ConversationLink,
    ConversationMessage,
    ConversationProjection,
)
from app.services.agent.query.schemas import EntityRef
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
from app.services.assistant.activity_edit import activity_edit_time
from app.services.assistant.entity_forms import ACTIONS as ENTITY_ACTIONS
from app.services.assistant.entity_forms import module_for as entity_module_for
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
from app.utils.public_id import is_follow_up_task_public_id, is_opportunity_public_id

if TYPE_CHECKING:
    from app.schemas.assistant import AssistantTaskView, ProfileProposalRowView
    from app.services.assistant.contracts import (
        ActivityPreview,
        ProposalCandidate,
        TaskDraft,
        TaskWaiting,
    )

_RAW_HTML_RE = re.compile(r"<(?:[A-Za-z][^>]*|/[A-Za-z][^>]*|![^>]*|\?[^>]*)>")
_FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_CUSTOMER_PUBLIC_ID_RE = re.compile(r"cus_[0-9a-f]{32}")
_UNAVAILABLE = "这条结果暂时无法显示"
_DEFAULT_VISIBLE_CANDIDATES = 10
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
_PROPOSAL_LABELS = {
    "opportunity_stage": "推进商机",
    "opportunity_create": "创建商机",
    "opportunity_lose": "标记商机输单",
    "follow_up_task_create": "创建跟进任务",
    # Retired kinds stay renderable: stored receipts still carry them. The disposition writes `follow_up_task`.
    "customer_fact": "写入客户事实",
    "follow_up_task": "更新跟进任务",
}
_FORM_FIELDS = {
    "create_opportunity_proposal": frozenset({
        "opportunity_name", "total_amount", "user_count", "license_type", "subscription_years",
        "purchase_type", "decision_maker_count", "expected_closing_date", "procurement_method_id",
        "stage_id", "owner_id", "product_public_id", "product_module_public_ids",
    }),
    "edit_confirmation": frozenset({
        "communication_time", "channel_kind", "internal_participants", "customer_participants",
        "summary", "next_action", "next_follow_time",
    }),
}


def finalize_assistant_ui(
    messages: list[ConversationMessage],
    *,
    focused_task: AssistantTaskView | None,
    pending_choice: ConversationBoundary | None,
) -> None:
    """Attach UI envelopes, except for user text and host-only completion boundaries."""

    _split_activity_disposition(messages)
    _ensure_current_waiting(messages, focused_task)
    _normalize_task_completions(messages)
    live_id = _live_waiting_message_id(messages, focused_task)
    submitted_kind = _resolved_activity_kind(focused_task)
    _project_coverage(messages, live_id)
    handled = _handled_forms(messages)
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
        same_task = (
            focused_task is not None and message.task is not None and message.task.public_id == focused_task.public_id
        )
        try:
            message.ui = project_assistant_message(
                message,
                active_waiting=active_waiting,
                active_boundary=active_boundary,
                submitted_kind=submitted_kind if same_task else None,
                handled=handled.get(message.id),
            )
        except (ValidationError, ValueError):
            message.ui = _failure_envelope(message, code="INTERNAL_ERROR", retryable=False, text=_UNAVAILABLE)
        message.links = _message_links(message)


def _message_links(message: ConversationMessage) -> list[ConversationLink]:
    """In-app destinations next to the card; the host owns the route for each page."""

    links = list(message.links)
    task = message.task
    if (
        message.ui is None or task is None or message.outcome == "failure" or message.error_code is not None
        or not isinstance(task.follow_up_disposition, dict)
    ):
        return links
    if not any(
        block.type == "interaction" and block.presentation == "OPEN_FOLLOW_UP_DISPOSITION"
        for block in message.ui.blocks
    ):
        return links
    customer = task.follow_up_disposition.get("customer_public_id")
    link = ConversationLink(
        page="follow_up_tasks", label="在客户追踪页处理",
        customer_public_id=customer if isinstance(customer, str) and customer else None,
    )
    # Re-projection must be stable, so the same destination is never appended twice.
    if link not in links:
        links.append(link)
    return links


def _is_task_completion(message: ConversationMessage) -> bool:
    """Only this message's authoritative snapshot can establish normal completion."""
    return (
        message.role == "assistant"
        and message.task is not None
        and message.task.status == "COMPLETED"
        and message.task.waiting is None
        and message.boundary is None
        and (
            message.outcome in {"task_completed", "activity_written", "follow_up_disposition"}
            or message.proposal_receipt is not None
            or message.entity_receipt is not None
        )
        and message.outcome != "failure"
        and message.error_code is None
    )


def _is_completion_only(message: ConversationMessage) -> bool:
    return (
        _is_task_completion(message)
        and message.outcome not in {"activity_written", "follow_up_disposition"}
        and message.proposal_receipt is None
        and message.entity_receipt is None
    )


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
            and (
                message.outcome in {"activity_written", "follow_up_disposition"}
                or message.proposal_receipt is not None
                or message.entity_receipt is not None
            )
            and message.error_code is None
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


def _split_activity_disposition(messages: list[ConversationMessage]) -> None:
    """Activity acceptance and task disposition have independent coverage lifetimes."""
    known = {message.id for message in messages}
    expanded: list[ConversationMessage] = []
    for message in messages:
        expanded.append(message)
        if message.outcome != "activity_written" or _disposition_items(message) is None:
            continue
        identifier = f"{message.id}:disposition"
        if identifier not in known:
            expanded.append(message.model_copy(update={
                "id": identifier, "outcome": "follow_up_disposition", "projection": None, "ui": None,
                "proposal_receipt": None, "entity_receipt": None,
                "text": "历史跟进任务",
            }))
            known.add(identifier)
    messages[:] = expanded


def _carrier_rank(message: ConversationMessage) -> tuple[int, int, str, str]:
    disposition = message.projection.disposition if message.projection else None
    return (
        {"NONE": 0, "CURRENT": 1, "FINAL": 2}.get(disposition.card_role, 0) if disposition else 0,
        message.task.version if message.task else 0, message.at, message.id,
    )


def _identified_disposition_items(message: ConversationMessage) -> dict[str, dict[str, object]] | None:
    items = _disposition_items(message)
    if not items:
        return None
    identified: dict[str, dict[str, object]] = {}
    task_ids: set[str] = set()
    for item in items:
        item_id, task_id = item.get("item_id"), item.get("task_public_id")
        if (
            not isinstance(item_id, str) or not item_id.strip() or item_id in identified
            or not isinstance(task_id, str) or not task_id.strip() or task_id in task_ids
        ):
            return None
        identified[item_id] = item
        task_ids.add(task_id)
    return identified


def _covers_disposition(carrier: ConversationMessage, source: ConversationMessage) -> bool:
    latest = _identified_disposition_items(carrier)
    source_items = _identified_disposition_items(source)
    if latest is None or source_items is None:
        return False
    for item_id, item in source_items.items():
        target = latest.get(item_id)
        if target is None or item["task_public_id"] != target["task_public_id"]:
            return False
        if item.get("state") in _SETTLED_LABELS and any(
            item.get(key) != target.get(key) for key in ("state", "result_title", "result_message")
        ):
            return False
        if any(item.get(key) and item.get(key) != target.get(key) for key in ("evidence_quote", "evidence_reason")):
            return False
    return True


def _project_coverage(messages: list[ConversationMessage], live_id: str | None) -> None:
    activities: dict[str, list[ConversationMessage]] = {}
    rounds: dict[tuple[str, str], list[ConversationMessage]] = {}
    for message in messages:
        prior = message.projection
        if prior is not None and prior.visibility == "COVERED":
            prior.visibility = "VISIBLE"
            prior.covered_by = None
        if message.role != "assistant" or message.outcome == "failure" or message.error_code:
            continue
        message.projection = None
        if message.outcome == "activity_written":
            activity_id = prior.activity_public_id if prior else None
            if activity_id is None and message.task:
                activity_id = next((receipt.public_id for receipt in message.task.committed
                                    if receipt.kind == "customer_activity"), None)
            if activity_id:
                message.projection = ConversationProjection(activity_public_id=activity_id)
                activities.setdefault(activity_id, []).append(message)
            continue
        items = _disposition_items(message)
        task = message.task
        payload = task.follow_up_disposition if task else None
        if items is None or task is None or not isinstance(payload, dict):
            continue
        batch_id = payload.get("batch_id")
        if not isinstance(batch_id, str) or not batch_id.strip() or len(items) > 100:
            continue
        role: Literal["NONE", "CURRENT", "FINAL"] = "NONE"
        if payload.get("status") == "DONE":
            role = "FINAL"
        elif message.id == live_id or (payload.get("settling") is True and message.outcome == "follow_up_disposition"):
            role = "CURRENT"
        message.projection = ConversationProjection(
            visibility="FALLBACK_RECEIPT" if role == "NONE" else "VISIBLE",
            disposition=ConversationDispositionProjection(
                task_public_id=task.public_id, batch_id=batch_id,
                item_ids=[item["item_id"] for item in items
                          if isinstance(item.get("item_id"), str) and item["item_id"].strip()],
                card_role=role, version=task.version,
            ),
        )
        rounds.setdefault((task.public_id, batch_id), []).append(message)
    for group in activities.values():
        carrier = max(group, key=_carrier_rank)
        for message in group:
            if (
                message is not carrier
                and message.projection
                and message.proposal_receipt is None
                and message.entity_receipt is None
                and message.id != live_id
            ):
                message.projection.visibility = "COVERED"
                message.projection.covered_by = carrier.id
    for group in rounds.values():
        full = [message for message in group if message.projection and message.projection.disposition
                and message.projection.disposition.card_role != "NONE"]
        if not full:
            continue
        carrier = max(full, key=_carrier_rank)
        for message in group:
            if (
                message is not carrier
                and message.projection
                and message.proposal_receipt is None
                and message.entity_receipt is None
                and message.id != live_id
                and _covers_disposition(carrier, message)
            ):
                message.projection.visibility = "COVERED"
                message.projection.covered_by = carrier.id


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
    handled: HandledForm | None = None,
) -> AgentUIEnvelope | None:
    """Build Web-visible blocks, or leave a normal completion to the host."""

    if message.outcome == "failure" or message.error_code is not None:
        return _project_failure(message)
    if _is_completion_only(message):
        return None
    result = _result_block(message)
    try:
        return _project_message_blocks(
            message, result=result, active_waiting=active_waiting, active_boundary=active_boundary,
            submitted_kind=submitted_kind, handled=handled,
        )
    except (ValidationError, ValueError):
        return _failure_envelope(message, code="INTERNAL_ERROR", retryable=False, text=_UNAVAILABLE, result=result)


def _project_message_blocks(
    message: ConversationMessage,
    *,
    result: ActionResultBlock | None,
    active_waiting: bool,
    active_boundary: bool,
    submitted_kind: str | None,
    handled: HandledForm | None = None,
) -> AgentUIEnvelope:
    prefix = (result,) if result is not None else ()
    if message.outcome == "proposal_unavailable":
        blocks = (*prefix, NoticeBlock(id="b_notice_1", type="notice", tone="warning", code="PROPOSAL_UNAVAILABLE",
                                       text=_plain(message.text) or _UNAVAILABLE))
        return _envelope(message, blocks, route="WORKFLOW")
    if (
        message.projection is not None
        and message.projection.disposition is not None
        and message.projection.disposition.card_role == "NONE"
        and _disposition_items(message) is not None
    ):
        return _envelope(message, (*prefix, *_disposition_receipt_blocks(message)), route="WORKFLOW")
    waiting = message.task.waiting if message.task is not None else None
    if message.outcome == "activity_written" and waiting is not None and waiting.type == "FOLLOW_UP_DISPOSITION":
        return _envelope(message, prefix, route="WORKFLOW")
    disposition = _disposition_blocks(message, active_waiting=active_waiting)
    if disposition is not None:
        return _envelope(message, (*prefix, *disposition), route="WORKFLOW")
    if message.boundary is not None:
        return _envelope(message, (*prefix, _boundary_block(message, active=active_boundary)), route="CLARIFY")
    if waiting is not None:
        blocks = _waiting_blocks(message, waiting, active=active_waiting, submitted_kind=submitted_kind,
                                 include_prose=result is None, handled=handled)
        return _envelope(message, (*prefix, *blocks), route="WORKFLOW")
    if prefix:
        return _envelope(message, prefix, route="WORKFLOW")
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


def _disposition_receipt_blocks(message: ConversationMessage) -> tuple[NoticeBlock, ...]:
    """Keep server-rendered, non-interactive facts available outside the carrier's page."""
    details = [_plain(message.text) or "历史跟进任务"]
    for item in _disposition_items(message) or []:
        label = _receipt_label(item) or "待处理"
        title = item.get("title")
        parts = [f"{label} · {_plain(title) if isinstance(title, str) else '跟进任务'}"]
        for key, prefix in (("result_message", ""), ("evidence_quote", "依据："), ("evidence_reason", "")):
            value = item.get(key)
            if isinstance(value, str) and value:
                parts.append(f"{prefix}{_plain(value)}")
        details.append("；".join(parts))
    text = "\n".join(details)
    # The existing batch allows 100 items. Preserve their facts without exceeding
    # the per-notice 10k contract (the envelope supports 30 blocks).
    return tuple(
        NoticeBlock(
            id=f"b_notice_disposition_receipt_{index // 10000}",
            type="notice", tone="info", title="历史跟进任务", text=text[index:index + 10000],
        )
        for index in range(0, len(text), 10000)
    )


def _is_disposition_state(
    state: str | None,
) -> TypeGuard[Literal["current", "waiting", "complete", "hold", "skip", "failed", "unknown"]]:
    return state in {"current", "waiting", *_SETTLED_LABELS}


def _disposition_blocks(
    message: ConversationMessage, *, active_waiting: bool,
) -> tuple[NoticeBlock | InteractionBlock, ...] | None:
    task = message.task
    if task is None or not isinstance(task.follow_up_disposition, dict):
        return None
    payload = task.follow_up_disposition
    waiting = task.waiting
    showing = message.outcome == "follow_up_disposition" or (
        waiting is not None and waiting.type == "FOLLOW_UP_DISPOSITION"
    )
    if not showing:
        return None
    items = payload.get("items")
    status = _string(payload.get("status"))
    if not isinstance(items, list):
        return None
    if status in {"OVERFLOW", "QUERY_FAILED"} or not items:
        tone: Literal["warning", "info"] = "warning" if status in {"OVERFLOW", "QUERY_FAILED"} else "info"
        notice = NoticeBlock(
            id="b_notice_disposition",
            type="notice",
            tone=tone,
            title="历史跟进任务",
            text=_clip(_plain(message.text) or _UNAVAILABLE, 10000),
        )
        return (notice,)
    rows: list[OpenFollowUpDispositionCardItem] = []
    handled = 0
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError("malformed disposition item")
        item_id = raw.get("item_id")
        title = raw.get("title")
        if not isinstance(item_id, str) or not item_id.strip() or not isinstance(title, str) or not title.strip():
            raise ValueError("malformed disposition identity")
        state = _string(raw.get("state"))
        if not _is_disposition_state(state):
            raise ValueError("malformed disposition state")
        if state == "failed" and raw.get("failure_code") == "ALREADY_HANDLED":
            handled += 1
        rows.append(OpenFollowUpDispositionCardItem(
            item_id=item_id,
            title=_clip(title, 255),
            owner_line=_clip(_owner_line(raw.get("owner_line")) or "", 300) or None,
            related=bool(raw.get("related")),
            evidence_quote=_clip(raw["evidence_quote"], 255) if isinstance(raw.get("evidence_quote"), str) else None,
            evidence_reason=_clip(raw["evidence_reason"], 500) if isinstance(raw.get("evidence_reason"), str) else None,
            state=state,
            result_title=_clip(raw["result_title"], 80) if isinstance(raw.get("result_title"), str) else None,
            result_message=_clip(raw["result_message"], 500) if isinstance(raw.get("result_message"), str) else None,
        ))
    active = (
        active_waiting
        and waiting is not None
        and waiting.type == "FOLLOW_UP_DISPOSITION"
        and status == "ACTIVE"
        and payload.get("settling") is not True
    )
    options = [
        InteractionOption(value=row.item_id, label=_clip(row.title, 200),
                          disabled=not active or row.state not in {"current", "waiting"})
        for row in rows
    ]
    prompt = _plain(waiting.prompt) if waiting is not None and waiting.type == "FOLLOW_UP_DISPOSITION" else ""
    summary = _disposition_summary(rows, handled, payload.get("suppression_status")) if status == "DONE" else (
        "历史跟进任务结果待核对" if payload.get("settling") is True else ""
    )
    # Batches frozen before the count existed still fold at the default page size.
    visible_count = payload.get("visible_count")
    if not isinstance(visible_count, int) or not 1 <= visible_count <= len(rows):
        visible_count = min(_DEFAULT_VISIBLE_CANDIDATES, len(rows))
    interaction = InteractionBlock(
        id="b_interaction_1",
        type="interaction",
        interaction_id=_interaction_id(message),
        interaction_type="choice",
        business_action="settle_follow_up_disposition",
        presentation="OPEN_FOLLOW_UP_DISPOSITION",
        state="ACTIVE" if active else "READ_ONLY",
        prompt=prompt or "历史跟进任务",
        hint=_clip(summary, 400) or None,
        options=options,
        disposition_items=rows,
        selection_mode="multiple",
        min_selections=0,
        max_selections=len(rows),
        submit_on_select=False,
        submit_action_id=_action_id(waiting) if active and waiting is not None else None,
        secondary_action=InteractionOption(value="suppress_week", label="本周不再提示") if active else None,
        disposition_visible_count=visible_count,
    )
    return (interaction,)


def _disposition_summary(
    rows: list[OpenFollowUpDispositionCardItem], handled: int, suppression: object,
) -> str:
    labels = (("complete", "完成"), ("hold", "保持"), ("skip", "不管了"),
              ("unknown", "结果待核对"))
    parts = [f"{count} 条{label}" for state, label in labels if (count := sum(row.state == state for row in rows))]
    failed = sum(row.state == "failed" for row in rows) - handled
    if handled:
        parts.append(f"{handled} 条已被处理")
    if failed:
        parts.append(f"{failed} 条未能处理")
    if suppression == "applied":
        parts.append("本周不再提示此客户的历史任务")
    elif suppression == "stale":
        parts.append("客户关联已失效，未设置本周免提示")
    return "，".join(parts)


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
    include_prose: bool = True,
    handled: HandledForm | None = None,
) -> tuple[TextBlock | NoticeBlock | InteractionBlock, ...]:
    prompt = _plain(waiting.prompt) or _plain(message.text) or _UNAVAILABLE
    interaction = _waiting_interaction(message, waiting, prompt=prompt, active=active, submitted_kind=submitted_kind,
                                       handled=handled)
    blocks: list[TextBlock | NoticeBlock | InteractionBlock] = []
    prose = _plain(message.text)
    # An entity form's title already says what is being created; the prose would repeat it.
    if include_prose and prose and prose != prompt and waiting.type != "ENTITY_FORM":
        blocks.append(_text_block(prose))
    if message.task is not None and waiting.type == "FIELD":
        notice = _accepted_notice(message.task.draft)
        if notice is not None:
            blocks.append(notice)
    blocks.append(interaction)
    return tuple(blocks)


def _form_interaction(
    message: ConversationMessage,
    waiting: TaskWaiting,
    *,
    prompt: str,
    active: bool,
    action_id: str,
    handled: HandledForm | None = None,
) -> InteractionBlock:
    allowed: frozenset[str]
    subject: EntityRef | None = None
    summary: str | None = None
    if waiting.type == "ENTITY_FORM":
        kind = (waiting.field or "").removeprefix("entity:")
        if kind not in ENTITY_ACTIONS:
            raise ValueError("missing frozen form")
        if not active and handled is not None:
            summary = _entity_form_summary(entity_module_for(kind).LABEL, handled, kind=kind)
        business_action = ENTITY_ACTIONS[kind]
        expected_field = waiting.field
        allowed = entity_module_for(kind).FIELD_KEYS
        entity_draft = message.task.draft.entity if message.task is not None else None
        if active and kind != "customer_create" and entity_draft is not None:
            subject = _receipt_entity(entity_draft.customer_public_id,
                                      customer_name=_plain(entity_draft.customer_name or ""))
    else:
        proposal = waiting.type == "PROPOSAL_FORM"
        business_action = "create_opportunity_proposal" if proposal else "edit_confirmation"
        expected_field = "proposal:opportunity_create" if proposal else "activity_write"
        allowed = _FORM_FIELDS[business_action]
    if waiting.field != expected_field or waiting.form_revision is None or not waiting.form_fields:
        raise ValueError("missing frozen form")
    fields = [InteractionField.model_validate(raw) for raw in waiting.form_fields]
    by_key = {field.key: field for field in fields}
    if len(by_key) != len(fields) or not by_key.keys() <= allowed:
        raise ValueError("duplicate or unsupported form field")
    for field in fields:
        if field.depends_on_key is not None:
            parent = by_key.get(field.depends_on_key)
            if parent is None or parent.field_type != "select" or parent.depends_on_key is not None:
                raise ValueError("invalid form dependency")
            values = {option.value for option in parent.options}
            if any(option.depends_on_value not in values for option in field.options):
                raise ValueError("unknown dependent option")
    return InteractionBlock(
        id="b_interaction_1",
        type="interaction",
        interaction_id=_interaction_id(message),
        interaction_type="form",
        business_action=business_action,
        state="ACTIVE" if active else "READ_ONLY",
        # A handled entity form keeps only what still holds: the outcome and the record's name.
        prompt=summary or prompt,
        subject=subject,
        fields=fields,
        hint=None if (waiting.type == "ENTITY_FORM" and not active) else _clip(_plain(waiting.hint), 400) or None,
        allow_cancel=active,
        submit_action_id=action_id if active else None,
    )


def _waiting_interaction(
    message: ConversationMessage,
    waiting: TaskWaiting,
    *,
    prompt: str,
    active: bool,
    submitted_kind: str | None = None,
    handled: HandledForm | None = None,
) -> InteractionBlock:
    action_id = _action_id(waiting)
    if waiting.type in {"PROPOSAL_FORM", "CONFIRMATION_EDIT", "ENTITY_FORM"}:
        return _form_interaction(message, waiting, prompt=prompt, active=active, action_id=action_id,
                                 handled=handled)
    if waiting.type == "FOLLOW_UP_DISPOSITION":
        raise ValueError("missing frozen disposition batch")
    if waiting.type in {"ENTITY_DEFERRED", "PROFILE_PROPOSALS"}:
        # Both waits take only an issued choice; typed text is rejected, so never offer a text box.
        deferred = waiting.type == "ENTITY_DEFERRED"
        options = _candidate_options(waiting.candidates) if deferred else _profile_options(message, waiting)
        if not options:
            raise ValueError("missing issued choices")
        return _choice(
            message,
            prompt=prompt,
            active=active,
            action_id=action_id,
            business_action="resume_entity_draft" if deferred else "settle_profile_proposals",
            options=options,
        )
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
                else "select_intent"
                if waiting.field == "intent"
                else "select_contact"
                if waiting.field == "contact_select"
                else "resolve_contact_conflict"
                if waiting.field == "contact_mobile_conflict"
                else "select_customer"
            )
            return _choice(
                message,
                prompt=prompt,
                active=active,
                action_id=action_id,
                business_action=business_action,
                options=options,
                hint=waiting.hint,
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
        facts = _proposal_facts(payload.candidate, message)
        confirm_label = "确认"
    edit_enabled = active and payload.kind == "activity_write"
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
                disabled=not active or confirm_disabled,
                description="先选择活动类型" if confirm_disabled else None,
            ),
            InteractionOption(value="cancel", label="取消", disabled=not active),
        ],
        selection_mode="single",
        submit_on_select=active,
        submit_action_id=action_id if active else None,
        secondary_action=InteractionOption(value="request_edit", label="修改内容") if edit_enabled else None,
        cancel_reasons=[
            InteractionOption(value="wrong_customer", label="客户不对"),
            InteractionOption(value="wrong_content", label="内容不对"),
            InteractionOption(value="should_not_record", label="不该记录"),
            InteractionOption(value="other", label="其他"),
        ] if edit_enabled else [],
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

    try:
        commitment_line, follow_override = confirmation_time_labels(preview.content_json)
    except ValidationError:
        commitment_line, follow_override = None, None
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
    override = activity_edit_time(content_json, "communication_time")
    if override is not None:
        at, granularity = override
        if at is not None:
            _add_fact(
                facts,
                "communication_time",
                "沟通时间",
                _format_temporal_date(at, include_time=granularity == "DATETIME"),
                group="write",
                source=None,
            )
            return
        # A cleared override restores the original evidence, exactly as the write does.

    bundle = content_json.get("temporal_evidence")
    if not isinstance(bundle, dict) or bundle.get("version") != "temporal-evidence-v1":
        return
    raw_mentions = bundle.get("mentions")
    if not isinstance(raw_mentions, list):
        return
    from app.services.assistant.temporal_evidence import StoredMention

    for raw in raw_mentions:
        try:
            mention = StoredMention.model_validate(raw)
        except ValidationError:
            continue
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

        mentions: list[StoredMention] = []
        for item in bundle["mentions"]:
            try:
                mentions.append(StoredMention.model_validate(item))
            except ValidationError:
                continue
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


def _proposal_facts(candidate: ProposalCandidate, message: ConversationMessage) -> list[InteractionConfirmationFact]:
    facts: list[InteractionConfirmationFact] = []
    _add_fact(facts, "proposal", "建议", _PROPOSAL_LABELS[candidate.kind])
    payload = candidate.payload
    if candidate.kind == "opportunity_stage":
        _add_fact(facts, "opportunity_name", "商机", _string(payload.get("opportunity_name")))
        destination = _string(payload.get("stage_name"))
        current = _string(payload.get("current_stage_name"))
        if destination:
            _add_fact(facts, "stage_transition", "阶段", f"{current or '未开始'} → {destination}")
    elif candidate.kind == "opportunity_lose":
        _add_fact(facts, "opportunity_name", "商机", _string(payload.get("opportunity_name")))
        _add_fact(facts, "loss_reason", "输单原因", _string(payload.get("loss_reason")))
    elif candidate.kind == "follow_up_task_create":
        _add_fact(facts, "action", "任务标题", _string(payload.get("action")))
        due = _string(payload.get("due_date"))
        if due and candidate.due_date_granularity in {"DATE", "DATETIME"}:
            _add_fact(facts, "due_date", "截止时间", due)
        _add_fact(facts, "owner", "负责人", _string(payload.get("owner_name")) or _string(payload.get("owner")))
    elif candidate.kind == "opportunity_create" and message.task is not None:
        _add_fact(facts, "customer", "客户", _accepted_value(message.task.draft.customer))
    _add_fact(facts, "evidence", "证据", candidate.evidence_quote, group="context")
    return facts


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


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


_PROFILE_ROW_STATES: dict[str, str] = {"skip": "不保存", "failed": "没能打开表单"}


def _profile_row_state(row: ProfileProposalRowView) -> str:
    if row.decision != "go":
        return _PROFILE_ROW_STATES[row.decision]
    if row.child_receipt is not None:
        saved = "已存在" if row.child_receipt.outcome == "existing" else "已保存"
        return f"{saved}，待审批" if row.child_receipt.approval_phase == "pending_review" else saved
    if row.child_status == "ACTIVE":
        return "草稿在「待补充」" if row.child_waiting_type == "ENTITY_DEFERRED" else "表单填写中"
    return "已取消" if row.child_status == "CANCELLED" else "没有保存"


def _profile_options(message: ConversationMessage, waiting: TaskWaiting) -> list[InteractionOption]:
    """One group per profile row in utterance order: pending rows take 去补充/不保存, settled rows show their child."""

    rows = message.task.profile_proposals if message.task is not None else None
    issued = {str(candidate.get("id")) for candidate in waiting.candidates}
    options: list[InteractionOption] = []
    for row in rows or []:
        # The model's summary may already open with the kind (e.g. "开票抬头 + colon"); name it once.
        summary = row.summary.removeprefix(f"{row.label}：").removeprefix(f"{row.label}:").strip()
        group = _clip(f"{row.label}：{summary or row.summary}", 40)
        if row.decision == "pending":
            go, skip = f"go:{row.index}", f"skip:{row.index}"
            if go not in issued or skip not in issued:
                raise ValueError("profile row without issued choices")
            options += [
                InteractionOption(value=go, label="去补充", group=group, description=_clip(f"原话：{row.quote}", 1000)),
                InteractionOption(value=skip, label="不保存", group=group),
            ]
        else:
            options.append(InteractionOption(
                value=f"row:{row.index}", label=_profile_row_state(row), group=group, disabled=True,
            ))
    if options and "none" in issued:
        options.append(InteractionOption(value="none", label="都不需要", group="全部"))
    return options


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


def _result_block(message: ConversationMessage) -> ActionResultBlock | None:
    """Use the event-local proposal result, never a cumulative committed proposal."""
    if message.outcome == "failure" or message.error_code is not None:
        return None
    proposal = message.proposal_receipt
    customer_name = _accepted_value(message.task.draft.customer) if message.task is not None else ""
    if proposal is not None and proposal.kind in _PROPOSAL_LABELS:
        title, fallback = {
            "opportunity_stage": ("商机阶段已推进", "商机阶段"),
            "opportunity_lose": ("商机已标记输单", "商机输单"),
            "opportunity_create": ("商机已创建", "商机"),
            "follow_up_task_create": ("跟进任务已创建", "跟进任务"),
            "customer_fact": ("客户事实已写入", "客户事实"),
            "follow_up_task": ("跟进任务已更新", "跟进任务"),
        }[proposal.kind]
        if (
            proposal.kind == "opportunity_create"
            and proposal.approval_phase == "pending_review"
            and proposal.approval_id is not None
            and proposal.approval_id > 0
        ):
            title = "商机已创建，待审批"
        detail = _plain(proposal.detail) or (f"客户：{customer_name}" if customer_name else fallback)
        entity = _receipt_entity(
            proposal.customer_public_id,
            customer_name=customer_name,
            opportunity_id=proposal.public_id if proposal.kind.startswith("opportunity_") else None,
            task_id=proposal.public_id if proposal.kind == "follow_up_task_create" else None,
            name=proposal.name,
        )
        subject = _receipt_entity(proposal.customer_public_id, customer_name=customer_name)
    elif message.entity_receipt is not None:
        title, detail, entity, subject = _entity_result(message)
    elif message.outcome == "activity_written":
        title, detail = "活动已写入", _result_message(message)
        activity_id = message.projection.activity_public_id if message.projection else None
        activity = next((
            receipt for receipt in message.task.committed
            if receipt.kind == "customer_activity" and (activity_id is None or receipt.public_id == activity_id)
        ), None) if message.task else None
        entity = (
            _receipt_entity(activity.customer_public_id, customer_name=customer_name, tab="activities")
            if activity else None
        )
        subject = entity
    else:
        return None
    return ActionResultBlock(
        id="b_result_1",
        type="action_result",
        action_id=_clip(message.id, 128),
        status="SUCCESS",
        title=title,
        message=_clip(detail, 10000),
        entity_ref=entity,
        subject=subject,
    )


def _receipt_entity(
    customer_id: str | None, *, customer_name: str, opportunity_id: str | None = None,
    task_id: str | None = None, name: str | None = None, tab: str | None = None,
) -> EntityRef | None:
    """Link a receipt to its record; the link only exists when bound to the owning customer."""
    if customer_id is None or not _CUSTOMER_PUBLIC_ID_RE.fullmatch(customer_id):
        return None
    label = _clip(name, 200) if name else ""
    if opportunity_id is not None:
        if not is_opportunity_public_id(opportunity_id):
            return None
        return EntityRef(
            ref_id=f"opportunity:{opportunity_id}", resource="opportunity", public_id=opportunity_id,
            display_name=label or "商机", attributes={"customer_public_id": customer_id},
        )
    if task_id is not None and is_follow_up_task_public_id(task_id):
        return EntityRef(
            ref_id=f"follow_up_task:{task_id}", resource="follow_up_task", public_id=task_id,
            display_name=label or "跟进任务", attributes={"customer_public_id": customer_id},
        )
    return EntityRef(
        ref_id=f"customer:{customer_id}", resource="customer", public_id=customer_id,
        display_name=_clip(customer_name, 200) or "客户",
        attributes={"customer_tab": tab} if tab else None,
    )


_ENTITY_RESULTS: dict[str, tuple[str, str, str | None]] = {
    "contact_create": ("联系人已保存", "联系人", "contacts"),
    "contact_supplement": ("联系人资料已补充", "联系人", "contacts"),
    "invoice_title_create": ("开票抬头已保存", "开票抬头", "invoice_titles"),
    "deployment_create": ("部署信息已保存", "部署信息", "deployments"),
    "customer_create": ("客户已创建", "客户", None),
    "opportunity_create": ("商机已创建", "商机", None),
}


def _entity_result(message: ConversationMessage) -> tuple[str, str, EntityRef | None, EntityRef | None]:
    """One directly created (or already existing) CRM record, linked on its customer page.

    Returns ``(title, detail, entity_ref, subject)``; ``subject`` is the owning customer.
    """

    receipt = message.entity_receipt
    assert receipt is not None
    title, label, tab = _ENTITY_RESULTS[receipt.kind]
    name = _clip(_plain(receipt.name), 200)
    entity_draft = message.task.draft.entity if message.task is not None else None
    customer_name = (
        name if receipt.kind == "customer_create"
        else _plain(entity_draft.customer_name or "") if entity_draft is not None else ""
    )
    lines = [f"{label}：{name}" if name else label]
    if receipt.kind != "customer_create" and customer_name:
        lines.append(f"客户：{customer_name}")
    if receipt.outcome == "existing":
        title = (
            "联系人资料已存在，未重复写入"
            if receipt.kind == "contact_supplement"
            else f"{label}已存在，未重复创建"
        )
    elif receipt.approval_phase == "pending_review":
        title = f"{title}，待审批"
    if receipt.kind == "contact_supplement" and receipt.summary:
        lines.append(f"补充内容：{_clip(_plain(receipt.summary), 400)}")
    if receipt.kind == "invoice_title_create":
        lines.append("申请开票去发票管理")
    subject = _receipt_entity(receipt.customer_public_id, customer_name=customer_name, tab=tab)
    if receipt.kind == "opportunity_create" and receipt.outcome == "created":
        entity = _receipt_entity(receipt.customer_public_id, customer_name=customer_name,
                                 opportunity_id=receipt.public_id, name=name)
    else:
        entity = subject
    return title, "\n".join(lines), entity, subject


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
    result: ActionResultBlock | None = None,
) -> AgentUIEnvelope:
    error = ErrorBlock(
        id="b_error_1",
        type="error",
        code=code,
        title="遇到问题" if code == "INTERNAL_ERROR" else "这次没处理成",
        message=text,
        retryable=retryable,
    )
    return _envelope(message, (result, error) if result is not None else (error,), route="WORKFLOW", state="failed")


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
        raw_desc = candidate.get("description")
        description = _clip(_plain(raw_desc), 1000) if isinstance(raw_desc, str) and raw_desc.strip() else None
        options.append(InteractionOption(value=raw_id, label=_clip(label.strip(), 200), description=description))
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


class HandledForm(NamedTuple):
    """The outcome that closed a historical entity form, and the text values it carried."""

    outcome: Literal["submitted", "cancelled", "deferred"]
    values: dict[str, object]


def _handled_forms(messages: list[ConversationMessage]) -> dict[str, HandledForm]:
    """Map each closed entity-form message to its outcome and submitted text values."""

    handled: dict[str, HandledForm] = {}
    for index, message in enumerate(messages):
        waiting = message.task.waiting if message.role == "assistant" and message.task is not None else None
        if waiting is None or waiting.type != "ENTITY_FORM" or message.task is None:
            continue
        later = messages[index + 1:]
        task_id = message.task.public_id
        kind = (waiting.field or "").removeprefix("entity:")
        next_task_idx, next_task_msg = next(
            (
                (offset, item)
                for offset, item in enumerate(later)
                if item.role == "assistant" and item.task is not None and item.task.public_id == task_id
            ),
            (None, None),
        )
        echo_slice = later[:next_task_idx] if next_task_idx is not None else later
        echo_msg = next((item for item in reversed(echo_slice) if item.role == "user"), None)
        echo = _plain(echo_msg.text) if echo_msg is not None else ""
        if not echo and next_task_msg is None:
            continue
        next_task = next_task_msg.task if next_task_msg is not None else None
        next_waiting = next_task.waiting if next_task is not None else None
        if (next_task is not None and next_task.status == "CANCELLED") or echo in {"取消", "算了，不记了"}:
            handled[message.id] = HandledForm(outcome="cancelled", values={})
            continue
        if (next_waiting is not None and next_waiting.type == "ENTITY_DEFERRED") or echo == "稍后补充":
            handled[message.id] = HandledForm(outcome="deferred", values={})
            continue
        if next_task_msg is not None:
            if next_task_msg.outcome == "failure" or next_task_msg.error_code is not None:
                continue
            if next_waiting is not None and next_waiting.type == "ENTITY_FORM" and next_waiting.field == waiting.field:
                continue
            next_entity = next_task.draft.entity if next_task is not None else None
            progressed = (
                next_task_msg.entity_receipt is not None
                or (next_task is not None and next_task.status == "COMPLETED")
                or (next_entity is not None and kind in next_entity.submitted)
            )
            if not progressed:
                continue
        elif echo not in {"提交", "提交表单"}:
            continue
        text_fields = [
            (key, raw.get("default_value"))
            for raw in waiting.form_fields or []
            if isinstance(key := raw.get("key"), str) and raw.get("field_type") in {"text", "textarea"}
        ]
        submitted: dict[str, object] | None = None
        for item in later:
            entity = item.task.draft.entity if item.task is not None and item.task.public_id == task_id else None
            if entity is not None and kind in entity.submitted:
                submitted = dict(entity.submitted[kind])
                break
        if submitted is None:
            submitted = dict(text_fields)
        # Form order, so the summary leads with the record's name.
        values = {key: submitted[key] for key, _ in text_fields if key in submitted}
        handled[message.id] = HandledForm(outcome="submitted", values=values)
    return handled


def _entity_form_summary(label: str, handled: HandledForm, *, kind: str = "") -> str:
    action = f"补充{label}" if kind == "contact_supplement" else f"新建{label}"
    if handled.outcome == "cancelled":
        return f"已取消 · {action}"
    if handled.outcome == "deferred":
        return f"稍后补充 · {action}"
    texts = [_clip(_plain(value), 80) for value in handled.values.values() if isinstance(value, str) and value.strip()]
    return " · ".join(["已提交", action, *texts[:2]])

def _live_waiting_message_id(
    messages: list[ConversationMessage],
    focused_task: AssistantTaskView | None,
) -> str | None:
    if focused_task is None or focused_task.status != "ACTIVE" or focused_task.waiting is None:
        return None
    current = focused_task.waiting
    live_id: str | None = None
    for message in messages:
        if message.role != "assistant" or message.outcome == "failure" or message.error_code or message.boundary:
            continue
        task = message.task
        waiting = task.waiting if task is not None else None
        if task is None or waiting is None or task.public_id != focused_task.public_id:
            continue
        if (
            waiting.action_id == current.action_id
            and waiting.expected_version == current.expected_version
            and waiting.form_revision == current.form_revision
            and waiting.type == current.type
            and waiting.field == current.field
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
