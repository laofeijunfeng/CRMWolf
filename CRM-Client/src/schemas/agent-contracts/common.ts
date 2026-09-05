import { z } from 'zod'

export type JsonValue = string | number | boolean | null | JsonValue[] | JsonObject
export interface JsonObject {
  [key: string]: JsonValue
}

export const JsonValueSchema: z.ZodType<JsonValue> = z.lazy(() => z.union([
  z.string(),
  z.number(),
  z.boolean(),
  z.null(),
  z.array(JsonValueSchema),
  z.record(JsonValueSchema)
]))

export const JsonObjectSchema = z.record(JsonValueSchema)

export const CRMResourceSchema = z.enum([
  'customer',
  'contact',
  'customer_activity',
  'deployment_info',
  'follow_up_task',
  'completed_work',
  'opportunity',
  'contract',
  'payment_plan',
  'payment',
  'invoice',
  'license'
])

export const CRMFilterOperatorSchema = z.enum([
  'eq',
  'neq',
  'in',
  'not_in',
  'contains',
  'gte',
  'lte',
  'between',
  'is_null'
])

export const EntityRefSchema = z.object({
  ref_id: z.string().min(1).max(128),
  resource: CRMResourceSchema,
  public_id: z.string().min(1).max(128),
  display_name: z.string().min(1).max(200),
  result_set_id: z.string().min(1).max(128).nullable().optional()
}).strict()

export type CRMResource = z.infer<typeof CRMResourceSchema>
export type EntityRef = z.infer<typeof EntityRefSchema>
