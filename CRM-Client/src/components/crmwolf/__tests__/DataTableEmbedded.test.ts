import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import DataTable from '../DataTable.vue'
import type { ListFieldDefinition } from '../listFieldCatalog'

const fields: ListFieldDefinition[] = [
  {
    key: 'name',
    label: '名称',
    column: true,
    filter: false,
    filterDisabledReason: '只读嵌入，不提供筛选',
    sort: false,
    sortDisabledReason: '只读嵌入，不提供排序',
  },
  { key: 'amount', label: '金额', role: 'decoration', column: { align: 'right' } },
]

describe('DataTable read-only embedding', () => {
  it('renders only the table: no pagination, state summary, tools or mobile cards', () => {
    const wrapper = mount(DataTable, {
      props: { fields, data: [{ name: '甲', amount: '1' }], total: 1, page: 1, pageSize: 1, embedded: true },
    })

    expect(wrapper.find('table').exists()).toBe(true)
    expect(wrapper.find('.data-table-footer').exists()).toBe(false)
    expect(wrapper.find('.list-view-state-summary').exists()).toBe(false)
    expect(wrapper.find('.data-table-tools').exists()).toBe(false)
    expect(wrapper.find('.data-table-card').classes()).toContain('data-table-card--embedded')
    expect(wrapper.find('.data-table-card').classes()).not.toContain('has-mobile-cards')
    wrapper.unmount()
  })

  it('keeps pagination and the state summary for list pages', () => {
    const wrapper = mount(DataTable, {
      props: { fields, data: [{ name: '甲', amount: '1' }], total: 1, page: 1, pageSize: 1 },
    })

    expect(wrapper.find('.data-table-footer').exists()).toBe(true)
    expect(wrapper.find('.list-view-state-summary').exists()).toBe(true)
    wrapper.unmount()
  })
})
