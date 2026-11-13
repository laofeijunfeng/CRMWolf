import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ContextTabs from '../ContextTabs.vue'

describe('ContextTabs controlled activation', () => {
  it('notifies the model before change without activating a disabled tab', async () => {
    const events: string[] = []
    const wrapper = mount(ContextTabs, {
      props: {
        tabs: [
          { key: 'first', label: 'First' },
          { key: 'second', label: 'Second', badge: 3 },
          { key: 'disabled', label: 'Disabled', disabled: true },
        ],
        activeTab: 'first',
        'onUpdate:activeTab': (value: string) => events.push(`model:${value}`),
        onChange: (value: string) => events.push(`change:${value}`),
      },
    })
    const tabs = wrapper.findAll('[role="tab"]')
    await tabs[1]?.trigger('mousedown', { button: 0 })
    expect(events).toEqual(['model:second', 'change:second'])
    expect(tabs[0]?.attributes('aria-selected')).toBe('true')
    await wrapper.setProps({ activeTab: 'second' })
    expect(tabs[1]?.attributes('aria-selected')).toBe('true')
    expect(tabs[1]?.text()).toContain('3')
    await tabs[2]?.trigger('mousedown', { button: 0 })
    expect(events).toEqual(['model:second', 'change:second'])
    wrapper.unmount()
  })
})
