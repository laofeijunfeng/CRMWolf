import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

vi.mock('@/components/ui/sheet', () => ({
  Sheet: defineComponent({
    name: 'Sheet',
    props: { open: Boolean },
    emits: ['update:open'],
    setup: (_, { slots }) => () => h('section', slots.default?.()),
  }),
}))
vi.mock('@/components/ui/detail-sheet', () => ({
  DetailSheetContent: defineComponent({
    name: 'DetailSheetContent',
    setup: (_, { slots }) => () => h('div', slots.default?.()),
  }),
}))
vi.mock('@/components/business-journey/DealJourneyDetailHost.vue', () => ({
  default: defineComponent({
    name: 'DealJourneyDetailHost',
    props: { customerId: String, customerName: String, journeyId: String },
    emits: ['close', 'refresh', 'view-customer'],
    setup: props => () => h('div', { 'data-customer-id': props.customerId, 'data-journey-id': props.journeyId }),
  }),
}))
vi.mock('@/views/CustomerDetailSheet.vue', () => ({
  default: defineComponent({ name: 'CustomerDetailSheet', setup: () => () => h('div') }),
}))

import DealJourneyDetailSheet from '@/views/DealJourneyDetailSheet.vue'
import DealJourneyDetailHost from '@/components/business-journey/DealJourneyDetailHost.vue'
import CustomerDetailSheet from '@/views/CustomerDetailSheet.vue'

function mountSheet() {
  return mount(DealJourneyDetailSheet, {
    props: { customerId: 'cus_test', customerName: '测试客户', journeyId: 'djy_test', visible: true },
  })
}

describe('DealJourneyDetailSheet', () => {
  it('wraps the Host directly and never renders CustomerDetailSheet', () => {
    const wrapper = mountSheet()

    expect(wrapper.findComponent(DealJourneyDetailHost).exists()).toBe(true)
    expect(wrapper.getComponent(DealJourneyDetailHost).props()).toMatchObject({
      customerId: 'cus_test',
      customerName: '测试客户',
      journeyId: 'djy_test',
    })
    expect(wrapper.findComponent(CustomerDetailSheet).exists()).toBe(false)
  })

  it('unmounts the Sheet boundary and Host when hidden', async () => {
    const wrapper = mountSheet()

    await wrapper.setProps({ visible: false })

    expect(wrapper.findComponent({ name: 'Sheet' }).exists()).toBe(false)
    expect(wrapper.findComponent(DealJourneyDetailHost).exists()).toBe(false)
  })

  it('closes the sheet from the Host and forwards refresh and customer events', async () => {
    const wrapper = mountSheet()
    const host = wrapper.getComponent(DealJourneyDetailHost)

    host.vm.$emit('refresh')
    host.vm.$emit('view-customer', 'cus_other')
    host.vm.$emit('close')
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('refresh')).toHaveLength(1)
    expect(wrapper.emitted('view-customer')).toEqual([['cus_other']])
    expect(wrapper.emitted('update:visible')).toEqual([[false]])
  })
})
