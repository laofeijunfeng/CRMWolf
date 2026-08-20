import { mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { nextTick, ref } from 'vue'
import HoverInfo from '../HoverInfo.vue'

const attached: VueWrapper[] = []

const mountHoverInfo = (label: string, contentClass?: string): VueWrapper => {
  const wrapper = mount({
    components: { HoverInfo },
    setup: () => ({
      open: ref(true),
      contentClass
    }),
    template: `
      <HoverInfo :open="open" :open-delay="0" :close-delay="0" :content-class="contentClass">
        <template #trigger>
          <button type="button">触发</button>
        </template>
        ${label}
      </HoverInfo>
    `,
    attachTo: document.body
  })
  attached.push(wrapper)
  return wrapper
}

const findHoverContent = (label: string): HTMLElement => {
  const content = Array.from(document.body.querySelectorAll<HTMLElement>('.crm-hover-info-content'))
    .find(node => node.textContent?.includes(label) === true)
  if (content === undefined) throw new Error(`HoverInfo content not found for ${label}`)
  return content
}

describe('HoverInfo overlay surface', () => {
  afterEach(() => {
    while (attached.length > 0) {
      attached.pop()?.unmount()
    }
  })

  it('keeps default hover content on the tooltip surface', async () => {
    mountHoverInfo('默认提示')
    await nextTick()
    const content = findHoverContent('默认提示')
    expect(content.classList.contains('rounded-md')).toBe(true)
    expect(content.classList.contains('shadow-wolf-hover')).toBe(true)
    expect(content.classList.contains('rounded-wolf-overlay')).toBe(false)
    expect(content.classList.contains('shadow-wolf-overlay')).toBe(false)
  })

  it('promotes is-panel hover content to the overlay surface', async () => {
    mountHoverInfo('商机面板', 'customer-opportunity-hover-card is-panel w-[460px] p-0')
    await nextTick()
    const content = findHoverContent('商机面板')
    expect(content.classList.contains('is-panel')).toBe(true)
    expect(content.classList.contains('rounded-wolf-overlay')).toBe(true)
    expect(content.classList.contains('shadow-wolf-overlay')).toBe(true)
    expect(content.classList.contains('rounded-md')).toBe(false)
    expect(content.classList.contains('shadow-wolf-hover')).toBe(false)
  })
})
