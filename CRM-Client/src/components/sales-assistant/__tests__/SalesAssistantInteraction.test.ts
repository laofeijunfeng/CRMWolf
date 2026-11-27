import type { VueWrapper } from '@vue/test-utils'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type * as AssistantApiModule from '@/api/assistant'

const openConversation = vi.hoisted(() => vi.fn())
const getConversation = vi.hoisted(() => vi.fn())
const conversationText = vi.hoisted(() => vi.fn())
const conversationChoice = vi.hoisted(() => vi.fn())
const getTurn = vi.hoisted(() => vi.fn())

vi.mock('@/api/assistant', async (importOriginal) => ({
  ...(await importOriginal<typeof AssistantApiModule>()),
  assistantApi: {
    openConversation,
    getConversation,
    conversationText,
    conversationChoice,
    getTurn,
    resumeConversation: vi.fn(),
  },
  submitInputStream: vi.fn(),
}))

import SalesAssistantChat from '../SalesAssistantChat.vue'
import type { AssistantTaskView, ConversationView } from '@/schemas/assistant-contracts'

const emptyView = (overrides: Partial<ConversationView> = {}): ConversationView => ({
  public_id: 'asc_1',
  version: 1,
  focused_task: null,
  pending_choice: null,
  has_pending_request: false,
  older_cursor: null,
  messages: [],
  ...overrides,
})

const runningTask = (): AssistantTaskView => ({
  public_id: 'ast_1',
  status: 'ACTIVE',
  goal: '记录客户沟通',
  draft: {
    customer: { status: 'MISSING' },
    content: { status: 'MISSING' },
    next_action: { status: 'MISSING' },
    next_follow_time: { status: 'MISSING' },
  },
  committed: [],
  budget_steps: 1,
  budget_max_steps: 10,
  version: 1,
  processing_turn_id: 'turn-1',
  processing_turn_status: 'RUNNING',
  reprocess_turn_id: null,
})

let mounted: VueWrapper | undefined

describe('SalesAssistant CRM-181 interactions', () => {
  beforeEach(() => {
    openConversation.mockReset()
    getConversation.mockReset()
    conversationText.mockReset()
    conversationChoice.mockReset()
    getTurn.mockReset()
  })

  afterEach(() => {
    mounted?.unmount()
    mounted = undefined
  })

  it('disables send button for empty/whitespace input and guards IME Enter composition', async () => {
    openConversation.mockResolvedValue(emptyView())
    conversationText.mockResolvedValue({
      conversation: emptyView({ version: 2 }),
      submission: null,
    })

    const wrapper = mount(SalesAssistantChat)
    mounted = wrapper
    await flushPromises()

    const textarea = wrapper.get('textarea')
    const sendBtn = wrapper.get('button[aria-label="发送"]')

    // Empty and whitespace-only disable send button.
    expect(sendBtn.attributes('disabled')).toBeDefined()
    await textarea.setValue('   \n  ')
    expect(sendBtn.attributes('disabled')).toBeDefined()

    // Non-empty enables send button.
    await textarea.setValue('和睿狐科技开了线上会议')
    expect(sendBtn.attributes('disabled')).toBeUndefined()

    // IME composing Enter (isComposing: true) must NOT submit.
    await textarea.trigger('keydown.enter', { isComposing: true })
    await flushPromises()
    expect(conversationText).not.toHaveBeenCalled()

    // Legacy IME Enter (keyCode: 229) must NOT submit.
    const imeEvent = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })
    Object.defineProperty(imeEvent, 'keyCode', { value: 229 })
    textarea.element.dispatchEvent(imeEvent)
    await flushPromises()
    expect(conversationText).not.toHaveBeenCalled()

    // Normal Enter submits.
    await textarea.trigger('keydown.enter', { isComposing: false, keyCode: 13 })
    await flushPromises()
    expect(conversationText).toHaveBeenCalledTimes(1)
  })

  it('renders empty-state suggestions that fill and focus the composer without auto-sending', async () => {
    openConversation.mockResolvedValue(emptyView())
    const wrapper = mount(SalesAssistantChat, { attachTo: document.body })
    mounted = wrapper
    await flushPromises()

    const suggestionButtons = wrapper.findAll('[data-assistant-empty-suggestions] button')
    expect(suggestionButtons.length).toBeGreaterThanOrEqual(2)

    const firstSuggestion = suggestionButtons[0]
    expect(firstSuggestion).toBeDefined()
    if (!firstSuggestion) return

    const expectedText = firstSuggestion.text()
    await firstSuggestion.trigger('click')
    await nextTick()

    const textarea = wrapper.get('textarea').element as HTMLTextAreaElement
    expect(textarea.value).toBe(expectedText)
    expect(document.activeElement).toBe(textarea)
    expect(conversationText).not.toHaveBeenCalled()
  })

  it('auto-resizes the composer up to its cap and resets when cleared', async () => {
    openConversation.mockResolvedValue(emptyView())
    const wrapper = mount(SalesAssistantChat)
    mounted = wrapper
    await flushPromises()

    const textarea = wrapper.get('textarea')
    const el = textarea.element as HTMLTextAreaElement
    Object.defineProperty(el, 'scrollHeight', { configurable: true, get: () => 260 })

    await textarea.setValue('line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\nline9\nline10')
    await nextTick()

    expect(el.style.height).not.toBe('')
    expect(el.style.overflowY).toBe('auto')

    await textarea.setValue('')
    await nextTick()

    expect(el.style.height).toBe('')
    expect(el.style.overflowY).toBe('hidden')
  })

  it('keeps a single progress anchor when live process card is shown', async () => {
    const task = runningTask()
    openConversation.mockResolvedValue(emptyView({ focused_task: task }))
    getTurn.mockResolvedValue({
      turn_id: 'turn-1',
      status: 'RUNNING',
      lease_version: 1,
      reprocess_allowed: false,
      events: [
        { seq: 1, event: 'stage', data: { stage: 'classify', phase: 'done', ms: 40 } },
        { seq: 2, event: 'stage', data: { stage: 'organize', phase: 'start' } },
      ],
      task,
    })

    const wrapper = mount(SalesAssistantChat)
    mounted = wrapper
    await flushPromises()

    // Live process section is rendered and carries the reassurance banner.
    const processSection = wrapper.find('section[aria-label="执行过程"]')
    expect(processSection.exists()).toBe(true)
    expect(processSection.text()).toContain('原始内容已保存，处理仍在后台继续；关闭或刷新不会取消')

    // No duplicate spinning processingHint row above the composer textarea.
    const statusTexts = wrapper.findAll('[role="status"]').map((node) => node.text())
    expect(statusTexts.some((text) => text.includes('正在整理内容'))).toBe(false)
  })

  it('restores focus to composer when pending_choice card unlocks', async () => {
    const lockedView = emptyView({
      pending_choice: {
        entry_id: 'entry-1',
        prompt: '请选择要继续的任务',
      },
    })
    openConversation.mockResolvedValue(lockedView)
    conversationChoice.mockResolvedValue({
      conversation: emptyView({ version: 2, pending_choice: null }),
      submission: null,
    })

    const wrapper = mount(SalesAssistantChat, { attachTo: document.body })
    mounted = wrapper
    await flushPromises()

    const textarea = wrapper.get('textarea').element as HTMLTextAreaElement
    expect(textarea.disabled).toBe(true)

    const cancelButton = wrapper.findAll('button').find((btn) => btn.text().includes('算了'))
    expect(cancelButton).toBeDefined()
    if (!cancelButton) return

    await cancelButton.trigger('click')
    await flushPromises()
    await nextTick()

    expect(textarea.disabled).toBe(false)
    expect(document.activeElement).toBe(textarea)
  })
})
