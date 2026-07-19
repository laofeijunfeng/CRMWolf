import type { ListFilterField, ListFilterFieldType, ListFilterOption } from './listFilterTypes'

export type ListSortFieldType = ListFilterFieldType

export type ListSortDirection = 'asc' | 'desc'

export type ListSortOption = ListFilterOption

export interface ListSortField extends Omit<ListFilterField, 'options'> {
  type: ListSortFieldType
  options?: ListSortOption[]
}

export interface ListSortCondition {
  field: string
  direction: ListSortDirection
}
