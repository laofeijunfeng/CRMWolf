import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import Button from '../Button.vue'

describe('Button loading state', () => {
  it('disables the button and exposes a busy state while loading', () => {
    const wrapper = mount(Button, {
      props: { loading: true },
      slots: { default: '保存' },
    })

    const button = wrapper.get('button')
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.attributes('aria-disabled')).toBe('true')
    expect(button.attributes('aria-busy')).toBe('true')
    expect(button.text()).toContain('保存')
    expect(button.find('svg').exists()).toBe(true)
  })

  it('does not add a disabled attribute for an idle button', () => {
    const wrapper = mount(Button, {
      slots: { default: '继续' },
    })

    const button = wrapper.get('button')
    expect(button.attributes('disabled')).toBeUndefined()
    expect(button.attributes('aria-busy')).toBeUndefined()
  })
})
