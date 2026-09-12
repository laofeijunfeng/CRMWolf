import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ActionCreateCustomerPanel from '../nodeConfigPanels/ActionCreateCustomerPanel.vue'
import ActionCreateContactPanel from '../nodeConfigPanels/ActionCreateContactPanel.vue'
import ActionCreateOpportunityPanel from '../nodeConfigPanels/ActionCreateOpportunityPanel.vue'

const SelectFieldStub = {
  props: ['id', 'modelValue', 'label', 'options'],
  emits: ['update:modelValue'],
  template: '<label><span>{{ label }}</span><select :id="id" :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><option v-for="option in options" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>',
}
const CheckboxStub = {
  props: ['checked'],
  emits: ['update:checked'],
  template: '<input type="checkbox" :checked="checked" @change="$emit(\'update:checked\', $event.target.checked)" />',
}
const global = { stubs: { SelectField: SelectFieldStub, Checkbox: CheckboxStub } }

describe('CRM workflow configuration panels', () => {
  it('updates customer fields through public patches only', async () => {
    const wrapper = mount(ActionCreateCustomerPanel, { props: { config: {} }, global })
    await wrapper.get('[data-testid="config-account-name"]').setValue('Acme')
    await wrapper.get('[data-testid="config-city"]').setValue('上海')
    await nextTick()
    expect(wrapper.emitted('update:config')).toEqual([[{ account_name: 'Acme' }], [{ city: '上海' }]])
  })

  it('updates contact fields and decision-maker flag through patches', async () => {
    const wrapper = mount(ActionCreateContactPanel, { props: { config: {} }, global })
    await wrapper.get('[data-testid="config-customer-ref"]').setValue('customer-1')
    await wrapper.get('[data-testid="config-contact-name"]').setValue('王总')
    await wrapper.get('[data-testid="config-contact-position"]').setValue('采购负责人')
    await wrapper.get('[data-testid="config-contact-mobile"]').setValue('13800138000')
    await wrapper.get('[data-testid="config-contact-decision-maker"]').setValue(true)
    expect(wrapper.emitted('update:config')).toEqual([
      [{ customer_ref: 'customer-1' }], [{ name: '王总' }], [{ position: '采购负责人' }], [{ mobile: '13800138000' }], [{ is_decision_maker: true }],
    ])
  })

  it('updates opportunity numeric fields through patches only', async () => {
    const wrapper = mount(ActionCreateOpportunityPanel, { props: { config: {} }, global })
    await wrapper.get('[data-testid="config-opportunity-customer-ref"]').setValue('customer-1')
    await wrapper.get('[data-testid="config-total-amount"]').setValue('12000')
    await wrapper.get('[data-testid="config-user-count"]').setValue('5')
    await wrapper.get('[data-testid="config-expected-closing-date"]').setValue('2026-12-31')
    expect(wrapper.emitted('update:config')).toEqual([
      [{ customer_ref: 'customer-1' }], [{ total_amount: 12000 }], [{ user_count: 5 }], [{ expected_closing_date: '2026-12-31' }],
    ])
  })
})
