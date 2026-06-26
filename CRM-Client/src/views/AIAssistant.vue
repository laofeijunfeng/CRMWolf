/**
 * AI 助手独立页面
 *
 * 布局：Header + 侧边栏（历史对话） + 对话区 + 输入区
 * 设计模式：对齐 ChatGPT 网页版 - 实时保存、单一状态源、刷新恢复
 */
<template>
  <div class="ai-assistant-page">
    <!-- Header -->
    <header class="ai-assistant-page__header">
      <div class="ai-assistant-page__header-left">
        <button
          class="ai-assistant-page__toggle-btn"
          :class="{ active: !sidebarCollapsed }"
          @click="toggleSidebar"
        >
          <el-icon class="ai-assistant-page__toggle-icon"><Operation /></el-icon>
        </button>
        <h1 class="ai-assistant-page__title">
          AI 助手
        </h1>
      </div>
      <button
        class="ai-assistant-page__new-btn"
        :disabled="loading || store.saving"
        @click="handleNewConversation"
      >
        新对话
      </button>
    </header>

    <!-- Main -->
    <main class="ai-assistant-page__main">
      <!-- Sidebar - 历史对话列表 -->
      <aside
        class="ai-assistant-page__sidebar"
        :class="{ collapsed: sidebarCollapsed }"
      >
        <HistoryList
          :groups="historyGroups"
          :active-id="currentId"
          :loading="loading"
          @select="handleSelectConversation"
          @delete="handleDeleteConversation"
        />
      </aside>

      <!-- Conversation Area -->
      <section class="ai-assistant-page__conversation">
        <!-- 对话内容（有消息时显示） -->
        <div
          v-if="hasMessages"
          ref="messagesContainer"
          class="ai-assistant-page__messages"
        >
          <!-- 对话气泡 -->
          <ChatBubble
            v-for="(msg, index) in messages"
            :key="index"
            :id="`message-${msg.id}`"
            :role="msg.role"
            :content="msg.content"
            :timestamp="msg.timestamp"
            :is-streaming="isStreamingAIMessage && index === messages.length - 1 && msg.role === 'assistant'"
          >
            <!-- 预览卡片插槽（仅 AI 消息且有预览数据时） -->
            <template
              v-if="msg.role === 'assistant' && index === messages.length - 1 && currentPreviewData"
              #preview-card
            >
              <PreviewCard
                :action-type="currentPreviewData.actionType"
                :params="currentPreviewData.params"
                :loading="sending"
                @confirm="handleConfirmPreview"
                @cancel="handleCancelPreview"
              />
            </template>
          </ChatBubble>

          <!-- Agent 执行过程（执行中和执行完成后都可见，支持展开查看详细过程） -->
          <AgentExecutionLog
            v-if="executionSteps.length > 0"
            :steps="executionSteps"
            :expanded="executionLogExpanded"
            :is-execution-complete="isExecutionComplete"
            :auto-collapse-countdown="autoCollapseCountdown"
            :step-to-message-map="stepToMessageMap"
            @toggle-expand="handleToggleExpand"
            @cancel-auto-collapse="cancelAutoCollapse"
            @navigate-to-message="handleNavigateToMessage"
          />

          <!-- 加载指示器（仅在无执行步骤时显示） -->
          <div
            v-if="sending && executionSteps.length === 0"
            class="ai-assistant-page__loading"
          >
            <span class="ai-assistant-page__loading-text">AI 正在思考...</span>
          </div>
        </div>

        <!-- 欢迎界面（无消息时显示） -->
        <WelcomeScreen
          v-else
          @quick-action="handleQuickAction"
        />
      </section>
    </main>

    <!-- Input Area -->
    <footer class="ai-assistant-page__input">
      <ChatInput
        :disabled="inputDisabled"
        @send="handleSendMessage"
      />
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useAIConversationStore } from '@/stores/aiConversation'
import { useUserStore } from '@/stores/user'
import { aiAssistantApi, type AIAssistantSSEEvent } from '@/api/aiAssistant'
import { useAgentExecutionLog } from '@/composables/useAgentExecutionLog'
import { logger } from '@/utils/logger'
import AgentExecutionLog from '@/components/AgentExecutionLog.vue'
import { Operation } from '@element-plus/icons-vue'
import HistoryList from '@/components/ai-assistant/HistoryList.vue'
import WelcomeScreen from '@/components/ai-assistant/WelcomeScreen.vue'
import ChatInput from '@/components/ai-assistant/ChatInput.vue'
import ChatBubble from '@/components/ai-assistant/ChatBubble.vue'
import PreviewCard from '@/components/ai-assistant/PreviewCard.vue'

// ========== Store ==========

const store = useAIConversationStore()
const userStore = useUserStore()

// ✅ 使用统一状态源（Store 的 messages computed）
const { historyGroups, currentId, loading, messages } = storeToRefs(store)

// ========== Agent Execution Log Composable ==========

const agentLog = useAgentExecutionLog()
const {
  steps: executionSteps,
  expanded: executionLogExpanded,
  isExecutionComplete,
  autoCollapseCountdown,
  handleToggleExpand,
  cancelAutoCollapse
} = agentLog

// ========== Task 17: 步骤 ID 与消息 ID 映射 ==========

const stepToMessageMap = computed(() => {
  const map: Record<string, number> = {}

  // 遍历所有消息，建立映射关系
  for (const message of messages.value) {
    if (message.role === 'assistant' && message.executionSteps) {
      for (const step of message.executionSteps) {
        // 每个 step 关联到对应的 message
        map[step.id] = message.id
      }
    }
  }

  return map
})

// ========== State ==========

/** 侧边栏折叠状态 */
const sidebarCollapsed = ref(false)

/** 消息容器 ref */
const messagesContainer = ref<HTMLDivElement | null>(null)

/** 是否正在发送 */
const sending = ref(false)

/** 当前预览卡片数据 */
const currentPreviewData = ref<{
  actionType: string
  params: Record<string, unknown>
} | null>(null)

/** SSE session ID */
const sessionId = ref<string | null>(null)

/** 当前正在构建的 AI 消息索引（用于流式追加） */
const currentAIMessageIndex = ref<number | null>(null)

/** 是否正在流式输出 AI 消息 */
const isStreamingAIMessage = ref(false)

// ========== Computed ==========

/** 输入框禁用状态 */
const inputDisabled = computed(() => {
  return loading.value || sending.value || store.saving
})

/** 是否有消息 */
const hasMessages = computed(() => {
  return messages.value.length > 0
})

// ========== Lifecycle ==========

onMounted(async () => {
  // 加载历史对话列表
  await store.fetchHistory()

  // ✅ ChatGPT 模式：刷新页面时，恢复最近的对话
  // 如果历史列表中有对话，自动加载最近的对话
  if (store.hasHistory && !currentId.value) {
    const recentConversation = store.allHistory[0]
    if (recentConversation) {
      await store.loadConversation(recentConversation.id)

      // ← Task 6: 使用 logger 追踪恢复流程
      const executionSteps = store.getLastAIMessageExecutionSteps()

      logger.info('[AIAssistant]', 'restore_start', {
        recentConversationId: recentConversation.id,
        storeCurrentId: currentId.value,
        executionStepsCount: executionSteps.length
      })

      if (executionSteps.length > 0) {
        // ✅ 修复：直接设置步骤，避免不必要的 localStorage 中间步骤
        agentLog.setStepsDirectly(executionSteps)

        logger.info('[AIAssistant]', 'restore_success', {
          stepsCount: executionSteps.length,
          lastStep: executionSteps[executionSteps.length - 1]?.title
        })
      } else {
        logger.warn('[AIAssistant]', 'restore_empty', {
          reason: 'No execution steps to restore'
        })
      }
    }
  }
})

// 监听消息变化，自动滚动到底部
watch(messages, () => {
  nextTick(() => {
    scrollToBottom()
  })
}, { deep: true })

// ========== Methods ==========

/** 切换侧边栏 */
function toggleSidebar(): void {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

/** 新建对话 */
async function handleNewConversation(): Promise<void> {
  // ✅ ChatGPT 模式：立即创建空会话，获取 ID
  await store.createEmptyConversation()

  // 清空所有状态
  currentPreviewData.value = null
  sessionId.value = null
  isStreamingAIMessage.value = false

  // ✅ 清空执行步骤（composable 会自动重置 expanded 状态）
  agentLog.clear()

  // ✅ Copywriting: 具体化的成功提示（不是 generic）
  ElMessage.success('已创建新对话，可以开始输入')
}

/** 选择对话 */
async function handleSelectConversation(id: number): Promise<void> {
  // ✅ ChatGPT 模式：立即加载历史对话内容
  await store.loadConversation(id)

  // 清空临时状态
  currentPreviewData.value = null
  sessionId.value = null
  isStreamingAIMessage.value = false

  // ✅ 恢复最后一条 AI 消息的 executionSteps（修复刷新后消失的问题）
  const executionSteps = store.getLastAIMessageExecutionSteps()
  if (executionSteps.length > 0) {
    // ✅ 修复：直接设置步骤，避免 localStorage round-trip
    agentLog.setStepsDirectly(executionSteps)

    logger.info('[AIAssistant]', 'restore_from_conversation', {
      conversationId: id,
      stepsCount: executionSteps.length,
      lastStep: executionSteps[executionSteps.length - 1]?.title
    })
  } else {
    // 无执行步骤时，清空 agentLog 状态
    agentLog.clear()
  }

  logger.info('[AIAssistant]', 'selected_conversation', { conversationId: id })
}

/** 删除对话 */
async function handleDeleteConversation(id: number): Promise<void> {
  try {
    // ✅ Copywriting: 具体后果 + 理性选择（不是 generic）
    await ElMessageBox.confirm(
      '删除后对话内容将无法恢复，确定删除？',
      '删除对话',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    await store.deleteConversation(id)
    ElMessage.success('删除成功')
  } catch (error) {
    // 用户取消删除或删除失败
    if (error !== 'cancel') {
      console.error('[AIAssistant] Delete error:', error)
      ElMessage.error('删除失败，请稍后重试')
    }
  }
}

/** 快捷操作 */
async function handleQuickAction(action: string): Promise<void> {
  // 将快捷操作转换为消息发送
  const actionMessages: Record<string, string> = {
    'create-customer': '创建一个新客户',
    'create-follow-up': '创建一条跟进记录',
    'win-opportunity': '将商机赢单',
    'query-contract': '查询合同信息'
  }
  const message = actionMessages[action] || action

  // ✅ 确保有当前对话（如果没有，先创建空会话）
  if (!store.hasCurrentConversation) {
    await store.createEmptyConversation()
  }

  handleSendMessage(message)
}

/** 发送消息 */
async function handleSendMessage(message: string): Promise<void> {
  // ✅ ChatGPT 模式：确保有当前对话
  if (!store.hasCurrentConversation) {
    // 如果没有当前对话，先创建空会话
    await store.createEmptyConversation()
  }

  // ✅ 立即添加用户消息并保存（防止刷新丢失）
  await store.addUserMessage(message)

  // 开始发送
  sending.value = true
  currentPreviewData.value = null
  isStreamingAIMessage.value = false

  // ✅ 清空旧的执行步骤（每次发送新消息重新开始）
  agentLog.clear()

  // ✅ 开始新的 AI 消息（用于流式输出）
  store.startAIMessage()
  isStreamingAIMessage.value = true
  currentAIMessageIndex.value = messages.value.length - 1

  // 获取 token
  const token = userStore.token

  try {
    // 调用 SSE API
    await aiAssistantApi.chatSSE(
      { content: message },
      handleSSEEvent,
      token
    )

    // SSE 流结束，完成 AI 消息
    await store.finishAIMessage()
  } catch (error) {
    console.error('[AIAssistant] SSE error:', error)

    // ✅ Copywriting: 具体化 + 方向性（不是 generic + apologetic）
    // 如果出错，完成 AI 消息（即使内容不完整）
    if (isStreamingAIMessage.value) {
      // ← Signature: 具体的错误提示 + 明确的解决方向
      const errorMessage = getSpecificErrorMessage(error)
      await store.appendAIMessageContent(errorMessage)
      await store.finishAIMessage()
    }
  } finally {
    sending.value = false
    currentAIMessageIndex.value = null
    isStreamingAIMessage.value = false
  }

  // ✅ 自动生成对话标题（从第一条用户消息提取）
  if (messages.value.length === 1) {
    // 第一条消息（用户消息），自动生成标题
    const title = message.slice(0, 50)
    await store.updateConversationTitle(title)
  }
}

/** 处理 SSE 事件 */
function handleSSEEvent(event: AIAssistantSSEEvent): void {
  console.log('[AIAssistant] SSE event:', event.event, event)

  // 提取 session_id
  if (event.session_id && !sessionId.value) {
    sessionId.value = event.session_id
  }

  // ✅ 使用 Agent Execution Log composable 处理 Agent 执行事件
  // 这些事件类型：react_start, round_start, tool_call, tool_result, round_completed, react_complete
  if (['react_start', 'round_start', 'tool_call', 'tool_result', 'round_completed',
       'react_complete', 'waiting_for_user', 'disambiguation_required',
       'awaiting_confirmation', 'max_rounds_reached', 'error'].includes(event.event ?? '')) {
    agentLog.handleSSEEvent(event)
  }

  switch (event.event) {
    case 'status':
      // 状态事件 - 不追加内容（已通过 startAIMessage 创建空消息）
      break

    case 'content':
      // ✅ 内容事件 - 流式追加并实时保存
      // 🔍 DEBUG: 追踪 content 事件
      logger.info('[AIAssistant]', 'sse_content_event', {
        hasContent: !!event.content,
        contentLength: event.content?.length || 0,
        contentPreview: event.content?.slice(0, 50) || 'NO CONTENT',
        isStreaming: isStreamingAIMessage.value
      })

      if (event.content && isStreamingAIMessage.value) {
        store.appendAIMessageContent(event.content)
      } else {
        // 🔍 DEBUG: 记录跳过的原因
        logger.warn('[AIAssistant]', 'sse_content_skipped', {
          reason: !event.content ? 'NO EVENT.CONTENT' : 'NOT STREAMING'
        })
      }
      break

    case 'parsed':
    case 'awaiting_confirmation':
      // 解析完成 - 显示预览卡片
      if (event.tool && event.params) {
        currentPreviewData.value = {
          actionType: event.tool,
          params: event.params
        }
      }
      break

    case 'result':
      // 执行结果 - 清空预览卡片，追加最终答案
      currentPreviewData.value = null
      if (event.content && isStreamingAIMessage.value) {
        store.appendAIMessageContent(event.content)
      }
      break

    case 'complete':
      // Agent 完成 - 检查是否有 answer 字段
      if (event.answer && isStreamingAIMessage.value) {
        store.appendAIMessageContent(event.answer)
      }
      break

    case 'react_complete':
      // ✅ 新增：Agent 执行完成，如果没有 content，生成默认回复
      // 🔍 DEBUG: 追踪 react_complete 时的 content 状态
      const lastAIMessage = messages.value.filter(m => m.role === 'assistant').pop()
      logger.info('[AIAssistant]', 'react_complete_event', {
        hasLastAIMessage: !!lastAIMessage,
        contentLength: lastAIMessage?.content?.length || 0,
        contentPreview: lastAIMessage?.content?.slice(0, 50) || 'NO CONTENT',
        isStreaming: isStreamingAIMessage.value,
        willGenerateDefault: lastAIMessage?.content === '' && isStreamingAIMessage.value
      })

      // 如果 AI 消息内容为空，根据执行步骤生成默认回复
      if (lastAIMessage && lastAIMessage.content === '' && isStreamingAIMessage.value) {
        // 生成默认回复：执行已完成
        const defaultReply = '操作已成功执行完成。'
        store.appendAIMessageContent(defaultReply)
        console.log('[AIAssistant] Generated default reply for empty content')
      }
      break

    case 'error':
      const errorMsg = event.message || '发生错误'
      if (isStreamingAIMessage.value) {
        store.appendAIMessageContent(errorMsg)
      }
      break

    default:
      if (event.message && isStreamingAIMessage.value) {
        store.appendAIMessageContent(event.message)
      }
  }
}

/** 确认预览卡片操作 */
async function handleConfirmPreview(
  actionType: string,
  params: Record<string, unknown>
): Promise<void> {
  console.log('[AIAssistant] Confirm action:', actionType, params)

  sending.value = true

  try {
    // 获取 token
    const token = userStore.token

    // 调用继续 ReAct API
    if (sessionId.value) {
      await aiAssistantApi.continueReactSSE(
        {
          round: 1,
          original_content: messages.value[0]?.content || '',
          executed_results: []
        },
        handleSSEEvent,
        token
      )

      // SSE 流结束，完成 AI 消息
      await store.finishAIMessage()
    }
  } catch (error) {
    console.error('[AIAssistant] Confirm error:', error)

    // ✅ Copywriting: 具体化的错误提示（不是 generic）
    if (isStreamingAIMessage.value) {
      const errorMessage = getConfirmErrorMessage(error)
      await store.appendAIMessageContent(errorMessage)
      await store.finishAIMessage()
    }
  } finally {
    sending.value = false
    currentPreviewData.value = null
  }
}

/**
 * ✅ Signature: 确认操作的错误提示（具体化 + 方向性）
 */
function getConfirmErrorMessage(error: unknown): string {
  const err = error as Error

  if (err.message.includes('permission') || err.message.includes('权限')) {
    return '无权限执行此操作，请检查权限设置或联系管理员。'
  }

  if (err.message.includes('validation') || err.message.includes('校验')) {
    return '操作参数校验失败，请检查输入内容后重新执行。'
  }

  if (err.message.includes('database') || err.message.includes('数据库')) {
    return '数据保存失败，请稍后重试或联系技术支持。'
  }

  // 默认：具体化但不是 generic
  return '操作执行失败，请重新尝试或描述问题继续对话。'
}

/** 取消预览卡片 */
async function handleCancelPreview(): Promise<void> {
  console.log('[AIAssistant] Cancel preview')
  currentPreviewData.value = null

  // ✅ Copywriting: 明确后果（不是 generic）
  if (isStreamingAIMessage.value) {
    await store.appendAIMessageContent('操作已取消，可以继续对话。')
    await store.finishAIMessage()
  }
}

/** 滚动到底部 */
function scrollToBottom(): void {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

/** Task 17: 跳转到消息并高亮 */
function handleNavigateToMessage(messageId: number): void {
  const messageElement = document.getElementById(`message-${messageId}`)

  if (messageElement) {
    // 滚动到对应消息位置
    messageElement.scrollIntoView({
      behavior: 'smooth',
      block: 'center'
    })

    // 高亮消息（2秒）
    messageElement.classList.add('highlighted')
    setTimeout(() => {
      messageElement.classList.remove('highlighted')
    }, 2000)

    console.log('[Navigation] Scrolled to message:', messageId)
  }
}

// ==================== Copywriting: 具体化 + 方向性 ====================

/**
 * ✅ Signature: 具体化的错误提示（不是 generic + apologetic）
 * 根据错误类型提供明确的解决方向
 */
function getSpecificErrorMessage(error: unknown): string {
  const err = error as Error

  // 网络连接错误
  if (err.message.includes('fetch') || err.message.includes('network')) {
    return '网络连接中断，请检查网络后重新发送消息。'
  }

  // 服务器响应超时
  if (err.message.includes('timeout') || err.message.includes('Timeout')) {
    return 'AI 服务响应超时，请等待片刻后继续对话。'
  }

  // 对话保存失败（本地暂存）
  if (err.message.includes('save') || err.message.includes('保存')) {
    return '对话保存失败，内容已暂存在本地，刷新页面后将自动恢复。'
  }

  // HTTP 错误（具体的状态码提示）
  if (err.message.includes('HTTP error')) {
    const statusMatch = err.message.match(/HTTP error: (\d+)/)
    if (statusMatch) {
      const status = parseInt(statusMatch[1])
      if (status === 401) {
        return '登录已过期，请重新登录后继续对话。'
      }
      if (status === 403) {
        return '无权限访问 AI 服务，请联系管理员。'
      }
      if (status === 500) {
        return 'AI 服务暂时不可用，请稍后再试。'
      }
    }
  }

  // 默认：具体化但不是 generic
  return '对话遇到技术问题，请尝试重新发送消息。'
}
</script>

<style scoped lang="scss">
@import '@/styles/variables.scss';

.ai-assistant-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background-color: $wolf-bg-page;

  // ========== Header ==========

  .ai-assistant-page__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 56px;
    padding: 0 $wolf-page-padding;
    background-color: $wolf-bg-card;
    border-bottom: 1px solid $wolf-border-divider;
  }

  .ai-assistant-page__header-left {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm;
  }

  .ai-assistant-page__toggle-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    color: $wolf-text-tertiary;
    background-color: transparent;
    border: none;
    border-radius: $wolf-radius-sm;
    cursor: pointer;
    transition: all 0.2s ease;

    &:hover {
      background-color: $wolf-bg-hover;
      color: $wolf-text-secondary;
    }

    &.active {
      color: $wolf-primary;
    }

    // 小屏隐藏（侧边栏默认隐藏）
    @media (min-width: 768px) {
      display: none;
    }
  }

  .ai-assistant-page__toggle-icon {
    font-size: 18px;
  }

  .ai-assistant-page__title {
    // ← Signature: IBM Plex Sans（页面主标题的唯一性格化字体）
    font-family: $wolf-font-display;
    font-size: $wolf-font-size-title;
    font-weight: $wolf-font-weight-semibold;
    color: $wolf-text-primary;
    margin: 0;
  }

  .ai-assistant-page__new-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    height: $wolf-button-height-md;
    padding: $wolf-button-padding-md;
    font-size: $wolf-font-size-body;
    font-weight: $wolf-font-weight-normal;
    color: $wolf-btn-text;
    background-color: $wolf-btn-bg;
    border: 1px solid $wolf-border-default;
    border-radius: $wolf-button-radius-sm;
    cursor: pointer;
    transition: all 0.2s ease;

    &:hover:not(:disabled) {
      background-color: $wolf-btn-bg-hover;
      color: $wolf-btn-text-hover;
      border-color: $wolf-border-hover;
    }

    &:active:not(:disabled) {
      background-color: $wolf-btn-bg-active;
    }

    &:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
  }

  // ========== Main ==========

  .ai-assistant-page__main {
    display: flex;
    flex: 1;
    overflow: hidden;
  }

  // ========== Sidebar ==========

  .ai-assistant-page__sidebar {
    width: 280px;
    background-color: $wolf-bg-sidebar;
    border-right: 1px solid $wolf-border-divider;
    transition: width 0.2s ease;

    &.collapsed {
      width: 0;
      overflow: hidden;
    }
  }

  // ========== Conversation Area ==========

  .ai-assistant-page__conversation {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background-color: $wolf-bg-page;
  }

  .ai-assistant-page__messages {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: $wolf-space-md;
    padding: $wolf-space-lg;
    max-width: 800px;
    margin: 0 auto;
    width: 100%;
    overflow-y: auto;
  }

  .ai-assistant-page__loading {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: $wolf-space-md;
  }

  .ai-assistant-page__loading-text {
    font-size: $wolf-font-size-auxiliary;
    color: $wolf-text-tertiary;
    animation: pulse 1.5s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% {
      opacity: 1;
    }
    50% {
      opacity: 0.5;
    }
  }

  .ai-assistant-page__messages-placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    font-size: $wolf-font-size-auxiliary;
    color: $wolf-text-tertiary;
  }

  // ========== Input Area ==========

  // ← Signature: AI 对话区底部的流动线条（智能边界）
  .ai-assistant-page__input {
    display: flex;
    justify-content: center;
    padding: $wolf-space-md $wolf-page-padding;
    background-color: $wolf-bg-card;
    position: relative;

    // ← Signature: 流动感渐变线条（暗示 AI 智能边界）
    &::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 1px;
      background: linear-gradient(
        90deg,
        transparent 0%,
        rgba($wolf-primary, 0.15) 20%,
        rgba($wolf-primary, 0.25) 50%,
        rgba($wolf-primary, 0.15) 80%,
        transparent 100%
      );
    }
  }

  // ========== Responsive ==========

  // 大屏（≥1200px）
  @media (min-width: 1200px) {
    .ai-assistant-page__sidebar {
      width: 280px;
    }
  }

  // 中屏（768px-1199px）
  @media (max-width: 1199px) {
    .ai-assistant-page__sidebar {
      width: 240px;
    }

    .ai-assistant-page__messages {
      max-width: 100%;
      padding: $wolf-space-md;
    }
  }

  // 小屏（<768px）
  @media (max-width: 767px) {
    .ai-assistant-page__sidebar {
      width: 0;

      &.collapsed {
        width: 100%;
        position: fixed;
        top: 56px;
        left: 0;
        right: 0;
        bottom: 0;
        z-index: 100;
        background-color: $wolf-bg-sidebar;
      }
    }

    .ai-assistant-page__header {
      padding: 0 $wolf-space-md;
    }

    .ai-assistant-page__header-left {
      gap: $wolf-space-xs;
    }

    .ai-assistant-page__toggle-btn {
      display: inline-flex;
    }

    .ai-assistant-page__title {
      font-size: $wolf-font-size-body;
    }

    .ai-assistant-page__new-btn {
      padding: $wolf-button-padding-sm;
    }

    .ai-assistant-page__messages {
      padding: $wolf-space-sm;
    }

    .ai-assistant-page__input {
      padding: $wolf-space-sm $wolf-space-md;
    }
  }

  // ========== Task 17: 高亮消息样式 ==========

  .ai-assistant-page__messages [id^="message-"].highlighted {
    background: rgba($wolf-primary, 0.1);
    border-left: 3px solid $wolf-primary;
    transition: background 0.3s ease, border-left 0.3s ease;
    padding-left: $wolf-space-sm;
    margin-left: -$wolf-space-sm;
    border-radius: $wolf-radius-sm;
  }

  .ai-assistant-page__messages [id^="message-"]:not(.highlighted) {
    background: transparent;
    border-left: none;
    transition: background 0.3s ease, border-left 0.3s ease;
  }
}
</style>