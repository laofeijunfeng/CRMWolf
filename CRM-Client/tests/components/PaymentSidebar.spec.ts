// CRM-Client/tests/components/PaymentSidebar.spec.ts
import { describe, it, expect } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import PaymentSidebar from '@/components/PaymentSidebar.vue'

const mountSidebar = (props: { activeNav: 'plans' | 'records' }) =>
  mount(PaymentSidebar, {
    props,
    global: {
      plugins: [ElementPlus],
      stubs: {
        // Stub el-tooltip to render content directly (avoid event interference in test mode)
        ElTooltip: {
          template: '<div><slot /></div>'
        }
      }
    }
  })

describe('PaymentSidebar', () => {
  it('renders navigation items', () => {
    const wrapper = mountSidebar({ activeNav: 'plans' })

    // Should have 2 nav items
    const navItems = wrapper.findAll('.nav-item')
    expect(navItems.length).toBe(2)
  })

  it('shows active state correctly', () => {
    const wrapper = mountSidebar({ activeNav: 'records' })

    // Second nav item should be active
    const activeNav = wrapper.find('.nav-item.active')
    expect(activeNav.exists()).toBe(true)
  })

  it('emits navChange event on click', async () => {
    const wrapper = mountSidebar({ activeNav: 'plans' })

    // Click second nav item
    const secondNav = wrapper.findAll('.nav-item')[1]
    await secondNav.trigger('click')
    await flushPromises()

    // Should emit navChange event with 'records' (camelCase as defined in defineEmits)
    expect(wrapper.emitted('navChange')).toBeTruthy()
    expect(wrapper.emitted('navChange')![0]).toEqual(['records'])
  })

  it('supports keyboard navigation', async () => {
    const wrapper = mountSidebar({ activeNav: 'plans' })

    // Press Enter on first nav item
    const firstNav = wrapper.find('.nav-item')
    await firstNav.trigger('keydown.enter')
    await flushPromises()

    // Should emit navChange event (camelCase as defined in defineEmits)
    expect(wrapper.emitted('navChange')).toBeTruthy()
  })
})