import request from "@/utils/request"
import type { PaginatedResponse } from "@/types/pagination"

/* eslint-disable crmwolf/require-zod-schema */

export type AgentEventType =
  | "session"
  | "message"
  | "agent_step"
  | "intent"
  | "semantic_parsed"
  | "follow_up_quality_evaluated"
  | "follow_up_quality_required"
  | "follow_up_quality_completed"
  | "follow_up_quality_failed"
  | "entity_parse"
  | "tool_result"
  | "customer_candidates"
  | "business_context_loaded"
  | "business_suggestions"
  | "suggestion_failed"
  | "suspended_tasks_loaded"
  | "turn_relation_classified"
  | "turn_relation_clarification_required"
  | "suspended_task_resumed"
  | "confirmation_required"
  | "customer_selection_required"
  | "customer_selected"
  | "customer_selection_failed"
  | "opportunity_fields_required"
  | "opportunity_fields_completed"
  | "contact_fields_required"
  | "contact_fields_completed"
  | "invoice_title_fields_required"
  | "invoice_title_fields_completed"
  | "deployment_info_fields_required"
  | "deployment_info_fields_completed"
  | "customer_member_fields_required"
  | "customer_member_fields_completed"
  | "payment_fields_required"
  | "payment_fields_completed"
  | "business_selection_required"
  | "business_selected"
  | "business_selection_failed"
  | "action_review_started"
  | "action_review_risk_classified"
  | "action_review_confidence_scored"
  | "action_review_decided"
  | "action_review_finished"
  | "action_auto_execution_queued"
  | "pending_interruption_confirmation_required"
  | "pending_task_interrupted"
  | "task_completed"
  | "task_failed"
  | "task_cancelled"
  | "final"
  | "done"
  | "error"

export type AgentContentFormat = "text" | "markdown"

export interface AgentChatRequest {
  content: string
  session_id?: number
  session_key?: string
  interaction_metadata?: Record<string, unknown>
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
  content_format?: AgentContentFormat | string
  message?: string
  role?: "user" | "assistant" | "system" | string
  session_id?: number
  session_key?: string
  message_id?: number
  task_id?: number
  task_key?: string
  intent?: string
  technical_intent?: string
  intent_label?: string
  confidence?: number
  execution_confidence?: number
  risk_level?: "low" | "medium" | "high" | string
  decision?: "auto_execute" | "require_confirmation" | "require_fields" | "require_choice" | "block" | string
  reason?: string
  source_event?: string
  step?: string
  status?: "started" | "completed" | string
  parse_source?: string | null
  model?: string | null
  fallback_reason?: string | null
  fallback_error?: string | null
  fallback_error_message?: string | null
  structured_output_strategy?: string | null
  score?: number
  passed?: boolean
  quality_source?: string | null
  missing_aspects?: string[]
  action?: string
  tool_name?: string
  success?: boolean
  customers?: Record<string, unknown>[]
  customer?: Record<string, unknown>
  parsed?: Record<string, unknown>
  summary?: string
  suggestions?: Record<string, unknown>[]
  need_user_choice?: boolean
  clarification_question?: string | null
  suggestion_source?: string | null
  payload?: Record<string, unknown>
  interaction?: AgentInteraction
  data?: unknown
  error_message?: string | null
  status_code?: number | null
}

export interface AgentInteractionChoice {
  label: string
  value: string
  metadata?: Record<string, unknown>
}

export interface AgentInteractionField {
  key: string
  label: string
  type: "text" | "number" | "date" | "select" | string
  required?: boolean
  placeholder?: string
  default_value?: string | number | null
  options?: AgentInteractionChoice[]
}

export interface AgentInteraction {
  schema_version?: "agent.interaction.v1" | string
  interaction_id?: string
  task_id?: number | string
  task_key?: string
  type: "choice" | "form" | "text" | string
  business_action?: string | null
  status?: "waiting_user_input" | "waiting_confirmation" | "completed" | "cancelled" | "failed" | string
  title?: string
  prompt?: string
  placeholder?: string
  submit_label?: string
  choices?: AgentInteractionChoice[]
  fields?: AgentInteractionField[]
  payload?: Record<string, unknown>
  allow_free_text?: boolean
  allow_cancel?: boolean
}

export const agentApi = {
  listSessions: (): Promise<PaginatedResponse<AgentSessionResponse>> => {
    return request.get<PaginatedResponse<AgentSessionResponse>>("/v1/agent/sessions")
  },

  listMessages: (sessionId: number, params?: { page?: number, page_size?: number }): Promise<PaginatedResponse<AgentMessageResponse>> => {
    return request.get<PaginatedResponse<AgentMessageResponse>>(`/v1/agent/sessions/${sessionId}/messages`, { params })
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
