# Lead Conversion Dialog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let authorized users convert a lead to a customer from the lead detail Sheet through a validated, recoverable shadcn-vue Dialog, then remove the obsolete standalone conversion route and page.

**Architecture:** `LeadDetailSheet.vue` owns the conversion intent, form state, dirty-state protection, procurement-method loading state, validation state, and submission lifecycle. `Leads.vue` opens the Sheet with an `open-conversion-dialog` input only for the explicit list-row conversion action; ordinary detail navigation continues to show only the Sheet. The existing `/v1/customers/convert-from-lead` endpoint creates the customer and inherits the lead city server-side, so the dialog displays city as read-only and submits only its supported request contract.

**Tech Stack:** Vue 3 Composition API, TypeScript, vue-router, Vitest + Vue Test Utils, shadcn-vue/Reka UI primitives, lucide-vue-next, vue-sonner, V2 SCSS design tokens.

## Global Constraints

- Use only installed shadcn-vue primitives: `Dialog`, `Input`, `Label`, `Select`, `Button`, `Skeleton`, and `AlertDialog` from `CRM-Client/src/components/ui/`.
- Use `lucide-vue-next` for icons and the existing `vue-sonner` + `handleApiError` feedback path; do not use Element Plus or the deleted `@/utils/errorMessages` module.
- Import styles only with `@use '@/styles/variables-v2.scss' as *;`; use only `-v2` design tokens and preserve shadcn-vue's native interaction/motion behavior.
- Customer city is read-only because `CRM-Server/app/crud/customer.py:288-300` copies it from the lead and `ConvertLeadToCustomer` does not accept `city`.
- A list-row conversion action must auto-open the conversion form after Sheet detail data and procurement choices are ready; a normal detail action must not.
- Required errors appear below their respective field, the first invalid field receives focus, and modified form dismissal requires a discard confirmation.
- During submission, prevent button, Escape, overlay, and Sheet-close dismissal; retain all entered data after a recoverable request failure.
- Keep unrelated existing working-tree changes intact; do not modify `MyLeads.vue` in this feature.

---

## File Structure

- Modify: `CRM-Client/src/views/LeadDetailSheet.vue` — owns the new dialog state machine, API calls, field validation, dismissal behavior, and shadcn-vue dialog markup.
- Modify: `CRM-Client/src/views/Leads.vue` — distinguishes list “view” from list “convert” intent and forwards auto-open intent to the Sheet.
- Modify: `CRM-Client/src/router/index.ts` — removes the two standalone lead conversion routes.
- Delete: `CRM-Client/src/views/LeadConvert.vue` — obsolete page containing the unresolved import of `@/utils/errorMessages`.
- Create: `CRM-Client/tests/views/LeadDetailSheet.conversion.spec.ts` — regression tests for dialog state, validation, API payload, failure retention, and list-triggered auto-open behavior.
- Create: `CRM-Client/tests/views/Leads.conversion.spec.ts` — regression test that the row conversion action passes the conversion intent to `LeadDetailSheet` rather than navigating to the deleted route.

## Task 1: Add conversion dialog behavior to the lead detail Sheet

**Files:**
- Modify: `CRM-Client/src/views/LeadDetailSheet.vue:18-257` and `CRM-Client/src/views/LeadDetailSheet.vue:452-end`
- Test: `CRM-Client/tests/views/LeadDetailSheet.conversion.spec.ts`

**Interfaces:**
- Consumes: `customerApi.convertLeadToCustomer(data: ConvertLeadToCustomer): Promise<ConvertResponse>` from `@/api/customer`.
- Consumes: `procurementApi.getProcurementMethodOptions(): Promise<ProcurementMethodOption[]>` from `@/api/procurement`.
- Produces: optional prop `openConversionDialog?: boolean` and emitted `update:openConversionDialog` boolean acknowledgement, used by `Leads.vue` in Task 2.
- Produces: `openConversionDialog()`, `submitConversion()`, `requestConversionDialogClose()`, and `requestSheetClose()` event handlers that retain or discard form data according to the confirmed specification.

- [ ] **Step 1: Write the failing Sheet conversion tests**

Create `CRM-Client/tests/views/LeadDetailSheet.conversion.spec.ts` with mocked router, lead/customer/procurement APIs, `vue-sonner`, and `handleApiError`. Stub heavyweight Sheet and FollowUp subcomponents, but do not stub the conversion form's dialog, input, select, or buttons. Include the following executable behavior checks:

```ts
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LeadDetailSheet from '@/views/LeadDetailSheet.vue'
import customerApi from '@/api/customer'
import procurementApi from '@/api/procurement'
import { leadApi } from '@/api/lead'

vi.mock('@/api/customer', () => ({ default: { convertLeadToCustomer: vi.fn() } }))
vi.mock('@/api/procurement', () => ({ default: { getProcurementMethodOptions: vi.fn() } }))
vi.mock('@/api/lead', () => ({ leadApi: { getLeadDetail: vi.fn(), getLeadScore: vi.fn(), addFollowUp: vi.fn(), deleteFollowUp: vi.fn() } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('vue-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

describe('LeadDetailSheet conversion dialog', () => {
  beforeEach(() => {
    vi.mocked(leadApi.getLeadDetail).mockResolvedValue({
      id: 7,
      lead_name: '星海科技',
      city: '上海',
      status: 1,
      follow_ups: [],
    })
    vi.mocked(leadApi.getLeadScore).mockResolvedValue({ details: [] })
    vi.mocked(procurementApi.getProcurementMethodOptions).mockResolvedValue([
      { id: 3, code: 'bidding', name: '招投标' },
    ])
  })

  it('auto-opens for list conversion intent and submits only supported request fields', async () => {
    vi.mocked(customerApi.convertLeadToCustomer).mockResolvedValue({ customer_id: 42, contact_id: 9, message: 'ok' })
    const wrapper = mount(LeadDetailSheet, {
      props: { visible: true, leadId: 7, openConversionDialog: true },
      global: { stubs: { FollowUpList: true, LeadFormDialog: true } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('转化为客户')
    expect((wrapper.get('#conversion-account-name').element as HTMLInputElement).value).toBe('星海科技')
    expect(wrapper.text()).toContain('上海')

    await wrapper.get('[data-test="procurement-method-trigger"]').trigger('click')
    await wrapper.get('[data-test="procurement-method-3"]').trigger('click')
    await wrapper.get('[data-test="submit-conversion"]').trigger('click')

    expect(customerApi.convertLeadToCustomer).toHaveBeenCalledWith({
      lead_id: 7,
      account_name: '星海科技',
      address: undefined,
      default_procurement_method_id: 3,
    })
  })

  it('keeps the dialog and entered form values open after conversion fails', async () => {
    vi.mocked(customerApi.convertLeadToCustomer).mockRejectedValue(new Error('network failed'))
    const wrapper = mount(LeadDetailSheet, {
      props: { visible: true, leadId: 7, openConversionDialog: true },
      global: { stubs: { FollowUpList: true, LeadFormDialog: true } },
    })
    await flushPromises()

    await wrapper.get('#conversion-account-name').setValue('星海科技（华东）')
    await wrapper.get('[data-test="procurement-method-trigger"]').trigger('click')
    await wrapper.get('[data-test="procurement-method-3"]').trigger('click')
    await wrapper.get('[data-test="submit-conversion"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('转化为客户')
    expect((wrapper.get('#conversion-account-name').element as HTMLInputElement).value).toBe('星海科技（华东）')
  })

  it('renders inline required errors and focuses the first invalid field', async () => {
    const wrapper = mount(LeadDetailSheet, {
      props: { visible: true, leadId: 7, openConversionDialog: true },
      global: { stubs: { FollowUpList: true, LeadFormDialog: true } },
    })
    await flushPromises()

    await wrapper.get('#conversion-account-name').setValue('')
    await wrapper.get('[data-test="submit-conversion"]').trigger('click')

    expect(wrapper.text()).toContain('请输入客户公司名称')
    expect(document.activeElement).toBe(wrapper.get('#conversion-account-name').element)
  })
})
```

- [ ] **Step 2: Run the new test file to verify it fails**

Run:

```bash
cd CRM-Client && npm run test:unit -- tests/views/LeadDetailSheet.conversion.spec.ts
```

Expected: FAIL because `LeadDetailSheet` does not yet accept `openConversionDialog`, render conversion controls, or expose the required test targets.

- [ ] **Step 3: Define typed conversion state and API helpers in `LeadDetailSheet.vue`**

Add the prop and imports beside the component's existing typed props and API imports. Keep the current `visible` and `leadId` contract unchanged:

```ts
import { nextTick, ref, reactive, watch, computed } from 'vue'
import { toast } from 'vue-sonner'
import { Loader2 } from 'lucide-vue-next'
import customerApi from '@/api/customer'
import procurementApi, { type ProcurementMethodOption } from '@/api/procurement'
import { handleApiError } from '@/utils/errorHandler'

interface Props {
  leadId: number | null
  visible: boolean
  openConversionDialog?: boolean
}

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'update:openConversionDialog': [value: boolean]
  'refresh': []
}>()

const conversionDialogOpen = ref(false)
const conversionSubmitting = ref(false)
const procurementOptionsLoading = ref(false)
const procurementOptionsFailed = ref(false)
const procurementMethodOptions = ref<ProcurementMethodOption[]>([])
const conversionErrors = reactive({ accountName: '', procurementMethod: '' })
const conversionForm = reactive({
  accountName: '',
  address: '',
  procurementMethodId: undefined as number | undefined,
})
const conversionInitialForm = ref({ accountName: '', address: '', procurementMethodId: undefined as number | undefined })
const conversionAccountNameInput = ref<HTMLInputElement | null>(null)

const conversionFormDirty = computed(() =>
  conversionForm.accountName !== conversionInitialForm.value.accountName ||
  conversionForm.address !== conversionInitialForm.value.address ||
  conversionForm.procurementMethodId !== conversionInitialForm.value.procurementMethodId,
)
```

Implement the supporting helpers below the existing `handleConvert` area. `loadProcurementMethodOptions` must set an inline retry state while still calling the centralized API error handler; `initializeConversionForm` resets from the currently loaded lead; `openConversionDialog` performs both operations before opening; `validateConversionForm` sets adjacent errors and focuses the name control first.

```ts
const loadProcurementMethodOptions = async (): Promise<boolean> => {
  procurementOptionsLoading.value = true
  procurementOptionsFailed.value = false
  try {
    procurementMethodOptions.value = await procurementApi.getProcurementMethodOptions()
    return true
  } catch (error) {
    procurementMethodOptions.value = []
    procurementOptionsFailed.value = true
    handleApiError(error, '获取采购方式')
    return false
  } finally {
    procurementOptionsLoading.value = false
  }
}

const initializeConversionForm = (): void => {
  const initial = {
    accountName: leadData.value?.lead_name ?? '',
    address: '',
    procurementMethodId: undefined as number | undefined,
  }
  Object.assign(conversionForm, initial)
  conversionInitialForm.value = { ...initial }
  Object.assign(conversionErrors, { accountName: '', procurementMethod: '' })
}

const openConversionDialog = async (): Promise<void> => {
  if (!leadData.value || conversionSubmitting.value) return
  initializeConversionForm()
  await loadProcurementMethodOptions()
  conversionDialogOpen.value = true
  await nextTick()
  conversionAccountNameInput.value?.focus()
}

const validateConversionForm = async (): Promise<boolean> => {
  Object.assign(conversionErrors, {
    accountName: conversionForm.accountName.trim() ? '' : '请输入客户公司名称',
    procurementMethod: conversionForm.procurementMethodId ? '' : '请选择默认采购方式',
  })
  if (conversionErrors.accountName) {
    await nextTick()
    conversionAccountNameInput.value?.focus()
    return false
  }
  return !conversionErrors.procurementMethod
}
```

- [ ] **Step 4: Implement safe closing, automatic open intent, and conversion submission**

Replace the previous direct navigation implementation of `handleConvert` with `openConversionDialog`. Add an `AlertDialog`-based discard confirmation state and prevent `Dialog`/`Sheet` closing while `conversionSubmitting` is true. When the form is dirty, retain the pending close action until the user explicitly selects “放弃填写”; otherwise close normally. Use an explicit `clearConversionIntent` callback so `Leads.vue` cannot repeatedly reopen the Dialog after the user cancels.

```ts
const discardConversionDialogOpen = ref(false)
const pendingConversionClose = ref<(() => void) | null>(null)

const performConversionClose = (): void => {
  conversionDialogOpen.value = false
  emit('update:openConversionDialog', false)
}

const requestConversionDialogClose = (): void => {
  if (conversionSubmitting.value) return
  if (!conversionFormDirty.value) {
    performConversionClose()
    return
  }
  pendingConversionClose.value = performConversionClose
  discardConversionDialogOpen.value = true
}

const requestSheetClose = (): void => {
  if (conversionSubmitting.value) return
  if (!conversionDialogOpen.value) {
    closeSheet()
    return
  }
  if (!conversionFormDirty.value) {
    performConversionClose()
    closeSheet()
    return
  }
  pendingConversionClose.value = () => {
    performConversionClose()
    closeSheet()
  }
  discardConversionDialogOpen.value = true
}

const confirmDiscardConversion = (): void => {
  discardConversionDialogOpen.value = false
  pendingConversionClose.value?.()
  pendingConversionClose.value = null
}

const submitConversion = async (): Promise<void> => {
  if (conversionSubmitting.value || !(await validateConversionForm())) return
  conversionSubmitting.value = true
  try {
    const result = await customerApi.convertLeadToCustomer({
      lead_id: leadData.value!.id,
      account_name: conversionForm.accountName.trim(),
      address: conversionForm.address.trim() || undefined,
      default_procurement_method_id: conversionForm.procurementMethodId,
    })
    toast.success('线索已转化为客户')
    performConversionClose()
    closeSheet()
    emit('refresh')
    await router.push(`/customers/${result.customer_id}`)
  } catch (error) {
    handleApiError(error, '转化线索')
  } finally {
    conversionSubmitting.value = false
  }
}

watch(() => props.openConversionDialog, async (shouldOpen) => {
  if (shouldOpen && props.visible && leadData.value) {
    await openConversionDialog()
  }
})

watch(() => props.visible, async (visible) => {
  if (visible && props.leadId) {
    await fetchLeadDetail()
    if (props.openConversionDialog) await openConversionDialog()
  }
})
```

Remove the old simpler `watch(() => props.visible, ...)` after replacing it with the awaited version above so the detail request and auto-open intent run in one deterministic order. Preserve any existing follow-up and edit Sheet behavior.

- [ ] **Step 5: Render the shadcn-vue dialog and discard confirmation**

Import `Dialog`, `DialogContent`, `DialogDescription`, `DialogFooter`, `DialogHeader`, `DialogTitle`, `AlertDialog`, `AlertDialogAction`, `AlertDialogCancel`, `AlertDialogContent`, `AlertDialogDescription`, `AlertDialogFooter`, `AlertDialogHeader`, `AlertDialogTitle`, `Select`, `SelectContent`, `SelectGroup`, `SelectItem`, `SelectTrigger`, `SelectValue`, and `Skeleton` from their existing `@/components/ui/*` modules.

Place the following markup after the root Sheet and before the current follow-up Dialog. Bind `@update:open` to `requestConversionDialogClose` rather than using a bare `v-model`, so Escape and overlay dismissal obey dirty/submitting safeguards. Use `@pointer-down-outside.prevent` and `@escape-key-down.prevent` only while `conversionSubmitting` is true; use standard shadcn-vue behavior in all other cases.

```vue
<Dialog :open="conversionDialogOpen" @update:open="requestConversionDialogClose">
  <DialogContent
    class="sm:max-w-[640px]"
    @pointer-down-outside="conversionSubmitting && $event.preventDefault()"
    @escape-key-down="conversionSubmitting && $event.preventDefault()"
  >
    <DialogHeader>
      <DialogTitle>转化为客户</DialogTitle>
      <DialogDescription>
        将线索“{{ leadData?.lead_name }}”转化为客户。转化后会保留线索关联记录。
      </DialogDescription>
    </DialogHeader>

    <form class="flex flex-col gap-4" @submit.prevent="submitConversion">
      <div class="flex flex-col gap-2">
        <Label for="conversion-account-name">客户公司名称 <span aria-hidden="true">*</span></Label>
        <Input
          id="conversion-account-name"
          ref="conversionAccountNameInput"
          v-model="conversionForm.accountName"
          :aria-invalid="Boolean(conversionErrors.accountName)"
          :disabled="conversionSubmitting"
          @blur="validateConversionForm"
        />
        <p v-if="conversionErrors.accountName" class="text-sm text-destructive" role="alert">
          {{ conversionErrors.accountName }}
        </p>
      </div>

      <div class="grid gap-4 sm:grid-cols-2">
        <div class="flex flex-col gap-2">
          <Label>所在城市</Label>
          <p class="min-h-10 rounded-md border border-input bg-muted px-3 py-2 text-sm text-muted-foreground">
            {{ leadData?.city || '未填写' }}
          </p>
        </div>
        <div class="flex flex-col gap-2">
          <Label for="conversion-procurement-method">默认采购方式 <span aria-hidden="true">*</span></Label>
          <Skeleton v-if="procurementOptionsLoading" class="h-10 w-full" />
          <template v-else-if="procurementOptionsFailed">
            <p class="text-sm text-destructive" role="alert">采购方式加载失败，请重新加载后再提交。</p>
            <Button type="button" variant="outline" :disabled="conversionSubmitting" @click="loadProcurementMethodOptions">重新加载</Button>
          </template>
          <template v-else>
            <Select v-model="conversionForm.procurementMethodId" :disabled="conversionSubmitting">
              <SelectTrigger id="conversion-procurement-method" data-test="procurement-method-trigger" :aria-invalid="Boolean(conversionErrors.procurementMethod)">
                <SelectValue placeholder="请选择默认采购方式" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem v-for="option in procurementMethodOptions" :key="option.id" :value="option.id" :data-test="`procurement-method-${option.id}`">
                    {{ option.name }}
                  </SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
            <p v-if="conversionErrors.procurementMethod" class="text-sm text-destructive" role="alert">
              {{ conversionErrors.procurementMethod }}
            </p>
          </template>
        </div>
      </div>

      <div class="flex flex-col gap-2">
        <Label for="conversion-address">公司地址</Label>
        <Input id="conversion-address" v-model="conversionForm.address" :disabled="conversionSubmitting" placeholder="请输入公司地址（选填）" />
      </div>

      <DialogFooter>
        <Button type="button" variant="outline" :disabled="conversionSubmitting" @click="requestConversionDialogClose">取消</Button>
        <Button type="submit" data-test="submit-conversion" :disabled="conversionSubmitting || procurementOptionsLoading || procurementOptionsFailed">
          <Loader2 v-if="conversionSubmitting" data-icon="inline-start" class="animate-spin" />
          {{ conversionSubmitting ? '正在转化' : '确认并转化' }}
        </Button>
      </DialogFooter>
    </form>
  </DialogContent>
</Dialog>

<AlertDialog v-model:open="discardConversionDialogOpen">
  <AlertDialogContent>
    <AlertDialogHeader>
      <AlertDialogTitle>放弃本次转化填写？</AlertDialogTitle>
      <AlertDialogDescription>已填写的客户信息不会保存。</AlertDialogDescription>
    </AlertDialogHeader>
    <AlertDialogFooter>
      <AlertDialogCancel @click="discardConversionDialogOpen = false">继续填写</AlertDialogCancel>
      <AlertDialogAction @click="confirmDiscardConversion">放弃填写</AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>
```

Update the parent Sheet `@update:open` listener to call `requestSheetClose` only on a close request and preserve opening updates:

```vue
<Sheet :open="visible" @update:open="(open) => open ? $emit('update:visible', true) : requestSheetClose()">
```

- [ ] **Step 6: Run the Sheet conversion tests to verify they pass**

Run:

```bash
cd CRM-Client && npm run test:unit -- tests/views/LeadDetailSheet.conversion.spec.ts
```

Expected: PASS. The tests prove the list intent opens the dialog, the payload excludes city, invalid input focuses the customer name, and API failures retain user input.

- [ ] **Step 7: Run scoped static checks**

Run:

```bash
cd CRM-Client && npm run type-check && npm run lint && npm run lint:style
```

Expected: all commands exit `0`. Resolve any type errors introduced by shadcn Select's numeric value typing without weakening types or adding `any`.

- [ ] **Step 8: Commit the Sheet conversion feature**

```bash
git add CRM-Client/src/views/LeadDetailSheet.vue CRM-Client/tests/views/LeadDetailSheet.conversion.spec.ts
git commit -m "feat: convert leads from detail sheet"
```

## Task 2: Route list conversion intent through the detail Sheet

**Files:**
- Modify: `CRM-Client/src/views/Leads.vue:53-58`, `CRM-Client/src/views/Leads.vue:243-246`, `CRM-Client/src/views/Leads.vue:327-329`, `CRM-Client/src/views/Leads.vue:663-668`
- Test: `CRM-Client/tests/views/Leads.conversion.spec.ts`

**Interfaces:**
- Consumes: `LeadDetailSheet` optional prop `openConversionDialog: boolean` and emitted event `update:openConversionDialog: (value: boolean) => void` from Task 1.
- Produces: `conversionDialogRequested: Ref<boolean>` that is true only for direct row conversion actions.

- [ ] **Step 1: Write the failing list conversion routing test**

Create `CRM-Client/tests/views/Leads.conversion.spec.ts`. Stub `LeadDetailSheet` while preserving its prop surface and capture the values passed to it. Mock the permission store so `canConvertRow` is true and mock the lead list API to return one following lead.

```ts
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import Leads from '@/views/Leads.vue'
import { leadApi } from '@/api/lead'

vi.mock('@/api/lead', () => ({
  leadApi: { getLeadList: vi.fn(), getPublicLeads: vi.fn(), getMyLeads: vi.fn() },
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/stores/permissions', () => ({ usePermissionStore: () => ({ hasPermission: () => true, hasAnyPermission: () => true }) }))
vi.mock('@/stores/user', () => ({ useUserStore: () => ({ userInfo: { id: 1 } }) }))
vi.mock('@/stores/header', () => ({ useHeaderStore: () => ({ setTabs: vi.fn(), setActions: vi.fn(), activeTab: 'all' }) }))
vi.mock('@/composables/usePageTitle', () => ({ usePageTitle: vi.fn() }))

describe('Leads conversion entry', () => {
  it('opens the detail Sheet with conversion intent instead of navigating to the deleted conversion route', async () => {
    vi.mocked(leadApi.getLeadList).mockResolvedValue([{ id: 7, lead_name: '星海科技', status: 1, owner_id: '1' }])
    const wrapper = mount(Leads, {
      global: {
        stubs: {
          FilterPanel: true,
          DataTable: { template: '<slot name="cell-actions" :row="{ id: 7, lead_name: \'星海科技\', status: 1, owner_id: \'1\' }" />' },
          TableRowActions: { props: ['primaryActions'], template: '<button data-test="convert-row" @click="primaryActions[1].handler({ id: 7, lead_name: \'星海科技\', status: 1, owner_id: \'1\' })">转化</button>' },
          LeadDetailSheet: { props: ['visible', 'leadId', 'openConversionDialog'], template: '<output data-test="sheet">{{ visible }}|{{ leadId }}|{{ openConversionDialog }}</output>' },
          AILeadCreateDialog: true,
          LeadFormDialog: true,
          StatusBadge: true,
        },
      },
    })
    await flushPromises()
    await wrapper.get('[data-test="convert-row"]').trigger('click')

    expect(wrapper.get('[data-test="sheet"]').text()).toBe('true|7|true')
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd CRM-Client && npm run test:unit -- tests/views/Leads.conversion.spec.ts
```

Expected: FAIL because `handleConvert` still uses `router.push('/leads/:id/convert')` and no conversion intent prop exists.

- [ ] **Step 3: Implement the list-to-Sheet intent state**

Replace the existing route navigation with explicit state setup. Add the ref next to the existing Sheet state and reset it for normal detail actions:

```ts
const sheetVisible = ref(false)
const selectedLeadId = ref<number | undefined>(undefined)
const conversionDialogRequested = ref(false)

const handleViewDetail = (record: Lead): void => {
  selectedLeadId.value = record.id
  conversionDialogRequested.value = false
  sheetVisible.value = true
}

const handleConvert = (record: Lead): void => {
  selectedLeadId.value = record.id
  conversionDialogRequested.value = true
  sheetVisible.value = true
}
```

Pass and clear the intent in the existing Sheet template:

```vue
<LeadDetailSheet
  v-model:visible="sheetVisible"
  v-model:open-conversion-dialog="conversionDialogRequested"
  :lead-id="selectedLeadId ?? null"
  @refresh="fetchLeadList"
/>
```

Remove the now-unused `useRouter` import and `const router = useRouter()` only if no other `router` reference remains in `Leads.vue`.

- [ ] **Step 4: Run the list conversion test to verify it passes**

Run:

```bash
cd CRM-Client && npm run test:unit -- tests/views/Leads.conversion.spec.ts
```

Expected: PASS. No test should observe a router navigation for row conversion.

- [ ] **Step 5: Commit the list entry migration**

```bash
git add CRM-Client/src/views/Leads.vue CRM-Client/tests/views/Leads.conversion.spec.ts
git commit -m "feat: open lead conversion from list sheet"
```

## Task 3: Delete the obsolete standalone conversion route and resolve the build failure

**Files:**
- Modify: `CRM-Client/src/router/index.ts:70-81`
- Delete: `CRM-Client/src/views/LeadConvert.vue`
- Test: `CRM-Client/tests/views/Leads.conversion.spec.ts`

**Interfaces:**
- Consumes: Task 2's Sheet intent flow, which removes all live navigation to `/leads/:id/convert`.
- Produces: a router that no longer imports the obsolete page, removing the unresolved `@/utils/errorMessages` import from the dependency graph.

- [ ] **Step 1: Extend the routing regression test**

Add a source-level assertion to `CRM-Client/tests/views/Leads.conversion.spec.ts` that reads the router module via Vite's supported `?raw` import and verifies no removed route path remains:

```ts
import routerSource from '@/router/index.ts?raw'

it('does not register the removed standalone lead conversion routes', () => {
  expect(routerSource).not.toContain("path: 'leads/:id/convert'")
  expect(routerSource).not.toContain("path: 'leads/convert'")
  expect(routerSource).not.toContain("LeadConvert.vue")
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd CRM-Client && npm run test:unit -- tests/views/Leads.conversion.spec.ts
```

Expected: FAIL because the current router still registers both `LeadConvert.vue` routes.

- [ ] **Step 3: Remove obsolete page and routes**

Delete `CRM-Client/src/views/LeadConvert.vue`. In `CRM-Client/src/router/index.ts`, remove only the two route objects below, retaining neighboring `/leads/my` and `/leads/reminder` routes unchanged:

```ts
{
  path: 'leads/:id/convert',
  name: 'LeadConvert',
  component: () => import('@/views/LeadConvert.vue'),
  meta: { requiresAuth: true }
},
{
  path: 'leads/convert',
  name: 'LeadConvertFromList',
  component: () => import('@/views/LeadConvert.vue'),
  meta: { requiresAuth: true }
},
```

Search the production source after deletion. The only remaining `LeadConvert` references must be historical `.backup` content or non-runtime documentation; remove any live `src/` route/import/navigation reference found.

```bash
cd /Users/eddie/Code/CRMWolf
grep -R "LeadConvert\|/leads/.*convert\|leads/convert\|@/utils/errorMessages" -n CRM-Client/src --exclude='*.backup'
```

Expected: no output.

- [ ] **Step 4: Run focused tests and build verification**

Run:

```bash
cd CRM-Client && npm run test:unit -- tests/views/LeadDetailSheet.conversion.spec.ts tests/views/Leads.conversion.spec.ts
npm run type-check
npm run lint
npm run lint:style
npm run build
```

Expected: every command exits `0`; notably, Vite must no longer report `Failed to resolve import "@/utils/errorMessages" from "src/views/LeadConvert.vue"`.

- [ ] **Step 5: Commit deletion and router cleanup**

```bash
git add CRM-Client/src/router/index.ts CRM-Client/tests/views/Leads.conversion.spec.ts
git rm CRM-Client/src/views/LeadConvert.vue
git commit -m "refactor: remove standalone lead conversion page"
```

## Task 4: Execute end-to-end visual and behavior verification

**Files:**
- Verify only: `CRM-Client/src/views/LeadDetailSheet.vue`, `CRM-Client/src/views/Leads.vue`, `CRM-Client/src/router/index.ts`

**Interfaces:**
- Consumes: completed conversion Dialog, list intent flow, and deleted standalone route from Tasks 1–3.
- Produces: verified acceptance of the actual user journey; no code changes unless a verified defect is discovered.

- [ ] **Step 1: Start the client application**

Run:

```bash
cd CRM-Client && npm run dev
```

Expected: Vite starts without an import-analysis error. Keep the command running while checking the following flows.

- [ ] **Step 2: Verify the detail-Sheet journey**

In the authenticated application, open an eligible following lead's detail Sheet and select “转化为客户”. Verify all of the following before continuing:

```text
- The Sheet stays visible behind a titled Dialog.
- Customer company name is prefilled from the lead.
- City is visibly read-only and matches the lead city.
- Procurement-method Select shows a loading placeholder before options arrive.
- Desktop layout uses a two-column city/procurement row; a narrow viewport collapses it to one column without horizontal scroll.
- Cancel closes an untouched Dialog; edited data triggers the discard confirmation on Cancel, Escape, overlay close, and Sheet close.
```

- [ ] **Step 3: Verify validation, loading, and successful conversion**

Clear the customer name and submit; confirm the adjacent error appears and the input receives focus. Select a procurement method and submit a valid form. Confirm:

```text
- The submit button changes to “正在转化” and all exit controls are disabled while the request is outstanding.
- Exactly one customer is created for one click.
- Success toast says “线索已转化为客户”.
- Dialog and Sheet close, the list refreshes, and the app navigates to /customers/{customer_id}.
- The converted lead no longer offers a conversion action.
```

- [ ] **Step 4: Verify recoverable errors and list shortcut**

Use a controlled API failure or browser network override to make the conversion request fail. Confirm the dialog remains open, entered values remain intact, and the unified error message provides a recovery path. Then, from the list's “转化为客户” row action, confirm the Sheet opens and the conversion Dialog opens automatically only after its details and procurement choices have loaded.

- [ ] **Step 5: Final verification and commit status check**

Run:

```bash
cd CRM-Client && npm run test:unit && npm run build
cd .. && git status --short
```

Expected: all automated checks pass. `git status --short` contains only intended feature files plus pre-existing user changes; do not commit unrelated modifications.
