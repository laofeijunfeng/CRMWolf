import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ListViewStateSummary from '../ListViewStateSummary.vue'

const baseProps = {
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
  it('keeps the active list state visible after tools are closed', () => {
    const wrapper = mount(ListViewStateSummary, { props: baseProps })

    expect(wrapper.text()).not.toContain('当前视图')
    expect(wrapper.text()).not.toContain('重点客户')
    expect(wrapper.text()).toContain('客户名称 包含')
    expect(wrapper.text()).toContain('“Acme”')
    expect(wrapper.text()).toContain('排序：更新时间 ↓')
    expect(wrapper.text()).toContain('已隐藏 2 列')
    expect(wrapper.get('.list-view-state-summary-filter').attributes('aria-label')).toBe('客户名称 包含 “Acme”')
    expect(wrapper.get('.list-view-state-summary-filter').attributes('tabindex')).toBe('0')
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

  it('places clear and save after filters, sorts, and hidden columns', async () => {
    const wrapper = mount(ListViewStateSummary, {
      props: { ...baseProps, saveViewEnabled: true },
    })

    const labels = wrapper.findAll('button').map((button) => button.text())
    const clearIndex = labels.indexOf('清除筛选')
    const saveIndex = labels.indexOf('另存为视图')
    expect(clearIndex).toBeGreaterThan(-1)
    expect(saveIndex).toBe(clearIndex + 1)

    await wrapper.findAll('button').find((button) => button.text() === '另存为视图')?.trigger('click')
    expect(wrapper.emitted('save-view')).toEqual([[]])
  })

  it('hides both actions when only the default list state remains', () => {
    const wrapper = mount(ListViewStateSummary, {
      props: { filters: [], sorts: [], hiddenColumnCount: 0, saveViewEnabled: true },
    })

    expect(wrapper.text()).toContain('无额外筛选')
    expect(wrapper.text()).not.toContain('清除筛选')
    expect(wrapper.text()).not.toContain('另存为视图')
  })

  it('shows both actions when only a sort or a hidden column remains', () => {
    const sortOnly = mount(ListViewStateSummary, {
      props: { filters: [], sorts: baseProps.sorts, hiddenColumnCount: 0, saveViewEnabled: true },
    })
    expect(sortOnly.text()).toContain('清除筛选')
    expect(sortOnly.text()).toContain('另存为视图')

    const hiddenOnly = mount(ListViewStateSummary, {
      props: { filters: [], sorts: [], hiddenColumnCount: 1, saveViewEnabled: true },
    })
    expect(hiddenOnly.text()).toContain('清除筛选')
    expect(hiddenOnly.text()).toContain('另存为视图')
  })
})
