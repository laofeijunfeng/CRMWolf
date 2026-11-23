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
  expect(wrapper.text()).toContain('已处理')
  expect(wrapper.find('textarea').exists()).toBe(false)
  expect(wrapper.find('button').exists()).toBe(false)
})

it('submits the clicked confirmation choice even when the payload omits submit_on_select', async () => {
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

  // 取消在左、确认在右；没有默认选中，点哪个就提交哪个协议值。
  expect(buttons.map(button => button.text())).toEqual(['否', '是'])
  await buttons[0]?.trigger('click')
  expect(wrapper.emitted('submit')).toEqual([
    ['act_opportunity_confirmation', { choice: 'cancel' }],
  ])
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
  await wrapper.findAll('button').find(button => button.text() === '否')?.trigger('click')

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
  expect(wrapper.text()).toContain('已处理')
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
  const confirmButton = wrapper.findAll('button').find(button => button.text() === '确认')

  await confirmButton?.trigger('click')
  await wrapper.setProps({ locked: true })
  await wrapper.setProps({ locked: false })
  expect(wrapper.findAll('button').every(button => button.attributes('disabled') !== undefined)).toBe(true)
  await confirmButton?.trigger('click')
  expect(wrapper.emitted('submit')).toEqual([['act_confirmation_retry', { choice: 'confirm' }]])
})

it('shows every open follow-up and submits only the current three-way choice', async () => {
  const block = InteractionBlockSchema.parse({
    id: 'b_open_follow_up',
    type: 'interaction',
    interaction_id: 'int_open_follow_up',
    interaction_type: 'choice',
    business_action: 'settle_follow_up_disposition',
    presentation: 'OPEN_FOLLOW_UP_DISPOSITION',
    selection_mode: 'single',
    min_selections: 1,
    max_selections: 1,
    submit_on_select: true,
    state: 'ACTIVE',
    prompt: '还发现 2 条未完成的历史任务，请逐条处理。',
    fields: [],
    options: [
      { value: 'i1:complete', label: '已完成', description: '标记此任务完成', disabled: false },
      { value: 'i1:hold', label: '先放着', description: '保持未完成', disabled: false },
      { value: 'i1:skip', label: '不管了', description: '仅跳过本次', disabled: false },
    ],
    disposition_items: [
      {
        item_id: 'i1',
        title: '联系客户确认采购安排',
        owner_line: '负责人：我 · 计划 10 月 28 日',
        related: true,
        evidence_quote: '已和林女士核对采购安排',
        evidence_reason: '本次跟进与任务均明确提到“确认采购安排”，且属于同一客户。',
        state: 'current',
        result_title: null,
        result_message: null,
      },
      {
        item_id: 'i2',
        title: '补充安全测评报告',
        owner_line: '负责人：我 · 计划 11 月 2 日',
        related: false,
        evidence_quote: null,
        evidence_reason: null,
        state: 'waiting',
        result_title: null,
        result_message: null,
      },
    ],
    submit_label: '提交',
    submit_action_id: 'act_follow_up_1',
  })
  const wrapper = mount(AgentUIInteractionBlock, { props: { block } })

  expect(wrapper.text()).toContain('联系客户确认采购安排')
  expect(wrapper.text()).toContain('补充安全测评报告')
  expect(wrapper.text()).not.toContain('标记此任务完成')
  expect(wrapper.text()).not.toContain('本次跟进与任务均明确提到')
  const toggles = wrapper.findAll('[data-agent-ui-related-toggle]')
  expect(toggles).toHaveLength(1)
  expect(wrapper.find('[data-agent-ui-related-line]').exists()).toBe(false)
  await toggles[0]?.trigger('click')
  expect(toggles[0]?.attributes('aria-expanded')).toBe('true')
  expect(wrapper.findAll('[data-agent-ui-related-line]')).toHaveLength(1)
  expect(wrapper.get('[data-agent-ui-related-line]').text()).toContain('已和林女士核对采购安排')
  const complete = wrapper.findAll('button').find(button => button.text().includes('已完成'))
  await complete?.trigger('click')
  expect(wrapper.emitted('submit')).toEqual([
    ['act_follow_up_1', { choice: 'i1:complete' }],
  ])
})

it('splits a customer month segment from a dated sales follow-up', async () => {
  const block = InteractionBlockSchema.parse({
    id: 'b_interaction_activity',
    type: 'interaction',
    interaction_id: 'ix_activity',
    interaction_type: 'confirmation',
    business_action: 'confirm_activity_write',
    state: 'ACTIVE',
    prompt: '确认后写入这条客户活动？',
    fields: [],
    facts: [
      { key: 'customer', label: '客户', value: '通力电梯', group: 'write' },
      { key: 'summary', label: '摘要', value: '客户说下个月初付款，11 月 5 号跟进下付款进展。', group: 'write' },
      { key: 'next_action', label: '下一步', value: '跟进付款进展', group: 'write' },
      { key: 'customer_commitment', label: '客户承诺', value: '下个月初付款（模糊时间，未确定具体日期）', group: 'write' },
      { key: 'next_follow_time', label: '跟进时间', value: '2026-11-05（周四）09:00', group: 'write', status_label: '默认时刻', source: '原话：“11 月 5 号”' },
      { key: 'activity_kind', label: '活动类型', value: '电话跟进', group: 'activity_kind', status_label: '已识别' }
    ],
    options: [
      { value: 'confirm', label: '确认写入', disabled: false },
      { value: 'cancel', label: '取消', disabled: false }
    ],
    selection_mode: 'single',
    submit_on_select: true,
    submit_action_id: 'act_1'
  })

  const wrapper = mount(AgentUIInteractionBlock, { props: { block } })
  const rows = Object.fromEntries(wrapper.findAll('[data-activity-prop]').map(row => [
    row.get('dt').text(),
    row.get('dd').text()
  ]))

  expect(rows['下一步']).toBe('跟进付款进展')
  expect(rows['客户承诺']).toBe('下个月初付款（模糊时间，未确定具体日期）')
  expect(wrapper.get('[data-activity-time-value]').text()).toBe('2026-11-05（周四）09:00')
  expect(rows['跟进时间']).toBe('2026-11-05（周四）09:00（默认时刻）')

  expect(wrapper.get('[data-activity-score]').text()).toContain('原话：')
  expect(wrapper.get('[data-activity-score]').element.closest('[data-activity-basis]')).not.toBeNull()
  expect(wrapper.get('[data-activity-score] button').attributes('aria-expanded')).toBe('false')
  await wrapper.get('[data-activity-basis] button').trigger('click')
  await wrapper.get('[data-activity-score] button').trigger('click')
  expect(wrapper.get('[data-activity-basis] button').attributes('aria-expanded')).toBe('true')
  expect(wrapper.get('[data-activity-score] button').attributes('aria-expanded')).toBe('true')
})

it('shows a full month commitment separately from a sales date', async () => {
  const block = InteractionBlockSchema.parse({
    id: 'b_interaction_full_month',
    type: 'interaction',
    interaction_id: 'ix_full_month',
    interaction_type: 'confirmation',
    business_action: 'confirm_activity_write',
    state: 'ACTIVE',
    prompt: '确认后写入这条客户活动？',
    fields: [],
    facts: [
      { key: 'customer', label: '客户', value: '上海期货信息技术有限公司', group: 'write' },
      { key: 'summary', label: '摘要', value: '预计11月份可以完成付款，11月15号跟进付款方面的情况。', group: 'write' },
      { key: 'next_action', label: '下一步', value: '11月15号跟进付款方面的情况', group: 'write' },
      { key: 'customer_commitment', label: '客户承诺', value: '预计11月份可以完成付款（整月，未确定具体日期）', group: 'write' },
      { key: 'next_follow_time', label: '跟进时间', value: '2026-11-15（周日）15:00', group: 'write', source: '原话：“11月15号下午3点”' },
      { key: 'activity_kind', label: '活动类型', value: '微信跟进', group: 'activity_kind', status_label: '已识别' }
    ],
    options: [
      { value: 'confirm', label: '确认写入', disabled: false },
      { value: 'cancel', label: '取消', disabled: false }
    ],
    selection_mode: 'single',
    submit_on_select: true,
    submit_action_id: 'act_1'
  })

  const wrapper = mount(AgentUIInteractionBlock, { props: { block } })
  const rows = Object.fromEntries(wrapper.findAll('[data-activity-prop]').map(row => [
    row.get('dt').text(),
    row.get('dd').text()
  ]))

  expect(rows['客户承诺']).toBe('预计11月份可以完成付款（整月，未确定具体日期）')
  expect(wrapper.get('[data-activity-time-value]').text()).toBe('2026-11-15（周日）15:00')
  expect(rows['跟进时间']).toBe('2026-11-15（周日）15:00')
  expect(wrapper.text()).not.toContain('11月1日')
  expect(wrapper.text()).not.toContain('11月30')

  expect(wrapper.get('[data-activity-score]').text()).toContain('原话：')
  expect(wrapper.get('[data-activity-score]').element.closest('[data-activity-basis]')).not.toBeNull()
  expect(wrapper.get('[data-activity-score] button').attributes('aria-expanded')).toBe('false')
  await wrapper.get('[data-activity-basis] button').trigger('click')
  await wrapper.get('[data-activity-score] button').trigger('click')
  expect(wrapper.get('[data-activity-basis] button').attributes('aria-expanded')).toBe('true')
  expect(wrapper.get('[data-activity-score] button').attributes('aria-expanded')).toBe('true')
})

it('keeps business fields primary and nests legacy background and organizing sources under one reference disclosure', async () => {
  const block = InteractionBlockSchema.parse({
    id: 'b_interaction_density',
    type: 'interaction',
    interaction_id: 'ix_density',
    interaction_type: 'confirmation',
    business_action: 'confirm_activity_write',
    state: 'ACTIVE',
    prompt: '确认后写入这条客户活动？',
    fields: [],
    facts: [
      { key: 'customer', label: '客户', value: '上海期货信息技术有限公司', group: 'write' },
      { key: 'summary', label: '摘要', value: '今天通过微信对齐了合同和发票。', group: 'write' },
      { key: 'next_action', label: '下一步', value: '11 月 15 日跟进付款', group: 'write' },
      { key: 'next_follow_time', label: '跟进时间', value: '11 月 15 日', group: 'write' },
      { key: 'activity_kind', label: '活动类型', value: '微信跟进', group: 'activity_kind', status_label: 'AI 已识别 · 高置信度', source: '从今天微信联系中识别' },
      { key: 'change_signal', label: '客户上下文判断', value: '推进', group: 'context', source: '这次出现了新的确认或下一步。' },
      { key: 'context_evidence', label: '依据', value: '2026-09-23 微信沟通；2026-09-01 上次拜访', group: 'context' },
      { key: 'context_notice_1', label: '需要注意', value: '没有权限查看这部分内容', group: 'context' },
      { key: 'score', label: '内容质量', value: '76 / 100', group: 'score' },
      { key: 'score_reason', label: '评分依据', value: '主体和下一步都已整理', group: 'score' }
    ],
    options: [
      { value: 'confirm', label: '确认写入', disabled: false },
      { value: 'cancel', label: '取消', disabled: false }
    ],
    selection_mode: 'single',
    submit_on_select: true,
    submit_action_id: 'act_1'
  })

  const wrapper = mount(AgentUIInteractionBlock, { props: { block } })

  expect(wrapper.get('[data-activity-customer]').text()).toContain('上海期货信息技术有限公司')
  expect(wrapper.get('[data-activity-summary]').text()).toBe('今天通过微信对齐了合同和发票。')
  expect(wrapper.find('[data-activity-change]').exists()).toBe(false)
  expect(wrapper.find('[data-activity-prop="activity_kind"] [data-tone="success"]').exists()).toBe(false)

  // 折叠区收起时不渲染内容；「参考与依据」是唯一的顶层折叠区，整理依据嵌套在它里面。
  const basis = wrapper.get('[data-activity-basis]')
  const basisTrigger = basis.get('button')
  expect(basisTrigger.attributes('aria-expanded')).toBe('false')
  expect(wrapper.findAll('[data-activity-basis]')).toHaveLength(1)

  await basisTrigger.trigger('click')

  const organizing = basis.get('[data-activity-score]')
  expect(organizing.get('button').attributes('aria-expanded')).toBe('false')
  expect(basis.text()).toContain('2026-09-23 微信沟通')
  expect(basis.text()).toContain('没有权限查看这部分内容')
  expect(organizing.get('button').attributes('aria-expanded')).toBe('false')

  await organizing.get('button').trigger('click')
  expect(organizing.get('button').attributes('aria-expanded')).toBe('true')

  expect(organizing.text()).toContain('从今天微信联系中识别')
  expect(organizing.text()).toContain('76 / 100')
  expect(organizing.text()).toContain('主体和下一步都已整理')
  expect(wrapper.get('[data-activity-prop="activity_kind"]').text()).not.toContain('从今天微信联系中识别')
  expect(wrapper.findAll('button').map(button => button.text())).toEqual(['查看参考与依据', '内容评分与整理依据', '取消', '确认写入'])
})

it('opens the existing reference disclosure and focuses the frozen comparison without submitting an action', async () => {
  const block = InteractionBlockSchema.parse({
    id: 'b_interaction_comparison',
    type: 'interaction',
    interaction_id: 'ix_comparison',
    interaction_type: 'confirmation',
    business_action: 'confirm_activity_write',
    state: 'ACTIVE',
    prompt: '确认后写入这条客户活动？',
    fields: [],
    facts: [
      { key: 'customer', label: '客户', value: '通力电梯', group: 'write' },
      { key: 'summary', label: '摘要', value: '客户更新了评审安排。', group: 'write' },
      { key: 'customer_commitment', label: '客户承诺', value: '客户确认周五评审', group: 'write' },
      { key: 'next_action', label: '下一步', value: '发送更新后的材料', group: 'write' },
      { key: 'change_summary', label: '具体变化', value: '评审由周四改至周五', group: 'context' },
      { key: 'comparison_previous', label: '此前', value: '原定周四评审', source: '2026-11-10 活动摘要', group: 'context' },
      { key: 'comparison_current', label: '本次', value: '改到周五评审', source: '本次客户原话', group: 'context' },
      { key: 'context_status', label: '参考状态', value: '仅比较可读取的历史', group: 'context' },
      { key: 'opportunity', label: '参考商机', value: '电梯更新 · 方案评审', group: 'context' },
      { key: 'score', label: '内容质量', value: '82 / 100', group: 'score' }
    ],
    options: [
      { value: 'confirm', label: '确认写入', disabled: false },
      { value: 'cancel', label: '取消', disabled: false }
    ],
    selection_mode: 'single',
    submit_on_select: true,
    submit_action_id: 'act_comparison'
  })
  const wrapper = mount(AgentUIInteractionBlock, { props: { block }, attachTo: document.body })
  try {
    const basis = wrapper.get('[data-activity-basis]')
    const basisTrigger = basis.get('button')
    expect(basisTrigger.attributes('aria-expanded')).toBe('false')
    expect(wrapper.findAll('[data-activity-prop] dt').map(node => node.text())).toEqual(['客户承诺', '下一步'])
    expect(wrapper.get('[data-activity-change]').text()).toContain('评审由周四改至周五')

    await wrapper.get('[data-activity-comparison-link]').trigger('click')

    expect(basisTrigger.attributes('aria-expanded')).toBe('true')
    expect(basis.get('[data-activity-comparison-previous]').text()).toContain('原定周四评审')
    expect(basis.get('[data-activity-comparison-previous]').text()).toContain('2026-11-10 活动摘要')
    expect(basis.get('[data-activity-comparison-current]').text()).toContain('改到周五评审')
    expect(basis.get('[data-activity-comparison-current]').text()).toContain('本次客户原话')
    expect(basis.get('[data-activity-opportunity]').text()).toContain('电梯更新 · 方案评审')
    expect(basis.text()).toContain('仅比较可读取的历史')
    expect(basis.get('[data-activity-score] button').attributes('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(basis.get('[data-activity-history-heading]').element)
    expect(wrapper.findAll('[data-activity-prop] dd').filter(node => node.text() === '客户确认周五评审')).toHaveLength(1)
    expect(wrapper.emitted('submit')).toBeUndefined()
  } finally {
    wrapper.unmount()
  }
})

it('keeps ignored input noise only in nested organizing details and omits it when absent', async () => {
  const confirmation = (extra: Record<string, string>[]): ReturnType<typeof InteractionBlockSchema.parse> => InteractionBlockSchema.parse({
    id: 'b_interaction_noise',
    type: 'interaction',
    interaction_id: 'ix_noise',
    interaction_type: 'confirmation',
    business_action: 'confirm_activity_write',
    state: 'ACTIVE',
    prompt: '确认后写入这条客户活动？',
    fields: [],
    facts: [
      { key: 'customer', label: '客户', value: '广州睿狐科技有限公司', group: 'write' },
      { key: 'summary', label: '摘要', value: '张总预算已批。', group: 'write' },
      ...extra
    ],
    options: [
      { value: 'confirm', label: '确认写入', disabled: false },
      { value: 'cancel', label: '取消', disabled: false }
    ],
    selection_mode: 'single',
    submit_on_select: true,
    submit_action_id: 'act_1'
  })

  const shown = mount(AgentUIInteractionBlock, {
    props: { block: confirmation([{ key: 'ignored_noise', label: '已忽略', value: '已忽略 3 处发言时间', group: 'context' }]) }
  })
  // 被忽略的原文片段只出现在嵌套的整理依据里。
  await shown.get('[data-activity-basis] button').trigger('click')
  await shown.get('[data-activity-basis] button').trigger('click')
  await shown.get('[data-activity-score] button').trigger('click')
  expect(shown.findAll('[data-activity-ignored-noise]').map(node => node.text())).toEqual(['已忽略 3 处发言时间'])
  expect(shown.get('[data-activity-ignored-noise]').element.closest('[data-activity-score]')).not.toBeNull()

  const absent = mount(AgentUIInteractionBlock, { props: { block: confirmation([]) } })
  expect(absent.find('[data-activity-basis]').exists()).toBe(false)
  expect(absent.find('[data-activity-ignored-noise]').exists()).toBe(false)
})

it('keeps an unrecognized activity type and its reason outside the fold', () => {
  const block = InteractionBlockSchema.parse({
    id: 'b_interaction_unknown_kind',
    type: 'interaction',
    interaction_id: 'ix_unknown_kind',
    interaction_type: 'confirmation',
    business_action: 'confirm_activity_write',
    state: 'ACTIVE',
    prompt: '确认后写入这条客户活动？',
    fields: [],
    facts: [
      { key: 'customer', label: '客户', value: '通力电梯', group: 'write' },
      { key: 'summary', label: '摘要', value: '聊了付款。', group: 'write' },
      {
        key: 'activity_kind',
        label: '活动类型',
        value: '请选择本次活动的主渠道',
        group: 'activity_kind',
        status_label: '未识别 · 需要确认',
        source: '原文没有写明渠道',
        options: [{ value: 'WECHAT_FOLLOW_UP', label: '微信跟进', disabled: false }]
      }
    ],
    options: [
      { value: 'confirm', label: '确认写入', disabled: true, description: '先选择活动类型' },
      { value: 'cancel', label: '取消', disabled: false }
    ],
    selection_mode: 'single',
    submit_on_select: true,
    submit_action_id: 'act_1'
  })

  const wrapper = mount(AgentUIInteractionBlock, { props: { block } })

  expect(wrapper.text()).toContain('等待选择类型')
  expect(wrapper.get('[data-agent-ui-kind-evidence]').text()).toBe('原文没有写明渠道')
  expect(wrapper.find('[data-activity-basis]').exists()).toBe(false)
  expect(wrapper.findAll('button').filter(button => button.attributes('disabled') !== undefined).map(button => button.text())).toEqual(['确认写入'])
})

it('replays a historical activity confirmation without write actions', async () => {
  const block = InteractionBlockSchema.parse({
    id: 'b_interaction_history',
    type: 'interaction',
    interaction_id: 'ix_history',
    interaction_type: 'confirmation',
    business_action: 'confirm_activity_write',
    state: 'READ_ONLY',
    prompt: '确认后写入这条客户活动？',
    fields: [],
    facts: [
      { key: 'customer', label: '客户', value: '上海期货信息技术有限公司', group: 'write' },
      { key: 'summary', label: '摘要', value: '当时冻结的活动正文。', group: 'write' },
      { key: 'activity_kind', label: '活动类型', value: '微信跟进', group: 'activity_kind', status_label: '历史冻结', source: '当时的识别来源' },
      { key: 'change_signal', label: '客户上下文判断', value: '推进', group: 'context', source: '当时判断。' },
      { key: 'score_reason', label: '评分依据', value: '当时评分理由', group: 'score' }
    ],
    options: [
      { value: 'confirm', label: '确认写入', disabled: false },
      { value: 'cancel', label: '取消', disabled: false }
    ],
    selection_mode: 'single',
    submit_on_select: true,
    submit_action_id: null
  })

  const wrapper = mount(AgentUIInteractionBlock, { props: { block } })

  expect(wrapper.get('h2').text()).toBe('客户活动')
  expect(wrapper.findAll('[role="status"]').filter(tag => tag.text() === '历史')).toHaveLength(1)
  expect(wrapper.text()).not.toContain('历史冻结')
  expect(wrapper.text()).toContain('当时冻结的活动正文。')
  // 只读卡只有两个折叠触发器，没有任何操作入口
  expect(wrapper.findAll('button').map(button => button.text())).toEqual(['查看参考与依据', '内容评分与整理依据'])
  expect(wrapper.text()).not.toContain('确认写入')
  expect(wrapper.text()).not.toContain('取消')
  expect(wrapper.text()).not.toContain('修改类型')
  expect(wrapper.text()).not.toContain('再次写入')

  const basis = wrapper.get('[data-activity-basis]')
  expect(basis.get('button').attributes('aria-expanded')).toBe('false')
  await basis.get('button').trigger('click')
  await basis.get('[data-activity-score] button').trigger('click')
  expect(basis.text()).toContain('当时的识别来源')
})

const KIND_OPTIONS = [
  { value: 'ONLINE_MEETING', label: '线上会议', description: '远程会议', group: '会议' },
  { value: 'OFFLINE_MEETING', label: '线下会议', description: '当面开会', group: '会议' },
  { value: 'WECHAT_FOLLOW_UP', label: '微信跟进', description: '微信 / 企业微信', group: '跟进' },
  { value: 'OTHER_FOLLOW_UP', label: '其他跟进', description: '以上都不是', group: '跟进' }
]

it('groups the activity kinds and shows the wording that triggered the question', async () => {
  const block = InteractionBlockSchema.parse({
    id: 'b_kind_choice',
    type: 'interaction',
    interaction_id: 'ix_kind_choice',
    interaction_type: 'choice',
    business_action: 'select_activity_kind',
    state: 'ACTIVE',
    prompt: '这次沟通属于哪种活动？',
    hint: '原文提到：微信、线上会议',
    fields: [],
    facts: [],
    options: KIND_OPTIONS,
    selection_mode: 'single',
    min_selections: 1,
    max_selections: 1,
    submit_on_select: true,
    submit_action_id: 'act_kind'
  })

  const wrapper = mount(AgentUIInteractionBlock, { props: { block } })

  const headings = wrapper.findAll('[role="radiogroup"] > p').map(heading => heading.text())
  expect(headings).toEqual(['会议', '跟进'])
  expect(wrapper.get('[data-agent-ui-kind-hint]').text()).toContain('原文提到：')
  expect(wrapper.get('[data-agent-ui-kind-hint]').text()).toContain('微信')
  expect(wrapper.get('[data-agent-ui-kind-hint]').text()).toContain('请按本次实际发生的沟通来选')
  expect(wrapper.text()).not.toContain('原文提到：微信、线上会议')

  const options = wrapper.findAll('[role="radio"]')
  expect(options.map(button => button.text())).toEqual([
    '线上会议远程会议', '线下会议当面开会', '微信跟进微信 / 企业微信', '其他跟进以上都不是'
  ])
  expect(options.every(button => button.attributes('aria-checked') === 'false')).toBe(true)

  await options[2]?.trigger('click')
  expect(wrapper.emitted('submit')?.[0]).toEqual(['act_kind', { choice: 'WECHAT_FOLLOW_UP' }])
})

it('keeps a resolved activity kind read-only with its origin', () => {
  const block = InteractionBlockSchema.parse({
    id: 'b_kind_history',
    type: 'interaction',
    interaction_id: 'ix_kind_history',
    interaction_type: 'choice',
    business_action: 'select_activity_kind',
    state: 'SUBMITTED',
    prompt: '这次沟通属于哪种活动？',
    hint: '原文提到：微信',
    fields: [],
    facts: [],
    options: KIND_OPTIONS,
    selection_mode: 'single',
    min_selections: 1,
    max_selections: 1,
    submit_on_select: true,
    submitted_values: { choice: 'WECHAT_FOLLOW_UP' },
    submit_action_id: null
  })

  const wrapper = mount(AgentUIInteractionBlock, { props: { block } })

  expect(wrapper.get('[data-agent-ui-submitted-choice]').text()).toContain('已选择：微信跟进')
  expect(wrapper.text()).toContain('已处理')
  expect(wrapper.find('[data-agent-ui-kind-hint]').exists()).toBe(false)
  expect(wrapper.findAll('button')).toHaveLength(0)
})

it('offers a retry with the same choice when the card never reported an outcome', async () => {
  const block = InteractionBlockSchema.parse({
    id: 'b_kind_failed',
    type: 'interaction',
    interaction_id: 'ix_kind_failed',
    interaction_type: 'choice',
    business_action: 'select_activity_kind',
    state: 'ACTIVE',
    prompt: '这次沟通属于哪种活动？',
    hint: null,
    fields: [],
    facts: [],
    options: KIND_OPTIONS,
    selection_mode: 'single',
    min_selections: 1,
    max_selections: 1,
    submit_on_select: true,
    submit_action_id: 'act_kind_failed'
  })

  const wrapper = mount(AgentUIInteractionBlock, {
    props: { block, notice: { kind: 'failed', choice: 'WECHAT_FOLLOW_UP', clientRequestId: 'req_1' } }
  })

  expect(wrapper.text()).toContain('提交失败')
  expect(wrapper.find('[data-agent-ui-card-notice="failed"] button').exists()).toBe(true)
  expect(wrapper.get('[role="radio"][aria-checked="true"]').text()).toContain('微信跟进')

  await wrapper.get('[data-agent-ui-card-notice="failed"] button').trigger('click')
  expect(wrapper.emitted('submit')?.[0]).toEqual(['act_kind_failed', { choice: 'WECHAT_FOLLOW_UP' }])
})

it('keeps the kind card open when the submitted choice is outside the card', () => {
  const block = InteractionBlockSchema.parse({
    id: 'b_kind_invalid',
    type: 'interaction',
    interaction_id: 'ix_kind_invalid',
    interaction_type: 'choice',
    business_action: 'select_activity_kind',
    state: 'ACTIVE',
    prompt: '这次沟通属于哪种活动？',
    hint: '原文提到：微信',
    fields: [],
    facts: [],
    options: KIND_OPTIONS,
    selection_mode: 'single',
    min_selections: 1,
    max_selections: 1,
    submit_on_select: true,
    submit_action_id: 'act_kind_invalid'
  })

  const wrapper = mount(AgentUIInteractionBlock, { props: { block, notice: { kind: 'invalid' } } })

  expect(wrapper.text()).toContain('待处理')
  expect(wrapper.text()).not.toContain('已过期')
  expect(wrapper.get('[data-agent-ui-card-notice="invalid"]').text())
    .toContain('请从卡片给出的活动类型中选择。')
  expect(wrapper.get('[data-agent-ui-kind-hint]').text()).toContain('微信')
  expect(wrapper.findAll('button').some((button) => button.text().includes('微信跟进'))).toBe(true)
})

it('refuses further submissions once the card is stale', () => {
  const block = InteractionBlockSchema.parse({
    id: 'b_kind_expired',
    type: 'interaction',
    interaction_id: 'ix_kind_expired',
    interaction_type: 'choice',
    business_action: 'select_activity_kind',
    state: 'ACTIVE',
    prompt: '这次沟通属于哪种活动？',
    hint: '原文提到：微信',
    fields: [],
    facts: [],
    options: KIND_OPTIONS,
    selection_mode: 'single',
    min_selections: 1,
    max_selections: 1,
    submit_on_select: true,
    submit_action_id: 'act_kind_expired'
  })

  const wrapper = mount(AgentUIInteractionBlock, { props: { block, notice: { kind: 'expired' } } })

  expect(wrapper.text()).toContain('已过期')
  expect(wrapper.find('[data-agent-ui-card-notice="expired"]').exists()).toBe(true)
  expect(wrapper.find('[data-agent-ui-kind-hint]').exists()).toBe(false)
  expect(wrapper.findAll('button')).toHaveLength(0)
})

it('shows the chosen kind with its origin and only same-category revisions', async () => {
  const block = InteractionBlockSchema.parse({
    id: 'b_kind_confirm',
    type: 'interaction',
    interaction_id: 'ix_kind_confirm',
    interaction_type: 'confirmation',
    business_action: 'confirm_activity_write',
    state: 'ACTIVE',
    prompt: '确认后写入这条客户活动？',
    fields: [],
    facts: [
      { key: 'customer', label: '客户', value: '某科技公司', group: 'write' },
      { key: 'summary', label: '摘要', value: '微信确认了合同条款。', group: 'write' },
      {
        key: 'activity_kind',
        label: '活动类型',
        value: '微信跟进',
        group: 'activity_kind',
        status_label: '已选择',
        source: '你选择：微信跟进',
        options: [
          { value: 'PHONE_FOLLOW_UP', label: '电话跟进', disabled: false },
          { value: 'WECHAT_FOLLOW_UP', label: '微信跟进', disabled: false }
        ]
      }
    ],
    options: [
      { value: 'cancel', label: '取消', disabled: false },
      { value: 'confirm', label: '确认写入', disabled: false }
    ],
    selection_mode: 'single',
    submit_on_select: true,
    submit_action_id: 'act_kind_confirm'
  })

  const wrapper = mount(AgentUIInteractionBlock, { props: { block } })

  expect(wrapper.get('[data-activity-prop="activity_kind"]').text()).not.toContain('你选择：微信跟进')
  await wrapper.get('[data-activity-basis] button').trigger('click')
  await wrapper.get('[data-activity-score] button').trigger('click')
  expect(wrapper.get('[data-activity-score]').text()).toContain('你选择：微信跟进')

  await wrapper.findAll('button').find(button => button.text() === '修改活动类型')?.trigger('click')
  expect(wrapper.findAll('button').some(button => button.text() === '收起类型选项')).toBe(true)
  const revisions = wrapper.findAll('[role="radio"]')
  expect(revisions.map(button => button.text())).toEqual(['电话跟进', '微信跟进'])

  await revisions[0]?.trigger('click')
  expect(wrapper.emitted('submit')?.[0]).toEqual(['act_kind_confirm', { revise_activity_kind: 'PHONE_FOLLOW_UP' }])
})
