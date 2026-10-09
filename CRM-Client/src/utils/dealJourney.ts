export type DealJourneyBoardStage =
  | 'early_communication'
  | 'active_progress'
  | 'closing_soon'
  | 'contract_processing'
  | 'payment_processing'
  | 'invoice_processing'
  | 'completed'
  | 'lost'

const DEAL_JOURNEY_PUBLIC_ID_PATTERN = /^djy_[0-9a-f]{32}$/

const DEAL_JOURNEY_PROGRESS_PERCENT: Record<DealJourneyBoardStage, number> = {
  early_communication: 14,
  active_progress: 29,
  closing_soon: 43,
  contract_processing: 57,
  payment_processing: 71,
  invoice_processing: 86,
  completed: 100,
  lost: 0
}

export const DEAL_JOURNEY_BOARD_STAGE_LABELS: Record<DealJourneyBoardStage, string> = {
  early_communication: '初期交流',
  active_progress: '持续推进',
  closing_soon: '即将签约',
  contract_processing: '签约中',
  payment_processing: '回款中',
  invoice_processing: '开票中',
  completed: '已完成',
  lost: '已输单'
}

export function isDealJourneyPublicId(value: string): boolean {
  return DEAL_JOURNEY_PUBLIC_ID_PATTERN.test(value)
}

export function dealJourneyProgressPercent(stage: DealJourneyBoardStage): number {
  return DEAL_JOURNEY_PROGRESS_PERCENT[stage]
}

export type DealJourneyProgressColorClass =
  | 'bg-orange-500'
  | 'bg-amber-500'
  | 'bg-yellow-500'
  | 'bg-lime-500'
  | 'bg-green-500'
  | 'bg-emerald-500'
  | 'bg-teal-500'
  | 'bg-cyan-500'
  | 'bg-sky-500'
  | 'bg-blue-500'

export function dealJourneyProgressColorClass(percent: number): DealJourneyProgressColorClass {
  if (percent <= 10) return 'bg-orange-500'
  if (percent <= 20) return 'bg-amber-500'
  if (percent <= 30) return 'bg-yellow-500'
  if (percent <= 40) return 'bg-lime-500'
  if (percent <= 50) return 'bg-green-500'
  if (percent <= 60) return 'bg-emerald-500'
  if (percent <= 70) return 'bg-teal-500'
  if (percent <= 80) return 'bg-cyan-500'
  if (percent <= 90) return 'bg-sky-500'
  return 'bg-blue-500'
}
