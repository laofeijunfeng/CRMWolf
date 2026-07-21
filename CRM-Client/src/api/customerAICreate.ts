/**
 * AI 创建客户 API
 */
import request from '@/utils/request'

/* eslint-disable crmwolf/require-zod-schema */

export interface CustomerAICreateParseRequest {
  content: string
}

export interface CustomerAIParsedInfo {
  account_name: string | null
  city: string | null
  company_scale: string | null
  source: string | null
  industry_hint: string | null
  missing_fields: string[]
}

export interface CustomerAIContactInfo {
  contact_name: string | null
  contact_phone: string | null
  contact_position: string | null
  contact_gender: string | null
  contact_email: string | null
}

export interface CustomerAIFollowUpInfo {
  content: string | null
  next_action: string | null
  next_follow_time: string | null
}

export interface CustomerAIParseSSEEvent {
  event: 'status' | 'content' | 'parsed' | 'error'
  message?: string
  content?: string
  customer_info?: CustomerAIParsedInfo
  contact_info?: CustomerAIContactInfo
  follow_up_info?: CustomerAIFollowUpInfo
  thinking_process?: string
}

export interface CustomerAICreateRequest {
  customer_info: CustomerAIParsedInfo
  contact_info: CustomerAIContactInfo
  follow_up_info?: CustomerAIFollowUpInfo
}

export const customerAiCreateApi = {
  /**
   * AI 解析客户创建信息（SSE 流式响应）
   */
  parseSSE: async (
    data: CustomerAICreateParseRequest,
    onEvent: (event: CustomerAIParseSSEEvent) => void,
    token: string
  ): Promise<void> => {
    const url = '/api/v1/customers/ai/create/parse'

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
   * 从 AI 解析结果创建客户
   */
  createFromAI: (data: CustomerAICreateRequest): Promise<{ id: number; account_name: string }> => {
    return request.post<{ id: number; account_name: string }>(
      '/v1/customers/ai/create/submit',
      data
    )
  }
}
