import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import FollowUpList from '../FollowUpList.vue'

const baseActivity = {
  id: 1,
  customer_id: 'cust-1',
  content: '### 核心进展\n- **已确认预算**',
  summary: '### 核心进展\n- **已确认预算**',
  source_content: '原始输入内容',
  method: '电话跟进',
  creator_id: '10',
  created_time: '2026-11-20T10:00:00',
  processing_status: 'COMPLETED',
  effectiveness_status: 'COMPLETED',
  effectiveness_score: 88,
  effectiveness_is_valid: true,
}

describe('FollowUpList Markdown & 3-state AI lifecycle', () => {
  it('keeps plain text rendering by default for LeadDetailSheet (Boundary 3B)', () => {
    const wrapper = mount(FollowUpList, {
      props: {
        followUps: [baseActivity],
        loading: false,
      },
    })
    expect(wrapper.find('[data-activity-markdown]').exists()).toBe(false)
    expect(wrapper.find('h3').exists()).toBe(false)
    expect(wrapper.text()).toContain('### 核心进展')
  })

  it('renders structured Markdown when renderMarkdown is true', () => {
    const wrapper = mount(FollowUpList, {
      props: {
        followUps: [baseActivity],
        loading: false,
        renderMarkdown: true,
      },
    })
    expect(wrapper.find('[data-activity-markdown]').exists()).toBe(true)
    expect(wrapper.find('h3').text()).toBe('核心进展')
    expect(wrapper.find('strong').text()).toBe('已确认预算')
  })

  it('shows pending loading state and failed retry action with double-click guard', async () => {
    const pendingItem = {
      ...baseActivity,
      id: 2,
      processing_status: 'PENDING',
      effectiveness_status: 'PENDING',
    }
    const failedItem = {
      ...baseActivity,
      id: 3,
      processing_status: 'FAILED',
      effectiveness_status: 'FAILED',
    }

    const wrapper = mount(FollowUpList, {
      props: {
        followUps: [pendingItem, failedItem],
        loading: false,
        renderMarkdown: true,
        allowProcess: true,
        retryingIds: [],
      },
    })

    expect(wrapper.find('[data-activity-processing-status="pending"]').text()).toContain('AI 正在整理与评分')
    const retryBtn = wrapper.find('[data-activity-retry-btn]')
    expect(retryBtn.exists()).toBe(true)
    expect(retryBtn.text()).toContain('重新整理')

    await retryBtn.trigger('click')
    const emitted = wrapper.emitted('process')
    expect(emitted).toHaveLength(1)
    expect(emitted?.[0]?.[0]).toMatchObject({ id: 3 })
    // When retryingIds contains 3, button is disabled and does not emit again
    await wrapper.setProps({ retryingIds: [3] })
    await retryBtn.trigger('click')
    expect(wrapper.emitted('process')).toHaveLength(1)
  })
})
