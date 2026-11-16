import { z } from 'zod'
import { BusinessDateTimeStringSchema } from './common'
import { ApprovalRecordSchema, MessageResponseSchema } from './approvalGeneric'

const NullableString = z.string().nullable()

export const ApprovalNodeResponseSchema = z.object({
  id: z.number().int().positive(),
  flow_id: z.number().int().positive(),
  node_name: z.string(),
  node_code: z.string(),
  node_order: z.number().int().positive(),
  description: NullableString,
  approve_role: z.string(),
  notify_user_ids: z.array(z.number().int()).nullable(),
  is_required: z.number().int().min(0).max(1),
  created_time: BusinessDateTimeStringSchema
})

export const ApprovalFlowDetailSchema = z.object({
  id: z.number().int().positive(),
  flow_name: z.string(),
  flow_code: z.string(),
  description: NullableString,
  min_amount: z.string().nullable(),
  max_amount: z.string().nullable(),
  license_type: NullableString,
  is_active: z.number().int().min(0).max(1),
  business_type: z.string(),
  created_time: BusinessDateTimeStringSchema,
  last_modified_time: BusinessDateTimeStringSchema,
  nodes: z.array(ApprovalNodeResponseSchema)
})

const ApprovalRecordResponseSchema = ApprovalRecordSchema.extend({
  approver_id: z.string(),
  action: z.string(),
  created_time: BusinessDateTimeStringSchema
})

export const ApprovalDetailSchema = z.object({
  id: z.number().int().positive(),
  contract_id: z.number().int().positive(),
  flow_id: z.number().int().positive().nullable(),
  flow_name: NullableString,
  current_node_id: z.number().int().positive().nullable(),
  current_node_name: NullableString,
  status: z.enum(['PENDING', 'APPROVED', 'REJECTED', 'CANCELLED']),
  submitter_id: z.string(),
  submitter_name: NullableString,
  created_time: BusinessDateTimeStringSchema,
  updated_time: BusinessDateTimeStringSchema,
  flow: ApprovalFlowDetailSchema.nullable(),
  flow_is_active: z.boolean().nullable(),
  flow_disabled_warning: NullableString,
  records: z.array(ApprovalRecordResponseSchema)
})

export type ApprovalDetail = z.infer<typeof ApprovalDetailSchema>
export { MessageResponseSchema }
export type { MessageResponse } from './approvalGeneric'

