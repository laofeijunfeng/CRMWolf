import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ListChecks } from 'lucide-vue-next'
import NavMain from '@/components/app-sidebar/NavMain.vue'

vi.mock('@/components/ui/sidebar', () => ({
  SidebarGroup: { template: '<section><slot /></section>' },
  SidebarGroupLabel: { template: '<h2><slot /></h2>' },
  SidebarGroupContent: { template: '<div><slot /></div>' },
  SidebarMenu: { template: '<div><slot /></div>' },
  SidebarMenuItem: { template: '<div><slot /></div>' },
  SidebarMenuButton: {
    inheritAttrs: false,
    template: '<button v-bind="$attrs"><slot /></button>',
  },
  SidebarMenuBadge: { template: '<span v-bind="$attrs"><slot /></span>' },
}))

describe('NavMain', () => {
  it('shows pending confirmations on the existing customer tracking destination', async () => {
    const wrapper = mount(NavMain, {
      props: {
        groups: [{
          label: '销售流程',
          items: [{
            label: '客户追踪',
            path: '/customer-tracking',
            icon: ListChecks,
            active: false,
            badge: 3,
            badgeDescription: '待确认 3 条',
          }],
        }],
      },
    })

    expect(wrapper.get('[data-testid="nav-item-badge"]').text()).toBe('3')
    expect(wrapper.get('button').attributes('aria-label')).toBe('客户追踪，待确认 3 条')

    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('navigate')).toEqual([['/customer-tracking']])
  })
})
