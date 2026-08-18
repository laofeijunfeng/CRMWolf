/**
 * Zod Schema - Acquisition Source
 *
 * @description 获客来源配置与跟读对象，映射后端 schemas/acquisition_source.py
 */

import { z } from 'zod'

const BooleanFlagSchema = z.preprocess((value: unknown): unknown => {
  if (typeof value === 'boolean') return value
  if (value === 1 || value === '1') return true
  if (value === 0 || value === '0') return false
  return value
}, z.boolean())

export const AcquisitionSourceInfoSchema = z.object({
  public_id: z.string().min(1),
  name: z.string().min(1),
  is_active: BooleanFlagSchema,
})

export type AcquisitionSourceInfo = z.infer<typeof AcquisitionSourceInfoSchema>

export const AcquisitionSourceOptionSchema = z.object({
  public_id: z.string().min(1),
  name: z.string().min(1),
  code: z.string().min(1),
  is_system: BooleanFlagSchema,
  is_active: BooleanFlagSchema,
  sort_order: z.number().int(),
})

export type AcquisitionSourceOption = z.infer<typeof AcquisitionSourceOptionSchema>

export const AcquisitionSourceSchema = AcquisitionSourceOptionSchema.extend({
  lead_count: z.number().int().nonnegative(),
  customer_count: z.number().int().nonnegative(),
  created_time: z.string().min(1),
  updated_time: z.string().min(1),
})

export type AcquisitionSource = z.infer<typeof AcquisitionSourceSchema>

export const AcquisitionSourceOptionListSchema = z.array(AcquisitionSourceOptionSchema)
export const AcquisitionSourceListSchema = z.array(AcquisitionSourceSchema)

export const AcquisitionSourceCreateSchema = z.object({
  name: z.string()
    .trim()
    .min(1, '请输入获客来源名称')
    .max(50, '名称不能超过50个字符'),
  sort_order: z.number().int().min(0, '排序序号不能小于0').optional(),
})

export type AcquisitionSourceCreate = z.infer<typeof AcquisitionSourceCreateSchema>

export const AcquisitionSourceUpdateSchema = z.object({
  name: z.string()
    .trim()
    .min(1, '请输入获客来源名称')
    .max(50, '名称不能超过50个字符')
    .optional(),
  is_active: z.union([z.literal(0), z.literal(1)]).optional(),
  sort_order: z.number().int().min(0, '排序序号不能小于0').optional(),
})

export type AcquisitionSourceUpdate = z.infer<typeof AcquisitionSourceUpdateSchema>

export const AcquisitionSourceReorderItemSchema = z.object({
  public_id: z.string().min(1),
  sort_order: z.number().int().min(0),
})

export const AcquisitionSourceReorderRequestSchema = z.object({
  items: z.array(AcquisitionSourceReorderItemSchema),
})

export type AcquisitionSourceReorderRequest = z.infer<typeof AcquisitionSourceReorderRequestSchema>

export interface AcquisitionSourceNamedEntity {
  source?: string | null
  source_info?: Pick<AcquisitionSourceInfo, 'name'> | null
}

export function getAcquisitionSourceDisplayName(
  entity: AcquisitionSourceNamedEntity | null | undefined,
  emptyText = '未设置',
): string {
  const name = entity?.source_info?.name ?? entity?.source
  if (name === undefined || name === null || name.trim() === '') return emptyText
  return name
}

export function toAcquisitionSourceSelectOptions(
  options: readonly Pick<AcquisitionSourceOption, 'public_id' | 'name'>[],
): { value: string; label: string }[] {
  return options.map((option) => ({
    value: option.public_id,
    label: option.name,
  }))
}
