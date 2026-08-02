import type { AgentMessageResponse, AgentSessionResponse } from "@/api/agent"
import type { PaginatedResponse } from "@/types/pagination"

type ListAgentMessages = (
  sessionId: number,
  params: { page: number, page_size: number }
) => Promise<PaginatedResponse<AgentMessageResponse>>

export const AGENT_HISTORY_PAGE_SIZE = 100

export const resolveInitialAgentSession = (
  sessions: AgentSessionResponse[],
  storedSessionId?: number
): AgentSessionResponse | undefined => {
  const latestSession = sessions[0]
  if (latestSession === undefined) return undefined

  const storedSession = sessions.find(session => session.id === storedSessionId)
  if (storedSession?.id === latestSession.id) return storedSession

  return latestSession
}

export const loadLatestAgentMessages = async (
  listMessages: ListAgentMessages,
  sessionId: number,
  pageSize = AGENT_HISTORY_PAGE_SIZE
): Promise<AgentMessageResponse[]> => {
  const firstPage = await listMessages(sessionId, { page: 1, page_size: pageSize })
  if (firstPage.total <= pageSize) return firstPage.items

  const totalPages = Math.max(firstPage.total_pages, Math.ceil(firstPage.total / pageSize), 1)
  const lastPage = await listMessages(sessionId, { page: totalPages, page_size: pageSize })
  if (lastPage.items.length >= pageSize || totalPages <= 1) {
    return lastPage.items.slice(-pageSize)
  }

  const previousPageItems = totalPages - 1 === 1
    ? firstPage.items
    : (await listMessages(sessionId, { page: totalPages - 1, page_size: pageSize })).items
  return [...previousPageItems, ...lastPage.items].slice(-pageSize)
}
