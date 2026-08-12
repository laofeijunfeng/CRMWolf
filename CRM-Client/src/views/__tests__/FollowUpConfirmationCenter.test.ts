import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

const apiMocks = vi.hoisted(() => ({
  list: vi.fn(),
  getPendingCount: vi.fn(),
  resolve: vi.fn()
}))
const toastMocks = vi.hoisted(() => ({
  success: vi.fn(),
  warning: vi.fn()
}))

vi.mock('@/api/followUpTask', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/followUpTask')>()
  return {
    ...original,
    followUpConfirmationApi: apiMocks
  }
})
vi.mock('vue-sonner', () => ({ toast: toastMocks }))
vi.mock('@/composables/usePageTitle', () => ({ usePageTitle: vi.fn(() => ({ setTitle: vi.fn(), resetTitle: vi.fn() })) }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

import type {
  FollowUpConfirmationCase,
  FollowUpConfirmationCaseListResponse,
  FollowUpConfirmationResolveResponse
} from '@/api/followUpTask'
import FollowUpConfirmationCenter from '@/views/FollowUpConfirmationCenter.vue'

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
    source_public_id: null
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

const listResponse = (overrides: Partial<FollowUpConfirmationCaseListResponse> = {}): FollowUpConfirmationCaseListResponse => ({
  items: [confirmationCase],
  total: 1,
  skip: 0,
  limit: 20,
  filters: { status: 'PENDING', owner_scope: 'mine' },
  usage_policy: { rule: 'owner scoped inbox' },
  ...overrides
})

const resolvedResponse = (resolved: boolean): FollowUpConfirmationResolveResponse => ({
  case: confirmationCase,
  decision: {
    action: resolved ? 'COMPLETE' : 'UNKNOWN',
    confidence: resolved ? 1 : 0.4,
    reason: resolved ? '用户确认完成' : '回复不明确',
    resolved,
    proposed_due_at: null,
    proposed_due_at_text: null
  },
  application: {
    status: resolved ? 'APPLIED' : 'SKIPPED',
    case_public_id: confirmationCase.public_id,
    task_public_id: confirmationCase.task?.public_id ?? null,
    action: resolved ? 'COMPLETE' : null,
    skip_reason: resolved ? null : 'CONFIRMATION_CASE_NOT_RESOLVED',
    execution_results: []
  },
  assistant_follow_up_prompt: resolved ? null : '请直接回复已完成、先放着、不管了，或说明延期时间。',
  usage_policy: { rule: 'application service' }
})

const mountCenter = (): VueWrapper => mount(FollowUpConfirmationCenter, {
  global: {
    stubs: {
      CircleAlert: true,
      ListChecks: true
    }
  }
})

describe('FollowUpConfirmationCenter', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    apiMocks.list.mockResolvedValue(listResponse())
    apiMocks.getPendingCount.mockResolvedValue(1)
    apiMocks.resolve.mockResolvedValue(resolvedResponse(true))
    vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined)
  })

  it('loads the durable owner inbox and exposes every resolution action', async () => {
    const wrapper = mountCenter()
    await flushPromises()

    expect(apiMocks.list).toHaveBeenCalledWith({ skip: 0, limit: 20 })
    expect(wrapper.get('[data-testid="confirmation-case-fuc_case_1"]').text()).toContain('中移互联网')
    expect(wrapper.text()).toContain('反馈新的数据分级分类收集表给张雷雨')
    expect(wrapper.text()).toContain('上次安排的分类分级表是否已经完成？')

    const buttons = wrapper.findAll('button')
    await buttons.find(button => button.text() === '已完成')?.trigger('click')
    await flushPromises()
    expect(apiMocks.resolve).toHaveBeenCalledWith('fuc_case_1', { reply_text: '已完成' })

    const delayInput = wrapper.get('#delay-fuc_case_1')
    await delayInput.setValue('下周五再说')
    await wrapper.findAll('button').find(button => button.text() === '确认延期')?.trigger('click')
    await flushPromises()
    expect(apiMocks.resolve).toHaveBeenCalledWith('fuc_case_1', { reply_text: '下周五再说' })
  })

  it('reports a successful confirmation even when the follow-up refresh fails', async () => {
    apiMocks.list
      .mockResolvedValueOnce(listResponse())
      .mockRejectedValueOnce(new Error('refresh unavailable'))
    apiMocks.getPendingCount.mockRejectedValueOnce(new Error('count unavailable'))
    const wrapper = mountCenter()
    await flushPromises()

    await wrapper.findAll('button').find(button => button.text() === '已完成')?.trigger('click')
    await flushPromises()

    expect(toastMocks.success).toHaveBeenCalledWith(
      '跟进确认已处理',
      { description: '确认已处理，但列表状态刷新失败，请手动刷新。' }
    )
  })

  it('keeps an unresolved case visible and tells the user how to clarify', async () => {
    apiMocks.resolve.mockResolvedValue(resolvedResponse(false))
    const wrapper = mountCenter()
    await flushPromises()

    await wrapper.findAll('button').find(button => button.text() === '先放着')?.trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="confirmation-case-fuc_case_1"]').exists()).toBe(true)
    expect(toastMocks.warning).toHaveBeenCalledWith(
      '还需要明确处理方式',
      { description: '请直接回复已完成、先放着、不管了，或说明延期时间。' }
    )
  })

  it('provides complete desktop pagination and core mobile navigation', async () => {
    apiMocks.list
      .mockResolvedValueOnce(listResponse({ total: 45 }))
      .mockResolvedValueOnce(listResponse({ total: 45, skip: 20 }))
      .mockResolvedValueOnce(listResponse({ total: 45, skip: 40 }))
    const wrapper = mountCenter()
    await flushPromises()

    const nav = wrapper.get('nav[aria-label="跟进确认分页"]')
    expect(nav.text()).toContain('首页')
    expect(nav.text()).toContain('上一页')
    expect(nav.text()).toContain('下一页')
    expect(nav.text()).toContain('末页')
    expect(nav.get('#confirmation-jump-page').element.closest('.hidden')).not.toBeNull()
    expect(nav.findAll('button').find(button => button.text() === '首页')?.classes()).toContain('hidden')
    expect(nav.findAll('button').find(button => button.text() === '上一页')?.classes()).not.toContain('hidden')

    await nav.findAll('button').find(button => button.text() === '下一页')?.trigger('click')
    await flushPromises()
    expect(apiMocks.list).toHaveBeenLastCalledWith({ skip: 20, limit: 20 })

    await wrapper.get('#confirmation-jump-page').setValue('99')
    await wrapper.findAll('button').find(button => button.text() === '跳转')?.trigger('click')
    await flushPromises()
    expect(apiMocks.list).toHaveBeenLastCalledWith({ skip: 40, limit: 20 })
    await nextTick()
    expect((wrapper.get('#confirmation-jump-page').element as HTMLInputElement).value).toBe('3')
  })
})
