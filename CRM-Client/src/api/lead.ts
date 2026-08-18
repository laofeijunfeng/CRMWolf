import request from '@/utils/request'
import type { AcquisitionSourceInfo } from '@/schemas/acquisition-source'
import type { PaginatedResponse } from '@/types/pagination'

export type { AcquisitionSourceInfo }

export interface OwnerInfo {
  id: string
  name: string
  avatar_url: string
}

export interface Lead {
  id: string
  public_id: string
  lead_name: string
  source: string
  source_info?: AcquisitionSourceInfo | null
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
  id: string
  public_id: string
  lead_name: string
  source: string
  source_info?: AcquisitionSourceInfo | null
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
  source_public_id: string
  city: string
  contact_name: string
  contact_phone: string
  company_scale?: string
}

export interface LeadUpdate {
  lead_name?: string
  source_public_id?: string
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
  filters?: string | null
  status?: number
  source?: string
  city?: string
  owner_id?: string
  order_by?: string
  order_dir?: 'asc' | 'desc'
}

export interface LeadFollowUp {
  id: number
  lead_id: string
  content: string
  method: string
  next_follow_time?: string
  next_action?: string
  creator_id: string
  creator_info?: OwnerInfo
  created_time: string
}

export interface LeadFollowUpCreate {
  content: string
  method: string
  next_follow_time?: string | null
  next_action?: string | null
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

export interface LeadMarkInvalidRequest {
  reason: string
}

export interface LeadOwnerFilterOption {
  id: string
  name: string
  is_me: boolean
}

export interface LeadOwnerFilterOptionsResponse {
  data: LeadOwnerFilterOption[]
}

export const leadApi = {
  createLead: (data: LeadCreate): Promise<Lead> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    return request.post<Lead>('/v1/leads/', data)
  },

  batchImport: (data: LeadBatchImportRequest): Promise<LeadBatchImportResponse> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    return request.post<LeadBatchImportResponse>('/v1/leads/batch-import', data)
  },

  getLeadList: (params: LeadListParams): Promise<Lead[] | PaginatedResponse<Lead>> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    return request.get<Lead[] | PaginatedResponse<Lead>>('/v1/leads/', { params })
  },

  getLeadDetail: (id: string): Promise<LeadDetail> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    return request.get<LeadDetail>(`/v1/leads/${id}`)
  },

  updateLead: (id: string, data: LeadUpdate): Promise<Lead> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    return request.put<Lead>(`/v1/leads/${id}`, data)
  },

  deleteLead: (id: string): Promise<Lead> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    return request.delete<Lead>(`/v1/leads/${id}`)
  },

  claimLead: (id: string): Promise<Lead> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    return request.post<Lead>(`/v1/leads/${id}/claim`)
  },

  assignLead: (id: string, data: LeadAssignRequest): Promise<Lead> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    return request.post<Lead>(`/v1/leads/${id}/assign`, data)
  },

  returnLead: (id: string): Promise<Lead> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    return request.post<Lead>(`/v1/leads/${id}/return`)
  },

  getFollowUps: (id: string, params?: { skip?: number; limit?: number }): Promise<LeadFollowUp[]> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    return request.get<LeadFollowUp[]>(`/v1/leads/${id}/follow-ups`, { params })
  },

  addFollowUp: (id: string, data: LeadFollowUpCreate): Promise<LeadFollowUp> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    return request.post<LeadFollowUp>(`/v1/leads/${id}/follow-ups`, data)
  },

  deleteFollowUp: (leadId: string, followUpId: number): Promise<unknown> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    return request.delete(`/v1/leads/${leadId}/follow-ups/${followUpId}`)
  },

  markInvalid: (id: string, data: LeadMarkInvalidRequest): Promise<Lead> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    return request.post<Lead>(`/v1/leads/${id}/mark-invalid`, data)
  },

  getPublicLeads: (params?: Pick<LeadListParams, 'skip' | 'limit' | 'filters'>): Promise<Lead[] | PaginatedResponse<Lead>> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    return request.get<Lead[] | PaginatedResponse<Lead>>('/v1/leads/public/list', { params })
  },

  getOwnerFilterOptions: (): Promise<LeadOwnerFilterOptionsResponse> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    return request.get<LeadOwnerFilterOptionsResponse>('/v1/filter-options/owners', { params: { resource: 'lead' } })
  },

  getStatistics: (): Promise<unknown> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    return request.get('/v1/leads/statistics')
  },

  getTrend: (days?: number): Promise<LeadTrendItem[]> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    return request.get<LeadTrendItem[]>('/v1/analytics/leads/trend', { params: { days } })
  },

  getConversion: (): Promise<LeadConversionItem[]> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    return request.get<LeadConversionItem[]>('/v1/analytics/leads/conversion')
  }
}
