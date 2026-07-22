import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ListCard from '../ListCard.vue'

const items = [{ id: 1, name: '测试商机' }]

describe('ListCard row interaction', () => {
  it('emits row-click when clicking plain content inside an interactive row', async () => {
    const wrapper = mount(ListCard, {
      props: {
        title: '商机',
        items,
        rowInteractive: true
      },
      slots: {
        itemMain: '<span class="item-title">{{ params.item.name }}</span>'
      }
    })

    await wrapper.get('.item-title').trigger('click')

    expect(wrapper.emitted('row-click')).toEqual([[items[0]]])
  })

  it('ignores clicks from nested interactive controls', async () => {
    const wrapper = mount(ListCard, {
      props: {
        title: '商机',
        items,
        rowInteractive: true
      },
      slots: {
        itemActions: '<button type="button" class="nested-action">操作</button>'
      }
    })

    await wrapper.get('.nested-action').trigger('click')

    expect(wrapper.emitted('row-click')).toBeUndefined()
  })
})
