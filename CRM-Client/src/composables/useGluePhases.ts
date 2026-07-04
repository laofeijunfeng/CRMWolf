/**
 * Glue Phases 状态管理 composable
 *
 * Task 5.3: 替代 ReAct useAgentExecutionLog，管理 Glue SSE 阶段状态
 * 设计原则：语义阶段驱动（intent/entity/preview/execute），而非 ReAct 轮次驱动
 */

import { shallowRef, type Ref } from 'vue'
import type { GlueSSEEvent } from '@/types/aiAssistant'

export interface Phase {
  id: string
  type: 'intent' | 'entity' | 'preview' | 'execute' | 'result' | 'error'
  summary: string
  detail?: unknown
  awaitingUser: boolean
  interaction?: 'entity_pick' | 'slot_fill' | 'danger_confirm'
  /** outcome 分态：win/lose/generic（仅 preview 阶段） */
  outcomeType?: 'win' | 'lose' | 'generic'
  data?: unknown
  status: 'running' | 'done' | 'failed'
}

const LOCAL_STORAGE_KEY_PREFIX = 'glue_phases_'
const AUTO_COLLAPSE_DELAY = 3000 // 3s auto-collapse（复用旧计时）

/**
 * 管理 Glue SSE 阶段状态
 * @param conversationId 对话 ID（用于 localStorage 缓存）
 */
export function useGluePhases(conversationId: Ref<string>) {
  const phases = shallowRef<Phase[]>([])
  const collapsed = shallowRef<boolean>(false)

  /**
   * 处理 SSE 事件，追加/更新 Phase
   */
  const handleSSEEvent = (ev: GlueSSEEvent): void => {
    switch (ev.event) {
      case 'start':
        // 清空旧 phases
        phases.value = []
        collapsed.value = false
        break

      case 'intent':
        phases.value = [...phases.value, mkIntentPhase(ev.data)]
        break

      case 'entity':
        phases.value = appendEntityPhase(phases.value, ev.data)
        break

      case 'preview':
        phases.value = appendPreviewPhase(phases.value, ev.data)
        break

      case 'execute':
        phases.value = appendExecutePhase(phases.value, ev.data)
        break

      case 'result':
        // 收尾阶段
        phases.value = [...phases.value, mkResultPhase(ev.data)]
        triggerAutoCollapse()
        break

      case 'error':
        phases.value = [...phases.value, mkErrorPhase(ev.data)]
        break

      case 'complete':
        // 最终完成，触发 auto-collapse
        triggerAutoCollapse()
        break
    }

    // 持久化到 localStorage
    persistToLocalStorage(conversationId.value, phases.value)
  }

  /**
   * 清空 phases
   */
  const clear = (): void => {
    phases.value = []
    collapsed.value = false
    clearLocalStorage(conversationId.value)
  }

  /**
   * 从 localStorage 加载（用于恢复历史对话）
   */
  const loadFromStorage = (): void => {
    const stored = localStorage.getItem(`${LOCAL_STORAGE_KEY_PREFIX}${conversationId.value}`)
    if (stored) {
      try {
        phases.value = JSON.parse(stored) as Phase[]
      } catch {
        // 忽略解析错误
      }
    }
  }

  return {
    phases,
    collapsed,
    handleSSEEvent,
    clear,
    loadFromStorage,
  }
}

// ==================== Phase 构造函数 ====================

function mkIntentPhase(data: { intent_type: string; confidence: number; auto_executed?: boolean }): Phase {
  return {
    id: `intent-${Date.now()}`,
    type: 'intent',
    summary: `识别意图: ${data.intent_type}`,
    detail: data,
    awaitingUser: false,
    status: data.auto_executed ? 'done' : 'running',
  }
}

function appendEntityPhase(current: Phase[], data: {
  entity_type: string
  status: 'resolved' | 'ambiguous' | 'not_found'
  resolved_id?: number
  candidates?: { id: number; name: string; hint: string }[]
}): Phase[] {
  const phase: Phase = {
    id: `entity-${Date.now()}`,
    type: 'entity',
    summary: data.status === 'resolved' ? `已锁定: ${data.entity_type}` : `消解中: ${data.entity_type}`,
    detail: data,
    awaitingUser: data.status === 'ambiguous',
    interaction: data.status === 'ambiguous' ? 'entity_pick' : undefined,
    status: data.status === 'resolved' ? 'done' : data.status === 'not_found' ? 'failed' : 'running',
  }
  return [...current, phase]
}

function appendPreviewPhase(current: Phase[], data: {
  intent_type: string
  risk_level: string
  requires_confirmation: boolean
  outcome_type?: 'win' | 'lose' | 'generic'
  preview_snapshot?: { changes: unknown[]; message: string }
}): Phase[] {
  const phase: Phase = {
    id: `preview-${Date.now()}`,
    type: 'preview',
    summary: data.requires_confirmation ? '待确认' : '预览已生成',
    detail: data.preview_snapshot,
    awaitingUser: data.requires_confirmation,
    interaction: data.requires_confirmation ? 'danger_confirm' : undefined,
    outcomeType: data.outcome_type ?? 'generic',
    data,
    status: 'running',
  }
  return [...current, phase]
}

function appendExecutePhase(current: Phase[], data: { success: boolean; message: string }): Phase[] {
  // 更新 preview 阶段状态为 done/failed
  const updated = current.map(p =>
    p.type === 'preview' ? { ...p, status: data.success ? 'done' : 'failed' } : p
  )

  const phase: Phase = {
    id: `execute-${Date.now()}`,
    type: 'execute',
    summary: data.success ? '执行成功' : '执行失败',
    detail: data,
    awaitingUser: false,
    status: data.success ? 'done' : 'failed',
  }
  return [...updated, phase]
}

function mkResultPhase(data: { success: boolean; message: string }): Phase {
  return {
    id: `result-${Date.now()}`,
    type: 'result',
    summary: data.success ? '完成' : '失败',
    detail: data,
    awaitingUser: false,
    status: data.success ? 'done' : 'failed',
  }
}

function mkErrorPhase(data: { message: string; recovery?: { suggestions: string[] } }): Phase {
  return {
    id: `error-${Date.now()}`,
    type: 'error',
    summary: '错误',
    detail: data,
    awaitingUser: false,
    interaction: undefined,
    data,
    status: 'failed',
  }
}

// ==================== 辅助函数 ====================

function persistToLocalStorage(conversationId: string, phases: Phase[]): void {
  try {
    localStorage.setItem(`${LOCAL_STORAGE_KEY_PREFIX}${conversationId}`, JSON.stringify(phases))
  } catch {
    // localStorage 可能不可用
  }
}

function clearLocalStorage(conversationId: string): void {
  try {
    localStorage.removeItem(`${LOCAL_STORAGE_KEY_PREFIX}${conversationId}`)
  } catch {
    // 忽略
  }
}

function triggerAutoCollapse(): void {
  setTimeout(() => {
    // 触发 collapsed 状态（由外部组件监听）
    // 注：auto-collapse 逻辑由使用方控制，这里只提供时机
  }, AUTO_COLLAPSE_DELAY)
}