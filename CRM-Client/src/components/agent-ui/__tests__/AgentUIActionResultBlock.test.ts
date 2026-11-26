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

describe('AgentUIActionResultBlock customer line', () => {
  const customer = { ref_id: 'ref-cus', resource: 'customer' as const, public_id: 'cus_1', display_name: '睿狐科技', result_set_id: null }
  const created = (subject: typeof customer | { ref_id: string, resource: 'payment', public_id: string, display_name: string, result_set_id: null }): Extract<AgentUIBlock, { type: 'action_result' }> => ({
    id: 'result-deployment',
    type: 'action_result',
    action_id: 'action-deployment',
    status: 'SUCCESS',
    title: '部署信息已创建',
    message: '客户：睿狐科技\n部署方式：私有化',
    entity_ref: { ref_id: 'ref-dep', resource: 'opportunity', public_id: 'opp_1', display_name: '部署信息', result_set_id: null },
    subject
  })

  it('makes the customer name itself the only link', async () => {
    const wrapper = mount(AgentUIActionResultBlock, { props: { block: created(customer) } })

    const buttons = wrapper.findAll('button')
    expect(buttons.map(button => button.text())).toEqual(['睿狐科技'])
    expect(buttons[0]?.element.closest('p')?.textContent?.trim()).toBe('客户：睿狐科技')
    await buttons[0]?.trigger('click')
    expect(wrapper.emitted('open-entity')).toEqual([[customer]])
  })

  it('keeps an unopenable customer as plain text without a second row', () => {
    const wrapper = mount(AgentUIActionResultBlock, {
      props: { block: created({ ...customer, resource: 'payment' }) }
    })

    expect(wrapper.find('button').exists()).toBe(false)
    expect(wrapper.text().match(/睿狐科技/g)).toEqual(['睿狐科技'])
    expect(wrapper.text()).not.toContain('部署信息部署')
  })
})
