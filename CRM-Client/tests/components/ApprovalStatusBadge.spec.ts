import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ApprovalStatusBadge from '@/components/ApprovalStatusBadge.vue'

describe('ApprovalStatusBadge', () => {
  const mountBadge = (props: Record<string, unknown>) =>
    mount(ApprovalStatusBadge, { props })

  it.each([
    ['PENDING', '审批中'],
    ['APPROVED', '已通过'],
    ['REJECTED', '已驳回'],
    ['CANCELLED', '已撤回'],
  ])('renders %s as %s with aria-label', (status, label) => {
    const wrapper = mountBadge({ status })
    expect(wrapper.text()).toContain(label)
    expect(wrapper.attributes('aria-label')).toBe(label)
    expect(wrapper.attributes('role')).toBe('status')
  })

  it('renders a semantic icon for every known approval state', () => {
    for (const status of ['PENDING', 'APPROVED', 'REJECTED', 'CANCELLED']) {
      expect(mountBadge({ status }).find('svg').exists()).toBe(true)
    }
  })

  it('uses the shared status base and traces unknown backend values', () => {
    const wrapper = mountBadge({ status: 'ARCHIVED' })
    expect(wrapper.text()).toContain('未知状态')
    expect(wrapper.attributes('data-status-tone')).toBe('neutral')
    expect(wrapper.attributes('data-status-domain')).toBe('approval')
    expect(wrapper.attributes('data-status-value')).toBe('ARCHIVED')
    expect(wrapper.attributes('title')).toBe('approval: ARCHIVED')
  })
})
