import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SelectionSummary from '../SelectionSummary.vue'

describe('SelectionSummary', () => {
  it('renders an accessible matching skeleton while context is loading', () => {
    const wrapper = mount(SelectionSummary, {
      props: {
        loading: true,
        loadingCount: 5,
        loadingDetails: true,
        items: [],
        details: [],
      },
      attachTo: document.body,
    })

    const status = wrapper.get('.selection-summary[role="status"]')
    expect(status.attributes('aria-live')).toBe('polite')
    expect(status.attributes('aria-busy')).toBe('true')
    expect(status.attributes('aria-label')).toBe('加载中')
    expect(wrapper.findAll('.selection-summary__skeleton-label')).toHaveLength(5)
    expect(wrapper.findAll('.selection-summary__skeleton-value')).toHaveLength(5)
    expect(wrapper.find('.selection-summary__details-trigger').exists()).toBe(false)
    expect(wrapper.find('.selection-summary__skeleton-details').exists()).toBe(true)

    wrapper.unmount()
  })

  it('renders compact primary context and collapsible secondary context', async () => {
    const wrapper = mount(SelectionSummary, {
      props: {
        variant: 'compact',
        items: [
          { key: 'customer', label: '客户', value: '飞驰科技' },
          { key: 'contract', label: '合同', value: '年度服务合同' },
          { key: 'stage', label: '回款阶段', value: '首付款' },
          { key: 'remainingAmount', label: '待回款', value: '70,000.00' },
          { key: 'status', label: '当前状态', value: 'PARTIAL' },
        ],
        details: [
          { key: 'planNumber', label: '计划编号', value: 'PP-2026-0018' },
          { key: 'plannedAmount', label: '计划金额', value: '100,000.00' },
          { key: 'paidAmount', label: '已回款', value: '30,000.00' },
        ],
      },
      slots: {
        'value-status': '<span>部分回款</span>',
      },
      attachTo: document.body,
    })

    expect(wrapper.classes()).toContain('selection-summary--compact')
    expect(wrapper.text()).toContain('飞驰科技')
    expect(wrapper.text()).toContain('年度服务合同')
    expect(wrapper.text()).toContain('部分回款')

    const detailsTrigger = wrapper.get('button.selection-summary__details-trigger')
    expect(detailsTrigger.attributes('aria-expanded')).toBe('false')
    expect(detailsTrigger.text()).toContain('详情')

    await detailsTrigger.trigger('click')

    expect(detailsTrigger.attributes('aria-expanded')).toBe('true')
    expect(wrapper.text()).toContain('PP-2026-0018')
    expect(wrapper.text()).toContain('100,000.00')

    wrapper.unmount()
  })
})
