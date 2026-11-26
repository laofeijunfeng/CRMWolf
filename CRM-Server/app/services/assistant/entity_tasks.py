"""Direct-create entity tasks: one task per CRM record (contact, invoice title, deployment, customer, opportunity).

The coordinator hands every non-activity task here; activity intake never sees entity tasks.
Text never writes: only a submitted form claims, writes and records one attributable CRM effect.
"""
# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

import hashlib
import json
import logging
import re
from time import monotonic
from typing import TYPE_CHECKING, NoReturn

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError
from sqlalchemy import update as sql_update
from sqlalchemy.exc import SQLAlchemyError

from app.models.assistant import AssistantAction, AssistantTask, AssistantTaskStatus, AssistantWaitingType
from app.services.assistant.contracts import (
    EntityCreateReceipt,
    EntityDraft,
    EntityFieldValue,
    EntityQuote,
    TaskWaiting,
)
from app.services.assistant.crm_effects import AssistantCRMCommand, checked_effect, record_effect
from app.services.assistant.entity_forms import (
    ACTIONS,
    Canonical,
    EntityFormError,
    EntityFormModule,
    FormContext,
    module_for,
    value,
)
from app.services.assistant.events import stage
from app.services.assistant.intent import not_written
from app.services.assistant.task_state import (
    InvalidTaskTransitionError,
    TaskStateConflictError,
    TaskUpdate,
    apply_task_update,
    load_draft,
    load_waiting,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.core.exceptions import DuplicateRecordError
    from app.models.customer import Customer
    from app.models.user import User
    from app.schemas.assistant import PendingEntityDraftView
    from app.services.assistant.contracts import ProfileProposalItem
    from app.services.assistant.coordinator import AssistantInput, CoordinatorOutcome
    from app.services.assistant.events import ProgressReporter

logger = logging.getLogger(__name__)

CUSTOMER_FIELD = "customer"
NEW_CUSTOMER = "new_customer"
_CUSTOMER_KIND = "customer_create"
_CLAIM = "proposal_command_claim"
# Frozen form key that names the record on a reconciled receipt.
_NAME_KEYS = {
    "contact_create": "name",
    "invoice_title_create": "title",
    "deployment_create": "deployment_name",
    "customer_create": "account_name",
    "opportunity_create": "opportunity_name",
}
_NOT_SAVED_HINT = "没有保存，表单内容都还在"
# Parking an open form (D20): the draft waits in 「待补充」 with no expiry and nothing written.
_DEFER_PHRASES = ("稍后再补", "先放着", "晚点再补", "回头再补")
RESUME = "resume"
# Prepared values the user did not say: a supplement never applies them (D18).
_UNSAID_SOURCES = frozenset({"DEFAULT", "CUSTOMER_DEFAULT", "AUTO_NAME"})


def is_defer_text(text: str | None) -> bool:
    return bool(text) and any(phrase in text for phrase in _DEFER_PHRASES)


def pending_drafts(db: Session, *, team_id: int, user_id: int) -> list[PendingEntityDraftView]:
    """The owner's ACTIVE direct-create tasks, most recently touched first (D20)."""

    from app.schemas.assistant import PendingEntityDraftView

    tasks = (
        db.query(AssistantTask)
        .filter(
            AssistantTask.team_id == team_id,
            AssistantTask.user_id == user_id,
            AssistantTask.status == AssistantTaskStatus.ACTIVE,
            AssistantTask.task_kind.in_(tuple(ACTIONS)),
        )
        .order_by(AssistantTask.last_modified_time.desc(), AssistantTask.id.desc())
        .limit(50)
        .all()
    )
    views = []
    for task in tasks:
        waiting = load_waiting(task)
        entity = load_draft(task).entity
        views.append(PendingEntityDraftView(
            public_id=task.public_id, task_kind=task.task_kind, label=module_for(task.task_kind).LABEL,
            customer_name=entity.customer_name if entity is not None else None,
            waiting_type=waiting.type if waiting is not None else None,
            prompt=waiting.prompt if waiting is not None else None,
            last_modified_time=task.last_modified_time,
        ))
    return views


class _Quoted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1, max_length=2000)
    quote: str = Field(min_length=1, max_length=2000)


class _ExtractedField(_Quoted):
    key: str = Field(min_length=1, max_length=64)


class EntityExtraction(BaseModel):
    """Model output: candidates only; the server keeps what it can locate in the user's text."""

    model_config = ConfigDict(extra="forbid")

    customer_name: _Quoted | None = None
    fields: list[_ExtractedField] = Field(default_factory=list, max_length=60)
    credentials_mentioned: bool = False


_SYSTEM_PROMPT = (
    "你是 CRM 资料整理助手，只整理用户原话里明确说出的信息。"
    "每个值都必须附 quote：原文中连续出现的原样片段。没说的字段不要输出，禁止推断、补全或编造。"
    "customer_name 是这条资料所属的客户名称（新建客户本身时填 null）。"
    "credentials_mentioned：原文出现账号、密码或口令时为 true。只输出 JSON。"
)


async def extract_entity(db: Session, task: AssistantTask, module: EntityFormModule, text: str) -> EntityExtraction:
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
            "record": module.LABEL,
            "keys": dict(module.EXTRACT_KEYS),
            "output": {"customer_name": {"value": "", "quote": ""},
                       "fields": [{"key": "", "value": "", "quote": ""}], "credentials_mentioned": False},
            "text": text,
        }, ensure_ascii=False),
        response_model=EntityExtraction, error_prefix="整理资料",
        timeout_seconds=ATTEMPT_DEADLINE_SECONDS if remaining is None else remaining, stage="structure",
    )


def _verified(
    module: EntityFormModule, text: str, extraction: EntityExtraction,
) -> tuple[list[EntityQuote], str | None]:
    quotes = [
        EntityQuote(key=item.key, value=item.value.strip(), quote=item.quote)
        for item in extraction.fields
        if item.key in module.EXTRACT_KEYS and item.value.strip() and item.quote in text
    ][:40]
    named = extraction.customer_name
    name = named.value.strip()[:200] if named is not None and named.quote in text and named.value.strip() else None
    return quotes, (None if module.KIND == _CUSTOMER_KIND else name)


def _outcome(task: AssistantTask, message: str) -> CoordinatorOutcome:
    from app.services.assistant.coordinator import CoordinatorOutcome, CoordinatorReply

    return CoordinatorOutcome(
        reply=CoordinatorReply(
            task_public_id=task.public_id, status=task.status, message=message[:2000], waiting=load_waiting(task),
        ),
        task=task,
    )


def _entity(task: AssistantTask) -> EntityDraft:
    entity = load_draft(task).entity
    if entity is None:
        raise InvalidTaskTransitionError("entity task has no entity draft")
    return entity


def _with_entity(task: AssistantTask, entity: EntityDraft):  # noqa: ANN202 -- TaskDraft
    return load_draft(task).model_copy(update={"entity": entity})


def _customer(db: Session, task: AssistantTask, public_id: str | None) -> Customer | None:
    from app.models.customer import Customer

    if not public_id:
        return None
    return db.query(Customer).filter(Customer.team_id == task.team_id, Customer.public_id == public_id).one_or_none()


def _permission_refusal(db: Session, task: AssistantTask, kind: str, customer: Customer | None) -> str | None:
    """The CRM's own permission rules, checked when the form is issued and again on submit (D11)."""

    from fastapi import HTTPException

    from app.core.exceptions import AppException
    from app.services.assistant.crm_proposal_commands import _customer_edit, _permissions

    try:
        if kind == _CUSTOMER_KIND:
            return None if "customer:create" in _permissions(db, task) else "你没有新建客户的权限"
        if customer is None:
            raise InvalidTaskTransitionError("entity permission check requires a bound customer")
        try:
            _customer_edit(db, task, customer)
        except (HTTPException, AppException):
            return f"你没有修改客户“{customer.account_name}”资料的权限"
        if kind == "invoice_title_create" and "invoice:title:create" not in _permissions(db, task):
            return "你没有新建开票抬头的权限"
        if kind == "opportunity_create" and "opportunity:create" not in _permissions(db, task):
            return "你没有新建商机的权限"
    except PermissionError:
        return "你的账号已不在当前团队或已停用"
    return None


def _refuse(db: Session, task: AssistantTask, reason: str, *, code: str = "PERMISSION_DENIED",
            fence: bool = False) -> CoordinatorOutcome:
    denied = code == "PERMISSION_DENIED"
    result = apply_task_update(db, task, TaskUpdate(
        status=AssistantTaskStatus.FAILED, require_no_active_turn=fence, clear_waiting=True, error_code=code,
        action_actor="SYSTEM", action_name="entity_permission_denied" if denied else "entity_refused",
        action_result={"code": code},
    ))
    return _outcome(result.task, not_written(f"{reason}，请联系管理员确认权限" if denied else reason))


def _user(db: Session, task: AssistantTask) -> User | None:
    from app.services.assistant.crm_proposal_commands import _user as crm_user

    try:
        return crm_user(db, task)
    except PermissionError:
        return None


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------


async def handle_entity_task(
    db: Session, task: AssistantTask, user_input: AssistantInput, *, reporter: ProgressReporter
) -> CoordinatorOutcome:
    if task.task_kind not in ACTIONS:
        raise InvalidTaskTransitionError(f"task kind {task.task_kind} is not a direct-create entity")
    module = module_for(task.task_kind)
    user = _user(db, task)
    if user is None:
        return _refuse(db, task, "你的账号已不在当前团队或已停用")
    waiting = load_waiting(task)
    if waiting is None:
        if user_input.kind != "text":
            raise InvalidTaskTransitionError("an entity task starts from text")
        return await _intake(db, task, module, user, user_input.text or task.goal, reporter)
    if waiting.type == AssistantWaitingType.ENTITY_FORM and user_input.kind == "submit_form":
        return await _submit_form(db, task, waiting, module, user, user_input, reporter)
    if waiting.type == AssistantWaitingType.ENTITY_FORM and user_input.kind == "text" and user_input.text:
        if is_defer_text(user_input.text):
            return _defer(db, task, waiting, module)
        return await _supplement(db, task, waiting, module, user, user_input.text, reporter)
    if waiting.type == AssistantWaitingType.ENTITY_DEFERRED and user_input.kind == "submit_field":
        if user_input.choice == "cancel":
            return cancel_entity_task(db, task)
        if user_input.choice == RESUME:
            return _resume(db, task, waiting, module, user)
    if waiting.type == AssistantWaitingType.ENTITY_DEFERRED and user_input.kind == "text" and user_input.text:
        if is_defer_text(user_input.text):
            return _outcome(task, not_written(waiting.prompt))
        resumed = _resume(db, task, waiting, module, user)
        reopened = load_waiting(resumed.task)
        if reopened is None or reopened.type != AssistantWaitingType.ENTITY_FORM:
            return resumed
        return await _supplement(db, resumed.task, reopened, module, user, user_input.text, reporter)
    if waiting.field == CUSTOMER_FIELD and waiting.type == AssistantWaitingType.OBJECT_SELECTION:
        return _select_customer(db, task, module, user, user_input.choice)
    if waiting.field == CUSTOMER_FIELD and waiting.type == AssistantWaitingType.FIELD and user_input.text:
        entity = _entity(task).model_copy(update={"customer_name": user_input.text.strip()[:200]})
        return _resolve_customer(db, task, module, user, entity)
    raise InvalidTaskTransitionError("当前输入不符合等待动作")


async def _intake(
    db: Session, task: AssistantTask, module: EntityFormModule, user: User, text: str, reporter: ProgressReporter,
) -> CoordinatorOutcome:
    from app.services.assistant.llm import AssistantLLMError

    source = text[:20000]
    started = monotonic()
    reporter.stage_start(stage("structure"))
    hint: str | None = None
    try:
        extraction = await extract_entity(db, task, module, source)
        reporter.stage_done(stage("structure"), ms=int((monotonic() - started) * 1000))
    except (AssistantLLMError, TimeoutError, ValueError, TypeError, ValidationError):
        logger.warning("assistant entity extraction failed task=%s", task.public_id, exc_info=True)
        reporter.stage_failed(stage("structure"))
        extraction = EntityExtraction()
        hint = "没能自动整理，请直接填写"
    quotes, customer_name = _verified(module, source, extraction)
    entity = EntityDraft(
        kind=module.KIND, customer_name=customer_name, extracted=quotes, source_text=source,
        credentials_mentioned=extraction.credentials_mentioned,
    )
    if module.KIND == _CUSTOMER_KIND:
        refusal = _permission_refusal(db, task, module.KIND, None)
        if refusal is not None:
            return _refuse(db, task, refusal)
        ctx = FormContext(db, task, user, None, entity)
        entity = entity.model_copy(update={"fields": module.prepare(ctx, quotes)})
        return _issue_form(db, task, module, user, entity, hint=hint, action_name="issue_entity_form")
    return _resolve_customer(db, task, module, user, entity)


# ---------------------------------------------------------------------------
# Customer binding (D8/D9)
# ---------------------------------------------------------------------------


def _ask_customer(db: Session, task: AssistantTask, entity: EntityDraft, prompt: str) -> CoordinatorOutcome:
    waiting = TaskWaiting(
        type=AssistantWaitingType.FIELD, field=CUSTOMER_FIELD,
        question_id=f"q_customer_{task.public_id}_{task.version}", prompt=prompt,
    )
    result = apply_task_update(db, task, TaskUpdate(
        draft=_with_entity(task, entity), waiting=waiting, action_actor="SYSTEM", action_name="ask_customer_name",
    ))
    return _outcome(result.task, prompt)


def _offer_customers(
    db: Session, task: AssistantTask, entity: EntityDraft, prompt: str, candidates: list[dict[str, object]],
) -> CoordinatorOutcome:
    waiting = TaskWaiting(
        type=AssistantWaitingType.OBJECT_SELECTION, field=CUSTOMER_FIELD,
        question_id=f"q_cust_{task.public_id}_{task.version}", prompt=prompt,
        candidates=[*candidates, {"id": NEW_CUSTOMER, "label": "新建客户"}],
    )
    result = apply_task_update(db, task, TaskUpdate(
        draft=_with_entity(task, entity), waiting=waiting, action_actor="SYSTEM", action_name="offer_customers",
    ))
    return _outcome(result.task, prompt)


def _resolve_customer(
    db: Session, task: AssistantTask, module: EntityFormModule, user: User, entity: EntityDraft,
) -> CoordinatorOutcome:
    from app.services.assistant.customer_resolution import resolve_customer_candidates_for_assistant

    name = entity.customer_name
    if not name:
        return _ask_customer(db, task, entity, "存到哪个客户？")
    resolution = resolve_customer_candidates_for_assistant(
        db, team_id=task.team_id, user_id=task.user_id, customer_name=name,
    )
    if resolution.status == "RESOLVED" and resolution.customer is not None:
        return _bind_and_issue(db, task, module, user, entity, resolution.customer)
    if resolution.status == "AMBIGUOUS":
        return _offer_customers(db, task, entity, f"“{name}”对应多个客户，存到哪一个？", [
            {"id": item["id"], "label": item["account_name"]} for item in resolution.candidates
        ])
    if resolution.status == "DEPENDENCY_FAILURE":
        return _ask_customer(db, task, entity, "客户查询暂时失败，请再说一次客户名称。")
    # NOT_FOUND and PERMISSION_DENIED read the same: a denied match is never revealed.
    return _offer_customers(db, task, entity, f"没找到可用的客户“{name}”。要新建这个客户吗？", [])


def _select_customer(
    db: Session, task: AssistantTask, module: EntityFormModule, user: User, choice: str | None,
) -> CoordinatorOutcome:
    entity = _entity(task)
    if choice == NEW_CUSTOMER:
        refusal = _permission_refusal(db, task, _CUSTOMER_KIND, None)
        if refusal is not None:
            return _refuse(db, task, refusal)
        name = entity.customer_name
        customer_fields = {"account_name": value("ORIGINAL", name)} if name else {}
        entity = entity.model_copy(update={"customer_fields": customer_fields})
        return _issue_form(db, task, module, user, entity, inline=True, action_name="issue_inline_customer_form")
    customer = _customer(db, task, choice)
    if customer is None:
        return _ask_customer(db, task, entity, "这个客户已不可用，请再说一次客户名称。")
    return _bind_and_issue(db, task, module, user, entity, customer)


def _bind_and_issue(
    db: Session, task: AssistantTask, module: EntityFormModule, user: User, entity: EntityDraft,
    customer: Customer, *, fence: bool = False,
) -> CoordinatorOutcome:
    refusal = _permission_refusal(db, task, module.KIND, customer)
    if refusal is not None:
        return _refuse(db, task, refusal, fence=fence)
    entity = entity.model_copy(update={
        "customer_public_id": customer.public_id, "customer_name": customer.account_name[:200],
    })
    ctx = FormContext(db, task, user, customer, entity)
    entity = entity.model_copy(update={"fields": module.prepare(ctx, entity.extracted)})
    return _issue_form(db, task, module, user, entity, action_name="issue_entity_form", fence=fence)


# ---------------------------------------------------------------------------
# Form
# ---------------------------------------------------------------------------


def _issue_form(
    db: Session, task: AssistantTask, module: EntityFormModule, user: User, entity: EntityDraft, *,
    action_name: str, inline: bool = False, errors: dict[str, str] | None = None, hint: str | None = None,
    fence: bool = False, flag_cleared: bool = False,
) -> CoordinatorOutcome:
    form = module_for(_CUSTOMER_KIND) if inline else module
    customer = None if form.KIND == _CUSTOMER_KIND else _customer(db, task, entity.customer_public_id)
    if form.KIND != _CUSTOMER_KIND and customer is None:
        return _ask_customer(db, task, entity.model_copy(update={"customer_public_id": None}), "存到哪个客户？")
    values = entity.customer_fields if inline else entity.fields
    ctx = FormContext(db, task, user, customer, entity)
    notes = [hint] if hint else []
    notes += form.notices(ctx, values)
    if entity.credentials_mentioned and not inline:
        notes.append("账号密码不会保存")
    prompt = f"为{customer.account_name}新建{form.LABEL}" if customer is not None else f"新建{form.LABEL}"
    revision = task.version
    submitted = entity.submitted.get(form.KIND)
    form_fields = form.fields(ctx, values, submitted, errors or {})[:20]
    if flag_cleared:
        # Options that disappeared since the draft was parked are cleared by render; say so (D20).
        cleared = [
            str(field["label"]) for field in form_fields
            if _empty(field.get("default_value")) and not _empty(_current(values, submitted, str(field["key"])))
        ]
        if cleared:
            notes.append(f"待补充：{'、'.join(cleared)}")
    waiting = TaskWaiting(
        type=AssistantWaitingType.ENTITY_FORM, field=f"entity:{form.KIND}",
        question_id=f"q_entity_{task.public_id}_{revision}", prompt=prompt[:2000], form_revision=revision,
        form_fields=form_fields, hint="；".join(notes)[:400] or None,
    )
    result = apply_task_update(db, task, TaskUpdate(
        require_no_active_turn=fence, draft=_with_entity(task, entity), waiting=waiting,
        action_actor="SYSTEM", action_name=action_name,
        action_result={"errors": sorted(errors)} if errors else {},
    ))
    fallback = "有字段需要修改，改好再保存" if errors else f"{prompt}，核对后保存"
    message = (errors or {}).get("form") or hint or fallback
    return _outcome(result.task, message)


def _submitted(module: EntityFormModule, values: dict[str, JsonValue] | None) -> dict[str, JsonValue]:
    return {key: item for key, item in (values or {}).items() if key in module.FIELD_KEYS}


def _empty(item: object) -> bool:
    return item is None or item == "" or item == []


def _current(
    values: dict[str, EntityFieldValue], submitted: dict[str, JsonValue] | None, key: str,
) -> object:
    """What the form shows for ``key``: the last submitted value, else the drafted one."""

    if submitted is not None and key in submitted:
        return submitted[key]
    drafted = values.get(key)
    return drafted.value if drafted is not None else None


# ---------------------------------------------------------------------------
# 待补充 (D20) and typed supplements (D18)
# ---------------------------------------------------------------------------


def _defer(db: Session, task: AssistantTask, waiting: TaskWaiting, module: EntityFormModule) -> CoordinatorOutcome:
    prompt = f"{module.LABEL}草稿先放着，随时可以继续"
    # Keeps the form's field so an inline customer form resumes inline; the draft is untouched.
    result = apply_task_update(db, task, TaskUpdate(
        waiting=TaskWaiting(
            type=AssistantWaitingType.ENTITY_DEFERRED, field=waiting.field,
            question_id=f"q_defer_{task.public_id}_{task.version}", prompt=prompt,
            candidates=[{"id": RESUME, "label": "继续填写"}, {"id": "cancel", "label": "不要了"}],
        ),
        action_actor="USER", action_name="defer_entity_form",
    ))
    return _outcome(result.task, not_written(f"{prompt}，在「待补充」里找到它"))


def _resume(
    db: Session, task: AssistantTask, waiting: TaskWaiting, module: EntityFormModule, user: User,
) -> CoordinatorOutcome:
    """Re-issue the parked form with fresh permission, duplicates and options; never re-prepares values."""

    entity = _entity(task)
    inline = waiting.field == f"entity:{_CUSTOMER_KIND}" and module.KIND != _CUSTOMER_KIND
    customer = None
    if module.KIND != _CUSTOMER_KIND and not inline:
        customer = _customer(db, task, entity.customer_public_id)
        if customer is None:
            return _resolve_customer(db, task, module, user, entity.model_copy(update={"customer_public_id": None}))
    refusal = _permission_refusal(db, task, _CUSTOMER_KIND if inline else module.KIND, customer)
    if refusal is not None:
        return _refuse(db, task, refusal)
    return _issue_form(db, task, module, user, entity, inline=inline, flag_cleared=True,
                       action_name="resume_entity_form")


def _named_keys(form: EntityFormModule, waiting: TaskWaiting, text: str) -> set[str]:
    """Keys the user named outright (「税号是…」): those override a filled value."""

    aliases: dict[str, set[str]] = {}
    for key, guide in form.EXTRACT_KEYS.items():
        head = re.split("[，；（]", guide, maxsplit=1)[0]
        aliases[key] = {alias.strip() for alias in head.split("/") if 1 < len(alias.strip()) <= 8}
    for field in waiting.form_fields or []:
        if isinstance(field.get("key"), str) and isinstance(field.get("label"), str):
            aliases.setdefault(field["key"], set()).add(field["label"])
    return {key for key, names in aliases.items() if any(name in text for name in names)}


async def _supplement(
    db: Session, task: AssistantTask, waiting: TaskWaiting, module: EntityFormModule, user: User, text: str,
    reporter: ProgressReporter,
) -> CoordinatorOutcome:
    """Typed text fills empty fields and named ones; it re-issues the form and never writes (D18)."""

    from app.services.assistant.llm import AssistantLLMError

    inline = waiting.field == f"entity:{_CUSTOMER_KIND}" and module.KIND != _CUSTOMER_KIND
    form = module_for(_CUSTOMER_KIND) if inline else module
    entity = _entity(task)
    source = text[:20000]
    started = monotonic()
    reporter.stage_start(stage("structure"))
    try:
        extraction = await extract_entity(db, task, form, source)
        reporter.stage_done(stage("structure"), ms=int((monotonic() - started) * 1000))
    except (AssistantLLMError, TimeoutError, ValueError, TypeError, ValidationError):
        logger.warning("assistant entity supplement failed task=%s", task.public_id, exc_info=True)
        reporter.stage_failed(stage("structure"))
        return _issue_form(db, task, module, user, entity, inline=inline, hint="没能整理这段补充，请直接填写",
                           action_name="supplement_entity_form")
    quotes, _ = _verified(form, source, extraction)
    customer = None if form.KIND == _CUSTOMER_KIND else _customer(db, task, entity.customer_public_id)
    if form.KIND != _CUSTOMER_KIND and customer is None:
        return _ask_customer(db, task, entity.model_copy(update={"customer_public_id": None}), "存到哪个客户？")
    values = entity.customer_fields if inline else entity.fields
    submitted = entity.submitted.get(form.KIND)
    named = _named_keys(form, waiting, source)
    applied: dict[str, EntityFieldValue] = {}
    if quotes:
        for key, item in form.prepare(FormContext(db, task, user, customer, entity), quotes).items():
            if item.source in _UNSAID_SOURCES or (item.value is None and not item.choices):
                continue
            if key in named or _empty(_current(values, submitted, key)):
                applied[key] = item.model_copy(update={"source": "SUPPLEMENT"})
    if not applied:
        return _issue_form(db, task, module, user, entity, inline=inline,
                           hint="这段话里没有能补到表单的内容", action_name="supplement_entity_form")
    merged = {**values, **applied}
    update: dict[str, object] = {"customer_fields": merged} if inline else {
        "fields": merged, "extracted": [*entity.extracted, *quotes][-40:],
    }
    if submitted is not None:
        # Applied keys leave the submitted snapshot so the form shows them as 「刚补充」.
        kept = {key: item for key, item in submitted.items() if key not in applied}
        update["submitted"] = {**entity.submitted, form.KIND: kept}
    labels = {field.get("key"): field.get("label") for field in waiting.form_fields or []}
    names = "、".join(str(labels.get(key) or key) for key in applied)
    return _issue_form(db, task, module, user, entity.model_copy(update=update), inline=inline,
                       hint=f"刚补充：{names}，核对后保存", action_name="supplement_entity_form")


async def _submit_form(
    db: Session, task: AssistantTask, waiting: TaskWaiting, module: EntityFormModule, user: User,
    user_input: AssistantInput, reporter: ProgressReporter,
) -> CoordinatorOutcome:
    inline = waiting.field == f"entity:{_CUSTOMER_KIND}" and module.KIND != _CUSTOMER_KIND
    if user_input.choice == "cancel":
        return cancel_entity_task(db, task)
    if user_input.choice == "defer":
        return _defer(db, task, waiting, module)
    if user_input.choice is not None:
        raise InvalidTaskTransitionError("当前表单不接受这个操作")
    form = module_for(_CUSTOMER_KIND) if inline else module
    entity = _entity(task)
    submitted = _submitted(form, user_input.values)
    entity = entity.model_copy(update={"submitted": {**entity.submitted, form.KIND: submitted}})
    customer = None if form.KIND == _CUSTOMER_KIND else _customer(db, task, entity.customer_public_id)
    if form.KIND != _CUSTOMER_KIND and customer is None:
        return _ask_customer(db, task, entity.model_copy(update={"customer_public_id": None}), "存到哪个客户？")
    refusal = _permission_refusal(db, task, form.KIND, customer)
    if refusal is not None:
        return _refuse(db, task, refusal)
    ctx = FormContext(db, task, user, customer, entity)
    canonical, errors = form.validate(ctx, submitted)
    if errors:
        return _issue_form(db, task, module, user, entity, inline=inline, errors=errors,
                           action_name="entity_form_rejected")
    if form.KIND == "opportunity_create":
        return await _write_opportunity(db, task, module, user, ctx, canonical, reporter)
    return _write(db, task, module, form, user, ctx, canonical, reporter, inline=inline)


def cancel_entity_task(db: Session, task: AssistantTask) -> CoordinatorOutcome:
    from app.services.assistant.proposals import has_unresolved_proposal_claim
    from app.services.assistant.turns import AssistantStateConflict

    if has_unresolved_proposal_claim(db, task):
        raise AssistantStateConflict("上次保存结果待核对，暂不能取消。")
    result = apply_task_update(db, task, TaskUpdate(
        status=AssistantTaskStatus.CANCELLED, clear_waiting=True, action_actor="USER", action_name="cancel_task",
        action_input={"source": "explicit_user_cancel", "input_kind": "submit_form"},
    ))
    label = module_for(task.task_kind).LABEL if task.task_kind in ACTIONS else "资料"
    return _outcome(result.task, not_written(f"已取消新建{label}"))


# ---------------------------------------------------------------------------
# Write: claim -> CRM write + effect -> receipt, all attributable to one command
# ---------------------------------------------------------------------------


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def entity_command(task: AssistantTask, kind: str, canonical: Canonical) -> AssistantCRMCommand:
    fingerprint = _digest(json.dumps(
        {"candidate_key": f"entity:{kind}", "form_values": canonical},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ))
    return AssistantCRMCommand(
        command_id=_digest(f"assistant:{task.team_id}:{task.public_id}:entity:{kind}"),
        team_id=task.team_id, actor_id=task.user_id, fingerprint=fingerprint,
    )


def _latest_claim(db: Session, task: AssistantTask, kind: str) -> AssistantAction | None:
    rows = db.query(AssistantAction).filter(
        AssistantAction.task_id == task.id, AssistantAction.team_id == task.team_id, AssistantAction.action == _CLAIM,
    ).order_by(AssistantAction.id.desc()).all()
    return next((row for row in rows if (row.result_json or {}).get("proposal_key") == f"entity:{kind}"), None)


def _publish_unknown(db: Session, task: AssistantTask, kind: str, label: str) -> NoReturn:
    from app.services.assistant.proposals import _mark_claim_status
    from app.services.assistant.turns import AssistantUnknownCommitResultError, assert_owned_execution_lease

    # Never publish UNKNOWN by committing a transaction that may hold unproven CRM writes.
    db.rollback()
    assert_owned_execution_lease(db, task)
    claim = _latest_claim(db, task, kind)
    if claim is not None and (claim.result_json or {}).get("status") in {"CLAIMED", "UNKNOWN"}:
        _mark_claim_status(db, claim, "UNKNOWN")
        db.commit()
    raise AssistantUnknownCommitResultError(f"{label}写入结果待核对。")


def _receipt(kind: str, public_id: str, name: str, customer_public_id: str | None,
             outcome: str = "created", *, pending_review: bool = False) -> dict[str, object]:
    return EntityCreateReceipt(
        kind=kind, public_id=public_id[:64], outcome=outcome, customer_public_id=customer_public_id,
        name=(name.strip() or "未命名")[:200], approval_phase="pending_review" if pending_review else None,
    ).model_dump(mode="json", exclude_none=True)


def _saved_message(kind: str, label: str, name: str) -> str:
    return f"客户已创建：{name}" if kind == _CUSTOMER_KIND else f"{label}已保存：{name}"


def _claim(
    db: Session, task: AssistantTask, form: EntityFormModule, ctx: FormContext, canonical: Canonical,
) -> tuple[AssistantTask, AssistantAction, AssistantCRMCommand]:
    """Durably claim the frozen command before any CRM write, then reacquire the turn lock."""

    from app.services.assistant.turns import assert_owned_execution_lease

    kind = form.KIND
    command = entity_command(task, kind, canonical)
    assert_owned_execution_lease(db, task)
    claimed = apply_task_update(db, task, TaskUpdate(
        draft=_with_entity(task, ctx.draft), action_actor="SYSTEM", action_name=_CLAIM, action_input={"kind": kind},
        action_result={"proposal_key": f"entity:{kind}", "status": "CLAIMED", "command_id": command.command_id,
                       "fingerprint": command.fingerprint, "form_values": canonical},
    ))
    task, claim = claimed.task, claimed.action
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        if _latest_claim(db, task, kind) is None:
            raise
        _publish_unknown(db, task, kind, form.LABEL)
    # The claim commit released the turn lock; reacquire it before the CRM write.
    assert_owned_execution_lease(db, task)
    return task, claim, command


def _write(
    db: Session, task: AssistantTask, module: EntityFormModule, form: EntityFormModule, user: User,
    ctx: FormContext, canonical: Canonical, reporter: ProgressReporter, *, inline: bool,
) -> CoordinatorOutcome:
    from app.core.exceptions import DuplicateRecordError
    from app.services.assistant.proposals import _mark_claim_status
    from app.services.assistant.turns import assert_owned_execution_lease

    kind = form.KIND
    task, claim, command = _claim(db, task, form, ctx, canonical)
    started = monotonic()
    reporter.stage_start(stage("write"))
    try:
        result = form.write(ctx, canonical)
        record_effect(db, command, kind, target_public_id=result.target_public_id)
    except DuplicateRecordError as exc:
        db.rollback()
        reporter.stage_failed(stage("write"))
        assert_owned_execution_lease(db, task)
        _mark_claim_status(db, claim, "NO_EFFECT")
        return _settle_duplicate(db, task, module, form, user, canonical, exc, inline=inline)
    except EntityFormError as exc:
        db.rollback()
        reporter.stage_failed(stage("write"))
        assert_owned_execution_lease(db, task)
        _mark_claim_status(db, claim, "NO_EFFECT")
        return _issue_form(db, task, module, user, _entity(task), inline=inline, errors=exc.errors,
                           action_name="entity_write_refused")
    except SQLAlchemyError:
        logger.exception("assistant entity write failed task=%s kind=%s", task.public_id, kind)
        db.rollback()
        reporter.stage_failed(stage("write"))
        try:
            effect = checked_effect(db, command, kind)
        except Exception:
            _publish_unknown(db, task, kind, form.LABEL)
        if effect is not None:
            _publish_unknown(db, task, kind, form.LABEL)
        assert_owned_execution_lease(db, task)
        _mark_claim_status(db, claim, "NO_EFFECT")
        return _issue_form(db, task, module, user, _entity(task), inline=inline, hint=_NOT_SAVED_HINT,
                           action_name="entity_write_no_effect")
    try:
        assert_owned_execution_lease(db, task)
        _mark_claim_status(db, claim, "SUCCEEDED", public_id=result.target_public_id)
        receipt = _receipt(kind, result.target_public_id, result.name, result.customer_public_id)
        if inline:
            _attach_inline_customer(db, task, receipt)
        else:
            task = apply_task_update(db, task, TaskUpdate(
                append_committed=[receipt], status=AssistantTaskStatus.COMPLETED, clear_waiting=True,
                action_actor="USER", action_name="entity_create",
                action_result={"kind": kind, "public_id": result.target_public_id},
            )).task
        db.commit()
    except SQLAlchemyError:
        _publish_unknown(db, task, kind, form.LABEL)
    reporter.stage_done(stage("write"), ms=int((monotonic() - started) * 1000))
    try:
        result.after_commit()
    except Exception:
        logger.exception("assistant entity after-commit work failed task=%s kind=%s", task.public_id, kind)
    if inline:
        customer = _customer(db, task, result.customer_public_id)
        if customer is None:
            raise InvalidTaskTransitionError("inline customer vanished after commit")
        return _bind_and_issue(db, task, module, user, _entity(task), customer)
    return _outcome(task, _saved_message(kind, form.LABEL, result.name))


_OPPORTUNITY_DUPLICATE = "已存在相同或无法区分的商机，未创建新商机，请到商机页查看"


async def _write_opportunity(
    db: Session, task: AssistantTask, module: EntityFormModule, user: User, ctx: FormContext,
    canonical: Canonical, reporter: ProgressReporter,
) -> CoordinatorOutcome:
    """The CRM commits the opportunity, its approval and the effect together; never record the effect here."""

    from fastapi import HTTPException

    from app.api.opportunities import create_opportunity
    from app.crud.product import product_crud
    from app.schemas.opportunity import OpportunityCreate
    from app.services.assistant.crm_proposal_commands import opportunity_create_receipt_outcome
    from app.services.assistant.opportunity_target_matching import match_opportunity_target
    from app.services.assistant.proposals import _mark_claim_status
    from app.services.assistant.turns import assert_owned_execution_lease

    kind = module.KIND
    task, claim, command = _claim(db, task, module, ctx, canonical)
    started = monotonic()
    reporter.stage_start(stage("write"))

    def refuse(message: str) -> CoordinatorOutcome:
        db.rollback()
        reporter.stage_failed(stage("write"))
        assert_owned_execution_lease(db, task)
        _mark_claim_status(db, claim, "NO_EFFECT")
        return _issue_form(db, task, module, user, _entity(task), errors={"form": message[:400]},
                           action_name="entity_write_refused")

    try:
        # The CRM creation path takes this fence; hold it from the re-check through the commit.
        product_crud.lock_catalog_team(db, task.team_id)
        effect = checked_effect(db, command, kind)
        if effect is None:
            customer = ctx.customer
            assert customer is not None
            current, errors = module.validate(ctx, ctx.draft.submitted.get(kind, {}))
            if errors or current != canonical:
                return refuse(next(iter(errors.values()), "商机选项已变化，请核对后再保存"))
            data = OpportunityCreate.model_validate(canonical)
            if match_opportunity_target(
                db, team_id=task.team_id, customer_id=customer.id, data=data, current_read=True,
            ).status != "DISTINCT":
                return refuse(_OPPORTUNITY_DUPLICATE)
            await create_opportunity(
                OpportunityCreate.model_validate(canonical), team_id=task.team_id, current_user=user, db=db,
                assistant_command=command,
            )
            effect = checked_effect(db, command, kind)
    except HTTPException as exc:
        return refuse(str(exc.detail))
    except EntityFormError as exc:
        return refuse(next(iter(exc.errors.values()), "暂时不能新建商机"))
    except SQLAlchemyError:
        logger.exception("assistant opportunity write failed task=%s", task.public_id)
        db.rollback()
        reporter.stage_failed(stage("write"))
        try:
            effect = checked_effect(db, command, kind)
        except Exception:
            _publish_unknown(db, task, kind, module.LABEL)
        if effect is not None:
            _publish_unknown(db, task, kind, module.LABEL)
        assert_owned_execution_lease(db, task)
        _mark_claim_status(db, claim, "NO_EFFECT")
        return _issue_form(db, task, module, user, _entity(task), hint=_NOT_SAVED_HINT,
                           action_name="entity_write_no_effect")
    except ValueError as exc:  # AssistantCRMNoEffect included: the CRM rolled back before writing.
        return refuse(str(exc) or "暂时不能新建商机")
    if opportunity_create_receipt_outcome(effect) is None:
        _publish_unknown(db, task, kind, module.LABEL)
    assert effect is not None and effect.target_public_id is not None
    name = str(canonical.get("opportunity_name") or module.LABEL)
    try:
        assert_owned_execution_lease(db, task)
        _mark_claim_status(db, claim, "SUCCEEDED", public_id=effect.target_public_id)
        receipt = _receipt(kind, effect.target_public_id, name, ctx.draft.customer_public_id, pending_review=True)
        task = apply_task_update(db, task, TaskUpdate(
            append_committed=[receipt], status=AssistantTaskStatus.COMPLETED, clear_waiting=True,
            action_actor="USER", action_name="entity_create",
            action_result={"kind": kind, "public_id": effect.target_public_id, "approval_id": effect.approval_id},
        )).task
        db.commit()
    except SQLAlchemyError:
        _publish_unknown(db, task, kind, module.LABEL)
    reporter.stage_done(stage("write"), ms=int((monotonic() - started) * 1000))
    return _outcome(task, f"商机已创建，待审批：{name}")


def _attach_inline_customer(db: Session, parent: AssistantTask, receipt: dict[str, object]) -> None:
    """The customer created inside another entity task is its own completed child task (D9)."""

    db.add(AssistantTask(
        team_id=parent.team_id, user_id=parent.user_id, status=AssistantTaskStatus.COMPLETED,
        task_kind=_CUSTOMER_KIND, parent_task_id=parent.id, goal=parent.goal, draft_json={}, waiting_json={},
        authority_json={}, committed_json=[receipt], version=0,
    ))
    entity = _entity(parent).model_copy(update={
        "customer_public_id": receipt["public_id"], "customer_name": receipt["name"],
    })
    apply_task_update(db, parent, TaskUpdate(
        draft=_with_entity(parent, entity), action_actor="USER", action_name="inline_customer_create",
        action_result={"kind": _CUSTOMER_KIND, "public_id": receipt["public_id"]},
    ))


def open_profile_child(db: Session, parent: AssistantTask, item: ProfileProposalItem) -> AssistantTask:
    """「去补充」 on a post-activity profile item: its own entity task under the activity task (D29).

    The child is bound to the activity's customer under the CRM's own permission rules and confirms
    separately; it never writes here.
    """

    from app.services.assistant.contracts import TaskDraft
    from app.services.assistant.task_state import load_authority

    child = AssistantTask(
        team_id=parent.team_id, user_id=parent.user_id, status=AssistantTaskStatus.ACTIVE, task_kind=item.kind,
        parent_task_id=parent.id, goal=item.quote[:2000], draft_json=TaskDraft().model_dump(mode="json"),
        waiting_json={}, authority_json={}, committed_json=[], version=0,
    )
    db.add(child)
    db.flush()
    module = module_for(item.kind)
    entity = EntityDraft(kind=item.kind, extracted=item.extracted, source_text=item.quote[:20000])
    user = _user(db, child)
    if user is None:
        _refuse(db, child, "你的账号已不在当前团队或已停用")
        return child
    customer = _customer(db, child, load_authority(parent).customer_public_id)
    if customer is not None:
        _bind_and_issue(db, child, module, user, entity, customer)
    else:
        _ask_customer(db, child, entity, "存到哪个客户？")
    return child


def _can_view_customer(db: Session, task: AssistantTask, user: User, customer: Customer) -> bool:
    from fastapi import HTTPException

    from app.core.deps import check_customer_view_permission
    from app.core.exceptions import AppException

    try:
        check_customer_view_permission(customer.public_id, task.team_id, user, db)
    except (HTTPException, AppException, PermissionError):
        return False
    return True


def _settle_duplicate(
    db: Session, task: AssistantTask, module: EntityFormModule, form: EntityFormModule, user: User,
    canonical: Canonical, exc: DuplicateRecordError, *, inline: bool,
) -> CoordinatorOutcome:
    """An existing record is never overwritten or duplicated; the user learns only what they may see."""

    from app.models.customer import Customer

    entity = _entity(task)
    if form.KIND == _CUSTOMER_KIND:
        existing = db.query(Customer).filter(
            Customer.team_id == task.team_id, Customer.id == exc.existing_id,
        ).one_or_none()
        if existing is None or not _can_view_customer(db, task, user, existing):
            return _issue_form(db, task, module, user, entity, inline=inline,
                               errors={"account_name": "已存在，请联系负责人"}, action_name="entity_duplicate_hidden")
        if inline:
            return _offer_customers(db, task, entity, f"客户“{existing.account_name}”已存在，未重复创建。", [
                {"id": existing.public_id, "label": f"用这个客户：{existing.account_name}"},
            ])
        receipt = _receipt(_CUSTOMER_KIND, existing.public_id, existing.account_name, existing.public_id, "existing")
        name = existing.account_name
    else:
        target = f"{form.TARGET_PREFIX}:{exc.existing_id}"
        name = exc.existing_name or str(canonical.get(_NAME_KEYS[form.KIND]) or form.LABEL)
        receipt = _receipt(form.KIND, target, name, entity.customer_public_id, "existing")
    customer = _customer(db, task, entity.customer_public_id)
    detail = form.describe_existing(FormContext(db, task, user, customer, entity), canonical, exc.existing_id)
    result = apply_task_update(db, task, TaskUpdate(
        append_committed=[receipt], status=AssistantTaskStatus.COMPLETED, clear_waiting=True,
        action_actor="USER", action_name="entity_existing",
        action_result={"kind": form.KIND, "public_id": receipt["public_id"]},
    ))
    message = "；".join(part for part in (f"{form.LABEL}“{name}”已存在，未重复创建", detail) if part)
    return _outcome(result.task, message)


# ---------------------------------------------------------------------------
# Operator adjudication of an UNKNOWN entity write
# ---------------------------------------------------------------------------


async def adjudicate_entity_claim(
    db: Session, claim: AssistantAction, task: AssistantTask, *, operator_id: int, reason: str,
) -> None:
    """Settle only a provable effect of the frozen command. The caller owns the transaction."""

    correlation = claim.result_json or {}
    claim_status = correlation.get("status")
    key = correlation.get("proposal_key")
    kind = key.removeprefix("entity:") if isinstance(key, str) and key.startswith("entity:") else None
    canonical = correlation.get("form_values")
    if kind not in ACTIONS or (kind != task.task_kind and kind != _CUSTOMER_KIND) or not isinstance(canonical, dict):
        raise TaskStateConflictError("待核对命令与当前任务不匹配。")
    latest = _latest_claim(db, task, kind)
    if latest is None or latest.id != claim.id:
        raise TaskStateConflictError("待核对命令已变化。")
    command = entity_command(task, kind, canonical)
    if correlation.get("command_id") != command.command_id or correlation.get("fingerprint") != command.fingerprint:
        raise TaskStateConflictError("命令与冻结表单不匹配。")
    effect = checked_effect(db, command, kind)
    if effect is None:
        raise TaskStateConflictError("缺少可归因的目标提交回执，结果仍待核对。")
    entity = _entity(task)
    public_id = effect.target_public_id
    if kind == _CUSTOMER_KIND:
        customer = _customer(db, task, public_id)
        if customer is None:
            raise TaskStateConflictError("已提交的客户不存在，结果仍待核对。")
        receipt = _receipt(kind, public_id, customer.account_name, public_id)
    else:
        if kind == "opportunity_create" and effect.approval_id is None:
            raise TaskStateConflictError("商机创建缺少审批凭据，结果仍待核对。")
        receipt = _receipt(kind, public_id, str(canonical.get(_NAME_KEYS[kind]) or module_for(kind).LABEL),
                           entity.customer_public_id, pending_review=kind == "opportunity_create")
    if kind == task.task_kind:
        apply_task_update(db, task, TaskUpdate(
            require_no_active_turn=True, clear_waiting=True, status=AssistantTaskStatus.COMPLETED,
            append_committed=[receipt], action_actor="SYSTEM", action_name="reconcile_entity_claim",
            action_result={"kind": kind, "public_id": public_id, "reconciled": True, "adjudicated_by": operator_id},
        ))
    else:
        user = _user(db, task)
        if user is None:
            raise TaskStateConflictError("任务所属用户已不可用。")
        _attach_inline_customer(db, task, receipt)
        _bind_and_issue(db, task, module_for(task.task_kind), user, _entity(task), customer, fence=True)
    changed = db.execute(sql_update(AssistantAction).where(
        AssistantAction.id == claim.id,
        AssistantAction.team_id == task.team_id,
        AssistantAction.task_id == task.id,
        AssistantAction.action == _CLAIM,
        AssistantAction.result_json["status"].as_string() == claim_status,
        AssistantAction.result_json["command_id"].as_string() == command.command_id,
        AssistantAction.result_json["fingerprint"].as_string() == command.fingerprint,
    ).values(result_json={**correlation, "status": "RECONCILED", "public_id": public_id,
                         "adjudicated_by": operator_id, "adjudication_reason": reason})
        .execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise TaskStateConflictError("待核对命令已变化。")
