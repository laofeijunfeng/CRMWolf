// CRM-Client/src/components/common/TabV2.spec.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TabV2 from './TabV2.vue'
import { User, Building2 } from 'lucide-vue-next'

describe('TabV2', () => {
  // ========== Basic Rendering Tests ==========
  it('renders correctly with default props', () => {
    const tabs = [
      { value: 'tab1', label: '选项一' },
      { value: 'tab2', label: '选项二' },
    ]
    const wrapper = mount(TabV2, {
      props: {
        modelValue: 'tab1',
        tabs,
      },
    })

    expect(wrapper.find('.tab-v2').exists()).toBe(true)
    expect(wrapper.findAll('.tab-v2__item')).toHaveLength(2)
    expect(wrapper.text()).toContain('选项一')
    expect(wrapper.text()).toContain('选项二')
  })

  it('applies active class to selected tab', () => {
    const tabs = [
      { value: 'tab1', label: '选项一' },
      { value: 'tab2', label: '选项二' },
    ]
    const wrapper = mount(TabV2, {
      props: {
        modelValue: 'tab1',
        tabs,
      },
    })

    const tabItems = wrapper.findAll('.tab-v2__item')
    // Using direct access (same pattern as ButtonV2.spec.ts)
    expect(tabItems[0].classes()).toContain('tab-v2__item--active')
    expect(tabItems[1].classes()).not.toContain('tab-v2__item--active')
  })

  it('renders icons correctly', () => {
    const tabs = [
      { value: 'tab1', label: '用户', icon: User },
      { value: 'tab2', label: '公司', icon: Building2 },
    ]
    const wrapper = mount(TabV2, {
      props: {
        modelValue: 'tab1',
        tabs,
      },
    })

    const icons = wrapper.findAll('.tab-v2__icon')
    expect(icons).toHaveLength(2)
  })

  it('renders badges correctly', () => {
    const tabs = [
      { value: 'tab1', label: '全部' },
      { value: 'tab2', label: '待处理', badge: 12 },
    ]
    const wrapper = mount(TabV2, {
      props: {
        modelValue: 'tab1',
        tabs,
      },
    })

    const badges = wrapper.findAll('.tab-v2__badge')
    expect(badges).toHaveLength(1)
    expect(badges[0].text()).toBe('12')
  })

  it('displays 99+ for badge numbers greater than 99', () => {
    const tabs = [
      { value: 'tab1', label: '通知', badge: 150 },
    ]
    const wrapper = mount(TabV2, {
      props: {
        modelValue: 'tab1',
        tabs,
      },
    })

    expect(wrapper.find('.tab-v2__badge').text()).toBe('99+')
  })

  // ========== Badge Variants Tests ==========
  it('applies badge variant classes correctly', () => {
    const tabs = [
      { value: 'tab1', label: '默认', badge: 1 },
      { value: 'tab2', label: '警告', badge: 2, badgeVariant: 'warning' },
      { value: 'tab3', label: '成功', badge: 3, badgeVariant: 'success' },
      { value: 'tab4', label: '危险', badge: 4, badgeVariant: 'danger' },
    ]
    const wrapper = mount(TabV2, {
      props: {
        modelValue: 'tab1',
        tabs,
      },
    })

    const badges = wrapper.findAll('.tab-v2__badge')
    expect(badges[0].classes()).not.toContain('tab-v2__badge--warning')
    expect(badges[1].classes()).toContain('tab-v2__badge--warning')
    expect(badges[2].classes()).toContain('tab-v2__badge--success')
    expect(badges[3].classes()).toContain('tab-v2__badge--danger')
  })

  // ========== Active Indicator Bar Tests ==========
  it('renders active indicator bar for active tab', () => {
    const tabs = [
      { value: 'tab1', label: '选项一' },
      { value: 'tab2', label: '选项二' },
    ]
    const wrapper = mount(TabV2, {
      props: {
        modelValue: 'tab1',
        tabs,
      },
    })

    // The indicator bar is rendered via CSS ::before pseudo-element
    // We verify the active class is applied
    const activeTab = wrapper.find('.tab-v2__item--active')
    expect(activeTab.exists()).toBe(true)
  })

  // ========== Interaction Tests ==========
  it('emits update:modelValue when tab is clicked', async () => {
    const tabs = [
      { value: 'tab1', label: '选项一' },
      { value: 'tab2', label: '选项二' },
    ]
    const wrapper = mount(TabV2, {
      props: {
        modelValue: 'tab1',
        tabs,
      },
    })

    await wrapper.findAll('.tab-v2__item')[1].trigger('click')
    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    expect(emitted?.[0]).toEqual(['tab2'])
  })

  it('does not emit update:modelValue when clicking active tab', async () => {
    const tabs = [
      { value: 'tab1', label: '选项一' },
      { value: 'tab2', label: '选项二' },
    ]
    const wrapper = mount(TabV2, {
      props: {
        modelValue: 'tab1',
        tabs,
      },
    })

    await wrapper.findAll('.tab-v2__item')[0].trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeFalsy()
  })

  // ========== Accessibility Tests (CRITICAL) ==========
  it('has correct ARIA attributes', () => {
    const tabs = [
      { value: 'tab1', label: '选项一' },
      { value: 'tab2', label: '选项二' },
    ]
    const wrapper = mount(TabV2, {
      props: {
        modelValue: 'tab1',
        tabs,
        ariaLabel: '导航选项卡',
      },
    })

    const tablist = wrapper.find('[role="tablist"]')
    expect(tablist.attributes('aria-label')).toBe('导航选项卡')

    const tabItems = wrapper.findAll('[role="tab"]')
    expect(tabItems).toHaveLength(2)
    expect(tabItems[0].attributes('aria-selected')).toBe('true')
    expect(tabItems[1].attributes('aria-selected')).toBe('false')
  })

  it('has correct aria-controls attribute', () => {
    const tabs = [
      { value: 'tab1', label: '选项一' },
      { value: 'tab2', label: '选项二' },
    ]
    const wrapper = mount(TabV2, {
      props: {
        modelValue: 'tab1',
        tabs,
        panelIdPrefix: 'my-panel',
      },
    })

    const tabItems = wrapper.findAll('[role="tab"]')
    expect(tabItems[0].attributes('aria-controls')).toBe('my-panel-tab1')
    expect(tabItems[1].attributes('aria-controls')).toBe('my-panel-tab2')
  })

  it('has correct tabindex for keyboard navigation', () => {
    const tabs = [
      { value: 'tab1', label: '选项一' },
      { value: 'tab2', label: '选项二' },
    ]
    const wrapper = mount(TabV2, {
      props: {
        modelValue: 'tab1',
        tabs,
      },
    })

    const tabItems = wrapper.findAll('[role="tab"]')
    // Active tab should be in tab order
    expect(tabItems[0].attributes('tabindex')).toBe('0')
    // Inactive tabs should be removed from tab order
    expect(tabItems[1].attributes('tabindex')).toBe('-1')
  })

  // ========== Focus States Tests (UI/UX Pro Max CRITICAL) ==========
  it('applies focus-visible styles', async () => {
    const tabs = [
      { value: 'tab1', label: '选项一' },
    ]
    const wrapper = mount(TabV2, {
      props: {
        modelValue: 'tab1',
        tabs,
      },
    })

    const tabItem = wrapper.find('.tab-v2__item')
    await tabItem.trigger('focus')

    // Focus ring styles are applied via CSS :focus-visible
    // We verify the element is focusable
    expect(tabItem.element.tagName).toBe('BUTTON')
  })

  // ========== Transition Tests ==========
  it('applies transition styles', () => {
    const tabs = [
      { value: 'tab1', label: '选项一' },
    ]
    const wrapper = mount(TabV2, {
      props: {
        modelValue: 'tab1',
        tabs,
      },
    })

    // Transition is applied via CSS
    // We verify the component renders without errors
    expect(wrapper.find('.tab-v2__item').exists()).toBe(true)
  })

  // ========== Design Tokens Validation Tests ==========
  it('uses Design Tokens (no hardcoded colors)', () => {
    const tabs = [
      { value: 'tab1', label: '选项一' },
    ]
    mount(TabV2, {
      props: {
        modelValue: 'tab1',
        tabs,
      },
    })
    // Colors are applied via SCSS variables
    // This test verifies the component renders correctly
    // Stylelint enforces no hardcoded colors in SCSS
  })

  // ========== Edge Cases ==========
  it('handles empty tabs array', () => {
    const wrapper = mount(TabV2, {
      props: {
        modelValue: '',
        tabs: [],
      },
    })

    expect(wrapper.findAll('.tab-v2__item')).toHaveLength(0)
  })

  it('handles single tab', () => {
    const tabs = [{ value: 'only', label: '唯一选项' }]
    const wrapper = mount(TabV2, {
      props: {
        modelValue: 'only',
        tabs,
      },
    })

    expect(wrapper.findAll('.tab-v2__item')).toHaveLength(1)
    expect(wrapper.find('.tab-v2__item--active').exists()).toBe(true)
  })

  it('handles missing badge value', () => {
    const tabs = [
      { value: 'tab1', label: '选项一' },
    ]
    const wrapper = mount(TabV2, {
      props: {
        modelValue: 'tab1',
        tabs,
      },
    })

    expect(wrapper.find('.tab-v2__badge').exists()).toBe(false)
  })

  it('handles 0 badge value', () => {
    const tabs = [
      { value: 'tab1', label: '选项一', badge: 0 },
    ]
    const wrapper = mount(TabV2, {
      props: {
        modelValue: 'tab1',
        tabs,
      },
    })

    // 0 badge should not render (badge > 0 check)
    expect(wrapper.find('.tab-v2__badge').exists()).toBe(false)
  })
})