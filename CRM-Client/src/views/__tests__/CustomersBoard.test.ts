import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, reactive, ref, type Ref, type VNode } from 'vue'
import type { CustomerBoardParams, CustomerResponse } from '@/api/customer'
import { normalizeCustomerDisplayMode, type ViewDisplayMode } from '@/api/viewPreference'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition } from '@/components/crmwolf/listSortTypes'
import type { CustomerBoardResponse } from '@/schemas/customerBoard'

const mocks = vi.hoisted(() => ({
  getCustomers: vi.fn(),
  getPublicCustomers: vi.fn(),
  getCustomerBoard: vi.fn(),
  getCustomerDetail: vi.fn(),
  exportCustomers: vi.fn(),
  claimCustomer: vi.fn(),
  deleteCustomer: vi.fn(),
  getOwnerFilterOptions: vi.fn(),
  getIndustryOptions: vi.fn(),
}))

const teamState = vi.hoisted(() => {
  const { reactive: vueReactive } = require('vue') as typeof import('vue')
  return vueReactive({ currentTeam: { id: 11 } as { id: number } | null })
})

const userState = vi.hoisted(() => ({
  userInfo: { id: '42' } as { id: string } | null,
}))

const permissionState = vi.hoisted(() => ({
  codes: ['customer:view:all', 'customer:view:own', 'customer:export', 'customer:create'] as string[],
  loadState: 'ready' as 'idle' | 'loading' | 'ready' | 'error',
}))

const headerStore = vi.hoisted(() => {
  const { reactive: vueReactive } = require('vue') as typeof import('vue')
  const store = vueReactive({
    activeTab: 'all',
    setActiveTab: (tab: string): void => {
      store.activeTab = tab
    },
    setTabs: (): void => undefined,
    setActions: (): void => undefined,
  })
  return store
})

const stubs = vi.hoisted(() => {
  const { defineComponent: defineStub, h: render } = require('vue') as typeof import('vue')
  return {
    journey: defineStub({
      name: 'CustomerDealJourneyHoverCard',
      setup: (_props: unknown, { slots }: { slots: { trigger?: () => unknown } }): (() => unknown) => () => render('div', slots.trigger?.()),
    }),
    detail: defineStub({
      name: 'CustomerDetailSheet',
      props: { visible: { type: Boolean, default: false }, customerId: { type: String, default: null } },
      setup: (props: { visible: boolean, customerId: string | null }): (() => unknown) => () => render('section', {
        'data-testid': 'customer-detail-sheet',
        'data-visible': String(props.visible),
        'data-customer-id': props.customerId ?? '',
      }),
    }),
    form: defineStub({
      name: 'CustomerFormDialog',
      props: {
        open: { type: Boolean, default: false },
        mode: { type: String, default: 'create' },
        customerId: { type: String, default: null },
      },
      setup: (props: { open: boolean, mode: string, customerId: string | null }): (() => unknown) => () => render('section', {
        'data-testid': 'customer-form-dialog',
        'data-open': String(props.open),
        'data-mode': props.mode,
        'data-customer-id': props.customerId ?? '',
      }),
    }),
    transfer: defineStub({
      name: 'CustomerTransferDialog',
      props: { open: { type: Boolean, default: false }, customer: { type: Object, default: null } },
      setup: (props: { open: boolean, customer: { id?: string } | null }): (() => unknown) => () => render('section', {
        'data-testid': 'customer-transfer-dialog',
        'data-open': String(props.open),
        'data-customer-id': props.customer?.id ?? '',
      }),
    }),
    opportunity: defineStub({
      name: 'OpportunityFormDialog',
      props: { open: { type: Boolean, default: false }, customerId: { type: String, default: null } },
      setup: (props: { open: boolean, customerId: string | null }): (() => unknown) => () => render('section', {
        'data-testid': 'opportunity-form-dialog',
        'data-open': String(props.open),
        'data-customer-id': props.customerId ?? '',
      }),
    }),
  }
})

const savedViewState = vi.hoisted(() => ({
  displayMode: null as ViewDisplayMode | null,
  activeTab: 'all',
  filters: [] as ListFilterCondition[],
  sorts: [] as ListSortCondition[],
}))

interface RouterPush {
  push: (path: string) => void
}

vi.mock('vue-router', (): Record<string, unknown> => ({
  useRoute: (): { query: Record<string, string> } => ({ query: {} }),
  useRouter: (): RouterPush => ({ push: vi.fn() }),
}))

vi.mock('@/api/customer', () => ({
  default: {
    getCustomers: mocks.getCustomers,
    getPublicCustomers: mocks.getPublicCustomers,
    getCustomerBoard: mocks.getCustomerBoard,
    getCustomerDetail: mocks.getCustomerDetail,
    exportCustomers: mocks.exportCustomers,
    claimCustomer: mocks.claimCustomer,
    deleteCustomer: mocks.deleteCustomer,
    getOwnerFilterOptions: mocks.getOwnerFilterOptions,
    getIndustryOptions: mocks.getIndustryOptions,
  },
}))

vi.mock('@/stores/team', () => ({
  useTeamStore: (): { currentTeam: { id: number } | null } => teamState,
}))

vi.mock('@/stores/user', () => ({
  useUserStore: (): { userInfo: { id: string } | null } => userState,
}))

vi.mock('@/stores/permissions', () => ({
  usePermissionStore: (): {
    permissions: { code: string }[]
    loadState: string
    hasPermission: (code: string) => boolean
    hasAnyPermission: (codes: string[]) => boolean
  } => ({
    permissions: permissionState.codes.map((code) => ({ code })),
    loadState: permissionState.loadState,
    hasPermission: (code: string): boolean => (
      permissionState.loadState === 'ready' && permissionState.codes.includes(code)
    ),
    hasAnyPermission: (codes: string[]): boolean => (
      permissionState.loadState === 'ready' && codes.some((code) => permissionState.codes.includes(code))
    ),
  }),
}))

vi.mock('@/stores/header', () => ({
  useHeaderStore: (): typeof headerStore => headerStore,
}))

vi.mock('@/composables/usePageTitle', () => ({ usePageTitle: (): void => undefined }))
vi.mock('@/composables/useTopBarRegistration', () => ({ useTopBarRegistration: (): void => undefined }))
vi.mock('@/composables/useAcquisitionSourceOptions', () => ({
  useAcquisitionSourceOptions: (): {
    filterSelectOptions: Ref<never[]>
    loadFilterOptions: () => Promise<void>
  } => ({
    filterSelectOptions: ref([]),
    loadFilterOptions: vi.fn().mockResolvedValue(undefined),
  }),
}))
vi.mock('@/utils/errorHandler', () => ({
  handleApiError: vi.fn(),
  handleOutcomeUnknown: vi.fn(),
  isOutcomeUnknown: (): boolean => false,
}))
vi.mock('@/utils/confirmDialog', () => ({
  confirmDialog: vi.fn().mockResolvedValue(true),
}))
vi.mock('vue-sonner', () => ({
  toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('@/components/customer/CustomerDealJourneyHoverCard.vue', () => ({ default: stubs.journey }))
vi.mock('@/views/CustomerDetailSheet.vue', () => ({ default: stubs.detail }))
vi.mock('@/components/dialogs/CustomerFormDialog.vue', () => ({ default: stubs.form }))
vi.mock('@/components/dialogs/CustomerTransferDialog.vue', () => ({ default: stubs.transfer }))
vi.mock('@/components/dialogs/OpportunityFormDialog.vue', () => ({ default: stubs.opportunity }))


interface SavedViewOptions {
  activeTab: Ref<string>
  activeFilters: Ref<ListFilterCondition[]>
  activeSorts: Ref<ListSortCondition[]>
  activeDisplayMode?: Ref<ViewDisplayMode>
  normalizeDisplayMode?: (mode: ViewDisplayMode | null | undefined) => 'table' | 'board'
  refresh: () => Promise<unknown>
}
interface CustomerPageState {
  activeTab: string
  activeFilters: ListFilterCondition[]
  activeSorts: ListSortCondition[]
  displayMode: 'table' | 'board'
  customFilterViews: { recordedNormalizer?: (mode: ViewDisplayMode | null | undefined) => 'table' | 'board' }
}

function pageState(wrapper: VueWrapper): CustomerPageState {
  const exposed = wrapper.vm as object
  if (!('activeTab' in exposed) || !('displayMode' in exposed)) throw new Error('customer page state is not exposed')
  return exposed as CustomerPageState
}

function applySavedView(wrapper: VueWrapper): void {
  const page = pageState(wrapper)
  headerStore.activeTab = savedViewState.activeTab
  page.activeTab = savedViewState.activeTab
  page.activeFilters = savedViewState.filters.map((filter) => ({ ...filter }))
  page.activeSorts = savedViewState.sorts.map((sort) => ({ ...sort }))
  page.displayMode = normalizeCustomerDisplayMode(savedViewState.displayMode)
}


vi.mock('@/composables/useCustomFilterViews', () => ({
  isCustomFilterViewTab: (tabKey: string): boolean => tabKey.startsWith('custom-view:'),
  useCustomFilterViews: (options: SavedViewOptions): Record<string, unknown> => ({
    saving: ref(false),
    applying: ref(false),
    applyError: ref(null),
    mergeTabs: (tabs: unknown[]): unknown[] => tabs,
    loadCustomViews: vi.fn().mockResolvedValue(undefined),
    updateActiveCustomViewConfig: vi.fn().mockResolvedValue(undefined),
    saveAsCustomView: vi.fn().mockResolvedValue(undefined),
    saveCurrentAsCustomView: vi.fn().mockResolvedValue(undefined),
    saveActiveCustomViewColumns: vi.fn().mockResolvedValue(undefined),
    consumeFailedViewApply: (): boolean => false,
    applyCustomViewTab: (): boolean => false,
    applyBuiltInTab: (tabKey: string): boolean => {
      options.activeTab.value = tabKey
      return false
    },
    retryViewApply: vi.fn().mockResolvedValue(undefined),
    recordedNormalizer: options.normalizeDisplayMode,
    customerNormalizer: normalizeCustomerDisplayMode,
  }),
}))


import Customers from '@/views/Customers.vue'

const customer: CustomerResponse = {
  id: 'cus_public_1',
  public_id: 'cus_public_1',
  account_name: '北方客户',
  city: '北京',
  status: 0,
  owner_id: '42',
  owner_info: { id: '42', name: '王销售' },
  version: 3,
  created_time: '2026-09-01T00:00:00',
  last_modified_time: '2026-09-02T00:00:00',
}

const publicCustomer: CustomerResponse = {
  ...customer,
  id: 'cus_public_pool',
  public_id: 'cus_public_pool',
  account_name: '公海客户',
  owner_id: null,
  owner_info: null,
}

const boardResponse: CustomerBoardResponse = {
  summary: [{ key: 'total_count', label: '客户总数', value_type: 'count', value: 1 }],
  columns: [
    {
      key: 'following',
      label: '跟进中',
      tone: 'info',
      count: 1,
      amount: null,
      has_more: false,
      remaining_count: 0,
      items: [{
        id: 'cus_public_1',
        title: '北方客户',
        subtitle: '方案阶段',
        amount: null,
        date: '2026-09-01',
        owner: { id: '42', name: '王销售', avatar_url: null },
        status: 'following',
        metadata: {
          stage_hint: '方案阶段',
          industry: '金融',
          city: '北京',
          company_scale: '51-200人',
          license_type: 'OFFICIAL',
          license_expiry_date: '2026-12-31',
        },
        action_state: {
          can_edit: true,
          can_delete: true,
          can_assign: true,
          can_create_opportunity: true,
        },
      }],
    },
  ],
  trends: [],
}

function mountPage(): VueWrapper {
  return mount(Customers, {
    global: {
      stubs: {
        StatusBadge: defineComponent({
          name: 'StatusBadge',
          setup: (): (() => VNode) => () => h('span'),
        }),
      },
    },
  })
}

async function switchMode(wrapper: VueWrapper, mode: 'table' | 'board'): Promise<void> {
  const table = wrapper.getComponent({ name: 'DataTable' })
  table.vm.$emit('update:view-display-mode', mode)
  await flushPromises()
}

describe('Customers board integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    headerStore.activeTab = 'all'
    teamState.currentTeam = { id: 11 }
    userState.userInfo = { id: '42' }
    permissionState.codes = ['customer:view:all', 'customer:view:own', 'customer:export', 'customer:create']
    permissionState.loadState = 'ready'
    savedViewState.displayMode = null
    savedViewState.activeTab = 'all'
    savedViewState.filters = []
    savedViewState.sorts = []
    mocks.getCustomers.mockResolvedValue({ items: [customer], total: 1 })
    mocks.getPublicCustomers.mockResolvedValue({ items: [publicCustomer], total: 1 })
    mocks.getCustomerBoard.mockResolvedValue(boardResponse)
    mocks.getCustomerDetail.mockResolvedValue(customer)
    mocks.getOwnerFilterOptions.mockResolvedValue({ data: [] })
    mocks.getIndustryOptions.mockResolvedValue([])
    permissionState.loadState = 'ready'
    mocks.claimCustomer.mockResolvedValue({ status: 'SUCCEEDED' })
    mocks.deleteCustomer.mockResolvedValue({ message: 'deleted' })
  })

  it('defaults to the existing customer table and does not request the board', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const table = wrapper.getComponent({ name: 'DataTable' })
    expect(table.props('viewDisplayMode')).toBe('table')
    expect(table.props('viewDisplayModeEnabled')).toBe(true)
    expect(table.props('data')).toEqual([customer])
    expect(mocks.getCustomers).toHaveBeenCalledWith(expect.objectContaining({ skip: 0, limit: 20 }))
    expect(mocks.getCustomerBoard).not.toHaveBeenCalled()
    expect(wrapper.findComponent({ name: 'CustomerBoardProjection' }).exists()).toBe(false)
    wrapper.unmount()
  })

  it('requests the ordinary board without pagination and replaces the list body', async () => {
    const wrapper = mountPage()
    await flushPromises()
    const table = wrapper.getComponent({ name: 'DataTable' })
    table.vm.$emit('update:search', '北方')
    table.vm.$emit('search-apply', '北方')
    table.vm.$emit('filter-apply', [{ field: 'city', op: 'eq', value: '北京' }])
    table.vm.$emit('sort-apply', [{ field: 'created_time', direction: 'desc' }])
    await flushPromises()
    mocks.getCustomerBoard.mockClear()

    await switchMode(wrapper, 'board')

    expect(mocks.getCustomerBoard).toHaveBeenCalledTimes(1)
    const params = mocks.getCustomerBoard.mock.calls[0]?.[0] as CustomerBoardParams
    expect(params).toEqual(expect.objectContaining({
      search: '北方',
      filters: JSON.stringify([{ field: 'city', op: 'eq', value: '北京' }]),
      sorts: JSON.stringify([{ field: 'created_time', direction: 'desc' }]),
    }))
    expect(params).not.toHaveProperty('skip')
    expect(params).not.toHaveProperty('limit')
    expect(params).not.toHaveProperty('page')
    expect(params).not.toHaveProperty('page_size')
    expect(wrapper.getComponent({ name: 'DataTable' }).props('viewDisplayMode')).toBe('board')
    expect(wrapper.getComponent({ name: 'CustomerBoardProjection' }).props('response')).toEqual(boardResponse)
    expect(wrapper.find('table.data-table').exists()).toBe(false)
    wrapper.unmount()
  })

  it('keeps the public tab on the public list and never requests or displays the ordinary board', async () => {
    const wrapper = mountPage()
    await flushPromises()
    mocks.getCustomers.mockClear()
    mocks.getPublicCustomers.mockClear()
    headerStore.activeTab = 'public'
    await flushPromises()
    mocks.getCustomerBoard.mockClear()

    await switchMode(wrapper, 'board')
    await flushPromises()


    expect(mocks.getCustomerBoard).not.toHaveBeenCalled()
    expect(mocks.getPublicCustomers).toHaveBeenCalled()
    expect(wrapper.findComponent({ name: 'CustomerBoardProjection' }).exists()).toBe(false)
    expect(wrapper.getComponent({ name: 'DataTable' }).props('viewDisplayMode')).toBe('table')
    expect(wrapper.getComponent({ name: 'DataTable' }).props('data')).toEqual([publicCustomer])
    wrapper.unmount()
  })

  it('keeps public claim and return flows on the public list', async () => {
    const wrapper = mountPage()
    await flushPromises()
    headerStore.activeTab = 'public'
    await flushPromises()

    const table = wrapper.getComponent({ name: 'DataTable' })
    const actions = table.props('getRowActions') as (row: CustomerResponse) => {
      primaryActions: { id: string, handler: (row: CustomerResponse) => void }[]
    }
    const claim = actions(publicCustomer).primaryActions.find((action) => action.id === 'claim')
    claim?.handler(publicCustomer)
    await flushPromises()

    expect(mocks.claimCustomer).toHaveBeenCalledWith(
      'cus_public_pool',
      expect.objectContaining({ owner_id: '42' }),
      expect.anything(),
    )
    expect(mocks.getPublicCustomers).toHaveBeenCalled()
    expect(mocks.getCustomerBoard).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('normalizes a stored customer chart preference to board through the customer normalizer', async () => {
    savedViewState.displayMode = 'chart'
    savedViewState.filters = [{ field: 'city', op: 'eq', value: '上海' }]
    const wrapper = mountPage()
    await flushPromises()
    const page = pageState(wrapper)
    expect(page.customFilterViews.recordedNormalizer).toBe(normalizeCustomerDisplayMode)
    applySavedView(wrapper)
    await flushPromises()

    expect(wrapper.getComponent({ name: 'DataTable' }).props('viewDisplayMode')).toBe('board')
    expect(mocks.getCustomerBoard).toHaveBeenCalledWith(expect.objectContaining({
      filters: JSON.stringify([{ field: 'city', op: 'eq', value: '上海' }]),
    }))
    wrapper.unmount()
  })

  it('opens the existing detail sheet from a board card public id', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await switchMode(wrapper, 'board')

    wrapper.getComponent({ name: 'CustomerBoardProjection' }).vm.$emit('activate-card', {
      id: 'cus_public_1',
      columnKey: 'following',
    })
    await nextTick()

    const sheet = wrapper.getComponent({ name: 'CustomerDetailSheet' })
    expect(sheet.props('visible')).toBe(true)
    expect(sheet.props('customerId')).toBe('cus_public_1')
    wrapper.unmount()
  })

  it('calls existing edit, delete, assign, and create-opportunity handlers from card actions', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await switchMode(wrapper, 'board')
    const projection = wrapper.getComponent({ name: 'CustomerBoardProjection' })

    projection.vm.$emit('card-action', { id: 'cus_public_1', action: 'edit' })
    await flushPromises()
    expect(mocks.getCustomerDetail).toHaveBeenCalledWith('cus_public_1')
    expect(wrapper.get('[data-testid="customer-form-dialog"]').attributes('data-open')).toBe('true')
    expect(wrapper.get('[data-testid="customer-form-dialog"]').attributes('data-mode')).toBe('edit')

    projection.vm.$emit('card-action', { id: 'cus_public_1', action: 'assign' })
    await nextTick()
    expect(wrapper.get('[data-testid="customer-transfer-dialog"]').attributes('data-open')).toBe('true')
    expect(wrapper.get('[data-testid="customer-transfer-dialog"]').attributes('data-customer-id')).toBe('cus_public_1')

    projection.vm.$emit('card-action', { id: 'cus_public_1', action: 'create-opportunity' })
    await nextTick()
    expect(wrapper.get('[data-testid="opportunity-form-dialog"]').attributes('data-open')).toBe('true')

    projection.vm.$emit('card-action', { id: 'cus_public_1', action: 'delete' })
    await flushPromises()
    expect(mocks.deleteCustomer).toHaveBeenCalledWith('cus_public_1')
    wrapper.unmount()
  })

  it('drills an exact derived status back to page one while preserving search', async () => {
    const wrapper = mountPage()
    await flushPromises()
    const table = wrapper.getComponent({ name: 'DataTable' })
    table.vm.$emit('update:search', '北方')
    table.vm.$emit('search-apply', '北方')
    table.vm.$emit('update:page', 4)
    await flushPromises()
    await switchMode(wrapper, 'board')
    mocks.getCustomers.mockClear()

    wrapper.getComponent({ name: 'CustomerBoardProjection' }).vm.$emit('view-all', 'following')
    await flushPromises()

    const drilled = wrapper.getComponent({ name: 'DataTable' })
    expect(drilled.props('viewDisplayMode')).toBe('table')
    expect(drilled.props('page')).toBe(1)
    expect(drilled.props('search')).toBe('北方')
    expect(drilled.props('filters')).toEqual([{ field: 'derived_status', op: 'eq', value: 'following' }])
    expect(mocks.getCustomers).toHaveBeenCalledWith(expect.objectContaining({
      skip: 0,
      search: '北方',
      filters: JSON.stringify([{ field: 'derived_status', op: 'eq', value: 'following' }]),
    }))
    wrapper.unmount()
  })

  it('rejects public pool and unknown column keys without changing the board', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await switchMode(wrapper, 'board')
    const filtersBefore = wrapper.getComponent({ name: 'DataTable' }).props('filters')

    wrapper.getComponent({ name: 'CustomerBoardProjection' }).vm.$emit('view-all', 'public_pool')
    wrapper.getComponent({ name: 'CustomerBoardProjection' }).vm.$emit('view-all', 'unclassified')
    await flushPromises()

    const table = wrapper.getComponent({ name: 'DataTable' })
    expect(table.props('viewDisplayMode')).toBe('board')
    expect(table.props('filters')).toEqual(filtersBefore)
    expect(JSON.stringify(table.props('filters'))).not.toContain('public_pool')
    wrapper.unmount()
  })

  it('clears search only when the active tab changes, not when display mode changes', async () => {
    const wrapper = mountPage()
    await flushPromises()
    const table = wrapper.getComponent({ name: 'DataTable' })
    table.vm.$emit('update:search', '北方')
    table.vm.$emit('search-apply', '北方')
    await flushPromises()

    await switchMode(wrapper, 'board')
    expect(wrapper.getComponent({ name: 'DataTable' }).props('search')).toBe('北方')

    headerStore.activeTab = 'collaborated'
    await flushPromises()
    expect(wrapper.getComponent({ name: 'DataTable' }).props('search')).toBe('')
    wrapper.unmount()
  })

  it('applies a saved view to the board query and keeps list export available', async () => {
    savedViewState.displayMode = 'board'
    savedViewState.activeTab = 'collaborated'
    savedViewState.filters = [{ field: 'owner_id', op: 'eq', value: '42' }]
    savedViewState.sorts = [{ field: 'account_name', direction: 'asc' }]
    const wrapper = mountPage()
    await flushPromises()

    applySavedView(wrapper)
    await flushPromises()
    expect(pageState(wrapper).activeTab).toBe('collaborated')
    expect(mocks.getCustomerBoard).toHaveBeenCalledWith(expect.objectContaining({
      scope: 'collaborated',
      filters: JSON.stringify([{ field: 'owner_id', op: 'eq', value: '42' }]),
      sorts: JSON.stringify([{ field: 'account_name', direction: 'asc' }]),
    }))
    vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:customers'), revokeObjectURL: vi.fn() })
    const table = wrapper.getComponent({ name: 'DataTable' })
    expect(table.props('exportEnabled')).toBe(true)
    const exportHandler = table.props('exportHandler') as (fields: string[]) => Promise<void>
    await exportHandler(['account_name'])
    expect(mocks.exportCustomers).toHaveBeenCalledWith(expect.objectContaining({
      fields: ['account_name'],
      tab: 'collaborated',
      filters: [{ field: 'owner_id', op: 'eq', value: '42' }],
      sorts: [{ field: 'account_name', direction: 'asc' }],
    }))
    wrapper.unmount()
  })

  it('keeps a successful board snapshot stale after refresh failure and clears it when scope changes', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await switchMode(wrapper, 'board')
    expect(wrapper.getComponent({ name: 'CustomerBoardProjection' }).props('response')).toEqual(boardResponse)

    mocks.getCustomerBoard.mockRejectedValueOnce(new Error('board refresh failed'))
    wrapper.getComponent({ name: 'DataTable' }).vm.$emit('update:search', '失败刷新')
    wrapper.getComponent({ name: 'DataTable' }).vm.$emit('search-apply', '失败刷新')
    await flushPromises()

    const projection = wrapper.getComponent({ name: 'CustomerBoardProjection' })
    expect(projection.props('response')).toEqual(boardResponse)
    expect(projection.props('stale')).toBe(true)
    expect(projection.props('canDrillThrough')).toBe(false)

    teamState.currentTeam = { id: 99 }
    await nextTick()
    expect(wrapper.findComponent({ name: 'CustomerBoardProjection' }).exists()).toBe(false)
    wrapper.unmount()
  })
})
