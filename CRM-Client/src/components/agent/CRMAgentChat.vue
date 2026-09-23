<template>
  <section class="agent-chat relative grid h-full max-h-full min-h-0 overflow-hidden" aria-label="AI Agent 聊天">
    <MessageScroller
      class="agent-chat__messages min-h-0"
      :items-count="messageScrollCount"
      :scroll-key="messageScrollKey"
    >
      <div v-if="showEmptyState" class="grid min-h-full place-items-center content-center gap-4 text-center text-muted-foreground">
        <Sparkles class="h-9 w-9 text-primary" aria-hidden="true" />
        <div class="text-base font-semibold text-foreground">告诉我你想查询或处理的 CRM 事项</div>
        <div class="flex flex-wrap justify-center gap-2">
          <Button type="button" variant="outline" size="sm" @click="useExample('我在上海有哪些客户？')">
            查询上海客户
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            @click="useExample('今天和越秀金融的王总沟通了项目进展，下周三再确认。')"
          >
            记录客户跟进
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            @click="useExample('帮我给越秀金融创建联系人王总，手机号 13800138000。')"
          >
            创建联系人
          </Button>
        </div>
      </div>

      <div v-for="message in messages" :key="message.message_id" class="grid w-full gap-2">
        <Message :role="message.role" class="items-start">
          <Avatar
            v-if="message.role !== 'user'"
            class="h-8 w-8 shrink-0 border border-primary/20 bg-primary/10 text-primary"
          >
            <AvatarFallback class="flex h-full w-full items-center justify-center font-semibold text-current">
              AI
            </AvatarFallback>
          </Avatar>
          <Bubble
            v-if="message.role === 'user'"
            variant="sent"
            class="min-w-0 break-words text-sm leading-5 text-primary-foreground"
          >
            <AgentUIMessage
              :message="message"
              :disabled="isStreaming"
              :locked-action-ids="lockedInteractionActionIds"
              @action="submitEntityAction"
              @interaction="submitInteraction"
              @open-entity="openEntity"
            />
          </Bubble>
          <div
            v-else
            class="agent-chat__assistant-content min-w-0 max-w-[760px] flex-1 break-words py-1 text-sm leading-5 text-foreground"
          >
            <AgentUIMessage
              :message="message"
              :disabled="isStreaming"
              :locked-action-ids="lockedInteractionActionIds"
              @action="submitEntityAction"
              @interaction="submitInteraction"
              @open-entity="openEntity"
            />
          </div>
          <Avatar v-if="message.role === 'user'" class="h-8 w-8 shrink-0 bg-primary text-primary-foreground">
            <AvatarFallback class="flex h-full w-full items-center justify-center font-semibold text-current">
              {{ userInitial }}
            </AvatarFallback>
          </Avatar>
        </Message>

        <Message
          v-if="operationsByMessageId.get(String(message.message_id))?.length"
          role="assistant"
          class="items-start"
        >
          <span class="h-8 w-8 shrink-0" aria-hidden="true" />
          <section
            class="agent-chat__operations grid min-w-0 max-w-[760px] flex-1 gap-2"
            aria-label="后台任务状态"
          >
            <AgentAsyncOperationList :operations="operationsByMessageId.get(String(message.message_id)) ?? []" />
          </section>
        </Message>
      </div>

      <Message v-if="pendingUserText !== null" role="user" class="items-start">
        <Bubble variant="sent" class="min-w-0 break-words text-sm leading-5 text-primary-foreground">
          <AgentMessageBody :content="pendingUserText" format="plain" />
        </Bubble>
        <Avatar class="h-8 w-8 shrink-0 bg-primary text-primary-foreground">
          <AvatarFallback class="flex h-full w-full items-center justify-center font-semibold text-current">
            {{ userInitial }}
          </AvatarFallback>
        </Avatar>
      </Message>

      <Message v-if="streamingMessage !== null || showProcessingState" role="assistant" class="items-start">
        <Avatar class="h-8 w-8 shrink-0 border border-primary/20 bg-primary/10 text-primary">
          <AvatarFallback class="flex h-full w-full items-center justify-center font-semibold text-current">
            AI
          </AvatarFallback>
        </Avatar>
        <div class="agent-chat__assistant-content min-w-0 max-w-[760px] flex-1 break-words py-1 text-sm leading-5 text-foreground">
          <AgentUIMessage
            v-if="streamingMessage !== null"
            :message="streamingMessage"
            :disabled="true"
            :locked-action-ids="lockedInteractionActionIds"
          />
          <div v-else class="flex items-center gap-2 text-muted-foreground" role="status">
            <Loader2 class="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            <span>{{ pendingRequestLabel }}</span>
          </div>
        </div>
      </Message>
      <div v-for="(label, index) in requestStatusLabels" :key="index" role="status" class="agent-chat__request-status px-10 text-sm text-warning">{{ label }}</div>
      <div v-if="pendingRequests.length > 0" role="status" class="agent-chat__pending-status px-10 text-sm text-muted-foreground">{{ pendingRequests.length }} 项操作状态确认中，请勿重复提交。</div>

      <section
        v-if="transportError !== null"
        class="agent-chat__transport-error flex items-center gap-2 rounded-xl border border-destructive/25 bg-destructive/5 px-3 py-2 text-destructive"
        role="alert"
      >
        <AlertTriangle aria-hidden="true" />
        <span>{{ transportError }}</span>
      </section>

      <Message
        v-if="unanchoredAsyncOperations.length > 0"
        role="assistant"
        class="mt-2 items-start"
      >
        <span class="h-8 w-8 shrink-0" aria-hidden="true" />
        <section class="agent-chat__operations grid min-w-0 max-w-[760px] flex-1 gap-2">
          <AgentAsyncOperationList :operations="unanchoredAsyncOperations" />
        </section>
      </Message>
    </MessageScroller>

    <form
      class="agent-chat__composer flex items-center justify-center bg-transparent px-4 pb-4 pt-3 md:px-6"
      @submit.prevent="sendMessage"
    >
      <InputGroup class="w-[min(100%,960px)] min-h-[60px] rounded-xl border-border/70 bg-card/95 shadow-none backdrop-blur">
        <InputGroupTextarea
          v-model="input"
          class="min-h-[72px] overflow-y-hidden pb-3.5 pr-14"
          placeholder="输入客户跟进、查询或操作指令..."
          :disabled="isStreaming || pendingRequests.some(request => request.kind !== 'compact')"
          :auto-resize="true"
          :min-rows="2"
          :max-rows="6"
          @keydown.enter.exact.prevent="sendMessage"
        />
        <InputGroupButton
          class="absolute bottom-3 right-3 h-11 min-h-11 w-11 min-w-11 rounded-full"
          type="submit"
          size="icon-xs"
          :disabled="!canSend"
          aria-label="发送"
        >
          <ArrowUp aria-hidden="true" />
        </InputGroupButton>
      </InputGroup>
    </form>
  </section>

  <CustomerDetailSheet
    v-model:visible="customerSheetVisible"
    :customer-id="selectedCustomerId"
  />

  <OpportunityDetailSheet
    v-model:visible="opportunitySheetVisible"
    :opportunity-id="selectedOpportunityId"
  />

  <ContractDetailSheet
    v-model:visible="contractSheetVisible"
    :contract-id="selectedContractId"
  />
</template>

<script setup lang="ts">
import { computed, nextTick, onActivated, onBeforeUnmount, onMounted, ref } from 'vue'
import { AlertTriangle, ArrowUp, Loader2, Sparkles } from 'lucide-vue-next'
import { toast } from 'vue-sonner'

import {
  AgentProtocolError,
  agentApi,
  type AgentChatRequest,
  type AgentStreamEvent,
  type AgentUIEnvelope,
  type AgentRequestStatus,
} from '@/api/agent'
import AgentAsyncOperationList from '@/components/agent/AgentAsyncOperationList.vue'
import { isAgentEntityOpenable, parseAgentContractId } from '@/components/agent/agentEntityNavigation'
import { groupAgentAsyncOperationsByMessage } from '@/components/agent/agentAsyncOperations'
import {
  findCompactTaskAction,
  isCompactTaskCompletionAction,
  optimisticallyCompleteCompactTask,
  unlockInteractionActionId,
} from '@/components/agent/agentInteractionState'
import {
  getMissingAgentHistoryAnchors,
  isVisibleAgentMessage,
  loadLatestAgentMessages,
  mergeAgentHistoryAnchors,
  resolveInitialAgentSession,
} from '@/components/agent/agentHistory'
import AgentMessageBody from '@/components/agent/AgentMessageBody.vue'
import AgentUIMessage from '@/components/agent-ui/AgentUIMessage.vue'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Bubble } from '@/components/ui/bubble'
import { Button } from '@/components/ui/button'
import { InputGroup, InputGroupButton, InputGroupTextarea } from '@/components/ui/input-group'
import { Message } from '@/components/ui/message'
import { MessageScroller } from '@/components/ui/message-scroller'
import { useAgentAsyncOperations } from '@/composables/useAgentAsyncOperations'
import type { AgentChatInput, AgentUIBlock, EntityRef, JsonObject } from '@/schemas/agent-contracts'
import { useUserStore } from '@/stores/user'
import CustomerDetailSheet from '@/views/CustomerDetailSheet.vue'
import OpportunityDetailSheet from '@/views/OpportunityDetailSheet.vue'
import ContractDetailSheet from '@/views/ContractDetailSheet.vue'
import { useTeamStore } from '@/stores/team'

const LAST_SESSION_STORAGE_KEY = 'crm_agent_last_session_id'
const PENDING_REQUESTS_STORAGE_KEY = 'crm_agent_pending_requests'
const REQUEST_POLL_INTERVAL_MS = 2000

interface PendingAgentRequest {
  userId: number
  teamId: number
  sessionId: number | null
  requestId: string
  actionId: string | null
  kind: 'text' | 'interaction' | 'compact' | 'entity'
  hold?: boolean
}

const isPendingAgentRequest = (value: unknown): value is PendingAgentRequest => {
  if (typeof value !== 'object' || value === null) return false
  const item = value as Record<string, unknown>
  const userId = item.userId
  const teamId = item.teamId
  const sessionIdValue = item.sessionId
  const requestId = item.requestId
  const actionId = item.actionId
  const kind = item.kind
  const hold = item.hold
  return typeof userId === 'number' && Number.isInteger(userId) && userId > 0
    && typeof teamId === 'number' && Number.isInteger(teamId) && teamId > 0
    && (sessionIdValue === null || typeof sessionIdValue === 'number' && Number.isInteger(sessionIdValue) && sessionIdValue > 0)
    && typeof requestId === 'string' && /^[\da-f]{8}-[\da-f]{4}-[1-8][\da-f]{3}-[89ab][\da-f]{3}-[\da-f]{12}$/i.test(requestId)
    && (actionId === null || typeof actionId === 'string')
    && (kind === 'text' || kind === 'interaction' || kind === 'compact' || kind === 'entity')
    && (hold === undefined || typeof hold === 'boolean')
}

const readPendingRequests = (): PendingAgentRequest[] => {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(PENDING_REQUESTS_STORAGE_KEY) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter(isPendingAgentRequest) : []
  } catch {
    return []
  }
}

const savePendingRequests = (requests: PendingAgentRequest[]): void => {
  localStorage.setItem(PENDING_REQUESTS_STORAGE_KEY, JSON.stringify(requests))
}

const userStore = useUserStore()
const teamStore = useTeamStore()
const input = ref('')
const isStreaming = ref(false)
const isLoadingHistory = ref(false)
const sessionId = ref<number | undefined>()
const sessionKey = ref<string | undefined>()
const messages = ref<AgentUIEnvelope[]>([])
const insertedHistoryAnchorIds = ref<ReadonlySet<number>>(new Set())
const pendingUserText = ref<string | null>(null)
const pendingRequestLabel = ref('正在处理...')
const streamingBlocks = ref<AgentUIBlock[]>([])
const activeStreamMessageId = ref<number | null>(null)
const activeStreamTurnId = ref<string | null>(null)
const activeStreamSequence = ref(0)
const activeStreamFinalized = ref(false)
const transportError = ref<string | null>(null)
const messageScrollKey = ref(0)
const selectedCustomerId = ref<string | null>(null)
const selectedOpportunityId = ref<string | null>(null)
const selectedContractId = ref<number | null>(null)
const lockedInteractionActionIds = ref<ReadonlySet<string>>(new Set())
const pendingRequests = ref<PendingAgentRequest[]>([])
const requestStatusLabels = ref<string[]>([])
let sessionOwner: { userId: number, teamId: number } | undefined
let requestPollTimer: ReturnType<typeof setTimeout> | undefined
let disposed = false
const activeStatusPolls = new Set<string>()
let messageLoadGeneration = 0

interface AgentMessageLoadResult {
  applied: boolean
  messages: AgentUIEnvelope[]
}

const closeSelectedEntity = (): void => {
  selectedCustomerId.value = null
  selectedOpportunityId.value = null
  selectedContractId.value = null
}

const customerSheetVisible = computed({
  get: () => selectedCustomerId.value !== null,
  set: (visible: boolean) => {
    if (!visible) selectedCustomerId.value = null
  },
})

const opportunitySheetVisible = computed({
  get: () => selectedOpportunityId.value !== null,
  set: (visible: boolean) => {
    if (!visible) selectedOpportunityId.value = null
  },
})

const contractSheetVisible = computed({
  get: () => selectedContractId.value !== null,
  set: (visible: boolean) => {
    if (!visible) selectedContractId.value = null
  },
})
const loadSessionMessages = async (targetSessionId: number): Promise<AgentMessageLoadResult> => {
  const generation = ++messageLoadGeneration
  const loadedMessages = await loadLatestAgentMessages(agentApi.listMessages, targetSessionId)
  const applied = generation >= messageLoadGeneration && sessionId.value === targetSessionId
  if (applied) {
    messageLoadGeneration = generation
    messages.value = loadedMessages
    insertedHistoryAnchorIds.value = new Set()
    if (pendingRequests.value.length === 0) pendingUserText.value = null
    messageScrollKey.value += 1
  }
  return { applied, messages: loadedMessages }
}

const loadSessionAnchors = async (
  targetSessionId: number,
  loadedMessages: AgentUIEnvelope[],
): Promise<void> => {
  const targetGeneration = messageLoadGeneration
  const loadedMessageIds = new Set(loadedMessages.map(message => message.message_id))
  const missingMessageIds = [...new Set(asyncOperations.value.flatMap(operation => (
    [operation.source_user_message_id, operation.source_assistant_message_id]
      .filter((messageId): messageId is number => (
        messageId !== null
        && messageId !== undefined
        && messageId > 0
        && !loadedMessageIds.has(messageId)
      ))
  )))].sort((left, right) => left - right)
  if (missingMessageIds.length === 0) return

  const anchors = await agentApi.listMessageAnchors(targetSessionId, missingMessageIds)
  if (targetGeneration !== messageLoadGeneration || sessionId.value !== targetSessionId) return
  const insertedAnchors = getMissingAgentHistoryAnchors(messages.value, anchors)
  if (insertedAnchors.length === 0) return
  insertedHistoryAnchorIds.value = new Set([
    ...insertedHistoryAnchorIds.value,
    ...insertedAnchors.map(anchor => anchor.message_id),
  ])
  messages.value = mergeAgentHistoryAnchors(messages.value, insertedAnchors)
}

const refreshSessionAnchors = (
  targetSessionId: number,
  loadedMessages: AgentUIEnvelope[],
): void => {
  void loadSessionAnchors(targetSessionId, loadedMessages).catch(() => {
    // Anchor reads are best-effort; operation ownership remains unresolved when unavailable.
  })
}

const {
  operations: asyncOperations,
  loadSession: loadSessionOperations,
  resumePolling: resumeOperationPolling,
  dispose: disposeOperationPolling,
} = useAgentAsyncOperations({
  onChanged: () => {
    messageScrollKey.value += 1
  },
  onWaitingUser: operation => {
    const targetSessionId = operation.session_id
    if (targetSessionId === null || targetSessionId === undefined || targetSessionId !== sessionId.value) return
    void loadSessionMessages(targetSessionId).then(result => {
      if (result.applied) refreshSessionAnchors(targetSessionId, result.messages)
    }).catch(() => {
      // A later session refresh restores messages if the projection is not visible yet.
    })
  },
  onTerminal: operation => {
    const targetSessionId = operation.session_id
    if (targetSessionId === null || targetSessionId === undefined || targetSessionId !== sessionId.value) return
    void loadSessionMessages(targetSessionId).then(result => {
      if (result.applied) refreshSessionAnchors(targetSessionId, result.messages)
    }).catch(() => {
      // A later session refresh restores messages if the projection is not visible yet.
    })
  },
})

const messageAnchors = computed(() => messages.value.map(message => ({
  id: String(message.message_id),
  role: message.role === 'user' ? 'user' as const : 'assistant' as const,
})))
const groupedAsyncOperations = computed(() => (
  groupAgentAsyncOperationsByMessage(messageAnchors.value, asyncOperations.value)
))
const operationsByMessageId = computed(() => groupedAsyncOperations.value.byMessageId)
const unanchoredAsyncOperations = computed(() => groupedAsyncOperations.value.unanchored)
const canSend = computed(() => input.value.trim().length > 0 && !isStreaming.value && !pendingRequests.value.some(request => request.kind !== 'compact'))
const streamingMessage = computed(() => {
  if (streamingBlocks.value.length === 0) return null
  return {
    schema_version: 'crm.agent.ui.v1',
    message_id: activeStreamMessageId.value ?? Number.MAX_SAFE_INTEGER,
    turn_id: activeStreamTurnId.value ?? 'turn_streaming',
    role: 'assistant',
    state: 'streaming',
    blocks: streamingBlocks.value,
    suggested_actions: [],
    metadata: {
      display: 'MESSAGE',
      route: 'WORKFLOW',
      accessibility_label: 'Agent 正在执行',
    },
  } as AgentUIEnvelope
})
const showProcessingState = computed(() => isStreaming.value && streamingBlocks.value.length === 0)
const showEmptyState = computed(() => (
  !isLoadingHistory.value
  && messages.value.length === 0
  && pendingUserText.value === null
  && !isStreaming.value
  && pendingRequests.value.length === 0
))
const messageScrollCount = computed(() => (
  messages.value.length
  - [...insertedHistoryAnchorIds.value].filter(messageId => messages.value.some(message => message.message_id === messageId)).length
  + (pendingUserText.value === null ? 0 : 1)
  + (isStreaming.value ? 1 : 0)
  + asyncOperations.value.length
  + (transportError.value === null ? 0 : 1)
  + requestStatusLabels.value.length
))
const userInitial = computed(() => {
  const name = userStore.userInfo?.name
  return name !== undefined && name.length > 0 ? name.charAt(0) : '我'
})

const storedSessionId = (): number | undefined => {
  const raw = localStorage.getItem(LAST_SESSION_STORAGE_KEY)
  if (raw === null) return undefined
  const parsed = Number(raw)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined
}

const rememberSession = (id: number, key: string): void => {
  if (sessionId.value !== undefined && sessionId.value !== id) {
    lockedInteractionActionIds.value = new Set()
    insertedHistoryAnchorIds.value = new Set()
    messageLoadGeneration += 1
    pendingRequests.value = []
  }
  sessionId.value = id
  sessionKey.value = key
  localStorage.setItem(LAST_SESSION_STORAGE_KEY, String(id))
}

const ownerForRequest = (): { userId: number, teamId: number } | undefined => {
  const userId = userStore.userInfo?.id
  const teamId = teamStore.currentTeam?.id
  if (sessionOwner !== undefined && typeof userId === 'number' && userId > 0 && userId !== sessionOwner.userId) return undefined
  if (sessionOwner !== undefined && typeof teamId === 'number' && teamId > 0 && teamId !== sessionOwner.teamId) return undefined
  if (typeof userId === 'number' && userId > 0 && typeof teamId === 'number' && teamId > 0) {
    return { userId, teamId }
  }
  return sessionOwner
}

const ownsRequest = (request: PendingAgentRequest): boolean => {
  const owner = ownerForRequest()
  return owner !== undefined && owner.userId === request.userId && owner.teamId === request.teamId
}

const scheduleRequestPoll = (): void => {
  const active = pendingRequests.value.filter(request => request.hold !== true && request.sessionId !== null)
  if (disposed || requestPollTimer !== undefined || active.length === 0) return
  requestPollTimer = setTimeout(() => {
    requestPollTimer = undefined
    void Promise.all(active.map(pollRequestStatus)).finally(scheduleRequestPoll)
  }, REQUEST_POLL_INTERVAL_MS)
}

const trackRequest = (request: PendingAgentRequest): void => {
  const stored = readPendingRequests().filter(item => item.requestId !== request.requestId)
  savePendingRequests([...stored, request])
  pendingRequests.value = [...pendingRequests.value, request]
  if (request.actionId !== null) {
    lockedInteractionActionIds.value = new Set([...lockedInteractionActionIds.value, request.actionId])
  }
  scheduleRequestPoll()
}

const bindRequestSession = (requestId: string, id: number): void => {
  const stored = readPendingRequests()
  const request = stored.find(item => item.requestId === requestId)
  if (request === undefined || !ownsRequest(request)) return
  request.sessionId = id
  savePendingRequests(stored)
  const active = pendingRequests.value.find(item => item.requestId === requestId)
  if (active !== undefined) active.sessionId = id
  pendingRequests.value = [...pendingRequests.value]
}

const restorePendingRequests = (id: number): void => {
  pendingRequests.value = readPendingRequests().filter(request => request.sessionId === id && ownsRequest(request))
  lockedInteractionActionIds.value = new Set(pendingRequests.value.flatMap(request => request.actionId === null ? [] : [request.actionId]))
  const active = pendingRequests.value.filter(request => request.hold !== true)
  if (active.length > 0) void Promise.all(active.map(pollRequestStatus)).finally(scheduleRequestPoll)
}

const forgetRequest = (request: PendingAgentRequest, releaseAction: boolean): void => {
  savePendingRequests(readPendingRequests().filter(item => item.requestId !== request.requestId))
  pendingRequests.value = pendingRequests.value.filter(item => item.requestId !== request.requestId)
  if (releaseAction && request.actionId !== null) unlockInteraction(request.actionId)
  if (pendingRequests.value.length === 0) pendingUserText.value = null
}

const settleRequest = async (request: PendingAgentRequest, status: AgentRequestStatus): Promise<void> => {
  if (status.status === 'IN_PROGRESS') return
  const action = request.actionId === null ? undefined : messages.value.flatMap(message => (
    message.blocks.filter(block => block.type === 'interaction' && block.submit_action_id === request.actionId)
      .map(block => ({ messageId: message.message_id, block }))
  ))[0]
  const history = await reloadAuthoritativeSessionState().catch(() => undefined)
  if (status.message !== null && request.kind !== 'compact') upsertFinalMessage(status.message)
  if (status.status === 'COMPLETED' && request.kind === 'compact' && request.actionId !== null) {
    messages.value = optimisticallyCompleteCompactTask(messages.value, request.actionId)
  }
  if (status.status === 'PARTIALLY_COMMITTED') {
    requestStatusLabels.value = [...requestStatusLabels.value, '部分操作已提交，请核对后续步骤。']
  } else if (status.status === 'NEEDS_RECONCILIATION') {
    requestStatusLabels.value = [...requestStatusLabels.value, '操作需要核对，部分更改可能已提交，请勿重复提交。']
  } else if (status.status === 'FAILED' && status.message === null) {
    requestStatusLabels.value = [...requestStatusLabels.value, '请求未完成，请核对后再继续。']
  }
  const failedBlock = status.status === 'FAILED' ? status.message?.blocks.find(block => block.type === 'error') : undefined
  if (failedBlock?.type === 'error' && request.kind === 'compact') toast.error(failedBlock.message)
  const retryableAction = action?.block.type === 'interaction'
    && action.block.business_action === 'provide_follow_up_content'
    && (action.block.interaction_type === 'text_input' || action.block.interaction_type === 'form')
  const sourceBlock = action?.block.type === 'interaction' ? action.block : undefined
  const active = history?.applied === true && sourceBlock !== undefined
    && history.messages.some(message => message.message_id === action?.messageId && message.blocks.some(block => (
      block.type === 'interaction' && sourceBlock !== undefined
      && block.id === sourceBlock.id && block.interaction_id === sourceBlock.interaction_id
      && block.state === 'ACTIVE' && block.submit_action_id === request.actionId
    )))
  const compactActive = request.kind === 'compact' && history?.applied === true && request.actionId !== null
    && history.messages.some(message => message.blocks.some(block => (
      block.type === 'interaction' && block.presentation === 'COMPACT_TASK_COMPLETION'
      && block.state === 'ACTIVE' && block.submit_action_id === request.actionId
    )))
  const releaseAction = status.status === 'FAILED' && failedBlock?.type === 'error' && failedBlock.retryable
    && ((retryableAction && active) || compactActive)
  if (releaseAction && request.actionId !== null) {
    await nextTick()
    unlockInteraction(request.actionId)
  }
  if (status.status === 'NEEDS_RECONCILIATION' || status.status === 'PARTIALLY_COMMITTED') {
    request.hold = true
    const stored = readPendingRequests().filter(item => item.requestId !== request.requestId)
    savePendingRequests([...stored, request])
  } else {
    forgetRequest(request, releaseAction)
  }
  transportError.value = null
  messageScrollKey.value += 1
}
const pollRequestStatus = async (request: PendingAgentRequest): Promise<void> => {
  if (disposed || request.hold === true || request.sessionId === null || activeStatusPolls.has(request.requestId) || !ownsRequest(request)) return
  activeStatusPolls.add(request.requestId)
  try {
    const status = await agentApi.getRequest(request.sessionId, request.requestId)
    if (disposed || sessionId.value !== request.sessionId || !ownsRequest(request)) return
    await settleRequest(request, status)
  } catch {
    // A failed status read cannot establish whether the write committed.
  } finally {
    activeStatusPolls.delete(request.requestId)
    scheduleRequestPoll()
  }
}

const createTrackedRequest = (agentInput: AgentChatInput, kind: PendingAgentRequest['kind']): { request: AgentChatRequest, pending?: PendingAgentRequest } => {
  const request: AgentChatRequest = { ...requestContext(), client_request_id: crypto.randomUUID(), input: agentInput }
  const owner = ownerForRequest()
  if (owner === undefined) return { request }
  const pending: PendingAgentRequest = {
    ...owner, sessionId: sessionId.value ?? null, requestId: request.client_request_id,
    actionId: agentInput.type === 'text' ? null : agentInput.action_id, kind,
  }
  trackRequest(pending)
  return { request, pending }
}

const loadInitialSession = async (): Promise<void> => {
  isLoadingHistory.value = true
  try {
    const response = await agentApi.listSessions()
    const session = resolveInitialAgentSession(response.items, storedSessionId())
    if (session === undefined) return
    rememberSession(session.id, session.session_key)
    sessionOwner = { userId: session.user_id, teamId: session.team_id }
    const [messageResult] = await Promise.all([
      loadSessionMessages(session.id),
      loadSessionOperations(session.id),
    ])
    if (messageResult.applied) refreshSessionAnchors(session.id, messageResult.messages)
    restorePendingRequests(session.id)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : 'Agent 会话加载失败')
  } finally {
    isLoadingHistory.value = false
  }
}

const resetStreamProjection = (): void => {
  streamingBlocks.value = []
  activeStreamMessageId.value = null
  activeStreamTurnId.value = null
  activeStreamSequence.value = 0
  activeStreamFinalized.value = false
}

const acceptStreamEvent = (event: Extract<AgentStreamEvent, { event: 'agent_ui' }>): boolean => {
  if (activeStreamTurnId.value === null) {
    if (event.sequence !== 1) {
      throw new AgentProtocolError('Agent stream must start with sequence 1')
    }
    activeStreamMessageId.value = event.message_id
    activeStreamTurnId.value = event.turn_id
  } else {
    if (activeStreamTurnId.value !== event.turn_id) {
      throw new AgentProtocolError('Agent stream changed turn identity before final')
    }
    if (
      activeStreamMessageId.value !== null
      && event.message_id !== null
      && activeStreamMessageId.value !== event.message_id
    ) {
      throw new AgentProtocolError('Agent stream changed message identity before final')
    }
    if (activeStreamMessageId.value === null && event.message_id !== null) {
      activeStreamMessageId.value = event.message_id
    }
  }
  if (event.sequence <= activeStreamSequence.value) return false
  if (activeStreamFinalized.value) {
    throw new AgentProtocolError('Agent stream emitted an event after final')
  }
  if (event.sequence !== activeStreamSequence.value + 1) {
    throw new AgentProtocolError('Agent stream sequence contains a gap or is out of order')
  }
  activeStreamSequence.value = event.sequence
  return true
}

const applyDelta = (event: Extract<AgentStreamEvent, { event: 'agent_ui', phase: 'delta' }>): void => {
  for (const operation of event.operations) {
    if (operation.op === 'upsert_block') {
      const index = streamingBlocks.value.findIndex(block => block.id === operation.block.id)
      if (index < 0) streamingBlocks.value.push(operation.block)
      else streamingBlocks.value[index] = operation.block
      continue
    }

    const existing = streamingBlocks.value.find(block => block.id === operation.block_id)
    if (existing === undefined) {
      streamingBlocks.value.push({
        id: operation.block_id,
        type: 'text',
        format: 'plain',
        text: operation.delta,
      })
    } else if (existing.type === 'text') {
      existing.text += operation.delta
    } else {
      throw new AgentProtocolError('append_text operation targeted a non-text block')
    }
  }
  messageScrollKey.value += 1
}

const upsertFinalMessage = (message: AgentUIEnvelope): void => {
  const index = messages.value.findIndex(item => item.message_id === message.message_id)
  if (!isVisibleAgentMessage(message)) {
    if (index >= 0) messages.value.splice(index, 1)
    return
  }
  if (index < 0) {
    messages.value.push(message)
  } else {
    messages.value[index] = message
  }
  messageScrollKey.value += 1
}

const handleStreamEvent = (event: AgentStreamEvent): void => {
  if (event.event === 'session') {
    rememberSession(event.session_id, event.session_key)
    return
  }
  if (event.event === 'transport_error') {
    transportError.value = event.message
    return
  }
  if (event.event === 'done') return

  if (!acceptStreamEvent(event)) return
  if (event.phase === 'delta') {
    applyDelta(event)
    return
  }

  upsertFinalMessage(event.message)
  streamingBlocks.value = []
  activeStreamFinalized.value = true
}

const requestContext = (): Pick<AgentChatRequest, 'session_id' | 'session_key'> => {
  if (sessionId.value !== undefined) return { session_id: sessionId.value }
  if (sessionKey.value !== undefined) return { session_key: sessionKey.value }
  return {}
}

const reloadAuthoritativeSessionState = async (): Promise<AgentMessageLoadResult | undefined> => {
  const targetSessionId = sessionId.value
  if (targetSessionId === undefined) return undefined
  const [messageResult] = await Promise.all([
    loadSessionMessages(targetSessionId),
    loadSessionOperations(targetSessionId).catch(() => undefined),
  ])
  if (messageResult.applied) refreshSessionAnchors(targetSessionId, messageResult.messages)
  return messageResult
}


const submitInput = async (
  agentInput: AgentChatInput,
  options: { pendingText?: string, label: string },
): Promise<void> => {
  if (isStreaming.value) return
  const token = userStore.token
  if (!token) {
    toast.error('请先登录')
    return
  }
  transportError.value = null
  resetStreamProjection()
  pendingUserText.value = options.pendingText ?? null
  pendingRequestLabel.value = options.label
  isStreaming.value = true

  const { request, pending } = createTrackedRequest(agentInput, agentInput.type === 'text' ? 'text' : agentInput.type === 'entity_action' ? 'entity' : 'interaction')
  try {
    await agentApi.chatStream(request, (event) => {
      if (event.event === 'session' && pending !== undefined) bindRequestSession(pending.requestId, event.session_id)
      handleStreamEvent(event)
    }, token)
    if (pending !== undefined) await pollRequestStatus(pending)
    if (pending === undefined) {
      try { await reloadAuthoritativeSessionState() } catch { /* Keep the streamed result. */ }
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Agent 请求失败'
    if (pending === undefined) {
      if (transportError.value === null) transportError.value = message
      toast.error(message)
    } else {
      transportError.value = null
      await pollRequestStatus(pending)
    }
    resetStreamProjection()
  } finally {
    isStreaming.value = false
    resetStreamProjection()
    messageScrollKey.value += 1
  }
}

const sendMessage = async (): Promise<void> => {
  const text = input.value.trim()
  if (text.length === 0 || !canSend.value) return
  input.value = ''
  await submitInput({ type: 'text', text }, { pendingText: text, label: '正在理解并处理...' })
}

const unlockInteraction = (actionId: string): void => {
  lockedInteractionActionIds.value = unlockInteractionActionId(
    lockedInteractionActionIds.value,
    actionId,
  )
}

const submitCompactTaskInteraction = async (actionId: string, values: JsonObject): Promise<void> => {
  if (lockedInteractionActionIds.value.has(actionId)) return
  const token = userStore.token
  if (!token) {
    toast.error('请先登录')
    return
  }
  if (findCompactTaskAction(messages.value, actionId) === undefined) return
  const { request, pending } = createTrackedRequest(
    { type: 'interaction_submission', action_id: actionId, values }, 'compact',
  )
  if (pending === undefined) lockedInteractionActionIds.value = new Set([...lockedInteractionActionIds.value, actionId])
  try {
    await agentApi.chatStream(request, event => {
      if (event.event === 'session') {
        rememberSession(event.session_id, event.session_key)
        if (pending !== undefined) bindRequestSession(pending.requestId, event.session_id)
      }
    }, token)
  } catch {
    // The request receipt, not stream liveness, determines whether the action committed.
  }
  if (pending !== undefined) await pollRequestStatus(pending)
  else requestStatusLabels.value = [...requestStatusLabels.value, '完成状态确认中，请勿重复提交。']
}

const submitInteraction = async (actionId: string, values: JsonObject): Promise<void> => {
  if (isCompactTaskCompletionAction(messages.value, actionId)) {
    await submitCompactTaskInteraction(actionId, values)
    return
  }
  if (isStreaming.value || lockedInteractionActionIds.value.has(actionId)) return
  const actionMessage = messages.value.find(message => message.blocks.some(block => (
    block.type === 'interaction' && block.submit_action_id === actionId
  )))
  const actionBlock = actionMessage?.blocks.find(block => (
    block.type === 'interaction' && block.submit_action_id === actionId
  ))
  if (actionBlock?.type !== 'interaction' || actionMessage === undefined) {
    await submitInput(
      { type: 'interaction_submission', action_id: actionId, values },
      { label: '正在提交...' },
    )
    return
  }

  lockedInteractionActionIds.value = new Set([...lockedInteractionActionIds.value, actionId])
  await submitInput(
    { type: 'interaction_submission', action_id: actionId, values },
    { label: '正在提交...' },
  )
}

const submitEntityAction = async (actionId: string): Promise<void> => {
  await submitInput(
    { type: 'entity_action', action_id: actionId },
    { label: '正在执行操作...' },
  )
}

const openEntity = (entityRef: EntityRef): void => {
  if (!isAgentEntityOpenable(entityRef)) {
    toast.info('该类型记录暂不支持在 Agent 中打开，请到对应业务页面查看')
    return
  }

  if (entityRef.resource === 'contract') {
    const contractId = parseAgentContractId(entityRef.public_id)
    if (contractId === null) {
      toast.error('无法打开合同详情：合同编号无效')
      return
    }
    closeSelectedEntity()
    selectedContractId.value = contractId
    return
  }

  closeSelectedEntity()
  if (entityRef.resource === 'customer') {
    selectedCustomerId.value = entityRef.public_id
    return
  }

  selectedOpportunityId.value = entityRef.public_id
}

const useExample = (example: string): void => {
  input.value = example
}

onMounted(() => {
  void loadInitialSession()
})

onActivated(() => {
  disposed = false
  messageScrollKey.value += 1
  resumeOperationPolling()
  if (pendingRequests.value.length > 0) void Promise.all(pendingRequests.value.map(pollRequestStatus)).finally(scheduleRequestPoll)
})
onBeforeUnmount(() => {
  disposed = true
  if (requestPollTimer !== undefined) clearTimeout(requestPollTimer)
  disposeOperationPolling()
})
</script>

<style scoped>
.agent-chat {
  height: 100%;
  max-height: 100%;
  min-height: 0;
  overflow: hidden;
  grid-template-rows: minmax(0, 1fr) auto;
}

.agent-chat__transport-error {
  width: min(calc(100% - 40px), 680px);
  margin-left: 40px;
}

.agent-chat__transport-error svg {
  width: 16px;
  height: 16px;
  flex: 0 0 16px;
}

.agent-chat__composer {
  min-height: calc(85px + env(safe-area-inset-bottom, 0px));
}

</style>
