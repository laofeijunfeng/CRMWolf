import { mount, type VueWrapper } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DataTable from '../DataTable.vue'

const columns = [{ key: 'name', title: '名称' }]
const data = [{ id: 1, name: '审批单' }]
const mountTable = (rowInteractive: boolean): VueWrapper => mount(DataTable, {
  props: {
    columns,
    data,
    total: 1,
    page: 1,
    pageSize: 10,
    rowInteractive
  }
})

describe('DataTable row interaction', () => {
  it('keeps noninteractive rows outside the tab order', () => {
    const row = mountTable(false).get('tbody tr')
    expect(row.attributes('role')).toBeUndefined()
    expect(row.attributes('tabindex')).toBeUndefined()
  })

  it('emits once for click, Enter, and Space on interactive rows', async () => {
    const wrapper = mountTable(true)
    const row = wrapper.get('tbody tr')
    expect(row.attributes('role')).toBe('button')
    expect(row.attributes('tabindex')).toBe('0')

    await row.trigger('click')
    await row.trigger('keydown', { key: 'Enter' })
    const spaceEvent = new KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true })
    row.element.dispatchEvent(spaceEvent)

    expect(spaceEvent.defaultPrevented).toBe(true)
    expect(wrapper.emitted('row-click')).toHaveLength(3)
  })

  it('renders fallback mobile cards from column metadata', () => {
    const wrapper = mount(DataTable, {
      props: {
        columns: [
          { key: 'name', title: '名称' },
          { key: 'status', title: '状态' },
          { key: 'owner', title: '负责人' }
        ],
        data: [{ id: 1, name: '合同 A', status: '审批中', owner: '张三' }],
        total: 1,
        page: 1,
        pageSize: 10,
        mobileTitleKey: 'name',
        mobileStatusKey: 'status',
        mobileMetaKeys: ['owner']
      }
    })

    const card = wrapper.get('.data-table-mobile-card')
    expect(card.text()).toContain('合同 A')
    expect(card.text()).toContain('审批中')
    expect(card.text()).toContain('负责人：张三')
  })

  it('emits row-click from mobile cards but ignores nested controls', async () => {
    const wrapper = mount(DataTable, {
      props: {
        columns,
        data,
        total: 1,
        page: 1,
        pageSize: 10,
        rowInteractive: true
      },
      slots: {
        'mobile-card': '<button type="button" class="nested-action">内部操作</button>'
      }
    })

    await wrapper.get('.data-table-mobile-card').trigger('click')
    await wrapper.get('.nested-action').trigger('click')

    expect(wrapper.emitted('row-click')).toHaveLength(1)
  })
})
