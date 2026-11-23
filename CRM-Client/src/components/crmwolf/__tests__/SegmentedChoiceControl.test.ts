import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SegmentedChoiceControl from '../SegmentedChoiceControl.vue'

describe('SegmentedChoiceControl', () => {
  it('renders described options as two-line tiles and keeps a disabled option disabled', () => {
    const wrapper = mount(SegmentedChoiceControl, {
      props: {
        modelValue: 'WECHAT',
        options: [
          { value: 'PHONE', label: '电话跟进', description: '电话沟通' },
          { value: 'OFFLINE', label: '线下会议', description: '原文没有提到线下', disabled: true },
          { value: 'WECHAT', label: '微信跟进', description: '微信 / 企业微信' },
        ],
      },
    })

    const options = wrapper.findAll('[role="radio"]')
    expect(options.map((option) => option.text())).toEqual(['电话跟进电话沟通', '线下会议原文没有提到线下', '微信跟进微信 / 企业微信'])
    expect(options[0]?.classes()).toContain('segmented-choice__option--described')
    expect(options[1]?.attributes('disabled')).toBeDefined()
    expect(options[2]?.attributes('aria-checked')).toBe('true')
    expect(options[2]?.classes()).toContain('segmented-choice__option--active')
  })

  it('emits the clicked value for a single choice and the whole selection for multiple', async () => {
    const single = mount(SegmentedChoiceControl, {
      props: { modelValue: '', options: [{ value: 'A', label: '甲' }, { value: 'B', label: '乙' }] },
    })
    await single.findAll('[role="radio"]')[1]?.trigger('click')
    expect(single.emitted('update:modelValue')).toEqual([['B']])

    const multiple = mount(SegmentedChoiceControl, {
      props: { multiple: true, modelValue: ['A'], options: [{ value: 'A', label: '甲' }, { value: 'B', label: '乙' }] },
    })
    expect(multiple.findAll('[role="checkbox"]').map((option) => option.attributes('aria-checked'))).toEqual(['true', 'false'])
    await multiple.findAll('[role="checkbox"]')[1]?.trigger('click')
    expect(multiple.emitted('update:modelValue')).toEqual([[['A', 'B']]])
  })

  it('names each group once above its options', () => {
    const wrapper = mount(SegmentedChoiceControl, {
      props: {
        modelValue: '',
        options: [
          { value: 'ONLINE', label: '线上会议', group: '会议' },
          { value: 'OFFLINE', label: '线下会议', group: '会议' },
          { value: 'WECHAT', label: '微信跟进', group: '跟进' },
        ],
      },
    })
    expect(wrapper.findAll('[role="radiogroup"] > p').map((heading) => heading.text())).toEqual(['会议', '跟进'])
  })
})
