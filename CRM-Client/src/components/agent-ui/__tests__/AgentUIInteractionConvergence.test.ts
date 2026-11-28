import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'

import { InteractionBlockSchema } from '@/schemas/agent-contracts'

import AgentUIInteractionBlock from '../AgentUIInteractionBlock.vue'

const activityBlock = {
  id: 'b_activity_confirm',
  type: 'interaction',
  interaction_id: 'ix_activity_confirm',
  interaction_type: 'confirmation',
  business_action: 'confirm_activity_write',
  prompt: '确认后写入这条客户活动？',
  fields: [],
  facts: [
    { key: 'customer', label: '客户', value: '通力电梯', group: 'write' },
    { key: 'summary', label: '摘要', value: '电话沟通了二期电梯维保续约。', group: 'write' },
  ],
  options: [
    { value: 'confirm', label: '确认写入', disabled: false },
    { value: 'cancel', label: '取消', disabled: false },
  ],
  selection_mode: 'single',
  submit_on_select: true,
}

it('collapses the activity confirmation card to a one-line summary once the server reports it submitted', async () => {
  const wrapper = mount(AgentUIInteractionBlock, {
    props: { block: InteractionBlockSchema.parse({ ...activityBlock, state: 'ACTIVE', submit_action_id: 'act_confirm' }) },
  })
  const confirm = wrapper.findAll('button').find(button => button.text() === '确认写入')
  expect(confirm).toBeDefined()
  await confirm?.trigger('click')
  expect(wrapper.emitted('submit')).toEqual([['act_confirm', { choice: 'confirm' }]])

  await wrapper.setProps({
    block: InteractionBlockSchema.parse({
      ...activityBlock, state: 'SUBMITTED', submit_action_id: null, submitted_values: { choice: 'confirm' },
    }),
  })

  const summary = wrapper.get('[data-agent-ui-submitted-choice]')
  expect(summary.text()).toBe('确认写入客户活动 · 已选「确认写入」 · 通力电梯')
  expect(summary.classes()).toContain('truncate')
  expect(summary.attributes('title')).toBe('确认写入客户活动 · 已选「确认写入」 · 通力电梯')
  expect(wrapper.findAll('button')).toHaveLength(0)
  expect(wrapper.text()).not.toContain('电话沟通了二期电梯维保续约。')
  expect(wrapper.text()).toContain('已处理')
})
