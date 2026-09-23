import { defineComponent, nextTick } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  AgentAsyncOperation,
  AgentChatRequest,
  AgentSessionResponse,
  AgentStreamEvent,
  AgentUIEnvelope,
} from '@/api/agent'
import CRMAgentChat from '@/components/agent/CRMAgentChat.vue'
import { AgentUIEnvelopeSchema } from '@/schemas/agent-contracts'
import { useUserStore } from '@/stores/user'
import { useTeamStore } from '@/stores/team'
import type { PaginatedResponse } from '@/types/pagination'

const toast = vi.hoisted(() => ({
  error: vi.fn(),
}))

const api = vi.hoisted(() => ({
  listSessions: vi.fn<() => Promise<PaginatedResponse<AgentSessionResponse>>>(),
  listMessages: vi.fn<(sessionId: number, params?: { page?: number, page_size?: number }) => Promise<PaginatedResponse<AgentUIEnvelope>>>(),
  listSessionOperationHistory: vi.fn<(sessionId: number, params?: { page?: number, page_size?: number }) => Promise<PaginatedResponse<AgentAsyncOperation>>>(),
  listMessageAnchors: vi.fn<(sessionId: number, messageIds: number[]) => Promise<AgentUIEnvelope[]>>(),
  getOperation: vi.fn<(operationPublicId: string) => Promise<AgentAsyncOperation>>(),
  getRequest: vi.fn<(sessionId: number, requestId: string) => Promise<{ status: 'IN_PROGRESS' | 'COMPLETED' | 'PARTIALLY_COMMITTED' | 'NEEDS_RECONCILIATION' | 'FAILED', message: AgentUIEnvelope | null }>>(),
  chatStream: vi.fn<(
    data: AgentChatRequest,
    onEvent: (event: AgentStreamEvent) => void,
    token: string
  ) => Promise<void>>(),
}))

vi.mock('@/api/agent', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/agent')>(),
  agentApi: api,
}))

vi.mock('vue-sonner', () => ({ toast }))

const emptyPage = (): PaginatedResponse<AgentUIEnvelope> => ({
  items: [],
  total: 0,
  page: 1,
  page_size: 100,
  total_pages: 0,
})

const emptyOperationPage = (): PaginatedResponse<AgentAsyncOperation> => ({
  items: [],
  total: 0,
  page: 1,
  page_size: 100,
  total_pages: 0,
})

const envelope = (messageId: number, text: string): AgentUIEnvelope => AgentUIEnvelopeSchema.parse({
  schema_version: 'crm.agent.ui.v1',
  message_id: messageId,
  turn_id: `turn_${messageId}`,
  role: 'assistant',
  state: 'final',
  blocks: [{ id: `text_${messageId}`, type: 'text', format: 'plain', text }],
  suggested_actions: [],
  metadata: {},
})


const compactTaskEnvelope = (
  firstState: 'ACTIVE' | 'SUBMITTED' = 'ACTIVE',
  secondState: 'ACTIVE' | 'SUBMITTED' = 'ACTIVE',
): AgentUIEnvelope => AgentUIEnvelopeSchema.parse({
  schema_version: 'crm.agent.ui.v1',
  message_id: 32,
  turn_id: 'turn_32',
  role: 'assistant',
  state: 'final',
  blocks: [
    {
      id: 'compact_task_1',
      type: 'interaction',
      interaction_id: 'int_compact_task_1',
      interaction_type: 'choice',
      presentation: 'COMPACT_TASK_COMPLETION',
      state: firstState,
      prompt: '确认 POC 环境部署情况',
      fields: [],
      options: [{ value: '已完成', label: '标记完成', description: null, disabled: false }],
      selection_mode: 'single',
      min_selections: 1,
      max_selections: 1,
      submit_on_select: true,
      submit_action_id: firstState === 'ACTIVE' ? 'act_compact_task_1' : null,
    },
    {
      id: 'compact_task_2',
      type: 'interaction',
      interaction_id: 'int_compact_task_2',
      interaction_type: 'choice',
      presentation: 'COMPACT_TASK_COMPLETION',
      state: secondState,
      prompt: '确认采购流程进度',
      fields: [],
      options: [{ value: '已完成', label: '标记完成', description: null, disabled: false }],
      selection_mode: 'single',
      min_selections: 1,
      max_selections: 1,
      submit_on_select: true,
      submit_action_id: secondState === 'ACTIVE' ? 'act_compact_task_2' : null,
    },
  ],
  suggested_actions: [],
  metadata: { route: 'WORKFLOW' },
})

const confirmationEnvelope = (state: 'ACTIVE' | 'SUBMITTED' | 'READ_ONLY'): AgentUIEnvelope => AgentUIEnvelopeSchema.parse({
  schema_version: 'crm.agent.ui.v1',
  message_id: 31,
  turn_id: 'turn_31',
  role: 'assistant',
  state: 'final',
  blocks: [{
    id: 'confirmation',
    type: 'interaction',
    interaction_id: 'int_create_follow_up',
    interaction_type: 'confirmation',
    state,
    prompt: '确认创建跟进吗？',
    fields: [],
    options: [
      { value: 'confirm', label: '确认创建', description: null, disabled: false },
      { value: 'cancel', label: '取消', description: null, disabled: false },
    ],
    selection_mode: 'single',
    submit_action_id: state === 'ACTIVE' ? 'act_confirm_follow_up' : null,
  }],
  suggested_actions: [],
  metadata: { route: 'WORKFLOW' },
})

const followUpEnvelope = (state: 'ACTIVE' | 'CANCELLED'): AgentUIEnvelope => AgentUIEnvelopeSchema.parse({
  schema_version: 'crm.agent.ui.v1',
  message_id: 33,
  turn_id: 'turn_33',
  role: 'assistant',
  state: 'final',
  blocks: [{
    id: 'follow_up_content',
    type: 'interaction',
    interaction_id: 'int_follow_up_content',
    interaction_type: 'text_input',
    business_action: 'provide_follow_up_content',
    allow_cancel: true,
    state,
    prompt: '请补充本次客户跟进的具体内容。',
    allow_blank: false,
    fields: [{
      key: 'text', label: '补充跟进内容', field_type: 'textarea', required: true,
      default_value: '', min_length: 1, max_length: 10000, options: [],
    }],
    options: [],
    submit_label: '继续',
    submit_action_id: state === 'ACTIVE' ? 'act_follow_up_content' : null,
  }],
  suggested_actions: [],
  metadata: { route: 'WORKFLOW' },
})

const AgentUIMessageActionStub = defineComponent({
  name: 'AgentUIMessage',
  emits: ['action', 'interaction', 'open-entity'],
  template: `
    <div class="agent-ui-message-stub">
      <button class="entity-action" type="button" @click="$emit('action', 'act_customer_1')">执行客户操作</button>
      <button
        class="open-customer"
        type="button"
        @click="$emit('open-entity', {
          ref_id: 'eref_customer_cus_1',
          resource: 'customer',
          public_id: 'cus_1',
          display_name: '测试客户'
        })"
      >打开客户</button>
      <button
        class="interaction-action"
        type="button"
        @click="$emit('interaction', 'act_choice_1', { choice: 'vip' })"
      >提交选择</button>
    </div>
  `,
})

const CustomerDetailSheetStub = defineComponent({
  name: 'CustomerDetailSheet',
  props: {
    visible: { type: Boolean, required: true },
    customerId: { type: String, default: null },
  },
  template: `
    <div
      data-testid="customer-detail-sheet"
      :data-visible="String(visible)"
      :data-customer-id="customerId ?? ''"
    />
  `,
})

const mountChat = (stubActions = false): VueWrapper => mount(CRMAgentChat, {
  global: {
    stubs: {
      MessageScroller: { template: '<div><slot /></div>' },
      CustomerDetailSheet: CustomerDetailSheetStub,
      ...(stubActions ? { AgentUIMessage: AgentUIMessageActionStub } : {}),
    },
  },
})

const startRequest = async (wrapper: VueWrapper, text = '查询上海客户'): Promise<void> => {
  await wrapper.get('textarea').setValue(text)
  await wrapper.get('form').trigger('submit')
  await nextTick()
}

describe('CRMAgentChat Agent UI protocol', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    useUserStore().setToken('test-token')
    vi.spyOn(crypto, 'randomUUID').mockReturnValue('550e8400-e29b-41d4-a716-446655440000')
    api.listSessions.mockReset().mockResolvedValue({
      items: [{
        id: 3,
        session_key: 'session-3',
        team_id: 1,
        user_id: 2,
        title: '测试会话',
        status: 'active',
        summary: null,
        context_json: null,
        created_time: '2026-08-12T12:00:00',
        last_modified_time: '2026-08-12T12:01:01',
      }],
      total: 1,
      page: 1,
      page_size: 20,
      total_pages: 1,
    })
    api.listMessages.mockReset().mockResolvedValue(emptyPage())
    api.listSessionOperationHistory.mockReset().mockResolvedValue(emptyOperationPage())
    api.listMessageAnchors.mockReset().mockResolvedValue([])
    api.getOperation.mockReset()
    api.getRequest.mockReset().mockResolvedValue({ status: 'COMPLETED', message: null })
    api.chatStream.mockReset().mockResolvedValue()
    toast.error.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('recovers a committed request after interruption and remount without a second POST', async () => {
    api.chatStream.mockRejectedValueOnce(new Error('connection interrupted'))
    api.getRequest.mockRejectedValueOnce(new Error('status unavailable'))
      .mockResolvedValueOnce({ status: 'COMPLETED', message: envelope(71, '客户已创建') })

    const first = mountChat()
    await flushPromises()
    await startRequest(first, '创建客户')
    await flushPromises()
    expect(first.text()).toContain('确认中')
    expect(localStorage.getItem('crm_agent_pending_requests')).toContain('550e8400-e29b-41d4-a716-446655440000')
    expect(localStorage.getItem('crm_agent_pending_requests')).not.toContain('创建客户')
    expect(localStorage.getItem('crm_agent_pending_requests')).not.toContain('test-token')
    first.unmount()

    const second = mountChat()
    await flushPromises()
    expect(api.getRequest).toHaveBeenCalledWith(3, '550e8400-e29b-41d4-a716-446655440000')
    expect(second.text()).toContain('客户已创建')
    expect(api.chatStream).toHaveBeenCalledTimes(1)
    expect(localStorage.getItem('crm_agent_pending_requests')).not.toContain('550e8400-e29b-41d4-a716-446655440000')
    second.unmount()
  })

  it('keeps ambiguous compact tasks separate and locks only each pending action', async () => {
    api.listMessages.mockResolvedValue({ ...emptyPage(), items: [compactTaskEnvelope()], total: 1, total_pages: 1 })
    api.chatStream.mockRejectedValue(new Error('connection interrupted'))
    api.getRequest.mockRejectedValue(new Error('status unavailable'))
    vi.spyOn(crypto, 'randomUUID')
      .mockReturnValueOnce('550e8400-e29b-41d4-a716-446655440001')
      .mockReturnValueOnce('550e8400-e29b-41d4-a716-446655440002')
    const wrapper = mountChat()
    await flushPromises()
    const buttons = wrapper.findAll('button[aria-label="标记完成"]')
    await buttons[0]?.trigger('click')
    await buttons[1]?.trigger('click')
    await flushPromises()
    expect(api.chatStream).toHaveBeenCalledTimes(2)
    expect(wrapper.findAll('[aria-label="已完成"]')).toHaveLength(0)
    expect(wrapper.text()).toContain('确认中')
    const stored = localStorage.getItem('crm_agent_pending_requests') ?? ''
    expect(stored).toContain('550e8400-e29b-41d4-a716-446655440001')
    expect(stored).toContain('550e8400-e29b-41d4-a716-446655440002')
    wrapper.unmount()

    const restored = mountChat()
    await flushPromises()
    expect(restored.findAll('button[aria-label="标记完成"]').every(button => button.attributes('disabled') !== undefined)).toBe(true)
    expect(api.chatStream).toHaveBeenCalledTimes(2)
    restored.unmount()
  })

  it('shows partial commits instead of a failed retry even when the stream reports an error', async () => {
    api.chatStream.mockImplementationOnce(async (_request, onEvent) => {
      onEvent({ event: 'transport_error', code: 'INTERNAL_ERROR', message: '连接中断', retryable: true, session_id: 3, status_code: 503 })
    })
    api.getRequest.mockResolvedValueOnce({ status: 'PARTIALLY_COMMITTED', message: envelope(72, '已创建客户，联系人待核对') })
    const wrapper = mountChat()
    await flushPromises()
    await startRequest(wrapper, '创建客户和联系人')
    await flushPromises()
    expect(wrapper.text()).toContain('已创建客户，联系人待核对')
    expect(wrapper.text()).toContain('部分')
    expect(wrapper.text()).not.toContain('连接中断')
    expect(api.chatStream).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
  it('binds a new session receipt without storing input and recovers it after reload', async () => {
    api.listSessions.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20, total_pages: 0 })
    useUserStore().setUserInfo({ id: 2, name: 'Tester', email: 'tester@example.test', mobile: null, avatar_url: null, employee_no: null, region: null, status: 'active', created_at: null, updated_at: null })
    useTeamStore().currentTeam = { id: 1, name: 'Team', code: 'team', owner_id: '2', created_at: '2026-08-12T12:00:00' }
    api.chatStream.mockImplementationOnce(async (_request, onEvent) => {
      onEvent({ event: 'session', session_id: 8, session_key: 'session-8' })
      throw new Error('connection interrupted')
    })
    api.getRequest.mockRejectedValue(new Error('unavailable'))
    const first = mountChat()
    await flushPromises()
    await startRequest(first, '新建客户')
    await flushPromises()
    const storedRequest = localStorage.getItem('crm_agent_pending_requests')
    expect(storedRequest).toContain('"sessionId":8')
    expect(storedRequest).not.toContain('新建客户')
    first.unmount()
    api.listSessions.mockResolvedValue({ items: [{ id: 8, session_key: 'session-8', team_id: 1, user_id: 2, title: null, status: 'active', created_time: '2026-08-12T12:00:00', last_modified_time: '2026-08-12T12:01:01' }], total: 1, page: 1, page_size: 20, total_pages: 1 })
    api.getRequest.mockResolvedValueOnce({ status: 'COMPLETED', message: envelope(73, '新会话已提交') })
    const second = mountChat()
    await flushPromises()
    expect(api.getRequest).toHaveBeenCalledWith(8, '550e8400-e29b-41d4-a716-446655440000')
    expect(second.text()).toContain('新会话已提交')
    expect(api.chatStream).toHaveBeenCalledTimes(1)
    second.unmount()
  })
  it('keeps a reconciliation action locked across reload despite stale ACTIVE history', async () => {
    api.listMessages.mockResolvedValue({ ...emptyPage(), items: [confirmationEnvelope('ACTIVE')], total: 1, total_pages: 1 })
    api.chatStream.mockRejectedValueOnce(new Error('connection interrupted'))
    api.getRequest.mockResolvedValue({ status: 'NEEDS_RECONCILIATION', message: envelope(74, '请人工核对记录') })
    const first = mountChat()
    await flushPromises()
    await first.findAll('button').find(button => button.text() === '确认创建')?.trigger('click')
    await flushPromises()
    expect(first.text()).toContain('请人工核对记录')
    expect(first.text()).toContain('请勿重复提交')
    first.unmount()
    api.getRequest.mockRejectedValue(new Error('receipt unavailable'))
    const second = mountChat()
    await flushPromises()
    expect(second.findAll('button').find(button => button.text() === '确认创建')?.attributes('disabled')).toBeDefined()
    expect(second.findAll('button').find(button => button.text() === '取消')?.attributes('disabled')).toBeDefined()
    expect(api.chatStream).toHaveBeenCalledTimes(1)
    second.unmount()
  })
  it('allows a failed compact action to retry only with a retryable failure and fresh ACTIVE history', async () => {
    api.listMessages.mockResolvedValue({ ...emptyPage(), items: [compactTaskEnvelope()], total: 1, total_pages: 1 })
    api.getRequest.mockResolvedValueOnce({ status: 'FAILED', message: AgentUIEnvelopeSchema.parse({ ...envelope(75, '操作失败'), blocks: [{ id: 'retry_error', type: 'error', code: 'INTERNAL_ERROR', title: '失败', message: '操作失败', retryable: true }] }) })
    const wrapper = mountChat()
    await flushPromises()
    await wrapper.findAll('button[aria-label="标记完成"]')[0]?.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('button[aria-label="标记完成"]')).toHaveLength(2)
    expect(wrapper.findAll('[aria-label="已完成"]')).toHaveLength(0)
    wrapper.unmount()
  })

  it('settles independent compact receipts without unlocking an unresolved sibling', async () => {
    api.listMessages.mockResolvedValue({ ...emptyPage(), items: [compactTaskEnvelope()], total: 1, total_pages: 1 })
    vi.spyOn(crypto, 'randomUUID').mockReturnValueOnce('550e8400-e29b-41d4-a716-446655440001').mockReturnValueOnce('550e8400-e29b-41d4-a716-446655440002')
    api.getRequest.mockImplementation(async (_sessionId, requestId) => requestId.endsWith('001')
      ? { status: 'COMPLETED', message: null }
      : { status: 'IN_PROGRESS', message: null })
    const wrapper = mountChat()
    await flushPromises()
    const buttons = wrapper.findAll('button[aria-label="标记完成"]')
    await buttons[0]?.trigger('click')
    await buttons[1]?.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[aria-label="已完成"]')).toHaveLength(1)
    const unresolved = wrapper.findAll('button[aria-label="标记完成"]')
    expect(unresolved).toHaveLength(1)
    expect(unresolved[0]?.attributes('disabled')).toBeDefined()
    expect(api.chatStream).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
  it('renders assistant output without an outer chat bubble', async () => {
    api.listMessages.mockResolvedValue({
      ...emptyPage(),
      items: [envelope(10, '结构化 Agent 输出')],
      total: 1,
      total_pages: 1,
    })

    const wrapper = mountChat()
    await flushPromises()

    const assistantContent = wrapper.get('.agent-chat__assistant-content')
    expect(assistantContent.text()).toContain('结构化 Agent 输出')
    expect(assistantContent.classes()).not.toContain('rounded-wolf-lg')
    expect(assistantContent.classes()).not.toContain('bg-wolf-bg-card')
    expect(assistantContent.classes()).not.toContain('border')
    expect(assistantContent.classes()).toContain('max-w-[760px]')
    wrapper.unmount()
  })

  it('uses delta text only as a temporary projection and replaces it with the final envelope', async () => {
    let emitEvent: ((event: AgentStreamEvent) => void) | undefined
    let finishStream: (() => void) | undefined
    const finalMessage = envelope(21, '上海共有 2 家客户')
    api.listMessages
      .mockResolvedValueOnce(emptyPage())
      .mockResolvedValueOnce({ ...emptyPage(), items: [finalMessage], total: 1, total_pages: 1 })
    api.chatStream.mockImplementation((_request, onEvent) => {
      emitEvent = onEvent
      return new Promise<void>(resolve => {
        finishStream = resolve
      })
    })

    const wrapper = mountChat()
    await flushPromises()
    await startRequest(wrapper)

    emitEvent?.({
      event: 'agent_ui',
      phase: 'delta',
      message_id: 21,
      turn_id: 'turn_21',
      sequence: 1,
      operations: [{ op: 'append_text', block_id: 'answer', delta: '正在查询上海客户...' }],
    })
    await nextTick()
    expect(wrapper.text()).toContain('正在查询上海客户...')

    emitEvent?.({
      event: 'agent_ui',
      phase: 'final',
      message_id: 21,
      turn_id: 'turn_21',
      sequence: 2,
      message: finalMessage,
    })
    emitEvent?.({ event: 'done', session_id: 3 })
    await nextTick()

    expect(wrapper.text()).toContain('上海共有 2 家客户')
    expect(wrapper.text()).not.toContain('正在查询上海客户...')

    finishStream?.()
    await flushPromises()
    wrapper.unmount()
  })

  it('renders structured workflow progress incrementally before the final envelope', async () => {
    let emitEvent: ((event: AgentStreamEvent) => void) | undefined
    let finishStream: (() => void) | undefined
    const finalMessage = envelope(22, '跟进任务已创建')
    api.listMessages
      .mockResolvedValueOnce(emptyPage())
      .mockResolvedValueOnce({ ...emptyPage(), items: [finalMessage], total: 1, total_pages: 1 })
    api.chatStream.mockImplementation((_request, onEvent) => {
      emitEvent = onEvent
      return new Promise<void>(resolve => {
        finishStream = resolve
      })
    })

    const wrapper = mountChat()
    await flushPromises()
    await startRequest(wrapper)

    emitEvent?.({
      event: 'agent_ui',
      phase: 'delta',
      message_id: null,
      turn_id: 'turn_22',
      sequence: 1,
      operations: [{
        op: 'upsert_block',
        block: {
          id: 'b_process_1',
          type: 'process',
          title: '执行过程',
          items: [{ key: 'understand_request', title: '理解业务操作', status: 'RUNNING' }],
        },
      }],
    })
    await nextTick()
    expect(wrapper.text()).toContain('执行过程')
    expect(wrapper.text()).toContain('理解业务操作')
    expect(wrapper.text()).toContain('执行中')
    expect(wrapper.text()).not.toContain('跟进任务已创建')

    emitEvent?.({
      event: 'agent_ui',
      phase: 'delta',
      message_id: null,
      turn_id: 'turn_22',
      sequence: 2,
      operations: [{
        op: 'upsert_block',
        block: {
          id: 'b_process_1',
          type: 'process',
          title: '执行过程',
          items: [
            { key: 'understand_request', title: '理解业务操作', status: 'COMPLETED' },
            { key: 'prepare_plan', title: '生成执行计划', status: 'RUNNING' },
          ],
        },
      }],
    })
    await nextTick()
    expect(wrapper.text()).toContain('生成执行计划')
    expect(wrapper.text()).toContain('共 2 步 · 执行中')

    emitEvent?.({
      event: 'agent_ui',
      phase: 'final',
      message_id: 22,
      turn_id: 'turn_22',
      sequence: 3,
      message: finalMessage,
    })
    emitEvent?.({ event: 'done', session_id: 3 })
    await nextTick()

    expect(wrapper.text()).toContain('跟进任务已创建')
    expect(wrapper.text()).not.toContain('生成执行计划')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)

    finishStream?.()
    await flushPromises()
    wrapper.unmount()
  })

  it('keeps a tracked transport failure behind its receipt instead of rendering a local alert', async () => {
    api.chatStream.mockImplementation(async (_request, onEvent) => {
      onEvent({
        event: 'transport_error',
        code: 'INTERNAL_ERROR',
        message: 'Agent 服务暂时不可用',
        retryable: true,
        session_id: 3,
        status_code: 503,
      })
      onEvent({ event: 'done', session_id: 3 })
    })

    const wrapper = mountChat()
    await flushPromises()
    await startRequest(wrapper)
    await flushPromises()

    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Agent 服务暂时不可用')
    expect(wrapper.findAll('.agent-ui-message')).toHaveLength(0)
    wrapper.unmount()
  })

  it('submits entity actions with only the server-issued action id', async () => {
    api.listMessages.mockResolvedValue({
      ...emptyPage(),
      items: [envelope(11, '请选择客户操作')],
      total: 1,
      total_pages: 1,
    })

    const wrapper = mountChat(true)
    await flushPromises()
    await wrapper.get('.entity-action').trigger('click')
    await flushPromises()

    expect(api.chatStream).toHaveBeenCalledWith(
      {
        session_id: 3,
        client_request_id: '550e8400-e29b-41d4-a716-446655440000',
        input: { type: 'entity_action', action_id: 'act_customer_1' },
      },
      expect.any(Function),
      'test-token',
    )
    wrapper.unmount()
  })

  it('opens the customer detail sheet directly from an entity reference', async () => {
    api.listMessages.mockResolvedValue({
      ...emptyPage(),
      items: [envelope(11, '请选择客户')],
      total: 1,
      total_pages: 1,
    })

    const wrapper = mountChat(true)
    await flushPromises()
    await wrapper.get('.open-customer').trigger('click')
    await nextTick()

    const sheet = wrapper.get('[data-testid="customer-detail-sheet"]')
    expect(sheet.attributes('data-visible')).toBe('true')
    expect(sheet.attributes('data-customer-id')).toBe('cus_1')
    expect(api.chatStream).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('submits interaction values without adding client-side business identifiers', async () => {
    api.listMessages.mockResolvedValue({
      ...emptyPage(),
      items: [envelope(11, '请选择客户分组')],
      total: 1,
      total_pages: 1,
    })

    const wrapper = mountChat(true)
    await flushPromises()
    await wrapper.get('.interaction-action').trigger('click')
    await flushPromises()

    expect(api.chatStream).toHaveBeenCalledWith(
      {
        session_id: 3,
        client_request_id: '550e8400-e29b-41d4-a716-446655440000',
        input: {
          type: 'interaction_submission',
          action_id: 'act_choice_1',
          values: { choice: 'vip' },
        },
      },
      expect.any(Function),
      'test-token',
    )
    wrapper.unmount()
  })


  it('completes a compact task from its receipt while keeping the other task interactive', async () => {
    const activeTasks = compactTaskEnvelope()
    api.listMessages.mockResolvedValue({
      ...emptyPage(),
      items: [activeTasks],
      total: 1,
      total_pages: 1,
    })
    api.getRequest.mockResolvedValueOnce({ status: 'COMPLETED', message: null })
    api.chatStream.mockImplementation(async (_request, onEvent) => {
      onEvent({
        event: 'agent_ui',
        phase: 'final',
        message_id: 99,
        turn_id: 'turn_state_update',
        sequence: 1,
        message: AgentUIEnvelopeSchema.parse({
          ...envelope(99, '不应显示的状态更新结果'),
          metadata: { display: 'STATE_UPDATE' },
        }),
      })
      onEvent({ event: 'done', session_id: 3 })
    })

    const wrapper = mountChat()
    await flushPromises()
    const completionButtons = wrapper.findAll('button[aria-label="标记完成"]')
    expect(completionButtons).toHaveLength(2)

    await completionButtons[0]?.trigger('click')
    await flushPromises()

    expect(api.chatStream).toHaveBeenCalledWith(
      {
        session_id: 3,
        client_request_id: '550e8400-e29b-41d4-a716-446655440000',
        input: {
          type: 'interaction_submission',
          action_id: 'act_compact_task_1',
          values: { choice: '已完成' },
        },
      },
      expect.any(Function),
      'test-token',
    )
    expect(wrapper.findAll('[aria-label="已完成"]')).toHaveLength(1)
    expect(wrapper.findAll('button[aria-label="标记完成"]')).toHaveLength(1)
    expect(wrapper.text()).not.toContain('不应显示的状态更新结果')
    wrapper.unmount()
  })


  it('restores a compact task after an explicit receipt failure without rendering an Agent message', async () => {
    const activeTasks = compactTaskEnvelope()
    api.listMessages.mockResolvedValue({
      ...emptyPage(),
      items: [activeTasks],
      total: 1,
      total_pages: 1,
    })
    api.getRequest.mockResolvedValueOnce({
      status: 'FAILED',
      message: AgentUIEnvelopeSchema.parse({
        schema_version: 'crm.agent.ui.v1',
        message_id: 100,
        turn_id: 'turn_state_update_failure',
        role: 'assistant',
        state: 'failed',
        blocks: [{
          id: 'error_100',
          type: 'error',
          code: 'CHECKPOINT_UNAVAILABLE',
          title: '操作未完成',
          message: '待办完成失败',
          retryable: true,
        }],
        suggested_actions: [],
        metadata: { display: 'STATE_UPDATE' },
      }),
    })

    const wrapper = mountChat()
    await flushPromises()
    await wrapper.findAll('button[aria-label="标记完成"]')[0]?.trigger('click')
    await flushPromises()

    expect(wrapper.findAll('button[aria-label="标记完成"]')).toHaveLength(2)
    expect(wrapper.findAll('[aria-label="已完成"]')).toHaveLength(0)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('待办完成失败')
    expect(toast.error).toHaveBeenCalledWith('待办完成失败')
    wrapper.unmount()
  })

  it('keeps an uncertain compact completion locked without claiming completion', async () => {
    api.listMessages
      .mockResolvedValueOnce({
        ...emptyPage(),
        items: [compactTaskEnvelope()],
        total: 1,
        total_pages: 1,
      })
      .mockRejectedValueOnce(new Error('历史刷新失败'))
    api.chatStream.mockRejectedValueOnce(new Error('连接中断'))
    api.getRequest.mockRejectedValueOnce(new Error('receipt unavailable'))

    const wrapper = mountChat()
    await flushPromises()
    await wrapper.findAll('button[aria-label="标记完成"]')[0]?.trigger('click')
    await flushPromises()

    const pending = wrapper.findAll('button[aria-label="标记完成"]')
    expect(pending).toHaveLength(2)
    expect(pending[0]?.attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('[aria-label="已完成"]')).toHaveLength(0)
    expect(api.chatStream).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
  it('ignores an older history reload that finishes after a newer compact-task reload', async () => {
    type Page = PaginatedResponse<AgentUIEnvelope>
    const deferred = <T,>() => {
      let resolvePromise: (value: T) => void = () => undefined
      const promise = new Promise<T>(resolve => { resolvePromise = resolve })
      return { promise, resolve: resolvePromise }
    }
    const firstReload = deferred<Page>()
    const secondReload = deferred<Page>()
    api.listMessages
      .mockResolvedValueOnce({
        ...emptyPage(),
        items: [compactTaskEnvelope()],
        total: 1,
        total_pages: 1,
      })
      .mockImplementationOnce(() => firstReload.promise)
      .mockImplementationOnce(() => secondReload.promise)
    vi.spyOn(crypto, 'randomUUID')
      .mockReturnValueOnce('550e8400-e29b-41d4-a716-446655440001')
      .mockReturnValueOnce('550e8400-e29b-41d4-a716-446655440002')
    api.getRequest.mockImplementation(async (_sessionId, requestId) => (
      requestId.endsWith('001')
        ? { status: 'COMPLETED' as const, message: null }
        : new Promise(() => undefined)
    ))

    const wrapper = mountChat()
    await flushPromises()
    const buttons = wrapper.findAll('button[aria-label="标记完成"]')
    await buttons[0]?.trigger('click')
    await buttons[1]?.trigger('click')
    await nextTick()

    secondReload.resolve({
      ...emptyPage(),
      items: [compactTaskEnvelope('SUBMITTED', 'SUBMITTED')],
      total: 1,
      total_pages: 1,
    })
    await flushPromises()
    firstReload.resolve({
      ...emptyPage(),
      items: [compactTaskEnvelope('SUBMITTED', 'ACTIVE')],
      total: 1,
      total_pages: 1,
    })
    await flushPromises()

    expect(wrapper.findAll('[aria-label="已完成"]')).toHaveLength(1)
    expect(wrapper.findAll('button[aria-label="标记完成"]')).toHaveLength(1)
    wrapper.unmount()
  })
  it('keeps an uncertain completion locked when a stale ACTIVE reload loses to newer history', async () => {
    type Page = PaginatedResponse<AgentUIEnvelope>
    const deferred = <T,>() => {
      let resolvePromise: (value: T) => void = () => undefined
      const promise = new Promise<T>(resolve => { resolvePromise = resolve })
      return { promise, resolve: resolvePromise }
    }
    const staleReload = deferred<Page>()
    const freshReload = deferred<Page>()
    api.listMessages
      .mockResolvedValueOnce({
        ...emptyPage(),
        items: [compactTaskEnvelope()],
        total: 1,
        total_pages: 1,
      })
      .mockImplementationOnce(() => staleReload.promise)
      .mockImplementationOnce(() => freshReload.promise)
    vi.spyOn(crypto, 'randomUUID')
      .mockReturnValueOnce('550e8400-e29b-41d4-a716-446655440001')
      .mockReturnValueOnce('550e8400-e29b-41d4-a716-446655440002')
    api.getRequest.mockImplementation(async (_sessionId, requestId) => (
      requestId.endsWith('001')
        ? { status: 'COMPLETED' as const, message: null }
        : new Promise(() => undefined)
    ))

    const wrapper = mountChat()
    await flushPromises()
    const buttons = wrapper.findAll('button[aria-label="标记完成"]')
    await buttons[0]?.trigger('click')
    await buttons[1]?.trigger('click')
    await nextTick()

    freshReload.resolve({
      ...emptyPage(),
      items: [compactTaskEnvelope('SUBMITTED', 'SUBMITTED')],
      total: 1,
      total_pages: 1,
    })
    await flushPromises()
    staleReload.resolve({
      ...emptyPage(),
      items: [compactTaskEnvelope('ACTIVE', 'ACTIVE')],
      total: 1,
      total_pages: 1,
    })
    await flushPromises()

    expect(wrapper.findAll('[aria-label="已完成"]')).toHaveLength(1)
    expect(wrapper.findAll('button[aria-label="标记完成"]')).toHaveLength(1)
    wrapper.unmount()
  })
  it('cannot submit or change a confirmation again after authoritative history marks it submitted', async () => {
    api.listMessages
      .mockResolvedValueOnce({
        ...emptyPage(),
        items: [confirmationEnvelope('ACTIVE')],
        total: 1,
        total_pages: 1,
      })
      .mockResolvedValue({
        ...emptyPage(),
        items: [confirmationEnvelope('SUBMITTED')],
        total: 1,
        total_pages: 1,
      })

    const wrapper = mountChat()
    await flushPromises()
    const confirmButton = wrapper.findAll('button').find(button => button.text() === '确认创建')
    expect(confirmButton?.attributes('disabled')).toBeUndefined()

    await confirmButton?.trigger('click')
    await flushPromises()

    expect(api.chatStream).toHaveBeenCalledTimes(1)
    const submittedButtons = wrapper.findAll('button').filter(button => (
      button.text() === '确认创建' || button.text() === '取消'
    ))
    expect(submittedButtons).toHaveLength(2)
    expect(submittedButtons.every(button => button.attributes('disabled') !== undefined)).toBe(true)

    await submittedButtons[1]?.trigger('click')
    await flushPromises()
    expect(api.chatStream).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('cannot resubmit a successful cancellation when its authoritative reload fails', async () => {
    api.listMessages.mockResolvedValueOnce({
      ...emptyPage(), items: [followUpEnvelope('ACTIVE')], total: 1, total_pages: 1,
    }).mockRejectedValueOnce(new Error('history unavailable'))
    api.chatStream.mockImplementation(async (_request, onEvent) => {
      const message = envelope(44, '已取消跟进')
      onEvent({ event: 'agent_ui', phase: 'final', message_id: 44, turn_id: 'turn_44', sequence: 1, message })
      onEvent({ event: 'done', session_id: 3 })
    })

    const wrapper = mountChat()
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '取消')?.trigger('click')
    await flushPromises()

    const cancel = wrapper.findAll('button').find(button => button.text() === '取消')
    const submit = wrapper.findAll('.agent-ui-interaction button')[1]
    expect(cancel?.attributes('disabled')).toBeDefined()
    expect(submit?.attributes('disabled')).toBeDefined()
    await cancel?.trigger('click')
    await submit?.trigger('click')
    await flushPromises()
    expect(api.chatStream).toHaveBeenCalledTimes(1)
    expect(crypto.randomUUID).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('allows retrying a failed cancellation only after authoritative ACTIVE and preserves draft text', async () => {
    api.listMessages.mockResolvedValue({
      ...emptyPage(), items: [followUpEnvelope('ACTIVE')], total: 1, total_pages: 1,
    })
    const failedReceipt = {
      status: 'FAILED' as const,
      message: AgentUIEnvelopeSchema.parse({
        schema_version: 'crm.agent.ui.v1', message_id: 44, turn_id: 'turn_44', role: 'assistant',
        state: 'final', blocks: [{
          id: 'cancel_error', type: 'error', code: 'INTERNAL_ERROR', title: '取消失败', message: '取消失败', retryable: true,
        }], suggested_actions: [], metadata: {},
      }),
    }
    api.getRequest.mockResolvedValueOnce(failedReceipt)

    const wrapper = mountChat()
    await flushPromises()
    await wrapper.get('.agent-ui-interaction textarea').setValue('需要保留的草稿')
    await wrapper.findAll('button').find(button => button.text() === '取消')?.trigger('click')
    await flushPromises()

    expect((wrapper.get('.agent-ui-interaction textarea').element as HTMLTextAreaElement).value).toBe('需要保留的草稿')
    expect(wrapper.findAll('button').find(button => button.text() === '取消')?.attributes('disabled')).toBeUndefined()
    await wrapper.findAll('button').find(button => button.text() === '取消')?.trigger('click')
    await flushPromises()
    expect(api.chatStream).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('retries failed follow-up text submission with its draft when history confirms ACTIVE', async () => {
    api.listMessages.mockResolvedValue({
      ...emptyPage(), items: [followUpEnvelope('ACTIVE')], total: 1, total_pages: 1,
    })
    api.getRequest.mockResolvedValueOnce({
      status: 'FAILED',
      message: AgentUIEnvelopeSchema.parse({
        schema_version: 'crm.agent.ui.v1', message_id: 47, turn_id: 'turn_47', role: 'assistant',
        state: 'final', blocks: [{
          id: 'submit_error', type: 'error', code: 'INTERNAL_ERROR', title: '提交失败',
          message: '提交失败', retryable: true,
        }], suggested_actions: [], metadata: {},
      }),
    })

    const wrapper = mountChat()
    await flushPromises()
    await wrapper.get('.agent-ui-interaction textarea').setValue('保留这份跟进内容')
    await wrapper.findAll('button').find(button => button.text() === '继续')?.trigger('click')
    await flushPromises()

    expect((wrapper.get('.agent-ui-interaction textarea').element as HTMLTextAreaElement).value).toBe('保留这份跟进内容')
    const submit = wrapper.findAll('button').find(button => button.text() === '继续')
    expect(submit?.attributes('disabled')).toBeUndefined()
    await submit?.trigger('click')
    await flushPromises()
    expect(api.chatStream).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('renders authoritative CANCELLED after cancellation and never resubmits its form', async () => {
    api.listMessages.mockResolvedValueOnce({
      ...emptyPage(), items: [followUpEnvelope('ACTIVE')], total: 1, total_pages: 1,
    }).mockResolvedValue({
      ...emptyPage(), items: [followUpEnvelope('CANCELLED')], total: 1, total_pages: 1,
    })

    const wrapper = mountChat()
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '取消')?.trigger('click')
    await flushPromises()

    expect(wrapper.get('.agent-ui-interaction').text()).toContain('已取消')
    expect(wrapper.find('.agent-ui-interaction textarea').exists()).toBe(true)
    expect(wrapper.find('.agent-ui-interaction button').exists()).toBe(false)
    expect(api.chatStream).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('does not retry an explicit failure without a fresh authoritative ACTIVE reload', async () => {
    api.listMessages.mockResolvedValueOnce({
      ...emptyPage(), items: [followUpEnvelope('ACTIVE')], total: 1, total_pages: 1,
    }).mockRejectedValueOnce(new Error('history unavailable'))
    api.chatStream.mockImplementation(async (_request, onEvent) => {
      onEvent({
        event: 'agent_ui', phase: 'final', message_id: 44, turn_id: 'turn_44', sequence: 1,
        message: AgentUIEnvelopeSchema.parse({
          schema_version: 'crm.agent.ui.v1', message_id: 44, turn_id: 'turn_44', role: 'assistant',
          state: 'final', blocks: [{
            id: 'cancel_error', type: 'error', code: 'INTERNAL_ERROR', title: '取消失败',
            message: '取消失败', retryable: true,
          }], suggested_actions: [], metadata: {},
        }),
      })
      onEvent({ event: 'done', session_id: 3 })
    })

    const wrapper = mountChat()
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '取消')?.trigger('click')
    await flushPromises()
    const cancel = wrapper.findAll('button').find(button => button.text() === '取消')
    expect(cancel?.attributes('disabled')).toBeDefined()
    await cancel?.trigger('click')
    await flushPromises()
    expect(api.chatStream).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('keeps a cancelled form locked after a nonretryable action error despite stale ACTIVE history', async () => {
    api.listMessages.mockResolvedValue({
      ...emptyPage(), items: [followUpEnvelope('ACTIVE')], total: 1, total_pages: 1,
    })
    api.chatStream.mockImplementation(async (_request, onEvent) => {
      onEvent({
        event: 'agent_ui', phase: 'final', message_id: 46, turn_id: 'turn_46', sequence: 1,
        message: AgentUIEnvelopeSchema.parse({
          schema_version: 'crm.agent.ui.v1', message_id: 46, turn_id: 'turn_46', role: 'assistant',
          state: 'final', blocks: [{
            id: 'rejected', type: 'error', code: 'ACTION_ALREADY_CONSUMED', title: '已处理',
            message: '该操作已处理', retryable: false,
          }], suggested_actions: [], metadata: {},
        }),
      })
      onEvent({ event: 'done', session_id: 3 })
    })

    const wrapper = mountChat()
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '取消')?.trigger('click')
    await flushPromises()
    const cancel = wrapper.findAll('button').find(button => button.text() === '取消')
    expect(cancel?.attributes('disabled')).toBeDefined()
    await cancel?.trigger('click')
    await flushPromises()
    expect(api.chatStream).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })


  it('keeps a confirmation locked when a successful final loses to stale ACTIVE history', async () => {
    api.listMessages.mockResolvedValue({
      ...emptyPage(), items: [confirmationEnvelope('ACTIVE')], total: 1, total_pages: 1,
    })
    api.chatStream.mockImplementation(async (_request, onEvent) => {
      const message = envelope(45, '已确认')
      onEvent({ event: 'agent_ui', phase: 'final', message_id: 45, turn_id: 'turn_45', sequence: 1, message })
      onEvent({ event: 'done', session_id: 3 })
    })

    const wrapper = mountChat()
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '确认创建')?.trigger('click')
    await flushPromises()
    const cancel = wrapper.findAll('button').find(button => button.text() === '取消')
    expect(cancel?.attributes('disabled')).toBeDefined()
    await cancel?.trigger('click')
    await flushPromises()
    expect(api.chatStream).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('does not retry an uncertain cancellation even when history returns ACTIVE', async () => {
    api.listMessages.mockResolvedValue({
      ...emptyPage(), items: [followUpEnvelope('ACTIVE')], total: 1, total_pages: 1,
    })
    api.chatStream.mockRejectedValue(new Error('connection interrupted'))

    const wrapper = mountChat()
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '取消')?.trigger('click')
    await flushPromises()
    const cancel = wrapper.findAll('button').find(button => button.text() === '取消')
    expect(cancel?.attributes('disabled')).toBeDefined()
    await cancel?.trigger('click')
    await flushPromises()
    expect(api.chatStream).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('ignores duplicate sequence events without applying their operations twice', async () => {
    let emitEvent: ((event: AgentStreamEvent) => void) | undefined
    let finishStream: (() => void) | undefined
    api.chatStream.mockImplementation((_request, onEvent) => {
      emitEvent = onEvent
      return new Promise<void>(resolve => {
        finishStream = resolve
      })
    })

    const wrapper = mountChat()
    await flushPromises()
    await startRequest(wrapper)

    emitEvent?.({
      event: 'agent_ui',
      phase: 'delta',
      message_id: 21,
      turn_id: 'turn_21',
      sequence: 1,
      operations: [{ op: 'append_text', block_id: 'answer', delta: '第一段' }],
    })
    emitEvent?.({
      event: 'agent_ui',
      phase: 'delta',
      message_id: 21,
      turn_id: 'turn_21',
      sequence: 2,
      operations: [{ op: 'append_text', block_id: 'answer', delta: '第二段' }],
    })
    emitEvent?.({
      event: 'agent_ui',
      phase: 'delta',
      message_id: 21,
      turn_id: 'turn_21',
      sequence: 1,
      operations: [{ op: 'append_text', block_id: 'answer', delta: '重复段' }],
    })
    await nextTick()

    expect(wrapper.text()).toContain('第一段第二段')
    expect(wrapper.text()).not.toContain('重复段')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)

    finishStream?.()
    await flushPromises()
    wrapper.unmount()
  })

  it('rejects events emitted after the authoritative final envelope', async () => {
    const finalMessage = envelope(21, '最终结果')
    api.chatStream.mockImplementation(async (_request, onEvent) => {
      onEvent({
        event: 'agent_ui',
        phase: 'final',
        message_id: 21,
        turn_id: 'turn_21',
        sequence: 1,
        message: finalMessage,
      })
      onEvent({
        event: 'agent_ui',
        phase: 'delta',
        message_id: 21,
        turn_id: 'turn_21',
        sequence: 2,
        operations: [{ op: 'append_text', block_id: 'answer', delta: '不应接受' }],
      })
    })

    const wrapper = mountChat()
    await flushPromises()
    await startRequest(wrapper)
    await flushPromises()

    expect(wrapper.text()).not.toContain('不应接受')
    expect(api.listMessages).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('rejects a sequence gap and reloads authoritative session history', async () => {
    api.chatStream.mockImplementation(async (_request, onEvent) => {
      onEvent({
        event: 'agent_ui',
        phase: 'delta',
        message_id: 21,
        turn_id: 'turn_21',
        sequence: 1,
        operations: [{ op: 'append_text', block_id: 'answer', delta: '第一段' }],
      })
      onEvent({
        event: 'agent_ui',
        phase: 'final',
        message_id: 21,
        turn_id: 'turn_21',
        sequence: 3,
        message: envelope(21, '不应直接采用的结果'),
      })
    })

    const wrapper = mountChat()
    await flushPromises()
    await startRequest(wrapper)
    await flushPromises()

    expect(wrapper.text()).not.toContain('不应直接采用的结果')
    expect(api.listMessages).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
})
