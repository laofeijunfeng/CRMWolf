/**
 * Zod Schema - Payment Types
 *
 * @description 回款类型 Schema，映射后端 schemas/payment.py
 */

import { z } from 'zod'
import { UserInfoSchema, PaginatedResponseSchema } from './common'

// ===== 回款状态枚举 =====
export const PaymentStatusSchema = z.enum([
  'PENDING',    // 待收款
  'PARTIAL',    // 部分收款
  'COMPLETED',  // 已完成
  'OVERDUE'     // 已逾期
])

export const PaymentStatusMap: Record<string, string> = {
  'PENDING': '待收款',
  'PARTIAL': '部分收款',
  'COMPLETED': '已完成',
  'OVERDUE': '已逾期'
}

// ===== 回款基础类型 =====
export const PaymentResponseSchema = z.object({
  id: z.number().int().positive(),
  contract_id: z.number().int().positive(),
  payment_plan_id: z.number().int().nullable(),
  payment_amount: z.number().positive(),
  payment_date: z.string().datetime(),
  payment_method: z.string().min(1).max(50),
  status: PaymentStatusSchema,
  remark: z.string().nullable(),
  creator_id: z.string(),
  created_time: z.string().datetime(),
  last_modified_time: z.string().datetime(),
  version: z.number().int().nonnegative()
})

export type PaymentResponse = z.infer<typeof PaymentResponseSchema>

// ===== 回款列表响应 =====
export const PaymentListResponseSchema = PaginatedResponseSchema(
  PaymentResponseSchema.extend({
    contract_number: z.string(),
    contract_name: z.string(),
    customer_name: z.string()
  })
)

export type PaymentListResponse = z.infer<typeof PaymentListResponseSchema>

// ===== 回款创建请求 =====
export const PaymentCreateSchema = z.object({
  contract_id: z.number().int().positive(),
  payment_plan_id: z.number().int().optional(),
  payment_amount: z.number().positive(),
  payment_date: z.string().datetime(),
  payment_method: z.string().min(1).max(50),
  remark: z.string().optional()
})

export type PaymentCreate = z.infer<typeof PaymentCreateSchema>

// ===== 回款计划 =====
export const PaymentPlanResponseSchema = z.object({
  id: z.number().int().positive(),
  contract_id: z.number().int().positive(),
  plan_amount: z.number().positive(),
  plan_date: z.string().datetime(),
  status: PaymentStatusSchema,
  remark: z.string().nullable()
})

export type PaymentPlanResponse = z.infer<typeof PaymentPlanResponseSchema>