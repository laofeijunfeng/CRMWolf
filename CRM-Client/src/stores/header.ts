// CRM-Client/src/stores/header.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Component } from 'vue'

export interface HeaderAction {
  id: string
  label: string
  handler: () => void
  type?: 'primary' | 'success' | 'danger' | 'default'
  icon?: Component
  disabled?: boolean
  visible?: boolean
  ariaLabel?: string  // Phase 6: Accessibility
}

export interface HeaderLeftAction {
  /** 左侧按钮图标 */
  icon: Component
  /** 左侧按钮点击处理 */
  handler: () => void
  /** 按钮是否处于激活状态（用于样式） */
  active?: boolean
  /** aria-label */
  ariaLabel?: string
}

export interface TabItem {
  /** Tab 唯一标识 */
  key: string
  /** Tab 显示文字 */
  label: string
  /** 是否禁用 */
  disabled?: boolean
  /** 徽标内容（如待办数量） */
  badge?: number | string
  /** 是否为用户自定义视图 */
  isCustomView?: boolean
  /** 自定义视图 ID */
  customViewId?: number
  /** 重命名处理 */
  onRename?: () => void
  /** 移到最前处理 */
  onMoveToFirst?: () => void
  /** 删除处理 */
  onDelete?: () => void
}

export interface HeaderConfig {
  showBack?: boolean
  backRoute?: string | null
  actions?: HeaderAction[]
  /** 左侧自定义按钮（替代默认返回按钮） */
  leftAction?: HeaderLeftAction | null
  /** ContextTabs 配置（替代页面标题） */
  tabs?: TabItem[] | null
  /** 当前激活的 Tab */
  activeTab?: string
}

const areTabsEqual = (left: TabItem[] | null, right: TabItem[] | null): boolean => {
  if (left === right) return true
  if (left === null || right === null) return left === right
  if (left.length !== right.length) return false

  return left.every((tab, index) => {
    const nextTab = right[index]
    return nextTab !== undefined &&
      tab.key === nextTab.key &&
      tab.label === nextTab.label &&
      tab.disabled === nextTab.disabled &&
      tab.badge === nextTab.badge &&
      tab.isCustomView === nextTab.isCustomView &&
      tab.customViewId === nextTab.customViewId
  })
}

const areActionsEqual = (left: HeaderAction[], right: HeaderAction[]): boolean => {
  if (left === right) return true
  if (left.length !== right.length) return false

  return left.every((action, index) => {
    const nextAction = right[index]
    return nextAction !== undefined &&
      action.id === nextAction.id &&
      action.label === nextAction.label &&
      action.type === nextAction.type &&
      action.icon === nextAction.icon &&
      action.disabled === nextAction.disabled &&
      action.visible === nextAction.visible &&
      action.ariaLabel === nextAction.ariaLabel
  })
}

export const useHeaderStore = defineStore('header', () => {
  const showBack = ref(false)
  const backRoute = ref<string | null>(null)
  const actions = ref<HeaderAction[]>([])
  const leftAction = ref<HeaderLeftAction | null>(null)
  const tabs = ref<TabItem[] | null>(null)
  const activeTab = ref<string>('')

  const hasActions = computed(() => actions.value.length > 0)
  const hasLeftAction = computed(() => leftAction.value !== null)
  const hasTabs = computed(() => tabs.value !== null && tabs.value.length > 0)

  function configure(config: HeaderConfig): void {
    if (config.showBack !== undefined) showBack.value = config.showBack
    if (config.backRoute !== undefined) backRoute.value = config.backRoute
    if (config.actions !== undefined) actions.value = config.actions
    if (config.leftAction !== undefined) leftAction.value = config.leftAction
    if (config.tabs !== undefined) tabs.value = config.tabs
    if (config.activeTab !== undefined) activeTab.value = config.activeTab
  }

  function clear(): void {
    showBack.value = false
    backRoute.value = null
    actions.value = []
    leftAction.value = null
    tabs.value = null
    activeTab.value = ''
  }

  function setBack(show: boolean, route?: string): void {
    showBack.value = show
    backRoute.value = route ?? null
    // 设置 back 时清除 leftAction
    if (show) {
      leftAction.value = null
    }
  }

  function setActions(newActions: HeaderAction[]): void {
    if (areActionsEqual(actions.value, newActions)) {
      actions.value.forEach((action, index) => {
        const nextAction = newActions[index]
        if (nextAction !== undefined) {
          action.handler = nextAction.handler
        }
      })
      return
    }
    actions.value = newActions
  }

  function addAction(action: HeaderAction): void {
    actions.value.push(action)
  }

  function removeAction(id: string): void {
    actions.value = actions.value.filter(a => a.id !== id)
  }

  function setLeftAction(action: HeaderLeftAction | null): void {
    leftAction.value = action
    // 设置 leftAction 时禁用 back
    if (action) {
      showBack.value = false
      backRoute.value = null
    }
  }

  function setTabs(newTabs: TabItem[] | null, initialTab?: string): void {
    const nextActiveTab = ((): string => {
      if (!newTabs || newTabs.length === 0) return ''
      if (initialTab !== undefined && initialTab !== '' && newTabs.some(tab => tab.key === initialTab)) return initialTab
      if (activeTab.value && newTabs.some(tab => tab.key === activeTab.value)) return activeTab.value
      return newTabs[0]?.key ?? ''
    })()

    if (areTabsEqual(tabs.value, newTabs)) {
      tabs.value?.forEach((tab, index) => {
        const nextTab = newTabs?.[index]
        if (nextTab === undefined) return
        if (nextTab.onRename === undefined) {
          delete tab.onRename
        } else {
          tab.onRename = nextTab.onRename
        }
        if (nextTab.onMoveToFirst === undefined) {
          delete tab.onMoveToFirst
        } else {
          tab.onMoveToFirst = nextTab.onMoveToFirst
        }
        if (nextTab.onDelete === undefined) {
          delete tab.onDelete
        } else {
          tab.onDelete = nextTab.onDelete
        }
      })
    } else {
      tabs.value = newTabs
    }

    if (activeTab.value !== nextActiveTab) {
      activeTab.value = nextActiveTab
    }

    if (!newTabs || newTabs.length === 0) {
      activeTab.value = ''
    }
  }

  function setActiveTab(tabKey: string): void {
    activeTab.value = tabKey
  }

  return {
    showBack,
    backRoute,
    actions,
    leftAction,
    tabs,
    activeTab,
    hasActions,
    hasLeftAction,
    hasTabs,
    configure,
    clear,
    setBack,
    setActions,
    addAction,
    removeAction,
    setLeftAction,
    setTabs,
    setActiveTab
  }
})
