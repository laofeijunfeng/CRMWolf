import { beforeEach, describe, expect, it, vi } from 'vitest'

const { requestMock } = vi.hoisted(() => ({
  requestMock: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('@/utils/request', () => ({
  default: requestMock,
}))

import { assistantApi } from '@/api/assistant'

const reply = {
  conversation: {
    public_id: 'conv_1',
    version: 1,
    focused_task: null,
    pending_choice: null,
    has_pending_request: false,
    messages: [],
    older_cursor: null,
  },
  submission: null,
}

describe('assistant conversation understanding timeout', () => {
  beforeEach(() => {
    requestMock.post.mockReset()
    requestMock.post.mockResolvedValue(reply)
  })

  it('keeps the understanding request open for 150 seconds', async () => {
    await assistantApi.conversationText({
      text: '下午和对方技术经理通了电话，说POC下周可以部署。',
      client_request_id: 'request-001',
      expected_version: 1,
    })
    expect(requestMock.post).toHaveBeenCalledWith(
      '/v1/assistant/conversation/messages',
      {
        text: '下午和对方技术经理通了电话，说POC下周可以部署。',
        client_request_id: 'request-001',
        expected_version: 1,
      },
      { timeout: 150_000 },
    )
  })

  it('uses the same 150 seconds when resuming that understanding', async () => {
    await assistantApi.resumeConversation()
    expect(requestMock.post).toHaveBeenCalledWith(
      '/v1/assistant/conversation/resume',
      undefined,
      { timeout: 150_000 },
    )
  })

  it('leaves the choice request on the normal timeout', async () => {
    await assistantApi.conversationChoice({
      entry_id: 'entry_1',
      choice: 'NEW',
      client_request_id: 'request-002',
      expected_version: 2,
    })
    expect(requestMock.post).toHaveBeenCalledWith('/v1/assistant/conversation/choices', {
      entry_id: 'entry_1',
      choice: 'NEW',
      client_request_id: 'request-002',
      expected_version: 2,
    })
  })
})
