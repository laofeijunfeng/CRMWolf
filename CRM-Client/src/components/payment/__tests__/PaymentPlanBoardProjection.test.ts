import { mount } from '@vue/test-utils'
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

function mountProjection(board: PaymentPlanBoardResponse = response) {
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
  it('renders planned, paid, remaining, overdue, due date, relations, stage, owner, status, and numeric id', () => {
    const wrapper = mountProjection()
    const column = wrapper.get('[data-column-key="OVERDUE"]')

    expect(wrapper.findComponent({ name: 'BoardView' }).exists()).toBe(true)
    expect(column.text()).toContain('¥10,000.00')
    expect(column.text()).toContain('¥2,500.00')
    expect(column.text()).toContain('¥7,500.00')
    expect(column.text()).not.toContain('10000.00')
    expect(column.text()).not.toContain('2500.00')
    expect(column.text()).not.toContain('7500.00')
    expect(column.text()).toContain('2026-07-31')
    expect(column.text()).toContain('星河科技')
    expect(column.text()).toContain('星河年度合同')
    expect(column.text()).toContain('星河续购')
    expect(column.text()).toContain('已逾期')
    expect(column.text()).toContain('陈晨')
    expect(column.text()).toContain('7')
    const card = column.get('.board-card')
    expect(card.text()).toContain('计划金额')
    expect(card.text()).toContain('已回款')
    expect(card.text()).toContain('待回款')
    expect(card.text()).toContain('逾期待回款')
    expect(card.text()).toContain('¥10,000.00')
    expect(card.text()).toContain('¥2,500.00')
    expect(card.text()).toContain('¥7,500.00')
    expect(column.findAllComponents({ name: 'AmountText' }).map((amount) => amount.props('value'))).toEqual([
      '7500.00',
      '10000.00',
    ])
  })

  it('keeps the column overdue total off a non-overdue card', () => {
    const wrapper = mountProjection()
    const column = wrapper.get('[data-column-key="PENDING"]')
    const card = column.get('.board-card')

    expect(column.findComponent({ name: 'AmountText' }).props('value')).toBe('7500.00')
    expect(column.text()).toContain('¥7,500.00')
    expect(card.text()).not.toContain('逾期待回款')
    expect(card.text()).not.toContain('¥7,500.00')
    expect(card.text()).toContain('计划金额')
    expect(card.text()).toContain('¥4,000.00')
    expect(card.text()).toContain('已回款')
    expect(card.text()).toContain('¥0.00')
    expect(card.text()).toContain('待回款')
    expect(card.text()).toContain('¥4,000.00')
  })

  it('shows a formatted zero when an overdue plan remaining balance is zero', () => {
    const board: PaymentPlanBoardResponse = {
      ...response,
      columns: response.columns.map((column) => {
        if (column.key !== 'OVERDUE') return column
        return {
          ...column,
          items: column.items.map((item) => ({
            ...item,
            remaining_amount: '0.00',
            metadata: { ...item.metadata, remaining_amount: '0.00' },
          })),
        }
      }),
    }
    const wrapper = mountProjection(board)
    const column = wrapper.get('[data-column-key="OVERDUE"]')
    const card = column.get('.board-card')
    const overdueLabel = card.findAll('dt').find((label) => label.text() === '逾期待回款')

    expect(overdueLabel?.element.nextElementSibling?.textContent?.trim()).toBe('¥0.00')
    expect(column.findComponent({ name: 'AmountText' }).props('value')).toBe('7500.00')
    expect(card.text()).not.toContain('¥7,500.00')
  })

  it('emits the numeric payment plan id', async () => {
    const wrapper = mountProjection()

    await wrapper.get('[role="button"]').trigger('click')
    expect(wrapper.emitted('activate-card')).toEqual([[{ id: 7, columnKey: 'OVERDUE' }]])
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('view-all')).toEqual([['OVERDUE']])
  })

  it('converts payment-plan chart amounts without changing the response', () => {
    const wrapper = mountProjection()
    const chart = wrapper.getComponent({ name: 'AreaTrendChart' })

    expect(chart.props('data')).toEqual([{
      month: '2026-07',
      count: 1,
      planned_amount: 10000,
      paid_amount: 2500,
      remaining_amount: 7500,
    }])
    expect(response.trends[0]?.planned_amount).toBe('10000.00')
  })
})
