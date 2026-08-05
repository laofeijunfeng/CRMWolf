import type { RouteLocationRaw } from 'vue-router'

export const isCustomerPublicId = (customerId: string): boolean => customerId.startsWith('cus_')

export const customerDetailRoute = (
  customerId: string,
  query: Record<string, string> = {}
): RouteLocationRaw => {
  if (!isCustomerPublicId(customerId)) {
    throw new Error(`Customer detail route requires customer public_id, got "${customerId}"`)
  }

  return {
    path: '/customers',
    query: {
      customerId,
      ...query,
    },
  }
}
