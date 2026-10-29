import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const openConversation = vi.hoisted(() => vi.fn())
const retryConversationEntry = vi.hoisted(() => vi.fn())
const getConversation = vi.hoisted(() => vi.fn())

vi.mock('@/api/assistant', () => ({
  assistantApi: {
    openConversation,
    retryConversationEntry,
    getConversation,
    resumeConversation: vi.fn(),
  },
  submitInputStream: vi.fn(),
}))

import SalesAssistantChat from '../SalesAssistantChat.vue'

const envelope = (retry: boolean) => ({
  schema_version: 'crm.agent.ui.v1',
  message_id: 1,
  turn_id: 'acm_1:reply',
  role: 'assistant',
  state: 'failed',
  blocks: [{
    id: 'b_error_1',
    type: 'error',
    code: retry ? 'UPSTREAM_TIMEOUT' : 'CONFIGURATION_ERROR',
    title: retry ? '模型服务响应超时' : '模型配置不可用',
    message: retry
      ? '模型服务响应超时，本次没有写入客户活动。'
      : '模型配置暂不可用，本次没有写入客户活动，请联系管理员。',
    retryable: retry,
    trace_id: 'acm_1',
  }],
  suggested_actions: retry ? [{ type: 'retry', action_id: 'retry:acm_1', label: '重试' }] : [],
  metadata: { display: 'MESSAGE', route: 'WORKFLOW', accessibility_label: '失败' },
})

const view = (retry: boolean) => ({
  public_id: 'asc_1',
  version: 7,
  focused_task: null,
  pending_choice: null,
  has_pending_request: false,
  older_cursor: null,
  messages: [
    {
      id: 'acm_1:user', role: 'user', text: '今天下午和睿狐科技开了个线上会议', at: '2026-10-29T01:00:00',
      task: null, boundary: null, outcome: null, ui: null,
    },
    {
      id: 'acm_1:reply', role: 'assistant', text: '模型服务响应超时，本次没有写入客户活动。',
      at: '2026-10-29T01:00:01', task: null, boundary: null, outcome: 'failure', ui: envelope(retry),
    },
  ],
})

describe('SalesAssistant root retry', () => {
  beforeEach(() => {
    openConversation.mockReset()
    retryConversationEntry.mockReset()
    getConversation.mockReset()
  })

  it('calls the entry retry API without another user bubble', async () => {
    openConversation.mockResolvedValue(view(true))
    retryConversationEntry.mockResolvedValue({ conversation: view(false), submission: null })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()

    const userBubbles = wrapper.findAll('.justify-end')
    expect(userBubbles).toHaveLength(1)
    const retry = wrapper.findAll('button').find((button) => button.text() === '重试')
    expect(retry).toBeDefined()
    await retry?.trigger('click')
    await flushPromises()

    expect(retryConversationEntry).toHaveBeenCalledTimes(1)
    expect(retryConversationEntry).toHaveBeenCalledWith('acm_1', 7)
    expect(wrapper.findAll('.justify-end')).toHaveLength(1)
  })

  it('does not offer retry for a configuration failure', async () => {
    openConversation.mockResolvedValue(view(false))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()

    expect(wrapper.text()).toContain('模型配置不可用')
    expect(wrapper.text()).toContain('不能盲目重试')
    expect(wrapper.findAll('button').some((button) => button.text() === '重试')).toBe(false)
    expect(retryConversationEntry).not.toHaveBeenCalled()
  })
})
