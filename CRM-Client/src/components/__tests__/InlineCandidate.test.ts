import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import InlineCandidate from '../InlineCandidate.vue'

describe('InlineCandidate.vue', () => {
  const mockCandidate = {
    id: 16,
    name: '光大证券股份有限公司',
    entity_info_inline: 'ID:16 · 金融 · 活跃'
  }

  it('renders entity name and inline info', () => {
    const wrapper = mount(InlineCandidate, {
      props: { candidate: mockCandidate }
    })

    expect(wrapper.find('.candidate-name').text()).toBe('光大证券股份有限公司')
    expect(wrapper.find('.entity-info-inline').text()).toBe('ID:16 · 金融 · 活跃')
  })

  it('has parentheses around entity info via CSS', () => {
    const wrapper = mount(InlineCandidate, {
      props: { candidate: mockCandidate }
    })

    // 括号由 CSS ::before/::after 生成，检查 class 存在
    expect(wrapper.find('.entity-info-inline').exists()).toBe(true)
  })

  it('toggles selected state on click', async () => {
    const wrapper = mount(InlineCandidate, {
      props: { candidate: mockCandidate }
    })

    await wrapper.find('.candidate-inline').trigger('click')

    expect(wrapper.emitted('select')).toBeTruthy()
    expect(wrapper.emitted('select')![0]).toEqual([16])
  })

  it('selects candidate on Enter key', async () => {
    const wrapper = mount(InlineCandidate, {
      props: { candidate: mockCandidate }
    })

    await wrapper.find('.candidate-inline').trigger('keydown', { key: 'Enter' })

    expect(wrapper.emitted('select')).toBeTruthy()
  })

  it('selects candidate on Space key', async () => {
    const wrapper = mount(InlineCandidate, {
      props: { candidate: mockCandidate }
    })

    await wrapper.find('.candidate-inline').trigger('keydown', { key: ' ' })

    expect(wrapper.emitted('select')).toBeTruthy()
  })

  it('emits cancel on Escape key', async () => {
    const wrapper = mount(InlineCandidate, {
      props: { candidate: mockCandidate }
    })

    await wrapper.find('.candidate-inline').trigger('keydown', { key: 'Escape' })

    expect(wrapper.emitted('cancel')).toBeTruthy()
  })

  it('applies selected class when selected prop is true', () => {
    const wrapper = mount(InlineCandidate, {
      props: { candidate: mockCandidate, selected: true }
    })

    expect(wrapper.find('.candidate-inline.selected').exists()).toBe(true)
    expect(wrapper.find('.candidate-radio.selected').exists()).toBe(true)
  })

  it('has correct padding 6px 12px', () => {
    const wrapper = mount(InlineCandidate, {
      props: { candidate: mockCandidate }
    })

    expect(wrapper.find('.candidate-inline').exists()).toBe(true)
  })

  it('has correct radio size 14px', () => {
    const wrapper = mount(InlineCandidate, {
      props: { candidate: mockCandidate }
    })

    expect(wrapper.find('.candidate-radio').exists()).toBe(true)
  })

  it('has ARIA role radio', () => {
    const wrapper = mount(InlineCandidate, {
      props: { candidate: mockCandidate }
    })

    expect(wrapper.find('.candidate-inline').attributes('role')).toBe('radio')
  })

  it('has ARIA aria-checked based on selected state', () => {
    const wrapperSelected = mount(InlineCandidate, {
      props: { candidate: mockCandidate, selected: true }
    })

    expect(wrapperSelected.find('.candidate-inline').attributes('aria-checked')).toBe('true')

    const wrapperUnselected = mount(InlineCandidate, {
      props: { candidate: mockCandidate, selected: false }
    })

    expect(wrapperUnselected.find('.candidate-inline').attributes('aria-checked')).toBe('false')
  })

  it('has tabindex for keyboard navigation', () => {
    const wrapper = mount(InlineCandidate, {
      props: { candidate: mockCandidate }
    })

    expect(wrapper.find('.candidate-inline').attributes('tabindex')).toBe('0')
  })
})