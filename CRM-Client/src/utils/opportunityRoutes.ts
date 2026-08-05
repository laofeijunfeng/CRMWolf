const OPPORTUNITY_PUBLIC_ID_PATTERN = /^opp_[0-9a-f]{32}$/

export const isOpportunityPublicId = (opportunityId: string): boolean =>
  OPPORTUNITY_PUBLIC_ID_PATTERN.test(opportunityId)
