import request from '@/utils/request'
import {
  BusinessJourneyBoardOwnerFilterOptionsResponseSchema,
  BusinessJourneyBoardResponseSchema,
  type BusinessJourneyBoardOwnerFilterOptionsResponse,
  type BusinessJourneyBoardResponse
} from '@/schemas/businessJourneyBoard'

export type {
  BusinessJourneyBoardCard,
  BusinessJourneyBoardColumn,
  BusinessJourneyBoardOwner,
  BusinessJourneyBoardOwnerFilterOption,
  BusinessJourneyBoardOwnerFilterOptionsResponse,
  BusinessJourneyBoardResponse,
  BusinessJourneyBoardScope,
  BusinessJourneyBoardStageKey,
  BusinessJourneyBoardSummary
} from '@/schemas/businessJourneyBoard'

export interface BusinessJourneyBoardParams {
  start_date?: string | null
  end_date?: string | null
  owner_id?: string | null
  limit?: number
}

const businessJourneyBoardApi = {
  async getBoard(params?: BusinessJourneyBoardParams): Promise<BusinessJourneyBoardResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get('/v1/business-journey-board/', { params })
    return BusinessJourneyBoardResponseSchema.parse(raw)
  },

  async getOwnerFilterOptions(): Promise<BusinessJourneyBoardOwnerFilterOptionsResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get('/v1/filter-options/owners', {
      params: { resource: 'sales_dashboard' }
    })
    return BusinessJourneyBoardOwnerFilterOptionsResponseSchema.parse(raw)
  }
}

export default businessJourneyBoardApi
