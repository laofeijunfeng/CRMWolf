import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { CalendarDate } from '@internationalized/date'
import Calendar from '@/components/ui/calendar/Calendar.vue'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import ListFilterPopover from '../ListFilterPopover.vue'
import type { ListFilterCondition, ListFilterField } from '../listFilterTypes'

const attached: VueWrapper[] = []

const mountAttached = (props: {
  fields: ListFilterField[]
  modelValue?: ListFilterCondition[]
}): VueWrapper => {
  const wrapper = mount(ListFilterPopover, {
    props,
    attachTo: document.body
  })
  attached.push(wrapper)
  return wrapper
}

async function openDateField(wrapper: VueWrapper): Promise<void> {
  const trigger = wrapper.findAll('button').find((button) => button.text().includes('筛选'))
  if (trigger === undefined) throw new Error('筛选按钮不存在')
  await trigger.trigger('click')
  await flushPromises()
  const fieldButton = document.querySelector<HTMLButtonElement>('.filter-field-button')
  if (fieldButton === null) throw new Error('字段按钮不存在')
  fieldButton.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }))
  await vi.advanceTimersByTimeAsync(80)
  await nextTick()
}

function clickOperator(label: string): void {
  const button = Array.from(document.querySelectorAll<HTMLButtonElement>('.filter-operator-button'))
    .find((item) => item.textContent?.trim() === label)
  if (button === undefined) throw new Error(`判断不存在: ${label}`)
  button.click()
}

function clickDay(day: string): void {
  const button = Array.from(document.querySelectorAll<HTMLElement>('.date-picker-calendar__cell-trigger'))
    .find((item) => item.textContent?.trim() === day && !item.hasAttribute('data-outside-view'))
  if (button === undefined) throw new Error(`日期不存在: ${day}`)
  button.dispatchEvent(new MouseEvent('click', { bubbles: true }))
}

function lastApply(wrapper: VueWrapper): ListFilterCondition[] | undefined {
  const events = wrapper.emitted('apply')
  const event = events?.[events.length - 1]
  return event?.[0] as ListFilterCondition[] | undefined
}

describe('date between filter', () => {
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

  it('places 介于 between 早于 and 为空 and does not refresh after one click', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 9, 15, 12, 0, 0))
    const wrapper = mountAttached({
      fields: [{ key: 'expected_closing_date', label: '预计成交日期', type: 'date' }]
    })

    await openDateField(wrapper)
    const labels = Array.from(document.querySelectorAll('.filter-operator-button')).map((button) => button.textContent?.trim())
    expect(labels.indexOf('介于')).toBe(labels.indexOf('早于') + 1)
    expect(labels.indexOf('为空')).toBe(labels.indexOf('介于') + 1)

    clickOperator('介于')
    await nextTick()
    clickDay('1'); await nextTick()

    expect(wrapper.emitted('apply')).toBeUndefined()
    expect(document.querySelectorAll('.is-range-point')).toHaveLength(1)
    expect(document.querySelector('.is-range-middle')).toBeNull()
  })

  it('emits an ordered inclusive range only after the second click', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 9, 15, 12, 0, 0))
    const wrapper = mountAttached({
      fields: [{ key: 'expected_closing_date', label: '预计成交日期', type: 'date' }]
    })

    await openDateField(wrapper)
    clickOperator('介于')
    await nextTick()
    clickDay('20'); await nextTick()
    clickDay('1'); await nextTick()

    expect(lastApply(wrapper)).toEqual([
      { field: 'expected_closing_date', op: 'between', value: ['2026-10-01', '2026-10-20'] }
    ])
    await wrapper.setProps({
      modelValue: lastApply(wrapper)
    })
    await nextTick()
    expect(document.querySelectorAll('.is-range-middle').length).toBeGreaterThan(0)
    expect(document.querySelectorAll('.is-range-start')).toHaveLength(1)
    expect(document.querySelectorAll('.is-range-end')).toHaveLength(1)
  })

  it('keeps the previous condition when between is abandoned after one click', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 9, 15, 12, 0, 0))
    const existing: ListFilterCondition[] = [
      { field: 'expected_closing_date', op: 'eq', value: '2026-10-01' }
    ]
    const wrapper = mountAttached({
      fields: [{ key: 'expected_closing_date', label: '预计成交日期', type: 'date' }],
      modelValue: existing
    })

    await openDateField(wrapper)
    clickOperator('介于')
    await nextTick()
    clickDay('20'); await nextTick()
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()

    expect(wrapper.emitted('apply')).toBeUndefined()
    const mountedProps: unknown = wrapper.props()
    const modelValue = typeof mountedProps === 'object' && mountedProps !== null && 'modelValue' in mountedProps
      ? mountedProps.modelValue
      : undefined
    expect(modelValue).toEqual(existing)
  })

  it('treats two clicks on the same day as a one-day range', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 9, 15, 12, 0, 0))
    const wrapper = mountAttached({
      fields: [{ key: 'created_time', label: '创建时间', type: 'date' }]
    })

    await openDateField(wrapper)
    clickOperator('介于')
    await nextTick()
    clickDay('1'); await nextTick()
    clickDay('1'); await nextTick()

    expect(lastApply(wrapper)).toEqual([
      { field: 'created_time', op: 'between', value: ['2026-10-01', '2026-10-01'] }
    ])
  })

  it('does not replace an active range until the new range is complete', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 9, 15, 12, 0, 0))
    const existing: ListFilterCondition[] = [
      { field: 'expected_closing_date', op: 'between', value: ['2026-10-01', '2026-10-20'] }
    ]
    const wrapper = mountAttached({
      fields: [{ key: 'expected_closing_date', label: '预计成交日期', type: 'date' }],
      modelValue: existing
    })

    await openDateField(wrapper)
    clickDay('5'); await nextTick()

    expect(wrapper.emitted('apply')).toBeUndefined()
    expect(document.querySelectorAll('.is-range-point')).toHaveLength(1)
    expect(document.querySelector('.is-range-middle')).toBeNull()
  })

  it('paints the range on the existing calendar and reports the clicked day', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 9, 15, 12, 0, 0))
    const wrapper = mount(Calendar, {
      props: {
        range: true,
        rangeStart: new CalendarDate(2026, 10, 1),
        rangeEnd: new CalendarDate(2026, 10, 20),
        placeholder: new CalendarDate(2026, 10, 1)
      },
      attachTo: document.body
    })
    attached.push(wrapper)
    await nextTick()

    expect(document.querySelectorAll('.is-range-start')).toHaveLength(1)
    expect(document.querySelectorAll('.is-range-end')).toHaveLength(1)
    expect(document.querySelectorAll('.is-range-middle').length).toBeGreaterThan(0)

    const day = Array.from(document.querySelectorAll<HTMLElement>('.date-picker-calendar__cell-trigger'))
      .find((item) => item.textContent?.trim() === '5' && !item.hasAttribute('data-outside-view'))
    if (day === undefined) throw new Error('日期不存在')
    day.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await nextTick()

    const events = wrapper.emitted('update:modelValue')
    expect(events?.[0]?.[0]).toEqual(new CalendarDate(2026, 10, 5))
  })
})
