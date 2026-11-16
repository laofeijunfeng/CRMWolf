import { z } from 'zod'
import { BusinessDateStringSchema, BusinessDateTimeStringSchema } from './common'

const NullableString = z.string().nullable()

export const AccountAgingSchema = z.object({
  range: z.string(),
  amount: z.number(),
  count: z.number().int().nonnegative()
})

export const AccountAgingAnalysisSchema = z.object({
  summary: z.object({
    total_overdue_amount: z.number(),
    total_overdue_plans: z.number().int().nonnegative(),
    analysis_date: BusinessDateStringSchema
  }),
  aging_analysis: z.array(AccountAgingSchema),
  details: z.array(z.object({
    plan_id: z.number().int().positive(),
    stage_name: z.string(),
    planned_amount: z.number(),
    paid_amount: z.number(),
    remaining_amount: z.number(),
    due_date: BusinessDateStringSchema,
    days_overdue: z.number().int().nonnegative(),
    contract_id: z.number().int().positive().nullable(),
    contract_name: NullableString,
    customer_id: NullableString,
    customer_name: NullableString
  }))
})

export const OverduePaymentAlertSchema = z.object({
  plan_id: z.number().int().positive(),
  contract_id: z.number().int().positive().nullable(),
  contract_name: NullableString,
  stage_name: z.string(),
  planned_amount: z.number(),
  paid_amount: z.number(),
  remaining_amount: z.number(),
  due_date: BusinessDateStringSchema,
  days_overdue: z.number().int().nonnegative(),
  customer_id: NullableString,
  customer_name: NullableString,
  opportunity_id: z.number().int().positive().nullable(),
  opportunity_name: NullableString,
  owner_id: NullableString,
  owner_name: NullableString
})

export const OverduePaymentAlertsResponseSchema = z.object({
  items: z.array(OverduePaymentAlertSchema),
  total: z.number().int().nonnegative(),
  skip: z.number().int().nonnegative(),
  limit: z.number().int().positive()
})

const ContractRevenueRowSchema = z.object({
  period: z.string().optional(),
  customer_id: NullableString.optional(),
  customer_name: z.string().optional(),
  contract_count: z.number().int().nonnegative(),
  total_amount: z.number(),
  total_paid: z.number(),
  total_pending: z.number()
})

export const ContractRevenueResponseSchema = z.object({
  group_by: z.string(),
  data: z.array(ContractRevenueRowSchema)
})

export const PendingPaymentConfirmationSchema = z.object({
  id: z.number().int().positive(),
  payment_plan_id: z.number().int().positive(),
  actual_amount: z.number(),
  payment_date: BusinessDateStringSchema,
  proof_attachment: NullableString,
  notes: NullableString,
  creator_id: NullableString,
  creator_name: NullableString,
  created_time: BusinessDateTimeStringSchema,
  confirmation_status: z.enum(['PENDING', 'CONFIRMED', 'DISPUTED']).nullable(),
  confirmed_by: NullableString,
  confirmed_by_name: NullableString,
  confirmed_time: BusinessDateTimeStringSchema.nullable(),
  confirmation_notes: NullableString,
  contract_id: z.number().int().positive().nullable(),
  contract_name: NullableString,
  stage_name: NullableString,
  customer_id: NullableString,
  customer_name: NullableString,
  opportunity_id: z.number().int().positive().nullable(),
  opportunity_name: NullableString
})

export const PendingPaymentConfirmationsResponseSchema = z.object({
  items: z.array(PendingPaymentConfirmationSchema),
  total: z.number().int().nonnegative(),
  skip: z.number().int().nonnegative(),
  limit: z.number().int().positive()
})

export const PaymentConfirmationResponseSchema = z.object({
  id: z.number().int().positive(),
  payment_plan_id: z.number().int().positive(),
  actual_amount: z.number(),
  payment_date: BusinessDateStringSchema,
  proof_attachment: NullableString,
  notes: NullableString,
  creator_id: z.string(),
  creator_name: NullableString,
  created_time: BusinessDateTimeStringSchema,
  confirmation_status: z.enum(['PENDING', 'CONFIRMED', 'DISPUTED']),
  confirmed_by: NullableString,
  confirmed_by_name: NullableString,
  confirmed_time: BusinessDateTimeStringSchema.nullable(),
  confirmation_notes: NullableString,
  contract_id: z.number().int().positive().nullable(),
  contract_name: NullableString,
  stage_name: NullableString,
  customer_id: NullableString,
  customer_name: NullableString,
  opportunity_id: z.number().int().positive().nullable(),
  opportunity_name: NullableString
})

export const DashboardStatsSchema = z.object({
  pending_invoice_approvals: z.number().int().nonnegative(),
  pending_payment_confirmations: z.number().int().nonnegative(),
  monthly_expected_revenue: z.string(),
  confirmed_revenue: z.string(),
  overdue_amount: z.string()
})

export type AccountAging = z.infer<typeof AccountAgingSchema>
export type AccountAgingAnalysis = z.infer<typeof AccountAgingAnalysisSchema>
export type OverduePaymentAlert = z.infer<typeof OverduePaymentAlertSchema>
export type OverduePaymentAlertsResponse = z.infer<typeof OverduePaymentAlertsResponseSchema>
export type ContractRevenueStats = z.infer<typeof ContractRevenueRowSchema>
export type ContractRevenueResponse = z.infer<typeof ContractRevenueResponseSchema>
export type PendingPaymentConfirmation = z.infer<typeof PendingPaymentConfirmationSchema>
export type PendingPaymentConfirmationsResponse = z.infer<typeof PendingPaymentConfirmationsResponseSchema>
export type PaymentConfirmationResponse = z.infer<typeof PaymentConfirmationResponseSchema>
export type DashboardStats = z.infer<typeof DashboardStatsSchema>
