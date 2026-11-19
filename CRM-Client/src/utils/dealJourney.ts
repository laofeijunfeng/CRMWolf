export type DealJourneyBoardStage =
  | 'early_communication'
  | 'active_progress'
  | 'closing_soon'
  | 'contract_processing'
  | 'payment_processing'
  | 'invoice_processing'
  | 'completed'
  | 'lost'
  | 'approval_rejected'

const DEAL_JOURNEY_PUBLIC_ID_PATTERN = /^djy_[0-9a-f]{32}$/


export const DEAL_JOURNEY_BOARD_STAGE_LABELS: Record<DealJourneyBoardStage, string> = {
  early_communication: '初期交流',
  active_progress: '持续推进',
  closing_soon: '即将签约',
  contract_processing: '签约中',
  payment_processing: '回款中',
  invoice_processing: '开票中',
  completed: '已完成',
  lost: '已输单',
  approval_rejected: '审批未通过'
}

export function isDealJourneyPublicId(value: string): boolean {
  return DEAL_JOURNEY_PUBLIC_ID_PATTERN.test(value)
}
