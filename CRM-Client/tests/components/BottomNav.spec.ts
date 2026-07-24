import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { usePermissionStore } from '@/stores/permissions'

const router = vi.hoisted(() => ({ push: vi.fn() }))
const route = vi.hoisted(() => ({ path: '/customers' }))
vi.mock('vue-router', async importOriginal => ({
  ...await importOriginal<typeof import('vue-router')>(),
  useRouter: () => router,
  useRoute: () => route,
}))

import BottomNav from '@/components/crmwolf/BottomNav.vue'
import appRouter from '@/router'

describe('BottomNav account affordances', () => {
  beforeEach(() => {
    router.push.mockReset()
    setActivePinia(createPinia())
    const permissionStore = usePermissionStore()
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

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('orders primary mobile navigation as Agent, customers, opportunities, contracts, more', () => {
    const wrapper = mount(BottomNav)

    const labels = wrapper
      .findAll('.bottom-nav-container > button')
      .map(button => button.attributes('aria-label'))

    expect(labels).toEqual(['Agent', '客户', '商机', '合同', '更多'])
  })

  it('orders More menu as dashboard, leads, payments, invoices, account settings, logout', async () => {
    const wrapper = mount(BottomNav)
    await wrapper.get('button[aria-label="更多"]').trigger('click')

    const menuLabels = Array.from(document.body.querySelectorAll('[role="menuitem"]'))
      .map(item => item.getAttribute('aria-label'))

    expect(menuLabels).toEqual(['看板', '线索', '回款', '发票', '账户设置', '退出登录'])
    expect(menuLabels).not.toContain('审批')
  })

  it('offers account settings in More and navigates to its dedicated route', async () => {
    const wrapper = mount(BottomNav)
    await wrapper.get('button[aria-label="更多"]').trigger('click')

    const accountItem = document.body.querySelector('[role="menuitem"][aria-label="账户设置"]') as HTMLElement
    expect(accountItem).not.toBeNull()
    accountItem.click()

    expect(router.push).toHaveBeenCalledWith('/account')
  })

  it('emits logout rather than mutating authentication state itself', async () => {
    const wrapper = mount(BottomNav)
    await wrapper.get('button[aria-label="更多"]').trigger('click')

    const logoutItem = document.body.querySelector('[role="menuitem"][aria-label="退出登录"]') as HTMLElement
    expect(logoutItem).not.toBeNull()
    logoutItem.click()

    expect(wrapper.emitted('logout')).toEqual([[]])
  })
})

describe('account settings route', () => {
  it('requires authentication and has the account settings title', () => {
    const accountRoute = appRouter.getRoutes().find(record => record.path === '/account')

    expect(accountRoute?.meta.requiresAuth).toBe(true)
    expect(accountRoute?.meta.title).toBe('账户设置')
  })
})
