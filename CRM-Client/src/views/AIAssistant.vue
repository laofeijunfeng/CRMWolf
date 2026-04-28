<template>
  <div class="ai-assistant">
    <div class="chat-header">
      <h1 class="header-title">AI 助手</h1>
      <el-button
        v-if="messages.length > 0"
        type="text"
        size="small"
        @click="clearMessages"
      >
        清空对话
      </el-button>
    </div>

    <div class="chat-container" ref="chatContainer">
      <!-- 加载历史记录 -->
      <div v-if="isLoadingHistory" class="loading-history">
        <el-icon class="loading-icon"><Loading /></el-icon>
        <span>正在加载历史记录...</span>
      </div>

      <!-- 快捷建议（首次进入时显示） -->
      <div v-if="messages.length === 0 && !isLoadingHistory" class="quick-suggestions">
        <div class="suggestions-title">
          <el-icon><Cpu /></el-icon>
          <span>你可以这样问</span>
        </div>
        <div class="suggestions-list">
          <div
            v-for="suggestion in quickSuggestions"
            :key="suggestion"
            class="suggestion-item"
            @click="handleSuggestionClick(suggestion)"
          >
            {{ suggestion }}
          </div>
        </div>
      </div>

      <!-- 消息列表 -->
      <div v-for="(message, index) in messages" :key="index" class="message-item" :class="message.role">
        <div class="message-bubble">
          <!-- 用户消息 -->
          <template v-if="message.role === 'user'">
            <div class="message-content">{{ message.content }}</div>
          </template>

          <!-- AI 消息 -->
          <template v-else>
            <!-- 思考过程（可折叠） -->
            <div v-if="message.thinking" class="thinking-section">
              <div class="thinking-header" @click="toggleThinking(index)">
                <el-icon class="thinking-icon"><Loading /></el-icon>
                <span class="thinking-label">思考过程</span>
                <el-icon class="toggle-icon">
                  <ArrowDown v-if="!message.showThinking" />
                  <ArrowUp v-else />
                </el-icon>
              </div>
              <div v-if="message.showThinking" class="thinking-content">
                {{ message.thinking }}
              </div>
            </div>

            <!-- 执行状态 -->
            <div v-if="message.status" class="status-section">
              <el-icon class="status-icon"><Loading /></el-icon>
              <span class="status-text">{{ message.status }}</span>
            </div>

            <!-- 最终结果 -->
            <div v-if="message.result" class="result-section" :class="{ success: message.success, error: !message.success }">
              <div class="result-content">{{ message.result }}</div>
            </div>
          </template>
        </div>
      </div>

      <!-- 正在输入指示器 -->
      <div v-if="isStreaming" class="message-item assistant">
        <div class="message-bubble">
          <div class="typing-indicator">
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
          </div>
        </div>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="input-area">
      <el-input
        v-model="inputText"
        type="textarea"
        :rows="2"
        placeholder="输入你的问题，按 Ctrl+Enter 发送"
        :disabled="isStreaming"
        @keydown.ctrl.enter="handleSend"
      />
      <el-button
        type="primary"
        :disabled="!inputText.trim() || isStreaming"
        :loading="isStreaming"
        @click="handleSend"
      >
        发送
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { useUserStore } from '@/stores/user'
import { ElMessage } from 'element-plus'
import { Cpu, Loading, ArrowDown, ArrowUp } from '@element-plus/icons-vue'
import { aiAssistantApi, type ChatHistoryItem } from '@/api/aiAssistant'

interface Message {
  role: 'user' | 'assistant'
  content?: string
  thinking?: string
  showThinking?: boolean
  status?: string
  result?: string
  success?: boolean
  isHistory?: boolean  // 标记为历史消息
}

const userStore = useUserStore()
const messages = ref<Message[]>([])
const inputText = ref('')
const isStreaming = ref(false)
const isLoadingHistory = ref(true)
const chatContainer = ref<HTMLElement | null>(null)

const quickSuggestions = [
  '查询本周新增的线索',
  '查询我的客户列表',
  '为线索张三添加跟进记录',
  '查询本月回款情况'
]

const scrollToBottom = () => {
  nextTick(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  })
}

const toggleThinking = (index: number) => {
  messages.value[index].showThinking = !messages.value[index].showThinking
}

const handleSuggestionClick = (suggestion: string) => {
  inputText.value = suggestion
  handleSend()
}

const clearMessages = () => {
  messages.value = []
}

// 加载历史记录
const loadHistory = async () => {
  try {
    const token = userStore.token
    if (!token) return

    const response = await aiAssistantApi.getHistory(50)
    if (response.code === 0 && response.data) {
      // 将历史记录转换为消息格式
      for (const item of response.data) {
        // 用户消息
        messages.value.push({
          role: 'user',
          content: item.request_text,
          isHistory: true
        })
        // AI 消息
        if (item.execution_result) {
          messages.value.push({
            role: 'assistant',
            result: item.execution_result,
            success: item.status === 'SUCCESS',
            isHistory: true
          })
        }
      }
      scrollToBottom()
    }
  } catch (error) {
    console.error('加载历史记录失败', error)
  } finally {
    isLoadingHistory.value = false
  }
}

onMounted(() => {
  loadHistory()
})

const handleSend = async () => {
  const content = inputText.value.trim()
  if (!content || isStreaming.value) return

  // 添加用户消息
  messages.value.push({ role: 'user', content })
  inputText.value = ''
  scrollToBottom()

  // 获取 token
  const token = userStore.token
  if (!token) {
    ElMessage.error('请先登录')
    return
  }

  // 添加 AI 消息占位
  const aiMessage: Message = { role: 'assistant', showThinking: false }
  messages.value.push(aiMessage)
  isStreaming.value = true
  scrollToBottom()

  try {
    await aiAssistantApi.chatSSE(
      { content },
      (event) => {
        const lastIndex = messages.value.length - 1
        const msg = messages.value[lastIndex]

        switch (event.event) {
          case 'status':
            msg.status = event.message
            break
          case 'content':
            // 累积思考过程
            if (!msg.thinking) msg.thinking = ''
            msg.thinking += event.content || ''
            break
          case 'parsed':
            msg.status = undefined
            break
          case 'result':
            msg.result = event.message
            msg.success = event.success
            msg.status = undefined
            isStreaming.value = false
            break
          case 'error':
            msg.result = event.message
            msg.success = false
            msg.status = undefined
            isStreaming.value = false
            break
        }

        scrollToBottom()
      },
      token
    )
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : '请求失败'
    aiMessage.result = errorMessage
    aiMessage.success = false
    isStreaming.value = false
    ElMessage.error(errorMessage)
  }
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.ai-assistant {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: $wolf-bg-page;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: $wolf-space-md $wolf-space-lg;
  background: $wolf-bg-card;
  border-bottom: 1px solid $wolf-border-default;
}

.header-title {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin: 0;
}

.chat-container {
  flex: 1;
  overflow-y: auto;
  padding: $wolf-space-lg;
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md;
}

.loading-history {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: $wolf-space-sm;
  padding: $wolf-space-lg;
  color: $wolf-text-tertiary;
  font-size: $wolf-font-size-body;

  .loading-icon {
    animation: spin 1s linear infinite;
    color: $wolf-primary;
  }
}

.quick-suggestions {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md;
  padding: $wolf-space-lg;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  margin-bottom: $wolf-space-lg;
}

.suggestions-title {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  font-size: $wolf-font-size-body;
  color: $wolf-text-tertiary;

  .el-icon {
    color: $wolf-primary;
    font-size: 18px;
  }
}

.suggestions-list {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-sm;
}

.suggestion-item {
  padding: $wolf-space-sm $wolf-space-md;
  background: $wolf-bg-hover;
  border-radius: $wolf-radius-sm;
  font-size: $wolf-font-size-body;
  color: $wolf-text-secondary;
  cursor: pointer;
  transition: background 0.2s;

  &:hover {
    background: $wolf-bg-active;
    color: $wolf-text-primary;
  }
}

.message-item {
  display: flex;
  max-width: 80%;

  &.user {
    align-self: flex-end;

    .message-bubble {
      background: $wolf-primary;
      color: $wolf-text-inverse;
    }
  }

  &.assistant {
    align-self: flex-start;

    .message-bubble {
      background: $wolf-bg-card;
      border: 1px solid $wolf-border-default;
    }
  }
}

.message-bubble {
  padding: $wolf-space-md;
  border-radius: $wolf-radius-md;
  min-width: 100px;
}

.message-content {
  font-size: $wolf-font-size-body;
  line-height: $wolf-line-height-body;
}

.thinking-section {
  margin-bottom: $wolf-space-sm;
}

.thinking-header {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
  cursor: pointer;
  padding: $wolf-space-xs 0;
  color: $wolf-text-tertiary;
  font-size: $wolf-font-size-caption;

  &:hover {
    color: $wolf-text-secondary;
  }
}

.thinking-icon {
  animation: spin 1s linear infinite;
  color: $wolf-primary;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.thinking-label {
  font-weight: $wolf-font-weight-medium;
}

.toggle-icon {
  font-size: 12px;
}

.thinking-content {
  margin-top: $wolf-space-xs;
  padding: $wolf-space-sm;
  background: $wolf-bg-hover;
  border-radius: $wolf-radius-sm;
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  line-height: $wolf-line-height-body;
  white-space: pre-wrap;
}

.status-section {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
  margin-bottom: $wolf-space-sm;
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

.status-icon {
  animation: spin 1s linear infinite;
  color: $wolf-primary;
}

.result-section {
  font-size: $wolf-font-size-body;
  line-height: $wolf-line-height-body;
  padding: $wolf-space-sm;
  border-radius: $wolf-radius-sm;

  &.success {
    background: $wolf-success-bg;
    color: $wolf-success-text;
  }

  &.error {
    background: $wolf-danger-bg;
    color: $wolf-danger-text;
  }
}

.result-content {
  white-space: pre-wrap;
}

.typing-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: $wolf-space-sm;
}

.typing-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: $wolf-text-placeholder;
  animation: typing 1.4s infinite ease-in-out;

  &:nth-child(1) { animation-delay: 0s; }
  &:nth-child(2) { animation-delay: 0.2s; }
  &:nth-child(3) { animation-delay: 0.4s; }
}

@keyframes typing {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-4px); }
}

.input-area {
  display: flex;
  gap: $wolf-space-md;
  padding: $wolf-space-md $wolf-space-lg;
  background: $wolf-bg-card;
  border-top: 1px solid $wolf-border-default;

  .el-textarea {
    flex: 1;
  }

  .el-button {
    align-self: flex-end;
  }
}
</style>