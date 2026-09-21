import type { DealJourneyBoardStage } from '@/schemas/dealJourney'

export interface BusinessJourneyStagePresentation {
  columnClass: string
  badgeClass: string
  emphasisBadgeClass: string
}

export const businessJourneyStagePresentation: Record<
  DealJourneyBoardStage,
  BusinessJourneyStagePresentation
> = {
  early_communication: {
    columnClass: 'business-board-stage--sky',
    badgeClass: 'bg-sky-50 text-sky-700 border-sky-100',
    emphasisBadgeClass: 'bg-sky-600 text-white border-transparent'
  },
  active_progress: {
    columnClass: 'business-board-stage--blue',
    badgeClass: 'bg-blue-50 text-blue-700 border-blue-100',
    emphasisBadgeClass: 'bg-blue-600 text-white border-transparent'
  },
  closing_soon: {
    columnClass: 'business-board-stage--emerald',
    badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-100',
    emphasisBadgeClass: 'bg-emerald-600 text-white border-transparent'
  },
  contract_processing: {
    columnClass: 'business-board-stage--violet',
    badgeClass: 'bg-violet-50 text-violet-700 border-violet-100',
    emphasisBadgeClass: 'bg-violet-600 text-white border-transparent'
  },
  payment_processing: {
    columnClass: 'business-board-stage--amber',
    badgeClass: 'bg-amber-50 text-amber-700 border-amber-100',
    emphasisBadgeClass: 'bg-amber-600 text-white border-transparent'
  },
  invoice_processing: {
    columnClass: 'business-board-stage--cyan',
    badgeClass: 'bg-cyan-50 text-cyan-700 border-cyan-100',
    emphasisBadgeClass: 'bg-cyan-600 text-white border-transparent'
  },
  completed: {
    columnClass: 'business-board-stage--slate',
    badgeClass: 'bg-slate-50 text-slate-700 border-slate-100',
    emphasisBadgeClass: 'bg-slate-600 text-white border-transparent'
  },
  lost: {
    columnClass: 'business-board-stage--rose',
    badgeClass: 'bg-rose-50 text-rose-700 border-rose-100',
    emphasisBadgeClass: 'bg-rose-600 text-white border-transparent'
  }
}
