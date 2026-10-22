import { defineComponent, h, type PropType } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import OpportunityChartPage from '@/components/opportunity/OpportunityChartPage.vue'
import type {
  OpportunityChartBucket,
  OpportunityChartCard,
  OpportunityChartResponse,
} from '@/schemas/opportunity'
interface DonutTestDatum { key: string, label: string, value: number, fill: string }

vi.mock('@unovis/vue', () => ({
  VisSingleContainer: defineComponent({
    name: 'VisSingleContainer',
    setup: (_, { slots }) => () => h('div', slots.default?.()),
  }),
  VisDonut: defineComponent({
    name: 'VisDonut',
    props: {
      data: { type: Array as PropType<DonutTestDatum[]>, default: () => [] },
      events: {
        type: Object as PropType<Record<string, { click?: (datum: DonutTestDatum) => void }>>,
        default: () => ({}),
      },
    },
    setup(props) {
      const click = Object.values(props.events)[0]?.click
      return () => h('div', props.data.map((datum) => h('button', {
        type: 'button',
        class: 'opportunity-chart-donut-segment',
        'data-donut-value': String(datum.value),
        'data-donut-fill': datum.fill,
        onClick: () => click?.(datum),
      }, datum.label)))
    },
  }),
}))

const chartCard = (key: string, bucket: Partial<OpportunityChartBucket> = {}): OpportunityChartCard => ({
  key,
  buckets: [{
    key: 'primary',
    label: '主分类',
    count: 4,
    amount: 120000,
    ratio: 100,
    amount_ratio: 100,
    preview: [{
      id: 'opp_1',
      name: '企业版采购',
      customer_name: '示例客户',
      owner_name: '李四',
      amount: 120000,
      expected_closing_date: '2026-10-20',
    }],
    preview_total: 1,
    ...bucket,
  }],
})

const metricBucket = (overrides: Partial<OpportunityChartBucket> = {}): OpportunityChartBucket => ({
  key: 'bucket',
  label: '分段',
  count: 1,
  amount: 100,
  ratio: 50,
  amount_ratio: 50,
  preview: [],
  preview_total: 1,
  ...overrides,
})

const chart: OpportunityChartResponse = {
  population: 64,
  total_amount: 9600000,
  cards: [
    chartCard('status', { key: 'active', label: '跟进中' }),
    chartCard('purchase_type', { key: 'new', label: '新购' }),
    chartCard('license_type', { key: 'subscription', label: '订阅' }),
    chartCard('amount_band', { key: 'small', label: '10 万以下' }),
    chartCard('product', { key: 'sales_cloud', label: '销售云' }),
    chartCard('win_probability', { key: 'high', label: '80–99%' }),
    chartCard('expected_closing_month', { key: '2026-10', label: '10月' }),
  ],
}

const stubs = {
  Card: { template: '<div><slot /></div>' },
  CardContent: { template: '<div><slot /></div>' },
  CardDescription: { template: '<div><slot /></div>' },
  CardHeader: { template: '<div><slot /></div>' },
  CardTitle: { template: '<h3><slot /></h3>' },
  Button: { template: '<button type="button"><slot /></button>' },
  ChartContainer: { template: '<div><slot /></div>' },
  ChartTooltip: { template: '<span />' },
  ChartTooltipContent: { template: '<span />' },
  Dialog: { props: ['open'], template: '<div v-if="open"><slot /></div>' },
  DialogContent: { template: '<div><slot /></div>' },
  DialogDescription: { template: '<div><slot /></div>' },
  DialogHeader: { template: '<div><slot /></div>' },
  DialogTitle: { template: '<h2><slot /></h2>' },
}

const mountPage = (value: OpportunityChartResponse) => mount(OpportunityChartPage, {
  props: {
    chart: value,
    loading: false,
    error: '',
    bucketOpportunities: null,
    bucketLoading: false,
    bucketError: '',
  },
  global: { stubs },
})

const cardWithBuckets = (key: string, buckets: OpportunityChartBucket[]): OpportunityChartCard => ({ key, buckets })

const bucket = (overrides: Partial<OpportunityChartBucket> = {}): OpportunityChartBucket => metricBucket(overrides)


describe('OpportunityChartPage', () => {
  it('shows the seven product-facing chart card labels and population summary', () => {
    const wrapper = mount(OpportunityChartPage, {
      props: {
        chart,
        loading: false,
        error: '',
        bucketOpportunities: null,
        bucketLoading: false,
        bucketError: '',
      },
      global: { stubs },
    })

    expect(wrapper.text()).toContain('64 条')
    expect(wrapper.text()).toContain('¥ 960 万')
    for (const title of ['状态', '采购类型', '授权模式', '金额档', '产品', '赢率', '预计成交']) {
      expect(wrapper.text()).toContain(title)
    }
  })

  it('opens a bucket preview and emits the selected opportunity when clicked', async () => {
    const wrapper = mount(OpportunityChartPage, {
      props: {
        chart,
        loading: false,
        error: '',
        bucketOpportunities: null,
        bucketLoading: false,
        bucketError: '',
      },
      global: { stubs },
    })

    const bucketButton = wrapper.find('button.opportunity-chart-legend-row')
    await bucketButton.trigger('click')
    expect(wrapper.emitted('view-bucket')).toHaveLength(1)
    expect(wrapper.text()).toContain('企业版采购')

    await wrapper.find('.opportunity-chart-opportunity').trigger('click')
    expect(wrapper.emitted('open-opportunity')).toEqual([['opp_1']])
  })
  it('keeps the bucket dialog open when an opportunity row is selected', async () => {
    const wrapper = mountPage(chart)

    await wrapper.find('button.opportunity-chart-legend-row').trigger('click')
    await wrapper.find('.opportunity-chart-opportunity').trigger('click')

    expect(wrapper.emitted('close-bucket')).toBeUndefined()
    expect(wrapper.emitted('open-opportunity')).toHaveLength(1)
    expect(wrapper.find('.opportunity-chart-opportunity').exists()).toBe(true)
  })

  it('opens a bucket when a donut segment is clicked', async () => {
    const wrapper = mountPage(chart)

    await wrapper.find('.opportunity-chart-donut-segment').trigger('click')

    expect(wrapper.emitted('view-bucket')).toHaveLength(1)
    expect(wrapper.emitted('view-bucket')?.[0]?.[1]).toEqual(chart.cards[0]?.buckets[0])
  })

  it('emits a retry event for the selected bucket after a bucket error', async () => {
    const wrapper = mount(OpportunityChartPage, {
      props: {
        chart,
        loading: false,
        error: '',
        bucketOpportunities: null,
        bucketLoading: false,
        bucketError: '分段加载失败',
      },
      global: { stubs },
    })

    await wrapper.find('button.opportunity-chart-legend-row').trigger('click')
    await wrapper.get('.opportunity-chart-bucket-retry').trigger('click')

    expect(wrapper.emitted('retry-bucket')).toEqual([[
      chart.cards[0],
      chart.cards[0]?.buckets[0],
    ]])
  })

  it('renders a one-percent bucket as a one-percent donut segment', () => {
    const value: OpportunityChartResponse = {
      ...chart,
      cards: [cardWithBuckets('status', [
        bucket({ key: 'one', label: '1%', count: 1, ratio: 1, amount_ratio: 1 }),
        bucket({ key: 'rest', label: '其余', count: 99, ratio: 99, amount_ratio: 99 }),
      ])],
    }

    const wrapper = mountPage(value)
    const values = wrapper.findAll('.opportunity-chart-donut-segment').map((segment) => segment.attributes('data-donut-value'))
    expect(values.slice(0, 2)).toEqual(['0.01', '0.99'])
  })

  it('keeps donut slice colors aligned with legend swatches after empty buckets', () => {
    const value: OpportunityChartResponse = {
      ...chart,
      cards: [cardWithBuckets('status', [
        bucket({ key: 'empty', label: '空', count: 0, ratio: 0, amount_ratio: 0 }),
        bucket({ key: 'active', label: '跟进中', count: 1, ratio: 50, amount_ratio: 50 }),
        bucket({ key: 'won', label: '已赢单', count: 1, ratio: 50, amount_ratio: 50 }),
      ])],
    }

    const wrapper = mountPage(value)
    const fills = wrapper.findAll('.opportunity-chart-donut-segment').map((segment) => segment.attributes('data-donut-fill'))
    expect(fills).toEqual(['hsl(var(--chart-2))', 'hsl(var(--chart-3))'])
    const swatches = wrapper.findAll('.opportunity-chart-legend-row i').map((swatch) => swatch.attributes('style'))
    expect(swatches).toEqual([
      'background-color: hsl(var(--chart-1));',
      'background-color: hsl(var(--chart-2));',
      'background-color: hsl(var(--chart-3));',
    ])
  })

  it('keeps unscheduled visible as its own bucket and disables zero-count buckets', () => {
    const unscheduled: OpportunityChartBucket = {
      key: 'unscheduled',
      label: '未排期',
      count: 2,
      amount: 300000,
      ratio: 50,
      amount_ratio: 50,
      preview: [],
      preview_total: 0,
    }
    const zero: OpportunityChartBucket = {
      key: 'empty',
      label: '空分段',
      count: 0,
      amount: 0,
      ratio: 0,
      amount_ratio: 0,
      preview: [],
      preview_total: 0,
    }
    const emptyChart: OpportunityChartResponse = {
      ...chart,
      cards: [
        ...chart.cards.slice(0, 6),
        { key: 'expected_closing_month', buckets: [unscheduled, zero] },
      ],
    }
    const wrapper = mount(OpportunityChartPage, {
      props: {
        chart: emptyChart,
        loading: false,
        error: '',
        bucketOpportunities: null,
        bucketLoading: false,
        bucketError: '',
      },
      global: { stubs },
    })

    expect(wrapper.text()).toContain('未排期')
    const buttons = wrapper.findAll('button.opportunity-chart-bar-row')
    expect(buttons.at(-1)?.attributes('disabled')).toBeDefined()
  })
  it('renders backend 0–100 ratios as fractional donut values', () => {
    const value: OpportunityChartResponse = {
      ...chart,
      cards: [cardWithBuckets('status', [
        bucket({ key: 'active', label: '跟进中', count: 43, ratio: 43, amount_ratio: 20 }),
        bucket({ key: 'won', label: '已赢单', count: 57, ratio: 57, amount_ratio: 80 }),
      ])],
    }

    const wrapper = mountPage(value)
    const values = wrapper.findAll('.opportunity-chart-donut-segment').map((segment) => segment.attributes('data-donut-value'))
    expect(values.slice(0, 2)).toEqual(['0.43', '0.57'])
  })

  it('selects count or amount metrics for donut cards and centers the dominant bucket', () => {
    const value: OpportunityChartResponse = {
      ...chart,
      cards: [
        cardWithBuckets('status', [
          bucket({ key: 'active', label: '跟进中', count: 80, ratio: 80, amount_ratio: 20 }),
          bucket({ key: 'won', label: '已赢单', count: 20, ratio: 20, amount_ratio: 80 }),
        ]),
        cardWithBuckets('purchase_type', [
          bucket({ key: 'new', label: '新购', count: 80, ratio: 80, amount_ratio: 20 }),
          bucket({ key: 'renewal', label: '续购', count: 20, ratio: 20, amount_ratio: 80 }),
        ]),
        cardWithBuckets('license_type', [
          bucket({ key: 'subscription', label: '订阅', count: 80, ratio: 80, amount_ratio: 20 }),
          bucket({ key: 'perpetual', label: '买断', count: 20, ratio: 20, amount_ratio: 80 }),
        ]),
      ],
    }

    const wrapper = mountPage(value)
    const centers = wrapper.findAll('.opportunity-chart-donut-hole')
    expect(centers[0]?.text()).toContain('跟进中')
    expect(centers[0]?.text()).toContain('80%')
    expect(centers[1]?.text()).toContain('续购')
    expect(centers[1]?.text()).toContain('80%')
    expect(centers[2]?.text()).toContain('买断')
    expect(centers[2]?.text()).toContain('80%')
  })

  it('uses count metrics for regular bars and actual amounts for forecast bar heights', () => {
    const value: OpportunityChartResponse = {
      ...chart,
      cards: [
        cardWithBuckets('amount_band', [
          bucket({ key: 'small', label: '小额', count: 80, ratio: 80, amount_ratio: 20 }),
          bucket({ key: 'large', label: '大额', count: 20, ratio: 20, amount_ratio: 80 }),
        ]),
        cardWithBuckets('product', [
          bucket({ key: 'cloud', label: '销售云', count: 80, ratio: 80, amount_ratio: 20 }),
          bucket({ key: 'other', label: '其他', count: 20, ratio: 20, amount_ratio: 80 }),
        ]),
        cardWithBuckets('win_probability', [
          bucket({ key: 'high', label: '高', count: 80, ratio: 80, amount_ratio: 20 }),
          bucket({ key: 'low', label: '低', count: 20, ratio: 20, amount_ratio: 80 }),
        ]),
        cardWithBuckets('expected_closing_month', [
          bucket({ key: '2026-10', label: '10月', count: 80, amount: 100, ratio: 80, amount_ratio: 20 }),
          bucket({ key: 'unscheduled', label: '未排期', count: 20, amount: 400, ratio: 20, amount_ratio: 80 }),
        ]),
      ],
    }

    const wrapper = mountPage(value)
    const regularCards = wrapper.findAll('.opportunity-chart-card--bar')
    for (const cardWrapper of regularCards) {
      const fills = cardWrapper.findAll('.opportunity-chart-bar-fill')
      expect(fills[0]?.attributes('style')).toContain('width: 100%')
      expect(fills[1]?.attributes('style')).toContain('width: 25%')
    }
    const forecast = wrapper.find('.opportunity-chart-card--forecast')
    const forecastFills = forecast.findAll('.opportunity-chart-forecast-fill')
    expect(forecastFills[0]?.attributes('style')).toContain('height: 25%')
    expect(forecastFills[1]?.attributes('style')).toContain('height: 100%')
  })

  it('keeps the summary and all seven card containers for an empty population', () => {
    const emptyCards = chart.cards.map((card) => ({
      ...card,
      buckets: card.buckets.map((bucket) => ({
        ...bucket,
        count: 0,
        amount: 0,
        ratio: 0,
        amount_ratio: 0,
        preview: [],
        preview_total: 0,
      })),
    }))
    const wrapper = mountPage({ population: 0, total_amount: 0, cards: emptyCards })

    expect(wrapper.text()).toContain('0 条')
    expect(wrapper.text()).toContain('¥ 0 万')
    expect(wrapper.find('.opportunity-chart-state').exists()).toBe(false)
    expect(wrapper.findAll('.opportunity-chart-card')).toHaveLength(7)
    expect(wrapper.findAll('.opportunity-chart-card-empty')).toHaveLength(7)
    for (const title of ['状态', '采购类型', '授权模式', '金额档', '产品', '赢率', '预计成交']) {
      expect(wrapper.text()).toContain(title)
    }
  })

  it('renders expected-closing as a full-width axis plot with unscheduled visible', () => {
    const value: OpportunityChartResponse = {
      ...chart,
      cards: [cardWithBuckets('expected_closing_month', [
        bucket({ key: '2026-10', label: '10月', count: 2, ratio: 50, amount_ratio: 50 }),
        bucket({ key: 'unscheduled', label: '未排期', count: 2, ratio: 50, amount_ratio: 50 }),
      ])],
    }

    const wrapper = mountPage(value)
    const forecast = wrapper.find('.opportunity-chart-card--forecast')
    expect(wrapper.find('.opportunity-chart-forecast-chart').exists()).toBe(true)
    expect(forecast.find('.opportunity-chart-forecast-plot').exists()).toBe(true)
    expect(forecast.findAll('.opportunity-chart-forecast-column')).toHaveLength(2)
    expect(forecast.find('.opportunity-chart-forecast-column--unscheduled').exists()).toBe(true)
    expect(wrapper.text()).toContain('未排期')
  })
  it('renders forecast data in an axis-based vertical plot with explicit zero and unscheduled states', () => {
    const value: OpportunityChartResponse = {
      ...chart,
      cards: [cardWithBuckets('expected_closing_month', [
        bucket({ key: '2026-10', label: '10月', count: 1, amount: 121800, amount_ratio: 28.9 }),
        bucket({ key: '2026-11', label: '11月', count: 1, amount: 300000, amount_ratio: 71.1 }),
        bucket({ key: '2026-12', label: '12月', count: 0, amount: 0, amount_ratio: 0 }),
        bucket({ key: 'unscheduled', label: '未排期', count: 1, amount: 100, amount_ratio: 0.03 }),
      ])],
    }

    const wrapper = mountPage(value)
    const forecast = wrapper.find('.opportunity-chart-card--forecast')

    expect(forecast.find('.opportunity-chart-forecast-plot').exists()).toBe(true)
    expect(forecast.find('.opportunity-chart-forecast-y-axis').exists()).toBe(true)
    expect(forecast.find('.opportunity-chart-forecast-baseline').exists()).toBe(true)
    expect(forecast.findAll('.opportunity-chart-forecast-column')).toHaveLength(4)
    expect(forecast.find('.opportunity-chart-forecast-column--unscheduled').exists()).toBe(true)
    expect(forecast.findAll('.opportunity-chart-bar-track')).toHaveLength(0)
    expect(forecast.find('.opportunity-chart-forecast-fill[style*="height: 0%"]').exists()).toBe(true)
  })

})
