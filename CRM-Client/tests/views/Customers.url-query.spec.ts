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
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
const confirmDelete = vi.hoisted(() => vi.fn())
const confirmDialog = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({ push: routerPush }),
}))
vi.mock('@/api/customer', () => ({ default: customerApi }))
vi.mock('@/stores/user', () => ({ useUserStore: () => userStore }))
vi.mock('@/stores/permissions', () => ({ usePermissionStore: () => permissionStore }))
vi.mock('@/stores/header', () => ({ useHeaderStore: () => headerStore }))
vi.mock('@/composables/usePageTitle', () => ({ usePageTitle: vi.fn() }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError }))
vi.mock('@/utils/confirmDialog', () => ({ confirmDelete, confirmDialog }))
vi.mock('vue-sonner', () => ({ toast }))

vi.mock('@/components/crmwolf', () => ({
  FilterPanel: defineComponent({
    name: 'FilterPanel',
    props: { fields: Array },
    emits: ['search', 'reset'],
    setup: () => () => h('div', { 'data-testid': 'filter-panel' }),
  }),
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
    },
    emits: ['update:page', 'update:page-size'],
    setup: (props, { slots }) => () => h('div', { 'data-testid': 'data-table' }, props.data.map(row => h('div', { key: row.id }, slots['cell-account_name']?.({ row })))),
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
vi.mock('@/components/dialogs/CustomerFormDialog.vue', () => ({ default: defineComponent({ name: 'CustomerFormDialog', setup: () => () => null }) }))
vi.mock('@/components/dialogs/OpportunityFormDialog.vue', () => ({ default: defineComponent({ name: 'OpportunityFormDialog', setup: () => () => null }) }))
vi.mock('@/components/StatusBadge.vue', () => ({ default: defineComponent({ name: 'StatusBadge', setup: () => () => h('span') }) }))
vi.mock('@/components/ScoreIndicator.vue', () => ({ default: defineComponent({ name: 'ScoreIndicator', setup: () => () => h('span') }) }))
vi.mock('@/views/CustomerDetailSheet.vue', () => ({
  default: defineComponent({
    name: 'CustomerDetailSheet',
    props: { visible: Boolean, customerId: Number },
    emits: ['update:visible', 'refresh'],
    setup: (props, { emit }) => () => h('div', {
      'data-testid': 'customer-detail-sheet',
      'data-visible': String(props.visible),
      'data-customer-id': props.customerId === undefined ? '' : String(props.customerId),
    }, [
      h('button', { type: 'button', 'data-testid': 'close-customer-detail', onClick: () => emit('update:visible', false) }, 'close'),
    ]),
  }),
}))

const customerFixture = (): CustomerResponse => ({
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
  loss_reason: null,
  return_reason: null,
  returned_time: null,
  creator_id: '9',
  created_time: '2026-07-15T00:00:00.000Z',
  last_modified_time: '2026-07-15T00:00:00.000Z',
  version: 1,
})

describe('Customers URL query detail sheet state', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeState.path = '/customers'
    routeState.query = {}
    headerStore.activeTab = ''
    customerApi.getCustomers.mockResolvedValue([customerFixture()])
    customerApi.getPublicCustomers.mockResolvedValue([])
  })

  it('pushes customerId into the route query when opening a customer detail sheet from the list', async () => {
    const wrapper = mount(Customers)
    await flushPromises()

    await wrapper.get('.link-text').trigger('click')

    expect(routerPush).toHaveBeenLastCalledWith({
      path: '/customers',
      query: { customerId: '19' },
    })
  })

  it('restores an open customer detail sheet from customerId in the route query on mount', async () => {
    routeState.query = { customerId: '19' }

    const wrapper = mount(Customers)
    await flushPromises()

    const sheet = wrapper.get('[data-testid="customer-detail-sheet"]')
    expect(sheet.attributes('data-visible')).toBe('true')
    expect(sheet.attributes('data-customer-id')).toBe('19')
  })

  it('removes customer detail query keys when closing the customer detail sheet', async () => {
    routeState.query = { customerId: '19', tab: 'opportunities', opportunityId: '88', keep: '1' }

    const wrapper = mount(Customers)
    await flushPromises()
    await wrapper.get('[data-testid="close-customer-detail"]').trigger('click')

    expect(routerPush).toHaveBeenLastCalledWith({
      path: '/customers',
      query: { keep: '1' },
    })
  })
})
