import { describe, expect, it } from 'vitest'
import { mergeListFilters, serializeListQuery, withEqualsFilter, withoutFilterFields } from '../listQuery'

describe('serializeListQuery', () => {
  it('always serializes filters and sorts, including empty arrays', () => {
    expect(serializeListQuery()).toEqual({
      filters: '[]',
      sorts: '[]'
    })
    expect(serializeListQuery({ filters: null })).toEqual({
      filters: '[]',
      sorts: '[]'
    })
    expect(serializeListQuery({
      filters: [{ field: 'owner_id', op: 'eq', value: 'me' }],
      sorts: [{ field: 'created_time', direction: 'desc' }]
    })).toEqual({
      filters: JSON.stringify([{ field: 'owner_id', op: 'eq', value: 'me' }]),
      sorts: JSON.stringify([{ field: 'created_time', direction: 'desc' }])
    })
    expect(serializeListQuery({
      filters: [{ field: 'status', op: 'in', value: ['active', 'expired'] }]
    })).toEqual({
      filters: JSON.stringify([{ field: 'status', op: 'in', value: ['active', 'expired'] }]),
      sorts: '[]'
    })
  })
})

describe('mergeListFilters', () => {
  it('flattens request filters without dropping empty groups', () => {
    expect(mergeListFilters(
      [{ field: 'city', op: 'contains', value: '深圳' }],
      { field: 'status', op: 'eq', value: 0 },
      null
    )).toEqual([
      { field: 'city', op: 'contains', value: '深圳' },
      { field: 'status', op: 'eq', value: 0 }
    ])
  })
})

describe('withEqualsFilter', () => {
  it('lets a tab status replace the user status filter', () => {
    expect(withEqualsFilter(
      [
        { field: 'owner_id', op: 'eq', value: 'u1' },
        { field: 'status', op: 'eq', value: 2 }
      ],
      'status',
      0
    )).toEqual([
      { field: 'owner_id', op: 'eq', value: 'u1' },
      { field: 'status', op: 'eq', value: 0 }
    ])
    expect(withEqualsFilter(
      [{ field: 'status', op: 'eq', value: 2 }],
      'status',
      null
    )).toEqual([])
  })
})


describe('withoutFilterFields', () => {
  it('removes tab-owned fields without mutating the original filters', () => {
    const filters = [
      { field: 'status', op: 'eq' as const, value: 'PENDING' },
      { field: 'owner_id', op: 'eq' as const, value: 'u1' },
      { field: 'approval_status', op: 'eq' as const, value: 'approved' }
    ]

    expect(withoutFilterFields(filters, ['status', 'approval_status'])).toEqual([
      { field: 'owner_id', op: 'eq', value: 'u1' }
    ])
    expect(filters).toHaveLength(3)
  })
})
