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

    <MessageScroller class="agent-chat__messages" :items-count="messageScrollCount">
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
            <div class="agent-chat__bubble-content">
              <div v-if="message.role === 'assistant' && message.steps.length > 0" class="agent-chat__stream">
                <button
                  type="button"
                  class="agent-chat__stream-summary"
                  :aria-expanded="message.stepsExpanded === true"
                  @click="message.stepsExpanded = !message.stepsExpanded"
                >
                  <span class="agent-chat__step-count">{{ message.steps.length }}</span>
                  <component
                    :is="message.stepsExpanded === true ? ChevronDown : ChevronRight"
                    class="agent-chat__stream-chevron"
                    aria-hidden="true"
                  />
                  <component
                    :is="stepIcon(latestStep(message)?.kind)"
                    class="agent-chat__stream-icon"
                    :class="stepIconClass(latestStep(message)?.kind, message.isStreaming)"
                    aria-hidden="true"
                  />
                  <span class="agent-chat__stream-latest">{{ latestStep(message)?.text }}</span>
                </button>
                <div v-if="message.stepsExpanded === true" class="agent-chat__stream-list">
                  <div v-for="step in message.steps" :key="step.id" class="agent-chat__stream-step">
                    <component
                      :is="stepIcon(step.kind)"
                      class="agent-chat__stream-icon"
                      :class="stepIconClass(step.kind)"
                      aria-hidden="true"
                    />
                    <span>{{ step.text }}</span>
                  </div>
                </div>
              </div>
              <div>{{ message.content }}</div>
            </div>
          </Bubble>
          <Avatar v-if="message.role === 'user'" class="agent-chat__avatar">
            <AvatarFallback>{{ userInitial }}</AvatarFallback>
          </Avatar>
        </Message>
      </template>
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
import { computed, onMounted, ref, type Component } from "vue"
import { toast } from "vue-sonner"
import {
  AlertTriangle,
  Bot,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  Database,
  HelpCircle,
  Loader2,
  Search,
  SendHorizontal,
  Sparkles,
  UserCheck,
  Wrench,
} from "lucide-vue-next"
import { useUserStore } from "@/stores/user"
import { agentApi, type AgentChatSSEEvent, type AgentEventType, type AgentMessageResponse } from "@/api/agent"
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
  steps: EventLog[]
  isStreaming?: boolean
  stepsExpanded?: boolean
}

interface EventLog {
  id: string
  text: string
  kind: AgentEventType
}

const userStore = useUserStore()
const input = ref("")
const isStreaming = ref(false)
const sessionId = ref<number | undefined>(undefined)
const sessionKey = ref<string | undefined>(undefined)
const messages = ref<ChatMessage[]>([])
const isLoadingHistory = ref(false)
const activeAssistantId = ref<string | null>(null)

const LAST_SESSION_STORAGE_KEY = "crm_agent_last_session_id"

const canSend = computed(() => input.value.trim().length > 0 && !isStreaming.value)
const userInitial = computed(() => {
  const name = userStore.userInfo?.name
  return name !== undefined && name.length > 0 ? name.charAt(0) : "我"
})
const sessionLabel = computed(() => sessionId.value !== undefined ? `会话 #${sessionId.value}` : "新会话")
const messageScrollCount = computed(() => (
  messages.value.length
  + messages.value.reduce((total, message) => total + message.steps.length, 0)
))

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
  messages.value.push({ id: String(id ?? nextId("assistant")), role: "assistant", content, steps: [] })
}

const activeAssistantMessage = (): ChatMessage | null => {
  const activeId = activeAssistantId.value
  if (activeId === null) return null
  return messages.value.find(message => message.id === activeId) ?? null
}

const startAssistantDraft = (): void => {
  const id = nextId("assistant_stream")
  messages.value.push({
    id,
    role: "assistant",
    content: "正在理解你的 CRM 操作意图...",
    steps: [],
    isStreaming: true,
  })
  activeAssistantId.value = id
}

const updateAssistantDraft = (content: string, id?: string | number, keepActive = false): void => {
  if (content.length === 0) return
  const draft = activeAssistantMessage()
  if (draft) {
    draft.content = content
    draft.isStreaming = false
    if (id !== undefined) draft.id = String(id)
    if (!keepActive) activeAssistantId.value = null
    return
  }
  addAssistantMessage(content, id)
}

const payloadTraceEvents = (payload?: Record<string, unknown> | null): AgentChatSSEEvent[] => {
  const traceEvents = payload?.["trace_events"]
  if (!Array.isArray(traceEvents)) return []
  return traceEvents
    .filter((event): event is AgentChatSSEEvent => {
      return typeof event === "object"
        && event !== null
        && "event" in event
        && typeof (event as { event?: unknown }).event === "string"
    })
}

const traceEventToStep = (event: AgentChatSSEEvent): EventLog | null => {
  const text = eventToLogText(event)
  if (text === null || text.length === 0) return null
  return {
    id: nextId("evt"),
    text,
    kind: event.event,
  }
}

const toChatMessage = (message: AgentMessageResponse): ChatMessage | null => {
  const role = normalizeRole(message.role)
  const content = message.content ?? ""
  if (role === null || content.length === 0) return null
  return {
    id: String(message.id),
    role,
    content,
    steps: role === "assistant"
      ? payloadTraceEvents(message.payload_json).map(traceEventToStep).filter((step): step is EventLog => step !== null)
      : [],
  }
}

const latestStep = (message: ChatMessage): EventLog | undefined => message.steps[message.steps.length - 1]

const loadSessionMessages = async (targetSessionId: number): Promise<boolean> => {
  const response = await agentApi.listMessages(targetSessionId)
  const loadedMessages = response.items
    .map(toChatMessage)
    .filter((message): message is ChatMessage => message !== null)

  messages.value = loadedMessages
  activeAssistantId.value = null
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
    addEventLog(message, "error")
  } finally {
    isLoadingHistory.value = false
  }
}

const addEventLog = (text: string, kind: AgentEventType): void => {
  const draft = activeAssistantMessage()
  if (draft) {
    draft.steps.push({ id: nextId("evt"), text, kind })
    return
  }
  const lastAssistant = [...messages.value].reverse().find(message => message.role === "assistant")
  if (lastAssistant) {
    lastAssistant.steps.push({ id: nextId("evt"), text, kind })
  }
}

const stepIcon = (kind?: AgentEventType): Component => {
  switch (kind) {
    case "agent_step":
    case "semantic_parsed":
    case "intent":
    case "entity_parse":
    case "business_suggestions":
      return Brain
    case "tool_result":
      return Wrench
    case "customer_candidates":
    case "customer_selected":
    case "customer_selection_required":
      return Search
    case "business_context_loaded":
      return Database
    case "confirmation_required":
    case "opportunity_fields_required":
    case "contact_fields_required":
    case "invoice_title_fields_required":
    case "deployment_info_fields_required":
    case "payment_fields_required":
    case "business_selection_required":
      return HelpCircle
    case "opportunity_fields_completed":
    case "contact_fields_completed":
    case "invoice_title_fields_completed":
    case "deployment_info_fields_completed":
    case "payment_fields_completed":
    case "business_selected":
      return UserCheck
    case "task_completed":
      return CheckCircle2
    case "task_failed":
    case "error":
    case "suggestion_failed":
    case "customer_selection_failed":
    case "business_selection_failed":
      return AlertTriangle
    default:
      return ClipboardCheck
  }
}

const stepIconClass = (kind?: AgentEventType, active = false): string => {
  const statusClass = active ? "agent-chat__stream-icon--active" : ""
  const normalizedKind = kind ?? ""
  if (kind === "tool_result" || kind === "task_completed") return `agent-chat__stream-icon--success ${statusClass}`
  if (kind === "error" || kind === "task_failed" || kind === "suggestion_failed" || normalizedKind.endsWith("_failed")) {
    return `agent-chat__stream-icon--danger ${statusClass}`
  }
  if (normalizedKind.includes("required") || kind === "confirmation_required") return `agent-chat__stream-icon--warning ${statusClass}`
  return `agent-chat__stream-icon--info ${statusClass}`
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

const formatAITrace = (prefix: string, source: unknown, model: unknown, fallbackReason?: unknown, fallbackError?: unknown): string => {
  const hasFallbackReason = fallbackReason !== null && fallbackReason !== undefined && fallbackReason !== ""
  const hasFallbackError = fallbackError !== null && fallbackError !== undefined && fallbackError !== ""
  const fallbackText = hasFallbackReason
    ? `，fallback：${stringifyValue(fallbackReason)}${hasFallbackError ? `/${stringifyValue(fallbackError)}` : ""}`
    : ""
  return `${prefix}：${stringifyValue(source)}，模型：${stringifyValue(model)}${fallbackText}`
}

const eventToLogText = (event: AgentChatSSEEvent): string | null => {
  switch (event.event) {
    case "agent_step":
      return `${event.status === "completed" ? "完成" : "开始"}：${stringifyValue(event.content ?? event.step)}`
    case "semantic_parsed":
      return formatAITrace("AI 语义解析", event.parse_source, event.model, event.fallback_reason, event.fallback_error)
    case "intent":
      return `识别意图：${stringifyValue(event.intent)}`
    case "entity_parse":
      return "已解析客户、跟进内容和下一步动作"
    case "tool_result":
      return `${event.success === true ? "Tool 调用成功" : "Tool 调用失败"}：${stringifyValue(event.tool_name)}`
    case "customer_candidates":
      return `找到候选客户：${formatCustomerNames(event.customers)}`
    case "business_context_loaded":
      return `已加载客户上下文：${stringifyValue(event.customer?.["account_name"])}`
    case "business_suggestions":
      return `${formatAITrace("AI 业务建议", event.suggestion_source, event.model, event.fallback_reason, event.fallback_error)}，建议：${formatSuggestionTitles(event.suggestions)}`
    case "suggestion_failed":
      return `AI 业务建议生成失败：${stringifyValue(event.message)}`
    case "customer_selection_required":
      return `需要选择客户：${formatCustomerNames(event.customers)}`
    case "customer_selected":
      return `已选择客户：${stringifyValue(event.customer?.["account_name"])}`
    case "customer_selection_failed":
      return event.content !== undefined && event.content.length > 0 ? event.content : "客户选择未匹配"
    case "confirmation_required":
      return `等待确认：${stringifyValue(event.action)}`
    case "opportunity_fields_required":
      return event.content !== undefined && event.content.length > 0 ? event.content : "需要补充商机信息"
    case "opportunity_fields_completed":
      return event.content !== undefined && event.content.length > 0 ? event.content : "商机信息已补齐"
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
    case "payment_fields_required":
      return event.content !== undefined && event.content.length > 0 ? event.content : "需要补充回款信息"
    case "payment_fields_completed":
      return event.content !== undefined && event.content.length > 0 ? event.content : "回款信息已补齐"
    case "business_selection_required":
      return event.content !== undefined && event.content.length > 0 ? event.content : "需要选择业务对象"
    case "business_selected":
      return event.content !== undefined && event.content.length > 0 ? event.content : "业务对象已选择"
    case "business_selection_failed":
      return event.content !== undefined && event.content.length > 0 ? event.content : "业务对象选择未匹配"
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

const formatSuggestionTitles = (suggestions?: Record<string, unknown>[]): string => {
  if (!suggestions || suggestions.length === 0) return "暂无建议"
  return suggestions
    .slice(0, 3)
    .map((suggestion, index) => `${index + 1}. ${stringifyValue(suggestion["title"])}`)
    .join("；")
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
      updateAssistantDraft(event.content, event.message_id)
    }
    return
  }

  if (event.event === "final") {
    if (event.content !== undefined) updateAssistantDraft(event.content, undefined, true)
    return
  }

  if (event.event === "done") {
    const draft = activeAssistantMessage()
    if (draft) draft.isStreaming = false
    activeAssistantId.value = null
    return
  }

  const text = eventToLogText(event)
  if (text !== null && text.length > 0) addEventLog(text, event.event)
}

const sendMessage = async (): Promise<void> => {
  const content = input.value.trim()
  if (content.length === 0 || isStreaming.value) return

  const token = userStore.token
  if (!token) {
    toast.error("请先登录")
    return
  }

  messages.value.push({ id: nextId("user"), role: "user", content, steps: [] })
  startAssistantDraft()
  input.value = ""
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
    addEventLog(message, "error")
    const draft = activeAssistantMessage()
    if (draft) {
      draft.content = "Agent 请求失败，请稍后重试。"
      draft.isStreaming = false
    }
    toast.error(message)
  } finally {
    const draft = activeAssistantMessage()
    if (draft) draft.isStreaming = false
    activeAssistantId.value = null
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

.agent-chat__stream {
  display: grid;
  gap: 6px;
  margin-bottom: 10px;
  padding: 8px;
  border: 1px solid #e4ecfc;
  border-radius: 8px;
  background: #f8fbff;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.agent-chat__stream-summary {
  display: grid;
  grid-template-columns: 28px 14px 16px minmax(0, 1fr);
  align-items: center;
  gap: 7px;
  width: 100%;
  min-height: 24px;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.agent-chat__step-count {
  display: inline-grid;
  place-items: center;
  width: 28px;
  height: 22px;
  border: 1px solid #cbdaf1;
  border-radius: 6px;
  background: #fff;
  color: #334155;
  font-size: 12px;
  font-weight: 650;
}

.agent-chat__stream-chevron {
  width: 14px;
  height: 14px;
  color: #94a3b8;
}

.agent-chat__stream-icon {
  width: 15px;
  height: 15px;
  margin-top: 1px;
  flex: 0 0 15px;
}

.agent-chat__stream-icon--active {
  animation: agent-chat-pulse 1.2s ease-in-out infinite;
}

.agent-chat__stream-icon--info {
  color: #2563eb;
}

.agent-chat__stream-icon--success {
  color: #16a34a;
}

.agent-chat__stream-icon--warning {
  color: #d97706;
}

.agent-chat__stream-icon--danger {
  color: #dc2626;
}

.agent-chat__stream-latest {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-chat__stream-list {
  display: grid;
  gap: 6px;
  padding-top: 6px;
  border-top: 1px solid #e4ecfc;
}

.agent-chat__stream-step {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr);
  align-items: flex-start;
  gap: 8px;
}

@keyframes agent-chat-pulse {
  0%,
  100% {
    opacity: 0.4;
  }

  50% {
    opacity: 1;
  }
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
