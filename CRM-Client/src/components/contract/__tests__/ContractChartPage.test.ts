import { mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ContractChartPage from '../ContractChartPage.vue'
import type { ContractChartResponse } from '@/api/contract'

vi.mock('@unovis/ts', () => ({ Donut: { selectors: { segment: 'segment' } }, GroupedBar: { selectors: { bar: 'bar' } } }))
vi.mock('@unovis/vue', () => ({
  VisAxis: {
    props: ['tickValues', 'tickFormat'],
    template: '<div class="vis-axis"><span v-for="value in tickValues" :key="value">{{ tickFormat ? tickFormat(value) : value }}</span></div>',
  },
  ...Object.fromEntries(['VisDonut', 'VisGroupedBar', 'VisSingleContainer', 'VisXYContainer', 'VisTooltip', 'VisCrosshair'].map(name => [name, { template: '<div><slot /></div>' }])),
}))

const chart: ContractChartResponse = {
  population: 3,
  total_amount: 120000,
  cards: [
    { key: 'license_type', title: '许可类型', description: '合同许可', buckets: [{ key: 'annual', label: '年度', count: 2, amount: 80000, ratio: 0, amount_ratio: 67, preview: [], preview_total: 2 }, { key: 'blank', label: '未填写', count: 0, amount: 0, ratio: 0, amount_ratio: 0, preview: [], preview_total: 0 }] },
    { key: 'amount_band', title: '金额区间', description: '合同金额', buckets: [{ key: 'small', label: '小额', count: 2, amount: 20000, ratio: 0, amount_ratio: 17, preview: [], preview_total: 2 }] },
    { key: 'signing_month', title: '签约月份', description: '签约趋势', buckets: [{ key: 'earlier', label: '更早', count: 1, amount: 50000, ratio: 0, amount_ratio: 0, preview: [], preview_total: 1 }, { key: '2026-06', label: '6月', count: 0, amount: 0, ratio: 0, amount_ratio: 0, preview: [], preview_total: 0 }, { key: '2026-07', label: '7月', count: 0, amount: 0, ratio: 0, amount_ratio: 0, preview: [], preview_total: 0 }, { key: '2026-08', label: '8月', count: 0, amount: 0, ratio: 0, amount_ratio: 0, preview: [], preview_total: 0 }, { key: '2026-09', label: '9月', count: 0, amount: 0, ratio: 0, amount_ratio: 0, preview: [], preview_total: 0 }, { key: '2026-10', label: '10月', count: 0, amount: 0, ratio: 0, amount_ratio: 0, preview: [], preview_total: 0 }, { key: '2026-11', label: '11月', count: 1, amount: 100000, ratio: 0, amount_ratio: 83, preview: [], preview_total: 1 }, { key: 'future', label: '未到期签署', count: 0, amount: 0, ratio: 0, amount_ratio: 0, preview: [], preview_total: 0 }, { key: 'unsigned', label: '未签署', count: 1, amount: 20000, ratio: 0, amount_ratio: 17, preview: [], preview_total: 1 }] },
  ],
}
const wrappers: VueWrapper[] = []
function render(): VueWrapper {
  const wrapper = mount(ContractChartPage, { props: { chart, loading: false, error: '', bucketContracts: null, bucketLoading: false, bucketError: '', bucketResetToken: 0 }, attachTo: document.body })
  wrappers.push(wrapper)
  return wrapper
}
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()); document.body.innerHTML = '' })

describe('Contract chart bucket controls', () => {
  it('provides keyboard bucket actions while preserving chart labels and disables empty non-month buckets', async () => {
    const wrapper = render()
    expect(wrapper.get('button[aria-label="年度，2 份 · ¥ 8 万"]')).toBeDefined()
    expect(wrapper.get('button[aria-label="未填写，0 份 · ¥ 0"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('许可类型')
    await wrapper.get('button[aria-label="年度，2 份 · ¥ 8 万"]').trigger('click')
    expect(wrapper.emitted('view-bucket')?.[0]).toEqual([chart.cards[0], chart.cards[0]?.buckets[0]])
  })
  it('maps every signing month bucket to an x-axis label without a visible duplicate list', () => {
    const wrapper = render()
    expect(wrapper.findAll('.vis-axis span').map((label) => label.text())).toEqual(['更早', '6月', '7月', '8月', '9月', '10月', '11月', '未到期签署', '未签署'])
    expect(wrapper.find('.contract-chart-page__month-actions').classes()).toContain('sr-only')
    expect(wrapper.get('button[aria-label="未到期签署，0 份 · ¥ 0"]').attributes('disabled')).toBeDefined()
  })

  it('keeps non-empty special month buckets keyboard activatable', async () => {
    const wrapper = render()
    await wrapper.get('button[aria-label="未签署，1 份 · ¥ 2 万"]').trigger('click')
    expect(wrapper.emitted('view-bucket')?.[0]?.[1]).toMatchObject({ key: 'unsigned' })
  })

  it('keeps month bucket actions and resets the dialog without a close loop', async () => {
    const wrapper = render()
    expect(wrapper.get('button[aria-label="10月，0 份 · ¥ 0"]').attributes('disabled')).toBeDefined()
    await wrapper.get('button[aria-label="11月，1 份 · ¥ 10 万"]').trigger('click')
    expect(wrapper.emitted('view-bucket')?.[0]?.[1]).toMatchObject({ key: '2026-11' })
    expect(document.body.querySelector('[role="dialog"]')).not.toBeNull()
    await wrapper.setProps({ bucketResetToken: 1 })
    expect(document.body.querySelector('[role="dialog"][data-state="open"]')).toBeNull()
    expect(wrapper.emitted('close-bucket')).toBeUndefined()
  })

  it('preserves retry, preview details, pagination and append error behavior', async () => {
    const wrapper = render()
    await wrapper.get('button[aria-label="年度，2 份 · ¥ 8 万"]').trigger('click')
    await wrapper.setProps({ bucketError: '读取失败' })
    document.body.querySelector<HTMLButtonElement>('[data-testid="contract-chart-retry"]')?.click()
    expect(wrapper.emitted('retry-bucket')).toHaveLength(1)
    await wrapper.setProps({ bucketError: '', bucketContracts: { chart: 'license_type', bucket: 'annual', total: 2, contracts: [{ id: 10, name: '合同一', customer_name: null, amount: 5000 }] } })
    expect(document.body.textContent).toContain('合同一')
    expect(document.body.textContent).toContain('无客户')
    const row = Array.from(document.body.querySelectorAll('button')).find(button => button.textContent?.includes('合同一') === true)
    row?.click()
    expect(wrapper.emitted('open-contract')?.[0]).toEqual([10])
    document.body.querySelector<HTMLButtonElement>('[data-testid="contract-chart-load-more"]')?.click()
    expect(wrapper.emitted('load-more')).toHaveLength(1)
    await wrapper.setProps({ bucketLoading: true })
    expect(document.body.textContent).toContain('合同一')
    await wrapper.setProps({ bucketLoading: false, bucketError: '下一页失败' })
    expect(document.body.textContent).toContain('合同一')
    expect(document.body.querySelector('[data-testid="contract-chart-load-more"]')?.textContent).toContain('下一页失败')
  })
})
