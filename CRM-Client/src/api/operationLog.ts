import request from '@/utils/request'
import { z } from 'zod'

export type ResourceType = 
  | 'LEAD' 
  | 'CUSTOMER' 
  | 'OPPORTUNITY' 
  | 'CONTRACT' 
  | 'INVOICE' 
  | 'PAYMENT_PLAN' 
  | 'PAYMENT_RECORD'

export type EventType = 
  | 'LEAD_CREATED'
  | 'LEAD_CONVERTED'
  | 'CUSTOMER_CREATED'
  | 'MANUAL_FOLLOW_UP'
  | 'OPPORTUNITY_CREATED'
  | 'CONTRACT_CREATED'
  | 'CONTRACT_STATUS_CHANGED'
  | 'INVOICE_CREATED'
  | 'PAYMENT_RECEIVED'
  | 'SYSTEM_ALERT'

export type EventAction = 'CREATE' | 'UPDATE' | 'DELETE' | 'STATUS_CHANGE'

export type OperationLogContent = Record<string, unknown>;

export interface OperationLog {
  id: number
  event_id: string
  event_type: EventType
  event_action: EventAction
  primary_resource_type: ResourceType
  primary_resource_id: number
  secondary_resource_type: ResourceType | null
  secondary_resource_id: number | null
  operator_id: string
  operator_name: string | null
  operated_at: string
  content: OperationLogContent
  remark: string | null
}

export interface OperationLogListResponse {
  list: OperationLog[]
  total: number
  page_no: number
  page_size: number
}

export interface GetResourceLogsParams {
  primary_resource_type: ResourceType
  primary_resource_id: number
  event_types?: EventType[] | null
  page_no?: number
  page_size?: number
}

export interface GetMyLogsParams {
  page_no?: number
  page_size?: number
}

const ResourceTypeSchema = z.enum([
  'LEAD',
  'CUSTOMER',
  'OPPORTUNITY',
  'CONTRACT',
  'INVOICE',
  'PAYMENT_PLAN',
  'PAYMENT_RECORD',
])

const EventTypeSchema = z.enum([
  'LEAD_CREATED',
  'LEAD_CONVERTED',
  'CUSTOMER_CREATED',
  'MANUAL_FOLLOW_UP',
  'OPPORTUNITY_CREATED',
  'CONTRACT_CREATED',
  'CONTRACT_STATUS_CHANGED',
  'INVOICE_CREATED',
  'PAYMENT_RECEIVED',
  'SYSTEM_ALERT',
])

const EventActionSchema = z.enum(['CREATE', 'UPDATE', 'DELETE', 'STATUS_CHANGE'])

const OperationLogSchema = z.object({
  id: z.number(),
  event_id: z.string(),
  event_type: EventTypeSchema,
  event_action: EventActionSchema,
  primary_resource_type: ResourceTypeSchema,
  primary_resource_id: z.number(),
  secondary_resource_type: ResourceTypeSchema.nullable(),
  secondary_resource_id: z.number().nullable(),
  operator_id: z.string(),
  operator_name: z.string().nullable(),
  operated_at: z.string(),
  content: z.record(z.string(), z.unknown()),
  remark: z.string().nullable(),
}).passthrough()

const OperationLogListResponseSchema = z.object({
  list: z.array(OperationLogSchema),
  total: z.number(),
  page_no: z.number(),
  page_size: z.number(),
})

const operationLogApi = {
  async getResourceLogs(params: GetResourceLogsParams): Promise<OperationLogListResponse> {
    const queryParams: Record<string, unknown> = {
      primary_resource_type: params.primary_resource_type,
      primary_resource_id: params.primary_resource_id,
      page_no: params.page_no ?? 1,
      page_size: params.page_size ?? 20
    }

    if (params.event_types !== undefined && params.event_types !== null && params.event_types.length > 0) {
      queryParams['event_types'] = params.event_types.join(',')
    }

    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get('/v1/operation-logs', {
      params: queryParams
    })
    return OperationLogListResponseSchema.parse(raw)
  },

  async getMyLogs(params?: GetMyLogsParams): Promise<OperationLogListResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get('/v1/operation-logs/my-logs', {
      params: params ?? {}
    })
    return OperationLogListResponseSchema.parse(raw)
  }
}

export default operationLogApi
