// CRM-Client/tests/composables/usePageTitle.spec.ts
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'
import { usePageTitle } from '@/composables/usePageTitle'
import { usePageTitleStore } from '@/stores/pageTitle'

// Mock Vue Router
const mockRoute = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => mockRoute()
}))

describe('usePageTitle composable', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('should auto-set title from route.meta.title on mount', async () => {
    mockRoute.mockReturnValue({
      meta: { title: '测试页面' }
    })

    const store = usePageTitleStore()

    // 创建测试组件来包装 composable
    const TestComponent = defineComponent({
      setup() {
        usePageTitle()
        return {}
      },
      render: () => h('div')
    })

    mount(TestComponent)

    // 等待 onMounted 执行
    await nextTick()
    expect(store.title).toBe('测试页面')
  })

  it('should allow manual title override via setTitle()', async () => {
    mockRoute.mockReturnValue({
      meta: { title: '测试页面' }
    })

    const store = usePageTitleStore()

    const TestComponent = defineComponent({
      setup() {
        const { setTitle } = usePageTitle()
        return { setTitle }
      },
      render: () => h('div')
    })

    const wrapper = mount(TestComponent)
    await nextTick()

    // 在挂载后手动设置标题
    wrapper.vm.setTitle('自定义标题')
    await nextTick()

    expect(store.title).toBe('自定义标题')
  })

  it('should reset title via resetTitle()', async () => {
    mockRoute.mockReturnValue({
      meta: { title: '测试页面' }
    })

    const store = usePageTitleStore()

    const TestComponent = defineComponent({
      setup() {
        const { resetTitle } = usePageTitle()
        return { resetTitle }
      },
      render: () => h('div')
    })

    const wrapper = mount(TestComponent)
    await nextTick()

    // 验证自动设置了标题
    expect(store.title).toBe('测试页面')

    // 调用 resetTitle
    wrapper.vm.resetTitle()
    await nextTick()

    expect(store.title).toBe('')
  })

  it('should handle empty route.meta.title', async () => {
    mockRoute.mockReturnValue({
      meta: {}
    })

    const store = usePageTitleStore()

    const TestComponent = defineComponent({
      setup() {
        usePageTitle()
        return {}
      },
      render: () => h('div')
    })

    mount(TestComponent)
    await nextTick()

    expect(store.title).toBe('')
  })
})