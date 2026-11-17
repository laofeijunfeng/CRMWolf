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

  it('turns between into inclusive bounds and swaps reversed dates', () => {
    expect(getDateBounds([
      { field: 'created_time', op: 'between', value: ['2026-10-20', '2026-10-01'] }
    ], 'created_time', new Date(2026, 9, 21))).toEqual({
      start: '2026-10-01',
      end: '2026-10-20'
    })
  })

  it('turns natural quarter presets into complete calendar quarter bounds', () => {
    expect(getDateBounds([
      { field: 'created_time', op: 'current_quarter', value: null }
    ], 'created_time', new Date(2026, 10, 17))).toEqual({
      start: '2026-10-01',
      end: '2026-12-31'
    })
    expect(getDateBounds([
      { field: 'created_time', op: 'previous_quarter', value: null }
    ], 'created_time', new Date(2026, 10, 17))).toEqual({
      start: '2026-07-01',
      end: '2026-09-30'
    })
  })

  it('turns natural year presets into complete year bounds across a year boundary', () => {
    expect(getDateBounds([
      { field: 'created_time', op: 'current_year', value: null }
    ], 'created_time', new Date(2026, 10, 17))).toEqual({
      start: '2026-01-01',
      end: '2026-12-31'
    })
    expect(getDateBounds([
      { field: 'created_time', op: 'previous_year', value: null }
    ], 'created_time', new Date(2026, 10, 17))).toEqual({
      start: '2025-01-01',
      end: '2025-12-31'
    })
  })

  it('handles a first-quarter year boundary and leap-year end date', () => {
    expect(getDateBounds([
      { field: 'created_time', op: 'previous_quarter', value: null }
    ], 'created_time', new Date(2026, 0, 15))).toEqual({
      start: '2025-10-01',
      end: '2025-12-31'
    })
    expect(getDateBounds([
      { field: 'created_time', op: 'current_year', value: null }
    ], 'created_time', new Date(2024, 1, 29))).toEqual({
      start: '2024-01-01',
      end: '2024-12-31'
    })
  })
})
