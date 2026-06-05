/**
 * AI 采购方式解析 API
 */
import request from '@/utils/request'

export interface ProcurementAIParseRequest {
  content: string
}

export interface ProcurementAIParsedStage {
  stage_name: string
  template_code: string
  win_probability: number
  sort_order: number
  is_default_start: boolean
  can_skip: boolean
  description?: string
}

export interface ProcurementAIParsedMethod {
  name: string
  code: string
  description?: string
  stages: ProcurementAIParsedStage[]
}

export interface ProcurementAIParseSSEEvent {
  event: 'status' | 'content' | 'parsed' | 'error'
  message?: string
  content?: string
  method?: ProcurementAIParsedMethod
  thinking_process?: string
}

export interface ProcurementAICreateRequest {
  name: string
  code: string
  description?: string
  stages: ProcurementAIParsedStage[]
  team_id?: number
}

export interface ProcurementAICreateResult {
  success: boolean
  message: string
  data: {
    method: {
      id: number
      name: string
      code: string
      description?: string
    }
    stages: Array<{
      id: number
      stage_name: string
      template_code: string
      win_probability: number
      sort_order: number
      is_default_start: boolean
    }>
  }
}

export const procurementAiApi = {
  /**
   * AI 解析采购方式配置（SSE 流式响应）
   * @param data 解析请求数据
   * @param onEvent SSE 事件回调
   * @param token JWT token
   */
  parseSSE: async (
    data: ProcurementAIParseRequest,
    onEvent: (event: ProcurementAIParseSSEEvent) => void,
    token: string
  ): Promise<void> => {
    const url = '/api/v1/procurement-ai/parse'

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
            const eventData = JSON.parse(line.slice(6)) as ProcurementAIParseSSEEvent
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
   * 从 AI 解析结果创建采购方式
   * @param data 创建请求数据
   * @returns 创建成功的采购方式数据
   */
  createFromAI: (data: ProcurementAICreateRequest) => {
    return request.post<ProcurementAICreateResult>(
      '/v1/procurement-ai/create',
      data
    )
  }
}