/**
 * PreviewField.vue 单元测试
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PreviewField from '../PreviewField.vue'

describe('PreviewField', () => {
  it('renders label and value correctly', () => {
    const wrapper = mount(PreviewField, {
      props: {
        label: '客户名称',
        value: '张三公司',
        type: 'text'
      }
    })

    expect(wrapper.find('.preview-field__label').text()).toBe('客户名称')
    expect(wrapper.find('.preview-field__value').text()).toBe('张三公司')
  })

  it('renders empty value placeholder', () => {
    const wrapper = mount(PreviewField, {
      props: {
        label: '备注',
        value: null,
        type: 'text',
        isEmpty: true
      }
    })

    expect(wrapper.find('.preview-field__value').text()).toBe('-')
    expect(wrapper.find('.preview-field__value').classes()).toContain('preview-field__value--empty')
  })

  it('renders entity type with link style', () => {
    const wrapper = mount(PreviewField, {
      props: {
        label: '客户',
        value: '张三公司',
        type: 'entity',
        entityType: 'customer'
      }
    })

    expect(wrapper.find('.preview-field__value').classes()).toContain('preview-field__value--entity')
  })

  it('does not apply entity style when empty', () => {
    const wrapper = mount(PreviewField, {
      props: {
        label: '客户',
        value: null,
        type: 'entity',
        isEmpty: true
      }
    })

    expect(wrapper.find('.preview-field__value').classes()).toContain('preview-field__value--empty')
    expect(wrapper.find('.preview-field__value').classes()).not.toContain('preview-field__value--entity')
  })
})