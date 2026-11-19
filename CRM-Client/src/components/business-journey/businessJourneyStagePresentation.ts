import type { DealJourneyBoardStage } from '@/schemas/dealJourney'

export type BusinessJourneyStageTone = 'neutral' | 'success' | 'warning' | 'danger'

/** 阶段只靠列标题与顺序表达；状态色只给结束态。 */
export const businessJourneyStageTone: Record<DealJourneyBoardStage, BusinessJourneyStageTone> = {
  early_communication: 'neutral',
  active_progress: 'neutral',
  closing_soon: 'neutral',
  contract_processing: 'neutral',
  payment_processing: 'neutral',
  invoice_processing: 'neutral',
  completed: 'success',
  lost: 'danger',
  approval_rejected: 'warning'
}

export const isBusinessJourneyEndStage = (stage: DealJourneyBoardStage): boolean =>
  businessJourneyStageTone[stage] !== 'neutral'
