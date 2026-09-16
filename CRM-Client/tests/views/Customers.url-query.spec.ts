import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, type PropType } from 'vue'
import Customers from '@/views/Customers.vue'
import type { CustomerResponse } from '@/api/customer'

const routeState = vi.hoisted(() => ({
  path: '/customers',
  query: {} as Record<string, string>,
}))
const routerPush = vi.hoisted(() => vi.fn(() => Promise.resolve()))
const customerApi = vi.hoisted(() => ({
  getCustomers: vi.fn(),
  getPublicCustomers: vi.fn(),
  getCustomerDetail: vi.fn(),
  claimCustomer: vi.fn(),
  updateCustomerStatus: vi.fn(),
  markAsLost: vi.fn(),
  deleteCustomer: vi.fn(),
  returnToPool: vi.fn(),
}))
const userStore = vi.hoisted(() => ({ userInfo: { id: 9 } }))
const permissionStore = vi.hoisted(() => ({
  hasPermission: vi.fn(() => true),
  hasAnyPermission: vi.fn(() => true),
}))
const headerStore = vi.hoisted(() => ({
  activeTab: '',
  setTabs: vi.fn(),
  setActions: vi.fn(),
}))
const handleApiError = vi.hoisted(() => vi.fn())
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }))
const sheetRefresh = vi.hoisted(() => vi.fn(() => Promise.resolve(true)))
const confirmDelete = vi.hoisted(() => vi.fn())
const confirmDialog = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({ push: routerPush }),
}))
vi.mock('@/api/customer', () => ({ default: customerApi }))
vi.mock('@/api/acquisition-source', () => ({
  acquisitionSourceApi: {
    listOptions: vi.fn().mockResolvedValue([]),
  },
}))
vi.mock('@/stores/user', () => ({ useUserStore: () => userStore }))
vi.mock('@/stores/permissions', () => ({ usePermissionStore: () => permissionStore }))
vi.mock('@/stores/header', () => ({ useHeaderStore: () => headerStore }))
vi.mock('@/composables/usePageTitle', () => ({ usePageTitle: vi.fn() }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError }))
vi.mock('@/utils/confirmDialog', () => ({ confirmDelete, confirmDialog }))
vi.mock('vue-sonner', () => ({ toast }))

vi.mock('@/components/crmwolf', () => ({
  DataTable: defineComponent({
    name: 'DataTable',
    props: {
      columns: Array,
      data: { type: Array as PropType<CustomerResponse[]>, default: () => [] },
      loading: Boolean,
      page: Number,
      pageSize: Number,
      total: Number,
      emptyTitle: String,
      getRowActions: { type: Function as PropType<(row: CustomerResponse) => { primaryActions?: Array<{ id: string; handler?: (row: Record<string, unknown>) => void }> }>, required: true },
    },
    emits: ['update:page', 'update:page-size'],
    setup: (props, { slots }) => () => h('div', { 'data-testid': 'data-table' }, props.data.map(row => {
      const editAction = props.getRowActions(row).primaryActions?.find(action => action.id === 'edit')
      return h('div', { key: row.id }, [
        slots['cell-account_name']?.({ row }),
        editAction?.handler
          ? h('button', { type: 'button', 'data-testid': `edit-customer-${row.id}`, onClick: () => editAction.handler?.(row as unknown as Record<string, unknown>) }, 'edit')
          : null,
      ])
    })),
  }),
  TableRowActions: defineComponent({
    name: 'TableRowActions',
    props: { row: Object, primaryActions: Array, secondaryActions: Array },
    setup: () => () => h('div', { 'data-testid': 'table-row-actions' }),
  }),
}))

vi.mock('@/components/ui/button', () => ({
  Button: defineComponent({
    name: 'Button',
    props: { type: String, variant: String, size: String, disabled: Boolean },
    setup: (props, { slots, attrs }) => () => h('button', { ...attrs, type: props.type ?? 'button', disabled: props.disabled }, slots.default?.()),
  }),
}))
vi.mock('@/components/AICustomerCreateDialog.vue', () => ({ default: defineComponent({ name: 'AICustomerCreateDialog', setup: () => () => null }) }))
vi.mock('@/components/dialogs/CustomerFormDialog.vue', () => ({
  default: defineComponent({
    name: 'CustomerFormDialog',
    props: { open: Boolean, customerId: String },
    emits: ['update:open', 'success'],
    setup: (props, { emit }) => () => props.open
      ? h('button', {
          type: 'button',
          'data-testid': 'customer-form-success',
          onClick: () => emit('success', {
            entityType: 'customer',
            entityId: 'cus_test_19',
            operation: 'update',
            outcome: 'success',
            stateSyncRequested: true,
          }),
        }, 'save')
      : null,
  }),
}))
vi.mock('@/components/dialogs/CustomerTransferDialog.vue', () => ({ default: defineComponent({ name: 'CustomerTransferDialog', setup: () => () => null }) }))
vi.mock('@/components/dialogs/OpportunityFormDialog.vue', () => ({ default: defineComponent({ name: 'OpportunityFormDialog', setup: () => () => null }) }))
vi.mock('@/components/StatusBadge.vue', () => ({ default: defineComponent({ name: 'StatusBadge', setup: () => () => h('span') }) }))
vi.mock('@/components/customer/CustomerOpportunityHoverCard.vue', () => ({
  default: defineComponent({
    name: 'CustomerOpportunityHoverCard',
    setup: (_, { slots }) => () => h('div', slots.trigger?.()),
  }),
}))
vi.mock('@/views/CustomerDetailSheet.vue', () => ({
  default: defineComponent({
    name: 'CustomerDetailSheet',
    props: {
      visible: Boolean,
      customerId: String,
      targetOpportunityId: String,
      targetJourneyId: String,
      targetPanel: String,
    },
    emits: ['update:visible', 'refresh'],
    setup: (props, { emit, expose }) => {
      expose({ refresh: sheetRefresh })
      return () => h('div', {
        'data-testid': 'customer-detail-sheet',
        'data-visible': String(props.visible),
        'data-customer-id': props.customerId === undefined ? '' : String(props.customerId),
        'data-target-panel': props.targetPanel ?? '',
        'data-target-journey-id': props.targetJourneyId ?? '',
        'data-target-opportunity-id': props.targetOpportunityId ?? '',
      }, [
        h('button', { type: 'button', 'data-testid': 'close-customer-detail', onClick: () => emit('update:visible', false) }, 'close'),
      ])
    },
  }),
}))

const customerFixture = (): CustomerResponse => ({
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
  loss_reason: null,
  return_reason: null,
  returned_time: null,
  creator_id: '9',
  created_time: '2026-07-15T00:00:00.000Z',
  last_modified_time: '2026-07-15T00:00:00.000Z',
  version: 1,
})

describe('Customers local detail sheet state', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeState.path = '/customers'
    routeState.query = {}
    headerStore.activeTab = ''
    customerApi.getCustomers.mockResolvedValue([customerFixture()])
    customerApi.getPublicCustomers.mockResolvedValue([])
    customerApi.getCustomerDetail.mockResolvedValue(customerFixture())
    sheetRefresh.mockClear()

  })

  it('opens a customer detail sheet from the list without changing the route query', async () => {
    const wrapper = mount(Customers)
    await flushPromises()

    await wrapper.get('.link-text').trigger('click')

    const sheet = wrapper.get('[data-testid="customer-detail-sheet"]')
    expect(sheet.attributes('data-visible')).toBe('true')
    expect(sheet.attributes('data-customer-id')).toBe('cus_test_19')
    expect(routerPush).not.toHaveBeenCalled()
  })

  it('restores an open customer detail sheet from customerId in the route query on mount', async () => {
    routeState.query = { customerId: 'cus_test_19' }

    const wrapper = mount(Customers)
    await flushPromises()

    const sheet = wrapper.get('[data-testid="customer-detail-sheet"]')
    expect(sheet.attributes('data-visible')).toBe('true')
    expect(sheet.attributes('data-customer-id')).toBe('cus_test_19')
    expect(routerPush).not.toHaveBeenCalled()
  })

  it('opens the journeys tab and target journey from query', async () => {
    routeState.query = {
      customerId: 'cus_test_19',
      tab: 'journeys',
      journeyId: 'djy_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    }

    const wrapper = mount(Customers)
    await flushPromises()

    const sheet = wrapper.get('[data-testid="customer-detail-sheet"]')
    expect(sheet.attributes('data-visible')).toBe('true')
    expect(sheet.attributes('data-target-panel')).toBe('journeys')
    expect(sheet.attributes('data-target-journey-id')).toBe('djy_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
  })

  it('aliases leftover opportunities tab and opportunityId without a journeyId', async () => {
    routeState.query = {
      customerId: 'cus_test_19',
      tab: 'opportunities',
      opportunityId: 'opp_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    }

    const wrapper = mount(Customers)
    await flushPromises()

    const sheet = wrapper.get('[data-testid="customer-detail-sheet"]')
    expect(sheet.attributes('data-visible')).toBe('true')
    expect(sheet.attributes('data-target-panel')).toBe('journeys')
    expect(sheet.attributes('data-target-opportunity-id')).toBe('opp_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb')
    expect(sheet.attributes('data-target-journey-id')).toBe('')
  })

  it('ignores legacy customer detail query keys', async () => {
    routeState.query = { customerId: '158', tab: 'opportunities', keep: '1' }

    const wrapper = mount(Customers)
    await flushPromises()

    const sheet = wrapper.get('[data-testid="customer-detail-sheet"]')
    expect(sheet.attributes('data-visible')).toBe('false')
    expect(sheet.attributes('data-customer-id')).toBe('null')
    expect(routerPush).not.toHaveBeenCalled()
  })

  it('clears journey targets when opening a customer from the list name', async () => {
    routeState.query = {
      customerId: 'cus_test_19',
      tab: 'journeys',
      journeyId: 'djy_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    }

    const wrapper = mount(Customers)
    await flushPromises()

    await wrapper.get('.link-text').trigger('click')

    const sheet = wrapper.get('[data-testid="customer-detail-sheet"]')
    expect(sheet.attributes('data-visible')).toBe('true')
    expect(sheet.attributes('data-customer-id')).toBe('cus_test_19')
    expect(sheet.attributes('data-target-panel')).toBe('')
    expect(sheet.attributes('data-target-journey-id')).toBe('')
    expect(sheet.attributes('data-target-opportunity-id')).toBe('')
  })

  it('closes the customer detail sheet without changing the route query', async () => {
    routeState.query = { customerId: 'cus_test_19', tab: 'opportunities', opportunityId: '88', keep: '1' }

    const wrapper = mount(Customers)
    await flushPromises()
    expect(wrapper.get('[data-testid="customer-detail-sheet"]').attributes('data-visible')).toBe('true')

    await wrapper.get('[data-testid="close-customer-detail"]').trigger('click')

    expect(wrapper.get('[data-testid="customer-detail-sheet"]').attributes('data-visible')).toBe('false')
    expect(routerPush).not.toHaveBeenCalled()
  })

  it('refreshes the list and matching open detail sheet after inline form success', async () => {
    const wrapper = mount(Customers)
    await flushPromises()

    await wrapper.get('.link-text').trigger('click')
    await wrapper.get('[data-testid="edit-customer-cus_test_19"]').trigger('click')
    await flushPromises()

    customerApi.getCustomers.mockClear()
    sheetRefresh.mockClear()
    await wrapper.get('[data-testid="customer-form-success"]').trigger('click')
    await flushPromises()

    expect(customerApi.getCustomers).toHaveBeenCalledTimes(1)
    expect(sheetRefresh).toHaveBeenCalledTimes(1)
  })

  it('does not refresh an open detail sheet for a different customer', async () => {
    const wrapper = mount(Customers)
    await flushPromises()

    await wrapper.get('.link-text').trigger('click')
    await wrapper.get('[data-testid="edit-customer-cus_test_19"]').trigger('click')
    await flushPromises()

    customerApi.getCustomers.mockClear()
    sheetRefresh.mockClear()
    wrapper.findComponent({ name: 'CustomerFormDialog' }).vm.$emit('success', {
      entityType: 'customer',
      entityId: 'cus_other',
      operation: 'update',
      outcome: 'success',
      stateSyncRequested: true,
    })
    await flushPromises()

    expect(customerApi.getCustomers).toHaveBeenCalledTimes(1)
    expect(sheetRefresh).not.toHaveBeenCalled()
  })
})
