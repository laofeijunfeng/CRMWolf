import request from "@/utils/request"

/* eslint-disable crmwolf/require-zod-schema */

export type AgentEventType =
  | "session"
  | "message"
  | "intent"
  | "entity_parse"
  | "tool_result"
  | "customer_candidates"
  | "confirmation_required"
  | "customer_selection_required"
  | "customer_selected"
  | "customer_selection_failed"
  | "contact_fields_required"
  | "contact_fields_completed"
  | "invoice_title_fields_required"
  | "invoice_title_fields_completed"
  | "deployment_info_fields_required"
  | "deployment_info_fields_completed"
  | "task_completed"
  | "task_failed"
  | "final"
  | "done"
  | "error"

export interface AgentChatRequest {
  content: string
  session_id?: number
  session_key?: string
}

export interface AgentSessionResponse {
  id: number
  session_key: string
  title?: string | null
  status: string
  summary?: string | null
  created_time: string
  last_modified_time: string
}

export interface AgentMessageResponse {
  id: number
  role: "user" | "assistant" | "system" | string
  event_type?: string | null
  content?: string | null
  payload_json?: Record<string, unknown> | null
  created_time: string
}

export interface AgentChatSSEEvent {
  event: AgentEventType
  content?: string
  message?: string
  role?: "user" | "assistant" | "system" | string
  session_id?: number
  session_key?: string
  message_id?: number
  task_id?: number
  task_key?: string
  intent?: string
  action?: string
  tool_name?: string
  success?: boolean
  customers?: Record<string, unknown>[]
  customer?: Record<string, unknown>
  parsed?: Record<string, unknown>
  payload?: Record<string, unknown>
  data?: unknown
  error_message?: string | null
  status_code?: number | null
}

export const agentApi = {
  listSessions: (): Promise<{ items: AgentSessionResponse[]; total: number }> => {
    return request.get<{ items: AgentSessionResponse[]; total: number }>("/v1/agent/sessions")
  },

  listMessages: (sessionId: number): Promise<AgentMessageResponse[]> => {
    return request.get<AgentMessageResponse[]>(`/v1/agent/sessions/${sessionId}/messages`)
  },

  chatStream: async (
    data: AgentChatRequest,
    onEvent: (event: AgentChatSSEEvent) => void,
    token: string
  ): Promise<void> => {
    const response = await fetch("/api/v1/agent/chat/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`,
      },
      body: JSON.stringify(data),
    })

    if (!response.ok) {
      throw new Error(`HTTP error: ${response.status}`)
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error("No response body")
    }

    const decoder = new TextDecoder()
    let buffer = ""

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const chunks = buffer.split("\n\n")
      buffer = chunks.pop() ?? ""

      for (const chunk of chunks) {
        const dataLine = chunk
          .split("\n")
          .find(line => line.startsWith("data: "))

        if (dataLine === undefined) continue

        try {
          const event = JSON.parse(dataLine.slice(6)) as AgentChatSSEEvent
          onEvent(event)
          if (event.event === "done" || event.event === "error") {
            return
          }
        } catch {
          // Ignore malformed SSE frames and continue reading.
        }
      }
    }
  },
}
