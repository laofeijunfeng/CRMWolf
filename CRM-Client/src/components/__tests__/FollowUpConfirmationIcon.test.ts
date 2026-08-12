import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const apiMocks = vi.hoisted(() => ({
  list: vi.fn(),
  getPendingCount: vi.fn(),
  resolve: vi.fn()
}))

vi.mock('@/api/followUpTask', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/followUpTask')>()
  return {
    ...original,
    followUpConfirmationApi: apiMocks
  }
})
vi.mock('vue-router', () => ({
  RouterLink: {
    props: ['to'],
    template: '<a :href="to"><slot /></a>'
  }
}))
vi.mock('@/utils/logger', () => ({ logger: { warn: vi.fn() } }))

import FollowUpConfirmationIcon from '@/components/FollowUpConfirmationIcon.vue'

describe('FollowUpConfirmationIcon', () => {
  const originalWindowAddEventListener = window.addEventListener
  const originalWindowRemoveEventListener = window.removeEventListener
  const originalWindowDispatchEvent = window.dispatchEvent

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.useRealTimers()
    apiMocks.getPendingCount.mockResolvedValue(0)
    if (typeof window.addEventListener !== 'function') {
      const listeners = new Map<string, EventListenerOrEventListenerObject[]>()
      window.addEventListener = vi.fn((type: string, listener: EventListenerOrEventListenerObject) => {
        listeners.set(type, [...(listeners.get(type) ?? []), listener])
      }) as typeof window.addEventListener
      window.removeEventListener = vi.fn((type: string, listener: EventListenerOrEventListenerObject) => {
        listeners.set(type, (listeners.get(type) ?? []).filter((item) => item !== listener))
      }) as typeof window.removeEventListener
      window.dispatchEvent = vi.fn((event: Event) => {
        for (const listener of listeners.get(event.type) ?? []) {
          if (typeof listener === 'function') {
            listener.call(window, event)
          } else {
            listener.handleEvent(event)
          }
        }
        return true
      }) as typeof window.dispatchEvent
    }
  })

  afterEach(() => {
    window.addEventListener = originalWindowAddEventListener
    window.removeEventListener = originalWindowRemoveEventListener
    window.dispatchEvent = originalWindowDispatchEvent
  })

  it('announces an empty confirmation center accessibly', async () => {
    const wrapper = mount(FollowUpConfirmationIcon)
    await flushPromises()

    expect(wrapper.get('[data-testid="follow-up-confirmation-link"]').attributes('aria-label'))
      .toBe('跟进确认中心，无待确认事项')
    expect(wrapper.find('[data-testid="follow-up-confirmation-badge"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('shows the pending count, caps the badge, and links to the center', async () => {
    apiMocks.getPendingCount.mockResolvedValue(108)
    const wrapper = mount(FollowUpConfirmationIcon)
    await flushPromises()

    expect(wrapper.get('[data-testid="follow-up-confirmation-link"]').attributes('aria-label'))
      .toBe('跟进确认中心，待确认 108 条')
    expect(wrapper.get('[data-testid="follow-up-confirmation-badge"]').text()).toBe('99+')

    expect(wrapper.get('[data-testid="follow-up-confirmation-link"]').attributes('href'))
      .toBe('/follow-up-confirmations')
    wrapper.unmount()
  })
  it('refreshes periodically and when the app becomes active, then cleans up listeners', async () => {
    vi.useFakeTimers()
    const addWindowListener = vi.spyOn(window, 'addEventListener')
    const removeWindowListener = vi.spyOn(window, 'removeEventListener')
    const addDocumentListener = vi.spyOn(document, 'addEventListener')
    const removeDocumentListener = vi.spyOn(document, 'removeEventListener')
    const wrapper = mount(FollowUpConfirmationIcon)
    await flushPromises()

    expect(apiMocks.getPendingCount).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(45_000)
    await flushPromises()
    expect(apiMocks.getPendingCount).toHaveBeenCalledTimes(2)

    window.dispatchEvent(new Event('focus'))
    await flushPromises()
    expect(apiMocks.getPendingCount).toHaveBeenCalledTimes(3)

    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
    document.dispatchEvent(new Event('visibilitychange'))
    await flushPromises()
    expect(apiMocks.getPendingCount).toHaveBeenCalledTimes(4)

    wrapper.unmount()
    expect(addWindowListener).toHaveBeenCalledWith('focus', expect.any(Function))
    expect(removeWindowListener).toHaveBeenCalledWith('focus', expect.any(Function))
    expect(addDocumentListener).toHaveBeenCalledWith('visibilitychange', expect.any(Function))
    expect(removeDocumentListener).toHaveBeenCalledWith('visibilitychange', expect.any(Function))
  })
})
