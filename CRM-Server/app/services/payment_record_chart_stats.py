# ruff: noqa: RUF001
"""只读回款图表。分组规则只属于回款。不进入通用图表组件。"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.utils.time import business_now

PREVIEW_LIMIT = 5
BLANK_KEY = "blank"
BLANK_LABEL = "未填写"
CHART_KEYS = ("license_type", "purchase_type", "amount_band", "payment_month", "arr_ratio")

_LICENSE_SEGMENTS = (("SUBSCRIPTION", "订阅"), ("PERPETUAL", "买断"))
_PURCHASE_SEGMENTS = (("NEW", "新购"), ("RENEWAL", "续购"), ("EXPANSION", "增购"))
_AMOUNT_SEGMENTS = (
    ("under_100k", "10 万以下"),
    ("100k_500k", "10–50 万"),
    ("500k_1m", "50–100 万"),
    ("over_1m", "100 万以上"),
)
_CARD_COPY = {
    "license_type": ("授权模式", "按回款金额看订阅和买断。没关联到的单独列出。"),
    "purchase_type": ("采购类型", "按回款金额看新购、续购、增购。没填的单独列出。"),
    "amount_band": ("金额档", "按回款金额分档。"),
    "payment_month": ("回款月份", "最近 12 个月，每个月回了多少。更早的不在这张图上。"),
    "arr_ratio": (
        "ARR 占比",
        "和回款月份同一种面积加线。纵轴是占比。没有回款的月份也连过去，不写成 0%。只有买断落到 0%。",
    ),
}
_TEN_WAN = Decimal(100_000)
_FIFTY_WAN = Decimal(500_000)
_HUNDRED_WAN = Decimal(1_000_000)


def _attr(row: object, name: str, default: object = None) -> object:
    return getattr(row, name, default)


def _text(value: object) -> str:
    if value is None:
        return ""
    raw = _attr(value, "value", value)
    return str(raw).strip()


def _amount(row: object) -> Decimal:
    value = _attr(row, "actual_amount")
    if value is None:
        return Decimal(0)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def _percent(part: Decimal, total: Decimal) -> int:
    if total <= 0:
        return 0
    return int((part * Decimal(100) / total).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _contract(row: object) -> object | None:
    plan = _attr(row, "payment_plan")
    if plan is None:
        return None
    contract = _attr(plan, "contract")
    return contract


def _customer_name(row: object) -> str | None:
    contract = _contract(row)
    if contract is None:
        return None
    customer = _attr(contract, "customer")
    if customer is None:
        return None
    name = _text(_attr(customer, "account_name"))
    return name or None


def _license_key(row: object) -> str:
    contract = _contract(row)
    if contract is None:
        return BLANK_KEY
    key = _text(_attr(contract, "license_type"))
    if key in {item[0] for item in _LICENSE_SEGMENTS}:
        return key
    return BLANK_KEY


def _purchase_key(row: object) -> str:
    contract = _contract(row)
    opportunity = _attr(contract, "opportunity") if contract is not None else None
    if opportunity is None:
        return BLANK_KEY
    key = _text(_attr(opportunity, "purchase_type"))
    if key in {item[0] for item in _PURCHASE_SEGMENTS}:
        return key
    return BLANK_KEY


def _amount_key(row: object) -> str:
    amount = _amount(row)
    if amount <= _TEN_WAN:
        return "under_100k"
    if amount <= _FIFTY_WAN:
        return "100k_500k"
    if amount <= _HUNDRED_WAN:
        return "500k_1m"
    return "over_1m"


def _payment_day(row: object) -> date | None:
    value = _attr(row, "payment_date")
    if isinstance(value, date):
        return value
    return None


def _month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _recent_months(today: date, count: int = 12) -> list[str]:
    year = today.year
    month = today.month
    keys: list[str] = []
    for _ in range(count):
        keys.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(keys))


def _month_label(key: str) -> str:
    month = int(key.split("-")[1])
    return f"{month}月"


def _row_key(row: object, chart_key: str, months: set[str]) -> str | None:
    if chart_key == "license_type":
        return _license_key(row)
    if chart_key == "purchase_type":
        return _purchase_key(row)
    if chart_key == "amount_band":
        return _amount_key(row)
    if chart_key == "payment_month":
        day = _payment_day(row)
        if day is None:
            return None
        key = _month_key(day)
        return key if key in months else None
    return None


def _preview(row: object) -> dict[str, Any]:
    day = _payment_day(row)
    number = _text(_attr(row, "record_number"))
    raw_id = _attr(row, "id")
    record_id = raw_id if isinstance(raw_id, int) and not isinstance(raw_id, bool) else int(str(raw_id))
    return {
        "id": record_id,
        "record_number": number or None,
        "customer_name": _customer_name(row),
        "amount": _number(_amount(row)),
        "payment_date": day,
    }


def _bucket(key: str, label: str, rows: list[object], total_count: int, total_amount: Decimal) -> dict[str, Any]:
    amount = sum((_amount(row) for row in rows), Decimal(0))
    return {
        "key": key,
        "label": label,
        "count": len(rows),
        "amount": _number(amount),
        "ratio": _percent(Decimal(len(rows)), Decimal(total_count)),
        "amount_ratio": _percent(amount, total_amount),
        "preview": [_preview(row) for row in rows[:PREVIEW_LIMIT]],
        "preview_total": len(rows),
    }


def _segments(chart_key: str, months: list[str]) -> list[tuple[str, str]]:
    if chart_key == "license_type":
        return [*_LICENSE_SEGMENTS, (BLANK_KEY, BLANK_LABEL)]
    if chart_key == "purchase_type":
        return [*_PURCHASE_SEGMENTS, (BLANK_KEY, BLANK_LABEL)]
    if chart_key == "amount_band":
        return list(_AMOUNT_SEGMENTS)
    return [(key, _month_label(key)) for key in months]


def _grouped(rows: list[object], chart_key: str, months: list[str]) -> dict[str, list[object]]:
    month_keys = set(months)
    grouped: dict[str, list[object]] = {key: [] for key, _label in _segments(chart_key, months)}
    for row in rows:
        key = _row_key(row, chart_key, month_keys)
        if key is None:
            continue
        grouped[key].append(row)
    return grouped



def _positive_years(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value <= 0:
        return None
    return value


def _arr_contribution(row: object) -> tuple[Decimal, Decimal] | None:
    contract = _contract(row)
    if contract is None:
        return None
    license_key = _text(_attr(contract, "license_type"))
    amount = _amount(row)
    if license_key == "PERPETUAL":
        return (Decimal(0), amount)
    if license_key != "SUBSCRIPTION":
        return None
    years = _positive_years(_attr(contract, "subscription_years"))
    if years is None:
        return None
    return (amount / Decimal(years), Decimal(0))


def _arr_ratio(annualized: Decimal, buyout: Decimal) -> int | None:
    total = annualized + buyout
    if total <= 0:
        return None
    return _percent(annualized, total)


def _arr_month_rows(rows: list[object], months: list[str]) -> dict[str, list[object]]:
    month_keys = set(months)
    grouped: dict[str, list[object]] = {key: [] for key in months}
    for row in rows:
        day = _payment_day(row)
        if day is None:
            continue
        key = _month_key(day)
        if key not in month_keys or _arr_contribution(row) is None:
            continue
        grouped[key].append(row)
    return grouped


def _arr_bucket(key: str, rows: list[object]) -> dict[str, Any]:
    annualized = Decimal(0)
    buyout = Decimal(0)
    for row in rows:
        contribution = _arr_contribution(row)
        if contribution is None:
            continue
        annualized += contribution[0]
        buyout += contribution[1]
    ratio = _arr_ratio(annualized, buyout)
    label = _month_label(key)
    if ratio is None:
        return {
            "key": key,
            "label": label,
            "count": 0,
            "amount": 0,
            "ratio": 0,
            "amount_ratio": 0,
            "preview": [],
            "preview_total": 0,
            "plotted_ratio": None,
            "annualized_subscription": None,
            "buyout_amount": None,
        }
    amount = sum((_amount(row) for row in rows), Decimal(0))
    return {
        "key": key,
        "label": label,
        "count": len(rows),
        "amount": _number(amount),
        "ratio": ratio,
        "amount_ratio": 0,
        "preview": [_preview(row) for row in rows[:PREVIEW_LIMIT]],
        "preview_total": len(rows),
        "plotted_ratio": ratio,
        "annualized_subscription": _number(annualized),
        "buyout_amount": _number(buyout),
    }


def build_payment_record_chart(rows: list[object], today: date | None = None) -> dict[str, Any]:
    current_day = today or business_now().date()
    months = _recent_months(current_day, 12)
    total_amount = sum((_amount(row) for row in rows), Decimal(0))
    cards: list[dict[str, Any]] = []
    for chart_key in CHART_KEYS:
        title, description = _CARD_COPY[chart_key]
        if chart_key == "arr_ratio":
            grouped_months = _arr_month_rows(rows, months)
            buckets = [_arr_bucket(key, grouped_months[key]) for key in months]
        else:
            grouped = _grouped(rows, chart_key, months)
            buckets = [
                _bucket(key, label, grouped[key], len(rows), total_amount)
                for key, label in _segments(chart_key, months)
            ]
        cards.append({
            "key": chart_key,
            "title": title,
            "description": description,
            "buckets": buckets,
        })
    return {
        "population": len(rows),
        "total_amount": _number(total_amount),
        "cards": cards,
    }


def list_chart_bucket_records(
    rows: list[object],
    chart_key: str,
    bucket_key: str,
    today: date | None = None,
) -> list[dict[str, Any]]:
    if chart_key not in CHART_KEYS:
        raise ValueError("未知图表")
    current_day = today or business_now().date()
    months = _recent_months(current_day, 12)
    segments = dict(_segments(chart_key, months))
    if bucket_key not in segments:
        raise ValueError("图表分段不存在")
    if chart_key == "arr_ratio":
        grouped_months = _arr_month_rows(rows, months)
        bucket_rows = grouped_months[bucket_key]
        if _arr_bucket(bucket_key, bucket_rows)["plotted_ratio"] is None:
            return []
        return [_preview(row) for row in bucket_rows]
    grouped = _grouped(rows, chart_key, months)
    return [_preview(row) for row in grouped[bucket_key]]
