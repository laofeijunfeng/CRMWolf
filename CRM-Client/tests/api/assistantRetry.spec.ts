import { beforeEach, describe, expect, it, vi } from 'vitest'

const transport = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/utils/request', () => ({ default: transport }))
import { assistantApi } from '@/api/assistant'

const turn = {
  turn_id: 'atn_retry', status: 'PENDING', lease_version: 3, events: [],
  task: {
    public_id: 'ast_retry', status: 'ACTIVE', goal: '已收下的跟进', activity_kind: 'FOLLOW_UP',
    draft: { customer: { status: 'MISSING' }, content: { status: 'MISSING' },
      next_action: { status: 'MISSING' }, next_follow_time: { status: 'MISSING' } },
    waiting: null, committed: [], budget_steps: 0, budget_max_steps: 50, version: 1,
    processing_turn_id: 'atn_retry', processing_turn_status: 'PENDING'
  }
}

beforeEach(() => { transport.get.mockReset(); transport.post.mockReset() })

describe('accepted turn retry transport', () => {
  it('keeps ordinary recovery read-only and parses the execution fence', async () => {
    transport.get.mockResolvedValue(turn)
    expect((await assistantApi.getTurn('ast_retry', 'atn_retry', 4)).lease_version).toBe(3)
    expect(transport.get).toHaveBeenCalledWith('/v1/assistant/tasks/ast_retry/turns/atn_retry', { params: { after_seq: 4 } })
    expect(transport.post).not.toHaveBeenCalled()
  })

  it('retries only the observed turn version without another text submission', async () => {
    transport.post.mockResolvedValue(turn)
    expect((await assistantApi.retryTurn('ast_retry', 'atn_retry', 2, 4)).turn_id).toBe('atn_retry')
    expect(transport.post).toHaveBeenCalledWith('/v1/assistant/tasks/ast_retry/turns/atn_retry/retry', { expected_lease_version: 2, after_seq: 4 })
    expect(transport.post).toHaveBeenCalledTimes(1)
  })

  it('fails closed when the retry response has no valid execution version', async () => {
    transport.post.mockResolvedValue({ ...turn, lease_version: -1 })
    await expect(assistantApi.retryTurn('ast_retry', 'atn_retry', 2)).rejects.toThrow()
  })
})
