import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, type PropType } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import CustomerDetailSheet from '@/views/CustomerDetailSheet.vue'
import type { CustomerDetailResponse } from '@/api/customer'
import type { ContractListResponse } from '@/api/contract'
import type { DealJourney } from '@/schemas/dealJourney'
import { usePermissionStore } from '@/stores/permissions'
import { useUserStore } from '@/stores/user'

const routeState = vi.hoisted(() => ({
  path: '/customers',
  query: {} as Record<string, string>,
}))
const routerPush = vi.hoisted(() => vi.fn(() => Promise.resolve()))
const routerReplace = vi.hoisted(() => vi.fn(() => Promise.resolve()))
const customerApi = vi.hoisted(() => ({
  getCustomerDetail: vi.fn(),
  getCustomerMembers: vi.fn(),
}))
const customerActivityApi = vi.hoisted(() => ({ getActivities: vi.fn() }))
const dealJourneyApi = vi.hoisted(() => ({
  listByCustomer: vi.fn(),
  getByCustomer: vi.fn(),
}))
const contractApi = vi.hoisted(() => ({ getCustomerContracts: vi.fn() }))
const paymentApi = vi.hoisted(() => ({ getPaymentPlans: vi.fn() }))
const invoiceApi = vi.hoisted(() => ({ getInvoiceTitles: vi.fn() }))
const deploymentApi = vi.hoisted(() => ({ list: vi.fn() }))
const handleApiError = vi.hoisted(() => vi.fn())
const toast = vi.hoisted(() => ({ success: vi.fn(), info: vi.fn() }))

interface Deferred<T> {
  promise: Promise<T>
  resolve: (value: T | PromiseLike<T>) => void
}

const createDeferred = <T>(): Deferred<T> => {
  let resolveDeferred: ((value: T | PromiseLike<T>) => void) | undefined
  const promise = new Promise<T>(resolve => {
    resolveDeferred = resolve
  })
  if (resolveDeferred === undefined) {
    throw new Error('Deferred resolver was not initialized')
  }
  return { promise, resolve: resolveDeferred }
}

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({ push: routerPush, replace: routerReplace }),
}))
vi.mock('@/api/customer', () => ({ default: customerApi }))
vi.mock('@/api/customerActivity', () => ({ default: customerActivityApi }))
vi.mock('@/api/dealJourney', () => ({ dealJourneyApi, default: dealJourneyApi }))
vi.mock('@/api/contract', () => ({ default: contractApi }))
vi.mock('@/api/payment', () => ({ default: paymentApi }))
vi.mock('@/api/invoice', () => ({ default: invoiceApi }))
vi.mock('@/api/deployment', () => ({ default: deploymentApi }))
vi.mock('@/api/customerProfile', () => ({
  default: {
    getProfile: vi.fn().mockResolvedValue(null),
    getEvidence: vi.fn().mockResolvedValue([]),
    refresh: vi.fn().mockResolvedValue({}),
  },
}))
vi.mock('@/utils/errorHandler', () => ({ handleApiError }))
vi.mock('vue-sonner', () => ({ toast }))

vi.mock('@/components/crmwolf', () => ({
  InputField: defineComponent({
    name: 'InputField',
    inheritAttrs: false,
    props: {
      modelValue: { type: String, default: '' },
      id: String,
      label: String,
      error: String,
      disabled: Boolean,
    },
    emits: ['update:modelValue'],
    setup: (props, { emit, attrs }) => () => h('input', {
      ...attrs,
      id: props.id,
      value: props.modelValue,
      disabled: props.disabled,
      'aria-label': props.label,
      'aria-invalid': props.error !== undefined && props.error !== '' ? 'true' : undefined,
      onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value),
    }),
  }),
  Switch: defineComponent({
    name: 'Switch',
    props: { checked: Boolean, disabled: Boolean, id: String },
    emits: ['update:checked'],
    setup: (props, { emit, attrs }) => () => h('button', {
      ...attrs,
      id: props.id,
      type: 'button',
      role: 'switch',
      'aria-checked': String(props.checked),
      disabled: props.disabled,
      onClick: () => emit('update:checked', !props.checked),
    }),
  }),
  ContextTabs: defineComponent({
    name: 'ContextTabs',
    props: { tabs: Array, activeTab: String },
    emits: ['update:activeTab'],
    setup: (props, { emit }) => () => h('nav', (props.tabs as { key: string; label: string }[]).map(tab => h('button', {
      type: 'button',
      'data-testid': `tab-${tab.key}`,
      'data-active': String(props.activeTab === tab.key),
      onClick: () => emit('update:activeTab', tab.key),
    }, tab.label))),
  }),
}))

vi.mock('@/components/ui/sheet', () => {
  const passthrough = (name: string) => defineComponent({ name, setup: (_, { slots }) => () => h('div', slots.default?.()) })
  return {
    Sheet: defineComponent({
      name: 'Sheet',
      props: { open: Boolean },
      emits: ['update:open'],
      setup: (props, { slots }) => () => props.open ? h('section', { 'data-testid': 'sheet-root' }, slots.default?.()) : null,
    }),
    SheetHeader: passthrough('SheetHeader'),
    SheetFooter: passthrough('SheetFooter'),
  }
})

vi.mock('@/components/ui/detail-sheet', () => ({
  DetailSheetContent: defineComponent({ name: 'DetailSheetContent', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
}))

vi.mock('@/components/ui/button', () => ({
  Button: defineComponent({
    name: 'Button',
    props: { type: String, variant: String, size: String, disabled: Boolean },
    setup: (props, { slots, attrs }) => () => h('button', { ...attrs, type: props.type ?? 'button', disabled: props.disabled }, slots.default?.()),
  }),
}))

vi.mock('@/components/ui/badge', () => ({ Badge: defineComponent({ name: 'Badge', setup: (_, { slots }) => () => h('span', slots.default?.()) }) }))
vi.mock('@/components/ui/card', () => ({
  Card: defineComponent({ name: 'Card', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
  CardContent: defineComponent({ name: 'CardContent', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
}))
vi.mock('@/components/ui/scroll-area', () => ({ ScrollArea: defineComponent({ name: 'ScrollArea', setup: (_, { slots }) => () => h('div', slots.default?.()) }) }))
vi.mock('@/components/ui/progress', () => ({ Progress: defineComponent({ name: 'Progress', setup: () => () => h('div') }) }))
vi.mock('@/components/ui/accordion', () => ({
  Accordion: defineComponent({ name: 'Accordion', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
  AccordionItem: defineComponent({ name: 'AccordionItem', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
  AccordionTrigger: defineComponent({ name: 'AccordionTrigger', setup: (_, { slots }) => () => h('button', { type: 'button' }, slots.default?.()) }),
  AccordionContent: defineComponent({ name: 'AccordionContent', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
}))

vi.mock('@/components/panels/FollowUpPanel.vue', () => ({ default: defineComponent({ name: 'FollowUpPanel', setup: () => () => h('div', 'followup') }) }))
vi.mock('@/components/panels/ContactsPanel.vue', () => ({ default: defineComponent({ name: 'ContactsPanel', setup: () => () => h('div', 'contacts') }) }))
vi.mock('@/components/panels/DealJourneysPanel.vue', () => ({
  default: defineComponent({
    name: 'DealJourneysPanel',
    props: {
      highlightedJourneyId: String,
      restoreFocusJourneyId: String,
    },
    emits: ['view', 'add'],
    setup: (props, { emit }) => () => h('div', {
      'data-testid': 'deal-journeys-panel',
      'data-highlighted-journey-id': props.highlightedJourneyId === undefined ? '' : String(props.highlightedJourneyId),
      'data-restore-focus-journey-id': props.restoreFocusJourneyId === undefined ? '' : String(props.restoreFocusJourneyId),
    }, [
      h('button', { type: 'button', 'data-testid': 'view-journey', onClick: () => emit('view', 'djy_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa') }, 'view journey'),
    ]),
  }),
}))
vi.mock('@/components/panels/ContractsPanel.vue', () => ({
  default: defineComponent({
    name: 'ContractsPanel',
    props: { contracts: { type: Array, default: () => [] } },
    emits: ['view'],
    setup: (props, { emit }) => () => h('div', {
      'data-testid': 'contracts-panel',
      'data-contract-count': String((props.contracts as ContractListResponse[]).length),
    }, [
      h('button', { type: 'button', 'data-testid': 'view-contract', onClick: () => emit('view', 701) }, 'view contract'),
    ]),
  }),
}))
vi.mock('@/components/panels/PaymentsPanel.vue', () => ({ default: defineComponent({ name: 'PaymentsPanel', setup: () => () => h('div', 'payments') }) }))
vi.mock('@/components/panels/InvoicesPanel.vue', () => ({ default: defineComponent({ name: 'InvoicesPanel', setup: () => () => h('div', 'invoices') }) }))
vi.mock('@/components/panels/LicensePanel.vue', () => ({ default: defineComponent({ name: 'LicensePanel', setup: () => () => h('div', 'license') }) }))
vi.mock('@/components/panels/ContractDetailContent.vue', () => ({
  default: defineComponent({
    name: 'ContractDetailContent',
    props: { contractId: Number, embedded: Boolean },
    setup: (props) => () => h('div', {
      'data-testid': 'contract-detail-content',
      'data-contract-id': String(props.contractId),
      'data-embedded': String(props.embedded),
    }),
  }),
}))

vi.mock('@/components/panels/DealJourneyDetailContent.vue', () => ({
  default: defineComponent({
    name: 'DealJourneyDetailContent',
    props: {
      journeyId: String,
      journey: Object as PropType<DealJourney | null>,
      embedded: Boolean,
    },
    emits: ['back', 'refresh', 'view-contract'],
    setup: (props, { emit }) => () => h('div', {
      'data-testid': 'deal-journey-detail',
      'data-journey-id': String(props.journeyId),
      'data-embedded': String(props.embedded),
    }, [
      props.journey?.name ?? '',
      h('button', { type: 'button', 'data-testid': 'back-to-journeys', onClick: () => emit('back') }, 'back'),
      h('button', { type: 'button', 'data-testid': 'detail-refresh', onClick: () => emit('refresh') }, 'refresh'),
      h('button', { type: 'button', 'data-testid': 'view-journey-contract', onClick: () => emit('view-contract', 701) }, 'view contract'),
    ]),
  }),
}))

vi.mock('@/components/dialogs/FollowUpFormDialog.vue', () => ({ default: defineComponent({ name: 'FollowUpFormDialog', setup: () => () => null }) }))
vi.mock('@/components/dialogs/ContactFormDialog.vue', () => ({ default: defineComponent({ name: 'ContactFormDialog', setup: () => () => null }) }))
vi.mock('@/components/dialogs/OpportunityFormDialog.vue', () => ({
  default: defineComponent({
    name: 'OpportunityFormDialog',
    props: {
      open: Boolean,
      customerId: String,
    },
    emits: ['success'],
    setup: (props, { emit }) => () => h('div', {
      'data-testid': 'opportunity-dialog',
      'data-open': String(props.open),
    }, [
      h('button', { type: 'button', 'data-testid': 'opportunity-success', onClick: () => emit('success') }, 'success'),
    ]),
  }),
}))
vi.mock('@/components/dialogs/ContractFormDialog.vue', () => ({ default: defineComponent({ name: 'ContractFormDialog', setup: () => () => null }) }))
vi.mock('@/components/dialogs/InvoiceTitleFormDialog.vue', () => ({ default: defineComponent({ name: 'InvoiceTitleFormDialog', setup: () => () => null }) }))
vi.mock('@/components/dialogs/DeploymentInfoFormDialog.vue', () => ({
  default: defineComponent({
    name: 'DeploymentInfoFormDialog',
    props: {
      open: Boolean,
      customerId: String,
    },
    setup: (props) => () => h('div', {
      'data-testid': 'deployment-dialog',
      'data-open': String(props.open),
      'data-customer-id': props.customerId,
    }),
  }),
}))

const JOURNEY_PUBLIC_ID = 'djy_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
const OPPORTUNITY_PUBLIC_ID = 'opp_test_88'

const customerFixture = (overrides: Partial<CustomerDetailResponse> = {}): CustomerDetailResponse => ({
  id: 'cus_test_19',
  public_id: 'cus_test_19',
  account_name: '上海测试客户',
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
  ...overrides,
})

const journeyFixture = (overrides: Partial<DealJourney> = {}): DealJourney => ({
  id: JOURNEY_PUBLIC_ID,
  public_id: JOURNEY_PUBLIC_ID,
  name: 'CRM 升级项目',
  status: 'OPEN',
  current_board_stage: 'closing_soon',
  current_board_stage_label: '即将签约',
  amount: 320000,
  purchase_type: 'NEW',
  started_at: '2026-07-15T00:00:00',
  closed_at: null,
  last_event_at: '2026-07-15T00:00:00',
  primary_opportunity: {
    public_id: OPPORTUNITY_PUBLIC_ID,
    opportunity_name: 'CRM 升级项目',
    status: 0,
    approval_phase: 'approved',
    win_probability: 50,
    expected_closing_date: '2026-08-30',
    product_name: 'CRM',
  },
  ...overrides,
})

const contractFixture = (): ContractListResponse => ({
  id: 701,
  contract_number: 'CON-701',
  contract_name: 'CRM 升级合同',
  customer_id: 'cus_test_19',
  customer_name: '上海测试客户',
  opportunity_id: OPPORTUNITY_PUBLIC_ID,
  opportunity_name: 'CRM 升级项目',
  signing_contact_id: 1,
  user_count: 20,
  total_amount: '320000',
  license_type: 'SUBSCRIPTION',
  subscription_years: 1,
  standard_unit_price: '16000',
  status: 'SIGNED',
  approval_phase: 'approved',
  signing_date: '2026-08-01',
  effective_date: '2026-08-01',
  expiry_date: '2027-08-01',
  owner_id: '9',
  creator_id: '9',
  created_time: '2026-07-15T00:00:00.000Z',
  last_modified_time: '2026-07-15T00:00:00.000Z',
})

describe('CustomerDetailSheet journey drilldown', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    const userStore = useUserStore()
    const permissionStore = usePermissionStore()
    userStore.userInfo = { id: 9, name: '测试用户', email: 'test@example.com' } as typeof userStore.userInfo
    permissionStore.loadState = 'ready'
    permissionStore.permissions = [
      { code: 'customer:edit:own' },
      { code: 'customer:activity:create' },
      { code: 'opportunity:create' },
    ] as typeof permissionStore.permissions
    vi.clearAllMocks()
    routeState.path = '/customers'
    routeState.query = {}
    customerApi.getCustomerDetail.mockResolvedValue(customerFixture())
    customerActivityApi.getActivities.mockResolvedValue([])
    dealJourneyApi.listByCustomer.mockResolvedValue([journeyFixture()])
    dealJourneyApi.getByCustomer.mockResolvedValue(journeyFixture())
    contractApi.getCustomerContracts.mockResolvedValue([])
    paymentApi.getPaymentPlans.mockResolvedValue([])
    invoiceApi.getInvoiceTitles.mockResolvedValue({ invoice_titles: [] })
    deploymentApi.list.mockResolvedValue([])
    customerApi.getCustomerMembers.mockResolvedValue([])
  })

  it('labels the fourth tab as 业务旅程', async () => {
    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 'cus_test_19',
        visible: true,
      },
    })

    await flushPromises()
    await nextTick()

    const journeysTab = wrapper.get('[data-testid="tab-journeys"]')
    expect(journeysTab.text()).toBe('业务旅程')
    expect(wrapper.find('[data-testid="tab-opportunities"]').exists()).toBe(false)
  })

  it('opens the matching journey when a target opportunity id is provided', async () => {
    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 'cus_test_19',
        targetOpportunityId: OPPORTUNITY_PUBLIC_ID,
        visible: true,
      },
    })

    await flushPromises()
    await nextTick()

    const detail = wrapper.get('[data-testid="deal-journey-detail"]')
    expect(detail.attributes('data-journey-id')).toBe(JOURNEY_PUBLIC_ID)
    expect(wrapper.find('[data-testid="deal-journeys-panel"]').exists()).toBe(false)
  })

  it('stays on the journeys list when the target opportunity has no matching journey', async () => {
    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 'cus_test_19',
        targetOpportunityId: 'opp_missing',
        targetPanel: 'journeys',
        visible: true,
      },
    })

    await flushPromises()
    await nextTick()

    expect(wrapper.get('[data-testid="tab-journeys"]').attributes('data-active')).toBe('true')
    expect(wrapper.find('[data-testid="deal-journeys-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="deal-journey-detail"]').exists()).toBe(false)
  })

  it('opens the journeys panel when the journeys panel is requested', async () => {
    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 'cus_test_19',
        targetPanel: 'journeys',
        visible: true,
      },
    })

    await flushPromises()
    await nextTick()

    expect(wrapper.get('[data-testid="tab-journeys"]').attributes('data-active')).toBe('true')
    expect(wrapper.find('[data-testid="deal-journeys-panel"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('新建商机')
  })

  it('opens a contract from the customer info panel inside the same detail sheet', async () => {
    contractApi.getCustomerContracts.mockResolvedValue([contractFixture()])

    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 'cus_test_19',
        visible: true,
      },
    })

    await flushPromises()
    await wrapper.get('[data-testid="tab-customer-info"]').trigger('click')
    await nextTick()

    expect(wrapper.get('[data-testid="contracts-panel"]').attributes('data-contract-count')).toBe('1')
    await wrapper.get('[data-testid="view-contract"]').trigger('click')
    await nextTick()

    expect(wrapper.findAll('[data-testid="sheet-root"]')).toHaveLength(1)
    expect(wrapper.get('[data-testid="contract-detail-content"]').attributes('data-contract-id')).toBe('701')
    expect(wrapper.get('[data-testid="contract-detail-content"]').attributes('data-embedded')).toBe('true')
  })

  it('renders journey detail content inside the current customer sheet when a journey is selected', async () => {
    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 'cus_test_19',
        visible: false,
      },
    })

    await wrapper.setProps({ visible: true })
    await flushPromises()
    await wrapper.get('[data-testid="tab-journeys"]').trigger('click')
    await nextTick()

    await wrapper.get('[data-testid="view-journey"]').trigger('click')
    await nextTick()

    expect(wrapper.findAll('[data-testid="sheet-root"]')).toHaveLength(1)
    expect(wrapper.find('[data-testid="deal-journeys-panel"]').exists()).toBe(false)
    const detail = wrapper.get('[data-testid="deal-journey-detail"]')
    expect(detail.attributes('data-journey-id')).toBe(JOURNEY_PUBLIC_ID)
    expect(detail.text()).toContain('CRM 升级项目')
  })

  it('opens a contract from a journey with journey parent context in the header', async () => {
    contractApi.getCustomerContracts.mockResolvedValue([contractFixture()])

    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 'cus_test_19',
        visible: true,
      },
    })

    await flushPromises()
    await wrapper.get('[data-testid="tab-journeys"]').trigger('click')
    await nextTick()
    await wrapper.get('[data-testid="view-journey"]').trigger('click')
    await nextTick()
    await wrapper.get('[data-testid="view-journey-contract"]').trigger('click')
    await nextTick()

    expect(wrapper.get('[data-testid="contract-detail-content"]').attributes('data-contract-id')).toBe('701')
    expect(wrapper.get('[data-testid="detail-context-header"]').text()).toContain('CRM 升级项目')
    expect(wrapper.get('[data-testid="detail-context-header"]').text()).not.toContain('商机')
  })

  it('returns from journey detail to the journeys list with highlighted row focus metadata', async () => {
    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 'cus_test_19',
        visible: false,
      },
    })

    await wrapper.setProps({ visible: true })
    await flushPromises()
    await wrapper.get('[data-testid="tab-journeys"]').trigger('click')
    await nextTick()
    await wrapper.get('[data-testid="view-journey"]').trigger('click')
    await nextTick()

    await wrapper.get('[data-testid="back-to-journeys"]').trigger('click')
    await nextTick()

    expect(wrapper.find('[data-testid="deal-journey-detail"]').exists()).toBe(false)
    const panel = wrapper.get('[data-testid="deal-journeys-panel"]')
    expect(panel.attributes('data-highlighted-journey-id')).toBe(JOURNEY_PUBLIC_ID)
    expect(panel.attributes('data-restore-focus-journey-id')).toBe(JOURNEY_PUBLIC_ID)
    expect(wrapper.get('[data-testid="tab-journeys"]').attributes('data-active')).toBe('true')
  })

  it('refreshes customer data when embedded journey detail emits refresh', async () => {
    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 'cus_test_19',
        visible: false,
      },
    })

    await wrapper.setProps({ visible: true })
    await flushPromises()
    await wrapper.get('[data-testid="tab-journeys"]').trigger('click')
    await nextTick()
    await wrapper.get('[data-testid="view-journey"]').trigger('click')
    await nextTick()

    customerApi.getCustomerDetail.mockClear()
    await wrapper.get('[data-testid="detail-refresh"]').trigger('click')
    await flushPromises()

    expect(customerApi.getCustomerDetail).toHaveBeenCalledWith('cus_test_19')
  })

  it('reloads all customer detail data when customerId changes while visible', async () => {
    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 'cus_test_19',
        visible: true,
      },
    })

    await flushPromises()

    customerApi.getCustomerDetail.mockClear()
    customerActivityApi.getActivities.mockClear()
    dealJourneyApi.listByCustomer.mockClear()
    contractApi.getCustomerContracts.mockClear()
    invoiceApi.getInvoiceTitles.mockClear()
    deploymentApi.list.mockClear()
    customerApi.getCustomerMembers.mockClear()

    await wrapper.setProps({ customerId: 'cus_test_42' })
    await flushPromises()

    expect(customerApi.getCustomerDetail).toHaveBeenCalledWith('cus_test_42')
    expect(customerActivityApi.getActivities).toHaveBeenCalledWith('cus_test_42')
    expect(dealJourneyApi.listByCustomer).toHaveBeenCalledWith('cus_test_42')
    expect(contractApi.getCustomerContracts).toHaveBeenCalledWith('cus_test_42')
    expect(invoiceApi.getInvoiceTitles).toHaveBeenCalledWith('cus_test_42')
    expect(deploymentApi.list).toHaveBeenCalledWith('cus_test_42')
    expect(customerApi.getCustomerMembers).toHaveBeenCalledWith('cus_test_42')
  })

  it('closes the deployment dialog when customerId changes while visible', async () => {
    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 'cus_test_19',
        visible: true,
      },
    })

    await flushPromises()
    await wrapper.get('[data-testid="tab-customer-info"]').trigger('click')
    await nextTick()

    const createDeploymentButton = wrapper.findAll('button').find(button => button.text() === '新建部署')
    expect(createDeploymentButton).toBeDefined()
    await createDeploymentButton!.trigger('click')
    await nextTick()
    expect(wrapper.get('[data-testid="deployment-dialog"]').attributes('data-open')).toBe('true')

    await wrapper.setProps({ customerId: 'cus_test_42' })
    await nextTick()

    expect(wrapper.get('[data-testid="deployment-dialog"]').attributes('data-open')).toBe('false')
  })

  it('keeps the latest customer detail data when an older load resolves after a customerId change', async () => {
    const customer19Load = createDeferred<CustomerDetailResponse>()
    const customer42Load = createDeferred<CustomerDetailResponse>()
    customerApi.getCustomerDetail.mockImplementation((customerId: string) => {
      if (customerId === 'cus_test_19') return customer19Load.promise
      if (customerId === 'cus_test_42') return customer42Load.promise
      return Promise.resolve(customerFixture({
        id: customerId,
        account_name: `客户 ${customerId}`,
      }))
    })

    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 'cus_test_19',
        visible: true,
      },
    })

    await nextTick()
    await wrapper.setProps({ customerId: 'cus_test_42' })
    await nextTick()

    customer42Load.resolve(customerFixture({ id: 'cus_test_42', public_id: 'cus_test_42', account_name: '客户 42' }))
    await flushPromises()
    await nextTick()
    await wrapper.get('[data-testid="tab-customer-info"]').trigger('click')
    await nextTick()

    expect(wrapper.text()).toContain('客户 42')
    expect(wrapper.find('[data-testid="deal-journey-detail"]').exists()).toBe(false)

    customer19Load.resolve(customerFixture({ id: 'cus_test_19', public_id: 'cus_test_19', account_name: '客户 19' }))
    await flushPromises()
    await nextTick()

    expect(wrapper.text()).toContain('客户 42')
    expect(wrapper.text()).not.toContain('客户 19')
  })

  it('does not restore the journeys tab from the route query on mount', async () => {
    routeState.query = { customerId: 'cus_test_19', tab: 'journeys' }

    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 'cus_test_19',
        visible: true,
      },
    })

    await flushPromises()

    expect(wrapper.get('[data-testid="tab-customer-profile"]').attributes('data-active')).toBe('true')
    expect(wrapper.find('[data-testid="deal-journeys-panel"]').exists()).toBe(false)
  })

  it('switches tabs locally without changing the route query', async () => {
    routeState.query = { customerId: 'cus_test_19' }

    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 'cus_test_19',
        visible: true,
      },
    })

    await flushPromises()
    await wrapper.get('[data-testid="tab-journeys"]').trigger('click')
    await nextTick()

    expect(wrapper.get('[data-testid="tab-journeys"]').attributes('data-active')).toBe('true')
    expect(routerPush).not.toHaveBeenCalled()
    expect(routerReplace).not.toHaveBeenCalled()
  })

  it('opens embedded journey detail locally without changing the route query', async () => {
    routeState.query = { customerId: 'cus_test_19', tab: 'journeys' }

    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 'cus_test_19',
        visible: true,
      },
    })

    await flushPromises()
    await wrapper.get('[data-testid="tab-journeys"]').trigger('click')
    await nextTick()
    await wrapper.get('[data-testid="view-journey"]').trigger('click')
    await nextTick()

    expect(wrapper.get('[data-testid="deal-journey-detail"]').attributes('data-journey-id')).toBe(JOURNEY_PUBLIC_ID)
    expect(routerPush).not.toHaveBeenCalled()
    expect(routerReplace).not.toHaveBeenCalled()
  })

  it('does not restore embedded journey detail from the route query on mount', async () => {
    routeState.query = { customerId: 'cus_test_19', tab: 'journeys', journeyId: JOURNEY_PUBLIC_ID }

    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 'cus_test_19',
        visible: true,
      },
    })

    await flushPromises()

    expect(wrapper.find('[data-testid="deal-journey-detail"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="tab-customer-profile"]').attributes('data-active')).toBe('true')
  })

  it('returns to the journeys list locally without changing the route query', async () => {
    routeState.query = { customerId: 'cus_test_19', tab: 'journeys', journeyId: JOURNEY_PUBLIC_ID }

    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 'cus_test_19',
        visible: true,
      },
    })

    await flushPromises()
    await wrapper.get('[data-testid="tab-journeys"]').trigger('click')
    await nextTick()
    await wrapper.get('[data-testid="view-journey"]').trigger('click')
    await nextTick()
    await wrapper.get('[data-testid="back-to-journeys"]').trigger('click')
    await nextTick()

    expect(wrapper.find('[data-testid="deal-journey-detail"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="deal-journeys-panel"]').exists()).toBe(true)
    expect(routerReplace).not.toHaveBeenCalled()
    expect(routerPush).not.toHaveBeenCalled()
  })

  it('aliases leftover opportunities targetPanel to the journeys list', async () => {
    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 'cus_test_19',
        targetPanel: 'opportunities',
        visible: true,
      },
    })

    await flushPromises()
    await nextTick()

    expect(wrapper.get('[data-testid="tab-journeys"]').attributes('data-active')).toBe('true')
    expect(wrapper.find('[data-testid="deal-journeys-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="deal-journey-detail"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('新建商机')
  })

  it('keeps the targeted journey after a sticky-target detail refresh', async () => {
    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 'cus_test_19',
        targetOpportunityId: OPPORTUNITY_PUBLIC_ID,
        visible: true,
      },
    })

    await flushPromises()
    await nextTick()

    expect(wrapper.get('[data-testid="deal-journey-detail"]').attributes('data-journey-id')).toBe(JOURNEY_PUBLIC_ID)

    dealJourneyApi.listByCustomer.mockClear()
    await wrapper.get('[data-testid="detail-refresh"]').trigger('click')
    await flushPromises()
    await nextTick()

    expect(dealJourneyApi.listByCustomer).toHaveBeenCalledWith('cus_test_19')
    const detail = wrapper.get('[data-testid="deal-journey-detail"]')
    expect(detail.attributes('data-journey-id')).toBe(JOURNEY_PUBLIC_ID)
    expect(wrapper.find('[data-testid="deal-journeys-panel"]').exists()).toBe(false)

    await wrapper.get('[data-testid="back-to-journeys"]').trigger('click')
    await nextTick()

    expect(wrapper.find('[data-testid="deal-journey-detail"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="deal-journeys-panel"]').exists()).toBe(true)
  })

  it('stays on the journeys list after back when a sticky-target loadAllData runs', async () => {
    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 'cus_test_19',
        targetOpportunityId: OPPORTUNITY_PUBLIC_ID,
        visible: true,
      },
    })

    await flushPromises()
    await nextTick()
    await wrapper.get('[data-testid="back-to-journeys"]').trigger('click')
    await nextTick()

    expect(wrapper.find('[data-testid="deal-journeys-panel"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="deal-journeys-panel"]').attributes('data-highlighted-journey-id')).toBe(JOURNEY_PUBLIC_ID)

    const createOpportunityButton = wrapper.findAll('button').find(button => button.text() === '新建商机')
    expect(createOpportunityButton).toBeDefined()
    await createOpportunityButton!.trigger('click')
    await nextTick()

    dealJourneyApi.listByCustomer.mockClear()
    await wrapper.get('[data-testid="opportunity-success"]').trigger('click')
    await flushPromises()
    await nextTick()

    expect(dealJourneyApi.listByCustomer).toHaveBeenCalledWith('cus_test_19')
    expect(wrapper.find('[data-testid="deal-journey-detail"]').exists()).toBe(false)
    const panel = wrapper.get('[data-testid="deal-journeys-panel"]')
    expect(panel.attributes('data-highlighted-journey-id')).toBe(JOURNEY_PUBLIC_ID)
    expect(wrapper.get('[data-testid="tab-journeys"]').attributes('data-active')).toBe('true')
  })
})
