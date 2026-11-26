"""客户 form: required choices are filled only on a unique match, never defaulted to 其他."""
# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.services.assistant.entity_forms import (
    Canonical,
    EntityFormError,
    FieldSpec,
    FormContext,
    Submitted,
    WriteResult,
    value,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.services.assistant.contracts import EntityFieldValue, EntityQuote

SCALE_BANDS = ("1-50人", "51-200人", "201-500人", "501-1000人", "1000人以上")
_UPPER = (50, 200, 500, 1000)
_MAX_OPTIONS = 50
_TAILS = re.compile(r"(那边的人|那边|那家|这家|的人)$")
_FUZZY = re.compile(r"(多|来|左右|上下|出头)")
_NUMBER = re.compile(r"\d+|[一二两三四五六七八九十百千万]+")
_DIGITS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}

NAME = FieldSpec("account_name", "客户名称", required=True, max_length=255)
CITY = FieldSpec("city", "城市", required=True, max_length=100)
SCALE = FieldSpec("company_scale", "公司规模", "select", required=True)
SOURCE = FieldSpec("source_public_id", "获客来源", "select", required=True)
METHOD = FieldSpec("default_procurement_method_id", "采购方式", "select", required=True)
PRODUCT = FieldSpec("product_public_id", "意向产品", "select", required=True)
INDUSTRY = FieldSpec("industry", "行业", max_length=100)
ADDRESS = FieldSpec("address", "地址", max_length=500)
_SELECT_KEYS = {"source": SOURCE, "procurement_method": METHOD, "product": PRODUCT}


def _cn_number(text: str) -> int | None:
    if text.isdigit():
        return int(text)
    total, section, digit = 0, 0, None
    for char in text:
        if char in _DIGITS:
            digit = _DIGITS[char]
        elif char == "万":
            total = (total + section + (digit or 0)) * 10000 or 10000
            section, digit = 0, None
        else:
            section += (digit if digit is not None else 1) * _UNITS[char]
            digit = None
    result = total + section + (digit or 0)
    return result or None


def _band(count: int) -> str:
    return next((band for band, upper in zip(SCALE_BANDS, _UPPER, strict=False) if count <= upper), SCALE_BANDS[-1])


def scale_bands(phrase: str) -> list[str]:
    """Bands a spoken headcount allows: one means fill it, several mean the user picks."""

    text = phrase.replace(" ", "")
    if "上万" in text or "几千" in text:
        return [SCALE_BANDS[4]]
    if "几百" in text:
        return [SCALE_BANDS[2], SCALE_BANDS[3]]
    if "几十" in text:
        return [SCALE_BANDS[0], SCALE_BANDS[1]]
    numbers = [n for n in (_cn_number(m) for m in _NUMBER.findall(text)) if n]
    if not numbers:
        return list(SCALE_BANDS) if re.search(r"大公司|小团队|大厂|小公司", text) else []
    if len(numbers) >= 2:
        return sorted({_band(numbers[0]), _band(numbers[1])}, key=SCALE_BANDS.index)
    count = numbers[0]
    if count in _UPPER and _FUZZY.search(text) and not text.endswith("来") and "来人" not in text:
        index = _UPPER.index(count)
        return [SCALE_BANDS[index], SCALE_BANDS[index + 1]]
    return [_band(count)]


def _unique(name: str, options: list[dict[str, str]]) -> str | None:
    wanted = name.strip()
    exact = [o["value"] for o in options if o["label"] == wanted]
    if len(exact) == 1:
        return exact[0]
    partial = [o["value"] for o in options if wanted and (wanted in o["label"] or o["label"] in wanted)]
    return partial[0] if len(partial) == 1 else None


def _options(ctx: FormContext) -> dict[str, list[dict[str, str]]]:
    from app.crud.acquisition_source import acquisition_source_crud
    from app.services.assistant.opportunity_form import _methods, _products

    sources = acquisition_source_crud.list_options(ctx.db, ctx.team_id)
    return {
        SOURCE.key: [{"value": s.public_id, "label": s.name} for s in sources][:_MAX_OPTIONS],
        METHOD.key: [
            {"value": str(m.id), "label": m.name} for m in _methods(ctx.db, ctx.team_id).limit(_MAX_OPTIONS)
        ],
        PRODUCT.key: [
            {"value": p.public_id, "label": p.name} for p in _products(ctx.db, ctx.team_id).limit(_MAX_OPTIONS)
        ],
    }


def _industry_name(ctx: FormContext, text: str) -> str | None:
    from app.crud.industry import industry_crud

    matches = [row.name for row in industry_crud.get_all_active(ctx.db) if row.name == text or row.code == text]
    return matches[0] if len(matches) == 1 else None


class CustomerForm:
    KIND = "customer_create"
    LABEL = "客户"
    TARGET_PREFIX = ""
    EXTRACT_KEYS: Mapping[str, str] = {
        "account_name": "客户公司名称，原样照抄；不要补“有限公司”",
        "city": "原文说的城市或区，原样照抄",
        "company_scale": "原文描述人数规模的短语，原样照抄（如“100多人”“几百人”）",
        "source": "原文明确说的获客来源",
        "procurement_method": "原文明确说的采购方式",
        "product": "原文明确说的意向产品",
        "industry": "原文明确说的行业",
        "address": "公司详细地址",
    }
    FIELD_KEYS = frozenset({
        "account_name", "city", "company_scale", "source_public_id", "default_procurement_method_id",
        "product_public_id", "industry", "address",
    })

    def prepare(self, ctx: FormContext, extracted: list[EntityQuote]) -> dict[str, EntityFieldValue]:
        out: dict[str, EntityFieldValue] = {}
        options: dict[str, list[dict[str, str]]] | None = None
        for item in extracted:
            text = item.value.strip()
            if item.key == "account_name":
                name = _TAILS.sub("", text).strip() or text
                out[NAME.key] = value("ORIGINAL" if name == text else "NORMALIZED", name[:2000])
            elif item.key == "city":
                city = text.removesuffix("的") or text
                out[CITY.key] = value("ORIGINAL", city[:2000])
            elif item.key == "company_scale":
                bands = scale_bands(text)
                if len(bands) == 1:
                    out[SCALE.key] = value("DERIVED", bands[0], phrase=item.quote[:200])
                elif bands:
                    out[SCALE.key] = value("DERIVED", None, phrase=item.quote[:200], choices=bands,
                                           warning=f"“{item.quote[:40]}”对应不止一个规模，请选一个")
            elif item.key in _SELECT_KEYS:
                spec = _SELECT_KEYS[item.key]
                options = options if options is not None else _options(ctx)
                matched = _unique(text, options[spec.key])
                if matched is not None:
                    out[spec.key] = value("ORIGINAL", matched)
            elif item.key == "industry":
                industry = _industry_name(ctx, text)
                if industry is not None:
                    out[INDUSTRY.key] = value("ORIGINAL", industry)
            elif item.key == "address":
                out[ADDRESS.key] = value("ORIGINAL", text[:2000])
        return out

    def fields(
        self, ctx: FormContext, values: Mapping[str, EntityFieldValue],
        submitted: Submitted | None, errors: Mapping[str, str],
    ) -> list[dict[str, object]]:
        options = _options(ctx)
        rendered = [
            NAME.render(values, submitted, errors),
            CITY.render(values, submitted, errors),
            SCALE.render(values, submitted, errors, options=[{"value": b, "label": b} for b in SCALE_BANDS]),
        ]
        for spec in (SOURCE, METHOD, PRODUCT):
            if options[spec.key]:
                rendered.append(spec.render(values, submitted, errors, options=options[spec.key]))
        rendered += [INDUSTRY.render(values, submitted, errors), ADDRESS.render(values, submitted, errors)]
        return rendered

    def notices(self, ctx: FormContext, values: Mapping[str, EntityFieldValue]) -> list[str]:  # noqa: ARG002
        notes = ["负责人默认是你，创建后到客户详情转交"]
        options = _options(ctx)
        if not options[PRODUCT.key]:
            notes.append("团队还没有可选的产品，请先在设置里启用产品")
        if not options[METHOD.key] or not options[SOURCE.key]:
            notes.append("团队还没有可选的获客来源或采购方式，请先在设置里维护")
        return notes

    def validate(self, ctx: FormContext, submitted: Submitted) -> tuple[Canonical, dict[str, str]]:
        errors: dict[str, str] = {}
        options = _options(ctx)
        canonical: Canonical = {
            NAME.key: NAME.text(submitted, errors),
            CITY.key: CITY.text(submitted, errors),
        }
        scale = SCALE.text(submitted, errors)
        if scale is not None and scale not in SCALE_BANDS:
            errors[SCALE.key] = "请选择公司规模"
        canonical[SCALE.key] = scale
        for spec in (SOURCE, METHOD, PRODUCT):
            picked = spec.text(submitted, {})
            if picked is None or picked not in {o["value"] for o in options[spec.key]}:
                errors[spec.key] = f"请选择{spec.label}"
            canonical[spec.key] = picked
        industry = INDUSTRY.text(submitted, errors)
        if industry is not None and _industry_name(ctx, industry) is None:
            errors[INDUSTRY.key] = "行业不在系统列表里，请改正或留空"
        canonical[INDUSTRY.key] = industry
        canonical[ADDRESS.key] = ADDRESS.text(submitted, errors)
        return canonical, errors

    def write(self, ctx: FormContext, values: Canonical) -> WriteResult:
        from pydantic import ValidationError

        from app.core.exceptions import DuplicateRecordError
        from app.crud.customer import customer_crud
        from app.crud.product_intent import ProductNotFoundError
        from app.schemas.customer import CustomerCreate
        from app.services.acquisition_source_service import AcquisitionSourceError
        from app.services.customer_lifecycle_post_commit_coordinator import (
            customer_lifecycle_post_commit_coordinator as lifecycle,
        )
        from app.services.customer_name_conflicts import customer_name_conflict_error

        name = str(values[NAME.key] or "")
        existing = customer_crud.get_by_name(ctx.db, name, ctx.team_id)
        if existing is not None:
            # The task decides what the user may learn about it (D10); the CRM message stays generic.
            raise DuplicateRecordError(
                entity="customer", existing_id=existing.id, existing_name=existing.account_name,
                detail="客户名称已存在",
            )
        conflict = customer_name_conflict_error(ctx.db, name, ctx.team_id)
        if conflict is not None:
            raise EntityFormError({NAME.key: conflict})
        method = values[METHOD.key]
        try:
            obj_in = CustomerCreate.model_validate({
                **values, METHOD.key: int(method) if isinstance(method, str) else None,
            })
            customer = customer_crud.create(
                db=ctx.db, obj_in=obj_in, creator_id=str(ctx.user.id), team_id=ctx.team_id,
                operator_name=ctx.user.name, commit=False,
            )
        except ValidationError as exc:
            raise EntityFormError({NAME.key: "客户资料不完整，请核对"}) from exc
        except AcquisitionSourceError as exc:
            raise EntityFormError({SOURCE.key: str(exc) or "获客来源不可用"}) from exc
        except ProductNotFoundError as exc:
            raise EntityFormError({PRODUCT.key: str(exc) or "产品不可用"}) from exc
        except ValueError as exc:
            raise EntityFormError({NAME.key: str(exc)[:500] or "客户资料不完整"}) from exc
        work = lifecycle.prepare_in_transaction(
            ctx.db, customer=customer, actor_id=str(ctx.user.id), trigger_type="customer_created",
        )

        def kick() -> list[str]:
            return list(lifecycle.kick(work) or [])

        return WriteResult(
            target_public_id=customer.public_id,
            name=customer.account_name[:200],
            customer_public_id=customer.public_id,
            after_commit=kick,
        )

    def describe_existing(self, ctx: FormContext, values: Canonical, existing_id: int) -> str | None:  # noqa: ARG002
        return None


FORM = CustomerForm()
