import { z } from 'zod'

import {
  AmountStringSchema,
  BoardOwnerSchema,
  BoardToneSchema,
  CountSchema,
  DateStringSchema,
  EntityIdSchema,
  MonthStringSchema,
} from '@/schemas/boardPrimitives'

const PaymentPlanBoardMetadataSchema = z.object({
  customer_name: z.string().nullable(),
  contract_name: z.string().nullable(),
  opportunity_name: z.string().nullable(),
  paid_amount: AmountStringSchema,
  remaining_amount: AmountStringSchema,
}).strict()

const PaymentPlanBoardActionStateSchema = z.object({
  can_edit: z.boolean(),
  can_delete: z.boolean(),
  can_view_detail: z.boolean(),
}).strict()

const PaymentPlanStatusSchema = z.enum(['PENDING', 'OVERDUE', 'PARTIAL', 'COMPLETED', 'UNCLASSIFIED'])

const PaymentPlanBoardItemSchema = z.object({
  id: EntityIdSchema,
  title: z.string(),
  subtitle: z.string().nullable(),
  amount: AmountStringSchema,
  planned_amount: AmountStringSchema,
  paid_amount: AmountStringSchema,
  remaining_amount: AmountStringSchema,
  date: DateStringSchema.nullable(),
  owner: BoardOwnerSchema.nullable(),
  status: PaymentPlanStatusSchema,
  metadata: PaymentPlanBoardMetadataSchema,
  action_state: PaymentPlanBoardActionStateSchema,
}).strict()

const PaymentPlanBoardColumnSchema = z.object({
  key: PaymentPlanStatusSchema,
  label: z.string(),
  tone: BoardToneSchema,
  count: CountSchema,
  amount: AmountStringSchema,
  planned_amount: AmountStringSchema,
  paid_amount: AmountStringSchema,
  remaining_amount: AmountStringSchema,
  overdue_remaining_amount: AmountStringSchema,
  items: z.array(PaymentPlanBoardItemSchema),
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

const PaymentPlanCountMetricSchema = z.object({
  key: z.literal('overdue_count'),
  label: z.string(),
  secondary_label: z.string().nullable().optional(),
  value_type: z.literal('count'),
  value: CountSchema,
  secondary_value: CountSchema.nullable().optional(),
}).strict()

const PaymentPlanAmountMetricSchema = z.object({
  key: z.enum([
    'planned_amount',
    'paid_amount',
    'remaining_amount',
    'overdue_remaining_amount',
  ]),
  label: z.string(),
  secondary_label: z.string().nullable().optional(),
  value_type: z.literal('amount'),
  value: AmountStringSchema,
  secondary_value: AmountStringSchema.nullable().optional(),
}).strict()

const PaymentPlanBoardMetricSchema = z.discriminatedUnion('value_type', [
  PaymentPlanCountMetricSchema,
  PaymentPlanAmountMetricSchema,
]).superRefine((value, context) => {
  if ((value.secondary_value != null) !== (value.secondary_label != null)) {
    context.addIssue({ code: 'custom', message: 'secondary value and label must be present together' })
  }
})

const PaymentPlanBoardTrendPointSchema = z.object({
  date: MonthStringSchema,
  count: CountSchema,
  planned_amount: AmountStringSchema,
  paid_amount: AmountStringSchema,
  remaining_amount: AmountStringSchema,
}).strict()

export const PaymentPlanBoardResponseSchema = z.object({
  summary: z.array(PaymentPlanBoardMetricSchema),
  columns: z.array(PaymentPlanBoardColumnSchema),
  trends: z.array(PaymentPlanBoardTrendPointSchema),
}).strict()

export type PaymentPlanBoardResponse = z.infer<typeof PaymentPlanBoardResponseSchema>
