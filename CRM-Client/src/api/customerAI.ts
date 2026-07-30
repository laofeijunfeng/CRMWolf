/**
 * AI 客户活动解析 API
 */
import request from '@/utils/request'
import { z } from 'zod'

export interface CustomerAIParseRequest {
  content: string
  customer_id: number
  customer_name: string
}

export interface CustomerAIActivityInfo {
  content: string | null
  method: string | null
  next_action: string | null
  next_follow_time: string | null
}

export interface CustomerAIParseSSEEvent {
  event: 'status' | 'content' | 'parsed' | 'error'
  message?: string
  content?: string
  customer_id?: number
  customer_name?: string
  follow_up_info?: CustomerAIActivityInfo
}

export interface CustomerAICreateRequest {
  customer_id: number
  customer_name: string
  content: string
  method?: string | undefined
  next_action?: string | undefined
  next_follow_time?: string | undefined
}

const CustomerAICreateResponseSchema = z.object({
  id: z.number(),
  customer_id: z.number(),
  source_content: z.string(),
  activity_kind: z.string()
})

type CustomerAICreateResponse = z.infer<typeof CustomerAICreateResponseSchema>

export const customerAiApi = {
  /**
   * AI 解析客户活动信息（SSE 流式响应）
   */
  parseSSE: async (
    data: CustomerAIParseRequest,
    onEvent: (event: CustomerAIParseSSEEvent) => void,
    token: string
  ): Promise<void> => {
    const url = '/api/v1/customers/ai/parse'

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
      const lines = buffer.split('\n\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const eventData = JSON.parse(line.slice(6)) as CustomerAIParseSSEEvent
            onEvent(eventData)

            if (eventData.event === 'parsed' || eventData.event === 'error') {
              return
            }
          } catch {
            // 忽略解析错误
          }
        }
      }
    }
  },

  /**
   * 从 AI 解析结果创建客户活动
   */
  create: async (data: CustomerAICreateRequest): Promise<CustomerAICreateResponse> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.post('/v1/customers/ai/create', data)
    return CustomerAICreateResponseSchema.parse(raw)
  }
}
