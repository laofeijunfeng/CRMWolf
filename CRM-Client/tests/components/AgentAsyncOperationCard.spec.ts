import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"
import {
  AlertTriangle,
  CheckCircle2,
  CircleHelp,
  CircleSlash2,
  Clock3,
  Loader2,
  RotateCcw,
  XCircle,
} from "lucide-vue-next"
import AgentAsyncOperationCard from "@/components/agent/AgentAsyncOperationCard.vue"
import type { AgentAsyncOperation } from "@/api/agent"

const degradedOperation: AgentAsyncOperation = {
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
  status: "DEGRADED",
  summary: "客户档案已更新，本次沉淀 0 条客户事实",
  current_step: "refresh_customer_brief",
  graph_thread_id: "thread-1",
  result: { persisted_fact_count: 0, degraded: true },
  error_message: null,
  started_time: "2026-08-12T12:00:00",
  finished_time: "2026-08-12T12:00:40",
  next_retry_at: null,
  attempt_count: 1,
  created_time: "2026-08-12T11:59:59",
  updated_time: "2026-08-12T12:00:40",
  events: [
    {
      sequence: 2,
      event_type: "PROGRESS",
      status: "RUNNING",
      event_key: "progress-1",
      step: "extract_customer_facts",
      message: "提炼客户事实：提炼出 6 条可沉淀事实，1 条需复核事实",
      payload: {},
      occurred_at: "2026-08-12T12:00:20",
    },
    {
      sequence: 3,
      event_type: "PROGRESS",
      status: "RUNNING",
      event_key: "progress-2",
      step: "persist_customer_facts",
      message: "沉淀客户事实：已沉淀 6 条客户事实，1 条保留复核",
      payload: {},
      occurred_at: "2026-08-12T12:00:30",
    },
  ],
}

describe("AgentAsyncOperationCard", () => {
  it("uses a lightweight status disclosure that is collapsed by default", () => {
    const wrapper = mount(AgentAsyncOperationCard, { props: { operation: degradedOperation } })
    const trigger = wrapper.get("button")

    expect(trigger.attributes("aria-expanded")).toBe("false")
    expect(trigger.attributes("aria-label")).toContain("已降级完成")
    expect(trigger.attributes("title")).toBeUndefined()
    expect(trigger.text()).toBe("客户档案更新")
    expect(wrapper.text()).not.toContain("客户档案已更新，本次沉淀 0 条客户事实")
    expect(wrapper.text()).not.toContain("提炼出 6 条可沉淀事实")
    expect(wrapper.find(".agent-async-operation__details").exists()).toBe(false)
  })

  it("shows execution events after expansion without repeating the completion summary", async () => {
    const wrapper = mount(AgentAsyncOperationCard, { props: { operation: degradedOperation } })

    await wrapper.get("button").trigger("click")

    expect(wrapper.get("button").attributes("aria-expanded")).toBe("true")
    expect(wrapper.text()).toContain("提炼客户事实：提炼出 6 条可沉淀事实，1 条需复核事实")
    expect(wrapper.text()).toContain("沉淀客户事实：已沉淀 6 条客户事实，1 条保留复核")
    expect(wrapper.text()).not.toContain("客户档案已更新，本次沉淀 0 条客户事实")
  })

  it.each([
    ["QUEUED", Clock3, "agent-async-operation__status-icon--pulse"],
    ["RUNNING", Loader2, "agent-async-operation__status-icon--spin"],
    ["WAITING_USER", CircleHelp, "agent-async-operation__status-icon--warning"],
    ["RETRY_SCHEDULED", RotateCcw, "agent-async-operation__status-icon--warning"],
    ["SUCCEEDED", CheckCircle2, "agent-async-operation__status-icon--success"],
    ["DEGRADED", AlertTriangle, "agent-async-operation__status-icon--warning"],
    ["FAILED", XCircle, "agent-async-operation__status-icon--danger"],
    ["CANCELLED", CircleSlash2, "agent-async-operation__status-icon--danger"],
  ] as const)("uses a clear icon-only treatment for %s", (status, icon, className) => {
    const wrapper = mount(AgentAsyncOperationCard, {
      props: { operation: { ...degradedOperation, status } },
    })

    expect(wrapper.findComponent(icon).exists()).toBe(true)
    expect(wrapper.get(".agent-async-operation__status-icon").classes()).toContain(className)
    expect(wrapper.get("button").text()).toBe("客户档案更新")
  })

  it("shows retry reason and schedule only after expansion", async () => {
    const wrapper = mount(AgentAsyncOperationCard, {
      props: {
        operation: {
          ...degradedOperation,
          status: "RETRY_SCHEDULED",
          error_message: "客户档案服务暂不可用",
          next_retry_at: "2026-08-13T08:30:00+08:00",
        },
      },
    })

    expect(wrapper.text()).not.toContain("客户档案服务暂不可用")
    expect(wrapper.text()).not.toContain("自动重试")

    await wrapper.get("button").trigger("click")

    expect(wrapper.text()).toContain("客户档案服务暂不可用")
    expect(wrapper.text()).toContain("自动重试")
  })

  it("labels post-commit work as task reconciliation and shows the backend summary when there is no progress trail", async () => {
    const wrapper = mount(AgentAsyncOperationCard, {
      props: {
        operation: {
          ...degradedOperation,
          public_id: "aop_post_commit",
          operation_type: "customer_activity_post_commit",
          resource_type: "activity",
          resource_id: 88,
          resource_public_id: "act_88",
          status: "SUCCEEDED",
          summary: "跟进已记录，任务对账完成",
          current_step: "complete_activity_post_commit",
          events: [],
        },
      },
    })

    expect(wrapper.get("button").text()).toBe("跟进任务对账")
    expect(wrapper.text()).not.toContain("跟进已记录，任务对账完成")
    expect(wrapper.text()).not.toContain("执行过程已完成。")

    await wrapper.get("button").trigger("click")

    expect(wrapper.text()).toContain("跟进已记录，任务对账完成")
    expect(wrapper.text()).not.toContain("执行过程已完成。")
  })
})
