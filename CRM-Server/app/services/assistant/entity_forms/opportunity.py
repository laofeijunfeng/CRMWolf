"""商机 form: direct creation; the CRM still submits it for approval (D27/D28).

Field rules, options and validation are the follow-up opportunity form's own; only the evidence
differs: values come from the rep's direct request instead of a committed activity.
"""
# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

import re
from contextlib import suppress
from datetime import date
from decimal import Decimal
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
    from app.services.assistant.opportunity_form import _FormOptions

# Select options narrowed by another field: stage by procurement method, modules by product.
_PARENTS = {"stage_id": "procurement_method_id", "product_module_public_ids": "product_public_id"}
_TRUNCATED_NOTICE = "选项较多，表单只列出前 50 项；找不到时请到客户页手动创建商机"
_YEARS = re.compile(r"(?<![\d.])([1-9][0-9]?)\s*年(?![底初中内末前后度])")
_PERPETUAL = re.compile(r"买断|永久")
_APPROXIMATE = re.compile(r"左右|大概|大约|约|差不多|上下|来万")
_RELATIVE_DATES = ("年底", "下个月", "Q1", "Q2", "Q3", "Q4")
_PURCHASE_WORDS = (("续", "RENEWAL"), ("增购", "EXPANSION"), ("加购", "EXPANSION"), ("扩容", "EXPANSION"),
                   ("新购", "NEW"))


def _spec(field: Mapping[str, object]) -> FieldSpec:
    key = str(field["key"])
    minimum, maximum, length = field.get("minimum"), field.get("maximum"), field.get("max_length")
    return FieldSpec(
        key, str(field["label"]), field["field_type"],  # type: ignore[arg-type]
        required=bool(field.get("required")),
        max_length=length if isinstance(length, int) else None,
        minimum=float(minimum) if isinstance(minimum, (int, float)) else None,
        maximum=float(maximum) if isinstance(maximum, (int, float)) else None,
        depends_on_key=_PARENTS.get(key),
    )


def _specs() -> list[FieldSpec]:
    from app.services.assistant.opportunity_form import _FIELDS

    return [_spec(field) for field in _FIELDS]


def _month_end(year: int, month: int) -> date:
    following = date(year + month // 12, month % 12 + 1, 1)
    return date.fromordinal(following.toordinal() - 1)


def _relative_date(phrase: str, today: date) -> date:
    if phrase == "年底":
        return date(today.year, 12, 31)
    if phrase == "下个月":
        return _month_end(today.year + today.month // 12, today.month % 12 + 1)
    end = _month_end(today.year, int(phrase[1]) * 3)
    return end if end >= today else _month_end(today.year + 1, int(phrase[1]) * 3)


def _unique(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    matches = list(pattern.finditer(text))
    return matches[0] if len(matches) == 1 else None


def _utterance(text: str, out: dict[str, EntityFieldValue]) -> None:
    """Direct literals are filled; approximate amounts and relative dates are only offered (D28)."""

    from app.schemas.opportunity import LicenseTypeEnum
    from app.services.assistant.opportunity_form import _AMOUNT, _COUNT, _DATE, _MAX_COUNT, _valid_amount
    from app.utils.time import business_today

    approximate = _APPROXIMATE.search(text) is not None
    if (count := _unique(_COUNT, text)) and 1 <= int(count[1]) <= _MAX_COUNT:
        out["user_count"] = value("ORIGINAL", int(count[1]))
    if amount := _unique(_AMOUNT, text):
        multiplier = {"亿": 10**8, "亿元": 10**8, "万": 10**4, "万元": 10**4, "元": 1}[amount[2]]
        total = Decimal(amount[1]) * multiplier
        if _valid_amount(total) and approximate:
            out["total_amount"] = value("ORIGINAL", None, choices=[format(total.normalize(), "f")],
                                        warning="原话是约数，请确认金额")
        elif _valid_amount(total):
            out["total_amount"] = value("ORIGINAL", float(total))
    if (closing := _unique(_DATE, text)) is not None:
        with suppress(ValueError):
            out["expected_closing_date"] = value(
                "ORIGINAL", date(*(int(v) for v in closing.groups() if v is not None)).isoformat(),
            )
    if "expected_closing_date" not in out and (
        offered := [phrase for phrase in _RELATIVE_DATES if phrase in text.upper()]
    ):
        today = business_today()
        out["expected_closing_date"] = value(
            "ORIGINAL", None, choices=[_relative_date(phrase, today).isoformat() for phrase in offered],
            warning=f"原话是“{offered[0]}”，请选一个日期",
        )
    if perpetual := _PERPETUAL.search(text):
        out["license_type"] = value("DERIVED", LicenseTypeEnum.PERPETUAL.value, phrase=perpetual[0])
    elif (years := _unique(_YEARS, _DATE.sub("", text))) is not None:
        out["subscription_years"] = value("DERIVED", int(years[1]), phrase=years[0].strip())
    if purchase := next(((word, kind) for word, kind in _PURCHASE_WORDS if word in text), None):
        out["purchase_type"] = value("DERIVED", purchase[1], phrase=purchase[0])


def _catalog(ctx: FormContext) -> tuple[_FormOptions, bool]:
    """Live options, recomputed on every render and submit (never frozen); True when a list was cut."""

    from app.models.user import User
    from app.schemas.opportunity import LicenseTypeEnum, PurchaseTypeEnum
    from app.services.assistant.opportunity_form import (
        _MAX_OPTIONS,
        OpportunityFormError,
        _option,
        _owners,
        _product_choices,
        _stage_choices,
    )

    assert ctx.customer is not None
    try:
        with ctx.db.no_autoflush:
            methods, stages, stages_cut = _stage_choices(ctx.db, ctx.team_id, ctx.customer)
            products, modules, products_cut = _product_choices(ctx.db, ctx.team_id, ctx.customer)
            others = (
                _owners(ctx.db, ctx.team_id).filter(User.id != ctx.user.id).order_by(User.name, User.id)
                .limit(_MAX_OPTIONS - 1).all()
            )
    except OpportunityFormError as exc:
        raise EntityFormError({"form": f"{exc}，暂时不能新建商机，请联系管理员"}) from exc
    product_ids = {product.id: str(product.public_id) for product in products}
    return {
        "license_type": [_option(v.value, v.description) for v in LicenseTypeEnum],
        "purchase_type": [_option(v.value, v.description) for v in PurchaseTypeEnum],
        "procurement_method_id": [_option(str(m.id), str(m.name)) for m in methods],
        "stage_id": [
            _option(str(s.id), str(s.stage_name), procurement_method_id=str(s.procurement_method_id)) for s in stages
        ],
        "owner_id": [_option(str(u.id), str(u.name)) for u in (ctx.user, *others)],
        "product_public_id": [_option(str(p.public_id), str(p.name)) for p in products],
        # Base module first per product: the first module of a product is the one preselected.
        "product_module_public_ids": [
            _option(str(m.public_id), str(m.name), product_public_id=product_ids[m.product_id]) for m in modules
        ],
    }, stages_cut or products_cut


def _rendered(key: str, options: _FormOptions) -> list[dict[str, str]] | None:
    parent = _PARENTS.get(key)
    out = []
    for option in options.get(key, []):
        bound = {"value": option["value"], "label": option["label"]}
        if parent is not None:
            bound["depends_on_value"] = option[parent]
        out.append(bound)
    return out or None


def _named(ctx: FormContext, fields: Mapping[str, EntityFieldValue]) -> str | None:
    """The CRM's own auto name; it only reads the customer, user count and license fields."""

    from app.crud.opportunity import opportunity_crud
    from app.schemas.opportunity import OpportunityCreate

    assert ctx.customer is not None
    count = fields.get("user_count")
    if count is None or not isinstance(count.value, int):
        return None
    data = {key: item.value for key, item in fields.items() if item.value is not None}
    return opportunity_crud._build_opportunity_name(
        OpportunityCreate.model_construct(_fields_set=None, customer_id=ctx.customer.public_id, **data), ctx.customer,
    )[:255]


class OpportunityForm:
    KIND = "opportunity_create"
    LABEL = "商机"
    # Opportunities carry their own public id.
    TARGET_PREFIX = ""
    EXTRACT_KEYS: Mapping[str, str] = {
        "product": "原文明确说的产品名称，原样照抄",
        "decision_maker_count": "原文明确的采购决策人数，只填数字",
    }
    FIELD_KEYS = frozenset(spec.key for spec in _specs())

    def prepare(self, ctx: FormContext, extracted: list[EntityQuote]) -> dict[str, EntityFieldValue]:
        from app.schemas.opportunity import LicenseTypeEnum, PurchaseTypeEnum

        assert ctx.customer is not None
        options, _ = _catalog(ctx)
        out: dict[str, EntityFieldValue] = {
            "license_type": value("DEFAULT", LicenseTypeEnum.SUBSCRIPTION.value),
            "subscription_years": value("DEFAULT", 1),
            "purchase_type": value("DEFAULT", PurchaseTypeEnum.NEW.value),
            "owner_id": value("DEFAULT", str(ctx.user.id)),
        }
        _utterance(ctx.draft.source_text, out)
        if out["license_type"].value == LicenseTypeEnum.PERPETUAL.value:
            out.pop("subscription_years")
        products = options["product_public_id"]
        named = next(
            (
                (product, item.quote) for item in extracted if item.key == "product"
                for product in products if product["label"].casefold() == item.value.strip().casefold()
            ),
            None,
        )
        product = named[0] if named else products[0]
        out["product_public_id"] = value("ORIGINAL" if named else "DEFAULT", product["value"])
        base = next(m["value"] for m in options["product_module_public_ids"]
                    if m["product_public_id"] == product["value"])
        out["product_module_public_ids"] = value("DEFAULT", [base])
        decision = next((item for item in extracted if item.key == "decision_maker_count"), None)
        if decision is not None and re.fullmatch(r"[1-9][0-9]{0,4}", decision.value.strip()):
            out["decision_maker_count"] = value("ORIGINAL", int(decision.value.strip()))
        default_method = ctx.customer.default_procurement_method_id
        if any(m["value"] == str(default_method) for m in options["procurement_method_id"]):
            out["procurement_method_id"] = value("CUSTOMER_DEFAULT", str(default_method))
            # Stages arrive default-start first per method.
            stage = next((s for s in options["stage_id"] if s["procurement_method_id"] == str(default_method)), None)
            if stage is not None:
                out["stage_id"] = value("CUSTOMER_DEFAULT", stage["value"])
        if (name := _named(ctx, out)) is not None:
            out["opportunity_name"] = value("AUTO_NAME", name)
        return out

    def fields(
        self, ctx: FormContext, values: Mapping[str, EntityFieldValue],
        submitted: Submitted | None, errors: Mapping[str, str],
    ) -> list[dict[str, object]]:
        options, _ = _catalog(ctx)
        return [spec.render(values, submitted, errors, options=_rendered(spec.key, options)) for spec in _specs()]

    def notices(self, ctx: FormContext, values: Mapping[str, EntityFieldValue]) -> list[str]:  # noqa: ARG002
        _, truncated = _catalog(ctx)
        notes = ["提交后进入审批，审批通过前不计入商机统计"]
        if truncated:
            notes.append(_TRUNCATED_NOTICE)
        return notes

    def validate(self, ctx: FormContext, submitted: Submitted) -> tuple[Canonical, dict[str, str]]:
        """The follow-up form's rules against live options; the CRM schema has the last word."""

        from pydantic import ValidationError

        from app.crud.opportunity import opportunity_crud
        from app.schemas.opportunity import OpportunityCreate
        from app.services.assistant.opportunity_form import _MAX_UNIT_PRICE, _catalog_values, _commercial_values
        from app.services.pricing import pricing_service

        assert ctx.customer is not None
        options, _ = _catalog(ctx)
        defaults = {key: item.value for key, item in ctx.draft.fields.items() if item.value is not None}
        errors: dict[str, str] = {}
        data: dict[str, object] = {key: submitted.get(key, defaults.get(key)) for key in self.FIELD_KEYS}
        data["customer_id"] = ctx.customer.public_id
        with ctx.db.no_autoflush:
            _commercial_values(data, defaults, errors)  # type: ignore[arg-type]
            _catalog_values(ctx.db, ctx.team_id, data, options, errors)
        try:
            create = OpportunityCreate.model_validate(data)
        except ValidationError as exc:
            for item in exc.errors():
                key = str(item["loc"][0]) if item["loc"] else "form"
                errors.setdefault(key if key in self.FIELD_KEYS else "form", item["msg"])
            return {}, errors
        if errors:
            return {}, errors
        unit_price = pricing_service.calculate_unit_price(
            create.total_amount, create.user_count, create.license_type, create.subscription_years or 1,
        )
        if unit_price > _MAX_UNIT_PRICE:
            return {}, {"total_amount": "预计总金额与用户数计算出的标准单价超出有效范围"}
        create.opportunity_name = opportunity_crud._build_opportunity_name(create, ctx.customer)
        return create.model_dump(mode="json"), {}

    def write(self, ctx: FormContext, values: Canonical) -> WriteResult:  # noqa: ARG002
        # The CRM commits an opportunity together with its approval; entity_tasks awaits it separately.
        raise TypeError("opportunities are created through create_opportunity, not a staged write")

    def describe_existing(self, ctx: FormContext, values: Canonical, existing_id: int) -> str | None:  # noqa: ARG002
        return "已存在相同或无法区分的商机，请到商机页查看"


FORM = OpportunityForm()
