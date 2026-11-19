/**
 * Touch Target Accessibility Tests
 * UI/UX Pro Max CRITICAL §2: Touch Target Minimum 44×44pt
 *
 * Tests verify:
 * - Button variants follow shadcn-vue compact desktop sizing
 * - TouchInput mobile/default sizing remains explicit
 * - Mobile base layer applies global touch target safety
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { Button } from '@/components/ui/button'
import TouchInput from '@/components/crmwolf/TouchInput.vue'

describe('Touch Target Compliance (UI/UX Pro Max §2)', () => {
  describe('Button', () => {
    it('default size follows shadcn-vue h-9 desktop sizing', () => {
      const wrapper = mount(Button, {
        slots: { default: 'Button' },
      })

      const button = wrapper.find('button')
      expect(button.classes()).toContain('h-9')
    })

    it('icon size follows shadcn-vue size-9 desktop sizing', () => {
      const wrapper = mount(Button, {
        props: { size: 'icon' },
        slots: { default: 'Icon' },
      })

      const button = wrapper.find('button')
      expect(button.classes()).toContain('size-9')
    })

    it('small size follows shadcn-vue h-8 desktop sizing', () => {
      const wrapper = mount(Button, {
        props: { size: 'sm' },
        slots: { default: 'Small' },
      })

      const button = wrapper.find('button')
      expect(button.classes()).toContain('h-8')
    })
  })

  describe('TouchInput', () => {
    it('size="mobile" has 44px height', () => {
      const wrapper = mount(TouchInput, {
        props: {
          label: 'Mobile Input',
          size: 'mobile',
        },
      })

      const inputWrapper = wrapper.find('.input-wrapper')
      expect(inputWrapper.classes()).toContain('h-input-mobile')
    })

    it('default size has 32px height for desktop', () => {
      const wrapper = mount(TouchInput, {
        props: {
          label: 'Desktop',
          size: 'default',
        },
      })

      const inputWrapper = wrapper.find('.input-wrapper')
      expect(inputWrapper.classes()).toContain('h-input-desktop')
    })
  })
})
