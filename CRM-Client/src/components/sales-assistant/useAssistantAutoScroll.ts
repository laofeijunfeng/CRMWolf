import { nextTick, ref, type Ref } from 'vue'

export const AUTO_SCROLL_PIN_THRESHOLD = 8
export const AUTO_SCROLL_BUTTON_THRESHOLD = 80
const TURN_ANCHOR_OFFSET = 16
const AUTO_SCROLL_RELEASE_MS = 100
const SMOOTH_SCROLL_GUARD_MS = 500

export interface UseAssistantAutoScrollOptions {
  isDisposed?: () => boolean
}

export interface UseAssistantAutoScrollReturn {
  isPinned: Ref<boolean>
  hasUnreadBelow: Ref<boolean>
  showScrollToBottom: Ref<boolean>
  onScroll: () => void
  scrollIfPinned: (waitForLayout?: boolean) => void
  scrollToBottomForce: (waitForLayout?: boolean, smooth?: boolean) => void
  scrollToLatestTurnOrBottom: (waitForLayout?: boolean) => void
  preservePositionAcrossPrepend: (applyPrepend: () => void | Promise<void>) => Promise<void>
  captureScrollPosition: () => void
  restoreScrollPosition: () => void
}

const prefersReducedMotion = (): boolean => (
  typeof window !== 'undefined'
  && typeof window.matchMedia === 'function'
  && window.matchMedia('(prefers-reduced-motion: reduce)').matches
)

const distanceFromBottom = (el: HTMLElement): number => (
  Math.max(0, el.scrollHeight - el.scrollTop - el.clientHeight)
)

export function useAssistantAutoScroll(
  containerRef: Ref<HTMLElement | null>,
  options: UseAssistantAutoScrollOptions = {},
): UseAssistantAutoScrollReturn {
  const isPinned = ref(true)
  const hasUnreadBelow = ref(false)
  const showScrollToBottom = ref(false)

  let scrollSchedule = 0
  let programmaticScroll = false
  let programmaticToken = 0
  let smoothGuardTimer: number | null = null
  let savedScrollTop: number | null = null
  let savedWasPinned = true

  const clearSmoothGuardTimer = (): void => {
    if (smoothGuardTimer !== null) {
      window.clearTimeout(smoothGuardTimer)
      smoothGuardTimer = null
    }
  }

  const syncPinState = (el: HTMLElement): void => {
    const distance = distanceFromBottom(el)
    const pinned = distance <= AUTO_SCROLL_PIN_THRESHOLD
    isPinned.value = pinned
    showScrollToBottom.value = distance > AUTO_SCROLL_BUTTON_THRESHOLD
    if (pinned) hasUnreadBelow.value = false
  }

  const armProgrammaticRelease = (token: number, behavior: ScrollBehavior): void => {
    clearSmoothGuardTimer()
    const release = (): void => {
      if (token !== programmaticToken) return
      clearSmoothGuardTimer()
      programmaticScroll = false
    }
    if (behavior === 'smooth') {
      smoothGuardTimer = window.setTimeout(release, SMOOTH_SCROLL_GUARD_MS)
      return
    }
    smoothGuardTimer = window.setTimeout(release, AUTO_SCROLL_RELEASE_MS)
    if (typeof requestAnimationFrame === 'function') {
      requestAnimationFrame(() => requestAnimationFrame(release))
    } else {
      release()
    }
  }

  const performProgrammaticScroll = (el: HTMLElement, top: number, behavior: ScrollBehavior = 'auto'): void => {
    const token = ++programmaticToken
    programmaticScroll = true
    if (typeof el.scrollTo === 'function') {
      el.scrollTo({ top, behavior })
    } else {
      el.scrollTop = top
    }
    armProgrammaticRelease(token, behavior)
  }

  const scheduleScroll = (waitForLayout: boolean, run: (el: HTMLElement) => void): void => {
    const schedule = ++scrollSchedule
    void nextTick(() => {
      const scroller = containerRef.value
      if (scroller === null || schedule !== scrollSchedule) return
      const execute = (): void => {
        if (schedule !== scrollSchedule || options.isDisposed?.() === true || containerRef.value !== scroller) return
        run(scroller)
      }
      if (!waitForLayout) {
        execute()
        return
      }
      if (typeof requestAnimationFrame === 'function') {
        requestAnimationFrame(() => requestAnimationFrame(execute))
      } else {
        execute()
      }
    })
  }

  const onScroll = (): void => {
    const el = containerRef.value
    if (el === null) return
    if (programmaticScroll) {
      if (distanceFromBottom(el) <= AUTO_SCROLL_PIN_THRESHOLD && smoothGuardTimer !== null) {
        clearSmoothGuardTimer()
        programmaticScroll = false
      }
      return
    }
    syncPinState(el)
  }

  const scrollToBottomForce = (waitForLayout = false, smooth = false): void => {
    isPinned.value = true
    hasUnreadBelow.value = false
    showScrollToBottom.value = false
    const behavior: ScrollBehavior = smooth && !prefersReducedMotion() ? 'smooth' : 'auto'
    scheduleScroll(waitForLayout, (el) => {
      performProgrammaticScroll(el, el.scrollHeight, behavior)
    })
  }

  const scrollIfPinned = (waitForLayout = false): void => {
    if (!isPinned.value) {
      hasUnreadBelow.value = true
      const el = containerRef.value
      if (el !== null && distanceFromBottom(el) > AUTO_SCROLL_BUTTON_THRESHOLD) {
        showScrollToBottom.value = true
      }
      return
    }
    scheduleScroll(waitForLayout, (el) => {
      if (!isPinned.value) {
        hasUnreadBelow.value = true
        return
      }
      performProgrammaticScroll(el, el.scrollHeight, 'auto')
    })
  }

  const scrollToLatestTurnOrBottom = (waitForLayout = true): void => {
    scheduleScroll(waitForLayout, (el) => {
      const anchors = el.querySelectorAll<HTMLElement>('[data-turn-anchor]')
      const lastAnchor = anchors.length > 0 ? anchors[anchors.length - 1] : undefined
      if (lastAnchor !== undefined && el.clientHeight > 0) {
        const containerRect = el.getBoundingClientRect()
        const anchorRect = lastAnchor.getBoundingClientRect()
        const anchorTop = el.scrollTop + (anchorRect.top - containerRect.top)
        if (el.scrollHeight - anchorTop > el.clientHeight) {
          const targetTop = Math.max(0, anchorTop - TURN_ANCHOR_OFFSET)
          performProgrammaticScroll(el, targetTop, 'auto')
          const remaining = Math.max(0, el.scrollHeight - targetTop - el.clientHeight)
          isPinned.value = remaining <= AUTO_SCROLL_PIN_THRESHOLD
          showScrollToBottom.value = remaining > AUTO_SCROLL_BUTTON_THRESHOLD
          hasUnreadBelow.value = false
          return
        }
      }
      isPinned.value = true
      hasUnreadBelow.value = false
      showScrollToBottom.value = false
      performProgrammaticScroll(el, el.scrollHeight, 'auto')
    })
  }

  const preservePositionAcrossPrepend = async (applyPrepend: () => void | Promise<void>): Promise<void> => {
    scrollSchedule += 1
    const el = containerRef.value
    const prevHeight = el?.scrollHeight ?? 0
    const prevTop = el?.scrollTop ?? 0
    await applyPrepend()
    await nextTick()
    const current = containerRef.value
    if (current !== null && current === el) {
      const token = ++programmaticToken
      programmaticScroll = true
      current.scrollTop = prevTop + current.scrollHeight - prevHeight
      syncPinState(current)
      armProgrammaticRelease(token, 'auto')
    }
  }

  const captureScrollPosition = (): void => {
    savedWasPinned = isPinned.value
    savedScrollTop = containerRef.value?.scrollTop ?? null
  }

  const restoreScrollPosition = (): void => {
    if (savedWasPinned || savedScrollTop === null) {
      scrollToBottomForce(true)
      return
    }
    const targetTop = savedScrollTop
    scheduleScroll(true, (el) => {
      performProgrammaticScroll(el, targetTop, 'auto')
      const remaining = Math.max(0, el.scrollHeight - targetTop - el.clientHeight)
      isPinned.value = remaining <= AUTO_SCROLL_PIN_THRESHOLD
      showScrollToBottom.value = remaining > AUTO_SCROLL_BUTTON_THRESHOLD
    })
  }

  return {
    isPinned,
    hasUnreadBelow,
    showScrollToBottom,
    onScroll,
    scrollIfPinned,
    scrollToBottomForce,
    scrollToLatestTurnOrBottom,
    preservePositionAcrossPrepend,
    captureScrollPosition,
    restoreScrollPosition,
  }
}
