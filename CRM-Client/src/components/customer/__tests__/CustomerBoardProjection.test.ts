import { mount } from '@vue/test-utils'
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

function mountProjection(value: CustomerBoardResponse = response) {
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
  it('maps public ids, metadata, nullable amounts, and derived-status view-all keys', async () => {
    const wrapper = mountProjection()

    expect(wrapper.get('[data-column-key="following"]').text()).toContain('星河科技')
    expect(wrapper.get('[data-column-key="following"]').text()).toContain('王敏')
    expect(wrapper.get('[data-column-key="following"]').text()).toContain('软件')
    expect(wrapper.get('[data-column-key="following"]').text()).toContain('上海')
    expect(wrapper.get('[data-column-key="following"]').text()).toContain('100-499人')
    expect(wrapper.get('[data-column-key="following"]').text()).toContain('正式授权')
    expect(wrapper.get('[data-column-key="following"]').text()).toContain('2027-03-15')
    expect(wrapper.get('[data-column-key="following"]').findComponent({ name: 'AmountText' }).props('value')).toBe('1200.50')

    const lost = wrapper.get('[data-column-key="lost"]')
    expect(lost.text()).toContain('北辰制造')
    expect(lost.findComponent({ name: 'AmountText' }).exists()).toBe(false)

    const followingCard = wrapper.get('[data-column-key="following"] [role="button"]')
    await followingCard.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('activate-card')).toEqual([[{ id: 'cus_public_1', columnKey: 'following' }]])

    await wrapper.get('[data-column-key="lost"] button').trigger('click')
    expect(wrapper.emitted('view-all')).toEqual([['lost']])
    expect(wrapper.emitted('activate-card')).toHaveLength(1)
  })

  it('converts customer trend counts only at the chart boundary', () => {
    const wrapper = mountProjection()
    const chart = wrapper.getComponent({ name: 'AreaTrendChart' })

    expect(chart.props('xKey')).toBe('month')
    expect(chart.props('data')).toEqual([
      { month: '2026-09', count: 1 },
      { month: '2026-10', count: 2 },
    ])
    expect(chart.props('series')).toEqual([
      expect.objectContaining({ key: 'count', label: '客户数' }),
    ])
    expect(response.trends).toEqual([
      { date: '2026-09', count: 1 },
      { date: '2026-10', count: 2 },
    ])
    for (const point of chart.props('data') as Array<Record<string, unknown>>) {
      expect(Object.keys(point).sort()).toEqual(['count', 'month'])
    }
  })

  it('formats percentage summaries and omits an empty trend chart', () => {
    const wrapper = mountProjection({
      ...response,
      trends: [],
    })

    expect(wrapper.text()).toContain('50%')
    expect(wrapper.text()).toContain('-')
    expect(wrapper.findComponent({ name: 'AreaTrendChart' }).exists()).toBe(false)
  })
})
