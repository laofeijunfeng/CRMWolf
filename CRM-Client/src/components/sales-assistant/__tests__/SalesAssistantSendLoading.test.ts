import type { VueWrapper } from '@vue/test-utils'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type * as AssistantApiModule from '@/api/assistant'

const openConversation = vi.hoisted(() => vi.fn())
const getConversation = vi.hoisted(() => vi.fn())
const conversationText = vi.hoisted(() => vi.fn())

vi.mock('@/api/assistant', async (importOriginal) => ({
  ...(await importOriginal<typeof AssistantApiModule>()),
  assistantApi: {
    openConversation,
    getConversation,
    conversationText,
    resumeConversation: vi.fn(),
  },
  submitInputStream: vi.fn(),
}))

import SalesAssistantChat from '../SalesAssistantChat.vue'
import type { ConversationReply, ConversationView } from '@/schemas/assistant-contracts'

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

let mounted: VueWrapper | undefined

describe('SalesAssistant send button loading', () => {
  beforeEach(() => {
    openConversation.mockReset()
    getConversation.mockReset()
    conversationText.mockReset()
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
})
