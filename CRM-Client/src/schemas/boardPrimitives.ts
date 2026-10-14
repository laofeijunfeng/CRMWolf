import { z } from 'zod'

export const CountSchema = z.number().int().nonnegative()
export const EntityIdSchema = z.number().int().positive()
export const AmountStringSchema = z.string().regex(/^-?\d+\.\d{2}$/)
export const PercentageSchema = z.number().finite().min(0).max(100)
export const DateStringSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/)
export const MonthStringSchema = z.string().regex(/^\d{4}-\d{2}$/)
export const BoardToneSchema = z.enum(['neutral', 'info', 'success', 'warning', 'danger', 'muted'])

export const BoardOwnerSchema = z.object({
  id: z.string(),
  name: z.string(),
  avatar_url: z.string().nullable(),
}).strict()
