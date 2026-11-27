import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type * as AssistantApi from '@/api/assistant'
import { InteractionBlockSchema } from '@/schemas/agent-contracts'
import type { AssistantTaskView, ConversationRequestStatus, ConversationView, TaskWaiting } from '@/schemas/assistant-contracts'

const api = vi.hoisted(() => ({
  openConversation: vi.fn(), getConversation: vi.fn(), conversationCommand: vi.fn(), conversationText: vi.fn(),
  conversationRequestStatus: vi.fn(), pendingDrafts: vi.fn(), focusConversation: vi.fn(), resumeConversation: vi.fn(),
}))

vi.mock('@/api/assistant', async (importOriginal) => ({
  ...await importOriginal<typeof AssistantApi>(),
  assistantApi: api,
  submitInputStream: vi.fn(),
}))

import SalesAssistantChat from '../SalesAssistantChat.vue'

const waiting: TaskWaiting = {
  type: 'ENTITY_FORM', question_id: 'q-dep', prompt: '请补全部署信息', action_id: 'act-dep',
  expected_version: 3, form_revision: 2,
}
const task: AssistantTaskView = {
  public_id: 'task-dep', status: 'ACTIVE', goal: '新建部署信息', task_kind: 'deployment_create',
  draft: {
    customer: { status: 'MISSING' }, content: { status: 'MISSING' },
    next_action: { status: 'MISSING' }, next_follow_time: { status: 'MISSING' },
  },
  committed: [], budget_steps: 1, budget_max_steps: 10, version: 3,
  processing_turn_id: null, processing_turn_status: null, reprocess_turn_id: null, waiting,
}
const formBlock = InteractionBlockSchema.parse({
  id: 'b-dep', type: 'interaction', interaction_id: 'q-dep', interaction_type: 'form',
  business_action: 'create_deployment', allow_cancel: true, state: 'ACTIVE', prompt: '请补全部署信息',
  submit_label: '提交', submit_action_id: 'act-dep', options: [],
  fields: [{ key: 'name', label: '环境名称', field_type: 'text', required: true, default_value: '正式环境', min_length: 1, max_length: 50, options: [] }],
})
const formView: ConversationView = {
  public_id: 'conversation-1', version: 5, focused_task: task,
  pending_choice: null, has_pending_request: false, older_cursor: null,
  messages: [{
    id: 'entry-1:reply', role: 'assistant', text: '请补全部署信息', at: '2026-11-26T01:00:00',
    task, boundary: null, outcome: null,
    ui: {
      schema_version: 'crm.agent.ui.v1', message_id: 1, turn_id: 'entry-1:reply', role: 'assistant', state: 'final',
      blocks: [formBlock], suggested_actions: [], metadata: { display: 'MESSAGE', route: 'WORKFLOW' },
    },
  }],
}
const emptyView: ConversationView = {
  public_id: 'conversation-1', version: 5, focused_task: null,
  pending_choice: null, has_pending_request: false, older_cursor: null, messages: [],
}
const savedView: ConversationView = {
  ...emptyView, version: 6,
  messages: [{
    id: 'entry-2:reply', role: 'assistant', text: '部署信息「正式环境」已保存', at: '2026-11-26T01:01:00',
    task: null, boundary: null, outcome: null,
    ui: {
      schema_version: 'crm.agent.ui.v1', message_id: 2, turn_id: 'entry-2:reply', role: 'assistant', state: 'final',
      blocks: [{ id: 'b-saved', type: 'text', format: 'plain', text: '部署信息「正式环境」已保存' }],
      suggested_actions: [], metadata: { display: 'MESSAGE', route: 'WORKFLOW' },
    },
  }],
}
const status = (state: ConversationRequestStatus['state'], conversation: ConversationView): ConversationRequestStatus => ({ state, conversation })
const timeout = (): Error => Object.assign(new Error('timeout of 30000ms exceeded'), { code: 'ECONNABORTED' })
// Covers the whole 2/4/8/16/30 s backoff window.
const LOST_SEND_WINDOW_MS = 61_000

const button = (wrapper: VueWrapper, label: string): DOMWrapper<Element> | undefined => wrapper.findAll('button').find((b) => b.text() === label)
const clickSubmit = async (wrapper: VueWrapper): Promise<void> => {
  const submit = button(wrapper, '提交')
  if (submit === undefined) throw new Error('missing 提交')
  await submit.trigger('click')
  await flushPromises()
}
const expectNeutral = (wrapper: VueWrapper): void => {
  expect(wrapper.text()).not.toMatch(/timeout|exceeded|ECONN|Network Error/)
  expect(wrapper.text()).not.toContain('重试同步')
}
const commandKey = (call: number): unknown => (api.conversationCommand.mock.calls[call]?.[0] as { input: { client_request_id?: string } }).input.client_request_id

let wrapper: VueWrapper | undefined
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  Object.values(api).forEach((mock) => mock.mockReset())
  api.pendingDrafts.mockResolvedValue([])
  api.openConversation.mockResolvedValue(formView)
  api.getConversation.mockResolvedValue(formView)
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.useRealTimers()
})

describe('SalesAssistant lost send response', () => {
  it('stays in 保存中 and shows the saved result without resending', async () => {
    api.conversationCommand.mockRejectedValue(timeout())
    api.conversationRequestStatus.mockResolvedValue(status('saved', savedView))
    wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await clickSubmit(wrapper)

    expect(wrapper.find('[data-assistant-lost-send="checking"]').text()).toBe('保存中…')
    expect(button(wrapper, '提交')?.attributes('disabled')).toBeDefined()
    expectNeutral(wrapper)

    await vi.advanceTimersByTimeAsync(2_000)
    await flushPromises()
    expect(api.conversationRequestStatus).toHaveBeenCalledWith(commandKey(0))
    expect(wrapper.text()).toContain('部署信息「正式环境」已保存')
    expect(wrapper.find('[data-assistant-lost-send]').exists()).toBe(false)
    expect(api.conversationCommand).toHaveBeenCalledTimes(1)
    expectNeutral(wrapper)
  })

  it('lets the user resend a not-saved card with the same key', async () => {
    api.conversationCommand.mockRejectedValueOnce(timeout()).mockResolvedValueOnce({ conversation: savedView })
    api.conversationRequestStatus.mockResolvedValue(status('not_saved', formView))
    wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await clickSubmit(wrapper)
    await vi.advanceTimersByTimeAsync(2_000)
    await flushPromises()

    expect(wrapper.find('[data-assistant-lost-send="not_saved"]').text()).toContain('刚才网络不稳定，这条还没有保存')
    expect(button(wrapper, '提交')?.attributes('disabled')).toBeUndefined()
    expect(api.conversationCommand).toHaveBeenCalledTimes(1)
    expectNeutral(wrapper)

    await clickSubmit(wrapper)
    expect(api.conversationCommand).toHaveBeenCalledTimes(2)
    expect(commandKey(1)).toBe(commandKey(0))
  })

  it('restores typed text after a not-saved send and reuses its key', async () => {
    api.openConversation.mockResolvedValue(emptyView)
    api.conversationText.mockRejectedValueOnce(timeout()).mockResolvedValueOnce({ conversation: savedView })
    api.conversationRequestStatus.mockResolvedValue(status('none', emptyView))
    wrapper = mount(SalesAssistantChat)
    await flushPromises()
    const input = wrapper.get('textarea[aria-label="客户沟通内容"]')
    await input.setValue('今天和睿狐科技开了线上会')
    await wrapper.get('button[aria-label="发送"]').trigger('click')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2_000)
    await flushPromises()

    expect((input.element as HTMLTextAreaElement).value).toBe('今天和睿狐科技开了线上会')
    expect(wrapper.text()).toContain('刚才网络不稳定，这条还没有保存')

    await wrapper.get('button[aria-label="发送"]').trigger('click')
    await flushPromises()
    const keys = api.conversationText.mock.calls.map(([request]) => (request as { client_request_id: string }).client_request_id)
    expect(keys).toHaveLength(2)
    expect(keys[1]).toBe(keys[0])
  })

  it('offers only 查看结果 when the save cannot be confirmed', async () => {
    api.conversationCommand.mockRejectedValue(timeout())
    api.conversationRequestStatus.mockRejectedValue(new Error('Network Error'))
    wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await clickSubmit(wrapper)
    await vi.advanceTimersByTimeAsync(LOST_SEND_WINDOW_MS)
    await flushPromises()

    expect(api.conversationRequestStatus).toHaveBeenCalledTimes(5)
    expect(wrapper.find('[data-assistant-lost-send="unconfirmed"]').text()).toContain('结果暂时未确认，为避免重复，先不要再次提交。')
    expect(button(wrapper, '刷新状态')).toBeUndefined()
    expect(button(wrapper, '提交')?.attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[aria-label="发送"]').attributes('disabled')).toBeDefined()
    expectNeutral(wrapper)

    api.conversationRequestStatus.mockResolvedValue(status('saved', savedView))
    const check = button(wrapper, '查看结果')
    if (check === undefined) throw new Error('missing 查看结果')
    await check.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('部署信息「正式环境」已保存')
    expect(button(wrapper, '查看结果')).toBeUndefined()
    expect(api.conversationCommand).toHaveBeenCalledTimes(1)
  })

  it('releases a held text card once 查看结果 confirms the send landed', async () => {
    const textWaiting: TaskWaiting = {
      type: 'FIELD', field: 'content', question_id: 'q-text', prompt: '请补充内容', action_id: 'act-text', expected_version: 3,
    }
    const textTask: AssistantTaskView = { ...task, task_kind: 'customer_activity', waiting: textWaiting }
    const textBlock = InteractionBlockSchema.parse({
      id: 'b-text', type: 'interaction', interaction_id: 'q-text', interaction_type: 'text_input', state: 'ACTIVE',
      prompt: '请补充内容', allow_blank: false, submit_label: '提交', submit_action_id: 'act-text', options: [],
      fields: [{ key: 'text', label: '内容', field_type: 'textarea', required: true, default_value: '已沟通部署', min_length: 1, max_length: 10000, options: [] }],
    })
    const [reply] = formView.messages
    if (reply?.ui === null || reply?.ui === undefined) throw new Error('missing reply ui')
    const textView: ConversationView = {
      ...formView, focused_task: textTask,
      messages: [{ ...reply, text: '请补充内容', task: textTask, ui: { ...reply.ui, blocks: [textBlock] } }],
    }
    api.openConversation.mockResolvedValue(textView)
    api.getConversation.mockResolvedValue(textView)
    api.conversationCommand.mockRejectedValue(timeout())
    api.conversationRequestStatus.mockRejectedValue(new Error('Network Error'))
    wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await clickSubmit(wrapper)
    await vi.advanceTimersByTimeAsync(LOST_SEND_WINDOW_MS)
    await flushPromises()
    expect(wrapper.find('[data-assistant-lost-send="unconfirmed"]').exists()).toBe(true)

    // Saved, and the server still waits on the same card (it asks again).
    api.conversationRequestStatus.mockResolvedValue(status('saved', textView))
    const check = button(wrapper, '查看结果')
    if (check === undefined) throw new Error('missing 查看结果')
    await check.trigger('click')
    await flushPromises()

    expect(button(wrapper, '查看结果')).toBeUndefined()
    expect(button(wrapper, '提交')?.attributes('disabled')).toBeUndefined()
    expect(api.conversationCommand).toHaveBeenCalledTimes(1)
  })

  it('checks request status once on window online when unconfirmed without resending', async () => {
    api.conversationCommand.mockRejectedValue(timeout())
    api.conversationRequestStatus.mockRejectedValue(new Error('Network Error'))
    wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await clickSubmit(wrapper)
    await vi.advanceTimersByTimeAsync(LOST_SEND_WINDOW_MS)
    await flushPromises()

    expect(api.conversationRequestStatus).toHaveBeenCalledTimes(5)
    api.conversationRequestStatus.mockResolvedValueOnce(status('saved', savedView))
    window.dispatchEvent(new Event('online'))
    await flushPromises()

    expect(api.conversationRequestStatus).toHaveBeenCalledTimes(6)
    expect(api.conversationCommand).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('部署信息「正式环境」已保存')
    expect(button(wrapper, '查看结果')).toBeUndefined()
  })
})
