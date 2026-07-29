import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AppDrawer from '@/components/ui/app-drawer/AppDrawer.vue'

class ResizeObserverMock {
  observe = vi.fn()
  disconnect = vi.fn()
}

describe('AppDrawer', () => {
  const originalResizeObserver = globalThis.ResizeObserver
  const originalRequestAnimationFrame = globalThis.requestAnimationFrame
  const originalGetBoundingClientRect = Element.prototype.getBoundingClientRect

  beforeEach(() => {
    globalThis.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver
    globalThis.requestAnimationFrame = ((callback: FrameRequestCallback) => {
      callback(0)
      return 1
    }) as typeof requestAnimationFrame
    Element.prototype.getBoundingClientRect = vi.fn(() => ({
      x: 0,
      y: 0,
      width: 720,
      height: 188,
      top: 0,
      right: 720,
      bottom: 188,
      left: 0,
      toJSON: () => ({}),
    }))
  })

  afterEach(() => {
    globalThis.ResizeObserver = originalResizeObserver
    globalThis.requestAnimationFrame = originalRequestAnimationFrame
    Element.prototype.getBoundingClientRect = originalGetBoundingClientRect
    vi.restoreAllMocks()
  })

  it('measures height when mounted open so inline agent drawers can reserve message space', async () => {
    const wrapper = mount(AppDrawer, {
      props: {
        open: true,
        title: '请选择客户',
        portal: false,
        modal: false,
        showOverlay: false,
      },
      slots: {
        default: '<button>越秀金融</button>',
      },
    })

    await nextTick()
    await nextTick()

    expect(wrapper.emitted('height-change')?.at(-1)).toEqual([188])
  })
})
