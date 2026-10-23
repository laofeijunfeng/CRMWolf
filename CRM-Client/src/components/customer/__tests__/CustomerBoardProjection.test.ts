import { mount, type VueWrapper } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CustomerBoardProjection from '../CustomerBoardProjection.vue'
import type { CustomerBoardResponse } from '@/schemas/customerBoard'

const response: CustomerBoardResponse = {
  summary: [
    {
      key: 'total_count',
      label: '客户',
      value_type: 'count',
      value: 2,
    },
    {
      key: 'recent_new_count',
      label: '新增',
      secondary_label: '上月',
      value_type: 'count',
      value: 1,
      secondary_value: 0,
    },
    {
      key: 'following_percentage',
      label: '跟进占比',
      value_type: 'percentage',
      value: 50,
    },
    {
      key: 'lost_percentage',
      label: '流失占比',
      value_type: 'percentage',
      value: null,
    },
  ],
  columns: [
    {
      key: 'following',
      label: '跟进中',
      tone: 'info',
      count: 2,
      amount: '1200.50',
      items: [
        {
          id: 'cus_public_1',
          title: '星河科技',
          subtitle: '方案沟通',
          amount: '1200.50',
          date: '2026-10-01',
          owner: { id: 'user-1', name: '王敏', avatar_url: null },
          status: 'following',
          metadata: {
            stage_hint: '方案沟通',
            industry: '软件',
            city: '上海',
            company_scale: '100-499人',
            license_type: 'OFFICIAL',
            license_expiry_date: '2027-03-15',
          },
          action_state: {
            can_edit: true,
            can_delete: false,
            can_assign: true,
            can_create_opportunity: true,
          },
        },
      ],
      has_more: true,
      remaining_count: 1,
    },
    {
      key: 'lost',
      label: '已流失',
      tone: 'danger',
      count: 1,
      amount: null,
      items: [
        {
          id: 'cus_public_2',
          title: '北辰制造',
          subtitle: null,
          amount: null,
          date: null,
          owner: null,
          status: 'lost',
          metadata: {
            stage_hint: null,
            industry: null,
            city: null,
            company_scale: null,
            license_type: null,
            license_expiry_date: null,
          },
          action_state: {
            can_edit: false,
            can_delete: false,
            can_assign: false,
            can_create_opportunity: false,
          },
        },
      ],
      has_more: false,
      remaining_count: 0,
    },
  ],
  trends: [
    { date: '2026-09', count: 1 },
    { date: '2026-10', count: 2 },
  ],
}

function mountProjection(value: CustomerBoardResponse = response): VueWrapper {
  return mount(CustomerBoardProjection, {
    props: { response: value },
    global: {
      stubs: {
        AreaTrendChart: {
          name: 'AreaTrendChart',
          props: ['title', 'description', 'data', 'series', 'xKey'],
          template: '<div class="trend-stub">{{ title }}</div>',
        },
      },
    },
  })
}

describe('CustomerBoardProjection', () => {
  it('renders stage hint, customer name, and owner without the old card rows', async () => {
    const wrapper = mountProjection()
    const following = wrapper.get('[data-column-key="following"]')
    const card = following.get('[role="button"]')

    expect(following.text()).toContain('方案沟通')
    expect(following.text()).toContain('星河科技')
    expect(following.text()).toContain('王敏')
    expect(following.text()).not.toContain('行业')
    expect(following.text()).not.toContain('软件')
    expect(following.text()).not.toContain('查看全部')
    expect(following.find('[data-testid="board-card-action-edit"]').exists()).toBe(false)
    expect(card.text()).not.toContain('¥')

    const lost = wrapper.get('[data-column-key="lost"]')
    expect(lost.text()).toContain('北辰制造')
    expect(lost.get('[role="button"]').text()).toContain('-')

    await card.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('activate-card')).toEqual([[{ id: 'cus_public_1', columnKey: 'following' }]])
    expect(wrapper.emitted('view-all')).toBeUndefined()
  })
})
