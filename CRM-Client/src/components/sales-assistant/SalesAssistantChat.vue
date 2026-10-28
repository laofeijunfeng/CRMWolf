<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, shallowRef } from 'vue'
import { isAxiosError } from 'axios'
import { ArrowUp, X } from 'lucide-vue-next'
import { assistantApi, submitInputStream, type AssistantTurn, type StageName } from '@/api/assistant'
import type { SubmitAssistantInput } from '@/api/assistant'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ZodError } from 'zod'
import AgentUIMessage from '@/components/agent-ui/AgentUIMessage.vue'
import type { JsonObject } from '@/schemas/agent-contracts/common'
import type { AgentUIEnvelope } from '@/schemas/agent-contracts/ui-envelope'
import { type AssistantTaskView, type TaskWaiting, type ConversationView, type ConversationReply, type ConversationBoundary } from '@/schemas/assistant-contracts'

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
  outcome?: 'activity_written' | 'failure' | undefined
  ui?: AgentUIEnvelope | null | undefined
}

const task = ref<AssistantTaskView | null>(null)
let disposed = false
let navigationVersion = 0
let viewRequestSequence = 0
let appliedViewRequest = 0
let historyExtended = false
onUnmounted(() => { disposed = true; if (elapsedTimer !== null) clearInterval(elapsedTimer) })
defineProps<{ optionalMarker?: boolean }>()
const emit = defineEmits<{
  (e: 'task-updated', task: AssistantTaskView, replyMessage: string): void
  (e: 'task-created', task: AssistantTaskView): void
}>()
const entries = ref<ChatEntry[]>([])
const inputText = ref('')
const submitting = ref(false)
const seq = ref(0)
const conversation = shallowRef<ConversationView | null>(null)
const loadingConversation = ref(true)
const historyError = ref('')
const routing = ref(false)
const olderCursor = ref<number | null>(null)
const pendingConversation = shallowRef<(() => Promise<ConversationReply>) | null>(null)
const unacceptedText = ref('')

const KIND_LABELS: Record<string, string> = {
  FOLLOW_UP: '普通跟进',
  ONLINE_MEETING: '线上会议',
  OFFLINE_MEETING: '线下会议'
}

const conversationLoadErrorMessage = (error: unknown): string => {
  const noNewRecord = '；不会自动开始新的记录。'
  if (!isAxiosError(error)) return `对话加载失败，请重试${noNewRecord}`
  const responseData = error.response?.data as { error_code?: unknown } | undefined
  if (responseData?.error_code === 'DATABASE_SCHEMA_MISMATCH') {
    return `数据库结构与当前版本不一致，请联系管理员执行数据库迁移后重试${noNewRecord}`
  }
  if (error.response?.status === 401) return `登录状态已失效，请重新登录后重试${noNewRecord}`
  if (error.response === undefined) return `服务或网络暂时不可用，请检查网络后重试${noNewRecord}`
  if (error.response.status >= 500) return `服务暂时不可用，请稍后重试${noNewRecord}`
  return `对话加载失败，请重试${noNewRecord}`
}

const waiting = computed<TaskWaiting | null>(() => task.value?.waiting ?? null)
const isWaiting = computed(() => waiting.value !== null)
const isTerminal = computed(() => task.value != null && task.value.status !== 'ACTIVE')



const inputPlaceholder = computed(() => {
  if (waiting.value?.type === 'FIELD' && waiting.value.field === 'temporal_choice') return '或输入完整日期，例如 2026-10-30'
  return '描述一次客户沟通，我来整理成跟进或会议纪要…'
})

const pushEntry = (
  role: 'user' | 'assistant',
  text: string,
  entryWaiting: TaskWaiting | null = null,
  replayed = false
): void => {
  seq.value += 1
  entries.value.push({ id: seq.value, role, text, waiting: entryWaiting, replayed, at: new Date(), ownTask: task.value })
  scrollToBottom()
}

const scrollId = ref<HTMLElement | null>(null)
const scrollToBottom = (): void => {
  void nextTick(() => {
    scrollId.value?.scrollTo?.({ top: scrollId.value.scrollHeight })
  })
}


interface LiveStage {
  name: StageName
  status: 'pending' | 'running' | 'done'
  ms?: number | undefined
  score?: number | undefined
}

const STAGE_LABELS: Record<StageName, string> = {
  classify: '判断活动类型',
  structure: '整理内容',
  quality_gate: '评估记录质量',
  write: '写入客户活动'
}

const processing = ref<{ active: boolean; stages: LiveStage[]; startedAt: number }>({
  active: false,
  stages: [],
  startedAt: 0
})
const elapsedSeconds = ref(0)
let elapsedTimer: ReturnType<typeof setInterval> | null = null

const presetStages = (input: SubmitAssistantInput, hasWaiting: boolean): StageName[] => {
  if (input.kind === 'text' && !hasWaiting) return ['classify', 'structure', 'quality_gate']
  if (input.kind === 'submit_field') return ['quality_gate']
  if (input.kind === 'confirm' && input.choice === 'confirm') return ['write']
  return []
}

const beginProcessing = (input: SubmitAssistantInput, hasWaiting: boolean): void => {
  processing.value = {
    active: true,
    stages: presetStages(input, hasWaiting).map((name) => ({ name, status: 'pending' })),
    startedAt: Date.now()
  }
  elapsedSeconds.value = 0
  if (elapsedTimer !== null) clearInterval(elapsedTimer)
  elapsedTimer = setInterval(() => {
    elapsedSeconds.value = Math.floor((Date.now() - processing.value.startedAt) / 1000)
  }, 1000)
}

const applyStageEvent = (event: { stage: StageName; phase: 'start' | 'done'; ms?: number | undefined; score?: number | undefined }): void => {
  const stages = processing.value.stages
  let target = stages.find((item) => item.name === event.stage)
  if (target === undefined) {
    target = { name: event.stage, status: 'pending' }
    stages.push(target)
  }
  if (event.phase === 'start') {
    target.status = 'running'
  } else {
    target.status = 'done'
    target.ms = event.ms
    target.score = event.score
  }
}

const endProcessing = (): void => {
  if (elapsedTimer !== null) {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }
  processing.value.active = false
}

const processingHint = computed(() => {
  if (!processing.value.active) return ''
  const base = 'Agent 正在处理，通常需要 30–60 秒…'
  if (elapsedSeconds.value >= 60) return `${base}（已 ${elapsedSeconds.value} 秒 · 内容已保存，刷新后可继续）`
  if (elapsedSeconds.value >= 15) return `${base}（已 ${elapsedSeconds.value} 秒 · 内容不会丢失，请稍候）`
  return base
})
const pendingRequest = shallowRef<{ input: SubmitAssistantInput; targetId: string; displayText: string; turnId: string; cursor: number } | null>(null)
const processingRecovery = shallowRef<{ targetId: string; turnId: string; cursor: number } | null>(null)
const reprocessTarget = shallowRef<{ targetId: string; turnId: string; cursor: number } | null>(null)
const recoveryNotice = ref('')
const autoRecovering = ref(false)
const reprocessAllowed = ref(false)
const seenEventKeys = new Set<string>()
const RECOVERY_POLLS = 90
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
        cursor: recovery?.cursor ?? 0
      }
    }
    resultPending.value = true
  } else if (processingRecovery.value?.targetId === updated.public_id) {
    processingRecovery.value = null
    resultPending.value = false
  }
  if (updated.reprocess_turn_id != null && updated.reprocess_turn_id !== '') {
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

const applyTurnEvents = (turnId: string, events: AssistantTurn['events']): string | undefined => {
  let reply: string | undefined
  for (const event of events) {
    if (!rememberEvent(turnId, event.seq)) continue
    if (event.event === 'stage') {
      const stage = event.data['stage']
      const phase = event.data['phase']
      if ((stage === 'classify' || stage === 'structure' || stage === 'quality_gate' || stage === 'write')
        && (phase === 'start' || phase === 'done')) {
        applyStageEvent({
          stage,
          phase,
          ms: typeof event.data['ms'] === 'number' ? event.data['ms'] : undefined,
          score: typeof event.data['score'] === 'number' ? event.data['score'] : undefined
        })
      }
    } else if (event.event === 'waiting' && typeof event.data['message'] === 'string') {
      reply = event.data['message']
    } else if (event.event === 'error') {
      pushEntry('assistant', typeof event.data['message'] === 'string' ? event.data['message'] : '处理失败')
      const entry = entries.value[entries.value.length - 1]
      if (entry !== undefined) entry.outcome = 'failure'
    }
  }
  return reply
}

const readKnownTurn = async (pending: { targetId: string; turnId: string; cursor: number }): Promise<boolean> => {
  const turn = await assistantApi.getTurn(pending.targetId, pending.turnId, pending.cursor)
  const seqs = turn.events.map((event) => event.seq)
  if (seqs.length > 0) pending.cursor = Math.max(pending.cursor, ...seqs)
  const reply = applyTurnEvents(pending.turnId, turn.events)
  publishTask(turn.task, reply)
  if (turn.reprocess_allowed) {
    reprocessAllowed.value = true
    reprocessTarget.value = { targetId: pending.targetId, turnId: pending.turnId, cursor: pending.cursor }
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
      if (pendingRequest.value?.targetId === pending.targetId) pendingRequest.value = null
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
        const done = await readKnownTurn(pending)
        if (token === recoveryToken) await refreshConversation()
        if (done || disposed || token !== recoveryToken) {
          const successor = processingRecovery.value
          if (done && successor !== null && successor.turnId !== pending.turnId && token === recoveryToken) {
            await startAutoRecovery(successor, '已受理，正在确认处理结果')
          }
          return
        }
        if (pollsLeft <= 1) {
          stopAutoRecovery()
          recoveryNotice.value = ''
          resultPending.value = true
          logRecovery('recovery_timeout', { task: pending.targetId, turn_id: pending.turnId, last_seq: pending.cursor, event_name: 'timeout' })
          return
        }
        scheduleRecovery(pending, pollsLeft - 1)
      } catch (error) {
        if (disposed || token !== recoveryToken) return
        if (!(error instanceof ZodError) && pollsLeft > 1) {
          scheduleRecovery(pending, pollsLeft - 1)
          return
        }
        stopAutoRecovery()
        recoveryNotice.value = ''
        resultPending.value = true
        pushEntry('assistant', '处理结果暂时无法显示，请点同步结果。')
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
    if (done && successor !== null && successor.turnId !== pending.turnId) {
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
    pushEntry('assistant', '处理结果暂时无法显示，请点同步结果。')
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


const publishTask = (updated: AssistantTaskView, message?: string): void => {
  if (disposed || updated === undefined || (task.value !== null && task.value.public_id !== updated.public_id)) return
  if (task.value !== null && updated.version < task.value.version) return
  const hadActivity = task.value?.committed.some((receipt) => receipt.kind === 'customer_activity') ?? false
  task.value = updated
  adoptProcessingTurn(updated)
  const prompt = updated.waiting?.prompt ?? ''
  const reply = message ?? prompt
  if (reply !== '') pushEntry('assistant', reply, updated.waiting ?? null)
  if (reply !== '' && !hadActivity && updated.committed.some((receipt) => receipt.kind === 'customer_activity')) {
    const entry = entries.value[entries.value.length - 1]
    if (entry !== undefined && entry.role === 'assistant' && entry.waiting === null) entry.outcome = 'activity_written'
  }
  emit('task-updated', updated, reply)
}
const runPrepared = async (prepared: NonNullable<ConversationReply['submission']>, displayText: string): Promise<void> => {
  const navigation = navigationVersion
  const targetId = prepared.task_public_id
  const request: SubmitAssistantInput = {
    kind: prepared.input.kind, text: prepared.input.text ?? undefined, choice: prepared.input.choice ?? undefined,
    client_request_id: prepared.input.client_request_id, action_id: prepared.input.action_id ?? undefined,
    expected_version: prepared.input.expected_version ?? undefined
  }
  submitting.value = true
  processingRecovery.value = null
  recoveryStarted = false
  try {
    resultPending.value = false
    const pending = { input: request, targetId, displayText, turnId: prepared.turn_id, cursor: 0 }
    pendingRequest.value = pending
    beginProcessing(request, task.value?.waiting != null)
    const active = (): boolean => !disposed && navigation === navigationVersion && pendingRequest.value === pending
    let turnId = prepared.turn_id
    let cursor = 0
    let delivered = false
    let disconnected = false
    let terminalInvalid = false
    await submitInputStream(targetId, request, {
      onAccepted: (id, seq) => {
        if (!active()) return
        turnId = id
        cursor = Math.max(cursor, seq ?? 0)
        rememberEvent(id, seq)
        if (pendingRequest.value !== null) { pendingRequest.value.turnId = id; pendingRequest.value.cursor = cursor }
      },
      onStage: (event) => {
        if (!active()) return
        cursor = Math.max(cursor, event.seq ?? 0)
        rememberEvent(turnId, event.seq)
        if (pendingRequest.value !== null) pendingRequest.value.cursor = cursor
        applyStageEvent(event)
      },
      onWaiting: (data) => {
        if (!active()) return
        delivered = true
        cursor = Math.max(cursor, data.seq ?? 0)
        publishTask(data.task, data.message)
      },
      onError: (event) => {
        if (!active()) return
        delivered = true
        cursor = Math.max(cursor, event.seq ?? 0)
        pushEntry('assistant', event.message)
        const entry = entries.value[entries.value.length - 1]
        if (entry !== undefined) entry.outcome = 'failure'
      },
      onNetworkLost: () => { if (active()) disconnected = true },
      onTerminalInvalid: () => { if (active()) terminalInvalid = true }
    })
    if (!active()) return
    if (!delivered && !disconnected && turnId !== '') {
      try {
        const turn = await assistantApi.getTurn(targetId, turnId, cursor)
        if (!active()) return
        if (turn.status === 'SUCCEEDED' || turn.status === 'FAILED') {
          publishTask(turn.task)
          delivered = true
          disconnected = false
        }
      } catch {
        // Fall through to the existing durable recovery path.
      }
    }
    if ((disconnected || !delivered) && turnId !== '') {
      pending.cursor = cursor
      const notice = terminalInvalid ? '处理结果暂时无法显示，正在重新读取。' : '已受理，正在确认处理结果'
      await startAutoRecovery({ targetId, turnId, cursor }, notice)
    } else if (disconnected || !delivered) {
      resultPending.value = true
      try {
        const latest = await assistantApi.getTask(targetId)
        if (!active()) return
        publishTask(latest)
        if (processingRecovery.value !== null) await startAutoRecovery(processingRecovery.value, '已受理，正在确认处理结果')
      } catch {
        resultPending.value = true
      }
    }
    if (!active()) return
    if (!resultPending.value) pendingRequest.value = null
    await refreshConversation()
  } catch (error) {
    if (disposed || navigation !== navigationVersion) return
    resultPending.value = true
    pushEntry('assistant', `提交状态待确认：${error instanceof Error ? error.message : '网络请求失败'}`)
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
  if (!text || loadingConversation.value || resultPending.value || submitting.value || conversation.value === null || conversation.value.pending_choice !== null) return
  if (explicitNone.value && waiting.value?.type === 'FIELD' && waiting.value.field === 'next_action') {
    explicitNone.value = false
    await submit({ kind: 'submit_field', choice: 'EXPLICITLY_NONE', text }, text, waiting.value)
    return
  }
  explicitNone.value = false
  unacceptedText.value = text
  const request = { text, client_request_id: crypto.randomUUID(), expected_version: conversation.value.version }
  pushEntry('user', text)
  inputText.value = ''
  await dispatchConversation(() => assistantApi.conversationText(request), text)
}

const submit = async (input: SubmitAssistantInput, displayText: string, source: TaskWaiting | null = null): Promise<void> => {
  if (submitting.value || resultPending.value || task.value === null || conversation.value === null) return
  if (source !== null && (task.value.waiting?.action_id !== source.action_id || task.value.waiting?.expected_version !== source.expected_version)) return
  const payload: SubmitAssistantInput = { ...input, client_request_id: crypto.randomUUID(),
    action_id: source?.action_id ?? undefined, expected_version: source?.expected_version ?? undefined }
  const request = { task_public_id: task.value.public_id, input: payload, expected_version: conversation.value.version }
  pushEntry('user', displayText)
  inputText.value = ''
  await dispatchConversation(() => assistantApi.conversationCommand(request), displayText)
}

const dispatchConversation = async (send: () => Promise<ConversationReply>, displayText: string): Promise<void> => {
  if (disposed) return
  const requestOrder = ++viewRequestSequence
  submitting.value = true
  routing.value = true
  pendingConversation.value = send
  try {
    const response = await send()
    if (disposed) return
    pendingConversation.value = null
    unacceptedText.value = ''
    applyConversation(response.conversation, false, requestOrder)
    routing.value = false
    if (response.submission !== null) await runPrepared(response.submission, displayText)
    else resultPending.value = false
  } catch (error) {
    if (disposed) return
    if (isAxiosError(error) && error.response?.status === 409) {
      // A rejected stale command must not stay in an endless same-version retry loop.
      resultPending.value = false
      await refreshConversation()
      if (conversation.value?.has_pending_request !== true) {
        pendingConversation.value = null
        if (unacceptedText.value !== '') inputText.value = unacceptedText.value
        unacceptedText.value = ''
      }
      historyError.value = '会话已更新，请查看当前提示；未接受的内容可重新发送。'
    } else {
      resultPending.value = true
      historyError.value = `发送状态待确认：${error instanceof Error ? error.message : '网络请求失败'}`
    }
  } finally {
    if (!disposed) { routing.value = false; submitting.value = false }
  }
}

const chooseBoundary = async (entry: ChatEntry, choice: 'CONTINUE' | 'NEW'): Promise<void> => {
  const boundary = entry.boundary
  if (!boundary || conversation.value?.pending_choice?.entry_id !== boundary.entry_id || submitting.value || resultPending.value) return
  const request = { entry_id: boundary.entry_id, choice, expected_version: conversation.value.version, client_request_id: crypto.randomUUID() }
  await dispatchConversation(() => assistantApi.conversationChoice(request), choice === 'CONTINUE' ? '接着刚才' : '另记一件')
}

const choiceLabel = (choice: string, source: TaskWaiting | null): string => {
  const candidate = source?.candidates?.find((item) => item.id === choice)
  if (candidate === undefined) return KIND_LABELS[choice] ?? '选择'
  return 'account_name' in candidate ? candidate.account_name : candidate.label
}

const pickKind = (choice: string, source: TaskWaiting | null): Promise<void> =>
  submit({ kind: 'submit_field', choice }, choiceLabel(choice, source), source)

const confirmWrite = (source: TaskWaiting | null): Promise<void> =>
  submit({ kind: 'confirm', choice: 'confirm' }, '确认', source)
const rejectWrite = (source: TaskWaiting | null): Promise<void> =>
  submit({ kind: 'confirm', choice: 'reject' }, '取消', source)
const cancelTask = async (source: TaskWaiting | null = waiting.value): Promise<void> => {
  const pending = conversation.value?.pending_choice
  if (pending && conversation.value) {
    const request = { entry_id: pending.entry_id, choice: 'CANCEL' as const, expected_version: conversation.value.version, client_request_id: crypto.randomUUID() }
    await dispatchConversation(() => assistantApi.conversationChoice(request), '算了，不记了')
    return
  }
  await submit({ kind: 'cancel' }, '算了，不记了', source)
}

const showConversationRetry = computed(() => resultPending.value && !autoRecovering.value && processingRecovery.value === null
  && (pendingConversation.value !== null || conversation.value?.has_pending_request === true))
const showSyncResult = computed(() => resultPending.value && !autoRecovering.value && !showConversationRetry.value
  && (processingRecovery.value !== null || (pendingRequest.value?.turnId ?? '') !== ''))
const showReprocess = computed(() => reprocessAllowed.value && reprocessTarget.value !== null && !autoRecovering.value)

const syncResult = async (): Promise<void> => {
  const activeRecovery = processingRecovery.value
  const request = pendingRequest.value
  const pending = activeRecovery ?? (request !== null && request.turnId !== ''
    ? { targetId: request.targetId, turnId: request.turnId, cursor: request.cursor }
    : null)
  if (pending === null || submitting.value) return
  submitting.value = true
  recoveryToken += 1
  stopAutoRecovery()
  try {
    await readKnownTurn(pending)
    await refreshConversation()
  } catch {
    resultPending.value = true
    pushEntry('assistant', '处理结果暂时无法显示，请点同步结果。')
  } finally {
    submitting.value = false
  }
}

const reprocessTurn = async (): Promise<void> => {
  const pending = reprocessTarget.value
  if (pending === null || !reprocessAllowed.value || submitting.value) return
  submitting.value = true
  recoveryToken += 1
  stopAutoRecovery()
  try {
    const current = await assistantApi.getTurn(pending.targetId, pending.turnId, pending.cursor)
    if (current.reprocess_allowed !== true) {
      reprocessAllowed.value = false
      publishTask(current.task)
      return
    }
    const restarted = await assistantApi.retryTurn(pending.targetId, pending.turnId, current.lease_version, pending.cursor)
    reprocessAllowed.value = restarted.reprocess_allowed === true
    const seqs = restarted.events.map((event) => event.seq)
    if (seqs.length > 0) pending.cursor = Math.max(pending.cursor, ...seqs)
    applyTurnEvents(pending.turnId, restarted.events)
    publishTask(restarted.task)
    if (restarted.status === 'PENDING' || restarted.status === 'RUNNING') {
      beginProcessing(pendingRequest.value?.input ?? { kind: 'text' }, task.value?.waiting != null)
      await startAutoRecovery(pending, '已受理，正在确认处理结果')
    }
  } catch {
    resultPending.value = true
    pushEntry('assistant', '处理结果暂时无法显示，请点同步结果。')
  } finally {
    submitting.value = false
  }
}

const retryPending = async (): Promise<void> => {
  if (submitting.value) return
  if (conversation.value?.has_pending_request === true && pendingConversation.value === null) {
    await dispatchConversation(() => assistantApi.resumeConversation(), '')
    return
  }
  if (processingRecovery.value !== null) {
    await syncResult()
    return
  }
  if (pendingConversation.value !== null) {
    await dispatchConversation(pendingConversation.value, '')
    return
  }
  const navigation = navigationVersion
  const pending = pendingRequest.value
  if (pending === null || submitting.value) return
  submitting.value = true
  try {
    if (pending.turnId !== '') {
      const turn = await assistantApi.getTurn(pending.targetId, pending.turnId, pending.cursor)
      if (disposed || navigation !== navigationVersion || task.value?.public_id !== pending.targetId || pendingRequest.value !== pending) return
      pending.cursor = Math.max(pending.cursor, ...turn.events.map((event) => event.seq))
      publishTask(turn.task)
      if (processingRecovery.value !== null || turn.status === 'PENDING' || turn.status === 'RUNNING') {
        await startAutoRecovery({ targetId: pending.targetId, turnId: pending.turnId, cursor: pending.cursor }, '已受理，正在确认处理结果')
        return
      }
      if (turn.status === 'SUCCEEDED' || turn.status === 'FAILED') {
        resultPending.value = false
        pendingRequest.value = null
        return
      }
    } else {
      const latest = await assistantApi.getTask(pending.targetId)
      if (disposed || navigation !== navigationVersion || task.value?.public_id !== pending.targetId || pendingRequest.value !== pending) return
      publishTask(latest)
      if (processingRecovery.value !== null) {
        await startAutoRecovery(processingRecovery.value, '已受理，正在确认处理结果')
        return
      }
    }
    await submitInputStream(pending.targetId, pending.input, {
      onAccepted: (id, seq) => {
        if (disposed || navigation !== navigationVersion || pendingRequest.value !== pending) return
        pending.turnId = id; pending.cursor = Math.max(pending.cursor, seq ?? 0)
      },
      onStage: (event) => { if (!disposed && navigation === navigationVersion && pendingRequest.value === pending) { pending.cursor = Math.max(pending.cursor, event.seq ?? 0); applyStageEvent(event) } },
      onWaiting: (data) => {
        if (disposed || navigation !== navigationVersion || pendingRequest.value !== pending) return
        publishTask(data.task, data.message)
        pendingRequest.value = null
        resultPending.value = processingRecovery.value !== null
      },
      onError: (event) => {
        if (disposed || navigation !== navigationVersion || pendingRequest.value !== pending) return
        pushEntry('assistant', event.message)
        const entry = entries.value[entries.value.length - 1]
        if (entry !== undefined) entry.outcome = 'failure'
        pendingRequest.value = null
        resultPending.value = false
      },
      onNetworkLost: () => { if (!disposed && navigation === navigationVersion && pendingRequest.value === pending) resultPending.value = true }
    })
  } catch {
    if (!disposed && navigation === navigationVersion && task.value?.public_id === pending.targetId) resultPending.value = true
  } finally {
    if (!disposed && navigation === navigationVersion && task.value?.public_id === pending.targetId) submitting.value = false
  }
}

const focusComposer = (): void => {
  inputText.value = ''
  void nextTick(() => {
    scrollId.value?.scrollIntoView?.({ block: 'center' })
    document.querySelector<HTMLTextAreaElement>('.sales-assistant-page textarea')?.focus()
  })
}

const changeKind = async (kind: 'FOLLOW_UP' | 'ONLINE_MEETING' | 'OFFLINE_MEETING'): Promise<void> => {
  if (busy.value || task.value === null || conversation.value === null) return
  const request = { task_public_id: task.value.public_id, kind, task_version: task.value.version,
    expected_version: conversation.value.version, client_request_id: crypto.randomUUID() }
  await dispatchConversation(() => assistantApi.conversationKind(request), `改为${KIND_LABELS[kind]}`)
}

const nextKindOf = (current: string | null | undefined): 'FOLLOW_UP' | 'ONLINE_MEETING' => {
  return current === 'ONLINE_MEETING' || current === 'OFFLINE_MEETING' ? 'FOLLOW_UP' : 'ONLINE_MEETING'
}

const explicitNone = ref(false)
const gapNone = (entry: ChatEntry): Promise<void> => {
  if (submitting.value || resultPending.value || !showExplicitNone(entry)) return Promise.resolve()
  explicitNone.value = true
  return Promise.resolve()
}


const busy = computed(() => submitting.value || resultPending.value)

const entryTask = (entry: ChatEntry): AssistantTaskView | null => entry.ownTask ?? null

const interactionBlock = (entry: ChatEntry): Extract<NonNullable<ChatEntry['ui']>['blocks'][number], { type: 'interaction' }> | undefined =>
  entry.ui?.blocks.find((block): block is Extract<NonNullable<ChatEntry['ui']>['blocks'][number], { type: 'interaction' }> => block.type === 'interaction')

const onAssistantInteraction = (entry: ChatEntry, values: JsonObject): void => {
  const block = interactionBlock(entry)
  if (block === undefined || block.type !== 'interaction') return
  const choice = typeof values['choice'] === 'string' ? values['choice'] : ''
  if (block.business_action === 'assistant_boundary') {
    if (choice === 'CONTINUE' || choice === 'NEW') void chooseBoundary(entry, choice)
    return
  }
  if (block.interaction_type === 'confirmation') {
    if (choice === 'confirm') void confirmWrite(entry.waiting)
    else void rejectWrite(entry.waiting)
    return
  }
  if (block.interaction_type === 'choice') {
    if (choice !== '') {
      void pickKind(choice, entry.waiting)
      return
    }
    const typed = typeof values['text'] === 'string' ? values['text'].trim() : ''
    if (typed !== '') void submit({ kind: 'submit_field', text: typed }, typed, entry.waiting)
    return
  }
  const fieldKey = block.fields[0]?.key
  const raw = fieldKey === undefined ? values['text'] : values[fieldKey]
  const answer = typeof raw === 'string' ? raw.trim() : ''
  if (answer === '') return
  void submit({ kind: 'submit_field', text: answer }, answer, entry.waiting)
}

const showActivityExtras = (entry: ChatEntry): boolean => {
  const block = interactionBlock(entry)
  return block?.type === 'interaction' && block.business_action === 'confirm_activity_write' && block.state === 'ACTIVE'
}

const showExplicitNone = (entry: ChatEntry): boolean => {
  const block = interactionBlock(entry)
  return block?.type === 'interaction'
    && block.state === 'ACTIVE'
    && block.business_action === 'collect_field'
    && block.fields[0]?.key === 'next_action'
}

const applyConversation = (view: ConversationView, older = false, requestOrder = ++viewRequestSequence): void => {
  if (disposed) return
  if (!older && conversation.value !== null && (view.version < conversation.value.version
    || (view.version === conversation.value.version && requestOrder < appliedViewRequest)
    || (view.version === conversation.value.version && task.value?.public_id === view.focused_task?.public_id
      && (view.focused_task?.version ?? 0) < (task.value?.version ?? 0)))) return
  historyError.value = ''
  if (!older) {
    appliedViewRequest = requestOrder
    if (task.value?.public_id !== view.focused_task?.public_id) {
      navigationVersion += 1
      pendingRequest.value = null
      processingRecovery.value = null
      resultPending.value = false
      submitting.value = false
      endProcessing()
    }
    conversation.value = view
    task.value = view.focused_task
  }
  if (older || !historyExtended) olderCursor.value = view.older_cursor
  const preserved = entries.value.filter((entry) => entry.serverId !== undefined && !entry.serverId.startsWith('current:'))
  const mapped = view.messages.map((message): ChatEntry => ({
    id: ++seq.value, serverId: message.id, role: message.role, text: message.text,
    waiting: message.task?.waiting ?? null, ownTask: message.task, boundary: message.boundary,
    at: new Date(message.at), replayed: true, outcome: message.outcome ?? undefined,
    ui: message.role === 'assistant' ? message.ui : null
  }))
  const incomingIds = new Set(mapped.map((entry) => entry.serverId))
  entries.value = older ? [...mapped, ...preserved.filter((entry) => !incomingIds.has(entry.serverId))]
    : [...preserved.filter((entry) => !incomingIds.has(entry.serverId)), ...mapped]
  const current = task.value
  if (current?.status === 'ACTIVE' && current.waiting != null) {
    const candidate = [...entries.value].reverse().find((entry) => entry.ownTask?.public_id === current.public_id
      && entry.waiting?.action_id === current.waiting?.action_id && entry.waiting?.expected_version === current.waiting?.expected_version)
    if (candidate !== undefined) {
      candidate.ownTask = current
      candidate.replayed = false
    } else {
      pushEntry('assistant', current.waiting.prompt, current.waiting)
      const added = entries.value[entries.value.length - 1]
      if (added !== undefined) added.serverId = `current:${current.public_id}:${current.version}`
    }
  }
  if (!older && current !== null) adoptProcessingTurn(current)
  if (!older && view.has_pending_request) resultPending.value = true
  if (!older) scrollToBottom()
}

const refreshConversation = async (): Promise<void> => {
  const order = ++viewRequestSequence
  try { applyConversation(await assistantApi.getConversation(), false, order) }
  catch { if (!disposed) historyError.value = '对话同步失败，已留下的内容仍保留，请重试同步。' }
}

const loadOlder = async (): Promise<void> => {
  if (olderCursor.value === null || submitting.value) return
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
  <div class="flex h-full min-h-0 flex-col">
    <div class="flex h-full min-h-0 flex-col">
    <div v-if="historyError" role="alert" class="mb-2 text-sm text-destructive">
      {{ historyError }}
      <Button variant="outline" size="sm" :disabled="submitting" @click="pendingConversation ? retryPending() : loadConversation()">重试同步</Button>
    </div>
    <div v-if="loadingConversation" role="status" class="mb-2 text-sm text-muted-foreground">正在恢复对话…</div>
    <div ref="scrollId" class="flex-1 space-y-3 overflow-y-auto pr-1">
      <Button v-if="olderCursor !== null" variant="ghost" size="sm" :disabled="submitting" @click="loadOlder">查看更早对话</Button>
      <div v-if="entries.length === 0 && !loadingConversation && !historyError" class="rounded-wolf-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
        发送一句话开始，例如「今天下午和睿狐科技开了个线上会议，聊了 POC 部署」。
      </div>

      <template v-for="entry in entries" :key="entry.id">
        <div v-if="entry.role === 'user'" class="flex justify-end">
          <div class="max-w-[75%] rounded-wolf-lg bg-primary px-3.5 py-2 text-sm text-primary-foreground">
            {{ entry.text }}
          </div>
        </div>
        <div v-else class="flex gap-2.5">
          <div class="mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg bg-[#dbeafe] text-[11px] font-semibold text-[#1d4ed8]">AI</div>
          <div class="min-w-0 max-w-[88%] flex-1 space-y-2">
            <AgentUIMessage
              v-if="entry.ui"
              :message="entry.ui"
              :disabled="busy"
              @interaction="(_actionId, values) => onAssistantInteraction(entry, values)"
            />
            <div v-else class="rounded-wolf-surface border bg-card px-3.5 py-2 text-sm text-foreground">这条结果暂时无法显示，原记录仍保留。</div>
            <div v-if="showActivityExtras(entry)" class="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" :disabled="busy" @click="focusComposer">修改内容</Button>
              <Button size="sm" variant="ghost" :disabled="busy" @click="() => { void changeKind(nextKindOf(entryTask(entry)?.activity_kind)) }">改为线下 / 跟进</Button>
            </div>
            <button
              v-if="showExplicitNone(entry)"
              type="button"
              class="text-xs text-muted-foreground underline-offset-2 hover:underline"
              :disabled="busy"
              @click="() => { void gapNone(entry) }"
            >这条没有下一步</button>
          </div>
        </div>
      </template>
    </div>

    <div v-if="processing.stages.length > 0" class="mt-2 rounded-wolf-surface border border-border bg-white px-3.5 py-3">
      <div class="mb-2 flex items-center justify-between gap-2 text-[13px] font-semibold">
        <span>执行过程</span>
        <span class="rounded-full border border-[#bfdbfe] bg-[#eff6ff] px-2 py-0.5 text-[11px] font-medium text-[#1d4ed8]">{{ processing.active ? '处理中' : '已更新' }}</span>
      </div>
      <div v-for="stageItem in processing.stages" :key="stageItem.name" class="flex items-center gap-2 py-0.5 text-sm" :class="stageItem.status === 'done' ? 'text-emerald-700' : stageItem.status === 'running' ? 'font-medium text-[#1d4ed8]' : 'text-muted-foreground'">
        <span class="size-2 shrink-0 rounded-full border-2" :class="stageItem.status === 'done' ? 'border-emerald-600 bg-emerald-600' : stageItem.status === 'running' ? 'border-[#2563eb] bg-white' : 'border-border'"></span>
        <span>{{ STAGE_LABELS[stageItem.name] }}</span>
        <span v-if="stageItem.status === 'done' && stageItem.ms !== undefined" class="text-xs text-muted-foreground">{{ (stageItem.ms / 1000).toFixed(1) }}s</span>
        <span v-if="stageItem.status === 'done' && stageItem.score !== undefined" class="rounded-wolf-md border bg-muted/50 px-1.5 text-[11px] text-success">{{ stageItem.score }} 分</span>
        <span v-if="stageItem.status === 'running'" class="text-xs font-normal text-muted-foreground">进行中…</span>
      </div>
    </div>

    <div class="mt-3 rounded-wolf-lg border bg-background p-2.5 shadow-sm" :class="{ 'border-2 border-primary/60': isWaiting }">
      <div v-if="processing.active || routing || recoveryNotice" class="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-primary">
        <svg v-if="routing || processing.active || autoRecovering" class="size-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-9-9"/><path d="M21 3v9h-9"/></svg>
        <span>{{ routing ? '正在理解这次沟通…' : (recoveryNotice || processingHint) }}</span>
      </div>
      <Textarea
        aria-label="客户沟通内容"
        v-model="inputText"
        :rows="2"
        :disabled="loadingConversation || submitting || resultPending || conversation?.pending_choice != null"
        :placeholder="inputPlaceholder"
        class="resize-none border-0 p-0 focus-visible:ring-0"
        @keydown.enter.exact.prevent="submitText"
      />
      <div class="mt-2 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <Badge v-if="task?.activity_kind" variant="secondary">{{ task.activity_kind === 'ONLINE_MEETING' ? '线上会议' : task.activity_kind === 'OFFLINE_MEETING' ? '线下会议' : '跟进' }}</Badge>
          <span class="text-xs text-muted-foreground">Enter 发送 · Shift+Enter 换行</span>
        </div>
        <div class="flex items-center gap-2">
          <Button v-if="showSyncResult" size="sm" variant="outline" :disabled="submitting" @click="syncResult">同步结果</Button>
          <Button v-if="showReprocess" size="sm" variant="outline" :disabled="submitting" @click="reprocessTurn">重新处理</Button>
          <Button v-if="showConversationRetry" size="sm" variant="outline" :disabled="submitting" @click="retryPending">重试同步</Button>
          <Button v-if="(!isTerminal && task !== null) || conversation?.pending_choice != null" size="sm" variant="ghost" :disabled="busy || resultPending" @click="cancelTask()">
            <X class="size-3.5" />算了
          </Button>
          <Button aria-label="发送" size="icon-sm" :disabled="loadingConversation || busy || resultPending || conversation?.pending_choice != null" @click="submitText">
            <ArrowUp class="size-4" />
          </Button>
        </div>
      </div>
    </div>
    </div>
  </div>
</template>
