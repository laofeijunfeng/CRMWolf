import type { VueWrapper } from '@vue/test-utils'
import { mount } from '@vue/test-utils'
import { defineComponent, nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  AUTO_SCROLL_BUTTON_THRESHOLD,
  AUTO_SCROLL_PIN_THRESHOLD,
  type UseAssistantAutoScrollReturn,
  useAssistantAutoScroll,
} from '../useAssistantAutoScroll'

interface MockScrollElement {
  scrollHeight: number
  clientHeight: number
  scrollTop: number
  scrollTo: ReturnType<typeof vi.fn>
}

const createScrollElement = (
  scrollHeight: number,
  clientHeight: number,
  scrollTop: number,
): HTMLDivElement & MockScrollElement => {
  const el = document.createElement('div') as HTMLDivElement & MockScrollElement
  let currentScrollTop = scrollTop
  let currentScrollHeight = scrollHeight
  let currentClientHeight = clientHeight
  Object.defineProperty(el, 'scrollHeight', {
    configurable: true,
    get: () => currentScrollHeight,
    set: (value: number) => { currentScrollHeight = value },
  })
  Object.defineProperty(el, 'clientHeight', {
    configurable: true,
    get: () => currentClientHeight,
    set: (value: number) => { currentClientHeight = value },
  })
  Object.defineProperty(el, 'scrollTop', {
    configurable: true,
    get: () => currentScrollTop,
    set: (value: number) => { currentScrollTop = value },
  })
  el.scrollTo = vi.fn((arg: ScrollToOptions | number, y?: number) => {
    if (typeof arg === 'number') {
      currentScrollTop = y ?? currentScrollTop
      return
    }
    if (typeof arg.top === 'number') {
      currentScrollTop = arg.top
    }
  })
  return el
}

const mountScrollHarness = (el: HTMLDivElement): { wrapper: VueWrapper; api: UseAssistantAutoScrollReturn } => {
  const container = ref<HTMLDivElement | null>(el)
  let api!: UseAssistantAutoScrollReturn
  const Harness = defineComponent({
    setup(): () => null {
      api = useAssistantAutoScroll(container)
      return (): null => null
    },
  })
  const wrapper = mount(Harness)
  return { wrapper, api }
}
describe('useAssistantAutoScroll', () => {
  let origRaf: typeof globalThis.requestAnimationFrame
  let origCancelRaf: typeof globalThis.cancelAnimationFrame

  beforeEach(() => {
    vi.useFakeTimers()
    origRaf = globalThis.requestAnimationFrame
    origCancelRaf = globalThis.cancelAnimationFrame
    globalThis.requestAnimationFrame = ((cb: FrameRequestCallback): number => {
      cb(0)
      return 1
    }) as typeof globalThis.requestAnimationFrame
    globalThis.cancelAnimationFrame = vi.fn()
  })

  afterEach(() => {
    globalThis.requestAnimationFrame = origRaf
    globalThis.cancelAnimationFrame = origCancelRaf
    vi.useRealTimers()
  })

  it('sticks to bottom within pin threshold and stops pulling when user scrolls up', async () => {
    const el = createScrollElement(1000, 400, 600)
    const { wrapper, api } = mountScrollHarness(el)

    // Pinned at bottom: new content scrolls to bottom.
    el.scrollHeight = 1200
    api.scrollIfPinned(true)
    await nextTick()
    expect(el.scrollTop).toBe(1200)
    expect(api.isPinned.value).toBe(true)
    expect(api.hasUnreadBelow.value).toBe(false)

    // User scrolls up past button threshold.
    el.scrollTop = 1200 - 400 - (AUTO_SCROLL_BUTTON_THRESHOLD + 20)
    api.onScroll()
    expect(api.isPinned.value).toBe(false)
    expect(api.showScrollToBottom.value).toBe(true)

    // New content arrives while unpinned: viewport is NOT pulled down, unread flag turns on.
    const stayedAt = el.scrollTop
    el.scrollHeight = 1400
    api.scrollIfPinned(true)
    await nextTick()
    expect(el.scrollTop).toBe(stayedAt)
    expect(api.hasUnreadBelow.value).toBe(true)

    // Clicking scroll-to-bottom forces bottom and resets flags.
    api.scrollToBottomForce(false)
    await nextTick()
    expect(el.scrollTop).toBe(1400)
    expect(api.isPinned.value).toBe(true)
    expect(api.hasUnreadBelow.value).toBe(false)
    expect(api.showScrollToBottom.value).toBe(false)

    wrapper.unmount()
  })

  it('only shows scroll-to-bottom button past button threshold, not pin threshold', () => {
    const el = createScrollElement(1000, 400, 600)
    const { wrapper, api } = mountScrollHarness(el)

    el.scrollTop = 600 - (AUTO_SCROLL_PIN_THRESHOLD + 12)
    api.onScroll()
    expect(api.isPinned.value).toBe(false)
    expect(api.showScrollToBottom.value).toBe(false)

    el.scrollTop = 600 - (AUTO_SCROLL_BUTTON_THRESHOLD + 1)
    api.onScroll()
    expect(api.showScrollToBottom.value).toBe(true)

    wrapper.unmount()
  })

  it('preserves viewport offset across history prepend and KeepAlive deactivate/activate', async () => {
    const el = createScrollElement(1000, 400, 200)
    const { wrapper, api } = mountScrollHarness(el)

    api.onScroll()
    expect(api.isPinned.value).toBe(false)

    await api.preservePositionAcrossPrepend(async () => {
      el.scrollHeight = 1450
      await nextTick()
    })
    expect(el.scrollTop).toBe(650)

    // Capture unpinned position and restore after KeepAlive activation.
    api.captureScrollPosition()
    el.scrollTop = 0
    await api.restoreScrollPosition()
    expect(el.scrollTop).toBe(650)

    wrapper.unmount()
  })

  it('anchors reopen scroll to the latest user turn when the tail exceeds one viewport', async () => {
    const el = createScrollElement(1600, 500, 0)
    const anchor = document.createElement('div')
    anchor.setAttribute('data-turn-anchor', '')
    el.appendChild(anchor)

    vi.spyOn(el, 'getBoundingClientRect').mockReturnValue({
      top: 100, bottom: 600, left: 0, right: 500, width: 500, height: 500, x: 0, y: 100, toJSON: () => ({}),
    })
    vi.spyOn(anchor, 'getBoundingClientRect').mockReturnValue({
      top: 900, bottom: 940, left: 0, right: 500, width: 500, height: 40, x: 0, y: 900, toJSON: () => ({}),
    })

    const { wrapper, api } = mountScrollHarness(el)
    api.scrollToLatestTurnOrBottom(true)
    await nextTick()

    // anchorTop = 900 - 100 + 0 = 800; scrollHeight - anchorTop = 800 > clientHeight (500) -> 800 - 16 = 784
    expect(el.scrollTop).toBe(784)

    wrapper.unmount()
  })
})
