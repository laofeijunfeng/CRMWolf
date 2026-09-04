import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { InteractionBlockSchema } from '@/schemas/agent-contracts'

import AgentUIInteractionBlock from '../AgentUIInteractionBlock.vue'

describe('AgentUIInteractionBlock', () => {
  it('renders the server-defined submit button label', () => {
    const block = InteractionBlockSchema.parse({
      id: 'b_interaction_form',
      type: 'interaction',
      interaction_id: 'int_form',
      interaction_type: 'form',
      state: 'ACTIVE',
      prompt: '请补充信息。',
      fields: [
        {
          key: 'note',
          label: '说明',
          field_type: 'textarea',
          required: true,
          default_value: '',
          min_length: 1,
          max_length: 100,
          options: []
        }
      ],
      options: [],
      submit_label: '确认创建',
      submit_action_id: 'act_submit_form'
    })

    const wrapper = mount(AgentUIInteractionBlock, { props: { block } })

    expect(wrapper.get('button').text()).toBe('确认创建')
  })
})

it('submits the protocol choice value rather than the display label', async () => {
  const block = InteractionBlockSchema.parse({
    id: 'b_interaction_choice',
    type: 'interaction',
    interaction_id: 'int_choice',
    interaction_type: 'choice',
    selection_mode: 'single',
    min_selections: 1,
    max_selections: 1,
    submit_on_select: true,
    state: 'ACTIVE',
    prompt: '是否创建商机？',
    fields: [],
    options: [
      { value: 'confirm', label: '是', description: null, disabled: false },
      { value: 'cancel', label: '否', description: null, disabled: false },
    ],
    submit_label: '提交',
    submit_action_id: 'act_opportunity_choice',
  })

  const wrapper = mount(AgentUIInteractionBlock, { props: { block } })
  await wrapper.get('button').trigger('click')

  expect(wrapper.emitted('submit')).toEqual([
    ['act_opportunity_choice', { choice: 'confirm' }],
  ])
  expect(wrapper.find('form').exists()).toBe(false)
})

it('renders submitted text input as immutable text instead of an empty editor', () => {
  const submittedText = '已与河南双汇技术经理沟通 POC 部署，等待确认具体时间。'
  const block = InteractionBlockSchema.parse({
    id: 'b_follow_up_detail',
    type: 'interaction',
    interaction_id: 'int_follow_up_detail',
    interaction_type: 'text_input',
    state: 'SUBMITTED',
    prompt: '请补充跟进信息',
    allow_blank: false,
    fields: [
      {
        key: 'text',
        label: '补充跟进信息',
        field_type: 'textarea',
        required: true,
        default_value: '',
        min_length: 1,
        max_length: 10000,
        options: [],
      },
    ],
    options: [],
    submit_label: '提交',
    submit_action_id: null,
    submitted_values: { text: submittedText },
  })

  const wrapper = mount(AgentUIInteractionBlock, { props: { block } })

  expect(wrapper.text()).toContain(`补充跟进信息：${submittedText}`)
  expect(wrapper.text()).toContain('已提交')
  expect(wrapper.find('textarea').exists()).toBe(false)
  expect(wrapper.find('button').exists()).toBe(false)
})

it('highlights only the selected choice instead of the first option', async () => {
  const block = InteractionBlockSchema.parse({
    id: 'b_opportunity_confirmation',
    type: 'interaction',
    interaction_id: 'int_opportunity_confirmation',
    interaction_type: 'confirmation',
    selection_mode: 'single',
    state: 'ACTIVE',
    prompt: '是否推进商机？',
    fields: [],
    options: [
      { value: 'confirm', label: '是', description: null, disabled: false },
      { value: 'cancel', label: '否', description: null, disabled: false },
    ],
    submit_label: '提交',
    submit_action_id: 'act_opportunity_confirmation',
  })

  const wrapper = mount(AgentUIInteractionBlock, { props: { block } })
  const buttons = wrapper.findAll('button')

  expect(buttons[0]?.attributes('aria-pressed')).toBe('false')
  expect(buttons[1]?.attributes('aria-pressed')).toBe('false')
  expect(buttons[0]?.classes()).not.toContain('bg-primary')

  await buttons[1]?.trigger('click')

  expect(buttons[0]?.attributes('aria-pressed')).toBe('false')
  expect(buttons[1]?.attributes('aria-pressed')).toBe('true')
  expect(buttons[0]?.classes()).not.toContain('bg-primary')
  expect(buttons[1]?.classes()).toContain('bg-accent')
})

it('submits a confirmation immediately when the signed contract opts in', async () => {
  const block = InteractionBlockSchema.parse({
    id: 'b_opportunity_confirmation_submit',
    type: 'interaction',
    interaction_id: 'int_opportunity_confirmation_submit',
    interaction_type: 'confirmation',
    selection_mode: 'single',
    submit_on_select: true,
    state: 'ACTIVE',
    prompt: '是否推进商机？',
    fields: [],
    options: [
      { value: 'confirm', label: '是', description: null, disabled: false },
      { value: 'cancel', label: '否', description: null, disabled: false },
    ],
    submit_label: '提交',
    submit_action_id: 'act_opportunity_confirmation_submit',
  })

  const wrapper = mount(AgentUIInteractionBlock, { props: { block } })
  await wrapper.findAll('button')[1]?.trigger('click')

  expect(wrapper.emitted('submit')).toEqual([
    ['act_opportunity_confirmation_submit', { choice: 'cancel' }],
  ])
})

it('renders a submitted choice as immutable text and keeps the final choice visible', () => {
  const block = InteractionBlockSchema.parse({
    id: 'b_opportunity_confirmation_submitted',
    type: 'interaction',
    interaction_id: 'int_opportunity_confirmation_submitted',
    interaction_type: 'confirmation',
    selection_mode: 'single',
    state: 'SUBMITTED',
    prompt: '是否推进商机？',
    fields: [],
    options: [
      { value: 'confirm', label: '是', description: null, disabled: false },
      { value: 'cancel', label: '否', description: null, disabled: false },
    ],
    submit_label: '提交',
    submit_action_id: null,
    submitted_values: { choice: 'cancel' },
  })

  const wrapper = mount(AgentUIInteractionBlock, { props: { block } })

  expect(wrapper.get('[data-agent-ui-submitted-choice]').text()).toContain('已选择：否')
  expect(wrapper.text()).toContain('已提交')
  expect(wrapper.findAll('button')).toHaveLength(0)
})
