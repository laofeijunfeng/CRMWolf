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

export interface HeaderConfig {
  showBack?: boolean
  backRoute?: string | null
  actions?: HeaderAction[]
  /** 左侧自定义按钮（替代默认返回按钮） */
  leftAction?: HeaderLeftAction | null
}

export const useHeaderStore = defineStore('header', () => {
  const showBack = ref(false)
  const backRoute = ref<string | null>(null)
  const actions = ref<HeaderAction[]>([])
  const leftAction = ref<HeaderLeftAction | null>(null)

  const hasActions = computed(() => actions.value.length > 0)
  const hasLeftAction = computed(() => leftAction.value !== null)

  function configure(config: HeaderConfig): void {
    if (config.showBack !== undefined) showBack.value = config.showBack
    if (config.backRoute !== undefined) backRoute.value = config.backRoute
    if (config.actions !== undefined) actions.value = config.actions
    if (config.leftAction !== undefined) leftAction.value = config.leftAction
  }

  function clear(): void {
    showBack.value = false
    backRoute.value = null
    actions.value = []
    leftAction.value = null
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

  return {
    showBack,
    backRoute,
    actions,
    leftAction,
    hasActions,
    hasLeftAction,
    configure,
    clear,
    setBack,
    setActions,
    addAction,
    removeAction,
    setLeftAction
  }
})