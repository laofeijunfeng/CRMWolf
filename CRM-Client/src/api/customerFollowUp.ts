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

export interface CustomerFollowUpCreate {
  method: string
  content: string
  next_follow_time?: string | null
  next_action?: string | null
}

export interface CustomerFollowUpUpdate {
  method?: string | null
  content?: string | null
  next_follow_time?: string | null
  next_action?: string | null
}

export interface CustomerFollowUpResponse {
  id: number
  customer_id: number | null
  original_lead_id: number | null
  content: string
  method: string
  next_follow_time: string | null
  next_action: string | null
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

export interface NextFollowUpTimeUpdate {
  next_follow_time: string
}

const customerFollowUpApi = {
  createFollowUp: (customerId: number, data: CustomerFollowUpCreate): Promise<CustomerFollowUpResponse> => {
    return request.post<CustomerFollowUpResponse>(`/v1/customer-follow-ups/${customerId}`, data)
  },

  getFollowUps: (customerId: number): Promise<CustomerFollowUpResponse[]> => {
    return request.get<CustomerFollowUpResponse[]>(`/v1/customer-follow-ups/${customerId}`)
  },

  updateFollowUp: (followUpId: number, data: CustomerFollowUpUpdate): Promise<CustomerFollowUpResponse> => {
    return request.put<CustomerFollowUpResponse>(`/v1/customer-follow-ups/${followUpId}`, data)
  },

  updateNextFollowUpTime: (followUpId: number, data: NextFollowUpTimeUpdate): Promise<CustomerFollowUpResponse> => {
    return request.patch<CustomerFollowUpResponse>(`/v1/customer-follow-ups/${followUpId}/next-time`, data)
  },

  deleteFollowUp: (followUpId: number): Promise<{ message: string }> => {
    return request.delete<{ message: string }>(`/v1/customer-follow-ups/${followUpId}`)
  }
}

export default customerFollowUpApi
