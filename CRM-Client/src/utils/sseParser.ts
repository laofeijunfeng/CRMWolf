/**
 * SSE 流解析器
 *
 * SSE (Server-Sent Events) 标准格式：
 * - 每个 event 格式：data: {JSON}\n\n
 * - 事件之间用双换行 (\n\n) 分隔
 * - 支持流式读取，处理数据分块到达的情况
 *
 * @example
 * // 使用方式
 * const reader = response.body.getReader()
 * await parseSSEStream(reader, {
 *   onEvent: (event) => console.log(event),
 *   onError: (e) => console.error(e)
 * })
 */

/**
 * SSE 解析选项
 */
export interface SSEParseOptions {
  /** 事件回调 */
  onEvent: (event: SSEEvent) => void
  /** 错误回调 */
  onError?: (error: Error) => void
  /** 完成回调 */
  onComplete?: () => void
}

/**
 * SSE 事件类型
 */
export type SSEEventType = string

/**
 * SSE 事件结构（通用定义）
 *
 * 注：具体字段由后端返回，此处定义常见字段
 * 后端可能直接在顶层返回字段，而不是嵌套在 data 中
 */
export interface SSEEvent {
  /** 事件类型 */
  event: SSEEventType

  // ========== 顶层字段（后端可能直接返回）==========

  /** 会话 ID */
  session_id?: string
  /** AI 向用户的问题 */
  question?: string
  /** 可选选项（用于选择场景） */
  options?: string[] | null
  /** 缺失字段（用于信息补充场景） */
  missing_fields?: string[]
  /** 字段选项配置（下拉选项等） */
  field_options?: Record<string, FieldOptionConfig>
  /** 上下文提示 */
  context_hint?: string

  // ========== ReAct 循环相关字段 ==========

  /** 当前轮数 */
  round?: number
  /** 最大轮数 */
  max_rounds?: number
  /** 工具名称 */
  tool?: string
  /** 工具参数 */
  params?: Record<string, unknown>
  /** 工具执行结果 */
  result?: {
    success: boolean
    message?: string
    data?: unknown
  }
  /** 前几轮执行结果 */
  previous_results?: Array<{
    tool: string
    success: boolean
    message?: string
    data?: unknown
  }>

  // ========== Workflow 相关字段 ==========

  /** Workflow 数据（部分事件使用） */
  data?: {
    session_id?: string
    step_id?: string
    workflow_name?: string
    description?: string
    success?: boolean
    message?: string
    error?: string
    result?: Record<string, unknown>
    question?: string
    options?: string[]
    missing_fields?: string[]
    field_options?: Record<string, FieldOptionConfig>
  }

  // ========== 结果相关字段 ==========

  /** 是否成功 */
  success?: boolean
  /** 消息 */
  message?: string
  /** 回复文本 */
  reply_text?: string
  /** 内容 */
  content?: string
  /** 状态消息 */
  status?: string
}

/**
 * 字段选项配置
 */
export interface FieldOptionConfig {
  /** 字段类型 */
  type: 'select' | 'text' | 'number' | 'date' | 'textarea'
  /** 下拉选项 */
  options?: string[]
  /** 默认值 */
  default?: string
  /** placeholder */
  placeholder?: string
}

/**
 * 从 ReadableStream 解析 SSE 事件
 *
 * @param reader ReadableStream 的 reader
 * @param options 解析选项
 */
export async function parseSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  options: SSEParseOptions
): Promise<void> {
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // SSE 标准格式：事件之间用 \n\n 分隔
      const events = buffer.split('\n\n')
      buffer = events.pop() || '' // 保留未完成的部分

      for (const eventStr of events) {
        const event = parseSSEEvent(eventStr)
        if (event) {
          options.onEvent(event)
        }
      }
    }

    // 处理 buffer 中剩余的数据（最后一个事件可能没有双换行结尾）
    if (buffer.trim()) {
      const event = parseSSEEvent(buffer)
      if (event) {
        options.onEvent(event)
      }
    }

    options.onComplete?.()
  } catch (error) {
    options.onError?.(error as Error)
  }
}

/**
 * 解析单个 SSE 事件字符串
 *
 * 支持两种格式：
 * 1. data: {JSON}
 * 2. event: xxx\ndata: {JSON}
 *
 * @param eventStr SSE 事件字符串
 * @returns 解析后的事件对象，解析失败返回 null
 */
function parseSSEEvent(eventStr: string): SSEEvent | null {
  const trimmed = eventStr.trim()

  if (!trimmed) {
    return null
  }

  // 格式 1: data: {...}
  if (trimmed.startsWith('data: ')) {
    try {
      return JSON.parse(trimmed.slice(6)) as SSEEvent
    } catch (e) {
      console.warn('[SSE Parser] Failed to parse event:', trimmed)
      return null
    }
  }

  // 格式 2: event: xxx\ndata: {...}
  const eventMatch = trimmed.match(/^event: (\S+)\ndata: (.+)$/s)
  if (eventMatch && eventMatch[1] && eventMatch[2]) {
    try {
      const data = JSON.parse(eventMatch[2]) as SSEEvent
      data.event = eventMatch[1]
      return data
    } catch (e) {
      console.warn('[SSE Parser] Failed to parse event:', trimmed)
      return null
    }
  }

  // 无法识别的格式
  console.warn('[SSE Parser] Unknown event format:', trimmed)
  return null
}

/**
 * 创建 SSE 解析函数（用于 fetch 回调）
 *
 * @param onEvent 事件回调
 * @param onError 错误回调（可选）
 * @returns 解析函数
 */
export function createSSEParser(
  onEvent: (event: SSEEvent) => void,
  onError?: (error: Error) => void
): (reader: ReadableStreamDefaultReader<Uint8Array>) => Promise<void> {
  return (reader: ReadableStreamDefaultReader<Uint8Array>) => {
    const options: SSEParseOptions = {
      onEvent,
      onError: onError ?? (() => {})
    }
    return parseSSEStream(reader, options)
  }
}