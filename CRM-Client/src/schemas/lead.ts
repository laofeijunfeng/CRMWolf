/**
 * Zod Schema - Lead Types
 *
 * @description 线索类型 Schema，映射后端 schemas/lead.py
 */

import { z } from 'zod'
import {
  BusinessDateTimeStringSchema,
  UserInfoSchema,
  LeadStatusSchema,
  LeadSourceSchema,
  CompanyScaleSchema,
  PaginatedResponseSchema
} from './common'
import { AcquisitionSourceInfoSchema } from './acquisition-source'

// ===== 线索基础类型 =====
export const LeadResponseSchema = z.object({
  id: z.string().min(1),
  public_id: z.string().min(1),
  lead_name: z.string().min(1).max(255),
  source: LeadSourceSchema,
  source_info: AcquisitionSourceInfoSchema.nullable().optional(),
  city: z.string().min(1).max(100),
  contact_name: z.string().min(1).max(100),
  contact_phone: z.string().min(1).max(20),
  company_scale: CompanyScaleSchema.nullable(),
  owner_id: z.string().nullable(),
  status: LeadStatusSchema,
  pool_id: z.number().int().nullable(),
  creator_id: z.string(),
  created_time: BusinessDateTimeStringSchema,
  last_modified_time: BusinessDateTimeStringSchema,
  version: z.number().int().nonnegative()
})

export type LeadResponse = z.infer<typeof LeadResponseSchema>

// ===== 线索列表响应 =====
export const LeadListResponseSchema = PaginatedResponseSchema(
  LeadResponseSchema.extend({
    owner_info: UserInfoSchema.nullable()
  })
)

export type LeadListResponse = z.infer<typeof LeadListResponseSchema>

// ===== 线索跟进记录 =====
export const LeadFollowUpResponseSchema = z.object({
  id: z.number().int().positive(),
  lead_id: z.string().min(1),
  content: z.string().min(1),
  method: z.enum(['PHONE', 'EMAIL', 'MEETING', 'WECHAT', 'OTHER']),
  next_follow_time: BusinessDateTimeStringSchema.nullable(),
  creator_id: z.string(),
  created_time: BusinessDateTimeStringSchema,
  creator_info: UserInfoSchema.nullable()
})

export type LeadFollowUpResponse = z.infer<typeof LeadFollowUpResponseSchema>

// ===== 线索详情响应 =====
export const LeadDetailResponseSchema = LeadResponseSchema.extend({
  owner_info: UserInfoSchema.nullable(),
  creator_info: UserInfoSchema.nullable(),
  follow_ups: z.array(LeadFollowUpResponseSchema)
})

export type LeadDetailResponse = z.infer<typeof LeadDetailResponseSchema>

// ===== 线索创建请求 =====
export const LeadCreateSchema = z.object({
  lead_name: z.string().min(1).max(255),
  source_public_id: z.string().min(1),
  city: z.string().min(1).max(100),
  contact_name: z.string().min(1).max(100),
  contact_phone: z.string().min(1).max(20),
  company_scale: CompanyScaleSchema.optional()
})

export type LeadCreate = z.infer<typeof LeadCreateSchema>

// ===== 线索更新请求 =====
export const LeadUpdateSchema = LeadCreateSchema.partial().extend({
  status: LeadStatusSchema.optional()
})

export type LeadUpdate = z.infer<typeof LeadUpdateSchema>

// ===== 线索转化请求 =====
export const LeadConvertRequestSchema = z.object({
  customer_name: z.string().min(1).max(255),
  customer_contact_name: z.string().min(1).max(100),
  customer_contact_phone: z.string().min(1).max(20),
  customer_address: z.string().max(500).optional(),
  customer_industry: z.string().max(100).optional()
})

export type LeadConvertRequest = z.infer<typeof LeadConvertRequestSchema>
