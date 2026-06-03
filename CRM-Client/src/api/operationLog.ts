import request from '@/utils/request'

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

export interface OperationLogContent {
  [key: string]: any
}

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

const operationLogApi = {
  getResourceLogs: (params: GetResourceLogsParams) => {
    const queryParams: any = {
      primary_resource_type: params.primary_resource_type,
      primary_resource_id: params.primary_resource_id,
      page_no: params.page_no || 1,
      page_size: params.page_size || 20
    }

    if (params.event_types && params.event_types.length > 0) {
      queryParams.event_types = params.event_types.join(',')
    }

    return request.get<OperationLogListResponse>('/v1/operation-logs', {
      params: queryParams
    })
  },

  getMyLogs: (params?: GetMyLogsParams) => {
    return request.get<OperationLogListResponse>('/v1/operation-logs/my-logs', {
      params: params || {}
    })
  }
}

export default operationLogApi
