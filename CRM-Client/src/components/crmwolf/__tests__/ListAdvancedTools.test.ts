import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import ListAdvancedTools from '../ListAdvancedTools.vue'

const wrappers: VueWrapper[] = []
const props = {
  sorts: [],
  sortFields: [{ key: 'name', label: '名称', type: 'text' as const }],
  columns: [{ key: 'name', title: '名称', visible: true, configurable: true, hideable: true }],
  columnConfigEnabled: true,
  columnConfigActive: false,
  columnConfigActiveCount: 0,
  columnConfigScope: 'personal' as const,
  columnPreferenceMode: 'default' as const,
  columnConfigLoading: false,
  columnConfigSaving: false,
}

describe('ListAdvancedTools', () => {
  afterEach(() => {
    while (wrappers.length > 0) wrappers.pop()?.unmount()
  })

  it('opens the low-frequency sort and column tools from the more-settings menu', async () => {
    const wrapper = mount(ListAdvancedTools, { props, attachTo: document.body })
    wrappers.push(wrapper)

    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('列表设置')
    expect(document.body.textContent).toContain('排序')
    expect(document.body.textContent).toContain('字段配置')

    const sortButton = Array.from(document.body.querySelectorAll('button')).find((button) => (
      button.textContent?.replace(/\s+/g, '') === '排序'
    ))
    expect(sortButton).toBeDefined()
    sortButton?.click()
    await flushPromises()
    expect(document.body.textContent).toContain('排序条件')

    const closeButtons = document.body.querySelectorAll('button[aria-label="关闭"]')
    expect(closeButtons.length).toBeGreaterThan(0)
  })
})
