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

  it('exposes only the approved date preset operators', () => {
    expect(listFilterOperatorsByType.date.map((operator) => operator.value)).toEqual([
      'past_3_days',
      'past_1_week',
      'past_1_month',
      'current_quarter',
      'previous_quarter',
      'current_year',
      'previous_year',
      'eq',
      'after',
      'before',
      'between',
      'is_empty',
      'is_not_empty'
    ])
    expect(listFilterOperatorsByType.date.map((operator) => operator.label)).toEqual([
      '过去 3 天',
      '过去 1 周',
      '过去 1 个月',
      '本季度',
      '上季度',
      '本年',
      '去年',
      '等于',
      '晚于',
      '早于',
      '介于',
      '为空',
      '不为空'
    ])
  })

  it('keeps between before empty for date filters', () => {
    const labels = listFilterOperatorsByType.date.map((operator) => operator.label)
    expect(labels.indexOf('介于')).toBe(labels.indexOf('早于') + 1)
    expect(labels.indexOf('为空')).toBe(labels.indexOf('介于') + 1)
    expect(listFilterOperatorsByType.date.some((operator) => operator.value === 'between')).toBe(true)
  })
})
