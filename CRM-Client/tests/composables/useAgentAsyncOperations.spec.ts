import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { AgentAsyncOperation } from "@/api/agent"
import { useAgentAsyncOperations } from "@/composables/useAgentAsyncOperations"

const operation = (
  status: AgentAsyncOperation["status"],
  overrides: Partial<AgentAsyncOperation> = {}
): AgentAsyncOperation => ({
  public_id: "aop_1",
  request_id: "request-1",
  team_id: 1,
  user_id: 2,
  session_id: 3,
  source_user_message_id: 4,
  source_assistant_message_id: null,
  operation_type: "customer_intelligence_refresh",
  resource_type: "customer",
  resource_id: 18,
  resource_public_id: "cus_18",
  status,
  summary: "客户档案正在后台更新",
  current_step: null,
  graph_thread_id: "thread-1",
  result: {},
  error_message: null,
  started_time: null,
  finished_time: null,
  next_retry_at: null,
  attempt_count: status === "QUEUED" ? 0 : 1,
  created_time: "2026-08-12T11:59:00",
  updated_time: "2026-08-12T12:00:00",
  events: [],
  ...overrides,
})

const flushPromises = async (): Promise<void> => {
  await Promise.resolve()
  await Promise.resolve()
}

describe("useAgentAsyncOperations", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-08-12T12:00:00Z"))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("keeps a queued acknowledgement visible and retries when the first detail request fails", async () => {
    const getOperation = vi.fn()
      .mockRejectedValueOnce(new Error("projection not committed yet"))
      .mockResolvedValueOnce(operation("RUNNING"))
    const tracker = useAgentAsyncOperations({
      api: { getOperation, listSessionOperations: vi.fn() },
      pollIntervalMs: 2_000,
    })

    tracker.acknowledgeScheduled({
      operationPublicId: "aop_1",
      requestId: "request-1",
      sessionId: 3,
      customerId: 18,
      sourceUserMessageId: 42,
    })
    await flushPromises()

    expect(tracker.operations.value).toHaveLength(1)
    expect(tracker.operations.value[0]?.status).toBe("QUEUED")
    expect(tracker.operations.value[0]?.source_user_message_id).toBe(42)
    expect(getOperation).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(2_000)

    expect(getOperation).toHaveBeenCalledTimes(2)
    expect(tracker.operations.value[0]?.status).toBe("RUNNING")
    tracker.dispose()
  })

  it("continues polling after acknowledgement and stops when the durable projection is terminal", async () => {
    const getOperation = vi.fn()
      .mockResolvedValueOnce(operation("RUNNING"))
      .mockResolvedValueOnce(operation("SUCCEEDED", {
        finished_time: "2026-08-12T12:00:05",
        updated_time: "2026-08-12T12:00:05",
      }))
    const tracker = useAgentAsyncOperations({
      api: { getOperation, listSessionOperations: vi.fn() },
      pollIntervalMs: 2_000,
    })

    tracker.acknowledgeScheduled({ operationPublicId: "aop_1", sessionId: 3 })
    await flushPromises()
    expect(tracker.operations.value[0]?.status).toBe("RUNNING")

    await vi.advanceTimersByTimeAsync(2_000)
    expect(tracker.operations.value[0]?.status).toBe("SUCCEEDED")

    await vi.advanceTimersByTimeAsync(6_000)
    expect(getOperation).toHaveBeenCalledTimes(2)
    tracker.dispose()
  })

  it("restores nonterminal operations from session history and resumes polling", async () => {
    const listSessionOperations = vi.fn().mockResolvedValue([operation("RUNNING")])
    const getOperation = vi.fn().mockResolvedValue(operation("SUCCEEDED"))
    const tracker = useAgentAsyncOperations({
      api: { getOperation, listSessionOperations },
      pollIntervalMs: 2_000,
    })

    await tracker.loadSession(3)

    expect(tracker.operations.value[0]?.status).toBe("RUNNING")
    await vi.advanceTimersByTimeAsync(2_000)
    expect(getOperation).toHaveBeenCalledWith("aop_1")
    expect(tracker.operations.value[0]?.status).toBe("SUCCEEDED")
    tracker.dispose()
  })

  it("invalidates old polling and projections when the active session changes", async () => {
    const listSessionOperations = vi.fn()
      .mockResolvedValueOnce([operation("RUNNING", { session_id: 3 })])
      .mockResolvedValueOnce([operation("QUEUED", {
        public_id: "aop_2",
        request_id: "request-2",
        session_id: 9,
      })])
    const getOperation = vi.fn()
    const tracker = useAgentAsyncOperations({
      api: { getOperation, listSessionOperations },
      pollIntervalMs: 2_000,
    })

    await tracker.loadSession(3)
    await tracker.loadSession(9)
    await vi.advanceTimersByTimeAsync(2_000)

    expect(tracker.operations.value.map(item => item.public_id)).toEqual(["aop_2"])
    expect(getOperation).toHaveBeenCalledWith("aop_2")
    expect(getOperation).not.toHaveBeenCalledWith("aop_1")
    tracker.dispose()
  })

  it("does not erase an SSE acknowledgement that arrives while session projections are loading", async () => {
    let resolveList: ((operations: AgentAsyncOperation[]) => void) | undefined
    const listSessionOperations = vi.fn().mockReturnValue(new Promise<AgentAsyncOperation[]>(resolve => {
      resolveList = resolve
    }))
    const tracker = useAgentAsyncOperations({
      api: { getOperation: vi.fn().mockRejectedValue(new Error("not ready")), listSessionOperations },
      pollIntervalMs: 2_000,
    })

    const loading = tracker.loadSession(3)
    tracker.acknowledgeScheduled({ operationPublicId: "aop_1", sessionId: 3 })
    await flushPromises()
    resolveList?.([])
    await loading

    expect(tracker.operations.value.map(item => item.public_id)).toEqual(["aop_1"])
    expect(tracker.operations.value[0]?.status).toBe("QUEUED")
    tracker.dispose()
  })
})
