/**
 * AI 线索解析 API
 */
import request from '@/utils/request'

export interface LeadAIParseRequest {
  content: string
}

export interface LeadAIParsedInfo {
  lead_name: string | null
  source: string | null
  city: string | null
  company_scale: string | null
  contact_name: string | null
  contact_phone: string | null
  missing_fields: string[]
}

export interface LeadAIFollowUpInfo {
  content: string | null
  next_action: string | null
  next_follow_time: string | null
}

export interface LeadAIParseSSEEvent {
  event: 'status' | 'content' | 'parsed' | 'error'
  message?: string
  content?: string
  lead_info?: LeadAIParsedInfo
  follow_up_info?: LeadAIFollowUpInfo
  thinking_process?: string
}

export interface LeadAICreateRequest {
  lead_name: string
  source: string
  city: string
  contact_name: string
  contact_phone: string
  company_scale?: string
  follow_up_content?: string
  next_action?: string
  next_follow_time?: string
}

export interface LeadAIResult {
  id: number
  lead_name: string
  contact_name: string
  contact_phone: string
  source: string
  city: string
  company_scale?: string
  status: number
  created_time: string
}

export const leadAiApi = {
  /**
   * AI 解析线索信息（SSE 流式响应）
   * @param data 解析请求数据
   * @param onEvent SSE 事件回调
   * @param token JWT token
   */
  parseSSE: async (
    data: LeadAIParseRequest,
    onEvent: (event: LeadAIParseSSEEvent) => void,
    token: string
  ): Promise<void> => {
    const url = '/api/v1/leads/ai/parse'

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

      // 解析 SSE 数据
      const lines = buffer.split('\n\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const eventData = JSON.parse(line.slice(6)) as LeadAIParseSSEEvent
            onEvent(eventData)

            // 收到 parsed 或 error 事件后结束
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
   * 从 AI 解析结果创建线索
   * @param data 创建请求数据
   * @returns 创建成功的线索数据
   */
  createFromAI: (data: LeadAICreateRequest) => {
    return request.post<LeadAIResult>(
      '/v1/leads/ai/create',
      data
    )
  }
}