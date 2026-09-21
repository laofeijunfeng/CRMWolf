import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'
import { describe, expect, it, onTestFinished, vi } from 'vitest'
import DetailContextHost from '@/components/crmwolf/DetailContextHost.vue'
import type { DetailContextNode } from '@/types/detailContext'

vi.mock('@/components/ui/button', () => ({
  Button: defineComponent({
    name: 'Button',
    props: {
      type: String,
      variant: String,
      size: String,
    },
    setup: (props, { attrs, slots }) => () => h('button', {
      ...attrs,
      type: props.type ?? 'button',
    }, slots.default?.()),
  }),
}))

vi.mock('@/components/ui/breadcrumb', () => {
  const passthrough = (name: string) => defineComponent({
    name,
    setup: (_, { slots }) => () => h('div', slots.default?.()),
  })

  return {
    Breadcrumb: passthrough('Breadcrumb'),
    BreadcrumbItem: passthrough('BreadcrumbItem'),
    BreadcrumbLink: passthrough('BreadcrumbLink'),
    BreadcrumbList: passthrough('BreadcrumbList'),
    BreadcrumbPage: passthrough('BreadcrumbPage'),
    BreadcrumbSeparator: passthrough('BreadcrumbSeparator'),
  }
})

interface DetailContextHostExpose {
  focusBackButton: () => void
}

const journeyNode: DetailContextNode = {
  type: 'journey',
  id: 'journey-1',
  label: '续费旅程',
  source: 'list',
}

const contractNode: DetailContextNode = {
  type: 'contract',
  id: 'contract-1',
  label: '续费合同',
  parentType: 'journey',
  parentId: 'journey-1',
  source: 'related-object',
}

const PersistentBody = defineComponent({
  name: 'PersistentBody',
  setup: () => () => h('input', {
    'data-testid': 'persistent-body',
    value: 'kept',
  }),
})

describe('DetailContextHost', () => {
  it('shows the context header by default', () => {
    const wrapper = mount(DetailContextHost, {
      props: {
        nodes: [journeyNode],
        canGoBack: false,
      },
      slots: { default: '<div data-testid="body">content</div>' },
    })

    expect(wrapper.find('[data-testid="detail-context-header"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="body"]').text()).toBe('content')
  })

  it('hides only the header while keeping the same body element', async () => {
    const wrapper = mount(DetailContextHost, {
      props: {
        nodes: [journeyNode],
        canGoBack: false,
        showHeader: true,
      },
      slots: { default: () => h(PersistentBody) },
    })
    const body = wrapper.get('[data-testid="persistent-body"]').element

    await wrapper.setProps({ showHeader: false })

    expect(wrapper.find('[data-testid="detail-context-header"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="persistent-body"]').element).toBe(body)
  })

  it('focuses the back button through the host expose API', async () => {
    const wrapper = mount(DetailContextHost, {
      attachTo: document.body,
      props: {
        nodes: [journeyNode, contractNode],
        canGoBack: true,
      },
    })
    onTestFinished(() => wrapper.unmount())

    ;(wrapper.vm as unknown as DetailContextHostExpose).focusBackButton()
    await nextTick()

    expect(document.activeElement).toBe(wrapper.get('[data-testid="detail-context-back"]').element)
  })

  it('does not focus a breadcrumb crumb when the back button is absent', async () => {
    const wrapper = mount(DetailContextHost, {
      attachTo: document.body,
      props: {
        nodes: [journeyNode, contractNode],
        canGoBack: false,
      },
    })
    onTestFinished(() => wrapper.unmount())

    const outsideTrigger = document.createElement('button')
    document.body.appendChild(outsideTrigger)
    onTestFinished(() => outsideTrigger.remove())
    outsideTrigger.focus()
    ;(wrapper.vm as unknown as DetailContextHostExpose).focusBackButton()
    await nextTick()

    expect(document.activeElement).toBe(outsideTrigger)
    expect(document.activeElement).not.toBe(wrapper.get('[aria-label="返回续费旅程"]').element)
  })
})
