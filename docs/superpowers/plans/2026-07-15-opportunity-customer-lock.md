# Opportunity Customer Lock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing “所属客户” Select in `OpportunityFormDialog.vue` show the current customer name when launched from a locked customer context, without breaking general opportunity creation where users can choose a customer.

**Architecture:** Keep one shared `OpportunityFormDialog.vue`. Locked callers pass both `customerId` and `customerName`; the dialog injects a single locked customer option immediately, then refreshes details for default opportunity values. Unlocked callers keep the existing fetch/search flow and do not receive locked options.

**Tech Stack:** Vue 3 `<script setup>`, TypeScript, vee-validate, Zod, shadcn-vue Select/Dialog components, Vitest, Vue Test Utils.

## Global Constraints

- Do not add a second “所属客户” field; update the existing Select.
- `customerLocked=false` remains the default and preserves the normal customer dropdown/search flow.
- Locked entry points are `Customers.vue` and `CustomerDetailSheet.vue`.
- `Opportunities.vue` must remain unlocked because it renders `OpportunityFormDialog` with only `open`.
- Submit `customer_id` to the backend as a number.
- Inside the Select form field, use string values to match shadcn-vue Select item values.
- Follow `CRM-Client/CLAUDE.md`: do not introduce new `any`, `as any`, `@ts-ignore`, or non-null assertions.
- Use existing dependencies only; do not add packages.
- Do not run `git commit` unless the user explicitly authorizes commits in the active session.

---

## File Structure

- Modify `CRM-Client/src/components/dialogs/OpportunityFormDialog.vue`
  - Owns customer Select behavior, locked/unlocked branching, form initialization, and create request conversion.
- Modify `CRM-Client/src/views/Customers.vue`
  - Owns row-level customer context for opening the opportunity dialog from the customer list.
- Modify `CRM-Client/src/views/CustomerDetailSheet.vue`
  - Owns current sheet customer context for opening the opportunity dialog from sheet actions and the opportunities panel.
- Modify `CRM-Client/src/api/customer.ts`
  - Adds typed `default_opportunity` metadata already consumed by `OpportunityFormDialog.vue`.
- Create `CRM-Client/tests/components/OpportunityFormDialog.customer-lock.spec.ts`
  - Regression tests for locked display and unlocked dropdown compatibility.

---

### Task 1: Add regression tests for locked and unlocked customer Select behavior

**Files:**
- Create: `CRM-Client/tests/components/OpportunityFormDialog.customer-lock.spec.ts`

**Interfaces:**
- Consumes: current `OpportunityFormDialog` props `open`, `customerId`, `customerLocked` and planned optional prop `customerName`.
- Produces: failing regression coverage proving locked customer names must render before `getCustomerDetail()` resolves, and unlocked mode still fetches selectable customers.

- [ ] **Step 1: Create the failing test file**

Create `CRM-Client/tests/components/OpportunityFormDialog.customer-lock.spec.ts` with this exact content:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'
import OpportunityFormDialog from '@/components/dialogs/OpportunityFormDialog.vue'
import type { CustomerDetailResponse, CustomerResponse } from '@/api/customer'

const customerApi = vi.hoisted(() => ({
  getCustomers: vi.fn(),
  getCustomerDetail: vi.fn(),
}))

const procurementApi = vi.hoisted(() => ({
  getProcurementMethodOptions: vi.fn(),
}))

const opportunityApi = vi.hoisted(() => ({
  createOpportunity: vi.fn(),
}))

const handleApiError = vi.hoisted(() => vi.fn())
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }))

vi.mock('@/api/customer', () => ({ default: customerApi }))
vi.mock('@/api/procurement', () => ({ default: procurementApi }))
vi.mock('@/api/opportunity', () => ({
  opportunityApi,
  LicenseType: { SUBSCRIPTION: 'SUBSCRIPTION', PERPETUAL: 'PERPETUAL' },
  PurchaseType: { NEW: 'NEW', RENEWAL: 'RENEWAL', EXPANSION: 'EXPANSION' },
}))
vi.mock('@/stores/user', () => ({ useUserStore: () => ({ userInfo: { id: 9, name: '当前销售' } }) }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError }))
vi.mock('vue-sonner', () => ({ toast }))

vi.mock('@/components/ui/dialog', () => {
  const passthrough = (name: string) => defineComponent({ name, setup: (_, { slots }) => () => h('div', slots.default?.()) })
  return {
    Dialog: defineComponent({
      name: 'Dialog',
      props: { open: Boolean },
      emits: ['update:open'],
      setup: (props, { slots }) => () => props.open ? h('section', { role: 'dialog' }, slots.default?.()) : null,
    }),
    DialogContent: passthrough('DialogContent'),
    DialogHeader: passthrough('DialogHeader'),
    DialogTitle: passthrough('DialogTitle'),
    DialogFooter: passthrough('DialogFooter'),
  }
})

vi.mock('@/components/ui/alert-dialog', () => {
  const passthrough = (name: string) => defineComponent({ name, setup: (_, { slots }) => () => h('div', slots.default?.()) })
  return {
    AlertDialog: passthrough('AlertDialog'),
    AlertDialogAction: passthrough('AlertDialogAction'),
    AlertDialogCancel: passthrough('AlertDialogCancel'),
    AlertDialogContent: passthrough('AlertDialogContent'),
    AlertDialogDescription: passthrough('AlertDialogDescription'),
    AlertDialogFooter: passthrough('AlertDialogFooter'),
    AlertDialogHeader: passthrough('AlertDialogHeader'),
    AlertDialogTitle: passthrough('AlertDialogTitle'),
  }
})

vi.mock('@/components/ui/form', () => {
  const passthrough = (name: string) => defineComponent({ name, setup: (_, { slots }) => () => h('div', slots.default?.()) })
  return {
    FormControl: passthrough('FormControl'),
    FormItem: passthrough('FormItem'),
    FormLabel: passthrough('FormLabel'),
    FormMessage: passthrough('FormMessage'),
    FormField: defineComponent({
      name: 'FormField',
      props: { name: { type: String, required: true } },
      setup: (props, { slots }) => () => h('div', { 'data-field': props.name }, slots.default?.({
        componentField: {
          name: props.name,
          modelValue: '',
          'onUpdate:modelValue': vi.fn(),
        },
        value: '',
        handleChange: vi.fn(),
      })),
    }),
  }
})

vi.mock('@/components/ui/button', () => ({
  Button: defineComponent({ name: 'Button', props: { type: String }, setup: (props, { slots }) => () => h('button', { type: props.type ?? 'button' }, slots.default?.()) }),
}))

vi.mock('@/components/ui/input', () => ({
  Input: defineComponent({ name: 'Input', setup: () => () => h('input') }),
}))

vi.mock('@/components/ui/date-picker', () => ({
  DatePicker: defineComponent({ name: 'DatePicker', setup: () => () => h('input', { type: 'date' }) }),
}))

vi.mock('@/components/ui/select', () => ({
  Select: defineComponent({
    name: 'Select',
    props: { disabled: Boolean },
    emits: ['update:open', 'update:search'],
    setup: (props, { slots }) => () => h('div', {
      'data-testid': 'select',
      'data-disabled': String(Boolean(props.disabled)),
    }, slots.default?.()),
  }),
  SelectContent: defineComponent({ name: 'SelectContent', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
  SelectItem: defineComponent({
    name: 'SelectItem',
    props: { value: { type: String, required: true } },
    setup: (props, { slots }) => () => h('div', { 'data-testid': 'select-item', 'data-value': props.value }, slots.default?.()),
  }),
  SelectTrigger: defineComponent({ name: 'SelectTrigger', setup: (_, { slots }) => () => h('button', { type: 'button' }, slots.default?.()) }),
  SelectValue: defineComponent({ name: 'SelectValue', props: { placeholder: String }, setup: (props) => () => h('span', props.placeholder) }),
}))

const customerResponse = (id: number, accountName: string): CustomerResponse => ({
  id,
  account_name: accountName,
  industry: null,
  city: '上海',
  address: null,
  company_scale: null,
  source: null,
  status: 0,
  owner_id: '9',
  source_lead_id: null,
  default_procurement_method_id: null,
  loss_reason: null,
  return_reason: null,
  returned_time: null,
  creator_id: '9',
  created_time: '2026-07-15T00:00:00.000Z',
  last_modified_time: '2026-07-15T00:00:00.000Z',
  version: 1,
})

const customerDetail = (id: number, accountName: string): CustomerDetailResponse => ({
  id,
  account_name: accountName,
  industry: null,
  city: '上海',
  address: null,
  company_scale: null,
  source: null,
  status: 0,
  owner_id: '9',
  source_lead_id: null,
  default_procurement_method_id: null,
  creator_id: '9',
  created_time: '2026-07-15T00:00:00.000Z',
  last_modified_time: '2026-07-15T00:00:00.000Z',
  version: 1,
  contacts: [],
  company_background: null,
  company_website: null,
  main_business: null,
  similar_customers: null,
  project_background: null,
  profile_status: null,
  profile_generated_time: null,
  profile_error_message: null,
  default_opportunity: null,
})

describe('OpportunityFormDialog customer lock behavior', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    procurementApi.getProcurementMethodOptions.mockResolvedValue([])
    opportunityApi.createOpportunity.mockResolvedValue({ id: 1 })
  })

  it('shows the locked customer name from props before customer detail finishes loading', async () => {
    let resolveDetail: (value: CustomerDetailResponse) => void = () => undefined
    customerApi.getCustomerDetail.mockReturnValue(new Promise<CustomerDetailResponse>((resolve) => {
      resolveDetail = resolve
    }))

    const wrapper = mount(OpportunityFormDialog, {
      props: {
        open: true,
        customerId: 42,
        customerName: '上海测试客户',
        customerLocked: true,
      },
    })

    await nextTick()

    expect(wrapper.text()).toContain('上海测试客户')
    expect(customerApi.getCustomerDetail).toHaveBeenCalledWith(42)
    expect(wrapper.findAll('[data-testid="select"]')[0]?.attributes('data-disabled')).toBe('true')

    resolveDetail(customerDetail(42, '上海测试客户'))
    await flushPromises()
  })

  it('keeps the customer Select unlocked and populated for general opportunity creation', async () => {
    customerApi.getCustomers.mockResolvedValue([customerResponse(7, '可选择客户')])
    customerApi.getCustomerDetail.mockResolvedValue(customerDetail(7, '可选择客户'))

    const wrapper = mount(OpportunityFormDialog, {
      props: {
        open: true,
      },
    })

    await flushPromises()

    expect(customerApi.getCustomers).toHaveBeenCalledWith({ limit: 50 })
    expect(wrapper.text()).toContain('可选择客户')
    expect(wrapper.findAll('[data-testid="select"]')[0]?.attributes('data-disabled')).toBe('false')
  })
})
```

- [ ] **Step 2: Run the new test to verify the locked-name case fails before implementation**

Run:

```bash
cd CRM-Client && npm run test:unit -- tests/components/OpportunityFormDialog.customer-lock.spec.ts
```

Expected result before Task 2:

```text
FAIL tests/components/OpportunityFormDialog.customer-lock.spec.ts
AssertionError: expected ... to contain '上海测试客户'
```

The unlocked test may pass before implementation. The locked-name test is the regression guard.

- [ ] **Step 3: Prepare commit only if commits are authorized**

If the user has explicitly authorized commits, run:

```bash
git add CRM-Client/tests/components/OpportunityFormDialog.customer-lock.spec.ts
git commit -m "test(opportunity): cover locked customer display"
```

If commits are not authorized, do not commit. Report that the test file is staged-ready but uncommitted.

---

### Task 2: Fix `OpportunityFormDialog.vue` locked customer display without changing unlocked behavior

**Files:**
- Modify: `CRM-Client/src/api/customer.ts:108-138`
- Modify: `CRM-Client/src/components/dialogs/OpportunityFormDialog.vue:40-260`
- Test: `CRM-Client/tests/components/OpportunityFormDialog.customer-lock.spec.ts`

**Interfaces:**
- Consumes: `customerName?: string` from locked callers.
- Produces: `OpportunityFormDialog` props `{ customerId?: number; customerName?: string; customerLocked?: boolean; open: boolean }` and submitted `OpportunityCreate.customer_id: number`.

- [ ] **Step 1: Type the customer default opportunity payload**

In `CRM-Client/src/api/customer.ts`, add this type before `export interface CustomerDetailResponse`:

```ts
export interface CustomerDefaultOpportunity {
  total_amount: number | null
  user_count: number | null
  license_type: string | null
  subscription_years: number | null
  purchase_type: string | null
  expected_closing_date: string | null
  procurement_method_id: number | null
}
```

Then add this property inside `CustomerDetailResponse` after `default_procurement_method_info?: ProcurementMethodInfo | null`:

```ts
  default_opportunity?: CustomerDefaultOpportunity | null
```

- [ ] **Step 2: Update imports and schema in `OpportunityFormDialog.vue`**

In `CRM-Client/src/components/dialogs/OpportunityFormDialog.vue`, update the customer import:

```ts
import customerApi, { type CustomerResponse, type CustomerDetailResponse } from '@/api/customer'
```

Replace the `customer_id` schema line with:

```ts
    customer_id: z.string().min(1, '请选择客户').refine((value) => {
      const parsed = Number(value)
      return Number.isInteger(parsed) && parsed > 0
    }, '请选择客户'),
```

- [ ] **Step 3: Add the `customerName` prop**

Replace the current `Props` and `withDefaults` blocks with:

```ts
interface Props {
  customerId?: number
  customerName?: string
  customerLocked?: boolean
  open: boolean
}

interface Emits {
  (e: 'update:open', value: boolean): void
  (e: 'success'): void
}

const props = withDefaults(defineProps<Props>(), {
  customerId: undefined,
  customerName: undefined,
  customerLocked: false,
  open: false
})
const emit = defineEmits<Emits>()
```

- [ ] **Step 4: Change customer form state to string Select values**

In the `useForm` initial values, replace:

```ts
    customer_id: 0,
```

with:

```ts
    customer_id: '',
```

- [ ] **Step 5: Add customer option helpers**

Below `const purchaseTypeOptions = [...]`, add:

```ts
interface CustomerOption {
  id: number
  account_name: string
}

type CustomerListResponse = CustomerResponse[] | { data?: { items?: CustomerResponse[] } }

const toCustomerOption = (customer: CustomerOption): CustomerOption => ({
  id: customer.id,
  account_name: customer.account_name,
})

const normalizeCustomerList = (response: CustomerListResponse): CustomerOption[] => {
  if (Array.isArray(response)) {
    return response.map(toCustomerOption)
  }
  return response.data?.items?.map(toCustomerOption) ?? []
}

const getLockedCustomerOption = (): CustomerOption | null => {
  if (props.customerId === undefined) return null
  return {
    id: props.customerId,
    account_name: props.customerName?.trim() || `客户 #${props.customerId}`,
  }
}

const setLockedCustomerOption = (): void => {
  const lockedCustomer = getLockedCustomerOption()
  if (lockedCustomer === null) return
  customers.value = [lockedCustomer]
}
```

- [ ] **Step 6: Update `customers` state and `fetchCustomers()`**

Replace:

```ts
const customers = ref<CustomerResponse[]>([])
```

with:

```ts
const customers = ref<CustomerOption[]>([])
```

Replace the body of `fetchCustomers()` with:

```ts
async function fetchCustomers(keyword?: string): Promise<void> {
  loadingCustomers.value = true
  try {
    const params: Record<string, unknown> = { limit: 50 }
    if (keyword) {
      params.keyword = keyword
    }
    const response = await customerApi.getCustomers(params)
    customers.value = normalizeCustomerList(response)
  } catch (error) {
    handleApiError(error, '获取客户列表')
  } finally {
    loadingCustomers.value = false
  }
}
```

- [ ] **Step 7: Replace the dialog-open watcher**

Replace the entire `watch(() => props.open, async (newOpen) => { ... })` block with:

```ts
watch(() => props.open, async (newOpen) => {
  if (newOpen) {
    const currentUserId = userStore.userInfo?.id?.toString() || ''
    const initialCustomerId = props.customerId === undefined ? '' : String(props.customerId)

    resetForm({
      values: {
        customer_id: initialCustomerId,
        opportunity_name: '',
        total_amount: 0,
        user_count: 1,
        license_type: LicenseType.SUBSCRIPTION,
        subscription_years: 1,
        purchase_type: PurchaseType.NEW,
        expected_closing_date: getDefaultDate(),
        procurement_method_id: null,
        owner_id: currentUserId,
        decision_maker_count: null
      }
    })

    if (props.customerLocked && props.customerId !== undefined) {
      setLockedCustomerOption()
    }

    if (props.customerId === undefined) {
      await fetchCustomers()
    } else {
      try {
        const customerDetail: CustomerDetailResponse = await customerApi.getCustomerDetail(props.customerId)
        customers.value = [toCustomerOption(customerDetail)]

        setFieldValue('opportunity_name', `${customerDetail.account_name}项目`)
        if (customerDetail.default_opportunity) {
          setFieldValue('total_amount', customerDetail.default_opportunity.total_amount ?? 0)
          setFieldValue('user_count', customerDetail.default_opportunity.user_count ?? 1)
          setFieldValue('license_type', customerDetail.default_opportunity.license_type ?? LicenseType.SUBSCRIPTION)
          setFieldValue('subscription_years', customerDetail.default_opportunity.subscription_years ?? 1)
          setFieldValue('purchase_type', customerDetail.default_opportunity.purchase_type ?? PurchaseType.NEW)
          if (customerDetail.default_opportunity.expected_closing_date) {
            setFieldValue('expected_closing_date', customerDetail.default_opportunity.expected_closing_date)
          }
          if (customerDetail.default_opportunity.procurement_method_id) {
            setFieldValue('procurement_method_id', customerDetail.default_opportunity.procurement_method_id)
          }
        }
        if (customerDetail.default_procurement_method_id) {
          setFieldValue('procurement_method_id', customerDetail.default_procurement_method_id)
        }
      } catch (error) {
        if (props.customerLocked) {
          setLockedCustomerOption()
        }
        handleApiError(error, '获取客户详情')
      }
    }

    isDirty.value = false
  }
})
```

- [ ] **Step 8: Convert `customer_id` to number on submit**

In `onSubmit`, replace:

```ts
      customer_id: formValues['customer_id'],
```

with:

```ts
      customer_id: Number(formValues['customer_id']),
```

- [ ] **Step 9: Run the dialog regression test**

Run:

```bash
cd CRM-Client && npm run test:unit -- tests/components/OpportunityFormDialog.customer-lock.spec.ts
```

Expected result:

```text
PASS tests/components/OpportunityFormDialog.customer-lock.spec.ts
```

- [ ] **Step 10: Run type-check for changed TypeScript contracts**

Run:

```bash
cd CRM-Client && npm run type-check
```

Expected result:

```text
vue-tsc --noEmit
```

with exit code 0.

- [ ] **Step 11: Prepare commit only if commits are authorized**

If the user has explicitly authorized commits, run:

```bash
git add CRM-Client/src/api/customer.ts CRM-Client/src/components/dialogs/OpportunityFormDialog.vue CRM-Client/tests/components/OpportunityFormDialog.customer-lock.spec.ts
git commit -m "fix(opportunity): show locked customer in create dialog"
```

If commits are not authorized, do not commit. Report the modified files.

---

### Task 3: Pass customer names from locked callers

**Files:**
- Modify: `CRM-Client/src/views/Customers.vue:60-249,657-664`
- Modify: `CRM-Client/src/views/CustomerDetailSheet.vue:665-672`
- Test: `CRM-Client/tests/components/OpportunityFormDialog.customer-lock.spec.ts`

**Interfaces:**
- Consumes: `OpportunityFormDialog` optional prop `customerName?: string` from Task 2.
- Produces: locked callers pass `customerName` while `Opportunities.vue` remains unchanged and unlocked.

- [ ] **Step 1: Add selected opportunity customer name state in `Customers.vue`**

Near the existing opportunity dialog state in `CRM-Client/src/views/Customers.vue`, keep the existing `opportunityDialogOpen` and `opportunityCustomerId`, then add:

```ts
const opportunityCustomerName = ref('')
```

- [ ] **Step 2: Replace the customer-list opportunity handlers**

Replace the existing `handleCreateOpportunity` and `handleOpportunitySuccess` functions with:

```ts
const clearOpportunityCustomer = (): void => {
  opportunityCustomerId.value = null
  opportunityCustomerName.value = ''
}

const handleCreateOpportunity = (record: CustomerResponse): void => {
  opportunityCustomerId.value = record.id
  opportunityCustomerName.value = record.account_name
  opportunityDialogOpen.value = true
}

const handleOpportunityDialogOpenChange = (open: boolean): void => {
  opportunityDialogOpen.value = open
  if (!open) {
    clearOpportunityCustomer()
  }
}

const handleOpportunitySuccess = (): void => {
  handleOpportunityDialogOpenChange(false)
  fetchCustomerList()
}
```

- [ ] **Step 3: Pass `customer-name` to `OpportunityFormDialog` from `Customers.vue`**

Replace the current customer-list dialog usage with:

```vue
    <!-- 新建商机弹窗 -->
    <OpportunityFormDialog
      v-if="opportunityCustomerId !== null"
      :customer-id="opportunityCustomerId"
      :customer-name="opportunityCustomerName"
      :customer-locked="true"
      :open="opportunityDialogOpen"
      @update:open="handleOpportunityDialogOpenChange"
      @success="handleOpportunitySuccess"
    />
```

- [ ] **Step 4: Pass `customer-name` from `CustomerDetailSheet.vue`**

Replace the current `OpportunityFormDialog` block in `CRM-Client/src/views/CustomerDetailSheet.vue` with:

```vue
  <OpportunityFormDialog
    v-if="customerId !== null"
    :customer-id="customerId"
    :customer-name="customer?.account_name"
    :customer-locked="true"
    :open="opportunityDialogOpen"
    @update:open="opportunityDialogOpen = $event"
    @success="handleOpportunitySuccess"
  />
```

- [ ] **Step 5: Confirm `Opportunities.vue` remains unlocked**

Do not modify `CRM-Client/src/views/Opportunities.vue`. Confirm the block remains:

```vue
    <OpportunityFormDialog
      :open="opportunityDialogOpen"
      @update:open="opportunityDialogOpen = $event"
      @success="handleOpportunitySuccess"
    />
```

This is the compatibility guard for the general opportunity creation page.

- [ ] **Step 6: Run the dialog regression test again**

Run:

```bash
cd CRM-Client && npm run test:unit -- tests/components/OpportunityFormDialog.customer-lock.spec.ts
```

Expected result:

```text
PASS tests/components/OpportunityFormDialog.customer-lock.spec.ts
```

- [ ] **Step 7: Run type-check**

Run:

```bash
cd CRM-Client && npm run type-check
```

Expected result:

```text
vue-tsc --noEmit
```

with exit code 0.

- [ ] **Step 8: Prepare commit only if commits are authorized**

If the user has explicitly authorized commits, run:

```bash
git add CRM-Client/src/views/Customers.vue CRM-Client/src/views/CustomerDetailSheet.vue CRM-Client/src/views/Opportunities.vue CRM-Client/src/components/dialogs/OpportunityFormDialog.vue CRM-Client/tests/components/OpportunityFormDialog.customer-lock.spec.ts
git commit -m "fix(customer): pass locked customer names to opportunity dialog"
```

Before running the `git add` command, check whether `CRM-Client/src/views/Opportunities.vue` changed. If it did not change, omit it from `git add`.

If commits are not authorized, do not commit. Report the modified files.

---

### Task 4: Verify the full customer-lock flow

**Files:**
- Verify: `CRM-Client/src/components/dialogs/OpportunityFormDialog.vue`
- Verify: `CRM-Client/src/views/Customers.vue`
- Verify: `CRM-Client/src/views/CustomerDetailSheet.vue`
- Verify: `CRM-Client/src/views/Opportunities.vue`
- Verify: `docs/superpowers/specs/2026-07-15-opportunity-customer-lock-design.md`

**Interfaces:**
- Consumes: Tasks 1 through 3.
- Produces: Evidence that locked and unlocked flows both work.

- [ ] **Step 1: Run targeted tests**

Run:

```bash
cd CRM-Client && npm run test:unit -- tests/components/OpportunityFormDialog.customer-lock.spec.ts
```

Expected result:

```text
PASS tests/components/OpportunityFormDialog.customer-lock.spec.ts
```

- [ ] **Step 2: Run the full unit test suite**

Run:

```bash
cd CRM-Client && npm run test:unit
```

Expected result:

```text
Test Files  ... passed
Tests       ... passed
```

If unrelated pre-existing failures appear, copy the failing test names and error output into the implementation report.

- [ ] **Step 3: Run TypeScript type-check**

Run:

```bash
cd CRM-Client && npm run type-check
```

Expected result:

```text
vue-tsc --noEmit
```

with exit code 0.

- [ ] **Step 4: Run lint on changed source files**

Run:

```bash
cd CRM-Client && npm run lint
```

Expected result:

```text
eslint src --max-warnings=0
```

with exit code 0.

- [ ] **Step 5: Manual browser verification for locked and unlocked paths**

Start the app if it is not already running:

```bash
cd CRM-Client && npm run dev
```

Verify these user-visible flows:

```text
1. 客户管理列表 → 行操作 “新建商机”
   Expected: “所属客户” displays that row's customer name immediately and the Select is disabled.

2. 客户详情 Sheet → 页脚 “新建商机”
   Expected: “所属客户” displays the sheet customer's name immediately and the Select is disabled.

3. 客户详情 Sheet → 商机面板 “新建商机”
   Expected: same behavior as the sheet footer.

4. 商机管理页面 → 顶部 “新建商机”
   Expected: “所属客户” Select is enabled, loads customers, and allows choosing a customer.

5. Open customer A's locked dialog, close it, open customer B's locked dialog
   Expected: customer B's name displays; customer A's name is absent.
```

- [ ] **Step 6: Capture final implementation report**

Report this exact structure:

```text
IMPLEMENTATION REPORT
Files changed:
- CRM-Client/src/api/customer.ts
- CRM-Client/src/components/dialogs/OpportunityFormDialog.vue
- CRM-Client/src/views/Customers.vue
- CRM-Client/src/views/CustomerDetailSheet.vue
- CRM-Client/tests/components/OpportunityFormDialog.customer-lock.spec.ts

Locked flows verified:
- Customers.vue row action: PASS or FAIL with reason
- CustomerDetailSheet.vue footer: PASS or FAIL with reason
- CustomerDetailSheet.vue opportunities panel: PASS or FAIL with reason

Unlocked flow verified:
- Opportunities.vue create action: PASS or FAIL with reason

Automated verification:
- Targeted test: PASS or FAIL with command output
- Full unit suite: PASS or FAIL with command output
- Type-check: PASS or FAIL with command output
- Lint: PASS or FAIL with command output
```

- [ ] **Step 7: Prepare final commit only if commits are authorized**

If the user has explicitly authorized commits and earlier tasks have not committed, run:

```bash
git add CRM-Client/src/api/customer.ts CRM-Client/src/components/dialogs/OpportunityFormDialog.vue CRM-Client/src/views/Customers.vue CRM-Client/src/views/CustomerDetailSheet.vue CRM-Client/tests/components/OpportunityFormDialog.customer-lock.spec.ts docs/superpowers/specs/2026-07-15-opportunity-customer-lock-design.md docs/superpowers/plans/2026-07-15-opportunity-customer-lock.md
git commit -m "fix(opportunity): show locked customer name in create dialog"
```

If commits are not authorized, do not commit. Report that the working tree contains verified uncommitted changes.

---

## Self-Review

**Spec coverage:** Covered locked Sheet and customer-list entry points, ordinary unlocked `Opportunities.vue`, string Select values with numeric submit conversion, customer detail failure fallback, stale customer clearing, and verification paths.

**Placeholder scan:** This plan contains no `TBD`, no empty tasks, no deferred validation, and no unspecified code snippets.

**Type consistency:** `customerName?: string` is introduced once on `OpportunityFormDialog` and consumed by both locked callers. `customer_id` is string inside the form and converted to number only when building `OpportunityCreate`.
