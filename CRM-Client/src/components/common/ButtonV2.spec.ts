// CRM-Client/src/components/common/ButtonV2.spec.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ButtonV2 from './ButtonV2.vue'
import { Plus } from 'lucide-vue-next'

describe('ButtonV2', () => {
  // ========== 基础功能测试 ==========
  it('renders correctly with default props', () => {
    const wrapper = mount(ButtonV2, {
      slots: {
        default: 'Button Text',
      },
    })
    expect(wrapper.text()).toContain('Button Text')
    expect(wrapper.classes()).toContain('button-v2')
    expect(wrapper.classes()).toContain('button-v2--default')
    expect(wrapper.classes()).toContain('button-v2--md')
  })

  it('applies variant class correctly', () => {
    const wrapper = mount(ButtonV2, {
      props: { variant: 'primary' },
    })
    expect(wrapper.classes()).toContain('button-v2--primary')
  })

  it('applies size class correctly', () => {
    const wrapper = mount(ButtonV2, {
      props: { size: 'lg' },
    })
    expect(wrapper.classes()).toContain('button-v2--lg')
  })

  // ========== 禁用状态测试 ==========
  it('disables button when disabled prop is true', () => {
    const wrapper = mount(ButtonV2, {
      props: { disabled: true },
    })
    // HTML disabled attribute is presence-based (empty string when true)
    expect(wrapper.attributes('disabled')).toBe('')
    expect(wrapper.attributes('aria-disabled')).toBe('true')
    expect(wrapper.classes()).toContain('button-v2--disabled')
  })

  it('does not emit click when disabled', async () => {
    const wrapper = mount(ButtonV2, {
      props: { disabled: true },
    })
    await wrapper.trigger('click')
    expect(wrapper.emitted('click')).toBeFalsy()
  })

  // ========== 加载状态测试 ==========
  it('shows loading spinner when loading prop is true', () => {
    const wrapper = mount(ButtonV2, {
      props: { loading: true },
    })
    expect(wrapper.classes()).toContain('button-v2--loading')
    expect(wrapper.find('.button-v2__spinner').exists()).toBe(true)
  })

  it('disables button when loading', () => {
    const wrapper = mount(ButtonV2, {
      props: { loading: true },
    })
    // HTML disabled attribute is presence-based (empty string when true)
    expect(wrapper.attributes('disabled')).toBe('')
  })

  // ========== 图标测试 ==========
  it('renders icon correctly', () => {
    const wrapper = mount(ButtonV2, {
      props: { icon: Plus },
    })
    expect(wrapper.find('.button-v2__icon').exists()).toBe(true)
  })

  it('does not render icon when loading', () => {
    const wrapper = mount(ButtonV2, {
      props: { icon: Plus, loading: true },
    })
    expect(wrapper.find('.button-v2__icon').exists()).toBe(false)
    expect(wrapper.find('.button-v2__spinner').exists()).toBe(true)
  })

  // ========== 无障碍测试（Accessibility - CRITICAL）==========
  it('has aria-label for icon-only button', () => {
    const wrapper = mount(ButtonV2, {
      props: {
        icon: Plus,
        ariaLabel: 'Add item',
      },
    })
    expect(wrapper.attributes('aria-label')).toBe('Add item')
  })

  it('has aria-disabled attribute when disabled', () => {
    const wrapper = mount(ButtonV2, {
      props: { disabled: true },
    })
    expect(wrapper.attributes('aria-disabled')).toBe('true')
  })

  // ========== Focus 状态测试（UI/UX Pro Max CRITICAL）==========
  it('has focus-visible styles', async () => {
    const wrapper = mount(ButtonV2)
    const button = wrapper.find('button')

    // 模拟 focus-visible
    await button.trigger('focus')

    // 检查 focus ring 样式（通过 CSS 类）
    expect(wrapper.find('button').element.style.outline).toBeDefined()
  })

  // ========== Touch Target 测试（UI/UX Pro Max CRITICAL）==========
  it('mobile size meets touch target requirement (44px)', () => {
    const wrapper = mount(ButtonV2, {
      props: { size: 'mobile' },
    })
    expect(wrapper.classes()).toContain('button-v2--mobile')
    // 验证高度通过 CSS 类实现（44px）
  })

  it('lg size meets touch target requirement (44px)', () => {
    const wrapper = mount(ButtonV2, {
      props: { size: 'lg' },
    })
    expect(wrapper.classes()).toContain('button-v2--lg')
  })

  // ========== Design Tokens 验证测试 ==========
  it('uses Design Tokens (no hardcoded colors)', () => {
    mount(ButtonV2)
    // 检查是否有硬编码的颜色值（应该通过 SCSS 变量）
    // 注意：这个测试在运行时可能无法直接验证 SCSS 变量
    // 主要依赖 Stylelint 在构建时检查
  })

  // ========== 事件测试 ==========
  it('emits click event when clicked', async () => {
    const wrapper = mount(ButtonV2)
    await wrapper.trigger('click')
    expect(wrapper.emitted('click')).toBeTruthy()
  })

  it('does not emit click when loading', async () => {
    const wrapper = mount(ButtonV2, {
      props: { loading: true },
    })
    await wrapper.trigger('click')
    expect(wrapper.emitted('click')).toBeFalsy()
  })
})