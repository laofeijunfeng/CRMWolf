import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import FailureCard from '@/components/sales-assistant/FailureCard.vue'

describe('terminal assistant failure', () => {
  it('keeps an independently committed customer activity visible after a later failure', () => {
    const wrapper = mount(FailureCard, {
      props: {
        message: '后续商机处理失败', errorCode: 'CRM_WRITE_REJECTED',
        task: {
          public_id: 'ast_1', status: 'ACTIVE', proposals_enabled: true, goal: '记录沟通', activity_kind: 'FOLLOW_UP',
          draft: { customer: { status: 'MISSING' }, content: { status: 'MISSING' }, next_action: { status: 'MISSING' }, next_follow_time: { status: 'MISSING' } },
          waiting: null, committed: [{ kind: 'customer_activity', public_id: 'act_1', customer_id: 1 }],
          budget_steps: 0, budget_max_steps: 50, version: 2
        }
      }
    })

    expect(wrapper.text()).toContain('客户活动已写入，不受后续处理失败影响')
    expect(wrapper.text()).not.toContain('本次写入未完成')
  })
})
