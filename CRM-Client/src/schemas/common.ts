/**
 * Zod Schema - Common Types
 *
 * @description 通用类型 Schema，映射后端 Pydantic schemas
 */

import { z } from 'zod'

// ===== 分页类型 =====
export const PaginationParamsSchema = z.object({
  page: z.number().int().positive().default(1),
  pageSize: z.number().int().positive().max(100).default(20)
})

export type PaginationParams = z.infer<typeof PaginationParamsSchema>

export const PaginatedResponseSchema = <T extends z.ZodTypeAny>(itemSchema: T) =>
  z.object({
    data: z.array(itemSchema),
    total: z.number().int().nonnegative(),
    page: z.number().int().positive(),
    pageSize: z.number().int().positive()
  })

export interface PaginatedResponse<T> {
  data: T[]
  total: number
  page: number
  pageSize: number
}

// ===== 用户信息类型 =====
export const UserInfoSchema = z.object({
  id: z.string().min(1),        // 飞书 Open ID
  name: z.string().min(1),
  avatar_url: z.string().url().nullable()
})

export type UserInfo = z.infer<typeof UserInfoSchema>

// ===== 状态枚举 =====
export const CustomerStatusSchema = z.enum(['0', '1', '2', '3'])

export const CustomerStatusMap: Record<string, string> = {
  '0': '跟进中',
  '1': '已成交',
  '2': '已流失',
  '3': '非激活'
}

export const LeadStatusSchema = z.enum([
  'NEW',
  'CONTACTED',
  'QUALIFIED',
  'CONVERTED',
  'INVALID'
])

export const LeadStatusMap: Record<string, string> = {
  'NEW': '新线索',
  'CONTACTED': '已联系',
  'QUALIFIED': '已确认',
  'CONVERTED': '已转化',
  'INVALID': '无效'
}

export const LeadSourceSchema = z.enum([
  'WEBSITE',
  'REFERRAL',
  'EVENT',
  'COLD_CALL',
  'WEBSITE_INQUIRY',
  'EXHIBITION',
  'OTHER'
])

export const CompanyScaleSchema = z.enum([
  '1-10',
  '11-50',
  '51-200',
  '201-500',
  '500+'
])