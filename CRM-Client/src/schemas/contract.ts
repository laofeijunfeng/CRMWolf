/**
 * Zod Schema - Contract Types
 *
 * @description 合同类型 Schema，映射后端 schemas/contract.py
 */

import { z } from 'zod'
import { UserInfoSchema, PaginatedResponseSchema } from './common'

// ===== 合同状态枚举 =====
export const ContractStatusSchema = z.enum([
  'DRAFT',          // 草稿
  'PENDING_APPROVAL', // 待审批
  'APPROVED',       // 已审批
  'REJECTED',       // 已拒绝
  'EXECUTING',      // 执行中
  'COMPLETED',      // 已完成
  'TERMINATED'      // 已终止
])

export const ContractStatusMap: Record<string, string> = {
  'DRAFT': '草稿',
  'PENDING_APPROVAL': '待审批',
  'APPROVED': '已审批',
  'REJECTED': '已拒绝',
  'EXECUTING': '执行中',
  'COMPLETED': '已完成',
  'TERMINATED': '已终止'
}

// ===== 合同基础类型 =====
export const ContractResponseSchema = z.object({
  id: z.number().int().positive(),
  contract_number: z.string().min(1).max(100),
  contract_name: z.string().min(1).max(255),
  customer_id: z.number().int().positive(),
  opportunity_id: z.number().int().nullable(),
  contract_amount: z.number().positive(),
  signed_date: z.string().datetime().nullable(),
  start_date: z.string().datetime().nullable(),
  end_date: z.string().datetime().nullable(),
  status: ContractStatusSchema,
  owner_id: z.string().nullable(),
  remark: z.string().nullable(),
  creator_id: z.string(),
  created_time: z.string().datetime(),
  last_modified_time: z.string().datetime(),
  version: z.number().int().nonnegative()
})

export type ContractResponse = z.infer<typeof ContractResponseSchema>

// ===== 合同列表响应 =====
export const ContractListResponseSchema = PaginatedResponseSchema(
  ContractResponseSchema.extend({
    owner_info: UserInfoSchema.nullable(),
    customer_name: z.string(),
    approved_amount: z.number().nullable()
  })
)

export type ContractListResponse = z.infer<typeof ContractListResponseSchema>

// ===== 合同创建请求 =====
export const ContractCreateSchema = z.object({
  contract_name: z.string().min(1).max(255),
  customer_id: z.number().int().positive(),
  opportunity_id: z.number().int().optional(),
  contract_amount: z.number().positive(),
  signed_date: z.string().datetime().optional(),
  start_date: z.string().datetime().optional(),
  end_date: z.string().datetime().optional(),
  remark: z.string().optional()
})

export type ContractCreate = z.infer<typeof ContractCreateSchema>

// ===== 合同更新请求 =====
export const ContractUpdateSchema = ContractCreateSchema.partial()

export type ContractUpdate = z.infer<typeof ContractUpdateSchema>

// ===== 合同审批请求 =====
export const ContractApprovalRequestSchema = z.object({
  action: z.enum(['approve', 'reject']),
  comment: z.string().optional()
})

export type ContractApprovalRequest = z.infer<typeof ContractApprovalRequestSchema>