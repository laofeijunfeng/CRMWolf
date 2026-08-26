import { afterEach, describe, expect, it, vi } from 'vitest'

import { agentApi, AgentProtocolError } from '@/api/agent'
import type { AgentChatRequest, AgentStreamEvent } from '@/api/agent'

const request: AgentChatRequest = {
  client_request_id: '6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be',
  input: {
    type: 'text',
    text: '我在上海有哪些客户'
  }
}

const finalEnvelope = {
  schema_version: 'crm.agent.ui.v1',
  message_id: 12,
  turn_id: 'turn_12',
  role: 'assistant',
  state: 'final',
  blocks: [
    {
      id: 'b_text_1',
      type: 'text',
      format: 'plain',
      text: '找到 1 位客户。'
    }
  ],
  suggested_actions: [],
  metadata: {
    route: 'QUERY'
  }
}

const streamResponse = (events: unknown[]): Response => {
  const body = events.map(event => `data: ${JSON.stringify(event)}\n\n`).join('')
  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' }
  })
}

describe('agentApi', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends typed input and exposes only validated Agent UI stream events', async () => {
    const fetchMock = vi.fn().mockResolvedValue(streamResponse([
      { event: 'session', session_id: 7, session_key: 'session_7' },
      {
        event: 'agent_ui',
        phase: 'final',
        message_id: 12,
        turn_id: 'turn_12',
        sequence: 1,
        message: finalEnvelope
      },
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
      {
        event: 'agent_ui',
        phase: 'delta',
        turn_id: 'turn_12',
        sequence: 1,
        operations: [{
          op: 'upsert_block',
          block: {
            id: 'b_process_1',
            type: 'process',
            title: '执行过程',
            items: [{ key: 'understand_request', title: '理解业务操作', status: 'RUNNING' }]
          }
        }]
      },
      {
        event: 'agent_ui',
        phase: 'final',
        message_id: 12,
        turn_id: 'turn_12',
        sequence: 2,
        message: finalEnvelope
      },
      { event: 'done', session_id: 7 }
    ])))
    const events: AgentStreamEvent[] = []

    await agentApi.chatStream(request, event => events.push(event), 'token')

    expect(events.map(event => event.event)).toEqual(['session', 'agent_ui', 'agent_ui', 'done'])
    expect(events[1]).toMatchObject({ event: 'agent_ui', phase: 'delta', message_id: null })
  })

  it('fails closed when the server emits a legacy or malformed event', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      { event: 'message', content: 'legacy response' }
    ])))

    await expect(agentApi.chatStream(request, () => undefined, 'token')).rejects.toBeInstanceOf(AgentProtocolError)
  })

  it('accepts transport_error as a terminal event when no session can be established', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      {
        event: 'transport_error',
        code: 'PERMISSION_DENIED',
        message: '无权访问该会话。',
        retryable: false,
        status_code: 403
      }
    ])))
    const events: AgentStreamEvent[] = []

    await agentApi.chatStream(request, event => events.push(event), 'token')

    expect(events.map(event => event.event)).toEqual(['transport_error'])
  })

  it('fails closed when the stream ends without done', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      { event: 'session', session_id: 7, session_key: 'session_7' }
    ])))

    await expect(agentApi.chatStream(request, () => undefined, 'token')).rejects.toThrow('Agent stream ended before done')
  })
})
