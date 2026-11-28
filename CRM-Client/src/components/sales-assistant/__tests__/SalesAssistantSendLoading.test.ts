import type { VueWrapper } from '@vue/test-utils'
import { flushPromises, mount } from '@vue/test-utils'
import type { VNode } from 'vue'
import { defineComponent, h, KeepAlive, nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type * as AssistantApiModule from '@/api/assistant'

const openConversation = vi.hoisted(() => vi.fn())
const getConversation = vi.hoisted(() => vi.fn())
const conversationText = vi.hoisted(() => vi.fn())
const stopTurn = vi.hoisted(() => vi.fn())
const pendingDrafts = vi.hoisted(() => vi.fn())
const submitInputStream = vi.hoisted(() => vi.fn())
const uploadAttachment = vi.hoisted(() => vi.fn())

vi.mock('@/api/assistant', async (importOriginal) => ({
  ...(await importOriginal<typeof AssistantApiModule>()),
  assistantApi: {
    openConversation,
    getConversation,
    conversationText,
    uploadAttachment,
    stopTurn,
    pendingDrafts,
    resumeConversation: vi.fn(),
  },
  submitInputStream,
}))

import SalesAssistantChat from '../SalesAssistantChat.vue'
import type { AssistantTaskView, ConversationReply, ConversationView } from '@/schemas/assistant-contracts'

const view = (olderCursor: number | null): ConversationView => ({
  public_id: 'asc_1',
  version: 3,
  focused_task: null,
  pending_choice: null,
  has_pending_request: false,
  older_cursor: olderCursor,
  messages: [
    {
      id: 'acm_1:user', role: 'user', text: '上周和睿狐科技通过电话', at: '2026-10-29T01:00:00',
      task: null, boundary: null, outcome: null, ui: null,
    },
  ],
})

const sendButton = (wrapper: VueWrapper): Element => wrapper.get('button[aria-label="发送"]').element

const attachImage = async (wrapper: VueWrapper, file: File): Promise<void> => {
  const input = wrapper.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', { value: [file] })
  await input.trigger('change')
}

let mounted: VueWrapper | undefined

describe('SalesAssistant send button loading', () => {
  beforeEach(() => {
    openConversation.mockReset()
    getConversation.mockReset()
    conversationText.mockReset()
    stopTurn.mockReset()
    pendingDrafts.mockReset()
    pendingDrafts.mockResolvedValue([])
    submitInputStream.mockReset()
    uploadAttachment.mockReset()
  })
  afterEach(() => {
    mounted?.unmount()
    mounted = undefined
  })

  it('shows loading only while the typed text is being sent', async () => {
    openConversation.mockResolvedValue(view(null))
    let resolveReply!: (reply: ConversationReply) => void
    conversationText.mockReturnValue(new Promise<ConversationReply>((resolve) => { resolveReply = resolve }))
    const wrapper = mount(SalesAssistantChat)
    mounted = wrapper
    await flushPromises()

    await wrapper.get('textarea').setValue('今天下午拜访了客户')
    await wrapper.get('button[aria-label="发送"]').trigger('click')
    await flushPromises()
    expect(sendButton(wrapper).getAttribute('aria-busy')).toBe('true')

    resolveReply({ conversation: view(null), submission: null })
    await flushPromises()
    expect(sendButton(wrapper).getAttribute('aria-busy')).toBeNull()
  })

  it('does not show send loading while older history loads', async () => {
    openConversation.mockResolvedValue(view(1))
    let resolvePage!: (page: ConversationView) => void
    getConversation.mockReturnValue(new Promise<ConversationView>((resolve) => { resolvePage = resolve }))
    const wrapper = mount(SalesAssistantChat)
    mounted = wrapper
    await flushPromises()

    const older = wrapper.findAll('button').find((button) => button.text() === '查看更早对话')
    await older?.trigger('click')
    await flushPromises()
    expect(getConversation).toHaveBeenCalledWith(1)
    expect(sendButton(wrapper).getAttribute('aria-busy')).toBeNull()

    resolvePage(view(null))
    await flushPromises()
  })

  it('scrolls back to the latest message when the kept-alive page is shown again, without refetching', async () => {
    openConversation.mockResolvedValue(view(null))
    const scrollTo = vi.fn()
    const original = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollTo')
    Object.defineProperty(HTMLElement.prototype, 'scrollTo', { configurable: true, value: scrollTo })
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { callback(0); return 0 })
    const shown = ref(true)
    const Host = defineComponent(() => (): VNode => h(KeepAlive, null, shown.value ? [h(SalesAssistantChat)] : []))
    try {
      mounted = mount(Host)
      await flushPromises()
      scrollTo.mockClear()

      shown.value = false
      await nextTick()
      shown.value = true
      await flushPromises()

      expect(scrollTo).toHaveBeenCalled()
      expect(openConversation).toHaveBeenCalledTimes(1)
    }
    finally {
      vi.unstubAllGlobals()
      if (original) Object.defineProperty(HTMLElement.prototype, 'scrollTo', original)
      else Reflect.deleteProperty(HTMLElement.prototype, 'scrollTo')
    }
  })

  it('preserves streamed partialText as a read-only bubble after stopping generation', async () => {
    const activeTask: AssistantTaskView = {
      public_id: 'ast_stop_1',
      status: 'ACTIVE',
      goal: '整理沟通纪要',
      task_kind: 'customer_activity',
      draft: {
        customer: { status: 'MISSING' },
        content: { status: 'MISSING' },
        next_action: { status: 'MISSING' },
        next_follow_time: { status: 'MISSING' },
      },
      committed: [],
      budget_steps: 1,
      budget_max_steps: 10,
      version: 2,
      processing_turn_id: 'atn_stop_1',
      processing_turn_status: 'RUNNING',
      reprocess_turn_id: null,
      waiting: null,
    }
    const stoppedTask: AssistantTaskView = {
      ...activeTask,
      processing_turn_id: null,
      processing_turn_status: null,
    }
    const activeView: ConversationView = { ...view(null), version: 4, focused_task: activeTask }
    const afterStopView: ConversationView = { ...view(null), version: 4, focused_task: stoppedTask }

    openConversation.mockResolvedValue(view(null))
    getConversation.mockResolvedValue(afterStopView)
    stopTurn.mockResolvedValue({ stopped: true, reason: 'STOPPED', task: stoppedTask })
    conversationText.mockResolvedValue({
      conversation: activeView,
      submission: {
        task_public_id: 'ast_stop_1',
        turn_id: 'atn_stop_1',
        input: { kind: 'text', text: '帮我整理客户沟通纪要' },
      },
    })
    submitInputStream.mockImplementation(
      (_taskId: string, _req: unknown, callbacks: AssistantApiModule.SubmitStreamHandlers, options?: { signal?: AbortSignal }) =>
        new Promise<void>((resolve) => {
          callbacks.onAccepted?.('atn_stop_1', 1)
          callbacks.onTextDelta?.({ turn_id: 'atn_stop_1', delta: '已识别客户需求：', seq: 2 })
          callbacks.onTextDelta?.({ turn_id: 'atn_stop_1', delta: '预算 50 万，下周复盘', seq: 3 })
          options?.signal?.addEventListener('abort', () => resolve(), { once: true })
        }),
    )

    const wrapper = mount(SalesAssistantChat)
    mounted = wrapper
    await flushPromises()

    await wrapper.get('textarea').setValue('帮我整理客户沟通纪要')
    await wrapper.get('button[aria-label="发送"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-assistant-streaming-message]').text()).toContain('已识别客户需求：预算 50 万，下周复盘')

    await wrapper.get('[data-assistant-stop-generation]').trigger('click')
    await flushPromises()

    expect(stopTurn).toHaveBeenCalledWith('ast_stop_1', 'atn_stop_1')
    expect(wrapper.find('[data-assistant-streaming-message]').exists()).toBe(false)
    expect(wrapper.get('[data-assistant-stopped-partial]').text()).toContain('已识别客户需求：预算 50 万，下周复盘')
    expect(wrapper.text()).toContain('已停止本次生成')
    expect(wrapper.text()).toContain('重新生成')
  })

  it('sends the server-stored image ref returned by upload', async () => {
    openConversation.mockResolvedValue(view(null))
    const stored = { file_url: 'assistant_attachments/1/2/abc.png', file_name: 'wechat.png', mime_type: 'image/png', size_bytes: 4 }
    uploadAttachment.mockResolvedValue(stored)
    conversationText.mockResolvedValue({ conversation: view(null), submission: null })
    const wrapper = mount(SalesAssistantChat)
    mounted = wrapper
    await flushPromises()

    const file = new File(['png!'], 'wechat.png', { type: 'image/png' })
    await attachImage(wrapper, file)
    await wrapper.get('textarea').setValue('客户发来的微信截图')
    await wrapper.get('button[aria-label="发送"]').trigger('click')
    await flushPromises()

    expect(uploadAttachment).toHaveBeenCalledWith(file)
    expect(conversationText).toHaveBeenCalledWith(expect.objectContaining({ text: '客户发来的微信截图', attachments: [stored] }))
    expect(wrapper.find('[data-assistant-attachment-chip]').exists()).toBe(false)
  })

  it('keeps the draft and image and does not send when the upload fails', async () => {
    openConversation.mockResolvedValue(view(null))
    uploadAttachment.mockRejectedValue(new Error('network down'))
    const wrapper = mount(SalesAssistantChat)
    mounted = wrapper
    await flushPromises()

    await attachImage(wrapper, new File(['png!'], 'wechat.png', { type: 'image/png' }))
    await wrapper.get('textarea').setValue('客户发来的微信截图')
    await wrapper.get('button[aria-label="发送"]').trigger('click')
    await flushPromises()

    expect(conversationText).not.toHaveBeenCalled()
    expect(wrapper.get('[data-assistant-attachment-error]').text()).toBe('图片上传失败，请重试。')
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('客户发来的微信截图')
    expect(wrapper.get('[data-assistant-attachment-chip]').text()).toContain('wechat.png')
    expect(sendButton(wrapper).getAttribute('aria-busy')).toBeNull()
  })
})
