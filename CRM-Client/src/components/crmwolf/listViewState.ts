import type { ColumnConfigOption } from './columnConfigTypes'
import {
  listFilterOperatorsByType,
  type ListFilterCondition,
  type ListFilterField,
  type ListFilterOption,
} from './listFilterTypes'
import type { ListSortCondition, ListSortField } from './listSortTypes'

export interface FilterSummaryItem {
  id: string
  field: string
  fieldLabel: string
  operator: ListFilterCondition['op']
  operatorLabel: string
  valueLabel?: string
  value?: ListFilterCondition['value']
  removable: boolean
}

export interface SortSummaryItem {
  id: string
  field: string
  fieldLabel: string
  direction: ListSortCondition['direction']
  directionLabel: string
  priority: number
}

const sortDirectionLabelsByType: Record<ListSortField['type'], Record<ListSortCondition['direction'], string>> = {
  text: { asc: 'A-Z', desc: 'Z-A' },
  enum: { asc: '选项顺序', desc: '选项倒序' },
  date: { asc: '最早-最晚', desc: '最晚-最早' },
  number: { asc: '从小到大', desc: '从大到小' },
}

function formatOptionValue(value: string | number, options: ListFilterOption[]): string {
  return options.find((option) => String(option.value) === String(value))?.label ?? String(value)
}

function isEmptyOperator(operator: ListFilterCondition['op']): boolean {
  return operator === 'is_empty' || operator === 'is_not_empty'
}

function isMeaningfulValue(value: ListFilterCondition['value']): boolean {
  if (Array.isArray(value)) return value.length > 0
  return value !== null && value !== undefined && String(value).trim() !== ''
}

export function formatFilterValue(
  field: ListFilterField,
  value: ListFilterCondition['value'],
): string | undefined {
  if (!isMeaningfulValue(value)) return undefined

  if (Array.isArray(value)) {
    return value
      .map((item) => formatOptionValue(item, field.options ?? []))
      .join('、')
  }

  if (value === null || value === undefined) return undefined

  if (field.type === 'enum') {
    return formatOptionValue(value, field.options ?? [])
  }

  if (field.type === 'number') {
    const numericValue = typeof value === 'number' ? value : Number(value)
    if (Number.isFinite(numericValue)) {
      return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(numericValue)
    }
  }

  return String(value).trim()
}

function buildFilterItemId(condition: ListFilterCondition, index: number): string {
  return `filter:${index}:${condition.field}:${condition.op}`
}

export function buildFilterSummaryItems(
  filters: ListFilterCondition[],
  fields: ListFilterField[],
): FilterSummaryItem[] {
  const fieldByKey = new Map(fields.map((field) => [field.key, field]))
  const operatorLabelByType = new Map(
    fields.flatMap((field) => listFilterOperatorsByType[field.type].map((option) => [
      `${field.type}:${option.value}`,
      option.label,
    ])),
  )

  return filters.flatMap((condition, index) => {
    const field = fieldByKey.get(condition.field)
    if (!field) return []

    const operatorLabel = operatorLabelByType.get(`${field.type}:${condition.op}`)
    if (operatorLabel === undefined) return []

    if (!isEmptyOperator(condition.op) && !isMeaningfulValue(condition.value)) return []

    const valueLabel = isEmptyOperator(condition.op)
      ? undefined
      : formatFilterValue(field, condition.value)
    if (!isEmptyOperator(condition.op) && valueLabel === undefined) return []

    return [{
      id: buildFilterItemId(condition, index),
      field: field.key,
      fieldLabel: field.label,
      operator: condition.op,
      operatorLabel,
      ...(valueLabel === undefined ? {} : { valueLabel }),
      value: condition.value,
      removable: true,
    }]
  })
}


export function findFilterSummaryIndex(id: string): number | undefined {
  const match = /^filter:(\d+):/.exec(id)
  if (!match) return undefined
  const index = Number(match[1])
  return Number.isInteger(index) ? index : undefined
}

export function buildSortSummaryItems(
  sorts: ListSortCondition[],
  fields: ListSortField[],
): SortSummaryItem[] {
  const fieldByKey = new Map(fields.map((field) => [field.key, field]))

  return sorts.flatMap((sort, index) => {
    const field = fieldByKey.get(sort.field)
    if (!field) return []

    return [{
      id: `sort:${index}:${sort.field}:${sort.direction}`,
      field: field.key,
      fieldLabel: field.label,
      direction: sort.direction,
      directionLabel: sortDirectionLabelsByType[field.type][sort.direction],
      priority: index + 1,
    }]
  })
}

export function countHiddenColumns(columns: ColumnConfigOption[]): number {
  return columns.filter((column) =>
    column.hideable && column.configurable && !column.visible,
  ).length
}
