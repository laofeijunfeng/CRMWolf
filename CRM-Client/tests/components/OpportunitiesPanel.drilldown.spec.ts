import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import OpportunitiesPanel from '@/components/panels/OpportunitiesPanel.vue'
import type { OpportunityListResponse } from '@/api/opportunity'

const routerPush = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush }),
}))

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

vi.mock('@/components/crmwolf/ListCard.vue', () => ({
  default: defineComponent({
    name: 'ListCard',
    props: {
      title: String,
      items: { type: Array, required: true },
      emptyText: String,
      rowInteractive: Boolean,
    },
    emits: ['row-click'],
    setup: (props, { emit, slots }) => () => h('section', [
      h('div', slots.headerActions?.()),
      ...(props.items as OpportunityListResponse[]).map(item => h('div', {
        'data-testid': `opportunity-row-${item.id}`,
        'data-row-interactive': String(props.rowInteractive),
        tabindex: props.rowInteractive ? 0 : undefined,
        onClick: () => emit('row-click', item),
      }, [
        h('div', slots.itemMain?.({ item })),
        h('div', slots.itemActions?.({ item })),
      ])),
    ]),
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

describe('OpportunitiesPanel drilldown behavior', () => {
  it('emits view-opportunity when an opportunity row is clicked instead of routing away', async () => {
    const wrapper = mount(OpportunitiesPanel, {
      props: {
        customerId: 19,
        opportunities: [opportunityFixture()],
      },
    })

    const row = wrapper.get('[data-testid="opportunity-row-88"]')
    expect(row.attributes('data-row-interactive')).toBe('true')

    await row.trigger('click')

    expect(wrapper.emitted('view-opportunity')).toEqual([[88]])
    expect(routerPush).not.toHaveBeenCalled()
  })

  it('emits open-full-page from the explicit full-detail button without triggering row drilldown', async () => {
    const wrapper = mount(OpportunitiesPanel, {
      props: {
        customerId: 19,
        opportunities: [opportunityFixture()],
      },
    })

    await wrapper.get('[aria-label="打开商机 CRM 升级项目 完整详情"]').trigger('click')

    expect(wrapper.emitted('open-full-page')).toEqual([[88]])
    expect(wrapper.emitted('view-opportunity')).toBeUndefined()
    expect(routerPush).not.toHaveBeenCalled()
  })
})
