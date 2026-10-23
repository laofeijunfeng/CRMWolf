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

const ContractBoardMetadataSchema = z.object({
  customer_name: z.string().nullable(),
  opportunity_name: z.string().nullable(),
  license_type: z.string().nullable(),
  purchase_type: z.string().nullable(),
  signing_date: DateStringSchema.nullable(),
  effective_date: DateStringSchema.nullable(),
  expiry_date: DateStringSchema.nullable(),
  license_expiry_date: DateStringSchema.nullable(),
  authorized_users: CountSchema.nullable(),
}).strict()

const ContractBoardActionStateSchema = z.object({
  can_edit: z.boolean(),
  can_delete: z.boolean(),
  can_submit_approval: z.boolean(),
  can_approve: z.boolean(),
  can_reject: z.boolean(),
}).strict()

const ContractStatusSchema = z.enum([
  'DRAFT',
  'PENDING_REVIEW',
  'SIGNED',
  'EFFECTIVE',
  'EXPIRED',
  'TERMINATED',
  'UNCLASSIFIED',
])

const ContractBoardItemSchema = z.object({
  id: EntityIdSchema,
  title: z.string(),
  subtitle: z.string().nullable(),
  amount: AmountStringSchema.nullable(),
  date: DateStringSchema.nullable(),
  owner: BoardOwnerSchema.nullable(),
  status: ContractStatusSchema,
  metadata: ContractBoardMetadataSchema,
  action_state: ContractBoardActionStateSchema,
}).strict()

const ContractBoardColumnSchema = z.object({
  key: ContractStatusSchema,
  label: z.string(),
  tone: BoardToneSchema,
  count: CountSchema,
  amount: AmountStringSchema,
  items: z.array(ContractBoardItemSchema),
  has_more: z.boolean(),
  remaining_count: CountSchema,
}).strict().superRefine((value, context) => {
  const shown = value.items.length
  if (
    shown !== value.count
    || value.remaining_count !== 0
    || value.has_more
  ) {
    context.addIssue({ code: 'custom', message: 'inconsistent board column counts' })
  }
})

const ContractCountMetricSchema = z.object({
  key: z.enum(['total_count', 'pending_review_count']),
  label: z.string(),
  secondary_label: z.string().nullable().optional(),
  value_type: z.literal('count'),
  value: CountSchema,
  secondary_value: CountSchema.nullable().optional(),
}).strict()

const ContractAmountMetricSchema = z.object({
  key: z.enum(['total_amount', 'signed_effective_amount']),
  label: z.string(),
  secondary_label: z.string().nullable().optional(),
  value_type: z.literal('amount'),
  value: AmountStringSchema,
  secondary_value: AmountStringSchema.nullable().optional(),
}).strict()

const ContractBoardMetricSchema = z.discriminatedUnion('value_type', [
  ContractCountMetricSchema,
  ContractAmountMetricSchema,
]).superRefine((value, context) => {
  if ((value.secondary_value != null) !== (value.secondary_label != null)) {
    context.addIssue({ code: 'custom', message: 'secondary value and label must be present together' })
  }
})

const ContractBoardTrendPointSchema = z.object({
  date: MonthStringSchema,
  count: CountSchema,
  amount: AmountStringSchema,
}).strict()

export const ContractBoardResponseSchema = z.object({
  summary: z.array(ContractBoardMetricSchema),
  columns: z.array(ContractBoardColumnSchema),
  trends: z.array(ContractBoardTrendPointSchema),
}).strict()

export type ContractBoardResponse = z.infer<typeof ContractBoardResponseSchema>
