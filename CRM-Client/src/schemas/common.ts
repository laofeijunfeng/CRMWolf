/**
 * Zod Schema - Common Types
 *
 * @description 通用类型 Schema，映射后端 Pydantic schemas
 */

import { z } from 'zod'

export const ApiResponseSchema = <T>(): z.ZodType<T> => z.custom<T>((value) => value !== undefined)
export const BlobPartResponseSchema = z.union([
  z.instanceof(Blob),
  z.instanceof(ArrayBuffer),
  z.string()
])

// ===== API 响应兼容类型 =====
// 后端 Pydantic Optional 字段会序列化为 null；前端展示字段统一在响应边界兼容 null。
export const NullableStringSchema = z.string().nullable()
export const OptionalNullableStringSchema = z.string().nullable().optional()
export const OptionalStringFromNullableSchema = z.preprocess(
  (value: unknown): unknown => value === null ? undefined : value,
  z.string().optional()
)

// 后端业务 DateTime 使用无时区 Asia/Shanghai 本地时间，FastAPI 序列化形如
// `2026-07-01T10:00:00`，不能使用 z.string().datetime() 强制要求 Z/offset。
export const BusinessDateTimeStringSchema = z.string().min(1)
export const BusinessDateStringSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/)

// ===== 分页类型 =====
export const PaginationParamsSchema = z.object({
  page: z.number().int().positive().default(1),
  pageSize: z.number().int().positive().max(100).default(20)
})

export type PaginationParams = z.infer<typeof PaginationParamsSchema>

export const PaginatedResponseSchema = <T extends z.ZodTypeAny>(itemSchema: T): z.ZodObject<{
  data: z.ZodArray<T>
  total: z.ZodNumber
  page: z.ZodNumber
  pageSize: z.ZodNumber
}> =>
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
// 与后端 OwnerInfo 保持一致
export const UserInfoSchema = z.object({
  id: z.string().min(1),        // 系统用户 ID
  name: z.string().min(1),
  avatar_url: z.string().url().nullable().or(z.literal(''))  // 允许 null、有效 URL 或空字符串
})

export type UserInfo = z.infer<typeof UserInfoSchema>

// ===== 状态枚举 =====
// 与后端 status: int 保持一致（数字类型）
export const CustomerStatusSchema = z.number().int().min(0).max(3)

export const CustomerStatusMap: Record<number, string> = {
  0: '跟进中',
  1: '已成交',
  2: '已流失',
  3: '非激活'
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

export const LeadSourceSchema = z.string().min(1)

export const CompanyScaleSchema = z.enum([
  '1-10',
  '11-50',
  '51-200',
  '201-500',
  '500+'
])
