import type { AgentAsyncOperation, AgentAsyncOperationStatus } from "@/api/agent"

export type AgentAsyncOperationTone = "info" | "success" | "warning" | "danger"

export interface AgentAsyncOperationStatusMeta {
  label: string
  tone: AgentAsyncOperationTone
  active: boolean
  terminal: boolean
  toneClasses: string
}

interface AgentAsyncOperationMessageAnchor {
  id: string
  role: "user" | "assistant"
}

export interface GroupedAgentAsyncOperations {
  byMessageId: Map<string, AgentAsyncOperation[]>
  unanchored: AgentAsyncOperation[]
}

export const AGENT_ASYNC_OPERATION_STATUS_META: Readonly<Record<AgentAsyncOperationStatus, AgentAsyncOperationStatusMeta>> = {
  QUEUED: {
    label: "已排队",
    tone: "info",
    active: true,
    terminal: false,
    toneClasses: "border-wolf-info-border bg-wolf-info-bg text-wolf-info-text",
  },
  RUNNING: {
    label: "处理中",
    tone: "info",
    active: true,
    terminal: false,
    toneClasses: "border-wolf-info-border bg-wolf-info-bg text-wolf-info-text",
  },
  WAITING_USER: {
    label: "等待确认",
    tone: "warning",
    active: false,
    terminal: false,
    toneClasses: "border-wolf-warning-border bg-wolf-warning-bg text-wolf-warning-text",
  },
  RETRY_SCHEDULED: {
    label: "等待重试",
    tone: "warning",
    active: false,
    terminal: false,
    toneClasses: "border-wolf-warning-border bg-wolf-warning-bg text-wolf-warning-text",
  },
  SUCCEEDED: {
    label: "已完成",
    tone: "success",
    active: false,
    terminal: true,
    toneClasses: "border-wolf-success-border bg-wolf-success-bg text-wolf-success-text",
  },
  DEGRADED: {
    label: "已降级完成",
    tone: "warning",
    active: false,
    terminal: true,
    toneClasses: "border-wolf-warning-border bg-wolf-warning-bg text-wolf-warning-text",
  },
  FAILED: {
    label: "处理失败",
    tone: "danger",
    active: false,
    terminal: true,
    toneClasses: "border-wolf-danger-border bg-wolf-danger-bg text-wolf-danger-text",
  },
  CANCELLED: {
    label: "已取消",
    tone: "danger",
    active: false,
    terminal: true,
    toneClasses: "border-wolf-danger-border bg-wolf-danger-bg text-wolf-danger-text",
  },
}

export const TERMINAL_AGENT_ASYNC_OPERATION_STATUSES: ReadonlySet<AgentAsyncOperationStatus> = new Set(
  Object.entries(AGENT_ASYNC_OPERATION_STATUS_META)
    .filter(([, meta]) => meta.terminal)
    .map(([status]) => status as AgentAsyncOperationStatus)
)

export const getAgentAsyncOperationStatusMeta = (
  status: AgentAsyncOperationStatus
): AgentAsyncOperationStatusMeta => AGENT_ASYNC_OPERATION_STATUS_META[status]

export const AGENT_ASYNC_OPERATION_TITLES: Readonly<Record<string, string>> = {
  customer_intelligence_refresh: "客户档案更新",
  customer_activity_post_commit: "跟进任务对账",
}

export const getAgentAsyncOperationTitle = (
  operation: Pick<AgentAsyncOperation, "operation_type">
): string => AGENT_ASYNC_OPERATION_TITLES[operation.operation_type] ?? "后台任务"

const AGGREGATE_STATUS_PRIORITY: readonly AgentAsyncOperationStatus[] = [
  "FAILED",
  "RETRY_SCHEDULED",
  "WAITING_USER",
  "RUNNING",
  "QUEUED",
  "DEGRADED",
  "CANCELLED",
  "SUCCEEDED",
]

export const summarizeAgentAsyncOperations = (
  operations: readonly AgentAsyncOperation[]
): AgentAsyncOperationStatus => {
  const statuses = new Set(operations.map(operation => operation.status))
  return AGGREGATE_STATUS_PRIORITY.find(status => statuses.has(status)) ?? "SUCCEEDED"
}

export const isTerminalAgentAsyncOperation = (operation: AgentAsyncOperation): boolean => {
  return getAgentAsyncOperationStatusMeta(operation.status).terminal
}

const resolveOperationMessageId = (
  messages: AgentAsyncOperationMessageAnchor[],
  operation: AgentAsyncOperation
): string | null => {
  if (operation.source_assistant_message_id !== null && operation.source_assistant_message_id !== undefined) {
    const assistantMessageId = String(operation.source_assistant_message_id)
    if (messages.some(message => message.role === "assistant" && message.id === assistantMessageId)) {
      return assistantMessageId
    }
  }

  if (operation.source_user_message_id === null || operation.source_user_message_id === undefined) return null
  const sourceUserMessageId = String(operation.source_user_message_id)
  const sourceUserIndex = messages.findIndex(message => message.role === "user" && message.id === sourceUserMessageId)
  if (sourceUserIndex < 0) return null

  for (let index = sourceUserIndex + 1; index < messages.length; index += 1) {
    const message = messages[index]
    if (message === undefined || message.role === "user") break
    if (message.role === "assistant") return message.id
  }
  return sourceUserMessageId
}

export const groupAgentAsyncOperationsByMessage = (
  messages: AgentAsyncOperationMessageAnchor[],
  operations: AgentAsyncOperation[]
): GroupedAgentAsyncOperations => {
  const byMessageId = new Map<string, AgentAsyncOperation[]>()
  const unanchored: AgentAsyncOperation[] = []

  for (const operation of operations) {
    const messageId = resolveOperationMessageId(messages, operation)
    if (messageId === null) {
      unanchored.push(operation)
      continue
    }
    const groupedOperations = byMessageId.get(messageId) ?? []
    groupedOperations.push(operation)
    byMessageId.set(messageId, groupedOperations)
  }

  return { byMessageId, unanchored }
}

const latestSequence = (operation: AgentAsyncOperation): number => {
  return operation.events.reduce((latest, event) => Math.max(latest, event.sequence), 0)
}

export const mergeAgentAsyncOperation = (
  current: AgentAsyncOperation | undefined,
  incoming: AgentAsyncOperation
): AgentAsyncOperation => {
  if (current === undefined) return incoming
  // A scheduling SSE acknowledgement is intentionally provisional and must yield to the first durable projection.
  if (current.team_id === 0 && current.user_id === 0 && (incoming.team_id !== 0 || incoming.user_id !== 0)) return incoming

  const currentSequence = latestSequence(current)
  const incomingSequence = latestSequence(incoming)
  if (incomingSequence < currentSequence) return current
  if (incomingSequence === currentSequence) {
    const currentUpdatedAt = Date.parse(current.updated_time)
    const incomingUpdatedAt = Date.parse(incoming.updated_time)
    if (Number.isFinite(currentUpdatedAt) && Number.isFinite(incomingUpdatedAt) && incomingUpdatedAt < currentUpdatedAt) {
      return current
    }
  }
  return incoming
}

export const upsertAgentAsyncOperation = (
  operations: AgentAsyncOperation[],
  incoming: AgentAsyncOperation
): AgentAsyncOperation[] => {
  const index = operations.findIndex(operation => operation.public_id === incoming.public_id)
  if (index < 0) return [...operations, incoming]

  const merged = mergeAgentAsyncOperation(operations[index], incoming)
  if (merged === operations[index]) return operations
  const next = operations.slice()
  next[index] = merged
  return next
}
