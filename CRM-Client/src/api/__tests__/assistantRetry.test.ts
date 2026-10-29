import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const requestPost = vi.hoisted(() => vi.fn())

vi.mock('@/utils/request', () => ({
  default: {
    post: requestPost,
    get: vi.fn(),
  },
}))

import { assistantApi } from '@/api/assistant'

describe('assistant retry API', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    requestPost.mockReset()
  })

  it('retries the same entry without a new client request id', async () => {
    requestPost.mockResolvedValue({
      conversation: {
        public_id: 'asc_1',
        version: 4,
        focused_task: null,
        pending_choice: null,
        has_pending_request: false,
        messages: [],
        older_cursor: null,
      },
      submission: null,
    })

    await assistantApi.retryConversationEntry('acm_1', 3)

    expect(requestPost).toHaveBeenCalledWith(
      '/v1/assistant/conversation/entries/acm_1/retry',
      { expected_version: 3 },
      { timeout: 150_000 },
    )
    const body = requestPost.mock.calls[0]?.[1] as Record<string, unknown>
    expect(body).not.toHaveProperty('client_request_id')
    expect(body).not.toHaveProperty('text')
  })
})
