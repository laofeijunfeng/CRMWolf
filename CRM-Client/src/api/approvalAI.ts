// CRM-Client/src/api/approvalAI.ts

/**
 * AI 审批流程解析 API
 */
import request from '@/utils/request'

/**
 * 预定义审批角色（匹配后端 constants/approval_roles.py）
 */
export const ALLOWED_APPROVAL_ROLES = [
  'TEAM_ADMIN',       // 团队所有者
  'SALES_DIRECTOR',   // 销售总监
  'FINANCE',          // 财务人员
  'SALES_MEMBER'      // 销售成员
] as const

export const ROLE_DISPLAY_NAMES: Record<string, string> = {
  TEAM_ADMIN: '团队所有者',
  SALES_DIRECTOR: '销售总监',
  FINANCE: '财务人员',
  SALES_MEMBER: '销售成员'
}

/**
 * AI 解析的审批节点（匹配 ApprovalAIParsedNode）
 */
export interface ApprovalAIParsedNode {
  node_name: string
  node_code: string
  node_order: number  // >= 1
  approve_role: string  // 预定义角色编码
  description?: string
  is_required: number  // 0 或 1，默认 1
}

/**
 * AI 解析的审批流程（匹配 ApprovalAIParsedFlow）
 */
export interface ApprovalAIParsedFlow {
  flow_name: string
  flow_code: string
  description?: string
  min_amount?: number  // Decimal → number
  max_amount?: number
  license_type?: string
  nodes: ApprovalAIParsedNode[]  // min_length=1
}

/**
 * 错误恢复动作（error 事件可附带的可操作按钮）
 */
export interface ErrorAction {
  type: 'retry' | 'simplify' | 'help'
  label: string
  suggestion?: string  // retry/simplify 时提供示例输入
  url?: string         // help 时提供跳转链接
}

/**
 * SSE 事件类型
 */
export interface ApprovalAIParseSSEEvent {
  event: 'status' | 'content' | 'parsed' | 'error' | 'done' | 'progress'
  message?: string
  content?: string
  flow?: ApprovalAIParsedFlow
  thinking_process?: string
  success?: boolean          // done 事件使用
  percentage?: number        // progress 事件使用
  stage?: 'analyzing' | 'generating' | 'validating'  // progress 阶段
  recovery?: string          // error 事件恢复提示
  actions?: ErrorAction[]    // error 事件可操作按钮
  estimated_seconds?: number // status 事件预估时间
  can_cancel?: boolean       // status 事件是否可取消
}

/**
 * 创建请求（使用 ApprovalNodeCreate 结构）
 */
export interface ApprovalAICreateRequest {
  flow_name: string
  flow_code: string
  description?: string
  min_amount?: number
  max_amount?: number
  license_type?: string
  nodes: ApprovalAIParsedNode[]  // 与 ApprovalNodeCreate 字段一致
}

/**
 * 创建响应
 */
export interface ApprovalAICreateResult {
  success: boolean
  message: string
  data: {
    flow: {
      id: number
      flow_name: string
      flow_code: string
      description?: string
      min_amount?: number
      max_amount?: number
      license_type?: string
    }
    nodes: {
      id: number
      node_name: string
      node_code: string
      node_order: number
      approve_role: string
    }[]
  }
}

export const approvalAiApi = {
  /**
   * AI 解析审批流程配置（SSE 流式响应）
   * @param data 解析请求数据
   * @param onEvent SSE 事件回调
   * @param token JWT token
   */
  parseSSE: async (
    data: { content: string },
    onEvent: (event: ApprovalAIParseSSEEvent) => void,
    token: string
  ): Promise<void> => {
    const url = '/api/v1/approval-ai/parse'

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
      const lastLine = lines.pop()
      buffer = lastLine !== undefined ? lastLine : ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const eventData = JSON.parse(line.slice(6)) as ApprovalAIParseSSEEvent
            onEvent(eventData)

            // 收到 parsed / error / done 事件后结束（done 为终端事件，含 success）
            if (eventData.event === 'parsed' || eventData.event === 'error' || eventData.event === 'done') {
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
   * 从 AI 解析结果创建审批流程
   * @param data 创建请求数据
   * @returns 创建结果
   */
  createFromAI: (data: ApprovalAICreateRequest): Promise<ApprovalAICreateResult> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    return request.post<ApprovalAICreateResult>(
      '/v1/approval-ai/create',
      data
    )
  }
}