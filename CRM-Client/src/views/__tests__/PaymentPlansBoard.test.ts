import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref, type Ref } from 'vue'
import type { PaymentPlanBoardParams, PaymentPlanWithDetails } from '@/api/payment'
import type { ViewDisplayMode } from '@/api/viewPreference'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import type { PaymentPlanBoardResponse } from '@/schemas/paymentPlanBoard'
import { toast } from 'vue-sonner'

const mocks = vi.hoisted(() => ({
  listPaymentPlans: vi.fn(),
  getPaymentPlanBoard: vi.fn(),
  exportPaymentPlans: vi.fn(),
}))

const teamState = vi.hoisted(() => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- vi.hoisted runs before imports
  const { reactive: vueReactive } = require('vue') as typeof import('vue')
  return vueReactive({ currentTeam: { id: 11 } as { id: number } | null })
})

const userState = vi.hoisted(() => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- vi.hoisted runs before imports
  const { reactive: vueReactive } = require('vue') as typeof import('vue')
  return vueReactive({ userInfo: { id: '42' } as { id: string } | null })
})

const permissionState = vi.hoisted(() => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- vi.hoisted runs before imports
  const { reactive: vueReactive } = require('vue') as typeof import('vue')
  return vueReactive({
    permissions: ['payment:plan:view', 'payment:plan:export'].map((code) => ({ code })),
    loadState: 'ready' as 'idle' | 'loading' | 'ready' | 'error',
    hasPermission(code: string): boolean {
      return this.loadState === 'ready' && this.permissions.some((permission) => permission.code === code)
    },
  })
})

const headerStore = vi.hoisted(() => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- vi.hoisted runs before imports
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

vi.mock('vue-router', (): Record<string, unknown> => ({
  useRoute: (): { query: Record<string, string> } => ({ query: {} }),
  useRouter: (): { push: ReturnType<typeof vi.fn> } => ({ push: vi.fn() }),
}))

vi.mock('@/api/payment', () => ({
  default: {
    listPaymentPlans: mocks.listPaymentPlans,
    getPaymentPlanBoard: mocks.getPaymentPlanBoard,
    exportPaymentPlans: mocks.exportPaymentPlans,
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
  } => permissionState,
}))

vi.mock('@/stores/header', () => ({
  useHeaderStore: (): typeof headerStore => headerStore,
}))

vi.mock('@/composables/usePageTitle', () => ({ usePageTitle: (): void => undefined }))
vi.mock('@/composables/useTopBarRegistration', () => ({ useTopBarRegistration: (): void => undefined }))
vi.mock('@/utils/errorHandler', () => ({
  handleApiError: vi.fn(),
  handleOutcomeUnknown: vi.fn(),
  isOutcomeUnknown: (): boolean => false,
}))
vi.mock('@/utils/confirmDialog', () => ({ confirmDialog: vi.fn().mockResolvedValue(true) }))
vi.mock('vue-sonner', () => ({
  toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('@/views/PaymentPlanDetailSheet.vue', () => ({
  default: {
    name: 'PaymentPlanDetailSheet',
    props: {
      visible: { type: Boolean, default: false },
      planId: { type: Number, default: null },
    },
    emits: ['update:visible', 'refresh'],
    template: '<section data-testid="payment-plan-detail-sheet" :data-visible="String(visible)" :data-plan-id="planId ?? \'\'" />',
  },
}))

vi.mock('@/components/dialogs/PaymentPlanFormDialog.vue', () => ({ default: { name: 'PaymentPlanFormDialog', template: '<div />' } }))
vi.mock('@/components/dialogs/PaymentRecordDialog.vue', () => ({ default: { name: 'PaymentRecordDialog', template: '<div />' } }))

interface SavedViewOptions {
  activeDisplayMode?: Ref<ViewDisplayMode>
  refresh: () => Promise<unknown>
}

interface PaymentPlanPageState {
  activeFilters: ListFilterCondition[]
  displayMode: 'table' | 'board'
  selectedPlanId: number | null
  planSheetVisible: boolean
}

function pageState(wrapper: VueWrapper): PaymentPlanPageState {
  const exposed = wrapper.vm as object
  if (!('displayMode' in exposed) || !('selectedPlanId' in exposed)) {
    throw new Error('payment plan page state is not exposed')
  }
  return exposed as PaymentPlanPageState
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
    applyBuiltInTab: (): boolean => false,
    retryViewApply: vi.fn().mockResolvedValue(undefined),
    recordedDisplayMode: options.activeDisplayMode,
  }),
}))

import PaymentPlans from '@/views/PaymentPlans.vue'

const plan: PaymentPlanWithDetails = {
  id: 64,
  contract_id: 81,
  plan_number: 'PP-064',
  stage_name: '首期',
  planned_amount: 5000,
  due_date: '2026-09-20',
  status: 'OVERDUE',
  paid_amount: 1000,
  remaining_amount: 4000,
  payment_records: [],
  contract_name: '星河合同',
  customer_name: '星河科技',
  opportunity_name: '星河续购',
  created_time: '2026-09-01T00:00:00',
  last_modified_time: '2026-09-02T00:00:00',
}

const statuses = ['PENDING', 'OVERDUE', 'PARTIAL', 'COMPLETED', 'UNCLASSIFIED'] as const

function planColumn(status: typeof statuses[number]): PaymentPlanBoardResponse['columns'][number] {
  return {
    key: status,
    label: status,
    tone: status === 'OVERDUE' ? 'danger' : 'neutral',
    count: status === 'OVERDUE' ? 1 : 0,
    amount: status === 'OVERDUE' ? '5000.00' : '0.00',
    planned_amount: status === 'OVERDUE' ? '5000.00' : '0.00',
    paid_amount: status === 'OVERDUE' ? '1000.00' : '0.00',
    remaining_amount: status === 'OVERDUE' ? '4000.00' : '0.00',
    overdue_remaining_amount: status === 'OVERDUE' ? '4000.00' : '0.00',
    has_more: false,
    remaining_count: 0,
    items: status === 'OVERDUE'
      ? [{
          id: 64,
          title: 'PP-064',
          subtitle: '首期',
          amount: '5000.00',
          planned_amount: '5000.00',
          paid_amount: '1000.00',
          remaining_amount: '4000.00',
          date: '2026-09-20',
          owner: { id: '42', name: '李娜', avatar_url: null },
          status,
          metadata: {
            customer_name: '星河科技',
            contract_name: '星河合同',
            opportunity_name: '星河续购',
            paid_amount: '1000.00',
            remaining_amount: '4000.00',
          },
          action_state: { can_edit: true, can_delete: false, can_view_detail: true },
        }]
      : [],
  }
}

const boardResponse: PaymentPlanBoardResponse = {
  summary: [{ key: 'planned_amount', label: '计划金额', value_type: 'amount', value: '5000.00' }],
  columns: statuses.map(planColumn),
  trends: [],
}

function mountPage(): VueWrapper {
  return mount(PaymentPlans, { global: { stubs: { StatusBadge: true } } })
}

async function switchMode(wrapper: VueWrapper, mode: 'table' | 'board'): Promise<void> {
  const label = mode === 'board' ? '看板' : '列表'
  const tab = wrapper.get('[aria-label="回款计划展示"]').findAll('button').find((button) => button.text() === label)
  if (tab === undefined) throw new Error(`missing payment plan ${label} tab`)
  await tab.trigger('mousedown')
  await flushPromises()
}

function viewAllButton(wrapper: VueWrapper, columnKey: string): HTMLButtonElement {
  const button = wrapper.get(`[data-column-key="${columnKey}"] .board-column__footer button`).element
  if (!(button instanceof HTMLButtonElement)) throw new Error('view-all control is not a button')
  return button
}


function emitFrom(vm: object, event: string, payload?: unknown): void {
  const emit = (vm as { $emit: (name: string, value?: unknown) => void }).$emit
  if (payload === undefined) emit(event)
  else emit(event, payload)
}

describe('Payment plans board integration', () => {
  beforeEach(() => {
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })))
    vi.clearAllMocks()
    headerStore.activeTab = 'all'
    teamState.currentTeam = { id: 11 }
    userState.userInfo = { id: '42' }
    permissionState.loadState = 'ready'
    mocks.listPaymentPlans.mockResolvedValue({ items: [plan], total: 1 })
    mocks.getPaymentPlanBoard.mockResolvedValue(boardResponse)
  })

  it('defaults to the existing payment-plan table and does not request the board', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const table = wrapper.getComponent({ name: 'DataTable' })
    expect(table.props('viewDisplayMode')).toBe('table')
    const tabs = wrapper.get('[aria-label="回款计划展示"]')
    expect(tabs.text()).toContain('列表')
    expect(tabs.text()).toContain('看板')
    expect(tabs.text()).not.toContain('图表')
    expect(table.props('data')).toEqual([plan])
    expect(mocks.listPaymentPlans).toHaveBeenCalledWith(expect.objectContaining({ page: 1, page_size: 20 }))
    expect(mocks.getPaymentPlanBoard).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('requests the board without pagination and preserves me when the page sets it', async () => {
    const wrapper = mountPage()
    await flushPromises()
    const page = pageState(wrapper)
    page.activeFilters = [{ field: 'due_date', op: 'before', value: '2026-10-01' }]
    const table = wrapper.getComponent({ name: 'DataTable' })
emitFrom(table.vm, 'update:search', '星河')
emitFrom(table.vm, 'search-apply', '星河')
emitFrom(table.vm, 'sort-apply', [{ field: 'due_date', direction: 'asc' }])
    await flushPromises()
    mocks.getPaymentPlanBoard.mockClear()

    await switchMode(wrapper, 'board')

    const params = mocks.getPaymentPlanBoard.mock.calls[0]?.[0] as PaymentPlanBoardParams
    expect(params).toEqual(expect.objectContaining({
      search: '星河',
      filters: JSON.stringify([{ field: 'due_date', op: 'before', value: '2026-10-01' }]),
      sorts: JSON.stringify([{ field: 'due_date', direction: 'asc' }]),
    }))
    expect(params).not.toHaveProperty('me')
    expect(params).not.toHaveProperty('page')
    expect(params).not.toHaveProperty('page_size')
    expect(params).not.toHaveProperty('skip')
    expect(params).not.toHaveProperty('limit')
    expect(wrapper.findAll('[data-column-key]').map((column) => column.attributes('data-column-key'))).toEqual([...statuses])
    wrapper.unmount()
  })

  it('opens the existing detail sheet with the numeric plan id', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await switchMode(wrapper, 'board')

    await wrapper.get('[data-column-key="OVERDUE"] .board-card').trigger('click')
    await nextTick()

    const page = pageState(wrapper)
    expect(page.selectedPlanId).toBe(64)
    expect(page.planSheetVisible).toBe(true)
    expect(wrapper.getComponent({ name: 'PaymentPlanDetailSheet' }).props('planId')).toBe(64)
    expect(wrapper.getComponent({ name: 'PaymentPlanDetailSheet' }).props('visible')).toBe(true)
    wrapper.unmount()
  })

  it('drills a known status to page one and disables unclassified drill-through', async () => {
    const wrapper = mountPage()
    await flushPromises()
    const table = wrapper.getComponent({ name: 'DataTable' })
emitFrom(table.vm, 'update:search', '星河')
emitFrom(table.vm, 'search-apply', '星河')
emitFrom(table.vm, 'update:page', 4)
    await flushPromises()
    await switchMode(wrapper, 'board')

    expect(viewAllButton(wrapper, 'UNCLASSIFIED').disabled).toBe(true)
    expect(viewAllButton(wrapper, 'OVERDUE').disabled).toBe(false)
    await wrapper.get('[data-column-key="UNCLASSIFIED"] .board-column__footer button').trigger('click')
    expect(wrapper.getComponent({ name: 'DataTable' }).props('viewDisplayMode')).toBe('board')

    await wrapper.get('[data-column-key="OVERDUE"] .board-column__footer button').trigger('click')
    await flushPromises()

    const drilled = wrapper.getComponent({ name: 'DataTable' })
    expect(drilled.props('viewDisplayMode')).toBe('table')
    expect(drilled.props('page')).toBe(1)
    expect(drilled.props('search')).toBe('星河')
    expect(drilled.props('filters')).toEqual([{ field: 'status', op: 'eq', value: 'OVERDUE' }])
    expect(mocks.listPaymentPlans).toHaveBeenCalledWith(expect.objectContaining({
      page: 1,
      search: '星河',
      filters: JSON.stringify([{ field: 'status', op: 'eq', value: 'OVERDUE' }]),
    }))
    wrapper.unmount()
  })

  it('keeps a successful snapshot stale after refresh failure and clears it when the user changes', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await switchMode(wrapper, 'board')

    mocks.getPaymentPlanBoard.mockRejectedValueOnce(new Error('board refresh failed'))
    emitFrom(wrapper.getComponent({ name: 'DataTable' }).vm, 'search-apply', '失败刷新')
    await flushPromises()

    expect(wrapper.getComponent({ name: 'PaymentPlanBoardProjection' }).props('response')).toEqual(boardResponse)
    expect(wrapper.getComponent({ name: 'PaymentPlanBoardProjection' }).props('stale')).toBe(true)
    expect(viewAllButton(wrapper, 'OVERDUE').disabled).toBe(true)

    userState.userInfo = { id: '99' }
    await nextTick()
    expect(wrapper.getComponent({ name: 'PaymentPlanBoardProjection' }).props('response')).toBeNull()
    wrapper.unmount()
  })

  it('refreshes the board after a rendered payment-plan save without a list request or false failure warning', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await switchMode(wrapper, 'board')

    mocks.listPaymentPlans.mockClear()
    mocks.getPaymentPlanBoard.mockClear()
    emitFrom(wrapper.getComponent({ name: 'PaymentPlanFormDialog' }).vm, 'success')
    await flushPromises()

    expect(mocks.getPaymentPlanBoard).toHaveBeenCalledTimes(1)
    expect(mocks.listPaymentPlans).not.toHaveBeenCalled()
    expect(toast.warning).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
