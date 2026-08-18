import { afterEach, describe, expect, it } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import HoverInfo from '@/components/crmwolf/HoverInfo.vue'

if (typeof globalThis.PointerEvent === 'undefined') {
  class PointerEventPolyfill extends MouseEvent {
    pointerType: string
    constructor(type: string, init: MouseEventInit & { pointerType?: string } = {}) {
      super(type, init)
      this.pointerType = init.pointerType ?? 'mouse'
    }
  }
  globalThis.PointerEvent = PointerEventPolyfill as typeof PointerEvent
}

const wait = async (ms: number): Promise<void> => {
  await new Promise(resolve => {
    setTimeout(resolve, ms)
  })
}

const hoverTrigger = async (wrapper: ReturnType<typeof mount>): Promise<void> => {
  const trigger = wrapper.get('[data-testid="hover-trigger"]')
  await trigger.trigger('pointerenter', { pointerType: 'mouse' })
  await trigger.trigger('mouseenter')
  await nextTick()
  await wait(50)
}

describe('HoverInfo', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('opens citation content on hover when the parent does not control open', async () => {
    const wrapper = mount(HoverInfo, {
      attachTo: document.body,
      props: { openDelay: 0, closeDelay: 0 },
      slots: {
        trigger: '<span class="customer-brief-citation" tabindex="0" data-testid="hover-trigger">[1]</span>',
        default: '<div data-testid="hover-content">索引内容：客户活动摘录</div>',
      },
    })

    await nextTick()
    expect(document.body.textContent).not.toContain('索引内容：客户活动摘录')

    await hoverTrigger(wrapper)

    expect(wrapper.get('[data-testid="hover-trigger"]').attributes('data-state')).toBe('open')
    expect(document.body.textContent).toContain('索引内容：客户活动摘录')
    wrapper.unmount()
  })

  it('stays closed until the parent updates v-model:open', async () => {
    const Harness = defineComponent({
      setup() {
        const open = ref(false)
        return () => h(HoverInfo, {
          open: open.value,
          openDelay: 0,
          closeDelay: 0,
          'onUpdate:open': (value: boolean) => {
            open.value = value
          },
        }, {
          trigger: () => h('span', {
            class: 'customer-brief-citation',
            tabindex: '0',
            'data-testid': 'hover-trigger',
          }, '[1]'),
          default: () => h('div', { 'data-testid': 'hover-content' }, '索引内容：客户活动摘录'),
        })
      },
    })

    const wrapper = mount(Harness, { attachTo: document.body })
    await nextTick()
    await hoverTrigger(wrapper)

    expect(wrapper.get('[data-testid="hover-trigger"]').attributes('data-state')).toBe('open')
    expect(document.body.textContent).toContain('索引内容：客户活动摘录')
    wrapper.unmount()
  })

  it('renders content when the parent forces open', async () => {
    const wrapper = mount(HoverInfo, {
      attachTo: document.body,
      props: { open: true, openDelay: 0, closeDelay: 0 },
      slots: {
        trigger: '<span data-testid="hover-trigger">[1]</span>',
        default: '<div data-testid="hover-content">索引内容：客户活动摘录</div>',
      },
    })

    await nextTick()
    expect(document.body.textContent).toContain('索引内容：客户活动摘录')
    wrapper.unmount()
  })
})
