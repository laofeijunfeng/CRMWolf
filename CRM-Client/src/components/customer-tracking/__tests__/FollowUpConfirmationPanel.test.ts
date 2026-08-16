import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const apiMocks = vi.hoisted(() => ({
  list: vi.fn(),
  getPendingCount: vi.fn(),
  resolve: vi.fn(),
}))
const toastMocks = vi.hoisted(() => ({
  success: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
}))

vi.mock('@/api/followUpTask', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/followUpTask')>()
  return {
    ...original,
    followUpConfirmationApi: apiMocks,
  }
})
vi.mock('vue-sonner', () => ({ toast: toastMocks }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

import type {
  FollowUpConfirmationCase,
  FollowUpConfirmationCaseListResponse,
  FollowUpConfirmationResolveResponse,
} from '@/api/followUpTask'
import FollowUpConfirmationPanel from '@/components/customer-tracking/FollowUpConfirmationPanel.vue'

const confirmationCase: FollowUpConfirmationCase = {
  id: 'fuc_case_1',
  public_id: 'fuc_case_1',
  status: 'PENDING',
  question_text: '上次安排的分类分级表是否已经完成？',
  suggested_action: 'COMPLETE',
  owner_id: '2',
  creator_id: '2',
  customer: { id: 'cus_1', public_id: 'cus_1', account_name: '中移互联网', name: '中移互联网' },
  task: {
    id: 'fut_1',
    public_id: 'fut_1',
    title: '反馈新的数据分级分类收集表给张雷雨',
    description: null,
    status: 'OPEN',
    due_at: null,
    due_at_text: '本周四',
    source_type: null,
    source_public_id: null,
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
  created_time: '2026-08-12T04:13:48',
}

const listResponse = (items: FollowUpConfirmationCase[] = [confirmationCase]): FollowUpConfirmationCaseListResponse => ({
  items,
  total: items.length,
  skip: 0,
  limit: 20,
  filters: { status: 'PENDING', owner_scope: 'mine' },
  usage_policy: { rule: 'owner scoped inbox' },
})

const resolveResponse = (resolved: boolean): FollowUpConfirmationResolveResponse => ({
  case: confirmationCase,
  decision: {
    action: resolved ? 'COMPLETE' : 'UNKNOWN',
    confidence: resolved ? 1 : 0.4,
    reason: resolved ? '用户确认完成' : '回复不明确',
    resolved,
    proposed_due_at: null,
    proposed_due_at_text: null,
  },
  application: {
    status: resolved ? 'APPLIED' : 'SKIPPED',
    case_public_id: confirmationCase.public_id,
    task_public_id: confirmationCase.task?.public_id ?? null,
    action: resolved ? 'COMPLETE' : null,
    skip_reason: resolved ? null : 'CONFIRMATION_CASE_NOT_RESOLVED',
    execution_results: [],
  },
  assistant_follow_up_prompt: resolved ? null : '请直接回复已完成、保持待处理、关闭追踪，或选择延期时间。',
  usage_policy: { rule: 'application service' },
})

function mountPanel(): VueWrapper {
  return mount(FollowUpConfirmationPanel, {
    global: {
      stubs: {
        CalendarClock: true,
        CheckCircle2: true,
        CircleAlert: true,
        PauseCircle: true,
        XCircle: true,
      },
    },
  })
}

function findButton(wrapper: VueWrapper, label: string): DOMWrapper<HTMLButtonElement> {
  const button = wrapper.findAll('button').find(item => item.text() === label)
  if (!button) throw new Error(`Button not found: ${label}`)
  return button
}

describe('FollowUpConfirmationPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    apiMocks.list.mockResolvedValue(listResponse())
    apiMocks.getPendingCount.mockResolvedValue(0)
    apiMocks.resolve.mockResolvedValue(resolveResponse(true))
  })

  it('shows pending confirmations inside customer tracking and resolves them in place', async () => {
    apiMocks.list
      .mockResolvedValueOnce(listResponse())
      .mockResolvedValueOnce(listResponse([]))
    const wrapper = mountPanel()
    await flushPromises()

    expect(apiMocks.list).toHaveBeenCalledWith({ skip: 0, limit: 20 })
    expect(wrapper.text()).toContain('中移互联网')
    expect(wrapper.text()).toContain('反馈新的数据分级分类收集表给张雷雨')
    expect(wrapper.text()).toContain('上次安排的分类分级表是否已经完成？')
    expect(wrapper.text()).toContain('建议完成')

    await findButton(wrapper, '确认完成').trigger('click')
    await flushPromises()

    expect(apiMocks.resolve).toHaveBeenCalledWith('fuc_case_1', { reply_text: '已完成' })
    expect(wrapper.text()).not.toContain('反馈新的数据分级分类收集表给张雷雨')
    expect(toastMocks.success).toHaveBeenCalledWith('追踪状态已更新', undefined)
  })

  it('keeps an unresolved confirmation visible and explains how to proceed', async () => {
    apiMocks.resolve.mockResolvedValue(resolveResponse(false))
    const wrapper = mountPanel()
    await flushPromises()

    await findButton(wrapper, '保持待处理').trigger('click')
    await flushPromises()

    expect(apiMocks.resolve).toHaveBeenCalledWith('fuc_case_1', { reply_text: '先放着' })
    expect(wrapper.text()).toContain('反馈新的数据分级分类收集表给张雷雨')
    expect(toastMocks.warning).toHaveBeenCalledWith('还需要明确处理方式', {
      description: '请直接回复已完成、保持待处理、关闭追踪，或选择延期时间。',
    })
  })

  it('keeps the existing complete, delay, retain and close choices available', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    expect(findButton(wrapper, '确认完成').exists()).toBe(true)
    expect(findButton(wrapper, '延期').exists()).toBe(true)
    expect(findButton(wrapper, '保持待处理').exists()).toBe(true)
    expect(findButton(wrapper, '关闭追踪').exists()).toBe(true)
  })
})
