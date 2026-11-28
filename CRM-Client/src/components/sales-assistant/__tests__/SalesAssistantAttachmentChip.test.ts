import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import type * as AssistantApiModule from '@/api/assistant'

const openConversation = vi.hoisted(() => vi.fn())
const conversationText = vi.hoisted(() => vi.fn())
const uploadAttachment = vi.hoisted(() => vi.fn())
const fetchAttachmentBlobUrl = vi.hoisted(() => vi.fn())

vi.mock('@/api/assistant', async (importOriginal) => ({
  ...(await importOriginal<typeof AssistantApiModule>()),
  assistantApi: {
    openConversation, pendingDrafts: vi.fn().mockResolvedValue([]), getConversation: vi.fn(),
    conversationText, uploadAttachment, fetchAttachmentBlobUrl, resumeConversation: vi.fn(),
  },
  submitInputStream: vi.fn(),
}))

import SalesAssistantChat from '../SalesAssistantChat.vue'

const LONG_NAME = '微信截图_睿狐科技张总关于二期项目报价与交付排期的完整沟通记录_2026-11-28_15-30-00.png'
let wrapper: VueWrapper | undefined
const originalCreateObjectURL = window.URL.createObjectURL
const originalRevokeObjectURL = window.URL.revokeObjectURL
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  Object.defineProperty(window.URL, 'createObjectURL', { configurable: true, writable: true, value: originalCreateObjectURL })
  Object.defineProperty(window.URL, 'revokeObjectURL', { configurable: true, writable: true, value: originalRevokeObjectURL })
  vi.clearAllMocks()
})
it('keeps a long attachment name on one truncated line with the full name in its tooltip', async () => {
  openConversation.mockResolvedValue({
    public_id: 'asc_1', version: 3, focused_task: null, pending_choice: null, has_pending_request: false,
    older_cursor: null, messages: [],
  })
  const mounted = mount(SalesAssistantChat)
  wrapper = mounted
  await flushPromises()

  const input = mounted.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', {
    value: [new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], LONG_NAME, { type: 'image/png' })],
  })
  await input.trigger('change')

  const chip = mounted.get('[data-assistant-attachment-chip]')
  const name = chip.get(`[title="${LONG_NAME}"]`)
  expect(name.text()).toBe(LONG_NAME)
  expect(name.classes()).toContain('truncate')
  expect(chip.get('button').attributes('aria-label')).toBe(`移除附件 ${LONG_NAME}`)
})

it('allows image-only submission and renders the image preview inside the user bubble', async () => {
  const stored = {
    file_url: 'assistant_attachments/1/2/card.png',
    file_name: 'card.png',
    mime_type: 'image/png' as const,
    size_bytes: 4,
  }
  const createUrl = vi.fn().mockReturnValue('blob:local-card')
  const revokeUrl = vi.fn()
  Object.defineProperty(window.URL, 'createObjectURL', { configurable: true, writable: true, value: createUrl })
  Object.defineProperty(window.URL, 'revokeObjectURL', { configurable: true, writable: true, value: revokeUrl })
  openConversation.mockResolvedValue({
    public_id: 'asc_1', version: 3, focused_task: null, pending_choice: null, has_pending_request: false,
    older_cursor: null, messages: [],
  })
  uploadAttachment.mockResolvedValue(stored)
  conversationText.mockResolvedValue({
    conversation: {
      public_id: 'asc_1', version: 4, focused_task: null, pending_choice: null, has_pending_request: false,
      older_cursor: null,
      messages: [
        {
          id: 'acm_1:user', role: 'user', text: '', at: '2026-11-28T10:00:00',
          task: null, boundary: null, outcome: null, ui: null, links: [], attachments: [stored],
        },
      ],
    },
    submission: null,
  })

  const mounted = mount(SalesAssistantChat)
  wrapper = mounted
  await flushPromises()

  const input = mounted.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', {
    value: [new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], 'card.png', { type: 'image/png' })],
  })
  await input.trigger('change')

  const sendButton = mounted.get('button[aria-label="发送"]')
  expect(sendButton.attributes('disabled')).toBeUndefined()
  await sendButton.trigger('click')
  await flushPromises()

  expect(uploadAttachment).toHaveBeenCalledTimes(1)
  expect(conversationText).toHaveBeenCalledWith(expect.objectContaining({
    text: '',
    attachments: [stored],
  }))
  expect(createUrl).toHaveBeenCalledTimes(1)
  const img = mounted.get('[data-assistant-user-attachment-img]')
  expect(img.attributes('src')).toBe('blob:local-card')
  expect(img.attributes('alt')).toBe('card.png')

  mounted.unmount()
  wrapper = undefined
  expect(revokeUrl).toHaveBeenCalledWith('blob:local-card')
})

it('loads authenticated blob previews for persisted user attachments and revokes them on unmount', async () => {
  const stored = {
    file_url: 'assistant_attachments/1/2/history.png',
    file_name: 'history.png',
    mime_type: 'image/png' as const,
    size_bytes: 128,
  }
  const revokeUrl = vi.fn()
  Object.defineProperty(window.URL, 'revokeObjectURL', { configurable: true, writable: true, value: revokeUrl })
  fetchAttachmentBlobUrl.mockResolvedValue('blob:history-preview')
  openConversation.mockResolvedValue({
    public_id: 'asc_1', version: 5, focused_task: null, pending_choice: null, has_pending_request: false,
    older_cursor: null,
    messages: [
      {
        id: 'acm_9:user', role: 'user', text: '这是刚才的截图', at: '2026-11-28T10:05:00',
        task: null, boundary: null, outcome: null, ui: null, links: [], attachments: [stored],
      },
    ],
  })

  const mounted = mount(SalesAssistantChat)
  wrapper = mounted
  await flushPromises()

  expect(fetchAttachmentBlobUrl).toHaveBeenCalledWith(stored.file_url)
  const img = mounted.get('[data-assistant-user-attachment-img]')
  expect(img.attributes('src')).toBe('blob:history-preview')
  expect(mounted.text()).toContain('这是刚才的截图')

  mounted.unmount()
  wrapper = undefined
  expect(revokeUrl).toHaveBeenCalledWith('blob:history-preview')
})

it('renders filename fallback chip when authenticated attachment preview fetch fails', async () => {
  const stored = {
    file_url: 'assistant_attachments/1/2/broken.png',
    file_name: 'broken.png',
    mime_type: 'image/png' as const,
    size_bytes: 64,
  }
  fetchAttachmentBlobUrl.mockRejectedValue(new Error('403 Forbidden'))
  openConversation.mockResolvedValue({
    public_id: 'asc_1', version: 6, focused_task: null, pending_choice: null, has_pending_request: false,
    older_cursor: null,
    messages: [
      {
        id: 'acm_10:user', role: 'user', text: '', at: '2026-11-28T10:10:00',
        task: null, boundary: null, outcome: null, ui: null, links: [], attachments: [stored],
      },
    ],
  })

  const mounted = mount(SalesAssistantChat)
  wrapper = mounted
  await flushPromises()

  expect(fetchAttachmentBlobUrl).toHaveBeenCalledWith(stored.file_url)
  expect(mounted.find('[data-assistant-user-attachment-img]').exists()).toBe(false)
  const fallback = mounted.get('[data-assistant-user-attachment-fallback]')
  expect(fallback.text()).toContain('broken.png')
})
