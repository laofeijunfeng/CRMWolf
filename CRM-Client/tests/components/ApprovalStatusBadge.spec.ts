/**
 * Task C2: ApprovalStatusBadge 单元测试
 *
 * 验证 4 态渲染 + 中文文案 + a11y role/aria-label + 图标（颜色非唯一指示）。
 * 覆盖 C-DSG-1 token 映射 + C-DSG-6 无障碍。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import ApprovalStatusBadge from '@/components/ApprovalStatusBadge.vue'

describe('ApprovalStatusBadge', () => {
  const mountBadge = (props: Record<string, unknown>) =>
    mount(ApprovalStatusBadge, { props, global: { plugins: [ElementPlus] } })

  it.each([
    ['PENDING', '待审批'],
    ['APPROVED', '已通过'],
    ['REJECTED', '已驳回'],
    ['CANCELLED', '已撤回']
  ])('renders %s as %s with aria-label', (status, label) => {
    const w = mountBadge({ status })
    expect(w.text()).toContain(label)
    expect(w.attributes('aria-label')).toContain(label)
  })

  it('exposes role="status" for screen readers', () => {
    const w = mountBadge({ status: 'PENDING' })
    expect(w.attributes('role')).toBe('status')
  })

  it('renders an icon for APPROVED (color is not the only indicator)', () => {
    const w = mountBadge({ status: 'APPROVED' })
    expect(w.find('svg').exists()).toBe(true)
  })

  it('renders an icon for REJECTED', () => {
    const w = mountBadge({ status: 'REJECTED' })
    expect(w.find('svg').exists()).toBe(true)
  })

  it('renders an icon for CANCELLED', () => {
    const w = mountBadge({ status: 'CANCELLED' })
    expect(w.find('svg').exists()).toBe(true)
  })

  it('renders an icon for PENDING', () => {
    const w = mountBadge({ status: 'PENDING' })
    expect(w.find('svg').exists()).toBe(true)
  })

  it('applies the approved CSS variable color token via inline style', () => {
    const w = mountBadge({ status: 'APPROVED' })
    // 颜色取 $wolf-approval-approved-text → --wolf-approval-approved-text CSS 变量
    const style = w.attributes('style') ?? ''
    expect(style).toContain('--wolf-approval-approved-text')
  })
})
