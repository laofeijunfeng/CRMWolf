/**
 * Zod Schema - 通用审批（Generic Approval）类型
 *
 * @description 映射后端通用审批端点 `app/api/approvals.py` 的
 * `_serialize_generic_approval` 输出与 `app/schemas/approval_generic.py` 的
 * 请求/响应模型。覆盖 CONTRACT / PAYMENT / INVOICE / LICENSE 四类业务单据。
 *
 * 字段命名沿后端 snake_case 约定（与既有 schemas/lead.ts、common.ts 一致）。
 * datetime 字段使用 `z.string().min(1)` 而非 `.datetime()`：后端 SQLAlchemy
 * `DateTime`（无 tzinfo）经 FastAPI 序列化为 `2026-07-01T10:00:00`（无 Z 后缀），
 * `z.string().datetime()` 强制要求 RFC 3339 时区段会拒绝真实响应。
 */

import { z } from 'zod'

// ===== 业务单据类型（A1 BusinessType） =====
export const EntityTypeSchema = z.enum(['CONTRACT', 'PAYMENT', 'INVOICE', 'LICENSE'])
export type EntityType = z.infer<typeof EntityTypeSchema>

// ===== 审批动作枚举（ApprovalActionEnum） =====
export const ApprovalActionSchema = z.enum(['APPROVE', 'REJECT', 'ROLLBACK'])
export type ApprovalAction = z.infer<typeof ApprovalActionSchema>

// ===== 审批状态枚举（ApprovalStatusEnum） =====
export const ApprovalStatusEnum = z.enum(['PENDING', 'APPROVED', 'REJECTED', 'CANCELLED'])
export type ApprovalStatus = z.infer<typeof ApprovalStatusEnum>

export const LicenseApplicationStatusSchema = z.enum(['DRAFT', 'PENDING_REVIEW', 'APPROVED', 'REJECTED', 'ISSUED'])
export type LicenseApplicationStatus = z.infer<typeof LicenseApplicationStatusSchema>

// ===== 审批人状态（UserStatus，可空） =====
export const ApproverStatusSchema = z.enum(['active', 'inactive', 'suspended'])
export type ApproverStatus = z.infer<typeof ApproverStatusSchema>

// ===== 关联客户/公司基础信息 =====
export const ApprovalCustomerInfoSchema = z.object({
  id: z.number().int().positive(),
  account_name: z.string().min(1),
  industry: z.string().nullable().optional(),
  city: z.string().nullable().optional(),
  company_scale: z.string().nullable().optional(),
  source: z.string().nullable().optional(),
  status: z.number().int().nullable().optional(),
  owner_id: z.string().nullable().optional()
})
export type ApprovalCustomerInfo = z.infer<typeof ApprovalCustomerInfoSchema>

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
  submitter_name: z.string().nullable(),  // 允许 null（发票/回款申请人无姓名字段）
  created_time: z.string().min(1),
  updated_time: z.string().min(1),
  flow_is_active: z.boolean().nullable(),
  flow_disabled_warning: z.string().nullable(),
  customer_info: ApprovalCustomerInfoSchema.nullable().optional(),
  records: z.array(ApprovalRecordSchema),
  // Task 6: 发票文件上传字段（仅 INVOICE 类型）
  invoice_file_path: z.string().nullable().optional(),
  invoice_number: z.string().nullable().optional(),
  issued_time: z.string().nullable().optional(),
  // License 发放状态字段（仅 LICENSE 类型）
  license_status: LicenseApplicationStatusSchema.nullable().optional()
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

// ===== FinanceApprovalCenter 列表项（Task C3 / E2 角色过滤） =====
// 后端列表端点按 tab+business_type 严格按角色过滤（E2）：
//   submitted  → submitter_id == current_user AND team_id
//   pending    → current_node.approve_role IN (user_roles) AND status=PENDING AND team_id
//   processed  → records.approver_id == current_user AND team_id
// 单号 / 实体摘要 / 金额由后端按 business_type 分组批量预取后内存 join（E9）。
export const ApprovalTabSchema = z.enum(['pending', 'processed', 'submitted'])
export type ApprovalTab = z.infer<typeof ApprovalTabSchema>

export const ApprovalListItemSchema = z.object({
  id: z.number().int().positive(),
  business_type: EntityTypeSchema,
  business_id: z.number().int().positive(),
  application_number: z.string().min(1),
  entity_name: z.string().nullable(),
  entity_amount: z.number().nullable(),
  actual_payer_name: z.string().nullable().optional(),
  license_status: LicenseApplicationStatusSchema.nullable().optional(),
  customer_info: ApprovalCustomerInfoSchema.nullable().optional(),
  submitter_id: z.string().min(1),
  submitter_name: z.string().nullable(),  // 允许 null（发票/回款申请人无姓名字段）
  status: ApprovalStatusEnum,
  created_time: z.string().min(1),
  updated_time: z.string().min(1),
  overdue_hours: z.number().nullable()
})
export type ApprovalListItem = z.infer<typeof ApprovalListItemSchema>

export const ApprovalListResponseSchema = z.object({
  items: z.array(ApprovalListItemSchema),
  total: z.number().int().nonnegative(),
  pending_count: z.number().int().nonnegative()
})
export type ApprovalListResponse = z.infer<typeof ApprovalListResponseSchema>

export const ApprovalListQuerySchema = z.object({
  tab: ApprovalTabSchema,
  business_type: EntityTypeSchema.optional(),
  page: z.number().int().positive().default(1),
  page_size: z.number().int().positive().default(20)
})
export type ApprovalListQuery = z.infer<typeof ApprovalListQuerySchema>

// ===== 发票文件上传审批响应（Task 5） =====
export const ApproveWithFileResponseSchema = z.object({
  success: z.boolean(),
  message: z.string().min(1),
  file_path: z.string().min(1),
  invoice_number: z.string().nullable(),
  new_status: z.string().min(1)
})
export type ApproveWithFileResponse = z.infer<typeof ApproveWithFileResponseSchema>
