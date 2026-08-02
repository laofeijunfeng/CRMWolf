import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"
import AgentMessageBody from "@/components/agent/AgentMessageBody.vue"

describe("AgentMessageBody", () => {
  it("renders markdown lists for structured Agent answers", () => {
    const wrapper = mount(AgentMessageBody, {
      props: {
        format: "markdown",
        content: "### 客户现状\n- **商机**：POC 阶段\n- **风险**：缺少合同计划",
      },
    })

    expect(wrapper.find("h3").text()).toBe("客户现状")
    expect(wrapper.findAll("li").map(item => item.text())).toEqual([
      "商机：POC 阶段",
      "风险：缺少合同计划",
    ])
  })

  it("normalizes inline markdown section headings from persisted Agent answers", () => {
    const wrapper = mount(AgentMessageBody, {
      props: {
        format: "markdown",
        content: "中科院信工所当前情况 ### 1. 客户现状\n客户资料完整。 ### 2. 商机与合同进展\n合同已签。",
      },
    })

    expect(wrapper.findAll("h3").map(item => item.text())).toEqual([
      "1. 客户现状",
      "2. 商机与合同进展",
    ])
    expect(wrapper.text()).not.toContain("###")
  })

  it("escapes raw html in markdown content", () => {
    const wrapper = mount(AgentMessageBody, {
      props: {
        format: "markdown",
        content: "<img src=x onerror=alert(1)> **安全文本**",
      },
    })

    expect(wrapper.find("img").exists()).toBe(false)
    expect(wrapper.html()).toContain("&lt;img")
    expect(wrapper.text()).toContain("安全文本")
  })
})
