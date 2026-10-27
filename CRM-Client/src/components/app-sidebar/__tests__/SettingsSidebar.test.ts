import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import SettingsSidebar from '@/components/app-sidebar/SettingsSidebar.vue'
import { getSettingsNavigationItem, getVisibleSettingsNavigation } from '@/settingsNavigation'

const router = vi.hoisted(() => ({ push: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: (): { path: string } => ({ path: '/settings/integrations' }), useRouter: (): typeof router => router }))
vi.mock('@/composables/useSettingsAccess', () => ({ useSettingsAccess: (): { canAccess: () => boolean } => ({ canAccess: (): boolean => true }) }))

describe('SettingsSidebar navigation contract', () => {
  it('filters inaccessible modules while keeping account settings available', () => {
    const visible = getVisibleSettingsNavigation(item => item.id === 'account' || item.id === 'roles')
    expect(visible.map(item => item.label)).toEqual(['账户设置', '角色管理'])
    expect(getSettingsNavigationItem('account')?.scope).toBe('personal')
  })

  it('exposes every settings module to the team owner policy', () => {
    const visible = getVisibleSettingsNavigation(() => true)
    expect(visible.map(item => item.id)).toEqual(expect.arrayContaining(['products', 'ai']))
  })

  it('does not expose the retired run-log item even to the team owner', () => {
    expect(getVisibleSettingsNavigation(() => true).some(item => item.id === 'agent-run-log')).toBe(false)
  })

  it('returns to the sales assistant', async () => {
    const passthrough = { template: '<div><slot /></div>' }
    const wrapper = mount(SettingsSidebar, {
      global: {
        stubs: {
          Sidebar: passthrough, SidebarHeader: passthrough, SidebarContent: passthrough,
          SidebarFooter: passthrough, SidebarMenu: passthrough, SidebarMenuItem: passthrough,
          SidebarGroup: passthrough, SidebarGroupContent: passthrough,
          SidebarMenuButton: { template: '<button><slot /></button>' },
          SidebarRail: true, NavMain: true, NavUser: true,
        },
      },
    })
    await wrapper.get('button[aria-label="返回系统"]').trigger('click')
    expect(router.push).toHaveBeenCalledWith('/assistant')
    wrapper.unmount()
  })

})
