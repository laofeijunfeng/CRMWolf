import { beforeEach, vi } from 'vitest'
import type { AssistantTaskView, ConversationReply, ConversationView, TaskWaiting } from '@/schemas/assistant-contracts'
import type { SubmitStreamHandlers } from '@/api/assistant'

const mocks = vi.hoisted(() => ({
  open: vi.fn(), get: vi.fn(), text: vi.fn(), choice: vi.fn(), command: vi.fn(),
  turn: vi.fn(), task: vi.fn(), kind: vi.fn(), resume: vi.fn(), stream: vi.fn()
}))
export { mocks }
vi.mock('@/api/assistant', () => ({
  assistantApi: {
    openConversation: mocks.open, getConversation: mocks.get,
    conversationText: mocks.text, conversationChoice: mocks.choice, conversationCommand: mocks.command,
    resumeConversation: mocks.resume, conversationKind: mocks.kind,
    getTurn: mocks.turn, getTask: mocks.task, changeKind: mocks.kind
  },
  submitInputStream: mocks.stream
}))

export const draft = {
  customer: { status: 'ACCEPTED' as const, value: '睿狐科技' },
  content: { status: 'ACCEPTED' as const, value: '客户确认 POC 可行' },
  next_action: { status: 'ACCEPTED' as const, value: '周三复盘' },
  next_follow_time: { status: 'MISSING' as const }
}
export const makeTask = (overrides: Partial<AssistantTaskView> = {}): AssistantTaskView => ({
  public_id: 'ast_one', status: 'ACTIVE', goal: '客户沟通原文', activity_kind: 'FOLLOW_UP', draft,
  waiting: null, committed: [], budget_steps: 0, budget_max_steps: 50, version: 1, ...overrides
})
export const field = (overrides: Partial<TaskWaiting> = {}): TaskWaiting => ({
  type: 'FIELD', field: 'customer', question_id: 'q1', action_id: 'action1', expected_version: 1,
  prompt: '请补充客户名称', ...overrides
})
export const confirmation = (overrides: Partial<TaskWaiting> = {}): TaskWaiting => field({
  type: 'CONFIRMATION', field: 'activity_write', prompt: '确认后写入这条客户活动？',
  confirmation_payload: { kind: 'activity_write', preview: {
    customer_name: '冻结客户', activity_kind: 'OTHER_FOLLOW_UP', title: '冻结标题', summary: '冻结整理稿',
    content_json: {}, source_content: '冻结原文', score: 85, score_reason: '要素完整'
  } }, ...overrides
})
export const message = (id: string, text: string, task: AssistantTaskView | null = null, role: 'user' | 'assistant' = 'assistant'): ConversationView['messages'][number] => ({
  id, role, text, at: '2026-10-23T14:00:00', task, boundary: null, outcome: null
})
export const view = (overrides: Partial<ConversationView> = {}): ConversationView => ({
  public_id: 'asc_one', version: 0, focused_task: null, pending_choice: null, has_pending_request: false, messages: [], older_cursor: null, ...overrides
})
export const show = (state: ConversationView): void => {
  mocks.open.mockResolvedValue(state)
  mocks.get.mockResolvedValue(state)
}
export const reply = (state: ConversationView, submission: ConversationReply['submission'] = null): ConversationReply => ({ conversation: state, submission })
export const prepared = (task: AssistantTaskView, kind: 'text' | 'confirm' | 'submit_field' | 'cancel' = 'text'): NonNullable<ConversationReply['submission']> => ({
  task_public_id: task.public_id, turn_id: 'atn_one', input: { kind, text: kind === 'text' ? task.goal : null,
    choice: kind === 'confirm' ? 'confirm' : null, client_request_id: 'conv-turn-key', action_id: null, expected_version: null }
})
export const drive = (callback: (handlers: SubmitStreamHandlers) => Promise<void> | void): void => {
  mocks.stream.mockImplementation(async (_id: string, _input: unknown, handlers: SubmitStreamHandlers) => { await callback(handlers) })
}

beforeEach(() => {
  Object.values(mocks).forEach((mock) => mock.mockReset())
  show(view())
  mocks.command.mockResolvedValue(reply(view()))
})
