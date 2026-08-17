import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { FollowUpConfirmationResolveResponse } from '@/api/followUpTask'

const apiMocks = vi.hoisted(() => ({
  getPendingCount: vi.fn(),
  resolve: vi.fn(),
}))

vi.mock('@/api/followUpTask', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/followUpTask')>()
  return {
    ...original,
    followUpConfirmationApi: apiMocks,
  }
})

import { useFollowUpConfirmationStore } from '@/stores/followUpConfirmation'

const resolvedResponse: FollowUpConfirmationResolveResponse = {
  case: null,
  decision: {
    action: 'COMPLETE',
    confidence: 1,
    reason: '用户确认已完成',
    resolved: true,
    proposed_due_at: null,
    proposed_due_at_text: null,
  },
  application: {
    status: 'APPLIED',
    case_public_id: 'fuc_case_1',
    task_public_id: 'fut_1',
    action: 'COMPLETE',
    skip_reason: null,
    execution_results: [],
  },
  assistant_follow_up_prompt: null,
  usage_policy: { rule: 'application service' },
}

describe('useFollowUpConfirmationStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    apiMocks.getPendingCount.mockResolvedValue(1)
    apiMocks.resolve.mockResolvedValue(resolvedResponse)
  })

  it('loads the lightweight pending count used by existing navigation status', async () => {
    apiMocks.getPendingCount.mockResolvedValue(108)
    const store = useFollowUpConfirmationStore()

    await store.fetchPendingCount()

    expect(store.pendingCount).toBe(108)
  })

  it('resolves a task-owned case and refreshes only the lightweight count', async () => {
    apiMocks.getPendingCount.mockResolvedValue(0)
    const store = useFollowUpConfirmationStore()
    store.pendingCount = 1

    const result = await store.resolveCase('fuc_case_1', '已完成')

    expect(apiMocks.resolve).toHaveBeenCalledWith('fuc_case_1', { reply_text: '已完成' })
    expect(apiMocks.getPendingCount).toHaveBeenCalledOnce()
    expect(result).toEqual(resolvedResponse)
    expect(store.pendingCount).toBe(0)
    expect(store.resolvingCaseId).toBeNull()
  })

  it('keeps a successful resolution authoritative when count refresh fails', async () => {
    apiMocks.getPendingCount.mockRejectedValue(new Error('count refresh unavailable'))
    const store = useFollowUpConfirmationStore()
    store.pendingCount = 1

    const result = await store.resolveCase('fuc_case_1', '已完成')

    expect(result).toEqual(resolvedResponse)
    expect(store.pendingCount).toBe(0)
    expect(store.postResolveRefreshError).toBe('确认已处理，但待确认数量刷新失败，请稍后重试。')
    expect(store.resolvingCaseId).toBeNull()
  })
})
