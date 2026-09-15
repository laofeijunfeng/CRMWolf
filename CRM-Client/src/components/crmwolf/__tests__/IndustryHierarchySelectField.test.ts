import { DOMWrapper, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import IndustryHierarchySelectField from '../IndustryHierarchySelectField.vue'

Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
  configurable: true,
  value: () => undefined,
})

const hierarchy = {
  internet: {
    name: '互联网',
    children: [
      { code: 'internet_saas', name: 'SaaS公司' },
      { code: 'internet_social', name: '社交媒体' },
    ],
  },
}

const mountedWrappers: VueWrapper[] = []

function mountField(options: Parameters<typeof mount>[1]): VueWrapper {
  const wrapper = mount(IndustryHierarchySelectField, options)
  mountedWrappers.push(wrapper)
  return wrapper
}

function getSearchInput(): HTMLInputElement {
  const searchInput = document.body.querySelector('input[placeholder="搜索行业"]')
  if (!(searchInput instanceof HTMLInputElement)) {
    throw new Error('搜索框未渲染')
  }
  return searchInput
}

afterEach(() => {
  mountedWrappers.splice(0).forEach((wrapper) => {
    wrapper.unmount()
  })
  document.body.innerHTML = ''
})

describe('IndustryHierarchySelectField', () => {
  it('renders the selected full path', () => {
    const wrapper = mountField({
      props: { modelValue: 'internet_saas', hierarchy },
    })
    expect(wrapper.get('button[role="combobox"]').text()).toContain('互联网 / SaaS公司')
    wrapper.unmount()
  })

  it('searches both primary and secondary names', async () => {
    const wrapper = mountField({
      props: { modelValue: '', hierarchy },
      attachTo: document.body,
    })
    await wrapper.get('button[role="combobox"]').trigger('click')
    await new DOMWrapper(getSearchInput()).setValue('互联网')
    expect(document.body.textContent).toContain('SaaS公司')
    await new DOMWrapper(getSearchInput()).setValue('社交媒体')
    expect(document.body.textContent).toContain('社交媒体')
    wrapper.unmount()
  })

  it('emits a child code', async () => {
    const wrapper = mountField({
      props: { modelValue: '', hierarchy },
      attachTo: document.body,
    })
    await wrapper.get('button[role="combobox"]').trigger('click')
    const option = Array.from(document.body.querySelectorAll('[role="option"]')).find((element) => element.textContent?.includes('社交媒体') === true)
    expect(option).toBeInstanceOf(HTMLElement)
    if (!(option instanceof HTMLElement)) throw new Error('行业选项未渲染')
    option.click()
    const childEmitted = wrapper.emitted('update:modelValue')
    expect(childEmitted?.[childEmitted.length - 1]).toEqual(['internet_social'])
    wrapper.unmount()
  })

  it('emits a primary code for a group without children', async () => {
    const wrapper = mountField({
      props: { modelValue: '', hierarchy: { manufacturing: { name: '制造业', children: [] } } },
      attachTo: document.body,
    })
    await wrapper.get('button[role="combobox"]').trigger('click')
    const option = Array.from(document.body.querySelectorAll('[role="option"]')).find((element) => element.textContent?.includes('制造业') === true)
    expect(option).toBeInstanceOf(HTMLElement)
    if (!(option instanceof HTMLElement)) throw new Error('一级行业选项未渲染')
    option.click()
    const primaryEmitted = wrapper.emitted('update:modelValue')
    expect(primaryEmitted?.[primaryEmitted.length - 1]).toEqual(['manufacturing'])
    wrapper.unmount()
  })

  it('renders a retained inactive value as a disabled option', async () => {
    const wrapper = mountField({
      props: {
        modelValue: 'legacy_industry',
        hierarchy: {},
        retainedIndustryInfo: { code: 'legacy_industry', name: '传统行业 / 已停用' },
      },
      attachTo: document.body,
    })
    await wrapper.get('button[role="combobox"]').trigger('click')
    const option = Array.from(document.body.querySelectorAll('[role="option"]')).find((element) => element.textContent?.includes('传统行业 / 已停用') === true)
    expect(option?.hasAttribute('data-disabled')).toBe(true)
    wrapper.unmount()
  })

  it('exposes the supplied trigger id, visible label, and described-by state', () => {
    const wrapper = mountField({
      props: {
        modelValue: 'internet_saas',
        hierarchy,
        id: 'customer-industry',
        error: '行业代码无效',
      },
    })
    const trigger = wrapper.get('button[role="combobox"]')
    expect(wrapper.get('label[for="customer-industry"]').text()).toBe('行业')
    expect(trigger.attributes('id')).toBe('customer-industry')
    expect(trigger.attributes('role')).toBe('combobox')
    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(trigger.attributes('aria-invalid')).toBe('true')
    expect(trigger.attributes('aria-describedby')).toBe('customer-industry-error')
    expect(wrapper.get('#customer-industry-error').text()).toContain('行业代码无效')
    expect(trigger.classes()).toContain('max-[767px]:h-input-mobile')
    expect(trigger.classes()).toContain('max-[767px]:min-h-input-mobile')
    wrapper.unmount()
  })

  it('uses shared input height and its own vertical scroll', async () => {
    const wrapper = mountField({
      props: { modelValue: '', hierarchy },
      attachTo: document.body,
    })
    const trigger = wrapper.get('button[role="combobox"]')
    expect(trigger.classes()).toContain('h-input-desktop')
    expect(trigger.classes()).toContain('min-h-input-desktop')
    expect(trigger.classes()).toContain('max-[767px]:h-input-mobile')
    expect(trigger.classes()).toContain('max-[767px]:min-h-input-mobile')
    await trigger.trigger('click')
    const searchInput = getSearchInput()
    expect(searchInput.className).toContain('h-input-desktop')
    expect(searchInput.className).toContain('max-[767px]:h-input-mobile')
    expect(searchInput.closest('[class*="overflow-y-auto"]')).toBeInstanceOf(HTMLElement)
    wrapper.unmount()
  })

  it('keeps the retained current value while the hierarchy is loading', () => {
    const wrapper = mountField({
      props: {
        modelValue: 'legacy_industry',
        hierarchy: {},
        retainedIndustryInfo: { code: 'legacy_industry', name: '传统行业 / 已停用' },
        loading: true,
      },
    })
    const trigger = wrapper.get('button[role="combobox"]')
    expect(trigger.text()).toContain('传统行业 / 已停用')
    expect(trigger.attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('keeps the retained current value when hierarchy loading fails', () => {
    const wrapper = mountField({
      props: {
        modelValue: 'legacy_industry',
        hierarchy: {},
        retainedIndustryInfo: { code: 'legacy_industry', name: '传统行业 / 已停用' },
        error: '行业加载失败',
        disabled: true,
      },
    })
    const trigger = wrapper.get('button[role="combobox"]')
    expect(trigger.text()).toContain('传统行业 / 已停用')
    expect(trigger.attributes('disabled')).toBeDefined()
    expect(trigger.attributes('aria-invalid')).toBe('true')
    expect(wrapper.get('[role="alert"]').text()).toContain('行业加载失败')
    wrapper.unmount()
  })

  it('keeps active options selectable when a field validation error is present', async () => {
    const wrapper = mountField({
      props: {
        modelValue: '',
        hierarchy,
        error: '行业代码无效',
        disabled: false,
      },
      attachTo: document.body,
    })
    await wrapper.get('button[role="combobox"]').trigger('click')
    const option = Array.from(document.body.querySelectorAll('[role="option"]')).find((element) => element.textContent?.includes('社交媒体') === true)
    expect(option).toBeInstanceOf(HTMLElement)
    if (!(option instanceof HTMLElement)) throw new Error('行业选项未渲染')
    option.click()
    const validationEmitted = wrapper.emitted('update:modelValue')
    expect(validationEmitted?.[validationEmitted.length - 1]).toEqual(['internet_social'])
    wrapper.unmount()
  })
})
