import { beforeEach, vi } from 'vitest'
import type { AssistantTaskView, ConversationReply, ConversationView, TaskWaiting } from '@/schemas/assistant-contracts'
import type { SubmitStreamHandlers } from '@/api/assistant'

const mocks = vi.hoisted(() => ({
  open: vi.fn(), get: vi.fn(), text: vi.fn(), choice: vi.fn(), command: vi.fn(),
  turn: vi.fn(), retry: vi.fn(), task: vi.fn(), kind: vi.fn(), resume: vi.fn(), stream: vi.fn()
}))
export { mocks }
vi.mock('@/api/assistant', () => ({
  assistantApi: {
    openConversation: mocks.open, getConversation: mocks.get,
    conversationText: mocks.text, conversationChoice: mocks.choice, conversationCommand: mocks.command,
    resumeConversation: mocks.resume, conversationKind: mocks.kind,
    getTurn: mocks.turn, retryTurn: mocks.retry, getTask: mocks.task, changeKind: mocks.kind
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
  id, role, text, at: '2026-10-23T14:00:00', task, boundary: null, outcome: null, ui: null
})

const fixtureEnvelope = (
  item: ConversationView['messages'][number],
  active: boolean,
  pendingEntryId: string | null
): ConversationView['messages'][number]['ui'] => {
  if (item.role !== 'assistant') return null
  if (item.boundary !== null) {
    const boundaryActive = pendingEntryId === item.boundary.entry_id
    return {
      schema_version: 'crm.agent.ui.v1' as const,
      message_id: 1,
      turn_id: item.id,
      role: 'assistant' as const,
      state: 'final' as const,
      suggested_actions: [],
      metadata: { display: 'MESSAGE' as const, route: 'CLARIFY' as const, accessibility_label: item.boundary.prompt },
      blocks: [{
        id: 'b_interaction_1', type: 'interaction' as const, interaction_id: `ix-${item.id}`, interaction_type: 'choice' as const,
        business_action: 'assistant_boundary', state: boundaryActive ? 'ACTIVE' as const : 'READ_ONLY' as const, prompt: item.boundary.prompt,
        fields: [], facts: [], options: [
          { value: 'CONTINUE', label: '接着刚才', description: null, disabled: false },
          { value: 'NEW', label: '另记一件', description: null, disabled: false }
        ],
        selection_mode: 'single' as const, min_selections: 1, max_selections: 1, submit_on_select: true, submit_label: '提交',
        allow_cancel: false, submit_action_id: boundaryActive ? `boundary:${item.boundary.entry_id}` : null
      }]
    }
  }
  const base = {
    schema_version: 'crm.agent.ui.v1' as const,
    message_id: 1,
    turn_id: item.id,
    role: 'assistant' as const,
    state: 'final' as const,
    suggested_actions: [],
    metadata: { display: 'MESSAGE' as const, route: 'WORKFLOW' as const, accessibility_label: item.text }
  }
  if (item.outcome === 'activity_written') {
    return { ...base, blocks: [{ id: 'b_result_1', type: 'action_result', action_id: item.id, status: 'SUCCESS', title: '已写入', message: item.text }] }
  }
  if (item.outcome === 'failure') {
    return { ...base, state: 'failed', blocks: [{ id: 'b_error_1', type: 'error', code: 'INTERNAL_ERROR', title: '遇到问题', message: item.text, retryable: false }] }
  }
  const waiting = item.task?.waiting ?? null
  if (waiting?.type === 'CONFIRMATION' && waiting.confirmation_payload?.kind === 'activity_write') {
    const preview = waiting.confirmation_payload.preview
    const facts = [
      { key: 'customer', label: '客户', value: preview.customer_name },
      { key: 'title', label: '标题', value: preview.title ?? '' },
      { key: 'summary', label: '摘要', value: preview.summary ?? '' },
      { key: 'next_action', label: '行动项', value: preview.next_action ?? '未提供行动项' }
    ].filter((fact) => fact.value !== '')
    const confirmationBlocks = item.text !== waiting.prompt
      ? [{ id: 'b_text_1', type: 'text' as const, format: 'plain' as const, text: item.text }]
      : []
    return {
      ...base,
      blocks: [...confirmationBlocks, {
        id: 'b_interaction_1', type: 'interaction', interaction_id: `ix-${item.id}`, interaction_type: 'confirmation',
        business_action: 'confirm_activity_write', state: active ? 'ACTIVE' : 'READ_ONLY', prompt: waiting.prompt,
        fields: [], facts, options: [
          { value: 'confirm', label: '确认写入', description: null, disabled: false },
          { value: 'cancel', label: '取消', description: null, disabled: false }
        ],
        selection_mode: 'single', submit_on_select: true, submit_label: '提交', allow_cancel: false,
        submit_action_id: active ? (waiting.action_id ?? 'act') : null
      }]
    }
  }
  if (waiting?.type === 'OBJECT_SELECTION' || waiting?.type === 'ACTIVITY_KIND' || waiting?.field === 'temporal_choice') {
    const options = waiting.type === 'ACTIVITY_KIND'
      ? [{ value: 'ONLINE_MEETING', label: '线上会议' }, { value: 'OFFLINE_MEETING', label: '线下会议' }, { value: 'FOLLOW_UP', label: '普通跟进' }]
      : (waiting.candidates ?? []).map((candidate) => ({
          value: candidate.id,
          label: 'account_name' in candidate ? candidate.account_name : candidate.label
        }))
    const choiceBlocks = item.text !== waiting.prompt
      ? [{ id: 'b_text_1', type: 'text' as const, format: 'plain' as const, text: item.text }]
      : []
    return {
      ...base,
      blocks: [...choiceBlocks, {
        id: 'b_interaction_1', type: 'interaction', interaction_id: `ix-${item.id}`, interaction_type: 'choice',
        business_action: waiting.field === 'temporal_choice' ? 'resolve_temporal_choice' : 'select_customer',
        state: active ? 'ACTIVE' : 'READ_ONLY', prompt: waiting.prompt, fields: [], facts: [],
        options: options.map((option) => ({ ...option, description: null, disabled: false })),
        selection_mode: 'single', min_selections: 1, max_selections: 1, submit_on_select: true, submit_label: '提交',
        allow_cancel: false, submit_action_id: active ? (waiting.action_id ?? 'act') : null
      }]
    }
  }
  if (waiting?.type === 'FIELD') {
    const chips: string[] = []
    const draft = item.task?.draft
    if (draft?.customer.status === 'ACCEPTED' && (draft.customer.value ?? '') !== '') chips.push(`客户：${draft.customer.value}`)
    const blocks = []
    if (item.text !== waiting.prompt) blocks.push({ id: 'b_text_1', type: 'text' as const, format: 'plain' as const, text: item.text })
    if (chips.length > 0) blocks.push({ id: 'b_notice_1', type: 'notice' as const, tone: 'info' as const, title: '已确认', text: chips.join('、') })
    blocks.push({
      id: 'b_interaction_1', type: 'interaction' as const, interaction_id: `ix-${item.id}`, interaction_type: 'text_input' as const,
      business_action: 'collect_field', state: active ? 'ACTIVE' as const : 'READ_ONLY' as const, prompt: waiting.prompt,
      fields: [{ key: waiting.field ?? 'answer', label: waiting.field === 'customer' ? '客户名称' : '补充内容', field_type: 'text' as const, required: true, min_length: 1, max_length: 2000, default_value: null, options: [] }],
      facts: [], options: [], allow_blank: false, allow_cancel: false, submit_label: '提交',
      submit_action_id: active ? (waiting.action_id ?? 'act') : null
    })
    return { ...base, blocks }
  }
  return { ...base, blocks: [{ id: 'b_text_1', type: 'text', format: 'plain', text: item.text }] }
}

const withFixtureUi = (state: ConversationView): ConversationView => {
  const focused = state.focused_task
  let liveId: string | null = null
  if (focused?.status === 'ACTIVE' && focused.waiting != null) {
    for (const item of state.messages) {
      const waiting = item.task?.waiting
      if (item.task?.public_id === focused.public_id && waiting?.action_id === focused.waiting.action_id && waiting?.expected_version === focused.waiting.expected_version && waiting?.question_id === focused.waiting.question_id) {
        liveId = item.id
      }
    }
  }
  return {
    ...state,
    messages: state.messages.map((item) => ({ ...item, ui: item.ui ?? fixtureEnvelope(item, item.id === liveId, state.pending_choice?.entry_id ?? null) }))
  }
}

export const view = (overrides: Partial<ConversationView> = {}): ConversationView => withFixtureUi({
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
