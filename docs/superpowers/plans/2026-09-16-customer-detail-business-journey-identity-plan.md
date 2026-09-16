# 客户详情业务旅程身份 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 客户详情第四页签和客户列表 hover 以业务旅程为身份；商机详情瘦成商机对象页；旅程对外使用 `djy_` public_id。

**Architecture:** 写路径不动。加 `CustomerDealJourney.public_id` 和客户下薄读接口。阶段推断从看板抽出共用函数。前端拆 `DealJourneyDetailContent` / `DealJourneysPanel`，瘦身 `OpportunityDetailContent`，hover 改旅程预览。

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic, Vue 3, TypeScript, Zod, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-09-16-customer-detail-business-journey-identity-design.md`

## Global Constraints

- 不改无关脏工作区。只改本计划列出的文件。
- 不改写接口语义、权限码、旅程事件模型。
- 不做独立旅程管理页、看板点进详情、共享/解绑 UI。
- 不把合同/回款/发票/License 聚合进旅程读接口。
- 合同、活动、承诺响应里的内部 `deal_journey_id` 本期不改。
- 看板 `journey_id` 本期仍为内部 int。
- 客户详情 footer / 空态按钮文案仍是「新建商机」。
- 产品面默认 1:1；无主商机不请求合同。
- 对外身份一律 `djy_` + 32 hex。内部 int 不得出现在新读接口、客户详情栈、商机响应 `deal_journey_id`。
- 前端禁止 `any`、`as any`、`@ts-ignore` 和无必要的非空断言。
- 中间任务只跑本任务写明的聚焦测试。不要跑全量 lint / type-check / 浏览器 smoke，除非步骤写明。
- 错误文案必须逐字：路径非法或找不到 → `业务旅程不存在`（404）。

## 文件结构与职责

- Create: `CRM-Server/migrations/versions/135_deal_journey_public_ids.py` — 列、回填、唯一索引。
- Modify: `CRM-Server/app/utils/public_id.py` — `djy_` 模式与 `is_deal_journey_public_id`。
- Modify: `CRM-Server/app/models/deal_journey.py` — `public_id` 列与 ORM default。
- Create: `CRM-Server/app/services/deal_journey_stage.py` — 共用阶段推断与合同/回款/发票摘要加载。
- Modify: `CRM-Server/app/api/business_journey_board.py` — 改用抽出的推断/摘要。
- Create: `CRM-Server/app/crud/deal_journey.py` — `get_by_public_id` / `list_by_customer`。
- Create: `CRM-Server/app/schemas/deal_journey.py` — 列表/详情 schema。
- Create: `CRM-Server/app/api/customer_deal_journeys.py` — `GET .../deal-journeys` 与单条。
- Modify: `CRM-Server/app/main.py` — include 新 router。
- Modify: `CRM-Server/app/schemas/opportunity.py`、`CRM-Server/app/api/opportunities.py` — 对外 `deal_journey_id` 改为 public_id。
- Create: `CRM-Client/src/utils/dealJourney.ts` — public_id 校验与阶段进度映射。
- Create: `CRM-Client/src/api/dealJourney.ts`、`CRM-Client/src/schemas/dealJourney.ts`。
- Create: `CRM-Client/src/components/panels/DealJourneysPanel.vue`。
- Create: `CRM-Client/src/components/panels/DealJourneyDetailContent.vue`。
- Modify: `CRM-Client/src/views/CustomerDetailSheet.vue`、`Customers.vue`、`OpportunityDetailContent.vue`、`OpportunityDetailSheet.vue`、`DetailContextHeader.vue`、`detailContext.ts`、`customerRoutes.ts`。
- Rename: `CustomerOpportunityHoverCard.vue` → `CustomerDealJourneyHoverCard.vue`。
- Delete: `CRM-Client/src/components/panels/OpportunitiesPanel.vue`（迁完无引用后）。

---

### Task 1: 旅程 public_id 列、生成器、迁移、模型

**Files:**
- Modify: `CRM-Server/app/utils/public_id.py`
- Modify: `CRM-Server/app/models/deal_journey.py`
- Create: `CRM-Server/migrations/versions/135_deal_journey_public_ids.py`
- Create: `CRM-Server/tests/unit/test_deal_journey_public_id.py`

**Interfaces:**
- Consumes: `generate_public_id(prefix: str) -> str`
- Produces: `DEAL_JOURNEY_PUBLIC_ID_PATTERN`; `is_deal_journey_public_id(value: object) -> bool`; `CustomerDealJourney.public_id: str` default `generate_public_id("djy")`; Alembic revision `135_deal_journey_public_ids` down_revision `134_lead_customer_product_intent`

- [ ] **Step 1: Write failing tests**

Create `CRM-Server/tests/unit/test_deal_journey_public_id.py`:

```python
from app.utils.public_id import generate_public_id, is_deal_journey_public_id


def test_generate_deal_journey_public_id_matches_pattern() -> None:
    value = generate_public_id("djy")
    assert is_deal_journey_public_id(value)


def test_is_deal_journey_public_id_rejects_internal_id_and_opportunity_id() -> None:
    assert is_deal_journey_public_id("12") is False
    assert is_deal_journey_public_id(12) is False
    assert is_deal_journey_public_id("opp_" + "a" * 32) is False
    assert is_deal_journey_public_id("") is False
```

Add migration revision-chain test in the same file. Do not run live Alembic against sqlite here; backfill is the 066-style SELECT/UPDATE in `upgrade()`, and ORM default is covered when association tests create journeys in Step 4.

```python
import importlib.util
from pathlib import Path
from types import ModuleType


def _load_migration() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "135_deal_journey_public_ids.py"
    )
    spec = importlib.util.spec_from_file_location("deal_journey_public_ids_135", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_revision_chain() -> None:
    migration = _load_migration()
    assert migration.revision == "135_deal_journey_public_ids"
    assert migration.down_revision == "134_lead_customer_product_intent"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd CRM-Server && python -m pytest tests/unit/test_deal_journey_public_id.py -v`

Expected: FAIL — `is_deal_journey_public_id` 未定义；migration 文件不存在。

- [ ] **Step 3: Implement generator, model, migration**

In `CRM-Server/app/utils/public_id.py` after `OPPORTUNITY_PUBLIC_ID_PATTERN`:

```python
DEAL_JOURNEY_PUBLIC_ID_PATTERN = re.compile(r"^djy_[0-9a-f]{32}$")
```

After `is_opportunity_public_id`:

```python
def is_deal_journey_public_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(DEAL_JOURNEY_PUBLIC_ID_PATTERN.fullmatch(value))
```

In `CRM-Server/app/models/deal_journey.py` import `generate_public_id` from `app.utils.public_id`. Add column after `id`:

```python
public_id = Column(
    String(64),
    nullable=False,
    unique=True,
    index=True,
    default=lambda: generate_public_id("djy"),
    comment="对外业务旅程ID",
)
```

Create `CRM-Server/migrations/versions/135_deal_journey_public_ids.py` copying the structure of `066_opportunity_public_ids.py`:

- `revision = "135_deal_journey_public_ids"`
- `down_revision = "134_lead_customer_product_intent"`
- table `crm_customer_deal_journeys`
- index `uq_crm_customer_deal_journeys_public_id`
- backfill `djy_{uuid4().hex}`
- comment `对外业务旅程ID`

- [ ] **Step 4: Run tests**

Run: `cd CRM-Server && python -m pytest tests/unit/test_deal_journey_public_id.py tests/unit/test_business_journey_board_stages.py tests/unit/test_deal_journey_association_service.py -v`

Expected: PASS. association 测试创建旅程时 ORM default 自动带 `public_id`。

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/utils/public_id.py CRM-Server/app/models/deal_journey.py CRM-Server/migrations/versions/135_deal_journey_public_ids.py CRM-Server/tests/unit/test_deal_journey_public_id.py
git commit -m "feat(journey): add deal journey public_id"
```

---

### Task 2: 抽出阶段推断；客户下旅程读接口

**Files:**
- Create: `CRM-Server/app/services/deal_journey_stage.py`
- Create: `CRM-Server/app/crud/deal_journey.py`
- Create: `CRM-Server/app/schemas/deal_journey.py`
- Create: `CRM-Server/app/api/customer_deal_journeys.py`
- Modify: `CRM-Server/app/api/business_journey_board.py`
- Modify: `CRM-Server/app/main.py`
- Modify: `CRM-Server/tests/unit/test_business_journey_board_stages.py`
- Create: `CRM-Server/tests/unit/api/test_customer_deal_journeys.py`

**Interfaces:**
- Consumes: `CustomerDealJourney`, `Opportunity`, contract/payment/invoice models, `check_customer_view_permission`, `is_deal_journey_public_id`
- Produces:
  - `BoardStageKey` Literal 与看板相同 8 值
  - `BOARD_STAGE_LABELS: dict[BoardStageKey, str]`
  - `infer_board_stage(journey, opportunity, contract_summary, payment_summary, invoice_summary) -> BoardStageKey`
  - `infer_active_opportunity_stage(opportunity) -> BoardStageKey`
  - `load_contract_summaries` / `load_payment_summaries` / `load_invoice_summaries`（签名与看板现有私有函数相同，返回类型复用看板 Pydantic 模型或同形 dataclass）
  - `deal_journey_crud.get_by_public_id(db, public_id: str, team_id: int, customer_id: int | None = None) -> CustomerDealJourney | None`
  - `deal_journey_crud.list_by_customer(db, *, team_id: int, customer_id: int) -> list[CustomerDealJourney]` — 排除 `ARCHIVED`，排序 `last_event_at DESC NULLS LAST, id DESC`
  - `GET /v1/customers/{customer_public_id}/deal-journeys` → `list[CustomerDealJourneyResponse]`
  - `GET /v1/customers/{customer_public_id}/deal-journeys/{journey_public_id}` → `CustomerDealJourneyResponse`
  - `CustomerDealJourneyResponse`: `id`/`public_id` 均为 `djy_…`；`name`; `status`; `current_board_stage`; `current_board_stage_label`; `amount: float`（主商机 `total_amount`，无主商机 `0`）；`purchase_type: str | None`; `started_at`/`closed_at`/`last_event_at`; `primary_opportunity: CustomerDealJourneyOpportunitySummary | None`
  - `CustomerDealJourneyOpportunitySummary`: `public_id`; `opportunity_name`; `status`; `approval_phase`; `win_probability`; `expected_closing_date`; `product_name: str | None`

客户列表 `amount` **不要**用看板 `_journey_amount`（那会优先合同额）。按 spec 用主商机 `total_amount`。

- [ ] **Step 1: Redirect existing stage tests to the new module, add API tests that fail**

Change `CRM-Server/tests/unit/test_business_journey_board_stages.py` imports from `app.api.business_journey_board` `_infer_stage` / `_infer_active_opportunity_stage` to `app.services.deal_journey_stage` `infer_board_stage` / `infer_active_opportunity_stage`. Keep `BOARD_COLUMNS` import from the board API.

Create `CRM-Server/tests/unit/api/test_customer_deal_journeys.py` using the same sqlite `api_env` pattern as `tests/unit/api/test_business_journey_board_date_filters.py`, but:

- include `customer_deal_journeys.router` and `customers` permission deps
- override `check_customer_view_permission` to return the seeded customer or raise 403
- seed journeys **without** requiring `OPPORTUNITY_APPROVED`

Minimum cases:

```python
def test_list_includes_unapproved_opportunity_journey(api_env):
    # approval_phase = draft, no OPPORTUNITY_APPROVED event
    # GET /v1/customers/{cus}/deal-journeys → 200, contains that journey
    # body[0]["id"] startswith "djy_"
    # "current_board_stage" == "early_communication" when win_probability < 50

def test_list_excludes_archived(api_env):
    # ARCHIVED journey not in list

def test_detail_404_for_internal_id_and_wrong_prefix(api_env):
    response = api_env.client.get(f"/v1/customers/{cus}/deal-journeys/12")
    assert response.status_code == 404
    assert response.json()["detail"] == "业务旅程不存在"
    response = api_env.client.get(f"/v1/customers/{cus}/deal-journeys/opp_{'a'*32}")
    assert response.status_code == 404

def test_detail_404_for_other_customer_journey(api_env):
    # journey belongs to customer B; request under customer A → 404

def test_list_forbidden_without_view_permission(api_env):
    # override check_customer_view_permission to HTTPException 403
```

- [ ] **Step 2: Run tests, expect FAIL**

Run: `cd CRM-Server && python -m pytest tests/unit/test_business_journey_board_stages.py tests/unit/api/test_customer_deal_journeys.py -v`

Expected: FAIL — 新模块/路由不存在。

- [ ] **Step 3: Implement**

Move `_infer_stage`, `_infer_active_opportunity_stage`, `_load_contract_summaries`, `_load_payment_summaries`, `_load_invoice_summaries` and the summary Pydantic models they need into `app/services/deal_journey_stage.py`. Board API becomes a thin importer/wrapper so existing board tests keep passing. Rename public functions as listed in Interfaces.

`deal_journey_crud.list_by_customer` must query via CRUD, not in the API file.

`customer_deal_journeys.py`:

```python
router = APIRouter(prefix="/v1/customers", tags=["客户业务旅程"])

@router.get("/{customer_public_id}/deal-journeys", response_model=list[CustomerDealJourneyResponse])
def list_customer_deal_journeys(...):
    customer = check_customer_view_permission(customer_public_id, team_id, current_user, db)
    journeys = deal_journey_crud.list_by_customer(db, team_id=team_id, customer_id=int(customer.id))
    return [_to_response(db, team_id, journeys)]

@router.get("/{customer_public_id}/deal-journeys/{journey_public_id}", response_model=CustomerDealJourneyResponse)
def get_customer_deal_journey(...):
    if not is_deal_journey_public_id(journey_public_id):
        raise HTTPException(status_code=404, detail="业务旅程不存在")
    customer = check_customer_view_permission(...)
    journey = deal_journey_crud.get_by_public_id(db, journey_public_id, team_id, customer_id=int(customer.id))
    if journey is None:
        raise HTTPException(status_code=404, detail="业务旅程不存在")
    return _to_response(...)
```

Stage for each journey: load summaries for the returned ids in one batch, then `infer_board_stage`. Primary opportunity: `Opportunity` via `primary_opportunity_id`（CRUD 里 `selectinload` 或二次查询按 id in）。`product_name` 来自 `opportunity.product.name` if loaded.

In `app/main.py` after `customers.router`:

```python
api_router.include_router(customer_deal_journeys.router)
```

Add the import.

- [ ] **Step 4: Run tests**

Run: `cd CRM-Server && python -m pytest tests/unit/test_business_journey_board_stages.py tests/unit/api/test_business_journey_board_date_filters.py tests/unit/api/test_customer_deal_journeys.py -v`

Expected: PASS. 看板日期筛选仍过，证明抽出没有改看板过滤。

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/deal_journey_stage.py CRM-Server/app/crud/deal_journey.py CRM-Server/app/schemas/deal_journey.py CRM-Server/app/api/customer_deal_journeys.py CRM-Server/app/api/business_journey_board.py CRM-Server/app/main.py CRM-Server/tests/unit/test_business_journey_board_stages.py CRM-Server/tests/unit/api/test_customer_deal_journeys.py
git commit -m "feat(journey): add customer deal-journey read API"
```

---

### Task 3: 商机对外 deal_journey_id 改为 public_id

**Files:**
- Modify: `CRM-Server/app/schemas/opportunity.py`
- Modify: `CRM-Server/app/api/opportunities.py`
- Modify: `CRM-Server/tests/unit/test_customer_business_object_intelligence_api.py`

**Interfaces:**
- Consumes: `deal_journey_crud.get_by_public_id`; `is_deal_journey_public_id`
- Produces: `OpportunityResponse.deal_journey_id: str | None`（`djy_…`）；`OpportunityDealJourneyUpdate.deal_journey_id: str | None`；PATCH 非法格式 404「业务旅程不存在」；associate 仍吃内部 int（handler 先解析）

- [ ] **Step 1: Update PATCH tests to public_id and add 404 case**

In `test_update_opportunity_deal_journey_passes_expected_version_and_returns_new_version`:

- seed/mock a journey with `id=22`, `public_id="djy_" + "b"*32`
- request body `deal_journey_id` is that public_id
- `fake_associate` still receives internal `deal_journey_id=22`
- `result.deal_journey_id` equals the public_id string

Add:

```python
async def test_update_opportunity_deal_journey_rejects_internal_id(monkeypatch) -> None:
    # OpportunityDealJourneyUpdate(deal_journey_id="22")
    # expect HTTPException 404 detail 业务旅程不存在
    # associate not called
```

`OpportunityDealJourneyUpdate` 字段改为 `str | None`，去掉 `ge=1`。非法非 `djy_` 在 **handler** 里 404，不要在 schema validator 里 422——spec 要求与商机路径校验一致（404）。

- [ ] **Step 2: Run, expect FAIL**

Run: `cd CRM-Server && python -m pytest tests/unit/test_customer_business_object_intelligence_api.py::test_update_opportunity_deal_journey_passes_expected_version_and_returns_new_version tests/unit/test_customer_business_object_intelligence_api.py::test_update_opportunity_deal_journey_maps_stale_version_to_conflict tests/unit/test_customer_business_object_intelligence_api.py::test_update_opportunity_deal_journey_rejects_internal_id -v`

- [ ] **Step 3: Implement serialization and PATCH resolve**

`OpportunityResponse.deal_journey_id: Optional[str]`

`_opportunity_response_dict`：若 `opportunity.deal_journey_id` 有值，查 `deal_journey_crud.get_by_public_id` 的反向——加 `deal_journey_crud.get_by_id(db, journey_id, team_id)` 返回 ORM，取 `.public_id`。不要在响应里回内部 int。

PATCH handler:

```python
if journey_update.deal_journey_id is None:
    deal_journey_service.detach_opportunity(...)
else:
    if not is_deal_journey_public_id(journey_update.deal_journey_id):
        raise HTTPException(status_code=404, detail="业务旅程不存在")
    target = deal_journey_crud.get_by_public_id(
        db, journey_update.deal_journey_id, db_opportunity.team_id, customer_id=db_opportunity.customer_id
    )
    if target is None:
        raise HTTPException(status_code=404, detail="业务旅程不存在")
    deal_journey_service.associate_opportunity(..., deal_journey_id=int(target.id), ...)
```

列表/详情所有走 `_opportunity_response_dict` 的路径一起变。列表循环里不要 N+1：本任务可在 `_opportunity_response_dict` 单条查；若列表测试变慢，用一次 `id IN` map。优先在 `_opportunity_response_dict` 接受可选 `journey_public_id: str | None`，列表接口预加载 map。

- [ ] **Step 4: Run tests**

Run: `cd CRM-Server && python -m pytest tests/unit/test_customer_business_object_intelligence_api.py tests/unit/test_deal_journey_association_service.py -v`

Expected: PASS。service 层仍用内部 int。

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/schemas/opportunity.py CRM-Server/app/api/opportunities.py CRM-Server/app/crud/deal_journey.py CRM-Server/tests/unit/test_customer_business_object_intelligence_api.py
git commit -m "feat(opportunity): expose deal journey public_id"
```

---

### Task 4: 前端旅程类型、API、进度映射

**Files:**
- Create: `CRM-Client/src/utils/dealJourney.ts`
- Create: `CRM-Client/src/utils/__tests__/dealJourney.test.ts`
- Create: `CRM-Client/src/schemas/dealJourney.ts`
- Create: `CRM-Client/src/api/dealJourney.ts`
- Modify: `CRM-Client/src/api/opportunity.ts`
- Modify: `CRM-Client/src/schemas/opportunity.ts`

**Interfaces:**
- Produces:
  - `isDealJourneyPublicId(value: string): boolean` — `^djy_[0-9a-f]{32}$`
  - `DealJourneyBoardStage` union 8 keys
  - `DEAL_JOURNEY_BOARD_STAGE_LABELS: Record<DealJourneyBoardStage, string>`
  - `dealJourneyProgressPercent(stage: DealJourneyBoardStage): number` — 14/29/43/57/71/86/100；`lost` 返回 `0`（调用方不渲染输单预览）
  - `dealJourneyApi.listByCustomer(customerId: string): Promise<DealJourney[]>`
  - `dealJourneyApi.getByCustomer(customerId: string, journeyPublicId: string): Promise<DealJourney>`
  - `Opportunity.deal_journey_id?: string | null`
  - `OpportunityListResponse.deal_journey_id?: string | null`

进度表必须逐字：

| stage | percent |
|---|---|
| early_communication | 14 |
| active_progress | 29 |
| closing_soon | 43 |
| contract_processing | 57 |
| payment_processing | 71 |
| invoice_processing | 86 |
| completed | 100 |
| lost | 0 |

- [ ] **Step 1: Write failing util tests**

```typescript
import { describe, expect, it } from 'vitest'
import { dealJourneyProgressPercent, isDealJourneyPublicId } from '@/utils/dealJourney'

describe('dealJourney', () => {
  it('accepts djy public ids only', () => {
    expect(isDealJourneyPublicId(`djy_${'a'.repeat(32)}`)).toBe(true)
    expect(isDealJourneyPublicId('12')).toBe(false)
    expect(isDealJourneyPublicId(`opp_${'a'.repeat(32)}`)).toBe(false)
  })

  it('maps board stages to hover progress', () => {
    expect(dealJourneyProgressPercent('early_communication')).toBe(14)
    expect(dealJourneyProgressPercent('closing_soon')).toBe(43)
    expect(dealJourneyProgressPercent('completed')).toBe(100)
  })
})
```

- [ ] **Step 2: Run, expect FAIL**

Run: `cd CRM-Client && npx vitest run src/utils/__tests__/dealJourney.test.ts`

- [ ] **Step 3: Implement utils, zod schema, api, opportunity field**

`dealJourneyApi` 使用 `request.get` + zod parse，路径：

- `GET /v1/customers/${customerId}/deal-journeys`
- `GET /v1/customers/${customerId}/deal-journeys/${journeyPublicId}`

Opportunity Zod：`deal_journey_id: z.string().nullable().optional()`。接口类型同步。

- [ ] **Step 4: Run tests**

Run: `cd CRM-Client && npx vitest run src/utils/__tests__/dealJourney.test.ts`

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/utils/dealJourney.ts CRM-Client/src/utils/__tests__/dealJourney.test.ts CRM-Client/src/schemas/dealJourney.ts CRM-Client/src/api/dealJourney.ts CRM-Client/src/api/opportunity.ts CRM-Client/src/schemas/opportunity.ts
git commit -m "feat(client): add deal journey API and progress map"
```

---

### Task 5: 客户详情页签、列表、栈改为旅程

**Files:**
- Create: `CRM-Client/src/components/panels/DealJourneysPanel.vue`
- Modify: `CRM-Client/src/types/detailContext.ts`
- Modify: `CRM-Client/src/components/crmwolf/DetailContextHeader.vue`
- Modify: `CRM-Client/src/views/CustomerDetailSheet.vue`
- Modify: `CRM-Client/tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts`
- Delete: `CRM-Client/src/components/panels/OpportunitiesPanel.vue`（本任务末尾无引用后）

**Interfaces:**
- Consumes: `dealJourneyApi.listByCustomer`; `DealJourney`
- Produces: panel key `'journeys'`；`targetJourneyId?: string | null`；`targetOpportunityId` 仍可传入，解析为该商机 `deal_journey_id`；栈类型 `'journey'`；`DealJourneysPanel` emit `'view': [journeyPublicId: string]` 与 `'add'`

本任务详情内容可先挂一个最小 `DealJourneyDetailContent` 占位（只显示旅程名称 + `data-testid="deal-journey-detail"`），Task 6 填满。不要继续挂 `OpportunityDetailContent` 当客户内详情。

- [ ] **Step 1: Rewrite drilldown spec to journey**

Rename describe to `CustomerDetailSheet journey drilldown`（文件名可暂留，避免 git 噪音；或 rename 为 `CustomerDetailSheet.journey-drilldown.spec.ts`）。

- mock `dealJourneyApi.listByCustomer` / `getByCustomer`
- mock `DealJourneysPanel` 发出 `view`
- mock 占位 `DealJourneyDetailContent`
- 断言第四页签文案「业务旅程」
- 断言点击行后 `data-testid="deal-journey-detail"` 出现
- 从旅程打开合同时 `parentType` 为 `journey`（若测试读栈，断言 header 含业务旅程）
- `targetOpportunityId`：mock 商机列表或详情带 `deal_journey_id: 'djy_…'`，打开对应旅程
- footer「新建商机」仍在 `activePanel === 'journeys'`
- 不再 mock/渲染 `OpportunitiesPanel`

- [ ] **Step 2: Run, expect FAIL**

Run: `cd CRM-Client && npx vitest run tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts`

- [ ] **Step 3: Implement sheet + panel**

`DealJourneysPanel.vue` 仿 `OpportunitiesPanel.vue`：

- title `业务旅程`
- empty `暂无业务旅程`
- itemMain: `item.name`
- itemMeta: `current_board_stage_label` · `AmountText` · 采购类型文案（NEW/RENEWAL/EXPANSION → 新购/续购/增购）；`purchase_type === null` 不显示类型
- row-click emit `view` with `item.public_id`
- header/empty 新建商机仍 emit `add`

`CustomerDetailSheet`:

- `navTabs` 第四项 `{ key: 'journeys', label: '业务旅程' }`
- 加载 `dealJourneyApi.listByCustomer` 替代 `opportunityApi.getOpportunities`
- `selectedJourneyId`
- `createJourneyContextNode`
- `handleViewJourney`
- `handleViewContractFromJourney`：`parentType: 'journey'`
- 嵌套详情：`selectedJourneyId !== null` 时渲染 `DealJourneyDetailContent`
- props: `targetJourneyId`；`targetPanel` 含 `'journeys'`；去掉 `'opportunities'`
- `targetOpportunityId`：在已加载旅程列表里找 `primary_opportunity.public_id === targetOpportunityId`，打开其旅程；找不到则停在列表
- 高亮/焦点恢复改用 `highlightedJourneyId`

`DetailObjectType` 增加 `'journey'`。header 标签 `业务旅程`。`opportunity` 类型可留着给独立商机页，客户栈不再 push。

- [ ] **Step 4: Run tests**

Run: `cd CRM-Client && npx vitest run tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts`

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/components/panels/DealJourneysPanel.vue CRM-Client/src/components/panels/DealJourneyDetailContent.vue CRM-Client/src/views/CustomerDetailSheet.vue CRM-Client/src/types/detailContext.ts CRM-Client/src/components/crmwolf/DetailContextHeader.vue CRM-Client/tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts
git rm CRM-Client/src/components/panels/OpportunitiesPanel.vue
git commit -m "feat(customer): hang deal journeys in customer detail"
```

---

### Task 6: 旅程详情履约工作台 + 商机行 icon

**Files:**
- Modify: `CRM-Client/src/components/panels/DealJourneyDetailContent.vue`
- Create: `CRM-Client/tests/components/DealJourneyDetailContent.spec.ts`

**Interfaces:**
- Consumes: `dealJourneyApi.getByCustomer`; `opportunityApi.getOpportunity`; existing contract/payment/invoice/license fetch 与 `OpportunityDetailContent` 现在相同（按 `primary_opportunity.public_id`）
- Produces: 顶栏阶段+类型；正文基本信息、审批进度、商机进度、商机 ListCard（编辑/赢单/输单 icon）、合同/回款/发票/许可申请；页脚无这三项；emit `view-contract` / `view-payment-plan` / `create-contract` / `refresh` / `back` / `close`

商机行 icon 顺序：编辑、赢单、输单。显隐：`canEditOpportunity && !pending && !rejected`；`isActive && canWin && approved`；`isActive && canLose && approved`。弹窗复用 `OpportunityFormDialog` / `OpportunityWinDialog` / `OpportunityLoseDialog`。

无主商机：不请求商机/合同；三块空态文案「该旅程暂无主商机」。

- [ ] **Step 1: Write failing component tests**

```typescript
it('shows board stage and purchase type in the header, not win/lose footer')
it('renders opportunity row action icons when approved and following')
it('does not fetch contracts when primary_opportunity is null')
```

断言：

- header 含 `即将签约`（或 fixture 的 `current_board_stage_label`）和 `新购`
- 无 footer 按钮文案「赢单」「输单」「编辑」作为页脚主按钮（icon `aria-label` 可以含这些词）
- `getContractByOpportunity` 在无主商机时 `not.toHaveBeenCalled`

- [ ] **Step 2: Run, expect FAIL**

Run: `cd CRM-Client && npx vitest run tests/components/DealJourneyDetailContent.spec.ts`

- [ ] **Step 3: Port the fulfillment body from OpportunityDetailContent**

从 `OpportunityDetailContent.vue` 复制审批/阶段/合同/回款/发票/License 加载与面板，数据源改为旅程 `primary_opportunity`。顶栏按 spec 7.2。商机 ListCard 单行，数据用主商机。

不要在本任务瘦身 `OpportunityDetailContent`（下一任务）。允许短暂重复。

- [ ] **Step 4: Run tests**

Run: `cd CRM-Client && npx vitest run tests/components/DealJourneyDetailContent.spec.ts tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts`

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/components/panels/DealJourneyDetailContent.vue CRM-Client/tests/components/DealJourneyDetailContent.spec.ts CRM-Client/src/views/CustomerDetailSheet.vue
git commit -m "feat(journey): add deal journey fulfillment detail"
```

---

### Task 7: 瘦身商机详情；查看业务旅程

**Files:**
- Modify: `CRM-Client/src/components/panels/OpportunityDetailContent.vue`
- Modify: `CRM-Client/src/views/OpportunityDetailSheet.vue`
- Modify: `CRM-Client/src/utils/customerRoutes.ts`
- Modify: `CRM-Client/src/views/Customers.vue`
- Modify: `CRM-Client/tests/components/OpportunityDetailContent.experience.spec.ts`

**Interfaces:**
- Produces: emit `'view-journey': [{ customerId: string, journeyPublicId: string }]`；`customerDetailRoute(customerId, { tab: 'journeys', journeyId })`；`Customers.vue` 读取 `route.query.customerId` / `tab` / `journeyId` / 兼容旧 `opportunityId`（若有）打开 sheet

- [ ] **Step 1: Replace license tests with slim-detail tests**

Delete `shows expired and valid customer licenses together on opportunity detail` and `does not pretend license applications are empty when the list request fails`.

Add:

```typescript
it('does not load contracts, payments, invoices, or licenses')
it('emits view-journey when deal_journey_id is present')
it('hides view-journey when deal_journey_id is null')
```

`getContractByOpportunity` / `getPaymentPlans` / `getInvoiceApplications` / `licenseApplicationApi.list` 在加载后 `not.toHaveBeenCalled`。

有 `deal_journey_id` 时点击 `data-testid="view-deal-journey"` emit `view-journey`。

- [ ] **Step 2: Run, expect FAIL**

Run: `cd CRM-Client && npx vitest run tests/components/OpportunityDetailContent.experience.spec.ts`

- [ ] **Step 3: Slim the component and wire deep link**

从 `OpportunityDetailContent` 删除合同/回款/发票/License 的 import、state、fetch、template、相关 dialog。保留基本信息、审批、阶段步进、页脚编辑/赢/输。

顶栏加：

```vue
<button
  v-if="opportunity.deal_journey_id"
  type="button"
  class="..."
  data-testid="view-deal-journey"
  @click="emit('view-journey', { customerId: opportunity.customer_id, journeyPublicId: opportunity.deal_journey_id })"
>
  查看业务旅程
</button>
```

`OpportunityDetailSheet`：监听 `view-journey`，`router.push(customerDetailRoute(payload.customerId, { tab: 'journeys', journeyId: payload.journeyPublicId }))` 并 close。

`Customers.vue`：用 `useRoute`。watch `route.query.customerId`：有值则 `selectedCustomerId = customerId`；`tab === 'journeys'` 则 `targetPanel = 'journeys'`；`journeyId` 合法 `djy_` 则 `targetJourneyId`。点名称打开详情时清这些 target。

扩展 `customerDetailRoute` 的 query 类型注释即可，已接受 `LocationQueryRaw`。

- [ ] **Step 4: Run tests**

Run: `cd CRM-Client && npx vitest run tests/components/OpportunityDetailContent.experience.spec.ts tests/views/OpportunityDetailSheet.content-reuse.spec.ts tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts`

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/components/panels/OpportunityDetailContent.vue CRM-Client/src/views/OpportunityDetailSheet.vue CRM-Client/src/utils/customerRoutes.ts CRM-Client/src/views/Customers.vue CRM-Client/tests/components/OpportunityDetailContent.experience.spec.ts
git commit -m "feat(opportunity): slim detail and link to deal journey"
```

---

### Task 8: 客户列表 hover 改为旅程预览

**Files:**
- Rename: `CRM-Client/src/components/customer/CustomerOpportunityHoverCard.vue` → `CustomerDealJourneyHoverCard.vue`
- Rename: `CRM-Client/tests/components/CustomerOpportunityHoverCard.spec.ts` → `CustomerDealJourneyHoverCard.spec.ts`
- Modify: `CRM-Client/src/views/Customers.vue`

**Interfaces:**
- Consumes: `dealJourneyApi.listByCustomer`
- Produces: emit `'select-journey': [journeyPublicId: string]`；`'view-all': []`；预览排除 `status === 'LOST' | 'ARCHIVED'`，最多 3 条；进度 `dealJourneyProgressPercent`；不渲染「赢率」

- [ ] **Step 1: Rewrite hover tests**

- mock `dealJourneyApi.listByCustomer`
- 打开后请求旅程列表，不请求 `getOpportunities`
- 断言名称旁是金额，条下是阶段徽章
- `expect(wrapper.text()).not.toContain('赢率')`
- 点击行 emit `select-journey` with `djy_…`
- 空态「暂无业务旅程」
- 输单旅程不出现
- `completed` 进度 `aria-label` 含 `100%`

- [ ] **Step 2: Run, expect FAIL**

Run: `cd CRM-Client && npx vitest run tests/components/CustomerDealJourneyHoverCard.spec.ts`

- [ ] **Step 3: Implement hover + Customers wiring**

布局按 spec 7.5：

```text
旅程名称                          金额
进度条
看板阶段徽章                      >
```

产品名作 caption 可保留在名称下。`aria-label`：`${name} 旅程进度 ${percent}%`。footer「查看全部业务旅程」。

`Customers.vue`：`openCustomerJourney(customerId, journeyPublicId)` 设 `targetPanel='journeys'`、`targetJourneyId`。`openCustomerJourneys` 只开页签。删除 `openCustomerOpportunity`。

- [ ] **Step 4: Run tests**

Run: `cd CRM-Client && npx vitest run tests/components/CustomerDealJourneyHoverCard.spec.ts tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts`

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/components/customer/CustomerDealJourneyHoverCard.vue CRM-Client/tests/components/CustomerDealJourneyHoverCard.spec.ts CRM-Client/src/views/Customers.vue
git rm CRM-Client/src/components/customer/CustomerOpportunityHoverCard.vue CRM-Client/tests/components/CustomerOpportunityHoverCard.spec.ts
git commit -m "feat(customer): preview deal journeys on name hover"
```

---

### Task 9: 收口引用、文案、定向回归

**Files:**
- Grep 清理：`项目旅程`、`OpportunitiesPanel`、`CustomerOpportunityHoverCard`、`openCustomerOpportunity`、`activePanel === 'opportunities'`
- Modify remaining copy：审批区「审批进度」、阶段区「商机进度」（旅程详情 + 瘦商机详情）
- Modify: `docs/ux/p1-packages/04-object-context-hierarchy.md` 对象栈改为 `客户 → 业务旅程 → 合同 → 回款`（一句，避免文档与产品打架）

- [ ] **Step 1: Grep leftovers**

Search `OpportunitiesPanel`, `项目旅程`, `CustomerOpportunityHoverCard`, `openCustomerOpportunity`, `'opportunities'` in `CRM-Client/src` and tests. Fix or delete each hit in scope. Do not rewrite 档案投影内部 `deal_journey_id` int。

- [ ] **Step 2: Run focused regression**

```bash
cd CRM-Server && python -m pytest tests/unit/test_deal_journey_public_id.py tests/unit/test_business_journey_board_stages.py tests/unit/api/test_customer_deal_journeys.py tests/unit/api/test_business_journey_board_date_filters.py tests/unit/test_customer_business_object_intelligence_api.py tests/unit/test_deal_journey_association_service.py -v
cd CRM-Client && npx vitest run src/utils/__tests__/dealJourney.test.ts tests/components/DealJourneyDetailContent.spec.ts tests/components/CustomerDealJourneyHoverCard.spec.ts tests/components/OpportunityDetailContent.experience.spec.ts tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts tests/views/OpportunityDetailSheet.content-reuse.spec.ts
```

Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add -u
git commit -m "refactor(customer): finish deal journey identity cutover"
```

---

## Spec coverage

| Spec | Task |
|---|---|
| §5 public_id 列/生成/迁移 | 1 |
| §6 客户下读接口、未审批仍列出、阶段共用推断 | 2 |
| §5.3 / §6 商机 `deal_journey_id` 改为 public_id、PATCH | 3 |
| §7.5 进度映射、前端 API | 4 |
| §7.1 页签/列表/栈 | 5 |
| §7.2 旅程详情 + 商机行 icon | 6 |
| §7.3 瘦身商机详情 + 查看业务旅程 | 7 |
| §7.5 hover | 8 |
| 文案、引用清理、P1-PKG-04 栈 | 9 |
| 非目标（管理页、看板跳转、聚合读、新建旅程按钮） | 不实施 |

## 风险（实现时记住）

- 客户列表 `amount` 用主商机总额，不是看板的合同优先额。
- PATCH 非法 id 必须 404 不是 422。
- `OpportunityDetailContent` 现有 experience 测试里 `opportunityId: 88` 与 `id: string` 不一致；瘦身时改成 `opp_` fixture，顺手修调用。
- `Customers.vue` 现在不读 `route.query.customerId`。Task 7 必须接上，否则「查看业务旅程」深链是空的。
