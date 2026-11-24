import { describe, expect, it } from 'vitest'
import {
  DEAL_JOURNEY_BOARD_STAGE_LABELS,
  isDealJourneyPublicId
} from '@/utils/dealJourney'

describe('dealJourney', () => {
  it('accepts djy public ids only', () => {
    expect(isDealJourneyPublicId(`djy_${'a'.repeat(32)}`)).toBe(true)
    expect(isDealJourneyPublicId('12')).toBe(false)
    expect(isDealJourneyPublicId(`opp_${'a'.repeat(32)}`)).toBe(false)
  })

  it('uses board Chinese labels', () => {
    expect(DEAL_JOURNEY_BOARD_STAGE_LABELS).toEqual({
      early_communication: '初期交流',
      active_progress: '持续推进',
      closing_soon: '即将签约',
      contract_processing: '签约中',
      payment_processing: '回款中',
      invoice_processing: '开票中',
      completed: '已完成',
      lost: '已输单',
      approval_rejected: '已驳回'
    })
  })
})
