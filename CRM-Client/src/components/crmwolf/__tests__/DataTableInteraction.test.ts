import { ref } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useCustomFilterViews } from '@/composables/useCustomFilterViews'
import { normalizeCustomerDisplayMode, viewPreferenceApi, type ViewDisplayMode, type ViewPreferenceConfig, type ViewPreferenceItem } from '@/api/viewPreference'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import DataTable from '../DataTable.vue'
import SelectField from '../SelectField.vue'
import type { ListFieldDefinition } from '../listFieldCatalog'
import type { ListFilterCondition } from '../listFilterTypes'
import type { ListSortCondition } from '../listSortTypes'

const fields: ListFieldDefinition[] = [{ key: 'name', label: '名称', type: 'text', column: true }]
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

  it('keeps native row semantics and exposes one named detail control', async () => {
    const wrapper = mountTable(true)
    const row = wrapper.get('tbody tr')
    const detailTrigger = wrapper.get('.data-table-row-detail-trigger')

    expect(row.attributes('role')).toBeUndefined()
    expect(row.attributes('tabindex')).toBeUndefined()
    expect(detailTrigger.attributes('type')).toBe('button')
    expect(detailTrigger.attributes('aria-label')).toBe('查看审批单详情')

    await row.trigger('click')
    await detailTrigger.trigger('click')
    await row.trigger('keydown', { key: 'Enter' })
    await row.trigger('keydown', { key: ' ' })

    expect(wrapper.emitted('row-click')).toHaveLength(2)
  })

  it('renders fallback mobile cards from column metadata', () => {
    const wrapper = mount(DataTable, {
      props: {
        fields: [
          { key: 'name', label: '名称', type: 'text', column: true },
          { key: 'status', label: '状态', type: 'text', column: true },
          { key: 'owner', label: '负责人', type: 'text', column: true }
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
  it('marks the first visible data column as the primary text column', () => {
    const wrapper = mount(DataTable, {
      props: {
        fields: [
          { key: 'name', label: '名称', type: 'text', column: true },
          { key: 'status', label: '状态', type: 'text', column: true }
        ] satisfies ListFieldDefinition[],
        data: [{ id: 1, name: '合同 A', status: '审批中' }],
        total: 1,
        page: 1,
        pageSize: 10
      }
    })

    const cells = wrapper.findAll('tbody tr.data-table-row > td.data-table-cell')
    expect(cells[0]?.classes()).toContain('data-table-cell--primary')
    expect(cells[1]?.classes()).not.toContain('data-table-cell--primary')
  })

  it('ignores the selection cell and hidden columns when finding the primary column', () => {
    const wrapper = mount(DataTable, {
      props: {
        fields: [
          { key: 'hidden', label: '隐藏', type: 'text', column: { visible: false } },
          { key: 'name', label: '名称', type: 'text', column: true },
          { key: 'status', label: '状态', type: 'text', column: true }
        ] satisfies ListFieldDefinition[],
        data: [{ id: 1, hidden: '内部', name: '合同 A', status: '审批中' }],
        total: 1,
        page: 1,
        pageSize: 10,
        selectable: true
      }
    })

    expect(wrapper.get('tbody tr > td.data-table-selection-cell').classes()).not.toContain('data-table-cell--primary')
    const cells = wrapper.findAll('tbody tr.data-table-row > td.data-table-cell:not(.data-table-selection-cell)')
    expect(cells[0]?.text()).toBe('合同 A')
    expect(cells[0]?.classes()).toContain('data-table-cell--primary')
    expect(cells[1]?.classes()).not.toContain('data-table-cell--primary')
  })
  it('marks the first column after custom preference reordering as primary', () => {
    const wrapper = mount(DataTable, {
      props: {
        fields: [
          { key: 'name', label: '名称', type: 'text', column: true },
          { key: 'status', label: '状态', type: 'text', column: true },
          { key: 'owner', label: '负责人', type: 'text', column: true }
        ] satisfies ListFieldDefinition[],
        data: [{ id: 1, name: '合同 A', status: '审批中', owner: '张三' }],
        total: 1,
        page: 1,
        pageSize: 10,
        fixedLeftCount: 0,
        columnPreferenceMode: 'custom',
        columnPreferenceConfig: {
          version: 1,
          columns: [
            { key: 'name', order: 20, visible: true },
            { key: 'status', order: 0, visible: true },
            { key: 'owner', order: 10, visible: true }
          ]
        }
      }
    })

    const cells = wrapper.findAll('tbody tr.data-table-row > td.data-table-cell')
    expect(cells.map((cell) => cell.text())).toEqual(['审批中', '张三', '合同 A'])
    expect(cells[0]?.classes()).toContain('data-table-cell--primary')
    expect(cells[1]?.classes()).not.toContain('data-table-cell--primary')
    expect(cells[2]?.classes()).not.toContain('data-table-cell--primary')
  })
  it('skips all non-business role columns when finding the primary column', () => {
    const wrapper = mount(DataTable, {
      props: {
        fields: [
          { key: 'keyword', label: '关键字', role: 'keyword', column: true },
          { key: 'badge', label: '标记', role: 'decoration', column: true },
          { key: 'actions', label: '操作', role: 'action', column: true },
          { key: 'name', label: '名称', type: 'text', column: true }
        ] satisfies ListFieldDefinition[],
        data: [{ id: 1, keyword: '重点', badge: '高价值', actions: '查看', name: '合同 A' }],
        total: 1,
        page: 1,
        pageSize: 10
      }
    })

    const cells = wrapper.findAll('tbody tr.data-table-row > td.data-table-cell')
    expect(cells.map((cell) => cell.text())).toEqual(['重点', '高价值', '查看', '合同 A'])
    expect(cells[0]?.classes()).not.toContain('data-table-cell--primary')
    expect(cells[1]?.classes()).not.toContain('data-table-cell--primary')
    expect(cells[2]?.classes()).not.toContain('data-table-cell--primary')
    expect(cells[3]?.classes()).toContain('data-table-cell--primary')
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

    const card = wrapper.get('.data-table-mobile-card')
    expect(card.attributes('role')).toBeUndefined()
    expect(card.attributes('tabindex')).toBeUndefined()
    expect(wrapper.get('.data-table-mobile-detail-trigger').attributes('aria-label')).toBe('查看审批单详情')

    await card.trigger('click')
    await wrapper.get('.nested-action').trigger('click')
    await wrapper.get('.data-table-mobile-detail-trigger').trigger('click')

    expect(wrapper.emitted('row-click')).toHaveLength(2)
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
    const fixedHeightViews = [
      'Contracts',
      'Customers',
      'CustomerTracking',
      'Invoices',
      'Leads',
      'Opportunities',
      'PaymentPlans',
      'PaymentRecords'
    ]

    for (const viewName of fixedHeightViews) {
      const source = readView(viewName)
      const expectedHeight = 'height="calc(100vh - 121px)"'
      expect(source).toContain(expectedHeight)
    }

    const approvalSource = readView('ApprovalCenter')
    expect(approvalSource).toContain('height="calc(100vh - 108px)"')

    for (const viewName of [...fixedHeightViews, 'ApprovalCenter']) {
      const source = readView(viewName)
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

  it('does not open row detail when clicking the edit action among multiple primary actions', async () => {
    const wrapper = mountActionTable({
      getRowActions: () => ({
        primaryActions: [
          { label: '新建商机', handler: rowActionHandlers.edit, desktopPrimary: true },
          { label: '编辑', handler: rowActionHandlers.edit, desktopPrimary: true }
        ],
        secondaryActions: []
      })
    })

    await wrapper.get('.desktop-table-row-action:nth-of-type(2)').trigger('click')

    expect(rowActionHandlers.edit).toHaveBeenCalledTimes(1)
    expect(rowActionHandlers.edit).toHaveBeenCalledWith(data[0])
    expect(wrapper.emitted('row-click')).toBeUndefined()
  })

  it('renders a discoverable desktop primary action and more menu', async () => {
    const wrapper = mountActionTable()
    expect(wrapper.get('th.data-table-actions-header').text()).toBe('操作')
    expect(wrapper.get('.data-table-actions-cell').text()).toContain('编辑')
    expect(wrapper.get('[aria-label="更多操作"]').attributes('title')).toBe('更多操作')
    expect(wrapper.get('.data-table-actions-cell').findAll('button')).toHaveLength(2)

    await wrapper.get('.data-table-actions-cell button').trigger('click')
    expect(rowActionHandlers.edit).toHaveBeenCalledWith(data[0])
    expect(wrapper.emitted('row-click')).toBeUndefined()
  })

  it('does not reserve an actions column when every row action is hidden', () => {
    const wrapper = mountActionTable({
      getRowActions: () => ({
        primaryActions: [{ label: '编辑', handler: rowActionHandlers.edit, visible: false }],
        secondaryActions: []
      })
    })

    expect(wrapper.find('th.data-table-actions-header').exists()).toBe(false)
    expect(wrapper.find('.data-table-actions-cell').exists()).toBe(false)
  })

  it('keeps a third primary action in the more menu', async () => {
    const wrapper = mountActionTable({
      getRowActions: () => ({
        primaryActions: [
          { label: '编辑', handler: rowActionHandlers.edit, desktopPrimary: true },
          { label: '推进', handler: rowActionHandlers.edit, desktopPrimary: true },
          { label: '转交', handler: rowActionHandlers.edit, desktopPrimary: true }
        ],
        secondaryActions: []
      })
    })

    expect(wrapper.get('.data-table-actions-cell').text()).toContain('编辑')
    expect(wrapper.get('.data-table-actions-cell').text()).toContain('推进')
    expect(wrapper.get('.data-table-actions-cell').text()).not.toContain('转交')

    await wrapper.get('[aria-label="更多操作"]').trigger('click')
    await flushPromises()
    expect(document.querySelector('.desktop-table-row-menu')?.textContent).toContain('转交')
  })

  it('opens the same menu from Shift+F10 on the named detail control', async () => {
    const wrapper = mountActionTable()
    const detailTrigger = wrapper.get('.data-table-row-detail-trigger')
    const event = new KeyboardEvent('keydown', {
      key: 'F10',
      shiftKey: true,
      bubbles: true,
      cancelable: true
    })
    detailTrigger.element.dispatchEvent(event)
    await flushPromises()
    await wrapper.vm.$nextTick()
    expect(event.defaultPrevented).toBe(true)
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
    const detailTrigger = wrapper.get('.data-table-row-detail-trigger')
    const event = new KeyboardEvent('keydown', {
      key: 'F10',
      shiftKey: true,
      bubbles: true,
      cancelable: true
    })
    detailTrigger.element.dispatchEvent(event)
    await flushPromises()
    expect(event.defaultPrevented).toBe(false)
    expect(menuEl()).toBeNull()
  })

  it('opens the row menu from a link-text identifier cell', async () => {
    const wrapper = mountActionTable(
      {},
      {
        'cell-name': '<span class="link-text">审批单</span>'
      }
    )
    const target = wrapper.get('.link-text')
    const event = new MouseEvent('contextmenu', {
      bubbles: true,
      cancelable: true,
      button: 2,
      clientX: 20,
      clientY: 20
    })
    target.element.dispatchEvent(event)
    await flushPromises()
    await wrapper.vm.$nextTick()
    await flushPromises()
    expect(event.defaultPrevented).toBe(true)
    expect(menuEl()?.textContent).toContain('编辑')
  })

  it('keeps native context menu on a real identifier button', async () => {
    const wrapper = mountActionTable(
      {},
      {
        'cell-name': '<button type="button" class="number-cell-link">PLAN-1</button>'
      }
    )
    const target = wrapper.get('.number-cell-link')
    const event = new MouseEvent('contextmenu', {
      bubbles: true,
      cancelable: true,
      button: 2,
      clientX: 20,
      clientY: 20
    })
    target.element.dispatchEvent(event)
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
          { key: 'name', label: '名称', type: 'text', column: { width: '160px' } },
          { key: 'created_time', label: '创建时间', type: 'date', column: { width: '160px' } }
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

  it('keeps business fixed-right columns behind the desktop actions column', () => {
    const wrapper = mount(DataTable, {
      props: {
        fields: [
          { key: 'name', label: '名称', type: 'text', column: { width: '160px' } },
          { key: 'status', label: '状态', type: 'text', column: { width: '120px', fixed: 'right' } }
        ] satisfies ListFieldDefinition[],
        data: [{ id: 1, name: '审批单', status: '审批中' }],
        total: 1,
        page: 1,
        pageSize: 10,
        getRowActions: () => ({
          primaryActions: [{ label: '编辑', handler: rowActionHandlers.edit }],
          secondaryActions: []
        })
      }
    })

    const statusHeader = wrapper.findAll('th').find((header) => header.text() === '状态')
    expect(statusHeader?.attributes('style') ?? '').toContain('right: calc(var(--data-table-actions-width, 0px))')
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

const preferenceColumns = [
  { key: 'name', order: 0, visible: true },
  { key: 'status', order: 10, visible: false },
]

function preferenceItem(displayMode: ViewDisplayMode | null): ViewPreferenceItem {
  return {
    id: 7,
    team_id: 1,
    user_id: 2,
    view_key: 'customers.list',
    scope: 'personal',
    preference_key: 'custom',
    name: '重点客户',
    is_default: false,
    sort_order: null,
    config: {
      version: 1,
      columns: preferenceColumns,
      filters: [{ field: 'account_name', op: 'contains', value: '重点' }],
      sorts: [{ field: 'updated_time', direction: 'desc' }],
      ...(displayMode === null ? {} : { display_mode: displayMode }),
    },
    created_by: 2,
    updated_by: 2,
    created_time: '2026-10-14T00:00:00Z',
    updated_time: '2026-10-14T00:00:00Z',
  }
}

describe('DataTable display mode selector', () => {
  afterEach(() => {
    document.body.innerHTML = ''
    vi.restoreAllMocks()
  })

  async function openModeSelector(mode: ViewDisplayMode | null = 'table'): Promise<VueWrapper> {
    const wrapper = mount(DataTable, {
      attachTo: document.body,
      props: {
        fields,
        data,
        total: 40,
        page: 3,
        pageSize: 10,
        viewKey: 'customers.list',
        columnConfigEnabled: true,
        viewDisplayModeEnabled: true,
        viewDisplayMode: mode,
      },
    })
    await flushPromises()
    const trigger = Array.from(document.body.querySelectorAll('button')).find((button) => (
      button.textContent?.includes('字段配置') === true
    ))
    trigger?.click()
    await flushPromises()
    return wrapper
  }

  it('renders list and board labels and emits only those modes', async () => {
    const wrapper = await openModeSelector('table')

    expect(document.body.textContent).toContain('列表')
    expect(document.body.textContent).toContain('看板')
    expect(document.body.querySelector('[role="switch"]')).toBeNull()

    const board = Array.from(document.body.querySelectorAll('button')).find((item) => (
      item.textContent?.trim() === '看板'
    ))
    board?.click()
    await flushPromises()

    expect(wrapper.emitted('update:view-display-mode')).toEqual([['board']])
    expect(wrapper.emitted('update:view-display-mode')?.flat()).not.toContain('chart')
    wrapper.unmount()
  })

  it('rejects a chart value in the selector', async () => {
    const wrapper = await openModeSelector('chart')
    const options = ['列表', '看板'].map((label) => (
      Array.from(document.body.querySelectorAll('button')).find((item) => item.textContent?.trim() === label)
    ))
    const selected = options.filter((item) => (
      item?.getAttribute('data-state') === 'on' || item?.getAttribute('aria-pressed') === 'true'
    ))

    expect(options.every((item) => item instanceof HTMLButtonElement)).toBe(true)
    expect(selected).toEqual([])
    expect(wrapper.emitted('update:view-display-mode')).toBeUndefined()
    wrapper.unmount()
  })

  it('hides list-only controls and pagination in board mode without clearing page state', async () => {
    const wrapper = mount(DataTable, {
      props: {
        fields,
        data,
        total: 40,
        page: 3,
        pageSize: 10,
        viewDisplayMode: 'board',
        viewDisplayModeEnabled: true,
        searchEnabled: true,
        search: '重点',
        filterFields: [{ key: 'name', label: '名称', type: 'text' }],
        filters: [{ field: 'name', op: 'contains', value: '重点' }],
        sorts: [{ field: 'name', direction: 'asc' }],
      },
    })

    expect(wrapper.find('.data-table-footer').exists()).toBe(false)
    expect(wrapper.find('table.data-table').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('共 40 条')
    expect(wrapper.props('page')).toBe(3)
    expect(wrapper.props('filters')).toEqual([{ field: 'name', op: 'contains', value: '重点' }])
    expect(wrapper.props('sorts')).toEqual([{ field: 'name', direction: 'asc' }])
    expect(wrapper.emitted('update:page')).toBeUndefined()
    expect(wrapper.emitted('filter-reset')).toBeUndefined()
    expect(wrapper.emitted('sort-reset')).toBeUndefined()
  })

  it('stores display mode with columns and restores both with pagination', async () => {
    const stored: ViewPreferenceConfig = {
      version: 1,
      columns: preferenceColumns,
      display_mode: 'board',
    }
    vi.spyOn(viewPreferenceApi, 'get').mockResolvedValue({
      view_key: 'customers.list',
      personal: null,
      team: null,
      effective_scope: 'personal',
      effective_config: stored,
    })
    const save = vi.spyOn(viewPreferenceApi, 'save').mockImplementation(async (_viewKey, request) => ({
      view_key: 'customers.list',
      personal: null,
      team: null,
      effective_scope: request.scope,
      effective_config: request.config,
    }))

    const wrapper = mount(DataTable, {
      attachTo: document.body,
      props: {
        fields: [
          { key: 'name', label: '名称', type: 'text', column: true },
          { key: 'status', label: '状态', type: 'text', column: true },
        ] satisfies ListFieldDefinition[],
        data: [{ id: 1, name: '客户 A', status: '跟进中' }],
        total: 40,
        page: 3,
        pageSize: 10,
        viewKey: 'customers.list',
        columnConfigEnabled: true,
        fixedLeftCount: 0,
        viewDisplayMode: 'table',
        viewDisplayModeEnabled: true,
      },
    })
    await flushPromises()
    expect(wrapper.findAll('th').map((header) => header.text())).toEqual(['名称'])

    await wrapper.setProps({ viewDisplayMode: 'board' })
    expect(wrapper.find('.data-table-footer').exists()).toBe(false)
    expect(wrapper.props('page')).toBe(3)

    const trigger = Array.from(document.body.querySelectorAll('button')).find((button) => (
      button.textContent?.includes('字段配置') === true
    ))
    trigger?.click()
    await flushPromises()
    Array.from(document.body.querySelectorAll('button')).find((button) => (
      button.textContent?.replace(/\s+/g, '') === '保存'
    ))?.click()
    await flushPromises()

    expect(JSON.stringify(save.mock.calls[0]?.[1]?.config)).toBe(JSON.stringify({
      version: 1,
      columns: preferenceColumns,
      display_mode: 'board',
    }))

    await wrapper.setProps({ viewDisplayMode: 'table' })
    expect(wrapper.findAll('th').map((header) => header.text())).toEqual(['名称'])
    expect(wrapper.find('.data-table-footer').text()).toContain('共 40 条')
    expect(wrapper.props('page')).toBe(3)
    wrapper.unmount()
  })
})

describe('customer display mode normalization and saved-view rollback', () => {
  it('normalizes only customer chart preferences to board', () => {
    expect(normalizeCustomerDisplayMode('chart')).toBe('board')
    expect(normalizeCustomerDisplayMode('board')).toBe('board')
    expect(normalizeCustomerDisplayMode('table')).toBe('table')
    expect(normalizeCustomerDisplayMode(null)).toBe('table')
    expect(normalizeCustomerDisplayMode(undefined)).toBe('table')
  })

  it('keeps a non-customer stored chart value unchanged', () => {
    const parsed = viewPreferenceApi.parseConfig({
      version: 1,
      columns: [],
      display_mode: 'chart',
    })

    expect(parsed.display_mode).toBe('chart')
    expect(normalizeCustomerDisplayMode('chart')).toBe('board')
  })

  it('saves normalized board after a successful customer view apply and rolls back synchronously', async () => {
    const activeTab = ref('all')
    const activeFilters = ref<ListFilterCondition[]>([{ field: 'status', op: 'eq', value: 'following' }])
    const activeSorts = ref<ListSortCondition[]>([{ field: 'updated_time', direction: 'desc' }])
    const activeColumns = ref([{ key: 'name', order: 0, visible: true }])
    const displayMode = ref<'table' | 'board'>('table')
    let resolveRefresh: ((value: boolean) => void) | undefined
    const refresh = vi.fn(() => new Promise<boolean>((resolve) => {
      resolveRefresh = resolve
    }))
    const update = vi.spyOn(viewPreferenceApi, 'updateCustomView').mockResolvedValue(
      preferenceItem('board'),
    )
    const views = useCustomFilterViews({
      viewKey: 'customers.list',
      activeTab,
      activeFilters,
      activeSorts,
      activeColumns,
      activeDisplayMode: displayMode,
      normalizeDisplayMode: normalizeCustomerDisplayMode,
      refresh,
    })
    views.customViews.value = [preferenceItem('chart')]

    expect(views.applyCustomViewTab('custom-view:7')).toBe(true)
    expect(activeTab.value).toBe('custom-view:7')
    expect(displayMode.value).toBe('board')
    expect(update).not.toHaveBeenCalled()
    expect(refresh).toHaveBeenCalledTimes(1)

    const resolveApply = resolveRefresh
    if (resolveApply === undefined) throw new Error('refresh was not started')
    resolveApply(false)
    await Promise.resolve()

    expect(activeTab.value).toBe('all')
    expect(activeFilters.value).toEqual([{ field: 'status', op: 'eq', value: 'following' }])
    expect(activeSorts.value).toEqual([{ field: 'updated_time', direction: 'desc' }])
    expect(activeColumns.value).toEqual([{ key: 'name', order: 0, visible: true }])
    expect(displayMode.value).toBe('table')
    expect(views.applyError.value).toMatchObject({ retryable: true })

    resolveRefresh = undefined
    const retryPromise = views.retryViewApply()
    await Promise.resolve()
    const resolveRetry = resolveRefresh as ((value: boolean) => void) | undefined
    if (resolveRetry === undefined) throw new Error('retry was not started')
    resolveRetry(true)
    await retryPromise
    expect(displayMode.value).toBe('board')
    expect(update).toHaveBeenCalledWith('customers.list', 7, {
      config: expect.objectContaining({ display_mode: 'board' }) as unknown,
    })
  })
})
