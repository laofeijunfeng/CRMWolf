import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
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

const rowActionHandlers = {
  edit: vi.fn(),
  remove: vi.fn()
}

const attachedWrappers: VueWrapper[] = []

const mountActionTable = (
  overrides: Record<string, unknown> = {},
  slots: Record<string, string> = {}
): VueWrapper => {
  const wrapper = mount(DataTable, {
    attachTo: document.body,
    props: {
      fields,
      data,
      total: 1,
      page: 1,
      pageSize: 10,
      rowInteractive: true,
      getRowActions: () => ({
        primaryActions: [{ label: '编辑', handler: rowActionHandlers.edit, visible: true }],
        secondaryActions: [{ label: '删除', handler: rowActionHandlers.remove, destructive: true, visible: true }]
      }),
      ...overrides
    },
    slots
  })
  attachedWrappers.push(wrapper)
  return wrapper
}

async function openRowMenu(wrapper: VueWrapper, eventInit: MouseEventInit = {}): Promise<void> {
  const row = wrapper.get('tbody tr')
  const event = new MouseEvent('contextmenu', {
    clientX: 48,
    clientY: 64,
    button: 2,
    bubbles: true,
    cancelable: true,
    ...eventInit
  })
  row.element.dispatchEvent(event)
  await flushPromises()
  await wrapper.vm.$nextTick()
  await flushPromises()
}

function menuEl(): HTMLElement | null {
  return document.querySelector('.data-table-row-menu')
}

describe('DataTable row context menu', () => {
  afterEach(() => {
    while (attachedWrappers.length > 0) {
      attachedWrappers.pop()?.unmount()
    }
    rowActionHandlers.edit.mockReset()
    rowActionHandlers.remove.mockReset()
  })

  it('does not render an actions column by default', () => {
    const wrapper = mountTable(true)
    expect(wrapper.findAll('th').map((header) => header.text())).toEqual(['名称'])
    expect(wrapper.html()).not.toContain('操作')
  })

  it('opens the row menu with visible actions on contextmenu', async () => {
    const wrapper = mountActionTable()
    await openRowMenu(wrapper)
    const menu = menuEl()
    expect(menu).not.toBeNull()
    expect(menu?.textContent).toContain('编辑')
    expect(menu?.textContent).toContain('删除')
    expect(menu?.textContent).toContain('常用')
    expect(menu?.textContent).toContain('危险')
  })

  it('does not open the menu on left click', async () => {
    const wrapper = mountActionTable()
    await wrapper.get('tbody tr').trigger('click')
    expect(menuEl()).toBeNull()
    expect(wrapper.emitted('row-click')).toHaveLength(1)
  })

  it('does not emit row-click after opening or dismissing the context menu', async () => {
    const wrapper = mountActionTable()
    await openRowMenu(wrapper)
    await wrapper.get('tbody tr').trigger('click')
    expect(wrapper.emitted('row-click')).toBeUndefined()
  })

  it('does not render row action buttons or overflow triggers', async () => {
    const wrapper = mountActionTable()
    await wrapper.get('tbody tr').trigger('mouseenter')
    expect(wrapper.find('tbody button').exists()).toBe(false)
    expect(wrapper.find('[aria-label="更多操作"]').exists()).toBe(false)
  })

  it('opens the same menu from Shift+F10', async () => {
    const wrapper = mountActionTable()
    const row = wrapper.get('tbody tr')
    const event = new KeyboardEvent('keydown', {
      key: 'F10',
      shiftKey: true,
      bubbles: true,
      cancelable: true
    })
    row.element.dispatchEvent(event)
    await flushPromises()
    await wrapper.vm.$nextTick()
    expect(menuEl()?.textContent).toContain('编辑')
  })

  it('does not open an empty menu', async () => {
    const wrapper = mountActionTable({
      getRowActions: () => ({
        primaryActions: [{ label: '领取', handler: vi.fn(), visible: false }],
        secondaryActions: []
      })
    })
    const row = wrapper.get('tbody tr')
    const event = new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 20, clientY: 20 })
    row.element.dispatchEvent(event)
    await flushPromises()
    expect(event.defaultPrevented).toBe(false)
    expect(menuEl()).toBeNull()
  })

  it('does not preventDefault Shift+F10 when there are no visible actions', async () => {
    const wrapper = mountActionTable({
      getRowActions: () => ({
        primaryActions: [{ label: '领取', handler: vi.fn(), visible: false }],
        secondaryActions: []
      })
    })
    const row = wrapper.get('tbody tr')
    const event = new KeyboardEvent('keydown', {
      key: 'F10',
      shiftKey: true,
      bubbles: true,
      cancelable: true
    })
    row.element.dispatchEvent(event)
    await flushPromises()
    expect(event.defaultPrevented).toBe(false)
    expect(menuEl()).toBeNull()
  })

  it('keeps native context menu on links and inputs', async () => {
    const wrapper = mountActionTable(
      {
        getRowActions: () => ({
          primaryActions: [{ label: '编辑', handler: rowActionHandlers.edit }],
          secondaryActions: []
        })
      },
      {
        'cell-name': '<a href="https://example.com/detail" class="name-link">审批单</a>'
      }
    )
    const link = wrapper.get('.name-link')
    const event = new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 20, clientY: 20 })
    link.element.dispatchEvent(event)
    await flushPromises()
    expect(event.defaultPrevented).toBe(false)
    expect(menuEl()).toBeNull()
  })

  it('does not pin the last column to the right by default', () => {
    const wrapper = mount(DataTable, {
      props: {
        fields: [
          { key: 'name', label: '名称', column: { width: '160px' } },
          { key: 'created_time', label: '创建时间', column: { width: '160px' } }
        ] satisfies ListFieldDefinition[],
        data: [{ id: 1, name: '审批单', created_time: '2026-08-19' }],
        total: 1,
        page: 1,
        pageSize: 10
      }
    })
    const headers = wrapper.findAll('th')
    expect(headers[0]?.classes()).toContain('fixed-left')
    expect(headers[1]?.classes()).not.toContain('fixed-right')
    expect(headers[1]?.attributes('style') ?? '').not.toContain('position: sticky')
  })

  it('invokes the original action handler from a destructive menu item', async () => {
    const wrapper = mountActionTable()
    await openRowMenu(wrapper)
    const deleteItem = Array.from(document.querySelectorAll('.data-table-row-menu [role="menuitem"]'))
      .find((item) => item.textContent?.includes('删除') === true)
    expect(deleteItem).toBeDefined()
    deleteItem?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushPromises()
    expect(rowActionHandlers.remove).toHaveBeenCalledTimes(1)
    expect(rowActionHandlers.edit).not.toHaveBeenCalled()
  })
})
