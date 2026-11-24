"""Read-only form preparation and validation for a confirmed create candidate."""

# ruff: noqa: RUF001
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal
from itertools import islice
from typing import TYPE_CHECKING, Any, Literal, NotRequired, TypedDict, TypeVar

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import case

from app.core.deps import check_customer_edit_permission
from app.crud.opportunity import opportunity_crud
from app.crud.permission import permission_crud
from app.models.customer import CustomerProduct
from app.models.procurement import ProcurementMethod, ProcurementStageTemplate
from app.models.product import Product, ProductModule, ProductModuleRole
from app.models.team import UserTeam
from app.models.user import User, UserStatus
from app.schemas.opportunity import LicenseTypeEnum, OpportunityCreate, PurchaseTypeEnum
from app.services.assistant.crm_proposal_commands import _customer, _user, source_activity
from app.services.pricing import pricing_service

if TYPE_CHECKING:
    from sqlalchemy.orm import Query, Session

    from app.models.assistant import AssistantTask
    from app.models.customer import Customer
    from app.models.customer_activity import CustomerActivity

_Child = TypeVar("_Child")
_FormDefault = int | float | str | list[str]
_FormOptions = dict[str, list[dict[str, str]]]

_MAX_OPTIONS = 50
_MAX_COUNT = 2**31 - 1
_MAX_ID = 2**63 - 1
_MAX_AMOUNT = Decimal("9999999999.99")  # Numeric(12, 2)
_MAX_UNIT_PRICE = Decimal("99999999.99")  # Numeric(10, 2)
_MIN_DATE_YEAR = 1000
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


class _FormField(TypedDict):
    key: str
    label: str
    field_type: Literal["text", "number", "select", "date", "multi_select"]
    required: NotRequired[bool]
    minimum: NotRequired[int | float]
    maximum: NotRequired[int | float]
    min_length: NotRequired[int]
    max_length: NotRequired[int]


_FIELDS: tuple[_FormField, ...] = (
    {"key": "opportunity_name", "label": "商机名称", "field_type": "text", "min_length": 1, "max_length": 255},
    {"key": "total_amount", "label": "预计总金额", "field_type": "number", "required": True,
     "minimum": 0.01, "maximum": float(_MAX_AMOUNT)},
    {"key": "user_count", "label": "采购用户数", "field_type": "number", "required": True,
     "minimum": 1, "maximum": _MAX_COUNT},
    {"key": "license_type", "label": "授权模式", "field_type": "select", "required": True},
    {"key": "subscription_years", "label": "订阅年限", "field_type": "number", "minimum": 1, "maximum": _MAX_COUNT},
    {"key": "purchase_type", "label": "采购类型", "field_type": "select", "required": True},
    {"key": "decision_maker_count", "label": "采购决策人数", "field_type": "number",
     "minimum": 1, "maximum": _MAX_COUNT},
    {"key": "expected_closing_date", "label": "预计成交日期", "field_type": "date", "required": True},
    {"key": "procurement_method_id", "label": "采购方式", "field_type": "select", "required": True},
    {"key": "stage_id", "label": "初始阶段", "field_type": "select"},
    {"key": "owner_id", "label": "负责人", "field_type": "select", "required": True},
    {"key": "product_public_id", "label": "产品", "field_type": "select", "required": True},
    {"key": "product_module_public_ids", "label": "产品模块", "field_type": "multi_select", "required": True},
)
_FIELD_KEYS = frozenset(field["key"] for field in _FIELDS)


class OpportunityFormError(ValueError):
    """Failure suitable for a field-addressed response from the coordinator."""

    def __init__(self, message: str, field_errors: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.field_errors = field_errors or {"form": message}


def _error(message: str, field: str = "form") -> OpportunityFormError:
    return OpportunityFormError(message, {field: message})


def _authority(db: Session, task: AssistantTask, candidate: dict[str, Any]) -> tuple[CustomerActivity, Customer, User]:
    key = candidate.get("key")
    if candidate.get("kind") != "opportunity_create" or not isinstance(key, str) or not key.strip():
        raise _error("商机候选无效")
    activity = source_activity(db, task)
    if activity is None or type(candidate.get("activity_id")) is not int or candidate["activity_id"] != activity.id:
        raise _error("活动证据已失效")
    if type(candidate.get("source_revision")) is not int or candidate["source_revision"] != activity.activity_revision:
        raise _error("活动内容已修订")
    customer = _customer(db, task, activity)
    if customer is None or type(candidate.get("customer_id")) is not int or candidate["customer_id"] != customer.id:
        raise _error("客户绑定已失效", "customer_id")
    try:
        actor = _user(db, task)
    except PermissionError as exc:
        raise _error(str(exc)) from exc
    permissions = permission_crud.get_user_permissions(db, task.user_id, task.team_id)
    if not any(p.code == "opportunity:create" for p in permissions):
        raise _error("缺少创建商机权限")
    try:
        checked = check_customer_edit_permission(str(customer.public_id), task.team_id, actor, db)
    except (HTTPException, PermissionError) as exc:
        raise _error("当前用户无权编辑客户", "customer_id") from exc
    if checked.id != customer.id:
        raise _error("客户绑定已失效", "customer_id")
    return activity, customer, actor


def _unique_offset(text: str, literal: str) -> int | None:
    offset = text.find(literal)
    return offset if offset >= 0 and text.find(literal, offset + 1) < 0 else None


def _verified_quote(activity: CustomerActivity, candidate: dict[str, Any]) -> tuple[str, str, int]:
    quote = candidate.get("evidence_quote")
    if not isinstance(quote, str) or not quote.strip():
        raise _error("商机信号缺少证据原文")
    source = activity.source_content
    original = source if isinstance(source, str) else ""
    segment_id = candidate.get("segment_id")
    if segment_id is None:
        offset = _unique_offset(original, quote)
    else:
        stored_content = activity.content_json
        try:
            content: object = json.loads(stored_content) if isinstance(stored_content, str) and stored_content else {}
        except (TypeError, ValueError):
            content = {}
        records = content.get("source_records") if isinstance(content, dict) else None
        if isinstance(records, list) and records:
            matches = [r.get("text") for r in records if isinstance(r, dict) and r.get("segment_id") == segment_id]
        else:
            matches = [original] if segment_id == "seg_primary" else []
        segment = matches[0] if len(matches) == 1 else None
        if not isinstance(segment, str) or not segment or not isinstance(segment_id, str) or not segment_id.strip():
            raise _error("商机信号段落已变化")
        segment_offset = _unique_offset(original, segment)
        quote_offset = _unique_offset(segment, quote)
        offset = None if segment_offset is None or quote_offset is None else segment_offset + quote_offset
    if offset is None:
        raise _error("商机信号原文已变化或无法唯一定位")
    return original, quote, offset


# Extract only direct literals. Look at the containing original clause (not merely
# the nominated substring), so a truncated quote cannot hide a range or qualifier.
_COUNT = re.compile(
    r"(?<![\d.,+\-])([0-9]{1,10})\s*(?:个\s*)?(?:账号|账户|用户|席位|套|人|licenses?)(?![A-Za-z])", re.I,
)
_AMOUNT = re.compile(
    r"(?<![\d.,+\-])([0-9]{1,10}(?:\.[0-9]{1,8})?)\s*(亿元|万元|亿(?!元)|万(?!元)|元)"
    r"(?![美欧港日澳加]元|[人套个用户])"
)
_DATE = re.compile(
    r"(?<!\d)(?:([0-9]{4})年\s*([0-9]{1,2})月\s*([0-9]{1,2})[日号]|([0-9]{4})-([0-9]{2})-([0-9]{2}))(?!\d)"
)
_CLAUSE_BREAK = re.compile(r"[，、；;。！？!?\n]|(?<!\d),|,(?!\d)")
_QUALIFIER = re.compile(
    r"不超过|不少于|不低于|不高于|至少|至多|以上|以下|以内|左右|大概|大致|"
    r"不采购|不购买|不签|尚未|不会|不是|不再|未确定|撤销|取消|放弃|或者|或是|可能|[<>≤≥]"
)
_UNCERTAIN_PREFIX = re.compile(r"(?:约|近|超|超过|不足|不含|未达|原定|此前|[$€£￥¥]|美元|欧元|港币)\s*$")
_RANGE_PREFIX = re.compile(r"\d(?:\s*(?:月|日|号|元|万|亿|个|人|账号|席位))*\s*(?:至|到|或|[-~～—–/])\s*$")
_RANGE_SUFFIX = re.compile(r"^\s*(?:至|到|或|[-~～—–/])\s*\d")
_CONTEXT = {
    "user_count": re.compile(r"采购|购买|订购|授权|账号|账户|席位|licenses?", re.I),
    "total_amount": re.compile(r"预算|金额|报价|总价|经费|采购|购买|合同"),
    "expected_closing_date": re.compile(r"成交|签约|签单|签署|下单|合同签"),
}


def _literal(original: str, quote: str, offset: int, pattern: re.Pattern[str], field: str) -> re.Match[str] | None:
    # Match on the original rather than a sliced quote to retain token boundaries.
    end = offset + len(quote)
    breaks = list(_CLAUSE_BREAK.finditer(original))
    matches = []
    for match in pattern.finditer(original):
        if not (offset <= match.start() and match.end() <= end):
            continue
        start = next((b.end() for b in reversed(breaks) if b.end() <= match.start()), 0)
        stop = next((b.start() for b in breaks if b.start() >= match.end()), len(original))
        context_start = start
        if field == "total_amount" and start > 0 and original[start - 1] in "，、,":
            # "采购 200 套，8.8 万": the money keyword may sit in the preceding clause of the same sentence.
            context_start = next((b.end() for b in reversed(breaks) if b.end() < start), 0)
        if _CONTEXT[field].search(original[max(context_start, offset):min(stop, end)]):
            clause = original[start:stop]
            prefix, suffix = original[start:match.start()], original[match.end():stop]
            if (
                _QUALIFIER.search(clause) or _UNCERTAIN_PREFIX.search(prefix) or _RANGE_PREFIX.search(prefix)
                or _RANGE_SUFFIX.search(suffix) or sum(1 for _ in pattern.finditer(clause)) != 1
            ):
                return None
            matches.append(match)
    return matches[0] if len(matches) == 1 else None


def _evidenced_defaults(original: str, quote: str, offset: int) -> dict[str, _FormDefault]:
    defaults: dict[str, _FormDefault] = {}
    if count := _literal(original, quote, offset, _COUNT, "user_count"):
        value = int(count[1])
        if 1 <= value <= _MAX_COUNT:
            defaults["user_count"] = value
    if amount := _literal(original, quote, offset, _AMOUNT, "total_amount"):
        multiplier = {"亿": 10**8, "亿元": 10**8, "万": 10**4, "万元": 10**4, "元": 1}[amount[2]]
        amount_value = Decimal(amount[1]) * multiplier
        if _valid_amount(amount_value):
            defaults["total_amount"] = float(amount_value)
    if closing := _literal(original, quote, offset, _DATE, "expected_closing_date"):
        try:
            closing_date = date(*(int(v) for v in closing.groups() if v is not None))
            if closing_date.year >= _MIN_DATE_YEAR:
                defaults["expected_closing_date"] = closing_date.isoformat()
        except ValueError:
            pass
    return defaults


def _owners(db: Session, team_id: int) -> Query[User]:
    return db.query(User).join(UserTeam, UserTeam.user_id == User.id).filter(
        UserTeam.team_id == team_id, User.status == UserStatus.ACTIVE,
    )


def _methods(db: Session, team_id: int) -> Query[ProcurementMethod]:
    return db.query(ProcurementMethod).filter(ProcurementMethod.team_id == team_id, ProcurementMethod.is_active == 1)


def _stages(db: Session, team_id: int) -> Query[ProcurementStageTemplate]:
    return db.query(ProcurementStageTemplate).filter(ProcurementStageTemplate.team_id == team_id)


def _products(db: Session, team_id: int) -> Query[Product]:
    return db.query(Product).filter(Product.team_id == team_id, Product.is_active.is_(True))


def _modules(db: Session, team_id: int) -> Query[ProductModule]:
    return db.query(ProductModule).filter(ProductModule.team_id == team_id, ProductModule.is_active.is_(True))


def _bounded_children(groups: list[list[_Child]]) -> tuple[list[_Child], bool]:
    """Every offered parent keeps its preferred child; the page size is the card limit."""
    remaining = _MAX_OPTIONS - len(groups)
    children = [group[0] for group in groups] + list(islice((item for group in groups for item in group[1:]), remaining))
    truncated = sum(len(group) for group in groups) > len(children)
    return children, truncated


def _stage_choices(
    db: Session, team_id: int, customer: Customer,
) -> tuple[list[ProcurementMethod], list[ProcurementStageTemplate], bool]:
    stage_exists = _stages(db, team_id).filter(ProcurementStageTemplate.procurement_method_id == ProcurementMethod.id)
    methods = (
        _methods(db, team_id).filter(stage_exists.exists())
        .order_by(case((ProcurementMethod.id == customer.default_procurement_method_id, 0), else_=1),
                  ProcurementMethod.sort_order, ProcurementMethod.id)
        .limit(_MAX_OPTIONS).all()
    )
    if not methods:
        raise _error("当前团队没有配置可用的采购方式和阶段", "procurement_method_id")
    groups: dict[str, list[ProcurementStageTemplate]] = defaultdict(list)
    for stage in (
        _stages(db, team_id).filter(ProcurementStageTemplate.procurement_method_id.in_([m.id for m in methods]))
        .order_by(ProcurementStageTemplate.is_default_start.desc(), ProcurementStageTemplate.sort_order,
                  ProcurementStageTemplate.id).all()
    ):
        groups[str(stage.procurement_method_id)].append(stage)
    stages, truncated = _bounded_children([groups[str(method.id)] for method in methods])
    return methods, stages, truncated


def _product_choices(
    db: Session, team_id: int, customer: Customer,
) -> tuple[list[Product], list[ProductModule], bool]:
    module_exists = _modules(db, team_id).filter(ProductModule.product_id == Product.id)
    intent = db.query(CustomerProduct).filter(
        CustomerProduct.customer_id == customer.id, CustomerProduct.team_id == team_id,
        CustomerProduct.product_id == Product.id,
    )
    products = (
        _products(db, team_id).filter(module_exists.exists())
        .order_by(case((intent.exists(), 0), else_=1), Product.name, Product.id)
        .limit(_MAX_OPTIONS).all()
    )
    if not products:
        raise _error("当前团队没有可用产品模块", "product_public_id")
    groups: dict[str, list[ProductModule]] = defaultdict(list)
    for module in (
        _modules(db, team_id).filter(ProductModule.product_id.in_([p.id for p in products]))
        .order_by(case((ProductModule.module_role == ProductModuleRole.BASE.value, 0), else_=1),
                  ProductModule.sort_order, ProductModule.id).all()
    ):
        groups[str(module.product_id)].append(module)
    modules, truncated = _bounded_children([groups[str(product.id)] for product in products])
    return products, modules, truncated


def _option(value: str, label: str, **parent: str) -> dict[str, str]:
    return {"value": value, "label": label, **parent}


def _binding(
    task: AssistantTask, candidate: dict[str, Any], activity: CustomerActivity, quote: str,
) -> dict[str, object]:
    return {
        "candidate_id": candidate["key"], "task_public_id": task.public_id,
        "team_id": task.team_id, "actor_id": task.user_id, "activity_id": activity.id,
        "source_revision": activity.activity_revision,
        "segment_id": candidate.get("segment_id"), "evidence_quote": quote,
    }


def prepare_opportunity_form(db: Session, task: AssistantTask, candidate: dict[str, Any]) -> dict[str, Any]:
    """Prepare a frozen JSON spec; only its editable form metadata is projected."""
    with db.no_autoflush:
        activity, customer, actor = _authority(db, task, candidate)
        original, quote, offset = _verified_quote(activity, candidate)
        methods, stages, stages_truncated = _stage_choices(db, task.team_id, customer)
        products, modules, products_truncated = _product_choices(db, task.team_id, customer)
        owners = (
            _owners(db, task.team_id)
            .filter(User.id != actor.id)
            .order_by(User.name, User.id)
            .limit(_MAX_OPTIONS - 1)
        )
        defaults = _evidenced_defaults(original, quote, offset)
        sources = {key: {"kind": "original", "label": "来自原文", "quote": quote} for key in defaults}
        product = products[0]
        defaults.update({
            "license_type": LicenseTypeEnum.SUBSCRIPTION.value, "subscription_years": 1,
            "purchase_type": PurchaseTypeEnum.NEW.value, "owner_id": str(actor.id),
            "product_public_id": str(product.public_id),
            "product_module_public_ids": [str(next(m.public_id for m in modules if m.product_id == product.id))],
        })
        if methods[0].id == customer.default_procurement_method_id:
            method_id = methods[0].id
            defaults["procurement_method_id"] = str(method_id)
            stage = next(
                (s for s in stages if s.procurement_method_id == method_id and s.is_default_start == 1), None,
            )
            if stage is not None:
                defaults["stage_id"] = str(stage.id)
        customer_public_id = str(customer.public_id)
        if "user_count" in defaults:
            # The CRM name helper only consumes the name, customer, count and license fields.
            defaults["opportunity_name"] = opportunity_crud._build_opportunity_name(
                OpportunityCreate.model_construct(_fields_set=None, customer_id=customer_public_id, **defaults),
                customer,
            )
        product_ids = {str(p.id): str(p.public_id) for p in products}
        options: _FormOptions = {
            "license_type": [_option(v.value, v.description) for v in LicenseTypeEnum],
            "purchase_type": [_option(v.value, v.description) for v in PurchaseTypeEnum],
            "procurement_method_id": [_option(str(m.id), str(m.name)) for m in methods],
            "stage_id": [
                _option(str(s.id), str(s.stage_name), procurement_method_id=str(s.procurement_method_id))
                for s in stages
            ],
            "owner_id": [_option(str(u.id), str(u.name)) for u in (actor, *owners.all())],
            "product_public_id": [_option(str(p.public_id), str(p.name)) for p in products],
            "product_module_public_ids": [
                _option(str(m.public_id), str(m.name), product_public_id=product_ids[str(m.product_id)])
                for m in modules
            ],
        }
        return {
            **_binding(task, candidate, activity, quote),
            "customer_id": customer_public_id,
            "customer_name": str(customer.account_name),
            "fields": [{"required": False, **field} for field in _FIELDS],
            "defaults": defaults,
            "sources": sources,
            "options": options,
            # The card shows at most 50 options per field; say so when a list was cut.
            "option_notice": "选项较多，表单只列出前 50 项；找不到时请在客户页手动创建商机。"
            if stages_truncated or products_truncated else None,
        }


def _valid_amount(amount: Decimal) -> bool:
    return (
        amount.is_finite()
        and Decimal("0.01") <= amount <= _MAX_AMOUNT
        and amount == amount.quantize(Decimal("0.01"))
    )


def _positive_int(value: object, maximum: int) -> int | None:
    if (
        (isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,18}", value))
        or (type(value) is float and value.is_integer() and 1 <= value <= maximum)
    ):
        value = int(value)
    return value if type(value) is int and 1 <= value <= maximum else None


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _chosen(options: _FormOptions, key: str, value: str, **parent: str) -> bool:
    return any(item["value"] == value and all(item.get(k) == v for k, v in parent.items()) for item in options[key])


def _commercial_values(data: dict[str, object], defaults: dict[str, _FormDefault], errors: dict[str, str]) -> None:
    amount = data.get("total_amount")
    amount_text = str(amount) if type(amount) in (int, float, str) else ""
    if not re.fullmatch(r"[0-9]{1,10}(?:\.[0-9]{1,2})?", amount_text):
        errors["total_amount"] = "请输入有效金额（最多两位小数）"
    elif not _valid_amount(Decimal(amount_text)):
        errors["total_amount"] = "金额超出有效范围"
    else:
        data["total_amount"] = float(amount_text)

    license_type = data.get("license_type")
    for key in ("user_count", "decision_maker_count", "subscription_years"):
        value = data.get(key)
        if (
            (key == "subscription_years" and license_type == LicenseTypeEnum.PERPETUAL.value)
            or (key == "decision_maker_count" and _blank(value))
        ):
            data[key] = None
        elif (number := _positive_int(value, _MAX_COUNT)) is None:
            errors[key] = "请输入有效的正整数"
        else:
            data[key] = number

    name = data.get("opportunity_name")
    if _blank(name) or (isinstance(name, str) and name.strip() == defaults.get("opportunity_name")):
        data["opportunity_name"] = None
    elif not isinstance(name, str) or len(name.strip()) > 255:
        errors["opportunity_name"] = "请输入不超过 255 个字符的名称"
    else:
        data["opportunity_name"] = name.strip()

    closing = data.get("expected_closing_date")
    try:
        if (
            not isinstance(closing, str)
            or not _ISO_DATE.fullmatch(closing)
            or date.fromisoformat(closing).year < _MIN_DATE_YEAR
        ):
            raise ValueError
    except ValueError:
        errors["expected_closing_date"] = "请输入有效的成交日期（YYYY-MM-DD）"


def _catalog_values(
    db: Session, team_id: int, data: dict[str, object], options: _FormOptions, errors: dict[str, str],
) -> None:
    product_id = data.get("product_public_id")
    product = None
    if isinstance(product_id, str) and _chosen(options, "product_public_id", product_id):
        product = _products(db, team_id).filter(Product.public_id == product_id).one_or_none()
    if product is None:
        errors["product_public_id"] = "请选择当前可用的产品"

    modules = data.get("product_module_public_ids")
    if not isinstance(modules, list) or not modules or not all(isinstance(m, str) and m for m in modules):
        errors["product_module_public_ids"] = "请选择至少一个有效的产品模块"
    else:
        module_ids: list[str] = list(dict.fromkeys(modules))
        if product is None or not isinstance(product_id, str) or not all(
            _chosen(options, "product_module_public_ids", module_id, product_public_id=product_id)
            for module_id in module_ids
        ):
            errors["product_module_public_ids"] = "产品模块未提供或不属于所选产品"
        else:
            live_modules = _modules(db, team_id).filter(
                ProductModule.product_id == product.id, ProductModule.public_id.in_(module_ids),
            )
            if live_modules.count() != len(module_ids):
                errors["product_module_public_ids"] = "产品模块已停用或不属于所选产品"
            else:
                data["product_module_public_ids"] = module_ids

    method_value = data.get("procurement_method_id")
    method_id = _positive_int(method_value, _MAX_ID) if type(method_value) in (int, str) else None
    if method_id is None or not _chosen(options, "procurement_method_id", str(method_id)) or not (
        _methods(db, team_id).filter(ProcurementMethod.id == method_id).first()
    ):
        errors["procurement_method_id"] = "请选择当前可用的采购方式"
    else:
        data["procurement_method_id"] = method_id
        stage_value = data.get("stage_id")
        query = _stages(db, team_id).filter(ProcurementStageTemplate.procurement_method_id == method_id)
        if _blank(stage_value):
            stage = query.filter(ProcurementStageTemplate.is_default_start == 1).order_by(
                ProcurementStageTemplate.sort_order, ProcurementStageTemplate.id,
            ).first()
        else:
            stage_id = _positive_int(stage_value, _MAX_ID) if type(stage_value) in (int, str) else None
            stage = None
            if stage_id is not None and _chosen(
                options, "stage_id", str(stage_id), procurement_method_id=str(method_id),
            ):
                stage = query.filter(ProcurementStageTemplate.id == stage_id).one_or_none()
        if stage is None:
            errors["stage_id"] = "请选择属于该采购方式的有效初始阶段"
        else:
            data["stage_id"] = stage.id

    owner_value = data.get("owner_id")
    owner_id = _positive_int(owner_value, _MAX_COUNT) if type(owner_value) in (int, str) else None
    if owner_id is None or not _chosen(options, "owner_id", str(owner_id)) or not (
        _owners(db, team_id).filter(User.id == owner_id).first()
    ):
        errors["owner_id"] = "请选择当前团队的有效成员"
    else:
        data["owner_id"] = str(owner_id)


def validate_opportunity_form(
    db: Session, task: AssistantTask, candidate: dict[str, Any], spec: dict[str, Any], values: dict[str, Any],
) -> dict[str, Any]:
    """Recheck frozen authority and live references, then serialize OpportunityCreate."""
    if not isinstance(values, dict):
        raise _error("表单值必须是对象")
    with db.no_autoflush:
        activity, customer, _ = _authority(db, task, candidate)
        _, quote, _ = _verified_quote(activity, candidate)
        for key, bound in _binding(task, candidate, activity, quote).items():
            if type(spec.get(key)) is not type(bound) or spec.get(key) != bound:
                raise _error("商机表单已过期")
        customer_public_id = str(customer.public_id)
        if spec.get("customer_id") != customer_public_id:
            raise _error("客户绑定已变化", "customer_id")
        errors = dict.fromkeys(values.keys() - _FIELD_KEYS, "不支持的表单字段")
        defaults: dict[str, _FormDefault] = spec["defaults"]
        options: _FormOptions = spec["options"]
        data: dict[str, object] = {key: values.get(key, defaults.get(key)) for key in _FIELD_KEYS}
        # An omitted stage is always the selected method's live configured default.
        data["stage_id"] = values.get("stage_id")
        data["customer_id"] = customer_public_id
        _commercial_values(data, defaults, errors)
        _catalog_values(db, task.team_id, data, options, errors)
        try:
            # Let CRM's schema handle enums and cross-field invariants, even when
            # another input failed, without obscuring the more specific errors.
            create = OpportunityCreate.model_validate(data)
        except ValidationError as exc:
            for item in exc.errors():
                errors.setdefault(str(item["loc"][0]) if item["loc"] else "form", item["msg"])
            raise OpportunityFormError("表单校验失败", errors) from exc
        if errors:
            raise OpportunityFormError("表单校验失败", errors)
        unit_price = pricing_service.calculate_unit_price(
            create.total_amount, create.user_count, create.license_type, create.subscription_years or 1,
        )
        if unit_price > _MAX_UNIT_PRICE:
            raise _error("预计总金额与用户数计算出的标准单价超出有效范围", "total_amount")
        create.opportunity_name = opportunity_crud._build_opportunity_name(create, customer)
        return create.model_dump(mode="json")
