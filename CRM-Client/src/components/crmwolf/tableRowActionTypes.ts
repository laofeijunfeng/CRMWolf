import type { Component } from 'vue'

export interface ActionConfig {
  label: string
  handler: (row: Record<string, unknown>) => void
  visible?: boolean
  disabled?: boolean
  icon?: Component
  destructive?: boolean
  separator?: boolean
}
