import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import CheckboxField from '@/components/crmwolf/CheckboxField.vue'
import MultiSelectField from '@/components/crmwolf/MultiSelectField.vue'
import MultiSelect from '@/components/crmwolf/MultiSelect.vue'

describe('CheckboxField / MultiSelectField', () => {
  it('ties the label to the checkbox and emits the boolean', async () => {
    const wrapper = mount(CheckboxField, { props: { id: 'confirmed', label: '已确认', modelValue: false } })

    expect(wrapper.get('label').attributes('for')).toBe('confirmed')
    await wrapper.get('[role="checkbox"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[true]])
    wrapper.unmount()
  })

  it('labels the multi-select trigger and forwards the selection', () => {
    const wrapper = mount(MultiSelectField, {
      props: { id: 'tags', label: '标签', modelValue: [], options: [{ value: 'a', label: '甲' }, { value: 'b', label: '乙' }] },
    })

    expect(wrapper.get('button[role="combobox"]').attributes('aria-labelledby')).toBe('tags-label')
    wrapper.findComponent(MultiSelect).vm.$emit('update:modelValue', ['b'])
    expect(wrapper.emitted('update:modelValue')).toEqual([[['b']]])
    wrapper.unmount()
  })
})
