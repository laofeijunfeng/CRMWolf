import type { Opportunity } from '@/api/opportunity'
import { parseOpportunityApiResponse } from '@/api/opportunity'
import request from '@/utils/request'
import {
  BusinessJourneyBoardResponseSchema,
  BusinessJourneyDetailResponseSchema,
  BusinessJourneyListResponseSchema,
  BusinessJourneyOwnerFilterOptionsResponseSchema,
  DealJourneyListSchema,
  type DealJourney,
  DealJourneySchema,
  type BusinessJourneyBoardResponse,
  type BusinessJourneyListResponse,
  type BusinessJourneyOwnerFilterOptionsResponse,
} from '@/schemas/dealJourney'

export type {
  BusinessJourneyBoardCard,
  BusinessJourneyBoardColumn,
  BusinessJourneyBoardResponse,
  BusinessJourneyListItem,
  BusinessJourneyListResponse,
  BusinessJourneyOwner,
  BusinessJourneyOwnerFilterOption,
  BusinessJourneyOwnerFilterOptionsResponse,
  DealJourney,
  DealJourneyOpportunitySummary
} from '@/schemas/dealJourney'

export type BusinessJourneyTab = 'all' | 'active' | 'completed' | 'lost'

export interface BusinessJourneyListParams {
  skip: number
  limit: number
  tab: BusinessJourneyTab
  search?: string
  filters?: string
  sorts?: string
}

export interface BusinessJourneyBoardParams {
  tab: BusinessJourneyTab
  search?: string
  filters?: string
  sorts?: string
  limit?: number
}

export interface BusinessJourneyDetailResponse {
  journey: DealJourney
  primary_opportunity: Opportunity | null
}

export const dealJourneyApi = {
  async list(params: BusinessJourneyListParams): Promise<BusinessJourneyListResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get('/v1/business-journeys', { params })
    return BusinessJourneyListResponseSchema.parse(raw)
  },

  async getBoard(params: BusinessJourneyBoardParams): Promise<BusinessJourneyBoardResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get('/v1/business-journeys/board', { params })
    return BusinessJourneyBoardResponseSchema.parse(raw)
  },

  async getOwnerFilterOptions(): Promise<BusinessJourneyOwnerFilterOptionsResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get('/v1/business-journeys/owner-options')
    return BusinessJourneyOwnerFilterOptionsResponseSchema.parse(raw)
  },

  async getDetail(journeyPublicId: string): Promise<BusinessJourneyDetailResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get(`/v1/business-journeys/${journeyPublicId}`)
    const parsed = BusinessJourneyDetailResponseSchema.parse(raw)
    return {
      journey: parsed.journey,
      primary_opportunity: parsed.primary_opportunity === null
        ? null
        : parseOpportunityApiResponse(parsed.primary_opportunity)
    }
  },

  async listByCustomer(customerId: string): Promise<DealJourney[]> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get(`/v1/customers/${customerId}/deal-journeys`)
    return DealJourneyListSchema.parse(raw)
  },

  async getByCustomer(customerId: string, journeyPublicId: string): Promise<DealJourney> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get(
      `/v1/customers/${customerId}/deal-journeys/${journeyPublicId}`
    )
    return DealJourneySchema.parse(raw)
  }
}

export default dealJourneyApi
