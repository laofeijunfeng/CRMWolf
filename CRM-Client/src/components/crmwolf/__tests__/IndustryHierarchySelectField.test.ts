import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import IndustryHierarchySelectField from '../IndustryHierarchySelectField.vue'
Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
  configurable: true,
  value: () => undefined,
})

const hierarchy = {
  internet: {
    name: '互联网',
    children: [
      { code: 'internet.enterprise', name: '企业服务' },
      { code: 'internet.software', name: '软件服务' },
    ],
  },
}

describe('IndustryHierarchySelectField', () => {
  it('renders the selected full path and grouped active options', async () => {
    const wrapper = mount(IndustryHierarchySelectField, {
      props: { modelValue: 'internet.enterprise', hierarchy },
    })
    const trigger = wrapper.get('button[role="combobox"]')
    expect(trigger.classes()).toContain('h-input-mobile')
    expect(trigger.classes()).toContain('min-h-input-mobile')
    await trigger.trigger('click')
    const searchInput = document.body.querySelector('input[placeholder="搜索行业"]')
    expect(searchInput).toBeInstanceOf(HTMLInputElement)
    if (!(searchInput instanceof HTMLInputElement)) throw new Error('search input was not rendered')
    expect(searchInput.classList).toContain('h-input-mobile')
    expect(searchInput.classList).toContain('min-h-input-mobile')
    expect(document.body.textContent).toContain('互联网')
    expect(document.body.textContent).toContain('企业服务')
    wrapper.unmount()
  })

  it('emits the selected child code', async () => {
    const wrapper = mount(IndustryHierarchySelectField, {
      props: { modelValue: '', hierarchy },
      attachTo: document.body,
    })
    await wrapper.get('button[role="combobox"]').trigger('click')
    const option = Array.from(document.body.querySelectorAll('[role="option"]'))
      .find((element) => element.textContent?.includes('软件服务') === true)
    expect(option).toBeInstanceOf(HTMLElement)
    if (!(option instanceof HTMLElement)) throw new Error('软件服务 option was not rendered')
    option.click()
    const emittedEvents = wrapper.emitted('update:modelValue') as unknown[][] | undefined
    expect(emittedEvents?.[emittedEvents.length - 1]).toEqual(['internet.software'])
    wrapper.unmount()
  })
  it('retains an inactive current code when the hierarchy is empty', async () => {
    const wrapper = mount(IndustryHierarchySelectField, {
      props: { modelValue: 'legacy.industry', hierarchy: {} },
      attachTo: document.body,
    })
    expect(wrapper.get('button[role="combobox"]').text()).toContain('legacy.industry')
    await wrapper.get('button[role="combobox"]').trigger('click')
    const option = Array.from(document.body.querySelectorAll('[role="option"]'))
      .find((element) => element.textContent?.includes('legacy.industry') === true)
    expect(option).toBeInstanceOf(HTMLElement)
    if (!(option instanceof HTMLElement)) throw new Error('legacy.industry option was not rendered')
    expect(option.hasAttribute('data-disabled')).toBe(true)
    wrapper.unmount()
  })
  it('retains an inactive current code while hierarchy loading fails', async () => {
    const wrapper = mount(IndustryHierarchySelectField, {
      props: { modelValue: 'legacy.industry', hierarchy: {}, error: '行业加载失败' },
      attachTo: document.body,
    })
    await wrapper.get('button[role="combobox"]').trigger('click')
    const option = Array.from(document.body.querySelectorAll('[role="option"]'))
      .find((element) => element.textContent?.includes('legacy.industry') === true)
    expect(option).toBeInstanceOf(HTMLElement)
    if (!(option instanceof HTMLElement)) throw new Error('legacy.industry option was not rendered during error state')
    expect(option.hasAttribute('data-disabled')).toBe(true)
    expect(document.body.textContent).toContain('行业加载失败')
    wrapper.unmount()
  })
})
