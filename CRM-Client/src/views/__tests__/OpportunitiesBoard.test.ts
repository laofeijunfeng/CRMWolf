import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref, type Ref } from 'vue'
import type { OpportunityBoardParams, OpportunityListResponse } from '@/api/opportunity'
import type { ViewDisplayMode } from '@/api/viewPreference'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition } from '@/components/crmwolf/listSortTypes'
import type { OpportunityBoardResponse } from '@/schemas/opportunityBoard'
import { toast } from 'vue-sonner'

const mocks = vi.hoisted(() => ({
  getOpportunities: vi.fn(),
  getOpportunityBoard: vi.fn(),
  getOwnerFilterOptions: vi.fn(),
  exportOpportunities: vi.fn(),
}))

const teamState = vi.hoisted(() => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- vi.hoisted runs before imports
  const { reactive: vueReactive } = require('vue') as typeof import('vue')
  return vueReactive({ currentTeam: { id: 11 } as { id: number } | null })
})

const userState = vi.hoisted(() => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- vi.hoisted runs before imports
  const { reactive: vueReactive } = require('vue') as typeof import('vue')
  return vueReactive({ userInfo: { id: 42 } as { id: number } | null })
})

const permissionState = vi.hoisted(() => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- vi.hoisted runs before imports
  const { reactive: vueReactive } = require('vue') as typeof import('vue')
  return vueReactive({
    permissions: ['opportunity:view:all', 'opportunity:export'].map((code) => ({ code })),
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

const savedViewState = vi.hoisted(() => ({
  displayMode: null as ViewDisplayMode | null,
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

vi.mock('@/api/opportunity', () => ({
  opportunityApi: {
    getOpportunities: mocks.getOpportunities,
    getOpportunityBoard: mocks.getOpportunityBoard,
    getOwnerFilterOptions: mocks.getOwnerFilterOptions,
    exportOpportunities: mocks.exportOpportunities,
  },
}))

vi.mock('@/api/procurement', () => ({
  default: { getMethods: vi.fn().mockResolvedValue([]) },
}))

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

vi.mock('@/views/OpportunityDetailSheet.vue', () => ({
  default: {
    name: 'OpportunityDetailSheet',
    props: {
      visible: { type: Boolean, default: false },
      opportunityId: { type: String, default: null },
    },
    template: '<section data-testid="opportunity-detail-sheet" :data-visible="String(visible)" :data-opportunity-id="opportunityId ?? \'\'" />',
  },
}))

vi.mock('@/components/dialogs/OpportunityFormDialog.vue', () => ({ default: { name: 'OpportunityFormDialog', template: '<div />' } }))
vi.mock('@/components/dialogs/OpportunityWinDialog.vue', () => ({ default: { name: 'OpportunityWinDialog', template: '<div />' } }))
vi.mock('@/components/dialogs/OpportunityLoseDialog.vue', () => ({ default: { name: 'OpportunityLoseDialog', template: '<div />' } }))

interface SavedViewOptions {
  activeDisplayMode?: Ref<ViewDisplayMode>
  refresh: () => Promise<unknown>
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
    recordedRefresh: options.refresh,
  }),
}))

import Opportunities from '@/views/Opportunities.vue'

const opportunity: OpportunityListResponse = {
  id: 'opp_public_1',
  public_id: 'opp_public_1',
  opportunity_number: 'OP-001',
  opportunity_name: '星河续购',
  customer_id: 'cus_1',
  customer_name: '星河科技',
  procurement_method_id: null,
  procurement_method_info: null,
  total_amount: 8800,
  user_count: 20,
  unit_price: 440,
  license_type: 'SUBSCRIPTION',
  subscription_years: null,
  purchase_type: 'RENEWAL',
  decision_maker_count: null,
  expected_closing_date: '2026-11-30',
  stage_id: null,
  stage: null,
  stage_info: null,
  status: 0,
  approval_phase: 'approved',
  owner_id: '42',
  creator_id: '42',
  owner_info: { id: '42', name: '李娜' },
  created_time: '2026-09-01T00:00:00',
  last_modified_time: '2026-09-02T00:00:00',
  win_probability: 65,
}

function column(
  key: string,
  kind: OpportunityBoardResponse['columns'][number]['column_kind'],
  identity: { methodId: number | null, templateId: number | null },
): OpportunityBoardResponse['columns'][number] {
  return {
    key,
    label: kind === 'active_stage' ? '方案确认' : key,
    tone: 'info',
    column_kind: kind,
    stage_name: kind === 'active_stage' ? '方案确认' : null,
    template_code: identity.templateId === null ? null : 'STD-02',
    template_sort_order: identity.templateId === null ? null : 2,
    procurement_method_id: identity.methodId,
    procurement_stage_template_id: identity.templateId,
    count: key === 'stage:18:42' ? 1 : 0,
    amount: key === 'stage:18:42' ? '8800.00' : '0.00',
    has_more: false,
    remaining_count: 0,
    items: key === 'stage:18:42'
      ? [{
          id: 'opp_0123456789abcdef0123456789abcdef',
          title: '星河续购',
          subtitle: '星河科技',
          amount: '8800.00',
          date: '2026-09-12',
          owner: { id: '42', name: '李娜', avatar_url: null },
          status: 'active',
          metadata: {
            customer_name: '星河科技',
            purchase_type: '续购',
            license_type: '订阅',
            expected_closing_date: '2026-11-30',
            win_probability: 65.5,
            stage_name: '方案确认',
            stage_sort_order: 2,
            procurement_method_name: '公开招标',
            procurement_method_code: 'OPEN-BID',
            procurement_stage_template_id: 42,
            template_code: 'STD-02',
          },
          action_state: {
            can_edit: true,
            can_delete: false,
            can_move_stage: true,
            can_mark_won: true,
            can_mark_lost: false,
          },
        }]
      : [],
  }
}

const boardResponse: OpportunityBoardResponse = {
  summary: [{ key: 'total_count', label: '商机', value_type: 'count', value: 1 }],
  columns: [
    column('stage:18:42', 'active_stage', { methodId: 18, templateId: 42 }),
    column('won', 'won', { methodId: null, templateId: null }),
    column('lost', 'lost', { methodId: null, templateId: null }),
    column('unset_stage', 'unset_stage', { methodId: null, templateId: null }),
  ],
  trends: [],
}

function mountPage(): VueWrapper {
  return mount(Opportunities, { global: { stubs: { StatusBadge: true } } })
}

async function switchMode(wrapper: VueWrapper, mode: 'table' | 'board'): Promise<void> {
  const label = mode === 'board' ? '看板' : '列表'
  const tab = wrapper.get('[aria-label="商机展示"]').findAll('button').find((button) => button.text() === label)
  if (tab === undefined) throw new Error(`missing opportunity ${label} tab`)
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

describe('Opportunities board integration', () => {
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
    userState.userInfo = { id: 42 }
    permissionState.loadState = 'ready'
    savedViewState.displayMode = null
    savedViewState.filters = []
    savedViewState.sorts = []
    mocks.getOpportunities.mockResolvedValue({ items: [opportunity], total: 1 })
    mocks.getOpportunityBoard.mockResolvedValue(boardResponse)
    mocks.getOwnerFilterOptions.mockResolvedValue({ data: [] })
  })

  it('defaults to the existing opportunity table and does not request the board', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const table = wrapper.getComponent({ name: 'DataTable' })
    expect(table.props('viewDisplayMode')).toBe('table')
    const tabs = wrapper.get('[aria-label="商机展示"]')
    expect(tabs.text()).toContain('列表')
    expect(tabs.text()).toContain('看板')
    expect(tabs.text()).toContain('图表')
    expect(table.props('data')).toEqual([opportunity])
    expect(mocks.getOpportunities).toHaveBeenCalledWith(expect.objectContaining({ skip: 0, limit: 20, status: null }))
    expect(mocks.getOpportunityBoard).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('requests the board without pagination and preserves the current non-pagination fields', async () => {
    const wrapper = mountPage()
    await flushPromises()
    const table = wrapper.getComponent({ name: 'DataTable' })
emitFrom(table.vm, 'update:search', '星河')
emitFrom(table.vm, 'search-apply', '星河')
emitFrom(table.vm, 'filter-apply', [{ field: 'purchase_type', op: 'eq', value: 'RENEWAL' }])
emitFrom(table.vm, 'sort-apply', [{ field: 'expected_closing_date', direction: 'asc' }])
    await flushPromises()
    mocks.getOpportunityBoard.mockClear()
    const listCallsBeforeBoard = mocks.getOpportunities.mock.calls.length

    await switchMode(wrapper, 'board')

    expect(mocks.getOpportunities.mock.calls.length).toBe(listCallsBeforeBoard)
    expect(mocks.getOpportunityBoard).toHaveBeenCalledTimes(1)
    const params = mocks.getOpportunityBoard.mock.calls[0]?.[0] as OpportunityBoardParams
    expect(params).toEqual(expect.objectContaining({
      status: null,
      search: '星河',
      filters: JSON.stringify([{ field: 'purchase_type', op: 'eq', value: 'RENEWAL' }]),
      sorts: JSON.stringify([{ field: 'expected_closing_date', direction: 'asc' }]),
    }))
    expect(params).not.toHaveProperty('skip')
    expect(params).not.toHaveProperty('limit')
    expect(params).not.toHaveProperty('page')
    expect(params).not.toHaveProperty('page_size')
    expect(wrapper.getComponent({ name: 'OpportunityBoardProjection' }).props('response')).toEqual(boardResponse)
    expect(wrapper.find('table.data-table').exists()).toBe(false)
    wrapper.unmount()
  })

  it('opens the existing detail sheet with the public opportunity id', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await switchMode(wrapper, 'board')

    await wrapper.get('[data-column-key="stage:18:42"] .board-card').trigger('click')
    await nextTick()

    const sheet = wrapper.getComponent({ name: 'OpportunityDetailSheet' })
    expect(sheet.props('visible')).toBe(true)
    expect(sheet.props('opportunityId')).toBe('opp_0123456789abcdef0123456789abcdef')
    wrapper.unmount()
  })

  it('enables won and lost drill-through and disables ambiguous stage and unset-stage drill-through', async () => {
    const wrapper = mountPage()
    await flushPromises()
    const table = wrapper.getComponent({ name: 'DataTable' })
emitFrom(table.vm, 'update:search', '星河')
emitFrom(table.vm, 'search-apply', '星河')
emitFrom(table.vm, 'update:page', 4)
    await flushPromises()
    await switchMode(wrapper, 'board')

    expect(viewAllButton(wrapper, 'stage:18:42').disabled).toBe(true)
    expect(viewAllButton(wrapper, 'unset_stage').disabled).toBe(true)
    expect(viewAllButton(wrapper, 'won').disabled).toBe(false)

    await wrapper.get('[data-column-key="stage:18:42"] .board-column__footer button').trigger('click')
    expect(wrapper.getComponent({ name: 'DataTable' }).props('viewDisplayMode')).toBe('board')
    expect(JSON.stringify(wrapper.getComponent({ name: 'DataTable' }).props('filters'))).not.toContain('stage_name')

    await wrapper.get('[data-column-key="won"] .board-column__footer button').trigger('click')
    await flushPromises()

    const drilled = wrapper.getComponent({ name: 'DataTable' })
    expect(drilled.props('viewDisplayMode')).toBe('table')
    expect(drilled.props('page')).toBe(1)
    expect(drilled.props('search')).toBe('星河')
    expect(drilled.props('filters')).toEqual([{ field: 'status', op: 'eq', value: '1' }])
    expect(mocks.getOpportunities).toHaveBeenCalledWith(expect.objectContaining({
      skip: 0,
      search: '星河',
      filters: JSON.stringify([{ field: 'status', op: 'eq', value: '1' }]),
    }))
    wrapper.unmount()
  })

  it('restores columns, pagination, export, and row actions after returning to table mode', async () => {
    const wrapper = mountPage()
    await flushPromises()
    const table = wrapper.getComponent({ name: 'DataTable' })
emitFrom(table.vm, 'update:page', 3)
    await flushPromises()
    await switchMode(wrapper, 'board')
    await switchMode(wrapper, 'table')

    const restored = wrapper.getComponent({ name: 'DataTable' })
    expect(restored.props('viewDisplayMode')).toBe('table')
    expect(restored.props('page')).toBe(3)
    expect(restored.props('exportEnabled')).toBe(true)
    expect(restored.props('columnConfigEnabled')).toBe(true)
    const actions = restored.props('getRowActions') as (row: OpportunityListResponse) => {
      primaryActions: { id: string }[]
    }
    expect(actions(opportunity).primaryActions.map((action) => action.id)).toContain('detail')
    expect(wrapper.findComponent({ name: 'OpportunityBoardProjection' }).exists()).toBe(false)
    wrapper.unmount()
  })

  it('keeps a successful board snapshot stale after refresh failure and clears it when scope changes', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await switchMode(wrapper, 'board')

    mocks.getOpportunityBoard.mockRejectedValueOnce(new Error('board refresh failed'))
    emitFrom(wrapper.getComponent({ name: 'DataTable' }).vm, 'search-apply', '失败刷新')
    await flushPromises()

    const projection = wrapper.getComponent({ name: 'OpportunityBoardProjection' })
    expect(projection.props('response')).toEqual(boardResponse)
    expect(projection.props('stale')).toBe(true)
    expect(projection.props('canDrillThrough')).toBe(false)
    expect(viewAllButton(wrapper, 'won').disabled).toBe(true)
    expect(wrapper.text()).toContain('星河续购')

    teamState.currentTeam = { id: 99 }
    await nextTick()
    expect(wrapper.getComponent({ name: 'OpportunityBoardProjection' }).props('response')).toBeNull()
    expect(wrapper.text()).not.toContain('星河续购')
    wrapper.unmount()
  })

  it('refreshes the board after a rendered detail update without a list request or false failure warning', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await switchMode(wrapper, 'board')
    await wrapper.get('[data-column-key="stage:18:42"] .board-card').trigger('click')
    await nextTick()

    mocks.getOpportunities.mockClear()
    mocks.getOpportunityBoard.mockClear()
    emitFrom(wrapper.getComponent({ name: 'OpportunityDetailSheet' }).vm, 'refresh')
    await flushPromises()

    expect(mocks.getOpportunityBoard).toHaveBeenCalledTimes(1)
    expect(mocks.getOpportunities).not.toHaveBeenCalled()
    expect(toast.warning).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
