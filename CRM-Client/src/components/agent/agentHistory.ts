import type { AgentSessionResponse, AgentUIEnvelope } from '@/api/agent'
import type { PaginatedResponse } from '@/types/pagination'

type ListAgentMessages = (
  sessionId: number,
  params: { page: number, page_size: number }
) => Promise<PaginatedResponse<AgentUIEnvelope>>

export const AGENT_HISTORY_PAGE_SIZE = 100

export const isVisibleAgentMessage = (message: AgentUIEnvelope): boolean => (
  message.metadata.display !== 'STATE_UPDATE'
)

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
): Promise<AgentUIEnvelope[]> => {
  const firstPage = await listMessages(sessionId, { page: 1, page_size: pageSize })
  if (firstPage.total <= pageSize) return firstPage.items.filter(isVisibleAgentMessage)

  const totalPages = Math.max(firstPage.total_pages, Math.ceil(firstPage.total / pageSize), 1)
  const visiblePages: AgentUIEnvelope[][] = []
  let visibleCount = 0

  for (let pageNumber = totalPages; pageNumber >= 1 && visibleCount < pageSize; pageNumber -= 1) {
    const currentPage = pageNumber === 1
      ? firstPage
      : await listMessages(sessionId, { page: pageNumber, page_size: pageSize })
    const visibleItems = currentPage.items.filter(isVisibleAgentMessage)
    if (visibleItems.length === 0) continue
    visiblePages.push(visibleItems)
    visibleCount += visibleItems.length
  }

  return visiblePages.reverse().flat().slice(-pageSize)
}
