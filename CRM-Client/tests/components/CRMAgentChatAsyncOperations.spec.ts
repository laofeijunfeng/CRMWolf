import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type {
  AgentAsyncOperation,
  AgentChatRequest,
  AgentRequestStatus,
  AgentSessionResponse,
  AgentStreamEvent,
  AgentUIEnvelope,
} from '@/api/agent'
import type * as AgentApiModule from '@/api/agent'
import type { PaginatedResponse } from '@/types/pagination'
import { AgentUIEnvelopeSchema } from '@/schemas/agent-contracts'

const api = vi.hoisted(() => ({
  listSessions: vi.fn<() => Promise<PaginatedResponse<AgentSessionResponse>>>(),
  listMessages: vi.fn<(sessionId: number, params?: { page?: number, page_size?: number }) => Promise<PaginatedResponse<AgentUIEnvelope>>>(),
  listSessionOperationHistory: vi.fn<(sessionId: number, params?: { page?: number, page_size?: number }) => Promise<PaginatedResponse<AgentAsyncOperation>>>(),
  listMessageAnchors: vi.fn<(sessionId: number, messageIds: number[]) => Promise<AgentUIEnvelope[]>>(),
  getOperation: vi.fn<(operationPublicId: string) => Promise<AgentAsyncOperation>>(),
  getRequest: vi.fn<(sessionId: number, requestId: string) => Promise<AgentRequestStatus>>(),
  chatStream: vi.fn<(
    data: AgentChatRequest,
    onEvent: (event: AgentStreamEvent) => void,
    token: string
  ) => Promise<void>>(),
}))

vi.mock('@/api/agent', async importOriginal => ({
  ...await importOriginal<typeof AgentApiModule>(),
  agentApi: api,
}))

import CRMAgentChat from '@/components/agent/CRMAgentChat.vue'
import AgentAsyncOperationList from '@/components/agent/AgentAsyncOperationList.vue'
import AgentUIMessage from '@/components/agent-ui/AgentUIMessage.vue'
import { useUserStore } from '@/stores/user'

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

const envelope = (messageId: number, role: 'user' | 'assistant', text: string): AgentUIEnvelope => (
  AgentUIEnvelopeSchema.parse({
    schema_version: 'crm.agent.ui.v1',
    message_id: messageId,
    turn_id: `turn_${messageId}`,
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

const page = <T,>(items: T[]): PaginatedResponse<T> => ({
  items,
  total: items.length,
  page: 1,
  page_size: 100,
  total_pages: items.length === 0 ? 0 : 1,
})

const mountChat = () => mount(CRMAgentChat, {
  global: { stubs: { MessageScroller: { template: '<div><slot /></div>' } } },
})

const expectOperationPlacement = (wrapper: VueWrapper, assistantId: number, nextUserId: number) => {
  const messageComponents = wrapper.findAllComponents(AgentUIMessage)
  const assistantMessage = messageComponents.find(message => message.props('message').message_id === assistantId)
  const nextUserMessage = messageComponents.find(message => message.props('message').message_id === nextUserId)
  const operationList = wrapper.getComponent(AgentAsyncOperationList)

  if (assistantMessage === undefined || nextUserMessage === undefined) {
    throw new Error('Expected both source assistant and later user messages to render')
  }
  expect(assistantMessage.element.compareDocumentPosition(operationList.element)
    & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(operationList.element.compareDocumentPosition(nextUserMessage.element)
    & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(operationList.props('operations').map(item => item.public_id)).toEqual([operation.public_id])
}

describe('CRMAgentChat background operation placement', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    useUserStore().setToken('test-token')
    api.listSessions.mockReset().mockResolvedValue(page([{
      id: 3,
      session_key: 'session-3',
      title: '测试会话',
      status: 'active',
      summary: null,
      created_time: '2026-08-12T12:00:00',
      last_modified_time: '2026-08-12T12:01:01',
    }]))
    api.listMessages.mockReset().mockResolvedValue(page(messages))
    api.listSessionOperationHistory.mockReset().mockResolvedValue(page([operation]))
    api.listMessageAnchors.mockReset().mockResolvedValue([])
    api.getOperation.mockReset()
    api.getRequest.mockReset().mockResolvedValue({ status: 'COMPLETED', message: null })
    api.chatStream.mockReset()
  })

  it('renders a completed background operation after the assistant response from its source turn', async () => {
    const wrapper = mountChat()
    await flushPromises()

    expectOperationPlacement(wrapper, 11, 12)
    wrapper.unmount()
  })

  it('keeps a newly persisted operation with its original turn after the user sends another message', async () => {
    api.listMessages.mockResolvedValueOnce(page([]))
      .mockResolvedValueOnce(page(messages.slice(0, 2)))
      .mockResolvedValue(page(messages))
    api.listSessionOperationHistory.mockResolvedValueOnce(page([]))
    api.chatStream
      .mockImplementationOnce(async (_request, onEvent) => {
        onEvent({ event: 'session', session_id: 3, session_key: 'session-3' })
        const message = messages[1]
        if (message === undefined) throw new Error('Missing first assistant fixture')
        onEvent({ event: 'agent_ui', phase: 'final', message_id: message.message_id, turn_id: message.turn_id, sequence: 1, message })
        onEvent({ event: 'done', session_id: 3 })
      })
      .mockImplementationOnce(async (_request, onEvent) => {
        const message = messages[3]
        if (message === undefined) throw new Error('Missing second assistant fixture')
        onEvent({ event: 'agent_ui', phase: 'final', message_id: message.message_id, turn_id: message.turn_id, sequence: 1, message })
        onEvent({ event: 'done', session_id: 3 })
      })

    const wrapper = mountChat()
    await flushPromises()
    await wrapper.get('textarea').setValue('第一条跟进')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await wrapper.get('textarea').setValue('第二条消息')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(api.chatStream).toHaveBeenCalledTimes(2)
    expectOperationPlacement(wrapper, 11, 12)
    wrapper.unmount()
  })
})
