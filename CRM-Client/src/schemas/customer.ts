/**
 * Zod Schema - Customer Types
 *
 * @description 客户类型 Schema，映射后端 schemas/customer.py
 */

import { z } from 'zod'
import { UserInfoSchema, CustomerStatusSchema, PaginationParamsSchema, PaginatedResponseSchema } from './common'

// ===== 客户基础类型 =====
export const CustomerResponseSchema = z.object({
  id: z.number().int().positive(),
  account_name: z.string().min(1).max(255),
  industry: z.string().max(100).nullable(),
  city: z.string().min(1).max(100),
  address: z.string().max(500).nullable(),
  company_scale: z.string().max(50).nullable(),
  source: z.string().max(100).nullable(),
  status: CustomerStatusSchema,
  owner_id: z.string().nullable(),
  source_lead_id: z.number().int().nullable(),
  default_procurement_method_id: z.number().int().nullable(),
  return_reason: z.string().nullable(),
  returned_time: z.string().datetime().nullable(),
  creator_id: z.string(),
  created_time: z.string().datetime(),
  last_modified_time: z.string().datetime(),
  version: z.number().int().nonnegative()
})

export type CustomerResponse = z.infer<typeof CustomerResponseSchema>

// ===== 客户列表响应 =====
export const CustomerListResponseSchema = PaginatedResponseSchema(
  CustomerResponseSchema.extend({
    owner_info: UserInfoSchema.nullable(),
    creator_info: UserInfoSchema.nullable()
  })
)

export type CustomerListResponse = z.infer<typeof CustomerListResponseSchema>

// ===== 客户详情响应 =====
export const CustomerDetailResponseSchema = CustomerResponseSchema.extend({
  owner_info: UserInfoSchema.nullable(),
  creator_info: UserInfoSchema.nullable(),
  contacts: z.array(z.object({
    id: z.number().int(),
    customer_id: z.number().int(),
    name: z.string(),
    position: z.string().nullable(),
    mobile: z.string(),
    email: z.string().nullable(),
    is_primary: z.boolean()
  }))
})

export type CustomerDetailResponse = z.infer<typeof CustomerDetailResponseSchema>

// ===== 客户创建请求 =====
export const CustomerCreateSchema = z.object({
  account_name: z.string().min(1).max(255),
  industry: z.string().max(100).optional(),
  city: z.string().min(1).max(100),
  address: z.string().max(500).optional(),
  company_scale: z.string().max(50).optional(),
  source: z.string().max(100).optional(),
  owner_id: z.string().optional(),
  default_procurement_method_id: z.number().int().optional()
})

export type CustomerCreate = z.infer<typeof CustomerCreateSchema>

// ===== 客户更新请求 =====
export const CustomerUpdateSchema = CustomerCreateSchema.partial()

export type CustomerUpdate = z.infer<typeof CustomerUpdateSchema>