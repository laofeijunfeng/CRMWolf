import { afterEach, describe, expect, it, vi } from 'vitest'

const requestGet = vi.hoisted(() => vi.fn())

vi.mock('@/utils/request', () => ({
  default: {
    get: requestGet,
  },
}))

import { agentApi, AgentProtocolError } from '@/api/agent'
import type { AgentChatRequest, AgentStreamEvent } from '@/api/agent'

const request: AgentChatRequest = {
  client_request_id: '6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be',
  input: { type: 'text', text: '我在上海有哪些客户' }
}

const finalEnvelope = {
  schema_version: 'crm.agent.ui.v1', message_id: 12, turn_id: 'turn_12', role: 'assistant', state: 'final',
  blocks: [{ id: 'b_text_1', type: 'text', format: 'plain', text: '找到 1 位客户。' }],
  suggested_actions: [], metadata: { route: 'QUERY' }
}

const streamResponse = (events: unknown[]): Response => new Response(
  events.map(event => `data: ${JSON.stringify(event)}\n\n`).join(''),
  { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
)

describe('agentApi', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    requestGet.mockReset()
  })

  it('sends typed input and exposes only validated Agent UI stream events', async () => {
    const fetchMock = vi.fn().mockResolvedValue(streamResponse([
      { event: 'session', session_id: 7, session_key: 'session_7' },
      { event: 'agent_ui', phase: 'final', message_id: 12, turn_id: 'turn_12', sequence: 1, message: finalEnvelope },
      { event: 'done', session_id: 7 }
    ]))
    vi.stubGlobal('fetch', fetchMock)
    const events: AgentStreamEvent[] = []

    await agentApi.chatStream(request, event => events.push(event), 'token')

    expect(fetchMock).toHaveBeenCalledOnce()
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit | undefined
    expect(JSON.parse(String(init?.body))).toEqual(request)
    expect(events.map(event => event.event)).toEqual(['session', 'agent_ui', 'done'])
  })

  it('accepts delta events when the server omits the nullable message_id', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      { event: 'session', session_id: 7, session_key: 'session_7' },
      { event: 'agent_ui', phase: 'delta', turn_id: 'turn_12', sequence: 1, operations: [{
        op: 'upsert_block', block: { id: 'b_process_1', type: 'process', title: '执行过程', items: [{ key: 'understand_request', title: '理解业务操作', status: 'RUNNING' }] }
      }] },
      { event: 'agent_ui', phase: 'final', message_id: 12, turn_id: 'turn_12', sequence: 2, message: finalEnvelope },
      { event: 'done', session_id: 7 }
    ])))
    const events: AgentStreamEvent[] = []

    await agentApi.chatStream(request, event => events.push(event), 'token')

    expect(events.map(event => event.event)).toEqual(['session', 'agent_ui', 'agent_ui', 'done'])
    expect(events[1]).toMatchObject({ event: 'agent_ui', phase: 'delta', message_id: null })
  })

  it('fails closed when the server emits a legacy or malformed event', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([{ event: 'message', content: 'legacy response' }])))
    await expect(agentApi.chatStream(request, () => undefined, 'token')).rejects.toBeInstanceOf(AgentProtocolError)
  })

  it('accepts transport_error as a terminal event when no session can be established', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([{ event: 'transport_error', code: 'PERMISSION_DENIED', message: '无权访问该会话。', retryable: false, status_code: 403 }])))
    const events: AgentStreamEvent[] = []
    await agentApi.chatStream(request, event => events.push(event), 'token')
    expect(events.map(event => event.event)).toEqual(['transport_error'])
  })

  it('fails closed when the stream ends without done', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([{ event: 'session', session_id: 7, session_key: 'session_7' }])))
    await expect(agentApi.chatStream(request, () => undefined, 'token')).rejects.toThrow('Agent stream ended before done')
  })

  it('loads paginated operation history with strict typed validation', async () => {
    const operation = {
      public_id: 'op_1', request_id: 'req_1', team_id: 1, user_id: 2, session_id: 7,
      source_user_message_id: 11, source_assistant_message_id: 12, operation_type: 'customer_activity_post_commit',
      resource_type: 'customer_activity', resource_id: 101, resource_public_id: 'activity_101', status: 'SUCCEEDED',
      summary: 'done', current_step: null, graph_thread_id: 'thread_1', result: {}, error_message: null,
      started_time: null, finished_time: null, next_retry_at: null, attempt_count: 1,
      created_time: '2026-07-29T00:00:00Z', updated_time: '2026-07-29T00:00:01Z', events: [],
    }
    const response = { items: [operation], total: 1, page: 2, page_size: 10, total_pages: 2 }
    requestGet.mockResolvedValueOnce(response)

    await expect(agentApi.listSessionOperationHistory(7, { page: 2, page_size: 10 })).resolves.toEqual(response)
    expect(requestGet).toHaveBeenCalledWith('/v1/agent/sessions/7/operations/history', { params: { page: 2, page_size: 10 } })
  })

  it('loads exact message anchors with repeated message_id query parameters and strict envelopes', async () => {
    const anchor = {
      schema_version: 'crm.agent.ui.v1', message_id: 12, turn_id: 'turn_12', role: 'assistant', state: 'final',
      blocks: [{ id: 'b_text_12', type: 'text', format: 'plain', text: 'anchor' }], suggested_actions: [], metadata: {},
    }
    requestGet.mockResolvedValueOnce([anchor])

    await expect(agentApi.listMessageAnchors(7, [12, 13])).resolves.toMatchObject([anchor])
    expect(requestGet).toHaveBeenCalledWith('/v1/agent/sessions/7/messages/anchors', { params: { message_id: [12, 13] } })
  })
})
