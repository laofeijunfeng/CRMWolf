import { describe, expect, it } from 'vitest'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import { getDateBounds, getDelimitedFilterValues } from '../listFilters'

describe('getDelimitedFilterValues', () => {
  it('serializes enum multi-select filters used by the business journey board', () => {
    const filters: ListFilterCondition[] = [
      { field: 'owner_id', op: 'in', value: ['owner-1', 'owner-2'] }
    ]

    expect(getDelimitedFilterValues(filters, 'owner_id')).toBe('owner-1,owner-2')
  })
})

describe('getDateBounds', () => {
  it('turns a past-week preset into an inclusive dashboard range', () => {
    const filters: ListFilterCondition[] = [
      { field: 'created_time', op: 'past_1_week', value: null }
    ]

    expect(getDateBounds(filters, 'created_time', new Date(2026, 9, 14))).toEqual({
      start: '2026-10-08',
      end: '2026-10-14'
    })
  })
})
