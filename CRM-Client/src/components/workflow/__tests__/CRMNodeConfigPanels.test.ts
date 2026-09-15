import { nextTick } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ActionCreateCustomerPanel from '../nodeConfigPanels/ActionCreateCustomerPanel.vue'
import ActionCreateContactPanel from '../nodeConfigPanels/ActionCreateContactPanel.vue'
import ActionCreateOpportunityPanel from '../nodeConfigPanels/ActionCreateOpportunityPanel.vue'
import TriggerOpportunityStagePanel from '../nodeConfigPanels/TriggerOpportunityStagePanel.vue'
import procurementApi, { type ProcurementMethodWithStages } from '@/api/procurement'

vi.mock('@/api/procurement', () => ({
  default: {
    getProcurementMethods: vi.fn(),
    getProcurementMethod: vi.fn(),
  },
}))

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
  it('preserves numeric select values in contact patches', async () => {
    const wrapper = mount(ActionCreateContactPanel, { props: { config: {} }, global })
    const selectField = wrapper.findComponent(SelectFieldStub) as unknown as { vm: { $emit: (event: string, value: number) => void } }
    selectField.vm.$emit('update:modelValue', 2)
    await nextTick()
    expect(wrapper.emitted('update:config')).toContainEqual([{ gender: 2 }])
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
  it('emits null when optional opportunity numeric fields are cleared', async () => {
    const wrapper = mount(ActionCreateOpportunityPanel, { props: { config: { decision_maker_count: 3, procurement_method_id: 4, procurement_stage_id: 5 } }, global })
    await wrapper.get('[data-testid="config-decision-maker-count"]').setValue('')
    await wrapper.get('[data-testid="config-procurement-method-id"]').setValue('')
    await wrapper.get('[data-testid="config-procurement-stage-id"]').setValue('')

    expect(wrapper.emitted('update:config')).toEqual([
      [{ decision_maker_count: null }],
      [{ procurement_method_id: null }],
      [{ procurement_stage_id: null }],
    ])
  })
  it('maps backend template_code values into trigger stage options', async () => {
    vi.mocked(procurementApi.getProcurementMethods).mockResolvedValue([{
      id: 1,
      code: 'SALES',
      name: '销售流程',
      is_active: 1,
      sort_order: 1,
      created_time: '2026-09-13T00:00:00',
      updated_time: '2026-09-13T00:00:00',
    }])
    const backendMethod = {
      id: 1,
      code: 'SALES',
      name: '销售流程',
      is_active: 1,
      sort_order: 1,
      created_time: '2026-09-13T00:00:00',
      updated_time: '2026-09-13T00:00:00',
      stage_templates: [{
        id: 11,
        procurement_method_id: 1,
        template_code: 'QUOTE',
        stage_name: '报价确认',
        win_probability: 50,
        sort_order: 1,
        is_default_start: 0,
        can_skip: 0,
        description: null,
        version: 1,
        version_lock: 0,
        created_by: '1',
        updated_by: null,
        created_time: '2026-09-13T00:00:00',
        updated_time: '2026-09-13T00:00:00',
      }],
    } as unknown as ProcurementMethodWithStages
    vi.mocked(procurementApi.getProcurementMethod).mockResolvedValue(backendMethod)

    const wrapper = mount(TriggerOpportunityStagePanel, { props: { config: {} }, global })
    await flushPromises()

    const toStage = wrapper.findAllComponents(SelectFieldStub).find(select => select.props('id') === 'config-select-to-stage')
    if (toStage === undefined) throw new Error('目标阶段选择器缺失')
    expect(toStage.props('options')).toEqual([{ value: 'QUOTE', label: '报价确认' }])
  })
})
