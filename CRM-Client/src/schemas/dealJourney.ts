import { z } from 'zod'
import { BusinessDateStringSchema, BusinessDateTimeStringSchema } from './common'

export const DealJourneyBoardStageSchema = z.enum([
  'early_communication',
  'active_progress',
  'closing_soon',
  'contract_processing',
  'payment_processing',
  'invoice_processing',
  'completed',
  'lost'
])

export const DealJourneyOpportunitySummarySchema = z.object({
  public_id: z.string().min(1),
  opportunity_name: z.string(),
  status: z.number().int(),
  approval_phase: z.string(),
  win_probability: z.number().int().nullable(),
  expected_closing_date: BusinessDateStringSchema.nullable(),
  product_name: z.string().nullable()
})

export const DealJourneySchema = z.object({
  id: z.string().min(1),
  public_id: z.string().min(1),
  name: z.string(),
  status: z.string(),
  current_board_stage: DealJourneyBoardStageSchema,
  current_board_stage_label: z.string(),
  amount: z.number(),
  purchase_type: z.string().nullable(),
  started_at: BusinessDateTimeStringSchema.nullable(),
  closed_at: BusinessDateTimeStringSchema.nullable(),
  last_event_at: BusinessDateTimeStringSchema.nullable(),
  primary_opportunity: DealJourneyOpportunitySummarySchema.nullable()
})

export const DealJourneyListSchema = z.array(DealJourneySchema)

export const BusinessJourneyOwnerSchema = z.object({
  id: z.string().min(1),
  name: z.string(),
  avatar_url: z.string().nullable().optional()
})

export const BusinessJourneyListItemSchema = DealJourneySchema.extend({
  customer_id: z.string().min(1),
  customer_name: z.string(),
  owner: BusinessJourneyOwnerSchema.nullable(),
  primary_opportunity_name: z.string().nullable(),
  product_name: z.string().nullable(),
  created_time: BusinessDateTimeStringSchema.nullable(),
  expected_closing_date: BusinessDateStringSchema.nullable()
})

export const BusinessJourneyListResponseSchema = z.object({
  items: z.array(BusinessJourneyListItemSchema),
  total: z.number().int().nonnegative(),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total_pages: z.number().int().nonnegative()
})

export const BusinessJourneyBoardOpportunitySummarySchema = z.object({
  public_id: z.string().min(1),
  opportunity_name: z.string(),
  amount: z.number(),
  actual_amount: z.number().nullable().optional(),
  status: z.number().int(),
  current_stage_name: z.string().nullable().optional(),
  win_probability: z.number().nullable().optional(),
  expected_closing_date: BusinessDateStringSchema.nullable().optional()
})

export const BusinessJourneyContractSummarySchema = z.object({
  count: z.number().int().nonnegative(),
  signed_count: z.number().int().nonnegative(),
  amount: z.number()
})

export const BusinessJourneyPaymentSummarySchema = z.object({
  plan_count: z.number().int().nonnegative(),
  record_count: z.number().int().nonnegative(),
  planned_amount: z.number(),
  paid_amount: z.number(),
  remaining_amount: z.number()
})

export const BusinessJourneyInvoiceSummarySchema = z.object({
  application_count: z.number().int().nonnegative(),
  issued_count: z.number().int().nonnegative(),
  applied_amount: z.number(),
  issued_amount: z.number()
})

export const BusinessJourneyBoardCardSchema = z.object({
  public_id: z.string().min(1),
  journey_name: z.string(),
  customer_id: z.string().min(1),
  customer_name: z.string(),
  owner: BusinessJourneyOwnerSchema.nullable().optional(),
  status: z.string(),
  current_board_stage: DealJourneyBoardStageSchema,
  started_at: BusinessDateTimeStringSchema.nullable().optional(),
  closed_at: BusinessDateTimeStringSchema.nullable().optional(),
  last_event_at: BusinessDateTimeStringSchema.nullable().optional(),
  last_event_summary: z.string().nullable().optional(),
  amount: z.number(),
  primary_opportunity: BusinessJourneyBoardOpportunitySummarySchema.nullable().optional(),
  contract_summary: BusinessJourneyContractSummarySchema,
  payment_summary: BusinessJourneyPaymentSummarySchema,
  invoice_summary: BusinessJourneyInvoiceSummarySchema
})

export const BusinessJourneyBoardColumnSchema = z.object({
  key: DealJourneyBoardStageSchema,
  title: z.string(),
  description: z.string(),
  count: z.number().int().nonnegative(),
  amount: z.number(),
  cards: z.array(BusinessJourneyBoardCardSchema)
})

export const BusinessJourneyBoardSummarySchema = z.object({
  total_count: z.number().int().nonnegative(),
  total_amount: z.number(),
  active_count: z.number().int().nonnegative(),
  completed_count: z.number().int().nonnegative(),
  lost_count: z.number().int().nonnegative()
})

export const BusinessJourneyBoardResponseSchema = z.object({
  columns: z.array(BusinessJourneyBoardColumnSchema),
  summary: BusinessJourneyBoardSummarySchema,
  truncated: z.boolean()
})

export const BusinessJourneyOwnerFilterOptionSchema = z.object({
  id: z.string().min(1),
  name: z.string(),
  is_me: z.boolean()
})

export const BusinessJourneyOwnerFilterOptionsResponseSchema = z.object({
  data: z.array(BusinessJourneyOwnerFilterOptionSchema)
})

export type DealJourneyBoardStage = z.infer<typeof DealJourneyBoardStageSchema>
export type DealJourneyOpportunitySummary = z.infer<typeof DealJourneyOpportunitySummarySchema>
export type DealJourney = z.infer<typeof DealJourneySchema>
export type BusinessJourneyOwner = z.infer<typeof BusinessJourneyOwnerSchema>
export type BusinessJourneyListItem = z.infer<typeof BusinessJourneyListItemSchema>
export type BusinessJourneyListResponse = z.infer<typeof BusinessJourneyListResponseSchema>
export type BusinessJourneyBoardOpportunitySummary = z.infer<typeof BusinessJourneyBoardOpportunitySummarySchema>
export type BusinessJourneyContractSummary = z.infer<typeof BusinessJourneyContractSummarySchema>
export type BusinessJourneyPaymentSummary = z.infer<typeof BusinessJourneyPaymentSummarySchema>
export type BusinessJourneyInvoiceSummary = z.infer<typeof BusinessJourneyInvoiceSummarySchema>
export type BusinessJourneyBoardCard = z.infer<typeof BusinessJourneyBoardCardSchema>
export type BusinessJourneyBoardColumn = z.infer<typeof BusinessJourneyBoardColumnSchema>
export type BusinessJourneyBoardSummary = z.infer<typeof BusinessJourneyBoardSummarySchema>
export type BusinessJourneyBoardResponse = z.infer<typeof BusinessJourneyBoardResponseSchema>
export type BusinessJourneyOwnerFilterOption = z.infer<typeof BusinessJourneyOwnerFilterOptionSchema>
export type BusinessJourneyOwnerFilterOptionsResponse = z.infer<typeof BusinessJourneyOwnerFilterOptionsResponseSchema>
