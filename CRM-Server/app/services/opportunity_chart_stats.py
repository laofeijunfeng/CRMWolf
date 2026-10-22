# ruff: noqa: RUF001
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from app.utils.time import business_now

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


_STATUS_SEGMENTS = (("0", "跟进中"), ("1", "已赢单"), ("2", "已输单"))
_PURCHASE_SEGMENTS = (("NEW", "新购"), ("RENEWAL", "续购"), ("EXPANSION", "增购"))
_LICENSE_SEGMENTS = (("SUBSCRIPTION", "订阅"), ("PERPETUAL", "买断"))
_AMOUNT_SEGMENTS = (
    ("under_100k", "10 万以下"),
    ("100k_500k", "10–50 万"),
    ("500k_1m", "50–100 万"),
    ("over_1m", "100 万以上"),
)
_PROBABILITY_SEGMENTS = (("0-49", "0–49%"), ("50-79", "50–79%"), ("80-99", "80–99%"), ("100", "100%"))
_CARD_KEYS = (
    "status",
    "purchase_type",
    "license_type",
    "amount_band",
    "product",
    "win_probability",
    "expected_closing_month",
)


def _value(value: object) -> object:
    return getattr(value, "value", value)


def _amount(value: object) -> Decimal:
    if value is None:
        return Decimal(0)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def _percent(value: Decimal, total: Decimal) -> int:
    if not total:
        return 0
    return int((value * Decimal(100) / total).quantize(Decimal("1")))


def _team_rows(team_id: object, opportunities: Iterable[object]) -> list[object]:
    return [row for row in opportunities if getattr(row, "team_id", None) == team_id]


def _product_name(row: object) -> str | None:
    direct = getattr(row, "product_name", None)
    if direct is not None and str(direct).strip():
        return str(direct)
    product = getattr(row, "product", None)
    name = getattr(product, "name", None) if product is not None else None
    return str(name) if name is not None and str(name).strip() else None


def _preview_name_maps(db: object, rows: Sequence[object]) -> tuple[dict[str, str], dict[str, str]]:
    customer_ids = {
        getattr(row, "customer_id", None)
        for row in rows
        if getattr(row, "customer_name", None) is None and getattr(row, "customer_id", None) is not None
    }
    owner_identifiers = {
        getattr(row, "owner_id", None)
        for row in rows
        if getattr(row, "owner_name", None) is None and getattr(row, "owner_id", None) is not None
    }
    query = getattr(db, "query", None)
    if not callable(query):
        return {}, {}

    customer_names: dict[str, str] = {}
    if customer_ids:
        from app.models.customer import Customer

        customer_rows = query(Customer).filter(Customer.id.in_(customer_ids)).all()
        customer_names = {
            str(item.id): str(item.account_name)
            for item in customer_rows
            if getattr(item, "account_name", None) is not None
        }

    owner_ids: set[int] = set()
    for identifier in owner_identifiers:
        try:
            owner_ids.add(int(identifier))
        except (TypeError, ValueError):
            continue

    owner_names: dict[str, str] = {}
    if owner_ids:
        from app.models.user import User

        user_rows = query(User).filter(User.id.in_(owner_ids)).all()
        owner_names = {
            str(item.id): str(item.name)
            for item in user_rows
            if getattr(item, "name", None) is not None
        }
    return customer_names, owner_names


def _display_name(row: object, field: str, relation_id: str, names: dict[str, str]) -> str | None:
    direct = getattr(row, field, None)
    if direct is not None:
        return str(direct)
    identifier = getattr(row, relation_id, None)
    return names.get(str(identifier)) if identifier is not None else None


def _preview(row: object, customer_names: dict[str, str], owner_names: dict[str, str]) -> dict[str, Any]:
    closing = getattr(row, "expected_closing_date", None)
    if isinstance(closing, datetime):
        closing = closing.date()
    return {
        "id": getattr(row, "public_id", None),
        "name": getattr(row, "opportunity_name", None),
        "customer_name": _display_name(row, "customer_name", "customer_id", customer_names),
        "owner_name": _display_name(row, "owner_name", "owner_id", owner_names),
        "amount": _number(_amount(getattr(row, "total_amount", None))),
        "expected_closing_date": closing.isoformat() if closing is not None else None,
    }


def _sorted_rows(rows: Sequence[object]) -> list[object]:
    return sorted(
        rows,
        key=lambda row: (
            str(getattr(row, "opportunity_name", None) or ""),
            str(getattr(row, "public_id", None) or ""),
        ),
    )


def _card_previews(
    customer_names: dict[str, str], owner_names: dict[str, str], rows: Sequence[object]
) -> list[dict[str, Any]]:
    return [_preview(row, customer_names, owner_names) for row in _sorted_rows(rows)[:5]]


def _all_previews(
    customer_names: dict[str, str], owner_names: dict[str, str], rows: Sequence[object]
) -> list[dict[str, Any]]:
    return [_preview(row, customer_names, owner_names) for row in _sorted_rows(rows)]


def _bucket(
    customer_names: dict[str, str],
    owner_names: dict[str, str],
    key: str,
    label: str,
    rows: Sequence[object],
    total_count: int,
    total_amount: Decimal,
) -> dict[str, Any]:
    amount = sum((_amount(getattr(row, "total_amount", None)) for row in rows), Decimal(0))
    return {
        "key": key,
        "label": label,
        "count": len(rows),
        "amount": _number(amount),
        "ratio": _percent(Decimal(len(rows)), Decimal(total_count)),
        "amount_ratio": _percent(amount, total_amount),
        "preview": _card_previews(customer_names, owner_names, rows),
        "preview_total": len(rows),
    }


def _status_key(row: object) -> str:
    return str(_value(getattr(row, "status", None)))


def _amount_key(row: object) -> str:
    amount = _amount(getattr(row, "total_amount", None))
    if amount <= 100_000:
        return "under_100k"
    if amount <= 500_000:
        return "100k_500k"
    if amount <= 1_000_000:
        return "500k_1m"
    return "over_1m"


def _probability_key(row: object) -> str:
    probability = int(str(_value(getattr(row, "win_probability", 0)) or 0))
    if probability >= 100:
        return "100"
    if probability >= 80:
        return "80-99"
    if probability >= 50:
        return "50-79"
    return "0-49"


def _month_key(value: object) -> str | None:
    if isinstance(value, datetime):
        value = value.date()
    return value.strftime("%Y-%m") if isinstance(value, date) else None


def _month_segments(today: date) -> list[tuple[str, str]]:
    year, month = today.year, today.month
    result: list[tuple[str, str]] = []
    for offset in range(6):
        absolute = year * 12 + month - 1 + offset
        segment_year, segment_month = divmod(absolute, 12)
        result.append((f"{segment_year:04d}-{segment_month + 1:02d}", f"{segment_month + 1}月"))
    return result


def _product_segments(rows: Sequence[object]) -> list[tuple[str, str]]:
    counts = Counter(name for name in (_product_name(row) for row in rows) if name is not None)
    ranked = sorted(counts, key=lambda name: (-counts[name], name))
    return [(name, name) for name in ranked[:8]] + [("other", "其他"), ("blank", "未填写")]


def _product_key(row: object, top_names: set[str]) -> str:
    name = _product_name(row)
    if name is None:
        return "blank"
    return name if name in top_names else "other"


def _row_key(
    chart_key: str,
    row: object,
    *,
    product_names: set[str],
    valid_months: set[str],
) -> str | None:
    if chart_key == "status":
        return _status_key(row)
    if chart_key == "purchase_type":
        return str(_value(getattr(row, "purchase_type", None)))
    if chart_key == "license_type":
        return str(_value(getattr(row, "license_type", None)))
    if chart_key == "amount_band":
        return _amount_key(row)
    if chart_key == "product":
        return _product_key(row, product_names)
    if chart_key == "win_probability":
        return _probability_key(row)
    closing = getattr(row, "expected_closing_date", None)
    key = _month_key(closing)
    return key if key in valid_months else ("unscheduled" if key is None else None)


def _group_rows(
    chart_key: str,
    rows: Sequence[object],
    segments: Sequence[tuple[str, str]],
) -> dict[str, list[object]]:
    segment_keys = {key for key, _ in segments}
    product_names = {
        key for key, _ in segments if chart_key == "product" and key not in {"other", "blank"}
    }
    valid_months = {
        key for key, _ in segments if chart_key == "expected_closing_month" and key != "unscheduled"
    }
    grouped = {key: [] for key in segment_keys}
    for row in rows:
        key = _row_key(
            chart_key,
            row,
            product_names=product_names,
            valid_months=valid_months,
        )
        if key in grouped:
            grouped[key].append(row)
    return grouped


def _segments(chart_key: str, rows: Sequence[object], today: date) -> list[tuple[str, str]]:
    if chart_key == "status":
        return list(_STATUS_SEGMENTS)
    if chart_key == "purchase_type":
        return list(_PURCHASE_SEGMENTS)
    if chart_key == "license_type":
        return list(_LICENSE_SEGMENTS)
    if chart_key == "amount_band":
        return list(_AMOUNT_SEGMENTS)
    if chart_key == "product":
        return _product_segments(rows)
    if chart_key == "win_probability":
        return list(_PROBABILITY_SEGMENTS)
    if chart_key == "expected_closing_month":
        return [*_month_segments(today), ("unscheduled", "未排期")]
    raise ValueError(f"Unknown chart key: {chart_key}")


def build_opportunity_chart(
    db: object,
    team_id: object,
    opportunities: Iterable[object],
    today: date | None = None,
) -> dict[str, Any]:
    rows = _team_rows(team_id, opportunities)
    customer_names, owner_names = _preview_name_maps(db, rows)
    resolved_today = today or business_now().date()
    total_amount = sum((_amount(getattr(row, "total_amount", None)) for row in rows), Decimal(0))
    cards: list[dict[str, Any]] = []
    for chart_key in _CARD_KEYS:
        segments = _segments(chart_key, rows, resolved_today)
        grouped = _group_rows(chart_key, rows, segments)
        buckets = [
            _bucket(
                customer_names,
                owner_names,
                key,
                label,
                grouped[key],
                len(rows),
                total_amount,
            )
            for key, label in segments
        ]
        cards.append({"key": chart_key, "buckets": buckets})
    return {"population": len(rows), "total_amount": _number(total_amount), "cards": cards}


def _dialog_order(row: object) -> tuple[int, float, str, str]:
    created = getattr(row, "created_time", None)
    if isinstance(created, datetime):
        stamp = created
    elif isinstance(created, date):
        stamp = datetime.combine(created, datetime.min.time())
    else:
        stamp = None
    return (
        0 if stamp is not None else 1,
        -(stamp.timestamp() if stamp is not None else 0),
        str(getattr(row, "opportunity_name", None) or ""),
        str(getattr(row, "public_id", None) or ""),
    )


def list_chart_bucket_opportunities(
    db: object,
    team_id: object,
    opportunities: Iterable[object],
    chart_key: str,
    bucket_key: str,
    today: date | None = None,
    skip: int = 0,
    limit: int = 10,
) -> tuple[int, list[dict[str, Any]]]:
    rows = _team_rows(team_id, opportunities)
    customer_names, owner_names = _preview_name_maps(db, rows)
    resolved_today = today or business_now().date()
    segments = _segments(chart_key, rows, resolved_today)
    valid_keys = {key for key, _ in segments}
    if bucket_key not in valid_keys:
        raise ValueError(f"Unknown bucket key for {chart_key}: {bucket_key}")
    matching = _group_rows(chart_key, rows, segments)[bucket_key]
    ordered = sorted(matching, key=_dialog_order)
    window = ordered[skip:skip + limit]
    return len(ordered), [_preview(row, customer_names, owner_names) for row in window]



__all__ = ["build_opportunity_chart", "list_chart_bucket_opportunities"]
