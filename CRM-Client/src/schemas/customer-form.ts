import { z } from 'zod'

// Company scale options
export const companyScaleOptions = [
  { value: '1-50人', label: '1-50人' },
  { value: '51-200人', label: '51-200人' },
  { value: '201-500人', label: '201-500人' },
  { value: '501-1000人', label: '501-1000人' },
  { value: '1000人以上', label: '1000人以上' }
] as const

const customerLicenseTypeSchema = z.enum(['TRIAL', 'OFFICIAL']).optional().or(z.literal(''))
const customerLifecycleStatusSchema = z.union([z.literal(0), z.literal(1)]).optional()
const customerLicenseExpirySchema = z.string().optional().or(z.literal(''))

const rejectExpiryWithoutLicenseType = (values: Record<string, unknown>): boolean => {
  const expiry = values['license_expiry_date']
  const hasExpiry = typeof expiry === 'string' && expiry.trim() !== ''
  if (!hasExpiry) {
    return true
  }
  const licenseType = values['license_type']
  return typeof licenseType === 'string' && licenseType.trim() !== ''
}

const licensePairIssue = {
  message: '授权到期日期不为空时必须选择授权类型',
  path: ['license_expiry_date'] as (string | number)[],
}

// Customer form schema for create/edit. Existing callers retain strict profile validation.
const customerFormObjectSchema = z.object({
  account_name: z.string()
    .min(1, '请输入客户名称')
    .max(255, '客户名称不能超过255个字符'),
  city: z.string()
    .min(1, '请输入所在城市')
    .max(100, '城市名称不能超过100个字符'),
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
  product_public_id: z.string({ required_error: '请选择产品' }).min(1, '请选择产品'),
  default_procurement_method_id: z.number({
    required_error: '请选择采购方式',
    invalid_type_error: '请选择采购方式'
  }).int().positive('请选择采购方式'),
  industry: z.string().max(100).optional().or(z.literal('')),
  status: customerLifecycleStatusSchema,
  license_type: customerLicenseTypeSchema,
  license_expiry_date: customerLicenseExpirySchema,
})

export const customerFormSchema = customerFormObjectSchema.refine(
  rejectExpiryWithoutLicenseType,
  licensePairIssue,
)

// Edit schema accepts unset profile fields and preserves non-empty legacy values.
export const customerEditSchema = customerFormObjectSchema.extend({
  company_scale: z.string().max(50, '公司规模不能超过50个字符').optional().or(z.literal('')),
  source_public_id: z.string().optional().or(z.literal('')),
  default_procurement_method_id: z.number().int().positive('请选择采购方式').optional(),
}).refine(rejectExpiryWithoutLicenseType, licensePairIssue)

export type CustomerForm = z.infer<typeof customerFormSchema>
export type CustomerEditForm = z.infer<typeof customerEditSchema>

// Create form schema (only basic fields, no profile)
export const customerCreateSchema = customerFormObjectSchema.pick({
  account_name: true,
  city: true,
  address: true,
  company_scale: true,
  source_public_id: true,
  product_public_id: true,
  default_procurement_method_id: true,
  industry: true,
  status: true,
  license_type: true,
  license_expiry_date: true,
}).extend({
  company_scale: z.enum([
    '1-50人', '51-200人', '201-500人',
    '501-1000人', '1000人以上'
  ], {
    required_error: '请选择公司规模',
    invalid_type_error: '请选择公司规模'
  }),
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
}).refine(rejectExpiryWithoutLicenseType, licensePairIssue)

export type CustomerCreateForm = z.infer<typeof customerCreateSchema>
