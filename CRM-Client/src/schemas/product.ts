import { z } from 'zod'

export const BooleanFlagSchema = z.preprocess((value: unknown): unknown => {
  if (typeof value === 'boolean') return value
  if (value === 1 || value === '1') return true
  if (value === 0 || value === '0') return false
  return value
}, z.boolean())

export const ProductModuleRoleSchema = z.enum(['BASE', 'ADD_ON'])
export type ProductModuleRole = z.infer<typeof ProductModuleRoleSchema>

export const ProductModuleResponseSchema = z.object({
  public_id: z.string().min(1), team_id: z.number().int(), product_id: z.number().int(), code: z.string(), name: z.string(),
  description: z.string().nullable(), module_role: ProductModuleRoleSchema, is_active: BooleanFlagSchema, sort_order: z.number().int(),
  created_by: z.string(), updated_by: z.string().nullable(), created_time: z.string().min(1), updated_time: z.string().min(1),
})
export type ProductModuleResponse = z.infer<typeof ProductModuleResponseSchema>

export const ProductResponseSchema = z.object({
  public_id: z.string().min(1), team_id: z.number().int(), code: z.string(), name: z.string(), description: z.string().nullable(),
  is_active: BooleanFlagSchema, created_by: z.string(), updated_by: z.string().nullable(), created_time: z.string().min(1), updated_time: z.string().min(1),
  modules: z.array(ProductModuleResponseSchema),
})
export type ProductResponse = z.infer<typeof ProductResponseSchema>
export const ProductListResponseSchema = z.array(ProductResponseSchema)

const CodeSchema = z.string().trim().min(1, '请输入编码').max(50, '编码不能超过50个字符')
const NameSchema = z.string().trim().min(1, '请输入名称').max(100, '名称不能超过100个字符')
const DescriptionSchema = z.string().max(2000, '描述不能超过2000个字符').nullable().optional()

export const ProductCreateSchema = z.object({ code: CodeSchema, name: NameSchema, description: DescriptionSchema })
export type ProductCreate = z.infer<typeof ProductCreateSchema>
export const ProductUpdateSchema = z.object({ name: NameSchema.optional(), description: DescriptionSchema, is_active: z.boolean().optional() })
export type ProductUpdate = z.infer<typeof ProductUpdateSchema>

export const ProductModuleCreateSchema = z.object({ code: CodeSchema, name: NameSchema, description: DescriptionSchema, module_role: z.literal('ADD_ON').default('ADD_ON'), is_active: z.boolean().default(true), sort_order: z.number().int().min(0).default(0) })
export type ProductModuleCreate = z.infer<typeof ProductModuleCreateSchema>
export const ProductModuleUpdateSchema = z.object({ name: NameSchema.optional(), description: DescriptionSchema, is_active: z.boolean().optional(), sort_order: z.number().int().min(0).optional() })
export type ProductModuleUpdate = z.infer<typeof ProductModuleUpdateSchema>
