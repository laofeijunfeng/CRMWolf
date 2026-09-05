import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { AgentUIBlock } from '@/schemas/agent-contracts'

import AgentUIEntityListBlock from '../AgentUIEntityListBlock.vue'

describe('AgentUIEntityListBlock', () => {
  const makeBlock = (resource: 'customer' | 'payment'): Extract<AgentUIBlock, { type: 'entity_list' }> => ({
    id: `list-${resource}`,
    type: 'entity_list',
    entity_type: resource,
    items: [{
      entity_ref: {
        ref_id: `ref-${resource}`,
        resource,
        public_id: '1',
        display_name: resource === 'customer' ? '客户 A' : '回款记录 1',
        result_set_id: null,
      },
    }],
    total: 1,
  })

  it('emits navigation for supported entity resources', async () => {
    const wrapper = mount(AgentUIEntityListBlock, { props: { block: makeBlock('customer') } })

    await wrapper.get('button').trigger('click')

    expect(wrapper.emitted('open-entity')).toHaveLength(1)
  })

  it('keeps unsupported resources readable without a misleading button', () => {
    const wrapper = mount(AgentUIEntityListBlock, { props: { block: makeBlock('payment') } })

    expect(wrapper.find('button').exists()).toBe(false)
    expect(wrapper.text()).toContain('回款记录 1')
  })
})
