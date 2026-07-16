import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, type PropType } from 'vue'
import CustomerDetailSheet from '@/views/CustomerDetailSheet.vue'
import type { CustomerDetailResponse } from '@/api/customer'
import type { OpportunityListResponse } from '@/api/opportunity'

const routeState = vi.hoisted(() => ({
  path: '/customers',
  query: {} as Record<string, string>,
}))
const routerPush = vi.hoisted(() => vi.fn(() => Promise.resolve()))
const routerReplace = vi.hoisted(() => vi.fn(() => Promise.resolve()))
const customerApi = vi.hoisted(() => ({
  getCustomerDetail: vi.fn(),
  regenerateProfile: vi.fn(),
}))
const customerFollowUpApi = vi.hoisted(() => ({ getFollowUps: vi.fn() }))
const opportunityApi = vi.hoisted(() => ({ getOpportunities: vi.fn() }))
const contractApi = vi.hoisted(() => ({ getCustomerContracts: vi.fn() }))
const invoiceApi = vi.hoisted(() => ({ getInvoiceTitles: vi.fn() }))
const licenseApplicationApi = vi.hoisted(() => ({ list: vi.fn() }))
const deploymentApi = vi.hoisted(() => ({ list: vi.fn() }))
const getCustomerScore = vi.hoisted(() => vi.fn())
const handleApiError = vi.hoisted(() => vi.fn())
const toast = vi.hoisted(() => ({ success: vi.fn(), info: vi.fn() }))

interface OpportunityCustomerContext {
  customerId: number
  customerName?: string
}

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
vi.mock('@/api/customerFollowUp', () => ({ default: customerFollowUpApi }))
vi.mock('@/api/opportunity', () => ({ opportunityApi }))
vi.mock('@/api/contract', () => ({ default: contractApi }))
vi.mock('@/api/invoice', () => ({ default: invoiceApi }))
vi.mock('@/api/licenseApplication', () => ({ default: licenseApplicationApi }))
vi.mock('@/api/deployment', () => ({ default: deploymentApi }))
vi.mock('@/api/score', () => ({ getCustomerScore }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError }))
vi.mock('vue-sonner', () => ({ toast }))

vi.mock('@/components/crmwolf', () => ({
  ContextTabs: defineComponent({
    name: 'ContextTabs',
    props: { tabs: Array, activeTab: String },
    emits: ['update:active-tab'],
    setup: (props, { emit }) => () => h('nav', (props.tabs as { key: string; label: string }[]).map(tab => h('button', {
      type: 'button',
      'data-testid': `tab-${tab.key}`,
      'data-active': String(props.activeTab === tab.key),
      onClick: () => emit('update:active-tab', tab.key),
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

vi.mock('@/components/ScoreIndicator.vue', () => ({ default: defineComponent({ name: 'ScoreIndicator', setup: () => () => h('div') }) }))
vi.mock('@/components/panels/FollowUpPanel.vue', () => ({ default: defineComponent({ name: 'FollowUpPanel', setup: () => () => h('div', 'followup') }) }))
vi.mock('@/components/panels/ContactsPanel.vue', () => ({ default: defineComponent({ name: 'ContactsPanel', setup: () => () => h('div', 'contacts') }) }))
vi.mock('@/components/panels/OpportunitiesPanel.vue', () => ({
  default: defineComponent({
    name: 'OpportunitiesPanel',
    props: {
      highlightedOpportunityId: Number,
      restoreFocusOpportunityId: Number,
    },
    emits: ['view-opportunity', 'open-full-page', 'add'],
    setup: (props, { emit }) => () => h('div', {
      'data-testid': 'opportunities-panel',
      'data-highlighted-opportunity-id': props.highlightedOpportunityId === undefined ? '' : String(props.highlightedOpportunityId),
      'data-restore-focus-opportunity-id': props.restoreFocusOpportunityId === undefined ? '' : String(props.restoreFocusOpportunityId),
    }, [
      h('button', { type: 'button', 'data-testid': 'view-opportunity', onClick: () => emit('view-opportunity', 88) }, 'view opportunity'),
      h('button', { type: 'button', 'data-testid': 'open-full-page', onClick: () => emit('open-full-page', 88) }, 'open full page'),
    ]),
  }),
}))
vi.mock('@/components/panels/ContractsPanel.vue', () => ({ default: defineComponent({ name: 'ContractsPanel', setup: () => () => h('div', 'contracts') }) }))
vi.mock('@/components/panels/PaymentsPanel.vue', () => ({ default: defineComponent({ name: 'PaymentsPanel', setup: () => () => h('div', 'payments') }) }))
vi.mock('@/components/panels/InvoicesPanel.vue', () => ({ default: defineComponent({ name: 'InvoicesPanel', setup: () => () => h('div', 'invoices') }) }))
vi.mock('@/components/panels/LicensePanel.vue', () => ({ default: defineComponent({ name: 'LicensePanel', setup: () => () => h('div', 'license') }) }))
vi.mock('@/components/panels/OpportunityDetailContent.vue', () => ({
  default: defineComponent({
    name: 'OpportunityDetailContent',
    props: {
      opportunityId: Number,
      embedded: Boolean,
      customerContext: Object as PropType<OpportunityCustomerContext>,
    },
    emits: ['back', 'refresh', 'open-full-page'],
    setup: (props, { emit }) => () => h('div', {
      'data-testid': 'opportunity-detail-content',
      'data-opportunity-id': String(props.opportunityId),
      'data-embedded': String(props.embedded),
      'data-context-customer-id': props.customerContext === undefined ? '' : String(props.customerContext.customerId),
      'data-context-customer-name': props.customerContext?.customerName ?? '',
    }, [
      h('button', { type: 'button', 'data-testid': 'back-to-opportunities', onClick: () => emit('back') }, 'back'),
      h('button', { type: 'button', 'data-testid': 'detail-refresh', onClick: () => emit('refresh') }, 'refresh'),
    ]),
  }),
}))

vi.mock('@/components/dialogs/FollowUpFormDialog.vue', () => ({ default: defineComponent({ name: 'FollowUpFormDialog', setup: () => () => null }) }))
vi.mock('@/components/dialogs/ContactFormDialog.vue', () => ({ default: defineComponent({ name: 'ContactFormDialog', setup: () => () => null }) }))
vi.mock('@/components/dialogs/OpportunityFormDialog.vue', () => ({ default: defineComponent({ name: 'OpportunityFormDialog', setup: () => () => null }) }))
vi.mock('@/components/dialogs/ContractFormDialog.vue', () => ({ default: defineComponent({ name: 'ContractFormDialog', setup: () => () => null }) }))
vi.mock('@/components/dialogs/InvoiceTitleFormDialog.vue', () => ({ default: defineComponent({ name: 'InvoiceTitleFormDialog', setup: () => () => null }) }))

const customerFixture = (overrides: Partial<CustomerDetailResponse> = {}): CustomerDetailResponse => ({
  id: 19,
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
  company_background: null,
  company_website: null,
  main_business: null,
  similar_customers: null,
  project_background: null,
  profile_status: null,
  profile_generated_time: null,
  profile_error_message: null,
  ...overrides,
})

const opportunityFixture = (): OpportunityListResponse => ({
  id: 88,
  opportunity_name: 'CRM 升级项目',
  customer_id: 19,
  procurement_method_id: null,
  procurement_method_info: null,
  total_amount: 320000,
  user_count: 20,
  unit_price: 16000,
  license_type: 'SUBSCRIPTION',
  subscription_years: 1,
  purchase_type: 'NEW',
  decision_maker_count: 1,
  expected_closing_date: '2026-08-30',
  stage_id: 1,
  stage_info: { id: 1, stage_name: '方案沟通', win_probability: 50, is_default: 0 },
  status: 0,
  created_time: '2026-07-15T00:00:00.000Z',
  last_modified_time: '2026-07-15T00:00:00.000Z',
})

describe('CustomerDetailSheet opportunity drilldown', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeState.path = '/customers'
    routeState.query = {}
    customerApi.getCustomerDetail.mockResolvedValue(customerFixture())
    getCustomerScore.mockResolvedValue(null)
    customerFollowUpApi.getFollowUps.mockResolvedValue([])
    opportunityApi.getOpportunities.mockResolvedValue([opportunityFixture()])
    contractApi.getCustomerContracts.mockResolvedValue([])
    invoiceApi.getInvoiceTitles.mockResolvedValue({ invoice_titles: [] })
    licenseApplicationApi.list.mockResolvedValue([])
    deploymentApi.list.mockResolvedValue([])
  })

  it('renders opportunity detail content inside the current customer sheet when an opportunity is selected', async () => {
    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 19,
        visible: false,
      },
    })

    await wrapper.setProps({ visible: true })
    await flushPromises()
    await wrapper.get('[data-testid="tab-opportunities"]').trigger('click')
    await nextTick()

    await wrapper.get('[data-testid="view-opportunity"]').trigger('click')
    await nextTick()

    expect(wrapper.findAll('[data-testid="sheet-root"]')).toHaveLength(1)
    expect(wrapper.find('[data-testid="opportunities-panel"]').exists()).toBe(false)
    const detail = wrapper.get('[data-testid="opportunity-detail-content"]')
    expect(detail.attributes('data-opportunity-id')).toBe('88')
    expect(detail.attributes('data-embedded')).toBe('true')
  })

  it('returns from opportunity detail to the opportunities list with highlighted row focus metadata', async () => {
    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 19,
        visible: false,
      },
    })

    await wrapper.setProps({ visible: true })
    await flushPromises()
    await wrapper.get('[data-testid="tab-opportunities"]').trigger('click')
    await nextTick()
    await wrapper.get('[data-testid="view-opportunity"]').trigger('click')
    await nextTick()

    await wrapper.get('[data-testid="back-to-opportunities"]').trigger('click')
    await nextTick()

    expect(wrapper.find('[data-testid="opportunity-detail-content"]').exists()).toBe(false)
    const panel = wrapper.get('[data-testid="opportunities-panel"]')
    expect(panel.attributes('data-highlighted-opportunity-id')).toBe('88')
    expect(panel.attributes('data-restore-focus-opportunity-id')).toBe('88')
    expect(wrapper.get('[data-testid="tab-opportunities"]').attributes('data-active')).toBe('true')
  })

  it('refreshes customer data when embedded opportunity detail emits refresh', async () => {
    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 19,
        visible: false,
      },
    })

    await wrapper.setProps({ visible: true })
    await flushPromises()
    await wrapper.get('[data-testid="tab-opportunities"]').trigger('click')
    await nextTick()
    await wrapper.get('[data-testid="view-opportunity"]').trigger('click')
    await nextTick()

    customerApi.getCustomerDetail.mockClear()
    await wrapper.get('[data-testid="detail-refresh"]').trigger('click')
    await flushPromises()

    expect(customerApi.getCustomerDetail).toHaveBeenCalledWith(19)
  })

  it('reloads all customer detail data when customerId changes while visible', async () => {
    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 19,
        visible: true,
      },
    })

    await flushPromises()

    customerApi.getCustomerDetail.mockClear()
    getCustomerScore.mockClear()
    customerFollowUpApi.getFollowUps.mockClear()
    opportunityApi.getOpportunities.mockClear()
    contractApi.getCustomerContracts.mockClear()
    invoiceApi.getInvoiceTitles.mockClear()
    licenseApplicationApi.list.mockClear()
    deploymentApi.list.mockClear()

    await wrapper.setProps({ customerId: 42 })
    await flushPromises()

    expect(customerApi.getCustomerDetail).toHaveBeenCalledWith(42)
    expect(getCustomerScore).toHaveBeenCalledWith(42)
    expect(customerFollowUpApi.getFollowUps).toHaveBeenCalledWith(42)
    expect(opportunityApi.getOpportunities).toHaveBeenCalledWith({ customer_id: 42 })
    expect(contractApi.getCustomerContracts).toHaveBeenCalledWith(42)
    expect(invoiceApi.getInvoiceTitles).toHaveBeenCalledWith(42)
    expect(licenseApplicationApi.list).toHaveBeenCalledWith(42)
    expect(deploymentApi.list).toHaveBeenCalledWith(42)
  })

  it('keeps the latest customer detail data when an older load resolves after a customerId change', async () => {
    routeState.query = { customerId: '19', tab: 'opportunities', opportunityId: '88' }
    const customer19Load = createDeferred<CustomerDetailResponse>()
    const customer42Load = createDeferred<CustomerDetailResponse>()
    customerApi.getCustomerDetail.mockImplementation((customerId: number) => {
      if (customerId === 19) return customer19Load.promise
      if (customerId === 42) return customer42Load.promise
      return Promise.resolve(customerFixture({
        id: customerId,
        account_name: `客户 ${customerId}`,
      }))
    })

    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 19,
        visible: true,
      },
    })

    await nextTick()
    routeState.query = { customerId: '42', tab: 'opportunities', opportunityId: '88' }
    await wrapper.setProps({ customerId: 42 })
    await nextTick()

    customer42Load.resolve(customerFixture({ id: 42, account_name: '客户 42' }))
    await flushPromises()
    await nextTick()

    const detail = wrapper.get('[data-testid="opportunity-detail-content"]')
    expect(detail.attributes('data-context-customer-id')).toBe('42')
    expect(detail.attributes('data-context-customer-name')).toBe('客户 42')

    customer19Load.resolve(customerFixture({ id: 19, account_name: '客户 19' }))
    await flushPromises()
    await nextTick()

    const currentDetail = wrapper.get('[data-testid="opportunity-detail-content"]')
    expect(currentDetail.attributes('data-context-customer-id')).toBe('42')
    expect(currentDetail.attributes('data-context-customer-name')).toBe('客户 42')
  })

  it('restores the opportunities tab from the route query on mount', async () => {
    routeState.query = { customerId: '19', tab: 'opportunities' }

    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 19,
        visible: true,
      },
    })

    await flushPromises()

    expect(wrapper.get('[data-testid="tab-opportunities"]').attributes('data-active')).toBe('true')
    expect(wrapper.find('[data-testid="opportunities-panel"]').exists()).toBe(true)
  })

  it('pushes the active tab into the route query when switching to opportunities', async () => {
    routeState.query = { customerId: '19' }

    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 19,
        visible: true,
      },
    })

    await flushPromises()
    await wrapper.get('[data-testid="tab-opportunities"]').trigger('click')
    await nextTick()

    expect(routerPush).toHaveBeenLastCalledWith({
      path: '/customers',
      query: { customerId: '19', tab: 'opportunities' },
    })
  })

  it('pushes opportunityId and keeps the opportunities tab when selecting an embedded opportunity', async () => {
    routeState.query = { customerId: '19', tab: 'opportunities' }

    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 19,
        visible: true,
      },
    })

    await flushPromises()
    await wrapper.get('[data-testid="view-opportunity"]').trigger('click')
    await nextTick()

    expect(routerPush).toHaveBeenLastCalledWith({
      path: '/customers',
      query: { customerId: '19', tab: 'opportunities', opportunityId: '88' },
    })
  })

  it('restores embedded opportunity detail from the route query on mount', async () => {
    routeState.query = { customerId: '19', tab: 'opportunities', opportunityId: '88' }

    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 19,
        visible: true,
      },
    })

    await flushPromises()

    const detail = wrapper.get('[data-testid="opportunity-detail-content"]')
    expect(detail.attributes('data-opportunity-id')).toBe('88')
    expect(wrapper.find('[data-testid="opportunities-panel"]').exists()).toBe(false)
  })

  it('replaces only opportunityId in the route query when returning to the opportunities list', async () => {
    routeState.query = { customerId: '19', tab: 'opportunities', opportunityId: '88' }

    const wrapper = mount(CustomerDetailSheet, {
      props: {
        customerId: 19,
        visible: true,
      },
    })

    await flushPromises()
    await wrapper.get('[data-testid="back-to-opportunities"]').trigger('click')
    await nextTick()

    expect(routerReplace).toHaveBeenLastCalledWith({
      path: '/customers',
      query: { customerId: '19', tab: 'opportunities' },
    })
    expect(routerPush).not.toHaveBeenCalled()
  })
})
