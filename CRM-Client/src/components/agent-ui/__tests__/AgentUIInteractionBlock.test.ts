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

it('renders confirmation facts above confirm and cancel', () => {
  const block = InteractionBlockSchema.parse({
    id: 'b_lead_confirmation_facts',
    type: 'interaction',
    interaction_id: 'int_lead_confirmation_facts',
    interaction_type: 'confirmation',
    selection_mode: 'single',
    submit_on_select: true,
    state: 'ACTIVE',
    prompt: '确认要创建线索“协鑫数智科技”并记录首次跟进吗?',
    fields: [],
    facts: [
      { key: 'lead_name', label: '线索名称', value: '协鑫数智科技' },
      { key: 'follow_up_method', label: '跟进方式', value: '其他' },
    ],
    options: [
      { value: 'confirm', label: '确认创建', description: null, disabled: false },
      { value: 'cancel', label: '取消', description: null, disabled: false },
    ],
    submit_label: '确认',
    submit_action_id: 'act_lead_confirmation_facts',
  })

  const wrapper = mount(AgentUIInteractionBlock, { props: { block } })
  const facts = wrapper.get('[data-agent-ui-confirmation-facts]')
  expect(facts.text()).toContain('线索名称')
  expect(facts.text()).toContain('协鑫数智科技')
  expect(facts.text()).toContain('跟进方式')
  expect(facts.text()).toContain('其他')
  expect(wrapper.findAll('button')).toHaveLength(2)
})

const followUpContentBlock = {
  id: 'b_follow_up_content',
  type: 'interaction' as const,
  interaction_id: 'int_follow_up_content',
  interaction_type: 'text_input' as const,
  business_action: 'provide_follow_up_content',
  allow_cancel: true,
  state: 'ACTIVE' as const,
  prompt: '请补充本次客户跟进的具体内容。',
  allow_blank: false,
  fields: [{
    key: 'text',
    label: '补充跟进内容',
    field_type: 'textarea' as const,
    required: true,
    default_value: '',
    min_length: 1,
    max_length: 10000,
    options: [],
  }],
  options: [],
  submit_label: '继续',
  submit_action_id: 'act_follow_up_content',
}

it('cancels a signed follow-up prompt with required text empty and locks both actions', async () => {
  const block = InteractionBlockSchema.parse(followUpContentBlock)
  const wrapper = mount(AgentUIInteractionBlock, { props: { block } })
  const buttons = wrapper.findAll('button')

  expect(buttons.map(button => button.text())).toEqual(['取消', '继续'])
  await buttons[0]?.trigger('click')

  expect(wrapper.emitted('submit')).toEqual([['act_follow_up_content', { cancel: true }]])
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  expect(wrapper.findAll('button').every(button => button.attributes('disabled') !== undefined)).toBe(true)
  await wrapper.findAll('button')[0]?.trigger('click')
  await wrapper.findAll('button')[1]?.trigger('click')
  expect(wrapper.emitted('submit')).toEqual([['act_follow_up_content', { cancel: true }]])
})

it('does not offer follow-up cancellation without both the signed permission and matching action', () => {
  for (const changes of [
    { allow_cancel: undefined, business_action: 'provide_follow_up_content' },
    { allow_cancel: false, business_action: 'provide_follow_up_content' },
    { allow_cancel: true, business_action: undefined },
    { allow_cancel: true, business_action: 'supplement_follow_up_quality' },
    { allow_cancel: true, business_action: 'provide_lead_fields' },
  ]) {
    const block = InteractionBlockSchema.parse({ ...followUpContentBlock, ...changes })
    const wrapper = mount(AgentUIInteractionBlock, { props: { block } })
    expect(wrapper.findAll('button').map(button => button.text())).toEqual(['继续'])
  }
})

it('permits cancellation of a signed follow-up form without validating required fields', async () => {
  const block = InteractionBlockSchema.parse({
    ...followUpContentBlock,
    interaction_type: 'form',
    allow_blank: undefined,
  })
  const wrapper = mount(AgentUIInteractionBlock, { props: { block } })

  expect(wrapper.findAll('button').map(button => button.text())).toEqual(['取消', '继续'])
  await wrapper.findAll('button')[0]?.trigger('click')
  expect(wrapper.emitted('submit')).toEqual([['act_follow_up_content', { cancel: true }]])
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
})

it('still validates required follow-up text for normal submission', async () => {
  const block = InteractionBlockSchema.parse(followUpContentBlock)
  const wrapper = mount(AgentUIInteractionBlock, { props: { block } })

  await wrapper.findAll('button')[1]?.trigger('click')
  expect(wrapper.emitted('submit')).toBeUndefined()
  expect(wrapper.get('[role="alert"]').text()).toContain('请填写补充跟进内容')
  await wrapper.get('textarea').setValue('与客户确定下周会议时间')
  await wrapper.findAll('button')[1]?.trigger('click')
  expect(wrapper.emitted('submit')).toEqual([['act_follow_up_content', { text: '与客户确定下周会议时间' }]])
})

it('does not offer cancellation for another action form even when the block says it is allowed', () => {
  const block = InteractionBlockSchema.parse({
    ...followUpContentBlock,
    interaction_type: 'form',
    business_action: 'provide_lead_fields',
    allow_blank: undefined,
  })
  const wrapper = mount(AgentUIInteractionBlock, { props: { block } })
  expect(wrapper.findAll('button').map(button => button.text())).toEqual(['继续'])
})

it('keeps the follow-up prompt retryable after a failed cancellation and consumes it after success', async () => {
  const block = InteractionBlockSchema.parse(followUpContentBlock)
  const wrapper = mount(AgentUIInteractionBlock, { props: { block } })
  await wrapper.get('textarea').setValue('尚待确认的跟进记录')

  await wrapper.findAll('button')[0]?.trigger('click')
  await wrapper.setProps({ locked: true })
  await wrapper.setProps({ locked: false })
  expect(wrapper.findAll('button').every(button => button.attributes('disabled') === undefined)).toBe(true)
  expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('尚待确认的跟进记录')

  await wrapper.findAll('button')[0]?.trigger('click')
  expect(wrapper.emitted('submit')).toEqual([
    ['act_follow_up_content', { cancel: true }],
    ['act_follow_up_content', { cancel: true }],
  ])

  await wrapper.setProps({ block: InteractionBlockSchema.parse({
    ...followUpContentBlock,
    state: 'CANCELLED',
    submit_action_id: null,
  }) })
  expect(wrapper.text()).toContain('已取消')
  expect(wrapper.find('textarea').exists()).toBe(true)
  expect(wrapper.findAll('button')).toHaveLength(0)
})

it('does not reopen a submitted confirmation when its parent releases a transient lock', async () => {
  const block = InteractionBlockSchema.parse({
    id: 'confirmation_retry', type: 'interaction', interaction_id: 'int_confirmation_retry',
    interaction_type: 'confirmation', state: 'ACTIVE', prompt: '确认创建？', fields: [],
    options: [{ value: 'confirm', label: '确认', disabled: false }, { value: 'cancel', label: '取消', disabled: false }],
    selection_mode: 'single', submit_action_id: 'act_confirmation_retry',
  })
  const wrapper = mount(AgentUIInteractionBlock, { props: { block } })

  await wrapper.findAll('button')[0]?.trigger('click')
  await wrapper.setProps({ locked: true })
  await wrapper.setProps({ locked: false })
  expect(wrapper.findAll('button').every(button => button.attributes('disabled') !== undefined)).toBe(true)
  await wrapper.findAll('button')[1]?.trigger('click')
  expect(wrapper.emitted('submit')).toEqual([['act_confirmation_retry', { choice: 'confirm' }]])
})
