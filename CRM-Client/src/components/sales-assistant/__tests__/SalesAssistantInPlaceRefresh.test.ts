import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { AxiosError, AxiosHeaders } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type * as AssistantApi from '@/api/assistant'
import { InteractionBlockSchema } from '@/schemas/agent-contracts'
import type { AssistantTaskView, ConversationView, TaskWaiting } from '@/schemas/assistant-contracts'

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
const task = (overrides: Partial<AssistantTaskView>): AssistantTaskView => ({
  public_id: 'task-contact', status: 'ACTIVE', goal: '新建联系人', task_kind: 'contact_create',
  draft: {
    customer: { status: 'MISSING' }, content: { status: 'MISSING' },
    next_action: { status: 'MISSING' }, next_follow_time: { status: 'MISSING' },
  },
  committed: [], budget_steps: 1, budget_max_steps: 10, version: 3,
  processing_turn_id: null, processing_turn_status: null, reprocess_turn_id: null, waiting,
  ...overrides,
})
const formBlock = (state: 'ACTIVE' | 'SUBMITTED'): ReturnType<typeof InteractionBlockSchema.parse> => InteractionBlockSchema.parse({
  id: 'b-contact', type: 'interaction', interaction_id: 'q-contact', interaction_type: 'form',
  business_action: 'create_contact', allow_cancel: true, state, prompt: '请补全联系人',
  submit_label: '提交', options: [],
  fields: [{ key: 'name', label: '姓名', field_type: 'text', required: true, default_value: '王敏', min_length: 1, max_length: 50, options: [] }],
  ...(state === 'ACTIVE' ? { submit_action_id: 'act-contact' } : { submit_action_id: null, submitted_values: { name: '王敏' } }),
})
const view = (version: number, focused: AssistantTaskView, state: 'ACTIVE' | 'SUBMITTED'): ConversationView => ({
  public_id: 'conversation-1', version, focused_task: focused,
  pending_choice: null, has_pending_request: false, older_cursor: null,
  messages: [{
    id: 'entry-1:reply', role: 'assistant', text: '请补全联系人', at: '2026-11-26T01:00:00',
    task: focused, boundary: null, outcome: null,
    ui: {
      schema_version: 'crm.agent.ui.v1', message_id: 1, turn_id: 'entry-1:reply', role: 'assistant', state: 'final',
      blocks: [formBlock(state)], suggested_actions: [], metadata: { display: 'MESSAGE', route: 'WORKFLOW' },
    },
  }],
})

let wrapper: VueWrapper | undefined

beforeEach(() => {
  Object.values(api).forEach((mock) => mock.mockReset())
  api.pendingDrafts.mockResolvedValue([])
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
})

describe('SalesAssistant in-place conversation refresh', () => {
  it('updates the same message element when a later GET returns the same message id with a new interaction state', async () => {
    api.openConversation.mockResolvedValue(view(5, task({}), 'ACTIVE'))
    api.conversationCommand.mockRejectedValue(new AxiosError('conflict', 'ERR_BAD_REQUEST', undefined, undefined, {
      status: 409, statusText: 'Conflict', data: { detail: '该卡片已在其他地方处理' }, headers: {},
      config: { headers: new AxiosHeaders() },
    }))
    api.getConversation.mockResolvedValue(view(6, task({ version: 4, waiting: null }), 'SUBMITTED'))
    wrapper = mount(SalesAssistantChat)
    await flushPromises()

    expect(wrapper.findAll('.agent-ui-message')).toHaveLength(1)
    const messageElement = wrapper.get('.agent-ui-message').element
    const submit = wrapper.findAll('button').filter((item) => item.text() === '提交')
    expect(submit).toHaveLength(1)
    expect(wrapper.find('[data-agent-ui-collapsed-form]').exists()).toBe(false)

    await submit[0]?.trigger('click')
    await flushPromises()

    expect(api.getConversation).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('.agent-ui-message')).toHaveLength(1)
    expect(wrapper.get('.agent-ui-message').element).toBe(messageElement)
    expect(wrapper.get('[data-agent-ui-collapsed-form]').text()).toBe('姓名：王敏')
    expect(wrapper.findAll('button').filter((item) => item.text() === '提交')).toHaveLength(0)
  })
})
