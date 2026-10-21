import { z } from 'zod'

import { BusinessDateStringSchema } from '@/schemas/common'

export const PaymentRecordChartKeySchema = z.enum([
  'license_type',
  'purchase_type',
  'amount_band',
  'payment_month',
  'arr_ratio',
])

export const PaymentRecordChartPreviewSchema = z.object({
  id: z.number().int().positive(),
  record_number: z.string().nullable(),
  customer_name: z.string().nullable(),
  amount: z.number(),
  payment_date: BusinessDateStringSchema.nullable(),
})

export const PaymentRecordChartBucketSchema = z.object({
  key: z.string().min(1),
  label: z.string().min(1),
  count: z.number().int().nonnegative(),
  amount: z.number(),
  ratio: z.number().int().min(0).max(100),
  amount_ratio: z.number().int().min(0).max(100),
  preview: z.array(PaymentRecordChartPreviewSchema),
  preview_total: z.number().int().nonnegative(),
  plotted_ratio: z.number().int().min(0).max(100).nullable().optional(),
  annualized_subscription: z.number().nullable().optional(),
  buyout_amount: z.number().nullable().optional(),
})

export const PaymentRecordChartCardSchema = z.object({
  key: PaymentRecordChartKeySchema,
  title: z.string().min(1),
  description: z.string().min(1),
  buckets: z.array(PaymentRecordChartBucketSchema),
})

export const PaymentRecordChartResponseSchema = z.object({
  population: z.number().int().nonnegative(),
  total_amount: z.number(),
  cards: z.array(PaymentRecordChartCardSchema).length(5),
})

export const PaymentRecordChartBucketRecordsSchema = z.object({
  chart: PaymentRecordChartKeySchema,
  bucket: z.string().min(1),
  total: z.number().int().nonnegative(),
  records: z.array(PaymentRecordChartPreviewSchema),
})

export type PaymentRecordChartPreview = z.infer<typeof PaymentRecordChartPreviewSchema>
export type PaymentRecordChartBucket = z.infer<typeof PaymentRecordChartBucketSchema>
export type PaymentRecordChartCard = z.infer<typeof PaymentRecordChartCardSchema>
export type PaymentRecordChartResponse = z.infer<typeof PaymentRecordChartResponseSchema>
export type PaymentRecordChartBucketRecords = z.infer<typeof PaymentRecordChartBucketRecordsSchema>
