import type { LocationQueryRaw, RouteLocationRaw } from 'vue-router'

export const isCustomerPublicId = (customerId: string): boolean => customerId.startsWith('cus_')

export interface CustomerDetailRouteQuery extends LocationQueryRaw {
  tab?: string
  journeyId?: string
  opportunityId?: string
}

/**
 * Opens /customers with customerId in the query.
 * Optional keys: tab ('journeys' | leftover 'opportunities' | other panels),
 * journeyId (djy_ + 32 hex), leftover opportunityId.
 */
export const customerDetailRoute = (
  customerId: string,
  query: CustomerDetailRouteQuery = {}
): RouteLocationRaw => {
  if (!isCustomerPublicId(customerId)) {
    throw new Error(`Customer detail route requires customer public_id, got "${customerId}"`)
  }

  return {
    path: '/customers',
    query: {
      ...query,
      customerId,
    },
  }
}
