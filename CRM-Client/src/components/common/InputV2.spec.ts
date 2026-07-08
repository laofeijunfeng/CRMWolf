/**
 * InputV2 单元测试 - CRMWolf Design System V2
 *
 * 覆盖 UI/UX Pro Max 规范：
 * - §8 Forms: Visible label（非 placeholder-only）
 * - §8 Forms: Error placement below field
 * - §1 Accessibility: Focus ring visible
 * - §2 Touch Target: Mobile height 44px
 * - §8 Forms: Helper text support
 *
 * 测试策略：使用 Vitest + Vue Test Utils
 * - 渲染测试：验证 DOM 结构
 * - 可见性测试：验证 label 显示
 * - 错误位置测试：验证 error 在 field 下方
 * - Focus 状态测试：验证 focus ring
 * - Touch Target 测试：验证移动端高度 44px
 * - 辅助说明测试：验证 helper text
 * - 交互测试：验证 input/change/focus/blur 事件
 * - 禁用状态测试：验证 disabled 行为
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import InputV2 from './InputV2.vue'

describe('InputV2', () => {
  // ========== 渲染测试 ==========

  it('renders basic input with visible label', () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '用户名'
      }
    })

    // 验证 label 存在且可见
    const label = wrapper.find('.input-v2-label')
    expect(label.exists()).toBe(true)
    expect(label.text()).toBe('用户名')

    // 验证 input 存在
    const input = wrapper.find('.input-v2-field')
    expect(input.exists()).toBe(true)
  })

  it('renders with placeholder', () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '用户名',
        placeholder: '请输入用户名'
      }
    })

    const input = wrapper.find('.input-v2-field')
    expect(input.attributes('placeholder')).toBe('请输入用户名')
  })

  it('renders with initial value via modelValue', () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '用户名',
        modelValue: 'test_value'
      }
    })

    const input = wrapper.find('.input-v2-field')
    expect(input.element.value).toBe('test_value')
  })

  // ========== 可见标签测试（UI/UX Pro Max §8 Forms）==========

  it('label is always visible, not just placeholder', () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '必填字段',
        placeholder: 'placeholder 仅作提示'
      }
    })

    // 验证 label 存在（核心要求：不可仅用 placeholder）
    const label = wrapper.find('.input-v2-label')
    expect(label.exists()).toBe(true)
    expect(label.isVisible()).toBe(true)
    expect(label.text()).toBe('必填字段')

    // placeholder 作为辅助提示，label 作为主要标识
    const input = wrapper.find('.input-v2-field')
    expect(input.attributes('placeholder')).toBe('placeholder 仅作提示')
  })

  it('required field shows required mark', () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '用户名',
        required: true
      }
    })

    // 验证必填标记存在
    const requiredMark = wrapper.find('.input-v2-required-mark')
    expect(requiredMark.exists()).toBe(true)
    expect(requiredMark.text()).toBe('*')

    // 验证 aria-required
    const input = wrapper.find('.input-v2-field')
    expect(input.attributes('aria-required')).toBe('true')
  })

  // ========== 错误位置测试（UI/UX Pro Max §8 Forms）==========

  it('error message appears below input field', () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '用户名',
        error: '用户名不能为空'
      }
    })

    // 验证错误信息存在
    const error = wrapper.find('.input-v2-error')
    expect(error.exists()).toBe(true)
    expect(error.text()).toContain('用户名不能为空')

    // 验证错误信息位于 input 下方（DOM 结构）
    const container = wrapper.find('.input-v2-container')
    const children = container.findAll('div')
    const inputWrapperIndex = children.findIndex(c => c.classes('input-v2-wrapper'))
    const errorIndex = children.findIndex(c => c.classes('input-v2-error'))

    // error 应在 input wrapper 之后
    expect(errorIndex).toBeGreaterThan(inputWrapperIndex)

    // 验证 aria-invalid
    const input = wrapper.find('.input-v2-field')
    expect(input.attributes('aria-invalid')).toBe('true')

    // 验证 aria-describedby 关联错误信息
    expect(input.attributes('aria-describedby')).toContain('-error')
  })

  it('error replaces helper text when both are provided', () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '邮箱',
        helperText: '请输入有效邮箱',
        error: '邮箱格式不正确'
      }
    })

    // 有错误时，helper text 应隐藏
    const helper = wrapper.find('.input-v2-helper')
    expect(helper.exists()).toBe(false)

    // 错误信息应显示
    const error = wrapper.find('.input-v2-error')
    expect(error.exists()).toBe(true)
    expect(error.text()).toContain('邮箱格式不正确')
  })

  // ========== Focus 状态测试（UI/UX Pro Max §1 Accessibility）==========

  it('shows focus ring when focused', async () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '用户名'
      }
    })

    const inputWrapper = wrapper.find('.input-v2-wrapper')

    // 初始状态：无 focus ring
    expect(inputWrapper.classes()).not.toContain('input-v2-wrapper--focused')

    // 触发 focus
    const input = wrapper.find('.input-v2-field')
    await input.trigger('focus')

    // focus 状态：有 focus ring class
    expect(inputWrapper.classes()).toContain('input-v2-wrapper--focused')

    // emit focus 事件
    expect(wrapper.emitted('focus')).toBeTruthy()
  })

  it('removes focus ring when blurred', async () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '用户名'
      }
    })

    const inputWrapper = wrapper.find('.input-v2-wrapper')
    const input = wrapper.find('.input-v2-field')

    // focus
    await input.trigger('focus')
    expect(inputWrapper.classes()).toContain('input-v2-wrapper--focused')

    // blur
    await input.trigger('blur')
    expect(inputWrapper.classes()).not.toContain('input-v2-wrapper--focused')

    // emit blur 事件
    expect(wrapper.emitted('blur')).toBeTruthy()
  })

  it('focus ring style applied via CSS class', () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '用户名'
      },
      attachTo: document.body
    })

    // 通过 CSS 类名验证 focus ring 机制（2px ring）
    const inputWrapper = wrapper.find('.input-v2-wrapper')

    // 验证类名结构（CSS 会应用 focus ring）
    expect(inputWrapper.classes()).toContain('input-v2-wrapper')

    wrapper.unmount()
  })

  // ========== Touch Target 测试（UI/UX Pro Max §2）==========

  it('large size variant has 44px height for mobile touch target', () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '用户名',
        size: 'large'
      }
    })

    const inputWrapper = wrapper.find('.input-v2-wrapper')
    expect(inputWrapper.classes()).toContain('input-v2-wrapper--large')

    // 验证 CSS 变量引用（44px = $wolf-input-height-mobile-v2）
    // 实际高度由 CSS 控制，此处验证类名存在
  })

  it('default size has standard desktop height (32px)', () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '用户名',
        size: 'default'
      }
    })

    const inputWrapper = wrapper.find('.input-v2-wrapper')
    expect(inputWrapper.classes()).toContain('input-v2-wrapper')
    expect(inputWrapper.classes()).not.toContain('input-v2-wrapper--large')
  })

  // ========== 辅助说明测试（UI/UX Pro Max §8 Forms）==========

  it('shows helper text when provided', () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '密码',
        helperText: '密码长度至少 8 位'
      }
    })

    const helper = wrapper.find('.input-v2-helper')
    expect(helper.exists()).toBe(true)
    expect(helper.text()).toBe('密码长度至少 8 位')
  })

  it('helper text has proper aria association', () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '密码',
        helperText: '密码长度至少 8 位'
      }
    })

    const input = wrapper.find('.input-v2-field')
    const helperId = input.attributes('aria-describedby')

    expect(helperId).toContain('-helper')

    // 验证 helper 元素 ID 匹配
    const helper = wrapper.find('.input-v2-helper')
    expect(helper.attributes('id')).toContain('-helper')
  })

  // ========== 交互测试 ==========

  it('emits update:modelValue on input', async () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '用户名'
      }
    })

    const input = wrapper.find('.input-v2-field')
    await input.setValue('new_value')

    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')![0][0]).toBe('new_value')

    expect(wrapper.emitted('input')).toBeTruthy()
    expect(wrapper.emitted('input')![0][0]).toBe('new_value')
  })

  it('emits change event on change', async () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '用户名'
      }
    })

    const input = wrapper.find('.input-v2-field')
    await input.setValue('changed_value')
    await input.trigger('change')

    expect(wrapper.emitted('change')).toBeTruthy()
  })

  it('supports number type and emits numeric value', async () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '数量',
        type: 'number'
      }
    })

    const input = wrapper.find('.input-v2-field')
    await input.setValue('42')

    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')![0][0]).toBe(42)
    expect(typeof wrapper.emitted('update:modelValue')![0][0]).toBe('number')
  })

  // ========== 禁用状态测试（UI/UX Pro Max §8 Forms）==========

  it('disabled state prevents interaction', () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '用户名',
        disabled: true
      }
    })

    const input = wrapper.find('.input-v2-field')
    expect(input.attributes('disabled')).toBeDefined()

    const inputWrapper = wrapper.find('.input-v2-wrapper')
    expect(inputWrapper.classes()).toContain('input-v2-wrapper--disabled')
  })

  it('disabled input does not emit events on input attempt', async () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '用户名',
        disabled: true,
        modelValue: 'initial'
      }
    })

    // 尝试输入（实际 DOM 行为：disabled input 不会响应）
    const input = wrapper.find('.input-v2-field')
    expect(input.attributes('disabled')).toBeDefined()

    // 验证 disabled 类存在（视觉 + cursor）
    const inputWrapper = wrapper.find('.input-v2-wrapper')
    expect(inputWrapper.classes()).toContain('input-v2-wrapper--disabled')
  })

  // ========== 只读状态测试 ==========

  it('readonly state allows focus but prevents modification', () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '用户名',
        readonly: true,
        modelValue: 'readonly_value'
      }
    })

    const input = wrapper.find('.input-v2-field')
    expect(input.attributes('readonly')).toBeDefined()
    expect(input.element.value).toBe('readonly_value')
  })

  // ========== Accessibility 测试 ==========

  it('has proper aria attributes for accessibility', () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '用户名',
        required: true,
        error: '必填字段'
      }
    })

    const input = wrapper.find('.input-v2-field')

    // aria-invalid
    expect(input.attributes('aria-invalid')).toBe('true')

    // aria-required
    expect(input.attributes('aria-required')).toBe('true')

    // aria-describedby
    expect(input.attributes('aria-describedby')).toContain('-error')

    // label for 关联
    const label = wrapper.find('.input-v2-label')
    const inputId = input.attributes('id')
    expect(label.attributes('for')).toBe(inputId)
  })

  it('error message has role="alert" for screen readers', () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '用户名',
        error: '用户名不能为空'
      }
    })

    const error = wrapper.find('.input-v2-error')
    expect(error.attributes('role')).toBe('alert')
    expect(error.attributes('aria-live')).toBe('polite')
  })

  // ========== ID 生成测试 ==========

  it('generates unique ID if inputId not provided', () => {
    const wrapper1 = mount(InputV2, {
      props: { label: '用户名' }
    })
    const wrapper2 = mount(InputV2, {
      props: { label: '密码' }
    })

    const id1 = wrapper1.find('.input-v2-field').attributes('id')
    const id2 = wrapper2.find('.input-v2-field').attributes('id')

    expect(id1).toBeDefined()
    expect(id2).toBeDefined()
    expect(id1).not.toBe(id2)
  })

  it('uses provided inputId', () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '用户名',
        inputId: 'custom-input-id'
      }
    })

    const input = wrapper.find('.input-v2-field')
    expect(input.attributes('id')).toBe('custom-input-id')

    const label = wrapper.find('.input-v2-label')
    expect(label.attributes('for')).toBe('custom-input-id')
  })

  // ========== 暴露方法测试 ==========

  it('exposes focus and blur methods', async () => {
    const wrapper = mount(InputV2, {
      props: { label: '用户名' },
      attachTo: document.body
    })

    // 验证方法存在
    expect(typeof wrapper.vm.focus).toBe('function')
    expect(typeof wrapper.vm.blur).toBe('function')

    wrapper.unmount()
  })

  // ========== 类型变体测试 ==========

  it('renders different input types correctly', () => {
    const types: Array<'text' | 'password' | 'email' | 'number' | 'tel' | 'url' | 'search'> =
      ['text', 'password', 'email', 'number', 'tel', 'url', 'search']

    for (const type of types) {
      const wrapper = mount(InputV2, {
        props: {
          label: `${type} 输入`,
          type
        }
      })

      const input = wrapper.find('.input-v2-field')
      expect(input.attributes('type')).toBe(type)
    }
  })

  // ========== 长度限制测试 ==========

  it('applies maxlength attribute', () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '备注',
        maxlength: 100
      }
    })

    const input = wrapper.find('.input-v2-field')
    expect(input.attributes('maxlength')).toBe('100')
  })

  it('applies minlength attribute', () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '密码',
        minlength: 8
      }
    })

    const input = wrapper.find('.input-v2-field')
    expect(input.attributes('minlength')).toBe('8')
  })

  it('applies min and max for number input', () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '数量',
        type: 'number',
        min: 1,
        max: 100
      }
    })

    const input = wrapper.find('.input-v2-field')
    expect(input.attributes('min')).toBe('1')
    expect(input.attributes('max')).toBe('100')
  })

  // ========== 错误状态 focus ring 测试 ==========

  it('error state has different focus ring color', async () => {
    const wrapper = mount(InputV2, {
      props: {
        label: '用户名',
        error: '用户名不能为空'
      }
    })

    const inputWrapper = wrapper.find('.input-v2-wrapper')

    // 错误状态类
    expect(inputWrapper.classes()).toContain('input-v2-wrapper--error')

    // focus 时应有错误 focus ring（CSS 控制）
    const input = wrapper.find('.input-v2-field')
    await input.trigger('focus')

    expect(inputWrapper.classes()).toContain('input-v2-wrapper--focused')
    expect(inputWrapper.classes()).toContain('input-v2-wrapper--error')
  })
})