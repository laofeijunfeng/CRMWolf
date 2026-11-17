import { isDatePresetOperator, type ListFilterCondition, type ListFilterOperator } from '@/components/crmwolf/listFilterTypes'

function normalizeFilterValues(value: ListFilterCondition['value']): string[] {
  if (value === undefined || value === null || value === '') return []
  if (Array.isArray(value)) {
    return value
      .filter((item) => item !== null && item !== undefined && item !== '')
      .map((item) => String(item))
  }
  return [String(value)]
}

export function getFilterValue(
  filters: ListFilterCondition[],
  field: string,
  operators: ListFilterCondition['op'][] = ['eq', 'contains']
): string | null {
  const condition = filters.find((item) => item.field === field && operators.includes(item.op))
  return normalizeFilterValues(condition?.value)[0] ?? null
}

export function getFilterValues(
  filters: ListFilterCondition[],
  field: string,
  operators: ListFilterCondition['op'][] = ['eq', 'contains']
): string[] {
  const condition = filters.find((item) => item.field === field && operators.includes(item.op))
  return normalizeFilterValues(condition?.value)
}

export function getDelimitedFilterValues(
  filters: ListFilterCondition[],
  field: string,
  operators: ListFilterCondition['op'][] = ['eq', 'contains', 'in']
): string | null {
  const values = getFilterValues(filters, field, operators)
  return values.length > 0 ? values.join(',') : null
}

export function getNumericFilterValue(
  filters: ListFilterCondition[],
  field: string,
  operators: ListFilterCondition['op'][] = ['eq']
): number | null {
  const value = getFilterValue(filters, field, operators)
  if (value === null) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function shiftMonths(day: Date, months: number): Date {
  const target = new Date(day.getFullYear(), day.getMonth() + months, 1)
  const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate()
  return new Date(target.getFullYear(), target.getMonth(), Math.min(day.getDate(), lastDay))
}

function formatDate(day: Date): string {
  const month = String(day.getMonth() + 1).padStart(2, '0')
  const date = String(day.getDate()).padStart(2, '0')
  return `${day.getFullYear()}-${month}-${date}`
}

function presetBounds(operator: ListFilterOperator, today: Date): [Date, Date] | null {
  const year = today.getFullYear()
  const month = today.getMonth()
  if (operator === 'past_3_days') return [new Date(year, month, today.getDate() - 2), today]
  if (operator === 'past_1_week') return [new Date(year, month, today.getDate() - 6), today]
  if (operator === 'past_1_month') return [shiftMonths(today, -1), today]
  const quarterMonth = Math.floor(month / 3) * 3
  if (operator === 'current_quarter') return [new Date(year, quarterMonth, 1), today]
  if (operator === 'previous_quarter') {
    return [new Date(year, quarterMonth - 3, 1), new Date(year, quarterMonth, 0)]
  }
  if (operator === 'current_year') return [new Date(year, 0, 1), today]
  if (operator === 'previous_year') return [new Date(year - 1, 0, 1), new Date(year - 1, 11, 31)]
  return null
}

export function getDateBounds(
  filters: ListFilterCondition[],
  field: string,
  today = new Date()
): { start?: string; end?: string } {
  const bounds: { start?: string; end?: string } = {}
  const currentDay = new Date(today.getFullYear(), today.getMonth(), today.getDate())

  for (const condition of filters) {
    if (condition.field !== field) continue
    if (isDatePresetOperator(condition.op)) {
      const range = presetBounds(condition.op, currentDay)
      if (range === null) continue
      bounds.start = formatDate(range[0])
      bounds.end = formatDate(range[1])
      continue
    }
    if (condition.op === 'between' && Array.isArray(condition.value) && condition.value.length === 2) {
      const dates = condition.value.map((item) => String(item))
      const first = dates[0]
      const second = dates[1]
      if (first === undefined || second === undefined) continue
      if (!/^\d{4}-\d{2}-\d{2}$/.test(first) || !/^\d{4}-\d{2}-\d{2}$/.test(second)) continue
      const [start, end] = first <= second ? [first, second] : [second, first]
      bounds.start = start
      bounds.end = end
      continue
    }
    if (condition.value === undefined || condition.value === null || condition.value === '') continue
    const value = String(condition.value)
    if (condition.op === 'eq') {
      bounds.start = value
      bounds.end = value
    } else if (condition.op === 'after') {
      bounds.start = value
    } else if (condition.op === 'before') {
      bounds.end = value
    }
  }

  return bounds
}
