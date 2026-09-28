# Payment Record Contract Fields and Permission Grouping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在回款管理页完整支持关联合同的授权模式、采购类型，并在角色权限配置中把回款、回款计划、回款记录权限合并到统一“回款”展示组。

**Architecture:** 后端继续从 `PaymentRecord → PaymentPlan → Contract → Opportunity` 实时投影字段，不新增数据库列；list-query catalog、响应 schema、批量列表投影和 export catalog 分别承担筛排、接口与导出契约。前端仅扩展 `PaymentRecords.vue` 的字段注册表和单元格展示，不向通用 `DataTable.vue` 写入业务特例；角色配置通过共享权限分组 helper 统一两个入口。

**Tech Stack:** Vue 3, TypeScript, Vitest, Vue Test Utils, Pinia, FastAPI, Pydantic 2, SQLAlchemy, pytest, Ruff, MyPy, openpyxl.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-09-28-payment-record-contract-fields-permission-grouping-design.md`.
- `license_type` 必须来自 `Contract.license_type`；`purchase_type` 必须来自关联合同的 `Opportunity.purchase_type`。
- 两列默认显示，顺序固定在“合同名称”之后：先“授权模式”，再“采购类型”。
- 两列必须完整支持服务端筛选、服务端排序、字段配置、自定义视图和 Excel 导出。
- 不把两个枚举加入统一文本搜索。
- 不修改 `DataTable.vue`，除非执行时证明其现有通用投影存在缺陷；禁止加入回款字段特例。
- 不修改数据库结构、权限码、permission resource、默认角色授权或 Alembic migration。
- `payment`、`payment_plan`、`payment_record` 只在角色配置展示层合并为 `payment`；保存时仍提交原始 permission id。
- 保留工作区所有无关改动；每次提交只暂存本任务列出的文件。
- 所有生产代码遵循红—绿—重构：先运行并确认新增测试因缺失行为失败，再写最小实现。

## File Structure

### Backend query and response

- Modify `CRM-Server/app/core/list_query/catalogs/payment_records.py` — 注册两个 enum 查询字段。
- Modify `CRM-Server/app/schemas/payment.py` — 扩展公开回款响应 schema。
- Modify `CRM-Server/app/api/payments.py` — 列表、详情、写入响应及导出行投影。
- Modify `CRM-Server/tests/unit/test_payment_list_query_crud.py` — 锁定两个字段的筛选、排序和分页前语义。
- Modify `CRM-Server/tests/test_payment_record_list.py` — 锁定列表 API 字段投影和空值兼容。
- Modify `CRM-Server/tests/unit/test_payment_approval_api.py` — 锁定更新响应使用同一字段合同。

### Backend export and generated contracts

- Modify `CRM-Server/app/core/list_export/catalogs/payment_records.py` — 注册两个导出字段。
- Modify `CRM-Server/tests/unit/test_payment_export_api.py` — 锁定中文导出值和缺失商机空值。
- Modify `CRM-Server/tests/unit/list_query/test_catalog_manifest.py` — 锁定 list-query manifest。
- Modify `CRM-Server/tests/unit/list_export/test_catalog_manifest.py` — 锁定 list-export manifest。
- Regenerate `CRM-Client/src/components/crmwolf/listQueryCatalogManifest.json`.
- Regenerate `CRM-Client/src/components/crmwolf/listExportCatalogManifest.json`.

### Frontend payment records

- Modify `CRM-Client/src/api/payment.ts` — 声明两个可空枚举字段。
- Modify `CRM-Client/src/views/PaymentRecords.vue` — 字段注册表、桌面 slot、移动卡片标签和样式。
- Create `CRM-Client/src/views/__tests__/PaymentRecords.contractFields.test.ts` — 挂载真实页面并验证字段合同与可见标签。
- Reuse existing `CRM-Client/src/components/crmwolf/__tests__/listPageQueryContract.test.ts` and `listExportContract.test.ts` without adding a second field list.

### Permission grouping

- Modify `CRM-Client/src/constants/permissions.ts` — 唯一的 assignable permission 分组 helper。
- Modify `CRM-Client/src/constants/__tests__/permissions.test.ts` — 锁定合并规则和原始权限保留。
- Modify `CRM-Client/src/views/settings/SettingsRolesPage.vue` — 使用共享 helper。
- Modify `CRM-Client/src/components/system-config/RoleSheet.vue` — 使用同一 helper，删除重复分组实现。
- Modify `CRM-Client/src/views/settings/__tests__/SettingsRolesPage.test.ts` — 验证设置页只出现一个回款组并包含导出回款记录。
- Create `CRM-Client/src/components/system-config/__tests__/RoleSheet.permissionGrouping.test.ts` — 验证旧角色入口使用相同的合并分组行为。

---

### Task 1: Register backend filter and sort fields

**Files:**
- Modify: `CRM-Server/app/core/list_query/catalogs/payment_records.py`
- Modify: `CRM-Server/tests/unit/test_payment_list_query_crud.py`
- Modify: `CRM-Server/tests/unit/list_query/test_catalog_manifest.py`
- Regenerate: `CRM-Client/src/components/crmwolf/listQueryCatalogManifest.json`

**Interfaces:**
- Produces list-query keys `license_type` and `purchase_type`, both `type="enum"`, filterable and sortable.
- Task 4 consumes the generated manifest through existing frontend contract tests.
- Does not change unified search predicates.

- [ ] **Step 1: Make the payment query fixture distinguish both enum fields**

In `_seed_payment_graph()` change only the second opportunity and second contract values:

```python
# Opportunity id=2
license_type="SUBSCRIPTION",
purchase_type="RENEWAL",

# Contract id=2
license_type="PERPETUAL",
```

Keep record `PR-001` on `SUBSCRIPTION / NEW` and record `PR-002` on `PERPETUAL / RENEWAL`.

- [ ] **Step 2: Add failing CRUD behavior tests**

Add this import with the existing list-query imports in `CRM-Server/tests/unit/test_payment_list_query_crud.py`:

```python
from app.core.list_query.errors import ListQueryError
```

Append the behavior tests:

```python
def test_payment_record_contract_license_type_filters_and_sorts_before_pagination(db_session):
    _seed_payment_graph(db_session)

    try:
        filtered, filtered_total = payment_record_crud.list_records(
            db_session,
            team_id=1,
            filters=[{"field": "license_type", "op": "eq", "value": "PERPETUAL"}],
            sorts=[],
        )
        first_page, sorted_total = payment_record_crud.list_records(
            db_session,
            team_id=1,
            skip=0,
            limit=1,
            filters=[],
            sorts=[{"field": "license_type", "direction": "asc"}],
        )
    except ListQueryError as error:
        pytest.fail(str(error))

    assert filtered_total == 1
    assert [record.record_number for record in filtered] == ["PR-002"]
    assert sorted_total == 2
    assert [record.record_number for record in first_page] == ["PR-002"]


def test_payment_record_purchase_type_filters_and_sorts_before_pagination(db_session):
    _seed_payment_graph(db_session)

    try:
        filtered, filtered_total = payment_record_crud.list_records(
            db_session,
            team_id=1,
            filters=[{"field": "purchase_type", "op": "eq", "value": "NEW"}],
            sorts=[],
        )
        first_page, sorted_total = payment_record_crud.list_records(
            db_session,
            team_id=1,
            skip=0,
            limit=1,
            filters=[],
            sorts=[{"field": "purchase_type", "direction": "desc"}],
        )
    except ListQueryError as error:
        pytest.fail(str(error))

    assert filtered_total == 1
    assert [record.record_number for record in filtered] == ["PR-001"]
    assert sorted_total == 2
    assert [record.record_number for record in first_page] == ["PR-002"]
```

- [ ] **Step 3: Add failing manifest assertions**

In `test_build_list_query_manifest_exposes_each_catalog_field_type()` add:

```python
    expected_payment_enum = {
        "type": "enum",
        "filterable": True,
        "sortable": True,
        "ops": ["contains", "eq", "in", "is_empty", "is_not_empty", "neq", "not_contains", "not_in"],
    }
    assert manifest["payment_records"].get("license_type") == expected_payment_enum
    assert manifest["payment_records"].get("purchase_type") == expected_payment_enum
```

- [ ] **Step 4: Run the focused tests and confirm RED**

```bash
cd CRM-Server
.venv/bin/python -m pytest \
  tests/unit/test_payment_list_query_crud.py::test_payment_record_contract_license_type_filters_and_sorts_before_pagination \
  tests/unit/test_payment_list_query_crud.py::test_payment_record_purchase_type_filters_and_sorts_before_pagination \
  tests/unit/list_query/test_catalog_manifest.py::test_build_list_query_manifest_exposes_each_catalog_field_type \
  -q --no-cov
```

Expected: the CRUD tests fail with `未知筛选字段: license_type` / `purchase_type`, and the manifest test fails because the keys are absent.

- [ ] **Step 5: Register the two backend fields**

In `CRM-Server/app/core/list_query/catalogs/payment_records.py` add the import:

```python
from app.models.opportunity import Opportunity
```

Immediately after `contract_name`, add:

```python
        ListQueryField(key="license_type", type="enum", expression=Contract.license_type),
        ListQueryField(key="purchase_type", type="enum", expression=Opportunity.purchase_type),
```

Do not add either expression to `keyword_predicate()` or `text_search_predicate()`.

- [ ] **Step 6: Regenerate the query manifest**

```bash
cd CRM-Server
.venv/bin/python scripts/generate_list_query_manifest.py
```

Expected: `CRM-Client/src/components/crmwolf/listQueryCatalogManifest.json` gains enum entries for both payment-record fields.

- [ ] **Step 7: Run the focused and manifest consistency tests**

```bash
cd CRM-Server
.venv/bin/python -m pytest \
  tests/unit/test_payment_list_query_crud.py::test_payment_record_contract_license_type_filters_and_sorts_before_pagination \
  tests/unit/test_payment_list_query_crud.py::test_payment_record_purchase_type_filters_and_sorts_before_pagination \
  tests/unit/list_query/test_catalog_manifest.py \
  -q --no-cov
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit the query contract**

```bash
git add \
  CRM-Server/app/core/list_query/catalogs/payment_records.py \
  CRM-Server/tests/unit/test_payment_list_query_crud.py \
  CRM-Server/tests/unit/list_query/test_catalog_manifest.py \
  CRM-Client/src/components/crmwolf/listQueryCatalogManifest.json
git commit -m "feat(payments): query records by contract fields"
```

---

### Task 2: Project contract fields into every payment-record response

**Files:**
- Modify: `CRM-Server/app/schemas/payment.py`
- Modify: `CRM-Server/app/api/payments.py`
- Modify: `CRM-Server/tests/test_payment_record_list.py`
- Modify: `CRM-Server/tests/unit/test_payment_approval_api.py`

**Interfaces:**
- Produces nullable response fields `license_type` and `purchase_type` on `PaymentRecordResponse`, inherited by list and detail responses.
- `_payment_record_response()` covers create/update/detail/plan-record responses.
- `_build_payment_record_list_items()` covers paginated list and export batch projection.

- [ ] **Step 1: Seed a real customer and opportunity in the list API fixture**

At the start of `seed_contract_plan()` in `CRM-Server/tests/test_payment_record_list.py`, before the contract is added, insert:

```python
    customer = Customer(
        id=1,
        public_id="cus_00000000000000000000000000000001",
        team_id=1,
        account_name="测试客户",
        city="上海",
        owner_id="1",
        creator_id="1",
    )
    opportunity = Opportunity(
        id=1,
        public_id="opp_00000000000000000000000000000001",
        team_id=1,
        opportunity_number="OPP-2026-001",
        opportunity_name="测试商机",
        customer_id=1,
        total_amount=100000,
        user_count=10,
        unit_price=10000,
        license_type="PERPETUAL",
        purchase_type="RENEWAL",
        expected_closing_date=date(2026, 8, 31),
        owner_id="1",
        creator_id="1",
    )
    db_session.add_all([customer, opportunity])
    db_session.flush()
```

Change the fixture contract to:

```python
        license_type="PERPETUAL",
```

- [ ] **Step 2: Add failing list response assertions, including null compatibility**

Append this test after `test_payment_record_list_all`:

```python
def test_payment_record_list_projects_contract_license_and_purchase_type(
    client, seed_payment_records, patched_deps
):
    patched_deps(["payment:view:all"])

    response = client.get("/v1/payments/payment-records")

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items
    assert {item.get("license_type") for item in items} == {"PERPETUAL"}
    assert {item.get("purchase_type") for item in items} == {"RENEWAL"}
```

In `test_payment_record_list_includes_record_number`, add:

```python
    assert "license_type" in item
    assert item["license_type"] is None
    assert "purchase_type" in item
    assert item["purchase_type"] is None
```

- [ ] **Step 3: Seed the update-response fixture and add failing assertions**

At the start of `seed_contract_plan()` in `CRM-Server/tests/unit/test_payment_approval_api.py`, before creating the contract, insert:

```python
    db_session.add(Customer(
        id=1,
        public_id="cus_00000000000000000000000000000001",
        team_id=1,
        account_name="测试客户",
        city="上海",
        owner_id="1",
        creator_id="1",
    ))
    db_session.add(Opportunity(
        id=1,
        public_id="opp_00000000000000000000000000000001",
        team_id=1,
        opportunity_number="OPP-2026-001",
        opportunity_name="测试商机",
        customer_id=1,
        total_amount=100000,
        user_count=10,
        unit_price=10000,
        license_type="PERPETUAL",
        purchase_type="EXPANSION",
        expected_closing_date=__import__("datetime").date(2026, 8, 31),
        owner_id="1",
        creator_id="1",
    ))
    db_session.flush()
```

Change that fixture contract to `license_type="PERPETUAL"`. In `test_update_payment_record_creator_can_edit_after_withdraw`, add:

```python
    assert body.get("license_type") == "PERPETUAL"
    assert body.get("purchase_type") == "EXPANSION"
```

- [ ] **Step 4: Run the response tests and confirm RED**

```bash
cd CRM-Server
.venv/bin/python -m pytest \
  tests/test_payment_record_list.py::test_payment_record_list_projects_contract_license_and_purchase_type \
  tests/test_payment_record_list.py::test_payment_record_list_includes_record_number \
  tests/unit/test_payment_approval_api.py::test_update_payment_record_creator_can_edit_after_withdraw \
  -q --no-cov
```

Expected: responses either omit the new keys or return `None` for the seeded contract/opportunity values.

- [ ] **Step 5: Extend the Pydantic response schema**

In `PaymentRecordResponse`, after the contract and opportunity identity fields, add:

```python
    license_type: Optional[str] = Field(None, description="关联合同授权模式：SUBSCRIPTION/PERPETUAL")
    purchase_type: Optional[str] = Field(None, description="关联合同商机采购类型：NEW/RENEWAL/EXPANSION")
```

- [ ] **Step 6: Extend both response projection paths**

In `_payment_record_response()` add:

```python
        "license_type": contract.license_type if contract else None,
        "purchase_type": opportunity.purchase_type if opportunity else None,
```

In `_build_payment_record_list_items()` add to `item_dict`:

```python
            "license_type": contract.license_type if contract is not None else None,
            "purchase_type": opportunity.purchase_type if opportunity is not None else None,
```

Place the values next to `contract_name` / `opportunity_name`, not near unrelated payment fields.

- [ ] **Step 7: Run the response tests and nearby regressions**

```bash
cd CRM-Server
.venv/bin/python -m pytest \
  tests/test_payment_record_list.py \
  tests/test_payment_record_invoice_title.py \
  tests/unit/test_payment_approval_api.py::test_update_payment_record_creator_can_edit_after_withdraw \
  -q --no-cov
```

Expected: all selected tests pass, including the legacy lightweight record returning `None` for both fields.

- [ ] **Step 8: Commit the response contract**

```bash
git add \
  CRM-Server/app/schemas/payment.py \
  CRM-Server/app/api/payments.py \
  CRM-Server/tests/test_payment_record_list.py \
  CRM-Server/tests/unit/test_payment_approval_api.py
git commit -m "feat(payments): expose contract fields on records"
```

---

### Task 3: Export the new fields with localized values

**Files:**
- Modify: `CRM-Server/app/core/list_export/catalogs/payment_records.py`
- Modify: `CRM-Server/app/api/payments.py`
- Modify: `CRM-Server/tests/unit/test_payment_export_api.py`
- Modify: `CRM-Server/tests/unit/list_export/test_catalog_manifest.py`
- Regenerate: `CRM-Client/src/components/crmwolf/listExportCatalogManifest.json`

**Interfaces:**
- Produces export keys `license_type` and `purchase_type`.
- Workbook values are `订阅` / `买断` and `新购` / `续购` / `增购`; missing opportunity stays blank.
- Keeps `payment:record:export` and existing view scope unchanged.

- [ ] **Step 1: Parameterize existing export seed helpers**

Extend `_seed_opportunity()` with:

```python
    purchase_type: str = "NEW",
```

and replace its hard-coded value with:

```python
            purchase_type=purchase_type,
```

Extend `_seed_contract()` with:

```python
    license_type: str = "SUBSCRIPTION",
```

and replace its hard-coded value with:

```python
            license_type=license_type,
```

- [ ] **Step 2: Add a failing localized export test**

Append to `CRM-Server/tests/unit/test_payment_export_api.py`:

```python
def test_payment_record_export_maps_contract_fields_and_blanks_missing_opportunity(
    client,
    db_session,
    monkeypatch,
):
    _grant(monkeypatch, "payment:record:export", "payment:view:all")
    _seed_user(db_session, user_id=1, name="销售张")
    _seed_customer(db_session, customer_id=1, account_name="客户A")
    _seed_customer(db_session, customer_id=2, account_name="客户B")
    _seed_opportunity(
        db_session,
        opportunity_id=1,
        customer_id=1,
        owner_id="1",
        purchase_type="RENEWAL",
    )
    _seed_contract(
        db_session,
        contract_id=1,
        customer_id=1,
        opportunity_id=1,
        license_type="PERPETUAL",
    )
    _seed_contract(
        db_session,
        contract_id=2,
        customer_id=2,
        opportunity_id=999,
        contract_name="无商机合同",
        license_type="SUBSCRIPTION",
    )
    _seed_plan(db_session, id=1, contract_id=1, plan_number="PP-LABELED")
    _seed_plan(db_session, id=2, contract_id=2, plan_number="PP-MISSING")
    _seed_record(
        db_session,
        id=1,
        record_number="PR-LABELED",
        payment_plan_id=1,
        payment_date=date(2026, 8, 11),
    )
    _seed_record(
        db_session,
        id=2,
        record_number="PR-MISSING",
        payment_plan_id=2,
        payment_date=date(2026, 8, 10),
    )
    db_session.commit()

    response = client.post("/v1/payments/payment-records/export", json={
        "fields": ["record_number", "license_type", "purchase_type"],
        "tab": "all",
        "filters": [],
        "sorts": [],
    })

    assert response.status_code == 200, response.text
    rows = _workbook_rows(response)
    assert rows == [
        ("回款编号", "授权模式", "采购类型"),
        ("PR-LABELED", "买断", "续购"),
        ("PR-MISSING", "订阅", None),
    ]
```

- [ ] **Step 3: Add failing export-manifest assertions**

In `test_manifest_contains_user_facing_contract()` add:

```python
    assert manifest["payment_records"].get("license_type") == {"label": "授权模式", "type": "text"}
    assert manifest["payment_records"].get("purchase_type") == {"label": "采购类型", "type": "text"}
```

- [ ] **Step 4: Run export tests and confirm RED**

```bash
cd CRM-Server
.venv/bin/python -m pytest \
  tests/unit/test_payment_export_api.py::test_payment_record_export_maps_contract_fields_and_blanks_missing_opportunity \
  tests/unit/list_export/test_catalog_manifest.py::test_manifest_contains_user_facing_contract \
  -q --no-cov
```

Expected: export returns 400 for unknown selected fields, and the manifest assertions fail because both keys are absent.

- [ ] **Step 5: Add export labels and row projection**

Near `PAYMENT_RECORD_STATUS_LABELS` in `CRM-Server/app/api/payments.py`, add:

```python
LICENSE_TYPE_LABELS = {
    "SUBSCRIPTION": "订阅",
    "PERPETUAL": "买断",
}
PURCHASE_TYPE_LABELS = {
    "NEW": "新购",
    "RENEWAL": "续购",
    "EXPANSION": "增购",
}
```

In `_payment_record_export_row()` normalize and map the values:

```python
    license_type = _enum_value(item.get("license_type"))
    purchase_type = _enum_value(item.get("purchase_type"))
```

Add to the returned mapping immediately after `contract_name`:

```python
        "license_type": LICENSE_TYPE_LABELS.get(license_type, license_type),
        "purchase_type": PURCHASE_TYPE_LABELS.get(purchase_type, purchase_type),
```

Unknown non-empty values remain visible as raw values; `None` remains an empty workbook cell.

- [ ] **Step 6: Register export fields and regenerate the manifest**

In `PAYMENT_RECORDS_LIST_EXPORT_CATALOG`, immediately after `contract_name`, add:

```python
        ListExportField("license_type", "授权模式", "text"),
        ListExportField("purchase_type", "采购类型", "text"),
```

Then run:

```bash
cd CRM-Server
.venv/bin/python scripts/generate_list_export_manifest.py
```

- [ ] **Step 7: Run export and catalog regressions**

```bash
cd CRM-Server
.venv/bin/python -m pytest \
  tests/unit/test_payment_export_api.py \
  tests/unit/list_export/test_catalog_manifest.py \
  -q --no-cov
```

Expected: all selected tests pass, including existing permission and view-own export tests.

- [ ] **Step 8: Commit the export contract**

```bash
git add \
  CRM-Server/app/core/list_export/catalogs/payment_records.py \
  CRM-Server/app/api/payments.py \
  CRM-Server/tests/unit/test_payment_export_api.py \
  CRM-Server/tests/unit/list_export/test_catalog_manifest.py \
  CRM-Client/src/components/crmwolf/listExportCatalogManifest.json
git commit -m "feat(payments): export record contract fields"
```

---

### Task 4: Render and register the fields on PaymentRecords

**Files:**
- Modify: `CRM-Client/src/api/payment.ts`
- Modify: `CRM-Client/src/views/PaymentRecords.vue`
- Create: `CRM-Client/src/views/__tests__/PaymentRecords.contractFields.test.ts`
- Test existing: `CRM-Client/src/components/crmwolf/__tests__/listPageQueryContract.test.ts`
- Test existing: `CRM-Client/src/components/crmwolf/__tests__/listExportContract.test.ts`

**Interfaces:**
- `PaymentRecordResponse.license_type?: LicenseType | null`.
- `PaymentRecordResponse.purchase_type?: PurchaseType | null`.
- The page field registry is the only source for columns, filters, sorts, column preferences and export candidates.
- Desktop and mobile reuse `StatusBadge` types `authorizationMode` and `procurementType`.

- [ ] **Step 1: Create a failing mounted page test**

Create `CRM-Client/src/views/__tests__/PaymentRecords.contractFields.test.ts`:

```typescript
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  listPaymentRecords: vi.fn(),
  loadCustomViews: vi.fn(),
}))

const headerStore = vi.hoisted(() => ({
  activeTab: 'all',
  setActiveTab: vi.fn(),
  setTabs: vi.fn(),
  setActions: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/api/payment', () => ({
  default: {
    listPaymentRecords: mocks.listPaymentRecords,
    exportPaymentRecords: vi.fn(),
    updatePaymentRecord: vi.fn(),
    deletePaymentRecord: vi.fn(),
  },
}))

vi.mock('@/stores/permissions', () => ({
  usePermissionStore: () => ({
    hasPermission: () => true,
    hasAnyPermission: () => true,
  }),
}))

vi.mock('@/stores/approval', () => ({
  useApprovalStore: () => ({ submitEntity: vi.fn() }),
}))

vi.mock('@/stores/header', () => ({
  useHeaderStore: () => headerStore,
}))

vi.mock('@/stores/user', () => ({
  useUserStore: () => ({ userInfo: { id: 1 } }),
}))

vi.mock('@/composables/usePageTitle', () => ({ usePageTitle: () => undefined }))
vi.mock('@/composables/useTopBarRegistration', () => ({ useTopBarRegistration: () => undefined }))
vi.mock('@/composables/useDataTableExport', () => ({
  useDataTableExport: () => ({ exportFields: vi.fn() }),
}))

vi.mock('@/composables/useCustomFilterViews', async () => {
  const { ref } = await import('vue')
  return {
    isCustomFilterViewTab: () => false,
    useCustomFilterViews: () => ({
      saving: ref(false),
      applying: ref(false),
      applyError: ref(null),
      mergeTabs: (tabs: unknown[]) => tabs,
      loadCustomViews: mocks.loadCustomViews,
      updateActiveCustomViewConfig: vi.fn().mockResolvedValue(undefined),
      saveAsCustomView: vi.fn().mockResolvedValue(undefined),
      saveActiveCustomViewColumns: vi.fn().mockResolvedValue(undefined),
      consumeFailedViewApply: () => false,
      applyCustomViewTab: () => false,
      applyBuiltInTab: () => false,
      retryViewApply: vi.fn().mockResolvedValue(undefined),
    }),
  }
})

vi.mock('@/components/crmwolf', async () => {
  const { defineComponent, h } = await import('vue')
  const DataTable = defineComponent({
    name: 'DataTable',
    props: {
      fields: { type: Array, default: () => [] },
      data: { type: Array, default: () => [] },
    },
    setup(props, { slots }) {
      return () => h('div', { 'data-testid': 'payment-records-table' },
        (props.data as Array<Record<string, unknown>>).map((row, index) => h('section', { key: String(row['id']) }, [
          h('div', { 'data-testid': `desktop-license-${row['id']}` },
            slots['cell-license_type']?.({ row, value: row['license_type'] })),
          h('div', { 'data-testid': `desktop-purchase-${row['id']}` },
            slots['cell-purchase_type']?.({ row, value: row['purchase_type'] })),
          h('div', { 'data-testid': `mobile-${row['id']}` },
            slots['mobile-card']?.({ row, index })),
        ])),
      )
    },
  })
  const AmountText = defineComponent({
    name: 'AmountText',
    props: ['value'],
    setup: (props) => () => h('span', String(props.value ?? '')),
  })
  const TableRowActions = defineComponent({ name: 'TableRowActions', setup: () => () => h('div') })
  return { DataTable, AmountText, TableRowActions }
})

vi.mock('@/views/PaymentRecordDetailSheet.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return { default: defineComponent({ name: 'PaymentRecordDetailSheet', setup: () => () => h('div') }) }
})

vi.mock('@/components/dialogs/EditRecordDialog.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return { default: defineComponent({ name: 'EditRecordDialog', setup: () => () => h('div') }) }
})

vi.mock('vue-sonner', () => ({ toast: { info: vi.fn(), success: vi.fn() } }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

import PaymentRecords from '@/views/PaymentRecords.vue'

const record = (overrides: Record<string, unknown>) => ({
  id: 1,
  payment_plan_id: 10,
  record_number: 'PAY-001',
  actual_amount: 1200,
  payment_date: '2026-09-28',
  created_time: '2026-09-28T10:00:00',
  last_modified_time: '2026-09-28T10:00:00',
  confirmation_status: 'PENDING',
  customer_name: '测试客户',
  contract_name: '测试合同',
  ...overrides,
})

describe('PaymentRecords contract fields', () => {
  beforeEach(() => {
    mocks.listPaymentRecords.mockReset().mockResolvedValue({
      items: [
        record({ id: 1, license_type: 'SUBSCRIPTION', purchase_type: 'RENEWAL' }),
        record({ id: 2, record_number: 'PAY-002', license_type: null, purchase_type: null }),
      ],
      total: 2,
      page: 1,
      page_size: 20,
      total_pages: 1,
    })
    mocks.loadCustomViews.mockReset().mockResolvedValue(undefined)
    headerStore.activeTab = 'all'
  })

  it('registers both enum fields after contract name with full DataTable capabilities', async () => {
    const wrapper = mount(PaymentRecords)
    await flushPromises()

    const fields = wrapper.getComponent({ name: 'DataTable' }).props('fields') as Array<Record<string, unknown>>
    const contractIndex = fields.findIndex(field => field['key'] === 'contract_name')
    const licenseIndex = fields.findIndex(field => field['key'] === 'license_type')
    const purchaseIndex = fields.findIndex(field => field['key'] === 'purchase_type')

    expect(licenseIndex).toBe(contractIndex + 1)
    expect(purchaseIndex).toBe(licenseIndex + 1)
    expect(fields[licenseIndex]).toMatchObject({
      key: 'license_type',
      label: '授权模式',
      type: 'enum',
      filter: true,
      sort: true,
      column: { align: 'center', width: '110px' },
    })
    expect(fields[purchaseIndex]).toMatchObject({
      key: 'purchase_type',
      label: '采购类型',
      type: 'enum',
      filter: true,
      sort: true,
      column: { align: 'center', width: '110px' },
    })
  })

  it('renders localized badges and keeps missing mobile values empty', async () => {
    const wrapper = mount(PaymentRecords)
    await flushPromises()

    expect(wrapper.get('[data-testid="desktop-license-1"]').text()).toContain('订阅制')
    expect(wrapper.get('[data-testid="desktop-purchase-1"]').text()).toContain('续购')
    expect(wrapper.get('[data-testid="desktop-license-2"]').text()).toBe('-')
    expect(wrapper.get('[data-testid="desktop-purchase-2"]').text()).toBe('-')

    const populatedMobile = wrapper.get('[data-testid="mobile-1"]')
    const emptyMobile = wrapper.get('[data-testid="mobile-2"]')
    expect(populatedMobile.text()).toContain('订阅制')
    expect(populatedMobile.text()).toContain('续购')
    expect(populatedMobile.findAll('[role="status"]')).toHaveLength(3)
    expect(emptyMobile.findAll('[role="status"]')).toHaveLength(1)
    expect(emptyMobile.text()).not.toContain('未知')
  })
})
```

- [ ] **Step 2: Run the page test and confirm RED**

```bash
cd CRM-Client
npm run test:unit -- src/views/__tests__/PaymentRecords.contractFields.test.ts
```

Expected: the field indexes are `-1`, and the new desktop slot wrappers are empty because the page has not registered or rendered the fields.

- [ ] **Step 3: Extend the payment API type**

At the top of `CRM-Client/src/api/payment.ts` add:

```typescript
import type { LicenseType, PurchaseType } from '@/api/contract'
```

Add to `PaymentRecordResponse`:

```typescript
  license_type?: LicenseType | null
  purchase_type?: PurchaseType | null
```

- [ ] **Step 4: Add enum options and field definitions**

In `PaymentRecords.vue`, before `fields`, add:

```typescript
const licenseTypeOptions = [
  { value: 'SUBSCRIPTION', label: '订阅' },
  { value: 'PERPETUAL', label: '买断' },
]
const purchaseTypeOptions = [
  { value: 'NEW', label: '新购' },
  { value: 'RENEWAL', label: '续购' },
  { value: 'EXPANSION', label: '增购' },
]
```

Immediately after the `contract_name` field, add:

```typescript
  {
    key: 'license_type',
    label: '授权模式',
    type: 'enum',
    options: licenseTypeOptions,
    column: { align: 'center', width: '110px' },
    filter: true,
    sort: true,
  },
  {
    key: 'purchase_type',
    label: '采购类型',
    type: 'enum',
    options: purchaseTypeOptions,
    column: { align: 'center', width: '110px' },
    filter: true,
    sort: true,
  },
```

Do not change the search placeholder or search predicates.

- [ ] **Step 5: Add desktop and mobile rendering**

In the mobile card, after `.payment-record-mobile-card-contract` and before the amount, add:

```vue
        <div v-if="row.license_type || row.purchase_type" class="payment-record-mobile-card-badges">
          <StatusBadge
            v-if="row.license_type"
            :status="row.license_type"
            type="authorizationMode"
            size="small"
          />
          <StatusBadge
            v-if="row.purchase_type"
            :status="row.purchase_type"
            type="procurementType"
            size="small"
          />
        </div>
```

After the `contract_name` cell area, add:

```vue
      <template #cell-license_type="{ row }">
        <StatusBadge
          v-if="row.license_type"
          :status="row.license_type"
          type="authorizationMode"
        />
        <span v-else class="text-muted-foreground">-</span>
      </template>

      <template #cell-purchase_type="{ row }">
        <StatusBadge
          v-if="row.purchase_type"
          :status="row.purchase_type"
          type="procurementType"
        />
        <span v-else class="text-muted-foreground">-</span>
      </template>
```

Add the scoped style:

```scss
.payment-record-mobile-card-badges {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-xs-v2;
  margin-top: $wolf-space-sm-v2;
}
```

- [ ] **Step 6: Run page and cross-layer contract tests**

```bash
cd CRM-Client
npm run test:unit -- \
  src/views/__tests__/PaymentRecords.contractFields.test.ts \
  src/components/crmwolf/__tests__/listPageQueryContract.test.ts \
  src/components/crmwolf/__tests__/listExportContract.test.ts
npm run type-check
```

Expected: all selected Vitest files and `vue-tsc` pass. The generic contract tests prove both new page fields exist in the generated backend manifests.

- [ ] **Step 7: Commit the frontend payment page**

```bash
git add \
  CRM-Client/src/api/payment.ts \
  CRM-Client/src/views/PaymentRecords.vue \
  CRM-Client/src/views/__tests__/PaymentRecords.contractFields.test.ts
git commit -m "feat(payments): show contract fields on records"
```

---

### Task 5: Merge payment permissions into one role-settings group

**Files:**
- Modify: `CRM-Client/src/constants/permissions.ts`
- Modify: `CRM-Client/src/constants/__tests__/permissions.test.ts`
- Modify: `CRM-Client/src/views/settings/SettingsRolesPage.vue`
- Create: `CRM-Client/src/components/system-config/__tests__/RoleSheet.permissionGrouping.test.ts`
- Modify: `CRM-Client/src/components/system-config/RoleSheet.vue`
- Modify: `CRM-Client/src/views/settings/__tests__/SettingsRolesPage.test.ts`

**Interfaces:**
- Produces `PermissionGroup` and `groupAssignablePermissions(permissions)`.
- Normalizes only `payment_plan` and `payment_record` to display resource `payment`.
- Preserves every permission object's original `resource`, id, code, action and scope.

- [ ] **Step 1: Add a failing shared-helper test**

Add this helper below the existing `permission()` helper in `CRM-Client/src/constants/__tests__/permissions.test.ts`:

```typescript
const permissionResponse = (
  id: number,
  code: string,
  resource: string,
  name: string,
  action: string,
  isActive = true,
) => ({
  id,
  code,
  name,
  resource,
  action,
  scope: null,
  description: null,
  is_active: isActive,
  created_at: '2026-09-28T00:00:00Z',
  updated_at: '2026-09-28T00:00:00Z',
})
```

Add a dynamic-import test so the initial RED is an assertion failure rather than a missing-export collection error:

```typescript
  it('groups payment, payment_plan, and payment_record under one payment display group', async () => {
    const permissionsModule = await import('@/constants/permissions')
    const candidate = (permissionsModule as unknown as Record<string, unknown>)['groupAssignablePermissions']
    expect(candidate).toBeTypeOf('function')
    if (typeof candidate !== 'function') return

    const groups = candidate([
      permissionResponse(1, 'payment:approve', 'payment', '审批回款', 'approve'),
      permissionResponse(2, 'payment:plan:export', 'payment_plan', '导出回款计划', 'export'),
      permissionResponse(3, 'payment:record:export', 'payment_record', '导出回款记录', 'export'),
      permissionResponse(4, 'customer:view:all', 'customer', '查看所有客户', 'view'),
      permissionResponse(5, 'payment:api:list', 'api', '旧回款 API', 'view'),
    ]) as Array<{ resource: string; permissions: Array<{ code: string; resource: string }> }>

    expect(groups.map(group => group.resource)).toEqual(['payment', 'customer'])
    const paymentGroup = groups[0]
    expect(paymentGroup?.permissions.map(item => item.code)).toEqual([
      'payment:approve',
      'payment:plan:export',
      'payment:record:export',
    ])
    expect(paymentGroup?.permissions.map(item => item.resource)).toEqual([
      'payment',
      'payment_plan',
      'payment_record',
    ])
  })
```

- [ ] **Step 2: Extend the settings-page test harness and add failing UI behavior**

1. Import `defineComponent` and `h` from `vue`.
2. Add `getRole` and `getAllPermissions` to the hoisted mocks.
3. Return `getRole` from the `@/api/role` mock and `getAllPermissions` from the `@/api/permissions` mock.
4. Replace the current template-only DataTable stub with this component:

```typescript
const DataTableStub = defineComponent({
  name: 'DataTable',
  props: {
    data: { type: Array, default: () => [] },
    getRowActions: { type: Function, required: true },
  },
  setup(props) {
    return () => h('div', { 'data-testid': 'roles-table' },
      (props.data as Array<Record<string, unknown>>).flatMap(row => {
        const actions = props.getRowActions(row) as {
          primaryActions?: Array<{ handler?: (value: Record<string, unknown>) => void }>
        }
        return [
          h('div', { key: `name-${row['id']}` }, String(row['name'])),
          h('button', {
            key: `permissions-${row['id']}`,
            'data-testid': `permissions-${row['id']}`,
            onClick: () => actions.primaryActions?.[0]?.handler?.(row),
          }, '配置权限'),
        ]
      }),
    )
  },
})
```

Use `DataTable: DataTableStub` in both mounts. Add the test:

```typescript
  it('shows one payment group containing the record export permission', async () => {
    setActivePinia(createPinia())
    const teamStore = useTeamStore()
    const userStore = useUserStore()
    const permissionStore = usePermissionStore()
    teamStore.currentTeam = {
      id: 7,
      name: '演示团队',
      code: 'DEMO',
      owner_id: '42',
      created_at: '2026-01-01T00:00:00Z',
    }
    userStore.userInfo = {
      id: 42,
      name: '团队所有者',
      email: 'owner@example.com',
      status: 'active',
      created_at: null,
      updated_at: null,
    }
    permissionStore.loadState = 'ready'

    const role = {
      id: 1,
      code: 'FINANCE',
      name: '财务人员',
      description: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }
    mocks.getRoles.mockResolvedValue([role])
    mocks.getRole.mockResolvedValue({ ...role, permissions: [] })
    mocks.getAllPermissions.mockResolvedValue([
      permissionResponse(1, 'payment:approve', 'payment', '审批回款', 'approve'),
      permissionResponse(2, 'payment:plan:export', 'payment_plan', '导出回款计划', 'export'),
      permissionResponse(3, 'payment:record:export', 'payment_record', '导出回款记录', 'export'),
    ])

    const wrapper = mount(SettingsRolesPage, {
      global: {
        stubs: {
          DataTable: DataTableStub,
          TableRowActions: true,
          SettingsContent: { template: '<main><slot /></main>' },
          Dialog: { template: '<div><slot /></div>' },
          DialogContent: { template: '<div><slot /></div>' },
          DialogHeader: true,
          DialogTitle: true,
          DialogDescription: true,
          DialogFooter: true,
          FormField: { template: '<div><slot :componentField="{}" /></div>' },
          Checkbox: { template: '<input type="checkbox">' },
          Label: { template: '<label><slot /></label>' },
          Badge: { template: '<span><slot /></span>' },
        },
      },
    })
    await vi.waitFor(() => expect(mocks.getRoles).toHaveBeenCalled())
    await wrapper.get('[data-testid="permissions-1"]').trigger('click')
    await flushPromises()

    const groupHeadings = wrapper.findAll('.font-semibold').map(item => item.text())
    expect(groupHeadings).toContain('回款')
    expect(groupHeadings).not.toContain('回款计划')
    expect(groupHeadings).not.toContain('回款记录')
    expect(wrapper.text()).toContain('导出回款记录')
    expect(wrapper.text()).toContain('payment:record:export')
  })
```

- [ ] **Step 3: Add a failing behavior test for the legacy RoleSheet entrypoint**

Create `CRM-Client/src/components/system-config/__tests__/RoleSheet.permissionGrouping.test.ts`:

```typescript
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  getRoles: vi.fn(),
  getRole: vi.fn(),
  getAllPermissions: vi.fn(),
}))

vi.mock('@/api/role', () => ({
  default: {
    getRoles: mocks.getRoles,
    getRole: mocks.getRole,
    createRole: vi.fn(),
    updateRole: vi.fn(),
    deleteRole: vi.fn(),
    updateRolePermissions: vi.fn(),
  },
}))

vi.mock('@/api/permissions', () => ({
  default: { getAllPermissions: mocks.getAllPermissions },
}))

vi.mock('@/stores/permissions', () => ({
  usePermissionStore: () => ({
    hasPermission: () => true,
    hasAnyPermission: () => true,
  }),
}))

vi.mock('@/composables/useSettingsAccess', async () => {
  const { ref } = await import('vue')
  return { useSettingsAccess: () => ({ isOwner: ref(true) }) }
})

vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('vue-sonner', () => ({ toast: { success: vi.fn() } }))

vi.mock('@/components/crmwolf', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    ListCard: defineComponent({
      name: 'ListCard',
      props: { items: { type: Array, default: () => [] } },
      setup(props, { slots }) {
        return () => h('div', (props.items as Array<Record<string, unknown>>).map(item => h('section', {
          key: String(item['id']),
        }, [
          slots['itemMain']?.({ item }),
          slots['itemActions']?.({ item }),
        ])))
      },
    }),
  }
})

import RoleSheet from '@/components/system-config/RoleSheet.vue'

const role = {
  id: 1,
  code: 'FINANCE',
  name: '财务人员',
  description: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const permissionResponse = (
  id: number,
  code: string,
  resource: string,
  name: string,
  action: string,
) => ({
  id,
  code,
  name,
  resource,
  action,
  scope: null,
  description: null,
  is_active: true,
  created_at: '2026-09-28T00:00:00Z',
  updated_at: '2026-09-28T00:00:00Z',
})

const DialogStub = defineComponent({
  name: 'Dialog',
  props: { open: Boolean },
  setup(props, { slots }) {
    return () => props.open ? h('div', { role: 'dialog' }, slots.default?.()) : null
  },
})

const SlotStub = defineComponent({
  setup: (_, { slots }) => () => h('div', slots.default?.()),
})

describe('RoleSheet permission grouping', () => {
  beforeEach(() => {
    mocks.getRoles.mockReset().mockResolvedValue([role])
    mocks.getRole.mockReset().mockResolvedValue({ ...role, permissions: [] })
    mocks.getAllPermissions.mockReset().mockResolvedValue([
      permissionResponse(1, 'payment:approve', 'payment', '审批回款', 'approve'),
      permissionResponse(2, 'payment:plan:export', 'payment_plan', '导出回款计划', 'export'),
      permissionResponse(3, 'payment:record:export', 'payment_record', '导出回款记录', 'export'),
    ])
  })

  it('shows payment record export inside one payment group', async () => {
    const wrapper = mount(RoleSheet, {
      props: { embedded: true, active: true },
      global: {
        stubs: {
          ScrollArea: SlotStub,
          Dialog: DialogStub,
          DialogContent: SlotStub,
          DialogHeader: SlotStub,
          DialogTitle: SlotStub,
          DialogDescription: SlotStub,
          DialogFooter: SlotStub,
          Button: {
            emits: ['click'],
            template: '<button type="button" @click="$emit(\'click\')"><slot /></button>',
          },
          Checkbox: { template: '<input type="checkbox">' },
          Label: { template: '<label><slot /></label>' },
          Badge: { template: '<span><slot /></span>' },
        },
      },
    })
    await vi.waitFor(() => expect(mocks.getRoles).toHaveBeenCalled())
    const permissionButton = wrapper.findAll('button').find(button => button.text().includes('权限'))
    if (permissionButton === undefined) throw new Error('RoleSheet permission action not rendered')
    await permissionButton.trigger('click')
    await flushPromises()

    const groupHeadings = wrapper.findAll('.font-semibold').map(item => item.text())
    expect(groupHeadings).toContain('回款')
    expect(groupHeadings).not.toContain('回款计划')
    expect(groupHeadings).not.toContain('回款记录')
    expect(wrapper.text()).toContain('导出回款记录')
    expect(wrapper.text()).toContain('payment:record:export')
  })
})
```

The test mounts the real `RoleSheet.vue`; only layout primitives and the list container are stubbed.

- [ ] **Step 4: Run permission tests and confirm RED**

```bash
cd CRM-Client
npm run test:unit -- \
  src/constants/__tests__/permissions.test.ts \
  src/views/settings/__tests__/SettingsRolesPage.test.ts \
  src/components/system-config/__tests__/RoleSheet.permissionGrouping.test.ts
```

Expected: the constants test fails because the exported helper is absent, and both mounted role entrypoints still render separate “回款计划”和“回款记录” groups.

- [ ] **Step 5: Implement the shared permission grouping helper**

In `CRM-Client/src/constants/permissions.ts`, add:

```typescript
export interface PermissionGroup {
  resource: string
  permissions: PermissionResponse[]
}

const PERMISSION_GROUP_RESOURCE_ALIASES: Readonly<Record<string, string>> = {
  payment_plan: 'payment',
  payment_record: 'payment',
}

export const getPermissionGroupResource = (resource: string): string => (
  PERMISSION_GROUP_RESOURCE_ALIASES[resource] ?? resource
)

export const groupAssignablePermissions = (
  permissions: readonly PermissionResponse[],
): PermissionGroup[] => {
  const groups = new Map<string, PermissionResponse[]>()
  for (const permission of permissions) {
    if (!isAssignablePermission(permission)) continue
    const resource = getPermissionGroupResource(permission.resource)
    const group = groups.get(resource)
    if (group === undefined) {
      groups.set(resource, [permission])
    } else {
      group.push(permission)
    }
  }
  return Array.from(groups, ([resource, groupedPermissions]) => ({
    resource,
    permissions: groupedPermissions,
  }))
}
```

The Map intentionally preserves API order for both group order and permission order.

- [ ] **Step 6: Replace both local grouping implementations**

In both `SettingsRolesPage.vue` and `RoleSheet.vue`:

- remove `isAssignablePermission` from imports;
- import `groupAssignablePermissions`;
- replace the local reducer with:

```typescript
const permissionGroups = computed(() => groupAssignablePermissions(allPermissions.value))
```

Do not change group checkbox logic; it already operates on permission ids and will now use the normalized group key.

- [ ] **Step 7: Run permission regressions and type checking**

```bash
cd CRM-Client
npm run test:unit -- \
  src/constants/__tests__/permissions.test.ts \
  src/views/settings/__tests__/SettingsRolesPage.test.ts \
  src/components/system-config/__tests__/RoleSheet.permissionGrouping.test.ts
npm run type-check
```

Expected: all three test files and `vue-tsc` pass. The helper test proves original resources remain unchanged inside the merged group.

- [ ] **Step 8: Commit the permission UI optimization**

```bash
git add \
  CRM-Client/src/constants/permissions.ts \
  CRM-Client/src/constants/__tests__/permissions.test.ts \
  CRM-Client/src/views/settings/SettingsRolesPage.vue \
  CRM-Client/src/components/system-config/RoleSheet.vue \
  CRM-Client/src/views/settings/__tests__/SettingsRolesPage.test.ts \
  CRM-Client/src/components/system-config/__tests__/RoleSheet.permissionGrouping.test.ts
git commit -m "fix(roles): group payment permissions together"
```

---

### Task 6: Run end-to-end verification and review

**Files:**
- Verify all files changed in Tasks 1–5.
- Do not create permanent smoke scripts or root-level reports.

**Interfaces:**
- Confirms the full path: SQL query → API response → DataTable registry → visible cells → export workbook → role permission UI.

- [ ] **Step 1: Run the focused backend suite**

```bash
cd CRM-Server
.venv/bin/python -m pytest \
  tests/unit/test_payment_list_query_crud.py \
  tests/test_payment_record_list.py \
  tests/test_payment_record_invoice_title.py \
  tests/unit/test_payment_approval_api.py \
  tests/unit/test_payment_export_api.py \
  tests/unit/list_query/test_catalog_manifest.py \
  tests/unit/list_export/test_catalog_manifest.py \
  -q --no-cov
```

Expected: all selected tests pass.

- [ ] **Step 2: Run backend static checks on touched modules**

```bash
cd CRM-Server
.venv/bin/python -m ruff check \
  app/schemas/payment.py \
  app/api/payments.py \
  app/core/list_query/catalogs/payment_records.py \
  app/core/list_export/catalogs/payment_records.py \
  tests/unit/test_payment_list_query_crud.py \
  tests/test_payment_record_list.py \
  tests/unit/test_payment_approval_api.py \
  tests/unit/test_payment_export_api.py
.venv/bin/python -m mypy \
  app/schemas/payment.py \
  app/api/payments.py \
  app/core/list_query/catalogs/payment_records.py \
  app/core/list_export/catalogs/payment_records.py
```

Expected: no Ruff or MyPy errors in the touched backend modules.

- [ ] **Step 3: Run the focused frontend suite and static checks**

```bash
cd CRM-Client
npm run test:unit -- \
  src/views/__tests__/PaymentRecords.contractFields.test.ts \
  src/components/crmwolf/__tests__/listPageQueryContract.test.ts \
  src/components/crmwolf/__tests__/listExportContract.test.ts \
  src/constants/__tests__/permissions.test.ts \
  src/views/settings/__tests__/SettingsRolesPage.test.ts \
  src/components/system-config/__tests__/RoleSheet.permissionGrouping.test.ts
npm run type-check
npx eslint \
  src/api/payment.ts \
  src/views/PaymentRecords.vue \
  src/views/__tests__/PaymentRecords.contractFields.test.ts \
  src/constants/permissions.ts \
  src/constants/__tests__/permissions.test.ts \
  src/views/settings/SettingsRolesPage.vue \
  src/components/system-config/RoleSheet.vue \
  src/views/settings/__tests__/SettingsRolesPage.test.ts \
  src/components/system-config/__tests__/RoleSheet.permissionGrouping.test.ts \
  --max-warnings=0
```

Expected: all selected tests, type checking and ESLint pass.

- [ ] **Step 4: Verify the actual web surfaces**

Start both applications as harness-managed long-running processes, not foreground shell commands:

```text
Backend
  application: .venv/bin/uvicorn
  cwd: CRM-Server
  args: ["app.main:app", "--host", "127.0.0.1", "--port", "8000"]
  ready port: 8000

Frontend
  application: npm
  cwd: CRM-Client
  args: ["run", "dev", "--", "--host", "127.0.0.1"]
  ready port: 5173
```

Use the browser tool with the existing authenticated local development team. If no authenticated local session or safe disposable dataset is available, verify the real rendered `PaymentRecords.vue` and `SettingsRolesPage.vue` surfaces through the focused Vue Test Utils mounts from Tasks 4–5, and report that authenticated persistence/export-download clicks could not be exercised rather than mutating shared data:

1. Open `http://127.0.0.1:5173/payments/records`.
2. Confirm “授权模式”和“采购类型” headers appear immediately after “合同名称”.
3. Confirm non-null values render as localized badges and empty values render `-`.
4. Open筛选 and verify both fields expose the expected enum options.
5. Apply each filter and confirm total/page results come from the server; clear filters afterward.
6. Apply sorting on each field and confirm page order changes without client-side slicing.
7. Open字段配置, hide and restore both columns, then restore the original preference before leaving the page.
8. Open导出, confirm both fields are selectable, export the current result, and inspect the workbook headers and localized values.
9. Open `http://127.0.0.1:5173/settings/roles`, configure a disposable local role, and confirm a single “回款” group contains “导出回款记录”.
10. Toggle that permission, save, reopen to confirm persistence, then restore the original permission selection and delete any disposable role created for the smoke check.

If the local payment list has no suitable non-null record, use an isolated local development dataset or the existing browser request-interception capability to supply one list response; do not mutate shared or production data merely to obtain a visual sample.

Expected: both pages match the approved design, export remains permission-gated, and no duplicate “回款计划” / “回款记录” permission groups appear.

- [ ] **Step 5: Request code review at a fixed point**

Record the implementation base before Task 1 and invoke the `requesting-code-review` skill against that fixed point and final HEAD. Fix every Critical or Important finding, rerun the exact focused commands above, and commit review fixes with a scoped message if any code changes are required.

- [ ] **Step 6: Run completion verification**

Invoke the `verification-before-completion` skill. Confirm:

- generated manifests match backend catalogs;
- no migration was added;
- unified search copy and predicates are unchanged;
- `DataTable.vue` has no payment-specific logic;
- all unrelated dirty files remain untouched;
- browser smoke cleanup restored temporary role and column preference state.

Only after those checks pass, report the exact commands and browser scenarios exercised.
