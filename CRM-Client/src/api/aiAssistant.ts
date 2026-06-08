/**
 * Web AI 助手 API
 * 用于 MagicWand 魔术棒功能
 */

export interface AIAssistantRequest {
  content: string
  tool?: string
  params?: Record<string, unknown>
}

/**
 * 参数定义（用于动态表单渲染）
 */
export interface ParamDefinition {
  label: string
  type: 'text' | 'number' | 'date' | 'select' | 'textarea'
  required: boolean
  placeholder: string
  default_value?: string
  options?: Array<{ value: string; label: string }>
}

export interface AIAssistantSSEEvent {
  event: 'status' | 'content' | 'parsed' | 'result' | 'error'
  message?: string
  content?: string
  tool?: string
  params?: Record<string, unknown>
  param_definitions?: Record<string, ParamDefinition>  // 参数定义
  missing_params?: string[]                             // 缺失的必填字段
  reply_text?: string
  success?: boolean
  data?: unknown
}

export const aiAssistantApi = {
  /**
   * AI 助手聊天（SSE 流式响应）
   */
  chatSSE: async (
    data: AIAssistantRequest,
    onEvent: (event: AIAssistantSSEEvent) => void,
    token: string
  ): Promise<void> => {
    const url = '/api/v1/assistant/chat'
    console.log('[AIAssistant] SSE request URL:', url)
    console.log('[AIAssistant] SSE request data:', data)
    console.log('[AIAssistant] SSE request token:', token ? 'exists' : 'empty')

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(data)
    })

    console.log('[AIAssistant] SSE response status:', response.status)

    if (!response.ok) {
      const errorText = await response.text()
      console.error('[AIAssistant] SSE error response:', errorText)
      throw new Error(`HTTP error: ${response.status} - ${errorText}`)
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
            const eventData = JSON.parse(line.slice(6)) as AIAssistantSSEEvent
            onEvent(eventData)

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