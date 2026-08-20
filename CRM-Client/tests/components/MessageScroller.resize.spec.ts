import { defineComponent, nextTick } from "vue"
import { mount } from "@vue/test-utils"
import { afterEach, describe, expect, it, vi } from "vitest"
import MessageScroller from "@/components/ui/message-scroller/MessageScroller.vue"

class ResizeObserverStub {
  static current: ResizeObserverStub | null = null
  private readonly callback: ResizeObserverCallback

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback
    ResizeObserverStub.current = this
  }

  observe = vi.fn()
  disconnect = vi.fn()

  trigger(): void {
    this.callback([], this as unknown as ResizeObserver)
  }
}

describe("MessageScroller resize behavior", () => {
  afterEach(() => {
    ResizeObserverStub.current = null
    vi.unstubAllGlobals()
  })

  const mountScroller = async () => {
    vi.stubGlobal("ResizeObserver", ResizeObserverStub)

    const wrapper = mount(MessageScroller, {
      global: {
        stubs: {
          ScrollArea: defineComponent({
            template: '<div data-reka-scroll-area-viewport><slot /></div>',
          }),
        },
      },
    })
    await nextTick()
    const viewport = wrapper.get("[data-reka-scroll-area-viewport]").element as HTMLElement
    return { viewport, wrapper }
  }

  it("keeps the viewport at the bottom when its height changes", async () => {
    const { viewport, wrapper } = await mountScroller()
    let scrollHeight = 300
    let clientHeight = 200
    Object.defineProperties(viewport, {
      scrollHeight: { configurable: true, get: () => scrollHeight },
      clientHeight: { configurable: true, get: () => clientHeight },
    })

    viewport.scrollTop = 100
    viewport.dispatchEvent(new Event("scroll"))
    scrollHeight = 400
    clientHeight = 150
    ResizeObserverStub.current?.trigger()
    await nextTick()

    expect(viewport.scrollTop).toBe(400)
    wrapper.unmount()
  })

  it("does not pull the user to the bottom after they scroll up", async () => {
    const { viewport, wrapper } = await mountScroller()
    let scrollHeight = 300
    const clientHeight = 200
    Object.defineProperties(viewport, {
      scrollHeight: { configurable: true, get: () => scrollHeight },
      clientHeight: { configurable: true, get: () => clientHeight },
    })

    viewport.scrollTop = 40
    viewport.dispatchEvent(new Event("scroll"))
    scrollHeight = 400
    ResizeObserverStub.current?.trigger()
    await nextTick()

    expect(viewport.scrollTop).toBe(40)
    wrapper.unmount()
  })
})
