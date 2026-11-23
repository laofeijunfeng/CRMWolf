// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { confirmation, drive, field, makeTask, message, mocks, prepared, reply, show, view } from './assistantChatHarness'
import SalesAssistantChat from '@/components/sales-assistant/SalesAssistantChat.vue'
import AgentUIMessage from '@/components/agent-ui/AgentUIMessage.vue'
import { AgentUIEnvelopeSchema, InteractionFieldSchema } from '@/schemas/agent-contracts'
import type { JsonObject } from '@/schemas/agent-contracts'
import type { ConversationView, TaskWaiting } from '@/schemas/assistant-contracts'

describe('owned historical conversation projection', () => {
  it('shows original text and human prompts, not internal action names', async () => {
    show(view({ messages: [message('u', '今天和客户复盘部署', null, 'user'), message('a', '请补充客户名称'), message('r', '已记录这条客户活动。')] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(wrapper.text()).toContain('今天和客户复盘部署')
    expect(wrapper.text()).toContain('请补充客户名称')
    expect(wrapper.text()).not.toMatch(/ask_confirmation|submit_field|confirm_write/)
  })

  it('binds an archived meeting card to its own frozen snapshot rather than the current task', async () => {
    const old = makeTask({ public_id: 'ast_old', status: 'COMPLETED', activity_kind: 'ONLINE_MEETING', waiting: confirmation({ confirmation_payload: { kind: 'activity_write', preview: {
      customer_name: '原客户', activity_kind: 'ONLINE_MEETING', title: '原会议主题', summary: '原会议讨论',
      content_json: {}, source_content: '原始记录', score: 88, score_reason: '原评分'
    } } }) })
    const current = makeTask({ public_id: 'ast_new', waiting: field(), draft: { ...old.draft, customer: { status: 'ACCEPTED', value: '新客户' } } })
    show(view({ focused_task: current, messages: [message('old', '会议确认', old), message('new', '当前提示', current)] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    const meeting = wrapper.findAllComponents({ name: 'AgentUIMessage' })[0]
    expect(meeting?.text()).toContain('原会议讨论')
    expect(meeting?.text()).toContain('原客户')
    expect(meeting?.text()).not.toContain('新客户')
  })

  it('keeps legacy field/kind labels readable from the server projection', async () => {
    show(view({ messages: [message('one', '客户名称：睿狐科技', null, 'user'), message('two', '线上会议', null, 'user')] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(wrapper.text()).toContain('客户名称：睿狐科技')
    expect(wrapper.text()).toContain('线上会议')
  })

  it('does not let an archived card confirm or change the focused activity kind', async () => {
    const old = makeTask({ status: 'COMPLETED', waiting: confirmation() })
    show(view({ focused_task: makeTask({ public_id: 'ast_new' }), messages: [message('old', '已归档', old)] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(wrapper.findAll('button').filter((b) => /确认写入|改为线下/.test(b.text()) && b.attributes('disabled') === undefined)).toHaveLength(0)
    expect(mocks.command).not.toHaveBeenCalled()
  })

  it('restores one live authoritative wait while older matching cards stay archived', async () => {
    const current = makeTask({ waiting: confirmation() })
    show(view({ focused_task: current, messages: [message('old', '旧提示', current), message('new', '当前提示', current)] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(wrapper.findAll('button').filter((b) => b.text() === '确认写入' && b.attributes('disabled') === undefined)).toHaveLength(1)
  })

  it('preserves the old draft field chips instead of taking values from a new focus', async () => {
    const old = makeTask({ public_id: 'ast_old', waiting: field(), draft: { ...makeTask().draft, customer: { status: 'ACCEPTED', value: '旧客户' } } })
    const next = makeTask({ public_id: 'ast_next', waiting: field(), draft: { ...makeTask().draft, customer: { status: 'ACCEPTED', value: '新客户' } } })
    show(view({ focused_task: next, messages: [message('old', '旧稿问题', old), message('new', '新稿问题', next)] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    const gaps = wrapper.findAllComponents({ name: 'AgentUIMessage' })
    expect(gaps[0]?.text()).toContain('旧客户')
    expect(gaps[0]?.text()).not.toContain('新客户')
  })

  it('loads earlier conversation by cursor without dropping the latest results', async () => {
    show(view({ messages: [message('new', '最近结果')], older_cursor: 31 }))
    mocks.get.mockResolvedValue(view({ messages: [message('old', '更早结果')], older_cursor: null }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text() === '查看更早对话')?.trigger('click')
    await flushPromises()
    expect(mocks.get).toHaveBeenCalledWith(31)
    expect(wrapper.text()).toContain('更早结果')
    expect(wrapper.text()).toContain('最近结果')
  })

  it('shows the server completion boundary after the business result without an AI message container', async () => {
    const completed = makeTask({ status: 'COMPLETED', committed: [{ kind: 'customer_activity', public_id: 'act_done' }] })
    show(view({ focused_task: completed, messages: [
      { ...message('result', '活动已写入', completed), outcome: 'activity_written' },
      { ...message(`completion:${completed.public_id}`, '本次任务已完成', completed), outcome: 'task_completed' }
    ] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    const divider = wrapper.find('[role="separator"]')
    expect(divider.text()).toBe('本次任务已完成')
    expect(divider.findComponent({ name: 'AgentUIMessage' }).exists()).toBe(false)
    expect(divider.text()).not.toContain('AI')
    expect(wrapper.findAllComponents({ name: 'AgentUIMessage' })).toHaveLength(1)
    expect(wrapper.text().indexOf('活动已写入')).toBeLessThan(wrapper.text().indexOf('本次任务已完成'))
    expect(wrapper.find('textarea').attributes('disabled')).toBeUndefined()
  })

  it('does not infer historical completion from text, task snapshots, or the current focus', async () => {
    const completed = makeTask({ status: 'COMPLETED' })
    show(view({ focused_task: completed, messages: [
      message('old', '本次任务已完成。', completed),
      message('unrelated', '此前的普通回复')
    ] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(wrapper.find('[role="separator"]').exists()).toBe(false)
    expect(wrapper.findAllComponents({ name: 'AgentUIMessage' })).toHaveLength(2)
  })

  it('deduplicates completion by task across overlapping pages and later conversation refreshes', async () => {
    const completed = makeTask({ status: 'COMPLETED' })
    const completion = { ...message(`completion:${completed.public_id}`, '本次任务已完成', completed), outcome: 'task_completed' as const }
    show(view({ version: 1, focused_task: completed, messages: [{ ...message('last-result', '最后一项结果', completed), outcome: 'activity_written' }, completion], older_cursor: 31 }))
    mocks.get.mockResolvedValueOnce(view({ messages: [message('old', '较早的结果', completed), completion, { ...completion, id: 'older-completion' }], older_cursor: null }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '查看更早对话')?.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[role="separator"]')).toHaveLength(1)
    expect(wrapper.text().indexOf('最后一项结果')).toBeLessThan(wrapper.text().indexOf('本次任务已完成'))
    mocks.text.mockResolvedValue({ conversation: view({ version: 2, focused_task: completed, messages: [completion, message('next', '后续沟通', null, 'user')] }), submission: null })
    await wrapper.find('textarea').setValue('后续沟通')
    await wrapper.find('textarea').trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()
    expect(wrapper.findAll('[role="separator"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('较早的结果')
    expect(wrapper.text().indexOf('本次任务已完成')).toBeLessThan(wrapper.text().indexOf('后续沟通'))
  })
})

describe('conversation snapshot fences', () => {
  it('does not restore a next history cursor after all earlier pages were loaded', async () => {
    show(view({ version: 1, messages: [message('new', '最近结果')], older_cursor: 31 }))
    mocks.get.mockResolvedValueOnce(view({ version: 1, messages: [message('old', '最早结果')], older_cursor: null }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text() === '查看更早对话')?.trigger('click')
    await flushPromises()
    mocks.text.mockResolvedValue({ conversation: view({ version: 2, messages: [message('new', '最近结果'), message('next', '新的回复')], older_cursor: 31 }), submission: null })
    await wrapper.find('textarea').setValue('下一件')
    await wrapper.find('textarea').trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()
    expect(wrapper.text()).toContain('最早结果')
    expect(wrapper.text()).toContain('新的回复')
    expect(wrapper.findAll('button').find((b) => b.text() === '查看更早对话')).toBeUndefined()
  })

})

const interactionMessage = (
  id: string, task: NonNullable<ConversationView['focused_task']>, overrides: Record<string, unknown>
): ConversationView['messages'][number] => {
  const waiting = task.waiting
  if (waiting == null) throw new Error('Interaction fixtures require a wait')
  return {
    ...message(id, waiting.prompt, task),
    ui: AgentUIEnvelopeSchema.parse({
      schema_version: 'crm.agent.ui.v1', message_id: 1, turn_id: id, role: 'assistant', state: 'final',
      metadata: { display: 'MESSAGE', route: 'WORKFLOW' },
      blocks: [{
        id: `block:${id}`, type: 'interaction', interaction_id: `ix:${id}`, prompt: waiting.prompt,
        state: 'ACTIVE', submit_action_id: waiting.action_id, ...overrides
      }]
    })
  }
}

const formMessage = (id: string, waiting: TaskWaiting): ConversationView['messages'][number] =>
  interactionMessage(id, makeTask({ waiting }), {
    interaction_type: 'form', fields: waiting.form_fields, allow_cancel: true,
    business_action: waiting.type === 'PROPOSAL_FORM' ? 'create_opportunity_proposal' : 'edit_confirmation'
  })

const formField = (key: string) => InteractionFieldSchema.parse({
  key, label: key, field_type: 'textarea', min_length: 0, max_length: 200
})

const loadInteractions = async (entries: ConversationView['messages']) => {
  const state = view({ version: 9, focused_task: entries[entries.length - 1]?.task ?? null, messages: entries })
  show(state)
  mocks.command.mockResolvedValue(reply(state))
  const page = { render: () => null }
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/assistant', component: page },
    { path: '/customer-tracking', name: 'CustomerTracking', component: page }
  ] })
  await router.push('/assistant')
  const wrapper = mount(SalesAssistantChat, { global: { plugins: [router] } })
  await flushPromises()
  const interaction = (id: string) => wrapper.findAllComponents(AgentUIMessage)
    .find((card) => card.props('message').turn_id === id)
  const submit = async (id: string, action: string, values: JsonObject): Promise<void> => {
    const card = interaction(id)
    expect(card).toBeDefined()
    card?.vm.$emit('interaction', action, values)
    await flushPromises()
  }
  return { wrapper, state, interaction, submit }
}

describe('revision-bound sales assistant interactions', () => {
  it('archives an older form revision and cancels the live revision without submitting form values', async () => {
    const waiting = field({ type: 'PROPOSAL_FORM', field: 'proposal:opportunity_create',
      form_revision: 0, form_fields: [formField('opportunity_name')] })
    const { wrapper, interaction, submit } = await loadInteractions([
      formMessage('old', waiting), formMessage('live', { ...waiting, form_revision: 1 })
    ])
    expect(interaction('old')?.props('message').blocks[0]).toMatchObject({ state: 'READ_ONLY', submit_action_id: null })
    await submit('old', 'action1', { opportunity_name: '过期值' })
    expect(mocks.command).not.toHaveBeenCalled()
    await submit('live', 'action1', { choice: 'cancel' })
    expect(mocks.command.mock.calls[0]?.[0]).toEqual({ task_public_id: 'ast_one', expected_version: 9,
      input: { kind: 'submit_form', form_revision: 1, choice: 'cancel', action_id: 'action1',
        expected_version: 1, client_request_id: expect.any(String) } })
    wrapper.unmount()
  })

  it('sends normalized participant text and uses the server-prepared revision after recovering admission', async () => {
    const waiting = field({ type: 'CONFIRMATION_EDIT', field: 'activity_write', form_revision: 0,
      form_fields: [formField('internal_participants'), formField('customer_participants')] })
    const { wrapper, state, submit } = await loadInteractions([formMessage('edit', waiting)])
    const task = state.focused_task
    if (task === null) throw new Error('Expected a focused edit task')
    const submission = { ...prepared(task), input: { kind: 'submit_form' as const,
      client_request_id: 'server-prepared-key', action_id: 'server-prepared-action', expected_version: 1,
      form_revision: 0, values: { internal_participants: '小林\n小陈' } } }
    mocks.command.mockRejectedValueOnce(new Error('网络中断')).mockResolvedValueOnce(reply(state, submission))
    drive((handlers) => handlers.onWaiting({ task, message: '已修改' }))
    await submit('edit', 'action1', { internal_participants: ' 小林 \r\n\r\n 小陈 ' })
    const request = mocks.command.mock.calls[0]?.[0]
    expect(request?.input).toEqual({ kind: 'submit_form', form_revision: 0, values: { internal_participants: '小林\n小陈' },
      action_id: 'action1', expected_version: 1, client_request_id: expect.any(String) })
    await submit('edit', 'action1', { internal_participants: '不得覆盖' })
    expect(mocks.command).toHaveBeenCalledTimes(1)
    const retry = wrapper.findAll('button').find((button) => button.text() === '重试同步')
    expect(retry).toBeDefined()
    await retry?.trigger('click')
    await flushPromises()
    expect(mocks.command.mock.calls[1]?.[0]).toEqual(request)
    expect(mocks.stream.mock.calls[0]?.slice(0, 2)).toEqual(['ast_one', submission.input])
    wrapper.unmount()
  })

  it('keeps confirmation edit and reasoned rejection distinct', async () => {
    const current = makeTask({ waiting: confirmation() })
    const card = interactionMessage('confirm', current, {
      interaction_type: 'confirmation', selection_mode: 'single',
      options: [{ value: 'confirm', label: '确认' }, { value: 'cancel', label: '取消' }],
      secondary_action: { value: 'request_edit', label: '修改内容' },
      cancel_reasons: [{ value: 'wrong_content', label: '内容不对' }]
    })
    const { wrapper, submit } = await loadInteractions([card])
    await submit('confirm', 'action1', { choice: 'request_edit' })
    await submit('confirm', 'action1', { choice: 'cancel', reason: 'wrong_content' })
    expect(mocks.command.mock.calls.map(([request]) => request.input)).toEqual([
      { kind: 'request_edit', action_id: 'action1', expected_version: 1, client_request_id: expect.any(String) },
      { kind: 'confirm', choice: 'reject', reason: 'wrong_content', action_id: 'action1', expected_version: 1,
        client_request_id: expect.any(String) }
    ])
    wrapper.unmount()
  })

  it('allows an explicit empty batch selection but blocks a settling batch', async () => {
    const item = { item_id: 'item_one', title: '核对采购时间', state: 'current' as const, related: true }
    const disposition = { batch_id: 'batch_one', status: 'ACTIVE' as const, customer_name: '客户', activity_kind_label: '跟进',
      total: 1, current_index: null, items: [item] }
    const current = makeTask({ waiting: field({ type: 'FOLLOW_UP_DISPOSITION', field: 'follow_up_disposition' }),
      follow_up_disposition: disposition })
    const block = { interaction_type: 'choice', business_action: 'settle_follow_up_disposition',
      presentation: 'OPEN_FOLLOW_UP_DISPOSITION', disposition_link: true, disposition_items: [item],
      selection_mode: 'multiple', min_selections: 0, max_selections: 1,
      options: [{ label: item.title, value: item.item_id }], secondary_action: { label: '本周不再提示', value: 'suppress_week' } }
    const active = interactionMessage('active', current, block)
    const first = await loadInteractions([active])
    await first.submit('active', 'action1', { choices: [], suppress_week: true })
    expect(mocks.command.mock.calls[0]?.[0]?.input).toEqual({ kind: 'submit_field', choices: [], suppress_week: true,
      action_id: 'action1', expected_version: 1, client_request_id: expect.any(String) })
    first.wrapper.unmount()
    mocks.command.mockClear()
    const settled = interactionMessage('settling', { ...current, follow_up_disposition: { ...disposition, settling: true } }, block)
    const second = await loadInteractions([settled])
    expect(second.interaction('settling')?.props('message').blocks[0]).toMatchObject({
      state: 'READ_ONLY', submit_action_id: null, secondary_action: null, disposition_link: true
    })
    expect(second.wrapper.get('a[href="/customer-tracking"]').text()).toBe('在客户追踪页处理')
    await second.submit('settling', 'action1', { choices: [item.item_id], suppress_week: false })
    expect(mocks.command).not.toHaveBeenCalled()
    second.wrapper.unmount()
  })
})
