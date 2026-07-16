import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

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
  beforeEach(() => router.push.mockReset())

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
