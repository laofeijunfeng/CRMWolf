import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type * as AssistantApiModule from '@/api/assistant'

const openConversation = vi.hoisted(() => vi.fn())
const conversationText = vi.hoisted(() => vi.fn())
const pendingDrafts = vi.hoisted(() => vi.fn())

vi.mock('@/api/assistant', async (importOriginal) => ({
  ...(await importOriginal<typeof AssistantApiModule>()),
  assistantApi: { openConversation, conversationText, pendingDrafts, getConversation: vi.fn(), resumeConversation: vi.fn() },
  submitInputStream: vi.fn(),
}))

import SalesAssistantChat from '../SalesAssistantChat.vue'
import type { TeamResponse } from '@/api/team'
import type { UserResponse } from '@/schemas/auth'
import type { ConversationView } from '@/schemas/assistant-contracts'
import { useTeamStore } from '@/stores/team'
import { useUserStore } from '@/stores/user'

const DRAFT_KEY = 'crmwolf:assistant:draft:1:12:asc_1'
const DRAFT_TEXT = '今天和睿狐科技张总电话，确认下周二演示'
const team: TeamResponse = { id: 1, name: '演示', code: 'DEMO', owner_id: '12', created_at: '2026-01-01T00:00:00Z' }
const owner: UserResponse = {
  id: 12, name: '所有者', email: 'owner@example.com', mobile: null, avatar_url: null, employee_no: null,
  region: null, status: 'active', created_at: null, updated_at: null, roles: null,
}
const view = (publicId: string): ConversationView => ({
  public_id: publicId, version: 3, focused_task: null, pending_choice: null, has_pending_request: false,
  older_cursor: null, messages: [],
})

let wrapper: VueWrapper | undefined

/** Mounts a fresh chat as `user` in team 1 viewing conversation `conversationId`. */
const mountAs = async (user: UserResponse, conversationId: string): Promise<VueWrapper> => {
  wrapper?.unmount()
  const pinia = createPinia()
  setActivePinia(pinia)
  useTeamStore().currentTeam = team
  useUserStore().userInfo = user
  openConversation.mockResolvedValue(view(conversationId))
  const mounted = mount(SalesAssistantChat, { global: { plugins: [pinia] } })
  wrapper = mounted
  await flushPromises()
  return mounted
}
const composer = (mounted: VueWrapper): HTMLTextAreaElement => mounted.get('textarea').element as HTMLTextAreaElement

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  for (const mock of [openConversation, conversationText, pendingDrafts]) mock.mockReset()
  pendingDrafts.mockResolvedValue([])
  localStorage.clear()
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.useRealTimers()
  localStorage.clear()
})

describe('SalesAssistant local composer draft', () => {
  it('saves the typed text after a 300ms pause and restores it with a clearable banner after remount', async () => {
    const first = await mountAs(owner, 'asc_1')
    await first.get('textarea').setValue(DRAFT_TEXT)
    await vi.advanceTimersByTimeAsync(299)
    expect(localStorage.getItem(DRAFT_KEY)).toBeNull()
    await vi.advanceTimersByTimeAsync(1)
    expect(JSON.parse(localStorage.getItem(DRAFT_KEY) ?? 'null')).toMatchObject({ text: DRAFT_TEXT, mentionedCustomer: null })

    const second = await mountAs(owner, 'asc_1')
    expect(composer(second).value).toBe(DRAFT_TEXT)
    const banner = second.get('[data-assistant-draft-banner]')
    expect(banner.attributes('role')).toBe('status')
    expect(banner.text()).toContain('已恢复上次未发送的本地草稿')

    await second.get('[data-assistant-clear-draft]').trigger('click')
    await vi.advanceTimersByTimeAsync(300)
    expect(composer(second).value).toBe('')
    expect(second.find('[data-assistant-draft-banner]').exists()).toBe(false)
    expect(localStorage.getItem(DRAFT_KEY)).toBeNull()
  })

  it('keeps the draft private to the user and conversation it was typed in', async () => {
    const first = await mountAs(owner, 'asc_1')
    await first.get('textarea').setValue(DRAFT_TEXT)
    await vi.advanceTimersByTimeAsync(300)

    const otherUser = await mountAs({ ...owner, id: 13, email: 'sales@example.com' }, 'asc_1')
    expect(composer(otherUser).value).toBe('')
    expect(otherUser.find('[data-assistant-draft-banner]').exists()).toBe(false)

    const otherConversation = await mountAs(owner, 'asc_2')
    expect(composer(otherConversation).value).toBe('')
    expect(otherConversation.find('[data-assistant-draft-banner]').exists()).toBe(false)
    expect(localStorage.getItem(DRAFT_KEY)).not.toBeNull()
  })

  it('drops the stored draft once the text is sent', async () => {
    const mounted = await mountAs(owner, 'asc_1')
    await mounted.get('textarea').setValue(DRAFT_TEXT)
    await vi.advanceTimersByTimeAsync(300)
    expect(localStorage.getItem(DRAFT_KEY)).not.toBeNull()

    conversationText.mockResolvedValue({ conversation: { ...view('asc_1'), version: 4 }, submission: null })
    await mounted.get('button[aria-label="发送"]').trigger('click')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(300)

    expect(conversationText).toHaveBeenCalledWith(expect.objectContaining({ text: DRAFT_TEXT }))
    expect(localStorage.getItem(DRAFT_KEY)).toBeNull()
  })
})
