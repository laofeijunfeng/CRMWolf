import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import type { PaymentPlanResponse } from '@/api/payment'

vi.mock('@/components/ui/sheet', () => ({
  Sheet: defineComponent({
    name: 'Sheet',
    props: { open: Boolean },
    emits: ['update:open'],
    setup: (props, { slots }) => () => props.open ? h('section', slots.default?.()) : null,
  }),
}))

vi.mock('@/components/ui/detail-sheet', () => ({
  DetailSheetContent: defineComponent({
    name: 'DetailSheetContent',
    setup: (_, { slots }) => () => h('div', slots.default?.()),
  }),
}))

vi.mock('@/components/panels/ContractDetailContent.vue', () => ({
  default: defineComponent({
    name: 'ContractDetailContent',
    props: {
      contractId: { type: Number, required: true },
      canApprove: Boolean,
    },
    emits: ['close', 'approve', 'reject', 'refresh', 'view-payment-plan'],
    setup: () => () => h('div'),
  }),
}))

import ContractDetailSheet from '@/views/ContractDetailSheet.vue'
import ContractDetailContent from '@/components/panels/ContractDetailContent.vue'

const paymentPlanFixture = (): PaymentPlanResponse => ({
  id: 41,
  contract_id: 31,
  stage_name: '首款',
  planned_amount: 50000,
  due_date: '2026-09-15',
  status: 'PENDING',
  payment_records: [],
  created_time: '2026-09-01T00:00:00',
  last_modified_time: '2026-09-01T00:00:00',
})

describe('ContractDetailSheet payment plan drilldown', () => {
  it('forwards the exact payment plan emitted by ContractDetailContent', async () => {
    const wrapper = mount(ContractDetailSheet, {
      props: { contractId: 31, visible: true },
    })
    const plan = paymentPlanFixture()

    wrapper.getComponent(ContractDetailContent).vm.$emit('view-payment-plan', plan)
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('view-payment-plan')).toEqual([[plan]])
    expect(wrapper.emitted('view-payment-plan')?.[0]?.[0]).toBe(plan)
  })
})
