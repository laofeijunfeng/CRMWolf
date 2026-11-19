/**
 * Focus Ring Accessibility Tests
 * UI/UX Pro Max CRITICAL §1: Focus States 2-4px visible
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TouchInput from '@/components/crmwolf/TouchInput.vue'

describe('Focus Ring Compliance (UI/UX Pro Max §1)', () => {
  describe('TouchInput', () => {
    it('shows focus ring on focus', async () => {
      const wrapper = mount(TouchInput, {
        props: { label: 'Focus Test' },
        attachTo: document.body,
      })

      const input = wrapper.find('input')
      await input.trigger('focus')

      const inputWrapper = wrapper.find('.input-wrapper')
      expect(inputWrapper.classes()).toContain('focus-ring')

      wrapper.unmount()
    })

    it('error state uses danger focus ring color', async () => {
      const wrapper = mount(TouchInput, {
        props: {
          label: 'Error',
          error: 'Required field',
        },
        attachTo: document.body,
      })

      const input = wrapper.find('input')
      await input.trigger('focus')

      const inputWrapper = wrapper.find('.input-wrapper')
      expect(inputWrapper.classes()).toContain('border-wolf-danger')

      wrapper.unmount()
    })
  })
})
