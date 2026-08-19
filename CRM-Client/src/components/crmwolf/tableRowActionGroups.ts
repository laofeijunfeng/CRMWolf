import type { ActionConfig } from './tableRowActionTypes'

export interface TableRowActionSet {
  primaryActions?: ActionConfig[]
  secondaryActions?: ActionConfig[]
}

export interface TableRowActionGroup {
  key: 'common' | 'more' | 'danger'
  label: string
  items: ActionConfig[]
}

function isVisibleAction(action: ActionConfig): boolean {
  return action.visible !== false
}

export function groupTableRowActions(
  actions: TableRowActionSet | null | undefined
): TableRowActionGroup[] {
  const primaryActions = (actions?.primaryActions ?? []).filter(isVisibleAction)
  const secondaryActions = (actions?.secondaryActions ?? []).filter(isVisibleAction)

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
