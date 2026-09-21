import { beforeEach, describe, expect, it, vi } from 'vitest'

const requestGet = vi.hoisted(() => vi.fn())

vi.mock('@/utils/request', () => ({
  default: {
    get: requestGet,
  },
}))

import { dealJourneyApi } from '@/api/dealJourney'
import type { Opportunity } from '@/api/opportunity'
import {
  BusinessJourneyBoardResponseSchema,
  BusinessJourneyDetailResponseSchema,
  BusinessJourneyListResponseSchema,
} from '@/schemas/dealJourney'

const journeyPublicId = `djy_${'a'.repeat(32)}`
const opportunityPublicId = `opp_${'b'.repeat(32)}`

const listItem = {
  id: journeyPublicId,
  public_id: journeyPublicId,
  name: '华东续约旅程',
  status: 'ACTIVE',
  current_board_stage: 'active_progress',
  current_board_stage_label: '积极推进',
  amount: 168000,
  purchase_type: 'RENEWAL',
  started_at: '2026-09-01T09:00:00',
  closed_at: null,
  last_event_at: '2026-09-20T12:00:00',
  primary_opportunity: {
    public_id: opportunityPublicId,
    opportunity_name: '华东续约商机',
    status: 1,
    approval_phase: 'approved',
    win_probability: 70,
    expected_closing_date: '2026-10-31',
    product_name: 'Hifox CRM',
  },
  customer_id: `cus_${'c'.repeat(32)}`,
  customer_name: '示例科技',
  owner: {
    id: '7',
    name: '王小明',
    avatar_url: null,
  },
  primary_opportunity_name: '华东续约商机',
  product_name: 'Hifox CRM',
  created_time: '2026-08-15T10:00:00',
  expected_closing_date: '2026-10-31',
}

const boardCard = {
  public_id: journeyPublicId,
  journey_name: '华东续约旅程',
  customer_id: `cus_${'c'.repeat(32)}`,
  customer_name: '示例科技',
  owner: {
    id: '7',
    name: '王小明',
    avatar_url: null,
  },
  status: 'ACTIVE',
  current_board_stage: 'active_progress',
  started_at: '2026-09-01T09:00:00',
  closed_at: null,
  last_event_at: '2026-09-20T12:00:00',
  last_event_summary: '完成方案确认',
  amount: 168000,
  primary_opportunity: {
    public_id: opportunityPublicId,
    opportunity_name: '华东续约商机',
    amount: 168000,
    actual_amount: null,
    status: 1,
    current_stage_name: '方案确认',
    win_probability: 70,
    expected_closing_date: '2026-10-31',
  },
  contract_summary: {
    count: 1,
    signed_count: 0,
    amount: 168000,
  },
  payment_summary: {
    plan_count: 1,
    record_count: 0,
    planned_amount: 168000,
    paid_amount: 0,
    remaining_amount: 168000,
  },
  invoice_summary: {
    application_count: 0,
    issued_count: 0,
    applied_amount: 0,
    issued_amount: 0,
  },
}

const detailOpportunity = {
  id: opportunityPublicId,
  public_id: opportunityPublicId,
  deal_journey_id: journeyPublicId,
  opportunity_number: 'OPP-2026-001',
  opportunity_name: '华东续约商机',
  customer_id: `cus_${'c'.repeat(32)}`,
  customer_name: '示例科技',
  procurement_method_id: null,
  procurement_method_info: null,
  product_public_id: null,
  product_name: 'Hifox CRM',
  product_module_public_ids: [],
  product_modules: [],
  total_amount: 168000,
  user_count: 20,
  unit_price: 8400,
  license_type: 'SUBSCRIPTION',
  subscription_years: 1,
  purchase_type: 'RENEWAL',
  decision_maker_count: 3,
  expected_closing_date: '2026-10-31',
  procurement_stage_id: null,
  win_probability: 70,
  current_stage_snapshot: null,
  owner_id: '7',
  creator_id: '7',
  status: 0,
  approval_phase: 'approved',
  actual_amount: null,
  actual_closing_date: null,
  loss_reason: null,
  created_time: '2026-08-15T10:00:00',
  updated_time: '2026-09-20T12:00:00',
  version: 1,
  customer_info: {
    id: `cus_${'c'.repeat(32)}`,
    account_name: '示例科技',
  },
}

describe('business journey page schemas', () => {
  it('parses the backend pagination envelope and complete list item', () => {
    const parsed = BusinessJourneyListResponseSchema.parse({
      items: [listItem],
      total: 1,
      page: 1,
      page_size: 20,
      total_pages: 1,
    })

    expect(parsed.items[0]?.public_id).toBe(journeyPublicId)
    expect(parsed.page_size).toBe(20)
    expect(parsed.total_pages).toBe(1)
  })

  it('requires public journey IDs for list rows', () => {
    const withoutPublicId: Partial<typeof listItem> = { ...listItem }
    delete withoutPublicId.public_id
    expect(() => BusinessJourneyListResponseSchema.parse({
      items: [withoutPublicId],
      total: 1,
      page: 1,
      page_size: 20,
      total_pages: 1,
    })).toThrow()
  })

  it('accepts public board cards and rejects numeric-only journey_id cards', () => {
    const response = {
      columns: [{
        key: 'active_progress',
        title: '积极推进',
        description: '持续推进中的旅程',
        count: 1,
        amount: 168000,
        cards: [boardCard],
      }],
      summary: {
        total_count: 1,
        total_amount: 168000,
        active_count: 1,
        completed_count: 0,
        lost_count: 0,
      },
      truncated: false,
    }

    expect(BusinessJourneyBoardResponseSchema.parse(response).columns[0]?.cards[0]?.public_id)
      .toBe(journeyPublicId)
    expect(() => BusinessJourneyBoardResponseSchema.parse({
      ...response,
      columns: [{
        ...response.columns[0],
        cards: [{ ...boardCard, public_id: undefined, journey_id: 12 }],
      }],
    })).toThrow()
  })
})

describe('business journey detail schema', () => {
  it('parses the unified journey and full primary opportunity envelope', () => {
    const parsed = BusinessJourneyDetailResponseSchema.parse({
      journey: listItem,
      primary_opportunity: detailOpportunity,
    })

    expect(parsed.journey.public_id).toBe(journeyPublicId)
    expect(parsed.primary_opportunity?.customer_name).toBe('示例科技')
  })

  it('accepts a null full primary opportunity', () => {
    const parsed = BusinessJourneyDetailResponseSchema.parse({
      journey: { ...listItem, primary_opportunity: null },
      primary_opportunity: null,
    })

    expect(parsed.primary_opportunity).toBeNull()
  })
})

describe('dealJourneyApi page projections', () => {
  beforeEach(() => {
    requestGet.mockReset()
  })

  it('calls the unified list, board, and owner option endpoints', async () => {
    requestGet
      .mockResolvedValueOnce({ items: [listItem], total: 1, page: 1, page_size: 20, total_pages: 1 })
      .mockResolvedValueOnce({
        columns: [],
        summary: { total_count: 0, total_amount: 0, active_count: 0, completed_count: 0, lost_count: 0 },
        truncated: false,
      })
      .mockResolvedValueOnce({ data: [{ id: '7', name: '王小明', is_me: true }] })

    await dealJourneyApi.list({ skip: 0, limit: 20, tab: 'all' })
    expect(requestGet).toHaveBeenCalledWith('/v1/business-journeys', {
      params: { skip: 0, limit: 20, tab: 'all' },
    })

    await dealJourneyApi.getBoard({ tab: 'active' })
    expect(requestGet).toHaveBeenCalledWith('/v1/business-journeys/board', {
      params: { tab: 'active' },
    })

    await dealJourneyApi.getOwnerFilterOptions()
    expect(requestGet).toHaveBeenCalledWith('/v1/business-journeys/owner-options')
  })

  it('calls the unified detail endpoint and parses its envelope', async () => {
    requestGet.mockResolvedValue({
      journey: listItem,
      primary_opportunity: detailOpportunity,
    })

    const detail = await dealJourneyApi.getDetail(journeyPublicId)

    expect(requestGet).toHaveBeenCalledWith(`/v1/business-journeys/${journeyPublicId}`)
    expect(detail.primary_opportunity?.public_id).toBe(opportunityPublicId)
    const normalizedOpportunity: Opportunity | null = detail.primary_opportunity
    expect(normalizedOpportunity?.deal_journey_id).toBe(journeyPublicId)
  })
})
