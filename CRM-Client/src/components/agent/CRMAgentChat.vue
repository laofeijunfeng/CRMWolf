<template>
  <section class="agent-chat" aria-label="AI Agent 聊天">
    <MessageScroller
      class="agent-chat__messages"
      :content-style="messageContentStyle"
      :items-count="messageScrollCount"
    >
      <div v-if="messages.length === 0" class="agent-chat__empty">
        <Sparkles class="agent-chat__empty-icon" aria-hidden="true" />
        <div class="agent-chat__empty-title">告诉我客户进展，我来帮你整理下一步</div>
        <div class="agent-chat__examples">
          <Button
            type="button"
            variant="outline"
            size="sm"
            @click="useExample('今天和越秀金融的王总沟通了下项目进展，客户反馈还在立项评估阶段，暂时持续跟进，下周三再确认进展。')"
          >
            跟进记录
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            @click="useExample('帮我给越秀金融创建联系人王总，手机号 13800138000，职位总经理。')"
          >
            创建联系人
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            @click="useExample('帮我给越秀金融添加售前张三，可跟进项目需求。')"
          >
            设置客户成员
          </Button>
        </div>
      </div>

      <template v-for="message in messages" :key="message.id">
        <Message :role="message.role" class="agent-chat__message">
          <Avatar v-if="message.role !== 'user'" class="agent-chat__avatar agent-chat__avatar--assistant">
            <AvatarFallback class="agent-chat__avatar-fallback">AI</AvatarFallback>
          </Avatar>
          <Bubble
            :variant="message.role === 'user' ? 'sent' : 'received'"
            :class="[
              'agent-chat__bubble',
              message.role === 'assistant' ? 'agent-chat__bubble--assistant' : 'agent-chat__bubble--user',
            ]"
          >
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
          <Avatar v-if="message.role === 'user'" class="agent-chat__avatar agent-chat__avatar--user">
            <AvatarFallback class="agent-chat__avatar-fallback">{{ userInitial }}</AvatarFallback>
          </Avatar>
        </Message>
      </template>
    </MessageScroller>

    <AgentInteractionDrawer
      v-if="activeInteraction !== null"
      :interaction="activeInteraction"
      :disabled="isStreaming"
      @submit="sendInteractionMessage"
      @cancel="cancelInteraction"
      @height-change="interactionDrawerHeight = $event"
    />

    <form v-if="activeInteraction === null" class="agent-chat__composer" @submit.prevent="sendMessage">
      <InputGroup class="agent-chat__input-group">
        <InputGroupTextarea
          v-model="input"
          class="agent-chat__textarea"
          rows="1"
          :disabled="isStreaming"
          placeholder="让我帮你记录客户跟进、补客户资料，顺手看看要不要推进商机..."
          aria-label="输入 Agent 消息"
          @keydown.enter.exact.prevent="sendMessage"
        />
        <InputGroupAddon align="block-end" class="agent-chat__input-actions">
          <InputGroupButton
            type="submit"
            size="icon-sm"
            variant="default"
            class="agent-chat__send"
            :disabled="!canSend"
            aria-label="发送消息"
          >
            <Loader2 v-if="isStreaming" class="h-4 w-4 animate-spin" aria-hidden="true" />
            <SendHorizontal v-else class="h-4 w-4" aria-hidden="true" />
          </InputGroupButton>
        </InputGroupAddon>
      </InputGroup>
    </form>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, type Component } from "vue"
import { toast } from "vue-sonner"
import {
  AlertTriangle,
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
import { agentApi, type AgentChatSSEEvent, type AgentEventType, type AgentInteraction, type AgentMessageResponse } from "@/api/agent"
import { loadLatestAgentMessages } from "@/components/agent/agentHistory"
import AgentInteractionDrawer from "@/components/agent/AgentInteractionDrawer.vue"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Bubble } from "@/components/ui/bubble"
import { Button } from "@/components/ui/button"
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupTextarea } from "@/components/ui/input-group"
import { Message } from "@/components/ui/message"
import { MessageScroller } from "@/components/ui/message-scroller"

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
  interaction?: AgentInteraction
}

const userStore = useUserStore()
const input = ref("")
const isStreaming = ref(false)
const sessionId = ref<number | undefined>(undefined)
const sessionKey = ref<string | undefined>(undefined)
const messages = ref<ChatMessage[]>([])
const isLoadingHistory = ref(false)
const activeAssistantId = ref<string | null>(null)
const activeInteraction = ref<AgentInteraction | null>(null)
const interactionDrawerHeight = ref(0)

const LAST_SESSION_STORAGE_KEY = "crm_agent_last_session_id"

const canSend = computed(() => input.value.trim().length > 0 && !isStreaming.value)
const userInitial = computed(() => {
  const name = userStore.userInfo?.name
  return name !== undefined && name.length > 0 ? name.charAt(0) : "我"
})
const messageScrollCount = computed(() => (
  messages.value.length
  + messages.value.reduce((total, message) => total + message.steps.length, 0)
))
const messageContentStyle = computed(() => ({
  paddingBottom: activeInteraction.value === null
    ? undefined
    : `max(calc(var(--agent-composer-height) + var(--agent-interaction-gap)), calc(${interactionDrawerHeight.value}px + var(--agent-interaction-gap)))`,
}))

const nextId = (prefix: string): string => `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`

const isWaitingInteraction = (interaction: AgentInteraction | undefined | null): interaction is AgentInteraction => {
  if (interaction === undefined || interaction === null) return false
  if (interaction.status === undefined) return true
  return interaction.status === "waiting_user_input" || interaction.status === "waiting_confirmation"
}

const isTerminalEvent = (event: AgentChatSSEEvent): boolean => {
  return event.event === "task_completed"
    || event.event === "task_cancelled"
    || event.event === "task_failed"
}

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
  const step: EventLog = {
    id: nextId("evt"),
    text,
    kind: event.event,
  }
  if (event.interaction !== undefined) step.interaction = event.interaction
  return step
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

const setActiveInteraction = (interaction: AgentInteraction | null): void => {
  activeInteraction.value = interaction
  if (interaction === null) interactionDrawerHeight.value = 0
}

const restoreInteractionFromMessages = (loadedMessages: ChatMessage[]): void => {
  let restoredInteraction: AgentInteraction | null = null

  for (const message of loadedMessages) {
    if (message.role !== "assistant") continue
    for (const step of message.steps) {
      if (step.interaction !== undefined) {
        restoredInteraction = isWaitingInteraction(step.interaction) ? step.interaction : null
      }
      if (isTerminalEvent({ event: step.kind })) {
        restoredInteraction = null
      }
    }
  }

  setActiveInteraction(restoredInteraction)
}

const loadSessionMessages = async (targetSessionId: number): Promise<boolean> => {
  const loadedMessages = (await loadLatestAgentMessages(agentApi.listMessages, targetSessionId))
    .map(toChatMessage)
    .filter((message): message is ChatMessage => message !== null)

  messages.value = loadedMessages
  activeAssistantId.value = null
  restoreInteractionFromMessages(loadedMessages)
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
    case "follow_up_quality_evaluated":
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
    case "customer_member_fields_required":
    case "payment_fields_required":
    case "business_selection_required":
      return HelpCircle
    case "opportunity_fields_completed":
    case "contact_fields_completed":
    case "invoice_title_fields_completed":
    case "deployment_info_fields_completed":
    case "customer_member_fields_completed":
    case "payment_fields_completed":
    case "business_selected":
      return UserCheck
    case "task_completed":
    case "task_cancelled":
      return CheckCircle2
    case "task_failed":
    case "error":
    case "suggestion_failed":
    case "follow_up_quality_failed":
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
    case "follow_up_quality_evaluated":
      return `${formatAITrace("AI 跟进质量评估", event.quality_source, event.model, event.fallback_reason, event.fallback_error)}，评分：${stringifyValue(event.score)}`
    case "follow_up_quality_required":
      return event.content !== undefined && event.content.length > 0 ? event.content : "需要补充跟进记录信息"
    case "intent":
      return `识别意图：${stringifyValue(event.intent)}`
    case "entity_parse":
      return "已解析客户、业务内容和下一步动作"
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
    case "follow_up_quality_failed":
      return `AI 跟进质量评估失败：${stringifyValue(event.message)}`
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
    case "customer_member_fields_required":
      return event.content !== undefined && event.content.length > 0 ? event.content : "需要补充客户成员信息"
    case "customer_member_fields_completed":
      return event.content !== undefined && event.content.length > 0 ? event.content : "客户成员信息已补齐"
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
    case "task_cancelled":
      return event.content !== undefined && event.content.length > 0 ? event.content : "已取消当前操作"
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
  if (event.interaction !== undefined) {
    setActiveInteraction(isWaitingInteraction(event.interaction) ? event.interaction : null)
    return
  }
  if (isTerminalEvent(event)) {
    setActiveInteraction(null)
  }
}

const sendMessageContent = async (content: string, interactionMetadata?: Record<string, unknown>): Promise<void> => {
  if (content.length === 0 || isStreaming.value) return

  const token = userStore.token
  if (!token) {
    toast.error("请先登录")
    return
  }

  messages.value.push({ id: nextId("user"), role: "user", content, steps: [] })
  startAssistantDraft()
  input.value = ""
  setActiveInteraction(null)
  isStreaming.value = true

  try {
    const request = {
      content,
      ...(sessionId.value !== undefined ? { session_id: sessionId.value } : {}),
      ...(sessionKey.value !== undefined ? { session_key: sessionKey.value } : {}),
      ...(interactionMetadata !== undefined ? { interaction_metadata: interactionMetadata } : {}),
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

const sendMessage = async (): Promise<void> => {
  await sendMessageContent(input.value.trim())
}

const sendInteractionMessage = async (content: string, metadata?: Record<string, unknown>): Promise<void> => {
  await sendMessageContent(content.trim(), metadata)
}

const cancelInteraction = async (): Promise<void> => {
  await sendInteractionMessage("先不处理")
}

const useExample = (example: string): void => {
  input.value = example
}

onMounted(() => {
  void loadInitialSession()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.agent-chat {
  --agent-composer-height: #{$wolf-shell-footer-height-v2};
  --agent-interaction-gap: #{$wolf-space-lg-v2};

  position: relative;
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  height: 100%;
  max-height: 100%;
  min-height: 0;
  overflow: hidden;
  border: 0;
  background: transparent;
  box-shadow: none;
}

.agent-chat__messages {
  height: 100%;
  max-height: 100%;
  min-height: 0;
  overflow: hidden;
}

.agent-chat__message {
  align-items: flex-start;
}

.agent-chat__avatar {
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
}

.agent-chat__avatar--assistant {
  border: 1px solid rgba($wolf-primary-v2, 0.14);
  background: rgba($wolf-primary-v2, 0.1);
  color: $wolf-primary-v2;
}

.agent-chat__avatar--user {
  background: $wolf-primary-v2;
  color: $wolf-text-inverse-v2;
}

.agent-chat__avatar-fallback {
  display: flex;
  width: 100%;
  height: 100%;
  align-items: center;
  justify-content: center;
  color: inherit;
  font-weight: $wolf-font-weight-semibold-v2;
}

.agent-chat__bubble {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: $wolf-font-size-auxiliary-v2;
  line-height: $wolf-line-height-body-v2;
}

.agent-chat__bubble--assistant {
  border-color: rgba($wolf-primary-v2, 0.16);
  background: #F8FBFF;
  color: $wolf-text-primary-v2;
  box-shadow: none;
}

.agent-chat__bubble--user {
  color: $wolf-text-inverse-v2;
}

.agent-chat__bubble-content {
  min-width: 0;
}

.agent-chat__stream {
  display: grid;
  gap: $wolf-space-xs-v2;
  margin-bottom: $wolf-space-md-v2;
  padding-bottom: $wolf-space-sm-v2;
  border-bottom: 1px solid rgba($wolf-primary-v2, 0.12);
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: 1.5;
}

.agent-chat__stream-summary {
  display: grid;
  grid-template-columns: 28px 14px 16px minmax(0, 1fr);
  align-items: center;
  gap: $wolf-space-sm-v2;
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
  border-radius: $wolf-radius-full-v2;
  background: rgba($wolf-primary-v2, 0.1);
  color: $wolf-primary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.agent-chat__stream-chevron {
  width: 14px;
  height: 14px;
  color: $wolf-text-tertiary-v2;
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
  color: $wolf-primary-v2;
}

.agent-chat__stream-icon--success {
  color: $wolf-success-v2;
}

.agent-chat__stream-icon--warning {
  color: $wolf-warning-v2;
}

.agent-chat__stream-icon--danger {
  color: $wolf-danger-v2;
}

.agent-chat__stream-latest {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-chat__stream-list {
  display: grid;
  gap: $wolf-space-sm-v2;
  margin-top: $wolf-space-xs-v2;
  padding-top: $wolf-space-xs-v2;
  padding-left: $wolf-space-md-v2;
  border-left: 1px solid rgba($wolf-primary-v2, 0.12);
}

.agent-chat__stream-step {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr);
  align-items: flex-start;
  gap: $wolf-space-sm-v2;
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
  gap: $wolf-space-lg-v2;
  min-height: 100%;
  color: $wolf-text-secondary-v2;
  text-align: center;
}

.agent-chat__empty-icon {
  width: 36px;
  height: 36px;
  color: $wolf-primary-v2;
}

.agent-chat__empty-title {
  font-size: $wolf-font-size-title-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
}

.agent-chat__examples {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: $wolf-space-sm-v2;
}

.agent-chat__composer {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: var(--agent-composer-height);
  padding: $wolf-space-md-v2 $wolf-page-padding-v2 $wolf-space-lg-v2;
  border-top: 0;
  background: transparent;
}

.agent-chat__input-group {
  width: min(100%, 960px);
  min-height: 60px;
  border-color: rgba($wolf-border-default-v2, 0.72);
  border-radius: $wolf-radius-xl-v2;
  background: rgba($wolf-bg-card-v2, 0.98);
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.08), 0 0 0 1px rgba(15, 23, 42, 0.03);
  backdrop-filter: blur(12px);
}

.agent-chat__textarea {
  min-height: 48px;
  max-height: 160px;
  overflow-y: auto;
}

.agent-chat__input-actions {
  justify-content: flex-end;
  padding-top: 0;
  padding-right: $wolf-space-sm-v2;
  padding-bottom: $wolf-space-sm-v2;
}

.agent-chat__send {
  width: 32px;
  min-width: 32px;
  height: 32px;
  min-height: 32px;
  border-radius: $wolf-radius-control-v2;
}

@media (max-width: 767px) {
  .agent-chat {
    height: 100%;
    min-height: 0;
  }

  .agent-chat__composer {
    padding: $wolf-space-md-v2 $wolf-page-padding-mobile-v2 $wolf-space-md-v2;
  }

}
</style>
