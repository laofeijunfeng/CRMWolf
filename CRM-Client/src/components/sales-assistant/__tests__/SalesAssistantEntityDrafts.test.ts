import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type * as AssistantApi from '@/api/assistant'
import { InteractionBlockSchema } from '@/schemas/agent-contracts'
import type { AssistantTaskView, ConversationView, PendingEntityDraft, TaskWaiting } from '@/schemas/assistant-contracts'

const api = vi.hoisted(() => ({
  openConversation: vi.fn(), getConversation: vi.fn(), conversationCommand: vi.fn(),
  pendingDrafts: vi.fn(), focusConversation: vi.fn(),
}))

vi.mock('@/api/assistant', async (importOriginal) => ({
  ...await importOriginal<typeof AssistantApi>(),
  assistantApi: api,
  submitInputStream: vi.fn(),
}))

import SalesAssistantChat from '../SalesAssistantChat.vue'

const waiting: TaskWaiting = {
  type: 'ENTITY_FORM', question_id: 'q-contact', prompt: '请补全联系人', action_id: 'act-contact',
  expected_version: 3, form_revision: 2,
}
const contactTask: AssistantTaskView = {
  public_id: 'task-contact', status: 'ACTIVE', goal: '新建联系人', task_kind: 'contact_create',
  draft: {
    customer: { status: 'MISSING' }, content: { status: 'MISSING' },
    next_action: { status: 'MISSING' }, next_follow_time: { status: 'MISSING' },
  },
  committed: [], budget_steps: 1, budget_max_steps: 10, version: 3,
  processing_turn_id: null, processing_turn_status: null, reprocess_turn_id: null, waiting,
}
const formBlock = InteractionBlockSchema.parse({
  id: 'b-contact', type: 'interaction', interaction_id: 'q-contact', interaction_type: 'form',
  business_action: 'create_contact', allow_cancel: true, state: 'ACTIVE', prompt: '请补全联系人',
  submit_label: '创建联系人', submit_action_id: 'act-contact', options: [],
  fields: [{ key: 'name', label: '姓名', field_type: 'text', required: true, default_value: '王敏', min_length: 1, max_length: 50, options: [] }],
})
const view = (focused: AssistantTaskView | null): ConversationView => ({
  public_id: 'conversation-1', version: 5, focused_task: focused,
  pending_choice: null, has_pending_request: false, older_cursor: null,
  messages: focused === null ? [] : [{
    id: 'entry-1:reply', role: 'assistant', text: '请补全联系人', at: '2026-11-26T01:00:00',
    task: focused, boundary: null, outcome: null,
    ui: {
      schema_version: 'crm.agent.ui.v1', message_id: 1, turn_id: 'entry-1:reply', role: 'assistant', state: 'final',
      blocks: [formBlock], suggested_actions: [], metadata: { display: 'MESSAGE', route: 'WORKFLOW' },
    },
  }],
})
const draft = (publicId: string, label: string): PendingEntityDraft => ({
  public_id: publicId, task_kind: 'contact_create', label, customer_name: '睿狐科技',
  waiting_type: 'ENTITY_FORM', prompt: null, last_modified_time: '2026-11-26T01:00:00',
})

let wrapper: VueWrapper | undefined
const sentInput = (): unknown => (api.conversationCommand.mock.calls[0]?.[0] as { input?: unknown } | undefined)?.input
const button = (label: string): ReturnType<VueWrapper['find']> => {
  const found = wrapper?.findAll('button').find((item) => item.text() === label)
  if (found === undefined) throw new Error(`missing button ${label}`)
  return found
}

beforeEach(() => {
  Object.values(api).forEach((mock) => mock.mockReset())
  api.pendingDrafts.mockResolvedValue([])
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
})

describe('SalesAssistant direct-create drafts', () => {
  it('submits entity form values and parks the form with a bare defer choice', async () => {
    api.openConversation.mockResolvedValue(view(contactTask))
    api.conversationCommand.mockRejectedValue(new Error('offline'))
    wrapper = mount(SalesAssistantChat)
    await flushPromises()

    await button('稍后补充').trigger('click')
    await flushPromises()

    expect(api.conversationCommand).toHaveBeenCalledTimes(1)
    expect(api.conversationCommand.mock.calls[0]?.[0]).toMatchObject({
      task_public_id: 'task-contact', expected_version: 5,
      input: { kind: 'submit_form', form_revision: 2, choice: 'defer', action_id: 'act-contact', expected_version: 3 },
    })
    expect(sentInput()).not.toHaveProperty('values')
  })

  it('sends the filled values when the entity form is submitted', async () => {
    api.openConversation.mockResolvedValue(view(contactTask))
    api.conversationCommand.mockRejectedValue(new Error('offline'))
    wrapper = mount(SalesAssistantChat)
    await flushPromises()

    await button('创建联系人').trigger('click')
    await flushPromises()

    expect(sentInput()).toMatchObject({
      kind: 'submit_form', form_revision: 2, values: { name: '王敏' },
    })
    expect(sentInput()).not.toHaveProperty('choice')
  })

  it('lists other parked drafts and opens one at the current conversation version', async () => {
    api.openConversation.mockResolvedValue(view(contactTask))
    api.pendingDrafts.mockResolvedValue([draft('task-contact', '联系人 王敏'), draft('task-invoice', '开票抬头')])
    api.focusConversation.mockResolvedValue({ conversation: { ...view(null), version: 6 }, submission: null })
    wrapper = mount(SalesAssistantChat)
    await flushPromises()

    const entry = wrapper.get('[data-assistant-pending-drafts]')
    expect(entry.text()).toContain('开票抬头 · 睿狐科技')
    expect(entry.text()).not.toContain('联系人 王敏')

    await button('开票抬头 · 睿狐科技').trigger('click')
    await flushPromises()

    expect(api.focusConversation).toHaveBeenCalledWith('task-invoice', 5)
    expect(api.pendingDrafts).toHaveBeenCalledTimes(2)
  })
})
