import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { AgentUIBlock } from '@/schemas/agent-contracts'

import AgentUIActionResultBlock from '../AgentUIActionResultBlock.vue'

describe('AgentUIActionResultBlock', () => {
  const makeBlock = (resource: 'customer' | 'payment'): Extract<AgentUIBlock, { type: 'action_result' }> => ({
    id: `result-${resource}`,
    type: 'action_result',
    action_id: 'action-1',
    status: 'SUCCESS',
    title: '处理完成',
    message: '操作已完成',
    entity_ref: {
      ref_id: `ref-${resource}`,
      resource,
      public_id: '1',
      display_name: resource === 'customer' ? '客户 A' : '回款记录 1',
      result_set_id: null,
    },
  })

  it('emits navigation for a supported result entity', async () => {
    const wrapper = mount(AgentUIActionResultBlock, { props: { block: makeBlock('customer') } })

    await wrapper.get('button').trigger('click')

    expect(wrapper.emitted('open-entity')).toHaveLength(1)
  })

  it('does not make an unsupported result entity look clickable', () => {
    const wrapper = mount(AgentUIActionResultBlock, { props: { block: makeBlock('payment') } })

    expect(wrapper.find('button').exists()).toBe(false)
    expect(wrapper.text()).toContain('回款记录 1')
  })
})

  it('renders activity success facts once and does not repeat the title', () => {
    const wrapper = mount(AgentUIActionResultBlock, {
      props: {
        block: {
          id: 'result-activity',
          type: 'action_result',
          action_id: 'action-activity',
          status: 'SUCCESS',
          title: '活动已写入',
          message: '客户：上海期货信息技术有限公司\n活动类型：微信跟进\n下一步：11 月 15 日跟进付款'
        }
      }
    })

    expect(wrapper.text().match(/活动已写入/g)).toEqual(['活动已写入'])
    expect(wrapper.text()).toContain('客户：上海期货信息技术有限公司')
    expect(wrapper.text()).toContain('活动类型：微信跟进')
    expect(wrapper.text()).toContain('下一步：11 月 15 日跟进付款')
  })
