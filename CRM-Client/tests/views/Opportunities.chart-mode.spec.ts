import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, inject, nextTick, provide, reactive, ref, type PropType } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import Opportunities from '@/views/Opportunities.vue'
import type { OpportunityChartBucket, OpportunityChartCard, OpportunityChartResponse } from '@/schemas/opportunity'

const routeState = vi.hoisted(() => ({ query: {} as Record<string, string> }))
const routerPush = vi.hoisted(() => vi.fn())
const headerStore = vi.hoisted(() => ({ activeTab: '', setActiveTab: vi.fn() }))
const permissionStore = vi.hoisted(() => ({ hasPermission: vi.fn(() => true), permissions: [] as { code: string }[], loadState: 'ready' }))
const userStore = vi.hoisted(() => ({ userInfo: { id: '9' } }))
const toast = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn() }))
const opportunityApi = vi.hoisted(() => ({
  getOpportunities: vi.fn(),
  getOpportunityChart: vi.fn(),
  getOpportunityChartBucket: vi.fn(),
  getOwnerFilterOptions: vi.fn(),
  getOpportunity: vi.fn(),
  deleteOpportunity: vi.fn(),
  exportOpportunities: vi.fn(),
}))
const chartBucketFixture: OpportunityChartBucket = {
  key: 'active',
  label: '跟进中',
  count: 1,
  amount: 300000,
  ratio: 100,
  amount_ratio: 100,
  preview: [{
    id: 'opp_1',
    name: '重要商机',
    customer_name: '示例客户',
    owner_name: '查询用户',
    amount: 300000,
    expected_closing_date: '2026-12-01',
  }],
  preview_total: 1,
}
const chartCardFixture: OpportunityChartCard = { key: 'status', buckets: [chartBucketFixture] }
const chartFixture: OpportunityChartResponse = {
  population: 2,
  total_amount: 300000,
  cards: [chartCardFixture],
}

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({ push: routerPush }),
}))
vi.mock('@/stores/header', () => {
  const state = reactive(headerStore)
  headerStore.setActiveTab.mockImplementation((tabKey: string) => {
    state.activeTab = tabKey
  })
  return { useHeaderStore: () => state }
})
vi.mock('@/stores/permissions', () => ({ usePermissionStore: () => permissionStore }))
vi.mock('@/stores/team', () => ({ useTeamStore: () => ({ currentTeam: { id: 1 } }) }))
vi.mock('@/stores/user', () => ({ useUserStore: () => userStore }))
vi.mock('vue-sonner', () => ({ toast }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('@/utils/confirmDialog', () => ({ confirmDialog: vi.fn() }))
vi.mock('@/composables/usePageTitle', () => ({ usePageTitle: vi.fn() }))
vi.mock('@/composables/useTopBarRegistration', () => ({ useTopBarRegistration: vi.fn() }))
vi.mock('@/composables/useDataTableExport', () => ({ useDataTableExport: () => ({ exportFields: vi.fn() }) }))
vi.mock('@/composables/useCustomFilterViews', () => ({
  isCustomFilterViewTab: () => false,
  useCustomFilterViews: (options: { activeTab: { value: string } }) => ({
    saving: ref(false),
    applying: ref(false),
    applyError: ref(null),
    mergeTabs: (tabs: unknown[]) => tabs,
    loadCustomViews: vi.fn(() => Promise.resolve()),
    updateActiveCustomViewConfig: vi.fn(() => Promise.resolve()),
    saveCurrentAsCustomView: vi.fn(() => Promise.resolve()),
    saveActiveCustomViewColumns: vi.fn(() => Promise.resolve()),
    consumeFailedViewApply: vi.fn(() => false),
    applyCustomViewTab: vi.fn(() => false),
    applyBuiltInTab: vi.fn((tabKey: string) => {
      options.activeTab.value = tabKey
      return false
    }),
    retryViewApply: vi.fn(),
  }),
}))
vi.mock('@/api/opportunity', () => ({ opportunityApi }))
vi.mock('@/api/procurement', () => ({
  default: {
    getOpportunityProcurementStages: vi.fn(() => Promise.resolve([])),
    moveOpportunityStage: vi.fn(),
  },
}))
vi.mock('@/components/crmwolf', () => ({
  AmountText: defineComponent({ name: 'AmountText', setup: (_, { slots }) => () => h('span', slots.default?.()) }),
  TableRowActions: defineComponent({ name: 'TableRowActions', setup: () => () => h('div') }),
  DataTable: defineComponent({
    name: 'DataTable',
    props: {
      data: { type: Array as PropType<unknown[]>, default: () => [] },
      loading: Boolean,
    },
    emits: ['search-apply', 'search-clear', 'filter-apply', 'filter-reset', 'sort-apply', 'sort-reset'],
    setup: (props, { emit, slots }) => () => h('section', { 'data-testid': 'data-table' }, [
      h('button', { type: 'button', 'data-testid': 'apply-search', onClick: () => emit('search-apply', '  Acme  ') }, 'apply search'),
      h('button', { type: 'button', 'data-testid': 'apply-filter', onClick: () => emit('filter-apply', [{ field: 'purchase_type', op: 'eq', value: 'NEW' }]) }, 'apply filter'),
      h('button', { type: 'button', 'data-testid': 'apply-sort', onClick: () => emit('sort-apply', [{ field: 'total_amount', direction: 'desc' }]) }, 'apply sort'),
      slots.tableTools?.(),
      slots.replacement?.(),
      h('span', { 'data-testid': 'table-count' }, String(props.data.length)),
    ]),
  }),
}))
vi.mock('@/components/StatusBadge.vue', () => ({ default: defineComponent({ name: 'StatusBadge', setup: () => () => h('span') }) }))
vi.mock('@/components/dialogs/OpportunityFormDialog.vue', () => ({ default: defineComponent({ name: 'OpportunityFormDialog', setup: () => () => null }) }))
vi.mock('@/components/dialogs/OpportunityWinDialog.vue', () => ({ default: defineComponent({ name: 'OpportunityWinDialog', setup: () => () => null }) }))
vi.mock('@/components/dialogs/OpportunityLoseDialog.vue', () => ({ default: defineComponent({ name: 'OpportunityLoseDialog', setup: () => () => null }) }))
vi.mock('@/views/OpportunityDetailSheet.vue', () => ({
  default: defineComponent({
    name: 'OpportunityDetailSheet',
    props: { visible: Boolean, opportunityId: String },
    emits: ['refresh', 'update:visible'],
    setup: (props) => () => h('div', {
      'data-testid': 'opportunity-detail-sheet',
      'data-visible': String(props.visible),
      'data-opportunity-id': props.opportunityId ?? '',
    }),
  }),
}))
vi.mock('@/components/opportunity/OpportunityChartPage.vue', () => ({
  default: defineComponent({
    name: 'OpportunityChartPage',
    props: {
      chart: { type: Object as PropType<OpportunityChartResponse | null>, default: null },
      loading: Boolean,
    },
    emits: ['view-bucket', 'open-opportunity'],
    setup: (props, { emit }) => () => h('div', { 'data-testid': 'opportunity-chart-page' }, [
      h('span', props.chart === null ? 'loading' : `${props.chart.population} 条`),
      h('button', {
        type: 'button',
        'data-testid': 'chart-bucket',
        onClick: () => {
          const card = props.chart?.cards[0]
          const bucket = card?.buckets[0]
          if (card !== undefined && bucket !== undefined) emit('view-bucket', card, bucket)
        },
      }, 'view bucket'),
      h('button', {
        type: 'button',
        'data-testid': 'chart-opportunity',
        onClick: () => emit('open-opportunity', 'opp_1'),
      }, 'open opportunity'),
    ]),
  }),
}))
const updateTabs = Symbol('update-tabs')
const tabStubs = {
  Tabs: defineComponent({
    name: 'Tabs',
    props: { modelValue: String },
    emits: ['update:modelValue'],
    setup: (_, { slots, emit }) => {
      provide(updateTabs, (value: string) => emit('update:modelValue', value))
      return () => h('div', slots.default?.())
    },
  }),
  TabsList: defineComponent({ name: 'TabsList', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
  TabsTrigger: defineComponent({
    name: 'TabsTrigger',
    props: { value: { type: String, required: true } },
    setup: (props) => {
      const update = inject<(value: string) => void>(updateTabs)
      return () => h('button', {
        type: 'button',
        'data-testid': `display-mode-${props.value}`,
        onClick: () => update?.(props.value),
      }, props.value === 'chart' ? '图表' : '列表')
    },
  }),
}

describe('Opportunities chart mode integration', () => {
  beforeEach(() => {
    headerStore.setActiveTab('')
    opportunityApi.getOpportunities.mockResolvedValue([])
    opportunityApi.getOpportunityChart.mockResolvedValue(chartFixture)
    opportunityApi.getOpportunityChartBucket.mockResolvedValue({ chart: 'status', bucket: 'active', total: 1, opportunities: chartBucketFixture.preview })
    opportunityApi.getOwnerFilterOptions.mockResolvedValue({ data: [] })
  })

  it('loads the complete chart population with current search context and no pagination', async () => {
    const wrapper = mount(Opportunities, { global: { stubs: tabStubs } })
    await flushPromises()

    await wrapper.get('[data-testid="display-mode-chart"]').trigger('click')
    await flushPromises()

    expect(opportunityApi.getOpportunityChart).toHaveBeenCalledWith({
      status: null,
      filters: '[]',
      sorts: '[]',
    })
    expect(opportunityApi.getOpportunityChart.mock.calls[0]?.[0]).not.toHaveProperty('skip')
    expect(opportunityApi.getOpportunityChart.mock.calls[0]?.[0]).not.toHaveProperty('limit')
    expect(wrapper.get('[data-testid="opportunity-chart-page"]').text()).toContain('2 条')

    await wrapper.get('[data-testid="apply-search"]').trigger('click')
    await nextTick()
    await flushPromises()

    expect(opportunityApi.getOpportunityChart).toHaveBeenLastCalledWith({
      status: null,
      search: 'Acme',
      filters: '[]',
      sorts: '[]',
    })
  })

  it('maps built-in status tabs to chart requests and clears tab-incompatible search', async () => {
    const wrapper = mount(Opportunities, { global: { stubs: tabStubs } })
    await flushPromises()
    await wrapper.get('[data-testid="display-mode-chart"]').trigger('click')
    await flushPromises()
    opportunityApi.getOpportunityChart.mockClear()

    for (const [tab, status] of [['active', 0], ['won', 1], ['lost', 2]] as const) {
      headerStore.setActiveTab(tab)
      await nextTick()
      await flushPromises()
      expect(opportunityApi.getOpportunityChart).toHaveBeenLastCalledWith({
        status,
        filters: '[]',
        sorts: '[]',
      })
    }
  })

  it('preserves filter and sort context for bucket queries and reuses the detail sheet', async () => {
    const wrapper = mount(Opportunities, { global: { stubs: tabStubs } })
    await flushPromises()
    await wrapper.get('[data-testid="display-mode-chart"]').trigger('click')
    await flushPromises()
    headerStore.setActiveTab('won')
    await nextTick()
    await flushPromises()
    await wrapper.get('[data-testid="apply-search"]').trigger('click')
    await wrapper.get('[data-testid="apply-filter"]').trigger('click')
    await wrapper.get('[data-testid="apply-sort"]').trigger('click')
    await flushPromises()

    await wrapper.get('[data-testid="chart-bucket"]').trigger('click')
    await flushPromises()

    expect(opportunityApi.getOpportunityChartBucket).toHaveBeenLastCalledWith({
      chart: 'status',
      bucket: 'active',
      status: 1,
      search: 'Acme',
      filters: '[{"field":"purchase_type","op":"eq","value":"NEW"}]',
      sorts: '[{"field":"total_amount","direction":"desc"}]',
      skip: 0,
      limit: 10,
    })

    await wrapper.get('[data-testid="chart-opportunity"]').trigger('click')
    await nextTick()
    expect(wrapper.get('[data-testid="opportunity-detail-sheet"]').attributes('data-visible')).toBe('true')
    expect(wrapper.get('[data-testid="opportunity-detail-sheet"]').attributes('data-opportunity-id')).toBe('opp_1')
  })
})
