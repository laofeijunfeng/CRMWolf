/**
 * AI 对话历史 Store
 *
 * 管理用户的 AI 对话历史记录，支持服务器持久化
 * 设计模式：对齐 ChatGPT 网页版 - 实时保存、单一状态源
 */

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { aiConversationApi, type ConversationDetail, type ConversationGroup } from '@/api/aiConversation'

// ========== Types ==========

/** 执行步骤（与 API ExecutionStep 对齐） */
interface ExecutionStep {
  id: string
  type: string
  title: string
  description?: string
  timestamp: string
  round?: number
  tool?: string
  params?: Record<string, unknown>
  result?: Record<string, unknown>
  success?: boolean
  error?: string
  businessParams?: string
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  executionSteps?: ExecutionStep[]
}

export const useAIConversationStore = defineStore('aiConversation', () => {
  // ========== State ==========

  /** 历史对话列表（按日期分组） */
  const historyGroups = ref<ConversationGroup>({
    today: [],
    yesterday: [],
    earlier: []
  })

  /** 当前对话详情（单一状态源） */
  const currentConversation = ref<ConversationDetail | null>(null)

  /** 当前对话 ID */
  const currentId = ref<number | null>(null)

  /** 加载状态 */
  const loading = ref(false)

  /** 保存状态（防止重复保存） */
  const saving = ref(false)

  /** 分页信息 */
  const pagination = ref({
    page: 1,
    pageSize: 20,
    total: 0
  })

  // ========== Computed ==========

  /** 所有历史对话（扁平化） */
  const allHistory = computed(() => {
    return [
      ...historyGroups.value.today,
      ...historyGroups.value.yesterday,
      ...historyGroups.value.earlier
    ]
  })

  /** 是否有历史记录 */
  const hasHistory = computed(() => allHistory.value.length > 0)

  /** 当前对话消息列表（直接渲染） */
  const messages = computed(() => {
    return currentConversation.value?.messages || []
  })

  /** 是否有当前对话 */
  const hasCurrentConversation = computed(() => {
    return currentConversation.value !== null
  })

  // ========== Actions ==========

  /**
   * 获取历史对话列表
   */
  async function fetchHistory(page: number = 1): Promise<void> {
    loading.value = true
    try {
      const response = await aiConversationApi.getHistory({
        page,
        pageSize: pagination.value.pageSize
      })

      historyGroups.value = response.groups
      pagination.value.total = response.total
      pagination.value.page = page
    } catch (error) {
      console.error('[AIConversationStore] fetchHistory error:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  /**
   * 加载单个对话详情
   */
  async function loadConversation(id: number): Promise<void> {
    loading.value = true
    currentId.value = id
    try {
      const response = await aiConversationApi.getDetail(id)

      // ← Task 12: 恢复 execution_steps 到本地状态
      // 将蛇形字段 execution_steps 转换为驼峰 executionSteps
      currentConversation.value = {
        ...response,
        messages: response.messages.map(msg => ({
          ...msg,
          executionSteps: msg.execution_steps || []
        }))
      }

      console.log('[AIConversationStore] Loaded conversation with execution steps:', {
        id,
        messagesCount: currentConversation.value.messages.length,
        hasExecutionSteps: currentConversation.value.messages.some(m => m.executionSteps && m.executionSteps.length > 0)
      })
    } catch (error) {
      console.error('[AIConversationStore] loadConversation error:', error)
      currentConversation.value = null
      throw error
    } finally {
      loading.value = false
    }
  }

  /**
   * 创建空会话（新对话逻辑）
   * ChatGPT 模式：立即创建空会话，获取临时 ID
   */
  async function createEmptyConversation(): Promise<void> {
    loading.value = true
    try {
      // 创建临时对话（标题为"新对话"，无消息）
      const response = await aiConversationApi.create({
        title: '新对话',
        messages: []
      })

      // 立即设置为当前对话
      currentConversation.value = response
      currentId.value = response.id

      // 刷新历史列表（新对话会出现在"今天"分组）
      await fetchHistory()

      console.log('[AIConversationStore] Created empty conversation:', response.id)
    } catch (error) {
      console.error('[AIConversationStore] createEmptyConversation error:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  /**
   * 添加用户消息并立即保存
   * ChatGPT 模式：实时保存，防止数据丢失
   */
  async function addUserMessage(content: string): Promise<void> {
    if (!currentConversation.value) {
      console.error('[AIConversationStore] No current conversation')
      return
    }

    const message: Message = {
      role: 'user',
      content,
      timestamp: new Date().toISOString()
    }

    // 1. 立即添加到当前对话
    currentConversation.value.messages.push(message)

    // 2. 立即保存到数据库（乐观更新）
    await saveCurrentConversation()

    console.log('[AIConversationStore] Added user message and saved')
  }

  /**
   * 开始新的 AI 消息（用于流式输出）
   */
  function startAIMessage(): void {
    if (!currentConversation.value) {
      console.error('[AIConversationStore] No current conversation')
      return
    }

    const message: Message = {
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString()
    }

    currentConversation.value.messages.push(message)
    console.log('[AIConversationStore] Started AI message')
  }

  /**
   * 流式追加 AI 消息内容
   * ChatGPT 模式：实时追加，实时保存
   */
  async function appendAIMessageContent(content: string): Promise<void> {
    if (!currentConversation.value) {
      console.error('[AIConversationStore] No current conversation')
      return
    }

    // 找到最后一条 AI 消息
    const lastAIMessage = currentConversation.value.messages
      .filter(m => m.role === 'assistant')
      .pop()

    if (lastAIMessage) {
      lastAIMessage.content += content

      // 实时保存（防止刷新丢失）
      // 注意：这里可以优化为批量保存（例如每 500ms 保存一次）
      // 当前为简化实现，每次追加都保存
      await saveCurrentConversation()
    }
  }

  /**
   * 完成 AI 消息（流式输出结束）
   */
  async function finishAIMessage(): Promise<void> {
    // 最后一次保存（确保完整内容已保存）
    await saveCurrentConversation()
    console.log('[AIConversationStore] Finished AI message')
  }

  /**
   * 设置当前 AI 消息的执行步骤
   * 用于 SSE 流结束时保存 execution steps
   */
  function setAIMessageExecutionSteps(steps: ExecutionStep[]): void {
    if (!currentConversation.value) {
      console.error('[AIConversationStore] No current conversation')
      return
    }

    // 找到最后一条 AI 消息
    const lastAIMessage = currentConversation.value.messages
      .filter(m => m.role === 'assistant')
      .pop()

    if (lastAIMessage) {
      lastAIMessage.executionSteps = steps
      console.log('[AIConversationStore] Set execution steps for AI message:', {
        stepsCount: steps.length
      })
    }
  }

  /**
   * 获取最后一条 AI 消息的执行步骤
   * 用于页面刷新恢复 execution steps
   *
   * @returns 执行步骤数组（可能为空）
   */
  function getLastAIMessageExecutionSteps(): ExecutionStep[] {
    if (!currentConversation.value) {
      return []
    }

    const lastAIMessage = currentConversation.value.messages
      .filter(m => m.role === 'assistant')
      .pop()

    return lastAIMessage?.executionSteps || []
  }

  /**
   * 更新对话标题
   * ChatGPT 模式：AI 自动生成标题，或用户手动修改
   */
  async function updateConversationTitle(title: string): Promise<void> {
    if (!currentConversation.value) {
      console.error('[AIConversationStore] No current conversation')
      return
    }

    currentConversation.value.title = title
    await saveCurrentConversation()

    // 刷新历史列表（更新标题显示）
    await fetchHistory()
  }

  /**
   * 保存当前对话到数据库
   * ChatGPT 模式：实时保存核心方法
   */
  async function saveCurrentConversation(): Promise<void> {
    if (!currentConversation.value) {
      return
    }

    // 防止重复保存
    if (saving.value) {
      console.log('[AIConversationStore] Already saving, skip')
      return
    }

    saving.value = true

    try {
      // 提取对话数据
      const conversationData = {
        title: currentConversation.value.title,
        messages: currentConversation.value.messages.map(m => ({
          role: m.role,
          content: m.content,
          timestamp: m.timestamp,
          execution_steps: m.executionSteps || undefined // ← 传递 execution_steps
        })),
        action_type: currentConversation.value.actionType,
        entity_type: currentConversation.value.entityType,
        entity_id: currentConversation.value.entityId
      }

      // 调用 API 保存（使用 currentId 判断是否更新）
      if (currentId.value) {
        // ✅ 已有 ID，更新现有对话（使用 update 方法）
        await aiConversationApi.update(currentId.value, conversationData)
        console.log('[AIConversationStore] Updated conversation:', currentId.value)
      } else {
        // 无 ID，创建新对话
        const response = await aiConversationApi.create(conversationData)
        currentConversation.value.id = response.id
        currentId.value = response.id
        console.log('[AIConversationStore] Created new conversation:', response.id)
      }

      // 刷新历史列表
      await fetchHistory()
    } catch (error) {
      console.error('[AIConversationStore] saveCurrentConversation error:', error)
      throw error
    } finally {
      saving.value = false
    }
  }

  /**
   * 删除对话记录
   */
  async function deleteConversation(id: number): Promise<void> {
    try {
      await aiConversationApi.delete(id)

      // 从本地列表中移除
      removeFromGroups(id)

      // 如果删除的是当前对话，清空当前对话
      if (currentId.value === id) {
        currentConversation.value = null
        currentId.value = null
      }
    } catch (error) {
      console.error('[AIConversationStore] deleteConversation error:', error)
      throw error
    }
  }

  /**
   * 从分组列表中移除对话
   */
  function removeFromGroups(id: number): void {
    const groups = historyGroups.value

    groups.today = groups.today.filter(c => c.id !== id)
    groups.yesterday = groups.yesterday.filter(c => c.id !== id)
    groups.earlier = groups.earlier.filter(c => c.id !== id)

    pagination.value.total -= 1
  }

  /**
   * 清空当前对话（回到初始状态）
   */
  function clearCurrent(): void {
    currentConversation.value = null
    currentId.value = null
  }

  /**
   * 重置 Store
   */
  function reset(): void {
    historyGroups.value = {
      today: [],
      yesterday: [],
      earlier: []
    }
    currentConversation.value = null
    currentId.value = null
    loading.value = false
    saving.value = false
    pagination.value = {
      page: 1,
      pageSize: 20,
      total: 0
    }
  }

  return {
    // State
    historyGroups,
    currentConversation,
    currentId,
    loading,
    saving,
    pagination,

    // Computed
    allHistory,
    hasHistory,
    messages,  // ✅ 新增：直接渲染的统一状态源
    hasCurrentConversation,

    // Actions
    fetchHistory,
    loadConversation,
    createEmptyConversation,  // ✅ 新增：创建空会话
    addUserMessage,  // ✅ 新增：添加用户消息并保存
    startAIMessage,  // ✅ 新增：开始 AI 消息
    appendAIMessageContent,  // ✅ 新增：流式追加内容
    finishAIMessage,  // ✅ 新增：完成 AI 消息
    setAIMessageExecutionSteps,  // ✅ 新增：设置 AI 消息执行步骤
    getLastAIMessageExecutionSteps,  // ✅ 新增：获取最后一条 AI 消息的执行步骤
    updateConversationTitle,  // ✅ 新增：更新标题
    saveCurrentConversation,  // ✅ 新增：实时保存
    deleteConversation,
    clearCurrent,
    reset
  }
})

export type AIConversationStore = ReturnType<typeof useAIConversationStore>