/**
 * Zod Schema - Invoice Types
 *
 * @description 发票类型 Schema，映射后端 schemas/invoice.py
 */

import { z } from 'zod'
import { UserInfoSchema, PaginatedResponseSchema } from './common'

// ===== 发票状态枚举 =====
export const InvoiceStatusSchema = z.enum([
  'DRAFT',           // 草稿
  'PENDING_APPROVAL', // 待审批
  'APPROVED',        // 已审批
  'REJECTED',        // 已拒绝
  'ISSUED',          // 已开票
  'CANCELLED'        // 已作废
])

export const InvoiceStatusMap: Record<string, string> = {
  'DRAFT': '草稿',
  'PENDING_APPROVAL': '待审批',
  'APPROVED': '已审批',
  'REJECTED': '已拒绝',
  'ISSUED': '已开票',
  'CANCELLED': '已作废'
}

// ===== 发票类型枚举 =====
export const InvoiceTypeSchema = z.enum([
  'ORDINARY',    // 普票
  'SPECIAL'      // 专票
])

// ===== 发票基础类型 =====
export const InvoiceResponseSchema = z.object({
  id: z.number().int().positive(),
  invoice_number: z.string().min(1).max(100).nullable(),
  contract_id: z.number().int().positive(),
  payment_id: z.number().int().nullable(),
  invoice_type: InvoiceTypeSchema,
  invoice_amount: z.number().positive(),
  invoice_title: z.string().min(1).max(255),
  tax_number: z.string().min(1).max(50),
  address: z.string().max(500).nullable(),
  phone: z.string().max(50).nullable(),
  bank_name: z.string().max(100).nullable(),
  bank_account: z.string().max(50).nullable(),
  status: InvoiceStatusSchema,
  issued_date: z.string().datetime().nullable(),
  remark: z.string().nullable(),
  creator_id: z.string(),
  created_time: z.string().datetime(),
  last_modified_time: z.string().datetime(),
  version: z.number().int().nonnegative()
})

export type InvoiceResponse = z.infer<typeof InvoiceResponseSchema>

// ===== 发票列表响应 =====
export const InvoiceListResponseSchema = PaginatedResponseSchema(
  InvoiceResponseSchema.extend({
    contract_number: z.string(),
    contract_name: z.string(),
    customer_name: z.string(),
    approver_info: UserInfoSchema.nullable()
  })
)

export type InvoiceListResponse = z.infer<typeof InvoiceListResponseSchema>

// ===== 发票创建请求 =====
export const InvoiceCreateSchema = z.object({
  contract_id: z.number().int().positive(),
  payment_id: z.number().int().optional(),
  invoice_type: InvoiceTypeSchema,
  invoice_amount: z.number().positive(),
  invoice_title: z.string().min(1).max(255),
  tax_number: z.string().min(1).max(50),
  address: z.string().max(500).optional(),
  phone: z.string().max(50).optional(),
  bank_name: z.string().max(100).optional(),
  bank_account: z.string().max(50).optional(),
  remark: z.string().optional()
})

export type InvoiceCreate = z.infer<typeof InvoiceCreateSchema>

// ===== 发票更新请求 =====
export const InvoiceUpdateSchema = InvoiceCreateSchema.partial()

export type InvoiceUpdate = z.infer<typeof InvoiceUpdateSchema>

// ===== 发票审批请求 =====
export const InvoiceApprovalRequestSchema = z.object({
  action: z.enum(['approve', 'reject']),
  comment: z.string().optional()
})

export type InvoiceApprovalRequest = z.infer<typeof InvoiceApprovalRequestSchema>