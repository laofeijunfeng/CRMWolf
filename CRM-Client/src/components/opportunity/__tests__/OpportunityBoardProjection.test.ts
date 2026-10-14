import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import OpportunityBoardProjection from '../OpportunityBoardProjection.vue'
import type { OpportunityBoardResponse } from '@/schemas/opportunityBoard'

const response: OpportunityBoardResponse = {
  summary: [
    {
      key: 'total_count',
      label: '商机',
      value_type: 'count',
      value: 2,
    },
    {
      key: 'pipeline_amount',
      label: '预计金额',
      value_type: 'amount',
      value: '8800.00',
    },
  ],
  columns: [
    {
      key: 'stage:18:42',
      label: '方案确认',
      tone: 'info',
      column_kind: 'active_stage',
      stage_name: '方案确认',
      template_code: 'STD-02',
      template_sort_order: 2,
      procurement_method_id: 18,
      procurement_stage_template_id: 42,
      count: 1,
      amount: '8800.00',
      items: [
        {
          id: 'opp_public_1',
          title: '星河续购',
          subtitle: '星河科技',
          amount: '8800.00',
          date: '2026-09-12',
          owner: { id: 'user-2', name: '李娜', avatar_url: null },
          status: 'active',
          metadata: {
            customer_name: '星河科技',
            purchase_type: '续购',
            license_type: '订阅',
            expected_closing_date: '2026-11-30',
            win_probability: 65.5,
            stage_name: '方案确认',
            stage_sort_order: 2,
            procurement_method_name: '公开招标',
            procurement_method_code: 'OPEN-BID',
            procurement_stage_template_id: 42,
            template_code: 'STD-02',
          },
          action_state: {
            can_edit: true,
            can_delete: false,
            can_move_stage: true,
            can_mark_won: true,
            can_mark_lost: false,
          },
        },
      ],
      has_more: false,
      remaining_count: 0,
    },
    {
      key: 'stage:19:77',
      label: '方案确认',
      tone: 'info',
      column_kind: 'active_stage',
      stage_name: '方案确认',
      template_code: 'FAST-01',
      template_sort_order: 1,
      procurement_method_id: 19,
      procurement_stage_template_id: 77,
      count: 1,
      amount: '100.00',
      items: [
        {
          id: 'opp_public_2',
          title: '北辰新购',
          subtitle: null,
          amount: null,
          date: null,
          owner: null,
          status: 'active',
          metadata: {
            customer_name: null,
            purchase_type: null,
            license_type: null,
            expected_closing_date: null,
            win_probability: null,
            stage_name: '方案确认',
            stage_sort_order: 1,
            procurement_method_name: '单一来源',
            procurement_method_code: 'SINGLE',
            procurement_stage_template_id: 77,
            template_code: 'FAST-01',
          },
          action_state: {
            can_edit: false,
            can_delete: false,
            can_move_stage: false,
            can_mark_won: false,
            can_mark_lost: false,
          },
        },
      ],
      has_more: false,
      remaining_count: 0,
    },
    {
      key: 'unset_stage',
      label: '未设置阶段',
      tone: 'muted',
      column_kind: 'unset_stage',
      stage_name: null,
      template_code: null,
      template_sort_order: null,
      procurement_method_id: null,
      procurement_stage_template_id: null,
      count: 0,
      amount: '0.00',
      items: [],
      has_more: false,
      remaining_count: 0,
    },
  ],
  trends: [
    { date: '2026-09', count: 1, amount: '8800.00' },
    { date: '2026-10', count: 0, amount: '-12.50' },
  ],
}

function mountProjection() {
  return mount(OpportunityBoardProjection, {
    props: { response },
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

describe('OpportunityBoardProjection', () => {
  it('renders amount, win probability, closing date, customer, purchase, license, and public id in backend order', () => {
    const wrapper = mountProjection()
    const keys = wrapper.findAll('[data-column-key]').map((column) => column.attributes('data-column-key'))

    expect(wrapper.findComponent({ name: 'BoardView' }).exists()).toBe(true)
    expect(keys).toEqual(['stage:18:42', 'stage:19:77', 'unset_stage'])
    const first = wrapper.get('[data-column-key="stage:18:42"]')
    expect(first.text()).toContain('星河续购')
    expect(first.text()).toContain('¥8,800.00')
    expect(first.text()).toContain('65.5%')
    expect(first.text()).toContain('2026-11-30')
    expect(first.text()).toContain('星河科技')
    expect(first.text()).toContain('续购')
    expect(first.text()).toContain('订阅')
    expect(first.text()).toContain('opp_public_1')
    expect(first.findComponent({ name: 'AmountText' }).props('value')).toBe('8800.00')

    const second = wrapper.get('[data-column-key="stage:19:77"]')
    expect(second.text()).toContain('北辰新购')
    expect(second.text()).not.toContain('%')
  })

  it('emits the public opportunity id and method/template view-all identity', async () => {
    const wrapper = mountProjection()

    await wrapper.get('[data-column-key="stage:18:42"] [role="button"]').trigger('click')
    expect(wrapper.emitted('activate-card')).toEqual([[{ id: 'opp_public_1', columnKey: 'stage:18:42' }]])

    await wrapper.get('[data-column-key="stage:19:77"] button').trigger('click')
    expect(wrapper.emitted('view-all')).toEqual([['method:19:template:77']])
  })

  it('converts fixed-point trend amounts only in the chart values', () => {
    const wrapper = mountProjection()
    const chart = wrapper.getComponent({ name: 'AreaTrendChart' })

    expect(chart.props('data')).toEqual([
      { month: '2026-09', count: 1, amount: 8800 },
      { month: '2026-10', count: 0, amount: -12.5 },
    ])
    expect(response.trends[0]?.amount).toBe('8800.00')
    expect(response.trends[1]?.amount).toBe('-12.50')
  })
})
