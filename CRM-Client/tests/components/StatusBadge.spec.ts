import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import StatusBadge from '@/components/StatusBadge.vue'

 describe('StatusBadge', () => {
  it('does not disguise unknown backend values as a valid state and retains diagnostic context', () => {
    const badge = mount(StatusBadge, { props: { type: 'invoice', status: 'ARCHIVED' } })
    expect(badge.text()).toBe('未知状态')
    expect(badge.attributes('role')).toBe('status')
    expect(badge.attributes('aria-label')).toBe(badge.text())
    expect(badge.attributes('data-status-value')).toBe('ARCHIVED')
    expect(badge.attributes('data-status-domain')).toBe('invoice')
    expect(badge.attributes('title')).toContain('invoice: ARCHIVED')
    expect(badge.attributes('tabindex')).toBeUndefined()
  })

  it('treats inherited object keys as unknown rather than a presentation entry', () => {
    const badge = mount(StatusBadge, { props: { type: 'invoice', status: 'constructor' } })
    expect(badge.text()).toBe('未知状态')
    expect(badge.attributes('title')).toContain('constructor')
  })

  it('preserves configurable source names instead of treating them as workflow states', () => {
    const badge = mount(StatusBadge, { props: { type: 'source', status: '合作伙伴推荐' } })
    expect(badge.text()).toBe('合作伙伴推荐')
    expect(badge.attributes('aria-label')).toBe(badge.text())
    expect(badge.attributes('title')).toBeUndefined()
  })
})
