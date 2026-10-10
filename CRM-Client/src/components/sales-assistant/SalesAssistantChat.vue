<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, shallowRef, watch } from 'vue'
import { SendHorizontal, X } from 'lucide-vue-next'
import { assistantApi, submitInputStream, type StageName } from '@/api/assistant'
import type { SubmitAssistantInput } from '@/api/assistant'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import AssistantTaskSidebar from './AssistantTaskSidebar.vue'
import ConfirmationCard from './ConfirmationCard.vue'
import MeetingConfirmationCard from './MeetingConfirmationCard.vue'
import ProposalCard from './ProposalCard.vue'
import GapCard from './GapCard.vue'
import FailureCard from './FailureCard.vue'
import { ConfirmationPayloadSchema, type AssistantTaskView, type ProposalConfirmation, type TaskWaiting } from '@/schemas/assistant-contracts'

interface ChatEntry {
  id: number
  role: 'user' | 'assistant'
  text: string
  waiting: TaskWaiting | null
  at?: Date | undefined
  /** Historical messages never hold authoritative task state or interactive cards. */
  replayed: boolean
  outcome?: 'activity_written' | 'failure' | undefined
}

const task = ref<AssistantTaskView | null>(null)
const recentTasks = ref<AssistantTaskView[]>([])
const recentTasksWarning = ref('')
let disposed = false
let navigationVersion = 0
onUnmounted(() => { disposed = true; if (elapsedTimer !== null) clearInterval(elapsedTimer) })

const loadRecentTasks = async (): Promise<void> => {
  try {
    const result = await assistantApi.listTasks()
    if (disposed) return
    recentTasks.value = result.tasks
    recentTasksWarning.value = result.skipped.length > 0 ? `${result.skipped.length} 条历史任务无法识别，已跳过。` : ''
  } catch {
    if (!disposed) {
      recentTasks.value = []
      recentTasksWarning.value = '最近任务加载失败。'
    }
  }
}

const resumeActiveTask = async (): Promise<void> => {
  const navigation = navigationVersion
  try {
    const active = await assistantApi.latestActiveTask()
    if (!disposed && navigation === navigationVersion && active !== null && active !== undefined) {
      task.value = active
      pushEntry('assistant', active.waiting?.prompt ?? active.goal, active.waiting ?? null)
      adoptProcessingTurn(active)
      if (processingRecovery.value !== null) await recoverProcessingTurn()
    }
  } catch {
    /* No task is displayed until the authoritative lookup succeeds. */
  }
}

void resumeActiveTask().then(() => { void loadRecentTasks() })

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

const resetTask = (): void => {
  task.value = null
  navigationVersion += 1
  pendingRequest.value = null
  pendingCreation.value = null
  resultPending.value = false
  processingRecovery.value = null
  currentWaitEntryId.value = null
  entries.value = []
  seq.value = 0
  inputText.value = ''
  editingDraft.value = false
  explicitNone.value = false
  endProcessing()
  void loadRecentTasks()
}

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

const isTaskLive = computed(() => task.value?.status === 'ACTIVE')

const pushReplayEntry = (role: 'user' | 'assistant', text: string, atIso: string): ChatEntry => {
  seq.value += 1
  const entry: ChatEntry = {
    id: seq.value,
    role,
    text,
    waiting: null,
    replayed: true,
    at: new Date(atIso)
  }
  entries.value.push(entry)
  return entry
}

const openTask = async (publicId: string): Promise<void> => {
  const navigation = ++navigationVersion
  try {
    const [loaded, actions] = await Promise.all([
      assistantApi.getTask(publicId),
      assistantApi.listTaskActions(publicId)
    ])
    if (disposed || navigation !== navigationVersion) return
    pendingRequest.value = null
    processingRecovery.value = null
    submitting.value = false
    endProcessing()
    pendingCreation.value = null
    resultPending.value = false
    task.value = loaded
    entries.value = []
    seq.value = 0
    currentWaitEntryId.value = null
    pushEntry('user', loaded.goal)
    for (const action of actions) {
      if (action.actor === 'USER' && action.action === 'submit_field') {
        const field = typeof action.input['field'] === 'string' ? action.input['field'] : ''
        const text = typeof action.input['text'] === 'string' ? action.input['text'] : ''
        const choice = typeof action.input['choice'] === 'string' ? action.input['choice'] : ''
        const fallback = choice !== ''
          ? KIND_LABELS[choice] ?? choice
          : `（补充${FIELD_LABELS[field] ?? field}）`
        if (text !== '' || choice !== '' || field !== '') {
          pushEntry('user', text !== '' ? text : fallback, null, true)
        }
      } else if (action.action === 'select_activity_kind') {
        const kind = typeof action.input['kind'] === 'string' ? action.input['kind'] : ''
        if (kind !== '') pushEntry('user', KIND_LABELS[kind] ?? kind, null, true)
      } else if (action.action === 'ask_activity_kind') {
        const prompt = typeof action.result['prompt'] === 'string' && action.result['prompt'] !== ''
          ? action.result['prompt']
          : '这条记录属于哪种活动？'
        pushEntry('assistant', prompt, {
          type: 'ACTIVITY_KIND',
          field: 'activity_kind',
          question_id: `replay_${action.created_time}`,
          prompt
        }, true)
      } else if (action.action === 'ask_field' || action.action === 'ask_quality_gap' || action.action === 'ask_customer_name') {
        const field = typeof action.input['field'] === 'string' ? action.input['field'] : ''
        const prompt = typeof action.result['prompt'] === 'string' && action.result['prompt'] !== ''
          ? action.result['prompt']
          : `请补充${FIELD_LABELS[field] ?? '关键信息'}。`
        pushEntry('assistant', prompt, {
          type: 'FIELD',
          field,
          question_id: `replay_${action.created_time}`,
          prompt
        }, true)
      } else if (action.action === 'ask_confirmation' || action.action === 'offer_proposal') {
        const prompt = typeof action.result['prompt'] === 'string' && action.result['prompt'] !== ''
          ? action.result['prompt']
          : '请确认。'
        const field = typeof action.result['field'] === 'string' && action.result['field'] !== ''
          ? action.result['field']
          : action.action === 'ask_confirmation' ? 'activity_write' : ''
        pushEntry('assistant', prompt, field === 'activity_write'
          ? { type: 'CONFIRMATION', field, question_id: `replay_${action.created_time}`, prompt }
          : null, true)
      } else if (action.action === 'reject_confirmation') {
        pushEntry('user', '取消', null, true)
      } else if (action.action === 'refuse_proposal') {
        pushEntry('user', '暂不处理', null, true)
      } else if (action.action === 'accept_proposal') {
        pushEntry('user', '确认', null, true)
      } else if (action.action === 'cancel_task') {
        pushEntry('assistant', '已取消本次任务。', null, true)
      } else if (action.event_type === 'meeting_card' || action.event_type === 'follow_up_card') {
        const confirmation = action.result['confirmation']
        const snapshot = typeof confirmation === 'object' && confirmation !== null ? confirmation as { prompt?: unknown; confirmation_payload?: unknown } : null
        const payloadParse = ConfirmationPayloadSchema.safeParse(snapshot?.confirmation_payload)
        const prompt = typeof snapshot?.prompt === 'string' && snapshot.prompt !== '' ? snapshot.prompt : '确认后写入这条客户活动？'
        pushEntry('assistant', prompt, {
          type: 'CONFIRMATION', field: 'activity_write', question_id: `replay_${action.created_time}`, prompt,
          ...(payloadParse.success && payloadParse.data.kind === 'activity_write' ? { confirmation_payload: payloadParse.data } : {}),
        }, true)
      } else if (action.event_type === 'user_choice') {
        pushEntry('user', String(action.result['label'] ?? '确认'), null, true)
      } else if (action.event_type === 'receipt') {
        const receipt = pushReplayEntry('assistant', String(action.result['label'] ?? '已记录这条客户活动。'), action.created_time)
        receipt.outcome = 'activity_written'
        void receipt
      } else if (action.action === 'confirm_write' && action.event_type == null) {
        const confirmation = action.result['confirmation']
        const snapshot = typeof confirmation === 'object' && confirmation !== null
          ? confirmation as { prompt?: unknown; confirmation_payload?: unknown }
          : null
        const payloadParse = ConfirmationPayloadSchema.safeParse(snapshot?.confirmation_payload)
        const prompt = typeof snapshot?.prompt === 'string' && snapshot.prompt !== '' ? snapshot.prompt : '确认后写入这条客户活动？'
        pushEntry('assistant', prompt, {
          type: 'CONFIRMATION', field: 'activity_write', question_id: `replay_${action.created_time}`, prompt,
          ...(payloadParse.success && payloadParse.data.kind === 'activity_write' ? { confirmation_payload: payloadParse.data } : {}),
        }, true)
        const receipt = pushReplayEntry('assistant', '已记录这条客户活动。', action.created_time)
        receipt.outcome = 'activity_written'
        void receipt
      }
    }
    // The projection, not the action log, determines the only current wait.
    if (loaded.status === 'ACTIVE' && loaded.waiting !== null && loaded.waiting !== undefined) {
      pushEntry('assistant', loaded.waiting.prompt, loaded.waiting)
    }
    adoptProcessingTurn(loaded)
    if (processingRecovery.value !== null) await recoverProcessingTurn()
  } catch {
    if (disposed || navigation !== navigationVersion) return
    submitting.value = false
    endProcessing()
    pushEntry('assistant', '未打开目标任务，当前任务已保留，请重试。')
  }
}

const waiting = computed<TaskWaiting | null>(() => task.value?.waiting ?? null)
const isWaiting = computed(() => waiting.value !== null)
const isTerminal = computed(() => task.value != null && task.value.status !== 'ACTIVE')



const inputPlaceholder = computed(() => {
  if (isWaiting.value && waiting.value?.type === 'FIELD') return waiting.value.prompt ?? ''
  if (isWaiting.value && waiting.value?.type === 'ACTIVITY_KIND') return '请在上方选择活动类型'
  if (isWaiting.value && waiting.value?.type === 'CONFIRMATION') return '请在上方确认或取消'
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
  entries.value.push({ id: seq.value, role, text, waiting: entryWaiting, replayed, at: new Date() })
  if (entryWaiting !== null && !replayed) currentWaitEntryId.value = seq.value
}

const scrollId = ref<HTMLElement | null>(null)
const scrollToBottom = (): void => {
  void nextTick(() => {
    scrollId.value?.scrollTo?.({ top: scrollId.value.scrollHeight })
  })
}
watch(entries, scrollToBottom, { deep: true })

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
  if (elapsedSeconds.value >= 60) return `${base}（已 ${elapsedSeconds.value} 秒 · 任务已持久化，刷新不丢，可稍后在最近任务中继续）`
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

const recoverProcessingTurn = async (): Promise<void> => {
  const pending = processingRecovery.value
  const navigation = navigationVersion
  if (pending === null) return
  try {
    const turn = await assistantApi.getTurn(pending.targetId, pending.turnId, pending.cursor)
    if (disposed || navigation !== navigationVersion || processingRecovery.value !== pending || task.value?.public_id !== pending.targetId) return
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
    if (processingRecovery.value !== null && processingRecovery.value !== pending) await recoverProcessingTurn()
  } catch {
    // The active turn is already persisted; recovery is GET-only even after failure.
    if (!disposed && navigation === navigationVersion && processingRecovery.value === pending) resultPending.value = true
  }
}
const pendingCreation = ref<{ createRequestId: string; input: SubmitAssistantInput; displayText: string } | null>(null)
const resultPending = ref(false)

const publishTask = (updated: AssistantTaskView, message?: string): void => {
  if (disposed || updated === undefined || (task.value !== null && task.value.public_id !== updated.public_id)) return
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
const submit = async (input: SubmitAssistantInput, displayText: string, sourceWaiting: TaskWaiting | null = null, recovery: typeof pendingCreation.value = null): Promise<void> => {
  const navigation = navigationVersion
  if (submitting.value || (resultPending.value && recovery === null)) return
  const current = task.value
  if (sourceWaiting !== null && (current?.waiting?.question_id !== sourceWaiting.question_id
    || current.waiting.action_id !== sourceWaiting.action_id
    || current.waiting.expected_version !== sourceWaiting.expected_version)) return
  submitting.value = true
  if (recovery === null) pushEntry('user', displayText)
  const request: SubmitAssistantInput = recovery?.input ?? {
    ...input,
    client_request_id: crypto.randomUUID(),
    ...(sourceWaiting?.action_id !== null && sourceWaiting?.action_id !== undefined ? { action_id: sourceWaiting.action_id } : {}),
    ...(sourceWaiting?.expected_version != null ? { expected_version: sourceWaiting.expected_version } : {})
  }
  try {
    let targetId = current?.public_id ?? null
    if (targetId === null) {
      const createRequestId = recovery?.createRequestId ?? crypto.randomUUID()
      pendingCreation.value = { createRequestId, input: request, displayText }
      const created = await assistantApi.createTask(displayText, createRequestId)
      if (disposed || navigation !== navigationVersion) return
      const authoritative = recovery === null ? created : await assistantApi.getTask(created.public_id)
      if (disposed || navigation !== navigationVersion) return
      task.value = authoritative
      emit('task-created', authoritative)
      targetId = authoritative.public_id
      pendingCreation.value = null
      if (recovery !== null && (authoritative.version !== 0 || authoritative.waiting !== null || authoritative.status !== 'ACTIVE')) {
        publishTask(authoritative)
        resultPending.value = processingRecovery.value !== null
        return
      }
    }
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
    void loadRecentTasks()
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

const submitText = (): Promise<void> => {
  editingDraft.value = false
  const text = inputText.value.trim()
  if (!text || resultPending.value) return Promise.resolve()
  if (explicitNone.value && isWaiting.value && waiting.value?.type === 'FIELD' && waiting.value.field === 'next_action') {
    explicitNone.value = false
    inputText.value = ''
    return submit({ kind: 'submit_field', choice: 'EXPLICITLY_NONE', text }, text, waiting.value)
  }
  explicitNone.value = false
  if (isWaiting.value && waiting.value?.type === 'FIELD') {
    return submit({ kind: 'submit_field', text }, text, waiting.value)
  }
  if (isTerminal.value || isWaiting.value) return Promise.resolve()
  return submit({ kind: 'text', text }, text)
}

const pickKind = (choice: string, source: TaskWaiting | null): Promise<void> =>
  submit({ kind: 'submit_field', choice }, choice, source)

const confirmWrite = (source: TaskWaiting | null): Promise<void> =>
  submit({ kind: 'confirm', choice: 'confirm' }, '确认', source)
const rejectWrite = (source: TaskWaiting | null): Promise<void> =>
  submit({ kind: 'confirm', choice: 'reject' }, '取消', source)
const cancelTask = (source: TaskWaiting | null = waiting.value): Promise<void> =>
  submit({ kind: 'cancel' }, '算了，不记了', source)

const retryPending = async (): Promise<void> => {
  if (processingRecovery.value !== null) {
    if (submitting.value) return
    submitting.value = true
    const navigation = navigationVersion
    try { await recoverProcessingTurn() } finally { if (navigation === navigationVersion) submitting.value = false }
    return
  }
  if (pendingCreation.value !== null) {
    const creation = pendingCreation.value
    await submit(creation.input, creation.displayText, null, creation)
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
        await recoverProcessingTurn()
        return
      }
      if ((turn.status === 'SUCCEEDED' || turn.status === 'FAILED') && processingRecovery.value === null) {
        resultPending.value = false
        pendingRequest.value = null
        return
      }
      // This turn is already accepted and still executing; only refresh its projection.
      return
    } else {
      const latest = await assistantApi.getTask(pending.targetId)
      if (disposed || navigation !== navigationVersion || task.value?.public_id !== pending.targetId || pendingRequest.value !== pending) return
      publishTask(latest)
      if (processingRecovery.value !== null) {
        await recoverProcessingTurn()
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

const editingDraft = ref(false)

const focusComposer = (): void => {
  editingDraft.value = true
  inputText.value = ''
  void nextTick(() => {
    scrollId.value?.scrollIntoView?.({ block: 'center' })
    document.querySelector<HTMLTextAreaElement>('.sales-assistant-page textarea')?.focus()
  })
}

const changeKind = async (kind: 'FOLLOW_UP' | 'ONLINE_MEETING' | 'OFFLINE_MEETING'): Promise<void> => {
  if (submitting.value || task.value === null) return
  submitting.value = true
  pushEntry('user', `改为${KIND_LABELS[kind]}`)
  try {
    const publicId = task.value.public_id
    await assistantApi.changeKind(publicId, kind)
    const updated = await assistantApi.getTask(publicId)
    if (disposed || task.value?.public_id !== publicId) return
    task.value = updated
    entries.value = []
    seq.value = 0
    currentWaitEntryId.value = null
    pushEntry('assistant', updated.waiting?.prompt ?? `已切换为${KIND_LABELS[kind]}，请重新描述这次沟通。`, updated.waiting ?? null)
    void loadRecentTasks()
  } catch (error) {
    const message = error instanceof Error ? error.message : '切换类型失败，请稍后重试。'
    pushEntry('assistant', message)
  } finally {
    submitting.value = false
  }
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
const entryTask = (_entry: ChatEntry): AssistantTaskView | null => task.value
const isMeeting = (current: AssistantTaskView | null): boolean =>
  current?.activity_kind === 'ONLINE_MEETING' || current?.activity_kind === 'OFFLINE_MEETING'

const isCurrentWait = (entry: ChatEntry): boolean =>
  !entry.replayed && entry.id === currentWaitEntryId.value && entry.waiting !== null && task.value?.status === 'ACTIVE'
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
  if (entry.replayed && w.type === 'CONFIRMATION' && w.field === 'activity_write') return isMeeting(task.value) ? 'meeting' : 'confirm'
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
  const receipt = task.value?.committed.find((item) => 'proposal_key' in item && item.proposal_key === proposal.candidate.key)
  if (receipt === undefined) return undefined
  return receipt.kind === `refused:${proposal.proposal_kind}` ? 'refused' : 'accepted'
}

</script>

<template>
  <div class="grid h-full min-h-0 grid-cols-[1fr_240px] gap-4">
    <div class="flex h-full min-h-0 flex-col">
    <div ref="scrollId" class="flex-1 space-y-3 overflow-y-auto pr-1">
      <div v-if="entries.length === 0" class="rounded-wolf-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
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
            <div
              v-if="cardKind(entry) === 'none' || cardKind(entry) === 'gap'"
              class="rounded-wolf-lg border bg-card px-3.5 py-2 text-sm shadow-sm"
            >
              {{ entry.text }}
              <span v-if="entry.outcome === 'activity_written'" class="ml-2 inline-flex items-center rounded-wolf-md bg-success/10 px-1.5 py-0.5 align-middle text-[11px] text-success">已写入</span>
              <span v-if="entry.outcome === 'activity_written' && formatHHmm(entry.at) !== ''" class="ml-1 text-[11px] text-muted-foreground">{{ formatHHmm(entry.at) }}</span>
            </div>

            <GapCard
              v-if="cardKind(entry) === 'gap' && entry.waiting !== null"
              :task="task"
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
              v-if="cardKind(entry) === 'meeting' && entry.waiting !== null && entryTask(entry) !== null"
              :task="entryTask(entry)!"
              :waiting="entry.waiting"
              :replayed="!isCurrentWait(entry)"
              :busy="busy"
              @confirm="() => { void confirmWrite(entry.waiting) }"
              @reject="() => { void rejectWrite(entry.waiting) }"
              @request-edit="focusComposer"
              @change-kind="() => { void changeKind(nextKindOf(entryTask(entry)?.activity_kind)) }"
            />

            <ConfirmationCard
              v-if="cardKind(entry) === 'confirm' && entry.waiting !== null && entryTask(entry) !== null"
              :task="entryTask(entry)!"
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
              @abort="cancelTask"
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
      <div v-else-if="processing.active" class="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-primary">
        <svg class="size-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-9-9"/><path d="M21 3v9h-9"/></svg>
        <span>{{ processingHint }}</span>
      </div>
      <Textarea
        v-model="inputText"
        :rows="2"
        :disabled="resultPending || (isWaiting && waiting?.type !== 'FIELD')"
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
          <Button v-if="resultPending && (pendingRequest || pendingCreation || processingRecovery)" size="sm" variant="outline" :disabled="submitting" @click="retryPending">重试同步</Button>
          <Button v-if="!isTerminal && task !== null" size="sm" variant="ghost" :disabled="busy || resultPending" @click="cancelTask">
            <X class="size-3.5" />算了
          </Button>
          <Button size="icon-sm" :disabled="busy || resultPending || (isWaiting && waiting?.type !== 'FIELD')" @click="submitText">
            <SendHorizontal class="size-4" />
          </Button>
        </div>
      </div>
    </div>
    </div>
    <AssistantTaskSidebar :task="task" :recent-tasks="recentTasks" :recent-tasks-warning="recentTasksWarning" @new-task="resetTask" @select-task="openTask" @cancel-task="cancelTask" />
  </div>
</template>
