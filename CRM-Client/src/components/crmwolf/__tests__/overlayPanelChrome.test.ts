import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import ColumnConfigPopover from '../ColumnConfigPopover.vue'
import ListFilterPopover from '../ListFilterPopover.vue'
import ListSortPopover from '../ListSortPopover.vue'
import TableToolbarBuilderPanel from '../TableToolbarBuilderPanel.vue'

const attached: VueWrapper[] = []

const mountAttached = (component: Parameters<typeof mount>[0], props: Record<string, unknown>): VueWrapper => {
  const wrapper = mount(component, {
    props,
    attachTo: document.body
  })
  attached.push(wrapper)
  return wrapper
}

const findButton = (label: string): HTMLButtonElement => {
  const button = Array.from(document.body.querySelectorAll('button')).find((node) => (
    node.getAttribute('aria-label') === label
    || node.textContent?.replace(/\s+/g, '') === label
  ))
  if (button === undefined) {
    throw new Error(`Button not found: ${label}`)
  }
  return button
}

const openToolbarPopover = async (wrapper: VueWrapper, triggerLabel: string): Promise<void> => {
  const trigger = wrapper.findAll('button').find((button) => button.text().includes(triggerLabel))
  if (trigger === undefined) {
    throw new Error(`Trigger not found: ${triggerLabel}`)
  }
  await trigger.trigger('click')
  await flushPromises()
  await nextTick()
}

describe('overlay panel chrome', () => {
  afterEach(() => {
    while (attached.length > 0) {
      attached.pop()?.unmount()
    }
  })

  it('uses the header icon to close the builder panel, not to reset it', async () => {
    const wrapper = mount(TableToolbarBuilderPanel, {
      props: { title: '筛选条件' },
      attachTo: document.body
    })
    attached.push(wrapper)

    await wrapper.get('[aria-label="关闭"]').trigger('click')

    expect(wrapper.emitted('close')).toEqual([[]])
    expect(wrapper.emitted('reset')).toBeUndefined()
  })

  it('keeps filter reset on the footer apply row and does not reset when closing', async () => {
    const wrapper = mountAttached(ListFilterPopover, {
      fields: [{ key: 'name', label: '名称', type: 'text' }],
      modelValue: [{ field: 'name', op: 'contains', value: '测试' }]
    })

    await openToolbarPopover(wrapper, '筛选')
    findButton('关闭').click()
    await flushPromises()
    expect(wrapper.emitted('reset')).toBeUndefined()

    await openToolbarPopover(wrapper, '筛选')
    expect(findButton('应用').querySelector('svg')).toBeNull()
    expect(findButton('添加条件').querySelector('svg')).not.toBeNull()
    findButton('清空').click()
    await flushPromises()
    expect(wrapper.emitted('reset')).toHaveLength(1)
  })

  it('keeps sort reset on the footer apply row and does not reset when closing', async () => {
    const wrapper = mountAttached(ListSortPopover, {
      fields: [{ key: 'name', label: '名称', type: 'text' }],
      modelValue: [{ field: 'name', direction: 'asc' }]
    })

    await openToolbarPopover(wrapper, '排序')
    findButton('关闭').click()
    await flushPromises()
    expect(wrapper.emitted('reset')).toBeUndefined()

    await openToolbarPopover(wrapper, '排序')
    expect(findButton('应用').querySelector('svg')).toBeNull()
    findButton('清空').click()
    await flushPromises()
    expect(wrapper.emitted('reset')).toHaveLength(1)
  })

  it('gives column config the same close control and text-only footer actions', async () => {
    const wrapper = mountAttached(ColumnConfigPopover, {
      columns: [{
        key: 'name',
        title: '名称',
        visible: true,
        configurable: true,
        hideable: true
      }]
    })

    await openToolbarPopover(wrapper, '字段配置')

    expect(findButton('关闭')).toBeTruthy()
    expect(findButton('保存').querySelector('svg')).toBeNull()
    expect(findButton('恢复默认').querySelector('svg')).toBeNull()
    expect(document.body.textContent).toContain('拖动非固定列调整表格顺序')
  })
})
