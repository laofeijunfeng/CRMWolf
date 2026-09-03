import { mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import FormErrorSummary, { type FormErrorSummaryItem } from '../FormErrorSummary.vue'
import LiveRegion from '../LiveRegion.vue'
import SegmentedChoiceControl from '../SegmentedChoiceControl.vue'

const mountedWrappers: VueWrapper[] = []

type MountableComponent = typeof FormErrorSummary | typeof LiveRegion | typeof SegmentedChoiceControl

const mountAndTrack = (component: MountableComponent, options?: Parameters<typeof mount>[1]): VueWrapper => {
  const wrapper = mount(component, {
    attachTo: document.body,
    ...options,
  })
  mountedWrappers.push(wrapper)
  return wrapper
}

afterEach(() => {
  mountedWrappers.forEach((wrapper) => wrapper.unmount())
  mountedWrappers.length = 0
  document.body.innerHTML = ''
})

describe('FormErrorSummary', () => {
  const items: FormErrorSummaryItem[] = [
    { field: 'name', label: '客户名称', message: '请输入客户名称', targetId: 'customer-name' },
    { field: 'owner', label: '负责人', message: '请选择负责人' },
  ]

  it('renders a live alert with business field labels and validation messages', () => {
    const wrapper = mountAndTrack(FormErrorSummary, { props: { items } })

    const summary = wrapper.get('[role="alert"]')
    expect(summary.attributes('aria-live')).toBe('assertive')
    expect(summary.attributes('aria-atomic')).toBe('true')
    expect(summary.text()).toContain('客户名称：请输入客户名称')
    expect(summary.text()).toContain('负责人：请选择负责人')
    expect(wrapper.findAll('button.form-error-summary__link')).toHaveLength(1)
  })

  it('focuses and scrolls the referenced field when an error is selected', async () => {
    const wrapper = mountAndTrack(FormErrorSummary, { props: { items: [items[0]] } })
    const target = document.createElement('input')
    target.id = 'customer-name'
    target.scrollIntoView = (): void => undefined
    document.body.appendChild(target)

    await wrapper.get('button.form-error-summary__link').trigger('click')

    expect(document.activeElement).toBe(target)
  })

  it('renders nothing when there are no validation errors', () => {
    const wrapper = mountAndTrack(FormErrorSummary, { props: { items: [] } })

    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })
})

describe('LiveRegion', () => {
  it('exposes the configured announcement semantics', () => {
    const wrapper = mountAndTrack(LiveRegion, {
      props: { politeness: 'polite', role: 'status', atomic: true },
      slots: { default: '正在刷新列表' },
    })

    const region = wrapper.get('[role="status"]')
    expect(region.attributes('aria-live')).toBe('polite')
    expect(region.attributes('aria-atomic')).toBe('true')
    expect(region.text()).toBe('正在刷新列表')
  })
})


describe('SegmentedChoiceControl', () => {
  it('marks an invalid choice group and associates its error text', () => {
    const wrapper = mountAndTrack(SegmentedChoiceControl, {
      props: {
        modelValue: '',
        options: [{ value: 'PHONE_FOLLOW_UP', label: '电话' }],
        labelledBy: 'method-label',
        invalid: true,
        describedBy: 'method-error',
      },
    })

    const group = wrapper.get('[role="radiogroup"]')
    expect(group.attributes('aria-labelledby')).toBe('method-label')
    expect(group.attributes('aria-invalid')).toBe('true')
    expect(group.attributes('aria-describedby')).toBe('method-error')
  })
})
