/**
 * AI 配置 API
 */
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

export const aiConfigApi = {
  /**
   * 获取 AI 配置
   */
  getConfig: () => {
    return request.get<any, { code: number; message: string; data: AIConfigResponse | null }>('/v1/ai/config')
  },

  /**
   * 保存 AI 配置
   */
  saveConfig: (data: AIConfigCreate) => {
    return request.post<AIConfigCreate, { code: number; message: string; data: AIConfigResponse }>('/v1/ai/config', data)
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
    const baseURL = import.meta.env.VITE_API_BASE_URL || ''
    const url = `${baseURL}/api/v1/ai/test`

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
      buffer = lines.pop() || ''  // 保留不完整的部分

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