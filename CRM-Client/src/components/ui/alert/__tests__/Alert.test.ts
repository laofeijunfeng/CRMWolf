import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import Alert from '../Alert.vue'

describe('Alert tone', () => {
  it('exposes the status tone that derives its tint and text colour', () => {
    const tones = { success: 'success', warning: 'warning', info: 'info', destructive: 'danger' } as const
    const variants = Object.keys(tones) as (keyof typeof tones)[]

    for (const variant of variants) {
      const wrapper = mount(Alert, { props: { variant } })
      expect(wrapper.get('[role="alert"]').attributes('data-tone'), variant).toBe(tones[variant])
    }
  })

  it('stays neutral for the default variant', () => {
    const wrapper = mount(Alert, { slots: { default: '内容' } })

    expect(wrapper.get('[role="alert"]').attributes('data-tone')).toBeUndefined()
  })
})
