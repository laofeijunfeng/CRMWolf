import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SettingsContent from '../SettingsContent.vue'

describe('SettingsContent', () => {
  it('renders a full-width main landmark without a page heading or max-width shell', () => {
    const wrapper = mount(SettingsContent, {
      props: { ariaLabel: '账户设置', description: '个人资料和登录安全。' },
      slots: { default: '<div class="probe">body</div>' },
    })
    expect(wrapper.html().trim().startsWith('<main')).toBe(true)
    expect(wrapper.attributes('aria-label')).toBe('账户设置')
    expect(wrapper.classes()).toContain('settings-content')
    expect(wrapper.classes().join(' ')).not.toContain('max-w-6xl')
    expect(wrapper.find('h1').exists()).toBe(false)
    expect(wrapper.get('p.settings-content__description').text()).toBe('个人资料和登录安全。')
    expect(wrapper.get('.probe').text()).toBe('body')
    wrapper.unmount()
  })

  it('omits the description paragraph when description is empty', () => {
    const wrapper = mount(SettingsContent, { props: { ariaLabel: '角色管理' } })
    expect(wrapper.find('p.settings-content__description').exists()).toBe(false)
    wrapper.unmount()
  })
})
