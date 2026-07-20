import { z } from 'zod'

export const SalesDashboardScopeSchema = z.enum(['own', 'team', 'all'])
export const SalesDashboardMetricValueTypeSchema = z.enum(['count', 'amount'])

export const SalesDashboardMetricSchema = z.object({
  key: z.string(),
  label: z.string(),
  count: z.number(),
  amount: z.number().nullable().optional(),
  secondary_label: z.string().nullable().optional(),
  secondary_value: z.number().nullable().optional(),
  secondary_type: SalesDashboardMetricValueTypeSchema.nullable().optional(),
  rate_label: z.string().nullable().optional(),
  rate: z.number().nullable().optional()
})

export const SalesDashboardFunnelResponseSchema = z.object({
  scope: SalesDashboardScopeSchema,
  period_label: z.string(),
  period_start: z.string(),
  period_end: z.string(),
  metrics: z.array(SalesDashboardMetricSchema)
})

export const SalesDashboardOwnerFilterOptionSchema = z.object({
  id: z.string(),
  name: z.string(),
  is_me: z.boolean()
})

export const SalesDashboardOwnerFilterOptionsResponseSchema = z.object({
  data: z.array(SalesDashboardOwnerFilterOptionSchema)
})

export type SalesDashboardScope = z.infer<typeof SalesDashboardScopeSchema>
export type SalesDashboardMetricValueType = z.infer<typeof SalesDashboardMetricValueTypeSchema>
export type SalesDashboardMetric = z.infer<typeof SalesDashboardMetricSchema>
export type SalesDashboardFunnelResponse = z.infer<typeof SalesDashboardFunnelResponseSchema>
export type SalesDashboardOwnerFilterOption = z.infer<typeof SalesDashboardOwnerFilterOptionSchema>
export type SalesDashboardOwnerFilterOptionsResponse = z.infer<typeof SalesDashboardOwnerFilterOptionsResponseSchema>
