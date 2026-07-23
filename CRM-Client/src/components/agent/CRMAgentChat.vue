<template>
  <section class="agent-chat" aria-label="CRM AI Agent 聊天">
    <div class="agent-chat__header">
      <div class="agent-chat__title">
        <Bot class="agent-chat__title-icon" aria-hidden="true" />
        <div>
          <h2>CRM AI Agent</h2>
          <p>围绕客户跟进记录，协助录入、确认和执行 CRM 操作</p>
        </div>
      </div>
      <Badge variant="outline" class="agent-chat__badge">
        {{ sessionLabel }}
      </Badge>
    </div>

    <MessageScroller class="agent-chat__messages" :items-count="messages.length + eventLogs.length">
      <div v-if="messages.length === 0" class="agent-chat__empty">
        <Sparkles class="agent-chat__empty-icon" aria-hidden="true" />
        <div class="agent-chat__empty-title">输入一段客户跟进内容开始</div>
        <div class="agent-chat__examples">
          <button type="button" @click="useExample('今天和越秀金融的王总沟通了下项目进展，客户反馈还在立项评估阶段，暂时持续跟进，下周三再确认进展。')">
            跟进记录
          </button>
          <button type="button" @click="useExample('帮我给越秀金融创建联系人王总，手机号 13800138000，职位总经理。')">
            创建联系人
          </button>
          <button type="button" @click="useExample('光大证券今天回款了')">
            回款线索
          </button>
        </div>
      </div>

      <template v-for="message in messages" :key="message.id">
        <Message :role="message.role" class="agent-chat__message">
          <Avatar v-if="message.role !== 'user'" class="agent-chat__avatar">
            <AvatarFallback>AI</AvatarFallback>
          </Avatar>
          <Bubble :variant="message.role === 'user' ? 'sent' : 'received'" class="agent-chat__bubble">
            <div class="agent-chat__bubble-content">{{ message.content }}</div>
          </Bubble>
          <Avatar v-if="message.role === 'user'" class="agent-chat__avatar">
            <AvatarFallback>{{ userInitial }}</AvatarFallback>
          </Avatar>
        </Message>
      </template>

      <div v-if="eventLogs.length > 0" class="agent-chat__events" aria-live="polite">
        <div v-for="eventLog in visibleEventLogs" :key="eventLog.id" class="agent-chat__event">
          <span class="agent-chat__event-dot"></span>
          <span>{{ eventLog.text }}</span>
        </div>
      </div>
    </MessageScroller>

    <form class="agent-chat__composer" @submit.prevent="sendMessage">
      <Textarea
        v-model="input"
        class="agent-chat__textarea"
        rows="3"
        :disabled="isStreaming"
        placeholder="输入客户跟进、联系人创建、回款等信息..."
        aria-label="输入 Agent 消息"
        @keydown.enter.exact.prevent="sendMessage"
      />
      <Button
        type="submit"
        size="icon"
        class="agent-chat__send"
        :disabled="!canSend"
        aria-label="发送消息"
      >
        <Loader2 v-if="isStreaming" class="h-5 w-5 animate-spin" aria-hidden="true" />
        <SendHorizontal v-else class="h-5 w-5" aria-hidden="true" />
      </Button>
    </form>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { toast } from "vue-sonner"
import { Bot, Loader2, SendHorizontal, Sparkles } from "lucide-vue-next"
import { useUserStore } from "@/stores/user"
import { agentApi, type AgentChatSSEEvent, type AgentMessageResponse } from "@/api/agent"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Bubble } from "@/components/ui/bubble"
import { Button } from "@/components/ui/button"
import { Message } from "@/components/ui/message"
import { MessageScroller } from "@/components/ui/message-scroller"
import { Textarea } from "@/components/ui/textarea"

interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
}

interface EventLog {
  id: string
  text: string
}

const userStore = useUserStore()
const input = ref("")
const isStreaming = ref(false)
const sessionId = ref<number | undefined>(undefined)
const sessionKey = ref<string | undefined>(undefined)
const messages = ref<ChatMessage[]>([])
const eventLogs = ref<EventLog[]>([])
const isLoadingHistory = ref(false)

const LAST_SESSION_STORAGE_KEY = "crm_agent_last_session_id"

const canSend = computed(() => input.value.trim().length > 0 && !isStreaming.value)
const userInitial = computed(() => {
  const name = userStore.userInfo?.name
  return name !== undefined && name.length > 0 ? name.charAt(0) : "我"
})
const sessionLabel = computed(() => sessionId.value !== undefined ? `会话 #${sessionId.value}` : "新会话")
const visibleEventLogs = computed(() => eventLogs.value.slice(-6))

const nextId = (prefix: string): string => `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`

const normalizeRole = (role: AgentChatSSEEvent["role"]): ChatMessage["role"] | null => {
  const normalized = String(role ?? "").toLowerCase()
  if (normalized === "user" || normalized === "assistant") return normalized
  return null
}

const addAssistantMessage = (content: string, id?: string | number): void => {
  if (content.length === 0) return
  const lastMessage = messages.value[messages.value.length - 1]
  if (lastMessage?.role === "assistant" && lastMessage.content === content) return
  messages.value.push({ id: String(id ?? nextId("assistant")), role: "assistant", content })
}

const toChatMessage = (message: AgentMessageResponse): ChatMessage | null => {
  const role = normalizeRole(message.role)
  const content = message.content ?? ""
  if (role === null || content.length === 0) return null
  return {
    id: String(message.id),
    role,
    content,
  }
}

const loadSessionMessages = async (targetSessionId: number): Promise<boolean> => {
  const response = await agentApi.listMessages(targetSessionId)
  const loadedMessages = response.items
    .map(toChatMessage)
    .filter((message): message is ChatMessage => message !== null)

  messages.value = loadedMessages
  eventLogs.value = []
  sessionId.value = targetSessionId
  localStorage.setItem(LAST_SESSION_STORAGE_KEY, String(targetSessionId))
  return true
}

const loadInitialSession = async (): Promise<void> => {
  if (!userStore.token || isLoadingHistory.value) return

  isLoadingHistory.value = true
  try {
    const storedSessionId = Number(localStorage.getItem(LAST_SESSION_STORAGE_KEY))
    if (Number.isInteger(storedSessionId) && storedSessionId > 0) {
      try {
        await loadSessionMessages(storedSessionId)
        return
      } catch {
        localStorage.removeItem(LAST_SESSION_STORAGE_KEY)
      }
    }

    const sessions = await agentApi.listSessions()
    const latestSession = sessions.items[0]
    if (latestSession === undefined) return

    sessionKey.value = latestSession.session_key
    await loadSessionMessages(latestSession.id)
  } catch (error) {
    const message = error instanceof Error ? error.message : "加载 Agent 历史消息失败"
    addEventLog(message)
  } finally {
    isLoadingHistory.value = false
  }
}

const addEventLog = (text: string): void => {
  eventLogs.value.push({ id: nextId("evt"), text })
}

const stringifyValue = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "-"
  if (typeof value === "string") return value
  if (typeof value === "number" || typeof value === "boolean") return String(value)
  return JSON.stringify(value)
}

const formatCustomerNames = (customers?: Record<string, unknown>[]): string => {
  if (!customers || customers.length === 0) return "未找到候选客户"
  return customers
    .slice(0, 5)
    .map((customer, index) => `${index + 1}. ${stringifyValue(customer["account_name"])}`)
    .join("；")
}

const eventToLogText = (event: AgentChatSSEEvent): string | null => {
  switch (event.event) {
    case "semantic_parsed":
      return `AI 语义解析：${stringifyValue(event.parse_source)}，模型：${stringifyValue(event.model)}`
    case "intent":
      return `识别意图：${stringifyValue(event.intent)}`
    case "entity_parse":
      return "已解析客户、跟进内容和下一步动作"
    case "tool_result":
      return `${event.success === true ? "Tool 调用成功" : "Tool 调用失败"}：${stringifyValue(event.tool_name)}`
    case "customer_candidates":
      return `找到候选客户：${formatCustomerNames(event.customers)}`
    case "customer_selection_required":
      return `需要选择客户：${formatCustomerNames(event.customers)}`
    case "customer_selected":
      return `已选择客户：${stringifyValue(event.customer?.["account_name"])}`
    case "customer_selection_failed":
      return event.content !== undefined && event.content.length > 0 ? event.content : "客户选择未匹配"
    case "confirmation_required":
      return `等待确认：${stringifyValue(event.action)}`
    case "contact_fields_required":
      return event.content !== undefined && event.content.length > 0 ? event.content : "需要补充联系人信息"
    case "contact_fields_completed":
      return event.content !== undefined && event.content.length > 0 ? event.content : "联系人信息已补齐"
    case "invoice_title_fields_required":
      return event.content !== undefined && event.content.length > 0 ? event.content : "需要补充发票抬头信息"
    case "invoice_title_fields_completed":
      return event.content !== undefined && event.content.length > 0 ? event.content : "发票抬头信息已补齐"
    case "deployment_info_fields_required":
      return event.content !== undefined && event.content.length > 0 ? event.content : "需要补充部署信息"
    case "deployment_info_fields_completed":
      return event.content !== undefined && event.content.length > 0 ? event.content : "部署信息已补齐"
    case "task_completed":
      return event.content !== undefined && event.content.length > 0 ? event.content : "任务已完成"
    case "task_failed":
      return event.content !== undefined && event.content.length > 0 ? event.content : "任务执行失败"
    case "error":
      return event.message ?? event.error_message ?? "Agent 服务异常"
    default:
      return null
  }
}

const handleSSEEvent = (event: AgentChatSSEEvent): void => {
  if (event.event === "session") {
    sessionId.value = event.session_id
    sessionKey.value = event.session_key
    if (event.session_id !== undefined) {
      localStorage.setItem(LAST_SESSION_STORAGE_KEY, String(event.session_id))
    }
    return
  }

  if (event.event === "message") {
    const role = normalizeRole(event.role)
    if (role === "assistant" && event.content !== undefined) {
      addAssistantMessage(event.content, event.message_id)
    }
    return
  }

  if (event.event === "final") {
    if (event.content !== undefined) addAssistantMessage(event.content)
    return
  }

  if (event.event === "done") {
    return
  }

  const text = eventToLogText(event)
  if (text !== null && text.length > 0) addEventLog(text)
}

const sendMessage = async (): Promise<void> => {
  const content = input.value.trim()
  if (content.length === 0 || isStreaming.value) return

  const token = userStore.token
  if (!token) {
    toast.error("请先登录")
    return
  }

  messages.value.push({ id: nextId("user"), role: "user", content })
  input.value = ""
  eventLogs.value = []
  isStreaming.value = true

  try {
    const request = {
      content,
      ...(sessionId.value !== undefined ? { session_id: sessionId.value } : {}),
      ...(sessionKey.value !== undefined ? { session_key: sessionKey.value } : {}),
    }

    await agentApi.chatStream(
      request,
      handleSSEEvent,
      token
    )
  } catch (error) {
    const message = error instanceof Error ? error.message : "Agent 请求失败"
    addEventLog(message)
    toast.error(message)
  } finally {
    isStreaming.value = false
  }
}

const useExample = (example: string): void => {
  input.value = example
}

onMounted(() => {
  void loadInitialSession()
})
</script>

<style scoped lang="scss">
.agent-chat {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  height: calc(100dvh - 64px);
  min-height: 560px;
  background: #f7f9fd;
}

.agent-chat__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 24px;
  border-bottom: 1px solid #e4ecfc;
  background: #fff;
}

.agent-chat__title {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 12px;

  h2 {
    margin: 0;
    font-size: 18px;
    font-weight: 650;
    color: #172033;
  }

  p {
    margin: 2px 0 0;
    font-size: 13px;
    color: #64748b;
  }
}

.agent-chat__title-icon {
  width: 32px;
  height: 32px;
  padding: 7px;
  border-radius: 8px;
  color: #2563eb;
  background: #eff6ff;
}

.agent-chat__badge {
  flex-shrink: 0;
}

.agent-chat__messages {
  min-height: 0;
}

.agent-chat__message {
  align-items: flex-start;
}

.agent-chat__avatar {
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
}

.agent-chat__bubble {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.agent-chat__bubble-content {
  min-width: 0;
}

.agent-chat__events {
  display: grid;
  gap: 6px;
  max-width: 760px;
  margin: 0 auto;
  color: #64748b;
  font-size: 12px;
}

.agent-chat__event {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 24px;
}

.agent-chat__event-dot {
  width: 6px;
  height: 6px;
  flex: 0 0 6px;
  border-radius: 999px;
  background: #2563eb;
}

.agent-chat__empty {
  display: grid;
  place-items: center;
  align-content: center;
  gap: 14px;
  min-height: 100%;
  color: #64748b;
  text-align: center;
}

.agent-chat__empty-icon {
  width: 36px;
  height: 36px;
  color: #2563eb;
}

.agent-chat__empty-title {
  font-size: 16px;
  font-weight: 600;
  color: #172033;
}

.agent-chat__examples {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;

  button {
    min-height: 34px;
    padding: 0 12px;
    border: 1px solid #dbe5f6;
    border-radius: 8px;
    background: #fff;
    color: #334155;
    font-size: 13px;
    cursor: pointer;
  }

  button:hover {
    border-color: #2563eb;
    color: #2563eb;
  }
}

.agent-chat__composer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 44px;
  align-items: end;
  gap: 10px;
  padding: 14px 24px 18px;
  border-top: 1px solid #e4ecfc;
  background: #fff;
}

.agent-chat__textarea {
  min-height: 76px;
  max-height: 160px;
  resize: vertical;
}

.agent-chat__send {
  width: 44px;
  height: 44px;
  border-radius: 8px;
}

@media (max-width: 767px) {
  .agent-chat {
    height: calc(100dvh - 56px);
    min-height: 0;
  }

  .agent-chat__header {
    align-items: flex-start;
    padding: 12px 16px;
  }

  .agent-chat__title {
    align-items: flex-start;

    p {
      display: none;
    }
  }

  .agent-chat__composer {
    padding: 10px 12px 12px;
  }
}
</style>
