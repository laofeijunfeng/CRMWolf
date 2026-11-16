import { mount, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import OpportunityChartPage from '../OpportunityChartPage.vue'
import type { OpportunityChartResponse } from '@/schemas/opportunity'

vi.mock('@unovis/ts', () => ({ Donut: { selectors: { segment: 'segment' } } }))
vi.mock('@unovis/vue', () => ({
  VisDonut: { template: '<div />' },
  VisSingleContainer: { template: '<div><slot /></div>' },
}))

const chart: OpportunityChartResponse = {
  population: 3,
  total_amount: 30000,
  cards: [
    { key: 'status', buckets: [
      { key: 'active', label: '跟进中', count: 2, amount: 20000, ratio: 66.67, amount_ratio: 66.67, preview: [], preview_total: 2 },
      { key: 'lost', label: '已输单', count: 0, amount: 0, ratio: 0, amount_ratio: 0, preview: [], preview_total: 0 },
    ] },
    { key: 'win_probability', buckets: [
      { key: 'high', label: '高赢率', count: 1, amount: 10000, ratio: 33.33, amount_ratio: 33.33, preview: [], preview_total: 1 },
    ] },
    { key: 'expected_closing_month', buckets: [
      { key: '2026-11', label: '2026年11月', count: 1, amount: 10000, ratio: 33.33, amount_ratio: 33.33, preview: [], preview_total: 1 },
      { key: 'unscheduled', label: '未排期', count: 2, amount: 20000, ratio: 66.67, amount_ratio: 66.67, preview: [], preview_total: 2 },
    ] },
  ],
}

const wrappers: VueWrapper[] = []
function mountChart(): VueWrapper {
  const wrapper = mount(OpportunityChartPage, {
    props: { chart, loading: false, error: '', bucketOpportunities: null, bucketLoading: false, bucketError: '', bucketResetToken: 0 },
    attachTo: document.body,
  })
  wrappers.push(wrapper)
  return wrapper
}
function dialogButton(testId: string): HTMLButtonElement {
  const button = document.body.querySelector<HTMLButtonElement>(`[data-testid="${testId}"]`)
  if (button === null) throw new Error(`Missing button ${testId}`)
  return button
}

afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount())
  document.body.innerHTML = ''
})

describe('OpportunityChartPage bucket controls', () => {
  it('opens donut, bar and unscheduled forecast buckets through accessible buttons while disabling empty buckets', async () => {
    const wrapper = mountChart()
    const empty = wrapper.get('button[aria-label^="已输单，"]')
    expect(empty.attributes('disabled')).toBeDefined()
    await empty.trigger('click')
    expect(wrapper.emitted('view-bucket')).toBeUndefined()

    await wrapper.get('button[aria-label^="跟进中，"]').trigger('click')
    expect(wrapper.emitted('view-bucket')?.[0]).toEqual([chart.cards[0], chart.cards[0]?.buckets[0]])
    await wrapper.setProps({ bucketResetToken: 1 })
    await wrapper.get('button[aria-label^="高赢率，"]').trigger('click')
    expect(wrapper.emitted('view-bucket')?.[1]).toEqual([chart.cards[1], chart.cards[1]?.buckets[0]])
    await wrapper.setProps({ bucketResetToken: 2 })
    await wrapper.get('button[aria-label^="未排期，"]').trigger('click')
    expect(wrapper.emitted('view-bucket')?.[2]).toEqual([chart.cards[2], chart.cards[2]?.buckets[1]])
    expect(document.body.querySelector('[role="dialog"]')?.textContent).toContain('未排期')
  })

  it('closes on external reset without a close echo and ignores late stale rows when another bucket opens', async () => {
    const wrapper = mountChart()
    await wrapper.get('button[aria-label^="跟进中，"]').trigger('click')
    expect(document.body.querySelector('[role="dialog"][data-state="open"]')).not.toBeNull()
    await wrapper.setProps({ bucketResetToken: 1 })
    expect(document.body.querySelector('[role="dialog"][data-state="open"]')).toBeNull()
    expect(wrapper.emitted('close-bucket')).toBeUndefined()
    await wrapper.setProps({ bucketOpportunities: { chart: 'status', bucket: 'active', total: 1, opportunities: [
      { id: 'stale', name: '过期商机', amount: 10000, customer_name: null, owner_name: null, expected_closing_date: null },
    ] } })
    await wrapper.get('button[aria-label^="未排期，"]').trigger('click')
    expect(document.body.querySelector('[role="dialog"][data-state="open"]')?.textContent).not.toContain('过期商机')
    const close = document.body.querySelector<HTMLButtonElement>('[role="dialog"][data-state="open"] button[aria-label="关闭"]')
    if (close === null) throw new Error('Missing close button')
    close.click()
    await nextTick()
    expect(wrapper.emitted('close-bucket')).toEqual([[]])
  })

  it('retries initial errors and preserves loaded item navigation during pagination', async () => {
    const wrapper = mountChart()
    await wrapper.get('button[aria-label^="跟进中，"]').trigger('click')
    await wrapper.setProps({ bucketError: '暂时无法读取' })
    dialogButton('opportunity-chart-bucket-retry').click()
    await nextTick()
    expect(wrapper.emitted('retry-bucket')?.[0]).toEqual([chart.cards[0], chart.cards[0]?.buckets[0]])

    await wrapper.setProps({ bucketError: '', bucketOpportunities: { chart: 'status', bucket: 'active', total: 2, opportunities: [
      { id: 'current', name: '当前商机', amount: 10000, customer_name: null, owner_name: null, expected_closing_date: null },
    ] } })
    dialogButton('opportunity-chart-bucket-load-more').click()
    await nextTick()
    expect(wrapper.emitted('load-more')).toEqual([[]])
    await wrapper.setProps({ bucketLoading: true })
    expect(dialogButton('opportunity-chart-bucket-load-more').disabled).toBe(true)
    const item = document.body.querySelector<HTMLButtonElement>('.opportunity-chart-opportunity')
    if (item === null) throw new Error('Missing opportunity')
    expect(item.textContent).toContain('未关联客户 · 未分配负责人')
    item.click()
    await nextTick()
    expect(wrapper.emitted('open-opportunity')).toEqual([['current']])
  })
})
