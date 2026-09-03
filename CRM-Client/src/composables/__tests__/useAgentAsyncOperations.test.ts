import { afterEach, describe, expect, it, vi } from "vitest"

import type { AgentAsyncOperation, AgentAsyncOperationStatus } from "@/api/agent"
import { useAgentAsyncOperations } from "../useAgentAsyncOperations"

const makeOperation = (
  status: AgentAsyncOperationStatus,
  publicId = "op-1",
): AgentAsyncOperation => ({
  public_id: publicId,
  request_id: `request-${publicId}`,
  team_id: 1,
  user_id: 1,
  session_id: 7,
  source_user_message_id: 10,
  source_assistant_message_id: null,
  operation_type: "customer_opportunity_suggestion",
  resource_type: "customer",
  resource_id: 42,
  resource_public_id: null,
  status,
  summary: null,
  current_step: null,
  graph_thread_id: null,
  result: {},
  error_message: null,
  started_time: null,
  finished_time: null,
  next_retry_at: null,
  attempt_count: 0,
  created_time: "2026-09-02T00:00:00Z",
  updated_time: "2026-09-02T00:00:00Z",
  events: [],
})

afterEach(() => {
  vi.useRealTimers()
})

describe("useAgentAsyncOperations", () => {
  it("notifies once when an operation reaches WAITING_USER", async () => {
    vi.useFakeTimers()
    const waitingOperation = makeOperation("WAITING_USER")
    const onWaitingUser = vi.fn()
    const api = {
      getOperation: vi.fn().mockResolvedValue(waitingOperation),
      listSessionOperations: vi.fn().mockResolvedValue([makeOperation("QUEUED")]),
    }
    const controller = useAgentAsyncOperations({
      api,
      pollIntervalMs: 1_000,
      onWaitingUser,
    })

    await controller.loadSession(7)
    expect(onWaitingUser).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(1_000)
    expect(onWaitingUser).toHaveBeenCalledTimes(1)
    expect(onWaitingUser).toHaveBeenCalledWith(waitingOperation)

    await vi.advanceTimersByTimeAsync(1_000)
    expect(onWaitingUser).toHaveBeenCalledTimes(1)
    controller.dispose()
  })

  it("refreshes the session message projection when the initial operation is already WAITING_USER", async () => {
    const waitingOperation = makeOperation("WAITING_USER")
    const onWaitingUser = vi.fn()
    const api = {
      getOperation: vi.fn().mockResolvedValue(waitingOperation),
      listSessionOperations: vi.fn().mockResolvedValue([waitingOperation]),
    }
    const controller = useAgentAsyncOperations({ api, onWaitingUser })

    await controller.loadSession(7)

    expect(onWaitingUser).toHaveBeenCalledTimes(1)
    expect(onWaitingUser).toHaveBeenCalledWith(waitingOperation)
    controller.dispose()
  })

  it("does not notify again when a WAITING_USER operation is reloaded", async () => {
    const waitingOperation = makeOperation("WAITING_USER")
    const onWaitingUser = vi.fn()
    const api = {
      getOperation: vi.fn().mockResolvedValue(waitingOperation),
      listSessionOperations: vi.fn().mockResolvedValue([waitingOperation]),
    }
    const controller = useAgentAsyncOperations({ api, onWaitingUser })

    await controller.loadSession(7)
    await controller.loadSession(7)

    expect(onWaitingUser).toHaveBeenCalledTimes(1)
    controller.dispose()
  })
})
