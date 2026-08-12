import { beforeEach, describe, expect, it, vi } from 'vitest'

const { requestMock } = vi.hoisted(() => ({
  requestMock: {
    patch: vi.fn(),
  },
}))

vi.mock('@/utils/request', () => ({
  default: requestMock,
}))

import { opportunityApi, OpportunityStatus } from '@/api/opportunity'

const terminalOpportunityResponse = {
  id: 'opp_123',
  public_id: 'opp_123',
  opportunity_number: 'OPP202608120001',
  opportunity_name: '企业版采购',
  customer_id: 'cus_123',
  procurement_method_id: null,
  total_amount: 120000,
  user_count: 100,
  unit_price: 1200,
  license_type: 'SUBSCRIPTION',
  subscription_years: 1,
  purchase_type: 'NEW',
  decision_maker_count: 2,
  expected_closing_date: '2026-12-31',
  procurement_stage_id: 3,
  win_probability: 0,
  owner_id: '9',
  creator_id: '9',
  status: OpportunityStatus.LOST,
  approval_phase: 'approved',
  loss_reason: '预算取消',
  actual_amount: null,
  actual_closing_date: null,
  created_time: '2026-08-01T08:00:00',
  updated_time: '2026-08-12T08:00:00',
  version: 2,
}

describe('opportunity API', () => {
  beforeEach(() => {
    requestMock.patch.mockReset()
  })

  it('accepts and returns the API response after marking an opportunity as lost', async () => {
    requestMock.patch.mockResolvedValue(terminalOpportunityResponse)

    const result = await opportunityApi.markAsLost('opp_123', { loss_reason: '预算取消' })

    expect(requestMock.patch).toHaveBeenCalledWith('/v1/opportunities/opp_123/lose', {
      loss_reason: '预算取消',
    })
    expect(result).toMatchObject({
      id: 'opp_123',
      status: OpportunityStatus.LOST,
      loss_reason: '预算取消',
    })
  })

  it('accepts and returns the API response after marking an opportunity as won', async () => {
    requestMock.patch.mockResolvedValue({
      ...terminalOpportunityResponse,
      status: OpportunityStatus.WON,
      loss_reason: null,
      actual_amount: 120000,
      actual_closing_date: '2026-08-12',
    })

    const result = await opportunityApi.markAsWon('opp_123', {
      actual_amount: 120000,
      actual_closing_date: '2026-08-12',
    })

    expect(requestMock.patch).toHaveBeenCalledWith('/v1/opportunities/opp_123/win', {
      actual_amount: 120000,
      actual_closing_date: '2026-08-12',
    })
    expect(result).toMatchObject({
      id: 'opp_123',
      status: OpportunityStatus.WON,
      actual_amount: 120000,
    })
  })
})
