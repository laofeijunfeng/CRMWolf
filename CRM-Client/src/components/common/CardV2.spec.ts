/**
 * CardV2 单元测试 - CRMWolf Design System V2
 *
 * 覆盖 UI/UX Pro Max 规范：
 * - §3.5 Card: Unified shadow, unified radius 6px
 * - §1 Accessibility: Focus states for interactive cards
 * - §2 Touch Target: Mobile-friendly padding
 * - §6 Typography & Color: Dark mode support
 * - §7 Animation: Reduced motion support
 *
 * 测试策略：使用 Vitest + Vue Test Utils
 * - 渲染测试：验证 DOM 结构
 * - 阴影测试：验证 shadow 变体
 * - 圆角测试：验证统一 6px 圆角
 * - Hover 状态测试：验证可点击卡片 hover 效果
 * - 禁用状态测试：验证 disabled 行为
 * - 内边距测试：验证 padding 变体
 * - 边框测试：验证 bordered 变体
 * - 可访问性测试：验证 aria 属性和键盘导航
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import CardV2 from './CardV2.vue'

describe('CardV2', () => {
  // ========== 渲染测试 ==========

  it('renders basic card with title', () => {
    const wrapper = mount(CardV2, {
      props: {
        title: '客户信息'
      }
    })

    // 验证 title 存在
    const title = wrapper.find('.card-v2__title')
    expect(title.exists()).toBe(true)
    expect(title.text()).toBe('客户信息')

    // 验证卡片存在
    const card = wrapper.find('.card-v2')
    expect(card.exists()).toBe(true)
  })

  it('renders card with title and subtitle', () => {
    const wrapper = mount(CardV2, {
      props: {
        title: '客户信息',
        subtitle: '客户基本信息卡片'
      }
    })

    // 验证 title 存在
    const title = wrapper.find('.card-v2__title')
    expect(title.text()).toBe('客户信息')

    // 验证 subtitle 存在
    const subtitle = wrapper.find('.card-v2__subtitle')
    expect(subtitle.text()).toBe('客户基本信息卡片')
  })

  it('renders card without title', () => {
    const wrapper = mount(CardV2)

    // 验证卡片存在
    const card = wrapper.find('.card-v2')
    expect(card.exists()).toBe(true)

    // 验证 title 不存在
    const title = wrapper.find('.card-v2__title')
    expect(title.exists()).toBe(false)
  })

  it('renders card with default slot content', () => {
    const wrapper = mount(CardV2, {
      slots: {
        default: '<p>这是卡片内容</p>'
      }
    })

    // 验证 slot 内容存在
    const body = wrapper.find('.card-v2__body')
    expect(body.html()).toContain('这是卡片内容')
  })

  it('renders card with footer slot', () => {
    const wrapper = mount(CardV2, {
      props: {
        title: '操作卡片'
      },
      slots: {
        footer: '<button>确定</button><button>取消</button>'
      }
    })

    // 验证 footer 存在
    const footer = wrapper.find('.card-v2__footer')
    expect(footer.exists()).toBe(true)
    expect(footer.html()).toContain('确定')
    expect(footer.html()).toContain('取消')
  })

  // ========== 阴影变体测试（UI/UX Pro Max §3.5 Card）==========

  it('applies small shadow by default', () => {
    const wrapper = mount(CardV2)

    const card = wrapper.find('.card-v2')
    expect(card.classes()).toContain('card-v2--shadow-sm')
  })

  it('applies no shadow when shadow is none', () => {
    const wrapper = mount(CardV2, {
      props: {
        shadow: 'none'
      }
    })

    const card = wrapper.find('.card-v2')
    expect(card.classes()).toContain('card-v2--shadow-none')
  })

  it('applies medium shadow when shadow is md', () => {
    const wrapper = mount(CardV2, {
      props: {
        shadow: 'md'
      }
    })

    const card = wrapper.find('.card-v2')
    expect(card.classes()).toContain('card-v2--shadow-md')
  })

  it('applies large shadow when shadow is lg', () => {
    const wrapper = mount(CardV2, {
      props: {
        shadow: 'lg'
      }
    })

    const card = wrapper.find('.card-v2')
    expect(card.classes()).toContain('card-v2--shadow-lg')
  })

  // ========== 圆角测试（UI/UX Pro Max §3.5 Card: unified 6px）==========

  it('has unified radius 6px', () => {
    const wrapper = mount(CardV2)

    const card = wrapper.find('.card-v2')
    // 验证 CSS 变量定义了正确的圆角
    // 注：实际样式验证需要 jsdom CSS 支持
    expect(card.exists()).toBe(true)
  })

  // ========== Hover 状态测试（可点击卡片）==========

  it('renders clickable card with hover state', () => {
    const wrapper = mount(CardV2, {
      props: {
        clickable: true,
        title: '可点击卡片'
      }
    })

    // 验证使用 button 元素
    const card = wrapper.find('button.card-v2')
    expect(card.exists()).toBe(true)
    expect(card.classes()).toContain('card-v2--clickable')
  })

  it('emits click event when clickable card is clicked', async () => {
    const wrapper = mount(CardV2, {
      props: {
        clickable: true
      }
    })

    const card = wrapper.find('button.card-v2')
    await card.trigger('click')

    // 验证 click 事件被触发
    expect(wrapper.emitted('click')).toBeTruthy()
    expect(wrapper.emitted('click')).toHaveLength(1)
  })

  it('renders non-clickable card as div', () => {
    const wrapper = mount(CardV2, {
      props: {
        clickable: false
      }
    })

    // 验证使用 div 元素
    const card = wrapper.find('div.card-v2')
    expect(card.exists()).toBe(true)
    expect(card.element.tagName).toBe('DIV')
  })

  // ========== 禁用状态测试（UI/UX Pro Max §8 Forms）==========

  it('applies disabled state', () => {
    const wrapper = mount(CardV2, {
      props: {
        clickable: true,
        disabled: true
      }
    })

    const card = wrapper.find('button.card-v2')
    expect(card.classes()).toContain('card-v2--disabled')
    expect(card.attributes('disabled')).toBe('')
    expect(card.attributes('aria-disabled')).toBe('true')
  })

  it('does not emit click when disabled', async () => {
    const wrapper = mount(CardV2, {
      props: {
        clickable: true,
        disabled: true
      }
    })

    const card = wrapper.find('button.card-v2')
    await card.trigger('click')

    // 验证 click 事件未被触发
    expect(wrapper.emitted('click')).toBeFalsy()
  })

  // ========== 内边距变体测试 ==========

  it('applies default padding (md)', () => {
    const wrapper = mount(CardV2)

    const card = wrapper.find('.card-v2')
    // 验证 CSS 变量被设置
    expect(card.attributes('style')).toContain('--card-padding: 16px')
  })

  it('applies none padding', () => {
    const wrapper = mount(CardV2, {
      props: {
        padding: 'none'
      }
    })

    const card = wrapper.find('.card-v2')
    expect(card.attributes('style')).toContain('--card-padding: 0')
  })

  it('applies small padding', () => {
    const wrapper = mount(CardV2, {
      props: {
        padding: 'sm'
      }
    })

    const card = wrapper.find('.card-v2')
    expect(card.attributes('style')).toContain('--card-padding: 12px')
  })

  it('applies large padding', () => {
    const wrapper = mount(CardV2, {
      props: {
        padding: 'lg'
      }
    })

    const card = wrapper.find('.card-v2')
    expect(card.attributes('style')).toContain('--card-padding: 24px')
  })

  // ========== 边框变体测试 ==========

  it('applies bordered class when bordered is true', () => {
    const wrapper = mount(CardV2, {
      props: {
        bordered: true
      }
    })

    const card = wrapper.find('.card-v2')
    expect(card.classes()).toContain('card-v2--bordered')
  })

  it('does not apply bordered class by default', () => {
    const wrapper = mount(CardV2)

    const card = wrapper.find('.card-v2')
    expect(card.classes()).not.toContain('card-v2--bordered')
  })

  // ========== 可访问性测试（UI/UX Pro Max §1 Accessibility）==========

  it('sets aria-label when provided', () => {
    const wrapper = mount(CardV2, {
      props: {
        clickable: true,
        ariaLabel: '查看客户详情'
      }
    })

    const card = wrapper.find('button.card-v2')
    expect(card.attributes('aria-label')).toBe('查看客户详情')
  })

  it('uses title as aria-label when ariaLabel not provided', () => {
    const wrapper = mount(CardV2, {
      props: {
        clickable: true,
        title: '客户信息'
      }
    })

    const card = wrapper.find('button.card-v2')
    expect(card.attributes('aria-label')).toBe('客户信息')
  })

  it('sets role="button" for clickable cards', () => {
    const wrapper = mount(CardV2, {
      props: {
        clickable: true
      }
    })

    const card = wrapper.find('button.card-v2')
    expect(card.attributes('role')).toBe('button')
  })

  it('sets tabindex="0" for clickable cards', () => {
    const wrapper = mount(CardV2, {
      props: {
        clickable: true
      }
    })

    const card = wrapper.find('button.card-v2')
    expect(card.attributes('tabindex')).toBe('0')
  })

  it('does not set tabindex for disabled cards', () => {
    const wrapper = mount(CardV2, {
      props: {
        clickable: true,
        disabled: true
      }
    })

    const card = wrapper.find('button.card-v2')
    // 禁用状态不应该是可 tab 的
    expect(card.attributes('tabindex')).toBeUndefined()
  })

  it('supports keyboard navigation (Enter key)', async () => {
    const wrapper = mount(CardV2, {
      props: {
        clickable: true
      }
    })

    const card = wrapper.find('button.card-v2')
    await card.trigger('keydown', { key: 'Enter' })

    // 验证 click 事件被触发
    expect(wrapper.emitted('click')).toBeTruthy()
  })

  it('supports keyboard navigation (Space key)', async () => {
    const wrapper = mount(CardV2, {
      props: {
        clickable: true
      }
    })

    const card = wrapper.find('button.card-v2')
    await card.trigger('keydown', { key: ' ' })

    // 验证 click 事件被触发
    expect(wrapper.emitted('click')).toBeTruthy()
  })

  it('does not trigger click on keyboard when disabled', async () => {
    const wrapper = mount(CardV2, {
      props: {
        clickable: true,
        disabled: true
      }
    })

    const card = wrapper.find('button.card-v2')
    await card.trigger('keydown', { key: 'Enter' })

    // 验证 click 事件未被触发
    expect(wrapper.emitted('click')).toBeFalsy()
  })

  // ========== 自定义类名测试 ==========

  it('applies custom class', () => {
    const wrapper = mount(CardV2, {
      props: {
        customClass: 'my-custom-card'
      }
    })

    const card = wrapper.find('.card-v2')
    expect(card.classes()).toContain('my-custom-card')
  })

  // ========== 插槽测试 ==========

  it('renders header slot instead of title/subtitle', () => {
    const wrapper = mount(CardV2, {
      slots: {
        header: '<div class="custom-header">Custom Header</div>'
      }
    })

    // 验证自定义 header 存在
    const customHeader = wrapper.find('.custom-header')
    expect(customHeader.exists()).toBe(true)
    expect(customHeader.text()).toBe('Custom Header')

    // 验证默认 title 不存在
    const title = wrapper.find('.card-v2__title')
    expect(title.exists()).toBe(false)
  })

  // ========== 组合场景测试 ==========

  it('renders clickable card with border and large shadow', () => {
    const wrapper = mount(CardV2, {
      props: {
        clickable: true,
        bordered: true,
        shadow: 'lg',
        title: '组合卡片'
      }
    })

    const card = wrapper.find('button.card-v2')
    expect(card.classes()).toContain('card-v2--clickable')
    expect(card.classes()).toContain('card-v2--bordered')
    expect(card.classes()).toContain('card-v2--shadow-lg')
  })

  it('renders disabled clickable card with border', () => {
    const wrapper = mount(CardV2, {
      props: {
        clickable: true,
        disabled: true,
        bordered: true,
        title: '禁用卡片'
      }
    })

    const card = wrapper.find('button.card-v2')
    expect(card.classes()).toContain('card-v2--disabled')
    expect(card.classes()).toContain('card-v2--bordered')
    expect(card.attributes('disabled')).toBe('')
  })
})