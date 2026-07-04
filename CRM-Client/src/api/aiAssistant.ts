/**
 * Web AI 助手 API
 * 用于 MagicWand 魔术棒功能
 * 支持 ReAct 循环、多工具依次确认、实体歧义消解
 */

export interface EntityContext {
  entity_type: 'customer' | 'opportunity' | 'lead' | 'contract'
  entity_id: number
  entity_name: string
}

export interface AIAssistantRequest {
  content: string
  tool?: string
  params?: Record<string, unknown>
  entity_context?: EntityContext  // 新增：实体上下文（JSON 格式）
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
  options?: { value: string; label: string }[]
}

/**
 * 工具调用（parsed_multi 事件中的单个工具）
 */
export interface ToolCall {
  tool: string
  params: Record<string, unknown>
  param_definitions?: Record<string, ParamDefinition>
  missing_params?: string[]
  reply_text: string
}

/**
 * 实体候选（歧义消解时展示）
 */
export interface EntityCandidate {
  id: number
  name: string
  display_info: string
}

/**
 * 已执行结果（ReAct 多轮时记录）
 */
export interface ExecutedResult {
  tool: string
  success: boolean
  message: string
  data?: unknown
}

/**
 * SSE 事件类型（扩展支持 ReAct 循环 + Human-in-the-Loop）
 */
/**
 * Glue SSE 事件类型（Task 5.2：对齐 GlueSSEStreamer）
 * 替代原有 ReAct 专有事件枚举
 */
export type SSEEventType =
  | 'start'           // 会话启动
  | 'intent'          // 意图识别
  | 'entity'          // 实体消解
  | 'preview'         // 预览生成
  | 'execute'         // 执行动作
  | 'result'          // 最终结果
  | 'complete'        // 会话完成
  | 'error'           // 错误

/**
 * 上下文汇总信息
 */
export interface ContextSummary {
  entity_type: string
  entity_id: number
  basic_info: Record<string, unknown>
  related_entities: {
    type: string
    id: number
    name: string
    status?: string
    amount?: number
  }[]
  recent_activities: {
    type: string
    content?: string
    method?: string
    date?: string
  }[]
}

export interface AIAssistantSSEEvent {
  event: SSEEventType
  message?: string
  content?: string
  answer?: string       // Agent 最终回答（complete 事件）
  tool?: string
  params?: Record<string, unknown>
  param_definitions?: Record<string, ParamDefinition>
  missing_params?: string[]
  reply_text?: string
  success?: boolean
  data?: unknown
  is_partial?: boolean  // 是否部分结果

  // 上下文汇总
  summary?: ContextSummary
  enhanced_content_preview?: string
  session_id?: string  // ReAct 会话 ID

  // ReAct 循环相关字段
  round?: number
  max_rounds?: number
  tool_calls?: ToolCall[]
  entity_type?: 'opportunity' | 'contact' | 'contract'
  candidates?: EntityCandidate[]
  previous_results?: ExecutedResult[]
  results?: ExecutedResult[]  // round_completed 事件使用

  // Human-in-the-Loop 字段（waiting_for_user 事件）
  question?: string            // AI 向用户的问题
  options?: string[]           // 可选选项（用于选择场景）
  missing_fields?: string[]    // 缺失字段（用于信息补充场景）
  context_hint?: string        // 上下文提示
  interaction_type?: 'select' | 'input' | 'mixed'  // 交互类型
}

/**
 * 继续 ReAct 循环请求
 */
export interface ContinueReactRequest {
  round: number
  original_content: string
  executed_results: ExecutedResult[]
}

/**
 * 用户回复后继续 ReAct 循环请求（新接口）
 */
export interface ReactContinueWithUserResponseRequest {
  session_id: string
  user_response: string
}

export const aiAssistantApi = {
  /**
   * AI 助手聊天（SSE 流式响应）
   * 已迁移到新 Agent API（/api/v1/agent/chat）
   */
  chatSSE: async (
    data: AIAssistantRequest,
    onEvent: (event: AIAssistantSSEEvent) => void,
    token: string
  ): Promise<void> => {
    const url = '/api/v1/agent/chat'  // ✅ 新 Agent API 端点
    console.log('[AIAssistant] SSE request URL:', url)
    console.log('[AIAssistant] SSE request data:', data)
    console.log('[AIAssistant] SSE request token:', token ? 'exists' : 'empty')

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        content: data.content,
        session_id: data.entity_context ? undefined : undefined  // Agent API 自动生成 session_id
      })
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
        // 新 Agent API 使用标准 SSE 格式：event: xxx\ndata: xxx
        if (line.startsWith('event: ')) {
          const eventMatch = line.match(/^event: (\S+)\ndata: (.+)$/s)
          if (eventMatch) {
            try {
              const eventData = JSON.parse(eventMatch[2]) as AIAssistantSSEEvent
              eventData.event = eventMatch[1] as SSEEventType
              onEvent(eventData)

              if (eventData.event === 'complete' || eventData.event === 'error') {
                return
              }
            } catch {
              // 忽略解析错误
            }
          }
        }
        // 兼容旧格式：data: xxx（不带 event 字段）
        else if (line.startsWith('data: ')) {
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

    // 处理 buffer 中剩余的数据（流结束时最后一个事件可能没有 \n\n 结尾）
    if (buffer.trim()) {
      // 新格式：event: xxx\ndata: xxx
      if (buffer.startsWith('event: ')) {
        const eventMatch = buffer.match(/^event: (\S+)\ndata: (.+)$/s)
        if (eventMatch) {
          try {
            const eventData = JSON.parse(eventMatch[2]) as AIAssistantSSEEvent
            eventData.event = eventMatch[1] as SSEEventType
            onEvent(eventData)
          } catch {
            // 忽略解析错误
          }
        }
      }
      // 兼容旧格式：data: xxx
      else if (buffer.startsWith('data: ')) {
        try {
          const eventData = JSON.parse(buffer.slice(6)) as AIAssistantSSEEvent
          onEvent(eventData)
        } catch {
          // 忽略解析错误
        }
      }
    }
  }
}