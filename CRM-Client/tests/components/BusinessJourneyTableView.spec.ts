import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import BusinessJourneyTableView from '@/components/business-journey/BusinessJourneyTableView.vue'
import { createBusinessJourneyListFields } from '@/components/business-journey/businessJourneyListFields'
import type { BusinessJourneyListItem } from '@/schemas/dealJourney'

const journeyFixture: BusinessJourneyListItem = {
  id: 'djy_test',
  public_id: 'djy_test',
  name: '华东续约旅程',
  status: 'ACTIVE',
  current_board_stage: 'active_progress',
  current_board_stage_label: '持续推进',
  amount: 168000,
  purchase_type: 'RENEWAL',
  started_at: '2026-09-01T00:00:00',
  closed_at: null,
  last_event_at: '2026-09-20T00:00:00',
  primary_opportunity: null,
  customer_id: 'cus_test',
  customer_name: '示例科技',
  owner: { id: '7', name: '王小明', avatar_url: null },
  primary_opportunity_name: '续约商机',
  product_name: 'CRM 企业版',
  created_time: '2026-09-01T00:00:00',
  expected_closing_date: '2026-10-01',
}

const mountJourneyTable = (data: BusinessJourneyListItem[]) => mount(
  BusinessJourneyTableView,
  {
    props: {
      fields: createBusinessJourneyListFields([]),
      data,
      total: data.length,
      page: 1,
      pageSize: 20,
      filters: [],
      sorts: [],
      columns: [],
      search: '',
      displayMode: 'table',
    },
  },
)

describe('BusinessJourneyTableView layout', () => {
  it('renders the standard list-page table height', () => {
    const wrapper = mount(BusinessJourneyTableView, {
      props: {
        fields: [],
        data: [],
        total: 0,
        page: 1,
        pageSize: 20,
        filters: [],
        sorts: [],
        columns: [],
        search: '',
        displayMode: 'table',
      },
    })

    const card = wrapper.get('.data-table-card')
    const content = wrapper.get('.data-table-content')

    expect((card.element as HTMLElement).style.height).toBe('calc(100vh - 121px)')
    expect(card.classes()).toContain('data-table-card--fill')
    expect(content.classes()).toContain('data-table-content--contained')
  })

  it('renders the journey name as the standard detail link and emits one row click', async () => {
    const wrapper = mountJourneyTable([journeyFixture])
    const link = wrapper.get('[data-testid="business-journey-name-link"]')

    expect(link.text()).toBe(journeyFixture.name)
    expect(link.classes()).toContain('business-journey-name-link')

    await link.trigger('click')

    expect(wrapper.emitted('row-click')).toEqual([[
      {
        customerId: journeyFixture.customer_id,
        journeyPublicId: journeyFixture.public_id,
      },
    ]])
  })

  it('shows the primary opportunity expected closing date instead of the journey start time', () => {
    const wrapper = mountJourneyTable([{
      ...journeyFixture,
      started_at: '2026-09-01T00:00:00',
      expected_closing_date: '2026-10-01',
    }])
    const dateField = createBusinessJourneyListFields([]).find(field => field.key === 'expected_closing_date')

    expect(dateField).toMatchObject({
      label: '预计成交日期',
      type: 'date',
      filter: true,
      sort: true,
    })
    expect(createBusinessJourneyListFields([]).some(field => field.key === 'started_at')).toBe(false)
    expect(wrapper.text()).toContain('预计成交日期')
    expect(wrapper.text()).toContain('2026-10-01')
    expect(wrapper.text()).not.toContain('开始时间')
    expect(wrapper.text()).not.toContain('2026-09-01')
  })

  it.each([
    ['early_communication', ['bg-sky-50', 'text-sky-700', 'border-sky-100']],
    ['active_progress', ['bg-blue-50', 'text-blue-700', 'border-blue-100']],
    ['closing_soon', ['bg-emerald-50', 'text-emerald-700', 'border-emerald-100']],
    ['contract_processing', ['bg-violet-50', 'text-violet-700', 'border-violet-100']],
    ['payment_processing', ['bg-amber-50', 'text-amber-700', 'border-amber-100']],
    ['invoice_processing', ['bg-cyan-50', 'text-cyan-700', 'border-cyan-100']],
    ['completed', ['bg-slate-50', 'text-slate-700', 'border-slate-100']],
    ['lost', ['bg-rose-50', 'text-rose-700', 'border-rose-100']],
  ] as const)('uses the board palette for %s', (stage, classes) => {
    const wrapper = mountJourneyTable([{ ...journeyFixture, current_board_stage: stage }])
    const badge = wrapper.get('[data-testid="business-journey-stage-badge"]')
    expect(badge.classes()).toEqual(expect.arrayContaining([...classes]))
  })
})
