import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition } from '@/components/crmwolf/listSortTypes'

export interface SerializedListQuery {
  filters: string
  sorts: string
}

export function serializeListQuery(input?: {
  filters?: ListFilterCondition[] | null
  sorts?: ListSortCondition[] | null
}): SerializedListQuery {
  return {
    filters: JSON.stringify(input?.filters ?? []),
    sorts: JSON.stringify(input?.sorts ?? [])
  }
}

export function mergeListFilters(
  ...groups: (ListFilterCondition | ListFilterCondition[] | null | undefined)[]
): ListFilterCondition[] {
  const merged: ListFilterCondition[] = []
  for (const group of groups) {
    if (group == null) continue
    if (Array.isArray(group)) merged.push(...group)
    else merged.push(group)
  }
  return merged
}

export function withEqualsFilter(
  filters: ListFilterCondition[],
  field: string,
  value: string | number | null | undefined
): ListFilterCondition[] {
  const rest = filters.filter((item) => item.field !== field)
  if (value === null || value === undefined || value === '') return rest
  return [...rest, { field, op: 'eq', value }]
}

export function withoutFilterFields(
  filters: ListFilterCondition[],
  fields: Iterable<string>
): ListFilterCondition[] {
  const excluded = new Set(fields)
  return filters.filter((item) => !excluded.has(item.field))
}
