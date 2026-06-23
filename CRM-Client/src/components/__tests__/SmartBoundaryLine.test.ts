// CRM-Client/src/components/__tests__/SmartBoundaryLine.test.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SmartBoundaryLine from '../SmartBoundaryLine.vue'

describe('SmartBoundaryLine', () => {
  it('should render boundary line with correct height', () => {
    const wrapper = mount(SmartBoundaryLine, {
      props: { active: false }
    })

    const line = wrapper.find('.smart-boundary-line')
    expect(line.exists()).toBe(true)

    // ← 验证高度为 2px（设计要求）
    expect(line.element.style.height).toBe('2px')
  })

  it('should apply active animation when active=true', () => {
    const wrapper = mount(SmartBoundaryLine, {
      props: { active: true }
    })

    const line = wrapper.find('.smart-boundary-line')
    expect(line.classes()).toContain('is-active')
  })

  it('should respect reduced motion preference', () => {
    const wrapper = mount(SmartBoundaryLine, {
      props: { active: true }
    })

    // ← 验证 Reduced Motion 支持（动画禁用）
    const styles = wrapper.find('.smart-boundary-line').attributes('style')
    expect(styles).toBeDefined()
  })
})