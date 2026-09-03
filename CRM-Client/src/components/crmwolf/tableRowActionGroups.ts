import type { ActionConfig } from './tableRowActionTypes'

export interface TableRowActionSet {
  primaryActions?: ActionConfig[]
  secondaryActions?: ActionConfig[]
}

export interface DesktopTableRowActionProjection {
  primaryActions: ActionConfig[]
  menuGroups: TableRowActionGroup[]
  groups: TableRowActionGroup[]
}

export interface TableRowActionGroup {
  key: 'common' | 'more' | 'danger'
  label: string
  items: ActionConfig[]
}

const DESKTOP_ACTIONS_MIN_WIDTH = 112
const DESKTOP_ACTIONS_MAX_WIDTH = 280
const DESKTOP_ACTIONS_HORIZONTAL_PADDING = 32
const DESKTOP_ACTION_GAP = 8
const DESKTOP_MORE_BUTTON_WIDTH = 44
const DESKTOP_PRIMARY_ACTION_MAX_WIDTH = 128

function isVisibleAction(action: ActionConfig): boolean {
  return action.visible !== false
}

const LEGACY_VIEW_ACTION_LABELS = new Set(['查看', '详情'])

export function isDetailTableRowAction(action: ActionConfig): boolean {
  // kind 是新的稳定语义；保留旧文案判断只用于兼容尚未迁移的页面。
  return action.kind === 'detail' || (action.kind === undefined && LEGACY_VIEW_ACTION_LABELS.has(action.label))
}

function getActionButtonWidth(action: ActionConfig): number {
  const labelWidth = Array.from(action.label).length * 14
  const iconWidth = action.icon === undefined ? 0 : 20
  return Math.max(40, labelWidth + 16 + iconWidth)
}

function canRenderAsDesktopPrimary(action: ActionConfig): boolean {
  return getActionButtonWidth(action) <= DESKTOP_PRIMARY_ACTION_MAX_WIDTH
}

function getProjectedActionsWidth(primaryActions: ActionConfig[], menuActions: ActionConfig[]): number {
  const primaryWidth = primaryActions.reduce((total, action) => total + getActionButtonWidth(action), 0)
  const primaryGap = primaryActions.length > 1
    ? (primaryActions.length - 1) * DESKTOP_ACTION_GAP
    : 0
  const moreWidth = menuActions.length > 0
    ? DESKTOP_ACTION_GAP + DESKTOP_MORE_BUTTON_WIDTH
    : 0
  return primaryWidth + primaryGap + moreWidth + DESKTOP_ACTIONS_HORIZONTAL_PADDING
}

/**
 * 为桌面操作栏生成“主操作 + 更多”两层结构。
 *
 * - 显式标记 desktopPrimary 的动作优先，最多显示两个；
 * - 未标记时，选择第一个非查看、非危险的 primary action 作为兼容兜底；
 * - 查看/详情不重复出现在操作栏，行点击已经承担查看详情；
 * - 所有未提升的动作仍保留在可见的“更多”菜单中。
 */
export function getDesktopTableRowActions(
  actions: TableRowActionSet | null | undefined
): DesktopTableRowActionProjection {
  const primaryActions = (actions?.primaryActions ?? []).filter((action) =>
    isVisibleAction(action) && !isDetailTableRowAction(action)
  )
  const secondaryActions = (actions?.secondaryActions ?? []).filter((action) =>
    isVisibleAction(action) && !isDetailTableRowAction(action)
  )
  const allActions = [...primaryActions, ...secondaryActions]
  const actionable = allActions.filter((action) => !isDetailTableRowAction(action))
  const explicitlyPrimary = actionable.filter((action) =>
    action.desktopPrimary === true &&
    action.destructive !== true &&
    canRenderAsDesktopPrimary(action)
  )
  const fallbackPrimary = actionable.find((action) =>
    primaryActions.includes(action) &&
    action.destructive !== true &&
    canRenderAsDesktopPrimary(action)
  )
  const promoted = explicitlyPrimary.length > 0
    ? explicitlyPrimary.slice(0, 2)
    : fallbackPrimary === undefined ? [] : [fallbackPrimary]
  const promotedSet = new Set(promoted)
  let menuActions = actionable.filter((action) => !promotedSet.has(action))

  // 操作列有明确上限时，优先保证第一个主操作不被截断；超出空间的
  // 后续主操作降级到“更多”，仍保留完整文案和可达入口。
  while (promoted.length > 1 && getProjectedActionsWidth(promoted, menuActions) > DESKTOP_ACTIONS_MAX_WIDTH) {
    const demoted = promoted.pop()
    if (demoted !== undefined) menuActions = [demoted, ...menuActions]
  }

  const groups = groupTableRowActions({ primaryActions: promoted, secondaryActions: menuActions })
  const menuGroups = groups.filter((group) => group.key !== 'common' || promoted.length === 0)

  return { primaryActions: promoted, menuGroups, groups }
}

/**
 * 根据当前页所有行的操作投影计算统一的操作列宽度。
 *
 * 表格列宽不能按单行变化，否则每一行的按钮会跳动；因此取当前页所需的
 * 最大宽度，并限制在合理范围内。只有一个短操作时保持紧凑，长标签或双
 * 主操作时才扩展，避免固定 176px 导致按钮被裁切。
 */
export function getDesktopTableRowActionsWidth(
  actionSets: (TableRowActionSet | null | undefined)[]
): number {
  let maxWidth = DESKTOP_ACTIONS_MIN_WIDTH

  for (const actionSet of actionSets) {
    const projection = getDesktopTableRowActions(actionSet)
    const menuActions = projection.menuGroups.flatMap((group) => group.items)
    maxWidth = Math.max(maxWidth, getProjectedActionsWidth(projection.primaryActions, menuActions))
  }

  return Math.min(DESKTOP_ACTIONS_MAX_WIDTH, Math.ceil(maxWidth))
}

export function groupTableRowActions(
  actions: TableRowActionSet | null | undefined
): TableRowActionGroup[] {
  const primaryActions = (actions?.primaryActions ?? []).filter((action) =>
    isVisibleAction(action) && !isDetailTableRowAction(action)
  )
  const secondaryActions = (actions?.secondaryActions ?? []).filter((action) =>
    isVisibleAction(action) && !isDetailTableRowAction(action)
  )

  const common = primaryActions.filter((action) => action.destructive !== true)
  const more = secondaryActions.filter((action) => action.destructive !== true)
  const danger = [...primaryActions, ...secondaryActions].filter((action) => action.destructive === true)

  const groups: TableRowActionGroup[] = []
  if (common.length > 0) {
    groups.push({ key: 'common', label: '常用', items: common })
  }
  if (more.length > 0) {
    groups.push({ key: 'more', label: '更多', items: more })
  }
  if (danger.length > 0) {
    groups.push({ key: 'danger', label: '危险', items: danger })
  }
  return groups
}

export function hasVisibleTableRowActions(
  actions: TableRowActionSet | null | undefined
): boolean {
  return groupTableRowActions(actions).length > 0
}

export function shouldShowTableRowActionGroupLabels(groups: TableRowActionGroup[]): boolean {
  return groups.length > 1
}
