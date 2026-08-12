import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type {
  FollowUpConfirmationCase,
  FollowUpConfirmationCaseListResponse,
  FollowUpConfirmationResolveResponse
} from '@/api/followUpTask'

const apiMocks = vi.hoisted(() => ({
  list: vi.fn(),
  getPendingCount: vi.fn(),
  resolve: vi.fn()
}))

vi.mock('@/api/followUpTask', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/followUpTask')>()
  return {
    ...original,
    followUpConfirmationApi: apiMocks
  }
})

import { useFollowUpConfirmationStore } from '@/stores/followUpConfirmation'

const confirmationCase: FollowUpConfirmationCase = {
  id: 'fuc_case_1',
  public_id: 'fuc_case_1',
  status: 'PENDING',
  question_text: '上次安排的任务这次是否已经完成？',
  suggested_action: 'COMPLETE',
  owner_id: '2',
  creator_id: '2',
  customer: {
    id: 'cus_1',
    public_id: 'cus_1',
    name: '中移互联网',
    account_name: '中移互联网'
  },
  task: {
    id: 'fut_1',
    public_id: 'fut_1',
    title: '反馈新的数据分级分类收集表',
    status: 'OPEN',
    due_at: '2026-08-13T09:00:00',
    due_at_text: '本周四'
  },
  expires_at: null,
  prompt_count: 0,
  last_prompted_at: null,
  unresolved_reply_count: 0,
  last_unresolved_reply_text: null,
  last_unresolved_reply_at: null,
  resolved_action: null,
  resolved_due_at: null,
  resolved_due_at_text: null,
  expired_at: null,
  application_status: null,
  application_skip_reason: null,
  applied_at: null,
  created_time: '2026-08-12T04:13:48'
}

const listResponse: FollowUpConfirmationCaseListResponse = {
  items: [confirmationCase],
  total: 1,
  skip: 0,
  limit: 20,
  filters: { status: 'PENDING', owner_scope: 'mine' },
  usage_policy: { rule: 'owner scoped' }
}

const resolvedResponse: FollowUpConfirmationResolveResponse = {
  case: { ...confirmationCase, status: 'RESOLVED', resolved_action: 'COMPLETE' },
  decision: {
    action: 'COMPLETE',
    confidence: 1,
    reason: '用户确认已完成',
    resolved: true,
    proposed_due_at: null,
    proposed_due_at_text: null
  },
  application: {
    status: 'APPLIED',
    case_public_id: confirmationCase.public_id,
    task_public_id: confirmationCase.task?.public_id ?? null,
    action: 'COMPLETE',
    skip_reason: null,
    execution_results: []
  },
  assistant_follow_up_prompt: null,
  usage_policy: { rule: 'application service' }
}

describe('useFollowUpConfirmationStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    apiMocks.list.mockResolvedValue(listResponse)
    apiMocks.getPendingCount.mockResolvedValue(1)
    apiMocks.resolve.mockResolvedValue(resolvedResponse)
  })

  it('loads owner-scoped pending cases and keeps the badge count in sync', async () => {
    const store = useFollowUpConfirmationStore()

    await store.fetchPendingCases()

    expect(apiMocks.list).toHaveBeenCalledWith({ skip: 0, limit: 20 })
    expect(store.items).toEqual([confirmationCase])
    expect(store.total).toBe(1)
    expect(store.pendingCount).toBe(1)
    expect(store.loading).toBe(false)
    expect(store.loadError).toBeNull()
  })


  it('loads a requested page and exposes the total page count', async () => {
    apiMocks.list.mockResolvedValue({
      ...listResponse,
      total: 45,
      skip: 20,
      limit: 20
    })
    const store = useFollowUpConfirmationStore()

    await store.fetchPendingCases(2)

    expect(apiMocks.list).toHaveBeenCalledWith({ skip: 20, limit: 20 })
    expect(store.page).toBe(2)
    expect(store.totalPages).toBe(3)
  })

  it('loads the lightweight pending count independently', async () => {
    apiMocks.getPendingCount.mockResolvedValue(108)
    const store = useFollowUpConfirmationStore()

    await store.fetchPendingCount()

    expect(store.pendingCount).toBe(108)
    expect(store.hasPendingCases).toBe(true)
  })

  it('resolves through the API and refreshes both inbox and badge state', async () => {
    apiMocks.list.mockResolvedValue({ ...listResponse, items: [], total: 0 })
    apiMocks.getPendingCount.mockResolvedValue(0)
    const store = useFollowUpConfirmationStore()

    const result = await store.resolveCase(confirmationCase.public_id, '已完成')

    expect(apiMocks.resolve).toHaveBeenCalledWith(confirmationCase.public_id, { reply_text: '已完成' })
    expect(apiMocks.list).toHaveBeenCalledOnce()
    expect(apiMocks.getPendingCount).toHaveBeenCalledOnce()
    expect(result).toEqual(resolvedResponse)
    expect(store.items).toEqual([])
    expect(store.pendingCount).toBe(0)
    expect(store.resolvingCaseId).toBeNull()
  })

  it('keeps a successful resolution authoritative when inbox refresh fails', async () => {
    apiMocks.list.mockRejectedValue(new Error('list refresh unavailable'))
    apiMocks.getPendingCount.mockRejectedValue(new Error('count refresh unavailable'))
    const store = useFollowUpConfirmationStore()
    store.items = [confirmationCase]
    store.total = 1
    store.pendingCount = 1

    const result = await store.resolveCase(confirmationCase.public_id, '已完成')

    expect(result).toEqual(resolvedResponse)
    expect(store.items).toEqual([])
    expect(store.total).toBe(0)
    expect(store.pendingCount).toBe(0)
    expect(store.postResolveRefreshError).toBe('确认已处理，但列表状态刷新失败，请手动刷新。')
    expect(store.resolvingCaseId).toBeNull()
  })

  it('exposes a retryable load error and resets loading state', async () => {
    apiMocks.list.mockRejectedValue(new Error('network unavailable'))
    const store = useFollowUpConfirmationStore()

    await expect(store.fetchPendingCases()).rejects.toThrow('network unavailable')

    expect(store.loadError).toBe('network unavailable')
    expect(store.loading).toBe(false)
  })
})
