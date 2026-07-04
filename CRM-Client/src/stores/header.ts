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

export interface HeaderConfig {
  showBack?: boolean
  backRoute?: string | null
  actions?: HeaderAction[]
}

export const useHeaderStore = defineStore('header', () => {
  const showBack = ref(false)
  const backRoute = ref<string | null>(null)
  const actions = ref<HeaderAction[]>([])

  const hasActions = computed(() => actions.value.length > 0)

  function configure(config: HeaderConfig): void {
    if (config.showBack !== undefined) showBack.value = config.showBack
    if (config.backRoute !== undefined) backRoute.value = config.backRoute
    if (config.actions !== undefined) actions.value = config.actions
  }

  function clear(): void {
    showBack.value = false
    backRoute.value = null
    actions.value = []
  }

  function setBack(show: boolean, route?: string): void {
    showBack.value = show
    backRoute.value = route ?? null
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

  return {
    showBack,
    backRoute,
    actions,
    hasActions,
    configure,
    clear,
    setBack,
    setActions,
    addAction,
    removeAction
  }
})