/**
 * Workflow API
 * 用于业务流程编排（硬编码流程，如赢单场景）
 * 支持 SSE 流式响应、暂停-恢复机制
 */

import { parseSSEStream, type SSEEvent } from '@/utils/sseParser'

/**
 * Workflow SSE 事件类型（复用 SSEEvent）
 */
export type WorkflowEvent = SSEEvent

/**
 * Workflow 继续请求
 */
export interface WorkflowContinueRequest {
  session_id: string
  user_response: string
}

/**
 * 启动 Workflow（通过 AI 助手聊天接口）
 *
 * 使用方式：
 * 1. 用户输入触发关键词（如"确认采购"）
 * 2. 后端检测到 Workflow 触发
 * 3. 返回 workflow_start 事件
 * 4. 后续步骤依次执行
 *
 * @param content 用户输入内容
 * @param onEvent SSE 事件回调
 */
export function startWorkflow(
  content: string,
  onEvent: (event: WorkflowEvent) => void,
  onError?: (error: Error) => void
): EventSource {
  const url = `/api/v1/assistant/chat`

  const eventSource = new EventSource(url, {
    // POST 方法需要通过 fetch 发送，这里简化处理
    // 实际项目中需要使用 POST + SSE，可以通过自定义方式实现
  })

  // 由于 EventSource 只支持 GET，这里返回一个模拟的接口
  // 实际实现需要使用 POST + fetch + ReadableStream
  return eventSource
}

/**
 * 继续 Workflow（用户回复后）
 *
 * @param request 继续请求（session_id + user_response）
 * @param onEvent SSE 事件回调
 * @param onError 错误回调
 * @returns Closeable（可关闭的连接）
 */
export function continueWorkflow(
  request: WorkflowContinueRequest,
  onEvent: (event: WorkflowEvent) => void,
  onError?: (error: Error) => void
): { close: () => void } {
  const url = `/api/v1/assistant/workflow/continue`

  // 使用 fetch + ReadableStream 实现 POST + SSE
  fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('No response body')
      }

      // 使用统一 SSE 解析器
      return parseSSEStream(reader, {
        onEvent: (event) => onEvent(event as WorkflowEvent),
        onError: (error) => {
          if (onError) onError(error)
        }
      })
    })
    .catch((error) => {
      if (onError) {
        onError(error)
      }
    })

  // 返回可关闭对象（简化实现）
  return {
    close: () => {
      console.log('Workflow connection closed')
    }
  }
}

/**
 * 继续 Workflow SSE（带 token）
 * 用于 MagicWand 对话框
 */
export function continueWorkflowSSE(
  request: WorkflowContinueRequest,
  onEvent: (event: WorkflowEvent) => void,
  token: string
): Promise<void> {
  const url = `/api/v1/assistant/workflow/continue`

  return fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify(request),
  }).then((response) => {
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('No response body')
    }

    // 使用统一 SSE 解析器
    return parseSSEStream(reader, {
      onEvent: (event) => onEvent(event as WorkflowEvent)
    })
  })
}

/**
 * Workflow 流程定义
 */
export const WORKFLOW_DEFINITIONS = {
  customer_win_flow: {
    name: '客户确认采购（赢单场景）',
    trigger_keywords: ['确认采购', '已签约', '准备签合同', '赢单', '成交', '签合同'],
    steps: [
      { id: 'create_follow_up', description: '创建跟进记录' },
      { id: 'get_entity_context', description: '获取客户商机列表' },
      { id: 'check_opportunity', description: '检查商机数量' },
      { id: 'win_opportunity', description: '标记商机为赢单' },
      { id: 'ask_create_contract', description: '询问是否创建合同' },
      { id: 'create_contract', description: '创建合同草稿' },
    ],
  },
  lead_convert_flow: {
    name: '线索转客户',
    trigger_keywords: ['转客户', '转化', '线索转化'],
    steps: [
      { id: 'create_follow_up', description: '创建跟进记录' },
      { id: 'check_lead_status', description: '检查线索状态' },
      { id: 'convert_lead', description: '转化线索' },
    ],
  },
}

/**
 * 判断是否是 Workflow 事件
 */
export function isWorkflowEvent(event: any): boolean {
  return event?.event?.startsWith('workflow') ||
         event?.event?.startsWith('step') ||
         event?.event?.startsWith('decision') ||
         event?.event === 'waiting_for_user' ||
         event?.event === 'rollback'
}