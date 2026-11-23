import { describe, expect, it } from 'vitest'

import { assistantEntityDetailRoute, isAgentEntityOpenable, parseAgentContractId } from '../agentEntityNavigation'

describe('agent entity navigation', () => {
  it('only enables resources with a stable Agent detail surface', () => {
    expect(isAgentEntityOpenable({ resource: 'customer' })).toBe(true)
    expect(isAgentEntityOpenable({ resource: 'opportunity' })).toBe(true)
    expect(isAgentEntityOpenable({ resource: 'contract' })).toBe(true)
    expect(isAgentEntityOpenable({ resource: 'payment' })).toBe(false)
    expect(isAgentEntityOpenable({ resource: 'customer_activity' })).toBe(false)
  })

  it('strictly converts numeric contract public ids', () => {
    expect(parseAgentContractId('42')).toBe(42)
    expect(parseAgentContractId(' 42 ')).toBe(42)
    expect(parseAgentContractId('contract-42')).toBeNull()
    expect(parseAgentContractId('0')).toBeNull()
    expect(parseAgentContractId('9007199254740992')).toBeNull()
  })
})

describe('sales assistant receipt navigation', () => {
  const customerId = `cus_${'a'.repeat(32)}`
  const opportunityId = `opp_${'b'.repeat(32)}`
  const customer = { resource: 'customer' as const, public_id: customerId, display_name: '客户', ref_id: 'customer-ref' }
  const opportunity = { resource: 'opportunity' as const, public_id: opportunityId, display_name: '商机', ref_id: 'opportunity-ref' }

  it('opens the receipt customer and focuses the exact receipt opportunity', () => {
    expect(assistantEntityDetailRoute(customer)).toEqual({ path: '/customers', query: { customerId } })
    expect(assistantEntityDetailRoute({ ...opportunity, attributes: { customer_public_id: customerId } })).toEqual({
      path: '/customers', query: { customerId, tab: 'opportunities', opportunityId }
    })
  })

  it('does not infer a customer from a name, an approval ID, or a malformed public ID', () => {
    expect(assistantEntityDetailRoute({ ...customer, public_id: 'cus_wrong' })).toBeNull()
    expect(assistantEntityDetailRoute({ ...opportunity, display_name: customerId, attributes: { approval_id: 42 } })).toBeNull()
    expect(assistantEntityDetailRoute({ ...opportunity, public_id: '42', attributes: { customer_public_id: customerId } })).toBeNull()
  })
})
