/**
 * Sidebar 状态管理 Composable
 *
 * 提供 Sidebar 状态的响应式管理和转换逻辑
 */

import { ref, computed, readonly } from 'vue'
import {
  SidebarState,
  StateUIConfig,
  StateTransitionEvent,
  isValidTransition,
  getStateUIConfig
} from '@/types/sidebar'

/**
 * Sidebar 状态管理 Hook
 *
 * 提供状态管理、UI 配置获取、状态转换等功能
 */
export function useSidebarState() {
  // 当前状态（响应式）
  const currentState = ref<SidebarState>(SidebarState.IDLE)

  // 状态转换历史（用于调试和审计）
  const transitionHistory = ref<StateTransitionEvent[]>([])

  // 当前状态的 UI 配置（计算属性）
  const uiConfig = computed<StateUIConfig>(() => {
    return getStateUIConfig(currentState.value)
  })

  /**
   * 转换到新状态
   *
   * @param newState - 目标状态
   * @param reason - 转换原因
   * @param data - 相关数据（可选）
   * @returns 是否成功转换
   */
  function transitionTo(
    newState: SidebarState,
    reason: StateTransitionReason,
    data?: Record<string, unknown>
  ): boolean {
    const fromState = currentState.value

    // 检查转换是否合法
    if (!isValidTransition(fromState, newState)) {
      console.warn(
        `Invalid state transition: ${fromState} -> ${newState} (reason: ${reason})`
      )
      return false
    }

    // 记录转换事件
    const event: StateTransitionEvent = {
      toState: newState,
      reason,
      timestamp: new Date(),
      data
    }

    transitionHistory.value.push(event)

    // 更新状态
    currentState.value = newState

    console.log(
      `Sidebar state transition: ${fromState} -> ${newState} (reason: ${reason})`
    )

    return true
  }

  /**
   * 重置到 IDLE 状态
   *
   * 用于"停止操作"或"新对话"场景
   */
  function resetToIdle(reason: 'user_stop' | 'user_new_chat' = 'user_new_chat'): void {
    currentState.value = SidebarState.IDLE
    transitionHistory.value = []

    console.log(`Sidebar reset to IDLE (reason: ${reason})`)
  }

  /**
   * 用户提交意图
   *
   * 从 IDLE 状态转换到 COLLECTING 状态
   */
  function userSubmit(userInput: string): boolean {
    const data = { userInput }
    return transitionTo(SidebarState.COLLECTING, 'user_submit', data)
  }

  /**
   * AI 完成意图收集
   *
   * 从 COLLECTING 状态转换到 RESOLVING_ENTITY 状态
   */
  function aiCollectingDone(intentData: Record<string, unknown>): boolean {
    return transitionTo(SidebarState.RESOLVING_ENTITY, 'ai_collecting_done', intentData)
  }

  /**
   * AI 发现歧义
   *
   * 从 RESOLVING_ENTITY 状态转换到 RESOLVING_AMBIGUITY 状态
   */
  function aiAmbiguityDetected(ambiguousEntities: unknown[]): boolean {
    const data = { ambiguousEntities }
    return transitionTo(
      SidebarState.RESOLVING_AMBIGUITY,
      'ai_ambiguity_detected',
      data
    )
  }

  /**
   * AI 完成 Preview 生成
   *
   * 从 RESOLVING_ENTITY/RESOLVING_AMBIGUITY 状态转换到 PREVIEW 状态
   */
  function aiPreviewGenerated(previewData: Record<string, unknown>): boolean {
    return transitionTo(SidebarState.PREVIEW, 'ai_preview_generated', previewData)
  }

  /**
   * 用户确认 Preview
   *
   * 从 PREVIEW 状态转换到 EXECUTING 状态
   */
  function userConfirm(): boolean {
    return transitionTo(SidebarState.EXECUTING, 'user_confirm')
  }

  /**
   * 用户取消操作
   *
   * 从 PREVIEW 状态转换到 IDLE 状态
   */
  function userCancel(): boolean {
    return resetToIdle('user_cancel')
  }

  /**
   * 用户停止操作
   *
   * 从 EXECUTING 状态转换到 IDLE 状态
   */
  function userStop(): void {
    resetToIdle('user_stop')
  }

  /**
   * AI 完成执行
   *
   * 从 EXECUTING 状态转换到 COMPLETED 状态
   */
  function aiExecutionDone(result: Record<string, unknown>): boolean {
    return transitionTo(SidebarState.COMPLETED, 'ai_execution_done', result)
  }

  /**
   * AI 执行失败
   *
   * 从 EXECUTING 状态转换到 IDLE 状态
   */
  function aiExecutionFailed(error: unknown): void {
    const data = { error }
    transitionTo(SidebarState.IDLE, 'ai_execution_failed', data)
  }

  /**
   * 用户点击新对话
   *
   * 从 COMPLETED 状态转换到 IDLE 状态
   */
  function userNewChat(): void {
    resetToIdle('user_new_chat')
  }

  /**
   * 用户选择实体
   *
   * 从 RESOLVING_AMBIGUITY 状态转换到 PREVIEW 状态
   */
  function userSelectEntity(selectedEntity: unknown): boolean {
    const data = { selectedEntity }
    return transitionTo(SidebarState.PREVIEW, 'user_select_entity', data)
  }

  /**
   * 获取最近的状态转换事件
   *
   * @param count - 获取数量（默认最近10条）
   * @returns 状态转换事件数组
   */
  function getRecentTransitions(count: number = 10): StateTransitionEvent[] {
    return transitionHistory.value.slice(-count)
  }

  /**
   * 检查当前状态是否为指定状态
   *
   * @param state - 要检查的状态
   * @returns 是否匹配
   */
  function isState(state: SidebarState): boolean {
    return currentState.value === state
  }

  /**
   * 检查当前状态是否为活跃状态（非 IDLE）
   *
   * @returns 是否活跃
   */
  function isActive(): boolean {
    return currentState.value !== SidebarState.IDLE
  }

  return {
    // 状态（只读）
    state: readonly(currentState),

    // UI 配置（计算属性）
    uiConfig,

    // 状态转换历史（只读）
    history: readonly(transitionHistory),

    // 状态转换方法
    transitionTo,
    resetToIdle,

    // 用户触发方法
    userSubmit,
    userConfirm,
    userCancel,
    userStop,
    userNewChat,
    userSelectEntity,

    // AI 触发方法
    aiCollectingDone,
    aiAmbiguityDetected,
    aiPreviewGenerated,
    aiExecutionDone,
    aiExecutionFailed,

    // 辅助方法
    getRecentTransitions,
    isState,
    isActive
  }
}

/**
 * 导出类型定义供外部使用
 */
export type SidebarStateHook = ReturnType<typeof useSidebarState>