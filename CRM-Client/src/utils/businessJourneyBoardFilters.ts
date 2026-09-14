import type { ListFilterCondition, ListFilterField } from '@/components/crmwolf/listFilterTypes'
import type { BusinessJourneyBoardParams } from '@/api/businessJourneyBoard'
import { getDateBounds, getDelimitedFilterValues } from '@/utils/listFilters'

export const BUSINESS_JOURNEY_BOARD_OPPORTUNITY_DATE_FILTER_FIELDS: ListFilterField[] = [
  { key: 'created_time', label: '商机创建时间', type: 'date' },
  { key: 'expected_closing_date', label: '预计成交日期', type: 'date' }
]

export function buildBusinessJourneyBoardParams(
  filters: ListFilterCondition[],
  limit = 500
): BusinessJourneyBoardParams {
  const lastEventBounds = getDateBounds(filters, 'last_event_at')
  const createdTimeBounds = getDateBounds(filters, 'created_time')
  const expectedClosingBounds = getDateBounds(filters, 'expected_closing_date')

  return {
    start_date: lastEventBounds.start ?? null,
    end_date: lastEventBounds.end ?? null,
    created_time_start: createdTimeBounds.start ?? null,
    created_time_end: createdTimeBounds.end ?? null,
    expected_closing_date_start: expectedClosingBounds.start ?? null,
    expected_closing_date_end: expectedClosingBounds.end ?? null,
    owner_id: getDelimitedFilterValues(filters, 'owner_id'),
    limit
  }
}
