import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { usePageTitle } from '@/composables/usePageTitle'
import { usePageTitleStore } from '@/stores/pageTitle'

const mockRoute = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({ useRoute: () => mockRoute() }))

describe('usePageTitle composable', () => {
  let pinia = createPinia()
  const wrappers: VueWrapper[] = []

  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    mockRoute.mockReturnValue({ meta: { title: '测试页面' } })
  })

  afterEach(() => {
    for (const wrapper of wrappers.splice(0)) wrapper.unmount()
    vi.clearAllMocks()
  })

  function mountPage() {
    const Page = defineComponent({
      setup: usePageTitle,
      render: () => h('div'),
    })
    const wrapper = mount(Page, { global: { plugins: [pinia] } })
    wrappers.push(wrapper)
    return wrapper
  }

  it('sets the route title on mount and releases it on unmount', () => {
    const store = usePageTitleStore(pinia)
    const wrapper = mountPage()
    expect(store.title).toBe('测试页面')
    wrapper.unmount()
    expect(store.title).toBe('')
    wrappers.pop()
  })

  it('allows a mounted page to override and reset its title', () => {
    const store = usePageTitleStore(pinia)
    const wrapper = mountPage()
    wrapper.vm.setTitle('自定义标题')
    expect(store.title).toBe('自定义标题')
    wrapper.vm.resetTitle()
    expect(store.title).toBe('')
  })

  it('leaves the title empty when route metadata has no title', () => {
    mockRoute.mockReturnValue({ meta: {} })
    mountPage()
    expect(usePageTitleStore(pinia).title).toBe('')
  })
})
