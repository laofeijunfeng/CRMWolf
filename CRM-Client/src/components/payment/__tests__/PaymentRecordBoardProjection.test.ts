import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PaymentRecordBoardProjection from '../PaymentRecordBoardProjection.vue'
import type { PaymentRecordBoardResponse } from '@/schemas/paymentRecordBoard'

const response: PaymentRecordBoardResponse = {
  summary: [
    {
      key: 'actual_total',
      label: '回款金额',
      value_type: 'amount',
      value: '6400.00',
    },
    {
      key: 'confirmed_amount',
      label: '已确认',
      value_type: 'amount',
      value: '6400.00',
    },
  ],
  columns: [
    {
      key: 'approved',
      label: '已通过',
      tone: 'success',
      count: 1,
      amount: '6400.00',
      actual_amount: '6400.00',
      confirmed_amount: '6400.00',
      unconfirmed_amount: '0.00',
      items: [
        {
          id: 91,
          title: 'PR-2026-091',
          subtitle: '星河科技',
          amount: '6400.00',
          actual_amount: '6400.00',
          date: '2026-09-18',
          owner: { id: 'user-5', name: '周宁', avatar_url: null },
          status: 'approved',
          metadata: {
            customer_name: '星河科技',
            contract_name: '星河年度合同',
            actual_payer_name: '星河科技有限公司',
            creator_name: '周宁',
            owner_name: '周宁',
            commission_member_name: '李娜',
            approval_phase: 'approved',
            approval_id: 15,
            confirmation_status: 'CONFIRMED',
          },
          action_state: {
            can_edit: false,
            can_delete: false,
            can_resubmit: false,
          },
        },
      ],
      has_more: false,
      remaining_count: 0,
    },
    {
      key: 'unclassified',
      label: '未分类',
      tone: 'muted',
      count: 1,
      amount: '100.00',
      actual_amount: '100.00',
      confirmed_amount: '0.00',
      unconfirmed_amount: '100.00',
      items: [
        {
          id: 92,
          title: 'PR-2026-092',
          subtitle: null,
          amount: '100.00',
          actual_amount: '100.00',
          date: null,
          owner: null,
          status: 'unclassified',
          metadata: {
            customer_name: null,
            contract_name: null,
            actual_payer_name: null,
            creator_name: null,
            owner_name: null,
            commission_member_name: null,
            approval_phase: null,
            approval_id: null,
            confirmation_status: null,
          },
          action_state: {
            can_edit: false,
            can_delete: false,
            can_resubmit: false,
          },
        },
      ],
      has_more: false,
      remaining_count: 0,
    },
  ],
  trends: [
    {
      date: '2026-09',
      count: 1,
      actual_amount: '6400.00',
      confirmed_amount: '6400.00',
      unconfirmed_amount: '0.00',
    },
  ],
}

function mountProjection() {
  return mount(PaymentRecordBoardProjection, {
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

describe('PaymentRecordBoardProjection', () => {
  it('keeps canonical approved separate from the confirmation badge', () => {
    const wrapper = mountProjection()
    const approved = wrapper.get('[data-column-key="approved"]')

    expect(approved.text()).toContain('已通过')
    expect(approved.text()).toContain('PR-2026-091')
    expect(approved.text()).toContain('2026-09-18')
    expect(approved.text()).toContain('已确认')
    expect(approved.text()).not.toContain('confirmed')
    expect(approved.findComponent({ name: 'AmountText' }).props('value')).toBe('6400.00')

    const badges = approved.findAllComponents({ name: 'Badge' }).map((badge) => badge.text())
    expect(badges).toEqual(expect.arrayContaining(['已通过', '已确认']))
    expect(badges).not.toContain('已确认页签')
  })

  it('emits the numeric record id and does not relabel approved as the external confirmed tab', async () => {
    const wrapper = mountProjection()

    await wrapper.get('[data-column-key="approved"] [role="button"]').trigger('click')
    expect(wrapper.emitted('activate-card')).toEqual([[{ id: 91, columnKey: 'approved' }]])

    await wrapper.get('[data-column-key="approved"] button').trigger('click')
    expect(wrapper.emitted('view-all')).toEqual([['approved']])
    expect(wrapper.text()).not.toContain('已确认页签')
  })

  it('converts record trend amounts without changing transport strings', () => {
    const wrapper = mountProjection()
    const chart = wrapper.getComponent({ name: 'AreaTrendChart' })
    const point = (chart.props('data') as Array<Record<string, unknown>>)[0]

    expect(chart.props('xKey')).toBe('month')
    expect(point).toEqual({
      month: '2026-09',
      count: 1,
      actual_amount: 6400,
      confirmed_amount: 6400,
      unconfirmed_amount: 0,
    })
    expect(Object.keys(point ?? {}).sort()).toEqual([
      'actual_amount',
      'confirmed_amount',
      'count',
      'month',
      'unconfirmed_amount',
    ])
    expect(response.trends[0]?.actual_amount).toBe('6400.00')
    expect(response.columns[0]?.key).toBe('approved')
  })
})
