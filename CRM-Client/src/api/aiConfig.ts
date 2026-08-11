/**
 * AI 配置 API
 */
import { z } from 'zod'
import request from '@/utils/request'

export interface AIConfigResponse {
  id: number
  api_host: string
  api_key_masked: string
  model_name: string
  temperature: number
  max_tokens: number
  updated_at: string | null
}

export interface AIConfigCreate {
  api_host: string
  api_key: string
  model_name: string
}

export interface AITestRequest {
  test_message: string
}

export interface AITestResponse {
  success: boolean
  message: string
  ai_response: string | null
}

export interface SSEEvent {
  event: 'start' | 'content' | 'done' | 'error'
  message?: string
  content?: string
  success?: boolean
  full_content?: string
}

const AIConfigResponseSchema = z.object({
  id: z.number(),
  api_host: z.string(),
  api_key_masked: z.string(),
  model_name: z.string(),
  temperature: z.number(),
  max_tokens: z.number(),
  updated_at: z.string().nullable(),
}).passthrough()

const AIConfigEnvelopeSchema = z.object({
  code: z.number(),
  message: z.string(),
  data: AIConfigResponseSchema.nullable(),
})

const AIConfigSaveEnvelopeSchema = z.object({
  code: z.number(),
  message: z.string(),
  data: AIConfigResponseSchema,
})

type AIConfigEnvelope = z.infer<typeof AIConfigEnvelopeSchema>
type AIConfigSaveEnvelope = z.infer<typeof AIConfigSaveEnvelopeSchema>

export const aiConfigApi = {
  /**
   * 获取 AI 配置
   */
  async getConfig(): Promise<AIConfigEnvelope> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get('/v1/ai/config')
    return AIConfigEnvelopeSchema.parse(raw)
  },

  /**
   * 保存 AI 配置
   */
  async saveConfig(data: AIConfigCreate): Promise<AIConfigSaveEnvelope> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.post('/v1/ai/config', data)
    return AIConfigSaveEnvelopeSchema.parse(raw)
  },

  /**
   * 测试 AI 连接（SSE 流式响应）
   * @param data 测试请求数据
   * @param onEvent SSE 事件回调
   * @returns Promise
   */
  testConnectionSSE: async (
    data: AITestRequest,
    onEvent: (event: SSEEvent) => void,
    token: string
  ): Promise<void> => {
    const url = '/api/v1/ai/test'

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(data)
    })

    if (!response.ok) {
      throw new Error(`HTTP error: ${response.status}`)
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('No response body')
    }

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // 解析 SSE 数据（按双换行分隔）
      const lines = buffer.split('\n\n')
      buffer = lines.pop() ?? ''  // 保留不完整的部分

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const eventData = JSON.parse(line.slice(6)) as SSEEvent
            onEvent(eventData)

            // 收到 done 或 error 事件后结束
            if (eventData.event === 'done' || eventData.event === 'error') {
              return
            }
          } catch {
            // 忽略解析错误
          }
        }
      }
    }
  }
}
