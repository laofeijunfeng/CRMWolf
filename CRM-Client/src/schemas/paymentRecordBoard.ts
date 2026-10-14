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

const PaymentRecordBoardMetadataSchema = z.object({
  customer_name: z.string().nullable(),
  contract_name: z.string().nullable(),
  actual_payer_name: z.string().nullable(),
  creator_name: z.string().nullable(),
  owner_name: z.string().nullable(),
  commission_member_name: z.string().nullable(),
  approval_phase: z.string().nullable(),
  approval_id: EntityIdSchema.nullable(),
  confirmation_status: z.enum(['PENDING', 'CONFIRMED', 'DISPUTED']).nullable(),
}).strict()

const PaymentRecordBoardActionStateSchema = z.object({
  can_edit: z.boolean(),
  can_delete: z.boolean(),
  can_resubmit: z.boolean(),
}).strict()

const PaymentRecordStatusSchema = z.enum([
  'pending_submit',
  'pending_approval',
  'rejected',
  'approved',
  'unclassified',
])

const PaymentRecordBoardItemSchema = z.object({
  id: EntityIdSchema,
  title: z.string(),
  subtitle: z.string().nullable(),
  amount: AmountStringSchema,
  actual_amount: AmountStringSchema,
  date: DateStringSchema.nullable(),
  owner: BoardOwnerSchema.nullable(),
  status: PaymentRecordStatusSchema,
  metadata: PaymentRecordBoardMetadataSchema,
  action_state: PaymentRecordBoardActionStateSchema,
}).strict()

const PaymentRecordBoardColumnSchema = z.object({
  key: PaymentRecordStatusSchema,
  label: z.string(),
  tone: BoardToneSchema,
  count: CountSchema,
  amount: AmountStringSchema,
  actual_amount: AmountStringSchema,
  confirmed_amount: AmountStringSchema,
  unconfirmed_amount: AmountStringSchema,
  items: z.array(PaymentRecordBoardItemSchema),
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

const PaymentRecordCountMetricSchema = z.object({
  key: z.enum(['total_count', 'rejected_count']),
  label: z.string(),
  secondary_label: z.string().nullable().optional(),
  value_type: z.literal('count'),
  value: CountSchema,
  secondary_value: CountSchema.nullable().optional(),
}).strict()

const PaymentRecordAmountMetricSchema = z.object({
  key: z.enum(['actual_total', 'confirmed_amount', 'unconfirmed_amount']),
  label: z.string(),
  secondary_label: z.string().nullable().optional(),
  value_type: z.literal('amount'),
  value: AmountStringSchema,
  secondary_value: AmountStringSchema.nullable().optional(),
}).strict()

const PaymentRecordBoardMetricSchema = z.discriminatedUnion('value_type', [
  PaymentRecordCountMetricSchema,
  PaymentRecordAmountMetricSchema,
]).superRefine((value, context) => {
  if ((value.secondary_value != null) !== (value.secondary_label != null)) {
    context.addIssue({ code: 'custom', message: 'secondary value and label must be present together' })
  }
})

const PaymentRecordBoardTrendPointSchema = z.object({
  date: MonthStringSchema,
  count: CountSchema,
  actual_amount: AmountStringSchema,
  confirmed_amount: AmountStringSchema,
  unconfirmed_amount: AmountStringSchema,
}).strict()

export const PaymentRecordBoardResponseSchema = z.object({
  summary: z.array(PaymentRecordBoardMetricSchema),
  columns: z.array(PaymentRecordBoardColumnSchema),
  trends: z.array(PaymentRecordBoardTrendPointSchema),
}).strict()

export type PaymentRecordBoardResponse = z.infer<typeof PaymentRecordBoardResponseSchema>
