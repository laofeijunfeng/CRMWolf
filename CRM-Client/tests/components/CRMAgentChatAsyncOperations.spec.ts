import { flushPromises, mount } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type {
  AgentAsyncOperation,
  AgentChatRequest,
  AgentChatSSEEvent,
  AgentMessageResponse,
  AgentSessionResponse,
} from "@/api/agent"
import type { PaginatedResponse } from "@/types/pagination"

const api = vi.hoisted(() => ({
  listSessions: vi.fn<() => Promise<PaginatedResponse<AgentSessionResponse>>>(),
  listMessages: vi.fn<(sessionId: number, params?: { page?: number, page_size?: number }) => Promise<PaginatedResponse<AgentMessageResponse>>>(),
  listSessionOperations: vi.fn<(sessionId: number, params?: { limit?: number }) => Promise<AgentAsyncOperation[]>>(),
  getOperation: vi.fn<(operationPublicId: string) => Promise<AgentAsyncOperation>>(),
  chatStream: vi.fn<(
    data: AgentChatRequest,
    onEvent: (event: AgentChatSSEEvent) => void,
    token: string
  ) => Promise<void>>(),
}))

vi.mock("@/api/agent", async importOriginal => ({
  ...await importOriginal<typeof import("@/api/agent")>(),
  agentApi: api,
}))

import CRMAgentChat from "@/components/agent/CRMAgentChat.vue"
import { useUserStore } from "@/stores/user"

const operation: AgentAsyncOperation = {
  public_id: "aop_first_turn",
  request_id: "request-first-turn",
  team_id: 1,
  user_id: 2,
  session_id: 3,
  source_user_message_id: 10,
  source_assistant_message_id: null,
  operation_type: "customer_intelligence_refresh",
  resource_type: "customer",
  resource_id: 18,
  resource_public_id: "cus_18",
  status: "SUCCEEDED",
  summary: "客户档案已更新",
  current_step: null,
  graph_thread_id: "thread-1",
  result: {},
  error_message: null,
  started_time: "2026-08-12T12:00:00",
  finished_time: "2026-08-12T12:00:05",
  next_retry_at: null,
  attempt_count: 1,
  created_time: "2026-08-12T12:00:00",
  updated_time: "2026-08-12T12:00:05",
  events: [],
}

const messages: AgentMessageResponse[] = [
  { id: 10, role: "user", content: "第一条跟进", created_time: "2026-08-12T12:00:00" },
  { id: 11, role: "assistant", content: "第一条已记录", created_time: "2026-08-12T12:00:01" },
  { id: 12, role: "user", content: "第二条消息", created_time: "2026-08-12T12:01:00" },
  { id: 13, role: "assistant", content: "第二条已处理", created_time: "2026-08-12T12:01:01" },
]

const paginatedMessages = (items: AgentMessageResponse[]): PaginatedResponse<AgentMessageResponse> => ({
  items,
  total: items.length,
  page: 1,
  page_size: 100,
  total_pages: 1,
})

describe("CRMAgentChat background operation placement", () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    useUserStore().setToken("test-token")
    api.listSessions.mockReset().mockResolvedValue({
      items: [{
        id: 3,
        session_key: "session-3",
        title: "测试会话",
        status: "active",
        summary: null,
        created_time: "2026-08-12T12:00:00",
        last_modified_time: "2026-08-12T12:01:01",
      }],
      total: 1,
      page: 1,
      page_size: 20,
      total_pages: 1,
    })
    api.listMessages.mockReset().mockResolvedValue(paginatedMessages(messages))
    api.listSessionOperations.mockReset().mockResolvedValue([operation])
    api.getOperation.mockReset()
    api.chatStream.mockReset()
  })

  it("renders a completed background operation after the assistant response from its source turn", async () => {
    const wrapper = mount(CRMAgentChat, {
      global: {
        stubs: {
          AgentInteractionDrawer: true,
          MessageScroller: { template: "<div><slot /></div>" },
        },
      },
    })
    await flushPromises()

    const text = wrapper.text()
    const firstAssistantIndex = text.indexOf("第一条已记录")
    const operationIndex = text.indexOf("后台任务")
    const secondUserIndex = text.indexOf("第二条消息")

    expect(firstAssistantIndex).toBeGreaterThanOrEqual(0)
    expect(operationIndex).toBeGreaterThan(firstAssistantIndex)
    expect(operationIndex).toBeLessThan(secondUserIndex)
    wrapper.unmount()
  })

  it("keeps a newly scheduled operation with its original turn after the user sends another message", async () => {
    api.listMessages.mockResolvedValue(paginatedMessages([]))
    api.listSessionOperations.mockResolvedValue([])
    api.getOperation.mockResolvedValue({
      ...operation,
      source_user_message_id: 20,
      status: "RUNNING",
      finished_time: null,
    })
    api.chatStream
      .mockImplementationOnce(async (_request, onEvent) => {
        onEvent({ event: "session", session_id: 3, session_key: "session-3" })
        onEvent({ event: "message", role: "user", message_id: 20, content: "本轮跟进" })
        onEvent({
          event: "agent_root_customer_intelligence_refresh_scheduled",
          session_id: 3,
          operation_public_id: "aop_first_turn",
          request_id: "request-first-turn",
          source_user_message_id: 20,
        })
        onEvent({ event: "message", role: "assistant", message_id: 21, content: "本轮已记录" })
        onEvent({ event: "done" })
      })
      .mockImplementationOnce(async (_request, onEvent) => {
        onEvent({ event: "session", session_id: 3, session_key: "session-3" })
        onEvent({ event: "message", role: "user", message_id: 22, content: "下一轮问题" })
        onEvent({ event: "message", role: "assistant", message_id: 23, content: "下一轮已处理" })
        onEvent({ event: "done" })
      })

    const wrapper = mount(CRMAgentChat, {
      global: {
        stubs: {
          AgentInteractionDrawer: true,
          MessageScroller: { template: "<div><slot /></div>" },
        },
      },
    })
    await flushPromises()

    await wrapper.get("textarea").setValue("本轮跟进")
    await wrapper.get("form").trigger("submit")
    await flushPromises()
    await wrapper.get("textarea").setValue("下一轮问题")
    await wrapper.get("form").trigger("submit")
    await flushPromises()

    const text = wrapper.text()
    expect(text.indexOf("后台任务")).toBeGreaterThan(text.indexOf("本轮已记录"))
    expect(text.indexOf("后台任务")).toBeLessThan(text.indexOf("下一轮问题"))
    wrapper.unmount()
  })

  it("renders a follow-up reconciliation card after the assistant response from its source turn", async () => {
    api.listSessionOperations.mockResolvedValue([
      {
        ...operation,
        public_id: "aop_post_commit",
        request_id: "pcj_first_turn",
        source_user_message_id: 10,
        source_assistant_message_id: null,
        operation_type: "customer_activity_post_commit",
        resource_type: "customer_activity",
        resource_id: 241,
        resource_public_id: null,
        summary: "跟进任务已完成对账",
      },
    ])

    const wrapper = mount(CRMAgentChat, {
      global: {
        stubs: {
          AgentInteractionDrawer: true,
          MessageScroller: { template: "<div><slot /></div>" },
        },
      },
    })
    await flushPromises()

    const text = wrapper.text()
    const firstAssistantIndex = text.indexOf("第一条已记录")
    const operationIndex = text.indexOf("后台任务")
    const secondUserIndex = text.indexOf("第二条消息")

    expect(firstAssistantIndex).toBeGreaterThanOrEqual(0)
    expect(operationIndex).toBeGreaterThan(firstAssistantIndex)
    expect(operationIndex).toBeLessThan(secondUserIndex)
    wrapper.unmount()
  })

  it("collapses both background operations into one list until the user expands it", async () => {
    api.listSessionOperations.mockResolvedValue([
      operation,
      {
        ...operation,
        public_id: "aop_post_commit",
        request_id: "pcj_first_turn",
        operation_type: "customer_activity_post_commit",
        resource_type: "customer_activity",
        resource_id: 241,
        resource_public_id: null,
        summary: "跟进任务已完成对账",
      },
    ])

    const wrapper = mount(CRMAgentChat, {
      global: {
        stubs: {
          AgentInteractionDrawer: true,
          MessageScroller: { template: "<div><slot /></div>" },
        },
      },
    })
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain("后台任务")
    expect(text).not.toContain("客户档案更新")
    expect(text).not.toContain("跟进任务对账")

    await wrapper.get(".agent-async-operation-list__trigger").trigger("click")

    expect(wrapper.text()).toContain("客户档案更新")
    expect(wrapper.text()).toContain("跟进任务对账")
    wrapper.unmount()
  })
})
