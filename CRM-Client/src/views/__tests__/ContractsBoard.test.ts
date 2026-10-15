import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref, type Ref } from 'vue'
import type { ContractBoardParams, ContractListResponse } from '@/api/contract'
import type { ViewDisplayMode } from '@/api/viewPreference'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import type { ContractBoardResponse } from '@/schemas/contractBoard'
import { toast } from 'vue-sonner'

const mocks = vi.hoisted(() => ({
  getContracts: vi.fn(),
  getContractBoard: vi.fn(),
  getOwnerFilterOptions: vi.fn(),
  exportContracts: vi.fn(),
}))

const teamState = vi.hoisted(() => {
  const { reactive: vueReactive } = require('vue') as typeof import('vue')
  return vueReactive({ currentTeam: { id: 11 } as { id: number } | null })
})

const userState = vi.hoisted(() => {
  const { reactive: vueReactive } = require('vue') as typeof import('vue')
  return vueReactive({ userInfo: { id: 42 } as { id: number } | null })
})

const permissionState = vi.hoisted(() => {
  const { reactive: vueReactive } = require('vue') as typeof import('vue')
  return vueReactive({
    permissions: ['contract:view:all', 'contract:export'].map((code) => ({ code })),
    loadState: 'ready' as 'idle' | 'loading' | 'ready' | 'error',
    hasPermission(code: string): boolean {
      return this.loadState === 'ready' && this.permissions.some((permission) => permission.code === code)
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

vi.mock('@/api/contract', () => ({
  default: {
    getContracts: mocks.getContracts,
    getContractBoard: mocks.getContractBoard,
    getOwnerFilterOptions: mocks.getOwnerFilterOptions,
    exportContracts: mocks.exportContracts,
  },
}))

vi.mock('@/api/approvalGeneric', () => ({ default: { submitApproval: vi.fn() } }))

vi.mock('@/stores/team', () => ({
  useTeamStore: (): { currentTeam: { id: number } | null } => teamState,
}))

vi.mock('@/stores/user', () => ({
  useUserStore: (): { userInfo: { id: number } | null } => userState,
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
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('@/utils/confirmDialog', () => ({ confirmDialog: vi.fn().mockResolvedValue(true) }))
vi.mock('vue-sonner', () => ({
  toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('@/views/ContractDetailSheet.vue', () => ({
  default: {
    name: 'ContractDetailSheet',
    props: {
      visible: { type: Boolean, default: false },
      contractId: { type: Number, default: null },
    },
    template: '<section data-testid="contract-detail-sheet" :data-visible="String(visible)" :data-contract-id="contractId ?? \'\'" />',
  },
}))

vi.mock('@/components/dialogs/ContractFormDialog.vue', () => ({ default: { name: 'ContractFormDialog', template: '<div />' } }))

interface SavedViewOptions {
  activeDisplayMode?: Ref<ViewDisplayMode>
  refresh: () => Promise<unknown>
}

interface ContractPageState {
  activeFilters: ListFilterCondition[]
  displayMode: 'table' | 'board'
}

function pageState(wrapper: VueWrapper): ContractPageState {
  const exposed = wrapper.vm as object
  if (!('displayMode' in exposed)) throw new Error('contract page state is not exposed')
  return exposed as ContractPageState
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

import Contracts from '@/views/Contracts.vue'

const contract: ContractListResponse = {
  id: 81,
  contract_number: 'CT-081',
  contract_name: '星河合同',
  customer_id: 'cus_1',
  customer_name: '星河科技',
  opportunity_id: 'opp_1',
  opportunity_name: '星河续购',
  signing_contact_id: 7,
  user_count: 20,
  total_amount: '8800.00',
  license_type: 'SUBSCRIPTION',
  subscription_years: null,
  standard_unit_price: '440.00',
  status: 'SIGNED',
  approval_phase: 'approved',
  signing_date: null,
  effective_date: null,
  expiry_date: null,
  owner_id: '42',
  creator_id: '42',
  owner_info: { id: '42', name: '李娜' },
  created_time: '2026-09-01T00:00:00',
  last_modified_time: '2026-09-02T00:00:00',
}

const statuses = ['DRAFT', 'PENDING_REVIEW', 'SIGNED', 'EFFECTIVE', 'EXPIRED', 'TERMINATED', 'UNCLASSIFIED'] as const

function contractColumn(status: typeof statuses[number]): ContractBoardResponse['columns'][number] {
  return {
    key: status,
    label: status,
    tone: status === 'SIGNED' ? 'success' : 'neutral',
    count: status === 'SIGNED' ? 1 : 0,
    amount: status === 'SIGNED' ? '8800.00' : '0.00',
    has_more: false,
    remaining_count: 0,
    items: status === 'SIGNED'
      ? [{
          id: 81,
          title: '星河合同',
          subtitle: 'CT-081',
          amount: '8800.00',
          date: '2026-09-12',
          owner: { id: '42', name: '李娜', avatar_url: null },
          status,
          metadata: {
            customer_name: '星河科技',
            opportunity_name: '星河续购',
            license_type: '订阅',
            purchase_type: '续购',
            signing_date: '2026-09-12',
            effective_date: '2026-09-13',
            expiry_date: '2027-09-12',
            license_expiry_date: '2027-09-12',
            authorized_users: 20,
          },
          action_state: {
            can_edit: false,
            can_delete: false,
            can_submit_approval: false,
            can_approve: false,
            can_reject: false,
          },
        }]
      : [],
  }
}

const boardResponse: ContractBoardResponse = {
  summary: [{ key: 'total_count', label: '合同', value_type: 'count', value: 1 }],
  columns: statuses.map(contractColumn),
  trends: [],
}

function mountPage(): VueWrapper {
  return mount(Contracts, { global: { stubs: { StatusBadge: true } } })
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

describe('Contracts board integration', () => {
  beforeEach(() => {
    permissionState.permissions = ['contract:view:all', 'contract:export'].map((code) => ({ code }))
    permissionState.loadState = 'ready'
    teamState.currentTeam = { id: 11 }
    userState.userInfo = { id: 42 }
    permissionState.loadState = 'ready'
    mocks.getContracts.mockResolvedValue({ items: [contract], total: 1 })
    mocks.getContractBoard.mockResolvedValue(boardResponse)
    mocks.getOwnerFilterOptions.mockResolvedValue({ data: [] })
  })

  it('defaults to the existing contract table and does not request the board', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const table = wrapper.getComponent({ name: 'DataTable' })
    expect(table.props('viewDisplayMode')).toBe('table')
    expect(table.props('viewDisplayModeEnabled')).toBe(true)
    expect(table.props('data')).toEqual([contract])
    expect(mocks.getContracts).toHaveBeenCalledWith(expect.objectContaining({ skip: 0, limit: 20, status: null }))
    expect(mocks.getContractBoard).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('requests the board without pagination from every current non-pagination field', async () => {
    const wrapper = mountPage()
    await flushPromises()
    const table = wrapper.getComponent({ name: 'DataTable' })
    table.vm.$emit('update:search', '星河')
    table.vm.$emit('search-apply', '星河')
    table.vm.$emit('filter-apply', [{ field: 'license_type', op: 'eq', value: 'SUBSCRIPTION' }])
    table.vm.$emit('sort-apply', [{ field: 'signing_date', direction: 'desc' }])
    await flushPromises()
    mocks.getContractBoard.mockClear()

    await switchMode(wrapper, 'board')

    const params = mocks.getContractBoard.mock.calls[0]?.[0] as ContractBoardParams
    expect(params).toEqual(expect.objectContaining({
      status: null,
      search: '星河',
      filters: JSON.stringify([{ field: 'license_type', op: 'eq', value: 'SUBSCRIPTION' }]),
      sorts: JSON.stringify([{ field: 'signing_date', direction: 'desc' }]),
    }))
    expect(params).not.toHaveProperty('skip')
    expect(params).not.toHaveProperty('limit')
    expect(params).not.toHaveProperty('page')
    expect(params).not.toHaveProperty('page_size')
    expect(wrapper.findAll('[data-column-key]').map((column) => column.attributes('data-column-key'))).toEqual([...statuses])
    wrapper.unmount()
  })

  it('opens the existing detail sheet with the numeric contract id', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await switchMode(wrapper, 'board')

    await wrapper.get('[data-column-key="SIGNED"] .board-card').trigger('click')
    await nextTick()

    const sheet = wrapper.getComponent({ name: 'ContractDetailSheet' })
    expect(sheet.props('visible')).toBe(true)
    expect(sheet.props('contractId')).toBe(81)
    wrapper.unmount()
  })

  it('drills a known lifecycle status and disables unclassified drill-through', async () => {
    const wrapper = mountPage()
    await flushPromises()
    const table = wrapper.getComponent({ name: 'DataTable' })
    table.vm.$emit('update:search', '星河')
    table.vm.$emit('search-apply', '星河')
    table.vm.$emit('update:page', 3)
    await flushPromises()
    await switchMode(wrapper, 'board')

    expect(viewAllButton(wrapper, 'UNCLASSIFIED').disabled).toBe(true)
    expect(viewAllButton(wrapper, 'SIGNED').disabled).toBe(false)
    await wrapper.get('[data-column-key="UNCLASSIFIED"] .board-column__footer button').trigger('click')
    expect(wrapper.getComponent({ name: 'DataTable' }).props('viewDisplayMode')).toBe('board')

    await wrapper.get('[data-column-key="SIGNED"] .board-column__footer button').trigger('click')
    await flushPromises()

    const drilled = wrapper.getComponent({ name: 'DataTable' })
    expect(drilled.props('viewDisplayMode')).toBe('table')
    expect(drilled.props('page')).toBe(1)
    expect(drilled.props('search')).toBe('星河')
    expect(drilled.props('filters')).toEqual([{ field: 'status', op: 'eq', value: 'SIGNED' }])
    expect(mocks.getContracts).toHaveBeenCalledWith(expect.objectContaining({
      skip: 0,
      search: '星河',
      filters: JSON.stringify([{ field: 'status', op: 'eq', value: 'SIGNED' }]),
    }))
    wrapper.unmount()
  })

  it('restores columns, pagination, export, and row actions when returning to table mode', async () => {
    const wrapper = mountPage()
    await flushPromises()
    wrapper.getComponent({ name: 'DataTable' }).vm.$emit('update:page', 2)
    await flushPromises()
    await switchMode(wrapper, 'board')
    await switchMode(wrapper, 'table')

    const restored = wrapper.getComponent({ name: 'DataTable' })
    expect(restored.props('viewDisplayMode')).toBe('table')
    expect(restored.props('page')).toBe(2)
    expect(restored.props('columnConfigEnabled')).toBe(true)
    expect(restored.props('exportEnabled')).toBe(true)
    const actions = restored.props('getRowActions') as (row: ContractListResponse) => {
      primaryActions: { id: string }[]
    }
    expect(actions(contract).primaryActions.map((action) => action.id)).toContain('detail')
    expect(wrapper.findComponent({ name: 'ContractBoardProjection' }).exists()).toBe(false)
    expect(pageState(wrapper).displayMode).toBe('table')
    wrapper.unmount()
  })

  it('keeps a successful snapshot stale after refresh failure and clears it when permission scope changes', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await switchMode(wrapper, 'board')

    mocks.getContractBoard.mockRejectedValueOnce(new Error('board refresh failed'))
    wrapper.getComponent({ name: 'DataTable' }).vm.$emit('search-apply', '失败刷新')
    await flushPromises()

    expect(wrapper.getComponent({ name: 'ContractBoardProjection' }).props('response')).toEqual(boardResponse)
    expect(wrapper.getComponent({ name: 'ContractBoardProjection' }).props('stale')).toBe(true)
    expect(viewAllButton(wrapper, 'SIGNED').disabled).toBe(true)

    permissionState.permissions = [{ code: 'contract:view:own' }]
    await nextTick()
    expect(wrapper.getComponent({ name: 'ContractBoardProjection' }).props('response')).toBeNull()
    wrapper.unmount()
  })

  it('refreshes the board after a rendered contract save without a list request or false failure warning', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await switchMode(wrapper, 'board')

    mocks.getContracts.mockClear()
    mocks.getContractBoard.mockClear()
    const dialogs = wrapper.findAllComponents({ name: 'ContractFormDialog' })
    dialogs[dialogs.length - 1]?.vm.$emit('success')
    await flushPromises()

    expect(mocks.getContractBoard).toHaveBeenCalledTimes(1)
    expect(mocks.getContracts).not.toHaveBeenCalled()
    expect(toast.warning).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
