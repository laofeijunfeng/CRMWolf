import { mount, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import CustomerChartPage from '../CustomerChartPage.vue'
import type { CustomerChartResponse } from '@/schemas/customer'

vi.mock('@unovis/ts', () => ({ Area: { selectors: { area: 'area' } }, Donut: { selectors: { segment: 'segment' } } }))
vi.mock('@unovis/vue', () => Object.fromEntries(['VisArea', 'VisAxis', 'VisDonut', 'VisLine', 'VisSingleContainer', 'VisXYContainer', 'VisTooltip', 'VisCrosshair'].map(name => [name, { template: '<div><slot /></div>' }])))

const chart: CustomerChartResponse = {
  population: 2,
  cards: [
    { key: 'status', title: '状态', description: '客户状态', buckets: [{ key: 'active', label: '跟进中', count: 2, ratio: 100, preview: [], preview_total: 2 }, { key: 'lost', label: '已流失', count: 0, ratio: 0, preview: [], preview_total: 0 }] },
    { key: 'industry', title: '行业', description: '客户行业', buckets: [{ key: 'software', label: '软件', count: 2, ratio: 100, preview: [], preview_total: 2 }, { key: 'other', label: '其他行业', count: 0, ratio: 0, preview: [], preview_total: 0 }] },
    { key: 'city', title: '城市', description: '客户城市', buckets: [{ key: 'shanghai', label: '上海', count: 2, ratio: 100, preview: [], preview_total: 2 }] },
    { key: 'created_month', title: '创建月份', description: '客户月份', buckets: [{ key: '2026-11', label: '11月', count: 2, ratio: 100, preview: [], preview_total: 2 }] },
  ],
}
const wrappers: VueWrapper[] = []
function render(): VueWrapper {
  const wrapper = mount(CustomerChartPage, { props: { chart, loading: false, error: '', bucketCustomers: null, bucketLoading: false, bucketError: '', bucketResetToken: 0 }, attachTo: document.body })
  wrappers.push(wrapper)
  return wrapper
}
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()); document.body.innerHTML = '' })

describe('Customer chart bucket controls', () => {
  it('keeps the legend static beside enabled bucket actions and disables empty buckets', async () => {
    const wrapper = render()
    const action = wrapper.get('button[aria-label="跟进中，2 家 · 100%"]')
    expect(wrapper.get('button[aria-label="已流失，0 家 · 0%"]').attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('span').some(node => node.text() === '跟进中' && !node.element.closest('button'))).toBe(true)
    await action.trigger('click')
    expect(wrapper.emitted('view-bucket')?.[0]).toEqual([chart.cards[0], chart.cards[0]?.buckets[0]])
    expect(document.body.querySelector('[role="dialog"]')).not.toBeNull()
  })

  it('closes on controlled invalidation without emitting a parent close and can reopen another bucket', async () => {
    const wrapper = render()
    await wrapper.get('button[aria-label="跟进中，2 家 · 100%"]').trigger('click')
    await wrapper.setProps({ bucketResetToken: 1 })
    expect(document.body.querySelector('[role="dialog"][data-state="open"]')).toBeNull()
    expect(wrapper.emitted('close-bucket')).toBeUndefined()
    await wrapper.get('button[aria-label="11月，2 家 · 100%"]').trigger('click')
    expect(wrapper.emitted('view-bucket')?.[1]?.[0]).toMatchObject({ key: 'created_month' })
  })

  it('offers industry and city actions without an action for the folded remainder', async () => {
    const wrapper = render()
    await wrapper.get('button[aria-label="软件，2 家 · 100%"]').trigger('click')
    await wrapper.get('button[aria-label="上海，2 家 · 100%"]').trigger('click')
    expect(wrapper.emitted('view-bucket')?.map(event => event[0])).toEqual([chart.cards[1], chart.cards[2]])
    expect(wrapper.find('button[aria-label^="其他行业，"]').exists()).toBe(false)
  })

  it('retries the selected bucket and retains customer detail and pagination controls during append failures', async () => {
    const wrapper = render()
    await wrapper.get('button[aria-label="跟进中，2 家 · 100%"]').trigger('click')
    await wrapper.setProps({ bucketError: '读取失败' })
    document.body.querySelector<HTMLButtonElement>('[data-testid="customer-chart-retry"]')?.click()
    await nextTick()
    expect(wrapper.emitted('view-bucket')).toHaveLength(2)
    await wrapper.setProps({ bucketError: '', bucketCustomers: { chart: 'status', bucket: 'active', total: 2, customers: [{ id: 'customer-1', name: '示例客户', owner_name: null }] } })
    const row = Array.from(document.body.querySelectorAll('button')).find(button => button.textContent?.includes('示例客户') === true)
    expect(row?.textContent).toContain('无负责人')
    row?.click()
    expect(wrapper.emitted('open-customer')?.[0]).toEqual(['customer-1'])
    document.body.querySelector<HTMLButtonElement>('[data-testid="customer-chart-load-more"]')?.click()
    await nextTick()
    expect(wrapper.emitted('load-more')).toHaveLength(1)
    await wrapper.setProps({ bucketLoading: true })
    expect(document.body.textContent).toContain('示例客户')
    expect(document.body.querySelector<HTMLButtonElement>('[data-testid="customer-chart-load-more"]')?.disabled).toBe(true)
    await wrapper.setProps({ bucketLoading: false, bucketError: '下一页失败' })
    expect(document.body.textContent).toContain('示例客户')
    expect(document.body.querySelector('[data-testid="customer-chart-load-more"]')?.textContent).toContain('下一页失败')
  })
})
