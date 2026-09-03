import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DataTable from '../DataTable.vue'

const fields = [
  {
    key: 'name',
    label: '名称',
    type: 'text' as const,
    column: true,
  },
]

const baseProps = {
  fields,
  total: 1,
  page: 1,
  pageSize: 20,
  height: '400px',
}

describe('DataTable feedback states', () => {
  it('shows the initial loading skeleton without rendering an empty table', () => {
    const wrapper = mount(DataTable, {
      props: {
        ...baseProps,
        data: [],
        loading: true,
      },
    })

    expect(wrapper.findComponent({ name: 'LoadingSkeleton' }).exists()).toBe(true)
    expect(wrapper.find('.data-table-card').exists()).toBe(false)
  })

  it('shows a blocking error and emits retry when no previous data exists', async () => {
    const wrapper = mount(DataTable, {
      props: {
        ...baseProps,
        data: [],
        loadError: {
          title: '列表加载失败',
          description: '请重试',
        },
      },
    })

    expect(wrapper.text()).toContain('列表加载失败')
    const retry = wrapper.get('[data-testid="data-table-retry"]')
    await retry.trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('keeps previous rows visible and shows an inline retry for refresh errors', async () => {
    const wrapper = mount(DataTable, {
      props: {
        ...baseProps,
        data: [{ name: 'Acme' }],
        loadError: {
          title: '刷新失败',
          description: '当前显示旧数据',
        },
      },
    })

    expect(wrapper.text()).toContain('Acme')
    expect(wrapper.find('[data-testid="data-table-refresh-retry"]').exists()).toBe(true)
    await wrapper.get('[data-testid="data-table-refresh-retry"]').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('uses the filtered empty-state copy when filters are active', async () => {
    const wrapper = mount(DataTable, {
      props: {
        ...baseProps,
        data: [],
        filters: [{ field: 'name', op: 'contains', value: 'missing' }],
      },
    })

    expect(wrapper.text()).toContain('未找到匹配结果')
    expect(wrapper.text()).toContain('请调整筛选条件或清除筛选后重试')
    const clearFilters = wrapper.get('[data-testid="data-table-clear-filters"]')
    await clearFilters.trigger('click')
    expect(wrapper.emitted('filter-reset')).toHaveLength(1)
  })

  it('keeps the explicit fixed height when fill strategy is used', () => {
    const wrapper = mount(DataTable, {
      props: {
        ...baseProps,
        data: [{ name: 'Acme' }],
        heightStrategy: 'fill',
        compactPagination: true,
      },
    })

    expect(wrapper.get('.data-table-card').classes()).toContain('data-table-card--fill')
    expect(wrapper.get('.data-table-card').attributes('style')).toContain('height: 400px')
    expect(wrapper.get('.data-table-footer').classes()).toContain('data-table-footer--compact')
  })

  it('moves vertical scrolling to the page when using the page strategy', () => {
    const wrapper = mount(DataTable, {
      props: {
        ...baseProps,
        data: [{ name: 'Acme' }],
        heightStrategy: 'page',
      },
    })

    expect(wrapper.get('.data-table-card').classes()).toContain('data-table-card--page')
    expect(wrapper.get('.data-table-card').attributes('style')).toBeUndefined()
    expect(wrapper.get('.data-table-content').classes()).toContain('data-table-content--page')
  })

  it('supports selecting eligible rows and selecting the current page', async () => {
    const wrapper = mount(DataTable, {
      props: {
        ...baseProps,
        data: [{ id: 1, name: 'Acme' }, { id: 2, name: 'Locked' }],
        selectable: true,
        getRowSelectable: (row: Record<string, unknown>) => row['name'] !== 'Locked',
      },
    })

    const rowCheckboxes = wrapper.findAll('.data-table tbody [role="checkbox"]')
    const headerCheckbox = wrapper.get('.data-table thead [role="checkbox"]')
    expect(rowCheckboxes).toHaveLength(2)
    const lockedCheckbox = rowCheckboxes[1]
    const eligibleCheckbox = rowCheckboxes[0]
    expect(lockedCheckbox?.attributes('disabled')).toBeDefined()
    expect(eligibleCheckbox).toBeDefined()

    await eligibleCheckbox?.trigger('click')
    const selectionEvents = wrapper.emitted('update:selectedRowKeys') ?? []
    expect(selectionEvents[selectionEvents.length - 1]?.[0]).toEqual([1])

    await headerCheckbox.trigger('click')
    const finalSelectionEvents = wrapper.emitted('update:selectedRowKeys') ?? []
    expect(finalSelectionEvents[finalSelectionEvents.length - 1]?.[0]).toEqual([1])
  })

})
