import type { RouteLocationRaw } from 'vue-router'

import type { EntityRef } from '@/schemas/agent-contracts'
import { customerDetailRoute } from '@/utils/customerRoutes'
import { isOpportunityPublicId } from '@/utils/opportunityRoutes'

/**
 * Agent only turns references into buttons when the host shell has a stable
 * detail surface for that resource. Other references stay readable so that a
 * missing deep-link target never looks like a broken click action.
 */
export const isAgentEntityOpenable = (entityRef: Pick<EntityRef, 'resource'>): boolean => (
  entityRef.resource === 'customer'
  || entityRef.resource === 'opportunity'
  || entityRef.resource === 'contract'
)

/**
 * Contract detail APIs currently use the numeric database id while Agent
 * references intentionally use strings. Keep the conversion strict and
 * bounded so malformed or unsafe ids cannot silently open the wrong record.
 */
export const parseAgentContractId = (publicId: string): number | null => {
  const normalized = publicId.trim()
  if (!/^\d+$/.test(normalized)) return null

  const parsed = Number(normalized)
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null
}

const isCustomerEntityId = (value: unknown): value is string =>
  typeof value === 'string' && /^cus_[0-9a-f]{32}$/.test(value)

/** Routes only references bound to a customer by the server. */
export const assistantEntityDetailRoute = (ref: EntityRef): RouteLocationRaw | null => {
  if (ref.resource === 'customer' && isCustomerEntityId(ref.public_id)) {
    return customerDetailRoute(ref.public_id)
  }
  if (ref.resource === 'opportunity' && isOpportunityPublicId(ref.public_id)) {
    const customerId = ref.attributes?.['customer_public_id']
    if (isCustomerEntityId(customerId)) {
      return customerDetailRoute(customerId, { tab: 'opportunities', opportunityId: ref.public_id })
    }
  }
  return null
}
