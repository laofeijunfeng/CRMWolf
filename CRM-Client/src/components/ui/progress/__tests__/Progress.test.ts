import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import Progress from '../Progress.vue'

describe('Progress indicator classes', () => {
  it('keeps bg-primary as the default indicator fill', () => {
    const wrapper = mount(Progress, { props: { modelValue: 42 } })

    expect(wrapper.get('[role="progressbar"] > div').classes()).toContain('bg-primary')
  })

  it('uses a caller-provided indicator class without the default fill', () => {
    const wrapper = mount(Progress, {
      props: {
        modelValue: 42,
        indicatorClass: 'bg-yellow-500'
      }
    })

    const indicator = wrapper.get('[role="progressbar"] > div')
    expect(indicator.classes()).toContain('bg-yellow-500')
    expect(indicator.classes()).not.toContain('bg-primary')
  })
})
