import { describe, expect, it } from 'vitest'
import { listFilterOperatorsByType, normalizeListFilterOperator } from '../listFilterTypes'

describe('list filter operator catalog', () => {
  it('defaults enum filters to multi-value membership operators', () => {
    expect(listFilterOperatorsByType.enum.map((operator) => operator.value)).toEqual([
      'in',
      'not_in',
      'is_empty',
      'is_not_empty'
    ])
  })

  it('migrates legacy enum operators without changing their meaning', () => {
    expect(normalizeListFilterOperator('enum', 'eq')).toBe('in')
    expect(normalizeListFilterOperator('enum', 'contains')).toBe('in')
    expect(normalizeListFilterOperator('enum', 'neq')).toBe('not_in')
    expect(normalizeListFilterOperator('enum', 'not_contains')).toBe('not_in')
  })

  it('offers comparison operators for number filters', () => {
    expect(listFilterOperatorsByType.number.map((operator) => operator.value)).toEqual([
      'eq',
      'neq',
      'gt',
      'gte',
      'lt',
      'lte',
      'is_empty',
      'is_not_empty'
    ])
  })
})
