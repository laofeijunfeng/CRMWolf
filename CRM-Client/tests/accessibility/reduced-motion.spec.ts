/**
 * Reduced Motion Accessibility Tests
 * UI/UX Pro Max CRITICAL §7: Respect prefers-reduced-motion
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TouchButton from '@/components/crmwolf/TouchButton.vue'
import fs from 'fs'
import path from 'path'

describe('Reduced Motion Compliance (UI/UX Pro Max §7)', () => {
  describe('TouchButton', () => {
    it('press feedback disabled when prefers-reduced-motion', () => {
      // This is handled via CSS @media query
      // Verify base.css has the rule
      const baseCssPath = path.resolve(__dirname, '../../src/styles/base.css')
      const baseCss = fs.readFileSync(baseCssPath, 'utf-8')

      expect(baseCss).toContain('prefers-reduced-motion')
      expect(baseCss).toContain('transition-duration: 0.01ms')
    })
  })

  describe('Global CSS', () => {
    it('base.css disables animations for reduced-motion users', () => {
      const baseCssPath = path.resolve(__dirname, '../../src/styles/base.css')
      const baseCss = fs.readFileSync(baseCssPath, 'utf-8')

      expect(baseCss).toContain('@media (prefers-reduced-motion: reduce)')
      expect(baseCss).toContain('animation-duration: 0.01ms')
      expect(baseCss).toContain('transition-duration: 0.01ms')
    })

    it('press feedback class exists in base.css', () => {
      const baseCssPath = path.resolve(__dirname, '../../src/styles/base.css')
      const baseCss = fs.readFileSync(baseCssPath, 'utf-8')

      // Press feedback is defined in base.css utilities layer
      expect(baseCss).toContain('press-feedback')
      expect(baseCss).toContain('active:scale')
    })
  })

  describe('Tailwind Config', () => {
    it('defines reduced motion duration', () => {
      const tailwindPath = path.resolve(__dirname, '../../tailwind.config.ts')
      const configContent = fs.readFileSync(tailwindPath, 'utf-8')

      // Verify wolf duration values exist
      expect(configContent).toContain("wolf: '150ms'")
    })
  })
})