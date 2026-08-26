import { describe, expect, it, vi } from 'vitest'

import type { AgentSessionResponse, AgentUIEnvelope } from '@/api/agent'
import { isVisibleAgentMessage, loadLatestAgentMessages, resolveInitialAgentSession } from '@/components/agent/agentHistory'
import { AgentUIEnvelopeSchema } from '@/schemas/agent-contracts'
import type { PaginatedResponse } from '@/types/pagination'

const message = (id: number): AgentUIEnvelope => AgentUIEnvelopeSchema.parse({
  schema_version: 'crm.agent.ui.v1',
  message_id: id,
  turn_id: `turn-${id}`,
  role: id % 2 === 0 ? 'assistant' : 'user',
  state: 'final',
  blocks: [{ id: `text-${id}`, type: 'text', format: 'plain', text: `message ${id}` }],
  suggested_actions: [],
  metadata: {},
})

const page = (
  items: AgentUIEnvelope[],
  total: number,
  pageNumber: number,
  pageSize = 100,
): PaginatedResponse<AgentUIEnvelope> => ({
  items,
  total,
  page: pageNumber,
  page_size: pageSize,
  total_pages: Math.ceil(total / pageSize),
})

const session = (
  id: number,
  lastModifiedTime = `2026-07-29T00:${String(id).padStart(2, '0')}:00Z`,
): AgentSessionResponse => ({
  id,
  session_key: `session-${id}`,
  team_id: 1,
  user_id: 2,
  title: `session ${id}`,
  status: 'active',
  summary: null,
  context_json: null,
  created_time: lastModifiedTime,
  last_modified_time: lastModifiedTime,
})

describe('resolveInitialAgentSession', () => {
  it('uses the latest server session as the Agent default entry', () => {
    expect(resolveInitialAgentSession([session(3), session(2), session(1)], 1)?.id).toBe(3)
  })

  it('keeps the cached session only when it already points to the latest session', () => {
    expect(resolveInitialAgentSession([session(3), session(2), session(1)], 3)?.id).toBe(3)
  })

  it('returns undefined when the user has no Agent session history', () => {
    expect(resolveInitialAgentSession([], 1)).toBeUndefined()
  })
})

describe('loadLatestAgentMessages', () => {
  it('filters internal state-update turns from visible Agent history', async () => {
    const visible = message(1)
    const stateUpdate = AgentUIEnvelopeSchema.parse({
      ...message(2),
      metadata: { display: 'STATE_UPDATE' },
    })
    const listMessages = vi.fn().mockResolvedValue(page([visible, stateUpdate], 2, 1))

    await expect(loadLatestAgentMessages(listMessages, 42)).resolves.toEqual([visible])
    expect(isVisibleAgentMessage(visible)).toBe(true)
    expect(isVisibleAgentMessage(stateUpdate)).toBe(false)
  })

  it('returns the first page when a session has at most one page', async () => {
    const items = [message(1), message(2)]
    const listMessages = vi.fn().mockResolvedValue(page(items, 2, 1))

    await expect(loadLatestAgentMessages(listMessages, 42)).resolves.toEqual(items)
    expect(listMessages).toHaveBeenCalledWith(42, { page: 1, page_size: 100 })
  })

  it('returns the final full page when the latest page already has 100 messages', async () => {
    const latest = Array.from({ length: 100 }, (_, index) => message(index + 101))
    const listMessages = vi.fn()
      .mockResolvedValueOnce(page(Array.from({ length: 100 }, (_, index) => message(index + 1)), 200, 1))
      .mockResolvedValueOnce(page(latest, 200, 2))

    await expect(loadLatestAgentMessages(listMessages, 42)).resolves.toEqual(latest)
    expect(listMessages).toHaveBeenLastCalledWith(42, { page: 2, page_size: 100 })
  })

  it('fills a short final page from the previous page to return the latest 100 messages', async () => {
    const previous = Array.from({ length: 100 }, (_, index) => message(index + 101))
    const last = Array.from({ length: 50 }, (_, index) => message(index + 201))
    const listMessages = vi.fn()
      .mockResolvedValueOnce(page(Array.from({ length: 100 }, (_, index) => message(index + 1)), 250, 1))
      .mockResolvedValueOnce(page(last, 250, 3))
      .mockResolvedValueOnce(page(previous, 250, 2))

    const loaded = await loadLatestAgentMessages(listMessages, 42)
    expect(loaded.map(item => item.message_id)).toEqual(Array.from({ length: 100 }, (_, index) => index + 151))
  })

  it('reuses the first page when filling a short second page', async () => {
    const first = Array.from({ length: 100 }, (_, index) => message(index + 1))
    const last = Array.from({ length: 50 }, (_, index) => message(index + 101))
    const listMessages = vi.fn()
      .mockResolvedValueOnce(page(first, 150, 1))
      .mockResolvedValueOnce(page(last, 150, 2))

    const loaded = await loadLatestAgentMessages(listMessages, 42)
    expect(loaded.map(item => item.message_id)).toEqual(Array.from({ length: 100 }, (_, index) => index + 51))
    expect(listMessages).toHaveBeenCalledTimes(2)
  })

  it('keeps paging backward when the latest full page only contains state updates', async () => {
    const first = Array.from({ length: 100 }, (_, index) => message(index + 1))
    const latestVisible = Array.from({ length: 100 }, (_, index) => message(index + 101))
    const stateUpdates = Array.from({ length: 100 }, (_, index) => AgentUIEnvelopeSchema.parse({
      ...message(index + 201),
      metadata: { display: 'STATE_UPDATE' },
    }))
    const listMessages = vi.fn()
      .mockResolvedValueOnce(page(first, 300, 1))
      .mockResolvedValueOnce(page(stateUpdates, 300, 3))
      .mockResolvedValueOnce(page(latestVisible, 300, 2))

    const loaded = await loadLatestAgentMessages(listMessages, 42)

    expect(loaded.map(item => item.message_id)).toEqual(
      Array.from({ length: 100 }, (_, index) => index + 101),
    )
    expect(listMessages).toHaveBeenCalledTimes(3)
    expect(listMessages).toHaveBeenLastCalledWith(42, { page: 2, page_size: 100 })
  })
})
