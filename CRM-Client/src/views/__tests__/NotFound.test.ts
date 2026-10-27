import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import NotFound from '@/views/NotFound.vue'
import { useHeaderStore } from '@/stores/header'
import { usePageTitleStore } from '@/stores/pageTitle'

vi.mock('vue-router', () => ({
  useRoute: (): { meta: { title: string } } => ({ meta: { title: '找不到页面' } }),
}))

describe('retired settings missing page', () => {
  it('shows the approved copy without settings actions or inherited header state', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const header = useHeaderStore()
    const title = usePageTitleStore()
    header.configure({ showBack: true, backRoute: '/settings/ai', actions: [
      { id: 'old-setting', label: '旧设置操作', handler: vi.fn() },
    ] })
    const wrapper = mount(NotFound, { global: { plugins: [pinia] } })
    expect(title.title).toBe('找不到页面')
    expect(wrapper.get('h3').text()).toBe('找不到页面')
    expect(wrapper.text()).toContain('这页不存在。')
    expect(wrapper.findAll('button, a')).toHaveLength(0)
    expect(header.actions).toEqual([])
    expect(header.showBack).toBe(false)
    wrapper.unmount()
    expect(title.title).toBe('')
    expect(header.actions).toEqual([])
  })
})
