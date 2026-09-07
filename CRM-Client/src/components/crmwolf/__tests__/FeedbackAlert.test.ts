import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import FeedbackAlert from '../FeedbackAlert.vue'
import type { FeedbackError } from '@/types/feedback'

describe('FeedbackAlert', () => {
  const error: FeedbackError = {
    title: '登记回款失败',
    description: '网络中断，操作结果可能尚未确认，请先查询最新状态后再重试。',
    kind: 'network',
    retryable: true,
    outcomeUnknown: true,
    requestId: 'req-001',
  }

  it('renders nothing without an error', () => {
    const wrapper = mount(FeedbackAlert, {
      props: { error: null },
    })

    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('renders recovery-aware feedback and emits retry', async () => {
    const wrapper = mount(FeedbackAlert, {
      props: {
        error,
        density: 'compact',
        retryLabel: '重新提交',
      },
      attachTo: document.body,
    })

    const alert = wrapper.get('[role="alert"]')
    expect(alert.attributes('aria-live')).toBe('assertive')
    expect(alert.text()).toContain('登记回款失败')
    expect(alert.text()).toContain('网络中断，操作结果可能尚未确认')
    expect(alert.text()).toContain('请先确认记录状态，避免重复提交')
    expect(alert.text()).toContain('req-001')

    await wrapper.get('button').trigger('click')

    expect(wrapper.emitted('retry')).toHaveLength(1)

    wrapper.unmount()
  })
})
