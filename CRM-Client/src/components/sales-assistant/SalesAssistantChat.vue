<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, shallowRef } from 'vue'
import { isAxiosError } from 'axios'
import { ArrowUp, CircleHelp, X } from 'lucide-vue-next'
import { assistantApi, submitInputStream, type StageName } from '@/api/assistant'
import type { SubmitAssistantInput } from '@/api/assistant'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import ConfirmationCard from './ConfirmationCard.vue'
import MeetingConfirmationCard from './MeetingConfirmationCard.vue'
import ProposalCard from './ProposalCard.vue'
import GapCard from './GapCard.vue'
import FailureCard from './FailureCard.vue'
import { type AssistantTaskView, type ProposalConfirmation, type TaskWaiting, type ConversationView, type ConversationReply, type ConversationBoundary } from '@/schemas/assistant-contracts'

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
const currentWaitEntryId = ref<number | null>(null)
const conversation = shallowRef<ConversationView | null>(null)
const loadingConversation = ref(true)
const historyError = ref('')
const routing = ref(false)
const olderCursor = ref<number | null>(null)
const pendingConversation = shallowRef<(() => Promise<ConversationReply>) | null>(null)
const unacceptedText = ref('')

const FIELD_LABELS: Record<string, string> = {
  customer: '客户名称',
  content: '沟通内容',
  next_action: '下一步行动',
  next_follow_time: '下次跟进时间'
}

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

const isTaskLive = computed(() => task.value?.status === 'ACTIVE')

const waiting = computed<TaskWaiting | null>(() => task.value?.waiting ?? null)
const isWaiting = computed(() => waiting.value !== null)
const isTerminal = computed(() => task.value != null && task.value.status !== 'ACTIVE')



const inputPlaceholder = computed(() => {
  if (isWaiting.value && waiting.value?.type === 'FIELD') return waiting.value.prompt ?? ''
  return '描述一次客户沟通，我来整理成跟进或会议纪要…'
})

const kindOptions = [
  { value: 'ONLINE_MEETING', label: '线上会议', hint: '远程沟通' },
  { value: 'OFFLINE_MEETING', label: '线下会议', hint: '面谈拜访' },
  { value: 'FOLLOW_UP', label: '普通跟进', hint: '电话/微信' }
]

const pushEntry = (
  role: 'user' | 'assistant',
  text: string,
  entryWaiting: TaskWaiting | null = null,
  replayed = false
): void => {
  seq.value += 1
  entries.value.push({ id: seq.value, role, text, waiting: entryWaiting, replayed, at: new Date(), ownTask: task.value })
  if (entryWaiting !== null && !replayed) currentWaitEntryId.value = seq.value
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

const fieldLabel = computed(() => {
  if (waiting.value?.type === 'OBJECT_SELECTION') return '选择客户'
  if (waiting.value?.type === 'ACTIVITY_KIND') return '活动类型'
  if (waiting.value?.type === 'CONFIRMATION') return '确认操作'
  const field = waiting.value?.field ?? ''
  if (field !== '' && field.startsWith('proposal:')) return field.slice('proposal:'.length)
  return FIELD_LABELS[field] ?? field
})

const processingHint = computed(() => {
  if (!processing.value.active) return ''
  const base = 'Agent 正在处理，通常需要 30–60 秒…'
  if (elapsedSeconds.value >= 60) return `${base}（已 ${elapsedSeconds.value} 秒 · 内容已保存，刷新后可继续）`
  if (elapsedSeconds.value >= 15) return `${base}（已 ${elapsedSeconds.value} 秒 · 内容不会丢失，请稍候）`
  return base
})
const pendingRequest = shallowRef<{ input: SubmitAssistantInput; targetId: string; displayText: string; turnId: string; cursor: number } | null>(null)
const processingRecovery = shallowRef<{ targetId: string; turnId: string; cursor: number } | null>(null)

const adoptProcessingTurn = (updated: AssistantTaskView): void => {
  if (updated.processing_turn_id != null && (updated.processing_turn_status === 'PENDING' || updated.processing_turn_status === 'RUNNING')) {
    const recovery = processingRecovery.value
    if (recovery === null || recovery.turnId !== updated.processing_turn_id || recovery.targetId !== updated.public_id) {
      processingRecovery.value = { targetId: updated.public_id, turnId: updated.processing_turn_id, cursor: 0 }
    }
    resultPending.value = true
  } else if (processingRecovery.value?.targetId === updated.public_id) {
    processingRecovery.value = null
    resultPending.value = false
  }
}

const recoverProcessingTurn = async (restart = false, watch = restart): Promise<void> => {
  const pending = processingRecovery.value
  const navigation = navigationVersion
  if (pending === null) return
  const active = (): boolean => !disposed && navigation === navigationVersion && processingRecovery.value === pending && task.value?.public_id === pending.targetId
  try {
    let turn = await assistantApi.getTurn(pending.targetId, pending.turnId, pending.cursor)
    if (!active()) return
    if (restart && (turn.status === 'PENDING' || turn.status === 'RUNNING')) {
      beginProcessing(pendingRequest.value?.input ?? { kind: 'text' }, task.value?.waiting != null)
      turn = await assistantApi.retryTurn(pending.targetId, pending.turnId, turn.lease_version, pending.cursor)
    }
    while (active()) {
      pending.cursor = Math.max(pending.cursor, ...turn.events.map((event) => event.seq))
      let reply: string | undefined
      for (const event of turn.events) {
        if (event.event === 'waiting' && typeof event.data['message'] === 'string') reply = event.data['message']
        if (event.event === 'error') {
          pushEntry('assistant', typeof event.data['message'] === 'string' ? event.data['message'] : '处理失败')
          const entry = entries.value[entries.value.length - 1]
          if (entry !== undefined) entry.outcome = 'failure'
        }
      }
      publishTask(turn.task, reply)
      if (processingRecovery.value === pending && (turn.status === 'SUCCEEDED' || turn.status === 'FAILED')) {
        processingRecovery.value = null
        resultPending.value = false
      }
      if (!resultPending.value && pendingRequest.value?.targetId === pending.targetId) pendingRequest.value = null
      await refreshConversation()
      if (disposed || navigation !== navigationVersion) return
      if (processingRecovery.value !== null && processingRecovery.value !== pending) {
        await recoverProcessingTurn(false, watch)
        return
      }
      if (!watch || !active()) return
      await new Promise<void>((resolve) => { setTimeout(resolve, 1000) })
      if (!active()) return
      turn = await assistantApi.getTurn(pending.targetId, pending.turnId, pending.cursor)
    }
  } catch {
    if (active()) {
      resultPending.value = true
      if (restart) pushEntry('assistant', '连接中断，处理结果待确认，正在同步任务状态。')
    }
  } finally {
    if (restart && navigation === navigationVersion) endProcessing()
  }
}
const resultPending = ref(false)

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
  try {
    resultPending.value = false
    const pending = { input: request, targetId, displayText, turnId: '', cursor: 0 }
    pendingRequest.value = pending
    beginProcessing(request, task.value?.waiting != null)
    const active = (): boolean => !disposed && navigation === navigationVersion && pendingRequest.value === pending
    let turnId = ''
    let cursor = 0
    let delivered = false
    let disconnected = false
    await submitInputStream(targetId, request, {
      onAccepted: (id, seq) => {
        if (!active()) return
        turnId = id
        cursor = Math.max(cursor, seq ?? 0)
        if (pendingRequest.value !== null) { pendingRequest.value.turnId = id; pendingRequest.value.cursor = cursor }
      },
      onStage: (event) => {
        if (!active()) return
        cursor = Math.max(cursor, event.seq ?? 0)
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
      onNetworkLost: () => { if (active()) disconnected = true }
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
    if (disconnected || !delivered) {
      resultPending.value = true
      pushEntry('assistant', '连接中断，处理结果待确认，正在同步任务状态。')
      try {
        if (turnId !== '') {
          const turn = await assistantApi.getTurn(targetId, turnId, cursor)
          if (!active()) return
          for (const event of turn.events) {
            cursor = Math.max(cursor, event.seq)
            if (event.event === 'stage') {
              const stage = event.data['stage']
              const phase = event.data['phase']
              if ((stage === 'classify' || stage === 'structure' || stage === 'quality_gate' || stage === 'write')
                && (phase === 'start' || phase === 'done')) applyStageEvent({ stage, phase })
            }
          }
          publishTask(turn.task)
          resultPending.value = processingRecovery.value !== null || turn.status === 'PENDING' || turn.status === 'RUNNING'
        } else {
          const latest = await assistantApi.getTask(targetId)
          if (!active()) return
          publishTask(latest)
          resultPending.value = true
        }
      } catch {
        // Keep the request ID for an idempotent retry; never claim it was not submitted.
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
      if (processingRecovery.value !== null) await recoverProcessingTurn()
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

const pickKind = (choice: string, source: TaskWaiting | null): Promise<void> =>
  submit({ kind: 'submit_field', choice }, KIND_LABELS[choice] ?? source?.candidates?.find((candidate) => candidate.id === choice)?.account_name ?? '选择客户', source)

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

const retryPending = async (): Promise<void> => {
  if (submitting.value) return
  if (conversation.value?.has_pending_request === true && pendingConversation.value === null) {
    await dispatchConversation(() => assistantApi.resumeConversation(), '')
    return
  }
  if (processingRecovery.value !== null) {
    if (submitting.value) return
    submitting.value = true
    const navigation = navigationVersion
    try { await recoverProcessingTurn(true) } finally { if (navigation === navigationVersion) submitting.value = false }
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
      if (processingRecovery.value !== null) {
        await recoverProcessingTurn(true)
        return
      }
      if ((turn.status === 'SUCCEEDED' || turn.status === 'FAILED') && processingRecovery.value === null) {
        resultPending.value = false
        pendingRequest.value = null
        return
      }
      processingRecovery.value = { targetId: pending.targetId, turnId: pending.turnId, cursor: pending.cursor }
      await recoverProcessingTurn(true)
      return
    } else {
      const latest = await assistantApi.getTask(pending.targetId)
      if (disposed || navigation !== navigationVersion || task.value?.public_id !== pending.targetId || pendingRequest.value !== pending) return
      publishTask(latest)
      if (processingRecovery.value !== null) {
        await recoverProcessingTurn(true)
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
  if (submitting.value || resultPending.value || !isCurrentWait(entry)) return Promise.resolve()
  explicitNone.value = true
  return Promise.resolve()
}


const busy = computed(() => submitting.value || resultPending.value)

const formatHHmm = (value: Date | string | undefined): string => {
  if (value === undefined) return ''
  const parsed = typeof value === 'string' ? new Date(value) : value
  if (Number.isNaN(parsed.getTime())) return ''
  return `${String(parsed.getHours()).padStart(2, '0')}:${String(parsed.getMinutes()).padStart(2, '0')}`
}
const entryTask = (entry: ChatEntry): AssistantTaskView | null => entry.ownTask ?? null

const isCurrentWait = (entry: ChatEntry): boolean =>
  entry.id === currentWaitEntryId.value && entryTask(entry)?.public_id === task.value?.public_id && entry.waiting !== null && task.value?.status === 'ACTIVE'
  && task.value.waiting?.question_id === entry.waiting.question_id
  && task.value.waiting?.action_id === entry.waiting.action_id
  && task.value.waiting?.expected_version === entry.waiting.expected_version


const cardKind = (entry: ChatEntry): 'confirm' | 'meeting' | 'proposal' | 'gap' | 'kind' | 'customer' | 'failure' | 'none' => {
  if (entry.outcome === 'failure') return 'failure'
  const settledConfirmation = entry.waiting?.type === 'CONFIRMATION' && !isCurrentWait(entry)
  const w = (isCurrentWait(entry) || entry.replayed || settledConfirmation) ? entry.waiting : null
  if (w === null) return 'none'
  if (w.type === 'CONFIRMATION' && w.confirmation_payload?.kind === 'activity_write') {
    const kind = w.confirmation_payload.preview.activity_kind
    return kind === 'ONLINE_MEETING' || kind === 'OFFLINE_MEETING' ? 'meeting' : 'confirm'
  }
  if (w.type === 'CONFIRMATION' && w.confirmation_payload?.kind === 'proposal') return 'proposal'
  if (w.type === 'ACTIVITY_KIND') return 'kind'
  if (w.type === 'OBJECT_SELECTION') return 'customer'
  if (w.type === 'FIELD') return 'gap'
  return 'none'
}

const proposalOf = (entry: ChatEntry): ProposalConfirmation | null =>
  entry.waiting?.confirmation_payload?.kind === 'proposal' ? entry.waiting.confirmation_payload : null

const proposalOutcome = (entry: ChatEntry): 'accepted' | 'refused' | undefined => {
  const proposal = proposalOf(entry)
  if (proposal === null) return undefined
  const receipt = entryTask(entry)?.committed.find((item) => 'proposal_key' in item && item.proposal_key === proposal.candidate.key)
  if (receipt === undefined) return undefined
  return receipt.kind === `refused:${proposal.proposal_kind}` ? 'refused' : 'accepted'
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
    at: new Date(message.at), replayed: true, outcome: message.outcome ?? undefined
  }))
  const incomingIds = new Set(mapped.map((entry) => entry.serverId))
  entries.value = older ? [...mapped, ...preserved.filter((entry) => !incomingIds.has(entry.serverId))]
    : [...preserved.filter((entry) => !incomingIds.has(entry.serverId)), ...mapped]
  currentWaitEntryId.value = null
  const current = task.value
  if (current?.status === 'ACTIVE' && current.waiting != null) {
    const candidate = [...entries.value].reverse().find((entry) => entry.ownTask?.public_id === current.public_id
      && entry.waiting?.action_id === current.waiting?.action_id && entry.waiting?.expected_version === current.waiting?.expected_version)
    if (candidate !== undefined) {
      candidate.ownTask = current
      candidate.replayed = false
      currentWaitEntryId.value = candidate.id
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
          <div class="mt-1 size-7 shrink-0 place-items-center rounded-wolf-md bg-muted text-[11px] font-medium text-muted-foreground grid">AI</div>
          <div class="min-w-0 max-w-[88%] flex-1 space-y-2">
            <div v-if="entry.boundary" class="overflow-hidden rounded-wolf-lg border bg-card shadow-sm">
              <div class="flex items-center gap-2 border-b bg-muted/30 px-4 py-3 text-sm font-medium"><CircleHelp class="size-5 shrink-0 rounded-full bg-warning/10 p-0.5 text-warning" />{{ entry.boundary.prompt }}</div>
              <div class="grid grid-cols-1 gap-2 p-4 sm:grid-cols-2">
                <Button variant="outline" :disabled="submitting || resultPending || conversation?.pending_choice?.entry_id !== entry.boundary.entry_id" @click="chooseBoundary(entry, 'CONTINUE')">接着刚才</Button>
                <Button variant="outline" :disabled="submitting || resultPending || conversation?.pending_choice?.entry_id !== entry.boundary.entry_id" @click="chooseBoundary(entry, 'NEW')">另记一件</Button>
              </div>
            </div>
            <div
              v-else-if="cardKind(entry) === 'none' || cardKind(entry) === 'gap'"
              class="rounded-wolf-lg border bg-card px-3.5 py-2 text-sm shadow-sm"
            >
              {{ entry.text }}
              <span v-if="entry.outcome === 'activity_written'" class="ml-2 inline-flex items-center rounded-wolf-md bg-success/10 px-1.5 py-0.5 align-middle text-[11px] text-success">已写入</span>
              <span v-if="entry.outcome === 'activity_written' && formatHHmm(entry.at) !== ''" class="ml-1 text-[11px] text-muted-foreground">{{ formatHHmm(entry.at) }}</span>
            </div>

            <GapCard
              v-if="cardKind(entry) === 'gap' && entry.waiting !== null"
              :task="entryTask(entry)"
              :prompt="entry.waiting.prompt"
              :field="entry.waiting.field ?? entry.waiting.type"
              :replayed="!isCurrentWait(entry)"
              @none="() => { void gapNone(entry) }"
            />

            <div
              v-if="cardKind(entry) === 'kind'"
              class="w-full overflow-hidden rounded-wolf-lg border bg-card shadow-sm"
            >
              <div class="flex items-center justify-between gap-2 border-b bg-muted/40 px-4 py-3">
                <div class="flex min-w-0 items-center gap-2">
                  <span class="grid size-6 shrink-0 place-items-center rounded-wolf-md bg-warning/15 text-warning">
                    <svg class="size-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
                  </span>
                  <span class="text-sm font-medium">这条记录属于哪种活动？</span>
                </div>
                <button
                  v-if="isCurrentWait(entry)"
                  type="button"
                  class="shrink-0 text-xs text-muted-foreground underline-offset-2 hover:underline"
                  :disabled="busy"
                  @click="() => { void cancelTask(entry.waiting) }"
                >算了，不记了</button>
              </div>
              <div class="px-4 py-3">
                <p class="text-xs text-muted-foreground">选错也没关系，确认写入前可以改。</p>
                <div class="mt-3 grid grid-cols-3 gap-2">
                  <Button
                    v-for="option in kindOptions"
                    :key="option.value"
                    variant="outline"
                    :disabled="busy || !isCurrentWait(entry) || waiting?.type !== 'ACTIVITY_KIND'"
                    class="h-auto flex-col py-2"
                    @click="() => { void pickKind(option.value, entry.waiting) }"
                  >
                    <span>{{ option.label }}</span>
                    <span class="text-[11px] text-muted-foreground">{{ option.hint }}</span>
                  </Button>
                </div>
              </div>
            </div>

            <div v-if="cardKind(entry) === 'customer' && entry.waiting" class="w-full rounded-wolf-lg border bg-card shadow-sm">
              <div class="border-b bg-muted/40 px-4 py-3 text-sm font-medium">{{ entry.waiting.prompt }}</div>
              <div class="grid gap-2 px-4 py-3">
                <Button
                  v-for="candidate in entry.waiting.candidates ?? []"
                  :key="candidate.id"
                  variant="outline"
                  class="h-auto justify-start py-2 text-left"
                  :disabled="busy || resultPending || !isCurrentWait(entry)"
                  @click="() => { void pickKind(candidate.id, entry.waiting) }"
                >{{ candidate.account_name }}</Button>
              </div>
            </div>

            <p v-if="isCurrentWait(entry) && entry.waiting?.type === 'CONFIRMATION'" class="text-xs text-muted-foreground">{{ entry.waiting.prompt }}</p>
            <MeetingConfirmationCard
              v-if="cardKind(entry) === 'meeting' && entry.waiting !== null && entry.ownTask != null"
              :task="entry.ownTask"
              :waiting="entry.waiting"
              :replayed="!isCurrentWait(entry)"
              :busy="busy"
              @confirm="() => { void confirmWrite(entry.waiting) }"
              @reject="() => { void rejectWrite(entry.waiting) }"
              @request-edit="focusComposer"
              @change-kind="() => { void changeKind(nextKindOf(entryTask(entry)?.activity_kind)) }"
            />

            <ConfirmationCard
              v-if="cardKind(entry) === 'confirm' && entry.waiting !== null && entry.ownTask != null"
              :task="entry.ownTask"
              :waiting="entry.waiting"
              :replayed="!isCurrentWait(entry)"
              :busy="busy"
              @confirm="() => { void confirmWrite(entry.waiting) }"
              @reject="() => { void rejectWrite(entry.waiting) }"
              @request-edit="focusComposer"
              @change-kind="() => { void changeKind(nextKindOf(entryTask(entry)?.activity_kind)) }"
            />

            <ProposalCard
              v-if="cardKind(entry) === 'proposal' && entry.waiting?.confirmation_payload?.kind === 'proposal'"
              :proposal="entry.waiting.confirmation_payload"
              :prompt="entry.waiting?.prompt ?? ''"
              :customer-name="(entryTask(entry) ?? task)?.draft.customer.value ?? ''"
              :outcome="proposalOutcome(entry)"
              :replayed="!isCurrentWait(entry)"
              :busy="busy"
              @accept="() => { void confirmWrite(entry.waiting) }"
              @refuse="() => { void rejectWrite(entry.waiting) }"
            />

            <FailureCard
              v-if="cardKind(entry) === 'failure'"
              :message="entry.text"
              :waiting="entry.waiting"
              :replayed="entry.replayed || !isTaskLive"
              :busy="busy"
              @retry="focusComposer"
              @abort="cancelTask()"
            />
          </div>
        </div>
      </template>
    </div>

    <div v-if="processing.active && processing.stages.length > 0" class="mt-2 rounded-wolf-lg border bg-card px-3.5 py-3 shadow-sm">
      <div v-for="stageItem in processing.stages" :key="stageItem.name" class="flex items-center gap-2 py-0.5 text-sm" :class="stageItem.status === 'done' ? 'text-muted-foreground' : stageItem.status === 'running' ? 'font-medium' : 'text-muted-foreground'">
        <svg v-if="stageItem.status === 'done'" class="size-4 shrink-0 text-success" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6 9 17l-5-5"/></svg>
        <svg v-else-if="stageItem.status === 'running'" class="size-4 shrink-0 animate-spin text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-9-9"/><path d="M21 3v9h-9"/></svg>
        <span v-else class="size-4 shrink-0 rounded-full border"></span>
        <span>{{ STAGE_LABELS[stageItem.name] }}</span>
        <span v-if="stageItem.status === 'done' && stageItem.ms !== undefined" class="text-xs text-muted-foreground">{{ (stageItem.ms / 1000).toFixed(1) }}s</span>
        <span v-if="stageItem.status === 'done' && stageItem.score !== undefined" class="rounded-wolf-md border bg-muted/50 px-1.5 text-[11px] text-success">{{ stageItem.score }} 分</span>
        <span v-if="stageItem.status === 'running'" class="text-xs font-normal text-muted-foreground">进行中…</span>
      </div>
    </div>

    <div class="mt-3 rounded-wolf-lg border bg-background p-2.5 shadow-sm" :class="{ 'border-2 border-primary/60': isWaiting }">
      <div v-if="isWaiting" class="mb-1.5 flex items-center justify-between text-xs font-medium text-primary">
        <span>正在回答：{{ fieldLabel || waiting?.type }}</span>
      </div>
      <div v-else-if="processing.active || routing" class="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-primary">
        <svg class="size-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-9-9"/><path d="M21 3v9h-9"/></svg>
        <span>{{ routing ? '正在理解这次沟通…' : processingHint }}</span>
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
          <Button v-if="resultPending && (pendingRequest || pendingConversation || processingRecovery || conversation?.has_pending_request)" size="sm" variant="outline" :disabled="submitting" @click="retryPending">重试同步</Button>
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
