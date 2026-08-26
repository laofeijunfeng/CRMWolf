import { z } from 'zod'

import { CRMFilterOperatorSchema, CRMResourceSchema, EntityRefSchema, JsonObjectSchema, JsonValueSchema } from './common'

export const CRMFilterSchema = z.object({
  field: z.string().min(1).max(128),
  operator: CRMFilterOperatorSchema,
  value: JsonValueSchema
}).strict()

export const CRMSortSchema = z.object({
  field: z.string().min(1).max(128),
  direction: z.enum(['asc', 'desc'])
}).strict()

export const CRMMetricSchema = z.object({
  key: z.string().min(1).max(128),
  operator: z.enum(['count', 'sum', 'avg', 'min', 'max']),
  field: z.string().min(1).max(128).nullable().optional()
}).strict().superRefine((metric, context) => {
  if (metric.operator !== 'count' && metric.field == null) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      message: `${metric.operator} metric requires field`,
      path: ['field']
    })
  }
})

export const CRMQuerySpecSchema = z.object({
  resource: CRMResourceSchema,
  projection: z.array(z.string()).min(1).max(50),
  filters: z.array(CRMFilterSchema).max(50).default([]),
  sorts: z.array(CRMSortSchema).max(10).default([]),
  metrics: z.array(CRMMetricSchema).max(20).default([]),
  group_by: z.array(z.string()).max(10).default([]),
  scope: z.enum(['accessible', 'mine', 'team']).default('accessible'),
  page_size: z.number().int().min(1).max(100).default(20),
  cursor: z.string().min(1).max(2048).nullable().optional()
}).strict()

export const GroundedFactSchema = z.object({
  fact_id: z.string().min(1).max(128),
  label: z.string().min(1).max(200),
  value: JsonValueSchema,
  source: z.enum(['CRM_API', 'CUSTOMER_INTELLIGENCE', 'DERIVED']),
  source_ref: z.string().min(1).max(512).nullable().optional(),
  entity_ref: EntityRefSchema.nullable().optional()
}).strict()

export const QueryWarningSchema = z.object({
  code: z.enum([
    'RESULT_TRUNCATED',
    'PARTIAL_RESULT',
    'STALE_DATA',
    'CUSTOMER_INTELLIGENCE_DEGRADED'
  ]),
  message: z.string().min(1).max(1000),
  resource: CRMResourceSchema.nullable().optional()
}).strict()

export const QueryErrorSchema = z.object({
  code: z.enum([
    'QUERY_INVALID',
    'QUERY_UNSUPPORTED',
    'QUERY_EMPTY',
    'PERMISSION_DENIED',
    'QUERY_LIMIT_EXCEEDED',
    'UPSTREAM_TIMEOUT',
    'MODEL_OUTPUT_INVALID',
    'INTERNAL_ERROR'
  ]),
  message: z.string().min(1).max(1000),
  retryable: z.boolean(),
  field: z.string().min(1).max(128).nullable().optional(),
  operator: CRMFilterOperatorSchema.nullable().optional()
}).strict()

export const CRMQueryResultSchema = z.object({
  query_id: z.string().min(1).max(128),
  result_set_id: z.string().min(1).max(128).nullable().optional(),
  resource: CRMResourceSchema,
  status: z.enum(['SUCCESS', 'EMPTY', 'PARTIAL']),
  rows: z.array(JsonObjectSchema).max(100).default([]),
  entity_refs: z.array(EntityRefSchema).max(100).default([]),
  total: z.number().int().nonnegative().nullable().optional(),
  next_cursor: z.string().min(1).max(2048).nullable().optional(),
  applied_filters: z.array(CRMFilterSchema).max(50).default([]),
  applied_sorts: z.array(CRMSortSchema).max(10).default([]),
  facts: z.array(GroundedFactSchema).max(200).default([]),
  warnings: z.array(QueryWarningSchema).max(20).default([])
}).strict()

export type CRMQuerySpec = z.infer<typeof CRMQuerySpecSchema>
export type CRMQueryResult = z.infer<typeof CRMQueryResultSchema>
