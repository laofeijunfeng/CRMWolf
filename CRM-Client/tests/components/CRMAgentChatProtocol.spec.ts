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
import type { PaginatedResponse } from '@/types/pagination'

const toast = vi.hoisted(() => ({
  error: vi.fn(),
}))

const api = vi.hoisted(() => ({
  listSessions: vi.fn<() => Promise<PaginatedResponse<AgentSessionResponse>>>(),
  listMessages: vi.fn<(sessionId: number, params?: { page?: number, page_size?: number }) => Promise<PaginatedResponse<AgentUIEnvelope>>>(),
  listSessionOperations: vi.fn<(sessionId: number, params?: { limit?: number }) => Promise<AgentAsyncOperation[]>>(),
  getOperation: vi.fn<(operationPublicId: string) => Promise<AgentAsyncOperation>>(),
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
    api.listSessionOperations.mockReset().mockResolvedValue([])
    api.getOperation.mockReset()
    api.chatStream.mockReset().mockResolvedValue()
    toast.error.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
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

  it('renders transport errors locally without creating an assistant Agent UI envelope', async () => {
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

    const transportAlert = wrapper.get('[role="alert"]')
    expect(transportAlert.text()).toContain('Agent 服务暂时不可用')
    expect(transportAlert.classes()).toContain('rounded-xl')
    expect(transportAlert.classes()).not.toContain('rounded-md')
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


  it('completes a compact task silently while keeping the other task interactive', async () => {
    let emitEvent: ((event: AgentStreamEvent) => void) | undefined
    let finishStream: (() => void) | undefined
    const activeTasks = compactTaskEnvelope()
    const authoritativeTasks = compactTaskEnvelope('SUBMITTED', 'ACTIVE')
    api.listMessages
      .mockResolvedValueOnce({
        ...emptyPage(),
        items: [activeTasks],
        total: 1,
        total_pages: 1,
      })
      .mockResolvedValue({
        ...emptyPage(),
        items: [authoritativeTasks],
        total: 1,
        total_pages: 1,
      })
    api.chatStream.mockImplementation((_request, onEvent) => {
      emitEvent = onEvent
      return new Promise<void>(resolve => {
        finishStream = resolve
      })
    })

    const wrapper = mountChat()
    await flushPromises()
    const completionButtons = wrapper.findAll('button[aria-label="标记完成"]')
    expect(completionButtons).toHaveLength(2)

    await completionButtons[0]?.trigger('click')
    await nextTick()

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
    expect(wrapper.text()).not.toContain('正在提交...')
    expect(wrapper.text()).not.toContain('正在处理')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)

    emitEvent?.({ event: 'session', session_id: 3, session_key: 'session-3' })
    emitEvent?.({
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
    emitEvent?.({ event: 'done', session_id: 3 })
    await nextTick()

    expect(wrapper.text()).not.toContain('不应显示的状态更新结果')
    expect(wrapper.findAll('[aria-label="已完成"]')).toHaveLength(1)
    expect(wrapper.findAll('button[aria-label="标记完成"]')).toHaveLength(1)

    finishStream?.()
    await flushPromises()

    expect(wrapper.findAll('[aria-label="已完成"]')).toHaveLength(1)
    expect(wrapper.findAll('button[aria-label="标记完成"]')).toHaveLength(1)
    wrapper.unmount()
  })


  it('restores a compact task after an explicit state-update failure without rendering an Agent message', async () => {
    const activeTasks = compactTaskEnvelope()
    api.listMessages.mockResolvedValue({
      ...emptyPage(),
      items: [activeTasks],
      total: 1,
      total_pages: 1,
    })
    api.chatStream.mockImplementation(async (_request, onEvent) => {
      onEvent({
        event: 'agent_ui',
        phase: 'final',
        message_id: 100,
        turn_id: 'turn_state_update_failure',
        sequence: 1,
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
      onEvent({ event: 'done', session_id: 3 })
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

  it('keeps an uncertain compact completion green and locked when both stream and history confirmation fail', async () => {
    api.listMessages
      .mockResolvedValueOnce({
        ...emptyPage(),
        items: [compactTaskEnvelope()],
        total: 1,
        total_pages: 1,
      })
      .mockRejectedValueOnce(new Error('历史刷新失败'))
    api.chatStream.mockRejectedValueOnce(new Error('连接中断'))

    const wrapper = mountChat()
    await flushPromises()
    await wrapper.findAll('button[aria-label="标记完成"]')[0]?.trigger('click')
    await flushPromises()

    expect(wrapper.findAll('[aria-label="已完成"]')).toHaveLength(1)
    expect(wrapper.findAll('button[aria-label="标记完成"]')).toHaveLength(1)
    expect(api.chatStream).toHaveBeenCalledTimes(1)
    expect(toast.error).toHaveBeenCalledWith('完成状态确认中，请刷新会话查看')
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

    const streams = new Map<string, { onEvent: (event: AgentStreamEvent) => void, finish: () => void }>()
    api.chatStream.mockImplementation((request, onEvent) => new Promise<void>(resolve => {
      if (request.input.type !== 'interaction_submission') throw new Error('expected interaction submission')
      streams.set(request.input.action_id, { onEvent, finish: resolve })
    }))
    vi.spyOn(crypto, 'randomUUID')
      .mockReturnValueOnce('550e8400-e29b-41d4-a716-446655440001')
      .mockReturnValueOnce('550e8400-e29b-41d4-a716-446655440002')

    const wrapper = mountChat()
    await flushPromises()
    const buttons = wrapper.findAll('button[aria-label="标记完成"]')
    await buttons[0]?.trigger('click')
    await buttons[1]?.trigger('click')
    await nextTick()

    const firstStream = streams.get('act_compact_task_1')
    firstStream?.onEvent({
      event: 'agent_ui',
      phase: 'final',
      message_id: 101,
      turn_id: 'turn_state_update_1',
      sequence: 1,
      message: AgentUIEnvelopeSchema.parse({
        ...envelope(101, '第一条完成'),
        metadata: { display: 'STATE_UPDATE' },
      }),
    })
    firstStream?.finish()
    await flushPromises()

    const secondStream = streams.get('act_compact_task_2')
    secondStream?.onEvent({
      event: 'agent_ui',
      phase: 'final',
      message_id: 102,
      turn_id: 'turn_state_update_2',
      sequence: 1,
      message: AgentUIEnvelopeSchema.parse({
        ...envelope(102, '第二条完成'),
        metadata: { display: 'STATE_UPDATE' },
      }),
    })
    secondStream?.finish()
    await flushPromises()

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

    expect(wrapper.findAll('[aria-label="已完成"]')).toHaveLength(2)
    expect(wrapper.findAll('button[aria-label="标记完成"]')).toHaveLength(0)
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

    const streams = new Map<string, { onEvent: (event: AgentStreamEvent) => void, finish: () => void }>()
    api.chatStream.mockImplementation((request, onEvent) => new Promise<void>(resolve => {
      if (request.input.type !== 'interaction_submission') throw new Error('expected interaction submission')
      streams.set(request.input.action_id, { onEvent, finish: resolve })
    }))

    const wrapper = mountChat()
    await flushPromises()
    const buttons = wrapper.findAll('button[aria-label="标记完成"]')
    await buttons[0]?.trigger('click')
    await buttons[1]?.trigger('click')
    await nextTick()

    streams.get('act_compact_task_1')?.finish()
    await flushPromises()

    const secondStream = streams.get('act_compact_task_2')
    secondStream?.onEvent({
      event: 'agent_ui',
      phase: 'final',
      message_id: 103,
      turn_id: 'turn_state_update_2',
      sequence: 1,
      message: AgentUIEnvelopeSchema.parse({
        ...envelope(103, '第二条完成'),
        metadata: { display: 'STATE_UPDATE' },
      }),
    })
    secondStream?.finish()
    await flushPromises()

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

    expect(wrapper.findAll('[aria-label="已完成"]')).toHaveLength(2)
    expect(wrapper.findAll('button[aria-label="标记完成"]')).toHaveLength(0)
    expect(toast.error).toHaveBeenCalledWith('完成状态确认中，请刷新会话查看')
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

    expect(wrapper.get('[role="alert"]').text()).toContain('Agent stream emitted an event after final')
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

    expect(wrapper.get('[role="alert"]').text())
      .toContain('Agent stream sequence contains a gap or is out of order')
    expect(api.listMessages).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
})
