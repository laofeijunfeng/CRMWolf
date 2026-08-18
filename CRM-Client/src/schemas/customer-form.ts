import { z } from 'zod'

// Company scale options
export const companyScaleOptions = [
  { value: '1-50人', label: '1-50人' },
  { value: '51-200人', label: '51-200人' },
  { value: '201-500人', label: '201-500人' },
  { value: '501-1000人', label: '501-1000人' },
  { value: '1000人以上', label: '1000人以上' }
] as const

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
  ], {
    required_error: '请选择公司规模',
    invalid_type_error: '请选择公司规模'
  }),

  source_public_id: z.string().min(1, '请选择获客来源'),

  default_procurement_method_id: z.number({
    required_error: '请选择采购方式',
    invalid_type_error: '请选择采购方式'
  }).int().positive('请选择采购方式'),
})

export type CustomerForm = z.infer<typeof customerFormSchema>

// Create form schema (only basic fields, no profile)
export const customerCreateSchema = customerFormSchema.pick({
  account_name: true,
  city: true,
  address: true,
  company_scale: true,
  source_public_id: true,
  default_procurement_method_id: true
}).extend({
  contact_name: z.string()
    .min(1, '请输入联系人姓名')
    .max(50, '联系人姓名不能超过50字'),
  contact_mobile: z.string()
    .min(1, '请输入联系电话')
    .regex(/^1[3-9]\d{9}$/, '请输入正确的手机号'),
  contact_position: z.string()
    .min(1, '请输入职位')
    .max(50, '职位不能超过50字'),
  contact_gender: z.enum(['男', '女'], {
    required_error: '请选择性别',
    invalid_type_error: '请选择性别'
  })
})

export type CustomerCreateForm = z.infer<typeof customerCreateSchema>
