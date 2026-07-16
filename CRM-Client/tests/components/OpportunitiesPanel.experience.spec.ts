import { describe, expect, it, vi, afterEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'
import OpportunitiesPanel from '@/components/panels/OpportunitiesPanel.vue'
import type { OpportunityListResponse } from '@/api/opportunity'

vi.mock('@/components/StatusBadge.vue', () => ({
  default: defineComponent({ name: 'StatusBadge', setup: () => () => h('span', 'status') }),
}))

vi.mock('@/components/ui/button', () => ({
  Button: defineComponent({
    name: 'Button',
    props: { type: String, variant: String, size: String },
    setup: (props, { slots, attrs }) => () => h('button', { ...attrs, type: props.type ?? 'button' }, slots.default?.()),
  }),
}))

const opportunityFixture = (): OpportunityListResponse => ({
  id: 88,
  opportunity_name: 'CRM 升级项目',
  customer_id: 19,
  procurement_method_id: null,
  procurement_method_info: null,
  total_amount: 320000,
  user_count: 20,
  unit_price: 16000,
  license_type: 'SUBSCRIPTION',
  subscription_years: 1,
  purchase_type: 'NEW',
  decision_maker_count: 1,
  expected_closing_date: '2026-08-30',
  stage_id: 1,
  stage_info: {
    id: 1,
    stage_name: '方案沟通',
    win_probability: 50,
    is_default: 0,
  },
  status: 0,
  created_time: '2026-07-15T00:00:00.000Z',
  last_modified_time: '2026-07-15T00:00:00.000Z',
})

describe('OpportunitiesPanel experience behavior', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('highlights and restores focus to the previously viewed opportunity row', async () => {
    const wrapper = mount(OpportunitiesPanel, {
      attachTo: document.body,
      props: {
        customerId: 19,
        opportunities: [opportunityFixture()],
        highlightedOpportunityId: 88,
        restoreFocusOpportunityId: 88,
      },
    })

    await flushPromises()
    await nextTick()

    const row = wrapper.get('[data-list-card-row-id="88"]')
    expect(row.attributes('data-highlighted')).toBe('true')
    expect(document.activeElement).toBe(row.element)
  })

  it('shows an empty-state create action when there are no opportunities', () => {
    const wrapper = mount(OpportunitiesPanel, {
      props: {
        customerId: 19,
        opportunities: [],
      },
    })

    expect(wrapper.get('[data-testid="empty-create-opportunity"]').text()).toContain('新建商机')
  })
})
