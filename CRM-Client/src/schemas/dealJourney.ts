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

export type DealJourneyBoardStage = z.infer<typeof DealJourneyBoardStageSchema>
export type DealJourneyOpportunitySummary = z.infer<typeof DealJourneyOpportunitySummarySchema>
export type DealJourney = z.infer<typeof DealJourneySchema>
