import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import CheckboxField from '@/components/crmwolf/CheckboxField.vue'
import MultiSelectField from '@/components/crmwolf/MultiSelectField.vue'
import MultiSelect from '@/components/crmwolf/MultiSelect.vue'

describe('CheckboxField / MultiSelectField', () => {
  it('ties the label to the checkbox and emits the boolean', async () => {
    const wrapper = mount(CheckboxField, { props: { id: 'confirmed', label: '已确认', modelValue: false } })

    expect(wrapper.get('label').attributes('for')).toBe('confirmed')
    // The label is the question: box first, text on its right, no 是/否 echo.
    expect(wrapper.text()).toBe('已确认')
    expect(wrapper.get('[role="checkbox"]').element.compareDocumentPosition(wrapper.get('label').element)
      & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    await wrapper.get('[role="checkbox"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[true]])
    wrapper.unmount()
  })

  it('preserves error and helper accessibility attributes on CheckboxField', () => {
    const wrapper = mount(CheckboxField, {
      props: {
        id: 'default-deploy',
        label: '设为默认部署',
        modelValue: false,
        required: true,
        helperText: '每个客户仅可设一个默认部署',
        error: '请确认部署环境',
      },
    })

    const checkbox = wrapper.get('[role="checkbox"]')
    expect(checkbox.attributes('aria-invalid')).toBe('true')
    expect(checkbox.attributes('aria-required')).toBe('true')
    expect(checkbox.attributes('aria-describedby')).toBe('default-deploy-error default-deploy-description')
    expect(wrapper.get('[role="alert"]').text()).toBe('请确认部署环境')
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
