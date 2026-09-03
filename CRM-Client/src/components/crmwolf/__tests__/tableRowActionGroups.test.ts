import { describe, expect, it } from 'vitest'
import type { ActionConfig } from '../tableRowActionTypes'
import {
  groupTableRowActions,
  getDesktopTableRowActions,
  getDesktopTableRowActionsWidth,
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

describe('getDesktopTableRowActions', () => {
  it('promotes explicitly marked actions and keeps the rest in the visible menu', () => {
    const edit = action('编辑', { desktopPrimary: true })
    const advance = action('推进阶段', { desktopPrimary: true })
    const transfer = action('移交')
    const remove = action('删除', { destructive: true })

    const projection = getDesktopTableRowActions({
      primaryActions: [action('查看'), edit, advance],
      secondaryActions: [transfer, remove]
    })

    expect(projection.primaryActions.map((item) => item.label)).toEqual(['编辑', '推进阶段'])
    expect(projection.menuGroups.flatMap((group) => group.items.map((item) => item.label))).toEqual(['移交', '删除'])
  })

  it('does not duplicate the row detail action and provides a fallback primary action', () => {
    const projection = getDesktopTableRowActions({
      primaryActions: [action('查看'), action('编辑')],
      secondaryActions: []
    })

    expect(projection.primaryActions.map((item) => item.label)).toEqual(['编辑'])
    expect(projection.menuGroups).toEqual([])
  })

  it('keeps destructive actions discoverable in more when no safe primary exists', () => {
    const projection = getDesktopTableRowActions({
      primaryActions: [action('查看')],
      secondaryActions: [action('删除', { destructive: true })]
    })

    expect(projection.primaryActions).toEqual([])
    expect(projection.menuGroups.flatMap((group) => group.items.map((item) => item.label))).toEqual(['删除'])
  })

  it('keeps a single short action compact', () => {
    expect(getDesktopTableRowActionsWidth([
      { primaryActions: [action('编辑')], secondaryActions: [] }
    ])).toBe(112)
  })

  it('moves long primary labels into the menu instead of truncating them', () => {
    const projection = getDesktopTableRowActions({
      primaryActions: [
        action('修改并重新提交申请单', { desktopPrimary: true }),
        action('确认完成', { desktopPrimary: true })
      ],
      secondaryActions: [action('删除', { destructive: true })]
    })

    expect(projection.primaryActions.map((item) => item.label)).toEqual(['确认完成'])
    expect(projection.menuGroups.flatMap((group) => group.items.map((item) => item.label))).toEqual([
      '修改并重新提交申请单',
      '删除'
    ])
    expect(getDesktopTableRowActionsWidth([
      {
        primaryActions: [
          action('修改并重新提交申请单', { desktopPrimary: true }),
          action('确认完成', { desktopPrimary: true })
        ],
        secondaryActions: [action('删除', { destructive: true })]
      }
    ])).toBe(156)
  })

  it('demotes a second primary action when both would exceed the column cap', () => {
    const projection = getDesktopTableRowActions({
      primaryActions: [
        action('修改并重新提交单', { desktopPrimary: true }),
        action('推进当前业务阶段', { desktopPrimary: true })
      ],
      secondaryActions: []
    })

    expect(projection.primaryActions.map((item) => item.label)).toEqual(['修改并重新提交单'])
    expect(projection.menuGroups.flatMap((group) => group.items.map((item) => item.label))).toEqual(['推进当前业务阶段'])
  })

  it('uses explicit detail semantics without relying on the visible label', () => {
    const projection = getDesktopTableRowActions({
      primaryActions: [action('打开', { kind: 'detail' }), action('编辑')],
      secondaryActions: []
    })

    expect(projection.primaryActions.map((item) => item.label)).toEqual(['编辑'])
    expect(projection.menuGroups).toEqual([])
  })

  it('does not expose detail actions in context-menu groups', () => {
    const groups = groupTableRowActions({
      primaryActions: [action('打开', { kind: 'detail' }), action('编辑')],
      secondaryActions: [action('详情'), action('移交')]
    })

    expect(groups.flatMap((group) => group.items.map((item) => item.label))).toEqual(['编辑', '移交'])
  })
})
