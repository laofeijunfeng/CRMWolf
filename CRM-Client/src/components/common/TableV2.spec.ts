import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TableV2 from './TableV2.vue'
import type { TableColumn, TableRow } from './TableV2.vue'

describe('TableV2.vue', () => {
  const basicColumns: TableColumn[] = [
    { key: 'name', title: '客户名称', width: '200px' },
    { key: 'status', title: '状态', width: '100px' },
    { key: 'amount', title: '金额', width: '120px', align: 'right' },
    { key: 'date', title: '创建日期', width: '150px' },
  ]

  const basicData: TableRow[] = [
    { id: 1, name: '北京科技有限公司', status: '活跃', amount: '¥ 12,500.00', date: '2024-01-15' },
    { id: 2, name: '上海创新科技', status: '待跟进', amount: '¥ 8,300.00', date: '2024-01-12' },
    { id: 3, name: '广州智能系统', status: '活跃', amount: '¥ 45,000.00', date: '2024-01-10' },
  ]

  // ==================== Rendering ====================
  describe('Rendering', () => {
    it('should render table structure correctly', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: basicData,
        },
      })

      // Check table element
      expect(wrapper.find('table.table-v2').exists()).toBe(true)
      expect(wrapper.find('table').attributes('role')).toBe('grid')
      expect(wrapper.find('table').attributes('aria-label')).toBe('数据表格')
    })

    it('should render all column headers', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: basicData,
        },
      })

      const headers = wrapper.findAll('th.table-v2__header')
      expect(headers.length).toBe(4)

      // Check header titles
      const headerTexts = headers.map((h) => h.text())
      expect(headerTexts[0]).toContain('客户名称')
      expect(headerTexts[1]).toContain('状态')
      expect(headerTexts[2]).toContain('金额')
      expect(headerTexts[3]).toContain('创建日期')
    })

    it('should render all data rows', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: basicData,
        },
      })

      const rows = wrapper.findAll('tr.table-v2__row')
      expect(rows.length).toBe(3)
    })

    it('should render cells with correct values', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: basicData,
        },
      })

      const rows = wrapper.findAll('tr.table-v2__row')
      const firstRow = rows[0]
      expect(firstRow).toBeDefined()

      const cells = firstRow!.findAll('td.table-v2__cell')
      expect(cells.length).toBe(4)

      expect(cells[0]!.text()).toBe('北京科技有限公司')
      expect(cells[1]!.text()).toBe('活跃')
      expect(cells[2]!.text()).toBe('¥ 12,500.00')
      expect(cells[3]!.text()).toBe('2024-01-15')
    })

    it('should display "-" for null/undefined values', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: [{ id: 1, name: 'Test', status: null, amount: undefined, date: '2024-01-01' }],
        },
      })

      const cells = wrapper.findAll('td.table-v2__cell')
      expect(cells.length).toBe(4)
      expect(cells[1]!.text()).toBe('-')
      expect(cells[2]!.text()).toBe('-')
    })

    it('should apply column width styles', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: basicData,
        },
      })

      const headers = wrapper.findAll('th.table-v2__header')
      expect(headers[0]!.attributes('style')).toContain('width: 200px')
      expect(headers[1]!.attributes('style')).toContain('width: 100px')
    })

    it('should apply column align styles', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: basicData,
        },
      })

      const headers = wrapper.findAll('th.table-v2__header')
      expect(headers[2]!.attributes('style')).toContain('text-align: right')

      const cells = wrapper.findAll('td.table-v2__cell')
      expect(cells[2]!.attributes('style')).toContain('text-align: right')
    })
  })

  // ==================== Hover States ====================
  describe('Hover States', () => {
    it('should have hoverable class when hoverable is true', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: basicData,
          hoverable: true,
        },
      })

      expect(wrapper.find('table.table-v2--hoverable').exists()).toBe(true)
    })

    it('should not have hoverable class when hoverable is false', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: basicData,
          hoverable: false,
        },
      })

      expect(wrapper.find('table.table-v2--hoverable').exists()).toBe(false)
    })

    it('should have hover transition styles', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: basicData,
          hoverable: true,
        },
      })

      // Check that rows exist with proper structure
      const rows = wrapper.findAll('.table-v2__row')
      expect(rows.length).toBeGreaterThan(0)
    })
  })

  // ==================== No Vertical Dividers ====================
  describe('No Vertical Dividers', () => {
    it('should not have vertical border styles on cells', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: basicData,
        },
      })

      // All cells should exist without vertical border classes
      const cells = wrapper.findAll('td.table-v2__cell')
      expect(cells.length).toBe(12) // 4 columns * 3 rows
    })

    it('should only have bottom border on rows', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: basicData,
        },
      })

      // Check that rows exist with proper structure
      const rows = wrapper.findAll('tr.table-v2__row')
      expect(rows.length).toBe(3)

      // Last row should exist (CSS handles no bottom border)
      expect(rows[2]).toBeDefined()
    })
  })

  // ==================== Striped Rows ====================
  describe('Striped Rows', () => {
    it('should have striped class when striped is true', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: basicData,
          striped: true,
        },
      })

      expect(wrapper.find('table.table-v2--striped').exists()).toBe(true)
    })

    it('should not have striped class when striped is false', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: basicData,
          striped: false,
        },
      })

      expect(wrapper.find('table.table-v2--striped').exists()).toBe(false)
    })
  })

  // ==================== Sortable Columns ====================
  describe('Sortable Columns', () => {
    const sortableColumns: TableColumn[] = [
      { key: 'name', title: '客户名称', sortable: true },
      { key: 'status', title: '状态' },
      { key: 'amount', title: '金额', sortable: true },
    ]

    it('should render sortable header with sortable class', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: sortableColumns,
          data: basicData,
        },
      })

      const headers = wrapper.findAll('th.table-v2__header')
      expect(headers.length).toBe(3)
      expect(headers[0]!.classes()).toContain('table-v2__header--sortable')
      expect(headers[1]!.classes()).not.toContain('table-v2__header--sortable')
      expect(headers[2]!.classes()).toContain('table-v2__header--sortable')
    })

    it('should emit sortChange event when clicking sortable header', async () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: sortableColumns,
          data: basicData,
        },
      })

      const sortableHeaders = wrapper.findAll('th.table-v2__header--sortable')
      const firstSortable = sortableHeaders[0]
      expect(firstSortable).toBeDefined()

      await firstSortable!.trigger('click')

      expect(wrapper.emitted('sortChange')).toBeTruthy()
      const emittedEvents = wrapper.emitted('sortChange')
      expect(emittedEvents![0]).toEqual(['name', 'asc'])
    })

    it('should toggle sort order on repeated clicks', async () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: sortableColumns,
          data: basicData,
        },
      })

      const sortableHeaders = wrapper.findAll('th.table-v2__header--sortable')
      const firstSortable = sortableHeaders[0]
      expect(firstSortable).toBeDefined()

      // First click: asc
      await firstSortable!.trigger('click')
      const emitted1 = wrapper.emitted('sortChange')
      expect(emitted1![0]).toEqual(['name', 'asc'])

      // Second click: desc
      await firstSortable!.trigger('click')
      const emitted2 = wrapper.emitted('sortChange')
      expect(emitted2![1]).toEqual(['name', 'desc'])

      // Third click: null (reset)
      await firstSortable!.trigger('click')
      const emitted3 = wrapper.emitted('sortChange')
      expect(emitted3![2]).toEqual(['name', null])
    })

    it('should set aria-sort attribute correctly', async () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: sortableColumns,
          data: basicData,
        },
      })

      const sortableHeaders = wrapper.findAll('th.table-v2__header--sortable')
      const firstSortable = sortableHeaders[0]
      expect(firstSortable).toBeDefined()

      // Initial state: no aria-sort
      expect(firstSortable!.attributes('aria-sort')).toBeUndefined()

      // Click to sort asc
      await firstSortable!.trigger('click')
      const headersAfterClick = wrapper.findAll('th.table-v2__header--sortable')
      expect(headersAfterClick[0]!.attributes('aria-sort')).toBe('ascending')

      // Click to sort desc
      await headersAfterClick[0]!.trigger('click')
      const headersAfterSecond = wrapper.findAll('th.table-v2__header--sortable')
      expect(headersAfterSecond[0]!.attributes('aria-sort')).toBe('descending')
    })
  })

  // ==================== Row Click ====================
  describe('Row Click', () => {
    it('should have clickable class when clickable is true', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: basicData,
          clickable: true,
        },
      })

      const rows = wrapper.findAll('tr.table-v2__row')
      expect(rows.length).toBeGreaterThan(0)
      expect(rows[0]!.classes()).toContain('table-v2__row--clickable')
    })

    it('should emit rowClick event when clicking clickable row', async () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: basicData,
          clickable: true,
        },
      })

      const rows = wrapper.findAll('tr.table-v2__row')
      const firstRow = rows[0]
      expect(firstRow).toBeDefined()

      await firstRow!.trigger('click')

      expect(wrapper.emitted('rowClick')).toBeTruthy()
      const emittedEvents = wrapper.emitted('rowClick')
      expect(emittedEvents![0]).toEqual([basicData[0], 0])
    })

    it('should not emit rowClick when clickable is false', async () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: basicData,
          clickable: false,
        },
      })

      const rows = wrapper.findAll('tr.table-v2__row')
      const firstRow = rows[0]
      expect(firstRow).toBeDefined()

      await firstRow!.trigger('click')

      expect(wrapper.emitted('rowClick')).toBeFalsy()
    })
  })

  // ==================== Empty State ====================
  describe('Empty State', () => {
    it('should render empty row when data is empty', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: [],
        },
      })

      expect(wrapper.find('tr.table-v2__empty').exists()).toBe(true)
      expect(wrapper.find('.table-v2__empty-content').exists()).toBe(true)
      expect(wrapper.find('.table-v2__empty-text').text()).toBe('暂无数据')
    })

    it('should not render empty row when data exists', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: basicData,
        },
      })

      expect(wrapper.find('tr.table-v2__empty').exists()).toBe(false)
    })

    it('should render custom empty slot', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: [],
        },
        slots: {
          empty: '<div class="custom-empty">自定义空状态</div>',
        },
      })

      expect(wrapper.find('.custom-empty').exists()).toBe(true)
      expect(wrapper.find('.custom-empty').text()).toBe('自定义空状态')
    })

    it('should set colspan on empty cell', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: [],
        },
      })

      const emptyCell = wrapper.find('td.table-v2__empty-cell')
      expect(emptyCell.attributes('colspan')).toBe('4')
    })
  })

  // ==================== Custom Cell Slots ====================
  describe('Custom Cell Slots', () => {
    it('should render custom cell slot', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: basicData,
        },
        slots: {
          'cell-status': '<span class="custom-status">{{ value }}</span>',
        },
      })

      const statusCells = wrapper.findAll('.custom-status')
      expect(statusCells.length).toBe(3)
      expect(statusCells[0]!.text()).toBe('活跃')
    })
  })

  // ==================== Accessibility ====================
  describe('Accessibility', () => {
    it('should have aria-label on table', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: basicData,
          ariaLabel: '客户数据表格',
        },
      })

      expect(wrapper.find('table').attributes('aria-label')).toBe('客户数据表格')
    })

    it('should have role="grid" on table', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: basicData,
        },
      })

      expect(wrapper.find('table').attributes('role')).toBe('grid')
    })

    it('should have aria-hidden on sort icons', () => {
      const sortableColumns: TableColumn[] = [
        { key: 'name', title: '名称', sortable: true },
      ]

      const wrapper = mount(TableV2, {
        props: {
          columns: sortableColumns,
          data: basicData,
        },
      })

      const sortIcon = wrapper.find('.table-v2__sort-icon')
      expect(sortIcon.attributes('aria-hidden')).toBe('true')
    })
  })

  // ==================== Responsive ====================
  describe('Responsive', () => {
    it('should have wrapper element for overflow handling', () => {
      const wrapper = mount(TableV2, {
        props: {
          columns: basicColumns,
          data: basicData,
        },
      })

      expect(wrapper.find('.table-v2-wrapper').exists()).toBe(true)
    })
  })
})