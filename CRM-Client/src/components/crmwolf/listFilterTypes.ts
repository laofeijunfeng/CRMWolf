export type ListFilterFieldType = 'text' | 'enum' | 'date' | 'number'

export type ListFilterOperator =
  | 'eq'
  | 'neq'
  | 'contains'
  | 'not_contains'
  | 'in'
  | 'not_in'
  | 'gt'
  | 'gte'
  | 'lt'
  | 'lte'
  | 'is_empty'
  | 'is_not_empty'
  | 'before'
  | 'after'
  | 'between'
  | 'past_3_days'
  | 'past_1_week'
  | 'past_1_month'
  | 'current_quarter'
  | 'previous_quarter'
  | 'current_year'
  | 'previous_year'

export interface ListFilterOperatorOption {
  value: ListFilterOperator
  label: string
}

export const listFilterOperatorsByType: Record<
  ListFilterFieldType,
  readonly ListFilterOperatorOption[]
> = {
  text: [
    { value: 'contains', label: '包含' },
    { value: 'not_contains', label: '不包含' },
    { value: 'eq', label: '等于' },
    { value: 'neq', label: '不等于' },
    { value: 'is_empty', label: '为空' },
    { value: 'is_not_empty', label: '不为空' }
  ],
  enum: [
    { value: 'in', label: '属于' },
    { value: 'not_in', label: '不属于' },
    { value: 'is_empty', label: '为空' },
    { value: 'is_not_empty', label: '不为空' }
  ],
  date: [
    { value: 'past_3_days', label: '过去 3 天' },
    { value: 'past_1_week', label: '过去 1 周' },
    { value: 'past_1_month', label: '过去 1 个月' },
    { value: 'current_quarter', label: '本季度' },
    { value: 'previous_quarter', label: '上季度' },
    { value: 'current_year', label: '本年' },
    { value: 'previous_year', label: '去年' },
    { value: 'eq', label: '等于' },
    { value: 'after', label: '晚于' },
    { value: 'before', label: '早于' },
    { value: 'between', label: '介于' },
    { value: 'is_empty', label: '为空' },
    { value: 'is_not_empty', label: '不为空' }
  ],
  number: [
    { value: 'eq', label: '等于' },
    { value: 'neq', label: '不等于' },
    { value: 'gt', label: '大于' },
    { value: 'gte', label: '大于等于' },
    { value: 'lt', label: '小于' },
    { value: 'lte', label: '小于等于' },
    { value: 'is_empty', label: '为空' },
    { value: 'is_not_empty', label: '不为空' }
  ]
}

export function normalizeListFilterOperator(
  type: ListFilterFieldType,
  operator: ListFilterOperator
): ListFilterOperator | undefined {
  if (listFilterOperatorsByType[type].some((option) => option.value === operator)) {
    return operator
  }
  if (type !== 'enum') return undefined
  if (operator === 'eq' || operator === 'contains') return 'in'
  if (operator === 'neq' || operator === 'not_contains') return 'not_in'
  return undefined
}

const DATE_PRESET_OPERATORS: Record<string, true> = {
  past_3_days: true,
  past_1_week: true,
  past_1_month: true,
  current_quarter: true,
  previous_quarter: true,
  current_year: true,
  previous_year: true
}

export function isDatePresetOperator(operator: ListFilterOperator): boolean {
  return DATE_PRESET_OPERATORS[operator] === true
}

export function operatorNeedsValue(operator: ListFilterOperator): boolean {
  return operator !== 'is_empty' && operator !== 'is_not_empty' && DATE_PRESET_OPERATORS[operator] !== true
}

export interface ListFilterOption {
  value: string | number
  label: string
}

export interface ListFilterField {
  key: string
  label: string
  type: ListFilterFieldType
  options?: ListFilterOption[]
  operators?: readonly ListFilterOperator[]
}

export interface ListFilterCondition {
  field: string
  op: ListFilterOperator
  value?: string | number | (string | number)[] | null
}
