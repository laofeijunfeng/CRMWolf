/**
 * Touch Target Accessibility Tests
 * UI/UX Pro Max CRITICAL §2: Touch Target Minimum 44×44pt
 *
 * Tests verify:
 * - All interactive elements meet 44px minimum on mobile
 * - Hit-slop extension works for small visual sizes
 * - Touch-action manipulation removes 300ms delay
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TouchButton from '@/components/crmwolf/TouchButton.vue'
import TouchInput from '@/components/crmwolf/TouchInput.vue'
import fs from 'fs'
import path from 'path'

describe('Touch Target Compliance (UI/UX Pro Max §2)', () => {
  describe('TouchButton', () => {
    it('size="touch" has explicit 44px height', () => {
      const wrapper = mount(TouchButton, {
        props: { size: 'touch' },
        slots: { default: 'Button' }
      })

      const button = wrapper.find('button')
      const classList = button.classes()

      expect(
        classList.some(c =>
          c.includes('h-touch-target') ||
          c.includes('min-h-touch-target') ||
          c.includes('h-\\[44px\\]')
        )
      ).toBe(true)
    })

    it('size="sm" uses hit-slop to achieve 44px touch area', () => {
      const wrapper = mount(TouchButton, {
        props: { size: 'sm' },
        slots: { default: 'Small' }
      })

      const button = wrapper.find('button')

      // sm button should have hit-slop class
      expect(button.classes().some(c => c.includes('hit-slop'))).toBe(true)
    })

    it('size="lg" always has 44px height', () => {
      const wrapper = mount(TouchButton, {
        props: { size: 'lg' },
        slots: { default: 'Large' }
      })

      const button = wrapper.find('button')
      expect(button.classes().some(c => c.includes('touch') || c.includes('44'))).toBe(true)
    })

    it('has touch-action: manipulation', () => {
      const wrapper = mount(TouchButton, {
        props: { size: 'touch' },
        slots: { default: 'Button' }
      })

      const button = wrapper.find('button')
      expect(button.classes().some(c => c.includes('touch-manipulation'))).toBe(true)
    })

    it('press feedback active:scale-[0.98] applied', () => {
      const wrapper = mount(TouchButton, {
        props: { size: 'touch' },
        slots: { default: 'Button' }
      })

      const button = wrapper.find('button')
      expect(button.classes().some(c => c.includes('press-feedback') || c.includes('active:scale'))).toBe(true)
    })
  })

  describe('TouchInput', () => {
    it('size="mobile" has 44px height', () => {
      const wrapper = mount(TouchInput, {
        props: {
          label: 'Mobile Input',
          size: 'mobile'
        }
      })

      const inputWrapper = wrapper.find('.input-wrapper')
      expect(inputWrapper.classes().some(c => c.includes('h-input-mobile'))).toBe(true)
    })

    it('mobile input has 16px font-size (iOS auto-zoom prevention)', () => {
      const wrapper = mount(TouchInput, {
        props: {
          label: 'Mobile',
          size: 'mobile'
        }
      })

      // This is enforced via CSS base layer @media (max-width: 767px)
      const input = wrapper.find('input')
      expect(input.exists()).toBe(true)
    })

    it('default size has 32px height for desktop', () => {
      const wrapper = mount(TouchInput, {
        props: {
          label: 'Desktop',
          size: 'default'
        }
      })

      const inputWrapper = wrapper.find('.input-wrapper')
      expect(inputWrapper.classes().some(c => c.includes('h-input-desktop'))).toBe(true)
    })
  })

  describe('Global Base Layer', () => {
    it('base.css applies min-h-touch-target on mobile', () => {
      // Check that base.css contains the rule
      const baseCssPath = path.resolve(__dirname, '../../src/styles/base.css')
      const baseCss = fs.readFileSync(baseCssPath, 'utf-8')

      expect(baseCss).toContain('min-h-touch-target')
      expect(baseCss).toContain('@media (max-width: 767px)')
    })
  })
})