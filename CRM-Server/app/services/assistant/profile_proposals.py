"""Profile records mentioned in a committed activity (D29).

After the activity write, and before the opportunity/task proposals, the activity task lists the contacts,
invoice titles and deployments the sales rep mentioned. Each accepted item opens its own child entity task
that confirms separately, so one item's failure never touches the others or the activity.
"""
# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

import json
import logging
from time import monotonic
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from app.models.assistant import AssistantTask, AssistantWaitingType
from app.services.assistant.contact_matching import (
    compute_contact_delta,
    extract_contact_signals,
    list_customer_contacts,
    match_existing_contact,
)
from app.services.assistant.contracts import EntityQuote, ProfileProposalItem, TaskAuthority, TaskWaiting
from app.services.assistant.entity_forms import module_for
from app.services.assistant.events import stage
from app.services.assistant.task_state import (
    InvalidTaskTransitionError,
    TaskStateConflictError,
    TaskUpdate,
    apply_task_update,
    load_authority,
    load_draft,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sqlalchemy.orm import Session

    from app.services.assistant.events import ProgressReporter

logger = logging.getLogger(__name__)

NONE = "none"
FIELD = "profile_proposals"
PROMPT = "客户活动已保存；以下提到的客户资料，要分别建档或更新吗？"
HINT = "每项将单独保存到对应客户资料模块，不影响已保存的客户活动；点「打开表单」后可先核对或补全再保存，不会直接写入。"
CANCELLED_HINT = "资料可以直接让我单独保存"
GO_CREATE_LABEL = "打开建档表单"
GO_SUPPLEMENT_LABEL = "打开补充表单"
GO_CONFIRM_CONTACT_LABEL = "去确认联系人"
SKIP_LABEL = "不保存"
NONE_LABEL = "全部不保存"
_KINDS = ("contact_create", "invoice_title_create", "deployment_create")
_ROW_LABELS: dict[str, str] = {
    "contact_create": "新建联系人",
    "contact_supplement": "更新已有联系人",
    "invoice_title_create": "新建开票抬头",
    "deployment_create": "新建部署信息",
}
_FIELD_LABELS: dict[str, dict[str, str]] = {
    "contact_create": {
        "name": "姓名",
        "gender": "性别",
        "position": "职位",
        "mobile": "手机号",
        "email": "邮箱",
        "wechat_id": "微信",
        "is_decision_maker": "关键决策人",
        "reports_to": "汇报对象",
        "remark": "备注",
    },
    "contact_supplement": {
        "name": "姓名",
        "mobile": "手机号",
        "email": "邮箱",
        "wechat_id": "微信",
        "reports_to": "汇报对象",
        "remark": "追加备注",
    },
    "invoice_title_create": {
        "title_type": "抬头类型",
        "title": "开票抬头",
        "taxpayer_id": "纳税人识别号",
        "bank_name": "开户行",
        "bank_account": "开户账号",
        "address": "开票地址",
        "phone": "电话",
    },
    "deployment_create": {
        "deployment_name": "部署名称",
        "server_address": "服务器地址",
        "is_default": "默认部署",
        "authorized_users": "授权人数",
    },
}


def profile_row_label(kind: str) -> str:
    return _ROW_LABELS.get(kind) or module_for(kind).LABEL


def go_action_label(item: ProfileProposalItem) -> str:
    if item.kind == "contact_supplement":
        if item.match_status in {"AMBIGUOUS_NAME", "MOBILE_CONFLICT"}:
            return GO_CONFIRM_CONTACT_LABEL
        return GO_SUPPLEMENT_LABEL
    return GO_CREATE_LABEL


def format_profile_group(
    kind: str,
    summary: str,
    *,
    row_label: str | None = None,
    max_len: int = 40,
) -> str:
    label = row_label or profile_row_label(kind)
    cleaned = summary.strip()
    prefixes = [f"{label}：", f"{label}:"]
    try:
        module_label = module_for(kind).LABEL
    except KeyError:
        module_label = ""
    if module_label and module_label != label:
        prefixes.extend([f"{module_label}：", f"{module_label}:"])
    if kind == "contact_supplement":
        prefixes.extend(["补充已有联系人：", "补充已有联系人:", "补充 ", "更新 "])
    for prefix in prefixes:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    text = f"{label}：{cleaned or summary.strip()}"
    return text[:max_len]


def format_extracted_summary(
    kind: str,
    extracted: Sequence[EntityQuote],
    *,
    max_items: int = 4,
    max_len: int = 120,
) -> str | None:
    field_labels = _FIELD_LABELS.get(kind, {})
    parts: list[str] = []
    seen: set[tuple[str, str]] = set()
    for entry in extracted:
        val = entry.value.strip()
        if not val:
            continue
        label = field_labels.get(entry.key)
        if not label:
            continue
        clipped_val = f"{val[:24]}…" if len(val) > 24 else val
        key_pair = (label, clipped_val)
        if key_pair in seen:
            continue
        seen.add(key_pair)
        parts.append(f"{label} {clipped_val}")
        if len(parts) >= max_items:
            break
    if not parts:
        return None
    text = f"已识别：{'、'.join(parts)}"
    return f"{text[:max_len - 1]}…" if len(text) > max_len else text
_MAX_ITEMS = 6
_SYSTEM_PROMPT = (
    "你只从销售自己的话里找出值得单独存档的客户资料：联系人、开票抬头、部署信息。"
    "每项给出 kind、一句 summary、逐字照抄的原文 quote，以及按该 kind 的 keys 提取的字段，"
    "每个字段的 quote 必须逐字出自原文。只是沟通过程、没有可存资料时返回空列表；禁止推断原文没说的内容。"
)


class _Field(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str = ""
    value: str = ""
    quote: str = ""


class _Item(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: str = ""
    summary: str = ""
    quote: str = ""
    fields: list[_Field] = Field(default_factory=list, max_length=40)


class ProfileExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[_Item] = Field(default_factory=list, max_length=20)


async def extract_profile_items(db: Session, task: AssistantTask, text: str) -> ProfileExtraction:
    """One structured model call; tests replace this seam."""

    from app.services.assistant.failure_contract import ATTEMPT_DEADLINE_SECONDS, attempt_budget_remaining
    from app.services.assistant.model_transport import (
        AssistantModelTransport,
        team_model_credentials,
        team_output_mode,
    )

    host, key, model = team_model_credentials(db, task.team_id)
    remaining = attempt_budget_remaining()
    return await AssistantModelTransport().ainvoke_structured(
        api_host=host, api_key=key, model=model, output_mode=team_output_mode(db, task.team_id),
        temperature=0.0, system_prompt=_SYSTEM_PROMPT,
        user_prompt=json.dumps({
            "kinds": {kind: {"record": module_for(kind).LABEL, "keys": dict(module_for(kind).EXTRACT_KEYS)}
                      for kind in _KINDS},
            "output": {"items": [{"kind": "", "summary": "", "quote": "",
                                  "fields": [{"key": "", "value": "", "quote": ""}]}]},
            "text": text,
        }, ensure_ascii=False),
        response_model=ProfileExtraction, error_prefix="整理资料",
        timeout_seconds=ATTEMPT_DEADLINE_SECONDS if remaining is None else remaining, stage="propose",
    )


def _source(task: AssistantTask) -> str:
    draft = load_draft(task)
    return "\n".join(record.text for record in draft.source_records) or "\n".join(draft.source_segments)


def _verified(text: str, extraction: ProfileExtraction) -> list[ProfileProposalItem]:
    """Keep items whose quote is the rep's own words, in the order they said them."""

    found: list[tuple[int, ProfileProposalItem]] = []
    for item in extraction.items:
        summary = item.summary.strip()[:120]
        if item.kind not in _KINDS or not summary or not item.quote or len(item.quote) > 2000 or item.quote not in text:
            continue
        keys = module_for(item.kind).EXTRACT_KEYS
        quotes = [
            EntityQuote(key=field.key, value=field.value.strip()[:2000], quote=field.quote)
            for field in item.fields
            if field.key in keys and field.value.strip() and field.quote and len(field.quote) <= 2000
            and field.quote in text
        ][:40]
        found.append((text.find(item.quote), ProfileProposalItem.model_validate({
            "kind": item.kind, "summary": summary, "quote": item.quote, "extracted": quotes,
        })))
    found.sort(key=lambda pair: pair[0])
    return [item for _, item in found][:_MAX_ITEMS]


def _pre_match_contact(
    db: Session, task: AssistantTask, item: ProfileProposalItem,
) -> ProfileProposalItem | None:
    from app.models.customer import Customer

    customer_public_id = load_authority(task).customer_public_id
    if not customer_public_id:
        return item
    customer = (
        db.query(Customer)
        .filter(Customer.team_id == task.team_id, Customer.public_id == customer_public_id)
        .first()
    )
    if customer is None:
        return item
    contacts = list_customer_contacts(db, team_id=task.team_id, customer_id=customer.id)
    if not contacts:
        return item

    signals = extract_contact_signals(item.extracted)
    match = match_existing_contact(contacts, signals)
    if match.status == "NO_MATCH":
        return item
    if match.status == "MATCHED" and match.contact is not None:
        delta = compute_contact_delta(match.contact, signals, contacts=contacts)
        if not delta.has_delta:
            return None
        parts = "、".join(delta.summary_parts())
        summary = f"补充 {match.contact.name}（{parts}）"[:120]
        return item.model_copy(
            update={
                "kind": "contact_supplement",
                "summary": summary,
                "target_contact_id": match.contact.id,
                "match_status": "MATCHED",
            }
        )
    if match.status == "AMBIGUOUS_NAME":
        name = signals.name or item.summary
        summary = f"补充 {name}（有 {len(match.candidates)} 位同名，需选择）"[:120]
        return item.model_copy(
            update={
                "kind": "contact_supplement",
                "summary": summary,
                "match_status": "AMBIGUOUS_NAME",
            }
        )
    if match.status == "MOBILE_CONFLICT" and match.contact is not None:
        summary = f"补充 {match.contact.name}（手机号不一致，需确认）"[:120]
        return item.model_copy(
            update={
                "kind": "contact_supplement",
                "summary": summary,
                "target_contact_id": match.contact.id,
                "match_status": "MOBILE_CONFLICT",
                "conflict_mobile": match.conflict_mobile,
            }
        )
    return item


_PRE_MATCH_HOOKS: dict[str, Callable[[Session, AssistantTask, ProfileProposalItem], ProfileProposalItem | None]] = {
    "contact_create": _pre_match_contact,
}


def _apply_pre_match_hooks(
    db: Session, task: AssistantTask, items: list[ProfileProposalItem],
) -> list[ProfileProposalItem]:
    matched: list[ProfileProposalItem] = []
    for item in items:
        hook = _PRE_MATCH_HOOKS.get(item.kind)
        if hook is None:
            matched.append(item)
            continue
        resolved = hook(db, task, item)
        if resolved is not None:
            matched.append(resolved)
    return matched


def _waiting(task: AssistantTask, items: list[ProfileProposalItem]) -> TaskWaiting:
    candidates: list[dict[str, object]] = []
    for index, item in enumerate(items):
        if item.decision == "pending":
            candidates += [
                {"id": f"go:{index}", "label": go_action_label(item)},
                {"id": f"skip:{index}", "label": SKIP_LABEL},
            ]
    candidates.append({"id": NONE, "label": NONE_LABEL})
    return TaskWaiting(
        type=AssistantWaitingType.PROFILE_PROPOSALS, field=FIELD,
        question_id=f"q_profile_{task.public_id}_{task.version}", prompt=PROMPT, hint=HINT, candidates=candidates,
    )


async def offer_profile_proposals(
    db: Session, task: AssistantTask, reporter: ProgressReporter,
) -> AssistantTask | None:
    """List the profile items once; ``None`` when there is nothing to list and the activity flow goes on."""

    if load_authority(task).profile_proposals is not None:
        return None
    text = _source(task)
    items: list[ProfileProposalItem] = []
    if text.strip():
        reporter.stage_start(stage("propose"))
        started = monotonic()
        try:
            items = _verified(text, await extract_profile_items(db, task, text))
            items = _apply_pre_match_hooks(db, task, items)
            reporter.stage_done(stage("propose"), ms=int((monotonic() - started) * 1000))
        except Exception:  # the activity is already written; a profile miss must never affect it.
            logger.warning("assistant profile extraction failed task=%s", task.public_id, exc_info=True)
            reporter.stage_failed(stage("propose"))
    if not items:
        apply_task_update(db, task, TaskUpdate(
            authority=TaskAuthority(profile_proposals=[]), action_actor="SYSTEM", action_name="profile_proposals_none",
        ))
        return None
    result = apply_task_update(db, task, TaskUpdate(
        authority=TaskAuthority(profile_proposals=items), waiting=_waiting(task, items),
        action_actor="SYSTEM", action_name="offer_profile_proposals", action_result={"count": len(items)},
    ))
    return result.task


def answer_profile_proposals(db: Session, task: AssistantTask, choice: str) -> tuple[AssistantTask, str, bool]:
    """Settle one row (or the whole list); returns the task, the reply and whether the list is finished."""

    from app.services.assistant.entity_tasks import open_profile_child

    items = list(load_authority(task).profile_proposals or [])
    if choice == NONE:
        items = [item.model_copy(update={"decision": "skip"}) if item.decision == "pending" else item for item in items]
        message = "好的，剩下的资料不保存"
    else:
        verb, _, raw = choice.partition(":")
        index = int(raw) if raw.isdigit() else -1
        if verb not in {"go", "skip"} or not 0 <= index < len(items) or items[index].decision != "pending":
            raise InvalidTaskTransitionError(f"profile proposal choice {choice!r} is not pending")
        item = items[index]
        if verb == "skip":
            items[index] = item.model_copy(update={"decision": "skip"})
            message = f"「{item.summary}」不保存"
        else:
            try:
                with db.begin_nested():
                    child = open_profile_child(db, task, item)
                items[index] = item.model_copy(update={"decision": "go", "child_task_public_id": child.public_id})
                if child.waiting_type == AssistantWaitingType.OBJECT_SELECTION:
                    message = f"已打开「{item.summary}」的确认卡片，请先选择处理方式"
                else:
                    message = f"已打开「{item.summary}」的{module_for(item.kind).LABEL}表单，核对后保存"
            except (SQLAlchemyError, InvalidTaskTransitionError, TaskStateConflictError, ValueError):
                logger.warning("assistant profile child failed task=%s item=%s", task.public_id, index, exc_info=True)
                items[index] = item.model_copy(update={"decision": "failed"})
                message = f"「{item.summary}」没能打开表单，{CANCELLED_HINT}"
    pending = any(item.decision == "pending" for item in items)
    result = apply_task_update(db, task, TaskUpdate(
        authority=TaskAuthority(profile_proposals=items),
        waiting=_waiting(task, items) if pending else None, clear_waiting=not pending,
        action_actor="USER", action_name="answer_profile_proposals", action_input={"choice": choice},
    ))
    return result.task, message, not pending
