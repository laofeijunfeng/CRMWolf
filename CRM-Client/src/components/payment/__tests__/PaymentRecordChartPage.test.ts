import { mount, type VueWrapper } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import PaymentRecordChartPage from '@/components/payment/PaymentRecordChartPage.vue'
import type { PaymentRecordChartBucket, PaymentRecordChartResponse } from '@/schemas/paymentRecordChart'

vi.mock('@unovis/ts', () => ({
  Donut: { selectors: { segment: 'segment' } },
  Area: { selectors: { area: 'area' } },
  Scatter: { selectors: { point: 'point' } },
}))

vi.mock('@unovis/vue', () => ({
  VisSingleContainer: { name: 'VisSingleContainer', template: '<div><slot /></div>' },
  VisDonut: { name: 'VisDonut', template: '<div />' },
  VisXYContainer: { name: 'VisXYContainer', template: '<div><slot /></div>' },
  VisArea: { name: 'VisArea', template: '<div />' },
  VisLine: { name: 'VisLine', template: '<div />' },
  VisScatter: { name: 'VisScatter', template: '<div />' },
  VisAxis: { name: 'VisAxis', template: '<div />' },
  VisTooltip: { name: 'VisTooltip', template: '<div />' },
  VisCrosshair: { name: 'VisCrosshair', template: '<div />' },
}))

function bucket(
  key: string,
  label: string,
  count: number,
  amount: number,
  previewTotal = count,
): PaymentRecordChartBucket {
  return {
    key,
    label,
    count,
    amount,
    ratio: 0,
    amount_ratio: 0,
    preview: count === 0 ? [] : [{
      id: 8,
      record_number: 'HK008',
      customer_name: '甲',
      amount,
      payment_date: '2026-10-02',
    }],
    preview_total: previewTotal,
  }
}

function emptyMonths(): PaymentRecordChartBucket[] {
  return Array.from({ length: 12 }, (_item, index) => (
    bucket(`2026-${String(index + 1).padStart(2, '0')}`, `${index + 1}月`, 0, 0)
  ))
}

const chart: PaymentRecordChartResponse = {
  population: 2,
  total_amount: 150000,
  cards: [
    {
      key: 'license_type',
      title: '授权模式',
      description: '按回款金额看订阅和买断。没关联到的单独列出。',
      buckets: [
        bucket('SUBSCRIPTION', '订阅', 1, 150000, 1),
        bucket('PERPETUAL', '买断', 0, 0),
        bucket('blank', '未填写', 0, 0),
      ],
    },
    {
      key: 'purchase_type',
      title: '采购类型',
      description: '按回款金额看新购、续购、增购。没填的单独列出。',
      buckets: [
        bucket('NEW', '新购', 1, 150000, 1),
        bucket('RENEWAL', '续购', 0, 0),
        bucket('EXPANSION', '增购', 0, 0),
        bucket('blank', '未填写', 0, 0),
      ],
    },
    {
      key: 'amount_band',
      title: '金额档',
      description: '按回款金额分档。',
      buckets: [
        bucket('under_100k', '10 万以下', 1, 50000, 1),
        bucket('100k_500k', '10–50 万', 1, 100000, 1),
        bucket('500k_1m', '50–100 万', 0, 0),
        bucket('over_1m', '100 万以上', 0, 0),
      ],
    },
    {
      key: 'payment_month',
      title: '回款月份',
      description: '最近 12 个月，每个月回了多少。更早的不在这张图上。',
      buckets: emptyMonths(),
    },
  ],
}

function mountChart(value: PaymentRecordChartResponse = chart): VueWrapper {
  return mount(PaymentRecordChartPage, {
    props: {
      chart: value,
      loading: false,
      error: '',
      bucketRecords: null,
      bucketLoading: false,
      bucketError: '',
    },
    attachTo: document.body,
  })
}

describe('PaymentRecordChartPage', () => {
  it('shows the batch total, keeps zero legend rows, and sizes bars by amount', () => {
    const wrapper = mountChart()

    expect(wrapper.get('[data-testid="payment-record-chart-title"]').text()).toContain('2 笔')
    expect(wrapper.get('[data-testid="payment-record-chart-title"]').text()).toContain('¥ 15 万')
    expect(wrapper.get('.payment-record-chart__heading p').text()).toBe('当前筛选范围内的回款。一页同时看，没有审批和确认状态。金额按回款金额汇总。')
    expect(wrapper.get('[data-testid="payment-chart-card-license_type"]').classes()).not.toContain('payment-record-chart__wide')
    expect(wrapper.get('[data-testid="payment-chart-card-purchase_type"]').classes()).not.toContain('payment-record-chart__wide')
    expect(wrapper.get('[data-testid="payment-chart-card-amount_band"]').classes()).toContain('payment-record-chart__wide')
    const legend = wrapper.get('[data-testid="payment-chart-legend-license_type-SUBSCRIPTION"]')
    const split = wrapper.get('[data-testid="payment-chart-card-license_type"] .payment-record-chart__donut-body')
    expect(split.element.contains(legend.element)).toBe(true)
    const expansion = wrapper.get('[data-testid="payment-chart-legend-purchase_type-EXPANSION"]')
    expect(expansion.attributes('disabled')).toBeDefined()
    expect(expansion.text()).toContain('0 笔')
    const longer = wrapper.get('[data-testid="payment-chart-bar-100k_500k"]')
    const shorter = wrapper.get('[data-testid="payment-chart-bar-under_100k"]')
    expect(longer.find('.payment-record-chart__fill').attributes('style')).toContain('width: 100%')
    expect(shorter.find('.payment-record-chart__fill').attributes('style')).toContain('width: 50%')
    expect(wrapper.get('[data-testid="payment-chart-card-payment_month"]').text()).toContain('回款月份')
    expect(wrapper.find('[data-testid="payment-chart-bar-earlier"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('opens a segment preview and asks for the full list only when more rows exist', async () => {
    const wrapper = mountChart()

    await wrapper.get('[data-testid="payment-chart-legend-purchase_type-EXPANSION"]').trigger('click')
    expect(document.body.textContent ?? '').not.toContain('HK008')

    await wrapper.get('[data-testid="payment-chart-legend-license_type-SUBSCRIPTION"]').trigger('click')
    expect(document.body.textContent ?? '').toContain('HK008')
    expect(document.body.querySelector('[data-testid="payment-chart-view-all"]')).toBeNull()

    const widePreview: PaymentRecordChartResponse = {
      ...chart,
      cards: chart.cards.map((card) => card.key === 'license_type'
        ? {
            ...card,
            buckets: card.buckets.map((item) => item.key === 'SUBSCRIPTION'
              ? { ...item, preview_total: 6 }
              : item),
          }
        : card),
    }
    await wrapper.setProps({ chart: widePreview })
    await wrapper.get('[data-testid="payment-chart-legend-license_type-SUBSCRIPTION"]').trigger('click')
    document.body.querySelector<HTMLButtonElement>('[data-testid="payment-chart-view-all"]')?.click()
    const events = wrapper.emitted('view-bucket')
    expect(events?.[0]?.[1]).toMatchObject({ key: 'SUBSCRIPTION', preview_total: 6 })
    wrapper.unmount()
  })

  it('places the ARR card under the month chart and labels only defined months', () => {
    const months = Array.from({ length: 12 }, (_item, index) => {
      const key = `2026-${String(index + 1).padStart(2, '0')}`
      const label = `${index + 1}月`
      if (index === 1) return bucket(key, label, 0, 0)
      if (index === 3) {
        return {
          ...bucket(key, label, 1, 200000),
          plotted_ratio: 0,
          annualized_subscription: 0,
          buyout_amount: 200000,
        }
      }
      if (index === 9) {
        return {
          ...bucket(key, label, 4, 720000),
          plotted_ratio: 57,
          annualized_subscription: 260000,
          buyout_amount: 200000,
        }
      }
      return {
        ...bucket(key, label, 1, 100000),
        plotted_ratio: 40,
        annualized_subscription: 100000,
        buyout_amount: 150000,
      }
    })
    const withArr: PaymentRecordChartResponse = {
      ...chart,
      cards: [
        ...chart.cards,
        {
          key: 'arr_ratio',
          title: 'ARR 占比',
          description: '和回款月份同一种面积加线。纵轴是占比。没有回款的月份也连过去，不写成 0%。只有买断落到 0%。',
          buckets: months,
        },
      ],
    }
    const wrapper = mountChart(withArr)
    const month = wrapper.get('[data-testid="payment-chart-card-payment_month"]')
    const arr = wrapper.get('[data-testid="payment-chart-card-arr_ratio"]')
    expect(month.element.compareDocumentPosition(arr.element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(arr.text()).toContain('ARR 占比')
    expect(arr.text()).toContain('没有回款的月份也连过去，不写成 0%。只有买断落到 0%。')
    expect(wrapper.get('[data-testid="payment-chart-arr-label-2026-04"]').text()).toBe('0%')
    expect(wrapper.get('[data-testid="payment-chart-arr-label-2026-10"]').text()).toBe('57%')
    expect(wrapper.find('[data-testid="payment-chart-arr-label-2026-02"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
