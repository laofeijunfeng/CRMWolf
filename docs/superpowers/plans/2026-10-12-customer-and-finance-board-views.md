# Customer and Finance Board Views Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add factual, permission-scoped board views for customers, opportunities, contracts, payment plans, and payment records without changing existing list, export, detail, approval, confirmation, or editing workflows.

**Architecture:** Keep `DataTable` as the owner of page search, filters, sorting, saved views, exports, pagination, and list state. Render each board through the existing `DataTable` `replacement` slot. Each domain gets an independent backend population query, Pydantic response contract, aggregation service, route, Zod schema, API client method, and projection adapter. A typed shared board shell owns layout and request-state presentation but never guesses domain field names.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, Decimal, existing list-query catalogs and permission dependencies; Vue 3 `<script setup>`, TypeScript, Zod, existing V2 CRM components, semantic design tokens, Vitest, pytest, Ruff, and mypy.

## Global Constraints

- The UI value `列表` maps to display mode `table`; `看板` maps to display mode `board`; the default is `table`.
- Preserve the global `ViewDisplayMode` union, including `chart` for unrelated consumers. Normalize only legacy customer `chart` preferences to `board`.
- Preserve `/v1/customers/chart` and all unrelated chart consumers; customer chart data is not the customer page's primary projection after this change.
- Reuse `DataTable` and its existing `replacement` slot. Do not add a second list/query framework or a universal board aggregation service.
- Preserve search, legacy filters, unified JSON filters, sorting, field configuration, saved views, pagination, retry, row actions, detail navigation, and exports.
- Board requests reuse the current list query fields and JSON filter/sort serialization. They omit `page`, `page_size`, `skip`, and `limit`.
- Board routes simply define no pagination parameters. Do not claim that FastAPI automatically rejects undeclared pagination query parameters.
- Backend team and permission isolation runs before every summary, trend, count, and preview calculation.
- Every board is computed from the complete authorized filtered population, never from the current list page and never by re-aggregating five preview cards.
- Sorting changes preview order only. It never changes counts, amounts, percentages, or trend buckets.
- Every response returns its complete ordered column set, full column counts, full column totals, at most five preview items per column, `has_more`, and `remaining_count`.
- Each domain has an independent strict Pydantic response contract. Shared primitives may be reused, but public item, metadata, column, summary, and response contracts remain domain-specific and reject unknown fields.
- Each domain has an independent strict Zod response contract. API methods parse `unknown` before returning domain data.
- Aggregate money with backend `Decimal`. Serialize every non-null amount as a fixed-point string with exactly two fractional digits. Counts are strict nonnegative integers and reject booleans and fractions. Percentages are finite JSON numbers in `0–100`; undefined ratios are `null`.
- Empty authorized populations return complete ordered columns, zero summaries, and empty trends. Unknown or missing states remain observable in explicit `unclassified` or `unset_stage` columns.
- Use the approved finite trend-window rules. Missing bounds never create open-ended intervals.
- Customer status comes from `derive_customer_statuses_for_list`. Public-pool customers remain in the existing `public` list tab and outside ordinary lifecycle columns.
- Payment-plan own scope uses `Contract.owner_id`. Payment-record own scope uses `Contract.creator_id`.
- Payment authorization is applied before every payment summary, trend, count, and preview query.
- Payment records group by canonical approval status. Confirmation status remains a separate card field and badge. A confirmed record without approval evidence is not approved.
- Preserve the payment-record external tab key `confirmed` and label `已确认`; map that tab to canonical approval `approved`. The board approval column may use `已通过`.
- Register every static `/board` route before the corresponding dynamic entity-ID route in the same router.
- Do not add a schema migration, drag-and-drop status write, board-specific mutation, duplicate detail route, or unrelated validation.
- Do not add TypeScript `any`, `as any`, or `@ts-ignore`.
- Use existing V2/shadcn components, semantic tokens, `AmountText`, existing date and currency helpers, contained desktop horizontal scrolling, narrow-screen state selection, and keyboard activation.
- Preserve successful board snapshots during ordinary refresh failure and mark them stale. Clear snapshots synchronously and invalidate in-flight requests when team, user, or permission scope changes.
- Schedule cleanup only after successful desktop and narrow-screen UI smoke verification.
- All commands in this document are future verification commands and are not run during plan preparation.

---

## Responsibility-Based File Map

### Backend shared primitives and contracts

- **Create** `CRM-Server/app/services/board_trend_window.py` for complete-month window resolution, filter-bound extraction, month keys, and strict event-date bounds.
- **Create** `CRM-Server/app/services/board_value_format.py` for Decimal serialization, finite percentage calculation, and the fixed preview limit.
- **Create** `CRM-Server/app/schemas/board_primitives.py` for strict owner and metric primitives only; each domain declares its own metadata, action state, item, column, trend, summary union, and response model.
- **Modify** `CRM-Server/app/core/list_query/engine.py` near `_parse_date` to expose the existing date parser to board-bound extraction without changing existing list semantics.
- **Create** `CRM-Server/app/services/payment_approval_status.py` for canonical Python and SQL approval read semantics.
- **Modify** `CRM-Server/app/core/list_query/catalogs/common.py` to delegate the payment approval expression to the canonical helper.
- **Modify** `CRM-Server/app/core/list_query/catalogs/payment_records.py` to use canonical approval semantics; the existing `is_empty` predicate selects the canonical `NULL` branch.
- **Modify** `CRM-Server/app/crud/payment.py` to apply canonical approval semantics to legacy tabs, unified filters, and exclusions.

### Backend domain contracts and aggregators

- **Create** `CRM-Server/app/schemas/customer_board.py` and `CRM-Server/app/services/customer_board_service.py`.
- **Create** `CRM-Server/app/schemas/opportunity_board.py` and `CRM-Server/app/services/opportunity_board_service.py`.
- **Create** `CRM-Server/app/schemas/contract_board.py` and `CRM-Server/app/services/contract_board_service.py`.
- **Create** `CRM-Server/app/schemas/payment_plan_board.py` and `CRM-Server/app/services/payment_plan_board_service.py`.
- **Create** `CRM-Server/app/schemas/payment_record_board.py` and `CRM-Server/app/services/payment_record_board_service.py`.
- **Modify** `CRM-Server/app/crud/customer.py`, `opportunity.py`, `contract.py`, and `payment.py` with keyword-only, non-paginated population builders that preserve current list semantics.
- **Modify** `CRM-Server/app/api/customers.py`, `opportunities.py`, `contracts.py`, and `payments.py` with the five static board routes, preserving current team dependencies, current-user dependencies, permission checks, and route ordering.

### Frontend transport and shared board UI

- **Create** `CRM-Client/src/schemas/customerBoard.ts`, `opportunityBoard.ts`, `contractBoard.ts`, `paymentPlanBoard.ts`, and `paymentRecordBoard.ts`.
- **Modify** `CRM-Client/src/api/customer.ts`, `opportunity.ts`, `contract.ts`, and `payment.ts` with exact non-paginated board parameter types and Zod-validated methods.
- **Create** `CRM-Client/src/components/crmwolf/boardTypes.ts`, `BoardView.vue`, and `useBoardSnapshot.ts`; create `CRM-Client/src/schemas/boardPrimitives.ts` for strict scalar/metric primitives, not domain items.
- **Modify** `CRM-Client/src/components/crmwolf/DataTable.vue` and `ColumnConfigPopover.vue` for mode persistence and the `列表`/`看板` selector. Keep export behavior in `ListAdvancedTools`.
- **Modify** `CRM-Client/src/composables/useCustomFilterViews.ts` to retain display mode, stored columns, and synchronous failed-apply rollback in its existing snapshots.
- **Modify** `CRM-Client/src/api/viewPreference.ts` to expose customer-only display-mode normalization while preserving the global `ViewDisplayMode = 'table' | 'board' | 'chart'` type.
- **Create** `CRM-Client/src/components/customer/CustomerBoardProjection.vue`.
- **Create** `CRM-Client/src/components/opportunity/OpportunityBoardProjection.vue` and the new `CRM-Client/src/components/opportunity/` directory.
- **Create** `CRM-Client/src/components/contract/ContractBoardProjection.vue` and the new `CRM-Client/src/components/contract/` directory.
- **Create** `CRM-Client/src/components/payment/PaymentPlanBoardProjection.vue`, `PaymentRecordBoardProjection.vue`, and the new `CRM-Client/src/components/payment/` directory.
- **Modify** `CRM-Client/src/views/Customers.vue`, `Opportunities.vue`, `Contracts.vue`, `PaymentPlans.vue`, and `PaymentRecords.vue` for board query state, mode switching, snapshots, details, actions, and list drill-through.

### Verification files

- **Create** focused backend tests under `CRM-Server/tests/unit/` for trend/value helpers, approval semantics, strict contracts, five aggregators, five routes, permissions, Decimal serialization, and pagination independence.
- **Create** focused frontend tests under `CRM-Client/src/schemas/__tests__/`, `CRM-Client/src/components/crmwolf/__tests__/`, and the existing view test locations for schemas, snapshots, shell interaction, mode persistence, projection mapping, and page integration.
- Do not create temporary plans, validation reports, or one-off scripts at the repository root.

---

## Shared Interfaces and Invariants

Use these interfaces consistently in all 18 tasks. Code fences are implementation recipes, not claims that implementation exists. No command or executable snippet is run during plan preparation.

### Backend trend window

Expose the existing parser in `CRM-Server/app/core/list_query/engine.py` as `parse_date_value(value: object) -> datetime | None`, retaining its existing body and timezone behavior. Migrate `_parse_value` and every actual `_parse_date` caller to that name; remove the old private name rather than retaining an unused wrapper. No configured language server is available: locate those callers with repository search during execution.

```python
# CRM-Server/app/services/board_trend_window.py
from dataclasses import dataclass
from datetime import date, timedelta
from collections.abc import Sequence

from app.core.list_query.engine import parse_date_value
from app.core.list_query.types import FilterCondition


@dataclass(frozen=True)
class BoardTrendWindow:
    event_start: date | None
    event_end: date | None
    months: tuple[str, ...]

    @property
    def empty(self) -> bool:
        return not self.months

    def __post_init__(self) -> None:
        if self.empty:
            if self.event_start is not None or self.event_end is not None:
                raise ValueError("empty trend window has no event interval")
        elif self.event_start is None or self.event_end is None:
            raise ValueError("nonempty trend window requires closed event bounds")
        elif self.event_start > self.event_end:
            raise ValueError("reversed trend event interval")


def month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _shift_month(value: date, offset: int) -> date:
    ordinal = value.year * 12 + value.month - 1 + offset
    year, zero_based_month = divmod(ordinal, 12)
    return date(year, zero_based_month + 1, 1)


def extract_board_date_bounds(
    filters: Sequence[FilterCondition] | None,
    field: str,
) -> tuple[date | None, date | None]:
    lower: date | None = None
    upper: date | None = None
    for condition in filters or ():
        if condition.field != field or condition.op not in {"eq", "after", "before"}:
            continue
        parsed = parse_date_value(condition.value)
        if parsed is None:
            continue
        day = parsed.date()
        if condition.op in {"eq", "after"}:
            lower = day if lower is None else max(lower, day)
        if condition.op in {"eq", "before"}:
            upper = day if upper is None else min(upper, day)
    return lower, upper


def resolve_board_trend_window(
    *,
    today: date,
    start_bound: date | None,
    end_bound: date | None,
) -> BoardTrendWindow:
    latest_complete_day = today.replace(day=1) - timedelta(days=1)
    if start_bound is not None and start_bound > latest_complete_day:
        return BoardTrendWindow(None, None, ())
    if start_bound is not None and end_bound is not None:
        start, end = start_bound, end_bound
    elif start_bound is not None:
        start, end = start_bound, latest_complete_day
    else:
        end = min(end_bound, latest_complete_day) if end_bound is not None else latest_complete_day
        start = _shift_month(end.replace(day=1), -5)
    if end < start:
        return BoardTrendWindow(None, None, ())
    cursor, last = start.replace(day=1), end.replace(day=1)
    months: list[str] = []
    while cursor <= last:
        months.append(month_key(cursor))
        cursor = _shift_month(cursor, 1)
    return BoardTrendWindow(start, end, tuple(months))
```

Date catalogs support `eq`, `after`, `before`, `is_empty`, and `is_not_empty`. The five event fields use inclusive `day_bounds`; the latter two operators do not define numeric date bounds. Extract bounds only after the existing catalog has validated the query. Invalid values retain the list's existing error behavior; window extraction does not add or suppress query validation. Intersect legacy event bounds only when the selected list branch actually applies them. Do not use ignored legacy dates to shorten a unified-query trend.

For `today=date(2026, 10, 12)`:

| Inputs | Month buckets | Closed event bounds |
| --- | --- | --- |
| neither bound | April–September 2026 | `2026-04-01`–`2026-09-30` |
| start `2026-07-18` only | July–September 2026 | `2026-07-18`–`2026-09-30` |
| end `2026-08-09` only | March–August 2026 | `2026-03-01`–`2026-08-09` |
| `2026-05-17`–`2026-07-09` | May–July 2026 | exact explicit bounds |
| start `2026-10-01` or reversed explicit bounds | none | both `None` |
| end `2026-12-10` only | April–September 2026 | capped at `2026-09-30` |

Both explicit bounds retain their end date/month, provided the start is not after the latest complete month; only missing-end and end-only windows impose the latest-complete-month cap. Every nonempty population with a nonempty window returns all month buckets, including zero-event months. An empty authorized population always returns `trends=[]`; a nonempty population with an empty window also returns `trends=[]`. A datetime event is included by its business-date value, preserving the parser's existing semantics; an equivalent SQL event constraint uses start-of-day through end-of-day inclusive.

### Backend fixed-point values

```python
# CRM-Server/app/services/board_value_format.py
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MONEY_QUANTUM = Decimal("0.01")
BOARD_PREVIEW_LIMIT = 5


def money_string(value: Decimal | int | str | None) -> str | None:
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            raise ValueError("amount must be finite")
        return format(amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP), ".2f")
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("invalid fixed-point amount") from error


def finite_percentage(
    numerator: int | Decimal,
    denominator: int | Decimal,
) -> float | None:
    try:
        top, bottom = Decimal(str(numerator)), Decimal(str(denominator))
        if not top.is_finite() or not bottom.is_finite():
            raise ValueError("percentage inputs must be finite")
        if bottom == 0:
            return None
        percentage = top * Decimal("100") / bottom
        if not percentage.is_finite() or not Decimal("0") <= percentage <= Decimal("100"):
            raise ValueError("percentage must be in 0-100")
        return float(percentage)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("invalid percentage") from error
```

Sum unrounded Decimal values first; quantize only when constructing transport values. `money_string(None)` is `None`; zero is `"0.00"`; negative amounts and negative remaining balances remain representable. Invalid/nonfinite values fail, rather than becoming zero. No per-request preview-limit function is necessary.

### Strict shared Pydantic primitives

```python
# CRM-Server/app/schemas/board_primitives.py
from datetime import date
from typing import Annotated, Literal, Self
from pydantic import (
    AfterValidator, BaseModel, ConfigDict, Field, StrictBool, StrictFloat,
    StrictInt, StrictStr, StringConstraints, model_validator,
)

Count = Annotated[StrictInt, Field(ge=0)]
EntityId = Annotated[StrictInt, Field(gt=0)]
AmountString = Annotated[StrictStr, StringConstraints(pattern=r"^-?\d+\.\d{2}$")]
Percentage = Annotated[StrictFloat, Field(ge=0, le=100, allow_inf_nan=False)]
BoardTone = Literal["neutral", "info", "success", "warning", "danger", "muted"]


def _valid_date(value: str) -> str:
    date.fromisoformat(value)
    return value


def _valid_month(value: str) -> str:
    date.fromisoformat(f"{value}-01")
    return value


DateString = Annotated[
    StrictStr, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$"), AfterValidator(_valid_date),
]
MonthString = Annotated[
    StrictStr, StringConstraints(pattern=r"^\d{4}-\d{2}$"), AfterValidator(_valid_month),
]


class StrictBoardModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class BoardOwner(StrictBoardModel):
    id: StrictStr
    name: StrictStr
    avatar_url: StrictStr | None = None


class BoardMetricBase(StrictBoardModel):
    key: StrictStr
    label: StrictStr
    secondary_label: StrictStr | None = None

    @model_validator(mode="after")
    def validate_secondary_label(self) -> Self:
        secondary_value = getattr(self, "secondary_value", None)
        if (secondary_value is not None) != (self.secondary_label is not None):
            raise ValueError("secondary value and label must be present together")
        return self


class BoardCountMetric(BoardMetricBase):
    value_type: Literal["count"]
    value: Count | None
    secondary_value: Count | None = None


class BoardAmountMetric(BoardMetricBase):
    value_type: Literal["amount"]
    value: AmountString | None
    secondary_value: AmountString | None = None


class BoardPercentageMetric(BoardMetricBase):
    value_type: Literal["percentage"]
    value: Percentage | None
    secondary_value: Percentage | None = None


BoardMetric = Annotated[
    BoardCountMetric | BoardAmountMetric | BoardPercentageMetric,
    Field(discriminator="value_type"),
]


def validate_preview_counts(*, count: int, shown: int, has_more: bool, remaining: int) -> None:
    if count < 0 or shown != min(count, 5) or remaining != count - shown or has_more != (remaining > 0):
        raise ValueError("inconsistent board preview counts")


```
`StrictBoardModel` uses Pydantic strict mode in addition to `extra="forbid"`; domain fields may use ordinary annotations without coercing booleans, fractions, or strings into numeric values. `BoardMetricBase` is the public shared base name used by every domain metric union. The base validator couples a non-null `secondary_value` to exactly one non-null `secondary_label` and rejects a label without a value.

### Canonical payment approval read status

```python
# CRM-Server/app/services/payment_approval_status.py
from dataclasses import dataclass
from enum import StrEnum
from sqlalchemy import and_, case, exists
from sqlalchemy.sql.elements import ColumnElement
from app.constants.business_types import BusinessType
from app.core.list_query.types import ListQueryContext
from app.models.approval import Approval, ApprovalStatus
from app.models.payment import PaymentRecord


class PaymentApprovalReadStatus(StrEnum):
    PENDING_SUBMIT = "pending_submit"
    PENDING_APPROVAL = "pending_approval"
    REJECTED = "rejected"
    APPROVED = "approved"
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True)
class LinkedPaymentApproval:
    id: int
    team_id: int
    business_type: str
    business_id: int
    status: str | None


def resolve_payment_approval_status(
    *,
    record_id: int,
    team_id: int,
    approval_id: int | None,
    approval_phase: str | None,
    linked_approval: LinkedPaymentApproval | None,
) -> PaymentApprovalReadStatus:
    if (
        linked_approval is not None
        and linked_approval.id == approval_id
        and linked_approval.team_id == team_id
        and linked_approval.business_type == BusinessType.PAYMENT
        and linked_approval.business_id == record_id
    ):
        if linked_approval.status == ApprovalStatus.PENDING:
            return PaymentApprovalReadStatus.PENDING_APPROVAL
        if linked_approval.status == ApprovalStatus.REJECTED:
            return PaymentApprovalReadStatus.REJECTED
        if linked_approval.status == ApprovalStatus.APPROVED:
            return PaymentApprovalReadStatus.APPROVED
    phase_by_value: dict[str, PaymentApprovalReadStatus] = {
        "pending_review": PaymentApprovalReadStatus.PENDING_APPROVAL,
        "rejected": PaymentApprovalReadStatus.REJECTED,
        "approved": PaymentApprovalReadStatus.APPROVED,
        "draft": PaymentApprovalReadStatus.PENDING_SUBMIT,
    }
    if approval_phase is None:
        return PaymentApprovalReadStatus.UNCLASSIFIED
    return phase_by_value.get(
        approval_phase,
        PaymentApprovalReadStatus.UNCLASSIFIED,
    )


def payment_approval_status_expression(context: ListQueryContext) -> ColumnElement[str | None]:
    def linked(status: str) -> ColumnElement[bool]:
        return exists().where(and_(
            Approval.id == PaymentRecord.approval_id,
            Approval.team_id == PaymentRecord.team_id,
            Approval.business_type == BusinessType.PAYMENT,
            Approval.business_id == PaymentRecord.id,
            Approval.status == status,
        )).correlate(PaymentRecord)

    return case(
        (linked(ApprovalStatus.PENDING), "pending_approval"),
        (linked(ApprovalStatus.REJECTED), "rejected"),
        (linked(ApprovalStatus.APPROVED), "approved"),
        (PaymentRecord.approval_phase == "pending_review", "pending_approval"),
        (PaymentRecord.approval_phase == "rejected", "rejected"),
        (PaymentRecord.approval_phase == "approved", "approved"),
        (PaymentRecord.approval_phase == "draft", "pending_submit"),
        else_=None,
    )
```

The `context` parameter preserves the existing catalog expression-builder contract. Authorization belongs to the population query, not this CASE expression. Linked `CANCELLED`, missing, wrong-ID, wrong-team, wrong-business-type, and wrong-business-record evidence fall through to native phase. Confirmation is deliberately absent. Keep canonical unclassified SQL output `NULL`; map it to `unclassified` only while constructing board response fields. Existing `approval_status is_empty` already selects that SQL-null branch; do not add another null predicate or operator. For direct legacy include/exclude helpers, compare known canonical strings and use `.is_(None)` only when `unclassified` is explicitly requested; exclusions retain nulls otherwise. Preserve the external tab key `confirmed` and label `已确认`, and map that key to canonical `approved` only at the existing route/client compatibility boundary.

---

## Task 1: Add shared backend trend, value, and primitive contracts

**Files:**
- Create: `CRM-Server/app/services/board_trend_window.py`
- Create: `CRM-Server/app/services/board_value_format.py`
- Create: `CRM-Server/app/schemas/board_primitives.py`
- Modify: `CRM-Server/app/core/list_query/engine.py` at the existing `_parse_date` implementation and its internal call site
- Create: `CRM-Server/tests/unit/test_board_trend_window.py`
- Create: `CRM-Server/tests/unit/test_board_value_format.py`
- Create: `CRM-Server/tests/unit/test_board_primitives.py`

- `parse_date_value(value: object) -> datetime | None` is the one reusable date parser. Rename the existing parser body, update `_parse_value`, and migrate every actual caller found by repository search; do not retain a private compatibility wrapper or an unused alias.
- `resolve_board_trend_window(*, today: date, start_bound: date | None, end_bound: date | None) -> BoardTrendWindow` and `extract_board_date_bounds(filters: Sequence[FilterCondition] | None, field: str) -> tuple[date | None, date | None]` produce the shared window semantics.
- `money_string(value: Decimal | int | str | None) -> str | None` and `finite_percentage(numerator: int | Decimal, denominator: int | Decimal) -> float | None` are the only backend transport-format helpers used by board services.

- [ ] **Step 1: Write red-capable helper tests.**

Use executable tests rather than source-text assertions:

```python
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.list_query.types import FilterCondition
from app.services.board_trend_window import extract_board_date_bounds, resolve_board_trend_window
from app.services.board_value_format import finite_percentage, money_string


def test_supported_date_bounds_use_inclusive_day_bounds() -> None:
    filters = [
        FilterCondition(field="created_time", op="after", value="2026-07-18"),
        FilterCondition(field="created_time", op="before", value="2026-08-09"),
    ]
    assert extract_board_date_bounds(filters, "created_time") == (
        date(2026, 7, 18), date(2026, 8, 9)
    )


@pytest.mark.parametrize("op", ["is_empty", "is_not_empty"])
def test_empty_date_operators_do_not_create_trend_bounds(op: str) -> None:
    assert extract_board_date_bounds(
        [FilterCondition(field="created_time", op=op)], "created_time"
    ) == (None, None)


def test_window_examples_are_exact() -> None:
    today = date(2026, 10, 12)
    assert resolve_board_trend_window(today=today, start_bound=None, end_bound=None).months == (
        "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"
    )
    assert resolve_board_trend_window(
        today=today, start_bound=date(2026, 7, 18), end_bound=None
    ).months == ("2026-07", "2026-08", "2026-09")
    assert resolve_board_trend_window(
        today=today, start_bound=None, end_bound=date(2026, 8, 9)
    ).months == ("2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08")


def test_empty_or_invalid_value_rules() -> None:
    assert resolve_board_trend_window(
        today=date(2026, 10, 12), start_bound=date(2026, 10, 1), end_bound=None
    ).months == ()
    assert resolve_board_trend_window(
        today=date(2026, 10, 12), start_bound=date(2026, 8, 1), end_bound=date(2026, 7, 31)
    ).months == ()
    assert money_string(Decimal("0")) == "0.00"
    assert money_string(Decimal("-1.005")) == "-1.01"
    assert finite_percentage(1, 0) is None
    with pytest.raises(ValueError):
        finite_percentage(2, 1)
```

The date catalog supports only `eq`, `after`, `before`, `is_empty`, and `is_not_empty`; numeric operators `gt`, `gte`, `lt`, and `lte` are not date-bound guidance and must not appear in the implementation or tests. A date query using an unsupported operator is rejected by the existing catalog before board extraction.

- [ ] **Step 2: Implement the shared algorithms.**

Use the executable implementations in the shared contract above. `resolve_board_trend_window` must use the latest day in the last complete calendar month, retain exact explicit two-sided bounds, cap only missing-end and end-only windows at that day, return `BoardTrendWindow(None, None, ())` for a future start or reversed interval, and include every month from the start month through the end month. The nonempty interval must have non-null closed event bounds; an empty interval must have both bounds `None`. Build a fresh zero-filled month map before adding events so empty months remain in the response.

For `money_string`, convert every non-null input with `Decimal(str(value))`, reject invalid or non-finite values, quantize with `ROUND_HALF_UP`, and format exactly two fractional digits. For `finite_percentage`, use Decimal arithmetic, return `None` for a zero denominator, and raise for non-finite inputs or a result outside `0–100`; never clamp.

- [ ] **Step 3: Implement strict shared Pydantic primitives.**

Keep `StrictInt` plus nonnegative validation for counts, strict fixed-point amount strings that accept negative values, finite bounded percentages, and `ConfigDict(extra="forbid")`. Use a discriminated metric union by `value_type`. The model validator must require `secondary_label` exactly when `secondary_value` is non-null; a label without a secondary value is also invalid. Shared primitives must not define a domain item or metadata dictionary.

- [ ] **Step 4: Run focused helper checks.**

**Future verification (not run during plan preparation):**

```bash
cd CRM-Server && pytest tests/unit/test_board_trend_window.py tests/unit/test_board_value_format.py tests/unit/test_board_primitives.py -q
```

Expected: exact month tuples, parser-compatible bounds, fixed-point rounding, zero-denominator nulls, and strict rejection of booleans, fractions, extra fields, invalid amounts, and invalid percentages.

---

## Task 2: Replace payment approval read semantics before payment aggregation

**Files:**
- Create: `CRM-Server/app/services/payment_approval_status.py`
- Modify: `CRM-Server/app/core/list_query/catalogs/common.py`
- Modify: `CRM-Server/app/core/list_query/catalogs/payment_records.py` to keep its existing `approval_status` expression wiring pointed at the canonical helper; the existing `approval_status is_empty` predicate already selects SQL `NULL`, so do not add a new null/unclassified operator
- Modify: `CRM-Server/app/crud/payment.py`
- Create: `CRM-Server/tests/unit/test_payment_approval_status.py`
- Create: `CRM-Server/tests/unit/test_payment_approval_list_parity.py`

**Interfaces and imports:**

```python
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import and_, case, exists
from sqlalchemy.sql.elements import ColumnElement

from app.constants.business_types import BusinessType
from app.core.list_query.types import ListQueryContext
from app.models.approval import Approval, ApprovalStatus
from app.models.payment import PaymentRecord

class PaymentApprovalReadStatus(StrEnum):
    PENDING_SUBMIT = "pending_submit"
    PENDING_APPROVAL = "pending_approval"
    REJECTED = "rejected"
    APPROVED = "approved"
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True)
class LinkedPaymentApproval:
    id: int
    team_id: int
    business_type: str
    business_id: int
    status: str | None


def resolve_payment_approval_status(
    *,
    record_id: int,
    team_id: int,
    approval_id: int | None,
    approval_phase: str | None,
    linked_approval: LinkedPaymentApproval | None,
) -> PaymentApprovalReadStatus:
    if (
        linked_approval is not None
        and linked_approval.id == approval_id
        and linked_approval.team_id == team_id
        and linked_approval.business_type == BusinessType.PAYMENT
        and linked_approval.business_id == record_id
    ):
        linked_status = linked_approval.status
        if linked_status == ApprovalStatus.PENDING:
            return PaymentApprovalReadStatus.PENDING_APPROVAL
        if linked_status == ApprovalStatus.REJECTED:
            return PaymentApprovalReadStatus.REJECTED
        if linked_status == ApprovalStatus.APPROVED:
            return PaymentApprovalReadStatus.APPROVED
    phase_by_value: dict[str, PaymentApprovalReadStatus] = {
        "pending_review": PaymentApprovalReadStatus.PENDING_APPROVAL,
        "rejected": PaymentApprovalReadStatus.REJECTED,
        "approved": PaymentApprovalReadStatus.APPROVED,
        "draft": PaymentApprovalReadStatus.PENDING_SUBMIT,
    }
    if approval_phase is None:
        return PaymentApprovalReadStatus.UNCLASSIFIED
    return phase_by_value.get(
        approval_phase,
        PaymentApprovalReadStatus.UNCLASSIFIED,
    )


def payment_approval_status_expression(context: ListQueryContext) -> ColumnElement[str | None]:
    def linked(status: str) -> ColumnElement[bool]:
        return exists().where(and_(
            Approval.id == PaymentRecord.approval_id,
            Approval.team_id == PaymentRecord.team_id,
            Approval.business_type == BusinessType.PAYMENT,
            Approval.business_id == PaymentRecord.id,
            Approval.status == status,
        )).correlate(PaymentRecord)

    return case(
        (linked(ApprovalStatus.PENDING), "pending_approval"),
        (linked(ApprovalStatus.REJECTED), "rejected"),
        (linked(ApprovalStatus.APPROVED), "approved"),
        (PaymentRecord.approval_phase == "pending_review", "pending_approval"),
        (PaymentRecord.approval_phase == "rejected", "rejected"),
        (PaymentRecord.approval_phase == "approved", "approved"),
        (PaymentRecord.approval_phase == "draft", "pending_submit"),
        else_=None,
    )
```
The `context` argument preserves the existing catalog expression-builder contract; authorization belongs to the population query. Linked `CANCELLED`, missing, wrong-ID, wrong-team, wrong-business-type, and wrong-record evidence falls through to the native phase. Confirmation is absent from both resolver and CASE. Keep SQL `NULL` for unclassified; map it to `unclassified` only while constructing board response fields. Existing `approval_status is_empty` already selects this SQL-null branch; do not add another null predicate. Legacy include/exclude helpers compare canonical strings and use `.is_(None)` only when unclassified is explicitly requested; exclusions retain nulls otherwise. Preserve the external tab key `confirmed` and label `已确认`, and map that key to canonical `approved` only at the route/client compatibility boundary.

The resolver must handle `approval_phase is None` explicitly before the phase dictionary lookup, then map only the four supported native phase values; every other native value is `unclassified`. The SQL expression returns SQL `NULL` for unclassified and uses the same predicates and precedence.

- [ ] **Step 1: Write resolver and list-parity regression tests.**

Parameterize linked pending/native draft, linked rejected, linked approved, native pending review, native rejected, native approved, native draft without approval, cancelled approval with native draft, unknown native phase, missing approval evidence, wrong-team approval, non-payment business type, wrong business ID, and confirmed-only fixtures. Assert confirmation changes none of the results. Exercise the actual list catalog and assert IDs for `pending_submit`, `pending_approval`, `rejected`, `approved`, and `unclassified`; a confirmed-but-unapproved record must not match approved.

- [ ] **Step 2: Implement and wire the canonical expression.**

Replace `common.py`'s confirmation-based CASE with the imported helper. Keep `payment_records.py`'s `approval_status` field pointed at that expression builder. Keep SQL `NULL` for unclassified so the existing `is_empty` catalog operation can select it; map null to `unclassified` only in board response construction.

- [ ] **Step 3: Replace both payment CRUD predicate paths.**

Remove confirmation-based approved and pending-submit predicates from `_apply_record_scope` and the legacy list branch. Use canonical approval comparisons for inclusion/exclusion and leave confirmation predicates only under `confirmation_status`. Preserve the current unified-query precedence: explicit legacy `approval_status` is applied by the CRUD scope and removes the same field from unified filters; other legacy fields remain bypassed when unified filters/sorts activate. Preserve the external `confirmed` tab key and label `已确认`; map it to canonical `approved` only at the route/client compatibility boundary.

- [ ] **Step 4: Verify scope isolation.**

Add assertions that a linked approval from another team or a non-payment business type is ignored and the record falls back to native phase classification.

**Future verification (not run during plan preparation):**

```bash
cd CRM-Server && pytest tests/unit/test_payment_approval_status.py tests/unit/test_payment_approval_list_parity.py -q
```

Expected: canonical Python status, SQL filters, legacy tabs, unified filters, exclusions, and team/business-type scoping agree.

---

## Task 3: Define five independent strict backend board contracts

**Files:**
- Create: `CRM-Server/app/schemas/customer_board.py`
- Create: `CRM-Server/app/schemas/opportunity_board.py`
- Create: `CRM-Server/app/schemas/contract_board.py`
- Create: `CRM-Server/app/schemas/payment_plan_board.py`
- Create: `CRM-Server/app/schemas/payment_record_board.py`
- Create: `CRM-Server/tests/unit/test_board_schemas.py`

**Interfaces:**

Every module imports only strict primitives from `board_primitives.py` and declares its own metadata, action state, item, column, trend point, metric union, and response classes. Every class inherits `StrictBoardModel` (`ConfigDict(strict=True, extra="forbid")`). Do not define a shared domain item or a generic metadata bag.

The following declarations are the required contract shape. Keep the field names stable across Pydantic and Zod. `count` and `remaining_count` use the strict nonnegative `Count`; amount fields use `AmountString`; public customer/opportunity IDs are strings; contract, payment-plan, and payment-record IDs are positive integers.

Each independent module below explicitly imports `Self`, `model_validator`, and its strict primitives. Metadata, action state, items, columns, trends, metric unions, responses, and preview validators remain domain-specific; no module imports another domain module.

#### `CRM-Server/app/schemas/customer_board.py`

```python
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.schemas.board_primitives import (
    AmountString, BoardMetricBase, BoardOwner, BoardTone, Count, DateString,
    MonthString, Percentage, StrictBoardModel, validate_preview_counts,
)


class CustomerBoardMetadata(StrictBoardModel):
    stage_hint: str | None = None
    industry: str | None = None
    city: str | None = None
    company_scale: str | None = None
    license_type: Literal["TRIAL", "OFFICIAL"] | None = None
    license_expiry_date: DateString | None = None


class CustomerBoardActionState(StrictBoardModel):
    can_edit: bool
    can_delete: bool
    can_assign: bool
    can_create_opportunity: bool


class CustomerBoardItem(StrictBoardModel):
    id: str
    title: str
    subtitle: str | None
    amount: AmountString | None
    date: DateString | None
    owner: BoardOwner | None
    status: Literal["not_started", "following", "repurchasing", "won", "lost"]
    metadata: CustomerBoardMetadata
    action_state: CustomerBoardActionState


class CustomerBoardColumn(StrictBoardModel):
    key: Literal["not_started", "following", "repurchasing", "won", "lost"]
    label: str
    tone: BoardTone
    count: Count
    amount: AmountString | None
    items: list[CustomerBoardItem]
    has_more: bool
    remaining_count: Count

    @model_validator(mode="after")
    def validate_preview(self) -> Self:
        validate_preview_counts(
            count=self.count,
            shown=len(self.items),
            has_more=self.has_more,
            remaining=self.remaining_count,
        )
        return self


class CustomerCountMetric(BoardMetricBase):
    key: Literal[
        "total_count", "following_count", "repurchasing_count",
        "won_count", "recent_new_count",
    ]
    value_type: Literal["count"]
    value: Count
    secondary_value: Count | None = None


class CustomerPercentageMetric(BoardMetricBase):
    key: Literal[
        "not_started_percentage", "following_percentage",
        "repurchasing_percentage", "won_percentage", "lost_percentage",
    ]
    value_type: Literal["percentage"]
    value: Percentage | None
    secondary_value: Percentage | None = None


CustomerBoardMetric = Annotated[
    CustomerCountMetric | CustomerPercentageMetric,
    Field(discriminator="value_type"),
]


class CustomerBoardTrendPoint(StrictBoardModel):
    date: MonthString
    count: Count


class CustomerBoardResponse(StrictBoardModel):
    summary: list[CustomerBoardMetric]
    columns: list[CustomerBoardColumn]
    trends: list[CustomerBoardTrendPoint]
```

#### `CRM-Server/app/schemas/opportunity_board.py`

```python
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.schemas.board_primitives import (
    AmountString, BoardMetricBase, BoardOwner, BoardTone, Count, DateString,
    EntityId, MonthString, Percentage, StrictBoardModel, validate_preview_counts,
)


class OpportunityBoardMetadata(StrictBoardModel):
    customer_name: str | None = None
    purchase_type: str | None = None
    license_type: str | None = None
    expected_closing_date: DateString | None = None
    win_probability: Percentage | None = None
    stage_name: str | None = None
    stage_sort_order: int | None = None
    procurement_method_name: str | None = None
    procurement_method_code: str | None = None
    procurement_stage_template_id: EntityId | None = None
    template_code: str | None = None


class OpportunityBoardActionState(StrictBoardModel):
    can_edit: bool
    can_delete: bool
    can_move_stage: bool
    can_mark_won: bool
    can_mark_lost: bool


class OpportunityBoardItem(StrictBoardModel):
    id: str
    title: str
    subtitle: str | None
    amount: AmountString | None
    date: DateString | None
    owner: BoardOwner | None
    status: Literal["active", "won", "lost", "unset_stage"]
    metadata: OpportunityBoardMetadata
    action_state: OpportunityBoardActionState


class OpportunityBoardColumn(StrictBoardModel):
    key: str
    label: str
    tone: BoardTone
    column_kind: Literal["active_stage", "won", "lost", "unset_stage"]
    stage_name: str | None = None
    template_code: str | None = None
    template_sort_order: int | None = None
    procurement_method_id: EntityId | None = None
    procurement_stage_template_id: EntityId | None = None
    count: Count
    amount: AmountString
    items: list[OpportunityBoardItem]
    has_more: bool
    remaining_count: Count

    @model_validator(mode="after")
    def validate_preview(self) -> Self:
        validate_preview_counts(
            count=self.count,
            shown=len(self.items),
            has_more=self.has_more,
            remaining=self.remaining_count,
        )
        return self


class OpportunityCountMetric(BoardMetricBase):
    key: Literal["total_count", "won_count"]
    value_type: Literal["count"]
    value: Count
    secondary_value: Count | None = None


class OpportunityAmountMetric(BoardMetricBase):
    key: Literal["pipeline_amount", "weighted_amount", "won_amount"]
    value_type: Literal["amount"]
    value: AmountString
    secondary_value: AmountString | None = None


OpportunityBoardMetric = Annotated[
    OpportunityCountMetric | OpportunityAmountMetric,
    Field(discriminator="value_type"),
]


class OpportunityBoardTrendPoint(StrictBoardModel):
    date: MonthString
    count: Count
    amount: AmountString


class OpportunityBoardResponse(StrictBoardModel):
    summary: list[OpportunityBoardMetric]
    columns: list[OpportunityBoardColumn]
    trends: list[OpportunityBoardTrendPoint]
```

The active-stage `key` is a deterministic identity such as `stage:{procurement_method_id}:{procurement_stage_template_id}`; it is not the historical snapshot row ID. The method/template IDs and template code are returned so same-name stages remain distinguishable.

#### `CRM-Server/app/schemas/contract_board.py`

```python
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.schemas.board_primitives import (
    AmountString, BoardMetricBase, BoardOwner, BoardTone, Count, DateString,
    EntityId, MonthString, StrictBoardModel, validate_preview_counts,
)


class ContractBoardMetadata(StrictBoardModel):
    customer_name: str | None = None
    opportunity_name: str | None = None
    license_type: str | None = None
    purchase_type: str | None = None
    signing_date: DateString | None = None
    effective_date: DateString | None = None
    expiry_date: DateString | None = None
    license_expiry_date: DateString | None = None
    authorized_users: Count | None = None


class ContractBoardActionState(StrictBoardModel):
    can_edit: bool
    can_delete: bool
    can_submit_approval: bool
    can_approve: bool
    can_reject: bool


class ContractBoardItem(StrictBoardModel):
    id: EntityId
    title: str
    subtitle: str | None
    amount: AmountString | None
    date: DateString | None
    owner: BoardOwner | None
    status: Literal[
        "DRAFT", "PENDING_REVIEW", "SIGNED", "EFFECTIVE",
        "EXPIRED", "TERMINATED", "UNCLASSIFIED",
    ]
    metadata: ContractBoardMetadata
    action_state: ContractBoardActionState


class ContractBoardColumn(StrictBoardModel):
    key: Literal[
        "DRAFT", "PENDING_REVIEW", "SIGNED", "EFFECTIVE",
        "EXPIRED", "TERMINATED", "UNCLASSIFIED",
    ]
    label: str
    tone: BoardTone
    count: Count
    amount: AmountString
    items: list[ContractBoardItem]
    has_more: bool
    remaining_count: Count

    @model_validator(mode="after")
    def validate_preview(self) -> Self:
        validate_preview_counts(
            count=self.count,
            shown=len(self.items),
            has_more=self.has_more,
            remaining=self.remaining_count,
        )
        return self


class ContractCountMetric(BoardMetricBase):
    key: Literal["total_count", "pending_review_count"]
    value_type: Literal["count"]
    value: Count
    secondary_value: Count | None = None


class ContractAmountMetric(BoardMetricBase):
    key: Literal["total_amount", "signed_effective_amount"]
    value_type: Literal["amount"]
    value: AmountString
    secondary_value: AmountString | None = None


ContractBoardMetric = Annotated[
    ContractCountMetric | ContractAmountMetric,
    Field(discriminator="value_type"),
]


class ContractBoardTrendPoint(StrictBoardModel):
    date: MonthString
    count: Count
    amount: AmountString


class ContractBoardResponse(StrictBoardModel):
    summary: list[ContractBoardMetric]
    columns: list[ContractBoardColumn]
    trends: list[ContractBoardTrendPoint]
```

#### `CRM-Server/app/schemas/payment_plan_board.py`

```python
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.schemas.board_primitives import (
    AmountString, BoardMetricBase, BoardOwner, BoardTone, Count, DateString,
    EntityId, MonthString, StrictBoardModel, validate_preview_counts,
)


class PaymentPlanBoardMetadata(StrictBoardModel):
    customer_name: str | None = None
    contract_name: str | None = None
    opportunity_name: str | None = None
    paid_amount: AmountString
    remaining_amount: AmountString


class PaymentPlanBoardActionState(StrictBoardModel):
    can_edit: bool
    can_delete: bool
    can_view_detail: bool


class PaymentPlanBoardItem(StrictBoardModel):
    id: EntityId
    title: str
    subtitle: str | None
    amount: AmountString
    planned_amount: AmountString
    paid_amount: AmountString
    remaining_amount: AmountString
    date: DateString | None
    owner: BoardOwner | None
    status: Literal["PENDING", "OVERDUE", "PARTIAL", "COMPLETED", "UNCLASSIFIED"]
    metadata: PaymentPlanBoardMetadata
    action_state: PaymentPlanBoardActionState


class PaymentPlanBoardColumn(StrictBoardModel):
    key: Literal["PENDING", "OVERDUE", "PARTIAL", "COMPLETED", "UNCLASSIFIED"]
    label: str
    tone: BoardTone
    count: Count
    amount: AmountString
    planned_amount: AmountString
    paid_amount: AmountString
    remaining_amount: AmountString
    overdue_remaining_amount: AmountString
    items: list[PaymentPlanBoardItem]
    has_more: bool
    remaining_count: Count

    @model_validator(mode="after")
    def validate_preview(self) -> Self:
        validate_preview_counts(
            count=self.count,
            shown=len(self.items),
            has_more=self.has_more,
            remaining=self.remaining_count,
        )
        return self


class PaymentPlanCountMetric(BoardMetricBase):
    key: Literal["overdue_count"]
    value_type: Literal["count"]
    value: Count
    secondary_value: Count | None = None


class PaymentPlanAmountMetric(BoardMetricBase):
    key: Literal[
        "planned_amount", "paid_amount", "remaining_amount",
        "overdue_remaining_amount",
    ]
    value_type: Literal["amount"]
    value: AmountString
    secondary_value: AmountString | None = None


PaymentPlanBoardMetric = Annotated[
    PaymentPlanCountMetric | PaymentPlanAmountMetric,
    Field(discriminator="value_type"),
]


class PaymentPlanBoardTrendPoint(StrictBoardModel):
    date: MonthString
    count: Count
    planned_amount: AmountString
    paid_amount: AmountString
    remaining_amount: AmountString


class PaymentPlanBoardResponse(StrictBoardModel):
    summary: list[PaymentPlanBoardMetric]
    columns: list[PaymentPlanBoardColumn]
    trends: list[PaymentPlanBoardTrendPoint]
```

#### `CRM-Server/app/schemas/payment_record_board.py`

```python
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.schemas.board_primitives import (
    AmountString, BoardMetricBase, BoardOwner, BoardTone, Count, DateString,
    EntityId, MonthString, StrictBoardModel, validate_preview_counts,
)


class PaymentRecordBoardMetadata(StrictBoardModel):
    customer_name: str | None = None
    contract_name: str | None = None
    actual_payer_name: str | None = None
    creator_name: str | None = None
    owner_name: str | None = None
    commission_member_name: str | None = None
    approval_phase: str | None = None
    approval_id: EntityId | None = None
    confirmation_status: Literal["PENDING", "CONFIRMED", "DISPUTED"] | None = None


class PaymentRecordBoardActionState(StrictBoardModel):
    can_edit: bool
    can_delete: bool
    can_resubmit: bool


class PaymentRecordBoardItem(StrictBoardModel):
    id: EntityId
    title: str
    subtitle: str | None
    amount: AmountString
    actual_amount: AmountString
    date: DateString | None
    owner: BoardOwner | None
    status: Literal[
        "pending_submit", "pending_approval", "rejected",
        "approved", "unclassified",
    ]
    metadata: PaymentRecordBoardMetadata
    action_state: PaymentRecordBoardActionState


class PaymentRecordBoardColumn(StrictBoardModel):
    key: Literal[
        "pending_submit", "pending_approval", "rejected",
        "approved", "unclassified",
    ]
    label: str
    tone: BoardTone
    count: Count
    amount: AmountString
    actual_amount: AmountString
    confirmed_amount: AmountString
    unconfirmed_amount: AmountString
    items: list[PaymentRecordBoardItem]
    has_more: bool
    remaining_count: Count

    @model_validator(mode="after")
    def validate_preview(self) -> Self:
        validate_preview_counts(
            count=self.count,
            shown=len(self.items),
            has_more=self.has_more,
            remaining=self.remaining_count,
        )
        return self


class PaymentRecordCountMetric(BoardMetricBase):
    key: Literal["total_count", "rejected_count"]
    value_type: Literal["count"]
    value: Count
    secondary_value: Count | None = None


class PaymentRecordAmountMetric(BoardMetricBase):
    key: Literal["actual_total", "confirmed_amount", "unconfirmed_amount"]
    value_type: Literal["amount"]
    value: AmountString
    secondary_value: AmountString | None = None


PaymentRecordBoardMetric = Annotated[
    PaymentRecordCountMetric | PaymentRecordAmountMetric,
    Field(discriminator="value_type"),
]


class PaymentRecordBoardTrendPoint(StrictBoardModel):
    date: MonthString
    count: Count
    actual_amount: AmountString
    confirmed_amount: AmountString
    unconfirmed_amount: AmountString


class PaymentRecordBoardResponse(StrictBoardModel):
    summary: list[PaymentRecordBoardMetric]
    columns: list[PaymentRecordBoardColumn]
    trends: list[PaymentRecordBoardTrendPoint]
```

All five column validators enforce `shown == min(count, 5)`, `remaining_count == count - shown`, and `has_more == (remaining_count > 0)`. Services must construct empty ordered columns as well as populated columns, and must not omit `UNCLASSIFIED` or `unset_stage`. Schema tests build each response independently, reject boolean/fractional/negative counts, invalid fixed-point values, nonfinite or out-of-range percentages, unknown fields, cross-domain metadata, invalid status keys, and secondary-label/value mismatches. Six matching source rows with five preview rows must produce `has_more=True` and `remaining_count=1`; exactly five rows must produce `has_more=False` and `remaining_count=0`.

- [ ] **Step 1: Add strict schema tests.**

Build one valid empty response and one valid populated response for each module; validate all domain-specific fields and every fixed column. Assert the preview invariants above and the `secondary_label` coupling. Reject booleans/fractions/negative counts, invalid fixed-point strings, non-finite/out-of-range percentages, unknown fields, wrong status keys, metadata from another domain, and mismatched secondary labels. `None` is valid only for an undefined percentage metric value or another explicitly nullable metric value; it is not valid for required metadata, action, column, or non-null secondary fields.

**Future verification (not run during plan preparation):**

```bash
cd CRM-Server && pytest tests/unit/test_board_schemas.py -q
```

Expected: all five independent strict contracts validate complete known payloads and reject malformed numeric, metadata, state, preview, and extra-field payloads.

---

## Task 4: Add non-paginated population builders with list parity

**Files:**
- Modify: `CRM-Server/app/crud/customer.py`
- Modify: `CRM-Server/app/crud/opportunity.py`
- Modify: `CRM-Server/app/crud/contract.py`
- Modify: `CRM-Server/app/crud/payment.py`
- Create: `CRM-Server/tests/unit/test_board_population_query_parity.py`

**Interfaces:**
- Each CRUD exposes a keyword-only `build_population_query` returning a concrete `Query[Model]` with team scope, filtering, and deterministic ordering but no offset/limit. Import `Query` and `Session` from `sqlalchemy.orm`; do not use a bare `Query` return annotation.
- Board routes retain every existing non-pagination query parameter, including `me: bool = Query(False)` on both payment routes. The route resolves `me` to the authenticated user; population builders receive only server-resolved `current_user_id` and never trust a client identity.
- Existing list methods call the population builder and then apply their existing pagination and response projection. Export methods retain their current branch semantics.

- [ ] **Step 1: Add the customer population builder.**

```python
def build_population_query(
    self,
    db: Session,
    *,
    team_id: int,
    status: str | None = None,
    status_exclude: str | None = None,
    industry: str | None = None,
    industry_exclude: str | None = None,
    city: str | None = None,
    source_ids: Sequence[int] | None = None,
    source_ids_exclude: Sequence[int] | None = None,
    company_scale: str | None = None,
    company_scale_exclude: str | None = None,
    owner_id: str | None = None,
    owner_id_exclude: str | None = None,
    keyword: str | None = None,
    search: str | None = None,
    created_time_start: date | None = None,
    created_time_end: date | None = None,
    order_by: str | None = None,
    order_dir: str | None = None,
    scope: str | None = None,
    current_user_id: str | None = None,
    include_collaborated: bool = False,
    filters: list[FilterCondition] | None = None,
    sorts: list[SortCondition] | None = None,
    chart_question: str | None = None,
    chart_bucket: str | None = None,
) -> Query[Customer]:
    query = db.query(Customer).options(
        selectinload(Customer.product_links).selectinload(CustomerProduct.product)
    ).filter(Customer.team_id == team_id)
    current_user_id = str(current_user_id) if current_user_id is not None else None
    if scope == "collaborated" and current_user_id:
        query = query.filter(db.query(CustomerMember.id).filter(
            CustomerMember.team_id == team_id,
            CustomerMember.customer_id == Customer.id,
            CustomerMember.user_id == current_user_id,
            CustomerMember.is_active.is_(True),
        ).exists())
    elif include_collaborated and current_user_id:
        query = query.filter(or_(
            Customer.owner_id == current_user_id,
            db.query(CustomerMember.id).filter(
                CustomerMember.team_id == team_id,
                CustomerMember.customer_id == Customer.id,
                CustomerMember.user_id == current_user_id,
                CustomerMember.is_active.is_(True),
            ).exists(),
        ))

    context = ListQueryContext(db=db, team_id=team_id, current_user_id=current_user_id)
    if uses_unified_list_query(filters=filters, sorts=sorts):
        if owner_id:
            query = query.filter(Customer.owner_id.in_(_split_csv(owner_id)))
        _, ordered = build_optional_list_query(
            query, CUSTOMERS_LIST_QUERY_CATALOG, filters=filters, sorts=sorts,
            context=context, search=search,
        )
    else:
        status_values = _split_int_csv(status)
        if status_values:
            query = query.filter(Customer.status.in_(status_values))
        status_exclude_values = _split_int_csv(status_exclude)
        if status_exclude_values:
            query = query.filter(Customer.status.notin_(status_exclude_values))
        if industry:
            query = query.filter(Customer.industry.in_(_split_csv(industry)))
        if industry_exclude:
            query = query.filter(Customer.industry.notin_(_split_csv(industry_exclude)))
        if city:
            query = query.filter(Customer.city == city)
        if source_ids is not None:
            query = query.filter(Customer.source_id.in_(source_ids))
        if source_ids_exclude is not None:
            query = query.filter(or_(
                Customer.source_id.is_(None), Customer.source_id.notin_(source_ids_exclude),
            ))
        if company_scale:
            query = query.filter(Customer.company_scale.in_(_split_csv(company_scale)))
        if company_scale_exclude:
            query = query.filter(Customer.company_scale.notin_(_split_csv(company_scale_exclude)))
        if owner_id:
            query = query.filter(Customer.owner_id.in_(_split_csv(owner_id)))
        if owner_id_exclude:
            query = query.filter(Customer.owner_id.notin_(_split_csv(owner_id_exclude)))
        if keyword:
            query = query.filter(or_(
                Customer.account_name.like(f"%{keyword}%"),
                Customer.industry.like(f"%{keyword}%"),
                Customer.city.like(f"%{keyword}%"),
                exists().where(
                    CustomerProduct.customer_id == Customer.id,
                    CustomerProduct.team_id == Customer.team_id,
                    Product.id == CustomerProduct.product_id,
                    Product.name.like(f"%{keyword}%"),
                ),
            ))
        query = apply_search(query, CUSTOMERS_LIST_QUERY_CATALOG, search, context=context)
        if created_time_start:
            query = query.filter(Customer.created_time >= datetime.combine(created_time_start, time.min))
        if created_time_end:
            query = query.filter(Customer.created_time <= datetime.combine(created_time_end, time.max))
        allowed = {
            "created_time", "account_name", "status", "industry",
            "source", "city", "company_scale", "owner_id",
        }
        if order_by in allowed and order_dir:
            column = getattr(Customer, order_by)
            query = query.order_by(column.desc() if order_dir.lower() == "desc" else column.asc())
        else:
            query = query.order_by(Customer.created_time.desc())
        ordered = query
    return self._apply_chart_bucket(db, team_id, ordered, chart_question, chart_bucket)
```

Resolve public source IDs in the route and pass internal IDs only. The existing limited `build_list_query` must call this builder with its current arguments and continue omitting the legacy arguments it does not accept today; do not silently add those arguments to the chart caller. `get_multi` calls this builder and then applies only its current `count`, `offset`, and `limit`.

- [ ] **Step 2: Add the opportunity population builder.**

```python
def build_population_query(
    self,
    db: Session,
    *,
    team_id: int,
    status: str | None = None,
    status_exclude: str | None = None,
    stage_id: int | None = None,
    owner_id: str | None = None,
    owner_id_exclude: str | None = None,
    customer_id: int | None = None,
    keyword: str | None = None,
    customer_keyword: str | None = None,
    search: str | None = None,
    license_type: str | None = None,
    license_type_exclude: str | None = None,
    purchase_type: str | None = None,
    purchase_type_exclude: str | None = None,
    stage_name: str | None = None,
    expected_closing_date_start: date | None = None,
    expected_closing_date_end: date | None = None,
    order_by: str | None = None,
    order_dir: str | None = None,
    filters: list[FilterCondition] | None = None,
    sorts: list[SortCondition] | None = None,
) -> Query[Opportunity]:
    query = self._query(db).filter(Opportunity.team_id == team_id)
    context = ListQueryContext(db=db, team_id=team_id, current_user_id=owner_id)
    if uses_unified_list_query(filters=filters, sorts=sorts):
        effective_filters = filters
        status_values = _split_int_csv(status)
        if status_values:
            query = query.filter(Opportunity.status.in_(status_values))
            effective_filters = without_filter_field(filters, "status")
        if owner_id is not None:
            query = query.filter(Opportunity.owner_id.in_(_split_csv(owner_id)))
        if customer_id is not None:
            query = query.filter(Opportunity.customer_id == customer_id)
        _, ordered = build_optional_list_query(
            query, OPPORTUNITIES_LIST_QUERY_CATALOG, filters=effective_filters,
            sorts=sorts, context=context, search=search,
        )
        return ordered.order_by(Opportunity.id.asc())

    status_values = _split_int_csv(status)
    if status_values:
        query = query.filter(Opportunity.status.in_(status_values))
    status_exclude_values = _split_int_csv(status_exclude)
    if status_exclude_values:
        query = query.filter(Opportunity.status.notin_(status_exclude_values))
    if stage_id is not None:
        query = query.filter(Opportunity.procurement_stage_id == stage_id)
    if owner_id is not None:
        query = query.filter(Opportunity.owner_id.in_(_split_csv(owner_id)))
    if owner_id_exclude:
        query = query.filter(Opportunity.owner_id.notin_(_split_csv(owner_id_exclude)))
    if customer_id is not None:
        query = query.filter(Opportunity.customer_id == customer_id)
    if keyword:
        query = query.filter(Opportunity.opportunity_name.like(f"%{keyword}%"))
    if customer_keyword:
        query = query.filter(Opportunity.customer.has(Customer.account_name.like(f"%{customer_keyword}%")))
    query = apply_search(query, OPPORTUNITIES_LIST_QUERY_CATALOG, search, context=context)
    if license_type:
        query = query.filter(Opportunity.license_type.in_(_split_csv(license_type)))
    if license_type_exclude:
        query = query.filter(Opportunity.license_type.notin_(_split_csv(license_type_exclude)))
    if purchase_type:
        query = query.filter(Opportunity.purchase_type.in_(_split_csv(purchase_type)))
    if purchase_type_exclude:
        query = query.filter(Opportunity.purchase_type.notin_(_split_csv(purchase_type_exclude)))
    if stage_name:
        query = query.filter(Opportunity.current_stage_name.like(f"%{stage_name}%"))
    if expected_closing_date_start:
        query = query.filter(Opportunity.expected_closing_date >= expected_closing_date_start)
    if expected_closing_date_end:
        query = query.filter(Opportunity.expected_closing_date <= expected_closing_date_end)
    allowed = {
        "created_time", "opportunity_name", "customer_name", "total_amount",
        "status", "license_type", "purchase_type", "expected_closing_date",
        "stage_name", "owner_id",
    }
    if order_by in allowed and order_dir:
        if order_by == "customer_name":
            query = query.join(Customer, Opportunity.customer_id == Customer.id)
            column = Customer.account_name
        elif order_by == "stage_name":
            column = Opportunity.current_stage_name
        else:
            column = getattr(Opportunity, order_by)
        query = query.order_by(column.desc() if order_dir.lower() == "desc" else column.asc())
    else:
        query = query.order_by(Opportunity.created_time.desc())
    return query
```

The route resolves public customer IDs before calling this builder. Existing `build_list_query` delegates to the unified branch and preserves its current direct-filter behavior; `get_multi` delegates and applies only pagination.

- [ ] **Step 3: Add the contract population builder.**

```python
def build_population_query(
    self,
    db: Session,
    *,
    team_id: int,
    customer_id: int | None = None,
    status: str | None = None,
    status_exclude: str | None = None,
    contract_number: str | None = None,
    license_type: str | None = None,
    license_type_exclude: str | None = None,
    purchase_type: str | None = None,
    purchase_type_exclude: str | None = None,
    subscription_years: int | None = None,
    subscription_years_exclude: int | None = None,
    license_authorized_users: int | None = None,
    license_authorized_users_exclude: int | None = None,
    standard_unit_price: Decimal | None = None,
    standard_unit_price_exclude: Decimal | None = None,
    keyword: str | None = None,
    customer_keyword: str | None = None,
    opportunity_keyword: str | None = None,
    search: str | None = None,
    owner_id: str | None = None,
    owner_id_exclude: str | None = None,
    signing_date_start: date | None = None,
    signing_date_end: date | None = None,
    effective_date_start: date | None = None,
    effective_date_end: date | None = None,
    expiry_date_start: date | None = None,
    expiry_date_end: date | None = None,
    license_expiry_date_start: date | None = None,
    license_expiry_date_end: date | None = None,
    order_by: str | None = None,
    order_dir: str | None = None,
    include_deleted: bool = False,
    filters: list[FilterCondition] | None = None,
    sorts: list[SortCondition] | None = None,
) -> Query[Contract]:
    query = db.query(Contract).filter(Contract.team_id == team_id)
    latest_license_authorized_users = db.query(LicenseApplication.authorized_users).filter(
        LicenseApplication.contract_id == Contract.id,
        LicenseApplication.license_type == "OFFICIAL",
        LicenseApplication.status == "ISSUED",
    ).order_by(
        LicenseApplication.last_modified_time.desc(), LicenseApplication.id.desc(),
    ).limit(1).correlate(Contract).scalar_subquery()
    latest_license_expiry_date = db.query(LicenseApplication.expiry_date).filter(
        LicenseApplication.contract_id == Contract.id,
        LicenseApplication.license_type == "OFFICIAL",
        LicenseApplication.status == "ISSUED",
    ).order_by(
        LicenseApplication.last_modified_time.desc(), LicenseApplication.id.desc(),
    ).limit(1).correlate(Contract).scalar_subquery()
    displayed_authorized_users = func.coalesce(latest_license_authorized_users, Contract.user_count)
    customer_name_sort = db.query(Customer.account_name).filter(
        Customer.id == Contract.customer_id,
    ).limit(1).correlate(Contract).scalar_subquery()
    opportunity_name_sort = db.query(Opportunity.opportunity_name).filter(
        Opportunity.id == Contract.opportunity_id,
    ).limit(1).correlate(Contract).scalar_subquery()
    purchase_type_sort = db.query(Opportunity.purchase_type).filter(
        Opportunity.id == Contract.opportunity_id,
    ).limit(1).correlate(Contract).scalar_subquery()
    if not include_deleted:
        query = query.filter(Contract.deleted_at.is_(None))

    context = ListQueryContext(db=db, team_id=team_id, current_user_id=owner_id)
    if uses_unified_list_query(filters=filters, sorts=sorts):
        effective_filters = filters
        if customer_id:
            query = query.filter(Contract.customer_id == customer_id)
        if status:
            query = query.filter(Contract.status.in_(_split_csv(status)))
            effective_filters = without_filter_field(filters, "status")
        if owner_id:
            query = query.filter(Contract.owner_id.in_(_split_csv(owner_id)))
        _, ordered = build_optional_list_query(
            query, CONTRACTS_LIST_QUERY_CATALOG, filters=effective_filters,
            sorts=sorts, context=context, search=search,
        )
        return ordered

    if customer_id:
        query = query.filter(Contract.customer_id == customer_id)
    if status:
        query = query.filter(Contract.status.in_(_split_csv(status)))
    if status_exclude:
        query = query.filter(Contract.status.notin_(_split_csv(status_exclude)))
    if contract_number:
        query = query.filter(Contract.contract_number.like(f"%{contract_number}%"))
    if license_type:
        query = query.filter(Contract.license_type.in_(_split_csv(license_type)))
    if license_type_exclude:
        query = query.filter(Contract.license_type.notin_(_split_csv(license_type_exclude)))
    if purchase_type:
        query = query.filter(Contract.opportunity.has(Opportunity.purchase_type.in_(_split_csv(purchase_type))))
    if purchase_type_exclude:
        query = query.filter(Contract.opportunity.has(Opportunity.purchase_type.notin_(_split_csv(purchase_type_exclude))))
    if subscription_years is not None:
        query = query.filter(Contract.subscription_years == subscription_years)
    if subscription_years_exclude is not None:
        query = query.filter(Contract.subscription_years != subscription_years_exclude)
    if license_authorized_users is not None:
        query = query.filter(displayed_authorized_users == license_authorized_users)
    if license_authorized_users_exclude is not None:
        query = query.filter(displayed_authorized_users != license_authorized_users_exclude)
    if standard_unit_price is not None:
        query = query.filter(Contract.standard_unit_price == standard_unit_price)
    if standard_unit_price_exclude is not None:
        query = query.filter(Contract.standard_unit_price != standard_unit_price_exclude)
    if keyword:
        query = query.filter(Contract.contract_name.like(f"%{keyword}%"))
    if customer_keyword:
        query = query.filter(Contract.customer.has(Customer.account_name.like(f"%{customer_keyword}%")))
    if opportunity_keyword:
        query = query.filter(Contract.opportunity.has(Opportunity.opportunity_name.like(f"%{opportunity_keyword}%")))
    query = apply_search(query, CONTRACTS_LIST_QUERY_CATALOG, search, context=context)
    if owner_id:
        query = query.filter(Contract.owner_id.in_(_split_csv(owner_id)))
    if owner_id_exclude:
        query = query.filter(Contract.owner_id.notin_(_split_csv(owner_id_exclude)))
    if signing_date_start:
        query = query.filter(Contract.signing_date >= signing_date_start)
    if signing_date_end:
        query = query.filter(Contract.signing_date <= signing_date_end)
    if effective_date_start:
        query = query.filter(Contract.effective_date >= effective_date_start)
    if effective_date_end:
        query = query.filter(Contract.effective_date <= effective_date_end)
    if expiry_date_start:
        query = query.filter(Contract.expiry_date >= expiry_date_start)
    if expiry_date_end:
        query = query.filter(Contract.expiry_date <= expiry_date_end)
    if license_expiry_date_start:
        query = query.filter(latest_license_expiry_date >= license_expiry_date_start)
    if license_expiry_date_end:
        query = query.filter(latest_license_expiry_date <= license_expiry_date_end)
    sort_columns = {
        "contract_number": Contract.contract_number,
        "contract_name": Contract.contract_name,
        "customer_name": customer_name_sort,
        "opportunity_name": opportunity_name_sort,
        "total_amount": Contract.total_amount,
        "license_type": Contract.license_type,
        "purchase_type": purchase_type_sort,
        "subscription_years": Contract.subscription_years,
        "license_authorized_users": displayed_authorized_users,
        "standard_unit_price": Contract.standard_unit_price,
        "license_expiry_date": latest_license_expiry_date,
        "status": Contract.status,
        "signing_date": Contract.signing_date,
        "effective_date": Contract.effective_date,
        "expiry_date": Contract.expiry_date,
        "created_time": Contract.created_time,
    }
    if order_by in sort_columns and order_dir:
        column = sort_columns[order_by]
        query = query.order_by(column.desc() if order_dir.lower() == "desc" else column.asc())
    else:
        query = query.order_by(Contract.created_time.desc())
    return query
```

These latest-license expressions are correlated scalar facts, not population pagination. Keep `include_deleted` internal and absent from the board route. `get_multi` delegates and applies only its existing pagination.

- [ ] **Step 4: Add the payment-plan population builder.**

```python
def build_population_query(
    self,
    db: Session,
    *,
    team_id: int,
    status: str | None = None,
    status_exclude: str | None = None,
    owner_id: str | None = None,
    keyword: str | None = None,
    search: str | None = None,
    due_date_start: date | None = None,
    due_date_end: date | None = None,
    sort: str | None = None,
    order_by: str | None = None,
    order_dir: str | None = None,
    current_user_id: str | None = None,
    filters: list[FilterCondition] | None = None,
    sorts: list[SortCondition] | None = None,
) -> Query[PaymentPlan]:
    from app.models.contract import Contract
    from app.models.customer import Customer
    from app.models.opportunity import Opportunity

    plans_query = self._base_plans_query(db, team_id)
    context = ListQueryContext(db=db, team_id=team_id, current_user_id=current_user_id)
    if uses_unified_list_query(filters=filters, sorts=sorts):
        if status:
            plans_query = plans_query.filter(PaymentPlan.status.in_(_split_csv(status)))
        if current_user_id:
            plans_query = plans_query.filter(Contract.owner_id == current_user_id)
        _, ordered = build_optional_list_query(
            plans_query, PAYMENT_PLANS_LIST_QUERY_CATALOG,
            filters=without_filter_field(filters, "status") if status else filters,
            sorts=sorts, context=context, search=search,
        )
        return ordered.order_by(PaymentPlan.id.asc())

    if status:
        plans_query = plans_query.filter(PaymentPlan.status.in_(_split_csv(status)))
    if current_user_id:
        plans_query = plans_query.filter(Contract.owner_id == current_user_id)
    plans_query = apply_search(plans_query, PAYMENT_PLANS_LIST_QUERY_CATALOG, search, context=context)
    if status_exclude:
        plans_query = plans_query.filter(PaymentPlan.status.notin_(_split_csv(status_exclude)))
    if due_date_start:
        plans_query = plans_query.filter(PaymentPlan.due_date >= due_date_start)
    if due_date_end:
        plans_query = plans_query.filter(PaymentPlan.due_date <= due_date_end)
    if owner_id:
        plans_query = plans_query.filter(Contract.owner_id.in_(_split_csv(owner_id)))
    if keyword and keyword.strip():
        like_keyword = f"%{keyword.strip()}%"
        plans_query = plans_query.filter(or_(
            PaymentPlan.stage_name.ilike(like_keyword),
            Contract.contract_name.ilike(like_keyword),
            Customer.account_name.ilike(like_keyword),
            Opportunity.opportunity_name.ilike(like_keyword),
        ))
    status_order = case(
        (PaymentPlan.status == PaymentPlanStatus.PENDING, 0),
        (PaymentPlan.status == PaymentPlanStatus.PARTIAL, 1),
        (PaymentPlan.status == PaymentPlanStatus.COMPLETED, 2),
        (PaymentPlan.status == PaymentPlanStatus.OVERDUE, 3),
        else_=99,
    )
    allowed = {
        "plan_number": PaymentPlan.plan_number,
        "stage_name": PaymentPlan.stage_name,
        "customer_name": Customer.account_name,
        "contract_name": Contract.contract_name,
        "planned_amount": PaymentPlan.planned_amount,
        "due_date": PaymentPlan.due_date,
        "status": status_order,
        "created_time": PaymentPlan.created_time,
    }
    clauses = []
    used: set[str] = set()
    for field, direction in _parse_sort(sort, order_by, order_dir):
        if field in used or field not in allowed:
            continue
        column = allowed[field]
        clauses.append(column.desc() if direction == "desc" else column.asc())
        used.add(field)
    if clauses:
        return plans_query.order_by(*clauses, PaymentPlan.id.desc())
    return plans_query.order_by(PaymentPlan.due_date.asc(), PaymentPlan.id.desc())
```

The route derives `current_user_id` from `me` and permissions. Existing `build_list_query` and `list_plans` delegate without changing unified/legacy precedence or pagination.

- [ ] **Step 5: Add the payment-record population builder.**

```python
def build_population_query(
    self,
    db: Session,
    *,
    team_id: int,
    contract_id: int | None = None,
    payment_plan_id: int | None = None,
    payment_date_start: date | None = None,
    payment_date_end: date | None = None,
    min_amount: float | None = None,
    actual_amount: float | None = None,
    creator_id: str | None = None,
    keyword: str | None = None,
    search: str | None = None,
    record_number: str | None = None,
    record_number_exclude: str | None = None,
    customer_name: str | None = None,
    customer_name_exclude: str | None = None,
    actual_payer_name: str | None = None,
    actual_payer_name_exclude: str | None = None,
    invoice_title_text: str | None = None,
    invoice_title_text_exclude: str | None = None,
    contract_name: str | None = None,
    contract_name_exclude: str | None = None,
    owner_name: str | None = None,
    owner_name_exclude: str | None = None,
    commission_member_name: str | None = None,
    commission_member_name_exclude: str | None = None,
    confirmation_status: str | None = None,
    confirmation_status_exclude: str | None = None,
    created_time_start: date | None = None,
    created_time_end: date | None = None,
    current_user_id: str | None = None,
    approval_status: str | None = None,
    approval_status_exclude: str | None = None,
    sort: str | None = None,
    order_by: str | None = None,
    order_dir: str | None = None,
    filters: list[FilterCondition] | None = None,
    sorts: list[SortCondition] | None = None,
) -> Query[PaymentRecord]:
    from app.models.contract import Contract
    from app.models.customer import Customer
    from app.models.opportunity import Opportunity
    from app.models.invoice import InvoiceApplication
    from app.models.user import User

    records_query = self._base_records_query(db, team_id)
    context = ListQueryContext(db=db, team_id=team_id, current_user_id=current_user_id)
    if uses_unified_list_query(filters=filters, sorts=sorts):
        records_query = self._apply_record_scope(
            records_query, approval_status=approval_status, current_user_id=current_user_id,
        )
        _, ordered = build_optional_list_query(
            records_query, PAYMENT_RECORDS_LIST_QUERY_CATALOG,
            filters=without_filter_field(filters, "approval_status") if approval_status else filters,
            sorts=sorts, context=context, search=search,
        )
        return ordered.order_by(PaymentRecord.id.asc())

    owner_id_expr = func.coalesce(Opportunity.owner_id, Contract.owner_id)
    has_invoice_table = inspect(db.bind).has_table(InvoiceApplication.__tablename__) if db.bind else True
    latest_invoice_title_expr = None
    if has_invoice_table:
        explicit_link = InvoiceApplication.payment_record_id == PaymentRecord.id
        latest_invoice_title_expr = db.query(InvoiceApplication.invoice_title_text).filter(
            InvoiceApplication.team_id == team_id,
            or_(
                explicit_link,
                and_(
                    InvoiceApplication.payment_record_id.is_(None),
                    InvoiceApplication.payment_plan_id == PaymentRecord.payment_plan_id,
                ),
            ),
        ).order_by(
            case((explicit_link, 0), else_=1),
            InvoiceApplication.created_time.desc(),
            InvoiceApplication.id.desc(),
        ).limit(1).correlate(PaymentRecord).scalar_subquery()
    owner_name_expr = db.query(User.name).filter(
        User.id == cast(owner_id_expr, Integer),
    ).limit(1).correlate(Contract, Opportunity).scalar_subquery()

    approval_expression = payment_approval_status_expression(context)
    approval_values = _split_csv(approval_status)
    if approval_values:
        predicates = []
        for value in approval_values:
            predicates.append(approval_expression.is_(None) if value == "unclassified" else approval_expression == value)
        records_query = records_query.filter(or_(*predicates))
    if current_user_id:
        records_query = records_query.filter(Contract.creator_id == current_user_id)
    records_query = apply_search(records_query, PAYMENT_RECORDS_LIST_QUERY_CATALOG, search, context=context)
    excluded_values = _split_csv(approval_status_exclude)
    if excluded_values:
        excluded = []
        for value in excluded_values:
            excluded.append(approval_expression.is_(None) if value == "unclassified" else approval_expression == value)
        records_query = records_query.filter(~or_(*excluded))
    if contract_id:
        records_query = records_query.filter(PaymentPlan.contract_id == contract_id)
    if payment_plan_id:
        records_query = records_query.filter(PaymentRecord.payment_plan_id == payment_plan_id)
    if payment_date_start:
        records_query = records_query.filter(PaymentRecord.payment_date >= payment_date_start)
    if payment_date_end:
        records_query = records_query.filter(PaymentRecord.payment_date <= payment_date_end)
    if min_amount:
        records_query = records_query.filter(PaymentRecord.actual_amount >= Decimal(str(min_amount)))
    if actual_amount is not None:
        records_query = records_query.filter(PaymentRecord.actual_amount == Decimal(str(actual_amount)))
    if creator_id:
        records_query = records_query.filter(PaymentRecord.creator_id == creator_id)
    if keyword and keyword.strip():
        like_keyword = f"%{keyword.strip()}%"
        predicates = [
            PaymentRecord.record_number.ilike(like_keyword),
            PaymentPlan.stage_name.ilike(like_keyword),
            Contract.contract_name.ilike(like_keyword),
            Customer.account_name.ilike(like_keyword),
            PaymentRecord.actual_payer_name.ilike(like_keyword),
            owner_name_expr.ilike(like_keyword),
            PaymentRecord.commission_member_name.ilike(like_keyword),
        ]
        if latest_invoice_title_expr is not None:
            predicates.append(latest_invoice_title_expr.ilike(like_keyword))
        records_query = records_query.filter(or_(*predicates))

    def apply_text(query: Query, expression: ColumnElement, include_value: str | None, exclude_value: str | None) -> Query:
        if include_value and include_value.strip():
            query = query.filter(expression.ilike(f"%{include_value.strip()}%"))
        if exclude_value and exclude_value.strip():
            query = query.filter(or_(expression.is_(None), ~expression.ilike(f"%{exclude_value.strip()}%")))
        return query

    records_query = apply_text(records_query, PaymentRecord.record_number, record_number, record_number_exclude)
    records_query = apply_text(records_query, Customer.account_name, customer_name, customer_name_exclude)
    records_query = apply_text(records_query, PaymentRecord.actual_payer_name, actual_payer_name, actual_payer_name_exclude)
    if latest_invoice_title_expr is not None:
        records_query = apply_text(records_query, latest_invoice_title_expr, invoice_title_text, invoice_title_text_exclude)
    records_query = apply_text(records_query, Contract.contract_name, contract_name, contract_name_exclude)
    records_query = apply_text(records_query, owner_name_expr, owner_name, owner_name_exclude)
    records_query = apply_text(records_query, PaymentRecord.commission_member_name, commission_member_name, commission_member_name_exclude)
    confirmation_values = _split_csv(confirmation_status)
    if confirmation_values:
        records_query = records_query.filter(PaymentRecord.confirmation_status.in_(confirmation_values))
    confirmation_excluded = _split_csv(confirmation_status_exclude)
    if confirmation_excluded:
        records_query = records_query.filter(PaymentRecord.confirmation_status.notin_(confirmation_excluded))
    if created_time_start:
        records_query = records_query.filter(PaymentRecord.created_time >= datetime.combine(created_time_start, time.min))
    if created_time_end:
        records_query = records_query.filter(PaymentRecord.created_time <= datetime.combine(created_time_end, time.max))
    confirmation_order = case(
        (PaymentRecord.confirmation_status == PaymentConfirmationStatus.PENDING, 0),
        (PaymentRecord.confirmation_status == PaymentConfirmationStatus.CONFIRMED, 1),
        (PaymentRecord.confirmation_status == PaymentConfirmationStatus.DISPUTED, 2),
        else_=99,
    )
    allowed = {
        "record_number": PaymentRecord.record_number,
        "contract_name": Contract.contract_name,
        "customer_name": Customer.account_name,
        "actual_payer_name": PaymentRecord.actual_payer_name,
        "stage_name": PaymentPlan.stage_name,
        "actual_amount": PaymentRecord.actual_amount,
        "owner_name": owner_name_expr,
        "commission_member_name": PaymentRecord.commission_member_name,
        "payment_date": PaymentRecord.payment_date,
        "confirmation_status": confirmation_order,
        "created_time": PaymentRecord.created_time,
    }
    if latest_invoice_title_expr is not None:
        allowed["invoice_title_text"] = latest_invoice_title_expr
    clauses = []
    used: set[str] = set()
    for field, direction in _parse_sort(sort, order_by, order_dir):
        if field in used or field not in allowed:
            continue
        column = allowed[field]
        clauses.append(column.desc() if direction == "desc" else column.asc())
        used.add(field)
    if clauses:
        return records_query.order_by(*clauses, PaymentRecord.id.desc())
    return records_query.order_by(PaymentRecord.payment_date.desc(), PaymentRecord.id.desc())
```

Replace confirmation-based predicates inside `_apply_record_scope` with the same canonical expression before wiring the unified branch. Preserve truthiness for `min_amount`, exact comparison for non-null `actual_amount`, explicit invoice-record precedence, the invoice-table guard, and the owner expression. The route resolves `me`; explicit `creator_id` remains a filter and is still permission-checked by the route.

- [ ] **Step 6: Refactor list paths and verify parity.**

Have each existing list method call its population builder, then apply only its existing pagination and response projection. Do not add `page`, `page_size`, `skip`, or `limit` to any population builder. Fixture-backed tests must show that all matching rows reach board aggregation, list page-size changes do not change board totals, sort changes only preview order, and existing list/export responses retain their current branch precedence and order.

**Future verification (not run during plan preparation):**

```bash
cd CRM-Server && pytest tests/unit/test_board_population_query_parity.py -q
```

Expected: concrete typed population queries preserve all existing list/export semantics while exposing complete authorized populations for board services.

---
## Task 5: Implement customer board aggregation and route

**Files:**
- Create: `CRM-Server/app/services/customer_board_service.py`
- Modify: `CRM-Server/app/api/customers.py`
- Create: `CRM-Server/tests/unit/test_customer_board_api.py`

**Interfaces:**
- Produces `CustomerBoardResponse` for `GET /v1/customers/board`.
- Uses the same query fields as the customer list except pagination and the `public` tab.

- [ ] **Step 1: Define the customer board route contract.**

```python
@router.get("/board", response_model=CustomerBoardResponse)
def get_customer_board(
    status: str | None = Query(None),
    status_exclude: str | None = Query(None),
    industry: str | None = Query(None),
    industry_exclude: str | None = Query(None),
    city: str | None = Query(None),
    source_public_id: str | None = Query(None),
    source_public_id_exclude: str | None = Query(None),
    company_scale: str | None = Query(None),
    company_scale_exclude: str | None = Query(None),
    owner_id: str | None = Query(None),
    owner_id_exclude: str | None = Query(None),
    keyword: str | None = Query(None),
    search: str | None = Query(None),
    created_time_start: date | None = Query(None),
    created_time_end: date | None = Query(None),
    order_by: str | None = Query(None),
    order_dir: str | None = Query(None),
    scope: str | None = Query(None),
    filters: str | None = Query(None),
    sorts: str | None = Query(None),
    chart_question: str | None = Query(None),
    chart_bucket: str | None = Query(None),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> CustomerBoardResponse:
```

Declare no pagination parameter. Reject `scope == "public"` and every value outside `{None, "collaborated", "accessible"}` with `400` detail `scope 仅支持 collaborated/accessible`. Resolve source public IDs with the existing `resolve_public_ids_to_ids` path. Reuse the list route's permission decision: a non-all owner request without `customer:view:all` raises `403` detail `只能查看自己负责的客户，或需要 customer:view:all 权限查看他人数据`. Register this route before the dynamic public-ID route.

- [ ] **Step 2: Build the complete authorized population.**

```python
rows = customer_crud.build_population_query(
    db, team_id=team_id, status=status, status_exclude=status_exclude,
    industry=industry, industry_exclude=industry_exclude, city=city,
    source_ids=resolved_source_ids, source_ids_exclude=resolved_excluded_source_ids,
    company_scale=company_scale, company_scale_exclude=company_scale_exclude,
    owner_id=owner_id, owner_id_exclude=owner_id_exclude, keyword=keyword,
    search=search, created_time_start=created_time_start,
    created_time_end=created_time_end, order_by=order_by, order_dir=order_dir,
    scope=scope, current_user_id=str(current_user.id),
    include_collaborated=authorized_include_collaborated,
    filters=parsed_filters, sorts=parsed_sorts,
    chart_question=chart_question, chart_bucket=chart_bucket,
).all()
derived = derive_customer_statuses_for_list(db, team_id, rows)
```

`derive_customer_statuses_for_list` already calls `load_customer_journey_views`; do not issue a second journey load. Materialize every authorized row before grouping. Exclude `PUBLIC_POOL` from ordinary columns while leaving the public-tab list endpoint unchanged.

- [ ] **Step 3: Aggregate fixed lifecycle columns and summaries.**

```python
keys = ("not_started", "following", "repurchasing", "won", "lost")
labels = {"not_started": "未启动", "following": "跟进中", "repurchasing": "复购中", "won": "已成交", "lost": "已流失"}
buckets = {key: [] for key in keys}
for row in rows:
    key = derived[row.id]
    if key != "public_pool":
        buckets[key].append(row)
```

Always emit all five columns. Summary keys are `total_count`, `following_count`, `repurchasing_count`, `won_count`, and `recent_new_count`; percentage keys are the five lifecycle percentages. Denominator is the non-public authorized population. `finite_percentage` returns `None` for a zero denominator.

- [ ] **Step 4: Build factual customer cards.**

```python
item = CustomerBoardItem(
    id=row.public_id, title=row.account_name, subtitle=stage_hint,
    amount=None, date=row.created_time.date().isoformat() if row.created_time else None,
    owner=owner, status=key,
    metadata=CustomerBoardMetadata(
        stage_hint=stage_hint, industry=row.industry, city=row.city,
        company_scale=row.company_scale, license_type=license_type,
        license_expiry_date=license_expiry,
    ),
    action_state=CustomerBoardActionState(
        can_edit=can_edit, can_delete=can_delete,
        can_assign=can_assign, can_create_opportunity=can_create_opportunity,
    ),
)
```

Use existing customer permission predicates for the four action flags. When no explicit sort is supplied, order by latest `created_time`, then `updated_time`, then public ID. Otherwise preserve the population order and add the public ID as the deterministic tie-breaker. Take the first five items.

- [ ] **Step 5: Build the creation trend.**

```python
window = resolve_board_trend_window(
    today=date.today(),
    start_bound=effective_created_start,
    end_bound=effective_created_end,
)
counts = fill_month_counts(window)
for row in non_public_rows:
    event_day = row.created_time.date() if row.created_time else None
    if event_day is not None and window.event_start <= event_day <= window.event_end:
        counts[month_key(event_day)] += 1
```

Intersect legacy creation bounds only when the legacy branch is active. Extract unified `created_time` bounds with `extract_board_date_bounds` only after catalog validation. Return `trends=[]` for an empty population or empty window. Count points contain no amount.

- [ ] **Step 6: Add customer endpoint tests.**

Cover all five columns, public-pool exclusion, derived repurchasing status, public IDs, license facts, more-than-five totals, empty columns, search, unified filters, legacy filters, sort-only preview changes, date-bounded trends, complete-population totals, invalid scope, and permission isolation. Verify `/v1/customers/board` is selected before a public ID that resembles `board`.

**Future verification (not run during plan preparation):**

```bash
cd CRM-Server && pytest tests/unit/test_customer_board_api.py -q
```

Expected: customer summaries, derived columns, complete trends, previews, public-pool behavior, route ordering, and scope errors match the approved contract.

---

## Task 6: Implement opportunity board aggregation and route

**Files:**
- Create: `CRM-Server/app/services/opportunity_board_service.py`
- Modify: `CRM-Server/app/api/opportunities.py`
- Create: `CRM-Server/tests/unit/test_opportunity_board_api.py`

**Interfaces:**
- Produces `OpportunityBoardResponse` for `GET /v1/opportunities/board`.
- Uses the exact opportunity list filters without pagination.

- [ ] **Step 1: Define the route and permission contract.**

```python
@router.get("/board", response_model=OpportunityBoardResponse)
def get_opportunity_board(
    status: str | None = Query(None),
    status_exclude: str | None = Query(None),
    stage_id: int | None = Query(None),
    owner_id: str | None = Query(None),
    owner_id_exclude: str | None = Query(None),
    customer_public_id: str | None = Query(None, alias="customer_id"),
    keyword: str | None = Query(None),
    customer_keyword: str | None = Query(None),
    search: str | None = Query(None),
    license_type: str | None = Query(None),
    license_type_exclude: str | None = Query(None),
    purchase_type: str | None = Query(None),
    purchase_type_exclude: str | None = Query(None),
    stage_name: str | None = Query(None),
    expected_closing_date_start: date | None = Query(None),
    expected_closing_date_end: date | None = Query(None),
    order_by: str | None = Query(None),
    order_dir: str | None = Query(None),
    filters: str | None = Query(None),
    sorts: str | None = Query(None),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> OpportunityBoardResponse:
```

Resolve `customer_public_id` through `check_customer_view_permission` and pass the internal ID to CRUD. Preserve `403` detail `只能查看自己负责的商机，或需要 opportunity:view:all 权限查看他人数据`. Declare no pagination and register `/board` before the dynamic opportunity route.

- [ ] **Step 2: Join stable current-stage facts.**

```python
snapshot = snapshots_by_id.get(row.current_stage_snapshot_id)
identity = (
    snapshot.procurement_method_id,
    snapshot.procurement_stage_template_id,
) if snapshot and snapshot.procurement_stage_template_id else None
```

Batch-load current snapshots by `current_stage_snapshot_id`. Group active status `0` by `(procurement_method_id, procurement_stage_template_id)`. The column key is `stage:{method_id}:{template_id}`. Use `template_sort_order`, then method ID, then template ID for ordering. Never use the snapshot row ID. Missing snapshot, missing template, or blank stage name goes to `unset_stage`.

- [ ] **Step 3: Apply terminal overrides and fixed column order.**

```python
if row.status == OpportunityStatus.WON:
    key = "won"
elif row.status == OpportunityStatus.LOST:
    key = "lost"
elif identity is None:
    key = "unset_stage"
else:
    key = f"stage:{identity[0]}:{identity[1]}"
```

Return discovered active columns in stable order, then fixed `won`, `lost`, and `unset_stage`. Empty terminal columns remain present. Same-name templates remain separate columns because their method/template identity differs.

- [ ] **Step 4: Aggregate amounts with Decimal.**

```python
total = Decimal(str(row.total_amount or 0))
probability = Decimal(str(row.win_probability or 0))
weighted = total * probability / Decimal("100")
won_amount = Decimal(str(row.actual_amount if row.actual_amount is not None else row.total_amount or 0))
```

Pipeline and weighted sums include only `FOLLOW_UP`. Won sums include only `WON` and use the actual-or-total rule above. Sum unrounded values, then call `money_string`. Return `total_count`, `pipeline_amount`, `weighted_amount`, `won_count`, and `won_amount`.

- [ ] **Step 5: Build cards and trends.**

```python
item = OpportunityBoardItem(
    id=row.public_id, title=row.opportunity_name, subtitle=customer_name,
    amount=money_string(row.total_amount), date=expected_closing,
    owner=owner, status=item_status, metadata=metadata, action_state=actions,
)
```

Metadata carries customer, purchase type, license type, expected closing date, win probability, stage name, sort order, method name/code, template ID, and template code. Default preview order is expected closing date ascending with nulls last, total amount descending, then public ID. Trend uses `created_time`, returns count and amount for every month, and applies created-date bounds only from the active query branch.

- [ ] **Step 6: Add opportunity endpoint tests.**

Cover stable stage ordering after template changes, same-name method/template separation, terminal overrides, unset stages, weighted Decimal arithmetic, exact won fallback, all summary totals, empty columns, more-than-five previews, stage/date/search filters, owner permissions, sort-only preview changes, and route ordering.

**Future verification (not run during plan preparation):**

```bash
cd CRM-Server && pytest tests/unit/test_opportunity_board_api.py -q
```

Expected: active stage grouping, terminal states, weighted and won amounts, trend bounds, permissions, and complete-population totals pass without float approximation.

---

## Task 7: Implement contract board aggregation and route

**Files:**
- Create: `CRM-Server/app/services/contract_board_service.py`
- Modify: `CRM-Server/app/api/contracts.py`
- Create: `CRM-Server/tests/unit/test_contract_board_api.py`

**Interfaces:**
- Produces `ContractBoardResponse` for `GET /v1/contracts/board`.
- Uses the current contract list filters and permission scope without pagination.

- [ ] **Step 1: Define the route contract.**

```python
@router.get("/board", response_model=ContractBoardResponse)
def get_contract_board(
    customer_public_id: str | None = Query(None, alias="customer_id"),
    status: str | None = Query(None),
    status_exclude: str | None = Query(None),
    contract_number: str | None = Query(None),
    license_type: str | None = Query(None),
    license_type_exclude: str | None = Query(None),
    purchase_type: str | None = Query(None),
    purchase_type_exclude: str | None = Query(None),
    subscription_years: int | None = Query(None),
    subscription_years_exclude: int | None = Query(None),
    license_authorized_users: int | None = Query(None),
    license_authorized_users_exclude: int | None = Query(None),
    standard_unit_price: Decimal | None = Query(None),
    standard_unit_price_exclude: Decimal | None = Query(None),
    keyword: str | None = Query(None),
    customer_keyword: str | None = Query(None),
    opportunity_keyword: str | None = Query(None),
    search: str | None = Query(None),
    owner_id: str | None = Query(None),
    owner_id_exclude: str | None = Query(None),
    signing_date_start: date | None = Query(None),
    signing_date_end: date | None = Query(None),
    effective_date_start: date | None = Query(None),
    effective_date_end: date | None = Query(None),
    expiry_date_start: date | None = Query(None),
    expiry_date_end: date | None = Query(None),
    license_expiry_date_start: date | None = Query(None),
    license_expiry_date_end: date | None = Query(None),
    order_by: str | None = Query(None),
    order_dir: str | None = Query(None),
    filters: str | None = Query(None),
    sorts: str | None = Query(None),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ContractBoardResponse:
```

Resolve the public customer ID with the existing contract-list helper. Preserve `403` detail `只能查看自己负责的合同，或需要 contract:view:all 权限查看他人数据`. Do not declare `include_deleted`, pagination, or a client user ID. Register `/board` before `/contracts/{contract_id}`.

- [ ] **Step 2: Build complete population and current license facts.**

```python
rows = contract_crud.build_population_query(
    db, team_id=team_id, customer_id=resolved_customer_id, status=status,
    status_exclude=status_exclude, contract_number=contract_number,
    license_type=license_type, license_type_exclude=license_type_exclude,
    purchase_type=purchase_type, purchase_type_exclude=purchase_type_exclude,
    subscription_years=subscription_years,
    subscription_years_exclude=subscription_years_exclude,
    license_authorized_users=license_authorized_users,
    license_authorized_users_exclude=license_authorized_users_exclude,
    standard_unit_price=standard_unit_price,
    standard_unit_price_exclude=standard_unit_price_exclude,
    keyword=keyword, customer_keyword=customer_keyword,
    opportunity_keyword=opportunity_keyword, search=search,
    owner_id=owner_id, owner_id_exclude=owner_id_exclude,
    signing_date_start=signing_date_start, signing_date_end=signing_date_end,
    effective_date_start=effective_date_start, effective_date_end=effective_date_end,
    expiry_date_start=expiry_date_start, expiry_date_end=expiry_date_end,
    license_expiry_date_start=license_expiry_date_start,
    license_expiry_date_end=license_expiry_date_end,
    order_by=order_by, order_dir=order_dir,
    include_deleted=False, filters=parsed_filters, sorts=parsed_sorts,
).all()
```

Use `latest_official_issued_license(LicenseApplication.authorized_users)` and `latest_official_issued_license(LicenseApplication.expiry_date)` from `catalogs/common.py`. Verify that helper's exact signature before copying it, and keep `last_modified_time.desc(), id.desc()` ordering. Fall back authorized users through `coalesce(..., Contract.user_count)`.

- [ ] **Step 3: Aggregate fixed lifecycle columns.**

```python
keys = ("DRAFT", "PENDING_REVIEW", "SIGNED", "EFFECTIVE", "EXPIRED", "TERMINATED", "UNCLASSIFIED")
key = row.status if row.status in keys[:-1] else "UNCLASSIFIED"
amount = Decimal(str(row.total_amount or 0))
```

Emit every key even when empty. Total amount sums every authorized contract once. Signed/effective amount sums only `SIGNED` and `EFFECTIVE`, once each. Pending-review count includes only `PENDING_REVIEW`.

- [ ] **Step 4: Build cards and signing trends.**

```python
item = ContractBoardItem(
    id=row.id, title=row.contract_name, subtitle=row.contract_number,
    amount=money_string(row.total_amount), date=signing_date,
    owner=owner, status=key, metadata=metadata, action_state=actions,
)
```

Metadata includes customer, opportunity, license/purchase type, signing/effective/expiry dates, latest official license expiry, and authorized users. Action flags reuse existing edit, delete, submit, approve, and reject predicates. Default order is signing date descending, effective date descending, then ID. Trend event date is `signing_date`; bounds come only from the active branch.

- [ ] **Step 5: Add contract endpoint tests.**

Cover all fixed columns, unknown status, empty columns, total and signed/effective amount without duplicate counting, latest-license parity, date bounds, complete-population totals, permission isolation, sort-only preview changes, and dynamic-route ordering.

**Future verification (not run during plan preparation):**

```bash
cd CRM-Server && pytest tests/unit/test_contract_board_api.py -q
```

Expected: contract lifecycle columns, Decimal totals, license facts, trends, permissions, and previews match list semantics.

---

## Task 8: Implement payment-plan board aggregation and route

**Files:**
- Create: `CRM-Server/app/services/payment_plan_board_service.py`
- Modify: `CRM-Server/app/api/payments.py`
- Create: `CRM-Server/tests/unit/test_payment_plan_board_api.py`

**Interfaces:**
- Produces `PaymentPlanBoardResponse` for `GET /v1/payments/payment-plans/board`.
- Applies payment permission and own-scope predicates before all aggregation work.

- [ ] **Step 1: Define route permission and query contract.**

```python
@router.get("/payment-plans/board", response_model=PaymentPlanBoardResponse)
def get_payment_plan_board(
    plan_status: str | None = Query(None, alias="status"),
    status_exclude: str | None = Query(None),
    owner_id: str | None = Query(None),
    keyword: str | None = Query(None),
    search: str | None = Query(None),
    me: bool = Query(False),
    due_date_start: date | None = Query(None),
    due_date_end: date | None = Query(None),
    sort: str | None = Query(None),
    order_by: str | None = Query(None),
    order_dir: str | None = Query(None),
    filters: str | None = Query(None),
    sorts: str | None = Query(None),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> PaymentPlanBoardResponse:
    current_user_id = resolve_payment_scope_user_id(
        db, current_user, team_id, me=me,
        missing_detail="没有查看回款计划的权限",
    )
```

`resolve_payment_scope_user_id` checks permissions before returning. It sets the user ID when `me` is true or the caller has own scope without all scope. It never reads a client-supplied user ID. Register this static route before `/payment-plans/{plan_id}`.

- [ ] **Step 2: Build authorized plans and approved paid-to-date.**

```python
plans = payment_plan_crud.build_population_query(
    db, team_id=team_id, status=plan_status, status_exclude=status_exclude,
    owner_id=owner_id, keyword=keyword, search=search,
    due_date_start=due_date_start, due_date_end=due_date_end,
    sort=sort, order_by=order_by, order_dir=order_dir,
    current_user_id=current_user_id, filters=parsed_filters, sorts=parsed_sorts,
).all()
approved_paid = sum_canonical_approved_amounts(db, team_id, [plan.id for plan in plans])
remaining = Decimal(str(plan.planned_amount)) - approved_paid[plan.id]
```

The grouped query joins records to plans, applies `payment_approval_status_expression`, and sums `actual_amount` only for canonical `approved`. Never call `PaymentPlan.paid_amount` or `PaymentPlan.remaining_amount`. Preserve negative remaining balances.

- [ ] **Step 3: Aggregate fixed payment-plan columns.**

```python
keys = ("PENDING", "OVERDUE", "PARTIAL", "COMPLETED", "UNCLASSIFIED")
labels = {"PENDING": "待登记", "OVERDUE": "已逾期", "PARTIAL": "部分回款", "COMPLETED": "已登记", "UNCLASSIFIED": "未分类"}
```

Use the stored status when it is one of the first four keys; otherwise use `UNCLASSIFIED`. Sum planned, approved-paid, and remaining amounts from the complete population. `overdue_count` counts `OVERDUE`; `overdue_remaining_amount` sums only overdue remaining balances.

- [ ] **Step 4: Build cards and due-month trends.**

```python
item = PaymentPlanBoardItem(
    id=plan.id, title=plan.plan_number, subtitle=plan.stage_name,
    amount=money_string(plan.planned_amount), planned_amount=planned,
    paid_amount=paid, remaining_amount=remaining, date=due_date,
    owner=owner, status=key, metadata=metadata, action_state=actions,
)
```

Default order is due date ascending with nulls last, then ID descending. Trend points use due month and contain count, planned, current approved paid-to-date, and remaining. Label the trend as due-month plan state, not payment-date cash flow.

- [ ] **Step 5: Add payment-plan endpoint tests.**

Cover missing permission, `me=true` with view-all, own-only isolation, another owner's exclusion from totals/trends/counts/previews, all five columns, overdue remaining amount, negative remaining balance, explicit Decimal calculation, no exception-catching property calls, due-month semantics, search/date filters, empty columns, more-than-five totals, sort-only preview changes, and route ordering.

**Future verification (not run during plan preparation):**

```bash
cd CRM-Server && pytest tests/unit/test_payment_plan_board_api.py -q
```

Expected: payment-plan authorization occurs before every aggregate, own-only users cannot see another owner, and all amounts use explicit Decimal calculations.

---

## Task 9: Implement payment-record board aggregation and route

**Files:**
- Create: `CRM-Server/app/services/payment_record_board_service.py`
- Modify: `CRM-Server/app/api/payments.py`
- Create: `CRM-Server/tests/unit/test_payment_record_board_api.py`

**Interfaces:**
- Produces `PaymentRecordBoardResponse` for `GET /v1/payments/payment-records/board`.
- Uses canonical approval status and independent confirmation status.

- [ ] **Step 1: Define route permission and query contract.**

```python
@router.get("/payment-records/board", response_model=PaymentRecordBoardResponse)
def get_payment_record_board(
    contract_id: int | None = Query(None),
    payment_plan_id: int | None = Query(None),
    payment_date_start: date | None = Query(None),
    payment_date_end: date | None = Query(None),
    min_amount: float | None = Query(None, ge=0),
    actual_amount: float | None = Query(None, ge=0),
    creator_id: str | None = Query(None),
    keyword: str | None = Query(None),
    search: str | None = Query(None),
    record_number: str | None = Query(None),
    record_number_exclude: str | None = Query(None),
    customer_name: str | None = Query(None),
    customer_name_exclude: str | None = Query(None),
    actual_payer_name: str | None = Query(None),
    actual_payer_name_exclude: str | None = Query(None),
    invoice_title_text: str | None = Query(None),
    invoice_title_text_exclude: str | None = Query(None),
    contract_name: str | None = Query(None),
    contract_name_exclude: str | None = Query(None),
    owner_name: str | None = Query(None),
    owner_name_exclude: str | None = Query(None),
    commission_member_name: str | None = Query(None),
    commission_member_name_exclude: str | None = Query(None),
    confirmation_status: str | None = Query(None),
    confirmation_status_exclude: str | None = Query(None),
    created_time_start: date | None = Query(None),
    created_time_end: date | None = Query(None),
    me: bool = Query(False),
    approval_status: str | None = Query(None),
    approval_status_exclude: str | None = Query(None),
    sort: str | None = Query(None),
    order_by: str | None = Query(None),
    order_dir: str | None = Query(None),
    filters: str | None = Query(None),
    sorts: str | None = Query(None),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> PaymentRecordBoardResponse:
    current_user_id = resolve_payment_scope_user_id(
        db, current_user, team_id, me=me,
        missing_detail="没有查看回款记录的权限",
    )
```

Accept the existing public float money inputs, then convert with `Decimal(str(value))` before predicates. Own scope uses `Contract.creator_id`. Register this route before `/payment-records/{record_id}`.

- [ ] **Step 2: Build the authorized population and canonical status.**

```python
records = payment_record_crud.build_population_query(
    db, team_id=team_id, contract_id=contract_id, payment_plan_id=payment_plan_id,
    payment_date_start=payment_date_start, payment_date_end=payment_date_end,
    min_amount=min_amount, actual_amount=actual_amount, creator_id=creator_id,
    keyword=keyword, search=search, record_number=record_number,
    record_number_exclude=record_number_exclude, customer_name=customer_name,
    customer_name_exclude=customer_name_exclude, actual_payer_name=actual_payer_name,
    actual_payer_name_exclude=actual_payer_name_exclude,
    invoice_title_text=invoice_title_text,
    invoice_title_text_exclude=invoice_title_text_exclude,
    contract_name=contract_name, contract_name_exclude=contract_name_exclude,
    owner_name=owner_name, owner_name_exclude=owner_name_exclude,
    commission_member_name=commission_member_name,
    commission_member_name_exclude=commission_member_name_exclude,
    confirmation_status=confirmation_status,
    confirmation_status_exclude=confirmation_status_exclude,
    created_time_start=created_time_start, created_time_end=created_time_end,
    current_user_id=current_user_id, approval_status=approval_status,
    approval_status_exclude=approval_status_exclude, sort=sort,
    order_by=order_by, order_dir=order_dir,
    filters=parsed_filters, sorts=parsed_sorts,
).all()
status_key = resolve_payment_approval_status(...).value
```

Map resolver `UNCLASSIFIED` and SQL `NULL` to column `unclassified`. Keep confirmation values `PENDING`, `CONFIRMED`, `DISPUTED`, or null independent of approval. Column order is `pending_submit`, `pending_approval`, `rejected`, `approved`, `unclassified`.

- [ ] **Step 3: Aggregate totals and trends.**

```python
actual = Decimal(str(record.actual_amount or 0))
confirmed = actual if record.confirmation_status == PaymentConfirmationStatus.CONFIRMED else Decimal("0")
unconfirmed = actual_total - confirmed_total
```

Confirmed includes only `CONFIRMED`. Unconfirmed therefore includes pending, disputed, and missing confirmation states. Rejected count uses canonical `rejected`. Trend event date is `payment_date`; each month returns count, actual, confirmed, and unconfirmed amounts.

- [ ] **Step 4: Build cards and list compatibility.**

```python
item = PaymentRecordBoardItem(
    id=record.id, title=record.record_number, subtitle=customer_name,
    amount=money_string(record.actual_amount),
    actual_amount=money_string(record.actual_amount), date=payment_date,
    owner=owner, status=status_key, metadata=metadata, action_state=actions,
)
```

Metadata keeps customer, contract, payer, creator, owner, commission member, native approval phase, approval ID, and confirmation status. The page keeps external tab key `confirmed` and label `已确认`, but sends canonical `approved`. Never cast this item to `PaymentRecordWithDetails`.

- [ ] **Step 5: Add payment-record endpoint tests.**

Cover every canonical column, unclassified status, approval/confirmation independence, confirmed versus unconfirmed amount, own-only creator isolation, team/business-type approval joins, date bounds, search/text filters, more-than-five totals, numeric preview IDs, `confirmed` compatibility, sort-only preview changes, and route ordering.

**Future verification (not run during plan preparation):**

```bash
cd CRM-Server && pytest tests/unit/test_payment_approval_status.py tests/unit/test_payment_record_board_api.py -q
```

Expected: approval and confirmation dimensions remain independent, payment authorization precedes all aggregate work, and record previews open through numeric authoritative IDs.

---

## Task 10: Add route-contract and backend integration coverage

**Files:**
- Create: `CRM-Server/tests/unit/test_board_route_contracts.py`

**Interfaces:**
- Proves the five routes expose complete non-paginated query contracts and distinct strict response models.

- [ ] **Step 1: Test route parameter surfaces.**

Inspect each route callable's explicit parameters and assert the exact non-pagination names from Tasks 5–9, including `me` on both payment routes. Assert `page`, `page_size`, `skip`, and `limit` are absent. Do not assert that FastAPI rejects undeclared query strings.

- [ ] **Step 2: Test response and permission behavior end to end.**

For each route, call a valid query and validate the response through its own Pydantic model. Call with neither view permission and assert the route-specific `403`. Call own-only scope with another user's records and assert those records are absent from summary, trends, counts, and previews.

- [ ] **Step 3: Test pagination independence observably.**

Seed more than five matching rows. Change only the separate list endpoint's page and page size; board totals remain unchanged. Change only sort and assert totals and trends remain unchanged while preview order may change. Repeat one identical query and assert the same structural totals.

**Future verification (not run during plan preparation):**

```bash
cd CRM-Server && pytest tests/unit/test_board_route_contracts.py tests/unit/test_customer_board_api.py tests/unit/test_opportunity_board_api.py tests/unit/test_contract_board_api.py tests/unit/test_payment_plan_board_api.py tests/unit/test_payment_record_board_api.py -q
```

Expected: all five endpoints validate distinct contracts, preserve authorization, and produce pagination-independent totals.

---

## Task 11: Add five strict frontend Zod contracts and API methods

**Files:**
- Create: `CRM-Client/src/schemas/boardPrimitives.ts`
- Create: `CRM-Client/src/schemas/customerBoard.ts`
- Create: `CRM-Client/src/schemas/opportunityBoard.ts`
- Create: `CRM-Client/src/schemas/contractBoard.ts`
- Create: `CRM-Client/src/schemas/paymentPlanBoard.ts`
- Create: `CRM-Client/src/schemas/paymentRecordBoard.ts`
- Modify: `CRM-Client/src/api/customer.ts`
- Modify: `CRM-Client/src/api/opportunity.ts`
- Modify: `CRM-Client/src/api/contract.ts`
- Modify: `CRM-Client/src/api/payment.ts`
- Create: `CRM-Client/src/schemas/__tests__/boardSchemas.test.ts`

**Interfaces:**

```ts
export type CustomerBoardParams = Omit<CustomerQueryParams, 'skip' | 'limit'>
export type OpportunityBoardParams = Omit<OpportunityListParams, 'skip' | 'limit'>
export type ContractBoardParams = Omit<ContractQueryParams, 'skip' | 'limit'>
export type PaymentPlanBoardParams = Omit<PaymentPlanListParams, 'page' | 'page_size'>
export type PaymentRecordBoardParams = Omit<PaymentRecordListParams, 'page' | 'page_size'>

getCustomerBoard(params: CustomerBoardParams): Promise<CustomerBoardResponse>
getOpportunityBoard(params: OpportunityBoardParams): Promise<OpportunityBoardResponse>
getContractBoard(params: ContractBoardParams): Promise<ContractBoardResponse>
getPaymentPlanBoard(params: PaymentPlanBoardParams): Promise<PaymentPlanBoardResponse>
getPaymentRecordBoard(params: PaymentRecordBoardParams): Promise<PaymentRecordBoardResponse>
```

`PaymentPlanBoardParams` and `PaymentRecordBoardParams` retain `me?: boolean`. Customer params retain public source IDs. No board params include `page`, `page_size`, `skip`, or `limit`.

- [ ] **Step 1: Define strict shared primitives.**

Create `boardPrimitives.ts` with:

```ts
export const CountSchema = z.number().int().nonnegative()
export const EntityIdSchema = z.number().int().positive()
export const AmountStringSchema = z.string().regex(/^-?\d+\.\d{2}$/)
export const PercentageSchema = z.number().finite().min(0).max(100)
export const DateStringSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/)
export const MonthStringSchema = z.string().regex(/^\d{4}-\d{2}$/)
export const BoardOwnerSchema = z.object({
  id: z.string(), name: z.string(), avatar_url: z.string().nullable(),
}).strict()
```

Each domain metric schema calls:

```ts
.superRefine((value, context) => {
  if ((value.secondary_value != null) !== (value.secondary_label != null)) {
    context.addIssue({ code: 'custom', message: 'secondary value and label must be present together' })
  }
})
```

Do not export a universal item schema.

- [ ] **Step 2: Define each domain schema independently.**

Each file imports only `boardPrimitives.ts` and declares its own metadata, action, item, column, trend, metric union, and response schemas. Use `.strict()` on every object. Customer and opportunity item IDs are strings; contract, plan, and record IDs use `EntityIdSchema`. Column keys and status literals match Task 3 exactly. Opportunity columns include `column_kind`, method ID, template ID, template code, and sort order. Payment columns and trends include their explicit planned/paid/remaining or actual/confirmed/unconfirmed amount fields. Each column schema refines `items.length === Math.min(count, 5)`, `remaining_count === count - items.length`, and `has_more === remaining_count > 0`.

- [ ] **Step 3: Add typed non-paginated API methods.**

```ts
async getCustomerBoard(params: CustomerBoardParams): Promise<CustomerBoardResponse> {
  const response: unknown = await request.get('/v1/customers/board', { params })
  return CustomerBoardResponseSchema.parse(response)
}
```

Repeat that shape for `/v1/opportunities/board`, `/v1/contracts/board`, `/v1/payments/payment-plans/board`, and `/v1/payments/payment-records/board`. Serialize filters and sorts with the existing helper so absent values become `[]`. Return the inferred parse result without a cast.

- [ ] **Step 4: Add schema tests.**

Build one empty and one populated payload per schema. Assert boolean, fractional, negative, and non-integer counts fail; invalid amount strings fail; `Infinity`, `NaN`, negative, and above-100 percentages fail; unknown fields fail; wrong status keys fail; and a secondary label without its value fails. Assert `null` percentage values pass. Assert both payment parameter types still accept `me` and no board parameter type accepts pagination.

**Future verification (not run during plan preparation):**

```bash
cd CRM-Client && npm run test:unit -- src/schemas/__tests__/boardSchemas.test.ts
```

Expected: all five Zod contracts parse valid payloads and reject malformed numeric, status, metadata, and pagination shapes.

---

## Task 12: Build typed board presentation and snapshot state

**Files:**
- Create: `CRM-Client/src/components/crmwolf/boardTypes.ts`
- Create: `CRM-Client/src/components/crmwolf/BoardView.vue`
- Create: `CRM-Client/src/components/crmwolf/useBoardSnapshot.ts`
- Create: `CRM-Client/src/components/crmwolf/__tests__/BoardView.test.ts`
- Create: `CRM-Client/src/components/crmwolf/__tests__/useBoardSnapshot.test.ts`

**Interfaces:**

```ts
export interface BoardMetricPresentation {
  key: string
  label: string
  value: string
  valueType: 'count' | 'amount' | 'percentage'
  secondaryValue?: string
  secondaryLabel?: string
}

export interface BoardCardPresentation {
  id: string | number
  title: string
  subtitle: string | null
  primaryValue: string | null
  dateLabel: string | null
  ownerLabel: string | null
  statusLabel: string
  metadata: readonly BoardMetadataRow[]
}

export interface BoardMetadataRow {
  key: string
  label: string
  value: string
}

export interface BoardColumnPresentation {
  key: string
  label: string
  tone: 'neutral' | 'info' | 'success' | 'warning' | 'danger' | 'muted'
  countLabel: string
  amountLabel: string | null
  cards: readonly BoardCardPresentation[]
  hasMore: boolean
  remainingCount: number
}

export interface BoardCardActivation {
  id: string | number
  columnKey: string
}

export interface BoardProjection {
  metrics: readonly BoardMetricPresentation[]
  columns: readonly BoardColumnPresentation[]
  trend: BoardTrendPresentation | null
}

export interface BoardTrendPresentation {
  title: string
  description: string
  points: readonly BoardTrendPointPresentation[]
  series: readonly BoardTrendSeriesPresentation[]
}

export interface BoardTrendPointPresentation {
  month: string
  values: Readonly<Record<string, string | number>>
}

export interface BoardTrendSeriesPresentation {
  key: string
  label: string
  color: string
  fillColor?: string
}
```

`Readonly<Record<string, string | number>>` is only an internal chart adapter shape at the existing chart boundary; domain API contracts remain explicit. The adapter must create a fresh typed object with known series keys before passing data to `AreaTrendChart.vue`, whose existing chart prop is intentionally looser.

```ts
export interface BoardQueryScopeKey {
  teamId: number | null
  userId: string | null
  permissionFingerprint: string
}

export interface BoardSnapshotState<TResponse> {
  data: TResponse | null
  successfulQuerySignature: string | null
  currentQuerySignature: string | null
  canDrillThrough: boolean
  scopeKey: BoardQueryScopeKey
  scopeRevision: number
  permissionReady: boolean
  loading: boolean
  refreshing: boolean
  stale: boolean
  error: Error | null
  requestSequence: number
}

export interface UseBoardSnapshotOptions<TQuery, TResponse> {
  fetchBoard: (query: TQuery) => Promise<TResponse>
  getQuerySignature: (query: TQuery) => string
  getScopeKey: () => BoardQueryScopeKey
  getCurrentQuery: () => TQuery
  isPermissionReady: () => boolean
}
```

`canDrillThrough` is true only when `permissionReady`, `data !== null`, `error === null`, and `successfulQuerySignature === currentQuerySignature`.

- [ ] **Step 1: Implement the generic snapshot composable.**

```ts
function clearSnapshot(): void {
  state.scopeRevision += 1
  state.requestSequence += 1
  state.data = null
  state.successfulQuerySignature = null
  state.error = null
  state.stale = false
  state.canDrillThrough = false
}
```

Watch `getScopeKey()` with `{ flush: 'sync' }`. Compare team ID, user ID, and the sorted permission fingerprint; on any difference call `clearSnapshot()` before the next request. Ignore responses whose captured sequence or scope revision is stale. First failure with `data === null` sets blocking `loading/error`; refresh failure preserves data, sets `refreshing=false`, `stale=true`, and inline `error`. `retry()` calls `fetchBoard(getCurrentQuery())`.

- [ ] **Step 2: Implement the shared board shell.**

```vue
<button type="button" :disabled="!canDrillThrough" @click.stop="emit('view-all', column.key)">查看全部</button>
<article tabindex="0" role="button" @click="emit('activate-card', payload)" @keydown.enter.prevent="emit('activate-card', payload)" @keydown.space.prevent="emit('activate-card', payload)">
```

Props are `projection`, `loading`, `refreshing`, `stale`, `error`, `canDrillThrough`, and `empty`. Emits are `activate-card`, `view-all`, and `retry`. Desktop columns scroll inside `.board-columns`; narrow screens render a state `<select>` and only the selected column. Card radius is at most 8px. Skeletons render before the first success; the empty message renders only after a successful empty response. Status text accompanies every tone.

- [ ] **Step 3: Add shell and snapshot tests.**

Test Enter and Space activation, `查看全部` click isolation, disabled stale drill-through, empty-column stability, first-load error, refresh error with preserved data, current-query retry, late-response discard, synchronous scope clearing, contained desktop scrolling, and narrow-screen selection.

**Future verification (not run during plan preparation):**

```bash
cd CRM-Client && npm run test:unit -- src/components/crmwolf/__tests__/BoardView.test.ts src/components/crmwolf/__tests__/useBoardSnapshot.test.ts
```

Expected: shared rendering and request-state transitions satisfy the approved loading, stale, error, empty, accessibility, and race requirements.

---

## Task 13: Update DataTable, preference persistence, and saved-view rollback

**Files:**
- Modify: `CRM-Client/src/components/crmwolf/DataTable.vue`
- Modify: `CRM-Client/src/components/crmwolf/ColumnConfigPopover.vue`
- Modify: `CRM-Client/src/composables/useCustomFilterViews.ts`
- Modify: `CRM-Client/src/api/viewPreference.ts`
- Modify: `CRM-Client/src/components/crmwolf/__tests__/DataTableInteraction.test.ts`
- Modify: `CRM-Client/src/components/crmwolf/__tests__/listPageQueryContract.test.ts`

**Interfaces:**
- Preserve `ViewDisplayMode = 'table' | 'board' | 'chart'`.
- Add `normalizeCustomerDisplayMode(mode: ViewDisplayMode | null | undefined): 'table' | 'board'`.
- Pages pass only `table` or `board` to the new selector.

- [ ] **Step 1: Render the mode selector.**

```vue
<ToggleGroup type="single" :model-value="viewDisplayMode" @update:model-value="emitMode">
  <ToggleGroupItem value="table">列表</ToggleGroupItem>
  <ToggleGroupItem value="board">看板</ToggleGroupItem>
</ToggleGroup>
```

Render it only when `viewDisplayModeEnabled` is true. Reject a `chart` value in this selector and emit only `table` or `board`.

- [ ] **Step 2: Round-trip display mode with stored preferences.**

```ts
return { ...existingConfig, display_mode: activeMode }
```

Store columns while board mode hides list-only controls and pagination. Restoring table mode restores stored columns and page state without clearing filters or sorts.

- [ ] **Step 3: Preserve custom-view snapshots.**

Extend the existing `ViewApplySnapshot` with `activeTab`, `filters`, `sorts`, `columns`, and `displayMode`. `cloneSnapshot` copies all five. Failed apply calls the existing rollback synchronously and exposes the existing retry path.

- [ ] **Step 4: Normalize customer chart preferences only.**

```ts
export function normalizeCustomerDisplayMode(mode: ViewDisplayMode | null | undefined): 'table' | 'board' {
  return mode === 'board' || mode === 'chart' ? 'board' : 'table'
}
```

Call it only from the customer page. Save the normalized `board` value after successful apply. Leave unrelated stored `chart` values unchanged.

- [ ] **Step 5: Add interaction tests.**

Assert labels, emitted values, stored `display_mode`, restored columns and pagination, customer `chart -> board`, unchanged non-customer `chart`, and synchronous rollback of tab, filters, sorts, columns, and mode.

**Future verification (not run during plan preparation):**

```bash
cd CRM-Client && npm run test:unit -- src/components/crmwolf/__tests__/DataTableInteraction.test.ts src/components/crmwolf/__tests__/listPageQueryContract.test.ts
```

Expected: table behavior remains unchanged while mode persistence, customer normalization, and rollback are covered.

---

## Task 14: Implement five domain projection components

**Files:**
- Create: `CRM-Client/src/components/customer/CustomerBoardProjection.vue`
- Create: `CRM-Client/src/components/opportunity/OpportunityBoardProjection.vue`
- Create: `CRM-Client/src/components/contract/ContractBoardProjection.vue`
- Create: `CRM-Client/src/components/payment/PaymentPlanBoardProjection.vue`
- Create: `CRM-Client/src/components/payment/PaymentRecordBoardProjection.vue`
- Create: `CRM-Client/src/components/customer/__tests__/CustomerBoardProjection.test.ts`
- Create: `CRM-Client/src/components/opportunity/__tests__/OpportunityBoardProjection.test.ts`
- Create: `CRM-Client/src/components/contract/__tests__/ContractBoardProjection.test.ts`
- Create: `CRM-Client/src/components/payment/__tests__/PaymentPlanBoardProjection.test.ts`
- Create: `CRM-Client/src/components/payment/__tests__/PaymentRecordBoardProjection.test.ts`

**Interfaces:**

```ts
defineProps<{ response: CustomerBoardResponse }>()
defineEmits<{ 'activate-card': [BoardCardActivation]; 'view-all': [string] }>()
```

Repeat with each domain response type. Each component returns `BoardProjection` through explicit local mapping.

- [ ] **Step 1: Implement customer projection.**

Import `formatLocalDate` and `formatDateRelative` from `@/utils/format`. Map public string IDs, owner name, stage hint, industry, city, company scale, and license expiry. Render `AmountText` only when `amount !== null`. Emit the public ID and column key. `查看全部` payload is the derived-status column key.

- [ ] **Step 2: Implement opportunity projection.**

Import `formatCurrency` and `formatLocalDate`. Format total amount, append `%` to finite win probability, and format expected closing date. Preserve backend column order. Emit the public opportunity ID. Include method/template identity in the view-all payload; do not emit a snapshot row ID.

- [ ] **Step 3: Implement contract projection.**

Format amount with `AmountText`, dates with `formatLocalDate`, and owner/customer/opportunity/license/purchase metadata. Preserve all seven columns, including `UNCLASSIFIED`. Emit numeric contract ID.

- [ ] **Step 4: Implement payment-plan projection.**

Render planned, approved paid-to-date, remaining, and overdue remaining amounts with `AmountText`. Show status text independently. Emit numeric plan ID.

- [ ] **Step 5: Implement payment-record projection.**

Render actual amount with `AmountText`, payment date with `formatLocalDate`, and separate approval and confirmation badges. Emit numeric record ID. Receive canonical `approved`; do not relabel it as the external `confirmed` tab inside this component.

- [ ] **Step 6: Adapt trends explicitly at the chart boundary.**

```ts
function chartAmount(value: string): number {
  if (!/^-?\d+\.\d{2}$/.test(value)) throw new Error('invalid chart amount')
  return Number(value)
}
const point = { month: source.date, count: source.count, amount: chartAmount(source.amount) }
```

Create a fresh object containing only the known series keys for that domain. Pass typed `data`, `series`, and `xKey="month"` to `AreaTrendChart`. Keep transport values fixed-point.

**Future verification (not run during plan preparation):**

```bash
cd CRM-Client && npm run test:unit -- src/components/customer/__tests__/CustomerBoardProjection.test.ts src/components/opportunity/__tests__/OpportunityBoardProjection.test.ts src/components/contract/__tests__/ContractBoardProjection.test.ts src/components/payment/__tests__/PaymentPlanBoardProjection.test.ts src/components/payment/__tests__/PaymentRecordBoardProjection.test.ts
```

Expected: each projection maps its own response, emits the correct ID type, and converts chart values only at the chart boundary.

---

## Task 15: Integrate customer page mode, board query, details, and drill-through

**Files:**
- Modify: `CRM-Client/src/views/Customers.vue`
- Create: `CRM-Client/src/views/__tests__/CustomersBoard.test.ts`

**Interfaces:**
- Customer list behavior remains the existing `DataTable` path.
- Ordinary customer board uses `getCustomerBoard`; public tab remains list-only.

- [ ] **Step 1: Add page display-mode state and query construction.**

```ts
const displayMode = ref<'table' | 'board'>('table')
const boardParams: CustomerBoardParams = { ...listParamsWithoutPagination, scope }
```

Remove only the page-local `customerView = ref<'list' | 'chart'>('list')` state. Build params from search, non-public active tab, legacy fields, serialized filters/sorts, public source IDs, scope, and chart compatibility fields. When `activeTab === 'public'`, do not call `getCustomerBoard`; keep `getPublicCustomers`, claim, and return flows.

- [ ] **Step 2: Wire the snapshot scope key.**

```ts
const scopeKey = computed(() => ({
  teamId: currentTeam.value?.id ?? null,
  userId: userInfo.value?.id ?? null,
  permissionFingerprint: [...permissionCodes].sort().join(','),
}))
```

Include active tab, search, filters, sorts, and every board param in `getQuerySignature`.

- [ ] **Step 3: Integrate the projection and existing detail surface.**

Render `CustomerBoardProjection` in the `replacement` slot and set `contentHidden` in board mode. Card activation sets the existing public-ID detail state and opens `CustomerDetailSheet`. Card actions call the existing edit, delete, assign, and create-opportunity predicates and handlers.

- [ ] **Step 4: Implement customer drill-through.**

```ts
filters.value = [{ field: 'derived_status', op: 'eq', value: columnKey }]
page.value = 1
displayMode.value = 'table'
```

Accept only `not_started`, `following`, `repurchasing`, `won`, and `lost`. Preserve the current search string. Never create a `public_pool` board column.

- [ ] **Step 5: Preserve tab search behavior.**

Keep the existing watcher that clears search only when `activeTab` itself changes. Changing `displayMode` must not enter that watcher.

- [ ] **Step 6: Add customer page tests.**

Cover default table mode, board request without pagination, public-tab switch absence, public list operations, chart normalization, detail opening, exact `derived_status eq`, search preservation, saved views, stale snapshots, and existing list/export/action paths.

**Future verification (not run during plan preparation):**

```bash
cd CRM-Client && npm run test:unit -- src/views/__tests__/CustomersBoard.test.ts
```

Expected: public customers never request or display the ordinary board, and ordinary customer list behavior remains available.

---

## Task 16: Integrate opportunity, contract, and payment-plan pages

**Files:**
- Modify: `CRM-Client/src/views/Opportunities.vue`
- Modify: `CRM-Client/src/views/Contracts.vue`
- Modify: `CRM-Client/src/views/PaymentPlans.vue`
- Create: `CRM-Client/src/views/__tests__/OpportunitiesBoard.test.ts`
- Create: `CRM-Client/src/views/__tests__/ContractsBoard.test.ts`
- Create: `CRM-Client/src/views/__tests__/PaymentPlansBoard.test.ts`

**Interfaces:**
- Each page uses its existing detail state and handlers.
- Each board request omits pagination and preserves `me` where the current page already sends it.

- [ ] **Step 1: Integrate opportunities.**

Use existing `selectedOpportunityId: Ref<string | null>` and `sheetVisible`. Build params from every current non-pagination opportunity field. For `won` and `lost`, `查看全部` applies `status eq`. For one active stage, apply `status eq FOLLOW_UP` plus a stage predicate only when the current catalog can represent that exact method/template identity. If it cannot, disable that column's `查看全部` rather than using ambiguous `stage_name eq`. Disable `unset_stage` drill-through unless the current catalog has an exact empty-stage predicate. Preserve search and set page one.

- [ ] **Step 2: Integrate contracts.**

Use existing `viewingContractId: Ref<number | null>`. Build params from every current non-pagination contract field. Known lifecycle columns use `status eq`. Disable `UNCLASSIFIED` drill-through because the current contract status catalog has no proven `is_empty` predicate. Preserve columns, pagination, exports, and row actions on return to table mode.

- [ ] **Step 3: Integrate payment plans.**

Use existing `selectedPlanId` and `planSheetVisible`. Build `PaymentPlanBoardParams` from every current non-pagination field and preserve `me` when the current page sets it. Known statuses use `status eq`. Disable `UNCLASSIFIED` drill-through unless the current payment-plan catalog proves an exact unknown-status predicate. Preserve search and set page one.

- [ ] **Step 4: Wire snapshots and scope invalidation.**

Use the Task 12 scope key and `canDrillThrough` on each page. Preserve successful data on ordinary refresh failure and clear synchronously on team, user, or permission changes.

- [ ] **Step 5: Add page tests.**

Assert exact enabled filters, disabled ambiguous/unsupported filters, numeric or public detail IDs, preserved `me`, absent pagination, and list restoration for each page.

**Future verification (not run during plan preparation):**

```bash
cd CRM-Client && npm run test:unit -- src/views/__tests__/OpportunitiesBoard.test.ts src/views/__tests__/ContractsBoard.test.ts src/views/__tests__/PaymentPlansBoard.test.ts
```

Expected: three pages render complete columns, use current detail surfaces, preserve search and list behavior, and issue only non-paginated board queries.

---

## Task 17: Integrate payment-record page and authoritative detail opening

**Files:**
- Modify: `CRM-Client/src/views/PaymentRecords.vue`
- Create: `CRM-Client/src/views/__tests__/PaymentRecordsBoard.test.ts`

**Interfaces:**
- Preserve `selectedRecord: Ref<PaymentRecordWithDetails | null>` for list rows.
- Add `selectedBoardRecordId: Ref<number | null>` for board cards.
- Preserve existing sheet events: `update:visible`, `refresh`, `edit`, and `resubmit`.
- Do not modify `PaymentRecordDetailSheet.vue`; its existing `recordId: number | null` prop already accepts the new state.

- [ ] **Step 1: Add board query state.**

```ts
const boardParams: PaymentRecordBoardParams = {
  ...currentNonPaginationParams,
  me: currentNonPaginationParams.me,
  approval_status: activeTab.value === 'confirmed' ? 'approved' : activeTab.value,
}
```

Keep the visible tab key `confirmed` and label `已确认`. Omit only `page`, `page_size`, `skip`, and `limit`.

- [ ] **Step 2: Preserve approval and confirmation semantics in the UI.**

Render canonical approval as the column and confirmation as a separate badge. Call the existing edit, delete, and resubmit predicates. Add no board-specific write.

- [ ] **Step 3: Open authoritative details from board cards.**

```ts
selectedBoardRecordId.value = activation.id
recordSheetVisible.value = true
```

Pass `selectedBoardRecordId` to `PaymentRecordDetailSheet`. Leave list-row activation on `selectedRecord`. Never cast a board item to `PaymentRecordWithDetails`.

- [ ] **Step 4: Implement record drill-through.**

```ts
const filter = columnKey === 'unclassified'
  ? { field: 'approval_status', op: 'is_empty', value: null }
  : { field: 'approval_status', op: 'eq', value: columnKey }
```

Use canonical `approved` for the approved column. Preserve search, set page one, and render the button only when `canDrillThrough` is true.

- [ ] **Step 5: Add page tests.**

Cover approval/confirmation independence, visible `confirmed` mapping, preserved `me`, numeric board detail state, list-row detail state, existing action locks, `approval_status is_empty`, refresh snapshot preservation, stale drill-through disablement, and exports.

**Future verification (not run during plan preparation):**

```bash
cd CRM-Client && npm run test:unit -- src/views/__tests__/PaymentRecordsBoard.test.ts
```

Expected: approval and confirmation remain separate, board-only records open authoritative numeric details, and existing list actions remain unchanged.

---

## Task 18: Run focused regression checks and real interface smoke verification

**Files:**
- Modify only files required by failures in the focused checks; do not expand scope.

**Interfaces:**
- All backend and frontend tasks above are integrated.
- No cleanup work is considered complete until both desktop and narrow-screen smoke checks succeed.

- [ ] **Step 1: Run the backend focused suite.**

**Future verification (not run during plan preparation):**

```bash
cd CRM-Server && pytest tests/unit/test_board_trend_window.py tests/unit/test_board_value_format.py tests/unit/test_board_primitives.py tests/unit/test_payment_approval_status.py tests/unit/test_board_population_query_parity.py tests/unit/test_customer_board_api.py tests/unit/test_opportunity_board_api.py tests/unit/test_contract_board_api.py tests/unit/test_payment_plan_board_api.py tests/unit/test_payment_record_board_api.py tests/unit/test_board_route_contracts.py -v
```

Expected: every focused test passes, with no skipped test hiding a board contract failure.

- [ ] **Step 2: Run the frontend focused suite.**

**Future verification (not run during plan preparation):**

```bash
cd CRM-Client && npm run test:unit -- src/schemas/__tests__/boardSchemas.test.ts src/components/crmwolf/__tests__/BoardView.test.ts src/components/crmwolf/__tests__/useBoardSnapshot.test.ts src/components/crmwolf/__tests__/DataTableInteraction.test.ts src/components/crmwolf/__tests__/listPageQueryContract.test.ts src/components/customer/__tests__/CustomerBoardProjection.test.ts src/components/opportunity/__tests__/OpportunityBoardProjection.test.ts src/components/contract/__tests__/ContractBoardProjection.test.ts src/components/payment/__tests__/PaymentPlanBoardProjection.test.ts src/components/payment/__tests__/PaymentRecordBoardProjection.test.ts src/views/__tests__/CustomersBoard.test.ts src/views/__tests__/OpportunitiesBoard.test.ts src/views/__tests__/ContractsBoard.test.ts src/views/__tests__/PaymentPlansBoard.test.ts src/views/__tests__/PaymentRecordsBoard.test.ts
```

Expected: schemas, shell state, snapshots, preference behavior, projections, and all five pages pass.

- [ ] **Step 3: Run backend quality checks separately.**

**Future verification (not run during plan preparation):**

```bash
cd CRM-Server && pytest tests/unit -v
```

**Future verification (not run during plan preparation):**

```bash
cd CRM-Server && ruff check app/
```

**Future verification (not run during plan preparation):**

```bash
cd CRM-Server && mypy app/
```

Expected: the existing unit suite, Ruff, and mypy complete without new diagnostics in changed files.

- [ ] **Step 4: Run frontend quality checks separately.**

**Future verification (not run during plan preparation):**

```bash
cd CRM-Client && npm run type-check
```

**Future verification (not run during plan preparation):**

```bash
cd CRM-Client && npm run lint
```

**Future verification (not run during plan preparation):**

```bash
cd CRM-Client && npm run lint:design-system
```

**Future verification (not run during plan preparation):**

```bash
cd CRM-Client && npm run lint:style
```

Expected: Vue type check, ESLint, design-system governance, and style lint complete without new diagnostics in changed files.

- [ ] **Step 5: Start the actual frontend for smoke verification.**

**Future verification (not run during plan preparation):**

Start `npm run dev` in `CRM-Client` with the project process supervisor, wait for its ready URL, and open the actual application in Chromium. Use the authenticated application session and existing test data; do not substitute a static component preview.

- [ ] **Step 6: Verify desktop behavior on all five pages.**

**Future verification (not run during plan preparation):**

1. Open customers, opportunities, contracts, payment plans, and payment records at desktop width.
2. Confirm each page defaults to `列表`/`table`, then switch to `看板`/`board`.
3. Confirm initial skeletons for metrics, columns, cards, and trends before the first success.
4. Confirm ordered columns, empty columns, complete totals, at most five cards, `还有 N 条`, amounts, and trends.
5. Apply search, one unified filter, one domain filter, and a sort on each page. Confirm totals change only for population filters and sort changes preview order only.
6. Return to table mode and confirm search, filters, sorting, columns, pagination, exports, row actions, saved views, and details remain usable.
7. Activate a card and confirm the existing detail surface opens with the correct public or numeric ID.
8. Activate enabled `查看全部` controls and confirm page one plus the exact filter. Confirm ambiguous opportunity, contract-unclassified, and plan-unclassified controls are disabled.
9. Force an initial error and confirm blocking retry; force a refresh error and confirm the successful snapshot remains, is marked stale, and retries the current query.
10. Change team, user, and permission scope and confirm the old snapshot disappears synchronously.
11. On customers, open `public` and confirm no ordinary board request, no board switch, and unchanged claim/return behavior.
12. On payment records, confirm `confirmed` remains visible as `已确认`, canonical `approved` is requested, confirmation badges stay independent, and `me` remains server-resolved.

- [ ] **Step 7: Verify narrow-screen and keyboard behavior.**

**Future verification (not run during plan preparation):**

Use a narrow viewport for all five pages. Confirm two-column or single-column metrics, vertical columns, state selection, no page-body horizontal scrolling, visible loading and error states, keyboard focus, Enter/Space card activation, and independent enabled or disabled `查看全部` controls.

- [ ] **Step 8: Perform cleanup only after smoke success.**

Remove obsolete customer chart-primary state, temporary fixtures, dead imports, and compatibility code made unreachable by the final implementation. Preserve `/v1/customers/chart`, unrelated chart consumers, existing list behavior, and all user-owned dirty worktree changes. Do not modify unrelated Business Journey code.

**Future verification (not run during plan preparation):**

```bash
cd CRM-Server && pytest tests/unit/test_customer_board_api.py tests/unit/test_payment_record_board_api.py -q
```

**Future verification (not run during plan preparation):**

```bash
cd CRM-Client && npm run test:unit -- src/views/__tests__/CustomersBoard.test.ts src/views/__tests__/PaymentRecordsBoard.test.ts
```

Expected: cleanup leaves the board contracts and existing list/chart compatibility behavior intact.

---

## Final Acceptance Checklist

- [ ] Five pages expose table and board modes, defaulting to table.
- [ ] Customer legacy chart preferences normalize only to board, while the customer chart API and unrelated chart consumers remain available.
- [ ] Customer public-pool tab remains list-only and public-pool customers do not enter ordinary lifecycle columns.
- [ ] All five board endpoints omit pagination declarations and receive no pagination fields from the frontend.
- [ ] Every board is authorized and filtered before aggregation and uses the complete authorized population.
- [ ] Every response has strict domain-specific Pydantic and Zod contracts, complete ordered columns, full totals, five-card previews, `has_more`, and `remaining_count`.
- [ ] Counts reject booleans and fractions; amounts use Decimal and fixed two-fraction strings; percentages are finite and bounded; undefined ratios are null.
- [ ] Trend windows exactly follow the approved no-bound, both-bound, start-only, end-only, future-start, reversed-range, and zero-month rules.
- [ ] Customer columns use derived status and factual license data.
- [ ] Opportunity columns use stable snapshot stage facts, terminal overrides, unset-stage handling, Decimal weighted amounts, and the explicit actual-or-total won amount rule.
- [ ] Contract columns use fixed lifecycle states, single-count totals, signed/effective sums, and existing latest official license semantics.
- [ ] Payment-plan calculations use explicit approved record sums and Decimal remaining balances, never exception-catching model properties.
- [ ] Payment-record columns use canonical approval status, preserve external `confirmed` compatibility, and show confirmation independently.
- [ ] Payment own-scope rules use contract owner for plans and contract creator for records.
- [ ] Existing detail, approval, confirmation, stage, edit, delete, row action, export, saved-view, and list workflows remain authoritative.
- [ ] Card activation is keyboard accessible; `查看全部` is independent; desktop scroll is contained; narrow screens use state selection.
- [ ] Ordinary refresh failures preserve successful snapshots; query changes disable stale drill-through; team/user/permission changes clear synchronously.
- [ ] Focused tests, project quality checks, desktop smoke checks, and narrow-screen smoke checks pass before cleanup is marked complete.
