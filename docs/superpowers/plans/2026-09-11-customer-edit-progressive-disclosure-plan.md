# 客户编辑弹窗渐进披露实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不替代正式 License 流程的前提下，为客户编辑弹窗增加默认收起的低频字段区，支持行业编辑、受控客户状态切换和客户授权汇总补录。

**Architecture:** 保留客户普通资料 PUT 作为基础保存边界；新增独立的客户授权汇总 PATCH；新增只接受 0/1 的客户生命周期快捷 PATCH，并将状态迁移规则与副作用集中到服务层。前端用 `Collapsible` 做渐进披露，用数据库行业层级驱动的 shadcn-vue `Combobox` 做分组搜索，并以 dirty diff 防止折叠字段和未修改字段被覆盖。

**Tech Stack:** Vue 3 + TypeScript + VeeValidate + Zod + shadcn-vue/Reka UI；FastAPI + Pydantic v2 + SQLAlchemy；Vitest；Pytest。

## Global Constraints

- 遵循 `docs/superpowers/specs/2026-09-11-customer-edit-progressive-disclosure-design.md` 的字段边界和保存语义。
- 不创建数据库 migration；客户行业、状态、授权类型和授权到期字段已存在。
- 不修改 `crm_license_applications`，不创建 License 申请、审批实例、授权码或发放记录。
- 客户编辑弹窗默认收起“更多客户信息”；状态 2/3、公海、领取、移交继续走专用流程。
- 授权补录不增加修改原因字段；必须展示固定风险提醒。
- 前端不使用 `any`、`as any`、`@ts-ignore`；API 响应继续经过 Zod schema。
- 所有客户写接口继续执行 team 隔离、客户编辑权限和 `expected_version` 乐观锁。
- 每个行为变更先写可失败测试，再写最小实现；跳过格式化、lint 和项目级测试，直到最终验证任务。
- 不触碰当前工作树中与本功能无关的未提交文件。

## File Map

### Backend

- Modify `CRM-Server/app/schemas/customer.py`: lifecycle status and license snapshot request models.
- Create `CRM-Server/app/schemas/industry.py`: typed industry hierarchy response.
- Modify `CRM-Server/app/api/industry.py`: typed `/v1/industries/hierarchy` response.
- Modify `CRM-Server/app/api/customers.py`: industry validation, ordinary-update audit, lifecycle-status route, license-snapshot route.
- Modify `CRM-Server/app/crud/customer.py`: locked license snapshot update and locked lifecycle status update.
- Create `CRM-Server/app/services/customer_status_transition_service.py`: 0/1 transition matrix and notification projection.
- Modify `CRM-Server/app/constants/operation_log_events.py`: license snapshot audit event.
- Add `CRM-Server/tests/unit/test_customer_edit_contracts.py`.
- Add `CRM-Server/tests/unit/test_customer_snapshot_crud.py`.
- Add `CRM-Server/tests/unit/test_customer_status_transition_service.py`.
- Add `CRM-Server/tests/unit/api/test_customer_edit_api.py`.
- Modify `CRM-Server/tests/unit/test_customer_update_concurrency.py`.

### Frontend

- Modify `CRM-Client/src/api/customer.ts`: hierarchy, industry, lifecycle status, and license snapshot APIs.
- Modify `CRM-Client/src/schemas/customer.ts`: hierarchy and request/response schemas.
- Modify `CRM-Client/src/schemas/customer-form.ts`: edit-only industry field.
- Create `CRM-Client/src/components/crmwolf/IndustryHierarchySelectField.vue`.
- Modify `CRM-Client/src/components/crmwolf/index.ts`.
- Add `CRM-Client/src/components/crmwolf/__tests__/IndustryHierarchySelectField.test.ts`.
- Create `CRM-Client/src/components/dialogs/customerFormDiff.ts`.
- Add `CRM-Client/src/components/dialogs/__tests__/customerFormDiff.test.ts`.
- Modify `CRM-Client/src/components/dialogs/CustomerFormDialog.vue`.
- Modify `CRM-Client/src/components/dialogs/__tests__/CustomerFormDialog.test.ts`.
- Modify `CRM-Client/src/views/Customers.vue` and `CRM-Client/src/views/CustomerDetailSheet.vue` for inline refresh events.
- Add `CRM-Client/src/api/__tests__/customer.test.ts` if no customer API test file exists.

---

### Task 1: Lock request, response, and dirty-diff contracts

**Files:**
- Modify: `CRM-Server/app/schemas/customer.py:225-256`
- Create: `CRM-Server/app/schemas/industry.py`
- Modify: `CRM-Server/app/api/industry.py:15-42`
- Modify: `CRM-Client/src/api/customer.ts:1-20,99-155`
- Modify: `CRM-Client/src/schemas/customer.ts:1-25,281-287`
- Modify: `CRM-Client/src/schemas/customer-form.ts:12-45`
- Create: `CRM-Client/src/components/dialogs/customerFormDiff.ts`
- Test: `CRM-Server/tests/unit/test_customer_edit_contracts.py`
- Test: `CRM-Client/src/components/dialogs/__tests__/customerFormDiff.test.ts`

**Interfaces:**
- `CustomerStatusUpdate(status: int, 0..3)` remains unchanged for legacy list actions.
- New `CustomerLifecycleStatusUpdate(status: Literal[0, 1], expected_version: int)` is used only by the popup lifecycle route.
- New `CustomerLicenseSnapshotUpdate(expected_version: int, license_type: TRIAL | OFFICIAL | null, license_expiry_date: date | null)` normalizes empty expiry to empty type.
- `IndustryHierarchyResponse = dict[str, IndustryHierarchyGroup]`.
- `customerApi.getIndustryHierarchy()`, `customerApi.updateCustomerLifecycleStatus()`, `customerApi.updateCustomerLicenseSnapshot()`, and `CustomerUpdate.industry` become available to later tasks.

- [ ] **Step 1: Write the failing backend contract tests**

Create `CRM-Server/tests/unit/test_customer_edit_contracts.py`:

```python
from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.customer import CustomerLicenseSnapshotUpdate, CustomerLifecycleStatusUpdate


def test_lifecycle_status_update_requires_a_zero_or_one_target_and_version() -> None:
    payload = CustomerLifecycleStatusUpdate(status=1, expected_version=7)
    assert payload.status == 1
    assert payload.expected_version == 7


def test_lifecycle_status_update_rejects_lost_and_inactive_targets() -> None:
    with pytest.raises(ValidationError):
        CustomerLifecycleStatusUpdate(status=2, expected_version=1)
    with pytest.raises(ValidationError):
        CustomerLifecycleStatusUpdate(status=3, expected_version=1)


def test_license_snapshot_requires_type_when_expiry_exists() -> None:
    with pytest.raises(ValidationError):
        CustomerLicenseSnapshotUpdate(
            expected_version=4,
            license_type=None,
            license_expiry_date=date(2026, 12, 31),
        )


def test_license_snapshot_clears_type_when_expiry_is_empty() -> None:
    payload = CustomerLicenseSnapshotUpdate(
        expected_version=4,
        license_type="TRIAL",
        license_expiry_date=None,
    )
    assert payload.license_type is None
    assert payload.license_expiry_date is None
```

Run: `cd CRM-Server && pytest tests/unit/test_customer_edit_contracts.py -q`
Expected: FAIL because the new request models do not exist.

- [ ] **Step 2: Write the failing frontend diff tests**

Create `CRM-Client/src/components/dialogs/__tests__/customerFormDiff.test.ts`:

```typescript
import { describe, expect, it } from 'vitest'
import { buildCustomerUpdatePayload } from '../customerFormDiff'

const baseline = {
  account_name: '客户 A',
  city: '上海',
  address: '浦东',
  company_scale: '51-200人',
  source_public_id: 'acq_source',
  default_procurement_method_id: 8,
  industry: 'internet.enterprise',
}

describe('buildCustomerUpdatePayload', () => {
  it('sends only the changed field and expected version', () => {
    expect(buildCustomerUpdatePayload(
      { ...baseline, industry: 'finance.securities' },
      baseline,
      12,
    )).toEqual({ expected_version: 12, industry: 'finance.securities' })
  })

  it('does not send untouched collapsed fields', () => {
    expect(buildCustomerUpdatePayload(baseline, baseline, 12)).toBeNull()
  })

  it('normalizes a cleared address to null only when the address changed', () => {
    expect(buildCustomerUpdatePayload(
      { ...baseline, address: '' },
      baseline,
      12,
    )).toEqual({ expected_version: 12, address: null })
  })
})
```

Run: `cd CRM-Client && npm run test:unit -- --run src/components/dialogs/__tests__/customerFormDiff.test.ts`
Expected: FAIL because the diff helper does not exist.

- [ ] **Step 3: Implement the contracts and pure diff helper**

In `CRM-Server/app/schemas/customer.py`, import `model_validator` and add these models after the existing legacy `CustomerStatusUpdate`:

```python
class CustomerLifecycleStatusUpdate(BaseModel):
    status: Literal[0, 1] = Field(..., description="客户快捷状态：0跟进中，1已成交")
    expected_version: int = Field(..., ge=1, description="客户端读取到的客户版本号")


class CustomerLicenseSnapshotUpdate(BaseModel):
    expected_version: int = Field(..., ge=1)
    license_type: Optional[Literal["TRIAL", "OFFICIAL"]] = None
    license_expiry_date: Optional[date] = None

    @model_validator(mode="after")
    def normalize_license_pair(self):
        if self.license_expiry_date is None:
            self.license_type = None
        elif self.license_type is None:
            raise ValueError("授权到期日期不为空时必须选择授权类型")
        return self
```

Create `CRM-Server/app/schemas/industry.py` with `IndustryHierarchyChild(code, name)`, `IndustryHierarchyGroup(name, children)`, and the `IndustryHierarchyResponse` type alias. Set `/v1/industries/hierarchy` to use the typed response model.

Add `industry?: string | null` to frontend `CustomerUpdate`, add `CustomerIndustryHierarchySchema`, and add `industry` as an optional edit-only field in `customerFormSchema` while keeping it out of `customerCreateSchema`.

Create `customerFormDiff.ts` with a typed key list. It must compare normalized values, send only changed keys, keep `expected_version`, and return `null` when no business field changed. Use an explicit switch over the seven supported keys; do not use `any` or a broad cast.

- [ ] **Step 4: Run targeted contract tests and commit**

Run:

```bash
cd CRM-Server && pytest tests/unit/test_customer_edit_contracts.py -q
cd CRM-Client && npm run test:unit -- --run src/components/dialogs/__tests__/customerFormDiff.test.ts
```

Expected: PASS. Commit:

```bash
git add CRM-Server/app/schemas/customer.py CRM-Server/app/schemas/industry.py CRM-Server/app/api/industry.py CRM-Server/tests/unit/test_customer_edit_contracts.py CRM-Client/src/api/customer.ts CRM-Client/src/schemas/customer.ts CRM-Client/src/schemas/customer-form.ts CRM-Client/src/components/dialogs/customerFormDiff.ts CRM-Client/src/components/dialogs/__tests__/customerFormDiff.test.ts
git commit -m "feat(customer): define edit field contracts"
```

### Task 2: Add the database-backed industry selector

**Files:**
- Modify: `CRM-Client/src/api/customer.ts`
- Modify: `CRM-Client/src/schemas/customer.ts`
- Create: `CRM-Client/src/components/crmwolf/IndustryHierarchySelectField.vue`
- Modify: `CRM-Client/src/components/crmwolf/index.ts`
- Create: `CRM-Client/src/components/crmwolf/__tests__/IndustryHierarchySelectField.test.ts`

**Interfaces:**
- Consumes `IndustryHierarchyResponse` from `customerApi.getIndustryHierarchy()`.
- Produces `update:modelValue(code: string)` and displays a complete path label.
- Keeps an existing inactive/unknown code visible as a disabled current option; new options contain active database hierarchy only.

- [ ] **Step 1: Write the failing selector tests**

Create `CRM-Client/src/components/crmwolf/__tests__/IndustryHierarchySelectField.test.ts`:

```typescript
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import IndustryHierarchySelectField from '../IndustryHierarchySelectField.vue'

const hierarchy = {
  internet: {
    name: '互联网',
    children: [
      { code: 'internet.enterprise', name: '企业服务' },
      { code: 'internet.software', name: '软件服务' },
    ],
  },
}

describe('IndustryHierarchySelectField', () => {
  it('renders the selected full path and grouped active options', async () => {
    const wrapper = mount(IndustryHierarchySelectField, {
      props: { modelValue: 'internet.enterprise', hierarchy },
    })
    expect(wrapper.text()).toContain('互联网 / 企业服务')
    await wrapper.get('button[role="combobox"]').trigger('click')
    expect(document.body.textContent).toContain('互联网')
    expect(document.body.textContent).toContain('企业服务')
  })

  it('emits the selected child code', async () => {
    const wrapper = mount(IndustryHierarchySelectField, {
      props: { modelValue: '', hierarchy },
      attachTo: document.body,
    })
    await wrapper.get('button[role="combobox"]').trigger('click')
    const option = Array.from(document.body.querySelectorAll('[role="option"]'))
      .find((element) => element.textContent?.includes('软件服务'))
    expect(option).toBeDefined()
    await (option as HTMLElement).click()
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['internet.software'])
    wrapper.unmount()
  })
})
```

Run: `cd CRM-Client && npm run test:unit -- --run src/components/crmwolf/__tests__/IndustryHierarchySelectField.test.ts`
Expected: FAIL because the component does not exist.

- [ ] **Step 2: Implement the component with existing Combobox primitives**

Use `Combobox`, `ComboboxAnchor`, `ComboboxTrigger`, `ComboboxInput`, `ComboboxList`, `ComboboxGroup`, `ComboboxItem`, and `ComboboxItemIndicator`. The component must:

- expose `modelValue`, `hierarchy`, `label`, `error`, `helperText`, `disabled`, and `loading` props;
- flatten groups only for internal lookup, preserving `{ primaryCode, primaryName, code, name, label }`;
- use `text-value` containing both the primary and secondary names so search matches either level;
- show a stable `id`, `role="combobox"`, `aria-expanded`, `aria-invalid`, and `aria-describedby`;
- close after selection and emit only the code;
- show `暂无行业` and `行业加载失败，请重试` states through props rather than throwing;
- keep the trigger at the shared 44px input height;
- use `ChevronsUpDown` and `Check` icons with `aria-hidden`.

Register it from `CRM-Client/src/components/crmwolf/index.ts`.

- [ ] **Step 3: Add API/schema plumbing and run the selector tests**

Add this typed API method:

```typescript
getIndustryHierarchy: (): Promise<CustomerIndustryHierarchy> =>
  api.get('/v1/industries/hierarchy', undefined, CustomerIndustryHierarchySchema),
```

Use the hierarchy route, not the legacy `/v1/customers/industries` enum route. Run the selector test and commit:

```bash
cd CRM-Client && npm run test:unit -- --run src/components/crmwolf/__tests__/IndustryHierarchySelectField.test.ts

git add CRM-Client/src/api/customer.ts CRM-Client/src/schemas/customer.ts CRM-Client/src/components/crmwolf/IndustryHierarchySelectField.vue CRM-Client/src/components/crmwolf/index.ts CRM-Client/src/components/crmwolf/__tests__/IndustryHierarchySelectField.test.ts
git commit -m "feat(customer): add hierarchy industry selector"
```

### Task 3: Validate industry codes and implement locked customer snapshot CRUD

**Files:**
- Modify: `CRM-Server/app/crud/customer.py:257-317`
- Modify: `CRM-Server/app/schemas/customer.py:225-275`
- Modify: `CRM-Server/app/constants/operation_log_events.py:20-28`
- Modify: `CRM-Server/app/api/customers.py:1825-1851`
- Create: `CRM-Server/tests/unit/test_customer_snapshot_crud.py`
- Modify: `CRM-Server/tests/unit/test_customer_update_concurrency.py`

**Interfaces:**
- `customer_crud.update(..., CustomerUpdate(industry=...))` validates the code belongs to an active or currently retained industry record before mutation.
- `customer_crud.update_license_snapshot(db, customer, payload)` locks the customer, checks version, normalizes the pair, increments version, commits, and returns `(updated_customer, before, after)`.
- Ordinary PUT logs `CUSTOMER_UPDATED`; snapshot PATCH logs `CUSTOMER_LICENSE_SNAPSHOT_UPDATED` with machine-readable before/after fields.

- [ ] **Step 1: Write failing CRUD tests**

Create tests for: successful snapshot update and version increment; stale version before mutation; unknown industry rejection; and preservation of a current inactive/legacy industry code. Use the existing `MagicMock` locking style in `test_customer_update_concurrency.py`. Run:

```bash
cd CRM-Server && pytest tests/unit/test_customer_snapshot_crud.py tests/unit/test_customer_update_concurrency.py -q
```

Expected: FAIL because the CRUD method and industry validation do not exist.

- [ ] **Step 2: Implement the minimal CRUD and validation**

Use a `with_for_update()` query filtered by both `Customer.id` and `Customer.team_id`. If `expected_version` differs, raise `ConflictException("客户已发生变化，请刷新后确认最新状态")` before setting any field. Capture audit values before commit. Normalize `license_expiry_date is None` to `license_type = None`; commit and refresh once on success.

Resolve industry codes through `industry_crud.get_by_code_with_parent`. Permit active codes and the customer’s current inactive/legacy code; reject absent codes with HTTP 400 from the API boundary. Keep the legacy `/v1/customers/industries` route untouched for create compatibility; the edit UI uses hierarchy.

Add `CUSTOMER_LICENSE_SNAPSHOT_UPDATED = "CUSTOMER_LICENSE_SNAPSHOT_UPDATED"` to `EventTypes`.

- [ ] **Step 3: Add ordinary-update audit without changing response shape**

In `update_customer`, capture the submitted fields before CRUD. After success, call `operation_log_service.log` with `EventTypes.CUSTOMER_UPDATED`, action `UPDATE`, resource `CUSTOMER`, team, operator, and content containing only `changed_fields`, `before`, and `after`. Do not include unrelated customer data or secrets.

- [ ] **Step 4: Run targeted backend tests and commit**

```bash
cd CRM-Server && pytest tests/unit/test_customer_snapshot_crud.py tests/unit/test_customer_update_concurrency.py -q

git add CRM-Server/app/crud/customer.py CRM-Server/app/schemas/customer.py CRM-Server/app/constants/operation_log_events.py CRM-Server/app/api/customers.py CRM-Server/tests/unit/test_customer_snapshot_crud.py CRM-Server/tests/unit/test_customer_update_concurrency.py
git commit -m "feat(customer): support audited snapshot updates"
```

### Task 4: Add the customer status transition service and route

**Files:**
- Create: `CRM-Server/app/services/customer_status_transition_service.py`
- Modify: `CRM-Server/app/schemas/customer.py:255-275`
- Modify: `CRM-Server/app/api/customers.py:1854-1893`
- Modify: `CRM-Server/app/crud/customer.py:301-306`
- Create: `CRM-Server/tests/unit/test_customer_status_transition_service.py`
- Create: `CRM-Server/tests/unit/api/test_customer_edit_api.py`

**Interfaces:**
- New route: `PATCH /v1/customers/{customer_id}/lifecycle-status`.
- Request: `{ "status": 0 | 1, "expected_version": number }`.
- Response: existing `CustomerResponse`.
- Existing `/status` route remains available to current list actions; the popup route is the only route with the restricted 0/1 contract.

- [ ] **Step 1: Write failing transition tests**

Create tests for 0→1 with `account_status_won`, 1→0 without notification, rejection of current status 2/3, rejection of target status 2/3, and stale version. Run:

```bash
cd CRM-Server && pytest tests/unit/test_customer_status_transition_service.py -q
```

Expected: FAIL because the service does not exist.

- [ ] **Step 2: Implement the service and locked CRUD operation**

Define a typed immutable decision with `previous_status`, `new_status`, and `notification_event: str | None`. `plan()` rejects current or target status outside `{0, 1}` and no-op transitions. Add `customer_crud.update_status_with_version()` that locks by team/customer, checks `expected_version`, applies the target, increments version, commits, and refreshes.

- [ ] **Step 3: Implement the lifecycle route**

Add `@router.patch("/{customer_id}/lifecycle-status")` before the generic `/{customer_id}` route. Resolve edit permission, call the service, update through locked CRUD, record `CUSTOMER_STATUS_CHANGED` with old/new status and versions, enqueue the existing customer intelligence update, and queue the existing won notification only for `new_status == 1`. Map stale version to HTTP 409 and invalid transitions to HTTP 400. Do not call lost or invalidate flows.

- [ ] **Step 4: Add API seam tests**

Use the monkeypatch style from `tests/unit/test_customer_assign_api.py` to assert 0→1 success with notification, 1→0 success without lost notification, target 2/3 rejection, and stale-version conflict without mutation.

- [ ] **Step 5: Run targeted tests and commit**

```bash
cd CRM-Server && pytest tests/unit/test_customer_status_transition_service.py tests/unit/api/test_customer_edit_api.py -q

git add CRM-Server/app/services/customer_status_transition_service.py CRM-Server/app/schemas/customer.py CRM-Server/app/api/customers.py CRM-Server/app/crud/customer.py CRM-Server/tests/unit/test_customer_status_transition_service.py CRM-Server/tests/unit/api/test_customer_edit_api.py
git commit -m "feat(customer): add controlled lifecycle status changes"
```

### Task 5: Implement the license snapshot endpoint

**Files:**
- Modify: `CRM-Server/app/api/customers.py`
- Modify: `CRM-Server/app/crud/customer.py`
- Modify: `CRM-Server/app/constants/operation_log_events.py`
- Modify: `CRM-Server/tests/unit/api/test_customer_edit_api.py`
- Modify: `CRM-Server/tests/unit/test_customer_snapshot_crud.py`

**Interfaces:**
- New route: `PATCH /v1/customers/{customer_id}/license-snapshot`.
- Request: `CustomerLicenseSnapshotUpdate`.
- Response: existing `CustomerResponse`.

- [ ] **Step 1: Add failing route tests**

Assert that the route accepts a valid trial snapshot, clears both type/date when date is cleared, rejects a missing type with a non-null date, rejects stale version, does not call LicenseApplication or approval code, emits `CUSTOMER_LICENSE_SNAPSHOT_UPDATED`, and enqueues a partial customer refresh. Run the focused API test and confirm these tests fail before implementation.

- [ ] **Step 2: Implement the route**

Resolve `_get_editable_customer`; call `customer_crud.update_license_snapshot`; log with current user/team; call `_persist_customer_business_object_refresh_after_commit` with `source_type="customer"`, summary `客户授权汇总已更新，刷新客户智能档案`, and payload `{ change_type: "license_snapshot_updated", changed_fields: ["license_type", "license_expiry_date"] }`; return `_customer_response(db, updated)`.

- [ ] **Step 3: Run focused backend tests and commit**

```bash
cd CRM-Server && pytest tests/unit/api/test_customer_edit_api.py tests/unit/test_customer_snapshot_crud.py -q

git add CRM-Server/app/api/customers.py CRM-Server/app/crud/customer.py CRM-Server/app/constants/operation_log_events.py CRM-Server/tests/unit/api/test_customer_edit_api.py CRM-Server/tests/unit/test_customer_snapshot_crud.py
git commit -m "feat(customer): add license snapshot editing"
```

### Task 6: Integrate progressive disclosure into CustomerFormDialog

**Files:**
- Modify: `CRM-Client/src/components/dialogs/CustomerFormDialog.vue`
- Modify: `CRM-Client/src/components/dialogs/__tests__/CustomerFormDialog.test.ts`
- Modify: `CRM-Client/src/views/Customers.vue:687-733,1359-1364`
- Modify: `CRM-Client/src/views/CustomerDetailSheet.vue:792-806,1946-1954`

**Interfaces:**
- `CustomerFormDialog` keeps existing `update:open` and `success` events and adds `refresh: []` for inline lifecycle/snapshot writes that keep the Dialog open.
- Ordinary profile save emits `success` and closes when no inline section remains dirty.
- Lifecycle and license snapshot actions emit `refresh` and keep the Dialog open.

- [ ] **Step 1: Write failing dialog behavior tests**

Add tests for: default collapsed trigger with `aria-expanded=false`; industry-only dirty-diff PUT; failed license snapshot preserving input and Dialog; lifecycle 0→1 calling the current version and emitting only `refresh`. Run the focused test and confirm failure before implementation.

- [ ] **Step 2: Add state and dirty baselines**

Add typed refs for `moreInfoOpen`, hierarchy loading/error, lifecycle submitting/error, license submitting/error, license type/date baseline, and current status. Use a computed `writeSubmitting` for the close guard. Reset the collapse on every new session. Count populated low-frequency values (`industry`, `license_type`, `license_expiry_date`) in the trigger summary; status is not counted.

Apply detail values to current and initial baselines; do not send them in create mode.

- [ ] **Step 3: Render the collapsed section**

Use existing `Collapsible`, `CollapsibleTrigger`, and `CollapsibleContent` with stable `id`, visible `更多客户信息`, `aria-expanded`, and `aria-controls`. On first expand call `getIndustryHierarchy`; on failure disable only industry and show retry. Render the industry selector, 0/1 lifecycle section or read-only 2/3 hint, and license type/date section with derived badge, fixed warning, clear action, and `保存授权信息`.

- [ ] **Step 4: Implement the three save paths**

Ordinary profile save calls `buildCustomerUpdatePayload`; if null, issue no PUT. Lifecycle calls `updateCustomerLifecycleStatus({ status, expected_version })`, updates version/status, emits `refresh`, and keeps the Dialog. Snapshot calls `updateCustomerLicenseSnapshot`, updates version/baseline, emits `refresh`, and shows `客户授权汇总已更新`. Never call a LicenseApplication API. Disable all action groups while any write is pending. Auto-expand before focusing inline errors.

- [ ] **Step 5: Wire parents and run focused tests**

`Customers.vue` handles `@refresh` by re-fetching the list without closing the Dialog. `CustomerDetailSheet.vue` reloads current customer data and related panels while keeping the Dialog open. Existing ordinary `@success` behavior remains unchanged.

Run:

```bash
cd CRM-Client && npm run test:unit -- --run src/components/dialogs/__tests__/CustomerFormDialog.test.ts
```

Expected: PASS. Commit:

```bash
git add CRM-Client/src/components/dialogs/CustomerFormDialog.vue CRM-Client/src/components/dialogs/__tests__/CustomerFormDialog.test.ts CRM-Client/src/views/Customers.vue CRM-Client/src/views/CustomerDetailSheet.vue
git commit -m "feat(customer): add progressive edit dialog sections"
```

### Task 7: Add frontend API and schema coverage

**Files:**
- Modify: `CRM-Client/src/api/customer.ts`
- Modify: `CRM-Client/src/schemas/customer.ts`
- Create: `CRM-Client/src/api/__tests__/customer.test.ts` if no customer API test file exists

**Interfaces:**
- `updateCustomerLifecycleStatus(customerId, data)` calls `/lifecycle-status` and parses `CustomerResponseSchema`.
- `updateCustomerLicenseSnapshot(customerId, data)` calls `/license-snapshot` and parses `CustomerResponseSchema`.
- `getIndustryHierarchy()` parses the hierarchy schema, including empty child arrays.

- [ ] **Step 1: Write failing API contract tests**

Mock the existing request wrapper and assert exact paths and payloads for lifecycle, snapshot, and hierarchy calls. The lifecycle payload must include `expected_version`; the snapshot payload must contain only its three defined fields.

- [ ] **Step 2: Implement and run API tests**

Add typed interfaces and methods; keep response parsing through `CustomerResponseSchema` and `CustomerIndustryHierarchySchema`. Run and commit:

```bash
cd CRM-Client && npm run test:unit -- --run src/api/__tests__/customer.test.ts

git add CRM-Client/src/api/customer.ts CRM-Client/src/schemas/customer.ts CRM-Client/src/api/__tests__/customer.test.ts
git commit -m "feat(customer): add lifecycle and snapshot API clients"
```

### Task 8: Complete backend API authorization, team isolation, audit, and intelligence tests

**Files:**
- Modify: `CRM-Server/tests/unit/api/test_customer_edit_api.py`
- Modify: `CRM-Server/tests/unit/test_customer_snapshot_crud.py`
- Modify: `CRM-Server/tests/unit/test_customer_status_transition_service.py`
- Modify: `CRM-Server/app/api/customers.py` only for error mapping exposed by a failing test

- [ ] **Step 1: Add failing route tests**

Assert no-edit permission receives 403 for both new PATCH routes; cross-team customers are not accessible; valid industry codes work; absent/inactive non-current industry codes fail; retained current inactive codes are accepted; each successful write increments version once.

- [ ] **Step 2: Add failing audit and intelligence assertions**

Monkeypatch `operation_log_service.log` and `customer_business_object_intelligence_service.enqueue_object_change_refresh_after_commit`. Assert ordinary PUT, lifecycle PATCH, and snapshot PATCH emit the correct event type, changed fields, before/after values, actor, and partial refresh payload.

- [ ] **Step 3: Run focused tests and commit**

```bash
cd CRM-Server && pytest tests/unit/api/test_customer_edit_api.py tests/unit/test_customer_snapshot_crud.py tests/unit/test_customer_status_transition_service.py -q

git add CRM-Server/app/api/customers.py CRM-Server/tests/unit/api/test_customer_edit_api.py CRM-Server/tests/unit/test_customer_snapshot_crud.py CRM-Server/tests/unit/test_customer_status_transition_service.py
git commit -m "test(customer): verify edit workflow boundaries"
```

### Task 9: Frontend recovery and accessibility coverage

**Files:**
- Modify: `CRM-Client/src/components/dialogs/__tests__/CustomerFormDialog.test.ts`
- Modify: `CRM-Client/src/components/crmwolf/__tests__/IndustryHierarchySelectField.test.ts`
- Modify: `CRM-Client/src/components/dialogs/CustomerFormDialog.vue` only for behavior exposed by a failing test

- [ ] **Step 1: Add failing recovery tests**

Cover hierarchy load failure with industry-only disable/retry; snapshot failure retaining type/date and Dialog; lifecycle failure retaining target; collapsed-area error auto-expansion and focus; discard guard for ordinary/inline dirty state; ordinary save emitting `success` and closing; inline save emitting only `refresh`.

- [ ] **Step 2: Run focused tests and commit**

```bash
cd CRM-Client && npm run test:unit -- --run src/components/dialogs/__tests__/CustomerFormDialog.test.ts src/components/crmwolf/__tests__/IndustryHierarchySelectField.test.ts

git add CRM-Client/src/components/dialogs/CustomerFormDialog.vue CRM-Client/src/components/dialogs/__tests__/CustomerFormDialog.test.ts CRM-Client/src/components/crmwolf/__tests__/IndustryHierarchySelectField.test.ts
git commit -m "test(customer): cover progressive edit recovery"
```

### Task 10: Final verification and UI smoke test

**Files:**
- No new production files. Update only affected tests or design-system documentation if a real verification failure requires it.

- [ ] **Step 1: Run focused backend verification**

```bash
cd CRM-Server && pytest tests/unit/test_customer_edit_contracts.py tests/unit/test_customer_snapshot_crud.py tests/unit/test_customer_status_transition_service.py tests/unit/api/test_customer_edit_api.py tests/unit/test_customer_update_concurrency.py -q
```

Expected: all selected tests pass with zero failures.

- [ ] **Step 2: Run focused frontend verification**

```bash
cd CRM-Client && npm run test:unit -- --run src/components/dialogs/__tests__/CustomerFormDialog.test.ts src/components/crmwolf/__tests__/IndustryHierarchySelectField.test.ts src/components/dialogs/__tests__/customerFormDiff.test.ts src/api/__tests__/customer.test.ts
```

Use the actual filenames created in prior tasks; do not omit focused tests.

- [ ] **Step 3: Run type checks and lint once**

```bash
cd CRM-Client && npm run type-check && npm run lint
cd CRM-Server && ruff check app/ tests/unit/test_customer_edit_contracts.py tests/unit/test_customer_snapshot_crud.py tests/unit/test_customer_status_transition_service.py tests/unit/api/test_customer_edit_api.py && mypy app/
```

- [ ] **Step 4: Run the actual UI smoke path**

Start the client with the repository’s existing dev command, open `/customers` in Chromium, and verify:

1. Edit opens with `更多客户信息` collapsed;
2. opening it loads grouped searchable industry options;
3. selecting a second-level industry shows the full path;
4. ordinary save sends only changed fields and refreshes list/detail;
5. lifecycle 0↔1 action stays in the Dialog and refreshes status;
6. license snapshot save shows the fixed warning and updates the derived badge;
7. failed inline writes keep input and retry context;
8. at narrow viewport the Dialog has one internal scroll container and no horizontal overflow.

- [ ] **Step 5: Review the final diff**

Run `git diff --check` and review only files owned by this feature. Do not reset or overwrite unrelated user changes. Commit any required correction with a focused message.

## Self-Review Checklist

- [x] Every design requirement maps to at least one task and observable verification.
- [x] No step relies on an undefined symbol or an unnamed neighboring task.
- [x] Legacy `CustomerStatusUpdate` and new `CustomerLifecycleStatusUpdate` are not conflated.
- [x] The plan uses the real existing test filename `CustomerFormDialog.test.ts` with matching case.
- [x] No migration is proposed; all new writes target existing columns.
- [x] License snapshot writes cannot reach LicenseApplication or approval code.
- [x] Industry selection uses the existing database hierarchy and existing Combobox primitives.
- [x] Dirty diff prevents untouched collapsed fields from being sent.
- [x] TDD red/green commands and final smoke path are explicit.

## Handoff

After the user approves this plan, use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement tasks in order. Review after each task; do not run project-wide validation between parallel tasks. Run Task 10 once after all implementation tasks are integrated.
