import type { ListSortCondition } from '@/components/crmwolf/listSortTypes'

export function serializeListSorts(sorts: ListSortCondition[]): string | null {
  const parts = sorts
    .filter((sort) => sort.field.trim() !== '')
    .map((sort) => `${sort.field}:${sort.direction}`)

  return parts.length > 0 ? parts.join(',') : null
}

export function getPrimarySort(sorts: ListSortCondition[]): {
  order_by?: string
  order_dir?: 'asc' | 'desc'
} {
  const firstSort = sorts.find((sort) => sort.field.trim() !== '')
  if (!firstSort) return {}

  return {
    order_by: firstSort.field,
    order_dir: firstSort.direction
  }
}
