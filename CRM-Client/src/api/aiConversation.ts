/**
 * AI 对话历史 API
 *
 * 用于获取和管理用户的 AI 对话历史记录
 */

import request from '@/utils/request'

// ========== Types ==========

/** 执行步骤（与 schema ExecutionStep 对齐） */
export interface ExecutionStep {
  id: string
  type: string
  title: string
  description?: string
  timestamp: string
  round?: number
  tool?: string
  params?: Record<string, unknown>
  result?: Record<string, unknown>
  success?: boolean
  error?: string
  businessParams?: string
}

/** 对话历史项 */
export interface ConversationHistory {
  id: number
  title: string
  actionType: string
  entityType: 'customer' | 'opportunity' | 'lead' | 'contract' | null
  entityId: number | null
  createdAt: string
}

/** 对话详情 */
export interface ConversationDetail {
  id: number
  title: string
  summary: string
  actionType: string
  entityType: string | null
  entityId: number | null
  messages: {
    role: 'user' | 'assistant'
    content: string
    timestamp: string
    execution_steps?: ExecutionStep[]
  }[]
  createdAt: string
  updatedAt: string
}

/** 按日期分组的对话列表 */
export interface ConversationGroup {
  today: ConversationHistory[]
  yesterday: ConversationHistory[]
  earlier: ConversationHistory[]
}

/** 历史列表响应 */
export interface HistoryListResponse {
  groups: ConversationGroup
  total: number
}

/** 历史列表请求参数 */
export interface HistoryListParams {
  page?: number
  pageSize?: number
}

/** 创建对话请求参数 */
export interface ConversationCreateParams {
  title: string
  messages: {
    role: 'user' | 'assistant'
    content: string
    timestamp: string
    execution_steps?: ExecutionStep[]
  }[]
  action_type?: string | undefined
  entity_type?: string | undefined
  entity_id?: number | undefined
}

// ========== Helper Functions ==========

/** 将蛇形字段转换为驼峰 */
function toCamelCase<T extends Record<string, unknown>>(obj: T): T {
  const result: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(obj)) {
    const camelKey = key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase())
    result[camelKey] = value
  }
  return result as T
}

// ========== API Functions ==========

/**
 * 创建对话记录
 */
export async function create(params: ConversationCreateParams): Promise<ConversationDetail> {
  const response = await request.post<Record<string, unknown>>(
    '/v1/assistant/conversations',
    params
  )
  return toCamelCase(response) as ConversationDetail
}

/**
 * 更新对话记录（实时保存）
 * ChatGPT 模式：用于实时保存消息
 */
export async function update(id: number, params: ConversationCreateParams): Promise<ConversationDetail> {
  const response = await request.put<Record<string, unknown>>(
    `/v1/assistant/conversations/${id}`,
    params
  )
  return toCamelCase(response) as ConversationDetail
}

/**
 * 获取历史对话列表
 */
export async function getHistory(params: HistoryListParams = {}): Promise<HistoryListResponse> {
  const response = await request.get<{
    groups: {
      today: Record<string, unknown>[]
      yesterday: Record<string, unknown>[]
      earlier: Record<string, unknown>[]
    }
    total: number
  }>(
    '/v1/assistant/conversations',
    { params }
  )

  // 转换字段名：蛇形 → 驼峰
  return {
    groups: {
      today: response.groups.today.map(toCamelCase) as ConversationHistory[],
      yesterday: response.groups.yesterday.map(toCamelCase) as ConversationHistory[],
      earlier: response.groups.earlier.map(toCamelCase) as ConversationHistory[]
    },
    total: response.total
  }
}

/**
 * 获取单个对话详情
 */
export async function getDetail(id: number): Promise<ConversationDetail> {
  const response = await request.get<Record<string, unknown>>(
    `/v1/assistant/conversations/${id}`
  )
  return toCamelCase(response) as ConversationDetail
}

/**
 * 删除对话记录
 */
export async function deleteConversation(id: number): Promise<void> {
  await request.delete(`/v1/assistant/conversations/${id}`)
}

/**
 * 搜索对话
 */
export async function search(keyword: string): Promise<ConversationHistory[]> {
  const response = await request.get<Record<string, unknown>[]>(
    '/v1/assistant/conversations/search',
    { params: { keyword } }
  )
  return response.map(toCamelCase) as ConversationHistory[]
}

// ========== Export ==========

export const aiConversationApi = {
  create,
  update,
  getHistory,
  getDetail,
  delete: deleteConversation,
  search
}