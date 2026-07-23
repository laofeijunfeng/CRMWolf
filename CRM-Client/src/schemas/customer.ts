/**
 * Zod Schema - Customer Types
 *
 * @description 客户类型 Schema，映射后端 schemas/customer.py
 */

import { z } from 'zod'
import { UserInfoSchema, CustomerStatusSchema, PaginatedResponseSchema } from './common'

// ===== 行业信息 Schema =====
export const CustomerIndustryInfoSchema = z.object({
  code: z.string(),
  name: z.string(),
  primary_code: z.string().nullable().optional(),
  primary_name: z.string().nullable().optional(),
  secondary_name: z.string().nullable().optional()
})

export type CustomerIndustryInfo = z.infer<typeof CustomerIndustryInfoSchema>

// ===== 采购方式信息 Schema =====
export const ProcurementMethodInfoSchema = z.object({
  id: z.number().int(),
  code: z.string(),
  name: z.string(),
  is_active: z.number()
})

export type ProcurementMethodInfo = z.infer<typeof ProcurementMethodInfoSchema>

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
  returned_time: z.string().nullable(), // 放宽日期格式验证
  creator_id: z.string(),
  created_time: z.string(), // 放宽日期格式验证
  last_modified_time: z.string(), // 放宽日期格式验证
  version: z.number().int().nonnegative(),
  license_expiry_date: z.string().nullable().optional(),
  license_type: z.string().nullable().optional()
})

export type CustomerResponse = z.infer<typeof CustomerResponseSchema>

// ===== 客户列表响应 =====
export const CustomerListResponseSchema = PaginatedResponseSchema(
  CustomerResponseSchema.extend({
    industry_info: CustomerIndustryInfoSchema.nullable().optional(),
    owner_info: UserInfoSchema.nullable(),
    collaborator_infos: z.array(UserInfoSchema).default([]),
    creator_info: UserInfoSchema.nullable(),
    default_procurement_method_info: ProcurementMethodInfoSchema.nullable().optional()
  })
)

export type CustomerListResponse = z.infer<typeof CustomerListResponseSchema>

// ===== 客户默认商机信息 =====
export const CustomerDefaultOpportunitySchema = z.object({
  total_amount: z.number().nullable(),
  user_count: z.number().int().nullable(),
  license_type: z.string().nullable(),
  subscription_years: z.number().int().nullable(),
  purchase_type: z.string().nullable(),
  expected_closing_date: z.string().nullable(),
  procurement_method_id: z.number().int().nullable()
})

export type CustomerDefaultOpportunity = z.infer<typeof CustomerDefaultOpportunitySchema>

// ===== 客户详情响应 =====
// 完整映射后端 CustomerDetailResponse (CRM-Server/app/schemas/customer.py:279-316)
export const CustomerDetailResponseSchema = CustomerResponseSchema.extend({
  // 关联信息
  industry_info: CustomerIndustryInfoSchema.nullable().optional(),
  owner_info: UserInfoSchema.nullable(),
  creator_info: UserInfoSchema.nullable(),
  default_procurement_method_info: ProcurementMethodInfoSchema.nullable().optional(),
  default_opportunity: CustomerDefaultOpportunitySchema.nullable().optional(),
  // 联系人列表（完整字段）
  contacts: z.array(z.object({
    id: z.number().int(),
    customer_id: z.number().int(),
    name: z.string(),
    gender: z.number().int().nullable().optional(),
    position: z.string().nullable(),
    is_decision_maker: z.boolean().optional(),
    mobile: z.string(),
    email: z.string().nullable(),
    wechat_id: z.string().nullable().optional(),
    remark: z.string().nullable().optional(),
    reports_to: z.number().int().nullable().optional(),
    is_primary: z.boolean(),
    created_time: z.string()
  })),
  // 档案字段
  company_background: z.string().nullable(),
  company_website: z.string().nullable(),
  main_business: z.string().nullable(),
  similar_customers: z.string().nullable(),
  project_background: z.string().nullable(),
  profile_status: z.string().nullable(),
  profile_generated_time: z.string().nullable(),
  profile_error_message: z.string().nullable(),
  customer_brief_json: z.string().nullable().optional(),
  customer_brief_markdown: z.string().nullable().optional(),
  customer_brief_citations: z.string().nullable().optional(),
  customer_brief_status: z.string().nullable().optional(),
  customer_brief_generated_time: z.string().nullable().optional(),
  customer_brief_error_message: z.string().nullable().optional(),
  // 热力值字段
  score: z.number().int().nullable().optional(),
  score_updated_at: z.string().nullable().optional(),
  // 输单原因
  loss_reason: z.string().nullable()
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

// ===== 线索转换响应 =====
export const ConvertResponseSchema = z.object({
  customer_id: z.number().int().positive(),
  contact_id: z.number().int().positive(),
  message: z.string()
})

export type ConvertResponse = z.infer<typeof ConvertResponseSchema>

// ===== 客户退回响应 =====
export const CustomerReturnResponseSchema = z.object({
  customer_id: z.number().int().positive(),
  previous_owner: z.string(),
  returned_time: z.string(),
  return_reason: z.string(),
  message: z.string()
})

export type CustomerReturnResponse = z.infer<typeof CustomerReturnResponseSchema>

const NullableEmailSchema = z.preprocess(
  (value) => typeof value === 'string' && value.trim() === '' ? null : value,
  z.string().email().nullable()
)

// ===== 联系人响应 =====
export const ContactResponseSchema = z.object({
  id: z.number().int().positive(),
  customer_id: z.number().int().positive(),
  name: z.string().min(1),
  gender: z.number().int().nullable(),
  position: z.string().nullable(),
  is_decision_maker: z.boolean(),
  mobile: z.string().min(1),
  email: NullableEmailSchema,
  wechat_id: z.string().nullable(),
  remark: z.string().nullable(),
  reports_to: z.number().int().nullable(),
  is_primary: z.boolean(),
  created_time: z.string()
})

export type ContactResponse = z.infer<typeof ContactResponseSchema>

// ===== 客户统计 =====
export const CustomerStatisticsSchema = z.object({
  total_customers: z.number().int().nonnegative(),
  by_status: z.array(z.object({
    status: z.number().int(),
    count: z.number().int().nonnegative()
  })),
  by_industry: z.array(z.object({
    industry: z.string().nullable(),
    count: z.number().int().nonnegative()
  })),
  by_city: z.array(z.object({
    city: z.string(),
    count: z.number().int().nonnegative()
  }))
})

export type CustomerStatistics = z.infer<typeof CustomerStatisticsSchema>

// ===== 客户趋势 =====
export const CustomerTrendSchema = z.object({
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  count: z.number().int().nonnegative()
})

export type CustomerTrend = z.infer<typeof CustomerTrendSchema>

// ===== 所有者筛选选项 =====
export const OwnerFilterOptionSchema = z.object({
  owner_id: z.string().min(1),
  owner_name: z.string().min(1),
  is_me: z.boolean()
})

export type OwnerFilterOption = z.infer<typeof OwnerFilterOptionSchema>

// ===== 行业选项 =====
export const CustomerIndustryOptionSchema = z.object({
  value: z.string().min(1),
  label: z.string().min(1)
})

export type CustomerIndustryOption = z.infer<typeof CustomerIndustryOptionSchema>

// ===== 合同列表响应 =====
export const ContractListResponseSchema = z.object({
  id: z.number().int().positive(),
  contract_number: z.string().min(1),
  contract_name: z.string().min(1),
  customer_id: z.number().int().positive(),
  opportunity_id: z.number().int().nullable(),
  signing_contact_id: z.number().int().nullable(),
  user_count: z.number().int().nonnegative(),
  total_amount: z.string(),
  license_type: z.string(),
  license_type_name: z.string().optional(),
  subscription_years: z.number().int().nullable(),
  standard_unit_price: z.string(),
  status: z.string(),
  status_info: z.object({
    name: z.string()
  }).optional(),
  signing_date: z.string().nullable(),
  effective_date: z.string().nullable(),
  expiry_date: z.string().nullable(),
  created_time: z.string(),
  last_modified_time: z.string(),
  customer_name: z.string().optional(),
  opportunity_name: z.string().optional(),
  owner_info: z.object({
    id: z.number().int(),
    name: z.string(),
    feishu_open_id: z.string()
  }).optional()
})

export type ContractListResponse = z.infer<typeof ContractListResponseSchema>

// ===== 付款计划响应 =====
export const PaymentPlanResponseSchema = z.object({
  id: z.number().int().positive(),
  stage_name: z.string().min(1),
  planned_amount: z.number().nonnegative(),
  due_date: z.string(),
  notes: z.string().nullable(),
  contract_id: z.number().int().positive(),
  status: z.string(),
  created_time: z.string(),
  last_modified_time: z.string(),
  paid_amount: z.number().nonnegative().nullable(),
  remaining_amount: z.number().nonnegative().nullable(),
  contract_name: z.string().optional(),
  customer_name: z.string().optional(),
  opportunity_name: z.string().optional()
})

export type PaymentPlanResponse = z.infer<typeof PaymentPlanResponseSchema>

// ===== 发票申请响应 =====
export const InvoiceApplicationResponseSchema = z.object({
  id: z.number().int().positive(),
  application_number: z.string().min(1),
  customer_id: z.number().int().positive(),
  contract_id: z.number().int().positive(),
  opportunity_id: z.number().int().positive(),
  payment_plan_id: z.number().int().positive(),
  invoice_title_id: z.number().int().positive(),
  invoice_amount: z.string(),
  invoice_type: z.string(),
  payment_record_id: z.number().int().nullable(),
  status: z.string(),
  approval_status: z.string(),
  rejection_reason: z.string().nullable(),
  applicant_id: z.string(),
  created_time: z.string(),
  last_modified_time: z.string(),
  contract_name: z.string().optional(),
  contract_number: z.string().optional(),
  stage_name: z.string().optional(),
  planned_amount: z.number().optional(),
  applicant_name: z.string().optional()
})

export type InvoiceApplicationResponse = z.infer<typeof InvoiceApplicationResponseSchema>
