import { flushPromises, mount } from '@vue/test-utils'
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

const envelope = (messageId: number, role: 'user' | 'assistant', text: string): AgentUIEnvelope => (
  AgentUIEnvelopeSchema.parse({
    schema_version: 'crm.agent.ui.v1',
    message_id: messageId,
    turn_id: `turn_${Math.ceil(messageId / 2)}`,
    role,
    state: 'final',
    blocks: [{ id: `text_${messageId}`, type: 'text', format: 'plain', text }],
    suggested_actions: [],
    metadata: {},
  })
)

const messages = [
  envelope(10, 'user', '第一条跟进'),
  envelope(11, 'assistant', '第一条已记录'),
  envelope(12, 'user', '第二条消息'),
  envelope(13, 'assistant', '第二条已处理'),
]

const paginatedMessages = (items: AgentUIEnvelope[]): PaginatedResponse<AgentUIEnvelope> => ({
  items,
  total: items.length,
  page: 1,
  page_size: 100,
  total_pages: items.length === 0 ? 0 : 1,
})

const operation: AgentAsyncOperation = {
  public_id: 'aop_first_turn',
  request_id: 'request-first-turn',
  team_id: 1,
  user_id: 2,
  session_id: 3,
  source_user_message_id: 10,
  source_assistant_message_id: null,
  operation_type: 'customer_intelligence_refresh',
  resource_type: 'customer',
  resource_id: 18,
  resource_public_id: 'cus_18',
  status: 'SUCCEEDED',
  summary: '客户档案已更新',
  current_step: null,
  graph_thread_id: 'thread-1',
  result: {},
  error_message: null,
  started_time: '2026-08-12T12:00:00',
  finished_time: '2026-08-12T12:00:05',
  next_retry_at: null,
  attempt_count: 1,
  created_time: '2026-08-12T12:00:00',
  updated_time: '2026-08-12T12:00:05',
  events: [],
}

const mountChat = () => mount(CRMAgentChat, {
  global: {
    stubs: {
      MessageScroller: { template: '<div><slot /></div>' },
    },
  },
})

describe('CRMAgentChat background operation placement', () => {
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
    api.listMessages.mockReset().mockResolvedValue(paginatedMessages(messages))
    api.listSessionOperations.mockReset().mockResolvedValue([operation])
    api.getOperation.mockReset()
    api.chatStream.mockReset().mockResolvedValue()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('renders a completed background operation after the assistant response from its source turn', async () => {
    const wrapper = mountChat()
    await flushPromises()

    const text = wrapper.text()
    expect(text.indexOf('后台任务')).toBeGreaterThan(text.indexOf('第一条已记录'))
    expect(text.indexOf('后台任务')).toBeLessThan(text.indexOf('第二条消息'))
    const operationRegion = wrapper.get('.agent-chat__operations')
    expect(operationRegion.classes()).toEqual(expect.arrayContaining(['max-w-[760px]', 'flex-1']))
    expect(operationRegion.element.parentElement?.tagName).toBe('ARTICLE')
    expect(operationRegion.element.previousElementSibling?.getAttribute('aria-hidden')).toBe('true')
    wrapper.unmount()
  })

  it('shows every automatically transitioned historical task as a visible result card', async () => {
    api.listSessionOperations.mockResolvedValue([{
      ...operation,
      operation_type: 'customer_activity_post_commit',
      result: {
        post_commit: {
          automatic_task_transitions: [
            {
              task_public_id: 'fut_private_package',
              title: '提供私有环境安装包和试用方案',
              action: 'COMPLETE',
              previous_status: 'OPEN',
              new_status: 'COMPLETED',
            },
          ],
        },
      },
    }])

    const wrapper = mountChat()
    await flushPromises()

    expect(wrapper.text()).toContain('提供私有环境安装包和试用方案')
    expect(wrapper.text()).toContain('已自动完成')
    wrapper.unmount()
  })

  it('loads the operation after a typed Agent UI stream is persisted', async () => {
    const finalAssistant = envelope(21, 'assistant', '本轮已记录')
    const completedHistory = [envelope(20, 'user', '本轮跟进'), finalAssistant]
    api.listMessages
      .mockResolvedValueOnce(paginatedMessages([]))
      .mockResolvedValueOnce(paginatedMessages(completedHistory))
    api.listSessionOperations
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{ ...operation, source_user_message_id: 20, source_assistant_message_id: 21 }])
    api.chatStream.mockImplementation(async (_request, onEvent) => {
      onEvent({ event: 'session', session_id: 3, session_key: 'session-3' })
      onEvent({
        event: 'agent_ui',
        phase: 'final',
        message_id: 21,
        turn_id: finalAssistant.turn_id,
        sequence: 1,
        message: finalAssistant,
      })
      onEvent({ event: 'done', session_id: 3 })
    })

    const wrapper = mountChat()
    await flushPromises()
    await wrapper.get('textarea').setValue('本轮跟进')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(api.chatStream).toHaveBeenCalledWith(
      {
        session_id: 3,
        client_request_id: '550e8400-e29b-41d4-a716-446655440000',
        input: { type: 'text', text: '本轮跟进' },
      },
      expect.any(Function),
      'test-token',
    )
    const text = wrapper.text()
    expect(text.indexOf('后台任务')).toBeGreaterThan(text.indexOf('本轮已记录'))
    wrapper.unmount()
  })

  it('refreshes Agent UI history when a session operation becomes terminal', async () => {
    vi.useFakeTimers()
    const runningOperation: AgentAsyncOperation = {
      ...operation,
      status: 'RUNNING',
      finished_time: null,
    }
    const completedOperation: AgentAsyncOperation = {
      ...runningOperation,
      status: 'SUCCEEDED',
      finished_time: '2026-08-12T12:00:05',
      updated_time: '2026-08-12T12:00:05',
    }
    api.listSessionOperations.mockResolvedValueOnce([runningOperation])
    api.getOperation.mockResolvedValueOnce(completedOperation)

    const wrapper = mountChat()
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2_000)
    await flushPromises()

    expect(api.listMessages).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('collapses multiple operations into one list until the user expands it', async () => {
    api.listSessionOperations.mockResolvedValue([
      operation,
      {
        ...operation,
        public_id: 'aop_post_commit',
        request_id: 'pcj_first_turn',
        operation_type: 'customer_activity_post_commit',
        resource_type: 'customer_activity',
        summary: '跟进任务已完成对账',
      },
    ])

    const wrapper = mountChat()
    await flushPromises()

    expect(wrapper.text()).toContain('后台任务')
    expect(wrapper.text()).not.toContain('客户档案更新')
    expect(wrapper.text()).not.toContain('跟进任务对账')

    await wrapper.get('.agent-async-operation-list__trigger').trigger('click')
    expect(wrapper.text()).toContain('客户档案更新')
    expect(wrapper.text()).toContain('跟进任务对账')
    wrapper.unmount()
  })
})
