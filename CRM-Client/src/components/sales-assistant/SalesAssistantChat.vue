<script setup lang="ts">
import { computed, nextTick, onActivated, onDeactivated, onUnmounted, ref, shallowReactive, shallowRef, watch } from 'vue'
import { useRouter } from 'vue-router'
import { isAxiosError } from 'axios'
import { ArrowUp, Info, LoaderCircle, Lock, MessageSquare, X } from 'lucide-vue-next'
import { assistantApi, parseStageEvent, StageNameSchema, submitInputStream } from '@/api/assistant'
import type { AssistantTurn, StageEvent, StageName, StageSegment, SubmitAssistantInput } from '@/api/assistant'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ZodError } from 'zod'
import AgentUIMessage from '@/components/agent-ui/AgentUIMessage.vue'
import AgentUIBanner from '@/components/agent-ui/AgentUIBanner.vue'
import AgentUIProcessBlock from '@/components/agent-ui/AgentUIProcessBlock.vue'
import DataViewStatePanel from '@/components/crmwolf/DataViewStatePanel.vue'
import FeedbackAlert from '@/components/crmwolf/FeedbackAlert.vue'
import type { ProcessBlock, ProcessItemMeta, ProcessItemStatus } from '@/components/agent-ui/agentUIProcess'
import type { FeedbackError } from '@/types/feedback'
import type { InteractionNotice } from '@/components/agent-ui/interactionNotice'
import type { EntityRef, JsonObject } from '@/schemas/agent-contracts/common'
import type { AgentUIEnvelope } from '@/schemas/agent-contracts/ui-envelope'
import { AssistantRejectReasonSchema } from '@/schemas/assistant-contracts'
import type {
  AssistantTaskView, TaskWaiting, ConversationView, ConversationReply, ConversationRequestStatus, ConversationBoundary, ConversationProjection,
  ConversationLink, PendingEntityDraft
} from '@/schemas/assistant-contracts'
import { assistantEntityDetailRoute, assistantPageRoute } from '@/components/agent/agentEntityNavigation'
import { handOffAssistantTurn, reclaimAssistantTurn } from '@/components/sales-assistant/assistantBackgroundTurn'

interface ChatEntry {
  id: number
  serverId?: string | undefined
  ownTask?: AssistantTaskView | null | undefined
  boundary?: ConversationBoundary | null | undefined
  role: 'user' | 'assistant'
  text: string
  waiting: TaskWaiting | null
  at?: Date | undefined
  /** Historical messages never hold authoritative task state or interactive cards. */
  replayed: boolean
  outcome?: NonNullable<ConversationView['messages'][number]['outcome']> | undefined
  ui?: AgentUIEnvelope | null | undefined
  links?: ConversationLink[] | undefined
  projection?: ConversationProjection | null | undefined
}

const router = useRouter()

const task = shallowRef<AssistantTaskView | null>(null)
let disposed = false
let navigationVersion = 0
let viewRequestSequence = 0
let appliedViewRequest = 0
let historyExtended = false
onUnmounted(() => { disposed = true })
defineProps<{ optionalMarker?: boolean }>()
const emit = defineEmits<{
  (e: 'task-updated', task: AssistantTaskView, replyMessage: string): void
  (e: 'task-created', task: AssistantTaskView): void
}>()
// Wire snapshots are replaced, not deeply mutated. React only to list and entry changes.
const entries = shallowRef<ChatEntry[]>(shallowReactive([]))
const inputText = ref('')
const submitting = ref(false)
const sendingText = ref(false)
const heldActionIds = ref<ReadonlySet<string>>(new Set())
const holdAction = (actionId: string | null): void => {
  if (actionId === null || heldActionIds.value.has(actionId)) return
  heldActionIds.value = new Set([...heldActionIds.value, actionId])
}
const releaseAction = (actionId: string | null): void => {
  if (actionId === null || !heldActionIds.value.has(actionId)) return
  const next = new Set(heldActionIds.value)
  next.delete(actionId)
  heldActionIds.value = next
}
const seq = ref(0)
const conversation = shallowRef<ConversationView | null>(null)
const loadingConversation = ref(true)
const historyError = ref('')
const routing = ref(false)
const olderCursor = ref<number | null>(null)
const unacceptedText = ref('')
/** Submission outcome per card (submit_action_id) that the server card cannot express. */
const interactionNotices = ref<Record<string, InteractionNotice>>({})
const lostSend = shallowRef<LostSend | null>(null)
const lostSendBlocking = computed(() => lostSend.value !== null && lostSend.value.phase !== 'not_saved')
/** Same content after a confirmed not-saved send keeps its key, so the server can never save it twice. */
const requestKey = (fingerprint: string): string => {
  const lost = lostSend.value
  return lost?.phase === 'not_saved' && lost.fingerprint === fingerprint ? lost.key : crypto.randomUUID()
}

const SESSION_UPDATED_MESSAGE = '会话已更新，请查看当前提示；未接受的内容可重新发送。'
const LOGIN_EXPIRED_MESSAGE = '登录状态已失效，请重新登录后重试；不会自动开始新的记录。'
const REJECTED_SUBMIT_MESSAGE = '这次提交没有被接受，请按当前提示修改后再提交。'
const NOT_SAVED_MESSAGE = '刚才网络不稳定，这条还没有保存。内容都在，可以直接再提交。'
const UNCONFIRMED_MESSAGE = '网络较慢，还没确认是否已保存。为避免重复，先不要再次提交。'
// Lost-response checks back off 2/4/8/16/30 s (about one minute) before handing over to 「查看结果」.
const LOST_SEND_DELAYS_MS = [2_000, 4_000, 8_000, 16_000, 30_000]
type CommandFailure = 'conflict' | 'auth' | 'rejected'
type CommandOutcome = 'accepted' | 'explicit' | 'not_saved' | 'unconfirmed' | 'conflict'
/**
 * A keyed send whose response never arrived. The client only asks the server what
 * became of `key`; it never resends on its own. A resend after `not_saved` reuses `key`.
 */
interface LostSend {
  key: string
  fingerprint: string
  phase: 'checking' | 'not_saved' | 'unconfirmed'
  /** The card shows its own not-saved banner, so the composer stays quiet. */
  cardNotice: boolean
  onNotSaved: () => void
  /** The server confirmed it landed after the response was lost. */
  onAccepted?: (() => void) | undefined
}
type KeyedSend = Omit<LostSend, 'phase'>
interface CommandDispatch {
  outcome: CommandOutcome
  detail: string
}

const OUT_OF_RANGE_KIND = '请从卡片给出的活动类型中选择'
const EMPTY_CONVERSATION_TITLE = '把一次客户沟通交给我整理'
const EMPTY_CONVERSATION_HINT = '发送一句话开始，例如「今天下午和睿狐科技开了个线上会议，聊了 POC 部署」。'
const INPUT_LOCKED_HINT = '请先处理上方的待办卡片，处理完成后可以继续输入。'
const LIVE_STAGE_STATUS: Record<LiveStage['status'], ProcessItemStatus> = {
  pending: 'PENDING',
  running: 'RUNNING',
  done: 'COMPLETED',
  failed: 'FAILED',
  awaiting: 'WAITING',
}

const conflictDetail = (error: unknown): string => {
  if (!isAxiosError(error)) return ''
  const data = error.response?.data as { detail?: unknown } | undefined
  const detail = data?.detail
  if (typeof detail === 'string') return detail
  if (detail !== null && typeof detail === 'object' && 'message' in detail) {
    const message = (detail as { message?: unknown }).message
    if (typeof message === 'string') return message
  }
  return ''
}

const explicitCommandFailure = (error: unknown): CommandFailure | null => {
  if (!isAxiosError(error)) return null
  const status = error.response?.status
  if (status === 401) return 'auth'
  if (status === 409) return 'conflict'
  if (status === 400 || status === 403 || status === 404 || status === 422) return 'rejected'
  return null
}

const conversationLoadErrorMessage = (error: unknown): string => {
  const noNewRecord = '；不会自动开始新的记录。'
  if (!isAxiosError(error)) return `对话加载失败，请重试${noNewRecord}`
  const responseData = error.response?.data as { error_code?: unknown } | undefined
  if (responseData?.error_code === 'DATABASE_SCHEMA_MISMATCH') {
    return `数据库结构与当前版本不一致，请联系管理员执行数据库迁移后重试${noNewRecord}`
  }
  if (error.response?.status === 401) return LOGIN_EXPIRED_MESSAGE
  if (error.response === undefined) return `服务或网络暂时不可用，请检查网络后重试${noNewRecord}`
  if (error.response.status >= 500) return `服务暂时不可用，请稍后重试${noNewRecord}`
  return `对话加载失败，请重试${noNewRecord}`
}

const waiting = computed<TaskWaiting | null>(() => task.value?.waiting ?? null)
const isTerminal = computed(() => task.value != null && task.value.status !== 'ACTIVE')



const inputPlaceholder = computed(() => {
  if (waiting.value?.type === 'FIELD' && waiting.value.field === 'temporal_choice') {
    const active = entries.value.flatMap((entry) => entry.ui?.blocks ?? []).find((block) =>
      block.type === 'interaction' && block.state === 'ACTIVE' && block.submit_action_id === waiting.value?.action_id)
    return active?.type === 'interaction' && active.interaction_type === 'text_input'
      ? active.fields[0]?.placeholder ?? '请按当前问题补充信息'
      : '请按当前问题补充信息'
  }
  return '描述一次客户沟通，我来整理成跟进或会议纪要…'
})

const pushEntry = (
  role: 'user' | 'assistant',
  text: string,
  entryWaiting: TaskWaiting | null = null,
  replayed = false
): void => {
  seq.value += 1
  entries.value.push(shallowReactive<ChatEntry>({
    id: seq.value, role, text, waiting: entryWaiting, replayed, at: new Date(), ownTask: task.value
  }))
  scrollToBottom()
}

const scrollId = ref<HTMLElement | null>(null)
let scrollSchedule = 0
const scrollToBottom = (waitForLayout = false): void => {
  const schedule = ++scrollSchedule
  void nextTick(() => {
    const scroller = scrollId.value
    if (scroller === null || schedule !== scrollSchedule) return
    const scroll = (): void => {
      if (schedule === scrollSchedule && !disposed && scrollId.value === scroller) scroller.scrollTo?.({ top: scroller.scrollHeight })
    }
    if (!waitForLayout) {
      scroll()
      return
    }
    requestAnimationFrame(() => requestAnimationFrame(scroll))
  })
}
// 页面在 KeepAlive 里：切走时滚动容器被重置到顶部，回来时只重新定位到最新一条，不重新请求、不改任何状态。
onActivated(() => scrollToBottom(true))


interface LiveStage {
  name: StageName
  status: 'pending' | 'running' | 'done' | 'failed' | 'awaiting'
  // Summed over segments when the stage runs in segments.
  ms?: number | undefined
  score?: number | undefined
  subject?: string | undefined
  segment?: StageSegment & { done: boolean } | undefined
}

// 步骤状态由右侧元信息表达，标题只说做什么；服务端给出 subject 时按实际对象命名。
const STAGE_LABELS: Record<StageName, (subject: string | undefined) => string> = {
  route: () => '理解输入',
  locate: () => '定位客户',
  context: () => '读取客户记录',
  judge: () => '比对未完成任务',
  propose: () => '生成后续建议',
  classify: () => '判断活动类型',
  structure: (subject) => `整理${subject ?? '活动内容'}`,
  quality_gate: () => '评估记录质量',
  write: (subject) => (subject === undefined ? '写入客户活动' : `保存${subject}`)
}
// 耗时取整秒；分段整理会超过一分钟，所以超过后显示到分。
const formatDuration = (ms: number): string => {
  const seconds = Math.max(1, Math.round(ms / 1000))
  if (seconds < 60) return `${seconds} 秒`
  return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`
}

type EpisodeSettlement = 'none' | 'failed' | 'unknown'
const processing = ref<{
  active: boolean
  stages: LiveStage[]
  startedAt: number
  episode: number
  baselineIds: string[]
  authoritativeWrite: boolean
  settlement: EpisodeSettlement
}>({
  active: false,
  stages: [],
  startedAt: 0,
  episode: 0,
  baselineIds: [],
  authoritativeWrite: false,
  settlement: 'none'
})
const serverMessageIds = (): string[] => entries.value.flatMap((entry) =>
  entry.serverId !== undefined && !entry.serverId.startsWith('current:') ? [entry.serverId] : [])
const startEpisode = (): void => {
  processing.value.episode += 1
  processing.value.baselineIds = serverMessageIds()
  processing.value.authoritativeWrite = false
  processing.value.settlement = 'none'
}
const resetProcessingEpisode = (): void => {
  processing.value.episode = 0
  processing.value.baselineIds = []
  processing.value.authoritativeWrite = false
  processing.value.settlement = 'none'
  processing.value.stages = []
}
const noteEpisodeFailure = (code: string | undefined): void => {
  if (processing.value.episode === 0 || processing.value.authoritativeWrite) return
  processing.value.settlement = code === 'UNKNOWN_COMMIT_RESULT' ? 'unknown' : 'failed'
}

const beginProcessing = (): void => {
  startEpisode()
  processing.value.active = true
  processing.value.stages = []
  processing.value.startedAt = Date.now()
}
const applyStageEvent = (event: StageEvent): void => {
  if (event.phase !== 'start' && event.phase !== 'done' && event.phase !== 'failed') return
  const stages = processing.value.stages
  let target = stages.find((item) => item.name === event.stage)
  if (target === undefined) {
    target = { name: event.stage, status: 'pending' }
    stages.push(target)
  }
  if (event.subject !== undefined) target.subject = event.subject
  const segment = event.segment
  if (event.phase === 'start') {
    target.status = 'running'
    if (segment === undefined || segment.index === 1) target.ms = undefined
    target.score = undefined
    target.segment = segment === undefined ? undefined : { ...segment, done: false }
  } else if (event.phase === 'failed') {
    target.status = 'failed'
    target.segment = segment === undefined ? undefined : { ...segment, done: false }
  } else if (segment === undefined) {
    target.status = 'done'
    target.ms = event.ms
    target.score = event.score
    target.segment = undefined
  } else {
    // A finished segment before the last keeps the stage running.
    target.status = segment.index < segment.total ? 'running' : 'done'
    target.ms = (target.ms ?? 0) + (event.ms ?? 0)
    target.score = event.score
    target.segment = { ...segment, done: true }
  }
}
// Without a server-attributed stage, the stage still running is the one that stopped.
const markStageFailed = (stage: StageName | undefined): void => {
  for (const item of processing.value.stages) {
    if (stage === undefined ? item.status === 'running' : item.name === stage && item.status !== 'done') item.status = 'failed'
  }
}
const markRunningStagesAwaiting = (): void => {
  for (const stage of processing.value.stages) {
    if (stage.status === 'running') stage.status = 'awaiting'
  }
  processing.value.active = false
}

const endProcessing = (): void => {
  // Keep stages. This also runs while recovery is still reading the turn.
  processing.value.active = false
}
const processingHint = computed(() => {
  if (!processing.value.active) return ''
  return '内容已保存，可以离开本页，完成后会通知你。'
})
const pendingRequest = shallowRef<{ input: SubmitAssistantInput; targetId: string; displayText: string; turnId: string; cursor: number } | null>(null)
const processingRecovery = shallowRef<{ targetId: string; turnId: string; cursor: number } | null>(null)
const reprocessTarget = shallowRef<{ targetId: string; turnId: string; cursor: number } | null>(null)
const unknownResult = shallowRef<{ targetId: string; turnId: string; cursor: number; version: number; waiting: TaskWaiting | null } | null>(null)
// The bare conversation pending bit cannot identify or replace a fenced turn.
const suppressConversationResume = ref(false)
const canResumeConversation = computed(() => !suppressConversationResume.value && conversation.value?.has_pending_request === true)
const reconciliationRequired = computed(() => task.value?.status === 'ACTIVE'
  && (task.value.reconciliation_required === true || unknownResult.value !== null))
const recoveryNotice = ref('')
const autoRecovering = ref(false)
const reprocessAllowed = ref(false)

const captureUnknownResult = (targetId: string, turnId: string, cursor: number, snapshot = task.value): void => {
  if (task.value?.public_id !== targetId || task.value.status !== 'ACTIVE' || snapshot?.public_id !== targetId) return
  const previous = unknownResult.value
  if (previous?.targetId !== targetId) {
    unknownResult.value = { targetId, turnId, cursor, version: snapshot.version, waiting: task.value.waiting ?? snapshot.waiting ?? null }
  } else if (previous.turnId === '' && turnId !== '') {
    previous.turnId = turnId
    previous.cursor = cursor
    previous.version = Math.max(previous.version, snapshot.version)
  } else if (previous.turnId === turnId) {
    previous.version = Math.max(previous.version, snapshot.version)
    previous.cursor = Math.max(previous.cursor, cursor)
  }
  suppressConversationResume.value = true
  reprocessAllowed.value = false
  reprocessTarget.value = null
}

const reconcileUnknownResult = (updated: AssistantTaskView | null): void => {
  const unresolved = unknownResult.value
  if (unresolved !== null && (updated?.public_id !== unresolved.targetId || updated.status !== 'ACTIVE')) {
    unknownResult.value = null
  }
  if (updated?.status !== 'ACTIVE') return
  if (updated.reconciliation_required === true) {
    if (unknownResult.value === null) captureUnknownResult(updated.public_id, updated.processing_turn_id ?? '', 0, updated)
    else unknownResult.value.version = Math.max(unknownResult.value.version, updated.version)
    return
  }
  if (unresolved === null || updated.public_id !== unresolved.targetId) return
  const wait = updated.waiting
  if (updated.version > unresolved.version && updated.reconciliation_required === false
    && typeof wait?.action_id === 'string' && wait.action_id.trim() !== '' && wait.expected_version === updated.version
    && unresolved.waiting?.action_id !== wait.action_id) {
    if (pendingRequest.value?.targetId === updated.public_id) pendingRequest.value = null
    if (processingRecovery.value === null) resultPending.value = false
    unknownResult.value = null
  }
}
const processingInFlight = computed(() => processing.value.active || autoRecovering.value || processingRecovery.value !== null)
const showProcessCard = computed(() => processing.value.stages.length > 0
  && !(processing.value.authoritativeWrite && !processingInFlight.value))
const processChipStatus = computed((): 'processing' | 'updated' | null => {
  if (!showProcessCard.value) return null
  if (processingInFlight.value) return 'processing'
  if (processing.value.settlement === 'failed' || processing.value.settlement === 'unknown') return null
  return 'updated'
})
const seenEventKeys = new Set<string>()
// Polls without new progress; matches the server attempt deadline (180 s), after which a dead turn is closed on read.
const RECOVERY_POLLS = 180
let recoveryTimer: ReturnType<typeof setTimeout> | null = null
let recoveryToken = 0
let recoveryStarted = false

const stopAutoRecovery = (): void => {
  autoRecovering.value = false
  if (recoveryTimer !== null) {
    clearTimeout(recoveryTimer)
    recoveryTimer = null
  }
}

const logRecovery = (action: string, data: Record<string, unknown>): void => {
  void import('@/utils/logger').then(({ logger }) => {
    logger.info('[SalesAssistant]', action, data)
  }).catch(() => undefined)
}

onUnmounted(() => { recoveryToken += 1; stopAutoRecovery() })

const adoptProcessingTurn = (updated: AssistantTaskView): void => {
  if (updated.processing_turn_id != null && (updated.processing_turn_status === 'PENDING' || updated.processing_turn_status === 'RUNNING')) {
    const recovery = processingRecovery.value
    if (recovery === null || recovery.turnId !== updated.processing_turn_id || recovery.targetId !== updated.public_id) {
      processingRecovery.value = {
        targetId: updated.public_id,
        turnId: updated.processing_turn_id,
        cursor: 0
      }
    }
    resultPending.value = true
  } else if (processingRecovery.value?.targetId === updated.public_id) {
    processingRecovery.value = null
    resultPending.value = false
  }
  if (updated.reprocess_turn_id != null && updated.reprocess_turn_id !== '' && !reconciliationRequired.value) {
    reprocessAllowed.value = true
    const current = reprocessTarget.value
    reprocessTarget.value = {
      targetId: updated.public_id,
      turnId: updated.reprocess_turn_id,
      cursor: current?.turnId === updated.reprocess_turn_id ? current.cursor : 0
    }
  } else {
    reprocessAllowed.value = false
    reprocessTarget.value = null
  }
}

const resultPending = ref(false)

const rememberEvent = (turnId: string, seq: number | undefined): boolean => {
  if (turnId === '' || seq === undefined) return true
  const key = `${turnId}:${seq}`
  if (seenEventKeys.has(key)) return false
  seenEventKeys.add(key)
  return true
}

const applyTurnEvents = (turnId: string, events: AssistantTurn['events'], snapshot: AssistantTaskView): string | undefined => {
  let reply: string | undefined
  for (const event of events) {
    if (!rememberEvent(turnId, event.seq)) continue
    if (event.event === 'stage') {
      const stageEvent = parseStageEvent(event.data)
      if (stageEvent !== null) applyStageEvent(stageEvent)
    } else if (event.event === 'waiting' && typeof event.data['message'] === 'string') {
      reply = event.data['message']
    } else if (event.event === 'error') {
      const stage = StageNameSchema.safeParse(event.data['stage'])
      markStageFailed(stage.success ? stage.data : undefined)
      pushEntry('assistant', typeof event.data['message'] === 'string' ? event.data['message'] : '处理失败')
      const entry = entries.value[entries.value.length - 1]
      if (entry !== undefined) entry.outcome = 'failure'
      const code = typeof event.data['code'] === 'string' ? event.data['code'] : undefined
      noteEpisodeFailure(code)
      if (code === 'UNKNOWN_COMMIT_RESULT') captureUnknownResult(snapshot.public_id, turnId, event.seq, snapshot)
      processing.value.active = false
    }
  }
  return reply
}

const readKnownTurn = async (pending: { targetId: string; turnId: string; cursor: number }): Promise<boolean> => {
  const navigation = navigationVersion
  const token = recoveryToken
  const previouslyFocused = task.value
  const turn = await assistantApi.getTurn(pending.targetId, pending.turnId, pending.cursor)
  if (disposed || navigation !== navigationVersion || token !== recoveryToken || task.value?.public_id !== pending.targetId
    || turn.turn_id !== pending.turnId || turn.task.public_id !== pending.targetId) return true
  const focused = task.value
  if (focused === null || turn.task.version < focused.version || (focused !== previouslyFocused && turn.task.version === focused.version)) {
    return processingRecovery.value?.turnId !== pending.turnId
  }
  if (focused.processing_turn_id != null && focused.processing_turn_id !== pending.turnId) return true
  if (processing.value.episode === 0) startEpisode()
  const seqs = turn.events.map((event) => event.seq)
  if (seqs.length > 0) pending.cursor = Math.max(pending.cursor, ...seqs)
  const reply = applyTurnEvents(pending.turnId, turn.events, turn.task)
  publishTask(turn.task, reply, turn.status === 'SUCCEEDED' && !turn.events.some((event) => event.event === 'error'))
  if (turn.reprocess_allowed && !reconciliationRequired.value && turn.task.reprocess_turn_id === pending.turnId) {
    reprocessAllowed.value = true
    reprocessTarget.value = { targetId: pending.targetId, turnId: pending.turnId, cursor: pending.cursor }
  } else if (reconciliationRequired.value) {
    reprocessAllowed.value = false
    reprocessTarget.value = null
  }
  if (turn.status === 'SUCCEEDED' || turn.status === 'FAILED') {
    const successor = processingRecovery.value !== null && processingRecovery.value.turnId !== pending.turnId
      ? processingRecovery.value
      : null
    if (successor === null) {
      processingRecovery.value = null
      resultPending.value = false
      recoveryNotice.value = ''
      stopAutoRecovery()
      if (pendingRequest.value?.targetId === pending.targetId && pendingRequest.value.turnId === pending.turnId) pendingRequest.value = null
    }
    logRecovery(turn.status === 'SUCCEEDED' ? 'recovery_success' : 'recovery_terminal', {
      task: pending.targetId, turn_id: pending.turnId, last_seq: pending.cursor, event_name: turn.status
    })
    return true
  }
  resultPending.value = true
  return false
}

const scheduleRecovery = (pending: { targetId: string; turnId: string; cursor: number }, pollsLeft: number): void => {
  const token = recoveryToken
  autoRecovering.value = true
  recoveryTimer = setTimeout(() => {
    void (async (): Promise<void> => {
      if (disposed || token !== recoveryToken || processingRecovery.value?.turnId !== pending.turnId) return
      try {
        const cursorBefore = pending.cursor
        const done = await readKnownTurn(pending)
        // Any new event is progress: a long segmented turn keeps polling while it advances.
        const nextPolls = pending.cursor > cursorBefore ? RECOVERY_POLLS : pollsLeft - 1
        if (token === recoveryToken) await refreshConversation()
        if (disposed || token !== recoveryToken) return
        const successor = processingRecovery.value
        if (successor === null) {
          stopAutoRecovery()
          return
        }
        if (successor.turnId !== pending.turnId) {
          await startAutoRecovery(successor, '已受理，正在确认处理结果')
          return
        }
        if (done) return
        if (nextPolls <= 0) {
          stopAutoRecovery()
          recoveryNotice.value = '处理结果待确认，请刷新状态。'
          markRunningStagesAwaiting()
          resultPending.value = true
          logRecovery('recovery_timeout', { task: pending.targetId, turn_id: pending.turnId, last_seq: pending.cursor, event_name: 'timeout' })
          return
        }
        scheduleRecovery(pending, nextPolls)
      } catch (error) {
        if (disposed || token !== recoveryToken) return
        if (!(error instanceof ZodError) && pollsLeft > 1) {
          scheduleRecovery(pending, pollsLeft - 1)
          return
        }
        stopAutoRecovery()
        recoveryNotice.value = '处理结果待确认，请刷新状态。'
        markRunningStagesAwaiting()
        resultPending.value = true
        pushEntry('assistant', '处理结果暂时无法显示，请点刷新状态。')
        logRecovery(error instanceof ZodError ? 'recovery_parse_failed' : 'recovery_read_failed', {
          task: pending.targetId, turn_id: pending.turnId, last_seq: pending.cursor, event_name: 'turn'
        })
      }
    })()
  }, 1000)
}

const startAutoRecovery = async (
  pending: { targetId: string; turnId: string; cursor: number },
  notice: string
): Promise<void> => {
  recoveryStarted = true
  recoveryToken += 1
  stopAutoRecovery()
  processingRecovery.value = pending
  recoveryNotice.value = notice
  resultPending.value = true
  autoRecovering.value = true
  const token = recoveryToken
  try {
    const done = await readKnownTurn(pending)
    if (token !== recoveryToken || disposed) return
    await refreshConversation()
    if (token !== recoveryToken || disposed) return
    const successor = processingRecovery.value
    if (successor !== null && successor.turnId !== pending.turnId) {
      await startAutoRecovery(successor, notice)
      return
    }
    if (!done && successor?.turnId === pending.turnId) scheduleRecovery(pending, RECOVERY_POLLS)
    else stopAutoRecovery()
  } catch (error) {
    if (token !== recoveryToken || disposed) return
    stopAutoRecovery()
    recoveryNotice.value = ''
    resultPending.value = true
    pushEntry('assistant', '处理结果暂时无法显示，请点刷新状态。')
    logRecovery(error instanceof ZodError ? 'recovery_parse_failed' : 'recovery_read_failed', {
      task: pending.targetId, turn_id: pending.turnId, last_seq: pending.cursor, event_name: 'turn'
    })
  }
}

const recoverProcessingTurn = async (): Promise<void> => {
  const pending = processingRecovery.value
  if (pending === null) return
  await startAutoRecovery(pending, '已受理，正在确认处理结果')
}


const publishTask = (updated: AssistantTaskView, message?: string, allowCompletion = true): void => {
  if (disposed || updated === undefined || (task.value !== null && task.value.public_id !== updated.public_id)) return
  if (task.value !== null && updated.version < task.value.version) return
  const previous = task.value
  const hadActivity = previous?.committed.some((receipt) => receipt.kind === 'customer_activity') ?? false
  const activityWritten = !hadActivity && updated.committed.some((receipt) => receipt.kind === 'customer_activity')
  const dispositionChanged = updated.status === 'COMPLETED' && updated.follow_up_disposition != null
    && JSON.stringify(updated.follow_up_disposition) !== JSON.stringify(previous?.follow_up_disposition)
  const proposalUnavailable = updated.proposal_outcome != null
  const completed = allowCompletion && updated.status === 'COMPLETED' && updated.waiting == null
    && !proposalUnavailable
    && updated.processing_turn_status !== 'FAILED' && conversation.value?.pending_choice == null
  task.value = updated
  reconcileUnknownResult(updated)
  adoptProcessingTurn(updated)
  const prompt = updated.waiting?.prompt ?? ''
  const reply = message ?? prompt
  if (proposalUnavailable) {
    // The conversation read model owns the warning envelope, including on recovery.
    void refreshConversation()
  } else if (reply !== '' && (!completed || activityWritten || dispositionChanged)) {
    pushEntry('assistant', reply, updated.waiting ?? null)
    const entry = entries.value[entries.value.length - 1]
    if (entry !== undefined && entry.waiting === null) {
      if (dispositionChanged) entry.outcome = 'follow_up_disposition'
      else if (activityWritten) entry.outcome = 'activity_written'
    }
  }
  if (completed && !entries.value.some((entry) => entry.outcome === 'task_completed' && entry.ownTask?.public_id === updated.public_id)) {
    pushEntry('assistant', '本次任务已完成')
    const entry = entries.value[entries.value.length - 1]
    if (entry !== undefined) {
      entry.serverId = `current:completion:${updated.public_id}`
      entry.outcome = 'task_completed'
    }
  }
  emit('task-updated', updated, reply)
  recomputeProjectionCoverage()
}
const runPrepared = async (prepared: NonNullable<ConversationReply['submission']>, displayText: string): Promise<void> => {
  const navigation = navigationVersion
  const targetId = prepared.task_public_id
  if (disposed || reconciliationRequired.value || task.value?.public_id !== targetId || task.value.status !== 'ACTIVE'
    || (task.value.processing_turn_id != null && task.value.processing_turn_id !== prepared.turn_id)) return
  const request: SubmitAssistantInput = {
    kind: prepared.input.kind, text: prepared.input.text ?? undefined, choice: prepared.input.choice ?? undefined,
    client_request_id: prepared.input.client_request_id, action_id: prepared.input.action_id ?? undefined,
    expected_version: prepared.input.expected_version ?? undefined,
    ...(prepared.input.values != null ? { values: prepared.input.values } : {}),
    ...(prepared.input.form_revision != null ? { form_revision: prepared.input.form_revision } : {}),
    ...(prepared.input.choices != null ? { choices: prepared.input.choices } : {}),
    ...(prepared.input.suppress_week != null ? { suppress_week: prepared.input.suppress_week } : {}),
    ...(prepared.input.reason != null ? { reason: prepared.input.reason } : {})
  }
  submitting.value = true
  processingRecovery.value = null
  recoveryStarted = false
  try {
    resultPending.value = false
    const pending = { input: request, targetId, displayText, turnId: prepared.turn_id, cursor: 0 }
    pendingRequest.value = pending
    beginProcessing()
    const active = (): boolean => !disposed && navigation === navigationVersion && pendingRequest.value === pending
    const acceptsStreamEvent = (): boolean => active() && task.value?.public_id === targetId && task.value.status === 'ACTIVE'
      && (task.value.processing_turn_id == null || task.value.processing_turn_id === prepared.turn_id)
    let turnId = prepared.turn_id
    let cursor = 0
    let delivered = false
    let disconnected = false
    let failed = false
    let terminalInvalid = false
    await submitInputStream(targetId, request, {
      onAccepted: (id, seq) => {
        if (!acceptsStreamEvent() || id !== prepared.turn_id) return
        turnId = id
        cursor = Math.max(cursor, seq ?? 0)
        rememberEvent(id, seq)
        if (pendingRequest.value !== null) { pendingRequest.value.turnId = id; pendingRequest.value.cursor = cursor }
      },
      onStage: (event) => {
        if (!acceptsStreamEvent()) return
        cursor = Math.max(cursor, event.seq ?? 0)
        rememberEvent(turnId, event.seq)
        if (pendingRequest.value !== null) pendingRequest.value.cursor = cursor
        applyStageEvent(event)
      },
      onWaiting: (data) => {
        if (!acceptsStreamEvent()) return
        delivered = true
        cursor = Math.max(cursor, data.seq ?? 0)
        publishTask(data.task, data.message, !failed)
      },
      onError: (event) => {
        if (!acceptsStreamEvent()) return
        delivered = true
        failed = true
        cursor = Math.max(cursor, event.seq ?? 0)
        markStageFailed(event.stage)
        pushEntry('assistant', event.message)
        const entry = entries.value[entries.value.length - 1]
        if (entry !== undefined) entry.outcome = 'failure'
        noteEpisodeFailure(event.code)
        processing.value.active = false
        if (event.code === 'UNKNOWN_COMMIT_RESULT') {
          rememberEvent(turnId, event.seq)
          captureUnknownResult(targetId, turnId, cursor)
        }
      },
      onNetworkLost: () => { if (active()) disconnected = true },
      onTerminalInvalid: () => { if (active()) terminalInvalid = true }
    })
    if (!active()) return
    if (!delivered && !disconnected && turnId !== '') {
      try {
        const previouslyFocused = task.value
        const turn = await assistantApi.getTurn(targetId, turnId, cursor)
        if (!active()) return
        const focused = task.value
        if (focused !== null && turn.turn_id === turnId && turn.task.public_id === targetId
          && (focused.processing_turn_id == null || focused.processing_turn_id === turnId)
          && (turn.task.version > focused.version || (focused === previouslyFocused && turn.task.version === focused.version))) {
          cursor = Math.max(cursor, ...turn.events.map((event) => event.seq))
          applyTurnEvents(turnId, turn.events, turn.task)
          if (turn.status === 'SUCCEEDED' || turn.status === 'FAILED') {
            publishTask(turn.task, undefined, turn.status === 'SUCCEEDED' && !turn.events.some((event) => event.event === 'error'))
            delivered = true
          }
        }
      } catch {
        // Fall through to durable GET recovery.
      }
    }
    if (!active()) return
    if ((disconnected || !delivered) && turnId !== '') {
      pending.cursor = cursor
      const notice = terminalInvalid ? '处理结果暂时无法显示，正在重新读取。' : '已受理，正在确认处理结果'
      await startAutoRecovery(processingRecovery.value ?? pending, notice)
    } else if (disconnected || !delivered) {
      resultPending.value = true
      try {
        const latest = await assistantApi.getTask(targetId)
        if (!active()) return
        if (latest.public_id !== targetId) return
        publishTask(latest)
        if (processingRecovery.value !== null) await startAutoRecovery(processingRecovery.value, '已受理，正在确认处理结果')
      } catch {
        if (active()) resultPending.value = true
      }
    }
    if (!active()) return
    if (!resultPending.value) pendingRequest.value = null
    await refreshConversation()
  } catch {
    if (disposed || navigation !== navigationVersion) return
    // The turn was already accepted; read it back instead of surfacing transport errors.
    resultPending.value = true
    processingRecovery.value ??= { targetId, turnId: prepared.turn_id, cursor: 0 }
  } finally {
    if (navigation === navigationVersion) {
      endProcessing()
      submitting.value = false
      if (!recoveryStarted && processingRecovery.value !== null && !autoRecovering.value) await recoverProcessingTurn()
    }
  }
}

const submitText = async (): Promise<void> => {
  const text = inputText.value.trim()
  if (!text || loadingConversation.value || busy.value || conversation.value === null || conversation.value.pending_choice !== null) return
  sendingText.value = true
  try {
    if (explicitNone.value && waiting.value?.type === 'FIELD' && waiting.value.field === 'next_action') {
      explicitNone.value = false
      await submit({ kind: 'submit_field', choice: 'EXPLICITLY_NONE', text }, text, waiting.value)
      return
    }
    explicitNone.value = false
    unacceptedText.value = text
    const fingerprint = `text:${text}`
    const request = { text, client_request_id: requestKey(fingerprint), expected_version: conversation.value.version }
    pushEntry('user', text)
    inputText.value = ''
    await dispatchConversation(() => assistantApi.conversationText(request), text, {
      key: request.client_request_id, fingerprint, cardNotice: false, onNotSaved: restoreUnacceptedText
    })
  } finally {
    sendingText.value = false
  }
}

const clearCardNotice = (key: string): void => {
  if (interactionNotices.value[key] === undefined) return
  const next: Record<string, InteractionNotice> = {}
  for (const [entryKey, notice] of Object.entries(interactionNotices.value)) {
    if (entryKey !== key) next[entryKey] = notice
  }
  interactionNotices.value = next
}

const cardNoticeKey = (source: TaskWaiting | null): string | null => (
  source?.type === 'ACTIVITY_KIND' && typeof source.action_id === 'string' ? source.action_id : null
)

const isSameWait = (source: TaskWaiting, current?: TaskWaiting | null): boolean =>
  current != null && source.type === current.type && source.question_id === current.question_id
  && source.action_id === current.action_id && source.expected_version === current.expected_version
  && source.field === current.field && source.form_revision === current.form_revision

const submit = async (
  input: SubmitAssistantInput,
  displayText: string,
  source: TaskWaiting | null = null,
  reuseClientRequestId: string | null = null
): Promise<boolean> => {
  if (busy.value || task.value === null || conversation.value === null) return false
  if (source !== null && !isSameWait(source, task.value.waiting)) return false
  const actionId = source?.action_id ?? null
  const fingerprint = `command:${task.value.public_id}:${actionId ?? ''}:${JSON.stringify(input)}`
  const clientRequestId = reuseClientRequestId ?? requestKey(fingerprint)
  const choice = typeof input.choice === 'string' ? input.choice : null
  const noticeKey = choice === null ? null : cardNoticeKey(source)
  const payload: SubmitAssistantInput = { ...input, client_request_id: clientRequestId,
    action_id: source?.action_id ?? undefined, expected_version: source?.expected_version ?? undefined }
  const request = { task_public_id: task.value.public_id, input: payload, expected_version: conversation.value.version }
  if (noticeKey !== null) clearCardNotice(noticeKey)
  pushEntry('user', displayText)
  inputText.value = ''
  const onNotSaved = (): void => {
    releaseAction(actionId)
    // The card cannot show this itself: the server confirmed the choice was never saved.
    if (noticeKey !== null && choice !== null) interactionNotices.value[noticeKey] = { kind: 'failed', choice, clientRequestId }
  }
  const dispatched = await dispatchConversation(() => assistantApi.conversationCommand(request), displayText, {
    key: clientRequestId, fingerprint, cardNotice: noticeKey !== null && choice !== null, onNotSaved,
    onAccepted: () => { releaseAction(actionId) }
  })
  const outcome = dispatched.outcome
  // An unconfirmed send keeps its card held until 「查看结果」 settles it.
  if (outcome !== 'unconfirmed') releaseAction(actionId)
  if (noticeKey !== null && choice !== null) {
    // The card was already handled elsewhere. An out-of-range choice is not stale.
    if (outcome === 'conflict') {
      if (historyError.value === SESSION_UPDATED_MESSAGE) historyError.value = ''
      interactionNotices.value[noticeKey] = dispatched.detail.includes(OUT_OF_RANGE_KIND)
        ? { kind: 'invalid' }
        : { kind: 'expired' }
    }
  }
  return true
}

const retryRootFailure = async (entry: ChatEntry, actionId: string): Promise<void> => {
  if (submitting.value || resultPending.value || reconciliationRequired.value || conversation.value === null) return
  if (entry.role !== 'assistant' || entry.serverId === undefined || !entry.serverId.endsWith(':reply')) return
  const entryId = entry.serverId.slice(0, -':reply'.length)
  if (actionId !== `retry:${entryId}`) return
  const message = conversation.value.messages.find((item) => item.id === entry.serverId)
  const action = message?.ui?.suggested_actions.find((item) => item.action_id === actionId)
  if (action === undefined || action.type !== 'retry') return
  const navigation = navigationVersion
  const requestOrder = ++viewRequestSequence
  submitting.value = true
  routing.value = true
  try {
    const response = await assistantApi.retryConversationEntry(entryId, conversation.value.version)
    if (disposed || navigation !== navigationVersion || !applyConversation(response.conversation, false, requestOrder)) return
    routing.value = false
    if (response.submission !== null) await runPrepared(response.submission, '')
    else resultPending.value = false
  } catch (error) {
    if (disposed || navigation !== navigationVersion) return
    if (isAxiosError(error) && error.response?.status === 409) {
      resultPending.value = false
      await refreshConversation()
      if (disposed || navigation !== navigationVersion) return
      if (historyError.value === '') {
        historyError.value = SESSION_UPDATED_MESSAGE
      }
      return
    }
    await refreshConversation()
    if (disposed || navigation !== navigationVersion) return
    resultPending.value = canResumeConversation.value && !reconciliationRequired.value
  } finally {
    if (!disposed && navigation === navigationVersion) { routing.value = false; submitting.value = false }
  }
}

const restoreUnacceptedText = (): void => {
  if (unacceptedText.value !== '') inputText.value = unacceptedText.value
  unacceptedText.value = ''
}

/** One read of what the server knows about the lost send; null means ask again later. */
const readLostSend = async (lost: LostSend): Promise<CommandOutcome | null> => {
  const order = ++viewRequestSequence
  let status: ConversationRequestStatus
  try {
    status = await assistantApi.conversationRequestStatus(lost.key)
  } catch {
    return null
  }
  if (disposed || lostSend.value?.key !== lost.key) return 'explicit'
  if (status.state === 'none' || status.state === 'not_saved') {
    lostSend.value = { ...lost, phase: 'not_saved' }
    resultPending.value = false
    applyConversation(status.conversation, false, order)
    lost.onNotSaved()
    return 'not_saved'
  }
  applyConversation(status.conversation, false, order)
  // Still routing with no turn to follow yet: keep asking.
  if (status.state === 'running' && processingRecovery.value === null) return null
  lostSend.value = null
  lost.onAccepted?.()
  if (processingRecovery.value !== null) void recoverProcessingTurn()
  else if (!canResumeConversation.value) resultPending.value = false
  return 'accepted'
}

const confirmLostSend = async (lost: LostSend): Promise<CommandOutcome> => {
  for (const delay of LOST_SEND_DELAYS_MS) {
    await new Promise<void>((resolve) => { window.setTimeout(resolve, delay) })
    if (disposed || lostSend.value?.key !== lost.key) return 'explicit'
    const settled = await readLostSend(lost)
    if (settled !== null) return settled
  }
  if (disposed || lostSend.value?.key !== lost.key) return 'explicit'
  lostSend.value = { ...lost, phase: 'unconfirmed' }
  return 'unconfirmed'
}

/** 「查看结果」: ask once more; never resend. */
const checkLostSend = async (): Promise<void> => {
  const lost = lostSend.value
  if (lost === null || lost.phase !== 'unconfirmed' || submitting.value) return
  submitting.value = true
  const checking: LostSend = { ...lost, phase: 'checking' }
  lostSend.value = checking
  try {
    const settled = await readLostSend(checking)
    if (settled === null && lostSend.value?.key === lost.key) lostSend.value = { ...lost, phase: 'unconfirmed' }
  } finally {
    if (!disposed) submitting.value = false
  }
}

const dispatchConversation = async (
  send: () => Promise<ConversationReply>,
  displayText: string,
  keyed: KeyedSend | null = null
): Promise<CommandDispatch> => {
  if (disposed || submitting.value || reconciliationRequired.value || lostSendBlocking.value) return { outcome: 'explicit', detail: '' }
  const navigation = navigationVersion
  const requestOrder = ++viewRequestSequence
  submitting.value = true
  routing.value = true
  lostSend.value = null
  try {
    const response = await send()
    if (disposed || navigation !== navigationVersion) return { outcome: 'accepted', detail: '' }
    unacceptedText.value = ''
    if (!applyConversation(response.conversation, false, requestOrder)) return { outcome: 'explicit', detail: '' }
    routing.value = false
    if (response.submission !== null) {
      if (reconciliationRequired.value) return { outcome: 'accepted', detail: '' }
      await runPrepared(response.submission, displayText)
    } else if (processingRecovery.value === null) resultPending.value = false
    return { outcome: 'accepted', detail: '' }
  } catch (error) {
    if (disposed || navigation !== navigationVersion || reconciliationRequired.value) return { outcome: 'explicit', detail: '' }
    const failure = explicitCommandFailure(error)
    if (failure !== null) {
      // A rejected command must not stay replayable or look still in progress.
      resultPending.value = false
      if (failure === 'conflict') {
        await refreshConversation()
        if (disposed || navigation !== navigationVersion) return { outcome: 'conflict', detail: conflictDetail(error) }
        if (conversation.value?.has_pending_request !== true) restoreUnacceptedText()
        historyError.value = SESSION_UPDATED_MESSAGE
      } else {
        restoreUnacceptedText()
        historyError.value = failure === 'auth' ? LOGIN_EXPIRED_MESSAGE : REJECTED_SUBMIT_MESSAGE
      }
      return { outcome: failure === 'conflict' ? 'conflict' : 'explicit', detail: conflictDetail(error) }
    }
    if (keyed === null) {
      // Unkeyed sends (focus, resume) change nothing twice; just show the server's current view.
      await refreshConversation()
      return { outcome: 'explicit', detail: '' }
    }
    // Timeout or dropped connection: the server may or may not have saved it. Ask, never resend.
    const lost: LostSend = { ...keyed, phase: 'checking' }
    lostSend.value = lost
    routing.value = false
    return { outcome: await confirmLostSend(lost), detail: '' }
  } finally {
    if (!disposed && navigation === navigationVersion) { routing.value = false; submitting.value = false }
  }
}

const chooseBoundary = async (entry: ChatEntry, choice: 'CONTINUE' | 'NEW'): Promise<void> => {
  const boundary = entry.boundary
  if (!boundary || conversation.value?.pending_choice?.entry_id !== boundary.entry_id || busy.value) return
  const fingerprint = `choice:${boundary.entry_id}:${choice}`
  const request = { entry_id: boundary.entry_id, choice, expected_version: conversation.value.version, client_request_id: requestKey(fingerprint) }
  await dispatchConversation(() => assistantApi.conversationChoice(request), choice === 'CONTINUE' ? '接着刚才' : '另记一件', {
    key: request.client_request_id, fingerprint, cardNotice: false, onNotSaved: () => undefined
  })
}

const choiceLabel = (choice: string, source: TaskWaiting | null): string => {
  const candidate = source?.candidates?.find((item) => item.id === choice)
  if (candidate === undefined) return ACTIVITY_BADGES[choice] ?? '选择'
  return 'account_name' in candidate ? candidate.account_name : candidate.label
}

const pickKind = (choice: string, source: TaskWaiting | null, reuseClientRequestId: string | null = null): Promise<boolean> =>
  submit({ kind: 'submit_field', choice }, choiceLabel(choice, source), source, reuseClientRequestId)

const confirmWrite = (source: TaskWaiting | null): Promise<boolean> =>
  submit({ kind: 'confirm', choice: 'confirm' }, '确认', source)

const rejectWrite = (source: TaskWaiting | null, reason?: SubmitAssistantInput['reason']): Promise<boolean> =>
  submit({ kind: 'confirm', choice: 'reject', ...(reason === undefined ? {} : { reason }) }, '取消', source)

const requestEdit = (source: TaskWaiting | null): Promise<boolean> =>
  submit({ kind: 'request_edit' }, '修改活动内容', source)
const cancelTask = async (source: TaskWaiting | null = waiting.value): Promise<void> => {
  if (busy.value) return
  const pending = conversation.value?.pending_choice
  if (pending && conversation.value) {
    const fingerprint = `choice:${pending.entry_id}:CANCEL`
    const request = { entry_id: pending.entry_id, choice: 'CANCEL' as const, expected_version: conversation.value.version, client_request_id: requestKey(fingerprint) }
    await dispatchConversation(() => assistantApi.conversationChoice(request), '算了，不记了', {
      key: request.client_request_id, fingerprint, cardNotice: false, onNotSaved: () => undefined
    })
    return
  }
  await submit({ kind: 'cancel' }, '算了，不记了', source)
}

// 「待补充」: parked direct-create drafts other than the one on screen.
const pendingDrafts = ref<PendingEntityDraft[]>([])
const visiblePendingDrafts = computed(() => pendingDrafts.value.filter((draft) => draft.public_id !== task.value?.public_id))
let pendingDraftsRequest = 0
const loadPendingDrafts = async (): Promise<void> => {
  const order = ++pendingDraftsRequest
  try {
    const drafts = await assistantApi.pendingDrafts()
    if (!disposed && order === pendingDraftsRequest) pendingDrafts.value = drafts
  } catch {
    // The list is a shortcut; the conversation itself stays usable without it.
  }
}
watch(() => conversation.value?.version, (version) => { if (version !== undefined) void loadPendingDrafts() })

const openPendingDraft = async (draft: PendingEntityDraft): Promise<void> => {
  const view = conversation.value
  if (busy.value || view === null || view.pending_choice !== null) return
  await dispatchConversation(() => assistantApi.focusConversation(draft.public_id, view.version), draft.label)
}

// The server already holds this request (its original key); continuing cannot save it twice.
const showContinuePending = computed(() => !reconciliationRequired.value && resultPending.value && !autoRecovering.value
  && processingRecovery.value === null && lostSend.value === null && canResumeConversation.value)
const lostSendNotice = computed(() => {
  const lost = lostSend.value
  if (lost?.phase === 'unconfirmed') return UNCONFIRMED_MESSAGE
  return lost?.phase === 'not_saved' && !lost.cardNotice ? NOT_SAVED_MESSAGE : ''
})
const showSyncResult = computed(() => resultPending.value && !autoRecovering.value && !showContinuePending.value
  && (processingRecovery.value !== null || (pendingRequest.value?.turnId ?? '') !== ''))
const showReprocess = computed(() => !reconciliationRequired.value && reprocessAllowed.value && reprocessTarget.value !== null && !autoRecovering.value)
const showRefreshStatus = computed(() => {
  if (autoRecovering.value) return false
  if (reconciliationRequired.value || showSyncResult.value || showReprocess.value) return true
  const current = task.value
  if (current == null || current.status !== 'ACTIVE' || current.waiting != null) return false
  return entries.value.some((entry) => entry.outcome === 'failure')
})

const syncResult = async (): Promise<void> => {
  const unresolved = unknownResult.value
  const pending = (unresolved !== null && unresolved.turnId !== '' ? unresolved : null) ?? processingRecovery.value ?? pendingRequest.value
  if (submitting.value || (pending === null && !reconciliationRequired.value)) return
  const navigation = navigationVersion
  submitting.value = true
  recoveryToken += 1
  stopAutoRecovery()
  try {
    if (pending !== null) await readKnownTurn(pending)
    if (disposed || navigation !== navigationVersion) return
    await refreshConversation()
    const successor = processingRecovery.value
    if (navigation === navigationVersion && successor !== null) await recoverProcessingTurn()
  } catch {
    if (disposed || navigation !== navigationVersion) return
    resultPending.value = true
    pushEntry('assistant', '处理结果暂时无法显示，请点刷新状态。')
    if (reconciliationRequired.value) await refreshConversation()
  } finally {
    if (!disposed && navigation === navigationVersion) submitting.value = false
  }
}

const reprocessTurn = async (): Promise<void> => {
  const pending = reprocessTarget.value
  if (reconciliationRequired.value || pending === null || !reprocessAllowed.value || submitting.value) return
  const navigation = navigationVersion
  submitting.value = true
  recoveryToken += 1
  const token = recoveryToken
  stopAutoRecovery()
  try {
    const previouslyFocused = task.value
    const current = await assistantApi.getTurn(pending.targetId, pending.turnId, pending.cursor)
    if (disposed || navigation !== navigationVersion || token !== recoveryToken || task.value?.public_id !== pending.targetId
      || current.turn_id !== pending.turnId || current.task.public_id !== pending.targetId) return
    const focused = task.value
    if (focused === null || current.task.version < focused.version) return
    const priorCursor = Math.max(pending.cursor, ...current.events.map((event) => event.seq))
    if (focused !== previouslyFocused && current.task.version === focused.version) return
    const currentAuthority = focused.status === 'ACTIVE' && focused.reprocess_turn_id === pending.turnId
    const reportedUnknown = current.events.some((event) => event.event === 'error' && event.data['code'] === 'UNKNOWN_COMMIT_RESULT')
    const reply = applyTurnEvents(pending.turnId, current.events, current.task)
    publishTask(current.task, reply, current.status === 'SUCCEEDED' && !current.events.some((event) => event.event === 'error'))
    if (reportedUnknown || reconciliationRequired.value || current.reprocess_allowed !== true || current.task.reprocess_turn_id !== pending.turnId) {
      reprocessAllowed.value = false
      reprocessTarget.value = null
      return
    }
    if (!currentAuthority || disposed || navigation !== navigationVersion || token !== recoveryToken || reconciliationRequired.value
      || task.value?.public_id !== pending.targetId || task.value.reprocess_turn_id !== pending.turnId) return
    const preRetryTask = task.value
    const restarted = await assistantApi.retryTurn(pending.targetId, pending.turnId, current.lease_version, priorCursor)
    if (disposed || navigation !== navigationVersion || token !== recoveryToken || task.value?.public_id !== pending.targetId
      || restarted.turn_id !== pending.turnId || restarted.task.public_id !== pending.targetId) return
    const restartedFocus = task.value
    if (restartedFocus === null || restarted.task.version < restartedFocus.version
      || (restartedFocus !== preRetryTask && restarted.task.version === restartedFocus.version)) return
    resetProcessingEpisode()
    beginProcessing()
    const retry = { ...pending, cursor: Math.max(priorCursor, ...restarted.events.map((event) => event.seq)) }
    applyTurnEvents(pending.turnId, restarted.events.filter((event) => event.seq > priorCursor), restarted.task)
    publishTask(restarted.task, undefined, restarted.status === 'SUCCEEDED' && !restarted.events.some((event) => event.event === 'error'))
    if (restarted.status === 'PENDING' || restarted.status === 'RUNNING') {
      await startAutoRecovery(retry, '已受理，正在确认处理结果')
    }
  } catch {
    if (disposed || navigation !== navigationVersion) return
    resultPending.value = true
    pushEntry('assistant', '处理结果暂时无法显示，请点刷新状态。')
  } finally {
    if (!disposed && navigation === navigationVersion) submitting.value = false
  }
}

const retryPending = async (): Promise<void> => {
  if (unknownResult.value !== null) {
    await syncResult()
    return
  }
  if (reconciliationRequired.value) {
    await refreshConversation()
    return
  }
  if (submitting.value) return
  if (showContinuePending.value) {
    await dispatchConversation(() => assistantApi.resumeConversation(), '')
    return
  }
  await syncResult()
}

const explicitNone = ref(false)
const gapNone = (entry: ChatEntry): Promise<void> => {
  if (submitting.value || resultPending.value || !showExplicitNone(entry)) return Promise.resolve()
  explicitNone.value = true
  return Promise.resolve()
}

const busy = computed(() => submitting.value || resultPending.value || reconciliationRequired.value || lostSendBlocking.value)

const visibleEntries = computed(() => entries.value.filter((entry) => entry.projection?.visibility !== 'COVERED'))
const isSeparator = (entry: ChatEntry): boolean => entry.role === 'assistant' && entry.outcome === 'task_completed'
// 同一轮里连续的助手条目只在首条出头像；任务完成分隔线之后再出现的助手消息重新出头像。
const showsAvatar = (index: number): boolean => {
  const entry = visibleEntries.value[index]
  if (entry === undefined || entry.role !== 'assistant' || isSeparator(entry)) return false
  const previous = visibleEntries.value[index - 1]
  return previous === undefined || previous.role !== 'assistant' || isSeparator(previous)
}
// 轮次之间 24（$space-6）；同一轮里连续的助手条目之间 16（$space-4）。
const entrySpacing = (index: number): string => {
  const entry = visibleEntries.value[index]
  const previous = visibleEntries.value[index - 1]
  if (index === 0 || entry === undefined || previous === undefined) return ''
  return entry.role === 'assistant' && !isSeparator(entry) && previous.role === 'assistant' && !isSeparator(previous)
    ? 'mt-space-4'
    : 'mt-space-6'
}
// 等待待办卡片时输入框被禁用；用一行文字说明原因，不靠边框变色。
const cardLocked = computed(() => conversation.value?.pending_choice != null)
const historyErrorFeedback = computed<FeedbackError | null>(() => (
  historyError.value === '' ? null : { title: historyError.value, description: '' }
))
// 聊天里的实时阶段走同一个执行过程块：阶段映射成步骤，耗时与评分作为右侧元信息。
const liveProcess = computed<ProcessBlock | null>(() => {
  const stages = processing.value.stages
  if (stages.length === 0) return null
  return {
    id: 'live-process',
    type: 'process',
    title: '执行过程',
    items: stages.map((stage) => ({ key: stage.name, title: STAGE_LABELS[stage.name](stage.subject), status: LIVE_STAGE_STATUS[stage.status] })),
  }
})
const liveStageMeta = (stage: LiveStage): ProcessItemMeta => {
  const segment = stage.segment
  if (stage.status === 'done') {
    return { text: [
      segment === undefined ? '' : `已完成 ${segment.total}/${segment.total} 段`,
      stage.ms === undefined ? '' : formatDuration(stage.ms),
      stage.score === undefined ? '' : `${stage.score} 分`
    ].filter((part) => part !== '').join(' · ') }
  }
  if (stage.status === 'running') {
    if (segment === undefined) return { text: '进行中…' }
    return { text: segment.done ? `已完成 ${segment.index}/${segment.total} 段` : `第 ${segment.index}/${segment.total} 段 · 进行中…` }
  }
  if (stage.status === 'failed') return { text: segment === undefined ? '失败' : `第 ${segment.index}/${segment.total} 段失败`, tone: 'danger' }
  if (stage.status === 'awaiting') return { text: '待确认' }
  return { text: '' }
}
const liveStageMetaByKey = computed<Record<string, ProcessItemMeta>>(() => Object.fromEntries(
  processing.value.stages.map((stage) => [stage.name, liveStageMeta(stage)])
))
const liveProcessSummary = computed(() => `共 ${processing.value.stages.length} 步`)

const ACTIVITY_BADGES: Record<string, string> = {
  PHONE_FOLLOW_UP: '电话跟进',
  WECHAT_FOLLOW_UP: '微信跟进',
  EMAIL_FOLLOW_UP: '邮件跟进',
  VISIT_FOLLOW_UP: '拜访跟进',
  OTHER_FOLLOW_UP: '其他跟进',
  ONLINE_MEETING: '线上会议',
  OFFLINE_MEETING: '线下会议',
  FOLLOW_UP: '跟进',
}

const activityBadge = computed((): string => {
  const waiting = task.value?.waiting
  const preview = waiting?.confirmation_payload?.kind === 'activity_write'
    ? waiting.confirmation_payload.preview
    : null
  if (preview?.channel_status === 'required') return '待确认类型'
  const kind = preview?.activity_kind || (task.value?.activity_kind ?? '')
  return ACTIVITY_BADGES[kind] ?? ''
})

const interactionBlock = (entry: ChatEntry): Extract<NonNullable<ChatEntry['ui']>['blocks'][number], { type: 'interaction' }> | undefined =>
  entry.ui?.blocks.find((block): block is Extract<NonNullable<ChatEntry['ui']>['blocks'][number], { type: 'interaction' }> => block.type === 'interaction')

const onAssistantInteraction = (entry: ChatEntry, actionId: string, values: JsonObject): void => {
  const block = interactionBlock(entry)
  if (block?.state !== 'ACTIVE' || block.submit_action_id !== actionId || busy.value) return
  const choice = typeof values['choice'] === 'string' ? values['choice'] : ''
  if (block.business_action === 'assistant_boundary') {
    if (choice === 'CONTINUE' || choice === 'NEW') void chooseBoundary(entry, choice)
    return
  }
  const source = entry.waiting
  if (entry.replayed || source === null || task.value?.public_id !== entry.ownTask?.public_id
    || !isSameWait(source, task.value?.waiting)) return
  if (block.business_action === 'settle_follow_up_disposition') {
    const disposition = task.value?.follow_up_disposition
    if (source.type !== 'FOLLOW_UP_DISPOSITION' || disposition?.status !== 'ACTIVE' || disposition.settling === true) return
    const choices = values['choices']
    if (!Array.isArray(choices) || !choices.every((item): item is string => typeof item === 'string')) return
    const suppressWeek = values['suppress_week']
    if (suppressWeek !== undefined && typeof suppressWeek !== 'boolean') return
    void submit({ kind: 'submit_field', choices, ...(suppressWeek !== undefined ? { suppress_week: suppressWeek } : {}) },
      '提交跟进处理', source)
    return
  }
  if (block.secondary_action?.value === 'request_edit' && choice === 'request_edit') {
    void requestEdit(entry.waiting)
    return
  }
  if (choice === 'request_edit') return
  if (typeof values['revise_activity_kind'] === 'string') {
    void submit({ kind: 'revise_activity_kind', choice: values['revise_activity_kind'] }, '修改活动类型', entry.waiting)
    return
  }
  if (block.interaction_type === 'confirmation') {
    if (choice === 'confirm') {
      void confirmWrite(entry.waiting)
    } else if (choice === 'cancel') {
      const reason = AssistantRejectReasonSchema.safeParse(values['reason'])
      void rejectWrite(source, reason.success ? reason.data : undefined)
    }
    return
  }
  if (block.interaction_type === 'choice') {
    if (choice !== '') {
      const notice = interactionNotices.value[block.submit_action_id ?? block.interaction_id]
      const reuse = notice?.kind === 'failed' && notice.choice === choice ? notice.clientRequestId : null
      void pickKind(choice, entry.waiting, reuse)
      return
    }
    const typed = typeof values['text'] === 'string' ? values['text'].trim() : ''
    if (typed !== '') void submit({ kind: 'submit_field', text: typed }, typed, entry.waiting)
    return
  }
  if (block.interaction_type === 'text_input') {
    const answer = typeof values['text'] === 'string' ? values['text'].trim() : ''
    if (answer === '') return
    holdAction(actionId)
    void submit({ kind: 'submit_field', text: answer }, answer, entry.waiting).then((started) => {
      if (!started) releaseAction(actionId)
    })
    return
  }
  if (block.business_action === 'provide_follow_up_content' && values['cancel'] === true) {
    void submit({ kind: 'cancel' }, '取消', entry.waiting)
    return
  }
  if (source.type === 'ENTITY_FORM') {
    const formRevision = source.form_revision
    if (formRevision == null) return
    const onlyChoice = Object.keys(values).length === 1 && (choice === 'cancel' || choice === 'defer')
    void submit(onlyChoice
      ? { kind: 'submit_form', form_revision: formRevision, choice }
      : { kind: 'submit_form', form_revision: formRevision, values },
    onlyChoice ? (choice === 'cancel' ? '取消' : '稍后补充') : '提交', source)
    return
  }
  if (source.type === 'PROPOSAL_FORM' || source.type === 'CONFIRMATION_EDIT') {
    const formRevision = source.form_revision
    if (formRevision == null) return
    const canceled = choice === 'cancel' && Object.keys(values).length === 1
    const input: SubmitAssistantInput = { kind: 'submit_form', form_revision: formRevision }
    if (canceled) {
      input.choice = 'cancel'
    } else if (source.type === 'CONFIRMATION_EDIT') {
      const editValues = { ...values }
      // The coordinator accepts newline text and converts it to canonical participant lists.
      for (const key of ['internal_participants', 'customer_participants']) {
        const raw = editValues[key]
        if (typeof raw === 'string') {
          editValues[key] = raw.split(/\r\n?|\n/).map((line) => line.trim()).filter(Boolean).join('\n')
        }
      }
      input.values = editValues
    } else {
      input.values = values
    }
    // Cancelling a proposal form backs out of the form; it does not edit the activity.
    void submit(input, canceled ? (source.type === 'CONFIRMATION_EDIT' ? '取消修改' : '取消') : '提交', source)
    return
  }
  const fieldKey = block.fields[0]?.key
  const raw = fieldKey === undefined ? values['text'] : values[fieldKey]
  const answer = typeof raw === 'string' ? raw.trim() : ''
  if (answer === '') return
  void submit({ kind: 'submit_field', text: answer }, answer, entry.waiting)
}

const openAssistantEntity = (entity: EntityRef): void => {
  const target = assistantEntityDetailRoute(entity)
  if (target !== null) void router?.push(target)
}

const openAssistantLink = (link: ConversationLink): void => {
  const target = assistantPageRoute(link)
  if (target !== null) void router?.push(target)
}

const showExplicitNone = (entry: ChatEntry): boolean => {
  const block = interactionBlock(entry)
  return block?.type === 'interaction'
    && block.state === 'ACTIVE'
    && block.business_action === 'collect_field'
    && block.fields[0]?.key === 'next_action'
}

const entryBlocks = (entry: ChatEntry): NonNullable<ChatEntry['ui']>['blocks'] => entry.ui?.blocks ?? []
const isUnknownResult = (entry: ChatEntry): boolean => entryBlocks(entry).some((block) =>
  (block.type === 'error' && block.code === 'UNKNOWN_COMMIT_RESULT')
  || (block.type === 'notice' && block.title === '结果待核对'))
const hasErrorUi = (entry: ChatEntry): boolean => entryBlocks(entry).some((block) => block.type === 'error')
const isAuthoritativeWrite = (entry: ChatEntry): boolean => {
  if (entry.role !== 'assistant' || entry.outcome === 'failure' || isUnknownResult(entry) || hasErrorUi(entry)) return false
  if (entry.outcome === 'activity_written') return true
  return entryBlocks(entry).some((block) =>
    (block.type === 'action_result' && block.status === 'SUCCESS')
    || (block.type === 'notice' && block.title === '本次跟进已写入'))
}
const activityProjectionId = (entry: ChatEntry): string | null => {
  if (entry.projection?.activity_public_id != null) return entry.projection.activity_public_id
  if (entry.outcome !== 'activity_written') return null
  const receipt = entry.ownTask?.committed.find((item) => item.kind === 'customer_activity')
  return receipt?.kind === 'customer_activity' ? receipt.public_id : null
}

const dispositionProjection = (entry: ChatEntry): NonNullable<ConversationProjection['disposition']> | null => {
  if (entry.role !== 'assistant' || entry.outcome === 'failure' || isUnknownResult(entry) || hasErrorUi(entry)) return null
  if (entry.projection?.disposition != null) return entry.projection.disposition
  const currentTask = entry.ownTask
  const payload = currentTask?.follow_up_disposition
  if (currentTask == null || payload == null) return null
  if (currentTask.waiting?.type !== 'FOLLOW_UP_DISPOSITION' && entry.outcome !== 'follow_up_disposition') return null
  if (payload.batch_id == null || payload.batch_id === '') return null
  return {
    task_public_id: currentTask.public_id,
    batch_id: payload.batch_id,
    item_ids: payload.items.map((item) => item.item_id),
    card_role: payload.status === 'DONE' ? 'FINAL' : currentTask.waiting?.type === 'FOLLOW_UP_DISPOSITION' ? 'CURRENT' : 'NONE',
    version: currentTask.version,
  }
}

const dispositionCovers = (carrier: ChatEntry, source: ChatEntry): boolean => {
  const carrierProjection = dispositionProjection(carrier)
  const sourceProjection = dispositionProjection(source)
  if (carrierProjection == null || sourceProjection == null || carrierProjection.card_role === 'NONE') return false
  if (carrierProjection.task_public_id !== sourceProjection.task_public_id || carrierProjection.batch_id !== sourceProjection.batch_id) return false
  const carrierProjectionIds = carrierProjection.item_ids.filter((id) => id.trim() !== '')
  const sourceProjectionIds = sourceProjection.item_ids.filter((id) => id.trim() !== '')
  if (carrierProjectionIds.length === 0 || sourceProjectionIds.length === 0
    || carrierProjectionIds.length !== carrierProjection.item_ids.length
    || sourceProjectionIds.length !== sourceProjection.item_ids.length
    || new Set(carrierProjectionIds).size !== carrierProjectionIds.length
    || new Set(sourceProjectionIds).size !== sourceProjectionIds.length
    || sourceProjectionIds.some((id) => !carrierProjectionIds.includes(id))) return false
  const carrierItems = new Map(carrier.ownTask?.follow_up_disposition?.items.map((item) => [item.item_id, item]) ?? [])
  const sourceItems = source.ownTask?.follow_up_disposition?.items
  if (sourceItems == null || sourceItems.length === 0) return false
  for (const sourceItem of sourceItems) {
    if (!sourceItem.item_id.trim() || sourceItem.task_public_id == null || !sourceItem.task_public_id.trim()) return false
    const target = carrierItems.get(sourceItem.item_id)
    if (target == null || target.task_public_id == null || target.task_public_id !== sourceItem.task_public_id) return false
    if (['complete', 'hold', 'skip', 'failed', 'unknown'].includes(sourceItem.state)
      && (target.state !== sourceItem.state || (target.result_title ?? null) !== (sourceItem.result_title ?? null)
        || (target.result_message ?? null) !== (sourceItem.result_message ?? null))) return false
    if (((sourceItem.evidence_quote ?? '') !== '' && target.evidence_quote !== sourceItem.evidence_quote)
      || ((sourceItem.evidence_reason ?? '') !== '' && target.evidence_reason !== sourceItem.evidence_reason)) return false
  }
  return true
}

const dispositionRoleRank = (role: NonNullable<ConversationProjection['disposition']>['card_role']): number =>
  role === 'FINAL' ? 2 : role === 'CURRENT' ? 1 : 0
const compareCardEntries = (left: ChatEntry, right: ChatEntry): number => {
  const leftProjection = dispositionProjection(left)
  const rightProjection = dispositionProjection(right)
  const roleOrder = dispositionRoleRank(leftProjection?.card_role ?? 'NONE') - dispositionRoleRank(rightProjection?.card_role ?? 'NONE')
  if (roleOrder !== 0) return roleOrder
  const versionOrder = (leftProjection?.version ?? 0) - (rightProjection?.version ?? 0)
  if (versionOrder !== 0) return versionOrder
  const timeOrder = (left.at?.getTime() ?? 0) - (right.at?.getTime() ?? 0)
  if (timeOrder !== 0) return timeOrder
  const serverOrder = (left.serverId ?? '').localeCompare(right.serverId ?? '')
  if (serverOrder !== 0) return serverOrder
  return left.id - right.id
}

const recomputeProjectionCoverage = (): void => {
  const activityGroups = new Map<string, ChatEntry[]>()
  const dispositionGroups = new Map<string, ChatEntry[]>()
  for (const entry of entries.value) {
    const wasCovered = entry.projection?.visibility === 'COVERED'
    if (wasCovered && entry.projection != null) {
      entry.projection = { ...entry.projection, visibility: 'VISIBLE', covered_by: null }

    }
    if (entry.role !== 'assistant') continue
    const block = interactionBlock(entry)
    if (block?.state === 'ACTIVE' && entry.ui != null) {
      const current = task.value
      const isCurrent = block.business_action === 'assistant_boundary'
        ? entry.boundary != null && entry.boundary.entry_id === conversation.value?.pending_choice?.entry_id
        : !entry.replayed && current?.status === 'ACTIVE' && current.public_id === entry.ownTask?.public_id
          && entry.waiting != null && isSameWait(entry.waiting, current.waiting)
      const disposition = current?.follow_up_disposition
      const isDisposition = block.business_action === 'settle_follow_up_disposition'
      if (!isCurrent || (isDisposition && (disposition?.status !== 'ACTIVE' || disposition.settling === true))) {
        entry.replayed = true
        entry.ui = { ...entry.ui, blocks: entry.ui.blocks.map((candidate) => candidate === block ? {
          ...block, state: 'READ_ONLY', submit_action_id: null, submit_on_select: false, allow_cancel: false,
          secondary_action: null, cancel_reasons: [], options: block.options.map((option) => ({ ...option, disabled: true }))
        } : candidate) }
      }
    }
    const activityId = activityProjectionId(entry)
    if (activityId != null && isAuthoritativeWrite(entry)) {
      entry.projection = { ...(entry.projection ?? {}), visibility: 'VISIBLE', activity_public_id: activityId, covered_by: null }
      const group = activityGroups.get(activityId) ?? []
      group.push(entry)
      activityGroups.set(activityId, group)
    }
    const disposition = dispositionProjection(entry)
    if (disposition != null) {
      entry.projection = { ...(entry.projection ?? {}), visibility: 'VISIBLE', disposition, covered_by: null }
      const key = `${disposition.task_public_id}:${disposition.batch_id}`
      const group = dispositionGroups.get(key) ?? []
      group.push(entry)
      dispositionGroups.set(key, group)
    }
  }
  for (const group of activityGroups.values()) {
    const carrier = [...group].sort((left, right) => (right.at?.getTime() ?? 0) - (left.at?.getTime() ?? 0) || right.id - left.id)[0]
    if (carrier === undefined) continue
    for (const entry of group) if (entry !== carrier && entry.projection != null) {
      entry.projection = { ...entry.projection, visibility: 'COVERED', covered_by: carrier.serverId ?? String(carrier.id) }
    }
  }
  for (const group of dispositionGroups.values()) {
    const carrier = [...group].sort((left, right) => compareCardEntries(right, left)).find((entry) => dispositionProjection(entry)?.card_role !== 'NONE')
    if (carrier === undefined) continue
    for (const entry of group) if (entry !== carrier && entry.projection != null && dispositionCovers(carrier, entry)) {
      entry.projection = { ...entry.projection, visibility: 'COVERED', covered_by: carrier.serverId ?? String(carrier.id) }
    }
  }
}
const noteEpisodeMessages = (): void => {
  if (processing.value.episode === 0) return
  const baseline = new Set(processing.value.baselineIds)
  let sawFailure = false
  let sawUnknown = false
  for (const entry of entries.value) {
    if (entry.serverId === undefined || baseline.has(entry.serverId)) continue
    if (isAuthoritativeWrite(entry)) {
      processing.value.authoritativeWrite = true
      continue
    }
    if (isUnknownResult(entry)) sawUnknown = true
    else if (entry.role === 'assistant' && entry.outcome === 'failure') sawFailure = true
  }
  if (processing.value.authoritativeWrite) return
  if (sawUnknown) processing.value.settlement = 'unknown'
  else if (sawFailure) processing.value.settlement = 'failed'
}

const applyConversation = (view: ConversationView, older = false, requestOrder = ++viewRequestSequence): boolean => {
  if (disposed) return false
  if (!older && conversation.value !== null && (view.version < conversation.value.version
    || (view.version === conversation.value.version && requestOrder < appliedViewRequest)
    || (task.value?.public_id === view.focused_task?.public_id
      && (view.focused_task?.version ?? 0) < (task.value?.version ?? 0)))) return false
  historyError.value = ''
  if (!older) {
    appliedViewRequest = requestOrder
    if (task.value?.public_id !== view.focused_task?.public_id) {
      suppressConversationResume.value = false
      navigationVersion += 1
      recoveryToken += 1
      stopAutoRecovery()
      recoveryNotice.value = ''
      unacceptedText.value = ''
      routing.value = false
      pendingRequest.value = null
      processingRecovery.value = null
      reprocessAllowed.value = false
      reprocessTarget.value = null
      resultPending.value = false
      submitting.value = false
      endProcessing()
      resetProcessingEpisode()
    }
    conversation.value = view
    task.value = view.focused_task
    reconcileUnknownResult(view.focused_task)
  }
  if (older || !historyExtended) olderCursor.value = view.older_cursor
  const preserved = entries.value.filter((entry) => entry.serverId !== undefined && !entry.serverId.startsWith('current:'))
  const mapped = view.messages.map((message) => shallowReactive<ChatEntry>({
    id: ++seq.value, serverId: message.id, role: message.role, text: message.text,
    waiting: message.task?.waiting ?? null, ownTask: message.task, boundary: message.boundary,
    at: new Date(message.at), replayed: true, outcome: message.outcome ?? undefined,
    ui: message.role === 'assistant' ? message.ui : null, links: message.links,
    projection: message.projection ?? null,
  }))
  const incomingIds = new Set(mapped.map((entry) => entry.serverId))
  const preservedIds = new Set(preserved.map((entry) => entry.serverId))
  const uniqueMapped: ChatEntry[] = []
  const seenMapped = new Set<string | undefined>()
  for (const entry of mapped) {
    if (entry.serverId !== undefined && seenMapped.has(entry.serverId)) continue
    seenMapped.add(entry.serverId)
    uniqueMapped.push(entry)
  }
  const merged = older
    ? [...uniqueMapped.filter((entry) => entry.serverId === undefined || !preservedIds.has(entry.serverId)), ...preserved]
    : [...preserved.filter((entry) => !incomingIds.has(entry.serverId)), ...uniqueMapped]
  const completionIds = new Map<string | undefined, number>()
  for (const entry of merged) {
    if (entry.outcome === 'task_completed') completionIds.set(entry.ownTask?.public_id ?? entry.serverId, entry.id)
  }
  entries.value = shallowReactive(merged.filter((entry) => entry.outcome !== 'task_completed'
    || completionIds.get(entry.ownTask?.public_id ?? entry.serverId) === entry.id))
  const current = task.value
  if (current?.status === 'ACTIVE' && current.waiting != null && !reconciliationRequired.value) {
    const matching = entries.value.filter((entry) => entry.role === 'assistant' && entry.boundary == null
      && entry.outcome !== 'failure' && entry.ownTask?.public_id === current.public_id
      && entry.waiting != null && isSameWait(entry.waiting, current.waiting))
    const candidate = matching.reverse().find((entry) => interactionBlock(entry)?.state === 'ACTIVE')
    if (candidate !== undefined) {
      candidate.ownTask = current
      candidate.replayed = false
    } else if (!matching.some((entry) => interactionBlock(entry) !== undefined)) {
      pushEntry('assistant', current.waiting.prompt, current.waiting)
      const added = entries.value[entries.value.length - 1]
      if (added !== undefined) added.serverId = `current:${current.public_id}:${current.version}`
    }
  }
  recomputeProjectionCoverage()
  if (!older && current !== null) adoptProcessingTurn(current)
  // A confirmed not-saved send leaves the stale busy entry for the same-key resend to resume.
  if (!older && canResumeConversation.value && !reconciliationRequired.value && lostSend.value?.phase !== 'not_saved') {
    resultPending.value = true
  }
  if (!older) noteEpisodeMessages()
  if (!older) scrollToBottom(true)
  return true
}

const refreshConversation = async (): Promise<void> => {
  const order = ++viewRequestSequence
  const navigation = navigationVersion
  try {
    const view = await assistantApi.getConversation()
    if (navigation === navigationVersion) applyConversation(view, false, order)
  } catch {
    if (!disposed && navigation === navigationVersion && order >= appliedViewRequest) {
      historyError.value = '对话暂时没有刷新，已有内容都还在，可以点「刷新」再看一次。'
    }
  }
}

const loadOlder = async (): Promise<void> => {
  if (olderCursor.value === null || submitting.value) return
  scrollSchedule += 1
  submitting.value = true
  const cursor = olderCursor.value
  const scroller = scrollId.value
  const height = scroller?.scrollHeight ?? 0
  const top = scroller?.scrollTop ?? 0
  try {
    const page = await assistantApi.getConversation(cursor)
    historyExtended = true
    applyConversation(page, true)
    await nextTick()
    if (scroller) scroller.scrollTop = top + scroller.scrollHeight - height
  }
  catch { if (!disposed) historyError.value = '更早的对话暂时无法加载，请重试。' }
  finally { submitting.value = false }
}

// Leaving the page never stops a turn: the layout announces the result, and coming back reads
// the turn from its last event instead of restarting it.
const inFlightTurn = (): { targetId: string; turnId: string } | null => {
  const pending = processingRecovery.value ?? pendingRequest.value
  return pending !== null && pending.turnId !== '' ? { targetId: pending.targetId, turnId: pending.turnId } : null
}
const reattachProcessingTurn = (): void => {
  if (disposed || autoRecovering.value || processingRecovery.value === null) return
  void recoverProcessingTurn()
}
const onVisibilityChange = (): void => {
  if (document.visibilityState === 'visible') reattachProcessingTurn()
}
onActivated(() => {
  reclaimAssistantTurn()
  reattachProcessingTurn()
})
onDeactivated(() => {
  const turn = inFlightTurn()
  if (turn !== null) handOffAssistantTurn(turn)
})
document.addEventListener('visibilitychange', onVisibilityChange)
onUnmounted(() => { document.removeEventListener('visibilitychange', onVisibilityChange) })

const loadConversation = async (): Promise<void> => {
  loadingConversation.value = true
  const order = ++viewRequestSequence
  try {
    applyConversation(await assistantApi.openConversation(), false, order)
    if (processingRecovery.value !== null) await recoverProcessingTurn()
  } catch (error) {
    if (!disposed) historyError.value = conversationLoadErrorMessage(error)
  } finally { if (!disposed) loadingConversation.value = false }
}
void loadConversation()
</script>

<template>
  <div class="mx-auto flex h-full min-h-0 w-full min-w-0 max-w-[var(--assistant-column)] flex-col">
    <FeedbackAlert
      v-if="historyErrorFeedback"
      class="mb-space-2"
      density="compact"
      :error="historyErrorFeedback"
    >
      <template #actions>
        <Button type="button" variant="outline" size="sm" :disabled="submitting" @click="reconciliationRequired ? retryPending() : conversation ? refreshConversation() : loadConversation()">刷新</Button>
      </template>
    </FeedbackAlert>

    <DataViewStatePanel v-if="loadingConversation" class="flex-1" state="loading" loading-type="list" :loading-rows="3" />

    <div v-else ref="scrollId" class="min-h-0 flex-1 overflow-y-auto pr-space-1">
      <div class="flex flex-col py-space-2">
        <Button v-if="olderCursor !== null" variant="ghost" size="sm" class="self-start" :disabled="submitting" @click="loadOlder">查看更早对话</Button>
        <DataViewStatePanel
          v-if="visibleEntries.length === 0 && !historyError"
          state="empty"
          :empty-title="EMPTY_CONVERSATION_TITLE"
          :empty-description="EMPTY_CONVERSATION_HINT"
          class="py-space-4"
        >
          <template #empty-media>
            <MessageSquare class="size-icon-lg text-muted-foreground" aria-hidden="true" />
          </template>
        </DataViewStatePanel>
        <template v-for="(entry, index) in visibleEntries" :key="entry.id">
          <div v-if="entry.role === 'user'" class="flex justify-end" :class="entrySpacing(index)">
            <div class="max-w-[72%] whitespace-pre-wrap rounded-lg bg-secondary px-space-3 py-space-2 text-body text-secondary-foreground [overflow-wrap:anywhere] max-[767px]:max-w-[88%]">
              {{ entry.text }}
            </div>
          </div>
          <div v-else-if="entry.outcome === 'task_completed'" role="separator" aria-label="本次任务已完成" class="flex items-center gap-space-3" :class="entrySpacing(index)">
            <span aria-hidden="true" class="min-w-0 flex-1 border-t border-border"></span>
            <span class="shrink-0 whitespace-nowrap text-caption text-muted-foreground">本次任务已完成</span>
            <span aria-hidden="true" class="min-w-0 flex-1 border-t border-border"></span>
          </div>
          <div v-else class="flex items-start gap-space-2" :class="entrySpacing(index)">
            <div
              v-if="showsAvatar(index)"
              class="grid h-space-6 w-space-6 shrink-0 place-items-center rounded-full bg-brand text-caption font-semibold leading-none text-brand-foreground select-none"
              aria-hidden="true"
            >AI</div>
            <div v-else class="h-space-6 w-space-6 shrink-0" aria-hidden="true"></div>
            <div class="grid min-w-0 flex-1 gap-space-2">
              <AgentUIMessage
                v-if="entry.ui"
                :message="entry.ui"
                :disabled="busy"
                :locked-action-ids="heldActionIds"
                :notices="interactionNotices"
                @interaction="(actionId, values) => onAssistantInteraction(entry, actionId, values)"
                @action="(actionId) => { void retryRootFailure(entry, actionId) }"
                @open-entity="openAssistantEntity"
              />
              <div v-else class="rounded-lg border border-border bg-card px-space-3 py-space-2 text-body text-foreground">这条结果暂时无法显示</div>
              <div v-if="(entry.links?.length ?? 0) > 0" class="flex flex-wrap gap-space-2" data-assistant-links>
                <Button
                  v-for="link in entry.links"
                  :key="link.page + (link.customer_public_id ?? '')"
                  type="button"
                  variant="link"
                  size="sm"
                  class="justify-start px-0"
                  @click="openAssistantLink(link)"
                >
                  {{ link.label }}
                </Button>
              </div>
              <Button
                v-if="showExplicitNone(entry)"
                type="button"
                variant="ghost"
                size="sm"
                class="self-start"
                :disabled="busy"
                @click="() => { void gapNone(entry) }"
              >这条没有下一步</Button>
            </div>
          </div>
        </template>
      </div>
    </div>

    <section v-if="showProcessCard && liveProcess" class="mt-space-4 grid gap-space-2" aria-label="执行过程">
      <AgentUIProcessBlock
        :block="liveProcess"
        default-open
        :summary="liveProcessSummary"
        :status="processChipStatus"
        :meta="liveStageMetaByKey"
      />
      <AgentUIBanner tone="info" :icon="Info" title="原始内容已保存" role="status" />
    </section>

    <nav v-if="visiblePendingDrafts.length > 0" class="mt-space-4 flex flex-wrap items-center gap-space-2" aria-label="待补充" data-assistant-pending-drafts>
      <span class="text-caption text-muted-foreground">待补充</span>
      <Button
        v-for="draft in visiblePendingDrafts"
        :key="draft.public_id"
        type="button"
        variant="outline"
        size="sm"
        class="min-h-11"
        :disabled="busy || conversation?.pending_choice != null"
        @click="() => { void openPendingDraft(draft) }"
      >
        {{ draft.customer_name ? `${draft.label} · ${draft.customer_name}` : draft.label }}
      </Button>
    </nav>

    <div class="mt-space-4 rounded-lg border border-input bg-card p-space-3 transition-colors hover:border-ring-input focus-within:border-ring-input">
      <p v-if="cardLocked" class="mb-space-2 flex items-center gap-space-2 text-caption text-muted-foreground">
        <Lock class="size-icon-sm shrink-0" aria-hidden="true" />
        <span>{{ INPUT_LOCKED_HINT }}</span>
      </p>
      <div v-if="lostSend?.phase === 'checking'" class="mb-space-2 flex items-center gap-space-2 text-caption font-medium text-brand" role="status" data-assistant-lost-send="checking">
        <LoaderCircle class="size-icon-sm animate-spin motion-reduce:animate-none" aria-hidden="true" />
        <span>保存中…</span>
      </div>
      <div v-else-if="processing.active || routing || recoveryNotice" class="mb-space-2 flex items-center gap-space-2 text-caption font-medium text-brand">
        <LoaderCircle v-if="routing || processing.active || autoRecovering" class="size-icon-sm animate-spin motion-reduce:animate-none" aria-hidden="true" />
        <span>{{ routing ? '正在理解这次沟通…' : (recoveryNotice || processingHint) }}</span>
      </div>
      <p v-if="lostSendNotice" class="mb-space-2 flex items-center gap-space-2 text-caption text-muted-foreground" role="status" :data-assistant-lost-send="lostSend?.phase">
        <Info class="size-icon-sm shrink-0" aria-hidden="true" />
        <span>{{ lostSendNotice }}</span>
      </p>
      <Textarea
        aria-label="客户沟通内容"
        v-model="inputText"
        :rows="2"
        :disabled="loadingConversation || busy || conversation?.pending_choice != null"
        :placeholder="inputPlaceholder"
        class="resize-none border-0 p-0"
        @keydown.enter.exact.prevent="submitText"
      />
      <div class="mt-space-2 flex flex-wrap items-center justify-between gap-space-2">
        <div class="flex flex-wrap items-center gap-space-2">
          <Badge v-if="activityBadge" variant="secondary">{{ activityBadge }}</Badge>
          <span class="text-caption text-muted-foreground">Enter 发送 · Shift+Enter 换行</span>
        </div>
        <div class="flex flex-wrap items-center gap-space-2">
          <Button v-if="showRefreshStatus" variant="outline" :disabled="submitting" @click="unknownResult !== null || showSyncResult ? syncResult() : refreshConversation()">刷新状态</Button>
          <p v-if="showReprocess" class="m-0 text-caption text-muted-foreground">使用同一条任务重新处理，不会重复写入。</p>
          <Button v-if="showReprocess" variant="outline" :disabled="submitting" @click="reprocessTurn">重新处理</Button>
          <Button v-if="lostSend?.phase === 'unconfirmed'" variant="outline" :disabled="submitting" @click="checkLostSend">查看结果</Button>
          <Button v-if="showContinuePending" variant="outline" :disabled="submitting" @click="retryPending">继续处理</Button>
          <Button v-if="(!isTerminal && task !== null) || conversation?.pending_choice != null" variant="ghost" :disabled="busy || resultPending" @click="cancelTask()">
            <X aria-hidden="true" />算了
          </Button>
          <Button aria-label="发送" :loading="sendingText" :disabled="loadingConversation || busy || conversation?.pending_choice != null" @click="submitText">
            <ArrowUp aria-hidden="true" />发送
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>
