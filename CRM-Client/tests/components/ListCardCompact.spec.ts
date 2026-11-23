import { mount } from '@vue/test-utils'
import { h } from 'vue'
import { describe, expect, it } from 'vitest'

import ListCard from '@/components/crmwolf/ListCard.vue'

interface Row {
  id: string
  name: string
}

describe('ListCard compact density', () => {
  const rows: Row[] = [
    { id: 'a', name: '甲' },
    { id: 'b', name: '乙' },
  ]

  it('drops the header and only makes accepted rows interactive', async () => {
    const wrapper = mount(ListCard, {
      props: { title: '列表', items: rows, density: 'compact', rowInteractive: (row) => row.id === 'a' },
      slots: { itemMain: ({ item }) => h('span', item.id) },
    })

    expect(wrapper.find('.list-card-header').exists()).toBe(false)
    expect(wrapper.attributes('aria-label')).toBe('列表')
    expect(wrapper.findAll('[data-list-card-row-id]').map((row) => row.attributes('role'))).toEqual(['button', undefined])

    await wrapper.get('[data-list-card-row-id="a"]').trigger('click')
    await wrapper.get('[data-list-card-row-id="b"]').trigger('click')
    expect(wrapper.emitted('row-click')).toEqual([[rows[0]]])
    wrapper.unmount()
  })
})
