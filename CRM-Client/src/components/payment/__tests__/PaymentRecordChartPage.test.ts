import { mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import PaymentRecordChartPage from '@/components/payment/PaymentRecordChartPage.vue'
import type { PaymentRecordChartBucket, PaymentRecordChartBucketRecords, PaymentRecordChartResponse } from '@/schemas/paymentRecordChart'

vi.mock('@unovis/ts', () => ({
  Donut: { selectors: { segment: 'segment' } },
  Area: { selectors: { area: 'area' } },
  Scatter: { selectors: { point: 'point' } },
}))

vi.mock('@unovis/vue', () => ({
  VisSingleContainer: { name: 'VisSingleContainer', template: '<div><slot /></div>' },
  VisDonut: { name: 'VisDonut', template: '<div />' },
  VisXYContainer: { name: 'VisXYContainer', template: '<div><slot /></div>' },
  VisArea: { name: 'VisArea', props: ['events'], template: '<div />' },
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

const mountedCharts: VueWrapper[] = []

afterEach(() => {
  for (const wrapper of mountedCharts.splice(0)) {
    if (wrapper.exists()) wrapper.unmount()
  }
})

function mountChart(value: PaymentRecordChartResponse = chart): VueWrapper {
  const wrapper = mount(PaymentRecordChartPage, {
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
  mountedCharts.push(wrapper)
  return wrapper
}

describe('PaymentRecordChartPage', () => {
  it('shows the batch total, keeps zero legend rows, and sizes bars by amount', () => {
    const wrapper = mountChart()

    expect(wrapper.get('[data-testid="payment-record-chart-title"]').text()).toContain('2 笔')
    expect(wrapper.get('[data-testid="payment-record-chart-title"]').text()).toContain('¥ 15 万')
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

  it('shows only the selected bucket response and requests more when its total exceeds loaded rows', async () => {
    const wrapper = mountChart()

    await wrapper.get('[data-testid="payment-chart-legend-purchase_type-EXPANSION"]').trigger('click')
    expect(wrapper.emitted('view-bucket')).toBeUndefined()

    await wrapper.get('[data-testid="payment-chart-legend-license_type-SUBSCRIPTION"]').trigger('click')
    expect(wrapper.emitted('view-bucket')?.[0]).toMatchObject([
      { key: 'license_type' },
      { key: 'SUBSCRIPTION' },
    ])
    expect(document.body.textContent ?? '').not.toContain('HK008')
    expect(document.body.querySelector('[data-testid="payment-chart-view-more"]')).toBeNull()

    const bucketRecords: PaymentRecordChartBucketRecords = {
      chart: 'license_type',
      bucket: 'SUBSCRIPTION',
      total: 1,
      records: [{ id: 9, record_number: 'HK009', customer_name: '乙', amount: 150000, payment_date: '2026-10-03' }],
    }
    await wrapper.setProps({ bucketRecords: { ...bucketRecords, bucket: 'PERPETUAL' } })
    expect(document.body.textContent ?? '').not.toContain('HK009')

    await wrapper.setProps({ bucketRecords })
    expect(document.body.textContent ?? '').toContain('HK009')
    expect(document.body.querySelector('[data-testid="payment-chart-view-more"]')).toBeNull()

    await wrapper.setProps({ bucketRecords: { ...bucketRecords, total: 6 } })
    const viewMore = document.body.querySelector<HTMLButtonElement>('[data-testid="payment-chart-view-more"]')
    expect(viewMore).not.toBeNull()
    viewMore?.click()
    expect(wrapper.emitted('load-more')).toHaveLength(1)
    wrapper.unmount()
  })

  it('closes the selected bucket when the parent reset token changes', async () => {
    const wrapper = mountChart()

    await wrapper.get('[data-testid="payment-chart-legend-license_type-SUBSCRIPTION"]').trigger('click')
    expect(document.body.querySelector('[role="dialog"]')).not.toBeNull()

    await wrapper.setProps({ resetToken: 1 })
    await wrapper.vm.$nextTick()

    expect(document.body.querySelector('[role="dialog"][data-state="open"]')).toBeNull()
    expect(wrapper.emitted('close-bucket')).toBeUndefined()
    wrapper.unmount()
  })

  it('removes fixed month action lists while preserving ARR curve labels', () => {
    const wrapper = mountChart({
      ...chart,
      cards: [...chart.cards, {
        key: 'arr_ratio', title: 'ARR 占比', description: '',
        buckets: [{ ...bucket('2026-01', '1月', 1, 200000), plotted_ratio: 53 }],
      }],
    })

    expect(wrapper.find('[data-testid^="payment-chart-month-"]:not([data-testid="payment-chart-month-tooltip"])').exists()).toBe(false)
    expect(wrapper.find('[data-testid^="payment-chart-arr-"]:not([data-testid="payment-chart-arr-tooltip"]):not([data-testid^="payment-chart-arr-label-"])').exists()).toBe(false)
    expect(wrapper.find('.payment-record-chart__month-actions').exists()).toBe(false)
    expect(wrapper.get('[data-testid="payment-chart-arr-label-2026-01"]').text()).toBe('53%')
    wrapper.unmount()
  })

  it('shows month, count, and amount while hovering the payment month chart', async () => {
    const months = emptyMonths()
    months[0] = bucket('2026-01', '1月', 2, 125000)
    const wrapper = mountChart({ ...chart, cards: chart.cards.map((card) => card.key === 'payment_month' ? { ...card, buckets: months } : card) })
    const plot = wrapper.get('.payment-record-chart__month-plot')
    vi.spyOn(plot.element, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 256, 240))

    await plot.trigger('mousemove', { clientX: 48, clientY: 100 })

    expect(wrapper.get('[data-testid="payment-chart-month-tooltip"]').text()).toContain('1月')
    expect(wrapper.get('[data-testid="payment-chart-month-tooltip"]').text()).toContain('2 笔')
    expect(wrapper.get('[data-testid="payment-chart-month-tooltip"]').text()).toContain('¥125,000.00')
    wrapper.unmount()
  })

  it('opens a zero-payment month through the plotted area event', async () => {
    const months = emptyMonths()
    months[0] = bucket('2026-01', '1月', 0, 0)
    months[1] = bucket('2026-02', '2月', 1, 125000)
    const wrapper = mountChart({ ...chart, cards: chart.cards.map((card) => card.key === 'payment_month' ? { ...card, buckets: months } : card) })
    const plot = wrapper.get('.payment-record-chart__month-plot')
    vi.spyOn(plot.element, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 256, 240))
    const area = wrapper.findAllComponents({ name: 'VisArea' })[0]
    expect(area).toBeDefined()
    const events = area?.props('events') as Record<string, { click: (datum: unknown, event: MouseEvent) => void }> | undefined
    const target = document.createElement('path')
    plot.element.append(target)
    const event = new MouseEvent('click', { bubbles: true, clientX: 48, clientY: 100 })
    Object.defineProperty(event, 'currentTarget', { value: target })
    events?.['area']?.click([months[0]], event)
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('view-bucket')?.[0]).toMatchObject([
      { key: 'payment_month' },
      { key: '2026-01', count: 0 },
    ])
    wrapper.unmount()
  })

  it('shows all ARR details while hovering an undefined month', async () => {
    const wrapper = mountChart({
      ...chart,
      cards: [...chart.cards, {
        key: 'arr_ratio', title: 'ARR 占比', description: '',
        buckets: [{ ...bucket('2026-01', '1月', 0, 0), plotted_ratio: null }, { ...bucket('2026-02', '2月', 1, 200000), plotted_ratio: 0 }],
      }],
    })
    const plot = wrapper.get('.payment-record-chart__arr-plot')
    vi.spyOn(plot.element, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 256, 240))

    await plot.trigger('mousemove', { clientX: 48, clientY: 100 })

    const tooltip = wrapper.get('[data-testid="payment-chart-arr-tooltip"]')
    expect(tooltip.text()).toContain('1月')
    expect(tooltip.text()).toContain('未定义')
    wrapper.unmount()
  })

  it('opens only defined ARR months, including a valid zero percent', async () => {
    const wrapper = mountChart({
      ...chart,
      cards: [...chart.cards, {
        key: 'arr_ratio', title: 'ARR 占比', description: '',
        buckets: [{ ...bucket('2026-01', '1月', 0, 0), plotted_ratio: null }, { ...bucket('2026-02', '2月', 1, 200000), plotted_ratio: 0 }],
      }],
    })
    const plot = wrapper.get('.payment-record-chart__arr-plot')
    vi.spyOn(plot.element, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 256, 240))

    await plot.trigger('click', { clientX: 48, clientY: 100 })
    expect(wrapper.emitted('view-bucket')).toBeUndefined()
    await plot.trigger('click', { clientX: 248, clientY: 100 })
    expect(wrapper.emitted('view-bucket')?.[0]).toMatchObject([
      { key: 'arr_ratio' },
      { key: '2026-02', plotted_ratio: 0 },
    ])
    wrapper.unmount()
  })

  it('renders paged record details and keeps loaded rows during load-more errors', async () => {
    const wrapper = mountChart()
    await wrapper.get('[data-testid="payment-chart-legend-license_type-SUBSCRIPTION"]').trigger('click')
    expect(document.body.querySelector('[role="status"]')?.textContent).toContain('正在读取这一段回款')

    await wrapper.setProps({ bucketError: '暂时无法读取' })
    const dialog = document.body.querySelector('[role="dialog"]')
    expect(dialog?.textContent).toContain('暂时无法读取')
    dialog?.querySelector<HTMLButtonElement>('[role="alert"] button')?.click()
    expect(wrapper.emitted('retry-bucket')?.[0]).toMatchObject([
      { key: 'license_type' }, { key: 'SUBSCRIPTION' },
    ])

    await wrapper.setProps({
      bucketError: '',
      bucketRecords: {
        chart: 'license_type', bucket: 'SUBSCRIPTION', total: 2,
        records: [{ id: 8, record_number: 'HK008', customer_name: '甲', amount: 150000, payment_date: '2026-10-02' }],
      },
    })
    expect(dialog?.textContent).toContain('HK008')
    expect(dialog?.textContent).toContain('甲 · 2026-10-02')
    dialog?.querySelector<HTMLButtonElement>('.payment-record-chart__dialog-list button')?.click()
    expect(wrapper.emitted('open-record')?.[0]).toEqual([8])
    document.body.querySelector<HTMLButtonElement>('[data-testid="payment-chart-view-more"]')?.click()
    expect(wrapper.emitted('load-more')).toHaveLength(1)

    await wrapper.setProps({ bucketError: '读取更多失败' })
    expect(dialog?.textContent).toContain('HK008')
    expect(document.body.querySelector('[data-testid="payment-chart-view-more"]')?.textContent).toContain('读取更多失败')
  })

  it('shows defined ARR values in the hover detail', async () => {
    const wrapper = mountChart({
      ...chart,
      cards: [...chart.cards, {
        key: 'arr_ratio', title: 'ARR 占比', description: '',
        buckets: [{
          ...bucket('2026-01', '1月', 1, 200000),
          plotted_ratio: 53,
          annualized_subscription: 100000,
          buyout_amount: 200000,
        }],
      }],
    })
    const plot = wrapper.get('.payment-record-chart__arr-plot')
    vi.spyOn(plot.element, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 256, 240))

    await plot.trigger('mousemove', { clientX: 48, clientY: 100 })

    const tooltip = wrapper.get('[data-testid="payment-chart-arr-tooltip"]')
    expect(tooltip.text()).toContain('1月')
    expect(tooltip.text()).toContain('¥ 10 万')
    expect(tooltip.text()).toContain('¥ 20 万')
    expect(tooltip.text()).toContain('53%')
    wrapper.unmount()
  })

  it('keeps the month and ARR cards ordered without persistent month details', () => {
    const wrapper = mountChart({
      ...chart,
      cards: [...chart.cards, { key: 'arr_ratio', title: 'ARR 占比', description: '', buckets: [] }],
    })
    const month = wrapper.get('[data-testid="payment-chart-card-payment_month"]')
    const arr = wrapper.get('[data-testid="payment-chart-card-arr_ratio"]')
    expect(month.element.compareDocumentPosition(arr.element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(arr.text()).toContain('ARR 占比')
    expect(arr.find('.payment-record-chart__month-actions').exists()).toBe(false)
    expect(arr.find('.payment-record-chart__arr-label').exists()).toBe(false)
    wrapper.unmount()
  })
})
