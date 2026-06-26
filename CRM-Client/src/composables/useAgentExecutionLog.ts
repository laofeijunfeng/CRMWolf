/**
 * Agent Execution Log Composable
 *
 * 将 SSE 事件流映射为业务化的执行步骤展示
 */

import { ref, readonly, watch, computed } from 'vue'
import { useAIConversationStore } from '@/stores/aiConversation'
import {
  ExecutionStep,
  ExecutionStepType,
  getBusinessTitle,
  formatBusinessParams
} from '@/types/agentExecution'
import type { AIAssistantSSEEvent } from '@/api/aiAssistant'

/**
 * Agent Execution Log Hook
 *
 * 提供 SSE 事件映射、执行日志管理等功能
 */
export function useAgentExecutionLog() {
  // 执行步骤列表（响应式）
  const steps = ref<ExecutionStep[]>([])

  // 当前轮次
  const currentRound = ref<number>(0)

  // 最大轮次
  const maxRounds = ref<number>(5)

  // 是否正在执行
  const isExecuting = ref<boolean>(false)

  // 是否已完成
  const isCompleted = ref<boolean>(false)

  // 是否有错误
  const hasError = ref<boolean>(false)

  // ReAct 会话 ID
  const sessionId = ref<string | undefined>(undefined)

  // 是否应该自动展开（需求文档 5.3：Human-in-the-Loop 场景）
  const shouldAutoExpand = ref<boolean>(false)

  // ========== Task 15: 自动收起逻辑 ==========

  // 展开状态（默认展开，执行中）
  const expanded = ref<boolean>(true)

  // 自动收起计时器
  const autoCollapseTimer = ref<number | null>(null)

  // 自动收起倒计时（显示给用户）
  const autoCollapseCountdown = ref<number>(0)

  // 用户是否手动操作（取消自动收起）
  const userCancelledAutoCollapse = ref<boolean>(false)

  /**
   * 生成步骤唯一标识
   */
  function generateStepId(): string {
    return `step-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
  }

  /**
   * 处理 SSE 事件
   *
   * @param event - SSE 事件对象
   */
  function handleSSEEvent(event: AIAssistantSSEEvent): void {
    switch (event.event) {
      case 'react_start':
        handleReactStart(event)
        break

      case 'round_start':
        handleRoundStart(event)
        break

      case 'tool_call':
        handleToolCall(event)
        break

      case 'tool_result':
        handleToolResult(event)
        break

      case 'waiting_for_user':
        handleWaitingForUser(event)
        break

      case 'disambiguation_required':
        handleDisambiguationRequired(event)
        break

      case 'awaiting_confirmation':
        handleAwaitingConfirmation(event)
        break

      case 'round_completed':
        handleRoundCompleted(event)
        break

      case 'react_complete':
        handleReactComplete(event)
        break

      case 'max_rounds_reached':
        handleMaxRoundsReached(event)
        break

      case 'error':
        handleError(event)
        break

      default:
        console.warn(`Unknown SSE event type: ${event.event}`)
    }
  }

  /**
   * 处理 react_start 事件
   */
  function handleReactStart(event: AIAssistantSSEEvent): void {
    // 清除旧的执行步骤，避免跨会话数据混淆
    clear()

    sessionId.value = event.session_id
    maxRounds.value = event.max_rounds ?? 5
    isExecuting.value = true

    const step: ExecutionStep = {
      id: generateStepId(),
      type: ExecutionStepType.REACT_START,
      title: '开始执行',
      description: `ReAct 循环开始（最大轮次：${maxRounds.value}）`,
      timestamp: new Date()
    }

    if (event.session_id !== undefined) {
      step.sessionId = event.session_id
    }

    steps.value.push(step)
  }

  /**
   * 处理 round_start 事件
   */
  function handleRoundStart(event: AIAssistantSSEEvent): void {
    currentRound.value = event.round ?? 0

    const step: ExecutionStep = {
      id: generateStepId(),
      type: ExecutionStepType.ROUND_START,
      title: `轮次 ${currentRound.value}`,
      description: `开始第 ${currentRound.value} 轮分析`,
      timestamp: new Date(),
      round: currentRound.value
    }

    steps.value.push(step)
  }

  /**
   * 处理 tool_call 事件
   *
   * 需求文档 4.4：
   * - ThinkingBubble 显示 AI 推理过程（thinking）
   * - 业务参数显示格式化的工具参数（businessParams）
   */
  function handleToolCall(event: AIAssistantSSEEvent): void {
    const toolName = event.tool ?? 'unknown'
    const businessTitle = getBusinessTitle(toolName)
    const params = event.params ?? {}
    const businessParams = formatBusinessParams(params, businessTitle)

    // thinking: AI 推理过程（需求文档 ThinkingBubble 显示内容）
    // 如果后端未发送 thinking，使用业务参数作为兜底
    const thinking = event.thinking ?? event.reasoning ?? businessParams

    const step: ExecutionStep = {
      id: generateStepId(),
      type: ExecutionStepType.TOOL_CALL,
      title: businessTitle,
      description: thinking,  // ← AI 推理过程（ThinkingBubble 显示）
      timestamp: new Date()
    }

    if (event.round !== undefined) {
      step.round = event.round
    }

    step.tool = toolName
    step.params = params
    step.businessParams = businessParams  // ← 业务化参数（单独显示）

    steps.value.push(step)
  }

  /**
   * 处理 tool_result 事件
   */
  function handleToolResult(event: AIAssistantSSEEvent): void {
    const toolName = event.tool ?? 'unknown'
    // 后端返回嵌套的 result 字段，需要提取
    const resultData = event.result ?? {}
    const success = resultData.success ?? event.success ?? false
    const message = resultData.message ?? event.message ?? ''

    const step: ExecutionStep = {
      id: generateStepId(),
      type: ExecutionStepType.TOOL_RESULT,
      title: success ? '执行成功' : '执行失败',
      description: message || (success ? `${getBusinessTitle(toolName)} 完成` : `${getBusinessTitle(toolName)} 失败`),
      timestamp: new Date()
    }

    if (event.round !== undefined) {
      step.round = event.round
    }

    step.tool = toolName
    step.success = success
    step.result = resultData.data ?? event.data

    steps.value.push(step)
  }

  /**
   * 处理 waiting_for_user 事件
   */
  function handleWaitingForUser(event: AIAssistantSSEEvent): void {
    const step: ExecutionStep = {
      id: generateStepId(),
      type: ExecutionStepType.WAITING_FOR_USER,
      title: '等待用户输入',
      description: event.question ?? '需要用户提供更多信息',
      timestamp: new Date()
    }

    if (event.round !== undefined) {
      step.round = event.round
    }

    step.data = {
      question: event.question,
      options: event.options,
      missing_fields: event.missing_fields,
      context_hint: event.context_hint,
      interaction_type: event.interaction_type
    }

    steps.value.push(step)

    // ← 需求文档 5.3：自动展开（需要用户关注）
    shouldAutoExpand.value = true
  }

  /**
   * 处理 disambiguation_required 事件
   */
  function handleDisambiguationRequired(event: AIAssistantSSEEvent): void {
    const step: ExecutionStep = {
      id: generateStepId(),
      type: ExecutionStepType.DISAMBIGUATION_REQUIRED,
      title: '需要消歧',
      description: `发现多个匹配实体，请选择具体目标`,
      timestamp: new Date()
    }

    if (event.round !== undefined) {
      step.round = event.round
    }

    step.data = {
      entity_type: event.entity_type,
      candidates: event.candidates
    }

    steps.value.push(step)
  }

  /**
   * 处理 awaiting_confirmation 事件
   */
  function handleAwaitingConfirmation(event: AIAssistantSSEEvent): void {
    const step: ExecutionStep = {
      id: generateStepId(),
      type: ExecutionStepType.AWAITING_CONFIRMATION,
      title: '等待确认',
      description: '操作已生成，请确认是否执行',
      timestamp: new Date()
    }

    if (event.round !== undefined) {
      step.round = event.round
    }

    step.data = event.data

    steps.value.push(step)
  }

  /**
   * 处理 round_completed 事件
   */
  function handleRoundCompleted(event: AIAssistantSSEEvent): void {
    const round = event.round ?? currentRound.value

    const step: ExecutionStep = {
      id: generateStepId(),
      type: ExecutionStepType.ROUND_COMPLETED,
      title: `轮次 ${round} 完成`,
      description: `第 ${round} 轮执行完成`,
      timestamp: new Date()
    }

    step.round = round
    step.data = event.results

    steps.value.push(step)
  }

  /**
   * 处理 react_complete 事件
   */
  function handleReactComplete(event: AIAssistantSSEEvent): void {
    isCompleted.value = true
    isExecuting.value = false

    const step: ExecutionStep = {
      id: generateStepId(),
      type: ExecutionStepType.REACT_COMPLETE,
      title: '执行完成',
      description: 'ReAct 循环已完成',
      timestamp: new Date()
    }

    if (event.session_id !== undefined) {
      step.sessionId = event.session_id
    }

    steps.value.push(step)

    // ← Task 12: SSE 流结束，保存 executionSteps 到当前 AI 消息
    saveExecutionStepsToCurrentMessage()
  }

  /**
   * 处理 max_rounds_reached 事件
   */
  function handleMaxRoundsReached(event: AIAssistantSSEEvent): void {
    isCompleted.value = true
    isExecuting.value = false

    const step: ExecutionStep = {
      id: generateStepId(),
      type: ExecutionStepType.MAX_ROUNDS_REACHED,
      title: '达到最大轮次',
      description: `已达到最大轮次限制（${maxRounds.value}）`,
      timestamp: new Date()
    }

    if (event.round !== undefined) {
      step.round = event.round
    }

    steps.value.push(step)
  }

  /**
   * 处理 error 事件
   */
  function handleError(event: AIAssistantSSEEvent): void {
    hasError.value = true
    isExecuting.value = false

    const step: ExecutionStep = {
      id: generateStepId(),
      type: ExecutionStepType.ERROR,
      title: '执行错误',
      description: event.message ?? '执行过程中发生错误',
      timestamp: new Date()
    }

    if (event.message !== undefined) {
      step.error = event.message
    }

    steps.value.push(step)

    // ← Task 12: SSE 流结束（错误），保存 executionSteps 到当前 AI 消息
    saveExecutionStepsToCurrentMessage()
  }

  /**
   * 清空执行日志
   */
  function clear(): void {
    steps.value = []
    currentRound.value = 0
    sessionId.value = undefined
    isExecuting.value = false
    isCompleted.value = false
    hasError.value = false
    shouldAutoExpand.value = false

    // Task 15: 清空自动收起相关状态
    expanded.value = true
    if (autoCollapseTimer.value) {
      clearTimeout(autoCollapseTimer.value)
      autoCollapseTimer.value = null
    }
    autoCollapseCountdown.value = 0
    userCancelledAutoCollapse.value = false
  }

  /**
   * 重置自动展开提示
   *
   * 父组件在展开后调用，避免重复触发
   */
  function resetAutoExpand(): void {
    shouldAutoExpand.value = false
  }

  /**
   * 获取指定轮次的步骤
   *
   * @param round - 轮次编号
   * @returns 该轮次的步骤列表
   */
  function getStepsByRound(round: number): ExecutionStep[] {
    return steps.value.filter(step => step.round === round)
  }

  /**
   * 获取最后一个步骤
   *
   * @returns 最后一个步骤（可能为 undefined）
   */
  function getLastStep(): ExecutionStep | undefined {
    return steps.value[steps.value.length - 1]
  }

  // ========== Task 15: 自动收起逻辑 ==========

  /**
   * 是否执行完成（REACT_COMPLETE 或 ERROR）
   */
  const isExecutionComplete = computed(() => {
    const lastStep = steps.value[steps.value.length - 1]
    return lastStep?.type === ExecutionStepType.REACT_COMPLETE || lastStep?.type === ExecutionStepType.ERROR
  })

  /**
   * 启动自动收起倒计时
   */
  function startAutoCollapseCountdown(): void {
    // 清除之前的计时器
    if (autoCollapseTimer.value) {
      clearTimeout(autoCollapseTimer.value)
      autoCollapseTimer.value = null
    }

    // 初始化倒计时
    autoCollapseCountdown.value = 3

    // 倒计时定时器（每秒更新）
    const countdownInterval = setInterval(() => {
      autoCollapseCountdown.value--
      if (autoCollapseCountdown.value <= 0) {
        clearInterval(countdownInterval)
      }
    }, 1000)

    // 3秒后自动收起
    autoCollapseTimer.value = window.setTimeout(() => {
      if (!userCancelledAutoCollapse.value && expanded.value) {
        expanded.value = false
        console.log('[Auto Collapse] Execution completed, collapsed after 3s')
      }
      clearInterval(countdownInterval)
      autoCollapseCountdown.value = 0
      autoCollapseTimer.value = null
    }, 3000)
  }

  /**
   * 取消自动收起（用户手动操作）
   */
  function cancelAutoCollapse(): void {
    userCancelledAutoCollapse.value = true

    if (autoCollapseTimer.value) {
      clearTimeout(autoCollapseTimer.value)
      autoCollapseTimer.value = null
    }

    autoCollapseCountdown.value = 0
    console.log('[Auto Collapse] User cancelled auto-collapse')
  }

  /**
   * 切换展开状态
   */
  function handleToggleExpand(): void {
    expanded.value = !expanded.value

    // 用户手动展开后，不再触发自动收起
    if (expanded.value) {
      cancelAutoCollapse()
    }
  }

  /**
   * 监听执行完成状态，触发自动收起
   */
  watch(isExecutionComplete, (isComplete) => {
    if (isComplete && expanded.value && !userCancelledAutoCollapse.value) {
      startAutoCollapseCountdown()
    }
  })

  // ========== Persistence Logic (Task 12) ==========

  /**
   * 获取 localStorage 缓存键
   *
   * @param conversationId - 可选的对话 ID（如果未提供，从 store 获取）
   * @returns 缓存键名
   */
  function getLocalStorageKey(conversationId?: number): string {
    const store = useAIConversationStore()
    // 兼容测试 mock：测试中 store.currentId 可能是 { value: 123 } 格式
    // 生产环境中 Pinia 会自动 unwrap，直接访问 store.currentId 即可
    const currentId = store.currentId
    const id = conversationId ?? (typeof currentId === 'object' && currentId !== null && 'value' in currentId ? (currentId as { value: number | null }).value : currentId as number | null)
    return `execution_steps_${id ?? 'temp'}`
  }

  /**
   * 将 executionSteps 缓存到 localStorage
   * 防止 SSE 中断导致数据丢失
   */
  function cacheToLocalStorage(): void {
    if (steps.value.length > 0) {
      const key = getLocalStorageKey()
      try {
        localStorage.setItem(key, JSON.stringify(steps.value))
        console.log('[AgentExecutionLog] Cached steps to localStorage:', {
          key,
          stepsCount: steps.value.length
        })
      } catch (error) {
        console.error('[AgentExecutionLog] Failed to cache steps:', error)
      }
    }
  }

  /**
   * 从 localStorage 恢复 executionSteps
   *
   * @returns 是否成功恢复
   */
  function restoreFromLocalStorage(): boolean {
    const key = getLocalStorageKey()

    // 🔍 DEBUG: 详细追踪 restore 过程
    const store = useAIConversationStore()
    console.log('[AgentExecutionLog] restoreFromLocalStorage - DIAGNOSTIC:', {
      computedKey: key,
      // ✅ 修复：正确访问 Pinia store 的 ref
      storeCurrentId: store.currentId as unknown as number | null,
      storeHasCurrentConversation: store.hasCurrentConversation,
      allLocalStorageKeys: Object.keys(localStorage).filter(k => k.startsWith('execution_steps')),
      localStorageContents: Object.fromEntries(
        Object.keys(localStorage)
          .filter(k => k.startsWith('execution_steps'))
          .map(k => [k, localStorage.getItem(k)?.slice(0, 100) + '...'])
      )
    })

    try {
      const cached = localStorage.getItem(key)
      console.log('[AgentExecutionLog] restoreFromLocalStorage - cache check:', {
        key,
        hasCachedData: !!cached,
        cachedDataLength: cached?.length || 0,
        cachedDataPreview: cached?.slice(0, 200) || 'NO DATA'
      })

      if (cached) {
        const parsedSteps = JSON.parse(cached) as ExecutionStep[]

        // 🔍 DEBUG: 检查解析后的数据格式
        console.log('[AgentExecutionLog] restoreFromLocalStorage - parsed data:', {
          stepsCount: parsedSteps.length,
          firstStep: parsedSteps[0] ? {
            id: parsedSteps[0].id,
            type: parsedSteps[0].type,
            title: parsedSteps[0].title,
            timestampType: typeof parsedSteps[0].timestamp,
            timestampValue: parsedSteps[0].timestamp
          } : 'NO STEPS',
          lastStep: (() => {
            const last = parsedSteps[parsedSteps.length - 1]
            return last ? {
              id: last.id,
              type: last.type,
              title: last.title
            } : 'NO STEPS'
          })()
        })

        // ✅ 转换 timestamp 从 string 到 Date（JSON.parse 后 timestamp 是 string）
        // 同时确保 description 字段有值
        const convertedSteps: ExecutionStep[] = parsedSteps.map(step => ({
          ...step,
          type: step.type as ExecutionStepType,
          description: step.description || step.title || '',  // ← 确保 description 有值
          timestamp: typeof step.timestamp === 'string' ? new Date(step.timestamp) : step.timestamp
        }))

        steps.value = convertedSteps

        // 🔍 DEBUG: 验证 steps.value 已更新
        console.log('[AgentExecutionLog] restoreFromLocalStorage - AFTER SET:', {
          stepsValueLength: steps.value.length,
          stepsValueFirstStep: steps.value[0]?.title || 'EMPTY'
        })

        return true
      } else {
        console.warn('[AgentExecutionLog] restoreFromLocalStorage - NO CACHE FOUND for key:', key)
      }
    } catch (error) {
      console.error('[AgentExecutionLog] Failed to parse cached steps:', error)
    }
    return false
  }

  /**
   * 清理 localStorage 缓存
   */
  function clearLocalStorageCache(): void {
    const key = getLocalStorageKey()
    localStorage.removeItem(key)
    console.log('[AgentExecutionLog] Cleared localStorage cache:', key)
  }

  /**
   * 将 executionSteps 保存到当前 AI 消息
   * SSE 流结束时触发
   *
   * ✅ 修复：只设置 executionSteps，不立即保存
   * 等待 finishAIMessage 后统一保存完整数据（包括 content）
   */
  function saveExecutionStepsToCurrentMessage(): void {
    const store = useAIConversationStore()

    if (!store.hasCurrentConversation) {
      console.warn('[AgentExecutionLog] No current conversation')
      return
    }

    // 设置当前 AI 消息的执行步骤
    // ✅ 转换为 store 兼容的格式（timestamp 转换为 ISO string）
    const stepsForStore = steps.value.map(step => ({
      ...step,
      timestamp: step.timestamp instanceof Date ? step.timestamp.toISOString() : String(step.timestamp)
    }))
    store.setAIMessageExecutionSteps(stepsForStore as unknown as ExecutionStep[])

    // 清理 localStorage 缓存（已设置到 Store）
    clearLocalStorageCache()

    console.log('[AgentExecutionLog] Set execution steps (will save in finishAIMessage):', {
      stepsCount: steps.value.length
    })
  }

  /**
   * ✅ 新增：直接设置执行步骤（用于页面刷新恢复）
   *
   * 避免不必要的 localStorage 中间步骤
   * 直接将 execution steps 设置到 composable 的内部状态
   *
   * @param executionSteps - 从 Store 获取的执行步骤数组（timestamp 可能是 string）
   */
  function setStepsDirectly(executionSteps: Array<{
    id: string
    type: string
    title: string
    description?: string
    timestamp: string | Date  // ← 接受 string 或 Date
    round?: number
    tool?: string
    params?: Record<string, unknown>
    result?: unknown
    success?: boolean
    error?: string
    businessParams?: string
    data?: unknown
    sessionId?: string
    inline_text?: string
    thinking?: string
    summary?: string
    summary_params?: Record<string, string>
    detail_params?: Record<string, { value: string; isEntity?: boolean }>
    confirmationType?: 'disambiguation' | 'confirmation' | 'info_gap'
    riskLevel?: 'low' | 'medium' | 'high'
    options?: Array<{
      id: number
      name: string
      entity_info_inline?: string
      entity_info_detail?: Record<string, string>
    }>
  }>): void {
    console.log('[AgentExecutionLog] setStepsDirectly - INPUT:', {
      stepsCount: executionSteps.length,
      firstStep: executionSteps[0]?.title || 'NO FIRST STEP',
      lastStep: (() => {
        const last = executionSteps[executionSteps.length - 1]
        return last?.title || 'NO LAST STEP'
      })()
    })

    // ✅ 转换 timestamp 从 string 到 Date（如果需要）
    // 同时确保 description 字段有值（ExecutionStep interface 要求 description 是必需的）
    const convertedSteps: ExecutionStep[] = executionSteps.map(step => ({
      ...step,
      type: step.type as ExecutionStepType,  // ← 转换类型
      description: step.description || step.title || '',  // ← 确保 description 有值
      timestamp: typeof step.timestamp === 'string' ? new Date(step.timestamp) : step.timestamp  // ← 转换时间戳
    }))

    // ✅ 直接设置步骤（不需要 localStorage 中间步骤）
    steps.value = convertedSteps

    // ✅ 标记为已完成（因为是从历史恢复的）
    if (convertedSteps.length > 0) {
      const lastStep = convertedSteps[convertedSteps.length - 1]
      if (lastStep?.type === ExecutionStepType.REACT_COMPLETE || lastStep?.type === ExecutionStepType.ERROR) {
        isCompleted.value = true
        isExecuting.value = false
      }
    }

    console.log('[AgentExecutionLog] setStepsDirectly - AFTER SET:', {
      stepsValueLength: steps.value.length,
      isCompleted: isCompleted.value,
      isExecuting: isExecuting.value
    })
  }

  // ========== localStorage 自动缓存（watch） ==========

  /**
   * 自动缓存 executionSteps 到 localStorage
   * 每次 steps 变化时触发
   */
  watch(steps, (newSteps) => {
    if (newSteps.length > 0) {
      cacheToLocalStorage()
    }
  }, { deep: true })

  return {
    // 状态（只读）
    steps: readonly(steps),
    currentRound: readonly(currentRound),
    maxRounds: readonly(maxRounds),
    isExecuting: readonly(isExecuting),
    isCompleted: readonly(isCompleted),
    hasError: readonly(hasError),
    sessionId: readonly(sessionId),
    shouldAutoExpand: readonly(shouldAutoExpand),  // ← 新增

    // Task 15: 自动收起逻辑（新增）
    expanded: readonly(expanded),
    isExecutionComplete: readonly(isExecutionComplete),
    autoCollapseCountdown: readonly(autoCollapseCountdown),

    // SSE 事件处理
    handleSSEEvent,

    // 辅助方法
    clear,
    getStepsByRound,
    getLastStep,
    resetAutoExpand,  // ← 新增

    // Task 15: 自动收起逻辑（新增）
    handleToggleExpand,
    cancelAutoCollapse,

    // 持久化方法（Task 12 新增）
    saveExecutionStepsToCurrentMessage,
    restoreFromLocalStorage,
    clearLocalStorageCache,

    // ✅ 新增：直接设置步骤（用于页面刷新恢复）
    setStepsDirectly
  }
}

/**
 * 导出类型定义供外部使用
 */
export type AgentExecutionLogHook = ReturnType<typeof useAgentExecutionLog>