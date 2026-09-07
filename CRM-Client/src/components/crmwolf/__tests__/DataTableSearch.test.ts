import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DataTableSearch from '../DataTableSearch.vue'

describe('DataTableSearch', () => {
  it('keeps input as a draft and only publishes it after an explicit submit', async () => {
    const wrapper = mount(DataTableSearch, {
      props: {
        modelValue: '',
        placeholder: '搜索编号、客户、合同',
      },
    })
    const input = wrapper.get('input')

    await input.setValue('  Alpha  ')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(wrapper.emitted('search')).toBeUndefined()

    await input.trigger('submit')
    expect(wrapper.emitted('update:modelValue')).toEqual([['Alpha']])
    expect(wrapper.emitted('search')).toEqual([['Alpha']])
  })

  it('keeps the compact focus ring without a white offset halo', () => {
    const wrapper = mount(DataTableSearch, {
      props: { modelValue: '' },
    })

    const inputGroup = wrapper.get('[data-slot="input-group"]')
    const input = wrapper.get('input')
    const focusOffsetClass = 'has-[[data-slot=input-group-control]:focus-visible]:ring-offset-0'

    expect(inputGroup.classes()).toContain(focusOffsetClass)
    expect(inputGroup.classes()).not.toContain('has-[[data-slot=input-group-control]:focus-visible]:ring-offset-2')
    expect(input.classes()).toContain('focus-visible:ring-offset-0')
  })

  it('uses the input group button loading state', () => {
    const wrapper = mount(DataTableSearch, {
      props: {
        modelValue: 'Alpha',
        loading: true,
      },
    })

    const submitButton = wrapper.findAll('button').find((button) => button.attributes('type') === 'submit')

    expect(submitButton).toBeDefined()
    expect(submitButton?.attributes('disabled')).toBeDefined()
    expect(submitButton?.attributes('aria-busy')).toBe('true')

    const clearButton = wrapper.find('[data-testid="data-table-search-clear"]')
    expect(clearButton.attributes('disabled')).toBeDefined()
  })

  it('matches toolbar typography and icon sizing', () => {
    const wrapper = mount(DataTableSearch, {
      props: { modelValue: 'Alpha' },
    })

    expect(wrapper.get('input').classes()).toContain('text-wolf-auxiliary')
    for (const icon of wrapper.findAll('svg')) {
      expect(icon.classes()).toEqual(expect.arrayContaining(['h-4', 'w-4']))
    }
  })

  it('clears the draft and emits a reset action', async () => {
    const wrapper = mount(DataTableSearch, {
      props: { modelValue: 'Alpha' },
    })

    await wrapper.get('[data-testid="data-table-search-clear"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([['']])
    expect(wrapper.emitted('clear')).toHaveLength(1)
    expect(wrapper.emitted('search')).toBeUndefined()
  })
})
