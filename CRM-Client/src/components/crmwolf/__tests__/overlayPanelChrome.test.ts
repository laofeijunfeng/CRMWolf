import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import ColumnConfigPopover from '../ColumnConfigPopover.vue'
import ListFilterPopover from '../ListFilterPopover.vue'
import ListSortPopover from '../ListSortPopover.vue'
import TableToolbarBuilderPanel from '../TableToolbarBuilderPanel.vue'
import type { ListFilterCondition } from '../listFilterTypes'

function lastEmittedArgument<T>(events: unknown[][] | undefined): T | undefined {
  const event = events?.[events.length - 1]
  if (event === undefined) return undefined
  return event[0] as T | undefined
}

const attached: VueWrapper[] = []
let mediaMatches = false
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
  beforeAll(() => {
    vi.stubGlobal('CSS', { escape: (value: string) => value.replace(/["\\]/g, '\\$&') })
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
      matches: mediaMatches,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn()
    })))
  })

  afterEach(() => {
    while (attached.length > 0) {
      attached.pop()?.unmount()
    }
    mediaMatches = false
    vi.useRealTimers()
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



  it('clears cascade filters from the footer without an apply button', async () => {
    const wrapper = mountAttached(ListFilterPopover, {
      fields: [{ key: 'name', label: '名称', type: 'text' }],
      modelValue: [{ field: 'name', op: 'contains', value: '测试' }]
    })

    await openToolbarPopover(wrapper, '筛选')
    expect(document.body.textContent).not.toContain('应用')
    expect(document.body.textContent).not.toContain('添加条件')
    findButton('清空').click()
    await flushPromises()
    expect(wrapper.emitted('reset')).toHaveLength(1)
    expect(wrapper.emitted('apply')).toBeUndefined()
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('applies enum choices immediately while keeping the field panel open', async () => {
    const wrapper = mountAttached(ListFilterPopover, {
      fields: [{
        key: 'status',
        label: '状态',
        type: 'enum',
        options: [{ value: 'open', label: '跟进中' }]
      }]
    })

    vi.useFakeTimers()
    await openToolbarPopover(wrapper, '筛选')
    const fieldButton = document.querySelector<HTMLButtonElement>('.filter-field-button')
    if (fieldButton === null) throw new Error('Filter field button not found')
    fieldButton.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }))
    vi.advanceTimersByTime(80)
    await nextTick()

    const optionRow = document.querySelector<HTMLElement>('.filter-option-row')
    if (optionRow === null) throw new Error('Filter option row not found')
    optionRow.click()
    await flushPromises()

    expect(lastEmittedArgument<ListFilterCondition[]>(wrapper.emitted('apply'))).toEqual([
      { field: 'status', op: 'in', value: ['open'] }
    ])
    expect(document.querySelector('.filter-field-panel')).not.toBeNull()
  })

  it('commits text only on enter or blur, not while typing', async () => {
    const wrapper = mountAttached(ListFilterPopover, {
      fields: [{ key: 'name', label: '名称', type: 'text' }]
    })

    vi.useFakeTimers()
    await openToolbarPopover(wrapper, '筛选')
    const fieldButton = document.querySelector<HTMLButtonElement>('.filter-field-button')
    if (fieldButton === null) throw new Error('Filter field button not found')
    fieldButton.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }))
    vi.advanceTimersByTime(80)
    await nextTick()

    const input = document.querySelector<HTMLInputElement>('.filter-field-panel input')
    if (input === null) throw new Error('Filter text input not found')
    input.value = 'Acme'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await nextTick()
    expect(wrapper.emitted('apply')).toBeUndefined()

    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    await flushPromises()
    expect(lastEmittedArgument<ListFilterCondition[]>(wrapper.emitted('apply'))).toEqual([
      { field: 'name', op: 'contains', value: 'Acme' }
    ])

    const replacementInput = new DOMWrapper(input)
    await replacementInput.setValue('Beta')
    await replacementInput.trigger('blur')
    await flushPromises()
    expect(lastEmittedArgument<ListFilterCondition[]>(wrapper.emitted('apply'))).toEqual([
      { field: 'name', op: 'contains', value: 'Beta' }
    ])
  })
  it('does not re-apply an unchanged text condition when switching fields', async () => {
    const wrapper = mountAttached(ListFilterPopover, {
      fields: [
        { key: 'name', label: '名称', type: 'text' },
        { key: 'status', label: '状态', type: 'enum', options: [{ value: 'open', label: '跟进中' }] }
      ]
    })

    vi.useFakeTimers()
    await openToolbarPopover(wrapper, '筛选')
    const buttons = (): HTMLButtonElement[] => Array.from(document.querySelectorAll<HTMLButtonElement>('.filter-field-button'))
    const nameButton = buttons()[0]
    const statusButton = buttons()[1]
    if (nameButton === undefined || statusButton === undefined) throw new Error('Filter field buttons not found')
    nameButton.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }))
    vi.advanceTimersByTime(80)
    await nextTick()

    const input = document.querySelector<HTMLInputElement>('.filter-field-panel input')
    if (input === null) throw new Error('Filter text input not found')
    input.value = 'Acme'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await nextTick()
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    await flushPromises()
    expect(wrapper.emitted('apply')).toHaveLength(1)

    statusButton.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }))
    vi.advanceTimersByTime(80)
    await nextTick()

    expect(lastEmittedArgument<ListFilterCondition[]>(wrapper.emitted('apply'))).toEqual([
      { field: 'name', op: 'contains', value: 'Acme' }
    ])
    expect(document.querySelector('.filter-field-panel[aria-label="状态"]')).not.toBeNull()
  })


  it('applies empty operators immediately and does not leak operators across fields', async () => {
    const wrapper = mountAttached(ListFilterPopover, {
      fields: [
        { key: 'name', label: '名称', type: 'text' },
        { key: 'city', label: '城市', type: 'text' }
      ]
    })

    vi.useFakeTimers()
    await openToolbarPopover(wrapper, '筛选')
    const buttons = (): HTMLButtonElement[] => Array.from(document.querySelectorAll<HTMLButtonElement>('.filter-field-button'))
    const firstButton = buttons()[0]
    if (firstButton === undefined) throw new Error('First filter field button not found')
    firstButton.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }))
    vi.advanceTimersByTime(80)
    await nextTick()
    const emptyButton = Array.from(document.querySelectorAll<HTMLButtonElement>('.filter-operator-button'))
      .find((button) => button.textContent?.trim() === '为空')
    if (emptyButton === undefined) throw new Error('Empty operator button not found')
    emptyButton.click()
    await flushPromises()
    expect(lastEmittedArgument<ListFilterCondition[]>(wrapper.emitted('apply'))).toEqual([
      { field: 'name', op: 'is_empty', value: null }
    ])

    const secondButton = buttons()[1]
    if (secondButton === undefined) throw new Error('Second filter field button not found')
    secondButton.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }))
    vi.advanceTimersByTime(80)
    await nextTick()
    const activeOperator = document.querySelector<HTMLButtonElement>('.filter-operator-button-active')
    expect(activeOperator?.textContent?.trim()).toBe('包含')
  })

  it('keeps the field panel open after a narrow-screen click', async () => {
    mediaMatches = true
    const wrapper = mountAttached(ListFilterPopover, {
      fields: [{ key: 'name', label: '名称', type: 'text' }]
    })

    await openToolbarPopover(wrapper, '筛选')
    const fieldButton = document.querySelector<HTMLButtonElement>('.filter-field-button')
    if (fieldButton === null) throw new Error('Filter field button not found')
    fieldButton.click()
    await nextTick()

    expect(document.querySelector('.filter-field-panel')).not.toBeNull()
  })

  it('shows a calendar after changing a date operator from a preset', async () => {
    const wrapper = mountAttached(ListFilterPopover, {
      fields: [{ key: 'created_at', label: '创建时间', type: 'date' }],
      modelValue: [{ field: 'created_at', op: 'past_1_week', value: null }]
    })

    vi.useFakeTimers()
    await openToolbarPopover(wrapper, '筛选')
    const fieldButton = document.querySelector<HTMLButtonElement>('.filter-field-button')
    if (fieldButton === null) throw new Error('Filter field button not found')
    fieldButton.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }))
    vi.advanceTimersByTime(80)
    await nextTick()
    const equalButton = Array.from(document.querySelectorAll<HTMLButtonElement>('.filter-operator-button'))
      .find((button) => button.textContent?.trim() === '等于')
    if (equalButton === undefined) throw new Error('Date equality button not found')
    equalButton.click()
    await nextTick()

    expect(document.querySelector('.date-picker-calendar')).not.toBeNull()
    expect(document.querySelector('.filter-operator-button-active')?.textContent?.trim()).toBe('等于')
  })

  it('closes the sort menu without clearing a selected direction', async () => {
    const wrapper = mountAttached(ListSortPopover, {
      fields: [{ key: 'name', label: '名称', type: 'text' }],
      modelValue: [{ field: 'name', direction: 'asc' }]
    })

    await openToolbarPopover(wrapper, '排序')
    expect(document.body.textContent).not.toContain('应用')
    expect(document.body.textContent).not.toContain('清空')
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(wrapper.emitted('reset')).toBeUndefined()
    expect(wrapper.emitted('apply')).toBeUndefined()
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
  })

  it('uses optional view config labels without changing the column chrome', async () => {
    const wrapper = mountAttached(ColumnConfigPopover, {
      columns: [{
        key: 'name',
        title: '名称',
        visible: true,
        configurable: true,
        hideable: true,
      }],
      viewDisplayModeEnabled: true,
      viewDisplayMode: 'table',
      viewConfigTriggerLabel: '视图配置',
      viewConfigPanelTitle: '视图配置',
    })

    await openToolbarPopover(wrapper, '视图配置')

    expect(document.body.textContent).toContain('看板视图')
    expect(document.body.textContent).toContain('字段')
    expect(findButton('关闭')).toBeTruthy()
  })
})
