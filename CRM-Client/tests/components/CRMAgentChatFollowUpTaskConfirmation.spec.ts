import { flushPromises, mount } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type {
  AgentChatRequest,
  AgentChatSSEEvent,
  AgentMessageResponse,
  AgentSessionResponse,
} from "@/api/agent"
import type { PaginatedResponse } from "@/types/pagination"

const agentApi = vi.hoisted(() => ({
  listSessions: vi.fn<() => Promise<PaginatedResponse<AgentSessionResponse>>>(),
  listMessages: vi.fn<(sessionId: number, params?: { page?: number, page_size?: number }) => Promise<PaginatedResponse<AgentMessageResponse>>>(),
  listSessionOperations: vi.fn(),
  getOperation: vi.fn(),
  chatStream: vi.fn<(
    data: AgentChatRequest,
    onEvent: (event: AgentChatSSEEvent) => void,
    token: string,
  ) => Promise<void>>(),
}))
const followUpConfirmationApi = vi.hoisted(() => ({
  getPendingCount: vi.fn<() => Promise<number>>(),
  resolve: vi.fn(),
}))
const confirmDialog = vi.hoisted(() => vi.fn<() => Promise<boolean>>())
const logger = vi.hoisted(() => ({
  error: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
}))

vi.mock("@/api/agent", async importOriginal => ({
  ...await importOriginal<typeof import("@/api/agent")>(),
  agentApi,
}))
vi.mock("@/api/followUpTask", async importOriginal => ({
  ...await importOriginal<typeof import("@/api/followUpTask")>(),
  followUpConfirmationApi,
}))
vi.mock("@/utils/confirmDialog", () => ({ confirmDialog }))
vi.mock("@/utils/logger", () => ({ logger }))

import CRMAgentChat from "@/components/agent/CRMAgentChat.vue"
import { useUserStore } from "@/stores/user"

const paginated = (items: AgentMessageResponse[]): PaginatedResponse<AgentMessageResponse> => ({
  items,
  total: items.length,
  page: 1,
  page_size: 100,
  total_pages: 1,
})

const pendingMessage = (): AgentMessageResponse => ({
  id: 12,
  role: "assistant",
  content: "请确认关联待办。",
  payload_json: {
    trace_events: [{
      event: "confirmation_required",
      action: "resolve_follow_up_task_confirmation_case",
      interaction: {
        type: "text",
        status: "waiting_confirmation",
        business_action: "resolve_follow_up_task_confirmation_case",
      },
    }],
  },
  linked_follow_up_task_confirmations: [{
    case_public_id: "fuc_apple",
    task_public_id: "fut_apple",
    task_title: "跟进 Apple 合同流程推进",
    customer_name: "Apple",
    due_at: "2026-08-18T09:00:00+08:00",
    task_status: "OPEN",
    confirmation_status: "PENDING",
    resolved_action: null,
    resolved_at: null,
    completed_at: null,
  }],
  created_time: "2026-08-20T09:00:00+08:00",
})

const completedMessage = (): AgentMessageResponse => ({
  ...pendingMessage(),
  linked_follow_up_task_confirmations: [{
    ...pendingMessage().linked_follow_up_task_confirmations?.[0]!,
    task_status: "COMPLETED",
    confirmation_status: "RESOLVED",
    resolved_action: "COMPLETE",
    resolved_at: "2026-08-20T10:00:00+08:00",
    completed_at: "2026-08-20T10:00:00+08:00",
  }],
})

describe("CRMAgentChat follow-up task confirmation", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useUserStore().setToken("test-token")
    agentApi.listSessions.mockReset().mockResolvedValue(paginated([{
      id: 3,
      session_key: "session-3",
      title: "测试会话",
      status: "ACTIVE",
      summary: null,
      created_time: "2026-08-20T09:00:00+08:00",
      last_modified_time: "2026-08-20T09:00:00+08:00",
    }]))
    agentApi.listMessages.mockReset()
      .mockResolvedValueOnce(paginated([pendingMessage()]))
      .mockResolvedValueOnce(paginated([completedMessage()]))
    agentApi.listSessionOperations.mockReset().mockResolvedValue([])
    agentApi.getOperation.mockReset()
    agentApi.chatStream.mockReset()
    followUpConfirmationApi.getPendingCount.mockReset().mockResolvedValue(0)
    followUpConfirmationApi.resolve.mockReset().mockResolvedValue({ decision: { resolved: true } })
    confirmDialog.mockReset().mockResolvedValue(true)
  })

  it("uses the message card as the only entry, resolves through the existing confirmation API, then locks the completed task", async () => {
    const wrapper = mount(CRMAgentChat, {
      global: {
        stubs: {
          MessageScroller: { template: "<div><slot /></div>" },
          AgentInteractionDrawer: { template: '<div data-testid="interaction-drawer" />' },
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain("关联待办：跟进 Apple 合同流程推进")
    expect(wrapper.text()).toContain("需确认")
    expect(wrapper.find('[data-testid="interaction-drawer"]').exists()).toBe(false)

    await wrapper.get('[role="checkbox"]').trigger("click")
    await flushPromises()

    expect(confirmDialog).toHaveBeenCalledWith(
      "确认已完成该关联待办？完成后不能在此消息中撤销。",
      "确认完成",
      { confirmText: "确认完成" },
    )
    expect(followUpConfirmationApi.resolve).toHaveBeenCalledWith("fuc_apple", { reply_text: "已完成" })
    expect(wrapper.text()).toContain("已完成")
    expect(wrapper.get('[role="checkbox"]').attributes("disabled")).toBeDefined()
  })

  it("keeps the card completed and blocks repeat submission when the Agent message refresh fails", async () => {
    agentApi.listMessages.mockReset()
      .mockResolvedValueOnce(paginated([pendingMessage()]))
      .mockRejectedValueOnce(new Error("Agent 会话刷新失败"))

    const wrapper = mount(CRMAgentChat, {
      global: {
        stubs: {
          MessageScroller: { template: "<div><slot /></div>" },
          AgentInteractionDrawer: { template: '<div data-testid="interaction-drawer" />' },
        },
      },
    })
    await flushPromises()

    await wrapper.get('[role="checkbox"]').trigger("click")
    await flushPromises()

    expect(wrapper.text()).toContain("已完成")
    expect(wrapper.get('[role="checkbox"]').attributes("disabled")).toBeDefined()

    await wrapper.get('[role="checkbox"]').trigger("click")
    await flushPromises()
    expect(followUpConfirmationApi.resolve).toHaveBeenCalledOnce()
    wrapper.unmount()
  })

  it("locks the card without waiting for the auxiliary pending-count refresh", async () => {
    followUpConfirmationApi.getPendingCount.mockImplementation(() => new Promise<number>(() => {}))

    const wrapper = mount(CRMAgentChat, {
      global: {
        stubs: {
          MessageScroller: { template: "<div><slot /></div>" },
          AgentInteractionDrawer: { template: '<div data-testid="interaction-drawer" />' },
        },
      },
    })
    await flushPromises()

    await wrapper.get('[role="checkbox"]').trigger("click")
    await flushPromises()

    expect(followUpConfirmationApi.resolve).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain("已完成")
    expect(wrapper.get('[role="checkbox"]').attributes("disabled")).toBeDefined()
    wrapper.unmount()
  })

  it("does not regress the completed card when the first Agent message refresh is stale", async () => {
    agentApi.listMessages.mockReset()
      .mockResolvedValueOnce(paginated([pendingMessage()]))
      .mockResolvedValueOnce(paginated([pendingMessage()]))

    const wrapper = mount(CRMAgentChat, {
      global: {
        stubs: {
          MessageScroller: { template: "<div><slot /></div>" },
          AgentInteractionDrawer: { template: '<div data-testid="interaction-drawer" />' },
        },
      },
    })
    await flushPromises()

    await wrapper.get('[role="checkbox"]').trigger("click")
    await flushPromises()

    expect(wrapper.text()).toContain("已完成")
    expect(wrapper.get('[role="checkbox"]').attributes("disabled")).toBeDefined()
    wrapper.unmount()
  })
})
