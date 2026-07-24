/**
 * Zod Schema - Opportunity Types
 *
 * @description 商机类型 Schema，映射后端 schemas/opportunity.py
 */

import { z } from 'zod'
import { UserInfoSchema, PaginatedResponseSchema } from './common'

const NullableStringSchema = z.string().nullable()
const OptionalNullableStringSchema = z.string().nullable().optional()

export const OpportunityStatusSchema = z.number().int().min(0).max(2)
export const OpportunityApprovalPhaseSchema = z.enum(['draft', 'pending_review', 'approved', 'rejected'])
export const OpportunityPurchaseTypeSchema = z.enum(['NEW', 'RENEWAL', 'EXPANSION'])
export const OpportunityLicenseTypeSchema = z.enum(['SUBSCRIPTION', 'PERPETUAL'])

export const OpportunityOwnerInfoSchema = z.object({
  id: z.string(),
  name: z.string(),
  avatar_url: OptionalNullableStringSchema
}).passthrough()

export const OpportunityStageTemplateSchema = z.object({
  id: z.number().int(),
  stage_code: z.string(),
  stage_name: z.string(),
  win_probability: z.number(),
  sort_order: z.number(),
  is_default_start: z.boolean().optional(),
  can_skip: z.boolean().optional()
}).passthrough()

export const OpportunityProcurementMethodInfoSchema = z.object({
  id: z.number().int(),
  code: z.string().optional(),
  name: z.string(),
  description: OptionalNullableStringSchema,
  is_active: z.number().int().optional(),
  stages: z.array(OpportunityStageTemplateSchema).optional()
}).passthrough()

export const OpportunityCurrentStageSnapshotSchema = z.object({
  id: z.number().int(),
  stage_name: z.string(),
  win_probability: z.number(),
  template_sort_order: z.number(),
  template_code: z.string().nullable().optional(),
  entered_at: z.string(),
  exited_at: NullableStringSchema,
  procurement_method: z.object({
    id: z.number().int(),
    code: z.string(),
    name: z.string()
  }).passthrough().nullable().optional()
}).passthrough()

export const OpportunityApiResponseSchema = z.object({
  id: z.number().int(),
  opportunity_name: z.string(),
  customer_id: z.number().int(),
  customer_name: z.string().optional(),
  procurement_method_id: z.number().int().nullable(),
  procurement_method_info: OpportunityProcurementMethodInfoSchema.nullable().optional(),
  total_amount: z.number(),
  user_count: z.number().int(),
  unit_price: z.number(),
  license_type: OpportunityLicenseTypeSchema,
  subscription_years: z.number().nullable(),
  purchase_type: OpportunityPurchaseTypeSchema,
  decision_maker_count: z.number().int().nullable(),
  expected_closing_date: z.string(),
  procurement_stage_id: z.number().int().nullable(),
  stage_name: z.string().optional(),
  win_probability: z.number(),
  current_stage_snapshot: OpportunityCurrentStageSnapshotSchema.nullable().optional(),
  owner_id: z.string(),
  owner_info: OpportunityOwnerInfoSchema.optional(),
  creator_id: z.string(),
  creator_info: OpportunityOwnerInfoSchema.optional(),
  status: OpportunityStatusSchema,
  approval_phase: OpportunityApprovalPhaseSchema,
  actual_amount: z.number().nullable().optional(),
  actual_closing_date: z.string().nullable().optional(),
  loss_reason: z.string().nullable().optional(),
  created_time: z.string(),
  updated_time: z.string(),
  version: z.number().int(),
  customer_info: z.object({
    id: z.number().int(),
    account_name: z.string()
  }).passthrough().optional()
}).passthrough()

export const OpportunityListItemApiSchema = z.object({
  id: z.number().int(),
  opportunity_name: z.string(),
  customer_id: z.number().int(),
  procurement_method_id: z.number().int().nullable(),
  procurement_method_info: OpportunityProcurementMethodInfoSchema.nullable(),
  total_amount: z.number(),
  user_count: z.number().int(),
  unit_price: z.number(),
  license_type: z.string(),
  subscription_years: z.number().nullable(),
  purchase_type: z.string(),
  decision_maker_count: z.number().int().nullable(),
  expected_closing_date: z.string(),
  stage_id: z.number().int().nullable(),
  stage_name: z.string().optional(),
  win_probability: z.number(),
  owner_id: z.string(),
  creator_id: z.string(),
  current_stage_snapshot: OpportunityCurrentStageSnapshotSchema.nullable().optional(),
  stage: z.object({
    id: z.number().int(),
    stage_code: z.string(),
    stage_name: z.string(),
    win_probability: z.number(),
    sort_order: z.number(),
    description: NullableStringSchema,
    is_active: z.number().int(),
    created_time: z.string(),
    last_modified_time: z.string()
  }).passthrough().nullable(),
  stage_info: z.object({
    id: z.number().int(),
    stage_name: z.string(),
    win_probability: z.number(),
    is_default: z.number().int()
  }).passthrough().nullable(),
  status: OpportunityStatusSchema,
  approval_phase: OpportunityApprovalPhaseSchema,
  created_time: z.string(),
  last_modified_time: z.string(),
  customer_name: z.string().optional(),
  owner_info: OpportunityOwnerInfoSchema.optional()
}).passthrough()

export const OpportunityPaginatedListApiSchema = z.object({
  items: z.array(OpportunityListItemApiSchema),
  total: z.number().int().nonnegative(),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total_pages: z.number().int().nonnegative()
}).passthrough()

export const OpportunityListApiResponseSchema = z.union([
  z.array(OpportunityListItemApiSchema),
  OpportunityPaginatedListApiSchema
])

export const SalesFunnelDataSchema = z.object({
  stage_id: z.number().int(),
  stage_name: z.string(),
  opportunity_count: z.number().int(),
  total_amount: z.number(),
  average_amount: z.number(),
  win_probability: z.number()
}).passthrough()

export const StageDurationDataSchema = z.object({
  stage_id: z.number().int(),
  stage_name: z.string(),
  avg_duration_days: z.number(),
  min_duration_days: z.number(),
  max_duration_days: z.number(),
  opportunity_count: z.number().int()
}).passthrough()

export const OpportunityOwnerFilterOptionsResponseSchema = z.object({
  data: z.array(z.object({
    id: z.string(),
    name: z.string(),
    is_me: z.boolean()
  }).passthrough())
}).passthrough()

// ===== 商机阶段枚举 =====
export const OpportunityStageSchema = z.enum([
  'INITIAL_CONTACT',    // 初步接洽
  'NEED_CONFIRMATION',  // 需求确认
  'SOLUTION_PROPOSAL',  // 方案报价
  'NEGOTIATION',        // 商务谈判
  'CONTRACT_SIGNING',   // 签约阶段
  'WON',                // 赢单
  'LOST'                // 输单
])

export const OpportunityStageMap: Record<string, string> = {
  'INITIAL_CONTACT': '初步接洽',
  'NEED_CONFIRMATION': '需求确认',
  'SOLUTION_PROPOSAL': '方案报价',
  'NEGOTIATION': '商务谈判',
  'CONTRACT_SIGNING': '签约阶段',
  'WON': '赢单',
  'LOST': '输单'
}

// ===== 商机基础类型 =====
export const OpportunityResponseSchema = z.object({
  id: z.number().int().positive(),
  opportunity_name: z.string().min(1).max(255),
  customer_id: z.number().int().positive(),
  expected_amount: z.number().positive().nullable(),
  expected_close_date: z.string().datetime().nullable(),
  stage: OpportunityStageSchema,
  probability: z.number().min(0).max(100).nullable(),
  owner_id: z.string().nullable(),
  source_lead_id: z.number().int().nullable(),
  lost_reason: z.string().nullable(),
  creator_id: z.string(),
  created_time: z.string().datetime(),
  last_modified_time: z.string().datetime(),
  version: z.number().int().nonnegative()
})

export type OpportunityResponse = z.infer<typeof OpportunityResponseSchema>

// ===== 商机列表响应 =====
export const OpportunityListResponseSchema = PaginatedResponseSchema(
  OpportunityResponseSchema.extend({
    owner_info: UserInfoSchema.nullable(),
    customer_name: z.string()
  })
)

export type OpportunityListResponse = z.infer<typeof OpportunityListResponseSchema>

// ===== 商机创建请求 =====
export const OpportunityCreateSchema = z.object({
  opportunity_name: z.string().min(1).max(255).optional(),
  customer_id: z.number().int().positive(),
  expected_amount: z.number().positive().optional(),
  expected_close_date: z.string().datetime().optional(),
  stage: OpportunityStageSchema.optional().default('INITIAL_CONTACT'),
  probability: z.number().min(0).max(100).optional(),
  source_lead_id: z.number().int().optional()
})

export type OpportunityCreate = z.infer<typeof OpportunityCreateSchema>

// ===== 商机更新请求 =====
export const OpportunityUpdateSchema = z.object({
  opportunity_name: z.string().min(1).max(255).optional(),
  expected_amount: z.number().positive().optional(),
  expected_close_date: z.string().datetime().optional(),
  stage: OpportunityStageSchema.optional(),
  probability: z.number().min(0).max(100).optional(),
  lost_reason: z.string().optional()
})

export type OpportunityUpdate = z.infer<typeof OpportunityUpdateSchema>
