import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { Building2 } from 'lucide-vue-next'
import BottomNavItem from '../BottomNavItem.vue'

describe('BottomNavItem', () => {
  it('renders an accessible route link whose current state follows the active prop', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/customers', component: { template: '<div />' } },
        { path: '/customers/:id', component: { template: '<div />' } },
      ],
    })
    await router.push('/customers/123')
    await router.isReady()

    const wrapper = mount(BottomNavItem, {
      props: {
        item: { route: '/customers', icon: Building2, label: '客户' },
        active: true,
      },
      global: { plugins: [router] },
    })

    try {
      const link = wrapper.get('a')
      expect(link.attributes('href')).toBe('/customers')
      expect(link.attributes('aria-label')).toBe('客户')
      expect(link.attributes('aria-current')).toBe('page')

      await wrapper.setProps({ active: false })
      expect(link.attributes('aria-current')).toBeUndefined()

      await link.trigger('click')
      await flushPromises()
      expect(router.currentRoute.value.path).toBe('/customers')
      expect(link.attributes('aria-current')).toBeUndefined()
    } finally {
      wrapper.unmount()
    }
  })
})
