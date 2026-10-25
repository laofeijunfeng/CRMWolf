import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import ListFilterPopover from '../ListFilterPopover.vue'
import type { ListFilterCondition } from '../listFilterTypes'

const attached: VueWrapper[] = []

const stageField = {
  key: 'stage',
  label: '当前阶段',
  type: 'enum' as const,
  options: [
    { value: 'early_communication', label: '早期沟通' },
    { value: 'active_progress', label: '积极推进' }
  ]
}

const mountAttached = (props: Record<string, unknown>): VueWrapper => {
  const wrapper = mount(ListFilterPopover, {
    props,
    attachTo: document.body
  })
  attached.push(wrapper)
  return wrapper
}

async function openStageField(wrapper: VueWrapper): Promise<void> {
  const trigger = wrapper.findAll('button').find((button) => button.text().includes('筛选'))
  if (trigger === undefined) throw new Error('筛选按钮不存在')
  await trigger.trigger('click')
  await flushPromises()
  const fieldButton = Array.from(document.querySelectorAll<HTMLButtonElement>('.filter-field-button'))
    .find((button) => button.textContent?.includes('当前阶段') === true)
  if (fieldButton === undefined) throw new Error('字段按钮不存在')
  fieldButton.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }))
  await vi.advanceTimersByTimeAsync(80)
  await nextTick()
}

function operatorButton(label: string): HTMLButtonElement {
  const button = Array.from(document.querySelectorAll<HTMLButtonElement>('.filter-operator-button'))
    .find((item) => item.textContent?.trim() === label)
  if (button === undefined) throw new Error(`判断不存在: ${label}`)
  return button
}

function clickOperator(label: string): void {
  operatorButton(label).click()
}

function activeOperatorLabel(): string | undefined {
  return document.querySelector('.filter-operator-button-active')?.textContent?.trim()
}

async function checkOption(label: string): Promise<void> {
  const row = Array.from(document.querySelectorAll<HTMLElement>('.filter-option-row'))
    .find((item) => item.textContent?.includes(label) === true)
  if (row === undefined) throw new Error(`选项不存在: ${label}`)
  const checkbox = row.querySelector<HTMLElement>('[role="checkbox"]')
  if (checkbox === null) throw new Error(`复选框不存在: ${label}`)
  checkbox.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  await nextTick()
}

function lastApply(wrapper: VueWrapper): ListFilterCondition[] | undefined {
  const events = wrapper.emitted('apply')
  const event = events?.[events.length - 1]
  return event?.[0] as ListFilterCondition[] | undefined
}

describe('enum operator draft', () => {
  beforeAll(() => {
    vi.stubGlobal('CSS', { escape: (value: string) => value.replace(/["\\]/g, '\\$&') })
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
      matches: false,
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
    vi.useRealTimers()
  })

  it('selects 不属于 before any stage is checked', async () => {
    vi.useFakeTimers()
    const wrapper = mountAttached({ fields: [stageField] })

    await openStageField(wrapper)
    expect(activeOperatorLabel()).toBe('属于')

    clickOperator('不属于')
    await nextTick()

    expect(activeOperatorLabel()).toBe('不属于')
    expect(wrapper.emitted('apply')).toBeUndefined()

    await checkOption('早期沟通')
    expect(lastApply(wrapper)).toEqual([
      { field: 'stage', op: 'not_in', value: ['early_communication'] }
    ])
  })

  it('switches an existing selection to 不属于', async () => {
    vi.useFakeTimers()
    const wrapper = mountAttached({
      fields: [stageField],
      modelValue: [{ field: 'stage', op: 'in', value: ['early_communication'] }]
    })

    await openStageField(wrapper)
    expect(activeOperatorLabel()).toBe('属于')

    clickOperator('不属于')
    await nextTick()

    expect(activeOperatorLabel()).toBe('不属于')
    expect(lastApply(wrapper)).toEqual([
      { field: 'stage', op: 'not_in', value: ['early_communication'] }
    ])
  })

  it('still applies 为空 immediately and keeps 属于 as the default', async () => {
    vi.useFakeTimers()
    const wrapper = mountAttached({ fields: [stageField] })

    await openStageField(wrapper)
    clickOperator('属于')
    await nextTick()
    expect(activeOperatorLabel()).toBe('属于')
    expect(wrapper.emitted('apply')).toBeUndefined()

    clickOperator('为空')
    await nextTick()
    expect(lastApply(wrapper)).toEqual([
      { field: 'stage', op: 'is_empty', value: null }
    ])
    await wrapper.setProps({ modelValue: lastApply(wrapper) })
    await nextTick()
    expect(activeOperatorLabel()).toBe('为空')
  })

  it('returns to 属于 after 不属于 is clicked with no values', async () => {
    vi.useFakeTimers()
    const wrapper = mountAttached({ fields: [stageField] })

    await openStageField(wrapper)
    clickOperator('不属于')
    await nextTick()
    clickOperator('属于')
    await nextTick()

    expect(activeOperatorLabel()).toBe('属于')
    await checkOption('早期沟通')
    expect(lastApply(wrapper)).toEqual([
      { field: 'stage', op: 'in', value: ['early_communication'] }
    ])
  })
})
