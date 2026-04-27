import request from '@/utils/request'

export interface OwnerInfo {
  id: string
  name: string
  avatar_url: string
}

export interface Lead {
  id: number
  lead_name: string
  source: string
  city: string
  contact_name: string
  contact_phone: string
  company_scale?: string
  owner_id?: string
  owner_info?: OwnerInfo
  status: number
  pool_id?: number
  creator_id: string
  created_time: string
  last_modified_time: string
  version: number
}

export interface LeadDetail {
  id: number
  lead_name: string
  source: string
  city: string
  contact_name: string
  contact_phone: string
  company_scale?: string
  owner_id?: string
  owner_info?: OwnerInfo
  status: number
  pool_id?: number
  creator_id: string
  creator_info?: OwnerInfo
  created_time: string
  last_modified_time: string
  version: number
  follow_ups: LeadFollowUp[]
}

export interface LeadCreate {
  lead_name: string
  source: string
  city: string
  contact_name: string
  contact_phone: string
  company_scale?: string
}

export interface LeadUpdate {
  lead_name?: string
  source?: string
  city?: string
  contact_name?: string
  contact_phone?: string
  company_scale?: string
  status?: number
}

export interface LeadListParams {
  skip?: number
  limit?: number
  keyword?: string
  status?: number
  source?: string
  city?: string
}

export interface LeadFollowUp {
  id: number
  lead_id: number
  content: string
  method: string
  next_follow_time?: string
  creator_id: string
  creator_info?: OwnerInfo
  created_time: string
}

export interface LeadFollowUpCreate {
  content: string
  method: string
  next_follow_time?: string | null
}

export interface LeadAssignRequest {
  owner_id: string
}

export interface LeadBatchImportRequest {
  leads: LeadCreate[]
}

export interface LeadBatchImportResponse {
  success_count: number
  failed_count: number
  errors?: string[]
}

export interface LeadConversionItem {
  source: string
  total: number
  converted: number
  conversion_rate: number
}

export interface LeadTrendItem {
  date: string
  count: number
}

export const leadApi = {
  createLead: (data: LeadCreate) => {
    return request.post<Lead>('/api/v1/leads/', data)
  },

  batchImport: (data: LeadBatchImportRequest) => {
    return request.post<LeadBatchImportResponse>('/api/v1/leads/batch-import', data)
  },

  getLeadList: (params: LeadListParams) => {
    return request.get<Lead[]>('/api/v1/leads/', { params })
  },

  getLeadDetail: (id: number) => {
    return request.get<LeadDetail>(`/api/v1/leads/${id}`)
  },

  updateLead: (id: number, data: LeadUpdate) => {
    return request.put<Lead>(`/api/v1/leads/${id}`, data)
  },

  deleteLead: (id: number) => {
    return request.delete<Lead>(`/api/v1/leads/${id}`)
  },

  claimLead: (id: number) => {
    return request.post<Lead>(`/api/v1/leads/${id}/claim`)
  },

  assignLead: (id: number, data: LeadAssignRequest) => {
    return request.post<Lead>(`/api/v1/leads/${id}/assign`, data)
  },

  returnLead: (id: number) => {
    return request.post<Lead>(`/api/v1/leads/${id}/return`)
  },

  getFollowUps: (id: number, params?: { skip?: number; limit?: number }) => {
    return request.get<LeadFollowUp[]>(`/api/v1/leads/${id}/follow-ups`, { params })
  },

  addFollowUp: (id: number, data: LeadFollowUpCreate) => {
    return request.post<LeadFollowUp>(`/api/v1/leads/${id}/follow-ups`, data)
  },

  markInvalid: (id: number) => {
    return request.post<Lead>(`/api/v1/leads/${id}/mark-invalid`)
  },

  getPublicLeads: (params?: { skip?: number; limit?: number }) => {
    return request.get<Lead[]>('/api/v1/leads/public/list', { params })
  },

  getMyLeads: (params?: { skip?: number; limit?: number }) => {
    return request.get<Lead[]>('/api/v1/leads/my/list', { params })
  },

  getFollowUpReminder: (days?: number) => {
    return request.get<Lead[]>('/api/v1/leads/follow-up/reminder', { params: { days } })
  },

  getStatistics: () => {
    return request.get('/api/v1/leads/statistics')
  },

  getTrend: (days?: number) => {
    return request.get<LeadTrendItem[]>('/api/v1/analytics/leads/trend', { params: { days } })
  },

  getConversion: () => {
    return request.get<LeadConversionItem[]>('/api/v1/analytics/leads/conversion')
  }
}
