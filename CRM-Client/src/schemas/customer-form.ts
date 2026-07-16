import { z } from 'zod'

// Source options for customer
export const customerSourceOptions = [
  { value: '线上注册', label: '线上注册' },
  { value: '市场活动', label: '市场活动' },
  { value: '客户推荐', label: '客户推荐' },
  { value: '电话营销', label: '电话营销' },
  { value: '网站咨询', label: '网站咨询' },
  { value: '展会', label: '展会' },
  { value: '其他', label: '其他' },
  { value: '线索转化', label: '线索转化' }
] as const

// Company scale options
export const companyScaleOptions = [
  { value: '1-50人', label: '1-50人' },
  { value: '51-200人', label: '51-200人' },
  { value: '201-500人', label: '201-500人' },
  { value: '501-1000人', label: '501-1000人' },
  { value: '1000人以上', label: '1000人以上' }
] as const

// Profile status type
export const profileStatusSchema = z.enum(['PENDING', 'GENERATING', 'COMPLETED', 'FAILED']).nullable()

// Customer form schema for create/edit
export const customerFormSchema = z.object({
  // Required fields
  account_name: z.string()
    .min(1, '请输入客户名称')
    .max(255, '客户名称不能超过255个字符'),

  city: z.string()
    .min(1, '请输入所在城市')
    .max(100, '城市名称不能超过100个字符'),

  // Optional fields
  address: z.string()
    .max(500, '地址不能超过500个字符')
    .optional()
    .or(z.literal('')),

  company_scale: z.enum([
    '1-50人', '51-200人', '201-500人',
    '501-1000人', '1000人以上'
  ]).optional().nullable(),

  source: z.enum([
    '线上注册', '市场活动', '客户推荐',
    '电话营销', '网站咨询', '展会',
    '其他', '线索转化'
  ]).optional().nullable(),

  default_procurement_method_id: z.number().int().positive().optional().nullable(),

  // Profile fields (only for edit mode)
  company_background: z.string()
    .max(2000, '企业背景不能超过2000个字符')
    .optional()
    .or(z.literal('')),

  company_website: z.string()
    .url('请输入正确的网址格式')
    .max(255, '网址不能超过255个字符')
    .optional()
    .or(z.literal(''))
    .or(z.literal(null)),

  main_business: z.string()
    .max(2000, '主营业务不能超过2000个字符')
    .optional()
    .or(z.literal('')),

  project_background: z.string()
    .max(2000, '项目需求背景不能超过2000个字符')
    .optional()
    .or(z.literal(''))
})

export type CustomerForm = z.infer<typeof customerFormSchema>

// Create form schema (only basic fields, no profile)
export const customerCreateSchema = customerFormSchema.pick({
  account_name: true,
  city: true,
  address: true,
  company_scale: true,
  source: true,
  default_procurement_method_id: true
})

export type CustomerCreateForm = z.infer<typeof customerCreateSchema>