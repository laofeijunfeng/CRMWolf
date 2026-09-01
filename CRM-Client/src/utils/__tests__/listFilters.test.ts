import { describe, expect, it } from 'vitest'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import { getDelimitedFilterValues } from '../listFilters'

describe('getDelimitedFilterValues', () => {
  it('serializes enum multi-select filters used by the business journey board', () => {
    const filters: ListFilterCondition[] = [
      { field: 'owner_id', op: 'in', value: ['owner-1', 'owner-2'] }
    ]

    expect(getDelimitedFilterValues(filters, 'owner_id')).toBe('owner-1,owner-2')
  })
})
