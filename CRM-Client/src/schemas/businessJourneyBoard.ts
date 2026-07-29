import { z } from 'zod'

export const BusinessJourneyBoardStageKeySchema = z.enum([
  'early_communication',
  'active_progress',
  'closing_soon',
  'won_pending_contract',
  'contract_processing',
  'payment_processing',
  'invoice_processing',
  'completed',
  'lost'
])

export const BusinessJourneyBoardScopeSchema = z.enum(['own', 'team', 'all'])

export const BusinessJourneyBoardOwnerSchema = z.object({
  id: z.string(),
  name: z.string(),
  avatar_url: z.string().nullable().optional()
})

export const BusinessJourneyOpportunitySummarySchema = z.object({
  id: z.number().nullable().optional(),
  name: z.string().nullable().optional(),
  amount: z.number().nullable().optional(),
  actual_amount: z.number().nullable().optional(),
  status: z.number().nullable().optional(),
  current_stage_name: z.string().nullable().optional(),
  win_probability: z.number().nullable().optional(),
  expected_closing_date: z.string().nullable().optional()
})

export const BusinessJourneyContractSummarySchema = z.object({
  count: z.number(),
  signed_count: z.number(),
  amount: z.number()
})

export const BusinessJourneyPaymentSummarySchema = z.object({
  plan_count: z.number(),
  record_count: z.number(),
  planned_amount: z.number(),
  paid_amount: z.number(),
  remaining_amount: z.number()
})

export const BusinessJourneyInvoiceSummarySchema = z.object({
  application_count: z.number(),
  issued_count: z.number(),
  applied_amount: z.number(),
  issued_amount: z.number()
})

export const BusinessJourneyBoardCardSchema = z.object({
  journey_id: z.number(),
  journey_name: z.string(),
  customer_id: z.number(),
  customer_name: z.string().nullable().optional(),
  owner: BusinessJourneyBoardOwnerSchema.nullable().optional(),
  status: z.string(),
  current_board_stage: BusinessJourneyBoardStageKeySchema,
  started_at: z.string().nullable().optional(),
  closed_at: z.string().nullable().optional(),
  last_event_at: z.string().nullable().optional(),
  last_event_summary: z.string().nullable().optional(),
  amount: z.number(),
  primary_opportunity: BusinessJourneyOpportunitySummarySchema.nullable().optional(),
  contract_summary: BusinessJourneyContractSummarySchema,
  payment_summary: BusinessJourneyPaymentSummarySchema,
  invoice_summary: BusinessJourneyInvoiceSummarySchema
})

export const BusinessJourneyBoardColumnSchema = z.object({
  key: BusinessJourneyBoardStageKeySchema,
  title: z.string(),
  description: z.string(),
  count: z.number(),
  amount: z.number(),
  cards: z.array(BusinessJourneyBoardCardSchema)
})

export const BusinessJourneyBoardSummarySchema = z.object({
  total_count: z.number(),
  total_amount: z.number(),
  active_count: z.number(),
  completed_count: z.number(),
  lost_count: z.number()
})

export const BusinessJourneyBoardResponseSchema = z.object({
  scope: BusinessJourneyBoardScopeSchema,
  period_start: z.string().nullable(),
  period_end: z.string().nullable(),
  columns: z.array(BusinessJourneyBoardColumnSchema),
  summary: BusinessJourneyBoardSummarySchema
})

export const BusinessJourneyBoardOwnerFilterOptionSchema = z.object({
  id: z.string(),
  name: z.string(),
  is_me: z.boolean()
})

export const BusinessJourneyBoardOwnerFilterOptionsResponseSchema = z.object({
  data: z.array(BusinessJourneyBoardOwnerFilterOptionSchema)
})

export type BusinessJourneyBoardStageKey = z.infer<typeof BusinessJourneyBoardStageKeySchema>
export type BusinessJourneyBoardScope = z.infer<typeof BusinessJourneyBoardScopeSchema>
export type BusinessJourneyBoardOwner = z.infer<typeof BusinessJourneyBoardOwnerSchema>
export type BusinessJourneyOpportunitySummary = z.infer<typeof BusinessJourneyOpportunitySummarySchema>
export type BusinessJourneyContractSummary = z.infer<typeof BusinessJourneyContractSummarySchema>
export type BusinessJourneyPaymentSummary = z.infer<typeof BusinessJourneyPaymentSummarySchema>
export type BusinessJourneyInvoiceSummary = z.infer<typeof BusinessJourneyInvoiceSummarySchema>
export type BusinessJourneyBoardCard = z.infer<typeof BusinessJourneyBoardCardSchema>
export type BusinessJourneyBoardColumn = z.infer<typeof BusinessJourneyBoardColumnSchema>
export type BusinessJourneyBoardSummary = z.infer<typeof BusinessJourneyBoardSummarySchema>
export type BusinessJourneyBoardResponse = z.infer<typeof BusinessJourneyBoardResponseSchema>
export type BusinessJourneyBoardOwnerFilterOption = z.infer<typeof BusinessJourneyBoardOwnerFilterOptionSchema>
export type BusinessJourneyBoardOwnerFilterOptionsResponse = z.infer<typeof BusinessJourneyBoardOwnerFilterOptionsResponseSchema>
