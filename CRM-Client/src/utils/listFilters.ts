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

function presetStart(operator: ListFilterOperator, today: Date): Date | null {
  if (operator === 'past_1_day') return today
  if (operator === 'past_3_days') return new Date(today.getFullYear(), today.getMonth(), today.getDate() - 2)
  if (operator === 'past_1_week') return new Date(today.getFullYear(), today.getMonth(), today.getDate() - 6)
  if (operator === 'past_1_month') return shiftMonths(today, -1)
  if (operator === 'past_3_months') return shiftMonths(today, -3)
  if (operator === 'past_6_months') return shiftMonths(today, -6)
  if (operator === 'past_1_year') return shiftMonths(today, -12)
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
      const start = presetStart(condition.op, currentDay)
      if (start === null) continue
      bounds.start = formatDate(start)
      bounds.end = formatDate(currentDay)
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
