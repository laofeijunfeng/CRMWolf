import request from '@/utils/request'
import {
  DealJourneyListSchema,
  DealJourneySchema,
  type DealJourney
} from '@/schemas/dealJourney'

export type { DealJourney, DealJourneyOpportunitySummary } from '@/schemas/dealJourney'

export const dealJourneyApi = {
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
