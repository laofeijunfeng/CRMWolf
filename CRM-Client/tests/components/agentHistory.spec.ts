import { describe, expect, it, vi } from "vitest"
import type { AgentMessageResponse } from "@/api/agent"
import type { PaginatedResponse } from "@/types/pagination"
import { loadLatestAgentMessages } from "@/components/agent/agentHistory"

const message = (id: number): AgentMessageResponse => ({
  id,
  role: id % 2 === 0 ? "assistant" : "user",
  content: `message ${id}`,
  created_time: `2026-07-29T00:${String(id % 60).padStart(2, "0")}:00Z`,
})

const page = (items: AgentMessageResponse[], total: number, pageNumber: number, pageSize = 100): PaginatedResponse<AgentMessageResponse> => ({
  items,
  total,
  page: pageNumber,
  page_size: pageSize,
  total_pages: Math.ceil(total / pageSize),
})

describe("loadLatestAgentMessages", () => {
  it("returns the first page when a session has at most one page", async () => {
    const items = [message(1), message(2)]
    const listMessages = vi.fn().mockResolvedValue(page(items, 2, 1))

    await expect(loadLatestAgentMessages(listMessages, 42)).resolves.toEqual(items)

    expect(listMessages).toHaveBeenCalledTimes(1)
    expect(listMessages).toHaveBeenCalledWith(42, { page: 1, page_size: 100 })
  })

  it("returns the final full page when the latest page already has 100 messages", async () => {
    const latest = Array.from({ length: 100 }, (_, index) => message(index + 101))
    const listMessages = vi.fn()
      .mockResolvedValueOnce(page(Array.from({ length: 100 }, (_, index) => message(index + 1)), 200, 1))
      .mockResolvedValueOnce(page(latest, 200, 2))

    await expect(loadLatestAgentMessages(listMessages, 42)).resolves.toEqual(latest)

    expect(listMessages).toHaveBeenCalledTimes(2)
    expect(listMessages).toHaveBeenLastCalledWith(42, { page: 2, page_size: 100 })
  })

  it("fills a short final page from the previous page to return the latest 100 messages", async () => {
    const previous = Array.from({ length: 100 }, (_, index) => message(index + 101))
    const last = Array.from({ length: 50 }, (_, index) => message(index + 201))
    const listMessages = vi.fn()
      .mockResolvedValueOnce(page(Array.from({ length: 100 }, (_, index) => message(index + 1)), 250, 1))
      .mockResolvedValueOnce(page(last, 250, 3))
      .mockResolvedValueOnce(page(previous, 250, 2))

    const loaded = await loadLatestAgentMessages(listMessages, 42)

    expect(loaded.map(item => item.id)).toEqual(Array.from({ length: 100 }, (_, index) => index + 151))
    expect(listMessages).toHaveBeenCalledTimes(3)
    expect(listMessages).toHaveBeenNthCalledWith(2, 42, { page: 3, page_size: 100 })
    expect(listMessages).toHaveBeenNthCalledWith(3, 42, { page: 2, page_size: 100 })
  })

  it("reuses the first page when filling a short second page", async () => {
    const first = Array.from({ length: 100 }, (_, index) => message(index + 1))
    const last = Array.from({ length: 50 }, (_, index) => message(index + 101))
    const listMessages = vi.fn()
      .mockResolvedValueOnce(page(first, 150, 1))
      .mockResolvedValueOnce(page(last, 150, 2))

    const loaded = await loadLatestAgentMessages(listMessages, 42)

    expect(loaded.map(item => item.id)).toEqual(Array.from({ length: 100 }, (_, index) => index + 51))
    expect(listMessages).toHaveBeenCalledTimes(2)
  })
})
