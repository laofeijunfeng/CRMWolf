import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type * as AssistantApiModule from '@/api/assistant'

const openConversation = vi.hoisted(() => vi.fn())
const getConversation = vi.hoisted(() => vi.fn())
const conversationText = vi.hoisted(() => vi.fn())
const stopTurn = vi.hoisted(() => vi.fn())
const pendingDrafts = vi.hoisted(() => vi.fn())
const submitInputStream = vi.hoisted(() => vi.fn())

vi.mock('@/api/assistant', async (importOriginal) => ({
  ...(await importOriginal<typeof AssistantApiModule>()),
  assistantApi: { openConversation, getConversation, conversationText, stopTurn, pendingDrafts, resumeConversation: vi.fn() },
  submitInputStream,
}))

import SalesAssistantChat from '../SalesAssistantChat.vue'
import type { AssistantTaskView, ConversationView } from '@/schemas/assistant-contracts'

const ORIGINAL_TEXT = '帮我整理客户沟通纪要'
const baseView: ConversationView = {
  public_id: 'asc_1', version: 3, focused_task: null, pending_choice: null, has_pending_request: false, older_cursor: null,
  messages: [{
    id: 'acm_1:user', role: 'user', text: '上周和睿狐科技通过电话', at: '2026-10-29T01:00:00',
    task: null, boundary: null, outcome: null, ui: null,
  }],
}
const activeTask: AssistantTaskView = {
  public_id: 'ast_stop_1', status: 'ACTIVE', goal: '整理沟通纪要', task_kind: 'customer_activity',
  draft: {
    customer: { status: 'MISSING' }, content: { status: 'MISSING' },
    next_action: { status: 'MISSING' }, next_follow_time: { status: 'MISSING' },
  },
  committed: [], budget_steps: 1, budget_max_steps: 10, version: 2,
  processing_turn_id: 'atn_stop_1', processing_turn_status: 'RUNNING', reprocess_turn_id: null, waiting: null,
}
const stoppedTask: AssistantTaskView = { ...activeTask, processing_turn_id: null, processing_turn_status: null }

let wrapper: VueWrapper | undefined
let streamSignal: AbortSignal | undefined

/** Mounts the chat, sends ORIGINAL_TEXT and leaves the turn streaming until its signal aborts. */
const mountStreaming = async (): Promise<VueWrapper> => {
  openConversation.mockResolvedValue(baseView)
  conversationText.mockResolvedValueOnce({
    conversation: { ...baseView, version: 4, focused_task: activeTask },
    submission: { task_public_id: 'ast_stop_1', turn_id: 'atn_stop_1', input: { kind: 'text', text: ORIGINAL_TEXT } },
  })
  submitInputStream.mockImplementation(
    (_taskId: string, _req: unknown, callbacks: AssistantApiModule.SubmitStreamHandlers, options?: { signal?: AbortSignal }) =>
      new Promise<void>((resolve) => {
        streamSignal = options?.signal
        callbacks.onAccepted?.('atn_stop_1', 1)
        callbacks.onTextDelta?.({ turn_id: 'atn_stop_1', delta: '已识别客户需求', seq: 2 })
        options?.signal?.addEventListener('abort', () => resolve(), { once: true })
      }),
  )
  const mounted = mount(SalesAssistantChat)
  wrapper = mounted
  await flushPromises()
  await mounted.get('textarea').setValue(ORIGINAL_TEXT)
  await mounted.get('button[aria-label="发送"]').trigger('click')
  await flushPromises()
  expect(mounted.get('[data-assistant-streaming-message]').text()).toContain('已识别客户需求')
  expect(streamSignal?.aborted).toBe(false)
  return mounted
}

beforeEach(() => {
  for (const mock of [openConversation, getConversation, conversationText, stopTurn, pendingDrafts, submitInputStream]) mock.mockReset()
  pendingDrafts.mockResolvedValue([])
  streamSignal = undefined
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
})

describe('SalesAssistant stop generation', () => {
  it('aborts the stream on click, stops the turn, and offers to regenerate from the original input', async () => {
    getConversation.mockResolvedValue({ ...baseView, version: 4, focused_task: stoppedTask })
    stopTurn.mockResolvedValue({ stopped: true, reason: 'STOPPED', task: stoppedTask })
    const mounted = await mountStreaming()

    await mounted.get('[data-assistant-stop-generation]').trigger('click')
    expect(streamSignal?.aborted).toBe(true)
    await flushPromises()

    expect(stopTurn).toHaveBeenCalledWith('ast_stop_1', 'atn_stop_1')
    const banner = mounted.get('[data-assistant-stopped-banner]')
    expect(banner.attributes('role')).toBe('status')
    expect(banner.text()).toContain('已停止本次生成')
    expect(mounted.find('[data-assistant-stop-write-lock]').exists()).toBe(false)

    conversationText.mockReturnValue(new Promise(() => undefined))
    await mounted.get('[data-assistant-regenerate]').trigger('click')
    await flushPromises()

    expect(conversationText).toHaveBeenCalledTimes(2)
    expect(conversationText.mock.calls[1]?.[0]).toMatchObject({ text: ORIGINAL_TEXT })
    expect(mounted.find('[data-assistant-stopped-banner]').exists()).toBe(false)
  })

  it('shows the write lock instead of a stopped state when the turn is already writing to CRM', async () => {
    getConversation.mockResolvedValue({ ...baseView, version: 4, focused_task: activeTask })
    stopTurn.mockResolvedValue({ stopped: false, reason: 'WRITE_IN_PROGRESS', task: activeTask })
    const mounted = await mountStreaming()

    await mounted.get('[data-assistant-stop-generation]').trigger('click')
    await flushPromises()

    const lock = mounted.get('[data-assistant-stop-write-lock]')
    expect(lock.attributes('role')).toBe('status')
    expect(lock.text()).toContain('正在写入 CRM，无法中途停止')
    expect(mounted.find('[data-assistant-stopped-banner]').exists()).toBe(false)
    expect(mounted.text()).not.toContain('已停止本次生成')
  })
})
