import type { DealJourneyBoardStage } from '@/schemas/dealJourney'
import { getStatusPresentation, type StatusTone } from '@/utils/statusPresentation'

export const businessJourneyStageTone = (stage: DealJourneyBoardStage): StatusTone =>
  getStatusPresentation('businessJourney', stage).tone

export const isBusinessJourneyEndStage = (stage: DealJourneyBoardStage): boolean =>
  businessJourneyStageTone(stage) !== 'neutral'
