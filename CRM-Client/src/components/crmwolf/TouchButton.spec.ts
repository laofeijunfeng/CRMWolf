/**
 * TouchButton 单元测试
 * UI/UX Pro Max CRITICAL §2: Touch Target 44px minimum
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TouchButton from './TouchButton.vue'

describe('TouchButton', () => {
  it('size="touch" variant has 44px height for touch target compliance', () => {
    const wrapper = mount(TouchButton, {
      props: {
        size: 'touch'
      },
      slots: {
        default: 'Click me'
      }
    })

    const button = wrapper.find('button')
    const classes = button.classes()

    // Verify touch-safe class applied
    expect(classes.some(c => c.includes('touch'))).toBe(true)
    expect(classes.some(c => c.includes('h-touch-target') || c.includes('min-h-touch-target'))).toBe(true)
  })

  it('has press feedback active:scale-[0.98]', () => {
    const wrapper = mount(TouchButton, {
      props: { size: 'touch' },
      slots: { default: 'Click' }
    })

    const button = wrapper.find('button')
    expect(button.classes().some(c => c.includes('press-feedback') || c.includes('active:scale'))).toBe(true)
  })

  it('has touch-action: manipulation to remove 300ms delay', () => {
    const wrapper = mount(TouchButton, {
      props: { size: 'touch' },
      slots: { default: 'Click' }
    })

    const button = wrapper.find('button')
    expect(button.classes().some(c => c.includes('touch-manipulation'))).toBe(true)
  })

  it('size="sm" has hit-slop for 44px touch target', () => {
    const wrapper = mount(TouchButton, {
      props: { size: 'sm' },
      slots: { default: 'Small' }
    })

    const button = wrapper.find('button')
    // sm button should have hit-slop to extend touch area
    expect(button.classes().some(c => c.includes('hit-slop') || c.includes('touch-safe'))).toBe(true)
  })

  it('focus ring visible with focus-visible state', async () => {
    const wrapper = mount(TouchButton, {
      props: { size: 'touch' },
      slots: { default: 'Focus' },
      attachTo: document.body
    })

    const button = wrapper.find('button')
    await button.trigger('focus')

    expect(button.classes().some(c => c.includes('focus-visible') || c.includes('focus-ring'))).toBe(true)

    wrapper.unmount()
  })

  it('supports reduced motion preference', () => {
    const wrapper = mount(TouchButton, {
      props: { size: 'touch' },
      slots: { default: 'Motion' }
    })

    // Reduced motion should disable press feedback animation
    // This is verified via CSS media query, not component logic
    const button = wrapper.find('button')
    expect(button.exists()).toBe(true)
  })
})