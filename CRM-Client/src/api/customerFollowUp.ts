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
}

export interface NextFollowUpTimeUpdate {
  next_follow_time: string
}

const customerFollowUpApi = {
  createFollowUp: (customerId: number, data: CustomerFollowUpCreate) => {
    return request.post<CustomerFollowUpResponse>(`/v1/customer-follow-ups/${customerId}`, data)
  },

  getFollowUps: (customerId: number) => {
    return request.get<CustomerFollowUpResponse[]>(`/v1/customer-follow-ups/${customerId}`)
  },

  updateFollowUp: (followUpId: number, data: CustomerFollowUpUpdate) => {
    return request.put<CustomerFollowUpResponse>(`/v1/customer-follow-ups/${followUpId}`, data)
  },

  updateNextFollowUpTime: (followUpId: number, data: NextFollowUpTimeUpdate) => {
    return request.patch<CustomerFollowUpResponse>(`/v1/customer-follow-ups/${followUpId}/next-time`, data)
  },

  deleteFollowUp: (followUpId: number) => {
    return request.delete<{ message: string }>(`/v1/customer-follow-ups/${followUpId}`)
  }
}

export default customerFollowUpApi
