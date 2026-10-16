"""只读客户图表, 同一批可见客户的数量和占比."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.list_query.license_status import (
    LICENSE_STATUS_EXPIRED,
    LICENSE_STATUS_NONE,
    LICENSE_STATUS_OFFICIAL,
    LICENSE_STATUS_TRIAL,
    classify_license_status,
)
from app.crud.industry import industry_crud
from app.models.lead import CompanyScale
from app.models.user import User
from app.services.customer_derived_status import (
    CUSTOMER_DERIVED_STATUS_LABELS,
    CustomerDerivedStatus,
    DerivedCustomerStatus,
    derive_customer_statuses_for_list,
)
from app.utils.time import business_now

CHART_KEYS = ("status", "license", "scale", "industry", "city", "created_month")
PREVIEW_LIMIT = 5
TOP_NAMED_LIMIT = 8
OTHER_KEY = "other"
BLANK_KEY = "blank"
OTHER_LABEL = "其他"
BLANK_LABEL = "未填写"

STATUS_ORDER = (
    CustomerDerivedStatus.NOT_STARTED,
    CustomerDerivedStatus.FOLLOWING,
    CustomerDerivedStatus.REPURCHASING,
    CustomerDerivedStatus.WON,
    CustomerDerivedStatus.LOST,
    CustomerDerivedStatus.PUBLIC_POOL,
)
LICENSE_ORDER = (
    (LICENSE_STATUS_NONE, "未授权"),
    (LICENSE_STATUS_EXPIRED, "已过期"),
    (LICENSE_STATUS_TRIAL, "试用"),
    (LICENSE_STATUS_OFFICIAL, "正式"),
)
SCALE_ORDER = tuple(item.value for item in CompanyScale)

CARD_COPY = {
    "status": ("状态", "各状态有多少家、占多少。"),
    "license": ("授权状态", "正式、试用、已过期、未授权各有多少家。"),
    "scale": ("规模", "各规模档有多少家。"),
    "industry": ("行业", "数量最多的 8 个。第 9 名起并进其他。没填的单独列出。"),
    "city": ("城市", "数量最多的 8 个。第 9 名起并进其他。写法不同的城市不会合并。"),
    "created_month": ("创建月份", "最近 6 个月, 每个月新建了多少家."),
}



@dataclass(frozen=True)
class ChartCustomer:
    customer_id: int
    public_id: str
    name: str
    owner_id: str | None
    industry_code: str | None
    city: str | None
    company_scale: str | None
    license_expiry_date: date | None
    license_type: str | None
    created_time: date
    derived: DerivedCustomerStatus | None


ChartPreview = dict[str, str | None]
ChartBucket = dict[str, str | int | list[ChartPreview]]
ChartCard = dict[str, str | list[ChartBucket]]
ChartPayload = dict[str, int | list[ChartCard]]
Segment = tuple[str, str, list[ChartCustomer]]


def build_customer_chart(
    db: Session,
    team_id: int,
    customers: Sequence[Any],
    today: date | None = None,
) -> ChartPayload:
    current_day = today or business_now().date()
    rows = _chart_rows(db, team_id, customers)
    owners = _owner_names(db, {row.owner_id for row in rows if row.owner_id})
    industry_names = _industry_names(db, [row.industry_code for row in rows])
    cards = [
        _fixed_card("status", rows, owners, _status_segments(rows)),
        _fixed_card("license", rows, owners, _license_segments(rows, current_day)),
        _scale_card(rows, owners),
        _named_card("industry", rows, owners, lambda row: _industry_label(row, industry_names)),
        _named_card("city", rows, owners, _city_label),
        _month_card(rows, owners, current_day),
    ]
    return {"population": len(rows), "cards": cards}


def list_chart_bucket_customers(
    db: Session,
    team_id: int,
    customers: Sequence[Any],
    chart_key: str,
    bucket_key: str,
    today: date | None = None,
) -> list[ChartPreview]:
    if chart_key not in CHART_KEYS:
        raise ValueError("未知图表")
    current_day = today or business_now().date()
    rows = _chart_rows(db, team_id, customers)
    owners = _owner_names(db, {row.owner_id for row in rows if row.owner_id})
    industry_names = _industry_names(db, [row.industry_code for row in rows])
    selected = [row for row in rows if _bucket_key(rows, row, chart_key, current_day, industry_names) == bucket_key]
    return [_preview(row, owners) for row in sorted(selected, key=lambda row: (row.name, row.public_id))]


def _chart_rows(db: Session, team_id: int, customers: Sequence[Any]) -> list[ChartCustomer]:
    derived = derive_customer_statuses_for_list(db, team_id, list(customers))
    rows: list[ChartCustomer] = []
    for customer in customers:
        if int(customer.team_id) != int(team_id):
            continue
        created = customer.created_time
        rows.append(ChartCustomer(
            customer_id=int(customer.id),
            public_id=str(customer.public_id),
            name=str(customer.account_name),
            owner_id=str(customer.owner_id) if customer.owner_id else None,
            industry_code=str(customer.industry).strip() if customer.industry else None,
            city=customer.city,
            company_scale=customer.company_scale,
            license_expiry_date=customer.license_expiry_date,
            license_type=customer.license_type,
            created_time=created.date() if hasattr(created, "date") else created,
            derived=derived.get(int(customer.id)),
        ))
    return rows


def _status_segments(rows: Sequence[ChartCustomer]) -> list[tuple[str, str, list[ChartCustomer]]]:
    grouped: dict[str, list[ChartCustomer]] = defaultdict(list)
    for row in rows:
        status = row.derived.status if row.derived is not None else None
        key = status.value if status is not None else BLANK_KEY
        grouped[key].append(row)
    segments = [
        (status.value, CUSTOMER_DERIVED_STATUS_LABELS[status], grouped.get(status.value, []))
        for status in STATUS_ORDER
    ]
    segments.append((BLANK_KEY, BLANK_LABEL, grouped.get(BLANK_KEY, [])))
    return segments


def _license_segments(rows: Sequence[ChartCustomer], today: date) -> list[tuple[str, str, list[ChartCustomer]]]:
    grouped: dict[str, list[ChartCustomer]] = defaultdict(list)
    for row in rows:
        grouped[classify_license_status(row.license_expiry_date, row.license_type, today)].append(row)
    return [(key, label, grouped.get(key, [])) for key, label in LICENSE_ORDER]


def _scale_card(rows: Sequence[ChartCustomer], owners: dict[str, str]) -> ChartCard:
    known = set(SCALE_ORDER)
    grouped: dict[str, list[ChartCustomer]] = defaultdict(list)
    extras: dict[str, list[ChartCustomer]] = defaultdict(list)
    for row in rows:
        scale = (row.company_scale or "").strip()
        if scale == "":
            grouped[BLANK_KEY].append(row)
        elif scale in known:
            grouped[scale].append(row)
        else:
            extras[scale].append(row)
    segments = [(scale, scale, grouped.get(scale, [])) for scale in SCALE_ORDER]
    for label in sorted(extras):
        segments.append((f"raw:{label}", label, extras[label]))
    segments.append((BLANK_KEY, BLANK_LABEL, grouped.get(BLANK_KEY, [])))
    return _card("scale", segments, len(rows), owners)


def _named_card(
    chart_key: str,
    rows: Sequence[ChartCustomer],
    owners: dict[str, str],
    label_of: Callable[[ChartCustomer], str | None],
) -> ChartCard:
    grouped: dict[str, list[ChartCustomer]] = defaultdict(list)
    blank: list[ChartCustomer] = []
    for row in rows:
        label = label_of(row)
        if label is None:
            blank.append(row)
        else:
            grouped[label].append(row)
    ranked = sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
    kept = ranked[:TOP_NAMED_LIMIT]
    overflow = ranked[TOP_NAMED_LIMIT:]
    segments = [(label, label, members) for label, members in kept]
    other = [row for _, members in overflow for row in members]
    segments.append((OTHER_KEY, OTHER_LABEL, other))
    segments.append((BLANK_KEY, BLANK_LABEL, blank))
    return _card(chart_key, segments, len(rows), owners)

def _fixed_card(
    chart_key: str,
    rows: Sequence[ChartCustomer],
    owners: dict[str, str],
    segments: Sequence[Segment],
) -> ChartCard:
    return _card(chart_key, segments, len(rows), owners)


def _month_card(rows: Sequence[ChartCustomer], owners: dict[str, str], today: date) -> ChartCard:
    months = _recent_months(today, 6)
    grouped: dict[str, list[ChartCustomer]] = defaultdict(list)
    for row in rows:
        key = f"{row.created_time.year:04d}-{row.created_time.month:02d}"
        if key in set(months):
            grouped[key].append(row)
    segments = [(key, _month_label(key), grouped.get(key, [])) for key in months]
    return _card("created_month", segments, len(rows), owners)


def _card(
    chart_key: str,
    segments: Sequence[Segment],
    population: int,
    owners: dict[str, str],
) -> ChartCard:
    title, description = CARD_COPY[chart_key]
    buckets: list[ChartBucket] = []
    for key, label, members in segments:
        ordered = sorted(members, key=lambda row: (row.name, row.public_id))
        count = len(ordered)
        buckets.append({
            "key": key,
            "label": label,
            "count": count,
            "ratio": _ratio(count, population),
            "preview": [_preview(row, owners) for row in ordered[:PREVIEW_LIMIT]],
            "preview_total": count,
        })
    return {"key": chart_key, "title": title, "description": description, "buckets": buckets}


def _bucket_key(
    rows: Sequence[ChartCustomer],
    row: ChartCustomer,
    chart_key: str,
    today: date,
    industry_names: dict[str, str],
) -> str:
    if chart_key == "status":
        return row.derived.status.value if row.derived is not None else BLANK_KEY
    if chart_key == "license":
        return classify_license_status(row.license_expiry_date, row.license_type, today)
    if chart_key == "scale":
        scale = (row.company_scale or "").strip()
        if scale == "":
            return BLANK_KEY
        if scale in SCALE_ORDER:
            return scale
        return f"raw:{scale}"
    if chart_key == "industry":
        labels = [_industry_label(item, industry_names) for item in rows]
        return _named_membership(_industry_label(row, industry_names), labels)
    if chart_key == "city":
        return _named_membership(_city_label(row), [_city_label(item) for item in rows])
    if chart_key == "created_month":
        return f"{row.created_time.year:04d}-{row.created_time.month:02d}"
    raise ValueError("未知图表")


def _named_membership(label: str | None, labels: Sequence[str | None]) -> str:
    if label is None:
        return BLANK_KEY
    counts: dict[str, int] = defaultdict(int)
    for item in labels:
        if item is not None:
            counts[item] += 1
    ranked = sorted(counts, key=lambda item: (-counts[item], item))
    if label in ranked[:TOP_NAMED_LIMIT]:
        return label
    return OTHER_KEY


def _industry_label(row: ChartCustomer, industry_names: dict[str, str]) -> str | None:
    code = (row.industry_code or "").strip()
    if code == "":
        return None
    name = industry_names.get(code, "").strip()
    if name == "" or name == BLANK_LABEL or name == OTHER_LABEL:
        return None
    return name


def _city_label(row: ChartCustomer) -> str | None:
    city = row.city if isinstance(row.city, str) else ""
    if city.strip() == "":
        return None
    return city


def _industry_names(db: Session, codes: Iterable[str | None]) -> dict[str, str]:
    unique = sorted({code.strip() for code in codes if code and code.strip()})
    if not unique:
        return {}
    found = industry_crud.get_by_codes_with_parent(db, unique)
    names: dict[str, str] = {}
    for code in unique:
        industry = found.get(code)
        if industry is None:
            names[code] = code
            continue
        secondary = industry.name if getattr(industry, "level", None) == 2 else None
        label = str(secondary or industry.name or "").strip()
        names[code] = label or BLANK_LABEL
    return names


def _owner_names(db: Session, owner_ids: set[str]) -> dict[str, str]:
    numeric_ids = [int(owner_id) for owner_id in owner_ids if str(owner_id).isdigit()]
    if not numeric_ids:
        return {}
    return {str(user.id): str(user.name) for user in db.query(User).filter(User.id.in_(numeric_ids)).all()}


def _preview(row: ChartCustomer, owners: dict[str, str]) -> ChartPreview:
    return {
        "id": row.public_id,
        "name": row.name,
        "owner_name": owners.get(row.owner_id) if row.owner_id else None,
    }


def _ratio(count: int, population: int) -> int:
    if population <= 0:
        return 0
    return int((count * 100 + population / 2) // population)


def _recent_months(today: date, count: int) -> list[str]:
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


if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence
    from datetime import date

    from sqlalchemy.orm import Session
