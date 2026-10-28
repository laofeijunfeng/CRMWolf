import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { Donut } from '@unovis/ts'
import { VisDonut, VisGroupedBar, VisSingleContainer, VisXYContainer } from '@unovis/vue'
import BusinessJourneyChartView from '@/components/business-journey/BusinessJourneyChartView.vue'
import { ChartContainer } from '@/components/ui/chart'
import type { BusinessJourneyChartResponse, BusinessJourneyChartSegment } from '@/schemas/dealJourney'

function segment(key: string, label: string, count: number, amount: number): BusinessJourneyChartSegment {
  return { key, label, count, amount, preview: [] }
}

const chart: BusinessJourneyChartResponse = {
  summary: { total_count: 86, total_amount: 12800000 },
  cards: [
    {
      key: 'stage', title: '阶段', description: '八个看板阶段都在。', graphic: 'horizontal_bar',
      segments: [
        segment('early_communication', '初期交流', 24, 2100000),
        segment('active_progress', '持续推进', 18, 3200000),
        segment('closing_soon', '即将签约', 10, 1800000),
        segment('contract_processing', '签约中', 8, 1500000),
        segment('payment_processing', '回款中', 6, 1400000),
        segment('invoice_processing', '开票中', 4, 900000),
        segment('completed', '已完成', 12, 1600000),
        segment('lost', '已输单', 4, 300000)
      ]
    },
    {
      key: 'purchase_type', title: '采购类型', description: '按金额占比。没填的单独列出。', graphic: 'pie',
      segments: [segment('NEW', '新购', 40, 5900000), segment('RENEWAL', '续购', 28, 4100000), segment('EXPANSION', '增购', 14, 2300000), segment('unset', '未填写', 4, 500000)]
    },
    {
      key: 'amount_band', title: '金额档', description: '看是很多小单，还是几笔大单。', graphic: 'horizontal_bar',
      segments: [segment('under_100k', '10 万以下', 30, 1200000), segment('100k_500k', '10–50 万', 34, 4100000), segment('500k_1m', '50–100 万', 14, 3800000), segment('over_1m', '100 万以上', 8, 3700000)]
    },
    {
      key: 'product', title: '产品', description: '数量最多的 8 个，其余并进其他。', graphic: 'horizontal_bar',
      segments: [segment('销售云', '销售云', 22, 3400000), segment('other', '其他', 10, 1600000), segment('unset', '未填写', 4, 400000)]
    },
    {
      key: 'recent_activity', title: '最近动态', description: '只看多久没动静，不提示该联系谁。', graphic: 'horizontal_bar',
      segments: [segment('within_7', '7 天内', 28, 4200000), segment('8_to_30', '8–30 天', 20, 3100000), segment('over_30', '30 天以上', 18, 2600000), segment('none', '没有动态', 10, 1400000)]
    },
    {
      key: 'expected_closing', title: '预计成交', description: '本月起 6 个月。没填预计成交日的单独是未排期，不并进本月。', graphic: 'vertical_bar',
      segments: [segment('2026-10', '10月', 12, 1800000), segment('2026-11', '11月', 16, 2600000), segment('2026-12', '12月', 9, 1400000), segment('2027-01', '1月', 11, 2100000), segment('2027-02', '2月', 6, 900000), segment('2027-03', '3月', 8, 1200000), segment('unscheduled', '未排期', 24, 2800000)]
    }
  ]
}

describe('BusinessJourneyChartView', () => {
  it('shows six cards and closing labels without chart tabs', () => {
    const wrapper = mount(BusinessJourneyChartView, { props: { chart } })

    expect(wrapper.findAll('.journey-chart-card')).toHaveLength(6)
    expect(wrapper.find('[role="tablist"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('86 条')
    expect(wrapper.text()).toContain('阶段')
    expect(wrapper.text()).toContain('采购类型')
    expect(wrapper.text()).toContain('金额档')
    expect(wrapper.text()).toContain('产品')
    expect(wrapper.text()).toContain('最近动态')
    expect(wrapper.text()).toContain('预计成交')
    expect(wrapper.text()).toContain('未排期')
    expect(wrapper.text()).toContain('不提示该联系谁')
    const stage = chart.cards[0]
    expect(stage?.segments.reduce((sum, item) => sum + item.count, 0)).toBe(86)
  })

  it('uses official chart primitives with stable color and tooltip data contracts', () => {
    const wrapper = mount(BusinessJourneyChartView, { props: { chart } })

    const containers = wrapper.findAllComponents(ChartContainer)
    expect(containers).toHaveLength(2)
    expect(wrapper.findComponent(VisDonut).props('arcWidth')).toBe(30)
    expect(wrapper.findComponent(VisGroupedBar).exists()).toBe(true)

    const pieConfig = containers[0]?.props('config') as Record<string, { color?: string }>
    expect(pieConfig.NEW?.color).toBe('hsl(var(--chart-1))')
    expect(pieConfig.unset?.color).toBe('hsl(var(--muted-foreground))')

    const pieData = wrapper.findComponent(VisSingleContainer).props('data') as Array<Record<string, unknown>>
    expect(pieData[0]?.NEW).toBe(5900000)
    expect(pieData[0]?.amount).toBe(5900000)

    const closingConfig = containers[1]?.props('config') as Record<string, { color?: string }>
    expect(closingConfig.amount?.color).toBe('hsl(var(--primary))')
    const closingData = wrapper.findComponent(VisXYContainer).props('data') as Array<{ key: string; fill: string }>
    expect(closingData.at(-1)).toMatchObject({ key: 'unscheduled', fill: 'hsl(var(--muted-foreground))' })
  })
  it('selects a segment from the wrapped Unovis donut datum', () => {
    const wrapper = mount(BusinessJourneyChartView, { props: { chart } })
    const donut = wrapper.findComponent(VisDonut)
    expect(donut.props('centralLabel')).toBe('86')
    expect(donut.props('centralSubLabel')).toBe('条')
    const events = donut.props('events') as Record<string, { click?: (datum: unknown) => void }>

    events[Donut.selectors.segment]?.click?.({ data: { key: 'NEW' } })

    expect(wrapper.emitted('open-segment')?.[0]?.[0]).toMatchObject({
      segment: { key: 'NEW' }
    })
  })

  it('exposes the expected-closing chart as a named graphic', () => {
    const wrapper = mount(BusinessJourneyChartView, { props: { chart } })

    expect(wrapper.find('.journey-chart-closing-plot').attributes('role')).toBe('img')
    expect(wrapper.find('.journey-chart-closing-summary').exists()).toBe(false)
  })

  it('places the pie beside recent activity and gives the long cards their own row', () => {
    const wrapper = mount(BusinessJourneyChartView, { props: { chart } })
    const cards = wrapper.findAll('.journey-chart-card')
    expect(cards[0]?.text()).toContain('采购类型')
    expect(cards[1]?.text()).toContain('最近动态')
    expect(cards[0]?.classes()).not.toContain('journey-chart-card--wide')
    expect(cards[1]?.classes()).not.toContain('journey-chart-card--wide')
    expect(cards[1]?.attributes('data-graphic')).toBe('horizontal_bar')
    for (const card of cards.slice(2)) {
      expect(card.classes()).toContain('journey-chart-card--wide')
    }
    expect(wrapper.find('.h-\\[220px\\]').exists()).toBe(true)
  })

  it('opens the segment dialog and emits the journey detail', async () => {
    const preview = {
      public_id: 'journey-1',
      customer_id: 'customer-1',
      customer_name: '示例客户',
      name: '示例旅程',
      amount: 120000
    }
    const wrapper = mount(BusinessJourneyChartView, {
      props: {
        chart,
        segmentOpen: true,
        segmentLabel: '初期交流',
        segmentTotal: 1,
        segmentItems: [preview]
      }
    })

    await wrapper.find('.journey-chart-bars button').trigger('click')
    expect(wrapper.emitted('open-segment')).toHaveLength(1)
    const detailButton = document.body.querySelector('.journey-chart-segment-list button')
    if (!(detailButton instanceof HTMLElement)) throw new Error('记录没有出现在对话框里')
    expect(detailButton.textContent).toContain('示例旅程')
    detailButton.click()
    expect(wrapper.emitted('open-journey')?.[0]?.[0]).toEqual({
      customerId: 'customer-1',
      journeyPublicId: 'journey-1'
    })
  })
})
