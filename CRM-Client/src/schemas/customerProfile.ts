import { z } from 'zod'

const JsonRecordSchema = z.record(z.unknown())

export const CustomerProfileFreshnessSchema = z.object({
  profile_as_of: z.string().nullable(),
  latest_business_event_at: z.string().nullable(),
  is_stale: z.boolean(),
  stale_reason: z.string().nullable()
})

export const CustomerProfileSectionsSchema = z.object({
  current_situation: JsonRecordSchema,
  current_journeys: z.array(JsonRecordSchema),
  important_changes: z.array(JsonRecordSchema),
  long_term_context: JsonRecordSchema,
  follow_up_process: z.array(JsonRecordSchema),
  recorded_follow_ups: z.array(JsonRecordSchema)
})

export const CustomerProfileEvidenceRefSchema = z.object({
  evidence_key: z.string().optional(),
  evidence_id: z.string().optional(),
  source_type: z.string().optional(),
  source_id: z.union([z.number().int(), z.string()]).nullable().optional(),
  source_version: z.union([z.number().int(), z.string()]).nullable().optional()
}).passthrough()

export const CustomerProfileEvidenceSchema = z.object({
  evidence_key: z.string(),
  source_type: z.string(),
  source_id: z.string().nullable(),
  source_version: z.union([z.number().int(), z.string()]).nullable(),
  occurred_at: z.string().nullable(),
  title: z.string().nullable(),
  snippet: z.string().nullable(),
  visibility: z.enum(['VISIBLE', 'UNAVAILABLE']),
  availability: z.enum(['AVAILABLE', 'UNAVAILABLE']),
  link: z.string().nullable(),
  reason: z.string().nullable()
})

export const CustomerProfileSubresourceResponseSchema = z.object({
  profile_status: z.enum(['READY', 'UPDATING', 'STALE', 'PARTIAL', 'FAILED', 'NOT_READY']),
  current_profile_version: z.string().nullable(),
  items: z.array(JsonRecordSchema),
  next_cursor: z.string().nullable(),
  has_more: z.boolean()
})

export const CustomerProfileResponseSchema = z.object({
  customer_id: z.string(),
  profile_status: z.enum(['READY', 'UPDATING', 'STALE', 'PARTIAL', 'FAILED', 'NOT_READY']),
  current_profile_version: z.string().nullable(),
  profile_version_number: z.number().int().nullable(),
  schema_version: z.string(),
  freshness: CustomerProfileFreshnessSchema,
  sections: CustomerProfileSectionsSchema,
  evidence_refs: z.array(CustomerProfileEvidenceRefSchema),
  links: z.object({
    changes: z.string(),
    evidence: z.string(),
    journeys: z.string(),
    follow_ups: z.string(),
    versions: z.string()
  })
})

export const CustomerProfileApiErrorSchema = z.object({
  code: z.string(),
  message: z.string(),
  details: JsonRecordSchema.nullable().optional()
})

export const CustomerProfileEnvelopeSchema = z.object({
  request_id: z.string(),
  data: z.unknown().nullable(),
  error: CustomerProfileApiErrorSchema.nullable()
})

export const CustomerProfileRefreshResponseSchema = z.object({
  request_id: z.string(),
  run_id: z.number().int(),
  profile_status: z.enum(['READY', 'UPDATING', 'STALE', 'PARTIAL', 'FAILED', 'NOT_READY']),
  current_profile_version: z.string().nullable(),
  scheduled_at: z.string()
})

export type CustomerProfileResponse = z.infer<typeof CustomerProfileResponseSchema>
export type CustomerProfileEvidence = z.infer<typeof CustomerProfileEvidenceSchema>
export type CustomerProfileRecord = z.infer<typeof JsonRecordSchema>
export type CustomerProfileRefreshResponse = z.infer<typeof CustomerProfileRefreshResponseSchema>
