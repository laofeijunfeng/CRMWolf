import { describe, expect, it } from 'vitest'
import type { ActionConfig } from '../tableRowActionTypes'
import {
  groupTableRowActions,
  hasVisibleTableRowActions,
  shouldShowTableRowActionGroupLabels
} from '../tableRowActionGroups'

const action = (label: string, extra: Partial<ActionConfig> = {}): ActionConfig => ({
  label,
  handler: () => undefined,
  ...extra
})

describe('groupTableRowActions', () => {
  it('puts visible non-destructive primary actions into 常用', () => {
    const groups = groupTableRowActions({
      primaryActions: [action('编辑'), action('推进阶段')],
      secondaryActions: []
    })

    expect(groups).toEqual([
      {
        key: 'common',
        label: '常用',
        items: [expect.objectContaining({ label: '编辑' }), expect.objectContaining({ label: '推进阶段' })]
      }
    ])
  })

  it('puts visible non-destructive secondary actions into 更多', () => {
    const groups = groupTableRowActions({
      primaryActions: [action('编辑')],
      secondaryActions: [action('移交')]
    })

    expect(groups.map((group) => group.key)).toEqual(['common', 'more'])
    expect(groups[1]?.items.map((item) => item.label)).toEqual(['移交'])
  })

  it('moves destructive primary actions into 危险 instead of 常用', () => {
    const groups = groupTableRowActions({
      primaryActions: [action('删除', { destructive: true })],
      secondaryActions: []
    })

    expect(groups).toEqual([
      {
        key: 'danger',
        label: '危险',
        items: [expect.objectContaining({ label: '删除', destructive: true })]
      }
    ])
  })

  it('moves destructive secondary actions into 危险 instead of 更多', () => {
    const groups = groupTableRowActions({
      primaryActions: [action('编辑')],
      secondaryActions: [action('输单', { destructive: true })]
    })

    expect(groups.map((group) => group.key)).toEqual(['common', 'danger'])
    expect(groups[1]?.items.map((item) => item.label)).toEqual(['输单'])
  })

  it('omits hidden actions and empty groups', () => {
    const groups = groupTableRowActions({
      primaryActions: [action('编辑', { visible: false })],
      secondaryActions: [action('删除', { visible: false, destructive: true })]
    })

    expect(groups).toEqual([])
  })

  it('ignores desktop separator flags when grouping', () => {
    const groups = groupTableRowActions({
      primaryActions: [action('编辑')],
      secondaryActions: [action('删除', { destructive: true, separator: true })]
    })

    expect(groups).toHaveLength(2)
    expect(groups[1]?.items[0]?.separator).toBe(true)
  })
})

describe('hasVisibleTableRowActions', () => {
  it('is false for null, empty, or fully hidden action sets', () => {
    expect(hasVisibleTableRowActions(null)).toBe(false)
    expect(hasVisibleTableRowActions(undefined)).toBe(false)
    expect(hasVisibleTableRowActions({ primaryActions: [], secondaryActions: [] })).toBe(false)
    expect(hasVisibleTableRowActions({
      primaryActions: [action('编辑', { visible: false })],
      secondaryActions: []
    })).toBe(false)
  })

  it('is true when any visible action remains', () => {
    expect(hasVisibleTableRowActions({
      primaryActions: [action('领取')],
      secondaryActions: []
    })).toBe(true)
  })
})

describe('shouldShowTableRowActionGroupLabels', () => {
  it('hides labels when only one group exists', () => {
    expect(shouldShowTableRowActionGroupLabels(groupTableRowActions({
      primaryActions: [action('领取')],
      secondaryActions: []
    }))).toBe(false)
  })

  it('shows labels when 常用 / 更多 / 危险 need to be distinguished', () => {
    expect(shouldShowTableRowActionGroupLabels(groupTableRowActions({
      primaryActions: [action('编辑')],
      secondaryActions: [action('移交'), action('删除', { destructive: true })]
    }))).toBe(true)
  })
})
