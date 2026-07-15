import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import FilterPanel from '../FilterPanel.vue'

const fields = [
  { key: 'keyword', type: 'text' as const, label: '搜索' },
  {
    key: 'status',
    type: 'select' as const,
    label: '状态',
    options: [{ value: 'PENDING', label: '待处理' }]
  }
]

describe('FilterPanel controlled values', () => {
  it('fills missing fields and removes deleted external keys from emitted search payload', async () => {
    const wrapper = mount(FilterPanel, {
      props: {
        fields,
        values: { keyword: '客户', external_filter: 2 }
      }
    })

    await wrapper.setProps({ values: { status: 'PENDING' } })
    await wrapper.get('form').trigger('submit')

    const searchEvents = wrapper.emitted('search')
    expect(searchEvents).toBeDefined()
    expect(searchEvents?.[searchEvents.length - 1]?.[0]).toEqual({
      keyword: '',
      status: 'PENDING'
    })
  })

  it('resets current controlled extras and fields without emitting stale values', async () => {
    const wrapper = mount(FilterPanel, {
      props: {
        fields,
        values: { keyword: '客户', external_filter: 2 }
      }
    })

    await wrapper.get('[aria-label="清除筛选条件"]').trigger('click')

    const updateEvents = wrapper.emitted('update:values')
    expect(updateEvents).toBeDefined()
    expect(updateEvents?.[updateEvents.length - 1]?.[0]).toEqual({
      keyword: '',
      status: '',
      external_filter: ''
    })
    expect(updateEvents).toHaveLength(1)
  })
})
