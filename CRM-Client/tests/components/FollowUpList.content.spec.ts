import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import FollowUpList from '@/components/FollowUpList.vue'

vi.mock('lucide-vue-next', () => {
  const icon = (name: string) => defineComponent({
    name,
    setup: () => () => h('svg', { 'data-icon': name }),
  })

  return {
    CalendarClock: icon('CalendarClock'),
    Loader2: icon('Loader2'),
    Mail: icon('Mail'),
    MessageCircle: icon('MessageCircle'),
    MessageSquare: icon('MessageSquare'),
    Phone: icon('Phone'),
    RefreshCw: icon('RefreshCw'),
    ThumbsDown: icon('ThumbsDown'),
    ThumbsUp: icon('ThumbsUp'),
    Trash2: icon('Trash2'),
    User: icon('User'),
    Users: icon('Users'),
  }
})

vi.mock('@/components/crmwolf', () => ({
  HoverInfo: defineComponent({
    name: 'HoverInfo',
    setup: (_, { slots }) => () => h('div', [slots.trigger?.(), slots.default?.()]),
  }),
}))

vi.mock('@/components/ui/skeleton', () => ({
  Skeleton: defineComponent({ name: 'Skeleton', setup: () => () => h('div') }),
}))

vi.mock('@/components/ui/button', () => ({
  Button: defineComponent({
    name: 'Button',
    setup: (_, { slots, attrs }) => () => h('button', attrs, slots.default?.()),
  }),
}))

vi.mock('@/components/ui/empty', () => {
  const passthrough = (name: string) => defineComponent({ name, setup: (_, { slots }) => () => h('div', slots.default?.()) })
  return {
    Empty: passthrough('Empty'),
    EmptyHeader: passthrough('EmptyHeader'),
    EmptyMedia: passthrough('EmptyMedia'),
    EmptyTitle: passthrough('EmptyTitle'),
    EmptyDescription: passthrough('EmptyDescription'),
  }
})

vi.mock('@/utils/confirmDialog', () => ({ confirmDelete: vi.fn() }))

describe('FollowUpList content rendering', () => {
  it('renders customer activity content instead of the generic activity kind title', () => {
    const wrapper = mount(FollowUpList, {
      props: {
        loading: false,
        followUps: [{
          id: 1,
          customer_id: 19,
          activity_kind: 'PHONE_FOLLOW_UP',
          activity_category: 'FOLLOW_UP',
          activity_label: '电话跟进',
          title: '电话跟进',
          source_content: '今天和王总沟通了预算，下周三继续确认采购流程。',
          content_json: {
            content: '客户预算已初步确认，下周三继续确认采购流程。',
          },
          summary: null,
          processing_status: 'COMPLETED',
          content: '电话跟进',
          method: '电话跟进',
          creator_id: '9',
          created_time: '2026-07-30T10:00:00.000Z',
        }],
      },
    })

    expect(wrapper.get('.follow-up-content').text()).toBe('客户预算已初步确认，下周三继续确认采购流程。')
  })

  it('keeps legacy lead follow-up content rendering', () => {
    const wrapper = mount(FollowUpList, {
      props: {
        loading: false,
        followUps: [{
          id: 2,
          lead_id: 8,
          content: '线索客户要求下周安排产品演示。',
          method: '电话',
          creator_id: '9',
          created_time: '2026-07-30T10:00:00.000Z',
        }],
      },
    })

    expect(wrapper.get('.follow-up-content').text()).toBe('线索客户要求下周安排产品演示。')
  })

  it('uses the activity kind to render a matching icon for customer activities', () => {
    const wrapper = mount(FollowUpList, {
      props: {
        loading: false,
        followUps: [{
          id: 3,
          customer_id: 19,
          activity_kind: 'PHONE_FOLLOW_UP',
          activity_category: 'FOLLOW_UP',
          activity_label: '电话跟进',
          source_content: '电话沟通客户预算。',
          content_json: {
            content: '电话沟通客户预算。',
          },
          content: '电话跟进',
          method: '电话跟进',
          creator_id: '9',
          created_time: '2026-07-30T10:00:00.000Z',
        }],
      },
    })

    expect(wrapper.get('.follow-up-method svg').attributes('data-icon')).toBe('Phone')
  })
})
