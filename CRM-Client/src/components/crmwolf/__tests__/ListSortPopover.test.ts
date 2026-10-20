import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
class ResizeObserverStub {
  observe(): void { return undefined }
  unobserve(): void { return undefined }
  disconnect(): void { return undefined }
}

import { nextTick } from 'vue'
import ListSortPopover from '../ListSortPopover.vue'
import type { ListSortCondition } from '../listSortTypes'

const attached: VueWrapper[] = []
let mediaMatches = false

const fields = [
  { key: 'account_name', label: '客户名称', type: 'text' as const },
  { key: 'created_time', label: '创建时间', type: 'date' as const },
  { key: 'license_authorized_users', label: '授权人数', type: 'number' as const },
  { key: 'status', label: '状态', type: 'enum' as const }
]

async function openSortPopover(wrapper: VueWrapper): Promise<void> {
  const trigger = wrapper.findAll('button').find((button) => button.text().includes('排序'))
  if (trigger === undefined) throw new Error('Sort popover trigger not found')
  await trigger.trigger('click')
  await flushPromises()
  await nextTick()
}

function fieldButton(label: string): HTMLButtonElement {
  const button = Array.from(document.body.querySelectorAll<HTMLButtonElement>('.sort-field-button'))
    .find((node) => node.textContent?.includes(label) === true)
  if (button === undefined) throw new Error(`Sort field not found: ${label}`)
  return button
}

async function hoverField(label: string): Promise<void> {
  fieldButton(label).dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }))
  vi.advanceTimersByTime(80)
  await nextTick()
}

function directionButton(label: string): HTMLButtonElement {
  const button = Array.from(document.body.querySelectorAll<HTMLButtonElement>('.sort-direction-button'))
    .find((node) => node.textContent?.replace(/\s+/g, '') === label)
  if (button === undefined) throw new Error(`Sort direction not found: ${label}`)
  return button
}

function lastSorts(wrapper: VueWrapper): ListSortCondition[] | undefined {
  const events = wrapper.emitted('apply')
  const event = events?.[events.length - 1]
  return event?.[0] as ListSortCondition[] | undefined
}

describe('ListSortPopover', () => {
  beforeEach(() => {
    mediaMatches = false
    vi.useFakeTimers()
    vi.stubGlobal('ResizeObserver', ResizeObserverStub)
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
      matches: mediaMatches,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn()
    })))
  })

  it('applies the hovered direction immediately and keeps the menu open', async () => {
    const wrapper = mount(ListSortPopover, {
      props: { fields, modelValue: [] },
      attachTo: document.body
    })
    attached.push(wrapper)

    await openSortPopover(wrapper)
    expect(document.body.textContent).not.toContain('应用')
    expect(document.body.textContent).not.toContain('清空')
    expect(document.body.textContent).not.toContain('添加条件')

    await hoverField('创建时间')
    expect(Array.from(document.body.querySelectorAll('.sort-direction-button'), (node) => node.textContent?.trim()))
      .toEqual(['最早-最晚', '最晚-最早'])

    directionButton('最晚-最早').click()
    await nextTick()

    expect(lastSorts(wrapper)).toEqual([{ field: 'created_time', direction: 'desc' }])
    expect(wrapper.emitted('update:open')?.some((event) => event[0] === false)).not.toBe(true)
    expect(document.body.textContent).toContain('排序1')
    expect(fieldButton('创建时间').textContent?.replace(/\s+/g, '')).toContain('创建时间1')
  })

  it('keeps the first choice first when a second field is chosen', async () => {
    const wrapper = mount(ListSortPopover, {
      props: {
        fields,
        modelValue: [{ field: 'created_time', direction: 'desc' }]
      },
      attachTo: document.body
    })
    attached.push(wrapper)

    await openSortPopover(wrapper)
    await hoverField('授权人数')
    expect(Array.from(document.body.querySelectorAll('.sort-direction-button'), (node) => node.textContent?.trim()))
      .toEqual(['0-9', '9-0'])
    directionButton('9-0').click()
    await nextTick()

    expect(lastSorts(wrapper)).toEqual([
      { field: 'created_time', direction: 'desc' },
      { field: 'license_authorized_users', direction: 'desc' }
    ])
    expect(fieldButton('创建时间').querySelector('.sort-field-priority')?.textContent).toBe('1')
    expect(fieldButton('授权人数').querySelector('.sort-field-priority')?.textContent).toBe('2')
  })

  it('changes direction without moving the field and removes only that field when clicked again', async () => {
    const wrapper = mount(ListSortPopover, {
      props: {
        fields,
        modelValue: [
          { field: 'created_time', direction: 'desc' },
          { field: 'license_authorized_users', direction: 'desc' }
        ]
      },
      attachTo: document.body
    })
    attached.push(wrapper)

    await openSortPopover(wrapper)
    await hoverField('创建时间')
    directionButton('最早-最晚').click()
    await nextTick()
    expect(lastSorts(wrapper)).toEqual([
      { field: 'created_time', direction: 'asc' },
      { field: 'license_authorized_users', direction: 'desc' }
    ])

    directionButton('最早-最晚').click()
    await nextTick()
    expect(lastSorts(wrapper)).toEqual([
      { field: 'license_authorized_users', direction: 'desc' }
    ])
    expect(wrapper.emitted('reset')).toBeUndefined()
    expect(fieldButton('授权人数').querySelector('.sort-field-priority')?.textContent).toBe('1')
    expect(fieldButton('创建时间').querySelector('.sort-field-priority')).toBeNull()
  })

  it('opens directions by click on a narrow screen and ignores hover', async () => {
    mediaMatches = true
    const wrapper = mount(ListSortPopover, {
      props: { fields, modelValue: [] },
      attachTo: document.body
    })
    attached.push(wrapper)

    await openSortPopover(wrapper)
    await hoverField('创建时间')
    expect(document.body.querySelector('.sort-direction-panel')).toBeNull()

    fieldButton('创建时间').click()
    await nextTick()
    expect(document.body.querySelector('.sort-direction-panel')).not.toBeNull()
    directionButton('最晚-最早').click()
    await nextTick()

    expect(lastSorts(wrapper)).toEqual([{ field: 'created_time', direction: 'desc' }])
    expect(document.body.querySelector('.sort-direction-panel')).not.toBeNull()
  })

  afterEach(() => {
    while (attached.length > 0) attached.pop()?.unmount()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })
})
