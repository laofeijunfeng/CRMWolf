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

export interface MobileTableRowActionProjection {
  primaryActions: ActionConfig[]
  secondaryActions: ActionConfig[]
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

export function getTableRowActionKey(action: ActionConfig, index: number): string {
  return `${action.id ?? action.label}-${index}`
}

export function isDetailTableRowAction(action: ActionConfig): boolean {
  // kind 是新的稳定语义；保留旧文案判断只用于兼容尚未迁移的页面。
  return action.id === 'detail' || action.kind === 'detail' ||
    (action.id === undefined && action.kind === undefined && LEGACY_VIEW_ACTION_LABELS.has(action.label))
}

function getVisibleNonDetailActions(actions: ActionConfig[] | undefined): ActionConfig[] {
  return (actions ?? []).filter((action) => isVisibleAction(action) && !isDetailTableRowAction(action))
}

/**
 * 为窄视口卡片生成与桌面一致的动作层级。
 *
 * 移动端没有桌面操作列的宽度约束，但危险动作仍不得因为调用方把它
 * 放进 primaryActions 就直接成为卡片上的常显按钮。
 */
export function getMobileTableRowActions(
  actions: TableRowActionSet | null | undefined
): MobileTableRowActionProjection {
  const primaryActions = getVisibleNonDetailActions(actions?.primaryActions)
  const secondaryActions = getVisibleNonDetailActions(actions?.secondaryActions)
  const safePrimaryActions = primaryActions.filter((action) => !isDestructiveTableRowAction(action))
  const destructivePrimaryActions = primaryActions.filter(isDestructiveTableRowAction)

  return {
    primaryActions: safePrimaryActions,
    secondaryActions: [...secondaryActions, ...destructivePrimaryActions]
  }
}

export function isDestructiveTableRowAction(action: ActionConfig): boolean {
  return action.destructive === true || action.risk === 'destructive'
}

export function getTableRowActionLabel(action: ActionConfig): string {
  if (action.disabledReason === undefined || action.disabledReason.trim() === '') return action.label
  return `${action.label}（${action.disabledReason}）`
}

function isStateAction(action: ActionConfig): boolean {
  return action.risk === 'state-transition' || action.risk === 'approval'
}

function selectExplicitPrimaryActions(actions: ActionConfig[]): ActionConfig[] {
  if (actions.length <= 2) return actions

  // 当多个候选动作竞争主操作位时，至少保留一个当前状态迁移动作；
  // 这样“提交/撤回/开票”等不会因为被放在 secondaryActions 而永远
  // 排在编辑、下载之后。其余动作仍然进入更多菜单，不改变可达性。
  const stateAction = actions.find(isStateAction)
  const normalActions = actions.filter((action) => !isStateAction(action))
  const selected = normalActions.slice(0, stateAction === undefined ? 2 : 1)
  if (stateAction !== undefined) selected.push(stateAction)

  if (selected.length < 2) {
    for (const action of actions) {
      if (!selected.includes(action)) selected.push(action)
      if (selected.length === 2) break
    }
  }

  return selected
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
    !isDestructiveTableRowAction(action) &&
    canRenderAsDesktopPrimary(action)
  )
  const fallbackPrimary = actionable.find((action) =>
    primaryActions.includes(action) &&
    !isDestructiveTableRowAction(action) &&
    canRenderAsDesktopPrimary(action)
  )
  const promoted = explicitlyPrimary.length > 0
    ? selectExplicitPrimaryActions(explicitlyPrimary)
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

  const common = primaryActions.filter((action) => !isDestructiveTableRowAction(action))
  const more = secondaryActions.filter((action) => !isDestructiveTableRowAction(action))
  const danger = [...primaryActions, ...secondaryActions].filter(isDestructiveTableRowAction)

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
