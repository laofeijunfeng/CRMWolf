/**
 * AI 客户跟进解析 API
 */
import request from '@/utils/request'

export interface CustomerAIParseRequest {
  content: string
  customer_id: number
  customer_name: string
}

export interface CustomerAIFollowUpInfo {
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
  follow_up_info?: CustomerAIFollowUpInfo
}

export interface CustomerAICreateRequest {
  customer_id: number
  customer_name: string
  content: string
  method?: string | undefined
  next_action?: string | undefined
  next_follow_time?: string | undefined
}

export const customerAiApi = {
  /**
   * AI 解析客户跟进信息（SSE 流式响应）
   */
  parseSSE: async (
    data: CustomerAIParseRequest,
    onEvent: (event: CustomerAIParseSSEEvent) => void,
    token: string
  ): Promise<void> => {
    const baseURL = import.meta.env.VITE_API_BASE_URL || ''
    const url = `${baseURL}/v1/customers/ai/parse`

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
      buffer = lines.pop() || ''

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
   * 从 AI 解析结果创建客户跟进记录
   */
  create: (data: CustomerAICreateRequest) => {
    return request.post<{ id: number; customer_id: number; content: string }>(
      '/v1/customers/ai/create',
      data
    )
  }
}