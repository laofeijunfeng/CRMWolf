/** AI 配置 API */
import { z } from 'zod'
import request from '@/utils/request'

export type StructuredOutputMode = 'json_object' | 'json_schema'
export type AssistantVerificationState = 'UNVERIFIED' | 'VERIFIED'

export interface AIConfigResponse {
  id: number
  api_host: string
  api_key_masked: string
  model_name: string
  temperature: number
  max_tokens: number
  updated_at: string | null
  structured_output_mode: StructuredOutputMode
  assistant_verification_state: AssistantVerificationState
  assistant_verified_at: string | null
}

export interface AIConfigCreate {
  api_host: string
  api_key: string
  model_name: string
  structured_output_mode: StructuredOutputMode
}

export interface AITestRequest { test_message: string }

export interface AITestResponse {
  success: boolean
  message: string
  ai_response: string | null
}
export type AssistantVerificationStage = 'CONFIGURATION' | 'ROOT_DECISION' | 'MEETING_STREAM' | 'QUALITY_STREAM' | 'SAVE_VERIFICATION' | 'COMPLETE'
export type AssistantVerificationCode =
  | 'CONFIGURATION_ERROR'
  | 'REQUEST_PROTOCOL_ERROR'
  | 'AUTHENTICATION_ERROR'
  | 'UPSTREAM_UNAVAILABLE'
  | 'UPSTREAM_TIMEOUT'
  | 'MODEL_OUTPUT_INVALID'
  | 'INTERNAL_ERROR'
  | 'CONFIGURATION_CHANGED'

export interface AssistantCapabilityResult {
  success: boolean
  stage: AssistantVerificationStage
  code: AssistantVerificationCode | null
  message: string
  output_mode: StructuredOutputMode | null
  verified_at: string | null
}

export interface SSEEvent {
  event: 'start' | 'content' | 'done' | 'error'
  message?: string
  content?: string
  success?: boolean
  full_content?: string
}

const AIConfigResponseSchema = z.object({
  id: z.number(), api_host: z.string(), api_key_masked: z.string(), model_name: z.string(),
  temperature: z.number(), max_tokens: z.number(), updated_at: z.string().nullable(),
  structured_output_mode: z.enum(['json_object', 'json_schema']),
  assistant_verification_state: z.enum(['UNVERIFIED', 'VERIFIED']),
  assistant_verified_at: z.string().nullable(),
}).passthrough()
const AIConfigEnvelopeSchema = z.object({ code: z.number(), message: z.string(), data: AIConfigResponseSchema.nullable() })
const AIConfigSaveEnvelopeSchema = z.object({ code: z.number(), message: z.string(), data: AIConfigResponseSchema })
const AssistantCapabilityResultSchema = z.object({
  success: z.boolean(), stage: z.enum(['CONFIGURATION', 'ROOT_DECISION', 'MEETING_STREAM', 'QUALITY_STREAM', 'SAVE_VERIFICATION', 'COMPLETE']),
  code: z.enum(['CONFIGURATION_ERROR', 'REQUEST_PROTOCOL_ERROR', 'AUTHENTICATION_ERROR', 'UPSTREAM_UNAVAILABLE', 'UPSTREAM_TIMEOUT', 'MODEL_OUTPUT_INVALID', 'INTERNAL_ERROR', 'CONFIGURATION_CHANGED']).nullable(),
  message: z.string(), output_mode: z.enum(['json_object', 'json_schema']).nullable(), verified_at: z.string().nullable(),
})
const AssistantCapabilityEnvelopeSchema = z.object({ code: z.number(), message: z.string(), data: AssistantCapabilityResultSchema })

type AIConfigEnvelope = z.infer<typeof AIConfigEnvelopeSchema>
type AIConfigSaveEnvelope = z.infer<typeof AIConfigSaveEnvelopeSchema>

export const aiConfigApi = {
  async getConfig(): Promise<AIConfigEnvelope> {
    // eslint-disable-next-line crmwolf/require-zod-schema -- parsed at this boundary
    const raw: unknown = await request.get('/v1/ai/config')
    return AIConfigEnvelopeSchema.parse(raw)
  },
  async saveConfig(data: AIConfigCreate): Promise<AIConfigSaveEnvelope> {
    // eslint-disable-next-line crmwolf/require-zod-schema -- parsed at this boundary
    const raw: unknown = await request.post('/v1/ai/config', data)
    return AIConfigSaveEnvelopeSchema.parse(raw)
  },
  async testAssistantCapability(): Promise<AssistantCapabilityResult> {
    // eslint-disable-next-line crmwolf/require-zod-schema -- parsed at this boundary
    const raw: unknown = await request.post('/v1/ai/test-assistant', {}, { timeout: 310000 })
    return AssistantCapabilityEnvelopeSchema.parse(raw).data
  },
  testConnectionSSE: async (
    data: AITestRequest,
    onEvent: (event: SSEEvent) => void,
    token: string,
  ): Promise<void> => {
    const response = await fetch('/api/v1/ai/test', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify(data),
    })
    if (!response.ok) throw new Error(`HTTP error: ${response.status}`)
    const reader = response.body?.getReader()
    if (!reader) throw new Error('No response body')
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const eventData = JSON.parse(line.slice(6)) as SSEEvent
          onEvent(eventData)
          if (eventData.event === 'done' || eventData.event === 'error') return
        } catch { /* Ignore incomplete SSE records. */ }
      }
    }
  },
}
