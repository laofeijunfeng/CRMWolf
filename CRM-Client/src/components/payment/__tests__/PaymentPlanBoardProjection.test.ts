import { mount, type VueWrapper } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PaymentPlanBoardProjection from '../PaymentPlanBoardProjection.vue'
import type { PaymentPlanBoardResponse } from '@/schemas/paymentPlanBoard'

const response: PaymentPlanBoardResponse = {
  summary: [
    {
      key: 'planned_amount',
      label: '计划金额',
      value_type: 'amount',
      value: '10000.00',
    },
    {
      key: 'paid_amount',
      label: '已回款',
      value_type: 'amount',
      value: '2500.00',
    },
    {
      key: 'remaining_amount',
      label: '待回款',
      value_type: 'amount',
      value: '7500.00',
    },
    {
      key: 'overdue_remaining_amount',
      label: '逾期待回款',
      value_type: 'amount',
      value: '7500.00',
    },
  ],
  columns: [
    {
      key: 'OVERDUE',
      label: '已逾期',
      tone: 'danger',
      count: 1,
      amount: '10000.00',
      planned_amount: '10000.00',
      paid_amount: '2500.00',
      remaining_amount: '7500.00',
      overdue_remaining_amount: '7500.00',
      items: [
        {
          id: 7,
          title: 'PP-2026-007',
          subtitle: '一期',
          amount: '10000.00',
          planned_amount: '10000.00',
          paid_amount: '2500.00',
          remaining_amount: '7500.00',
          date: '2026-07-31',
          owner: { id: 'user-4', name: '陈晨', avatar_url: null },
          status: 'OVERDUE',
          metadata: {
            customer_name: '星河科技',
            contract_name: '星河年度合同',
            opportunity_name: '星河续购',
            paid_amount: '2500.00',
            remaining_amount: '7500.00',
          },
          action_state: {
            can_edit: false,
            can_delete: false,
            can_view_detail: true,
          },
        },
      ],
      has_more: false,
      remaining_count: 0,
    },
    {
      key: 'PENDING',
      label: '待回款',
      tone: 'neutral',
      count: 1,
      amount: '4000.00',
      planned_amount: '4000.00',
      paid_amount: '0.00',
      remaining_amount: '4000.00',
      overdue_remaining_amount: '7500.00',
      items: [
        {
          id: 8,
          title: 'PP-2026-008',
          subtitle: '二期',
          amount: '4000.00',
          planned_amount: '4000.00',
          paid_amount: '0.00',
          remaining_amount: '4000.00',
          date: '2026-08-31',
          owner: { id: 'user-5', name: '林岚', avatar_url: null },
          status: 'PENDING',
          metadata: {
            customer_name: '北辰制造',
            contract_name: '北辰采购合同',
            opportunity_name: '北辰扩容',
            paid_amount: '0.00',
            remaining_amount: '4000.00',
          },
          action_state: {
            can_edit: false,
            can_delete: false,
            can_view_detail: true,
          },
        },
      ],
      has_more: false,
      remaining_count: 0,
    },
  ],
  trends: [
    {
      date: '2026-07',
      count: 1,
      planned_amount: '10000.00',
      paid_amount: '2500.00',
      remaining_amount: '7500.00',
    },
  ],
}

function mountProjection(board: PaymentPlanBoardResponse = response): VueWrapper {
  return mount(PaymentPlanBoardProjection, {
    props: { response: board },
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

describe('PaymentPlanBoardProjection', () => {
  it('renders customer, stage name, and owner without the plan number or amounts', async () => {
    const wrapper = mountProjection()
    const overdue = wrapper.get('[data-column-key="OVERDUE"]')
    const card = overdue.get('[role="button"]')

    expect(card.text()).toContain('星河科技')
    expect(card.text()).toContain('一期')
    expect(card.text()).toContain('陈晨')
    expect(card.text()).not.toContain('PP-2026-007')
    expect(card.text()).not.toContain('计划金额')
    expect(card.text()).not.toContain('¥')
    expect(overdue.text()).not.toContain('查看全部')

    const pending = wrapper.get('[data-column-key="PENDING"]')
    expect(pending.text()).toContain('北辰制造')
    expect(pending.text()).toContain('二期')
    expect(pending.text()).toContain('林岚')

    await card.trigger('click')
    expect(wrapper.emitted('activate-card')).toEqual([[{ id: 7, columnKey: 'OVERDUE' }]])
    expect(wrapper.emitted('view-all')).toBeUndefined()
  })
})
