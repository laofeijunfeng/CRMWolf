import { describe, expect, it } from 'vitest'

import { assistantEntityDetailRoute, assistantPageRoute, isAgentEntityOpenable, parseAgentContractId } from '../agentEntityNavigation'

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

describe('sales assistant page links', () => {
  const customerId = `cus_${'c'.repeat(32)}`
  const taskId = `fut_${'d'.repeat(32)}`

  it('routes a named page and keeps the customer scope the server bound', () => {
    expect(assistantPageRoute({ page: 'customers', label: '客户管理' })).toEqual({ path: '/customers' })
    expect(assistantPageRoute({ page: 'customers', label: '客户管理', customer_public_id: customerId })).toEqual({
      path: '/customers', query: { customerId }
    })
    expect(assistantPageRoute({ page: 'follow_up_tasks', label: '客户追踪', customer_public_id: customerId })).toEqual({
      name: 'CustomerTracking', query: { customerId }
    })
    expect(assistantPageRoute({ page: 'follow_up_tasks', label: '客户追踪' })).toEqual({ name: 'CustomerTracking' })
  })

  it('opens a follow-up task receipt at that task, scoped to its customer', () => {
    const task = {
      resource: 'follow_up_task' as const, public_id: taskId, display_name: '发方案', ref_id: `follow_up_task:${taskId}`,
      attributes: { customer_public_id: customerId },
    }
    expect(assistantEntityDetailRoute(task)).toEqual({ name: 'CustomerTracking', query: { customerId, taskId } })
    expect(isAgentEntityOpenable({ resource: 'follow_up_task' })).toBe(true)
    expect(assistantEntityDetailRoute({ ...task, attributes: null })).toBeNull()
  })

  it('opens an activity receipt on the customer activity panel', () => {
    const receipt = {
      resource: 'customer' as const, public_id: customerId, display_name: '客户', ref_id: `customer:${customerId}`,
      attributes: { customer_tab: 'activities' },
    }
    expect(assistantEntityDetailRoute(receipt)).toEqual({ path: '/customers', query: { customerId, tab: 'followup' } })
  })
})
