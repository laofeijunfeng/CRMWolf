import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref, type Ref } from 'vue'
import type { PaymentRecordBoardParams, PaymentRecordWithDetails } from '@/api/payment'
import type { ViewDisplayMode } from '@/api/viewPreference'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition } from '@/components/crmwolf/listSortTypes'
import type { PaymentRecordBoardResponse } from '@/schemas/paymentRecordBoard'
import { toast } from 'vue-sonner'

const mocks = vi.hoisted(() => ({
  listPaymentRecords: vi.fn(),
  getPaymentRecordBoard: vi.fn(),
  getPaymentRecordDetail: vi.fn(),
  exportPaymentRecords: vi.fn(),
  updatePaymentRecord: vi.fn(),
  deletePaymentRecord: vi.fn(),
}))

const teamState = vi.hoisted(() => {
  const { reactive: vueReactive } = require('vue') as typeof import('vue')
  return vueReactive({ currentTeam: { id: 11 } as { id: number } | null })
})

const userState = vi.hoisted(() => {
  const { reactive: vueReactive } = require('vue') as typeof import('vue')
  return vueReactive({ userInfo: { id: '42' } as { id: string } | null })
})

const permissionState = vi.hoisted(() => {
  const { reactive: vueReactive } = require('vue') as typeof import('vue')
  return vueReactive({
    permissions: ['payment:record:view', 'payment:record:export', 'payment:record:edit', 'payment:record:delete', 'payment:submit'].map((code) => ({ code })),
    loadState: 'ready' as 'idle' | 'loading' | 'ready' | 'error',
    hasPermission(code: string): boolean {
      return this.loadState === 'ready' && this.permissions.some((permission) => permission.code === code)
    },
    hasAnyPermission(codes: string[]): boolean {
      return codes.some((code) => this.hasPermission(code))
    },
  })
})

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

vi.mock('vue-router', (): Record<string, unknown> => ({
  useRoute: (): { query: Record<string, string> } => ({ query: {} }),
  useRouter: (): { push: ReturnType<typeof vi.fn> } => ({ push: vi.fn() }),
}))

vi.mock('@/api/payment', () => ({
  default: {
    listPaymentRecords: mocks.listPaymentRecords,
    getPaymentRecordBoard: mocks.getPaymentRecordBoard,
    getPaymentRecordDetail: mocks.getPaymentRecordDetail,
    exportPaymentRecords: mocks.exportPaymentRecords,
    updatePaymentRecord: mocks.updatePaymentRecord,
    deletePaymentRecord: mocks.deletePaymentRecord,
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
  } => permissionState,
}))

vi.mock('@/stores/header', () => ({
  useHeaderStore: (): typeof headerStore => headerStore,
}))

vi.mock('@/stores/approval', () => ({
  useApprovalStore: (): { submitEntity: ReturnType<typeof vi.fn> } => ({ submitEntity: vi.fn() }),
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

vi.mock('@/views/PaymentRecordDetailSheet.vue', () => ({
  default: {
    name: 'PaymentRecordDetailSheet',
    props: {
      visible: { type: Boolean, default: false },
      recordId: { type: Number, default: null },
      record: { type: Object, default: null },
      stageName: { type: String, default: '' },
      approval: { type: Object, default: null },
    },
    emits: ['update:visible', 'refresh', 'edit', 'resubmit'],
    template: '<section data-testid="payment-record-detail-sheet" :data-visible="String(visible)" :data-record-id="recordId ?? \'\'" :data-has-record="String(record !== null)" />',
  },
}))

vi.mock('@/components/dialogs/EditRecordDialog.vue', () => ({
  default: {
    name: 'EditRecordDialog',
    props: {
      open: { type: Boolean, default: false },
      record: { type: Object, default: null },
      submitting: { type: Boolean, default: false },
    },
    emits: ['update:open', 'submit'],
    template: '<div data-testid="edit-record-dialog" :data-open="String(open)" :data-record-id="record?.id ?? \'\'" />',
  },
}))

interface SavedViewOptions {
  activeDisplayMode?: Ref<ViewDisplayMode>
  refresh: () => Promise<unknown>
}

interface PaymentRecordPageState {
  activeTab: string
  tabs: { key: string, label: string }[]
  activeFilters: ListFilterCondition[]
  activeSorts: ListSortCondition[]
  displayMode: 'table' | 'board'
  selectedRecord: PaymentRecordWithDetails | null
  selectedBoardRecordId: number | null
  detailSheetVisible: boolean
  ownRecordScope: boolean
}
function pageState(wrapper: VueWrapper): PaymentRecordPageState {
  const exposed = wrapper.vm as object
  if (!('displayMode' in exposed) || !('selectedBoardRecordId' in exposed) || !('ownRecordScope' in exposed)) {
    throw new Error('payment record page state is not exposed')
  }
  return exposed as PaymentRecordPageState
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

import PaymentRecords from '@/views/PaymentRecords.vue'

const record: PaymentRecordWithDetails = {
  id: 77,
  payment_plan_id: 18,
  record_number: 'PR-077',
  actual_amount: 3200,
  payment_date: '2026-09-12',
  created_time: '2026-09-12T00:00:00',
  last_modified_time: '2026-09-12T00:00:00',
  confirmation_status: 'PENDING',
  approval_phase: 'draft',
  creator_id: '42',
  contract_name: '星河合同',
  customer_name: '星河科技',
  stage_name: '首期',
}

const statuses = ['pending_submit', 'pending_approval', 'rejected', 'approved', 'unclassified'] as const

type RecordColumn = PaymentRecordBoardResponse['columns'][number]
type RecordItem = RecordColumn['items'][number]

function recordItem(
  status: typeof statuses[number],
  actionState: RecordItem['action_state'],
): RecordItem {
  return {
    id: status === 'approved' ? 91 : 92,
    title: status === 'approved' ? 'PR-2026-091' : 'PR-2026-092',
    subtitle: status === 'approved' ? '星河科技' : null,
    amount: status === 'approved' ? '6400.00' : '100.00',
    actual_amount: status === 'approved' ? '6400.00' : '100.00',
    date: status === 'approved' ? '2026-09-18' : null,
    owner: status === 'approved' ? { id: '42', name: '周宁', avatar_url: null } : null,
    status,
    metadata: {
      customer_name: status === 'approved' ? '星河科技' : null,
      contract_name: status === 'approved' ? '星河年度合同' : null,
      actual_payer_name: status === 'approved' ? '星河科技有限公司' : null,
      creator_name: status === 'approved' ? '周宁' : null,
      owner_name: status === 'approved' ? '周宁' : null,
      commission_member_name: status === 'approved' ? '李娜' : null,
      approval_phase: status === 'approved' ? 'approved' : null,
      approval_id: status === 'approved' ? 15 : null,
      confirmation_status: status === 'approved' ? 'CONFIRMED' : null,
    },
    action_state: actionState,
  }
}

function recordColumn(status: typeof statuses[number]): RecordColumn {
  const occupied = status === 'approved' || status === 'rejected'
  return {
    key: status,
    label: status,
    tone: status === 'approved' ? 'success' : 'neutral',
    count: occupied ? 1 : 0,
    amount: occupied ? (status === 'approved' ? '6400.00' : '100.00') : '0.00',
    actual_amount: occupied ? (status === 'approved' ? '6400.00' : '100.00') : '0.00',
    confirmed_amount: status === 'approved' ? '6400.00' : '0.00',
    unconfirmed_amount: status === 'rejected' ? '100.00' : '0.00',
    has_more: false,
    remaining_count: 0,
    items: status === 'approved'
      ? [recordItem(status, { can_edit: false, can_delete: false, can_resubmit: false })]
      : status === 'rejected'
        ? [recordItem(status, { can_edit: true, can_delete: true, can_resubmit: true })]
        : [],
  }
}

const boardResponse: PaymentRecordBoardResponse = {
  summary: [{ key: 'actual_total', label: '回款金额', value_type: 'amount', value: '6400.00' }],
  columns: statuses.map(recordColumn),
  trends: [],
}

function mountPage(): VueWrapper {
  return mount(PaymentRecords, { global: { stubs: { StatusBadge: true } } })
}

async function switchMode(wrapper: VueWrapper, mode: 'table' | 'board'): Promise<void> {
  wrapper.getComponent({ name: 'DataTable' }).vm.$emit('update:view-display-mode', mode)
  await flushPromises()
}

function viewAllButton(wrapper: VueWrapper, columnKey: string): HTMLButtonElement {
  const button = wrapper.get(`[data-column-key="${columnKey}"] .board-column__footer button`).element
  if (!(button instanceof HTMLButtonElement)) throw new Error('view-all control is not a button')
  return button
}

describe('Payment records board integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    headerStore.activeTab = 'all'
    teamState.currentTeam = { id: 11 }
    userState.userInfo = { id: '42' }
    permissionState.loadState = 'ready'
    permissionState.permissions = ['payment:record:view', 'payment:record:export', 'payment:record:edit', 'payment:record:delete', 'payment:submit'].map((code) => ({ code }))
    mocks.listPaymentRecords.mockResolvedValue({ items: [record], total: 1 })
    mocks.getPaymentRecordBoard.mockResolvedValue(boardResponse)
    mocks.getPaymentRecordDetail.mockResolvedValue({ ...record, id: 92, record_number: 'PR-2026-092' })
    mocks.deletePaymentRecord.mockResolvedValue(undefined)
  })

  it('defaults to the existing payment-record table and does not request the board', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const table = wrapper.getComponent({ name: 'DataTable' })
    expect(table.props('viewDisplayMode')).toBe('table')
    expect(table.props('viewDisplayModeEnabled')).toBe(true)
    expect(table.props('data')).toEqual([record])
    expect(table.props('exportEnabled')).toBe(true)
    expect(mocks.listPaymentRecords).toHaveBeenCalledWith(expect.objectContaining({ page: 1, page_size: 20 }))
    expect(mocks.getPaymentRecordBoard).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('requests the non-paginated board and preserves me when own scope is enabled', async () => {
    const wrapper = mountPage()
    await flushPromises()
    const page = pageState(wrapper)
    page.ownRecordScope = true
    page.activeFilters = [{ field: 'payment_date', op: 'before', value: '2026-10-01' }]
    const table = wrapper.getComponent({ name: 'DataTable' })
    table.vm.$emit('update:search', '星河')
    table.vm.$emit('search-apply', '星河')
    table.vm.$emit('sort-apply', [{ field: 'payment_date', direction: 'asc' }])
    await flushPromises()
    mocks.getPaymentRecordBoard.mockClear()

    await switchMode(wrapper, 'board')

    const params = mocks.getPaymentRecordBoard.mock.calls[0]?.[0] as PaymentRecordBoardParams
    expect(params).toEqual(expect.objectContaining({
      me: true,
      search: '星河',
      filters: JSON.stringify([{ field: 'payment_date', op: 'before', value: '2026-10-01' }]),
      sorts: JSON.stringify([{ field: 'payment_date', direction: 'asc' }]),
    }))
    expect(params).not.toHaveProperty('page')
    expect(params).not.toHaveProperty('page_size')
    expect(params).not.toHaveProperty('skip')
    expect(params).not.toHaveProperty('limit')
    expect(wrapper.findAll('[data-column-key]').map((column) => column.attributes('data-column-key'))).toEqual([...statuses])
    wrapper.unmount()
  })

  it('keeps the visible confirmed tab and maps the board request to canonical approved', async () => {
    const wrapper = mountPage()
    await flushPromises()
    headerStore.activeTab = 'confirmed'
    await flushPromises()
    mocks.listPaymentRecords.mockClear()
    await switchMode(wrapper, 'board')

    const page = pageState(wrapper)
    expect(page.activeTab).toBe('confirmed')
    expect(page.tabs.find((tab) => tab.key === 'confirmed')?.label).toBe('已确认')
    expect(mocks.getPaymentRecordBoard).toHaveBeenCalledWith(expect.objectContaining({
      approval_status: 'approved',
    }))
    const params = mocks.getPaymentRecordBoard.mock.calls[0]?.[0] as PaymentRecordBoardParams
    expect(params.approval_status).not.toBe('confirmed')
    expect(mocks.listPaymentRecords).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('keeps approval columns independent from confirmation badges', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await switchMode(wrapper, 'board')

    const approved = wrapper.get('[data-column-key="approved"]')
    const approval = approved.findAll('dt').find((term) => term.text() === '审批状态')
    const confirmation = approved.findAll('dt').find((term) => term.text() === '确认状态')
    expect(approved.text()).toContain('已通过')
    expect(approved.text()).toContain('已确认')
    expect(approved.text()).not.toContain('confirmed')
    expect(approval?.element.nextElementSibling?.textContent).toContain('已通过')
    expect(confirmation?.element.nextElementSibling?.textContent).toContain('已确认')
    wrapper.unmount()
  })

  it('opens board cards through a numeric detail id and leaves the list record empty', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await switchMode(wrapper, 'board')

    await wrapper.get('[data-column-key="approved"] .board-card').trigger('click')
    await nextTick()

    const page = pageState(wrapper)
    const sheet = wrapper.getComponent({ name: 'PaymentRecordDetailSheet' })
    expect(page.selectedBoardRecordId).toBe(91)
    expect(page.selectedRecord).toBeNull()
    expect(page.detailSheetVisible).toBe(true)
    expect(sheet.props('recordId')).toBe(91)
    expect(sheet.props('record')).toBeNull()
    expect(sheet.props('visible')).toBe(true)
    wrapper.unmount()
  })

  it('keeps list-row detail on the existing selected record', async () => {
    const wrapper = mountPage()
    await flushPromises()

    wrapper.getComponent({ name: 'DataTable' }).vm.$emit('row-click', record)
    await nextTick()

    const page = pageState(wrapper)
    const sheet = wrapper.getComponent({ name: 'PaymentRecordDetailSheet' })
    expect(page.selectedRecord).toEqual(record)
    expect(page.selectedBoardRecordId).toBeNull()
    expect(sheet.props('recordId')).toBe(77)
    expect(sheet.props('record')).toEqual(record)
    wrapper.unmount()
  })

  it('shows edit, delete, and resubmit only when the existing action locks allow them', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await switchMode(wrapper, 'board')

    const approved = wrapper.get('[data-column-key="approved"]')
    const rejected = wrapper.get('[data-column-key="rejected"]')
    expect(approved.find('[data-testid="board-card-action-edit"]').exists()).toBe(false)
    expect(approved.find('[data-testid="board-card-action-delete"]').exists()).toBe(false)
    expect(approved.find('[data-testid="board-card-action-resubmit"]').exists()).toBe(false)
    expect(rejected.find('[data-testid="board-card-action-edit"]').exists()).toBe(true)
    expect(rejected.find('[data-testid="board-card-action-delete"]').exists()).toBe(true)
    expect(rejected.find('[data-testid="board-card-action-resubmit"]').exists()).toBe(true)

    await rejected.get('[data-testid="board-card-action-edit"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('activate-card')).toBeUndefined()
    expect(mocks.getPaymentRecordDetail).toHaveBeenCalledWith(92)
    expect(wrapper.get('[data-testid="edit-record-dialog"]').attributes('data-open')).toBe('true')
    expect(wrapper.get('[data-testid="edit-record-dialog"]').attributes('data-record-id')).toBe('92')
    expect(mocks.updatePaymentRecord).not.toHaveBeenCalled()

    await rejected.get('[data-testid="board-card-action-delete"]').trigger('click')
    await flushPromises()
    expect(mocks.deletePaymentRecord).toHaveBeenCalledWith(92)

    mocks.getPaymentRecordDetail.mockClear()
    await rejected.get('[data-testid="board-card-action-resubmit"]').trigger('click')
    await flushPromises()
    expect(mocks.getPaymentRecordDetail).toHaveBeenCalledWith(92)
    expect(wrapper.get('[data-testid="edit-record-dialog"]').attributes('data-open')).toBe('true')
    expect(wrapper.get('[data-testid="edit-record-dialog"]').attributes('data-record-id')).toBe('92')
    wrapper.unmount()
  })

  it('drills unclassified with approval_status is_empty and approved with canonical equality', async () => {
    const wrapper = mountPage()
    await flushPromises()
    const table = wrapper.getComponent({ name: 'DataTable' })
    table.vm.$emit('update:search', '星河')
    table.vm.$emit('search-apply', '星河')
    table.vm.$emit('update:page', 4)
    await flushPromises()
    await switchMode(wrapper, 'board')

    expect(viewAllButton(wrapper, 'unclassified').disabled).toBe(false)
    expect(viewAllButton(wrapper, 'approved').disabled).toBe(false)

    await wrapper.get('[data-column-key="unclassified"] .board-column__footer button').trigger('click')
    await flushPromises()

    let drilled = wrapper.getComponent({ name: 'DataTable' })
    expect(drilled.props('viewDisplayMode')).toBe('table')
    expect(drilled.props('page')).toBe(1)
    expect(drilled.props('search')).toBe('星河')
    expect(drilled.props('filters')).toEqual([{ field: 'approval_status', op: 'is_empty', value: null }])
    expect(mocks.listPaymentRecords).toHaveBeenCalledWith(expect.objectContaining({
      page: 1,
      search: '星河',
      filters: JSON.stringify([{ field: 'approval_status', op: 'is_empty', value: null }]),
    }))

    await switchMode(wrapper, 'board')
    await wrapper.get('[data-column-key="approved"] .board-column__footer button').trigger('click')
    await flushPromises()

    drilled = wrapper.getComponent({ name: 'DataTable' })
    expect(drilled.props('filters')).toEqual([{ field: 'approval_status', op: 'eq', value: 'approved' }])
    expect(drilled.props('page')).toBe(1)
    expect(drilled.props('search')).toBe('星河')
    wrapper.unmount()
  })

  it('keeps a successful snapshot stale after refresh failure and disables drill-through', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await switchMode(wrapper, 'board')
    mocks.getPaymentRecordBoard.mockRejectedValueOnce(new Error('board refresh failed'))
    const search = wrapper.get('input[type="search"]')
    await search.setValue('失败刷新')
    await wrapper.get('form[role="search"]').trigger('submit')
    await flushPromises()

    expect(wrapper.getComponent({ name: 'PaymentRecordBoardProjection' }).props('response')).toEqual(boardResponse)
    expect(wrapper.getComponent({ name: 'PaymentRecordBoardProjection' }).props('stale')).toBe(true)
    expect(viewAllButton(wrapper, 'approved').disabled).toBe(true)
    expect(viewAllButton(wrapper, 'unclassified').disabled).toBe(true)

    userState.userInfo = { id: '99' }
    await nextTick()
    expect(wrapper.getComponent({ name: 'PaymentRecordBoardProjection' }).props('response')).toBeNull()
    wrapper.unmount()
  })

  it('keeps export available and restores list columns after returning from the board', async () => {
    const wrapper = mountPage()
    await flushPromises()
    const table = wrapper.getComponent({ name: 'DataTable' })
    expect(typeof table.props('exportHandler')).toBe('function')
    await switchMode(wrapper, 'board')

    expect(wrapper.getComponent({ name: 'DataTable' }).props('exportEnabled')).toBe(true)
    wrapper.getComponent({ name: 'DataTable' }).vm.$emit('update:view-display-mode', 'table')
    await flushPromises()

    const restored = wrapper.getComponent({ name: 'DataTable' })
    expect(restored.props('viewDisplayMode')).toBe('table')
    expect(restored.props('exportEnabled')).toBe(true)
    expect(restored.props('columnConfigEnabled')).toBe(true)
    expect(restored.props('data')).toEqual([record])
    expect(toast.warning).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
