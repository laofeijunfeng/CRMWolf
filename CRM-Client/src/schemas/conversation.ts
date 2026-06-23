/**
 * Conversation Schema 定义
 *
 * 用于对话历史的 Zod schema 校验和 TypeScript 类型推导
 */
import { z } from 'zod'

/**
 * 执行步骤类型枚举（与 backend ExecutionStepType 对齐）
 */
export const ExecutionStepTypeSchema = z.enum([
  'ROUND_START',
  'TOOL_CALL',
  'TOOL_RESULT',
  'ROUND_COMPLETED',
  'REACT_COMPLETE',
  'ERROR'
])

/**
 * 执行步骤 Schema
 *
 * 定义单个执行步骤的数据结构，用于 Zod 校验
 */
export const ExecutionStepSchema = z.object({
  /** 步骤唯一标识 */
  id: z.string(),

  /** 步骤类型 */
  type: ExecutionStepTypeSchema,

  /** 业务化标题 */
  title: z.string(),

  /** 步骤描述 */
  description: z.string().optional(),

  /** 时间戳 */
  timestamp: z.coerce.date(),

  /** 轮次编号（可选） */
  round: z.number().optional(),

  /** 工具名称（可选） */
  tool: z.string().optional(),

  /** 工具参数（可选） */
  params: z.record(z.any()).optional(),

  /** 执行结果（可选） */
  result: z.record(z.any()).optional(),

  /** 是否成功（可选） */
  success: z.boolean().optional(),

  /** 错误信息（可选） */
  error: z.string().optional(),

  /** 业务化参数描述（可选） */
  businessParams: z.string().optional()
})

/**
 * 消息项 Schema
 *
 * 定义单条消息的数据结构
 */
export const MessageItemSchema = z.object({
  /** 角色：user 或 assistant */
  role: z.enum(['user', 'assistant']),

  /** 消息内容 */
  content: z.string(),

  /** 时间戳 */
  timestamp: z.string(),

  /** 执行步骤列表（可选，仅 assistant 消息） */
  execution_steps: z.array(ExecutionStepSchema).optional()
})

/**
 * 对话历史项 Schema
 *
 * 用于对话列表展示
 */
export const ConversationHistoryItemSchema = z.object({
  /** 对话 ID */
  id: z.number(),

  /** 对话标题 */
  title: z.string(),

  /** 操作类型（可选） */
  action_type: z.string().nullable().optional(),

  /** 实体类型（可选） */
  entity_type: z.string().nullable().optional(),

  /** 实体 ID（可选） */
  entity_id: z.number().nullable().optional(),

  /** 创建时间 */
  created_at: z.string()
})

/**
 * 对话详情 Schema
 *
 * 包含完整的消息列表
 */
export const ConversationDetailSchema = z.object({
  /** 对话 ID */
  id: z.number(),

  /** 对话标题 */
  title: z.string(),

  /** 对话摘要（可选） */
  summary: z.string().nullable().optional(),

  /** 操作类型（可选） */
  action_type: z.string().nullable().optional(),

  /** 实体类型（可选） */
  entity_type: z.string().nullable().optional(),

  /** 实体 ID（可选） */
  entity_id: z.number().nullable().optional(),

  /** 消息列表 */
  messages: z.array(MessageItemSchema),

  /** 创建时间 */
  created_at: z.string(),

  /** 更新时间 */
  updated_at: z.string()
})

/**
 * 对话分组 Schema
 *
 * 按日期分组的对话列表
 */
export const ConversationGroupSchema = z.object({
  /** 今天的对话 */
  today: z.array(ConversationHistoryItemSchema),

  /** 昨天的对话 */
  yesterday: z.array(ConversationHistoryItemSchema),

  /** 更早的对话 */
  earlier: z.array(ConversationHistoryItemSchema)
})

/**
 * 历史列表响应 Schema
 */
export const HistoryListResponseSchema = z.object({
  /** 分组对话列表 */
  groups: ConversationGroupSchema,

  /** 总数 */
  total: z.number()
})

/**
 * 创建对话请求 Schema
 */
export const ConversationCreateParamsSchema = z.object({
  /** 对话标题 */
  title: z.string().max(200),

  /** 消息列表 */
  messages: z.array(MessageItemSchema),

  /** 操作类型（可选） */
  action_type: z.string().optional(),

  /** 实体类型（可选） */
  entity_type: z.string().optional(),

  /** 实体 ID（可选） */
  entity_id: z.number().optional()
})

// ========== TypeScript 类型导出 ==========

/**
 * 执行步骤类型
 */
export type ExecutionStepType = z.infer<typeof ExecutionStepTypeSchema>

/**
 * 执行步骤
 */
export type ExecutionStep = z.infer<typeof ExecutionStepSchema>

/**
 * 消息项
 */
export type MessageItem = z.infer<typeof MessageItemSchema>

/**
 * 对话历史项
 */
export type ConversationHistoryItem = z.infer<typeof ConversationHistoryItemSchema>

/**
 * 对话详情
 */
export type ConversationDetail = z.infer<typeof ConversationDetailSchema>

/**
 * 对话分组
 */
export type ConversationGroup = z.infer<typeof ConversationGroupSchema>

/**
 * 历史列表响应
 */
export type HistoryListResponse = z.infer<typeof HistoryListResponseSchema>

/**
 * 创建对话请求参数
 */
export type ConversationCreateParams = z.infer<typeof ConversationCreateParamsSchema>