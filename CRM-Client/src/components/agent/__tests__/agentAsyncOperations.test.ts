import { describe, expect, it } from "vitest"

import { getAgentAsyncOperationTitle } from "../agentAsyncOperations"

describe("agent async operation titles", () => {
  it("labels opportunity suggestion operations explicitly", () => {
    expect(getAgentAsyncOperationTitle({ operation_type: "customer_opportunity_suggestion" })).toBe("商机建议分析")
  })
})
