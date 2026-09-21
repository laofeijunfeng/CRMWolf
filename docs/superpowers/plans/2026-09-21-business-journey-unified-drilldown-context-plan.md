# Business Journey Unified Drilldown Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace journey child-object Sheet stacking with one context-aware detail surface that shows a continuous, clickable breadcrumb from journey through contract, payment plan, and payment record.

**Architecture:** `DealJourneyDetailHost` owns one internal `useDetailContextStack` for the journey subtree and renders all child DetailContent components inside one `DetailContextHost`. Optional customer context is displayed as a non-rendered prefix and delegated back to the outer customer surface. Existing child business actions and refresh handlers remain in the Host; only their rendering boundary changes.

**Tech Stack:** Vue 3 `<script setup>`, TypeScript, Pinia, Vue Test Utils, Vitest, CRMWolf `DetailContextHost`/`DetailContextHeader`, existing contract/payment detail content components.

## Global Constraints

- Do not modify backend APIs, schemas, or permissions.
- Do not change business-journey list/board querying, filters, saved views, display mode, or table visuals.
- Do not change contract/payment write APIs, confirmation behavior, approval policy, or refresh ordering.
- Use one `DetailContextHost`; do not add another breadcrumb/navigation implementation.
- Keep the root `DealJourneyDetailContent` instance mounted across child drilldowns.
- Existing `ContractDetailSheet`, `PaymentPlanDetailSheet`, and `PaymentRecordDetailSheet` remain available to other pages, but the journey Host stops using them.
- Disable every child content component's fixed legacy breadcrumb; only the context Header shows navigation.
- CustomerDetailSheet direct contract/payment navigation remains on its current outer context stack.
- Preserve current stale-response guards, error feedback, public IDs, close semantics, and focus restoration.
- Do not touch unrelated dirty files or the concurrent DataTable export design/plan work.

---

### Task 1: Extend the shared detail context host for optional header and focus

**Files:**
- Modify: `CRM-Client/src/components/crmwolf/DetailContextHeader.vue`
- Modify: `CRM-Client/src/components/crmwolf/DetailContextHost.vue`
- Create: `CRM-Client/tests/components/DetailContextHost.spec.ts`

**Interfaces:**

`DetailContextHost` adds:

```ts
interface Props {
  nodes: readonly DetailContextNode[]
  canGoBack: boolean
  showHeader?: boolean
}

interface DetailContextHostExpose {
  focusBackButton: () => void
}
```

`DetailContextHeader` exposes the same `focusBackButton()` method.

- [ ] **Step 1: Write shared host RED tests**

Create `DetailContextHost.spec.ts` with real `DetailContextHost` and a shallow Button/Breadcrumb environment.

Test default compatibility:

```ts
it('shows the context header by default', () => {
  const wrapper = mount(DetailContextHost, {
    props: {
      nodes: [journeyNode],
      canGoBack: false,
    },
    slots: { default: '<div data-testid="body">content</div>' },
  })

  expect(wrapper.find('[data-testid="detail-context-header"]').exists()).toBe(true)
  expect(wrapper.get('[data-testid="body"]').text()).toBe('content')
})
```

Test hidden header without slot remount. Define a stateful slot probe before the test:

```ts
const PersistentBody = defineComponent({
  name: 'PersistentBody',
  setup: () => () => h('input', { 'data-testid': 'persistent-body', value: 'kept' }),
})

it('hides only the header while keeping the same body element', async () => {
  const wrapper = mount(DetailContextHost, {
    props: {
      nodes: [journeyNode],
      canGoBack: false,
      showHeader: true,
    },
    slots: { default: () => h(PersistentBody) },
  })
  const body = wrapper.get('[data-testid="persistent-body"]').element

  await wrapper.setProps({ showHeader: false })

  expect(wrapper.find('[data-testid="detail-context-header"]').exists()).toBe(false)
  expect(wrapper.get('[data-testid="persistent-body"]').element).toBe(body)
})
```

Test focus exposure:

```ts
it('focuses the back button through the host expose API', async () => {
  const wrapper = mount(DetailContextHost, {
    attachTo: document.body,
    props: {
      nodes: [journeyNode, contractNode],
      canGoBack: true,
    },
  })

  ;(wrapper.vm as unknown as DetailContextHostExpose).focusBackButton()
  await nextTick()

  expect(document.activeElement).toBe(wrapper.get('[data-testid="detail-context-back"]').element)
})
```

Register wrapper cleanup with `onTestFinished`.

- [ ] **Step 2: Run RED**

```bash
cd CRM-Client && npx vitest run tests/components/DetailContextHost.spec.ts
```

Expected: FAIL because `showHeader` and exposed focus APIs are absent.

- [ ] **Step 3: Implement the backward-compatible host/header APIs**

In `DetailContextHeader.vue`:

```ts
import { ref } from 'vue'

const backButtonRef = ref<InstanceType<typeof Button> | null>(null)

function focusBackButton(): void {
  const element = backButtonRef.value?.$el as HTMLElement | undefined
  element?.focus()
}

defineExpose({ focusBackButton })
```

Bind `ref="backButtonRef"` on the existing back Button. If the Button ref type is not stable, use a wrapper element ref and `querySelector('button')`; do not change Button.

In `DetailContextHost.vue`:

```ts
const props = withDefaults(defineProps<Props>(), { showHeader: true })
const headerRef = ref<{ focusBackButton: () => void } | null>(null)

function focusBackButton(): void {
  headerRef.value?.focusBackButton()
}

defineExpose({ focusBackButton })
```

Render `DetailContextHeader` with `v-if="showHeader"` and `ref="headerRef"`; keep `.detail-context-host__body` always mounted.

- [ ] **Step 4: Run shared host tests GREEN**

```bash
cd CRM-Client && npx vitest run tests/components/DetailContextHost.spec.ts
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add \
  CRM-Client/src/components/crmwolf/DetailContextHeader.vue \
  CRM-Client/src/components/crmwolf/DetailContextHost.vue \
  CRM-Client/tests/components/DetailContextHost.spec.ts
git commit -m "feat(ui): support persistent detail context headers"
```

---

### Task 2: Move journey child details into one internal context stack

**Files:**
- Modify: `CRM-Client/src/components/business-journey/DealJourneyDetailHost.vue`
- Modify: `CRM-Client/src/components/panels/DealJourneyDetailContent.vue`
- Modify: `CRM-Client/tests/components/DealJourneyDetailHost.spec.ts`
- Modify: `CRM-Client/tests/components/DealJourneyDetailContent.spec.ts`

**Interfaces:**

`DealJourneyDetailHost` props add:

```ts
journeyName?: string
contextPrefix?: readonly DetailContextNode[]
```

`DealJourneyDetailContent` changes only the `view-contract` payload:

```ts
'view-contract': [contract: ContractListResponse]
```

- [ ] **Step 1: Rewrite Host mocks and add RED context tests**

In `DealJourneyDetailHost.spec.ts`:

- Remove mocks/import assertions for `ContractDetailSheet`, `PaymentPlanDetailSheet`, and `PaymentRecordDetailSheet`.
- Add mocks for `DetailContextHost`, `ContractDetailContent`, `PaymentPlanDetailContent`, and `PaymentRecordDetailContent` that expose props/events and render stable test IDs for the active content.
- The `DetailContextHost` mock must render its default slot and expose `nodes`, `canGoBack`, and `showHeader`, so tests observe the component contract rather than source text.
- Pass `journeyName: '华东续约旅程'` in `mountHost()`.

Add tests:

```ts
it('shows journey and contract in one context path without another Sheet', async () => {
  const wrapper = mountHost()
  wrapper.getComponent(DealJourneyDetailContent).vm.$emit('view-contract', contractFixture())
  await nextTick()

  expect(wrapper.getComponent(DetailContextHost).props('nodes')).toMatchObject([
    { type: 'journey', id: 'djy_test', label: '华东续约旅程' },
    { type: 'contract', id: '31', label: '旅程合同' },
  ])
  expect(wrapper.getComponent(ContractDetailContent).props()).toMatchObject({
    contractId: 31,
    embedded: true,
    showBreadcrumb: false,
  })
  expect(wrapper.findComponent({ name: 'ContractDetailSheet' }).exists()).toBe(false)
})
```

```ts
type BreadcrumbPaymentRecord = PaymentRecordInfo & { record_number?: string }

it('builds journey contract plan record breadcrumbs and supports ancestor navigation', async () => {
  const wrapper = mountHost()
  const contract = contractFixture()
  const plan = paymentPlanFixture({ contract_name: contract.contract_name, plan_number: 'PAY-001' })
  const record: BreadcrumbPaymentRecord = {
    ...paymentRecordFixture({ id: 51 }),
    record_number: 'REC-051',
  }

  wrapper.getComponent(DealJourneyDetailContent).vm.$emit('view-contract', contract)
  await nextTick()
  wrapper.getComponent(ContractDetailContent).vm.$emit('view-payment-plan', plan)
  await nextTick()
  wrapper.getComponent(PaymentPlanDetailContent).vm.$emit('record-click', record)
  await nextTick()

  expect(wrapper.getComponent(DetailContextHost).props('nodes').map(node => node.label)).toEqual([
    '华东续约旅程',
    '旅程合同',
    'PAY-001',
    'REC-051',
  ])

  wrapper.getComponent(DetailContextHost).vm.$emit('navigate', 1)
  await nextTick()
  expect(wrapper.findComponent(ContractDetailContent).exists()).toBe(true)
  expect(wrapper.findComponent(PaymentRecordDetailContent).exists()).toBe(false)
})
```

Add tests for:

- direct journey → payment plan auto-inserts contract;
- back from contract returns the same DealJourneyDetailContent wrapper element;
- customer prefix index emits `view-customer` rather than changing internal current node;
- journeyId change resets nodes and child state;
- payment-plan → contract avoids duplicate nodes;
- existing refresh/edit/resubmit/stale-request tests still pass using content components.

- [ ] **Step 2: Write DealJourneyDetailContent event RED test**

Update the ContractsPanel mock so it can emit the actual contract object. Assert:

```ts
expect(wrapper.emitted('view-contract')).toEqual([[contractFixture]])
```

Expected old behavior: emits only numeric ID.

- [ ] **Step 3: Run RED**

```bash
cd CRM-Client && npx vitest run \
  tests/components/DealJourneyDetailHost.spec.ts \
  tests/components/DealJourneyDetailContent.spec.ts
```

Expected: failures from old nested Sheet rendering, absent stack props, and numeric contract payload.

- [ ] **Step 4: Change DealJourneyDetailContent contract event**

Update emit type and handler:

```ts
'view-contract': [contract: ContractListResponse]

function handleViewContract(contract?: ContractListResponse): void {
  if (contract === undefined) return
  emit('view-contract', contract)
}
```

`ContractsPanel` already emits the full row to its local handler; no new request is needed.

- [ ] **Step 5: Implement Host context state**

In `DealJourneyDetailHost.vue`:

- Import `computed`, `nextTick`, `watch`, `DetailContextHost`, `useDetailContextStack`, `DetailContextNode`, and child DetailContent components.
- Remove child Sheet imports and booleans.
- Keep existing dialog/API/action handlers.
- Create an internal root journey node and reset stack on `journeyId`, resolved journey label, or context-prefix identity change.
- Derive `displayNodes`, `currentNode`, `showContextHeader`, and `canGoBack`.
- Track trigger elements by node identity in a `Map<string, HTMLElement>`.

Use these exact label resolvers and keep the shared API type unchanged:

```ts
type BreadcrumbPaymentRecord = PaymentRecordInfo & {
  record_number?: string
}

const journeyLabel = (): string => props.journeyName?.trim()
  || props.journey?.name?.trim()
  || '业务旅程'
const contractLabel = (contract: Pick<ContractListResponse, 'contract_name'>): string =>
  contract.contract_name.trim() || '合同详情'
const planLabel = (plan: PaymentPlanResponse): string =>
  plan.plan_number?.trim() || plan.stage_name.trim() || '回款计划详情'
const recordLabel = (record: PaymentRecordInfo): string => {
  const recordNumber = (record as BreadcrumbPaymentRecord).record_number?.trim()
  return recordNumber || `回款记录 #${record.id}`
}
```

- [ ] **Step 6: Implement navigation handlers**

- `handleViewContract(contract)` resets descendants and pushes/reuses contract.
- `handleViewPaymentPlan(planId, plan)` ensures the plan's contract node follows journey, then pushes plan.
- `handlePaymentRecord(record)` pushes record.
- `handleContextBack()` pops internal stack or emits `view-customer` at prefixed root.
- `handleContextNavigate(displayIndex)` maps prefix versus internal indexes exactly as the spec.
- After back/navigate, `nextTick` and restore trigger focus; fallback to `DetailContextHost.focusBackButton()`.
- `handleContextClose()` emits `close` only.

- [ ] **Step 7: Render one Host and content switch**

Template shape:

```vue
<DetailContextHost
  ref="contextHostRef"
  :nodes="displayNodes"
  :can-go-back="canGoBack"
  :show-header="showContextHeader"
  @back="handleContextBack"
  @navigate="handleContextNavigate"
  @close="handleContextClose"
>
  <div v-show="currentNode?.type === 'journey'" ref="journeyContentContainerRef" class="contents">
    <DealJourneyDetailContent ... />
  </div>
  <ContractDetailContent v-if="currentNode?.type === 'contract'" ... />
  <PaymentPlanDetailContent v-if="currentNode?.type === 'payment-plan'" ... />
  <PaymentRecordDetailContent v-if="currentNode?.type === 'payment-record'" ... />
</DetailContextHost>
```

Use `showBreadcrumb=false` for journey/contract, `embedded` for all content, and preserve existing event handlers.

- [ ] **Step 8: Run Host/content GREEN tests**

```bash
cd CRM-Client && npx vitest run \
  tests/components/DealJourneyDetailHost.spec.ts \
  tests/components/DealJourneyDetailContent.spec.ts
```

Expected: pass.

- [ ] **Step 9: Commit**

```bash
git add \
  CRM-Client/src/components/business-journey/DealJourneyDetailHost.vue \
  CRM-Client/src/components/panels/DealJourneyDetailContent.vue \
  CRM-Client/tests/components/DealJourneyDetailHost.spec.ts \
  CRM-Client/tests/components/DealJourneyDetailContent.spec.ts
git commit -m "feat(journey): unify child detail context"
```

---

### Task 3: Pass journey identity through the standalone page and Sheet

**Files:**
- Modify: `CRM-Client/src/views/DealJourneyDetailSheet.vue`
- Modify: `CRM-Client/src/views/BusinessJourneys.vue`
- Modify: `CRM-Client/tests/components/DealJourneyDetailSheet.spec.ts`
- Modify: `CRM-Client/tests/components/BusinessJourneys.spec.ts`

**Interfaces:**

`DealJourneyDetailSheet` adds:

```ts
journeyName?: string
```

and forwards it to Host.

- [ ] **Step 1: Write RED page/Sheet identity tests**

Sheet test:

```ts
expect(wrapper.getComponent(DealJourneyDetailHost).props()).toMatchObject({
  customerId: 'cus_test',
  customerName: '测试客户',
  journeyId: 'djy_test',
  journeyName: '华东续约旅程',
})
```

Page tests:

- table row click passes the list item's `name`;
- board row click resolves `journey_name` and passes it;
- close clears `journeyName` with other selected state;
- nested `view-customer` behavior remains unchanged;
- no new router navigation.

- [ ] **Step 2: Run RED**

```bash
cd CRM-Client && npx vitest run \
  tests/components/DealJourneyDetailSheet.spec.ts \
  tests/components/BusinessJourneys.spec.ts
```

Expected: journeyName assertions fail.

- [ ] **Step 3: Implement identity propagation**

In `BusinessJourneys.vue`:

```ts
const selectedJourneyName = ref<string | undefined>(undefined)

function findJourneyName(customerId: string, journeyPublicId: string): string | undefined {
  const tableMatch = tableItems.value.find(item => item.customer_id === customerId && item.public_id === journeyPublicId)
  if (tableMatch !== undefined) return tableMatch.name
  return board.value?.columns
    .flatMap(column => column.cards)
    .find(card => card.customer_id === customerId && card.public_id === journeyPublicId)
    ?.journey_name
}
```

Set it in `handleRowClick`, clear it in `clearJourneyDetailSelection`, and bind `:journey-name`.

In `DealJourneyDetailSheet.vue`, declare/default/forward `journeyName`.

- [ ] **Step 4: Run page/Sheet tests GREEN**

```bash
cd CRM-Client && npx vitest run \
  tests/components/DealJourneyDetailSheet.spec.ts \
  tests/components/BusinessJourneys.spec.ts
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add \
  CRM-Client/src/views/DealJourneyDetailSheet.vue \
  CRM-Client/src/views/BusinessJourneys.vue \
  CRM-Client/tests/components/DealJourneyDetailSheet.spec.ts \
  CRM-Client/tests/components/BusinessJourneys.spec.ts
git commit -m "feat(journey): pass journey context into detail sheet"
```

---

### Task 4: Remove duplicate customer context around the journey subtree

**Files:**
- Modify: `CRM-Client/src/views/CustomerDetailSheet.vue`
- Modify: `CRM-Client/tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts`

**Interfaces:**

CustomerDetailSheet passes:

```ts
contextPrefix: [customerNode]
journeyName: selectedJourney?.name
```

- [ ] **Step 1: Write CustomerDetailSheet RED tests**

Add assertions that when a journey is selected:

```ts
expect(wrapper.findAllComponents(DetailContextHost)).toHaveLength(0)
expect(wrapper.getComponent(DealJourneyDetailHost).props('contextPrefix')).toEqual([
  expect.objectContaining({
    type: 'customer',
    id: CUSTOMER_ID,
    label: customerFixture.account_name,
  }),
])
```

The Host stub emits `view-customer(CUSTOMER_ID)`; assert CustomerDetailSheet returns to customer root without emitting `update:visible=false`.

The Host stub emits `close`; assert existing whole-Sheet close behavior remains.

Add a direct-contract regression proving customer root → contract still uses the existing outer `DetailContextHost` and remains unaffected.

- [ ] **Step 2: Run RED**

```bash
cd CRM-Client && npx vitest run tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts
```

Expected: fail because the outer ContextHost still wraps the journey Host and no contextPrefix is passed.

- [ ] **Step 3: Separate journey subtree from outer nested details**

Template structure:

```vue
<DealJourneyDetailHost
  v-if="selectedJourneyId !== null"
  :journey-id="selectedJourneyId"
  :journey-name="selectedJourney?.name"
  :customer-id="customerId ?? ''"
  :customer-name="customer?.account_name"
  :journey="selectedJourney"
  :context-prefix="customerId === null ? [] : [createCustomerContextNode(customerId)]"
  embedded
  :can-edit-customer-context="canEditCurrentCustomer"
  @close="handleContextClose"
  @refresh="handleJourneyDetailRefresh"
  @view-customer="handleJourneyHostViewCustomer"
/>

<DetailContextHost v-else-if="hasNestedDetail" ...>
  <!-- contract/payment direct-entry branches only -->
</DetailContextHost>
```

Implement:

```ts
function handleJourneyHostViewCustomer(customerId: string): void {
  if (customerId === props.customerId) {
    selectedJourneyId.value = null
    resetDetailContext()
    return
  }
  emit('view-customer', customerId)
}
```

Keep `handleContextClose` for Host close.

- [ ] **Step 4: Run CustomerDetailSheet GREEN tests**

```bash
cd CRM-Client && npx vitest run tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add \
  CRM-Client/src/views/CustomerDetailSheet.vue \
  CRM-Client/tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts
git commit -m "refactor(customer): delegate journey drilldown context"
```

---

## Final Verification

- [ ] Run focused suite:

```bash
cd CRM-Client && npx vitest run \
  tests/components/DetailContextHost.spec.ts \
  tests/components/DealJourneyDetailHost.spec.ts \
  tests/components/DealJourneyDetailSheet.spec.ts \
  tests/components/DealJourneyDetailContent.spec.ts \
  tests/components/BusinessJourneys.spec.ts \
  tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts \
  tests/views/ContractDetailSheet.spec.ts \
  tests/views/PaymentPlanDetailSheet.spec.ts \
  tests/views/PaymentRecordDetailSheet.spec.ts
```

- [ ] Run production lint on changed Vue/TS files and design-system governance.

- [ ] Run TypeScript check; changed files must have zero diagnostics. Existing unrelated baseline diagnostics may remain only if reproduced at the starting commit.

- [ ] Real browser smoke both entry paths:

```text
表格 → 旅程 → 合同 → 回款计划 → 回款记录
看板 → 旅程 → 合同 → 回款计划 → 回款记录
```

Verify back, ancestor crumb clicks, close, focus restoration, root journey scroll/Accordion state preservation, customer prefix behavior, and exactly one Sheet portal.

- [ ] Confirm old child Sheet components remain functional through their existing focused tests but are not rendered by `DealJourneyDetailHost`.

- [ ] Confirm unrelated dirty files remain untouched:

```bash
git status --short
git diff --check
```

- [ ] Final code review against `docs/superpowers/specs/2026-09-21-business-journey-unified-drilldown-context-design.md`.
