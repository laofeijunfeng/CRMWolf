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
    expect(wrapper.text()).toContain('互联网 / 企业服务')
    await wrapper.get('button[role="combobox"]').trigger('click')
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
})
