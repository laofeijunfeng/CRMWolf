/**
 * Zod Schema - Opportunity Types
 *
 * @description 商机类型 Schema，映射后端 schemas/opportunity.py
 */

import { z } from 'zod'
import { UserInfoSchema, PaginatedResponseSchema } from './common'

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
  opportunity_name: z.string().min(1).max(255),
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