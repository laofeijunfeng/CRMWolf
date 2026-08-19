import { describe, expect, it } from "vitest"
import type { AgentAsyncOperation } from "@/api/agent"
import {
  groupAgentAsyncOperationsByMessage,
  getAgentAsyncOperationStatusMeta,
  getAgentAsyncOperationTitle,
  isTerminalAgentAsyncOperation,
  mergeAgentAsyncOperation,
  summarizeAgentAsyncOperations,
  upsertAgentAsyncOperation,
} from "@/components/agent/agentAsyncOperations"

const operation = (
  status: AgentAsyncOperation["status"],
  sequence: number,
  updatedTime = "2026-08-12T12:00:00"
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
  attempt_count: 1,
  created_time: "2026-08-12T11:59:00",
  updated_time: updatedTime,
  events: Array.from({ length: sequence }, (_, index) => ({
    sequence: index + 1,
    event_type: index === 0 ? "SCHEDULED" : "PROGRESS",
    status,
    event_key: `event-${index + 1}`,
    step: null,
    message: null,
    payload: {},
    occurred_at: updatedTime,
  })),
})

describe("agent async operation projection", () => {
  it("keeps a background operation with the assistant response for the turn that scheduled it", () => {
    const firstTurnOperation = operation("RUNNING", 2)
    const messages = [
      { id: "4", role: "user" as const },
      { id: "5", role: "assistant" as const },
      { id: "6", role: "user" as const },
      { id: "7", role: "assistant" as const },
    ]

    const grouped = groupAgentAsyncOperationsByMessage(messages, [firstTurnOperation])

    expect(grouped.byMessageId.get("5")).toEqual([firstTurnOperation])
    expect(grouped.byMessageId.has("7")).toBe(false)
    expect(grouped.unanchored).toEqual([])
  })

  it("keeps operations without a matching source message visible as unanchored fallbacks", () => {
    const unmatchedOperation = operation("SUCCEEDED", 3)
    const grouped = groupAgentAsyncOperationsByMessage(
      [{ id: "99", role: "assistant" }],
      [unmatchedOperation]
    )

    expect(grouped.byMessageId.size).toBe(0)
    expect(grouped.unanchored).toEqual([unmatchedOperation])
  })

  it("replaces queued state with newer running and succeeded projections", () => {
    const queued = operation("QUEUED", 1)
    const running = operation("RUNNING", 2, "2026-08-12T12:00:02")
    const succeeded = operation("SUCCEEDED", 3, "2026-08-12T12:00:05")

    expect(mergeAgentAsyncOperation(queued, running).status).toBe("RUNNING")
    expect(mergeAgentAsyncOperation(running, succeeded).status).toBe("SUCCEEDED")
  })

  it("ignores duplicate or older replay results", () => {
    const succeeded = operation("SUCCEEDED", 3, "2026-08-12T12:00:05")
    const staleRunning = operation("RUNNING", 2, "2026-08-12T12:00:06")

    expect(mergeAgentAsyncOperation(succeeded, staleRunning)).toBe(succeeded)
    expect(upsertAgentAsyncOperation([succeeded], staleRunning)).toEqual([succeeded])
  })

  it("stops polling only for terminal lifecycle states", () => {
    expect(isTerminalAgentAsyncOperation(operation("RUNNING", 2))).toBe(false)
    expect(isTerminalAgentAsyncOperation(operation("RETRY_SCHEDULED", 2))).toBe(false)
    expect(isTerminalAgentAsyncOperation(operation("SUCCEEDED", 3))).toBe(true)
    expect(isTerminalAgentAsyncOperation(operation("DEGRADED", 3))).toBe(true)
    expect(isTerminalAgentAsyncOperation(operation("FAILED", 3))).toBe(true)
  })
  it("uses one semantic status contract for presentation and lifecycle decisions", () => {
    expect(getAgentAsyncOperationStatusMeta("RUNNING")).toMatchObject({
      label: "处理中",
      tone: "info",
      active: true,
      terminal: false,
    })
    expect(getAgentAsyncOperationStatusMeta("DEGRADED")).toMatchObject({
      label: "已降级完成",
      tone: "warning",
      terminal: true,
    })
    expect(getAgentAsyncOperationStatusMeta("FAILED").toneClasses).toContain("wolf-danger")
  })

  it("names operations by type and summarizes the list by the most urgent status", () => {
    expect(getAgentAsyncOperationTitle(operation("SUCCEEDED", 1))).toBe("客户档案更新")
    expect(getAgentAsyncOperationTitle({
      ...operation("SUCCEEDED", 1),
      operation_type: "customer_activity_post_commit",
    })).toBe("跟进任务对账")
    expect(summarizeAgentAsyncOperations([
      operation("SUCCEEDED", 1),
      {
        ...operation("RUNNING", 1),
        public_id: "aop_2",
        operation_type: "customer_activity_post_commit",
      },
    ])).toBe("RUNNING")
  })
})

