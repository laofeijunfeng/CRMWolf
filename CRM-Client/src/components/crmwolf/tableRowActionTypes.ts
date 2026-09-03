import type { Component } from 'vue'

export interface ActionConfig {
  label: string
  handler: (row: Record<string, unknown>) => void
  visible?: boolean
  disabled?: boolean
  icon?: Component
  destructive?: boolean
  separator?: boolean
  /** 桌面列表中优先显示的主操作；最多展示两个，其余进入更多菜单 */
  desktopPrimary?: boolean
  /** 详情语义的动作由 DataTable 的详情入口承载，不重复投影到桌面操作区 */
  kind?: 'detail' | 'standard'
  /** 禁用时向用户解释原因，同时供按钮、菜单和读屏使用 */
  disabledReason?: string
}
