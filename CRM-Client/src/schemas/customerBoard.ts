import { z } from 'zod'

import {
  AmountStringSchema,
  BoardOwnerSchema,
  BoardToneSchema,
  CountSchema,
  DateStringSchema,
  MonthStringSchema,
  PercentageSchema,
} from '@/schemas/boardPrimitives'

const CustomerBoardMetadataSchema = z.object({
  stage_hint: z.string().nullable(),
  industry: z.string().nullable(),
  city: z.string().nullable(),
  company_scale: z.string().nullable(),
  license_type: z.enum(['TRIAL', 'OFFICIAL']).nullable(),
  license_expiry_date: DateStringSchema.nullable(),
}).strict()

const CustomerBoardActionStateSchema = z.object({
  can_edit: z.boolean(),
  can_delete: z.boolean(),
  can_assign: z.boolean(),
  can_create_opportunity: z.boolean(),
}).strict()

const CustomerStatusSchema = z.enum(['not_started', 'following', 'repurchasing', 'won', 'lost'])

const CustomerBoardItemSchema = z.object({
  id: z.string(),
  title: z.string(),
  subtitle: z.string().nullable(),
  amount: AmountStringSchema.nullable(),
  date: DateStringSchema.nullable(),
  owner: BoardOwnerSchema.nullable(),
  status: CustomerStatusSchema,
  metadata: CustomerBoardMetadataSchema,
  action_state: CustomerBoardActionStateSchema,
}).strict()

const CustomerBoardColumnSchema = z.object({
  key: CustomerStatusSchema,
  label: z.string(),
  tone: BoardToneSchema,
  count: CountSchema,
  amount: AmountStringSchema.nullable(),
  items: z.array(CustomerBoardItemSchema),
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

const CustomerCountMetricSchema = z.object({
  key: z.enum([
    'total_count',
    'following_count',
    'repurchasing_count',
    'won_count',
    'recent_new_count',
  ]),
  label: z.string(),
  secondary_label: z.string().nullable().optional(),
  value_type: z.literal('count'),
  value: CountSchema,
  secondary_value: CountSchema.nullable().optional(),
}).strict()

const CustomerPercentageMetricSchema = z.object({
  key: z.enum([
    'not_started_percentage',
    'following_percentage',
    'repurchasing_percentage',
    'won_percentage',
    'lost_percentage',
  ]),
  label: z.string(),
  secondary_label: z.string().nullable().optional(),
  value_type: z.literal('percentage'),
  value: PercentageSchema.nullable(),
  secondary_value: PercentageSchema.nullable().optional(),
}).strict()

const CustomerBoardMetricSchema = z.discriminatedUnion('value_type', [
  CustomerCountMetricSchema,
  CustomerPercentageMetricSchema,
]).superRefine((value, context) => {
  if ((value.secondary_value != null) !== (value.secondary_label != null)) {
    context.addIssue({ code: 'custom', message: 'secondary value and label must be present together' })
  }
})

const CustomerBoardTrendPointSchema = z.object({
  date: MonthStringSchema,
  count: CountSchema,
}).strict()

export const CustomerBoardResponseSchema = z.object({
  summary: z.array(CustomerBoardMetricSchema),
  columns: z.array(CustomerBoardColumnSchema),
  trends: z.array(CustomerBoardTrendPointSchema),
}).strict()

export type CustomerBoardResponse = z.infer<typeof CustomerBoardResponseSchema>
