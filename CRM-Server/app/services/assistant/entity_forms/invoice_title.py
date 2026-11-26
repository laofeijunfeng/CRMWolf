"""开票抬头 form: an existing taxpayer id is reported, never overwritten."""
# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.assistant.entity_forms import (
    Canonical,
    EntityFormError,
    FieldSpec,
    FormContext,
    Submitted,
    WriteResult,
    refresh_after_commit,
    value,
)
from app.utils.dedupe_normalizer import normalize_taxpayer_id

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.services.assistant.contracts import EntityFieldValue, EntityQuote

TITLE_TYPE = FieldSpec("title_type", "抬头类型", "select", required=True)
TITLE = FieldSpec("title", "开票抬头", required=True, max_length=100)
TAXPAYER = FieldSpec("taxpayer_id", "纳税人识别号", required=True, max_length=30)
BANK = FieldSpec("bank_name", "开户行", max_length=50)
ACCOUNT = FieldSpec("bank_account", "开户账号", max_length=30)
ADDRESS = FieldSpec("address", "开票地址", max_length=200)
PHONE = FieldSpec("phone", "电话", max_length=20)
_TYPE_OPTIONS = [{"value": "COMPANY", "label": "单位"}, {"value": "PERSONAL", "label": "个人"}]
_DIFF_LABELS = {"title": "抬头", "bank_name": "开户行", "bank_account": "开户账号", "address": "地址", "phone": "电话"}


class InvoiceTitleForm:
    KIND = "invoice_title_create"
    LABEL = "开票抬头"
    TARGET_PREFIX = "invoice_title"
    EXTRACT_KEYS: Mapping[str, str] = {
        "title_type": "原文明确说个人抬头时填“个人”，明确说单位/公司抬头时填“单位”",
        "title": "开票抬头名称，原样照抄",
        "taxpayer_id": "纳税人识别号/税号，原样照抄；禁止编造",
        "bank_name": "开户行",
        "bank_account": "开户账号，原样照抄；禁止编造",
        "address": "开票地址",
        "phone": "开票电话",
    }
    FIELD_KEYS = frozenset({"title_type", "title", "taxpayer_id", "bank_name", "bank_account", "address", "phone"})

    def prepare(self, ctx: FormContext, extracted: list[EntityQuote]) -> dict[str, EntityFieldValue]:
        out: dict[str, EntityFieldValue] = {}
        seen: set[str] = set()
        for item in extracted:
            if item.key in seen:
                # A second set of invoice details: keep the first, never merge two titles into one form.
                out.setdefault("_second_set", value("ORIGINAL", "true"))
                continue
            seen.add(item.key)
            text = item.value.strip()[:2000]
            if item.key == "title_type":
                if text in {"个人", "单位"}:
                    out["title_type"] = value("DERIVED", "PERSONAL" if text == "个人" else "COMPANY",
                                              phrase=item.quote[:200])
            elif item.key == "taxpayer_id":
                normalized = normalize_taxpayer_id(text)
                out["taxpayer_id"] = value("ORIGINAL" if normalized == text else "NORMALIZED", normalized or None)
            else:
                out[item.key] = value("ORIGINAL", text)
        out.setdefault("title_type", value("DEFAULT", "COMPANY"))
        if "title" not in out and ctx.customer is not None:
            out["title"] = value("CUSTOMER_DEFAULT", ctx.customer.account_name[:2000])
        return out

    def fields(
        self, ctx: FormContext, values: Mapping[str, EntityFieldValue],  # noqa: ARG002
        submitted: Submitted | None, errors: Mapping[str, str],
    ) -> list[dict[str, object]]:
        return [
            TITLE_TYPE.render(values, submitted, errors, options=_TYPE_OPTIONS),
            TITLE.render(values, submitted, errors),
            TAXPAYER.render(values, submitted, errors),
            BANK.render(values, submitted, errors),
            ACCOUNT.render(values, submitted, errors),
            ADDRESS.render(values, submitted, errors),
            PHONE.render(values, submitted, errors),
        ]

    def notices(self, ctx: FormContext, values: Mapping[str, EntityFieldValue]) -> list[str]:
        notes: list[str] = []
        title = values.get("title")
        if ctx.customer is not None and title is not None and title.value and title.value != ctx.customer.account_name:
            notes.append("抬头与客户名称不同，请核对")
        if "_second_set" in values:
            notes.append("原文有第二套开票信息，这里只填了第一套，另一套保存后再发一次")
        notes.append("申请开票去发票管理")
        return notes

    def validate(self, ctx: FormContext, submitted: Submitted) -> tuple[Canonical, dict[str, str]]:  # noqa: ARG002
        errors: dict[str, str] = {}
        title_type = TITLE_TYPE.text(submitted, errors)
        if title_type is not None and title_type not in {"COMPANY", "PERSONAL"}:
            errors["title_type"] = "请选择抬头类型"
        raw_taxpayer = TAXPAYER.text(submitted, {})
        taxpayer = normalize_taxpayer_id(raw_taxpayer) or None
        TAXPAYER.text({"taxpayer_id": taxpayer}, errors)
        return {
            "title_type": title_type,
            "title": TITLE.text(submitted, errors),
            "taxpayer_id": taxpayer,
            "bank_name": BANK.text(submitted, errors),
            "bank_account": ACCOUNT.text(submitted, errors),
            "address": ADDRESS.text(submitted, errors),
            "phone": PHONE.text(submitted, errors),
        }, errors

    def write(self, ctx: FormContext, values: Canonical) -> WriteResult:
        from pydantic import ValidationError

        from app.crud.invoice import invoice_title_crud
        from app.schemas.invoice import InvoiceTitleCreate

        assert ctx.customer is not None
        try:
            obj_in = InvoiceTitleCreate.model_validate(values)
        except ValidationError as exc:
            raise EntityFormError({"title": "开票资料不完整，请核对"}) from exc
        title = invoice_title_crud.create(ctx.db, ctx.customer.id, obj_in, ctx.team_id, commit=False)
        return WriteResult(
            target_public_id=f"invoice_title:{title.id}",
            name=title.title[:200],
            customer_public_id=ctx.customer.public_id,
            after_commit=refresh_after_commit("invoice_title", title, str(ctx.user.id)),
        )

    def describe_existing(self, ctx: FormContext, values: Canonical, existing_id: int) -> str | None:
        """Only the fields that differ from the stored title; nothing is overwritten."""

        from app.models.invoice import InvoiceTitle

        existing = ctx.db.query(InvoiceTitle).filter(
            InvoiceTitle.id == existing_id, InvoiceTitle.team_id == ctx.team_id,
        ).one_or_none()
        if existing is None:
            return None
        differ = [
            label for key, label in _DIFF_LABELS.items()
            if values.get(key) and values.get(key) != getattr(existing, key)
        ]
        return f"这次填的{'、'.join(differ)}和已有抬头不同，如需修改请到客户详情" if differ else None


FORM = InvoiceTitleForm()
