import { describe, expect, it } from 'vitest'

import { isAgentEntityOpenable, parseAgentContractId } from '../agentEntityNavigation'

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
