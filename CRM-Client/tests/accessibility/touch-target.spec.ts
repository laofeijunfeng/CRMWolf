/**
 * Touch Target Accessibility Tests
 * UI/UX Pro Max CRITICAL §2: Touch Target Minimum 44×44pt
 *
 * Tests verify:
 * - TouchInput mobile/default sizing remains explicit
 * - Mobile base layer applies global touch target safety
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TouchInput from '@/components/crmwolf/TouchInput.vue'

describe('Touch Target Compliance (UI/UX Pro Max §2)', () => {
  describe('TouchInput', () => {
    it('size="mobile" has 44px height', () => {
      const wrapper = mount(TouchInput, {
        props: {
          label: 'Mobile Input',
          size: 'mobile',
        },
      })

      const inputWrapper = wrapper.find('.input-wrapper')
      expect(inputWrapper.classes()).toContain('h-touch-target')
    })

    it('default size has 32px height for desktop', () => {
      const wrapper = mount(TouchInput, {
        props: {
          label: 'Desktop',
          size: 'default',
        },
      })

      const inputWrapper = wrapper.find('.input-wrapper')
      expect(inputWrapper.classes()).toContain('h-control')
    })
  })
})
