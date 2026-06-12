/**
 * Sidebar 状态类型定义
 *
 * 用于 AI Assistant Sidebar 的状态管理和 UI 映射
 */

/**
 * Sidebar 状态枚举
 *
 * 定义 Sidebar 的所有可能状态
 */
export enum SidebarState {
  /** 空闲状态：显示主输入框，等待用户输入 */
  IDLE = 'IDLE',

  /** 收集意图：AI 正在解析用户输入 */
  COLLECTING = 'COLLECTING',

  /** 解析实体：AI 正在提取和解析实体信息 */
  RESOLVING_ENTITY = 'RESOLVING_ENTITY',

  /** 消解歧义：发现多个匹配实体，需要用户选择 */
  RESOLVING_AMBIGUITY = 'RESOLVING_AMBIGUITY',

  /** 预览确认：生成操作预览，等待用户确认 */
  PREVIEW = 'PREVIEW',

  /** 执行中：正在执行操作 */
  EXECUTING = 'EXECUTING',

  /** 完成：操作完成，显示撤销提示 */
  COMPLETED = 'COMPLETED'
}

/**
 * 状态 UI 配置接口
 *
 * 定义每个状态下 UI 元素的显示配置
 */
export interface StateUIConfig {
  /** 是否显示主输入框 */
  showInputBox: boolean

  /** 是否显示 Sidebar */
  showSidebar: boolean

  /** 是否显示停止操作按钮 */
  showStopButton: boolean

  /** 是否显示新对话按钮 */
  showNewChatButton: boolean

  /** 是否显示 Mini-map 进度 */
  showMiniMap: boolean

  /** 是否显示实体选择界面 */
  showEntitySelect: boolean

  /** 是否显示 Preview 详情 */
  showPreviewDetails: boolean
}

/**
 * 状态 UI 映射表
 *
 * 定义每个状态对应的 UI 配置
 */
export const StateUIMap: Record<SidebarState, StateUIConfig> = {
  [SidebarState.IDLE]: {
    showInputBox: true,
    showSidebar: false,
    showStopButton: false,
    showNewChatButton: false,
    showMiniMap: false,
    showEntitySelect: false,
    showPreviewDetails: false
  },

  [SidebarState.COLLECTING]: {
    showInputBox: false,
    showSidebar: true,
    showStopButton: false,
    showNewChatButton: false,
    showMiniMap: true,
    showEntitySelect: false,
    showPreviewDetails: false
  },

  [SidebarState.RESOLVING_ENTITY]: {
    showInputBox: false,
    showSidebar: true,
    showStopButton: true,
    showNewChatButton: false,
    showMiniMap: true,
    showEntitySelect: false,
    showPreviewDetails: false
  },

  [SidebarState.RESOLVING_AMBIGUITY]: {
    showInputBox: false,
    showSidebar: true,
    showStopButton: true,
    showNewChatButton: false,
    showMiniMap: true,
    showEntitySelect: true,
    showPreviewDetails: false
  },

  [SidebarState.PREVIEW]: {
    showInputBox: false,
    showSidebar: true,
    showStopButton: true,
    showNewChatButton: false,
    showMiniMap: false,
    showEntitySelect: false,
    showPreviewDetails: true
  },

  [SidebarState.EXECUTING]: {
    showInputBox: false,
    showSidebar: true,
    showStopButton: true,
    showNewChatButton: false,
    showMiniMap: true,
    showEntitySelect: false,
    showPreviewDetails: false
  },

  [SidebarState.COMPLETED]: {
    showInputBox: false,
    showSidebar: true,
    showStopButton: false,
    showNewChatButton: true,
    showMiniMap: false,
    showEntitySelect: false,
    showPreviewDetails: false
  }
}

/**
 * 合法状态转换映射
 *
 * 定义哪些状态转换是合法的
 */
export const ValidStateTransitions: Record<SidebarState, SidebarState[]> = {
  [SidebarState.IDLE]: [
    SidebarState.COLLECTING
  ],

  [SidebarState.COLLECTING]: [
    SidebarState.RESOLVING_ENTITY,
    SidebarState.IDLE // 用户取消
  ],

  [SidebarState.RESOLVING_ENTITY]: [
    SidebarState.RESOLVING_AMBIGUITY,
    SidebarState.PREVIEW,
    SidebarState.EXECUTING, // 直接执行（无 Preview）
    SidebarState.IDLE // 用户停止
  ],

  [SidebarState.RESOLVING_AMBIGUITY]: [
    SidebarState.PREVIEW,
    SidebarState.EXECUTING,
    SidebarState.IDLE // 用户停止
  ],

  [SidebarState.PREVIEW]: [
    SidebarState.EXECUTING, // 用户确认
    SidebarState.RESOLVING_ENTITY, // 用户修改参数
    SidebarState.IDLE // 用户取消
  ],

  [SidebarState.EXECUTING]: [
    SidebarState.COMPLETED,
    SidebarState.IDLE // 用户停止或失败
  ],

  [SidebarState.COMPLETED]: [
    SidebarState.IDLE // 用户点击新对话
  ]
}

/**
 * 检查状态转换是否合法
 *
 * @param from - 当前状态
 * @param to - 目标状态
 * @returns 是否为合法转换
 */
export function isValidTransition(from: SidebarState, to: SidebarState): boolean {
  const validTargets = ValidStateTransitions[from]
  return validTargets ? validTargets.includes(to) : false
}

/**
 * 获取状态的 UI 配置
 *
 * @param state - Sidebar 状态
 * @returns UI 配置对象
 */
export function getStateUIConfig(state: SidebarState): StateUIConfig {
  return StateUIMap[state]
}

/**
 * 状态转换触发原因类型
 */
export type StateTransitionReason =
  | 'user_submit' // 用户提交意图
  | 'user_confirm' // 用户确认 Preview
  | 'user_cancel' // 用户取消
  | 'user_stop' // 用户停止操作
  | 'user_new_chat' // 用户点击新对话
  | 'user_select_entity' // 用户选择实体
  | 'ai_collecting_done' // AI 完成意图收集
  | 'ai_entity_resolved' // AI 完成实体解析
  | 'ai_ambiguity_detected' // AI 发现歧义
  | 'ai_preview_generated' // AI 生成 Preview
  | 'ai_execution_done' // AI 完成执行
  | 'ai_execution_failed' // AI 执行失败

/**
 * 状态转换事件接口
 */
export interface StateTransitionEvent {
  /** 目标状态 */
  toState: SidebarState

  /** 转换原因 */
  reason: StateTransitionReason

  /** 转换时间戳 */
  timestamp: Date

  /** 相关数据（可选） */
  data?: Record<string, unknown>
}