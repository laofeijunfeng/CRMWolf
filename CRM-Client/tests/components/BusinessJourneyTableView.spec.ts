import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

vi.stubGlobal('matchMedia', (query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  addListener: vi.fn(),
  removeListener: vi.fn(),
  dispatchEvent: vi.fn(() => false),
}))
import BusinessJourneyTableView from '@/components/business-journey/BusinessJourneyTableView.vue'
import { createBusinessJourneyListFields } from '@/components/business-journey/businessJourneyListFields'
import type { BusinessJourneyListItem } from '@/schemas/dealJourney'
import { projectListFieldCatalog } from '@/components/crmwolf/listFieldCatalog'

const journeyFixture: BusinessJourneyListItem = {
  id: 'djy_test',
  public_id: 'djy_test',
  name: '华东续约旅程',
  status: 'ACTIVE',
  current_board_stage: 'active_progress',
  current_board_stage_label: '持续推进',
  amount: 168000,
  purchase_type: 'RENEWAL',
  started_at: '2026-09-01T00:00:00',
  closed_at: null,
  last_event_at: '2026-09-20T00:00:00',
  primary_opportunity: null,
  customer_id: 'cus_test',
  customer_name: '示例科技',
  owner: { id: '7', name: '王小明', avatar_url: null },
  primary_opportunity_name: '续约商机',
  product_name: 'CRM 企业版',
  created_time: '2026-09-01T00:00:00',
  expected_closing_date: '2026-10-01',
}

const mountJourneyTable = (data: BusinessJourneyListItem[]) => mount(
  BusinessJourneyTableView,
  {
    props: {
      fields: createBusinessJourneyListFields([]),
      data,
      total: data.length,
      page: 1,
      pageSize: 20,
      filters: [],
      sorts: [],
      columns: [],
      search: '',
      displayMode: 'table',
    },
  },
)

describe('BusinessJourneyTableView layout', () => {
  it('renders the standard list-page table height', () => {
    const wrapper = mount(BusinessJourneyTableView, {
      props: {
        fields: [],
        data: [],
        total: 0,
        page: 1,
        pageSize: 20,
        filters: [],
        sorts: [],
        columns: [],
        search: '',
        displayMode: 'table',
      },
    })

    const card = wrapper.get('.data-table-card')
    const content = wrapper.get('.data-table-content')

    expect((card.element as HTMLElement).style.height).toBe('calc(100vh - 121px)')
    expect(card.classes()).toContain('data-table-card--fill')
    expect(content.classes()).toContain('data-table-content--contained')
  })

  it('renders the journey name as the standard detail link and emits one row click', async () => {
    const wrapper = mountJourneyTable([journeyFixture])
    const link = wrapper.get('[data-testid="business-journey-name-link"]')

    expect(link.text()).toBe(journeyFixture.name)
    expect(link.classes()).toContain('business-journey-name-link')

    await link.trigger('click')

    expect(wrapper.emitted('row-click')).toEqual([[
      {
        customerId: journeyFixture.customer_id,
        journeyPublicId: journeyFixture.public_id,
      },
    ]])
  })

  it('shows the primary opportunity expected closing date instead of the journey start time', () => {
    const wrapper = mountJourneyTable([{
      ...journeyFixture,
      started_at: '2026-09-01T00:00:00',
      expected_closing_date: '2026-10-01',
    }])
    const dateField = createBusinessJourneyListFields([]).find(field => field.key === 'expected_closing_date')

    expect(dateField).toMatchObject({
      label: '预计成交日期',
      type: 'date',
      filter: true,
      sort: true,
    })
    expect(createBusinessJourneyListFields([]).some(field => field.key === 'started_at')).toBe(false)
    expect(wrapper.text()).toContain('预计成交日期')
    expect(wrapper.text()).toContain('2026-10-01')
    expect(wrapper.text()).not.toContain('开始时间')
    expect(wrapper.text()).not.toContain('2026-09-01')
  })

  it('registers progress immediately after stage as a default-visible display-only field', () => {
    const fields = createBusinessJourneyListFields([])

    expect(fields.map(field => field.key)).toEqual([
      'name',
      'customer_name',
      'current_board_stage',
      'progress',
      'primary_opportunity_name',
      'product_name',
      'amount',
      'purchase_type',
      'owner_id',
      'last_event_at',
      'expected_closing_date'
    ])

    expect(fields[3]).toMatchObject({
      key: 'progress',
      label: '当前进度',
      role: 'decoration',
      column: { width: '96px' },
      filter: false,
      filterDisabledReason: '当前进度由当前阶段派生，不支持筛选',
      sort: false,
      sortDisabledReason: '当前进度由当前阶段派生，不支持排序',
      export: false
    })

    const projected = projectListFieldCatalog(fields)
    expect(projected.columns.map(column => column.key)).toContain('progress')
    expect(projected.filterFields.map(field => field.key)).not.toContain('progress')
    expect(projected.sortFields.map(field => field.key)).not.toContain('progress')
    expect(projected.exportFields.map(field => field.fieldKey)).not.toContain('progress')
  })
  it('renders the derived percentage, shared color, compact bar, and accessible label', () => {
    const wrapper = mountJourneyTable([journeyFixture])
    const progressCell = wrapper.get('.data-table tbody [data-testid="business-journey-progress"]')
    const progress = progressCell.get('[role="progressbar"]')
    const indicator = progressCell.get('[role="progressbar"] > div')

    expect(progressCell.attributes('aria-label')).toBe('华东续约旅程 当前进度 29%')
    expect(progress.attributes('aria-label')).toBe('华东续约旅程 当前进度 29%')
    expect(progressCell.text()).toContain('29%')
    expect(progressCell.classes()).toContain('items-center')
    expect(progress.classes()).toContain('h-1.5')
    expect(indicator.classes()).toContain('bg-yellow-500')
  })
  it('renders derived progress in mobile cards with the shared color and accessible label', () => {
    const wrapper = mountJourneyTable([journeyFixture])
    const card = wrapper.get('.data-table-mobile-card')
    const progressCell = card.get('[data-testid="business-journey-progress"]')
    const progress = progressCell.get('[role="progressbar"]')
    const indicator = progress.get(':scope > div')

    expect(card.text()).toContain('华东续约旅程')
    expect(card.text()).toContain('示例科技')
    expect(card.text()).toContain('当前阶段：持续推进')
    expect(progressCell.attributes('aria-label')).toBe('华东续约旅程 当前进度 29%')
    expect(progressCell.text()).toContain('29%')
    expect(progress.attributes('aria-label')).toBe('华东续约旅程 当前进度 29%')
    expect(indicator.classes()).toContain('bg-yellow-500')
  })

  it.each([
    ['early_communication', ['bg-sky-50', 'text-sky-700', 'border-sky-100']],
    ['active_progress', ['bg-blue-50', 'text-blue-700', 'border-blue-100']],
    ['closing_soon', ['bg-emerald-50', 'text-emerald-700', 'border-emerald-100']],
    ['contract_processing', ['bg-violet-50', 'text-violet-700', 'border-violet-100']],
    ['payment_processing', ['bg-amber-50', 'text-amber-700', 'border-amber-100']],
    ['invoice_processing', ['bg-cyan-50', 'text-cyan-700', 'border-cyan-100']],
    ['completed', ['bg-slate-50', 'text-slate-700', 'border-slate-100']],
    ['lost', ['bg-rose-50', 'text-rose-700', 'border-rose-100']],
  ] as const)('uses the board palette for %s', (stage, classes) => {
    const wrapper = mountJourneyTable([{ ...journeyFixture, current_board_stage: stage }])
    const badge = wrapper.get('[data-testid="business-journey-stage-badge"]')
    expect(badge.classes()).toEqual(expect.arrayContaining([...classes]))
  })

  it('offers list, board, and chart modes from the shared DataTable toolbar', () => {
    const wrapper = mountJourneyTable([])

    expect(wrapper.findAll('[role="tab"]').map(tab => tab.text())).toEqual(['列表', '看板', '图表'])
  })

  it('renders non-list replacement content inside the DataTable frame', () => {
    const wrapper = mount(BusinessJourneyTableView, {
      props: {
        fields: [],
        data: [],
        total: 0,
        page: 1,
        pageSize: 20,
        filters: [],
        sorts: [],
        columns: [],
        search: '',
        displayMode: 'board',
      },
      slots: {
        replacement: '<div data-testid="journey-replacement">看板内容</div>',
      },
    })

    const card = wrapper.get('.data-table-card')
    expect(card.get('[data-testid="journey-replacement"]').text()).toBe('看板内容')
    expect(card.find('.data-table').exists()).toBe(false)
  })

  const filteredJourneyProps = {
    fields: createBusinessJourneyListFields([{ value: '7', label: 'Eddie' }]),
    data: [],
    total: 0,
    page: 1,
    pageSize: 20,
    filters: [{ field: 'owner_id', op: 'in' as const, value: ['7'] }],
    sorts: [{ field: 'last_event_at', direction: 'desc' as const }],
    columns: [{ key: 'product_name', order: 60, visible: false }],
    search: '续约',
    contentHidden: true,
  }

  it('shows only the filter on the chart summary and keeps refresh without sort or view config', async () => {
    const wrapper = mount(BusinessJourneyTableView, {
      props: { ...filteredJourneyProps, displayMode: 'chart' },
      slots: {
        tableTools: '<button type="button">刷新</button>',
        replacement: '<div data-testid="journey-replacement">图表内容</div>',
      },
    })
    await flushPromises()

    const tools = wrapper.get('.data-table-tools').text()
    expect(tools).toContain('刷新')
    expect(tools).toContain('筛选')
    expect(tools).not.toContain('排序')
    expect(tools).not.toContain('字段配置')
    expect(wrapper.findAll('button').map(button => button.text()).join(' ')).not.toContain('更多设置')

    const summary = wrapper.get('.list-view-state-summary')
    expect(summary.text()).toContain('负责人 属于')
    expect(summary.text()).toContain('“Eddie”')
    expect(summary.text()).toContain('清除筛选')
    expect(summary.text()).toContain('另存为视图')
    expect(summary.text()).not.toContain('排序：')
    expect(summary.text()).not.toContain('已隐藏')
    expect(wrapper.get('[data-testid="journey-replacement"]').text()).toBe('图表内容')

    await summary.get('.list-view-state-summary-clear').trigger('click')
    expect(wrapper.emitted('filter-reset')).toEqual([[]])
    expect(wrapper.emitted('update:filters')).toEqual([[[]]])
    expect(wrapper.emitted('sort-reset')).toBeUndefined()
    expect(wrapper.emitted('column-config-reset')).toBeUndefined()
  })

  it('removes one chart filter without touching the sort or hidden columns', async () => {
    const wrapper = mount(BusinessJourneyTableView, {
      props: { ...filteredJourneyProps, displayMode: 'chart' },
    })
    await flushPromises()

    await wrapper.get('[aria-label="移除筛选：负责人"]').trigger('click')

    const applied = wrapper.emitted('filter-apply')
    expect(applied?.[0]?.[0]).toEqual([])
    expect(wrapper.emitted('sort-reset')).toBeUndefined()
    expect(wrapper.emitted('column-config-reset')).toBeUndefined()
    expect(wrapper.emitted('update:view-display-mode')).toBeUndefined()
  })

  it('keeps the chart save action when only a sort remains', async () => {
    const wrapper = mount(BusinessJourneyTableView, {
      props: {
        ...filteredJourneyProps,
        displayMode: 'chart',
        filters: [],
      },
    })
    await flushPromises()
    const summary = wrapper.get('.list-view-state-summary')

    expect(summary.text()).toContain('无额外筛选')
    expect(summary.text()).not.toContain('清除筛选')
    expect(summary.text()).toContain('另存为视图')
    expect(summary.text()).not.toContain('排序：')
    expect(wrapper.get('.data-table-tools').text()).not.toContain('排序')
  })

  it('shows the filter and sort on the board summary without view config', async () => {
    const wrapper = mount(BusinessJourneyTableView, {
      props: { ...filteredJourneyProps, displayMode: 'board' },
      slots: {
        tableTools: '<button type="button">刷新</button>',
        replacement: '<div data-testid="journey-replacement">看板内容</div>',
      },
    })
    await flushPromises()

    const tools = wrapper.get('.data-table-tools').text()
    expect(tools).toContain('刷新')
    expect(tools).toContain('排序')
    expect(tools).not.toContain('字段配置')

    const summary = wrapper.get('.list-view-state-summary')
    expect(summary.text()).toContain('负责人 属于')
    expect(summary.text()).toContain('排序：最近动态 ↓')
    expect(summary.text()).not.toContain('已隐藏')
    expect(summary.text()).toContain('清除筛选')
    expect(summary.text()).toContain('另存为视图')

    await summary.get('.list-view-state-summary-clear').trigger('click')
    expect(wrapper.emitted('filter-reset')).toEqual([[]])
    expect(wrapper.emitted('sort-reset')).toEqual([[]])
    expect(wrapper.emitted('update:sorts')).toEqual([[[]]])
    expect(wrapper.emitted('column-config-reset')).toBeUndefined()
  })

  it('still clears filters, sorts, and hidden columns together on the list', async () => {
    const wrapper = mount(BusinessJourneyTableView, {
      props: {
        ...filteredJourneyProps,
        displayMode: 'table',
        contentHidden: false,
      },
    })
    await flushPromises()

    expect(wrapper.get('.data-table-tools').text()).toContain('字段配置')
    const summary = wrapper.get('.list-view-state-summary')
    expect(summary.text()).toContain('排序：最近动态 ↓')
    expect(summary.text()).toContain('已隐藏 1 列')

    await summary.get('.list-view-state-summary-clear').trigger('click')
    expect(wrapper.emitted('filter-reset')).toEqual([[]])
    expect(wrapper.emitted('sort-reset')).toEqual([[]])
    expect(wrapper.emitted('column-config-reset')).toEqual([[]])
  })

  it('keeps save-as-view on the status bar and out of the field config footer', async () => {
    const wrapper = mount(BusinessJourneyTableView, {
      props: {
        ...filteredJourneyProps,
        displayMode: 'table',
        contentHidden: false,
      },
      attachTo: document.body,
    })
    await flushPromises()

    const summary = wrapper.get('.list-view-state-summary')
    expect(summary.text()).toContain('清除筛选')
    expect(summary.text()).toContain('另存为视图')

    const trigger = wrapper.findAll('button').find((button) => button.text().includes('字段配置'))
    expect(trigger).toBeDefined()
    await trigger?.trigger('click')
    await flushPromises()

    const footer = document.body.querySelector('.table-toolbar-builder-footer')
    expect(footer).not.toBeNull()
    expect(footer?.textContent).toContain('恢复默认')
    expect(footer?.textContent).toContain('保存')
    expect(footer?.textContent).not.toContain('另存为视图')
    wrapper.unmount()
  })

  it('hides both status actions when only a search term is set', async () => {
    const wrapper = mount(BusinessJourneyTableView, {
      props: {
        ...filteredJourneyProps,
        displayMode: 'table',
        contentHidden: false,
        filters: [],
        sorts: [],
        columns: [],
        search: '续约',
      },
    })
    await flushPromises()

    const summary = wrapper.get('.list-view-state-summary')
    expect(summary.text()).not.toContain('清除筛选')
    expect(summary.text()).not.toContain('另存为视图')
  })
})
