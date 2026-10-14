import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import BoardView from '../BoardView.vue'
import type { BoardProjection } from '../boardTypes'

const projection: BoardProjection = {
  metrics: [
    {
      key: 'count',
      label: '客户数',
      value: '12',
      valueType: 'count',
    },
    {
      key: 'amount',
      label: '金额',
      value: '1200.00',
      valueType: 'amount',
      secondaryValue: '80',
      secondaryLabel: '占比',
    },
  ],
  columns: [
    {
      key: 'following',
      label: '跟进中',
      tone: 'info',
      countLabel: '2',
      amountLabel: '800.00',
      cards: [
        {
          id: 'cus_1',
          title: '星河科技',
          subtitle: '上海',
          primaryValue: '800.00',
          dateLabel: '2026-10-01',
          ownerLabel: '王敏',
          statusLabel: '跟进中',
          metadata: [{ key: 'industry', label: '行业', value: '软件' }],
        },
      ],
      hasMore: true,
      remainingCount: 3,
    },
    {
      key: 'won',
      label: '已成交',
      tone: 'success',
      countLabel: '0',
      amountLabel: null,
      cards: [],
      hasMore: false,
      remainingCount: 0,
    },
  ],
  trend: {
    title: '近六月趋势',
    description: '按完整月份统计',
    points: [{ month: '2026-09', values: { count: 2, amount: '800.00' } }],
    series: [{ key: 'count', label: '数量', color: 'hsl(var(--primary))' }],
  },
}

function mountBoard(props: Record<string, unknown> = {}) {
  return mount(BoardView, {
    props: {
      projection,
      loading: false,
      refreshing: false,
      stale: false,
      error: null,
      canDrillThrough: true,
      empty: false,
      ...props,
    },
    global: {
      stubs: {
        AreaTrendChart: {
          name: 'AreaTrendChart',
          props: ['title', 'description', 'data', 'series', 'xKey'],
          template: '<div class="trend-stub">{{ title }}</div>',
        },
      },
    },
  })
}

describe('BoardView', () => {
  it('activates a card with Enter and Space without activating from 查看全部', async () => {
    const wrapper = mountBoard()
    const card = wrapper.get('[data-column-key="following"] [role="button"]')

    await card.trigger('keydown', { key: 'Enter' })
    await card.trigger('keydown', { key: ' ' })

    expect(wrapper.emitted('activate-card')).toEqual([
      [{ id: 'cus_1', columnKey: 'following' }],
      [{ id: 'cus_1', columnKey: 'following' }],
    ])

    const viewAll = wrapper.get('[data-column-key="following"] button')
    expect(viewAll.text()).toContain('查看全部')
    await viewAll.trigger('click')
    expect(wrapper.emitted('activate-card')).toHaveLength(2)
    expect(wrapper.emitted('view-all')).toEqual([['following']])
  })

  it('disables stale drill-through while keeping the successful cards visible', async () => {
    const wrapper = mountBoard({
      stale: true,
      canDrillThrough: false,
      error: new Error('刷新失败'),
    })

    expect(wrapper.text()).toContain('星河科技')
    expect(wrapper.text()).toContain('数据已过期')
    expect(wrapper.text()).toContain('刷新失败')
    const viewAll = wrapper.get('[data-column-key="following"] button')
    expect(viewAll.attributes('disabled')).toBeDefined()
    await viewAll.trigger('click')
    expect(wrapper.emitted('view-all')).toBeUndefined()

    await wrapper.get('[data-testid="board-inline-retry"]').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('keeps an empty column visible and shows the board empty message only after success', () => {
    const loading = mountBoard({
      projection: null,
      loading: true,
      empty: false,
    })
    expect(loading.find('[data-testid="board-skeleton"]').exists()).toBe(true)
    expect(loading.text()).not.toContain('暂无看板数据')

    const empty = mountBoard({
      projection: { ...projection, columns: projection.columns.map((column) => ({ ...column, cards: [] })) },
      empty: true,
    })
    expect(empty.text()).toContain('暂无看板数据')
    expect(empty.text()).toContain('跟进中')
    expect(empty.text()).toContain('已成交')
    expect(empty.find('[data-column-key="won"]').text()).toContain('暂无记录')
  })

  it('shows a blocking first-load error and retries it', async () => {
    const wrapper = mountBoard({
      projection: null,
      loading: false,
      error: new Error('看板加载失败'),
      empty: false,
    })

    expect(wrapper.text()).toContain('看板加载失败')
    expect(wrapper.find('[data-column-key="following"]').exists()).toBe(false)
    await wrapper.get('[data-testid="board-blocking-retry"]').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('contains desktop column scrolling and selects one narrow-screen column', async () => {
    let width = 1280
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('max-width: 767px') && width <= 767,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })))

    const desktop = mountBoard()
    const columns = desktop.get('.board-columns')
    expect(columns.classes()).not.toContain('board-columns--narrow')
    expect(columns.element.className).toContain('board-columns')
    const style = document.createElement('style')
    style.textContent = '.board-columns { overflow-x: auto; overflow-y: hidden; }'
    document.head.append(style)
    expect(getComputedStyle(columns.element).overflowX).toBe('auto')
    style.remove()
    desktop.unmount()

    width = 390
    const narrow = mountBoard()
    const select = narrow.get('select')
    expect(select.element.value).toBe('following')
    expect(narrow.find('[data-column-key="won"]').exists()).toBe(false)

    await select.setValue('won')
    expect(narrow.find('[data-column-key="following"]').exists()).toBe(false)
    expect(narrow.get('[data-column-key="won"]').text()).toContain('已成交')
    expect(narrow.get('[data-column-key="won"]').text()).toContain('暂无记录')
    vi.unstubAllGlobals()
  })

  it('renders status text for every tone and passes typed trend points', () => {
    const tones = ['neutral', 'info', 'success', 'warning', 'danger', 'muted'] as const
    const wrapper = mountBoard({
      projection: {
        ...projection,
        columns: tones.map((tone) => ({
          ...projection.columns[0],
          key: tone,
          label: `${tone}状态`,
          tone,
        })),
      },
    })

    for (const tone of tones) {
      const column = wrapper.get(`[data-column-key="${tone}"]`)
      expect(column.text()).toContain(`${tone}状态`)
      expect(column.attributes('data-tone')).toBe(tone)
    }

    const chart = wrapper.getComponent({ name: 'AreaTrendChart' })
    expect(chart.props('xKey')).toBe('month')
    expect(chart.props('data')).toEqual([{ month: '2026-09', count: 2, amount: '800.00' }])
    expect(chart.props('series')).toEqual(projection.trend?.series)
  })
})
