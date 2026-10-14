import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ContractBoardProjection from '../ContractBoardProjection.vue'
import type { ContractBoardResponse } from '@/schemas/contractBoard'

const statuses = [
  'DRAFT',
  'PENDING_REVIEW',
  'SIGNED',
  'EFFECTIVE',
  'EXPIRED',
  'TERMINATED',
  'UNCLASSIFIED',
] as const

const response: ContractBoardResponse = {
  summary: [
    {
      key: 'total_count',
      label: '合同',
      value_type: 'count',
      value: 1,
    },
    {
      key: 'total_amount',
      label: '合同金额',
      value_type: 'amount',
      value: '32000.00',
    },
  ],
  columns: statuses.map((key, index) => ({
    key,
    label: key === 'UNCLASSIFIED' ? '未分类' : `状态${index}`,
    tone: key === 'UNCLASSIFIED' ? 'muted' : 'neutral',
    count: index === 2 ? 1 : 0,
    amount: index === 2 ? '32000.00' : '0.00',
    items: index === 2
      ? [{
          id: 42,
          title: '星河年度合同',
          subtitle: 'HT-2026-042',
          amount: '32000.00',
          date: '2026-08-01',
          owner: { id: 'user-3', name: '赵磊', avatar_url: null },
          status: 'SIGNED',
          metadata: {
            customer_name: '星河科技',
            opportunity_name: '星河续购',
            license_type: '订阅',
            purchase_type: '续购',
            signing_date: '2026-08-01',
            effective_date: '2026-08-15',
            expiry_date: '2027-08-14',
            license_expiry_date: '2027-08-14',
            authorized_users: 25,
          },
          action_state: {
            can_edit: false,
            can_delete: false,
            can_submit_approval: false,
            can_approve: true,
            can_reject: true,
          },
        }]
      : [],
    has_more: false,
    remaining_count: 0,
  })),
  trends: [{ date: '2026-08', count: 1, amount: '32000.00' }],
}

function mountProjection() {
  return mount(ContractBoardProjection, {
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

describe('ContractBoardProjection', () => {
  it('renders amount, dates, customer, opportunity, license, purchase, owner, numeric id, and all seven columns', () => {
    const wrapper = mountProjection()
    const keys = wrapper.findAll('[data-column-key]').map((column) => column.attributes('data-column-key'))
    const signed = wrapper.get('[data-column-key="SIGNED"]')

    expect(wrapper.findComponent({ name: 'BoardView' }).exists()).toBe(true)
    expect(keys).toEqual([...statuses])
    expect(signed.text()).toContain('星河年度合同')
    expect(signed.text()).toContain('赵磊')
    expect(signed.text()).toContain('星河科技')
    expect(signed.text()).toContain('星河续购')
    expect(signed.text()).toContain('订阅')
    expect(signed.text()).toContain('续购')
    expect(signed.text()).toContain('2026-08-01')
    expect(signed.text()).toContain('2026-08-15')
    expect(signed.text()).toContain('2027-08-14')
    expect(signed.text()).toContain('42')
    expect(signed.findComponent({ name: 'AmountText' }).props('value')).toBe('32000.00')
    expect(wrapper.get('[data-column-key="UNCLASSIFIED"]').text()).toContain('未分类')
  })

  it('emits the numeric contract id and the unclassified column key', async () => {
    const wrapper = mountProjection()

    await wrapper.get('[data-column-key="SIGNED"] [role="button"]').trigger('keydown', { key: ' ' })
    expect(wrapper.emitted('activate-card')).toEqual([[{ id: 42, columnKey: 'SIGNED' }]])
    await wrapper.get('[data-column-key="UNCLASSIFIED"] button').trigger('click')
    expect(wrapper.emitted('view-all')).toEqual([['UNCLASSIFIED']])
  })

  it('passes a numeric contract chart amount without changing the response', () => {
    const wrapper = mountProjection()
    const chart = wrapper.getComponent({ name: 'AreaTrendChart' })

    expect(chart.props('data')).toEqual([{ month: '2026-08', count: 1, amount: 32000 }])
    expect(response.trends[0]?.amount).toBe('32000.00')
  })
})
