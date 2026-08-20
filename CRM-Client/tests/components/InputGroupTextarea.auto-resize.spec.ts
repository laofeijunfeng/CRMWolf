import { nextTick } from "vue"
import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"
import InputGroupTextarea from "@/components/ui/input-group/InputGroupTextarea.vue"

describe("InputGroupTextarea auto resize", () => {
  const mountTextarea = (scrollHeight: { value: number }) => {
    const wrapper = mount(InputGroupTextarea, {
      props: {
        autoResize: true,
        minRows: 3,
        maxRows: 10,
      },
      attrs: {
        style: "line-height: 20px; padding: 0; border-width: 0",
      },
    })
    const textarea = wrapper.get("textarea").element
    Object.defineProperty(textarea, "scrollHeight", {
      configurable: true,
      get: () => scrollHeight.value,
    })
    return { textarea, wrapper }
  }

  it("keeps the minimum height for content within the minimum row count", async () => {
    const scrollHeight = { value: 40 }
    const { textarea, wrapper } = mountTextarea(scrollHeight)
    await nextTick()

    expect(textarea.style.height).toBe("60px")
    expect(textarea.style.overflowY).toBe("hidden")
    wrapper.unmount()
  })

  it("grows with content and caps at the configured maximum row count", async () => {
    const scrollHeight = { value: 120 }
    const { textarea, wrapper } = mountTextarea(scrollHeight)
    await nextTick()

    expect(textarea.style.height).toBe("120px")
    expect(textarea.style.overflowY).toBe("hidden")

    scrollHeight.value = 240
    await wrapper.get("textarea").setValue("超过十行的内容")

    expect(textarea.style.height).toBe("200px")
    expect(textarea.style.overflowY).toBe("auto")
    wrapper.unmount()
  })

  it("returns to the minimum height when the model is cleared", async () => {
    const scrollHeight = { value: 180 }
    const { textarea, wrapper } = mountTextarea(scrollHeight)
    await nextTick()

    await wrapper.get("textarea").setValue("较长的内容")
    expect(textarea.style.height).toBe("180px")

    scrollHeight.value = 40
    await wrapper.get("textarea").setValue("")

    expect(textarea.style.height).toBe("60px")
    expect(textarea.style.overflowY).toBe("hidden")
    wrapper.unmount()
  })
})
