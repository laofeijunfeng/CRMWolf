# 客户管理授权人数 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从已发放的 License 申请为客户维护统一的授权类型、授权人数和授权到期快照，并将授权人数贯通客户列表、详情、筛选、排序和导出。

**Architecture:** 在 `crm_customers` 增加可空的 `license_authorized_users` 快照字段。License 发放完成后，在客户行锁内查询同团队全部 `ISSUED` 申请，按到期日、最后修改时间、ID 的稳定顺序选出一条，同时更新三项快照；历史数据由 Alembic 使用同一投影规则回填。客户列表、详情和导出只读取客户快照，前端继续使用通用列表字段目录和生成的 manifest。

**Tech Stack:** Python 3、FastAPI、Pydantic v2、SQLAlchemy、Alembic、pytest、Vue 3、TypeScript、Zod、Vitest。

## Global Constraints

- 只有 `LicenseApplication.status = ISSUED` 的申请参与快照选取；`TRIAL` 和 `OFFICIAL` 都参与。
- 申请选取顺序固定为 `expiry_date DESC`、`last_modified_time DESC`、`id DESC`；授权类型、授权人数、授权到期必须来自同一条申请。
- 没有已发放申请时，客户的 `license_type`、`license_authorized_users`、`license_expiry_date` 全部为 `NULL`。
- 新增字段为 `crm_customers.license_authorized_users INTEGER NULL`，生产模型字段为 `Customer.license_authorized_users`。
- 授权人数只读，不加入客户创建、普通编辑或人工授权快照更新请求。
- 发放同步继续校验 `team_id`、锁定客户行、保留 `commit` 参数语义；不改变 `update_customer_license_expiry()` 的行为。
- 进度推进只在现有快照发生“更晚到期”的有效变化时触发；仅授权类型或授权人数变化、同到期日重算不得无故推进。
- 客户列表、详情和导出只读取客户快照，不在列表请求中逐客户查询 License 申请。
- 查询目录字段顺序和用户展示顺序均为：授权状态、授权人数、授权到期。
- Alembic migration 必须兼容 MySQL 和 SQLite，不使用 PostgreSQL 专用 SQL；升级同时回填三项快照，降级删除新增字段。
- 前端 manifest 只能通过现有生成脚本更新，不手工编辑 JSON。
- 不修改 `CRM-Server/tests/unit/test_license_approval.py` 中用户已有脏改动；不触碰 Assistant 相关脏文件。
- 每个生产改动先有能证明缺失行为的失败测试，并观察正确 RED 后再实现 GREEN。
- 任务实现者跳过 formatter、lint、mypy 和项目级测试；只运行任务内 focused 测试。最终统一运行全局检查和必要的实际场景验证。
- 只精确暂存本功能文件，禁止使用 `git add .`。

---

## 文件与职责映射

- `CRM-Server/app/models/customer.py`: 增加客户授权人数自动快照列。
- `CRM-Server/app/crud/crud_license_application.py`: 在客户锁内重算同一条已发放申请对应的三项授权快照。
- `CRM-Server/tests/unit/test_customer_license_authorized_users.py`: 独立覆盖授权申请选取、快照同步和进度推进边界，避免覆盖用户已修改的 License 审批测试。
- `CRM-Server/migrations/versions/151_customer_license_authorized_users.py`: 增加列并按同一排序规则回填历史客户，支持可逆 downgrade。
- `CRM-Server/tests/unit/test_customer_license_authorized_users_migration.py`: 在 SQLite 临时库验证迁移升级、回填、跨团队隔离、无申请清空和降级。
- `CRM-Server/app/schemas/customer.py`: 在基础客户响应和详情响应增加可空授权人数，不修改任何请求 schema。
- `CRM-Server/app/api/customers.py`: 客户详情、列表和导出行组装授权人数。
- `CRM-Server/app/core/list_query/catalogs/customers.py`: 增加 number 查询字段，放在授权状态后、到期日前。
- `CRM-Server/app/core/list_export/catalogs/customers.py`: 增加 number 导出字段，放在授权状态后、到期日前。
- `CRM-Server/tests/unit/list_query/test_catalog_manifest.py`: 验证字段类型、数字能力和授权字段顺序。
- `CRM-Server/tests/unit/list_export/test_catalog_manifest.py`: 验证导出标签、类型、顺序和生成 manifest 一致性。
- `CRM-Client/src/api/customer.ts`: 客户列表/详情响应类型增加可空授权人数；请求类型不增加该字段。
- `CRM-Client/src/schemas/customer.ts`: 客户响应 Zod schema 增加可空整数授权人数；请求 schema 不增加该字段。
- `CRM-Client/src/views/Customers.vue`: 通用字段目录和表格 cell 增加授权人数，保持固定顺序和空值显示。
- `CRM-Client/src/views/CustomerDetailSheet.vue`: 详情只读授权信息增加授权人数，不改编辑表单。
- `CRM-Client/src/api/__tests__/customer.test.ts`: 响应 schema/API 解析覆盖 number、null、缺省值和详情响应。
- `CRM-Client/src/components/crmwolf/__tests__/listPageQueryContract.test.ts`: 验证客户 manifest 和客户页面授权人数查询/排序契约。
- `CRM-Client/src/components/crmwolf/__tests__/listExportContract.test.ts`: 验证客户列表导出字段与后端 manifest 的标签一致。
- `CRM-Client/src/components/crmwolf/__tests__/listFieldCatalog.test.ts`: 验证客户字段目录注册及授权三字段顺序。
- `CRM-Client/src/components/crmwolf/listQueryCatalogManifest.json`: 由生成脚本更新，不手工编辑。
- `CRM-Client/src/components/crmwolf/listExportCatalogManifest.json`: 由生成脚本更新，不手工编辑。

---

### Task 1: 建立授权快照同步的失败测试并实现后端选取逻辑

**Files:**
- Create: `CRM-Server/tests/unit/test_customer_license_authorized_users.py`
- Modify: `CRM-Server/app/models/customer.py:92-93`
- Modify: `CRM-Server/app/crud/crud_license_application.py:633-671`

**Interfaces:**
- Consumes: `LicenseApplicationCRUD.update_customer_license_info(db, team_id, issued_application, commit=True)`。
- Produces: `Customer.license_authorized_users: Optional[int]`；同步方法在客户锁内按 `LicenseApplication.expiry_date.desc(), LicenseApplication.last_modified_time.desc(), LicenseApplication.id.desc()` 选择同团队 `ISSUED` 申请，并从该申请一次性写入 `license_type`、`license_authorized_users`、`license_expiry_date`。

- [ ] **Step 1: Write the failing tests**

Create a new SQLite fixture with `Customer.__table__`, `CustomerLegacySourceProgress.__table__`, and `LicenseApplication.__table__`; register the existing SQLite `BigInteger` compiler pattern used by License tests. Use a customer factory with `team_id=1`, explicit dates, and an application factory that sets `status`, `license_type`, `authorized_users`, `expiry_date`, `last_modified_time`, and a unique `application_number`.

The file must contain these behavior tests:

```python
def test_customer_model_exposes_nullable_license_authorized_users(db):
    customer = _customer()
    db.add(customer)
    db.commit()
    assert customer.license_authorized_users is None


def test_snapshot_ignores_non_issued_and_accepts_trial_and_official(db, customer, monkeypatch):
    db.add_all([
        _application("draft", status="DRAFT", license_type="OFFICIAL", users=99, expiry=date(2030, 1, 1)),
        _application("trial", status="ISSUED", license_type="TRIAL", users=5, expiry=date(2027, 1, 1)),
        _application("official", status="ISSUED", license_type="OFFICIAL", users=20, expiry=date(2028, 1, 1)),
    ])
    db.commit()
    _disable_progress_side_effect(monkeypatch)

    license_application_crud.update_customer_license_info(db, 1, db.query(LicenseApplication).filter_by(application_number="trial").one())
    db.refresh(customer)

    assert (customer.license_type, customer.license_authorized_users, customer.license_expiry_date) == (
        "OFFICIAL", 20, date(2028, 1, 1)
    )


def test_snapshot_prefers_later_expiry_then_last_modified_then_id(db, customer, monkeypatch):
    same_expiry_older_time = _application("older-time", status="ISSUED", license_type="TRIAL", users=1, expiry=date(2028, 1, 1), modified=datetime(2026, 1, 1))
    same_expiry_newer_time = _application("newer-time", status="ISSUED", license_type="OFFICIAL", users=2, expiry=date(2028, 1, 1), modified=datetime(2026, 2, 1))
    same_expiry_same_time_low_id = _application("low-id", status="ISSUED", license_type="TRIAL", users=3, expiry=date(2029, 1, 1), modified=datetime(2026, 3, 1), application_id=10)
    same_expiry_same_time_high_id = _application("high-id", status="ISSUED", license_type="OFFICIAL", users=4, expiry=date(2029, 1, 1), modified=datetime(2026, 3, 1), application_id=11)
    db.add_all([same_expiry_older_time, same_expiry_newer_time, same_expiry_same_time_low_id, same_expiry_same_time_high_id])
    db.commit()
    _disable_progress_side_effect(monkeypatch)

    license_application_crud.update_customer_license_info(db, 1, same_expiry_older_time)
    db.refresh(customer)

    assert (customer.license_type, customer.license_authorized_users, customer.license_expiry_date) == (
        "OFFICIAL", 4, date(2029, 1, 1)
    )
```

Also add independent tests for: the three values coming from one selected application (use deliberately mismatched values in competing applications), a cross-team issued application leaving the customer unchanged, a missing customer being a no-op, no issued applications clearing all three fields, an older issued application not replacing a newer snapshot, an older application still causing a recomputation when it becomes the selected row after the prior winner is no longer eligible, and an equal-expiry type/user change not calling `advance_eligible_progress` a second time. Assert `db.commit()` behavior for `commit=False` and `commit=True` through persisted values rather than mocks.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
cd CRM-Server
pytest tests/unit/test_customer_license_authorized_users.py -q
```

Expected: collection or assertion failures identify the missing `Customer.license_authorized_users` field and/or the old two-field synchronization behavior. Fix only test fixture/setup errors until the failure is caused by the missing production behavior; do not alter production code before this RED observation.

- [ ] **Step 3: Add the nullable customer model field**

In `Customer`, directly after the existing License fields, add:

```python
license_authorized_users = Column(
    Integer,
    nullable=True,
    comment="客户 License 授权人数（自动更新）",
)
```

Do not add the field to any customer create/update schema in this task.

- [ ] **Step 4: Replace partial synchronization with a single-winner projection**

Keep the existing team guard and locked customer query. After the customer is found, query all matching applications while the customer row is locked:

```python
selected_application = (
    db.query(LicenseApplication)
    .filter(
        LicenseApplication.customer_id == customer.id,
        LicenseApplication.team_id == team_id,
        LicenseApplication.status == LicenseApplicationStatus.ISSUED,
    )
    .order_by(
        LicenseApplication.expiry_date.desc(),
        LicenseApplication.last_modified_time.desc(),
        LicenseApplication.id.desc(),
    )
    .first()
)
```

Derive a tuple from exactly that row, or `(None, None, None)` when no row exists. Compare the old expiry with the selected expiry before assignment so `advance_eligible_progress(db, team_id=team_id, customer_id=customer.id)` runs only when the selected expiry is non-null and later than the previous customer expiry. Assign all three fields together regardless of whether only type or user count changed. Preserve `commit=False` and `commit=True` semantics; commit only inside the existing valid-change branch when `commit` is true.

- [ ] **Step 5: Run the focused tests and verify GREEN**

Run:

```bash
cd CRM-Server
pytest tests/unit/test_customer_license_authorized_users.py -q
```

Expected: all tests in the new file pass. The output must show zero failures and no collection errors.

- [ ] **Step 6: Commit only the task files**

```bash
git add CRM-Server/app/models/customer.py CRM-Server/app/crud/crud_license_application.py CRM-Server/tests/unit/test_customer_license_authorized_users.py
git commit -m "feat(server): sync customer license authorized users"
```

Do not stage `CRM-Server/tests/unit/test_license_approval.py` or unrelated dirty files.

---

### Task 2: Add and verify the historical Alembic backfill

**Files:**
- Create: `CRM-Server/migrations/versions/151_customer_license_authorized_users.py`
- Create: `CRM-Server/tests/unit/test_customer_license_authorized_users_migration.py`

**Interfaces:**
- Consumes: `crm_customers`, `crm_license_applications`, and revision `150_profile_version_attestation`.
- Produces: Alembic upgrade that adds `crm_customers.license_authorized_users`, projects all three snapshot fields from one selected same-team `ISSUED` application, clears all three when no winner exists, and downgrade that drops only the new column.

- [ ] **Step 1: Write the failing migration test**

Create a temporary SQLite engine and minimal tables matching the columns used by the migration. Load the migration module by file path and invoke `upgrade()`/`downgrade()` under `alembic.op` operations using the existing project migration-test pattern. Seed customers in two teams and applications covering: non-ISSUED exclusion, later expiry, same expiry/newer modification, same expiry/time/higher ID, cross-team application, and no issued application. Before the migration, assert the new column does not exist.

The core assertions must be:

```python
assert "license_authorized_users" not in _column_names(connection, "crm_customers")

upgrade()

assert "license_authorized_users" in _column_names(connection, "crm_customers")
assert _customer_snapshot(connection, customer_id=1) == ("OFFICIAL", 42, date(2029, 1, 1))
assert _customer_snapshot(connection, customer_id=2) == (None, None, None)
assert _customer_snapshot(connection, customer_id=3) == (None, None, None)

downgrade()
assert "license_authorized_users" not in _column_names(connection, "crm_customers")
```

The customer with ID 1 must prove all three values originate from the same selected application, and the customer with ID 3 must prove a different team cannot supply the snapshot.

- [ ] **Step 2: Run the migration test and verify RED**

Run:

```bash
cd CRM-Server
pytest tests/unit/test_customer_license_authorized_users_migration.py -q
```

Expected: failure because the migration file does not exist or the column/backfill behavior is absent. Correct only test harness/import problems before accepting the intended RED result.

- [ ] **Step 3: Create the migration at the current head**

Use the concrete revision ID and exact dependency:

```python
revision = "151_customer_license_authorized_users"
down_revision = "150_profile_version_attestation"
```

In `upgrade()`:

1. `op.add_column("crm_customers", sa.Column("license_authorized_users", sa.Integer(), nullable=True, comment="客户 License 授权人数（自动更新）"))`.
2. Get `bind = op.get_bind()` and define lightweight `sa.table` objects for customers and license applications; do not import application models into migration history.
3. Select customer `id` and `team_id`, then for each customer select one application with exact predicates `customer_id == customer.id`, `team_id == customer.team_id`, `status == "ISSUED"`, ordered by `expiry_date DESC`, `last_modified_time DESC`, `id DESC`, `LIMIT 1`.
4. Update `license_expiry_date`, `license_type`, and `license_authorized_users` in one update from the selected row, or set all three to `None` when no row exists. This per-customer SQLAlchemy Core approach is required for MySQL/SQLite portability and guarantees one source row for all three fields.

In `downgrade()`, call `op.drop_column("crm_customers", "license_authorized_users")` and do not rewrite the historical two-field values.

- [ ] **Step 4: Run the migration test and verify GREEN**

Run:

```bash
cd CRM-Server
pytest tests/unit/test_customer_license_authorized_users_migration.py -q
```

Expected: all migration assertions pass on SQLite, including upgrade, same-row projection, team isolation, no-winner clearing, and downgrade.

- [ ] **Step 5: Commit only migration files**

```bash
git add CRM-Server/migrations/versions/151_customer_license_authorized_users.py CRM-Server/tests/unit/test_customer_license_authorized_users_migration.py
git commit -m "feat(server): backfill customer license authorization snapshots"
```

---

### Task 3: Update backend response, list-query, and export contracts

**Files:**
- Modify: `CRM-Server/app/schemas/customer.py:351-354,515-518`
- Modify: `CRM-Server/app/api/customers.py:488-489,1691-1692,1740-1742`
- Modify: `CRM-Server/app/core/list_query/catalogs/customers.py:78-88`
- Modify: `CRM-Server/app/core/list_export/catalogs/customers.py:15-18`
- Modify: `CRM-Server/tests/unit/list_query/test_catalog_manifest.py`
- Modify: `CRM-Server/tests/unit/list_export/test_catalog_manifest.py`
- Create: `CRM-Server/tests/unit/test_customer_license_contracts.py`

**Interfaces:**
- Consumes: `Customer.license_authorized_users` from Task 1 and the existing list catalog/response builders.
- Produces: `CustomerResponse`, `CustomerListResponse`, and `CustomerDetailResponse` with `license_authorized_users: Optional[int]`; customer list query field `number`; customer export field `license_authorized_users -> 授权人数 -> number`.

- [ ] **Step 1: Write backend contract tests that fail**

Add assertions before production edits:

```python
def test_customer_response_and_detail_response_accept_nullable_authorized_users():
    payload = _valid_customer_payload(license_authorized_users=32)
    assert CustomerResponse.model_validate(payload).license_authorized_users == 32
    assert CustomerDetailResponse.model_validate({**payload, "contacts": []}).license_authorized_users == 32
    assert CustomerResponse.model_validate(_valid_customer_payload()).license_authorized_users is None


def test_customer_query_catalog_exposes_numeric_authorized_users_between_license_fields():
    keys = [field.key for field in CUSTOMERS_LIST_QUERY_CATALOG.fields]
    assert keys[keys.index("license_status"):keys.index("license_expiry_date") + 1] == [
        "license_status", "license_authorized_users", "license_expiry_date",
    ]
    field = CUSTOMERS_LIST_QUERY_CATALOG.require("license_authorized_users")
    assert field.type == "number"
    assert field.supports_filtering() and field.supports_sorting()


def test_customer_export_exposes_authorized_users_between_license_fields():
    fields = LIST_EXPORT_CATALOGS["customers"].fields
    selected = [field for field in fields if field.key in {"license_status", "license_authorized_users", "license_expiry_date"}]
    assert [(field.key, field.label, field.cell_type) for field in selected] == [
        ("license_status", "授权状态", "text"),
        ("license_authorized_users", "授权人数", "number"),
        ("license_expiry_date", "授权到期", "date"),
    ]
```

Extend the existing list/export manifest tests to assert the generated query manifest field is numeric, filterable, sortable, and has the standard number operators; assert the generated export manifest entry is exactly `{"label": "授权人数", "type": "number"}` and the committed manifest matches generation.

Add a builder/export-row test with a customer whose snapshot has `license_authorized_users=32`, asserting the list response and `_customer_export_row()` both contain `32`.

- [ ] **Step 2: Run the backend contract tests and verify RED**

Run:

```bash
cd CRM-Server
pytest tests/unit/test_customer_license_contracts.py tests/unit/list_query/test_catalog_manifest.py tests/unit/list_export/test_catalog_manifest.py -q
```

Expected: failures identify missing schema field, catalog field, export field, or assembled response key; no collection error unrelated to this feature.

- [ ] **Step 3: Implement the backend response and catalog changes**

Add this field to `CustomerResponse` directly between existing License fields in the fixed contract order:

```python
license_expiry_date: Optional[date] = Field(None, description="客户 License 最晚到期时间")
license_authorized_users: Optional[int] = Field(None, description="客户 License 授权人数")
license_type: Optional[str] = Field(None, description="客户 License 类型：TRIAL/OFFICIAL")
```

Add the same field to `CustomerDetailResponse` in the same relative position. Do not add it to `CustomerCreate`, `CustomerUpdate`, or `CustomerLicenseSnapshotUpdate`.

Add `"license_authorized_users": customer.license_authorized_users` to `_customer_response`, `_build_customer_list_responses`, and `_customer_export_row` between the existing License fields. Add `ListQueryField(key="license_authorized_users", type="number", expression=Customer.license_authorized_users)` between `license_status` and `license_expiry_date`. Add `ListExportField("license_authorized_users", "授权人数", "number")` in the same position.

- [ ] **Step 4: Generate manifests and verify GREEN**

Run the existing generators from `CRM-Server`:

```bash
cd CRM-Server
python scripts/generate_list_query_manifest.py
python scripts/generate_list_export_manifest.py
pytest tests/unit/test_customer_license_contracts.py tests/unit/list_query/test_catalog_manifest.py tests/unit/list_export/test_catalog_manifest.py -q
```

Expected: both JSON manifests are regenerated, all focused backend contract tests pass, and the committed-manifest equality tests pass.

- [ ] **Step 5: Commit backend contract files**

```bash
git add CRM-Server/app/schemas/customer.py CRM-Server/app/api/customers.py CRM-Server/app/core/list_query/catalogs/customers.py CRM-Server/app/core/list_export/catalogs/customers.py CRM-Server/tests/unit/test_customer_license_contracts.py CRM-Server/tests/unit/list_query/test_catalog_manifest.py CRM-Server/tests/unit/list_export/test_catalog_manifest.py CRM-Client/src/components/crmwolf/listQueryCatalogManifest.json CRM-Client/src/components/crmwolf/listExportCatalogManifest.json
git commit -m "feat(server): expose customer license authorization contracts"
```

---

### Task 4: Update frontend types, schemas, list display, and detail display

**Files:**
- Modify: `CRM-Client/src/api/customer.ts:228-229,293-294`
- Modify: `CRM-Client/src/schemas/customer.ts:61-63`
- Modify: `CRM-Client/src/views/Customers.vue:351-359,1384-1394`
- Modify: `CRM-Client/src/views/CustomerDetailSheet.vue:1648-1662`
- Modify: `CRM-Client/src/api/__tests__/customer.test.ts`
- Modify: `CRM-Client/src/components/crmwolf/__tests__/listPageQueryContract.test.ts`
- Modify: `CRM-Client/src/components/crmwolf/__tests__/listExportContract.test.ts`
- Modify: `CRM-Client/src/components/crmwolf/__tests__/listFieldCatalog.test.ts`

**Interfaces:**
- Consumes: generated manifests and backend response field from Task 3.
- Produces: typed/Zod-validated read-only `license_authorized_users: number | null`; customer list field order and cell slot; customer detail read-only display. No create/edit form field.

- [ ] **Step 1: Add frontend tests that fail**

Extend the shared `customerResponse` fixture with `license_authorized_users: null`, then add tests proving the Zod response schema accepts all three read forms:

```typescript
it('accepts numeric, null, and omitted customer license authorized users', async () => {
  const { CustomerResponseSchema, CustomerDetailResponseSchema } = await import('@/schemas/customer')
  expect(CustomerResponseSchema.parse({ ...customerResponse, license_authorized_users: 32 }).license_authorized_users).toBe(32)
  expect(CustomerResponseSchema.parse({ ...customerResponse, license_authorized_users: null }).license_authorized_users).toBeNull()
  expect(CustomerResponseSchema.parse(customerResponse).license_authorized_users).toBeUndefined()
  expect(CustomerDetailResponseSchema.parse({ ...customerResponse, owner_info: null, creator_info: null, contacts: [], license_authorized_users: 32 }).license_authorized_users).toBe(32)
})
```

Add static contract assertions that `Customers.vue` contains the three keys in order `license_status`, `license_authorized_users`, `license_expiry_date`, declares the new field as `type: 'number'`, and renders `row.license_authorized_users ?? '-'`. Assert the export contract sees the generated `授权人数` field. Assert the detail sheet contains a read-only `授权人数` attribute between the existing status and expiry labels and does not add `license_authorized_users` to request interfaces or edit form payloads.

- [ ] **Step 2: Run the frontend focused tests and verify RED**

Run:

```bash
cd CRM-Client
npm run test:unit -- src/api/__tests__/customer.test.ts src/components/crmwolf/__tests__/listPageQueryContract.test.ts src/components/crmwolf/__tests__/listExportContract.test.ts src/components/crmwolf/__tests__/listFieldCatalog.test.ts
```

Expected: failures identify the absent Zod property, missing customer list field, or missing detail display. Fix only test import/fixture issues until the feature assertions fail for the intended reason.

- [ ] **Step 3: Add the frontend read contracts and display**

In `CustomerResponse` and `CustomerDetailResponse`, add `license_authorized_users: number | null` between `license_type` and `license_expiry_date` according to the established API interface ordering; do not add it to `CustomerCreate`, `CustomerUpdate`, or `CustomerLicenseSnapshotUpdate`.

In `CustomerResponseSchema`, add:

```typescript
license_authorized_users: z.number().int().nullable().optional(),
```

The list and detail schemas inherit this field from `CustomerResponseSchema` and must not redeclare it.

In `Customers.vue`, register:

```typescript
{
  key: 'license_authorized_users',
  label: '授权人数',
  type: 'number',
  column: { width: '100px' }
},
```

between `license_status` and `license_expiry_date`, and add the standard slot:

```vue
<!-- 授权人数 -->
<template #cell-license_authorized_users="{ row }">
  {{ row.license_authorized_users ?? '-' }}
</template>
```

In `CustomerDetailSheet.vue`, insert the read-only attribute between the existing status and expiry attributes:

```vue
<div class="attribute-item">
  <div class="attribute-label">授权人数</div>
  <div class="attribute-value">{{ customer?.license_authorized_users ?? '-' }}</div>
</div>
```

- [ ] **Step 4: Run the frontend focused tests and verify GREEN**

Run:

```bash
cd CRM-Client
npm run test:unit -- src/api/__tests__/customer.test.ts src/components/crmwolf/__tests__/listPageQueryContract.test.ts src/components/crmwolf/__tests__/listExportContract.test.ts src/components/crmwolf/__tests__/listFieldCatalog.test.ts
```

Expected: all selected frontend tests pass with zero failures.

- [ ] **Step 5: Commit only frontend contract/display files**

```bash
git add CRM-Client/src/api/customer.ts CRM-Client/src/schemas/customer.ts CRM-Client/src/views/Customers.vue CRM-Client/src/views/CustomerDetailSheet.vue CRM-Client/src/api/__tests__/customer.test.ts CRM-Client/src/components/crmwolf/__tests__/listPageQueryContract.test.ts CRM-Client/src/components/crmwolf/__tests__/listExportContract.test.ts CRM-Client/src/components/crmwolf/__tests__/listFieldCatalog.test.ts
git commit -m "feat(client): display customer license authorized users"
```

---

### Task 5: Verify database migration and focused backend behavior

**Files:**
- Modify only when required by a failing focused check: Task 1–4 files and migration test files.
- Do not modify unrelated dirty files.

**Interfaces:**
- Consumes: completed backend model, synchronization method, migration, response/catalog contracts, and generated manifests.
- Produces: fresh evidence for migration graph, upgrade/downgrade, API projection, query filtering/sorting, and export row behavior.

- [ ] **Step 1: Run all feature-specific backend tests**

Run:

```bash
cd CRM-Server
pytest tests/unit/test_customer_license_authorized_users.py tests/unit/test_customer_license_authorized_users_migration.py tests/unit/test_customer_license_contracts.py tests/unit/list_query/test_catalog_manifest.py tests/unit/list_export/test_catalog_manifest.py -q
```

Expected: all feature-specific backend tests pass. If a test fails, fix the production or test defect and rerun the same command; do not broaden the scope.

- [ ] **Step 2: Exercise Alembic upgrade/current and downgrade/upgrade on SQLite**

Run the project migration validation command with a temporary SQLite URL or the repository’s configured local migration database, preserving the existing environment configuration:

```bash
cd CRM-Server
alembic upgrade head
alembic current
alembic downgrade 150_profile_version_attestation
alembic upgrade head
alembic current
```

Expected: upgrade and downgrade exit successfully; the final `alembic current` reports the new migration revision at head. If the configured database is MySQL rather than SQLite, run the same sequence against the project’s configured local dialect and retain the focused SQLite migration test as the portable proof.

- [ ] **Step 3: Verify neighboring customer regressions**

Run:

```bash
cd CRM-Server
pytest tests/unit/test_customer_primary_contact_list.py tests/unit/test_customer_product_intent.py -q
```

Expected: existing customer list projection behavior remains passing, including response construction and export behavior.

- [ ] **Step 4: Run the actual customer list read path**

Use the repository’s existing frontend dev/test environment with a seeded customer response containing `license_authorized_users=32` and a null snapshot row. Confirm the rendered customer list shows `授权状态`, `授权人数`, `授权到期` in that order, displays `32` for the populated row, and displays `-` for null. Confirm the detail sheet displays the same number and null placeholder. If a browser session cannot be started, run the focused Vue contract tests and a direct `CustomerListResponseSchema.parse()` scenario, then report that visual runtime verification was unavailable rather than claiming it was performed.

- [ ] **Step 5: Commit only verification-driven fixes**

If fixes were required, stage only the changed feature files and use a scoped commit:

```bash
git add CRM-Server/app/models/customer.py CRM-Server/app/crud/crud_license_application.py CRM-Server/app/schemas/customer.py CRM-Server/app/api/customers.py CRM-Server/app/core/list_query/catalogs/customers.py CRM-Server/app/core/list_export/catalogs/customers.py CRM-Server/migrations/versions/151_customer_license_authorized_users.py CRM-Server/tests/unit/test_customer_license_authorized_users.py CRM-Server/tests/unit/test_customer_license_authorized_users_migration.py CRM-Server/tests/unit/test_customer_license_contracts.py CRM-Server/tests/unit/list_query/test_catalog_manifest.py CRM-Server/tests/unit/list_export/test_catalog_manifest.py CRM-Client/src/api/customer.ts CRM-Client/src/schemas/customer.ts CRM-Client/src/views/Customers.vue CRM-Client/src/views/CustomerDetailSheet.vue CRM-Client/src/api/__tests__/customer.test.ts CRM-Client/src/components/crmwolf/__tests__/listPageQueryContract.test.ts CRM-Client/src/components/crmwolf/__tests__/listExportContract.test.ts CRM-Client/src/components/crmwolf/__tests__/listFieldCatalog.test.ts CRM-Client/src/components/crmwolf/listQueryCatalogManifest.json CRM-Client/src/components/crmwolf/listExportCatalogManifest.json
git commit -m "fix(customer): close license authorization verification gaps"
```

If no source fixes were required, do not create an empty commit.

---

### Task 6: Run final project checks and inspect the change boundary

**Files:**
- No planned source additions; modify only if a check exposes a real feature defect.

**Interfaces:**
- Consumes: all completed feature tasks.
- Produces: final verification evidence and a clean, narrowly scoped diff boundary that preserves pre-existing user changes.

- [ ] **Step 1: Run backend focused and project-required static checks**

Run the feature tests again, then the repository-required checks:

```bash
cd CRM-Server
pytest tests/unit/test_customer_license_authorized_users.py tests/unit/test_customer_license_authorized_users_migration.py tests/unit/test_customer_license_contracts.py tests/unit/list_query/test_catalog_manifest.py tests/unit/list_export/test_catalog_manifest.py -q
ruff check app/
mypy app/
```

Expected: focused tests, Ruff, and mypy exit 0. Do not reformat unrelated files.

- [ ] **Step 2: Run frontend focused tests and type-check**

Run:

```bash
cd CRM-Client
npm run test:unit -- src/api/__tests__/customer.test.ts src/components/crmwolf/__tests__/listPageQueryContract.test.ts src/components/crmwolf/__tests__/listExportContract.test.ts src/components/crmwolf/__tests__/listFieldCatalog.test.ts
npm run type-check
```

Expected: all selected Vitest tests and TypeScript type-check exit 0.

- [ ] **Step 3: Inspect exact changed paths without staging unrelated work**

Run:

```bash
git diff --name-only f1127c36..HEAD
git status --short
```

Expected: feature commits contain only the design/plan and listed customer License model, CRUD, migration, schema, API, catalog, manifest, frontend, and focused test files. Existing Assistant and other user-modified files remain unstaged/uncommitted and are not included in feature commits.

- [ ] **Step 4: Scan the plan and implementation for forbidden placeholders**

Run:

```bash
python -c 'from pathlib import Path; p=Path("docs/superpowers/plans/2026-10-09-customer-license-authorized-users-plan.md"); text=p.read_text(); forbidden=("TBD", "TODO", "Task N", "Write tests for above"); assert not any(item in text for item in forbidden), [item for item in forbidden if item in text]'
```

Expected: command exits 0 and prints no placeholder list.

---

### Task 7: Task-level and final code review, then close out

**Files:**
- Review all feature commits and the working diff; fix only Critical/Important findings in feature files.

**Interfaces:**
- Consumes: task reports, focused verification output, and complete branch diff.
- Produces: reviewer-approved implementation with no unresolved Critical/Important findings and final evidence-based status.

- [ ] **Step 1: Review each implementation task**

For each completed implementation task, generate a review package from the recorded base commit to the task head and dispatch a fresh reviewer with the task brief, report, diff package, and the exact global constraints above. The reviewer must separately return spec compliance and code-quality verdicts. Do not proceed while a Critical or Important issue remains open.

- [ ] **Step 2: Fix and re-review all Critical/Important findings**

Dispatch one focused fix worker per review round with the complete finding list and the named covering tests. The fix worker must rerun those covering tests and append the command/output to the task report. Re-dispatch the reviewer only after the report contains the fix and fresh test evidence.

- [ ] **Step 3: Perform whole-branch review**

Generate a review package from the branch-start commit to the final feature head and dispatch the most capable available reviewer. The review scope must explicitly inspect:

- same-row provenance of all three customer snapshot fields;
- team filter on both runtime synchronization and migration backfill;
- status and stable ordering rules;
- progress advancement semantics;
- migration MySQL/SQLite portability and reversible downgrade;
- absence of `license_authorized_users` from all write request schemas/forms;
- generated manifest consistency and fixed frontend field order;
- preservation of unrelated dirty files.

- [ ] **Step 4: Close the todo only after fresh evidence**

Only after final review is clean and all commands above have fresh successful output, mark the implementation todo tasks complete and report exact commands, counts, migration revision, review result, and any runtime verification limitation. Do not claim unrun checks or claim visual verification if only static tests were available.

---

## Plan self-review

- **Spec coverage:** The plan covers the nullable customer column, ISSUED-only selection, TRIAL/OFFICIAL inclusion, expiry/time/ID ordering, same-row three-field projection, empty-state clearing, team isolation, missing customer no-op, older-application recomputation, progress semantics, Alembic history backfill and downgrade, backend response/list/export contracts, generated manifests, frontend types/Zod/list/detail display, focused tests, migration commands, runtime verification, and task/final code review.
- **Placeholder scan:** No implementation placeholder remains; the migration revision is concretely `151_customer_license_authorized_users`, and every verification command names its exact files or fixed base commit.
- **Type consistency:** `Customer.license_authorized_users`, `Optional[int]`, `number | null`, `z.number().int().nullable().optional()`, list query `type="number"`, and export `cell_type="number"` are consistent across tasks. The synchronization method signature and migration head match the design document.
- **Scope check:** The plan changes only customer License snapshot/read contracts and generated manifests; it does not alter License creation/approval semantics, deployment fields, Assistant work, or unrelated list architecture.
