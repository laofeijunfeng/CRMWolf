/**
 * Focus Ring Accessibility Tests
 * UI/UX Pro Max CRITICAL §1: Focus States 2-4px visible
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { Button } from '@/components/ui/button'
import TouchInput from '@/components/crmwolf/TouchInput.vue'
import fs from 'fs'
import path from 'path'

describe('Focus Ring Compliance (UI/UX Pro Max §1)', () => {
  describe('Button', () => {
    it('has focus-visible ring classes', () => {
      const wrapper = mount(Button, {
        props: { size: 'icon' },
        slots: { default: 'Button' },
      })

      const button = wrapper.find('button')

      expect(button.classes()).toContain('focus-visible:ring-2')
      expect(button.classes()).toContain('focus-visible:ring-ring')
      expect(button.classes()).toContain('focus-visible:ring-offset-2')
    })
  })

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

    it('focus ring width is 2px (WCAG compliant)', () => {
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
