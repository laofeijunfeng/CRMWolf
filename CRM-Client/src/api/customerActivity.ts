/* eslint-disable crmwolf/require-zod-schema */
import request from '@/utils/request'

export interface OwnerInfo {
  id: string
  name: string
  avatar_url: string | null
}

export interface CustomerBasicInfo {
  id: number
  account_name: string
}

export interface CustomerActivityCreate {
  activity_kind: string
  source_content: string
  title?: string | null
  occurred_at?: string | null
  next_follow_time?: string | null
  next_follow_time_source?: 'UI_DEFAULT' | 'USER' | 'AI_EXTRACTED' | 'AGENT' | 'MIGRATED' | null
  next_action?: string | null
}

export interface CustomerActivityUpdate {
  activity_kind?: string | null
  source_content?: string | null
  title?: string | null
  occurred_at?: string | null
  next_follow_time?: string | null
  next_follow_time_source?: 'UI_DEFAULT' | 'USER' | 'AI_EXTRACTED' | 'AGENT' | 'MIGRATED' | null
  next_action?: string | null
}

export interface CustomerActivityResponse {
  id: number
  customer_id: number | null
  original_lead_id: number | null
  deal_journey_id?: number | null
  activity_kind: string
  activity_category: string
  activity_label: string
  title?: string | null
  source_content: string
  content_json?: Record<string, unknown> | null
  summary?: string | null
  processing_status?: 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED' | string
  processing_error?: string | null
  processed_at?: string | null
  content: string
  method: string
  next_follow_time: string | null
  next_follow_time_source?: 'UI_DEFAULT' | 'USER' | 'AI_EXTRACTED' | 'AGENT' | 'MIGRATED' | null
  next_action: string | null
  occurred_at?: string
  creator_id: string
  creator_info?: OwnerInfo
  customer_info?: CustomerBasicInfo
  created_time: string
  effectiveness_score?: number | null
  effectiveness_is_valid?: boolean | null
  effectiveness_reason?: string | null
  effectiveness_detail_json?: string | null
  effectiveness_status?: 'PENDING' | 'GENERATING' | 'COMPLETED' | 'FAILED' | string | null
  effectiveness_evaluated_time?: string | null
  effectiveness_error_message?: string | null
}

export interface NextActivityTimeUpdate {
  next_follow_time: string
}

const customerActivityApi = {
  createActivity: (customerId: number, data: CustomerActivityCreate): Promise<CustomerActivityResponse> => {
    return request.post<CustomerActivityResponse>(`/v1/customer-activities/${customerId}`, data)
      .then(normalizeActivity)
  },

  getActivities: (customerId: number): Promise<CustomerActivityResponse[]> => {
    return request.get<CustomerActivityResponse[]>(`/v1/customer-activities/${customerId}`)
      .then((items) => items.map(normalizeActivity))
  },

  updateActivity: (activityId: number, data: CustomerActivityUpdate): Promise<CustomerActivityResponse> => {
    return request.put<CustomerActivityResponse>(`/v1/customer-activities/${activityId}`, data)
      .then(normalizeActivity)
  },

  updateNextActivityTime: (activityId: number, data: NextActivityTimeUpdate): Promise<CustomerActivityResponse> => {
    return request.patch<CustomerActivityResponse>(`/v1/customer-activities/${activityId}/next-time`, data)
      .then(normalizeActivity)
  },

  deleteActivity: (activityId: number): Promise<{ message: string }> => {
    return request.delete<{ message: string }>(`/v1/customer-activities/${activityId}`)
  },

  processActivity: (activityId: number): Promise<{ message: string }> => {
    return request.post<{ message: string }>(`/v1/customer-activities/${activityId}/process`)
  },

  getKinds: (): Promise<{ value: string; category: string; label: string; agent_schema: string; score_rule: string }[]> => {
    return request.get<{ value: string; category: string; label: string; agent_schema: string; score_rule: string }[]>('/v1/customer-activities/kinds')
  }
}

function normalizeActivity(activity: CustomerActivityResponse): CustomerActivityResponse {
  return {
    ...activity,
    content: activity.summary !== null && activity.summary !== undefined && activity.summary.length > 0 ? activity.summary : activity.source_content,
    method: activity.activity_label.length > 0 ? activity.activity_label : activity.activity_kind,
    created_time: activity.occurred_at !== undefined && activity.occurred_at.length > 0 ? activity.occurred_at : activity.created_time
  }
}

export default customerActivityApi
