import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"
import type { AgentLinkedFollowUpTaskConfirmation } from "@/api/agent"
import AgentFollowUpTaskConfirmationCard from "@/components/agent/AgentFollowUpTaskConfirmationCard.vue"

const pendingConfirmation: AgentLinkedFollowUpTaskConfirmation = {
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
}

describe("AgentFollowUpTaskConfirmationCard", () => {
  it("renders a pending task with the shadcn neutral card colors and requests confirmation without changing local state", async () => {
    const wrapper = mount(AgentFollowUpTaskConfirmationCard, {
      props: { confirmation: pendingConfirmation },
    })

    expect(wrapper.text()).toContain("关联待办：跟进 Apple 合同流程推进")
    expect(wrapper.text()).toContain("需确认")
    expect(wrapper.classes()).toContain("bg-card")
    expect(wrapper.classes()).toContain("border-border")

    const checkbox = wrapper.get('[role="checkbox"]')
    expect(checkbox.attributes("data-state")).toBe("unchecked")
    await checkbox.trigger("click")

    expect(wrapper.emitted("confirm-complete")).toEqual([[pendingConfirmation]])
    expect(checkbox.attributes("data-state")).toBe("unchecked")
  })

  it("shows completed as a non-reversible green card and disables its checkbox", () => {
    const wrapper = mount(AgentFollowUpTaskConfirmationCard, {
      props: {
        confirmation: {
          ...pendingConfirmation,
          task_status: "COMPLETED",
          confirmation_status: "RESOLVED",
          resolved_action: "COMPLETE",
          resolved_at: "2026-08-20T10:30:00+08:00",
          completed_at: "2026-08-20T10:30:00+08:00",
        },
      },
    })

    expect(wrapper.text()).toContain("已完成")
    expect(wrapper.classes()).toContain("bg-green-50")
    expect(wrapper.classes()).toContain("border-green-200")
    const checkbox = wrapper.get('[role="checkbox"]')
    expect(checkbox.attributes("data-state")).toBe("checked")
    expect(checkbox.attributes("disabled")).toBeDefined()
  })
})
