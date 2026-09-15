import { describe, expect, it } from 'vitest'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import {
  BUSINESS_JOURNEY_BOARD_OPPORTUNITY_DATE_FILTER_FIELDS,
  buildBusinessJourneyBoardParams
} from '../businessJourneyBoardFilters'

describe('business journey board filter mapping', () => {
  it('exposes opportunity created time and expected closing date fields', () => {
    expect(BUSINESS_JOURNEY_BOARD_OPPORTUNITY_DATE_FILTER_FIELDS).toEqual([
      { key: 'created_time', label: '商机创建时间', type: 'date' },
      { key: 'expected_closing_date', label: '预计成交日期', type: 'date' }
    ])
  })

  it('maps each date field to its own query bounds and ANDs them in params', () => {
    const filters: ListFilterCondition[] = [
      { field: 'last_event_at', op: 'after', value: '2026-08-01' },
      { field: 'last_event_at', op: 'before', value: '2026-08-31' },
      { field: 'created_time', op: 'after', value: '2026-03-01' },
      { field: 'created_time', op: 'before', value: '2026-03-31' },
      { field: 'expected_closing_date', op: 'eq', value: '2026-09-30' },
      { field: 'owner_id', op: 'in', value: ['1', '2'] }
    ]

    expect(buildBusinessJourneyBoardParams(filters)).toEqual({
      start_date: '2026-08-01',
      end_date: '2026-08-31',
      created_time_start: '2026-03-01',
      created_time_end: '2026-03-31',
      expected_closing_date_start: '2026-09-30',
      expected_closing_date_end: '2026-09-30',
      owner_id: '1,2',
      limit: 500
    })
  })

  it('omits unused date pairs instead of sending empty strings', () => {
    expect(buildBusinessJourneyBoardParams([])).toEqual({
      start_date: null,
      end_date: null,
      created_time_start: null,
      created_time_end: null,
      expected_closing_date_start: null,
      expected_closing_date_end: null,
      owner_id: null,
      limit: 500
    })
  })
})
