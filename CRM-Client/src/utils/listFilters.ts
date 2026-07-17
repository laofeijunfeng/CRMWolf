import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'

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
  operators: ListFilterCondition['op'][] = ['eq', 'contains']
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

export function getDateBounds(
  filters: ListFilterCondition[],
  field: string
): { start?: string; end?: string } {
  const bounds: { start?: string; end?: string } = {}

  for (const condition of filters) {
    if (condition.field !== field || condition.value === undefined || condition.value === null || condition.value === '') continue
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
