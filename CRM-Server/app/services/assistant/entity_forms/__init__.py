"""Server-side forms for direct-create entity tasks: one module per record kind.

Each kind module exposes ``EntityFormModule``. ``entity_tasks`` owns the task flow and the write
sequence; the modules own field rules, provenance and the staged CRM call.
"""
# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

from pydantic import JsonValue

from app.services.assistant.contracts import EntityDraft, EntityFieldValue, EntityKind, EntityQuote, FieldSource

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.assistant import AssistantTask
    from app.models.customer import Customer
    from app.models.user import User
    from app.services.customer_business_object_intelligence_service import CustomerBusinessObjectSourceType

logger = logging.getLogger(__name__)

SOURCE_LABELS: dict[FieldSource, str] = {
    "ORIGINAL": "来自原文",
    "DERIVED": "按原话",
    "DEFAULT": "默认值",
    "USER_CHOICE": "你选的",
    "SUPPLEMENT": "刚补充",
    "NORMALIZED": "已整理",
    "AUTO_NAME": "自动生成",
    "CUSTOMER_DEFAULT": "客户默认",
}
ACTIONS: dict[EntityKind, str] = {
    "contact_create": "create_contact",
    "invoice_title_create": "create_invoice_title",
    "deployment_create": "create_deployment",
    "customer_create": "create_customer",
}

Canonical = dict[str, str | bool | None]
Submitted = Mapping[str, JsonValue]


def source_label(value: EntityFieldValue | None) -> str | None:
    """The only place provenance becomes UI text; the client never derives it."""

    if value is None or value.value is None:
        return None
    if value.source == "DERIVED" and value.phrase:
        phrase = value.phrase if len(value.phrase) <= 34 else f"{value.phrase[:33]}…"
        return f"按“{phrase}”"
    return SOURCE_LABELS[value.source]


@dataclass
class FormContext:
    db: Session
    task: AssistantTask
    user: User
    # The bound customer; None only for the customer form itself.
    customer: Customer | None
    draft: EntityDraft

    @property
    def team_id(self) -> int:
        return self.task.team_id


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    field_type: Literal["text", "textarea", "select", "boolean"] = "text"
    required: bool = False
    max_length: int | None = None
    placeholder: str | None = None

    def render(
        self,
        values: Mapping[str, EntityFieldValue],
        submitted: Submitted | None,
        errors: Mapping[str, str],
        *,
        options: list[dict[str, str]] | None = None,
        suggestions: list[str] | None = None,
    ) -> dict[str, object]:
        """One validated ``InteractionField``: last submitted value wins, provenance only while unchanged."""

        from app.services.agent.ui.schemas import InteractionField

        drafted = values.get(self.key)
        label: str | None = None
        value: JsonValue
        if submitted is not None and self.key in submitted:
            value = submitted[self.key]
            if drafted is not None and drafted.value is not None and _same(value, drafted.value):
                label = source_label(drafted)
        else:
            value = drafted.value if drafted is not None else None
            label = source_label(drafted)
        if self.field_type == "boolean":
            value = value is True or value == "true"
        elif self.field_type == "select" and value not in {option["value"] for option in options or []}:
            value, label = None, None
        error = errors.get(self.key)
        if error is None and submitted is None and drafted is not None:
            error = drafted.warning
        text = self.field_type in {"text", "textarea"}
        return InteractionField.model_validate({
            "key": self.key,
            "label": self.label,
            "field_type": self.field_type,
            "required": self.required,
            "placeholder": self.placeholder,
            "default_value": value,
            "min_length": (1 if self.required else 0) if text else None,
            "max_length": self.max_length if text else None,
            "options": options or [],
            "source_label": label,
            "error_message": error,
            "suggestions": (suggestions if suggestions is not None else drafted.choices if drafted else [])[:8],
        }).model_dump(mode="json")

    def text(self, submitted: Submitted, errors: dict[str, str]) -> str | None:
        """Trimmed text value; records a required/length error instead of raising."""

        raw = submitted.get(self.key)
        value = str(raw).strip() if isinstance(raw, (str, int, float)) and not isinstance(raw, bool) else ""
        if not value:
            if self.required:
                errors[self.key] = f"请填写{self.label}"
            return None
        if self.max_length is not None and len(value) > self.max_length:
            errors[self.key] = f"{self.label}最多 {self.max_length} 个字，现在 {len(value)} 个"
        return value

    def flag(self, submitted: Submitted) -> bool:
        raw = submitted.get(self.key)
        return raw is True or raw == "true"


def _same(value: JsonValue, drafted: str) -> bool:
    if isinstance(value, bool):
        return ("true" if value else "false") == drafted
    return isinstance(value, (str, int, float)) and str(value).strip() == drafted


def value(source: FieldSource, text: str | None, **extra: object) -> EntityFieldValue:
    return EntityFieldValue.model_validate({"value": text, "source": source, **extra})


@dataclass
class WriteResult:
    """A staged (flushed, uncommitted) CRM write; ``after_commit`` runs best-effort side work."""

    target_public_id: str
    name: str
    customer_public_id: str
    after_commit: Callable[[], list[str]] = field(default=lambda: [])


class EntityFormError(ValueError):
    """The CRM refused the values; nothing was written and the form stays open."""

    def __init__(self, errors: Mapping[str, str]) -> None:
        super().__init__("; ".join(errors.values()))
        self.errors = dict(errors)


class EntityFormModule(Protocol):
    KIND: EntityKind
    LABEL: str
    # Effect target prefix (``contact`` → ``contact:<id>``); empty when the record has a public id.
    TARGET_PREFIX: str
    # Keys the extraction model may nominate, with one-line guidance each.
    EXTRACT_KEYS: Mapping[str, str]
    FIELD_KEYS: frozenset[str]

    def prepare(self, ctx: FormContext, extracted: list[EntityQuote]) -> dict[str, EntityFieldValue]: ...

    def fields(
        self, ctx: FormContext, values: Mapping[str, EntityFieldValue],
        submitted: Submitted | None, errors: Mapping[str, str],
    ) -> list[dict[str, object]]: ...

    def notices(self, ctx: FormContext, values: Mapping[str, EntityFieldValue]) -> list[str]: ...

    def validate(self, ctx: FormContext, submitted: Submitted) -> tuple[Canonical, dict[str, str]]: ...

    def write(self, ctx: FormContext, values: Canonical) -> WriteResult: ...

    def describe_existing(self, ctx: FormContext, values: Canonical, existing_id: int) -> str | None: ...


def module_for(kind: str) -> EntityFormModule:
    from app.services.assistant.entity_forms import contact, customer, deployment, invoice_title

    modules: dict[str, EntityFormModule] = {
        "contact_create": contact.FORM,
        "invoice_title_create": invoice_title.FORM,
        "deployment_create": deployment.FORM,
        "customer_create": customer.FORM,
    }
    return modules[kind]


def refresh_after_commit(
    source_type: CustomerBusinessObjectSourceType, obj: object, actor_id: str,
) -> Callable[[], list[str]]:
    """Customer intelligence refresh through the same seam the CRM child-record endpoints use."""

    def run() -> list[str]:
        from app.services.customer_business_object_intelligence_service import (
            customer_business_object_intelligence_service as service,
        )

        try:
            service.enqueue_object_change_refresh_after_commit(
                source_type=source_type, business_object=obj, change_type="created", actor_id=actor_id,
            )
        except Exception:
            logger.exception("assistant entity intelligence refresh failed source=%s", source_type)
        return []

    return run
