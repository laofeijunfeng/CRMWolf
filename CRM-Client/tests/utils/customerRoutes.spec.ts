import { describe, expect, it } from 'vitest'
import { customerDetailRoute } from '@/utils/customerRoutes'

describe('customerDetailRoute', () => {
  it('opens the customer detail sheet through the customers query route', () => {
    expect(customerDetailRoute('cus_9bc8995abc6042aca357ca28bddf8e08')).toEqual({
      path: '/customers',
      query: {
        customerId: 'cus_9bc8995abc6042aca357ca28bddf8e08',
      },
    })
  })

  it('preserves extra customer detail query state', () => {
    expect(customerDetailRoute('cus_9bc8995abc6042aca357ca28bddf8e08', { tab: 'license-management' })).toEqual({
      path: '/customers',
      query: {
        customerId: 'cus_9bc8995abc6042aca357ca28bddf8e08',
        tab: 'license-management',
      },
    })
  })

  it('rejects legacy internal customer ids', () => {
    expect(() => customerDetailRoute('158')).toThrow('Customer detail route requires customer public_id')
  })
})
