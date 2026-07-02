/**
 * Zod Schema - 通用审批（Generic Approval）类型
 *
 * @description 映射后端通用审批端点 `app/api/approvals.py` 的
 * `_serialize_generic_approval` 输出与 `app/schemas/approval_generic.py` 的
 * 请求/响应模型。覆盖 CONTRACT / PAYMENT / INVOICE 三类业务单据。
 *
 * 字段命名沿后端 snake_case 约定（与既有 schemas/lead.ts、common.ts 一致）。
 * datetime 字段使用 `z.string().min(1)` 而非 `.datetime()`：后端 SQLAlchemy
 * `DateTime`（无 tzinfo）经 FastAPI 序列化为 `2026-07-01T10:00:00`（无 Z 后缀），
 * `z.string().datetime()` 强制要求 RFC 3339 时区段会拒绝真实响应。
 */

import { z } from 'zod'

// ===== 业务单据类型（A1 BusinessType） =====
export const EntityTypeSchema = z.enum(['CONTRACT', 'PAYMENT', 'INVOICE'])
export type EntityType = z.infer<typeof EntityTypeSchema>

// ===== 审批动作枚举（ApprovalActionEnum） =====
export const ApprovalActionSchema = z.enum(['APPROVE', 'REJECT', 'ROLLBACK'])
export type ApprovalAction = z.infer<typeof ApprovalActionSchema>

// ===== 审批状态枚举（ApprovalStatusEnum） =====
export const ApprovalStatusEnum = z.enum(['PENDING', 'APPROVED', 'REJECTED', 'CANCELLED'])
export type ApprovalStatus = z.infer<typeof ApprovalStatusEnum>

// ===== 审批人状态（UserStatus，可空） =====
export const ApproverStatusSchema = z.enum(['active', 'inactive', 'suspended'])
export type ApproverStatus = z.infer<typeof ApproverStatusSchema>

// ===== 审批记录（timeline 节点） =====
export const ApprovalRecordSchema = z.object({
  id: z.number().int().positive(),
  approval_id: z.number().int().positive(),
  node_id: z.number().int().nullable(),
  node_name: z.string().nullable(),
  approver_id: z.string().nullable(),
  approver_name: z.string().nullable(),
  approver_status: ApproverStatusSchema.nullable(),
  approver_status_display: z.string().nullable(),
  action: z.enum(['SUBMIT', 'APPROVE', 'REJECT', 'ROLLBACK']).nullable(),
  comment: z.string().nullable(),
  created_time: z.string().min(1)
})

export type ApprovalRecord = z.infer<typeof ApprovalRecordSchema>

// ===== 审批详情响应 =====
export const ApprovalDetailSchema = z.object({
  id: z.number().int().positive(),
  business_type: EntityTypeSchema,
  business_id: z.number().int().positive(),
  contract_id: z.number().int().nullable(),
  flow_id: z.number().int(),
  flow_name: z.string().nullable(),
  current_node_id: z.number().int().nullable(),
  current_node_name: z.string().nullable(),
  status: ApprovalStatusEnum,
  submitter_id: z.string().min(1),
  submitter_name: z.string().min(1),
  created_time: z.string().min(1),
  updated_time: z.string().min(1),
  flow_is_active: z.boolean().nullable(),
  flow_disabled_warning: z.string().nullable(),
  records: z.array(ApprovalRecordSchema)
})

export type ApprovalDetail = z.infer<typeof ApprovalDetailSchema>

// ===== 通用提交响应（GenericApprovalSubmitResponse） =====
export const ApprovalSubmitResponseSchema = z.object({
  approval_id: z.number().int().nonnegative(),
  status: ApprovalStatusEnum
})

export type ApprovalSubmitResponse = z.infer<typeof ApprovalSubmitResponseSchema>

// ===== 撤回响应（MessageResponse） =====
export const MessageResponseSchema = z.object({
  message: z.string().min(1)
})

export type MessageResponse = z.infer<typeof MessageResponseSchema>

// ===== 批量审批失败条目（BulkApproveFailedItem） =====
export const BulkApproveFailedItemSchema = z.object({
  id: z.number().int(),
  reason: z.string().min(1)
})

export type BulkApproveFailedItem = z.infer<typeof BulkApproveFailedItemSchema>

// ===== 批量审批汇总响应（BulkApproveResponse） =====
export const BulkApproveResponseSchema = z.object({
  success_count: z.number().int().nonnegative(),
  failed: z.array(BulkApproveFailedItemSchema)
})

export type BulkApproveResponse = z.infer<typeof BulkApproveResponseSchema>