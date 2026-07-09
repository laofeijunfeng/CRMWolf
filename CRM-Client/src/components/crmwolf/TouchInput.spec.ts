/**
 * TouchInput 单元测试
 * UI/UX Pro Max CRITICAL: §1 Focus, §2 Touch Target, §8 Forms
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TouchInput from './TouchInput.vue'

describe('TouchInput', () => {
  // Touch Target Tests
  it('mobile size has 44px height for touch target', () => {
    const wrapper = mount(TouchInput, {
      props: {
        label: 'Username',
        size: 'mobile'
      }
    })

    const inputWrapper = wrapper.find('.input-wrapper')
    expect(inputWrapper.classes().some(c => c.includes('h-input-mobile') || c.includes('h-touch-target'))).toBe(true)
  })

  // Focus Ring Tests
  it('has visible focus ring on focus', async () => {
    const wrapper = mount(TouchInput, {
      props: { label: 'Focus Test' },
      attachTo: document.body
    })

    const input = wrapper.find('input')
    await input.trigger('focus')

    expect(input.classes().some(c => c.includes('focus-visible') || c.includes('focus-ring'))).toBe(true)

    wrapper.unmount()
  })

  // Visible Label Tests (§8 Forms)
  it('label is always visible, not just placeholder', () => {
    const wrapper = mount(TouchInput, {
      props: {
        label: 'Visible Label',
        placeholder: 'Placeholder hint'
      }
    })

    const label = wrapper.find('label')
    expect(label.exists()).toBe(true)
    expect(label.isVisible()).toBe(true)
    expect(label.text()).toBe('Visible Label')
  })

  it('required field shows required marker', () => {
    const wrapper = mount(TouchInput, {
      props: {
        label: 'Required',
        required: true
      }
    })

    const requiredMark = wrapper.find('.required-mark')
    expect(requiredMark.exists()).toBe(true)
  })

  // Error Placement Tests (§8 Forms)
  it('error message appears below input field', () => {
    const wrapper = mount(TouchInput, {
      props: {
        label: 'Error Test',
        error: 'This field is required'
      }
    })

    const error = wrapper.find('.error-message')
    expect(error.exists()).toBe(true)
    expect(error.text()).toContain('required')

    // Verify error is below input in DOM structure
    const container = wrapper.find('.touch-input-container')
    const children = Array.from(container.element.children)
    const inputWrapperIndex = children.findIndex(el => el.classList.contains('input-wrapper'))
    const errorIndex = children.findIndex(el => el.classList.contains('error-message'))
    expect(errorIndex).toBeGreaterThan(inputWrapperIndex)
  })

  it('error replaces helper text when both provided', () => {
    const wrapper = mount(TouchInput, {
      props: {
        label: 'Test',
        helperText: 'Helper hint',
        error: 'Error message'
      }
    })

    const helper = wrapper.find('.helper-text')
    expect(helper.exists()).toBe(false)

    const error = wrapper.find('.error-message')
    expect(error.exists()).toBe(true)
  })

  // Accessibility Tests
  it('has proper aria attributes', () => {
    const wrapper = mount(TouchInput, {
      props: {
        label: 'Aria Test',
        required: true,
        error: 'Error'
      }
    })

    const input = wrapper.find('input')
    expect(input.attributes('aria-invalid')).toBe('true')
    expect(input.attributes('aria-required')).toBe('true')
    expect(input.attributes('aria-describedby')).toBeDefined()
  })

  it('label for attribute matches input id', () => {
    const wrapper = mount(TouchInput, {
      props: { label: 'ID Test' }
    })

    const label = wrapper.find('label')
    const input = wrapper.find('input')
    expect(label.attributes('for')).toBe(input.attributes('id'))
  })
})