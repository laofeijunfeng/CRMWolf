export type ListFilterFieldType = 'text' | 'enum' | 'date' | 'number'

export type ListFilterOperator =
  | 'eq'
  | 'neq'
  | 'contains'
  | 'not_contains'
  | 'is_empty'
  | 'is_not_empty'
  | 'before'
  | 'after'

export interface ListFilterOption {
  value: string | number
  label: string
}

export interface ListFilterField {
  key: string
  label: string
  type: ListFilterFieldType
  options?: ListFilterOption[]
}

export interface ListFilterCondition {
  field: string
  op: ListFilterOperator
  value?: string | number | (string | number)[] | null
}
