import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ChartBucketActionList, { type ChartBucketAction } from '../ChartBucketActionList.vue'

interface TestAction extends ChartBucketAction {
  value: number
}

describe('ChartBucketActionList', () => {
  it('activates enabled actions and prevents disabled actions', async () => {
    const actions: TestAction[] = [
      { key: 'active', label: 'Active bucket', value: 1 },
      { key: 'locked', label: 'Locked bucket', value: 2, disabled: true },
    ]
    const wrapper = mount(ChartBucketActionList, {
      props: { actions, testIdPrefix: 'bucket-action' },
    })

    const buttons = wrapper.findAll('button')
    expect(buttons).toHaveLength(2)
    expect(buttons[0]?.attributes('type')).toBe('button')
    expect(buttons[0]?.attributes('data-testid')).toBe('bucket-action-active')
    expect(buttons[0]?.attributes('aria-label')).toBe('Active bucket')
    expect(buttons[0]?.classes()).toContain('focus-visible:ring-2')
    expect(buttons[1]?.attributes('disabled')).toBeDefined()

    await buttons[0]?.trigger('click')
    await buttons[1]?.trigger('click')

    expect(wrapper.emitted('activate')).toEqual([[actions[0]]])
  })

  it('renders a scoped action slot while retaining accessible button semantics', () => {
    const action: TestAction = { key: 'active', label: 'Active bucket', ariaLabel: 'Open active bucket', class: 'forecast-column', value: 1 }
    const wrapper = mount(ChartBucketActionList, {
      props: { actions: [action] },
      slots: { default: '<template #default="{ action }"><span class="custom">{{ action.value }}</span></template>' },
    })

    expect(wrapper.find('.custom').text()).toBe('1')
    expect(wrapper.find('button').attributes('aria-label')).toBe('Open active bucket')
    expect(wrapper.find('button').classes()).toContain('forecast-column')
  })
})
