/**
 * Zod Schema - LicenseApplication Types
 *
 * @description License 申请类型 Schema，映射后端 schemas/license_application.py
 */

import { z } from 'zod'

// ===== License 申请状态枚举 =====
export const LicenseApplicationStatusSchema = z.enum([
  'DRAFT',      // 草稿
  'PENDING',    // 待审批
  'APPROVED',   // 已批准
  'REJECTED',   // 已拒绝
  'ISSUED'      // 已发放
])

export const LicenseApplicationStatusMap: Record<string, string> = {
  'DRAFT': '草稿',
  'PENDING': '待审批',
  'APPROVED': '已批准',
  'REJECTED': '已拒绝',
  'ISSUED': '已发放'
}

// ===== License 类型枚举 =====
export const LicenseTypeSchema = z.enum([
  'TRIAL',      // 试用版
  'OFFICIAL'    // 正式版
])

export const LicenseTypeMap: Record<string, string> = {
  'TRIAL': '试用版',
  'OFFICIAL': '正式版'
}

// ===== License 申请基础类型（含补充字段）=====
export const LicenseApplicationSchema = z.object({
  id: z.number().int().positive(),
  team_id: z.number().int().positive(),
  application_number: z.string().min(1, '申请单号不能为空'),
  customer_id: z.number().int().positive(),
  deployment_info_id: z.number().int().nullable(),
  contract_id: z.number().int().nullable(),
  expiry_date: z.string()
    .refine((val) => {
      const date = new Date(val)
      const today = new Date()
      today.setHours(0, 0, 0, 0)
      return date > today
    }, '到期时间必须晚于今天'),
  license_type: LicenseTypeSchema,
  // 补充需求字段
  enterprise_id: z.string().nullable(),
  supported_modules: z.string().nullable(),
  server_license_code: z.string().nullable(),
  client_license_code: z.string().nullable(),
  remark: z.string().nullable(),
  // 原有字段
  license_code: z.string().nullable(),
  status: LicenseApplicationStatusSchema,
  applicant_id: z.string(),
  approver_id: z.string().nullable(),
  approved_time: z.string().datetime().nullable(),
  created_time: z.string().datetime(),
  last_modified_time: z.string().datetime(),
  // 关联信息（用于前端展示）
  customer_name: z.string().nullable(),
  deployment_name: z.string().nullable(),
  contract_name: z.string().nullable()
})

export type LicenseApplication = z.infer<typeof LicenseApplicationSchema>

// ===== License 申请创建请求（含备注字段）=====
export const LicenseApplicationCreateSchema = LicenseApplicationSchema.omit({
  id: true,
  team_id: true,
  application_number: true,
  enterprise_id: true,
  supported_modules: true,
  server_license_code: true,
  client_license_code: true,
  license_code: true,
  status: true,
  applicant_id: true,
  approver_id: true,
  approved_time: true,
  created_time: true,
  last_modified_time: true,
  customer_name: true,
  deployment_name: true,
  contract_name: true
}).extend({
  // 正式版必须关联合同（通过 refine 验证）
  contract_id: z.number().int().nullable(),
  // 补充需求：备注字段
  remark: z.string().nullable()
}).refine(
  (data) => {
    // 正式版必须关联合同
    if (data.license_type === 'OFFICIAL' && !data.contract_id) {
      return false
    }
    return true
  },
  {
    message: '正式版 License 必须关联合同',
    path: ['contract_id']
  }
)

export type LicenseApplicationCreate = z.infer<typeof LicenseApplicationCreateSchema>

// ===== License 申请更新请求（含备注字段）=====
export const LicenseApplicationUpdateSchema = z.object({
  deployment_info_id: z.number().int().nullable(),
  contract_id: z.number().int().nullable(),
  expiry_date: z.string()
    .refine((val) => {
      if (!val) return true // 可选字段，允许为空
      const date = new Date(val)
      const today = new Date()
      today.setHours(0, 0, 0, 0)
      return date > today
    }, '到期时间必须晚于今天')
    .nullable(),
  remark: z.string().nullable()
})

export type LicenseApplicationUpdate = z.infer<typeof LicenseApplicationUpdateSchema>

// ===== License 申请审批请求（简化版本）=====
export const LicenseApplicationApproveSchema = z.object({
  license_code: z.string().min(1, '授权码不能为空')
})

export type LicenseApplicationApprove = z.infer<typeof LicenseApplicationApproveSchema>

// ===== License 申请审批请求（完整版本）=====
export const LicenseApplicationApproveFullSchema = z.object({
  license_info: z.string().min(1, 'License 信息不能为空'),
  comment: z.string().nullable()
})

export type LicenseApplicationApproveFull = z.infer<typeof LicenseApplicationApproveFullSchema>