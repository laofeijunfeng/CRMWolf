"""联系人 form: only explicit words fill gender, decision-maker and the reporting line."""
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
    refresh_after_commit,
    value,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.models.customer import Contact
    from app.services.assistant.contracts import EntityFieldValue, EntityQuote

MOBILE = re.compile(r"^1[3-9]\d{9}$")
_TITLE_ONLY = re.compile(r"^.{1,2}(总|工|经理|老师|主任|老板)$")
_GENDERS = {"男": "1", "女": "2"}
_MAX_REPORTS_TO = 50

NAME = FieldSpec("name", "姓名", required=True, max_length=50)
GENDER = FieldSpec("gender", "性别", "select", required=True)
POSITION = FieldSpec("position", "职位", required=True, max_length=50)
MOBILE_FIELD = FieldSpec("mobile", "手机号", required=True, max_length=20)
EMAIL = FieldSpec("email", "邮箱", max_length=100)
WECHAT = FieldSpec("wechat_id", "微信", max_length=50)
DECISION = FieldSpec("is_decision_maker", "关键决策人", "boolean")
REPORTS_TO = FieldSpec("reports_to", "汇报对象", "select")
REMARK = FieldSpec("remark", "备注", "textarea", max_length=500)
_GENDER_OPTIONS = [{"value": "1", "label": "男"}, {"value": "2", "label": "女"}]


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"[\s\-()（）]", "", raw)
    if digits.startswith("+86"):
        digits = digits[3:]
    elif digits.startswith("0086"):
        digits = digits[4:]
    elif digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    return digits


def _contacts(ctx: FormContext) -> list[Contact]:
    from app.models.customer import Contact

    if ctx.customer is None:
        return []
    return (
        ctx.db.query(Contact)
        .filter(Contact.team_id == ctx.team_id, Contact.customer_id == ctx.customer.id)
        .order_by(Contact.id)
        .limit(_MAX_REPORTS_TO)
        .all()
    )


class ContactForm:
    KIND = "contact_create"
    LABEL = "联系人"
    TARGET_PREFIX = "contact"
    EXTRACT_KEYS: Mapping[str, str] = {
        "name": "联系人姓名，原样保留（李总、王工也照抄）",
        "gender": "只有原文明确说了男/女/先生/女士时填“男”或“女”；禁止按称呼或名字推断",
        "position": "原文明确说的职位；禁止从李总/王工这类称呼推断",
        "mobile": "原文中每个电话号码各一条，原样照抄（含座机）",
        "email": "邮箱",
        "wechat_id": "微信号；若原文说“微信同号”则 value 填“同号”，quote 填“微信同号”",
        "is_decision_maker": "只有原文明确说是拍板人/决策人时填“是”",
        "reports_to": "原文明确说的上级姓名",
        "remark": "其余值得记录的备注",
    }
    FIELD_KEYS = frozenset({
        "name", "gender", "position", "mobile", "email", "wechat_id", "is_decision_maker", "reports_to", "remark",
    })

    def prepare(self, ctx: FormContext, extracted: list[EntityQuote]) -> dict[str, EntityFieldValue]:
        out: dict[str, EntityFieldValue] = {}
        phones: list[EntityQuote] = []
        remarks: list[str] = []
        wechat_same: EntityQuote | None = None
        for item in extracted:
            if item.key == "mobile":
                phones.append(item)
            elif item.key == "gender" and item.value in _GENDERS:
                out["gender"] = value("DERIVED", _GENDERS[item.value], phrase=item.quote[:200])
            elif item.key == "is_decision_maker" and item.value in {"是", "true"}:
                out["is_decision_maker"] = value("DERIVED", "true", phrase=item.quote[:200])
            elif item.key == "wechat_id" and "同号" in item.value:
                wechat_same = item
            elif item.key == "remark":
                remarks.append(item.value)
            elif item.key == "reports_to":
                matches = [c for c in _contacts(ctx) if c.name == item.value.strip()]
                if len(matches) == 1:
                    out["reports_to"] = value("ORIGINAL", str(matches[0].id))
            elif item.key in {"name", "position", "email", "wechat_id"}:
                out[item.key] = value("ORIGINAL", item.value.strip()[:2000])

        mobiles: list[tuple[str, str]] = []
        short: list[str] = []
        landlines: list[str] = []
        for item in phones:
            digits = normalize_phone(item.value)
            if MOBILE.match(digits):
                if digits not in {m for m, _ in mobiles}:
                    mobiles.append((digits, item.value.strip()))
            elif len(digits) == 10 and digits.startswith("1"):
                short.append(digits)
            else:
                landlines.append(item.value.strip())
        if len(mobiles) == 1:
            digits, raw = mobiles[0]
            out["mobile"] = value("ORIGINAL" if raw == digits else "NORMALIZED", digits)
        elif len(mobiles) > 1:
            out["mobile"] = value("ORIGINAL", None, choices=[m for m, _ in mobiles][:8],
                                  warning="原文有多个手机号，请选一个")
        elif short:
            out["mobile"] = value("ORIGINAL", short[0], warning="原文少一位，请核对")
        elif landlines:
            out["mobile"] = value("ORIGINAL", None, warning="只支持手机号，座机已放进备注")
        if landlines:
            remarks.append("座机：" + "、".join(landlines))
        if wechat_same is not None and len(mobiles) == 1:
            out["wechat_id"] = value("DERIVED", mobiles[0][0], phrase=wechat_same.quote[:200])
        if remarks:
            out["remark"] = value("ORIGINAL", "；".join(remarks)[:2000])
        return out

    def fields(
        self, ctx: FormContext, values: Mapping[str, EntityFieldValue],
        submitted: Submitted | None, errors: Mapping[str, str],
    ) -> list[dict[str, object]]:
        rendered = [
            NAME.render(values, submitted, errors),
            GENDER.render(values, submitted, errors, options=_GENDER_OPTIONS),
            POSITION.render(values, submitted, errors),
            MOBILE_FIELD.render(values, submitted, errors),
            WECHAT.render(values, submitted, errors),
            EMAIL.render(values, submitted, errors),
            DECISION.render(values, submitted, errors),
        ]
        contacts = _contacts(ctx)
        if contacts:
            options = [{"value": str(c.id), "label": c.name[:200]} for c in contacts]
            rendered.append(REPORTS_TO.render(values, submitted, errors, options=options))
        rendered.append(REMARK.render(values, submitted, errors))
        return rendered

    def notices(self, ctx: FormContext, values: Mapping[str, EntityFieldValue]) -> list[str]:  # noqa: ARG002
        name = values.get("name")
        if name is not None and name.value and _TITLE_ONLY.match(name.value):
            return ["建议补全姓名"]
        return []

    def validate(self, ctx: FormContext, submitted: Submitted) -> tuple[Canonical, dict[str, str]]:
        errors: dict[str, str] = {}
        name = NAME.text(submitted, errors)
        gender = GENDER.text(submitted, errors)
        if gender is not None and gender not in {"1", "2"}:
            errors["gender"] = "请选择性别"
        position = POSITION.text(submitted, errors)
        raw_mobile = MOBILE_FIELD.text(submitted, errors)
        mobile = normalize_phone(raw_mobile) if raw_mobile else None
        if mobile is not None and not MOBILE.match(mobile):
            errors["mobile"] = "请填写 11 位手机号"
        email = EMAIL.text(submitted, errors)
        if email is not None and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            errors["email"] = "邮箱格式不对"
        reports_to = REPORTS_TO.text(submitted, {})
        if reports_to is not None and reports_to not in {str(c.id) for c in _contacts(ctx)}:
            errors["reports_to"] = "请从列表里选汇报对象"
        return {
            "name": name,
            "gender": gender,
            "position": position,
            "mobile": mobile,
            "wechat_id": WECHAT.text(submitted, errors),
            "email": email,
            "is_decision_maker": DECISION.flag(submitted),
            "reports_to": reports_to,
            "remark": REMARK.text(submitted, errors),
        }, errors

    def write(self, ctx: FormContext, values: Canonical) -> WriteResult:
        from pydantic import ValidationError

        from app.crud.customer import contact_crud
        from app.schemas.customer import ContactCreate

        assert ctx.customer is not None
        try:
            obj_in = ContactCreate.model_validate({
                **values, "reports_to": int(values["reports_to"]) if values["reports_to"] else None,
            })
        except ValidationError as exc:
            raise EntityFormError({"name": "联系人资料不完整，请核对"}) from exc
        contact = contact_crud.create(ctx.db, obj_in, ctx.customer.id, ctx.team_id, commit=False)
        return WriteResult(
            target_public_id=f"contact:{contact.id}",
            name=contact.name,
            customer_public_id=ctx.customer.public_id,
            after_commit=refresh_after_commit("customer_contact", contact, str(ctx.user.id)),
        )

    def describe_existing(self, ctx: FormContext, values: Canonical, existing_id: int) -> str | None:  # noqa: ARG002
        return "这个手机号已是该客户的联系人，如需修改请到客户详情"


FORM = ContactForm()
