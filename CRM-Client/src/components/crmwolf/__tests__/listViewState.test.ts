import { describe, expect, it } from 'vitest'
import type { ColumnConfigOption } from '../columnConfigTypes'
import {
  buildFilterSummaryItems,
  buildSortSummaryItems,
  countHiddenColumns,
  formatFilterValue,
} from '../listViewState'
import type { ListFilterField } from '../listFilterTypes'
import type { ListSortField } from '../listSortTypes'

describe('list view state summaries', () => {
  const filterFields: ListFilterField[] = [
    {
      key: 'status',
      label: '客户状态',
      type: 'enum',
      options: [
        { value: 'active', label: '跟进中' },
        { value: 'won', label: '已签约' },
      ],
    },
    { key: 'name', label: '客户名称', type: 'text' },
    { key: 'amount', label: '合同金额', type: 'number' },
    { key: 'created_at', label: '创建时间', type: 'date' },
  ]

  it('summarizes text, enum, number, date, and empty-value conditions', () => {
    expect(buildFilterSummaryItems([
      { field: 'name', op: 'contains', value: 'Acme' },
      { field: 'status', op: 'in', value: ['active', 'won'] },
      { field: 'amount', op: 'gt', value: 10000 },
      { field: 'created_at', op: 'is_empty', value: null },
    ], filterFields)).toEqual([
      expect.objectContaining({
        fieldLabel: '客户名称',
        operatorLabel: '包含',
        valueLabel: 'Acme',
      }),
      expect.objectContaining({
        fieldLabel: '客户状态',
        operatorLabel: '属于',
        valueLabel: '跟进中、已签约',
      }),
      expect.objectContaining({
        fieldLabel: '合同金额',
        operatorLabel: '大于',
        valueLabel: '10,000',
      }),
      expect.objectContaining({
        fieldLabel: '创建时间',
        operatorLabel: '为空',
      }),
    ])
  })

  it('ignores invalid fields and incomplete conditions', () => {
    expect(buildFilterSummaryItems([
      { field: 'missing', op: 'eq', value: 'x' },
      { field: 'name', op: 'contains', value: '' },
      { field: 'status', op: 'in', value: [] },
    ], filterFields)).toEqual([])
  })

  it('formats enum labels while retaining readable primitive values', () => {
    const enumField = filterFields[0]
    expect(enumField).toBeDefined()
    if (!enumField) return

    expect(formatFilterValue(enumField, 'active')).toBe('跟进中')
    expect(formatFilterValue(enumField, ['active', 'unknown'])).toBe('跟进中、unknown')
    const dateField = filterFields.find((field) => field.key === 'created_at')
    expect(dateField).toBeDefined()
    if (!dateField) return
    expect(formatFilterValue(dateField, '2026-09-04')).toBe('2026-09-04')
  })

  it('summarizes sort priority and direction', () => {
    const sortFields: ListSortField[] = [
      { key: 'updated_at', label: '更新时间', type: 'date' },
      { key: 'amount', label: '合同金额', type: 'number' },
    ]

    expect(buildSortSummaryItems([
      { field: 'updated_at', direction: 'desc' },
      { field: 'amount', direction: 'asc' },
    ], sortFields)).toEqual([
      expect.objectContaining({
        fieldLabel: '更新时间',
        directionLabel: '最晚-最早',
        priority: 1,
      }),
      expect.objectContaining({
        fieldLabel: '合同金额',
        directionLabel: '从小到大',
        priority: 2,
      }),
    ])
  })

  it('counts only hidden configurable columns', () => {
    const columns: ColumnConfigOption[] = [
      { key: 'name', title: '名称', visible: false, configurable: true, hideable: true },
      { key: 'status', title: '状态', visible: false, configurable: false, hideable: false },
      { key: 'actions', title: '操作', visible: true, configurable: false, hideable: false },
      { key: 'owner', title: '负责人', visible: true, configurable: true, hideable: true },
    ]

    expect(countHiddenColumns(columns)).toBe(1)
  })

  it('generates stable unique ids for duplicate field conditions', () => {
    const first = buildFilterSummaryItems([
      { field: 'name', op: 'contains', value: 'a' },
      { field: 'name', op: 'contains', value: 'b' },
    ], filterFields)
    const second = buildFilterSummaryItems([
      { field: 'name', op: 'contains', value: 'a' },
      { field: 'name', op: 'contains', value: 'b' },
    ], filterFields)

    expect(first.map((item) => item.id)).toEqual(second.map((item) => item.id))
    expect(new Set(first.map((item) => item.id)).size).toBe(2)
  })
})
