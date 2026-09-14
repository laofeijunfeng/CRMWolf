# 业务看板商机日期筛选 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 业务看板筛选增加主商机「创建时间」和「预计成交日期」，与现有「最近动态时间」「负责人」AND 组合，不改卡片展示。

**Architecture:** `GET /v1/business-journey-board/` 保留 `start_date`/`end_date` 作为旅程 `last_event_at` 区间，新增 `created_time_*` 与 `expected_closing_date_*` 作用在主商机上。前端继续用 `ListFilterPopover` + `getDateBounds`，把三个日期字段分别映射到对应参数。看板仍只返回已审批且存在 `OPPORTUNITY_APPROVED` 事件的旅程。

**Tech Stack:** FastAPI, SQLAlchemy, pytest, Vue 3, TypeScript, Vitest, 现有 `ListFilterPopover` / `getDateBounds`。

**Spec:** `docs/superpowers/specs/2026-09-14-business-journey-board-opportunity-date-filters-design.md`

## Global Constraints

- 不改无关脏工作区文件。
- 不筛选 `PaymentPlan.due_date`，不展示卡片日期，不新增排序，不重命名 `start_date`/`end_date`，不把商机日期写进 `period_start`/`period_end`。
- 筛选项文案必须是「商机创建时间」和「预计成交日期」，禁止「预计回款」。
- 多个已启用日期条件互相 AND，再与负责人、权限范围、已审批门槛 AND。
- `created_time_*` 用 `_date_range`（datetime，右开）；`expected_closing_date_*` 用 `Date` 闭区间。
- 每对 start > end 返回 400，文案「开始日期不能晚于结束日期」。
- 前端禁止 `any` / `as any` / `@ts-ignore` / 不必要的非空断言。
- 不把用例塞进 `test_backend_business_scenarios.py`。
- 不为这次改动挂 Vue 页面测试。

---

## 文件结构与职责

- Create: `CRM-Server/tests/unit/api/test_business_journey_board_date_filters.py` — 看板日期筛选 API 契约。
- Modify: `CRM-Server/app/api/business_journey_board.py` — 增加四个 Query 参数并按主商机过滤。
- Create: `CRM-Client/src/utils/businessJourneyBoardFilters.ts` — 筛选字段常量与 params 映射。
- Create: `CRM-Client/src/utils/__tests__/businessJourneyBoardFilters.test.ts` — 钉住字段文案和 params 映射。
- Modify: `CRM-Client/src/api/businessJourneyBoard.ts` — params 增加四字段。
- Modify: `CRM-Client/src/views/BusinessJourneyBoard.vue` — 使用新筛选字段和映射函数。

---

### Task 1: 后端日期筛选 API

**Files:**
- Create: `CRM-Server/tests/unit/api/test_business_journey_board_date_filters.py`
- Modify: `CRM-Server/app/api/business_journey_board.py`

**Interfaces:**
- Consumes: existing board query (`CustomerDealJourney` + approved `Opportunity` + `OPPORTUNITY_APPROVED` event), `_date_range`, `_resolve_scope`.
- Produces: `GET /v1/business-journey-board/` accepts optional `created_time_start`, `created_time_end`, `expected_closing_date_start`, `expected_closing_date_end`. Existing `start_date`/`end_date` still filter `last_event_at`. Response `period_start`/`period_end` still only reflect `start_date`/`end_date`.

- [ ] **Step 1: Write the failing API tests**

Create `CRM-Server/tests/unit/api/test_business_journey_board_date_filters.py` with this content:

```python
"""Business journey board opportunity date filter contract tests."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import business_journey_board as board_api
from app.constants.approval_phase import ApprovalPhase
from app.core import database, deps
from app.core.database import Base
from app.models.contract import Contract
from app.models.customer import Contact, Customer
from app.models.deal_journey import (
    CustomerDealJourney,
    CustomerDealJourneyEvent,
    DealJourneyEventType,
    DealJourneyStatus,
)
from app.models.invoice import InvoiceApplication, InvoiceTitle
from app.models.opportunity import Opportunity
from app.models.payment import PaymentPlan, PaymentRecord
from app.models.user import User, UserStatus


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


@pytest.fixture()
def api_env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        User.__table__,
        Customer.__table__,
        Contact.__table__,
        Opportunity.__table__,
        CustomerDealJourney.__table__,
        CustomerDealJourneyEvent.__table__,
        Contract.__table__,
        PaymentPlan.__table__,
        PaymentRecord.__table__,
        InvoiceTitle.__table__,
        InvoiceApplication.__table__,
    ]
    renamed_indexes = []
    for table in tables:
        for index in table.indexes:
            if index.name:
                renamed_indexes.append((index, index.name))
                index.name = f"{table.name}_{index.name}"
    try:
        Base.metadata.create_all(engine, tables=tables)
    finally:
        for index, original_name in renamed_indexes:
            index.name = original_name

    Session = sessionmaker(bind=engine)
    db = Session()
    current_user = SimpleNamespace(id=1, name="销售张", status="active")
    db.add(User(id=1, email="sales@example.com", name="销售张", status=UserStatus.ACTIVE))
    db.commit()

    monkeypatch.setattr(
        "app.api.business_journey_board.permission_crud.get_user_permissions",
        lambda _db, _user_id, team_id=None: [SimpleNamespace(code="sales_dashboard:view:all")],
    )

    app = FastAPI()
    app.include_router(board_api.router)
    app.dependency_overrides[database.get_db] = lambda: db
    app.dependency_overrides[deps.get_db] = lambda: db
    app.dependency_overrides[board_api.get_db] = lambda: db
    app.dependency_overrides[deps.get_current_user_team] = lambda: 1
    app.dependency_overrides[board_api.get_current_user_team] = lambda: 1
    app.dependency_overrides[deps.get_current_active_user] = lambda: current_user
    app.dependency_overrides[board_api.get_current_active_user] = lambda: current_user

    with TestClient(app) as client:
        yield SimpleNamespace(client=client, db=db)

    db.close()
    engine.dispose()


def _journey_ids(body: dict) -> set[int]:
    return {
        card["journey_id"]
        for column in body["columns"]
        for card in column["cards"]
    }


def seed_board_card(
    env,
    *,
    suffix: str,
    created_time: datetime,
    expected_closing_date: date,
    last_event_at: datetime,
) -> CustomerDealJourney:
    customer = Customer(
        team_id=1,
        account_name=f"客户{suffix}",
        city="上海",
        owner_id="1",
        creator_id="1",
    )
    env.db.add(customer)
    env.db.flush()

    opportunity = Opportunity(
        team_id=1,
        opportunity_number=f"OPP-{suffix}",
        opportunity_name=f"商机{suffix}",
        customer_id=customer.id,
        total_amount=Decimal("10000"),
        user_count=10,
        unit_price=Decimal("1000"),
        license_type="SUBSCRIPTION",
        subscription_years=1,
        purchase_type="NEW",
        expected_closing_date=expected_closing_date,
        owner_id="1",
        creator_id="1",
        approval_phase=ApprovalPhase.APPROVED.value,
        created_time=created_time,
        win_probability=20,
    )
    env.db.add(opportunity)
    env.db.flush()

    journey = CustomerDealJourney(
        team_id=1,
        customer_id=customer.id,
        primary_opportunity_id=opportunity.id,
        name=f"旅程{suffix}",
        status=DealJourneyStatus.ACTIVE,
        started_at=created_time,
        last_event_at=last_event_at,
    )
    env.db.add(journey)
    env.db.flush()

    opportunity.deal_journey_id = journey.id
    env.db.add(
        CustomerDealJourneyEvent(
            team_id=1,
            deal_journey_id=journey.id,
            customer_id=customer.id,
            event_type=DealJourneyEventType.OPPORTUNITY_APPROVED,
            event_time=last_event_at,
            source_type="opportunity",
            source_id=opportunity.id,
            actor_id="1",
            summary="商机审批通过",
        )
    )
    env.db.commit()
    return journey


def seed_three_cards(env):
    march = seed_board_card(
        env,
        suffix="A",
        created_time=datetime(2026, 3, 15, 10, 0, 0),
        expected_closing_date=date(2026, 9, 30),
        last_event_at=datetime(2026, 8, 1, 9, 0, 0),
    )
    april = seed_board_card(
        env,
        suffix="B",
        created_time=datetime(2026, 4, 15, 10, 0, 0),
        expected_closing_date=date(2026, 10, 15),
        last_event_at=datetime(2026, 8, 15, 9, 0, 0),
    )
    march_early_close = seed_board_card(
        env,
        suffix="C",
        created_time=datetime(2026, 3, 20, 10, 0, 0),
        expected_closing_date=date(2026, 9, 10),
        last_event_at=datetime(2026, 7, 1, 9, 0, 0),
    )
    return march, april, march_early_close


def test_created_time_range_includes_only_matching_opportunities(api_env):
    march, april, march_early_close = seed_three_cards(api_env)

    response = api_env.client.get(
        "/v1/business-journey-board/",
        params={"created_time_start": "2026-03-01", "created_time_end": "2026-03-31"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert _journey_ids(body) == {march.id, march_early_close.id}
    assert april.id not in _journey_ids(body)
    assert body["period_start"] is None
    assert body["period_end"] is None


def test_created_time_start_only_is_inclusive_lower_bound(api_env):
    march, april, march_early_close = seed_three_cards(api_env)

    response = api_env.client.get(
        "/v1/business-journey-board/",
        params={"created_time_start": "2026-04-01"},
    )

    assert response.status_code == 200, response.text
    assert _journey_ids(response.json()) == {april.id}
    assert march.id not in _journey_ids(response.json())
    assert march_early_close.id not in _journey_ids(response.json())


def test_expected_closing_date_range_is_inclusive_on_both_ends(api_env):
    march, april, march_early_close = seed_three_cards(api_env)

    response = api_env.client.get(
        "/v1/business-journey-board/",
        params={
            "expected_closing_date_start": "2026-09-10",
            "expected_closing_date_end": "2026-09-30",
        },
    )

    assert response.status_code == 200, response.text
    assert _journey_ids(response.json()) == {march.id, march_early_close.id}
    assert april.id not in _journey_ids(response.json())


def test_created_time_and_expected_closing_date_are_anded(api_env):
    march, april, march_early_close = seed_three_cards(api_env)

    response = api_env.client.get(
        "/v1/business-journey-board/",
        params={
            "created_time_start": "2026-03-01",
            "created_time_end": "2026-03-31",
            "expected_closing_date_start": "2026-09-20",
            "expected_closing_date_end": "2026-09-30",
        },
    )

    assert response.status_code == 200, response.text
    assert _journey_ids(response.json()) == {march.id}
    assert april.id not in _journey_ids(response.json())
    assert march_early_close.id not in _journey_ids(response.json())


def test_opportunity_dates_and_last_event_at_are_anded(api_env):
    march, april, march_early_close = seed_three_cards(api_env)

    response = api_env.client.get(
        "/v1/business-journey-board/",
        params={
            "created_time_start": "2026-03-01",
            "created_time_end": "2026-03-31",
            "start_date": "2026-08-01",
            "end_date": "2026-08-31",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert _journey_ids(body) == {march.id}
    assert april.id not in _journey_ids(body)
    assert march_early_close.id not in _journey_ids(body)
    assert body["period_start"] == "2026-08-01"
    assert body["period_end"] == "2026-08-31"


def test_created_time_start_after_end_returns_400(api_env):
    response = api_env.client.get(
        "/v1/business-journey-board/",
        params={"created_time_start": "2026-04-01", "created_time_end": "2026-03-01"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "开始日期不能晚于结束日期"


def test_expected_closing_date_start_after_end_returns_400(api_env):
    response = api_env.client.get(
        "/v1/business-journey-board/",
        params={
            "expected_closing_date_start": "2026-10-01",
            "expected_closing_date_end": "2026-09-01",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "开始日期不能晚于结束日期"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd CRM-Server && python -m pytest tests/unit/api/test_business_journey_board_date_filters.py -q
```

Expected: FAIL because the four new query params are unknown or ignored, so March-only / start-only / September-only / AND cases still return all three cards (or FastAPI 422). The inverted-range cases currently only validate `start_date`/`end_date`, so `created_time_*` and `expected_closing_date_*` inversions do not return 400. Seven tests fail.

- [ ] **Step 3: Implement the API filters**

In `CRM-Server/app/api/business_journey_board.py`, change `get_business_journey_board` to:

```python
@router.get("/", response_model=BusinessJourneyBoardResponse, summary="业务旅程看板")
def get_business_journey_board(
    start_date: date | None = Query(None, description="最近业务动态开始日期"),
    end_date: date | None = Query(None, description="最近业务动态结束日期"),
    created_time_start: date | None = Query(None, description="主商机创建开始日期"),
    created_time_end: date | None = Query(None, description="主商机创建结束日期"),
    expected_closing_date_start: date | None = Query(None, description="主商机预计成交开始日期"),
    expected_closing_date_end: date | None = Query(None, description="主商机预计成交结束日期"),
    owner_id: str | None = Query(None, description="负责人ID，多个用英文逗号分隔"),
    limit: int = Query(500, ge=1, le=1000, description="最多加载的旅程卡片数"),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    for range_start, range_end in (
        (start_date, end_date),
        (created_time_start, created_time_end),
        (expected_closing_date_start, expected_closing_date_end),
    ):
        if range_start and range_end and range_start > range_end:
            raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
```

Keep the existing approved-opportunity and `OPPORTUNITY_APPROVED` filters. After the current `last_event_at` filters, add:

```python
    created_start, created_end = _date_range(created_time_start, created_time_end)
    if created_start is not None:
        query = query.filter(Opportunity.created_time >= created_start)
    if created_end is not None:
        query = query.filter(Opportunity.created_time < created_end)

    if expected_closing_date_start is not None:
        query = query.filter(Opportunity.expected_closing_date >= expected_closing_date_start)
    if expected_closing_date_end is not None:
        query = query.filter(Opportunity.expected_closing_date <= expected_closing_date_end)
```

Do not change the response builder. `period_start` / `period_end` must still come only from `start_date` / `end_date`.

- [ ] **Step 4: Run the focused backend tests**

Run:

```bash
cd CRM-Server && python -m pytest tests/unit/api/test_business_journey_board_date_filters.py -q
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/tests/unit/api/test_business_journey_board_date_filters.py CRM-Server/app/api/business_journey_board.py
git commit -m "$(cat <<'EOF'
feat(board): filter journeys by opportunity dates

Add created_time and expected_closing_date query bounds to the
business journey board while keeping last_event_at on start_date.
EOF
)"
```

Stage only these two files. Do not include unrelated dirty worktree changes.

---

### Task 2: 前端筛选字段与 params 映射

**Files:**
- Create: `CRM-Client/src/utils/businessJourneyBoardFilters.ts`
- Create: `CRM-Client/src/utils/__tests__/businessJourneyBoardFilters.test.ts`
- Modify: `CRM-Client/src/api/businessJourneyBoard.ts`
- Modify: `CRM-Client/src/views/BusinessJourneyBoard.vue`

**Interfaces:**
- Consumes: `ListFilterCondition`, `getDateBounds`, `getDelimitedFilterValues`, `BusinessJourneyBoardParams`.
- Produces: `BUSINESS_JOURNEY_BOARD_OPPORTUNITY_DATE_FILTER_FIELDS` with labels `商机创建时间` and `预计成交日期`; `buildBusinessJourneyBoardParams(filters)` returns `{ start_date, end_date, created_time_start, created_time_end, expected_closing_date_start, expected_closing_date_end, owner_id, limit }`. Filter popover order is `last_event_at`, `owner_id`, then the two opportunity date fields.

- [ ] **Step 1: Write the failing mapper tests**

Create `CRM-Client/src/utils/__tests__/businessJourneyBoardFilters.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import {
  BUSINESS_JOURNEY_BOARD_OPPORTUNITY_DATE_FILTER_FIELDS,
  buildBusinessJourneyBoardParams
} from '../businessJourneyBoardFilters'

describe('business journey board filter mapping', () => {
  it('exposes opportunity created time and expected closing date fields', () => {
    expect(BUSINESS_JOURNEY_BOARD_OPPORTUNITY_DATE_FILTER_FIELDS).toEqual([
      { key: 'created_time', label: '商机创建时间', type: 'date' },
      { key: 'expected_closing_date', label: '预计成交日期', type: 'date' }
    ])
  })

  it('maps each date field to its own query bounds and ANDs them in params', () => {
    const filters: ListFilterCondition[] = [
      { field: 'last_event_at', op: 'after', value: '2026-08-01' },
      { field: 'last_event_at', op: 'before', value: '2026-08-31' },
      { field: 'created_time', op: 'after', value: '2026-03-01' },
      { field: 'created_time', op: 'before', value: '2026-03-31' },
      { field: 'expected_closing_date', op: 'eq', value: '2026-09-30' },
      { field: 'owner_id', op: 'in', value: ['1', '2'] }
    ]

    expect(buildBusinessJourneyBoardParams(filters)).toEqual({
      start_date: '2026-08-01',
      end_date: '2026-08-31',
      created_time_start: '2026-03-01',
      created_time_end: '2026-03-31',
      expected_closing_date_start: '2026-09-30',
      expected_closing_date_end: '2026-09-30',
      owner_id: '1,2',
      limit: 500
    })
  })

  it('omits unused date pairs instead of sending empty strings', () => {
    expect(buildBusinessJourneyBoardParams([])).toEqual({
      start_date: null,
      end_date: null,
      created_time_start: null,
      created_time_end: null,
      expected_closing_date_start: null,
      expected_closing_date_end: null,
      owner_id: null,
      limit: 500
    })
  })
})
```

- [ ] **Step 2: Run the mapper tests to verify they fail**

Run:

```bash
cd CRM-Client && npm run test:unit -- --run src/utils/__tests__/businessJourneyBoardFilters.test.ts
```

Expected: FAIL because `businessJourneyBoardFilters.ts` does not exist.

- [ ] **Step 3: Implement the mapper and API params**

Create `CRM-Client/src/utils/businessJourneyBoardFilters.ts`:

```ts
import type { ListFilterCondition, ListFilterField } from '@/components/crmwolf/listFilterTypes'
import type { BusinessJourneyBoardParams } from '@/api/businessJourneyBoard'
import { getDateBounds, getDelimitedFilterValues } from '@/utils/listFilters'

export const BUSINESS_JOURNEY_BOARD_OPPORTUNITY_DATE_FILTER_FIELDS: ListFilterField[] = [
  { key: 'created_time', label: '商机创建时间', type: 'date' },
  { key: 'expected_closing_date', label: '预计成交日期', type: 'date' }
]

export function buildBusinessJourneyBoardParams(
  filters: ListFilterCondition[],
  limit = 500
): BusinessJourneyBoardParams {
  const lastEventBounds = getDateBounds(filters, 'last_event_at')
  const createdTimeBounds = getDateBounds(filters, 'created_time')
  const expectedClosingBounds = getDateBounds(filters, 'expected_closing_date')

  return {
    start_date: lastEventBounds.start ?? null,
    end_date: lastEventBounds.end ?? null,
    created_time_start: createdTimeBounds.start ?? null,
    created_time_end: createdTimeBounds.end ?? null,
    expected_closing_date_start: expectedClosingBounds.start ?? null,
    expected_closing_date_end: expectedClosingBounds.end ?? null,
    owner_id: getDelimitedFilterValues(filters, 'owner_id'),
    limit
  }
}
```

In `CRM-Client/src/api/businessJourneyBoard.ts`, extend params:

```ts
export interface BusinessJourneyBoardParams {
  start_date?: string | null
  end_date?: string | null
  created_time_start?: string | null
  created_time_end?: string | null
  expected_closing_date_start?: string | null
  expected_closing_date_end?: string | null
  owner_id?: string | null
  limit?: number
}
```

Do not change `getBoard`; it already forwards `params`.

- [ ] **Step 4: Wire the board view**

In `CRM-Client/src/views/BusinessJourneyBoard.vue`:

Replace the `filterFields` computed body so existing fields stay first and the two opportunity dates are appended:

```ts
import {
  BUSINESS_JOURNEY_BOARD_OPPORTUNITY_DATE_FILTER_FIELDS,
  buildBusinessJourneyBoardParams
} from '@/utils/businessJourneyBoardFilters'
```

```ts
const filterFields = computed<ListFilterField[]>(() => [
  {
    key: 'last_event_at',
    label: '最近动态时间',
    type: 'date'
  },
  {
    key: 'owner_id',
    label: '负责人',
    type: 'enum',
    options: ownerFilterOptions.value
  },
  ...BUSINESS_JOURNEY_BOARD_OPPORTUNITY_DATE_FILTER_FIELDS
])
```

In `loadBoard`, replace the local `getDateBounds` / `owner_id` assembly with:

```ts
    const nextBoard = await businessJourneyBoardApi.getBoard(
      buildBusinessJourneyBoardParams(activeFilters.value)
    )
```

Remove the now-unused `getDateBounds` import if nothing else in the file uses it. Keep `getDelimitedFilterValues` imported only if still used; after this change it should not be.

Do not change the card template, custom-view key, or `period_start` handling.

- [ ] **Step 5: Run the focused frontend tests**

Run:

```bash
cd CRM-Client && npm run test:unit -- --run src/utils/__tests__/businessJourneyBoardFilters.test.ts src/utils/__tests__/listFilters.test.ts
```

Expected: all focused tests pass.

- [ ] **Step 6: Commit**

```bash
git add CRM-Client/src/utils/businessJourneyBoardFilters.ts CRM-Client/src/utils/__tests__/businessJourneyBoardFilters.test.ts CRM-Client/src/api/businessJourneyBoard.ts CRM-Client/src/views/BusinessJourneyBoard.vue
git commit -m "$(cat <<'EOF'
feat(board): map opportunity date filters on journey board

Expose created_time and expected_closing_date in the board filter
popover and send them as dedicated query bounds.
EOF
)"
```

Stage only these four files.

---

### Task 3: 对照 spec 做聚焦验证

**Files:**
- Review: files from Task 1 and Task 2 only.

- [ ] **Step 1: Re-run focused tests**

```bash
cd CRM-Server && python -m pytest tests/unit/api/test_business_journey_board_date_filters.py tests/unit/test_business_journey_board_stages.py -q
cd CRM-Client && npm run test:unit -- --run src/utils/__tests__/businessJourneyBoardFilters.test.ts src/utils/__tests__/listFilters.test.ts
```

Expected: all listed tests pass.

- [ ] **Step 2: Lint/type the touched files**

```bash
cd CRM-Server && ruff check app/api/business_journey_board.py tests/unit/api/test_business_journey_board_date_filters.py
cd CRM-Client && npx vue-tsc --noEmit --pretty false
```

If `vue-tsc` is too broad for local noise, run the project's `npm run type-check` and only treat errors in the four frontend files above as in-scope. Do not “fix” unrelated dirty files.

- [ ] **Step 3: Spec coverage check**

Confirm the diff:

- keeps `start_date`/`end_date` as `last_event_at`
- ANDs the three date dimensions
- uses labels `商机创建时间` and `预计成交日期`, in popover order `最近动态时间` → `负责人` → `商机创建时间` → `预计成交日期`
- does not mention 预计回款 in UI
- does not change card markup
- does not add `due_date` params
- leaves `period_start`/`period_end` bound to last-event dates only
- does not edit `test_backend_business_scenarios.py`

- [ ] **Step 4: Smoke the real query path if a backend venv is available**

If `CRM-Server` tests already passed, that is the behavioral proof for the API. Do not start a full app stack unless already running. Do not add root-level reports.

---
