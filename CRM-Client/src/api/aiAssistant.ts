/**
 * AI 助手 API
 */
import request from '@/utils/request'

export interface AIAssistantChatRequest {
  content: string
}

export interface AIAssistantSSEEvent {
  event: 'status' | 'content' | 'parsed' | 'result' | 'error'
  message?: string
  content?: string
  skill?: string
  action?: string
  params?: Record<string, unknown>
  reply_text?: string
  success?: boolean
}

export interface ChatHistoryItem {
  id: number
  request_text: string
  execution_result: string | null
  status: string
  created_at: string | null
}

export const aiAssistantApi = {
  /**
   * 获取聊天历史记录
   */
  getHistory: (limit: number = 20) => {
    return request.get<any, { code: number; message: string; data: ChatHistoryItem[] }>(
      `/api/v1/ai/history?limit=${limit}`
    )
  },

  /**
   * 发送聊天消息（SSE 流式响应）
   * @param data 聊天请求数据
   * @param onEvent SSE 事件回调
   * @param token JWT token
   * @returns Promise
   */
  chatSSE: async (
    data: AIAssistantChatRequest,
    onEvent: (event: AIAssistantSSEEvent) => void,
    token: string
  ): Promise<void> => {
    const baseURL = import.meta.env.VITE_API_BASE_URL || ''
    const url = `${baseURL}/api/v1/ai/chat`

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
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const eventData = JSON.parse(line.slice(6)) as AIAssistantSSEEvent
            onEvent(eventData)

            // 收到 result 或 error 事件后结束
            if (eventData.event === 'result' || eventData.event === 'error') {
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