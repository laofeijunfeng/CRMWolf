import { describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import ListCard from '@/components/crmwolf/ListCard.vue'

interface TestItem {
  id: number
  name: string
}

const items: TestItem[] = [
  { id: 88, name: 'CRM 升级项目' },
]

const RowAction = defineComponent({
  name: 'RowAction',
  setup: () => () => h('button', { type: 'button', 'data-testid': 'row-action' }, '打开完整详情')
})

describe('ListCard interactive rows', () => {
  it('marks and exposes the highlighted row for focus restoration', () => {
    const wrapper = mount(ListCard<TestItem>, {
      props: {
        title: '商机',
        items,
        rowInteractive: true,
        highlightedItemId: 88,
      },
      slots: {
        itemMain: ({ item }: { item: TestItem }) => item.name,
      },
    })

    const row = wrapper.get('[data-list-card-row-id="88"]')
    expect(row.attributes('data-highlighted')).toBe('true')
    expect(row.classes()).toContain('is-highlighted')
  })

  it('prevents nested action clicks from also triggering row-click', async () => {
    const wrapper = mount(ListCard<TestItem>, {
      props: {
        title: '商机',
        items,
        rowInteractive: true,
      },
      slots: {
        itemMain: ({ item }: { item: TestItem }) => item.name,
        itemActions: () => h(RowAction),
      },
    })

    await wrapper.get('[data-testid="row-action"]').trigger('click')

    expect(wrapper.emitted('row-click')).toBeUndefined()
  })
})
