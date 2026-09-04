import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ListViewStateSummary from '../ListViewStateSummary.vue'

const baseProps = {
  viewLabel: '重点客户',
  filters: [{
    id: 'filter:name:contains:0',
    field: 'name',
    fieldLabel: '客户名称',
    operator: 'contains' as const,
    operatorLabel: '包含',
    valueLabel: 'Acme',
    removable: true,
  }],
  sorts: [{
    id: 'sort:0:updated_at:desc',
    field: 'updated_at',
    fieldLabel: '更新时间',
    direction: 'desc' as const,
    directionLabel: '最晚-最早',
    priority: 1,
  }],
  hiddenColumnCount: 2,
}

describe('ListViewStateSummary', () => {
  it('keeps the current view state visible after tools are closed', () => {
    const wrapper = mount(ListViewStateSummary, { props: baseProps })

    expect(wrapper.text()).toContain('当前视图')
    expect(wrapper.text()).toContain('重点客户')
    expect(wrapper.text()).toContain('客户名称 包含')
    expect(wrapper.text()).toContain('“Acme”')
    expect(wrapper.text()).toContain('排序：更新时间 ↓')
    expect(wrapper.text()).toContain('已隐藏 2 列')
  })

  it('emits a single-filter removal and clear-filters actions', async () => {
    const wrapper = mount(ListViewStateSummary, { props: baseProps })

    await wrapper.get('[aria-label="移除筛选：客户名称"]').trigger('click')
    expect(wrapper.emitted('remove-filter')).toEqual([['filter:name:contains:0']])

    const clearButton = wrapper.findAll('button').find((button) => button.text() === '清除筛选')
    expect(clearButton).toBeDefined()
    await clearButton?.trigger('click')
    expect(wrapper.emitted('clear-filters')).toEqual([[]])
  })

  it('shows applying feedback and failure retry feedback', async () => {
    const applyingWrapper = mount(ListViewStateSummary, {
      props: { ...baseProps, applying: true },
    })
    expect(applyingWrapper.text()).toContain('正在应用视图…')
    expect(applyingWrapper.find('[role="alert"]').exists()).toBe(false)

    const errorWrapper = mount(ListViewStateSummary, {
      props: {
        ...baseProps,
        applying: false,
        applyError: {
          title: '视图应用失败',
          description: '当前仍显示上一次成功加载的列表，可重试应用该视图',
          retryable: true,
        },
      },
    })
    expect(errorWrapper.get('[role="alert"]').text()).toContain('当前仍显示上一次成功加载的列表')
    await errorWrapper.get('[role="alert"] button').trigger('click')
    expect(errorWrapper.emitted('retry-view-apply')).toEqual([[]])
  })

  it('does not render a clear action when there are no filters', () => {
    const wrapper = mount(ListViewStateSummary, {
      props: { ...baseProps, filters: [] },
    })

    expect(wrapper.text()).toContain('无额外筛选')
    expect(wrapper.text()).not.toContain('清除筛选')
  })
})
