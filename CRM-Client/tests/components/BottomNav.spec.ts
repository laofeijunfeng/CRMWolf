import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { usePermissionStore } from '@/stores/permissions'
import BottomNav from '@/components/crmwolf/BottomNav.vue'

enableAutoUnmount(afterEach)

async function mountNavigation() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: ['agent', 'customers', 'opportunities', 'contracts', 'sales-dashboard', 'leads', 'payments', 'invoices', 'account']
      .map(path => ({ path: `/${path}`, component: { template: '<div />' } })),
  })
  await router.push('/customers')
  await router.isReady()
  const wrapper = mount(BottomNav, { attachTo: document.body, global: { plugins: [router] } })
  return { wrapper, router }
}

describe('BottomNav account affordances', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    const permissionStore = usePermissionStore()
    permissionStore.loadState = 'ready'
    permissionStore.permissions = [{
      id: 1,
      code: 'sales_dashboard:view:own',
      name: '查看自己的销售看板',
      resource: 'sales_dashboard',
      action: 'view',
      scope: 'own',
      description: null,
      created_at: '2026-07-24T00:00:00Z',
      updated_at: '2026-07-24T00:00:00Z',
    }]
  })


  it('offers primary destinations as links followed by the More disclosure', async () => {
    const { wrapper } = await mountNavigation()
    const links = wrapper.findAll('.bottom-nav-container > a')
    expect(links.map(link => link.attributes('href'))).toEqual(['/agent', '/customers', '/opportunities', '/contracts'])
    expect(links[1].attributes('aria-current')).toBe('page')
    expect(wrapper.get('button[aria-label="更多"]').attributes('aria-expanded')).toBe('false')
  })

  it('orders More menu as dashboard, leads, payments, invoices, account settings, logout', async () => {
    const { wrapper } = await mountNavigation()
    await wrapper.get('button[aria-label="更多"]').trigger('click')

    const menuLabels = Array.from(document.body.querySelectorAll('[role="menuitem"]'))
      .map(item => item.getAttribute('aria-label'))

    expect(menuLabels).toEqual(['看板', '线索', '回款', '发票', '账户设置', '退出登录'])
    expect(menuLabels).not.toContain('审批')
  })

  it('offers account settings in More and navigates to its dedicated route', async () => {
    const { wrapper, router } = await mountNavigation()
    await wrapper.get('button[aria-label="更多"]').trigger('click')

    const accountItem = document.body.querySelector('[role="menuitem"][aria-label="账户设置"]') as HTMLElement
    expect(accountItem).not.toBeNull()
    expect(accountItem.tagName).toBe('A')
    expect(accountItem.getAttribute('href')).toBe('/account')
    accountItem.click()

    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/account')
    expect(wrapper.emitted('logout')).toBeUndefined()
  })

  it('emits logout rather than mutating authentication state itself', async () => {
    const { wrapper, router } = await mountNavigation()
    await wrapper.get('button[aria-label="更多"]').trigger('click')

    const logoutItem = document.body.querySelector('[role="menuitem"][aria-label="退出登录"]') as HTMLElement
    expect(logoutItem).not.toBeNull()
    logoutItem.click()

    expect(wrapper.emitted('logout')).toEqual([[]])
    expect(router.currentRoute.value.path).toBe('/customers')
  })
})
