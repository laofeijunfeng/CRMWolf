import { ref, type Ref } from "vue"
import { agentApi, type AgentAsyncOperation } from "@/api/agent"
import {
  isTerminalAgentAsyncOperation,
  mergeAgentAsyncOperation,
  upsertAgentAsyncOperation,
} from "@/components/agent/agentAsyncOperations"

interface AgentAsyncOperationsApi {
  getOperation: (operationPublicId: string) => Promise<AgentAsyncOperation>
  listSessionOperations: (sessionId: number, params?: { limit?: number }) => Promise<AgentAsyncOperation[]>
}

interface ScheduledOperationAcknowledgement {
  operationPublicId: string
  requestId?: string
  sessionId?: number
  customerId?: number
  sourceUserMessageId?: number
}

interface UseAgentAsyncOperationsOptions {
  api?: AgentAsyncOperationsApi
  pollIntervalMs?: number
  onChanged?: () => void
  onTerminal?: (operation: AgentAsyncOperation) => void
}

interface AgentAsyncOperationsController {
  operations: Ref<AgentAsyncOperation[]>
  loadSession: (sessionId: number) => Promise<void>
  acknowledgeScheduled: (acknowledgement: ScheduledOperationAcknowledgement) => void
  resumePolling: () => void
  dispose: () => void
}

const DEFAULT_POLL_INTERVAL_MS = 2_000

const createQueuedProjection = (
  acknowledgement: ScheduledOperationAcknowledgement
): AgentAsyncOperation => {
  const now = new Date().toISOString()
  return {
    public_id: acknowledgement.operationPublicId,
    request_id: acknowledgement.requestId ?? `pending:${acknowledgement.operationPublicId}`,
    team_id: 0,
    user_id: 0,
    session_id: acknowledgement.sessionId ?? null,
    source_user_message_id: acknowledgement.sourceUserMessageId ?? null,
    source_assistant_message_id: null,
    operation_type: "customer_intelligence_refresh",
    resource_type: "customer",
    resource_id: acknowledgement.customerId ?? null,
    resource_public_id: null,
    status: "QUEUED",
    summary: "客户活动已记录，客户档案更新已进入后台队列。",
    current_step: null,
    graph_thread_id: null,
    result: {},
    error_message: null,
    started_time: null,
    finished_time: null,
    next_retry_at: null,
    attempt_count: 0,
    created_time: now,
    updated_time: now,
    events: [],
  }
}

const mergeOperationLists = (
  current: AgentAsyncOperation[],
  incoming: AgentAsyncOperation[]
): AgentAsyncOperation[] => {
  let merged = incoming.slice()
  for (const operation of current) {
    const incomingOperation = incoming.find(item => item.public_id === operation.public_id)
    if (incomingOperation === undefined) {
      merged = [...merged, operation]
      continue
    }
    const selected = mergeAgentAsyncOperation(operation, incomingOperation)
    merged = merged.map(item => item.public_id === selected.public_id ? selected : item)
  }
  return merged
}

export const useAgentAsyncOperations = (
  options: UseAgentAsyncOperationsOptions = {}
): AgentAsyncOperationsController => {
  const api = options.api ?? agentApi
  const pollIntervalMs = options.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS
  const operations = ref<AgentAsyncOperation[]>([])
  const pollTimers = new Map<string, ReturnType<typeof setTimeout>>()
  let generation = 0
  let activeSessionId: number | undefined

  const notifyChanged = (): void => {
    options.onChanged?.()
  }

  const clearPollTimer = (operationPublicId: string): void => {
    const timer = pollTimers.get(operationPublicId)
    if (timer !== undefined) clearTimeout(timer)
    pollTimers.delete(operationPublicId)
  }

  const clearPollTimers = (): void => {
    for (const timer of pollTimers.values()) clearTimeout(timer)
    pollTimers.clear()
  }

  const upsert = (operation: AgentAsyncOperation): void => {
    const next = upsertAgentAsyncOperation(operations.value, operation)
    if (next === operations.value) return
    operations.value = next
    notifyChanged()
  }

  const schedulePoll = (operationPublicId: string, targetGeneration: number): void => {
    if (targetGeneration !== generation || pollTimers.has(operationPublicId)) return
    pollTimers.set(operationPublicId, setTimeout(() => {
      pollTimers.delete(operationPublicId)
      void pollOperation(operationPublicId, targetGeneration)
    }, pollIntervalMs))
  }

  const pollOperation = async (operationPublicId: string, targetGeneration: number): Promise<void> => {
    if (targetGeneration !== generation) return
    try {
      const operation = await api.getOperation(operationPublicId)
      if (targetGeneration !== generation) return
      upsert(operation)
      if (isTerminalAgentAsyncOperation(operation)) {
        clearPollTimer(operationPublicId)
        options.onTerminal?.(operation)
        return
      }
    } catch {
      // Projection delivery may briefly lag the scheduling acknowledgement. Retry without rerunning the graph.
    }
    schedulePoll(operationPublicId, targetGeneration)
  }

  const ensurePolling = (operation: AgentAsyncOperation): void => {
    if (isTerminalAgentAsyncOperation(operation)) {
      clearPollTimer(operation.public_id)
      return
    }
    schedulePoll(operation.public_id, generation)
  }

  const loadSession = async (sessionId: number): Promise<void> => {
    if (activeSessionId !== sessionId) {
      generation += 1
      activeSessionId = sessionId
      clearPollTimers()
      operations.value = []
      notifyChanged()
    }
    const targetGeneration = generation
    const sessionOperations = await api.listSessionOperations(sessionId)
    if (targetGeneration !== generation || activeSessionId !== sessionId) return
    operations.value = mergeOperationLists(operations.value, sessionOperations)
    notifyChanged()
    for (const operation of operations.value) ensurePolling(operation)
  }

  const acknowledgeScheduled = (acknowledgement: ScheduledOperationAcknowledgement): void => {
    const provisional = createQueuedProjection(acknowledgement)
    upsert(provisional)
    const targetGeneration = generation
    void pollOperation(acknowledgement.operationPublicId, targetGeneration)
  }

  const resumePolling = (): void => {
    for (const operation of operations.value) ensurePolling(operation)
  }

  const dispose = (): void => {
    generation += 1
    clearPollTimers()
  }

  return {
    operations,
    loadSession,
    acknowledgeScheduled,
    resumePolling,
    dispose,
  }
}
