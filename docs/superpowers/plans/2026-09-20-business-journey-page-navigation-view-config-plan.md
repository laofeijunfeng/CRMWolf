# 业务旅程独立页面、导航与保存视图 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增加统一的业务旅程页面，默认 DataTable、可通过现有视图配置切换到迁移后的看板，保存显示模式到自定义视图，并让表格行 / 看板卡片直接打开复用的业务旅程 Sheet。

**Architecture:** 后端新增团队级 `BusinessJourneyQueryService`，统一客户 / 商机可见范围、搜索、筛选、排序、阶段推断和摘要加载；表格 API 分页返回该查询，现有看板 API 改为同一查询结果的阶段投影。前端 `BusinessJourneys.vue` 管理系统 Tab、自定义视图、`displayMode`、列表 / 看板与 Sheet；现有 `useCustomFilterViews`、DataTable 工具、看板视觉和 `DealJourneyDetailContent` 原样复用。

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, Alembic, pytest, Vue 3, TypeScript, Zod, Pinia, Vitest, vue-test-utils, shadcn-vue.

**Specs:**
- `docs/superpowers/specs/2026-09-20-business-journey-page-navigation-view-config-design.md`
- `docs/superpowers/specs/2026-09-16-customer-detail-business-journey-identity-design.md`

## Global Constraints

- 不改业务旅程、商机、合同、回款、发票、License 的写入接口或审批流程。
- 不新增「新建业务旅程」入口；新建商机继续自动建立旅程。
- 不新增第二套筛选、排序、字段配置、自定义视图、看板 Card、Sheet 内容或响应式组件。
- 复用 `DataTable`、`ListFilterPopover`、`ListSortPopover`、`ColumnConfigPopover`、`ListAdvancedTools`、`TableToolbarButton`、现有看板视觉和 `DealJourneyDetailContent`。
- 当前工作区存在用户未提交改动：
  - `CRM-Client/src/components/crmwolf/ColumnConfigPopover.vue`
  - `CRM-Client/src/components/crmwolf/ListAdvancedTools.vue`
  - `CRM-Client/src/components/crmwolf/ListSortPopover.vue`
  - `CRM-Client/src/components/crmwolf/__tests__/ListAdvancedTools.test.ts`
  - `CRM-Client/src/components/crmwolf/__tests__/overlayPanelChrome.test.ts`
  执行前必须从包含这些改动的最新 `main` 建隔离 worktree；Task 4 只能在其当前接口上增量适配，禁止覆盖、回滚或重写该改造。
- 执行前置：上述五个视图工具文件必须先进入实施分支的基线提交。若执行时仍为未提交状态，必须停止并请用户完成提交，或明确授权携带这份精确 diff；禁止创建一个静默遗漏这些改动的 worktree，也禁止把它们冒充为本业务旅程功能的改动自动提交。
- 不重命名或复制 `ColumnConfigPopover`。业务旅程额外配置通过现有工具的 optional props / slot 接入，其他页面不传则行为不变。
- 表格与看板必须经过同一个 `BusinessJourneyQueryService`；禁止前端当前页分组，禁止两套权限谓词。
- 业务旅程页面不依赖 `sales_dashboard:view:*`。可见范围是客户可见 OR 商机可见：`customer:view:*`、客户成员 VIEW+、`opportunity:view:*`。
- 表格 / 看板相同 scope、系统 Tab、search、filters、sorts 时，旅程集合必须一致（看板可按 limit 截断，但必须返回 `truncated`）。
- 系统 Tab 不落库；自定义视图保存 `display_mode`。旧 config 无该字段时默认 `table`。
- 搜索词不保存。
- 新稳定 view key：`business-journeys.list`。
- clean cutover：删除 `/business-journey-board` 前端路由和菜单，不保留别名 / redirect；后端旧 API 在前端切换后删除，不留双读路径。
- Alembic 新 revision：`136_business_journey_saved_views`，`down_revision = "135_deal_journey_public_ids"`。
- 前端禁止 `any`、`as any`、`@ts-ignore` 和无必要非空断言。
- 中间 Task 只跑定向测试；最终 Task 才跑本计划的完整定向集合、type-check 和真实浏览器 smoke。
- 设计系统改动必须是现有组件的通用可选能力；仅业务旅程传入该能力，其他 DataTable 页面 DOM、文案和行为不变。

## 文件结构与职责

### Backend

- Create: `CRM-Server/app/services/business_journey_query_service.py` — 权限范围、统一查询、分页 / 看板投影输入。
- Create: `CRM-Server/app/services/business_journey_presenter.py` — customer-scoped and team-scoped APIs share response mapping; API modules never import each other.
- Create: `CRM-Server/app/core/list_query/catalogs/business_journeys.py` — 旅程表格筛选 / 排序 / 搜索字段。
- Create: `CRM-Server/app/api/business_journeys.py` — `/v1/business-journeys` 列表 / 看板 / owner-options 读接口。
- Modify: `CRM-Server/app/schemas/deal_journey.py` — 团队级列表行、分页和看板响应 schema。
- Modify: `CRM-Server/app/core/list_query/catalogs/__init__.py` — 注册 `business_journeys` catalog。
- Modify: `CRM-Server/app/main.py` — Task 3 注册新 router；Task 7 移除旧 board router。
- Modify then delete: `CRM-Server/app/api/business_journey_board.py` — Task 3 继续兼容旧入口并改用共享 stage 常量；Task 7 删除。
- Modify: `CRM-Server/app/schemas/view_preference.py` — `display_mode`。
- Create: `CRM-Server/migrations/versions/136_business_journey_saved_views.py` — 旧 view key/config 数据迁移。
- Modify: `CRM-Server/scripts/generate_list_query_manifest.py` output — 重新生成前端 manifest。

### Frontend

- Create: `CRM-Client/src/views/BusinessJourneys.vue` — 统一页面状态与工具栏。
- Create: `CRM-Client/src/components/business-journey/BusinessJourneyListTools.vue` — 看板模式复用现有搜索 / 筛选 / 排序 / 视图配置组件的业务组合，不新增 UI 原语。
- Create: `CRM-Client/src/components/business-journey/BusinessJourneyTableView.vue` — DataTable 组合。
- Create: `CRM-Client/src/components/business-journey/BusinessJourneyBoardView.vue` — 从现有页面抽出的看板主体，不改视觉。
- Create: `CRM-Client/src/views/DealJourneyDetailSheet.vue` — 独立 Sheet 壳。
- Modify: `CRM-Client/src/api/dealJourney.ts` — 团队级列表 / 看板 / owner options。
- Modify: `CRM-Client/src/schemas/dealJourney.ts` — 列表与看板 schema。
- Modify: `CRM-Client/src/api/viewPreference.ts` — `display_mode` 类型与 Zod。
- Modify: `CRM-Client/src/composables/useCustomFilterViews.ts` — 可选 displayMode 快照、保存 / 恢复、通用 saveCurrentView。
- Modify: `CRM-Client/src/components/crmwolf/DataTable.vue` — 向 `ListAdvancedTools` 透传可选页面级视图配置状态；不自己保存业务旅程状态。
- Modify: `CRM-Client/src/components/crmwolf/ListAdvancedTools.vue` — 在当前 Teleport / responsive 改造上增加可选页面级配置 props。
- Modify: `CRM-Client/src/components/crmwolf/ColumnConfigPopover.vue` — 在现有浮层中增加可选页面级视图配置区域与另存动作；其他页面不传则无差异。
- Modify: `CRM-Client/src/components/app-sidebar/AppSidebar.vue` — 新导航分组。
- Modify: `CRM-Client/src/router/index.ts` — `/business-journeys`，删除旧路由。
- Modify: `CRM-Client/src/AppLayout.vue` — 新路由继续 fixed layout。
- Delete: `CRM-Client/src/views/BusinessJourneyBoard.vue` — 主体迁入新组件后删除。
- Delete: `CRM-Client/src/api/businessJourneyBoard.ts`、`CRM-Client/src/schemas/businessJourneyBoard.ts`、`CRM-Client/src/utils/businessJourneyBoardFilters.ts` — 能力合并到 journey API/schema/page 后删除。

---

### Task 1: Extend saved-view config with display mode and migrate legacy board views

**Files:**
- Modify: `CRM-Server/app/schemas/view_preference.py`
- Create: `CRM-Server/migrations/versions/136_business_journey_saved_views.py`
- Modify: `CRM-Server/tests/unit/test_view_preferences_api.py`
- Create: `CRM-Server/tests/unit/test_business_journey_saved_view_migration.py`
- Modify: `CRM-Client/src/api/viewPreference.ts`

**Interfaces:**
- Produces:
  - Backend `ViewPreferenceConfig.display_mode: Literal["table", "board"] | None = None`
  - Frontend `ViewDisplayMode = 'table' | 'board'`
  - Frontend `ViewPreferenceConfig.display_mode?: ViewDisplayMode | null`
  - Migration `136_business_journey_saved_views`, down `135_deal_journey_public_ids`
- Migration rules:
  - rows with `view_key = 'business-journey-board.board'` → `business-journeys.list`
  - parse `config_json` as object, set `display_mode='board'`, preserve all other keys
  - if target owner/preference key already exists, merge only when it is the same source row; otherwise do not create duplicates — update target row by keeping target identity/name/sort fields and only adding `display_mode='board'` if absent, then delete source row
  - repeated upgrade is no-op
  - downgrade changes migrated `business-journeys.list` rows with `display_mode='board'` back to old key only when old key does not exist; remove `display_mode` added by this migration

- [ ] **Step 1: Write failing API config tests**

Add to `test_view_preferences_api.py`:

```python
def test_custom_view_round_trips_business_journey_display_mode(client):
    response = client.post(
        "/v1/view-preferences/business-journeys.list/custom-views",
        json={"config": {"version": 1, "columns": [], "filters": [], "sorts": [], "display_mode": "board"}},
    )
    assert response.status_code == 201
    assert response.json()["config"]["display_mode"] == "board"


def test_view_preference_rejects_unknown_display_mode(client):
    response = client.post(
        "/v1/view-preferences/business-journeys.list/custom-views",
        json={"config": {"version": 1, "columns": [], "display_mode": "cards"}},
    )
    assert response.status_code == 422


def test_old_view_config_without_display_mode_still_parses(client):
    response = client.post(
        "/v1/view-preferences/customers.list/custom-views",
        json={"config": {"version": 1, "columns": []}},
    )
    assert response.status_code == 201
    assert response.json()["config"]["display_mode"] is None
```

- [ ] **Step 2: Run API tests RED**

Run: `cd CRM-Server && .venv/bin/python -m pytest tests/unit/test_view_preferences_api.py -q --no-cov`

Expected: `display_mode` missing / extra ignored or invalid value accepted.
- [ ] **Step 3: Add backend and frontend config field**

Backend exact schema:

```python
class ViewPreferenceConfig(BaseModel):
    version: int = Field(1, ge=1)
    columns: list[ViewPreferenceColumn] = Field(default_factory=list, max_length=100)
    sorts: list[dict[str, Any]] = Field(default_factory=list, max_length=10)
    filters: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    density: str | None = Field(None, max_length=20)
    display_mode: Literal["table", "board"] | None = None
```

Frontend exact type and schema extension:

```typescript
export type ViewDisplayMode = 'table' | 'board'

export interface ViewPreferenceConfig {
  version: number
  columns: ViewPreferenceColumn[]
  sorts?: Record<string, unknown>[] | undefined
  filters?: Record<string, unknown>[] | undefined
  density?: string | null | undefined
  display_mode?: ViewDisplayMode | null | undefined
}

const ViewPreferenceConfigSchema: z.ZodType<ViewPreferenceConfig> = z.object({
  version: z.number(),
  columns: z.array(ViewPreferenceColumnSchema),
  sorts: z.array(z.record(z.string(), z.unknown())).optional(),
  filters: z.array(z.record(z.string(), z.unknown())).optional(),
  density: z.string().nullable().optional(),
  display_mode: z.enum(['table', 'board']).nullable().optional(),
})
```

Use the existing inline column schema if it has not been extracted as `ViewPreferenceColumnSchema`; do not create a second runtime schema.

- [ ] **Step 4: Write failing migration tests**

`test_business_journey_saved_view_migration.py` loads migration 136. Use SQLite or mock op helpers following existing migration tests. Assert:

```python
assert migration.revision == "136_business_journey_saved_views"
assert migration.down_revision == "135_deal_journey_public_ids"
```

Database behavior:

```python
# source config
{"version": 1, "columns": [], "filters": [{"field": "owner_id", "op": "eq", "value": "me"}]}
# after upgrade
row.view_key == "business-journeys.list"
json.loads(row.config_json)["display_mode"] == "board"
# filters preserved
# second upgrade leaves one row
# target-key collision leaves one target row, preserves target name/sort_order, no unique failure
```

- [ ] **Step 5: Run migration tests RED**

Run: `cd CRM-Server && .venv/bin/python -m pytest tests/unit/test_business_journey_saved_view_migration.py -q --no-cov`

Expected: migration missing.

- [ ] **Step 6: Implement migration**

Use SQLAlchemy table reflection / `op.get_bind()`; no schema column change. Parse invalid JSON defensively: leave the row key migrated and replace invalid config with `{"version": 1, "columns": [], "display_mode": "board"}` only for the legacy board key; do not fail deployment.

- [ ] **Step 7: Run Task 1 tests**

```bash
cd CRM-Server && .venv/bin/python -m pytest tests/unit/test_view_preferences_api.py tests/unit/test_business_journey_saved_view_migration.py -q --no-cov
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add CRM-Server/app/schemas/view_preference.py CRM-Server/migrations/versions/136_business_journey_saved_views.py CRM-Server/tests/unit/test_view_preferences_api.py CRM-Server/tests/unit/test_business_journey_saved_view_migration.py CRM-Client/src/api/viewPreference.ts
git commit -m "feat(views): save business journey display mode"
```

---

### Task 2: Build shared business-journey query service and list-query catalog

**Files:**
- Create: `CRM-Server/app/services/business_journey_query_service.py`
- Create: `CRM-Server/app/core/list_query/catalogs/business_journeys.py`
- Modify: `CRM-Server/app/core/list_query/catalogs/__init__.py`
- Modify: `CRM-Server/app/schemas/deal_journey.py`
- Create: `CRM-Server/tests/unit/test_business_journey_query_service.py`
- Modify: `CRM-Server/tests/unit/list_query/test_catalog_manifest.py`
- Modify generated: `CRM-Client/src/components/crmwolf/listQueryCatalogManifest.json`

**Interfaces:**

```python
JourneyScopeTab = Literal["all", "active", "completed", "lost"]

@dataclass(frozen=True)
class BusinessJourneyQueryRequest:
    team_id: int
    user_id: int
    permission_codes: frozenset[str] = frozenset()
    tab: JourneyScopeTab = "all"
    search: str | None = None
    filters: list[FilterCondition] | None = None
    sorts: list[SortCondition] | None = None

@dataclass(frozen=True)
class BusinessJourneyQueryRow:
    journey: CustomerDealJourney
    customer: Customer
    opportunity: Opportunity | None
    owner_id: str | None
    stage: BoardStageKey
    contract_summary: BusinessJourneyContractSummary
    payment_summary: BusinessJourneyPaymentSummary
    invoice_summary: BusinessJourneyInvoiceSummary

class BusinessJourneyQueryService:
    def query_base(self, db: Session, *, request: BusinessJourneyQueryRequest) -> Query
    def paginate(
        self, db: Session, *, request: BusinessJourneyQueryRequest, skip: int, limit: int
    ) -> tuple[list[BusinessJourneyQueryRow], int]
    def list_for_board(
        self, db: Session, *, request: BusinessJourneyQueryRequest, limit: int
    ) -> tuple[list[BusinessJourneyQueryRow], int, bool]
    def owner_options(self, db: Session, *, request: BusinessJourneyQueryRequest) -> list[OwnerOption]
```

Visibility predicate is OR:

```text
customer:view:all
OR opportunity:view:all
OR (customer:view:own AND Customer.owner_id == user)
OR (opportunity:view:own AND Opportunity.owner_id == user)
OR active CustomerMember access_level >= VIEW
```

Archived journeys are always excluded. If the user has neither all permission, each row must satisfy at least one own/member branch. Customer-member visibility applies even without own/all codes.

Catalog `BUSINESS_JOURNEYS_LIST_QUERY_CATALOG`, name `business_journeys`:

| key | type | expression |
|---|---|---|
| `journey_name` | text | `CustomerDealJourney.name` |
| `customer_name` | text | `Customer.account_name` |
| `stage` | enum | `predicate_builder` returns `None` only to advertise accepted enum operators in the manifest; service removes and applies stage filters before `apply_filters`; frontend disables sorting |
| `owner_id` | enum | `coalesce(Opportunity.owner_id, Customer.owner_id)` + person aliases |
| `amount` | number | `coalesce(Opportunity.actual_amount, Opportunity.total_amount, 0)`; table, board, filter and sort use the same primary amount |
| `purchase_type` | enum | `Opportunity.purchase_type` |
| `product_name` | text | `Product.name` outer join through opportunity |
| `last_event_at` | date | `CustomerDealJourney.last_event_at` |
| `started_at` | date | `CustomerDealJourney.started_at` |
| `created_time` | date | `Opportunity.created_time` |
| `expected_closing_date` | date | `Opportunity.expected_closing_date`, `date_kind="date"` |
| `status` | enum | `CustomerDealJourney.status` |

Search: journey name, customer identity terms, opportunity name, product name.
Default with no explicit sorts: `case(last_event_at IS NULL), last_event_at desc, journey.id desc`. With explicit sorts: call `query.order_by(None)`, apply catalog sorts, then append `journey.id desc` tie-break. This prevents the default null-case expression from overriding the user's selected sort.

- [ ] **Step 1: Write failing query-service tests**

Create a SQLite fixture helper `_seed_query_case(db) -> dict[str, CustomerDealJourney]` with:

- `customer_owned`: customer owner user 1; opportunity owner user 2
- `opportunity_owned`: customer owner user 2; opportunity owner user 1
- `member_visible`: customer owner user 2; user 1 active VIEW member
- `foreign`: customer / opportunity owner user 2, no membership
- `no_opportunity`: customer owner user 1, no primary opportunity
- `completed`, `lost`, `archived`
- Hifox / Apifox products, one signed contract row, one payment plan row, one pending invoice row to cover derived stages

Implement these tests with real assertions:

```python
def test_own_scope_unions_customer_owner_opportunity_owner_and_member(db):
    seeded = _seed_query_case(db)
    rows, total = service.paginate(db, request=_request(user_id=1, permission_codes=frozenset({"customer:view:own", "opportunity:view:own"})), skip=0, limit=50)
    assert {row.journey.id for row in rows} == {
        seeded["customer_owned"].id,
        seeded["opportunity_owned"].id,
        seeded["member_visible"].id,
        seeded["no_opportunity"].id,
        seeded["completed"].id,
        seeded["lost"].id,
    }
    assert total == 6


def test_all_permission_returns_all_non_archived_rows(db):
    seeded = _seed_query_case(db)
    rows, total = service.paginate(db, request=_request(user_id=9, permission_codes=frozenset({"customer:view:all"})), skip=0, limit=50)
    assert seeded["foreign"].id in {row.journey.id for row in rows}
    assert seeded["archived"].id not in {row.journey.id for row in rows}
    assert total == 7


def test_list_and_board_queries_return_same_ids_for_same_request(db):
    _seed_query_case(db)
    request = _request(
        user_id=1,
        filters=[FilterCondition(field="product_name", op="eq", value="Hifox")],
        sorts=[SortCondition(field="last_event_at", direction="desc")],
    )
    table_rows, total = service.paginate(db, request=request, skip=0, limit=500)
    board_rows, board_total, truncated = service.list_for_board(db, request=request, limit=500)
    assert [row.journey.id for row in board_rows] == [row.journey.id for row in table_rows]
    assert board_total == total
    assert truncated is False
```

Additional tests with explicit assertions:

- `test_tabs_active_completed_lost_are_mutually_correct`: active result statuses are exactly subset `{ACTIVE, WON}`; completed IDs equal `{seeded["completed"].id}`; lost IDs equal `{seeded["lost"].id}`.
- `test_search_and_filters_apply_before_count`: customer search plus amount `gte` returns one expected journey and `total == 1`.
- `test_stage_filter_uses_infer_board_stage`: `stage=contract_processing` returns only the journey with contract summary; `stage=payment_processing` returns payment journey; `stage=invoice_processing` returns invoice journey.
- `test_sort_and_pagination_are_stable`: equal `last_event_at` breaks by journey ID descending and pages have no overlap.
- `test_board_limit_reports_untruncated_total`: limit 2 returns length 2, full total and `truncated is True`.
- `test_owner_options_use_visible_rows_only`: user 1 does not receive user 2 owner option when the only user-2 journey is foreign.

- [ ] **Step 2: Run query tests RED**

Run: `cd CRM-Server && .venv/bin/python -m pytest tests/unit/test_business_journey_query_service.py -q --no-cov`

Expected: module missing.

- [ ] **Step 3: Implement catalog and query service**

API resolves permission codes once and passes them in `BusinessJourneyQueryRequest`; the service does not read permission CRUD. Use `ListQueryContext(db=db, team_id=team_id, current_user_id=str(user_id))`, `apply_search`, `apply_filters`, `apply_sorts`; count after visibility + tab + search + all filters, before pagination.

Stage filter exact flow:

1. Remove `field == "stage"` conditions from filters passed to `apply_filters`.
2. Apply visibility, tab, search and remaining filters.
3. Read candidate journey IDs only.
4. Batch-load contract / payment / invoice summaries and opportunities; call `infer_board_stage`.
5. Apply the existing filter operators (`eq`, `neq`, `in`, `not_in`) to derived stage values in Python; reject unsupported stage operators with `ListQueryError`.
6. Add `CustomerDealJourney.id.in_(matching_ids)` before count. Empty IDs use `query.filter(False)`.

Do not reproduce stage logic in SQL.

- [ ] **Step 4: Add schemas**

Extend journey schema with:

```python
class BusinessJourneyOwner(BaseModel):
    id: str
    name: str
    avatar_url: str | None = None

class BusinessJourneyListItem(CustomerDealJourneyResponse):
    customer_id: str
    customer_name: str
    owner: BusinessJourneyOwner | None
    primary_opportunity_name: str | None
    product_name: str | None
    created_time: datetime | None
    expected_closing_date: date | None

class BusinessJourneyListResponse(PaginatedResponse[BusinessJourneyListItem]):
    pass
```

Board card uses:

```python
public_id: str
customer_id: str
```

It does not expose internal `journey_id`. Board response retains summary; `summary.total_count` is untruncated and top-level `truncated: bool` indicates limit clipping.

- [ ] **Step 5: Register catalog and regenerate manifest**

Add catalog to `LIST_QUERY_CATALOGS`; update manifest test DataTable catalog set with `business_journeys`; run:

```bash
cd CRM-Server && .venv/bin/python scripts/generate_list_query_manifest.py
```

- [ ] **Step 6: Run Task 2 tests**

```bash
cd CRM-Server && .venv/bin/python -m pytest tests/unit/test_business_journey_query_service.py tests/unit/list_query/test_catalog_manifest.py -q --no-cov
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add CRM-Server/app/services/business_journey_query_service.py CRM-Server/app/core/list_query/catalogs/business_journeys.py CRM-Server/app/core/list_query/catalogs/__init__.py CRM-Server/app/schemas/deal_journey.py CRM-Server/tests/unit/test_business_journey_query_service.py CRM-Server/tests/unit/list_query/test_catalog_manifest.py CRM-Client/src/components/crmwolf/listQueryCatalogManifest.json
git commit -m "feat(journey): add shared journey query service"
```

---

### Task 3: Replace the old board API with unified list, board, and owner endpoints

**Files:**
- Create: `CRM-Server/app/api/business_journeys.py`
- Create: `CRM-Server/app/services/business_journey_presenter.py`
- Modify: `CRM-Server/app/api/customer_deal_journeys.py` — reuse presenter; endpoints unchanged
- Modify: `CRM-Server/app/api/business_journey_board.py` — keep endpoint temporarily; import shared `BOARD_COLUMNS` after domain move
- Modify: `CRM-Server/app/main.py` — register new router alongside old board router during transition
- Modify: `CRM-Server/app/services/deal_journey_stage.py` — domain-own `BOARD_COLUMNS`
- Modify: `CRM-Server/tests/unit/test_backend_business_scenarios.py`
- Create: `CRM-Server/tests/unit/api/test_business_journeys_api.py` by porting date-filter cases; keep old test until Task 7
- Create: `CRM-Server/tests/unit/api/test_business_journey_visibility.py`
- Modify: `CRM-Server/tests/unit/test_business_journey_board_stages.py` imports

**Interfaces:**

Router prefix: `/v1/business-journeys`.

```text
GET /v1/business-journeys
  skip, limit, tab, search, filters, sorts
  → PaginatedResponse[BusinessJourneyListItem]

GET /v1/business-journeys/board
  tab, search, filters, sorts, limit=500
  → BusinessJourneyBoardResponse with public journey ids and truncated

GET /v1/business-journeys/owner-options
  → OwnerListResponse from BusinessJourneyQueryService.owner_options
```

No `sales_dashboard:view:*` requirement. Before querying, API loads permission codes. If the user has none of `customer:view:all|own`, `opportunity:view:all|own`, it checks whether any active CustomerMember row grants VIEW+; if neither, return 403 `缺少业务旅程查看权限`. Rows are still filtered by the service’s OR predicate.

Both list and board build the same `BusinessJourneyQueryRequest`. Parse `filters` / `sorts` with `optional_request_list_query`; map `ListQueryError` through `run_or_400`.

Tab is `Literal["all", "active", "completed", "lost"]`; invalid value returns FastAPI 422.

- [ ] **Step 1: Write API RED tests**

Move the existing date filter fixture to the new API module and update it to seed unapproved opportunities too. Replace `_journey_ids` with public IDs:

```python
def _journey_public_ids(body: dict) -> set[str]:
    return {
        card["public_id"]
        for column in body["columns"]
        for card in column["cards"]
    }
```

Create visibility tests with these explicit assertions:

```python
def test_sales_member_lists_own_journey_without_dashboard_permission(api_env):
    journey = seed_journey(api_env, customer_owner="1", opportunity_owner="1")
    api_env.permissions = ["customer:view:own", "opportunity:view:own"]
    response = api_env.client.get("/v1/business-journeys")
    assert response.status_code == 200
    assert [item["public_id"] for item in response.json()["items"]] == [journey.public_id]


def test_customer_member_can_see_shared_customer_journey(api_env):
    journey = seed_journey(api_env, customer_owner="2", opportunity_owner="2")
    seed_customer_member(api_env, customer_id=journey.customer_id, user_id="1", access_level="VIEW")
    api_env.permissions = []
    response = api_env.client.get("/v1/business-journeys")
    assert response.status_code == 200
    assert journey.public_id in {item["public_id"] for item in response.json()["items"]}


def test_board_and_list_share_filtered_ids(api_env):
    seed_journey(api_env, product_name="Hifox")
    seed_journey(api_env, product_name="Apifox")
    params = {"filters": json.dumps([{"field": "product_name", "op": "eq", "value": "Hifox"}])}
    list_body = api_env.client.get("/v1/business-journeys", params=params).json()
    board_body = api_env.client.get("/v1/business-journeys/board", params=params).json()
    assert _journey_public_ids(board_body) == {item["public_id"] for item in list_body["items"]}
    assert board_body["summary"]["total_count"] == list_body["total"]


def test_board_uses_public_id_and_omits_internal_journey_id(api_env):
    journey = seed_journey(api_env)
    card = next(card for column in api_env.client.get("/v1/business-journeys/board").json()["columns"] for card in column["cards"])
    assert card["public_id"] == journey.public_id
    assert "journey_id" not in card


def test_no_relevant_permission_or_membership_returns_403(api_env):
    api_env.permissions = []
    response = api_env.client.get("/v1/business-journeys")
    assert response.status_code == 403
    assert response.json()["detail"] == "缺少业务旅程查看权限"
```

Also test:

- unapproved primary opportunity journey appears in list and board as `early_communication`.
- owner options contain only owners present in visible rows.
- invalid `tab=unknown` returns 422.
- unknown filter / sort field returns 400.
- created-time and expected-closing date ranges preserve existing boundary behavior on the new board endpoint.

Update `run_opportunity_approval_starts_business_journey_board`: before approval the journey count is already 1 and card stage is `early_communication`; after approval event, journey remains present. Replace internal ID assertion with `public_id`.

- [ ] **Step 2: Run API tests RED**

```bash
cd CRM-Server && .venv/bin/python -m pytest \
  tests/unit/api/test_business_journeys_api.py \
  tests/unit/api/test_business_journey_visibility.py \
  tests/unit/test_backend_business_scenarios.py -q --no-cov
```

Expected: new endpoints 404 / old expectations fail.

- [ ] **Step 3: Implement unified API**

Move response mapping helpers from the old board API and `customer_deal_journeys.py` into `app/services/business_journey_presenter.py`. Both API modules import this presenter; API modules must not import each other. Board columns continue `BOARD_COLUMNS`; remove approved-event gating. Board `amount` uses the query row’s unified opportunity amount, not contract amount.

Return pagination:

```python
PaginatedResponse(
    items=items,
    total=total,
    page=skip // limit + 1,
    page_size=limit,
    total_pages=(total + limit - 1) // limit if total else 0,
)
```

- [ ] **Step 4: Register new router without removing the old router**

`main.py` includes `business_journeys` while the old board router remains registered until Task 7. Move `BOARD_COLUMNS` to `deal_journey_stage.py`; both APIs import the domain constant. No frontend dual-read is introduced.

- [ ] **Step 5: Run Task 3 tests**

```bash
cd CRM-Server && .venv/bin/python -m pytest \
  tests/unit/api/test_business_journeys_api.py \
  tests/unit/api/test_business_journey_visibility.py \
  tests/unit/test_business_journey_board_stages.py \
  tests/unit/test_backend_business_scenarios.py -q --no-cov
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add CRM-Server/app/api/business_journeys.py CRM-Server/app/api/business_journey_board.py CRM-Server/app/api/customer_deal_journeys.py CRM-Server/app/main.py CRM-Server/app/services/business_journey_presenter.py CRM-Server/app/services/deal_journey_stage.py CRM-Server/tests/unit/api/test_business_journeys_api.py CRM-Server/tests/unit/api/test_business_journey_visibility.py CRM-Server/tests/unit/test_business_journey_board_stages.py CRM-Server/tests/unit/test_backend_business_scenarios.py
git commit -m "feat(journey): unify list and board read APIs"
```

---
### Task 4: Make display mode part of custom-view snapshots and existing view config controls

**Files:**
- Modify: `CRM-Client/src/composables/useCustomFilterViews.ts`
- Modify: `CRM-Client/src/composables/__tests__/useCustomFilterViews.spec.ts`
- Modify carefully on current user work: `CRM-Client/src/components/crmwolf/ColumnConfigPopover.vue`
- Modify carefully on current user work: `CRM-Client/src/components/crmwolf/ListAdvancedTools.vue`
- Modify: `CRM-Client/src/components/crmwolf/DataTable.vue`
- Modify carefully: `CRM-Client/src/components/crmwolf/__tests__/ListAdvancedTools.test.ts`
- Modify carefully: `CRM-Client/src/components/crmwolf/__tests__/overlayPanelChrome.test.ts`

**Interfaces:**

`useCustomFilterViews` options add:

```typescript
activeDisplayMode?: Ref<ViewDisplayMode>
builtInDisplayMode?: ViewDisplayMode
getBuiltInFilters?: (tabKey: string) => ListFilterCondition[]
```

Return adds `saveCurrentAsCustomView(): Promise<void>`. Existing `updateActiveCustomViewConfig()` includes display mode when supplied.

`ViewApplySnapshot` has optional `displayMode`. Existing callers that omit `activeDisplayMode` produce configs without `display_mode`.

`ColumnConfigPopover` / `ListAdvancedTools` / DataTable optional props:

```typescript
viewDisplayMode?: ViewDisplayMode | null
viewDisplayModeEnabled?: boolean
viewConfigTriggerLabel?: string
viewConfigPanelTitle?: string
canSaveCurrentView?: boolean
viewSaveLoading?: boolean
```

Emits:

```typescript
'update:view-display-mode': [value: ViewDisplayMode]
'save-current-view': []
```

Defaults for all existing pages:

```text
trigger label = 字段配置
panel title = 字段配置
viewDisplayModeEnabled = false
```

Business journey passes both labels as「视图配置」. Its existing popover gains one page-level option before the unchanged column list:

```text
视图配置
  看板视图 [Switch]
字段
  existing column rows
```

Use existing `Switch`, `Button`, typography and spacing; no new Popover or design-system component.

- [ ] **Step 1: Write RED composable tests**

Append these tests using the file's existing `customView`, mocked API and `flushPromises` imports:

```typescript
it('applies custom display mode and restores the built-in mode', async () => {
  const activeTab = ref('all')
  const activeFilters = ref<ListFilterCondition[]>([])
  const activeSorts = ref<ListSortCondition[]>([])
  const activeColumns = ref<ViewPreferenceItem['config']['columns']>([])
  const displayMode = ref<ViewDisplayMode>('board')
  const refresh = vi.fn().mockResolvedValue(true)
  const views = useCustomFilterViews({
    viewKey: 'business-journeys.list',
    activeTab,
    activeFilters,
    activeSorts,
    activeColumns,
    activeDisplayMode: displayMode,
    builtInDisplayMode: 'table',
    refresh,
  })
  views.customViews.value = [{
    ...customView,
    config: { ...customView.config, display_mode: 'table' },
  }]

  expect(views.applyCustomViewTab('custom-view:1')).toBe(true)
  await flushPromises()
  expect(displayMode.value).toBe('table')

  expect(views.applyBuiltInTab('all')).toBe(true)
  expect(displayMode.value).toBe('board')
})


it('saves a board-only current snapshot without filters', async () => {
  const activeTab = ref('all')
  const activeFilters = ref<ListFilterCondition[]>([])
  const activeSorts = ref<ListSortCondition[]>([])
  const activeColumns = ref<ViewPreferenceItem['config']['columns']>([])
  const displayMode = ref<ViewDisplayMode>('board')
  vi.mocked(viewPreferenceApi.createCustomView).mockResolvedValue({
    ...customView,
    config: { ...customView.config, filters: [], sorts: [], columns: [], display_mode: 'board' },
  })
  const views = useCustomFilterViews({
    viewKey: 'business-journeys.list',
    activeTab,
    activeFilters,
    activeSorts,
    activeColumns,
    activeDisplayMode: displayMode,
    getBuiltInFilters: () => [],
    refresh: vi.fn().mockResolvedValue(true),
  })

  await views.saveCurrentAsCustomView()

  expect(viewPreferenceApi.createCustomView).toHaveBeenCalledWith('business-journeys.list', {
    config: { version: 1, columns: [], filters: [], sorts: [], display_mode: 'board' },
  })
})


it('materializes built-in tab scope and lets explicit filters win by field', async () => {
  const activeTab = ref('active')
  const activeFilters = ref<ListFilterCondition[]>([
    { field: 'status', op: 'eq', value: 'WON' },
    { field: 'owner_id', op: 'eq', value: 'me' },
  ])
  vi.mocked(viewPreferenceApi.createCustomView).mockResolvedValue(customView)
  const views = useCustomFilterViews({
    viewKey: 'business-journeys.list',
    activeTab,
    activeFilters,
    activeSorts: ref<ListSortCondition[]>([]),
    activeColumns: ref([]),
    activeDisplayMode: ref<ViewDisplayMode>('table'),
    getBuiltInFilters: tab => tab === 'active'
      ? [{ field: 'status', op: 'in', value: ['ACTIVE', 'WON'] }]
      : [],
    refresh: vi.fn().mockResolvedValue(true),
  })

  await views.saveCurrentAsCustomView()

  const call = vi.mocked(viewPreferenceApi.createCustomView).mock.calls[0]
  expect(call?.[1].config.filters).toEqual([
    { field: 'status', op: 'eq', value: 'WON' },
    { field: 'owner_id', op: 'eq', value: 'me' },
  ])
})


it('keeps existing callers free of display_mode', async () => {
  const activeTab = ref('all')
  const activeFilters = ref<ListFilterCondition[]>([])
  const activeSorts = ref<ListSortCondition[]>([])
  const activeColumns = ref<ViewPreferenceItem['config']['columns']>([])
  const views = useCustomFilterViews({
    viewKey: 'customers.list',
    activeTab,
    activeFilters,
    activeSorts,
    activeColumns,
    refresh: vi.fn().mockResolvedValue(true),
  })
  views.customViews.value = [customView]
  activeTab.value = 'custom-view:1'
  vi.mocked(viewPreferenceApi.updateCustomView).mockResolvedValue(customView)

  await views.updateActiveCustomViewConfig()

  const config = vi.mocked(viewPreferenceApi.updateCustomView).mock.calls[0]?.[2].config
  expect(config).not.toHaveProperty('display_mode')
})
```

- [ ] **Step 2: Run composable tests RED**

Run: `cd CRM-Client && npx vitest run src/composables/__tests__/useCustomFilterViews.spec.ts`

Expected: option / method missing.

- [ ] **Step 3: Implement composable state**

Update clone, capture, restore, equality, custom apply, built-in restore, create and update. `saveAsCustomView(filters)` calls the shared creation helper and retains its existing empty-filter guard. `saveCurrentAsCustomView()` has no empty-filter guard. Merge built-in and explicit filters by `field`, with explicit filters replacing built-in filters of the same field.

- [ ] **Step 4: Write RED view-config surface tests**

Extend the current dirty tests without replacing their breakpoint / open-state coverage:

```typescript
it('shows the optional journey view config and emits board mode', async () => {
  const wrapper = mount(ListAdvancedTools, {
    props: {
      ...props,
      viewDisplayModeEnabled: true,
      viewDisplayMode: 'table',
      viewConfigTriggerLabel: '视图配置',
      viewConfigPanelTitle: '视图配置',
      canSaveCurrentView: true,
      viewSaveLoading: false,
    },
    attachTo: document.body,
  })
  wrappers.push(wrapper)
  await flushPromises()

  const trigger = Array.from(document.body.querySelectorAll('button')).find(button => button.textContent?.includes('视图配置'))
  expect(trigger).toBeDefined()
  trigger?.click()
  await flushPromises()
  const boardSwitch = document.body.querySelector('[role="switch"]')
  expect(boardSwitch).not.toBeNull()
  ;(boardSwitch as HTMLElement).click()
  await flushPromises()
  expect(wrapper.emitted('update:view-display-mode')).toEqual([['board']])
})


it('emits save-current-view from the same config surface', async () => {
  const wrapper = mount(ListAdvancedTools, {
    props: {
      ...props,
      viewDisplayModeEnabled: true,
      viewDisplayMode: 'board',
      viewConfigTriggerLabel: '视图配置',
      viewConfigPanelTitle: '视图配置',
      canSaveCurrentView: true,
      viewSaveLoading: false,
    },
    attachTo: document.body,
  })
  wrappers.push(wrapper)
  await flushPromises()
  const trigger = Array.from(document.body.querySelectorAll('button')).find(button => button.textContent?.includes('视图配置'))
  trigger?.click()
  await flushPromises()
  const save = Array.from(document.body.querySelectorAll('button')).find(button => button.textContent?.replace(/\s+/g, '') === '另存为视图')
  expect(save).toBeDefined()
  save?.click()
  await flushPromises()
  expect(wrapper.emitted('save-current-view')).toHaveLength(1)
})


it('keeps existing pages free of the board switch and view label', async () => {
  const wrapper = mount(ListAdvancedTools, { props, attachTo: document.body })
  wrappers.push(wrapper)
  await flushPromises()
  expect(document.body.textContent).not.toContain('看板视图')
  expect(document.body.textContent).not.toContain('视图配置')
  expect(document.body.textContent).toContain('字段配置')
})


it('preserves controlled board mode across the compact breakpoint', async () => {
  const viewport = mockViewportWidth(767.5)
  const wrapper = mount(ListAdvancedTools, {
    props: {
      ...props,
      viewDisplayModeEnabled: true,
      viewDisplayMode: 'table',
      viewConfigTriggerLabel: '视图配置',
      viewConfigPanelTitle: '视图配置',
      canSaveCurrentView: true,
      viewSaveLoading: false,
    },
    attachTo: document.body,
  })
  wrappers.push(wrapper)
  await flushPromises()
  await wrapper.get('button').trigger('click')
  await flushPromises()
  const trigger = Array.from(document.body.querySelectorAll('button')).find(button => button.textContent?.includes('视图配置'))
  trigger?.click()
  await flushPromises()
  const boardSwitch = document.body.querySelector('[role="switch"]') as HTMLElement | null
  boardSwitch?.click()
  await wrapper.setProps({ viewDisplayMode: 'board' })
  viewport.setWidth(768)
  await flushPromises()
  expect(document.body.querySelector('[role="switch"]')?.getAttribute('data-state')).toBe('checked')
})
```

- [ ] **Step 5: Run tool tests RED**

```bash
cd CRM-Client && npx vitest run \
  src/components/crmwolf/__tests__/ListAdvancedTools.test.ts \
  src/components/crmwolf/__tests__/overlayPanelChrome.test.ts
```

Expected: optional props missing.

- [ ] **Step 6: Implement optional controls without overwriting current work**

Before editing, re-read latest files and preserve Teleport targets, controlled open state and viewport behavior. Add the optional section inside `ColumnConfigPopover`; add trigger/title props with defaults; `ListAdvancedTools` and DataTable only pass props/events. Other consumers render exactly the prior DOM and labels.

- [ ] **Step 7: Run Task 4 tests**

```bash
cd CRM-Client && npx vitest run \
  src/composables/__tests__/useCustomFilterViews.spec.ts \
  src/components/crmwolf/__tests__/ListAdvancedTools.test.ts \
  src/components/crmwolf/__tests__/overlayPanelChrome.test.ts
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add CRM-Client/src/api/viewPreference.ts CRM-Client/src/composables/useCustomFilterViews.ts CRM-Client/src/composables/__tests__/useCustomFilterViews.spec.ts CRM-Client/src/components/crmwolf/ColumnConfigPopover.vue CRM-Client/src/components/crmwolf/ListAdvancedTools.vue CRM-Client/src/components/crmwolf/DataTable.vue CRM-Client/src/components/crmwolf/__tests__/ListAdvancedTools.test.ts CRM-Client/src/components/crmwolf/__tests__/overlayPanelChrome.test.ts
git commit -m "feat(views): persist optional list display mode"
```

---

### Task 5: Build the unified BusinessJourneys page with existing DataTable and board visual

**Files:**
- Create: `CRM-Client/src/views/BusinessJourneys.vue`
- Create: `CRM-Client/src/components/business-journey/BusinessJourneyListTools.vue`
- Create: `CRM-Client/src/components/business-journey/BusinessJourneyTableView.vue`
- Create: `CRM-Client/src/components/business-journey/BusinessJourneyBoardView.vue`
- Modify: `CRM-Client/src/api/dealJourney.ts`
- Modify: `CRM-Client/src/schemas/dealJourney.ts`
- Create: `CRM-Client/src/schemas/__tests__/dealJourneyPage.test.ts`
- Modify: `CRM-Client/src/AppLayout.vue`
- Modify: `CRM-Client/src/views/BusinessJourneyBoard.vue` — temporary thin wrapper around shared BoardView; Task 7 deletes it
- Keep unchanged through Task 6: `CRM-Client/src/api/businessJourneyBoard.ts`
- Keep unchanged through Task 6: `CRM-Client/src/schemas/businessJourneyBoard.ts`
- Keep unchanged through Task 6: `CRM-Client/src/utils/businessJourneyBoardFilters.ts`
- Keep unchanged through Task 6: `CRM-Client/src/utils/__tests__/businessJourneyBoardFilters.test.ts`
- Create: `CRM-Client/tests/components/BusinessJourneys.spec.ts`
- Create: `CRM-Client/tests/components/BusinessJourneyBoardView.spec.ts`

**Interfaces:**

```typescript
interface BusinessJourneyListParams {
  skip: number
  limit: number
  tab: 'all' | 'active' | 'completed' | 'lost'
  search?: string
  filters?: string
  sorts?: string
}

dealJourneyApi.list(params): Promise<PaginatedResponse<BusinessJourneyListItem>>
dealJourneyApi.getBoard(params): Promise<BusinessJourneyBoardResponse>
dealJourneyApi.getOwnerFilterOptions(): Promise<OwnerFilterOptionsResponse>
```

List Zod uses backend keys `items`, `total`, `page`, `page_size`, `total_pages`; do not use the unrelated `data/pageSize` helper.

```typescript
const activeTab = ref<string>('all')
const displayMode = ref<ViewDisplayMode>('table')
const activeFilters = ref<ListFilterCondition[]>([])
const activeSorts = ref<ListSortCondition[]>([])
const activeColumns = ref<ViewPreferenceConfig['columns']>([])

const builtInFilters: Record<string, ListFilterCondition[]> = {
  all: [],
  active: [{ field: 'status', op: 'in', value: ['ACTIVE', 'WON'] }],
  completed: [{ field: 'status', op: 'eq', value: 'COMPLETED' }],
  lost: [{ field: 'status', op: 'eq', value: 'LOST' }],
}
```

Built-in requests pass `tab`; custom views pass `tab='all'` plus saved explicit status filters.

`BusinessJourneyTableView` fields use response keys and list-query mappings:

```typescript
defineListFields([
  { key: 'name', label: '旅程名称', type: 'text', column: { width: '220px' }, filter: { apiKey: 'journey_name' }, sort: { apiKey: 'journey_name' } },
  { key: 'customer_name', label: '客户', type: 'text', column: { width: '190px' }, filter: true, sort: true },
  { key: 'current_board_stage', label: '当前阶段', type: 'enum', options: stageOptions, column: { width: '120px' }, filter: { apiKey: 'stage' }, sort: false, sortDisabledReason: '阶段由跨对象状态动态推断，请使用看板查看阶段顺序' },
  { key: 'primary_opportunity_name', label: '主商机', type: 'text', column: { width: '200px' }, filter: false, filterDisabledReason: '主商机仅作关联摘要', sort: false, sortDisabledReason: '主商机仅作关联摘要' },
  { key: 'product_name', label: '产品', type: 'text', column: { width: '140px' }, filter: true, sort: true },
  { key: 'amount', label: '金额', type: 'number', column: { width: '130px', align: 'right' }, filter: true, sort: true },
  { key: 'purchase_type', label: '采购类型', type: 'enum', options: purchaseTypeOptions, column: { width: '110px' }, filter: true, sort: true },
  { key: 'owner_id', label: '负责人', type: 'enum', options: ownerOptions, column: { width: '120px' }, filter: true, sort: true },
  { key: 'last_event_at', label: '最近动态', type: 'date', column: { width: '150px' }, filter: true, sort: true },
  { key: 'started_at', label: '开始时间', type: 'date', column: { width: '140px' }, filter: true, sort: true },
])
```

Slots render stage label, owner, amount, purchase type and dates. `BusinessJourneyBoardView` is the old board surface extracted without visual changes. `BusinessJourneyListTools` composes existing toolbar controls and owns no persistence. No hidden DataTable.

- [ ] **Step 1: Write RED schema/API tests**

In `dealJourneyPage.test.ts`, define a complete list item fixture and board card fixture. Assert pagination parses, public ID is required, and numeric-only `journey_id` is rejected. Mock request calls:

```typescript
await dealJourneyApi.list({ skip: 0, limit: 20, tab: 'all' })
expect(request.get).toHaveBeenCalledWith('/v1/business-journeys', { params: { skip: 0, limit: 20, tab: 'all' } })
await dealJourneyApi.getBoard({ tab: 'active' })
expect(request.get).toHaveBeenCalledWith('/v1/business-journeys/board', { params: { tab: 'active' } })
await dealJourneyApi.getOwnerFilterOptions()
expect(request.get).toHaveBeenCalledWith('/v1/business-journeys/owner-options')
```

- [ ] **Step 2: Write RED page tests**

Mock journey/view APIs; stub TableView and BoardView.

```typescript
it('loads only the table projection initially', async () => {
  mountPage()
  await flushPromises()
  expect(dealJourneyApi.list).toHaveBeenCalledOnce()
  expect(dealJourneyApi.getBoard).not.toHaveBeenCalled()
})


it('switches to board through the existing view config event', async () => {
  const wrapper = mountPage()
  await flushPromises()
  wrapper.getComponent(BusinessJourneyTableView).vm.$emit('update:view-display-mode', 'board')
  await flushPromises()
  expect(dealJourneyApi.getBoard).toHaveBeenCalledOnce()
  expect(wrapper.findComponent(BusinessJourneyBoardView).exists()).toBe(true)
})


it('uses built-in tab at runtime and explicit filters for a saved board view', async () => {
  vi.mocked(viewPreferenceApi.listCustomViews).mockResolvedValue(customLostBoardViewResponse)
  const wrapper = mountPage()
  await flushPromises()
  headerStore.setActiveTab('active')
  await flushPromises()
  expect(dealJourneyApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ tab: 'active' }))
  headerStore.setActiveTab('custom-view:7')
  await flushPromises()
  const params = vi.mocked(dealJourneyApi.getBoard).mock.calls.at(-1)?.[0]
  expect(params?.tab).toBe('all')
  expect(JSON.parse(params?.filters ?? '[]')).toEqual([{ field: 'status', op: 'eq', value: 'LOST' }])
  expect(wrapper.findComponent(BusinessJourneyBoardView).exists()).toBe(true)
})
```

`BusinessJourneyBoardView.spec.ts` ports old board contracts: stage classes, age tones, skeleton, stale refresh message, blocking error, and `row-click` payload `{ customerId, journeyPublicId }`.

- [ ] **Step 3: Run page tests RED**

```bash
cd CRM-Client && npx vitest run \
  src/schemas/__tests__/dealJourneyPage.test.ts \
  tests/components/BusinessJourneys.spec.ts \
  tests/components/BusinessJourneyBoardView.spec.ts
```

Expected: schemas / components missing.

- [ ] **Step 4: Implement API/schema and page composition**

Use `serializeListQuery`. Load only active mode. Keep separate request sequence and last-success state per mode; stale failures preserve prior data with warning. Mode change invalidates the previous request.

- [ ] **Step 5: Extract board visual and keep the old page as a thin wrapper**

Move old board markup, SCSS, palette, age helpers and error/loading copy into BoardView. New page handles public-ID row clicks. Old `BusinessJourneyBoard.vue` renders the same BoardView with its old API/tools until Task 7; it must not retain copied card/column markup.

- [ ] **Step 6: Update fixed layout**

Rename `isFixedDashboardRoute` to `isFixedWorkspaceRoute`; include `SalesDashboard`, old `BusinessJourneyBoard`, and new `BusinessJourneys` until Task 7.

- [ ] **Step 7: Run Task 5 tests**

```bash
cd CRM-Client && npx vitest run \
  src/schemas/__tests__/dealJourneyPage.test.ts \
  tests/components/BusinessJourneys.spec.ts \
  tests/components/BusinessJourneyBoardView.spec.ts \
  src/composables/__tests__/useCustomFilterViews.spec.ts \
  src/components/crmwolf/__tests__/listFieldCatalog.test.ts \
  src/utils/__tests__/businessJourneyBoardFilters.test.ts
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add CRM-Client/src/views/BusinessJourneys.vue CRM-Client/src/views/BusinessJourneyBoard.vue CRM-Client/src/components/business-journey CRM-Client/src/api/dealJourney.ts CRM-Client/src/schemas/dealJourney.ts CRM-Client/src/schemas/__tests__/dealJourneyPage.test.ts CRM-Client/src/AppLayout.vue CRM-Client/tests/components/BusinessJourneys.spec.ts CRM-Client/tests/components/BusinessJourneyBoardView.spec.ts
git commit -m "feat(journey): add unified list and board page"
```

---
### Task 6: Extract a reusable journey-detail host and add the independent Sheet

**Files:**
- Create: `CRM-Client/src/components/business-journey/DealJourneyDetailHost.vue`
- Create: `CRM-Client/src/views/DealJourneyDetailSheet.vue`
- Modify: `CRM-Client/src/components/panels/DealJourneyDetailContent.vue`
- Modify: `CRM-Client/src/views/CustomerDetailSheet.vue`
- Modify: `CRM-Client/src/views/BusinessJourneys.vue`
- Create: `CRM-Client/tests/components/DealJourneyDetailHost.spec.ts`
- Create: `CRM-Client/tests/components/DealJourneyDetailSheet.spec.ts`
- Modify: `CRM-Client/tests/components/DealJourneyDetailContent.spec.ts`
- Modify: `CRM-Client/tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts`

**Host contract:**

```typescript
interface Props {
  customerId: string
  customerName?: string
  journeyId: string
  journey?: DealJourney | null
  embedded?: boolean
  canEditCustomerContext?: boolean | null
}

const emit = defineEmits<{
  close: []
  refresh: []
  'view-customer': [customerId: string]
}>()
```

`DealJourneyDetailHost` renders the only `DealJourneyDetailContent` and owns the journey branch orchestration currently in `CustomerDetailSheet`:

- existing `ContractFormDialog` for create/edit
- existing contract delete / submit / withdraw APIs and confirmation behavior
- existing `ContractDetailSheet` for `view-contract`
- existing `PaymentPlanDetailSheet` for `view-payment-plan`
- existing `PaymentRecordDetailSheet` for plan record clicks / approval view
- existing `EditRecordDialog` for payment record edit / resubmit
- after successful child action, call `journeyContentRef.refresh()` then emit `refresh`
- nested Sheet close reveals the still-open journey host

Do not create new contract/payment content or action policy. `CustomerDetailSheet` must use Host for its selected-journey branch, so journey orchestration exists once. Its separate customer-info ContractsPanel handlers remain in the customer Sheet.

`DealJourneyDetailSheet`:

```typescript
interface Props {
  customerId: string | null
  customerName?: string
  journeyId: string | null
  visible: boolean
}
```

```vue
<Sheet v-model:open="visibleModel">
  <DetailSheetContent>
    <DealJourneyDetailHost
      v-if="customerId !== null && journeyId !== null"
      :customer-id="customerId"
      :customer-name="customerName"
      :journey-id="journeyId"
      @close="closeSheet"
      @refresh="emit('refresh')"
      @view-customer="emit('view-customer', $event)"
    />
  </DetailSheetContent>
</Sheet>
```

- [ ] **Step 1: Write RED Host tests**

```typescript
it('renders one DealJourneyDetailContent with journey identity', () => {
  const wrapper = mountHost()
  expect(wrapper.getComponent(DealJourneyDetailContent).props()).toMatchObject({
    customerId: 'cus_test',
    journeyId: 'djy_test',
  })
})


it('opens existing contract and payment sheets from detail events', async () => {
  const wrapper = mountHost()
  wrapper.getComponent(DealJourneyDetailContent).vm.$emit('view-contract', 31)
  await nextTick()
  expect(wrapper.getComponent(ContractDetailSheet).props()).toMatchObject({ contractId: 31, visible: true })
  wrapper.getComponent(DealJourneyDetailContent).vm.$emit('view-payment-plan', 41, paymentPlanFixture)
  await nextTick()
  expect(wrapper.getComponent(PaymentPlanDetailSheet).props()).toMatchObject({ planId: 41, visible: true })
})


it('opens the existing contract form and refreshes journey after success', async () => {
  const wrapper = mountHost()
  wrapper.getComponent(DealJourneyDetailContent).vm.$emit('create-contract', createContractPayload)
  await nextTick()
  expect(wrapper.getComponent(ContractFormDialog).props('open')).toBe(true)
  wrapper.getComponent(ContractFormDialog).vm.$emit('success')
  await flushPromises()
  expect(journeyRefresh).toHaveBeenCalled()
  expect(wrapper.emitted('refresh')).toHaveLength(1)
})
```

Add concrete tests for edit (mock `getContract`), delete (mock confirm + `deleteContract`), submit / withdraw approval, plan record → PaymentRecordDetailSheet, record edit / resubmit → EditRecordDialog, and refresh error preserving current Host.

- [ ] **Step 2: Run Host tests RED**

Run: `cd CRM-Client && npx vitest run tests/components/DealJourneyDetailHost.spec.ts`

Expected: Host missing.

- [ ] **Step 3: Implement Host and migrate CustomerDetailSheet**

Replace the `selectedJourneyId !== null` branch with Host. Remove journey-specific handlers now owned by Host. Keep customer-info contract handlers; rename them with `Customer` prefix where necessary to make ownership obvious. Update `DealJourneyDetailContent` comment to the unique-content contract.

- [ ] **Step 4: Write RED Sheet and page tests**

```typescript
it('wraps the Host directly and never renders CustomerDetailSheet', () => {
  const wrapper = mount(DealJourneyDetailSheet, {
    props: { customerId: 'cus_test', journeyId: 'djy_test', visible: true },
  })
  expect(wrapper.findComponent(DealJourneyDetailHost).exists()).toBe(true)
  expect(wrapper.findComponent(CustomerDetailSheet).exists()).toBe(false)
})


it('opens from table and restores the originating focus after close', async () => {
  const wrapper = mountPage()
  const trigger = document.createElement('button')
  document.body.appendChild(trigger)
  trigger.focus()
  wrapper.getComponent(BusinessJourneyTableView).vm.$emit('row-click', listItemFixture)
  await nextTick()
  expect(wrapper.getComponent(DealJourneyDetailSheet).props()).toMatchObject({
    customerId: listItemFixture.customer_id,
    journeyId: listItemFixture.public_id,
    visible: true,
  })
  wrapper.getComponent(DealJourneyDetailSheet).vm.$emit('update:visible', false)
  await nextTick()
  expect(document.activeElement).toBe(trigger)
})
```

Add the same payload assertion for board `row-click`.

- [ ] **Step 5: Implement Sheet and focus wiring**

Before opening, capture `document.activeElement` when it is an HTMLElement. On close, clear selected state, await `nextTick`, and focus the captured element when `isConnected`.

- [ ] **Step 6: Run Task 6 tests**

```bash
cd CRM-Client && npx vitest run \
  tests/components/DealJourneyDetailHost.spec.ts \
  tests/components/DealJourneyDetailSheet.spec.ts \
  tests/components/DealJourneyDetailContent.spec.ts \
  tests/components/BusinessJourneys.spec.ts \
  tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add CRM-Client/src/components/business-journey/DealJourneyDetailHost.vue CRM-Client/src/views/DealJourneyDetailSheet.vue CRM-Client/src/components/panels/DealJourneyDetailContent.vue CRM-Client/src/views/CustomerDetailSheet.vue CRM-Client/src/views/BusinessJourneys.vue CRM-Client/tests/components/DealJourneyDetailHost.spec.ts CRM-Client/tests/components/DealJourneyDetailSheet.spec.ts CRM-Client/tests/components/DealJourneyDetailContent.spec.ts CRM-Client/tests/components/BusinessJourneys.spec.ts CRM-Client/tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts
git commit -m "feat(journey): reuse journey workbench in independent sheet"
```

---

### Task 7: Cut over navigation, router, and legacy board entry

**Files:**
- Modify: `CRM-Client/src/components/app-sidebar/AppSidebar.vue`
- Modify: `CRM-Client/src/router/index.ts`
- Modify: `CRM-Client/src/AppLayout.vue`
- Modify: `CRM-Client/tests/components/AppLayout.spec.ts`
- Create: `CRM-Client/src/components/app-sidebar/__tests__/AppSidebar.test.ts`
- Modify: `CRM-Docs/design-system/patterns/kanban-page.md`
- Modify: `CRM-Server/app/main.py`
- Delete: `CRM-Client/src/views/BusinessJourneyBoard.vue`
- Delete: `CRM-Client/src/api/businessJourneyBoard.ts`
- Delete: `CRM-Client/src/schemas/businessJourneyBoard.ts`
- Delete: `CRM-Client/src/utils/businessJourneyBoardFilters.ts`
- Delete: `CRM-Client/src/utils/__tests__/businessJourneyBoardFilters.test.ts`
- Delete: `CRM-Server/app/api/business_journey_board.py`
- Delete: `CRM-Server/tests/unit/api/test_business_journey_board_date_filters.py`

**Navigation exact structure:**

```text
销售工作: AI Agent, 线索管理, 客户管理, 客户追踪, 业务旅程
交易管理: 商机管理, 合同管理, 回款计划
财务管理: 回款管理, 发票管理
数据看板: 销售看板 (permission gated)
```

```typescript
const canViewBusinessJourneys = computed(() => (
  permissionStore.loadState === 'idle'
  || permissionStore.loadState === 'loading'
  || permissionStore.hasAnyPermission([
    'customer:view:all', 'customer:view:own',
    'opportunity:view:all', 'opportunity:view:own',
  ])
))
```

Permission error state hides the item. Default roles with journey access carry own/all codes; customer membership remains an API row expansion, not a sidebar capability request.

- [ ] **Step 1: Write RED navigation/router tests**

Create `AppSidebar.test.ts` with a typed `NavMain` stub and assert:

```typescript
expect(groupLabels()).toEqual(['销售工作', '交易管理', '财务管理', '数据看板'])
expect(items('销售工作')).toEqual(['AI Agent', '线索管理', '客户管理', '客户追踪', '业务旅程'])
expect(items('交易管理')).toEqual(['商机管理', '合同管理', '回款计划'])
expect(items('财务管理')).toEqual(['回款管理', '发票管理'])
expect(items('数据看板')).toEqual(['销售看板'])
expect(pathFor('业务旅程')).toBe('/business-journeys')
expect(wrapper.text()).not.toContain('业务看板')
```

Add permission assertions: ready with no customer/opportunity codes hides 业务旅程; idle/loading show it; error hides it.

In `AppLayout.spec.ts`, assert router source contains `name: 'BusinessJourneys'`, title「业务旅程」, no `business-journey-board`, and fixed workspace includes `BusinessJourneys` but not `BusinessJourneyBoard`.

- [ ] **Step 2: Run RED**

```bash
cd CRM-Client && npx vitest run tests/components/AppLayout.spec.ts src/components/app-sidebar/__tests__/AppSidebar.test.ts
```

Expected: old groups / route.

- [ ] **Step 3: Implement navigation and route cutover**

Use `GitBranch` for 业务旅程 and existing icons for other items. Route `/business-journeys`, name `BusinessJourneys`, component `BusinessJourneys.vue`, title「业务旅程」. Delete old route rather than redirect. Remove `BusinessJourneyBoard` from fixed route names.

- [ ] **Step 4: Delete old entries and update docs**

Remove old frontend files, old backend router registration/module/test, and update `kanban-page.md` to define the board as a mode of `/business-journeys`; visual rules remain unchanged.

Search runtime for `/business-journey-board`, `BusinessJourneyBoard`, `businessJourneyBoardApi`, `业务看板`; runtime matches must be zero. `business-journey-board.board` may remain only in migration 136 and migration tests.

- [ ] **Step 5: Run Task 7 tests**

```bash
cd CRM-Client && npx vitest run tests/components/AppLayout.spec.ts src/components/app-sidebar/__tests__/AppSidebar.test.ts tests/components/BusinessJourneys.spec.ts
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add CRM-Client/src/components/app-sidebar/AppSidebar.vue CRM-Client/src/router/index.ts CRM-Client/src/AppLayout.vue CRM-Client/tests/components/AppLayout.spec.ts CRM-Client/src/components/app-sidebar/__tests__/AppSidebar.test.ts CRM-Docs/design-system/patterns/kanban-page.md CRM-Server/app/main.py
git rm CRM-Client/src/views/BusinessJourneyBoard.vue CRM-Client/src/api/businessJourneyBoard.ts CRM-Client/src/schemas/businessJourneyBoard.ts CRM-Client/src/utils/businessJourneyBoardFilters.ts CRM-Client/src/utils/__tests__/businessJourneyBoardFilters.test.ts CRM-Server/app/api/business_journey_board.py CRM-Server/tests/unit/api/test_business_journey_board_date_filters.py
git commit -m "feat(navigation): group sales work and transaction records"
```

---

### Task 8: Final verification and real UI smoke

**Files:**
- No planned production edits
- Mark design spec implemented only after every check and smoke pass

- [ ] **Step 1: Backend focused suite**

```bash
cd CRM-Server && .venv/bin/python -m pytest \
  tests/unit/test_view_preferences_api.py \
  tests/unit/test_business_journey_saved_view_migration.py \
  tests/unit/test_business_journey_query_service.py \
  tests/unit/api/test_business_journeys_api.py \
  tests/unit/api/test_business_journey_visibility.py \
  tests/unit/test_business_journey_board_stages.py \
  tests/unit/test_backend_business_scenarios.py \
  tests/unit/list_query/test_catalog_manifest.py -q --no-cov
```

Expected: pass.

- [ ] **Step 2: Frontend focused suite**

```bash
cd CRM-Client && npx vitest run \
  src/composables/__tests__/useCustomFilterViews.spec.ts \
  src/components/crmwolf/__tests__/ListAdvancedTools.test.ts \
  src/components/crmwolf/__tests__/overlayPanelChrome.test.ts \
  src/components/crmwolf/__tests__/listFieldCatalog.test.ts \
  src/schemas/__tests__/dealJourneyPage.test.ts \
  tests/components/BusinessJourneys.spec.ts \
  tests/components/BusinessJourneyBoardView.spec.ts \
  tests/components/DealJourneyDetailHost.spec.ts \
  tests/components/DealJourneyDetailSheet.spec.ts \
  tests/components/DealJourneyDetailContent.spec.ts \
  tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts \
  tests/components/AppLayout.spec.ts \
  src/components/app-sidebar/__tests__/AppSidebar.test.ts
```

Expected: pass.

- [ ] **Step 3: Generated manifest and type-check**

```bash
cd CRM-Server && .venv/bin/python scripts/generate_list_query_manifest.py
git diff --exit-code -- ../CRM-Client/src/components/crmwolf/listQueryCatalogManifest.json
cd ../CRM-Client && npm run type-check
```

Expected: manifest clean; type-check pass. Any unrelated pre-existing error must be reproduced at the base commit; new journey files must have zero errors.

- [ ] **Step 4: Alembic verification**

```bash
cd CRM-Server && .venv/bin/alembic upgrade head && .venv/bin/alembic current
```

Expected: `136_business_journey_saved_views (head)`.

- [ ] **Step 5: Real browser smoke**

Start worktree backend/frontend through hub. In Chromium:

1. Open `/business-journeys` as Eddie; confirm default DataTable and four system Tabs.
2. Open「视图配置」; switch「看板视图」on; confirm existing board visual.
3. Click board card → direct `DealJourneyDetailSheet`; customer Sheet must not open.
4. Close; switch table; click row → same Host.
5. From journey Host, open contract and payment-plan detail; closing child Sheet returns to journey.
6. Save board-only custom view with no filters; rename / pin via existing Tab controls.
7. Switch built-in Tab to table, enter custom board view, return built-in Tab; table restores.
8. Reload; pinned custom view applies board mode.
9. Confirm sidebar group order and no 业务看板 item.
10. Confirm an unapproved opportunity journey appears and 商机已赢单未签约 shows「即将签约」, not「已完成」.

Capture screenshots: sidebar + table, board, journey Sheet, nested contract/payment detail.

- [ ] **Step 6: Clean-cutover search**

Runtime code must have no old route/view/API references. Allowed matches: migration 136 historical key and migration tests.

```text
/business-journey-board
BusinessJourneyBoard.vue
businessJourneyBoardApi
business-journey-board.board
```

- [ ] **Step 7: Resolve verification defects through their owning Task**

Do not make a generic catch-all commit. Add a failing regression test in the owning Task, fix it, rerun that Task plus Steps 1–4, and commit with that Task’s explicit file list.

- [ ] **Step 8: Mark design implemented**

After Steps 1–7 pass:

```bash
git add docs/superpowers/specs/2026-09-20-business-journey-page-navigation-view-config-design.md
git commit -m "docs(journey): mark unified journey page implemented"
```

---

## Spec Coverage

| Spec requirement | Task |
|---|---|
| Navigation groups / names | 7 |
| Independent `/business-journeys` page | 5, 7 |
| Default table + board view | 5 |
| Reuse existing controls / no duplicate components | 4, 5, 6 |
| `display_mode` saved / restored | 1, 4 |
| Built-in tabs temporary / custom views persisted | 4, 5 |
| Save board-only view without filters | 4, 5 |
| Shared permission/query semantics | 2, 3 |
| List / board same dataset | 2, 3 |
| Direct journey Sheet | 5, 6 |
| Reuse one `DealJourneyDetailContent` | 6 |
| Migrate legacy board views | 1 |
| Remove old route/menu/API | 7 |
| Visual reuse and browser proof | 5, 8 |

## Execution Handoff

Plan complete at `docs/superpowers/plans/2026-09-20-business-journey-page-navigation-view-config-plan.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — fresh implementer + task review for each Task
2. **Inline Execution** — execute Task-by-Task in this session with checkpoints
