import { describe, expect, it } from 'vitest'
import { useDetailContextStack } from '@/composables/useDetailContextStack'
import type { DetailContextNode } from '@/types/detailContext'

const node = (type: DetailContextNode['type'], id: string): DetailContextNode => ({
  type,
  id,
  label: `${type}-${id}`,
  source: 'related-object'
})

describe('useDetailContextStack', () => {
  it('keeps a bounded path and returns to the previous object with pop', () => {
    const stack = useDetailContextStack(3)
    stack.push(node('customer', 'cus-1'))
    stack.push(node('opportunity', 'opp-1'))
    stack.push(node('contract', 'contract-1'))
    stack.push(node('payment-plan', 'plan-1'))

    expect(stack.nodes.value.map(item => item.type)).toEqual(['opportunity', 'contract', 'payment-plan'])
    expect(stack.current.value?.id).toBe('plan-1')
    expect(stack.canGoBack.value).toBe(true)

    stack.pop()
    expect(stack.current.value?.type).toBe('contract')
  })

  it('truncates the forward path when navigating to an existing context', () => {
    const stack = useDetailContextStack()
    stack.reset([node('customer', 'cus-1'), node('opportunity', 'opp-1'), node('contract', 'contract-1')])

    stack.push(node('opportunity', 'opp-1'))

    expect(stack.nodes.value.map(item => item.type)).toEqual(['customer', 'opportunity'])
    expect(stack.depth.value).toBe(2)
  })

  it('does not pop the root and closes the whole path explicitly', () => {
    const stack = useDetailContextStack()
    stack.push(node('customer', 'cus-1'))

    stack.pop()
    expect(stack.nodes.value).toHaveLength(1)
    expect(stack.current.value?.type).toBe('customer')

    stack.closeRoot()
    expect(stack.nodes.value).toHaveLength(0)
    expect(stack.current.value).toBeNull()
  })
})
