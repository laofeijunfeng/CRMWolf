/**
 * StatusBadge 契约测试。
 *
 * 验证生命周期状态的稳定文案、未知状态兜底、尺寸和无障碍语义。
 * 审批状态由 ApprovalStatusBadge 单独承载，不在这里重复映射。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import StatusBadge from '@/components/StatusBadge.vue'

describe('StatusBadge', () => {
  const mountBadge = (props: Record<string, unknown>) => mount(StatusBadge, { props })

  it.each([
    ['customer', 'won', '已赢单'],
    ['opportunity', 'lost', '已输单'],
    ['contract', 'signed', '已签署'],
    ['invoice', 'issued', '已开票'],
    ['paymentPlan', 'overdue', '已逾期'],
    ['paymentRecord', 'confirmed', '已确认'],
  ])('renders %s/%s with the stable label %s', (type, status, label) => {
    const wrapper = mountBadge({ type, status })

    expect(wrapper.text()).toContain(label)
    expect(wrapper.attributes('aria-label')).toBe(label)
    expect(wrapper.attributes('role')).toBe('status')
  })

  it('renders dynamic source values without inventing a status mapping', () => {
    const wrapper = mountBadge({ type: 'source', status: '合作伙伴推荐' })

    expect(wrapper.text()).toContain('合作伙伴推荐')
    expect(wrapper.attributes('aria-label')).toBe('合作伙伴推荐')
  })

  it('renders a readable fallback when a backend status is unknown', () => {
    const wrapper = mountBadge({ type: 'contract', status: 'archived' })

    expect(wrapper.text()).toContain('未知')
    expect(wrapper.attributes('aria-label')).toBe('未知')
    expect(wrapper.classes()).toContain('status-neutral')
  })

  it('keeps the compact size as a visual-only contract', () => {
    const wrapper = mountBadge({ type: 'customer', status: 'following', size: 'small' })

    expect(wrapper.classes()).toContain('status-badge--small')
    expect(wrapper.attributes('role')).toBe('status')
  })
})
