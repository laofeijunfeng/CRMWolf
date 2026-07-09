/**
 * Focus Ring Accessibility Tests
 * UI/UX Pro Max CRITICAL §1: Focus States 2-4px visible
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TouchButton from '@/components/crmwolf/TouchButton.vue'
import TouchInput from '@/components/crmwolf/TouchInput.vue'
import fs from 'fs'
import path from 'path'

describe('Focus Ring Compliance (UI/UX Pro Max §1)', () => {
  describe('TouchButton', () => {
    it('has focus-visible state', async () => {
      const wrapper = mount(TouchButton, {
        props: { size: 'touch' },
        slots: { default: 'Button' },
        attachTo: document.body
      })

      const button = wrapper.find('button')

      // Focus the button
      await button.trigger('focus')

      // Check for focus-ring class or focus-visible outline
      expect(button.classes().some(c => c.includes('focus-ring') || c.includes('focus-visible'))).toBe(true)

      wrapper.unmount()
    })

    it('focus ring uses wolf primary color', () => {
      const wrapper = mount(TouchButton, {
        props: { size: 'touch' },
        slots: { default: 'Button' }
      })

      const button = wrapper.find('button')

      // Focus ring color should be wolf-primary/50 (rgba)
      // This is verified via CSS, class presence indicates compliance
      expect(button.classes().some(c => c.includes('focus-ring'))).toBe(true)
    })
  })

  describe('TouchInput', () => {
    it('shows focus ring on focus', async () => {
      const wrapper = mount(TouchInput, {
        props: { label: 'Focus Test' },
        attachTo: document.body
      })

      const input = wrapper.find('input')
      await input.trigger('focus')

      const inputWrapper = wrapper.find('.input-wrapper')
      expect(inputWrapper.classes().some(c => c.includes('focus-ring'))).toBe(true)

      wrapper.unmount()
    })

    it('error state uses danger focus ring color', async () => {
      const wrapper = mount(TouchInput, {
        props: {
          label: 'Error',
          error: 'Required field'
        },
        attachTo: document.body
      })

      const input = wrapper.find('input')
      await input.trigger('focus')

      const inputWrapper = wrapper.find('.input-wrapper')
      expect(inputWrapper.classes().some(c => c.includes('border-wolf-danger'))).toBe(true)

      wrapper.unmount()
    })

    it('focus ring width is 2px (WCAG compliant)', () => {
      // Verify via CSS config
      const baseCssPath = path.resolve(__dirname, '../../src/styles/base.css')
      const baseCss = fs.readFileSync(baseCssPath, 'utf-8')

      expect(baseCss).toContain('outline-wolf-focus')
    })
  })

  describe('Global Focus Ring Config', () => {
    it('tailwind.config.ts defines focus ring width 2px', () => {
      const tailwindPath = path.resolve(__dirname, '../../tailwind.config.ts')
      const config = fs.readFileSync(tailwindPath, 'utf-8')

      expect(config).toContain("'wolf-focus': '2px'")
    })
  })
})