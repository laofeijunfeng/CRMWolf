import { mount, type VueWrapper } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import DataTable from '../DataTable.vue'
import SelectField from '../SelectField.vue'
import type { ListFieldDefinition } from '../listFieldCatalog'

const fields: ListFieldDefinition[] = [{ key: 'name', label: '名称', column: true }]
const data = [{ id: 1, name: '审批单' }]
const readView = (name: string): string => readFileSync(
  resolve(process.cwd(), `src/views/${name}.vue`),
  'utf8'
)
const mountTable = (rowInteractive: boolean): VueWrapper => mount(DataTable, {
  props: {
    fields,
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
        fields: [
          { key: 'name', label: '名称', column: true },
          { key: 'status', label: '状态', column: true },
          { key: 'owner', label: '负责人', column: true }
        ] satisfies ListFieldDefinition[],
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
        fields,
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

  it('emits kebab-case page size updates and resets to the first page', async () => {
    const wrapper = mount(DataTable, {
      props: {
        fields,
        data,
        total: 200,
        page: 3,
        pageSize: 20
      }
    })

    const select = wrapper.getComponent(SelectField)
    const selectVm = select.vm as unknown as { $emit: (event: string, value: string) => void }
    selectVm.$emit('update:modelValue', '100')
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('update:page-size')).toEqual([[100]])
    expect(wrapper.emitted('update:page')).toEqual([[1]])
    expect(wrapper.emitted('update:pageSize')).toBeUndefined()
  })

  it('keeps standard list pages aligned with the sidebar layout vertical inset', () => {
    const listViews = [
      'ApprovalCenter',
      'Contracts',
      'Customers',
      'Invoices',
      'Leads',
      'Opportunities',
      'PaymentPlans',
      'PaymentRecords'
    ]

    for (const viewName of listViews) {
      const source = readView(viewName)
      const expectedHeight = viewName === 'ApprovalCenter'
        ? 'height="calc(100vh - 108px)"'
        : 'height="calc(100vh - 121px)"'
      expect(source).toContain(expectedHeight)
      expect(source).not.toContain('height="calc(100vh - 104px)"')
      expect(source).not.toContain('height="calc(100vh - 120px)"')
      expect(source).not.toContain('height="calc(100vh - 136px)"')
    }
  })
})
