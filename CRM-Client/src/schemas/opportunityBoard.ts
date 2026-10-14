import { z } from 'zod'

import {
  AmountStringSchema,
  BoardOwnerSchema,
  BoardToneSchema,
  CountSchema,
  DateStringSchema,
  EntityIdSchema,
  MonthStringSchema,
  PercentageSchema,
} from '@/schemas/boardPrimitives'

const OpportunityBoardMetadataSchema = z.object({
  customer_name: z.string().nullable(),
  purchase_type: z.string().nullable(),
  license_type: z.string().nullable(),
  expected_closing_date: DateStringSchema.nullable(),
  win_probability: PercentageSchema.nullable(),
  stage_name: z.string().nullable(),
  stage_sort_order: z.number().int().nullable(),
  procurement_method_name: z.string().nullable(),
  procurement_method_code: z.string().nullable(),
  procurement_stage_template_id: EntityIdSchema.nullable(),
  template_code: z.string().nullable(),
}).strict()

const OpportunityBoardActionStateSchema = z.object({
  can_edit: z.boolean(),
  can_delete: z.boolean(),
  can_move_stage: z.boolean(),
  can_mark_won: z.boolean(),
  can_mark_lost: z.boolean(),
}).strict()

const OpportunityStatusSchema = z.enum(['active', 'won', 'lost', 'unset_stage'])

const OpportunityBoardItemSchema = z.object({
  id: z.string(),
  title: z.string(),
  subtitle: z.string().nullable(),
  amount: AmountStringSchema.nullable(),
  date: DateStringSchema.nullable(),
  owner: BoardOwnerSchema.nullable(),
  status: OpportunityStatusSchema,
  metadata: OpportunityBoardMetadataSchema,
  action_state: OpportunityBoardActionStateSchema,
}).strict()

const OpportunityBoardColumnSchema = z.object({
  key: z.string(),
  label: z.string(),
  tone: BoardToneSchema,
  column_kind: z.enum(['active_stage', 'won', 'lost', 'unset_stage']),
  stage_name: z.string().nullable(),
  template_code: z.string().nullable(),
  template_sort_order: z.number().int().nullable(),
  procurement_method_id: EntityIdSchema.nullable(),
  procurement_stage_template_id: EntityIdSchema.nullable(),
  count: CountSchema,
  amount: AmountStringSchema,
  items: z.array(OpportunityBoardItemSchema),
  has_more: z.boolean(),
  remaining_count: CountSchema,
}).strict().superRefine((value, context) => {
  const shown = value.items.length
  if (
    shown !== Math.min(value.count, 5)
    || value.remaining_count !== value.count - shown
    || value.has_more !== (value.remaining_count > 0)
  ) {
    context.addIssue({ code: 'custom', message: 'inconsistent board preview counts' })
  }
})

const OpportunityCountMetricSchema = z.object({
  key: z.enum(['total_count', 'won_count']),
  label: z.string(),
  secondary_label: z.string().nullable().optional(),
  value_type: z.literal('count'),
  value: CountSchema,
  secondary_value: CountSchema.nullable().optional(),
}).strict()

const OpportunityAmountMetricSchema = z.object({
  key: z.enum(['pipeline_amount', 'weighted_amount', 'won_amount']),
  label: z.string(),
  secondary_label: z.string().nullable().optional(),
  value_type: z.literal('amount'),
  value: AmountStringSchema,
  secondary_value: AmountStringSchema.nullable().optional(),
}).strict()

const OpportunityBoardMetricSchema = z.discriminatedUnion('value_type', [
  OpportunityCountMetricSchema,
  OpportunityAmountMetricSchema,
]).superRefine((value, context) => {
  if ((value.secondary_value != null) !== (value.secondary_label != null)) {
    context.addIssue({ code: 'custom', message: 'secondary value and label must be present together' })
  }
})

const OpportunityBoardTrendPointSchema = z.object({
  date: MonthStringSchema,
  count: CountSchema,
  amount: AmountStringSchema,
}).strict()

export const OpportunityBoardResponseSchema = z.object({
  summary: z.array(OpportunityBoardMetricSchema),
  columns: z.array(OpportunityBoardColumnSchema),
  trends: z.array(OpportunityBoardTrendPointSchema),
}).strict()

export type OpportunityBoardResponse = z.infer<typeof OpportunityBoardResponseSchema>
