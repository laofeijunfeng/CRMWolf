import { describe, expect, it } from 'vitest'
import {
  DEAL_JOURNEY_BOARD_STAGE_LABELS,
  dealJourneyProgressPercent,
  isDealJourneyPublicId
} from '@/utils/dealJourney'

describe('dealJourney', () => {
  it('accepts djy public ids only', () => {
    expect(isDealJourneyPublicId(`djy_${'a'.repeat(32)}`)).toBe(true)
    expect(isDealJourneyPublicId('12')).toBe(false)
    expect(isDealJourneyPublicId(`opp_${'a'.repeat(32)}`)).toBe(false)
  })

  it('maps board stages to hover progress', () => {
    expect(dealJourneyProgressPercent('early_communication')).toBe(14)
    expect(dealJourneyProgressPercent('active_progress')).toBe(29)
    expect(dealJourneyProgressPercent('closing_soon')).toBe(43)
    expect(dealJourneyProgressPercent('contract_processing')).toBe(57)
    expect(dealJourneyProgressPercent('payment_processing')).toBe(71)
    expect(dealJourneyProgressPercent('invoice_processing')).toBe(86)
    expect(dealJourneyProgressPercent('completed')).toBe(100)
    expect(dealJourneyProgressPercent('lost')).toBe(0)
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
      lost: '已输单'
    })
  })
})
