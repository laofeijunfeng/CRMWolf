import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type * as AssistantApiModule from '@/api/assistant'
import type * as CustomerApiModule from '@/api/customer'

const openConversation = vi.hoisted(() => vi.fn())
const conversationText = vi.hoisted(() => vi.fn())
const pendingDrafts = vi.hoisted(() => vi.fn())
const getCustomers = vi.hoisted(() => vi.fn())

vi.mock('@/api/assistant', async (importOriginal) => ({
  ...(await importOriginal<typeof AssistantApiModule>()),
  assistantApi: { openConversation, conversationText, pendingDrafts, getConversation: vi.fn(), resumeConversation: vi.fn() },
  submitInputStream: vi.fn(),
}))
vi.mock('@/api/customer', async (importOriginal) => ({
  ...(await importOriginal<typeof CustomerApiModule>()),
  default: { getCustomers },
}))

import SalesAssistantChat from '../SalesAssistantChat.vue'
import type { CustomerResponse } from '@/api/customer'
import type { ConversationView } from '@/schemas/assistant-contracts'

const view: ConversationView = {
  public_id: 'asc_1', version: 3, focused_task: null, pending_choice: null, has_pending_request: false,
  older_cursor: null, messages: [],
}
const customer = (id: string, name: string): CustomerResponse => ({
  id, public_id: `cus_${id}`, account_name: name, industry: null, city: '', address: null, company_scale: null,
  source: null, status: 1, owner_id: null, source_lead_id: null, default_procurement_method_id: null,
  loss_reason: null, return_reason: null, returned_time: null, creator_id: '12',
  created_time: '2026-01-01T00:00:00', last_modified_time: '2026-01-01T00:00:00', version: 1,
  license_expiry_date: null, license_is_permanent: false, license_authorized_users: null, license_type: null,
})

let wrapper: VueWrapper | undefined

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  for (const mock of [openConversation, conversationText, pendingDrafts, getCustomers]) mock.mockReset()
  pendingDrafts.mockResolvedValue([])
  openConversation.mockResolvedValue(view)
  getCustomers.mockResolvedValue([customer('1', '睿狐科技'), customer('2', '睿狐数据')])
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.useRealTimers()
})

describe('SalesAssistant @customer mention', () => {
  it('searches customers after @, picks one with the keyboard, and sends it as the mentioned customer', async () => {
    const mounted = mount(SalesAssistantChat)
    wrapper = mounted
    await flushPromises()
    const textarea = mounted.get('textarea')

    await textarea.setValue('联系 @睿狐')
    expect(mounted.get('[data-assistant-mention-popover]').attributes('role')).toBe('listbox')
    await vi.advanceTimersByTimeAsync(200)
    await flushPromises()
    expect(getCustomers).toHaveBeenCalledWith({ search: '睿狐', limit: 8 })
    const options = mounted.findAll('[data-assistant-mention-popover] [role="option"]')
    expect(options.map(option => option.text())).toEqual(['睿狐科技', '睿狐数据'])
    expect(options.map(option => option.attributes('aria-selected'))).toEqual(['true', 'false'])

    await textarea.trigger('keydown', { key: 'ArrowDown' })
    expect(mounted.findAll('[role="option"]').map(option => option.attributes('aria-selected'))).toEqual(['false', 'true'])
    await textarea.trigger('keydown', { key: 'Enter' })

    expect(mounted.find('[data-assistant-mention-popover]').exists()).toBe(false)
    expect(conversationText).not.toHaveBeenCalled()
    expect((textarea.element as HTMLTextAreaElement).value).toBe('联系 ')
    const chip = mounted.get('[data-assistant-mention-chip]')
    expect(chip.text()).toContain('@ 睿狐数据')
    expect(chip.get('[title="睿狐数据"]').classes()).toContain('truncate')

    conversationText.mockResolvedValue({ conversation: { ...view, version: 4 }, submission: null })
    await textarea.setValue('联系张总确认演示时间')
    await mounted.get('button[aria-label="发送"]').trigger('click')
    await flushPromises()

    expect(conversationText).toHaveBeenCalledWith(expect.objectContaining({
      text: '联系张总确认演示时间', mentioned_customer_public_id: 'cus_2',
    }))
  })

  it('closes the popover on Escape without picking, and a picked customer can be removed before sending', async () => {
    const mounted = mount(SalesAssistantChat)
    wrapper = mounted
    await flushPromises()
    const textarea = mounted.get('textarea')

    await textarea.setValue('@')
    await vi.advanceTimersByTimeAsync(200)
    await flushPromises()
    expect(getCustomers).toHaveBeenCalledWith({ limit: 8 })
    await textarea.trigger('keydown', { key: 'Escape' })
    expect(mounted.find('[data-assistant-mention-popover]').exists()).toBe(false)
    expect(mounted.find('[data-assistant-mention-chip]').exists()).toBe(false)

    await mounted.get('[data-assistant-mention-trigger]').trigger('click')
    await flushPromises()
    await mounted.findAll('[role="option"]')[0]?.trigger('mousedown')
    expect(mounted.get('[data-assistant-mention-chip]').text()).toContain('@ 睿狐科技')
    await mounted.get('button[aria-label="移除关联客户"]').trigger('click')
    expect(mounted.find('[data-assistant-mention-chip]').exists()).toBe(false)

    conversationText.mockResolvedValue({ conversation: { ...view, version: 4 }, submission: null })
    await textarea.setValue('联系张总')
    await mounted.get('button[aria-label="发送"]').trigger('click')
    await flushPromises()
    expect(conversationText.mock.calls[0]?.[0]).not.toHaveProperty('mentioned_customer_public_id')
  })
})
