import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"
import { CheckCircle2, Loader2 } from "lucide-vue-next"
import AgentAsyncOperationList from "@/components/agent/AgentAsyncOperationList.vue"
import type { AgentAsyncOperation } from "@/api/agent"

const intelligenceOperation: AgentAsyncOperation = {
  public_id: "aop_intelligence",
  request_id: "request-intelligence",
  team_id: 1,
  user_id: 2,
  session_id: 3,
  source_user_message_id: 4,
  source_assistant_message_id: null,
  operation_type: "customer_intelligence_refresh",
  resource_type: "customer",
  resource_id: 18,
  resource_public_id: "cus_18",
  status: "SUCCEEDED",
  summary: "客户档案已更新",
  current_step: "refresh_customer_brief",
  graph_thread_id: "thread-1",
  result: {},
  error_message: null,
  started_time: "2026-08-12T12:00:00",
  finished_time: "2026-08-12T12:00:40",
  next_retry_at: null,
  attempt_count: 1,
  created_time: "2026-08-12T11:59:59",
  updated_time: "2026-08-12T12:00:40",
  events: [],
}

const postCommitOperation: AgentAsyncOperation = {
  ...intelligenceOperation,
  public_id: "aop_post_commit",
  request_id: "request-post-commit",
  operation_type: "customer_activity_post_commit",
  resource_type: "customer_activity",
  resource_id: 241,
  resource_public_id: null,
  status: "RUNNING",
  summary: "跟进已记录，任务对账处理中",
  current_step: "reconcile_follow_up_tasks",
  finished_time: null,
}

describe("AgentAsyncOperationList", () => {
  it("collapses every background operation into one list until the user expands it", () => {
    const wrapper = mount(AgentAsyncOperationList, {
      props: {
        operations: [intelligenceOperation, postCommitOperation],
      },
    })

    expect(wrapper.get("button").text()).toBe("后台任务")
    expect(wrapper.findComponent(Loader2).exists()).toBe(true)
    expect(wrapper.text()).not.toContain("客户档案更新")
    expect(wrapper.text()).not.toContain("跟进任务对账")
    expect(wrapper.text()).not.toContain("客户档案已更新")
    expect(wrapper.text()).not.toContain("跟进已记录，任务对账处理中")
  })

  it("reveals named operations after the list is expanded", async () => {
    const wrapper = mount(AgentAsyncOperationList, {
      props: {
        operations: [intelligenceOperation, postCommitOperation],
      },
    })

    await wrapper.get("button").trigger("click")

    expect(wrapper.text()).toContain("客户档案更新")
    expect(wrapper.text()).toContain("跟进任务对账")
    expect(wrapper.findComponent(CheckCircle2).exists()).toBe(true)
    expect(wrapper.text()).not.toContain("客户档案已更新")
    expect(wrapper.text()).not.toContain("跟进已记录，任务对账处理中")
  })
})
