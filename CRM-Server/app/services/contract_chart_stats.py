# ruff: noqa: RUF001
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from app.utils.time import business_now

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


_LICENSE_SEGMENTS = (("SUBSCRIPTION", "订阅"), ("PERPETUAL", "买断"))
_PURCHASE_SEGMENTS = (("NEW", "新购"), ("RENEWAL", "续购"), ("EXPANSION", "增购"), ("blank", "未填写"))
_AMOUNT_SEGMENTS = (
    ("under_100k", "10 万以下"),
    ("100k_500k", "10–50 万"),
    ("500k_1m", "50–100 万"),
    ("over_1m", "100 万以上"),
)
_CARD_KEYS = ("license_type", "purchase_type", "amount_band", "signing_month")
_CARD_COPY = {
    "license_type": ("授权模式", "订阅、买断按合同金额看占比。"),
    "purchase_type": ("采购类型", "新购、续购、增购按合同金额看占比。没填的单独列出。"),
    "amount_band": ("金额档", "按合同金额分成四档。每行是份数和金额。"),
    "signing_month": (
        "签署月份",
        "最近 6 个月从左到右。更早签署的并成一根「更早」。还没签署的单独一根「未签署」，不并进本月。",
    ),
}
_PREVIEW_LIMIT = 5
_KNOWN_PURCHASE = {"NEW", "RENEWAL", "EXPANSION"}


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


def _team_rows(team_id: object, contracts: Iterable[object]) -> list[object]:
    return [row for row in contracts if getattr(row, "team_id", None) == team_id]


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


def _month_key(value: object) -> str | None:
    resolved = _as_date(value)
    return None if resolved is None else f"{resolved.year:04d}-{resolved.month:02d}"


def _recent_months(today: date) -> list[tuple[str, str]]:
    year, month = today.year, today.month
    result: list[tuple[str, str]] = []
    for offset in range(5, -1, -1):
        absolute = year * 12 + month - 1 - offset
        segment_year, segment_month = divmod(absolute, 12)
        result.append((f"{segment_year:04d}-{segment_month + 1:02d}", f"{segment_month + 1}月"))
    return result


def _signing_segments(today: date) -> list[tuple[str, str]]:
    return [("earlier", "更早"), *_recent_months(today), ("future", "未到期签署"), ("unsigned", "未签署")]


def _purchase_key(row: object, purchase_types: dict[int, str | None]) -> str:
    opportunity_id = getattr(row, "opportunity_id", None)
    if opportunity_id is None:
        return "blank"
    purchase_type = purchase_types.get(int(opportunity_id))
    if purchase_type is None:
        return "blank"
    value = str(_value(purchase_type))
    return value if value in _KNOWN_PURCHASE else "blank"


def _amount_key(row: object) -> str:
    amount = _amount(getattr(row, "total_amount", None))
    if amount <= 100_000:
        return "under_100k"
    if amount <= 500_000:
        return "100k_500k"
    if amount <= 1_000_000:
        return "500k_1m"
    return "over_1m"


def _signing_key(row: object, months: set[str], today: date) -> str:
    signing_date = _as_date(getattr(row, "signing_date", None))
    if signing_date is None:
        return "unsigned"
    key = f"{signing_date.year:04d}-{signing_date.month:02d}"
    if key in months:
        return key
    if (signing_date.year, signing_date.month) > (today.year, today.month):
        return "future"
    return "earlier"


def _row_key(
    chart_key: str,
    row: object,
    *,
    purchase_types: dict[int, str | None],
    months: set[str],
    today: date,
) -> str:
    if chart_key == "license_type":
        return str(_value(getattr(row, "license_type", None)))
    if chart_key == "purchase_type":
        return _purchase_key(row, purchase_types)
    if chart_key == "amount_band":
        return _amount_key(row)
    return _signing_key(row, months, today)


def _purchase_types(db: object, team_id: object, rows: Sequence[object]) -> dict[int, str | None]:
    direct = {
        int(row.opportunity_id): getattr(row, "purchase_type", None)
        for row in rows
        if getattr(row, "opportunity_id", None) is not None and hasattr(row, "purchase_type")
    }
    opportunity_ids = {
        int(row.opportunity_id)
        for row in rows
        if getattr(row, "opportunity_id", None) is not None and int(row.opportunity_id) not in direct
    }

    query = getattr(db, "query", None)
    if opportunity_ids and callable(query):
        from app.models.opportunity import Opportunity

        loaded = query(Opportunity).filter(
            Opportunity.team_id == team_id,
            Opportunity.id.in_(opportunity_ids),
        ).all()
        direct.update({
            int(item.id): None if item.purchase_type is None else item.purchase_type
            for item in loaded
        })
    return {
        opportunity_id: None if purchase_type is None else str(_value(purchase_type))
        for opportunity_id, purchase_type in direct.items()
    }


def _names(db: object, team_id: object, rows: Sequence[object]) -> tuple[dict[int, str], dict[str, str]]:
    customers = {
        int(row.customer_id): str(row.customer_name)
        for row in rows
        if getattr(row, "customer_id", None) is not None and getattr(row, "customer_name", None) is not None
    }
    owners = {
        str(row.owner_id): str(row.owner_name)
        for row in rows
        if getattr(row, "owner_id", None) is not None and getattr(row, "owner_name", None) is not None
    }
    query = getattr(db, "query", None)
    if not callable(query):
        return customers, owners
    from app.models.customer import Customer
    from app.models.user import User

    customer_ids = {
        int(row.customer_id)
        for row in rows
        if getattr(row, "customer_id", None) is not None and int(row.customer_id) not in customers
    }
    owner_ids = {
        str(row.owner_id)
        for row in rows
        if getattr(row, "owner_id", None) is not None and str(row.owner_id) not in owners
    }
    if customer_ids:
        loaded = query(Customer).filter(Customer.team_id == team_id, Customer.id.in_(customer_ids)).all()
        customers.update({int(item.id): str(item.account_name) for item in loaded if item.account_name is not None})
    if owner_ids:
        loaded = query(User).filter(User.id.in_(owner_ids)).all()
        owners.update({str(item.id): str(item.name) for item in loaded if item.name is not None})
    return customers, owners


def _sorted_rows(rows: Sequence[object]) -> list[object]:
    return sorted(rows, key=lambda row: (str(getattr(row, "contract_name", "")), int(getattr(row, "id", 0))))


def _preview(row: object, customers: dict[int, str], owners: dict[str, str]) -> dict[str, Any]:
    customer_id = getattr(row, "customer_id", None)
    owner_id = getattr(row, "owner_id", None)
    return {
        "id": int(row.id),
        "name": str(getattr(row, "contract_name", "")),
        "customer_name": customers.get(int(customer_id)) if customer_id is not None else None,
        "owner_name": owners.get(str(owner_id)) if owner_id is not None else None,
        "amount": _number(_amount(getattr(row, "total_amount", None))),
        "signing_date": _as_date(getattr(row, "signing_date", None)),
    }


def _bucket(
    customers: dict[int, str],
    owners: dict[str, str],
    key: str,
    label: str,
    rows: Sequence[object],
    total_count: int,
    total_amount: Decimal,
    *,
    preview_limit: int | None,
) -> dict[str, Any]:
    ordered = _sorted_rows(rows)
    amount = sum((_amount(getattr(row, "total_amount", None)) for row in ordered), Decimal(0))
    visible = ordered if preview_limit is None else ordered[:preview_limit]
    return {
        "key": key,
        "label": label,
        "count": len(ordered),
        "amount": _number(amount),
        "ratio": _percent(Decimal(len(ordered)), Decimal(total_count)),
        "amount_ratio": _percent(amount, total_amount),
        "preview": [_preview(row, customers, owners) for row in visible],
        "preview_total": len(ordered),
    }


def _segments(chart_key: str, today: date) -> list[tuple[str, str]]:
    if chart_key == "license_type":
        return list(_LICENSE_SEGMENTS)
    if chart_key == "purchase_type":
        return list(_PURCHASE_SEGMENTS)
    if chart_key == "amount_band":
        return list(_AMOUNT_SEGMENTS)
    if chart_key == "signing_month":
        return _signing_segments(today)
    raise ValueError("未知图表")


def _cards(
    rows: Sequence[object],
    *,
    purchase_types: dict[int, str | None],
    customers: dict[int, str],
    owners: dict[str, str],
    today: date,
    preview_limit: int | None,
) -> list[dict[str, Any]]:
    total_amount = sum((_amount(getattr(row, "total_amount", None)) for row in rows), Decimal(0))
    months = {key for key, _label in _recent_months(today)}
    cards: list[dict[str, Any]] = []
    for chart_key in _CARD_KEYS:
        segments = _segments(chart_key, today)
        grouped = {key: [] for key, _label in segments}
        for row in rows:
            key = _row_key(chart_key, row, purchase_types=purchase_types, months=months, today=today)
            if key in grouped:
                grouped[key].append(row)
        title, description = _CARD_COPY[chart_key]
        cards.append({
            "key": chart_key,
            "title": title,
            "description": description,
            "buckets": [
                _bucket(
                    customers,
                    owners,
                    key,
                    label,
                    grouped[key],
                    len(rows),
                    total_amount,
                    preview_limit=preview_limit,
                )
                for key, label in segments
            ],
        })
    return cards


def build_contract_chart(
    db: object,
    team_id: object,
    contracts: Iterable[object],
    today: date | None = None,
) -> dict[str, Any]:
    rows = _team_rows(team_id, contracts)
    resolved_today = today or business_now().date()
    customers, owners = _names(db, team_id, rows)
    total_amount = sum((_amount(getattr(row, "total_amount", None)) for row in rows), Decimal(0))
    return {
        "population": len(rows),
        "total_amount": _number(total_amount),
        "cards": _cards(
            rows,
            purchase_types=_purchase_types(db, team_id, rows),
            customers=customers,
            owners=owners,
            today=resolved_today,
            preview_limit=_PREVIEW_LIMIT,
        ),
    }


def list_chart_bucket_contracts(
    db: object,
    team_id: object,
    contracts: Iterable[object],
    chart_key: str,
    bucket_key: str,
    today: date | None = None,
) -> list[dict[str, Any]]:
    if chart_key not in _CARD_KEYS:
        raise ValueError("未知图表")
    rows = _team_rows(team_id, contracts)
    resolved_today = today or business_now().date()
    segments = _segments(chart_key, resolved_today)
    if bucket_key not in {key for key, _label in segments}:
        raise ValueError("未知图表")
    customers, owners = _names(db, team_id, rows)
    purchase_types = _purchase_types(db, team_id, rows)
    months = {key for key, _label in _recent_months(resolved_today)}
    matching = [
        row for row in rows
        if _row_key(
            chart_key,
            row,
            purchase_types=purchase_types,
            months=months,
            today=resolved_today,
        ) == bucket_key
    ]
    return [_preview(row, customers, owners) for row in _sorted_rows(matching)]


__all__ = ["build_contract_chart", "list_chart_bucket_contracts"]
