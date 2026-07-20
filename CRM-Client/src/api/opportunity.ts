import request from '@/utils/request'
import type { PaginatedResponse } from '@/types/pagination'

export enum OpportunityStatus {
  FOLLOW_UP = 0,
  WON = 1,
  LOST = 2
}

export enum PurchaseType {
  NEW = 'NEW',
  RENEWAL = 'RENEWAL',
  EXPANSION = 'EXPANSION'
}

export enum LicenseType {
  SUBSCRIPTION = 'SUBSCRIPTION',
  PERPETUAL = 'PERPETUAL'
}

export interface SalesStage {
  id: number
  stage_code: string
  stage_name: string
  win_probability: number
  sort_order: number
  is_active: number
  created_time: string
  updated_time: string
}

export interface SalesStageCreate {
  stage_code: string
  stage_name: string
  win_probability: number
  sort_order: number
}

export interface SalesStageUpdate {
  stage_name?: string
  win_probability?: number
  sort_order?: number
  is_active?: number
}

export interface Opportunity {
  id: number
  opportunity_name: string
  customer_id: number
  customer_name?: string
  procurement_method_id: number | null
  procurement_method_info?: {
    id: number
    code: string
    name: string
    stages?: {
      id: number
      stage_code: string
      stage_name: string
      win_probability: number
      sort_order: number
      is_default_start: boolean
      can_skip: boolean
    }[]
  }
  total_amount: number
  user_count: number
  unit_price: number
  license_type: LicenseType
  subscription_years: number | null
  purchase_type: PurchaseType
  decision_maker_count: number | null
  expected_closing_date: string
  procurement_stage_id: number
  stage_name?: string
  win_probability: number
  current_stage_snapshot?: {
    id: number
    stage_name: string
    win_probability: number
    template_sort_order: number
    template_code: string
    entered_at: string
    exited_at: string | null
    procurement_method: {
      id: number
      code: string
      name: string
    }
  }
  owner_id: string
  owner_info?: OwnerInfo
  creator_id: string
  creator_info?: OwnerInfo
  status: OpportunityStatus
  approval_phase: 'draft' | 'pending_review' | 'approved' | 'rejected'
  actual_amount?: number
  actual_closing_date?: string
  loss_reason?: string
  created_time: string
  updated_time: string
  version: number
  customer_info?: {
    id: number
    account_name: string
  }
}

export interface OwnerInfo {
  id: string
  name: string
  avatar_url: string
}

export interface OwnerFilterOption {
  id: string
  name: string
  is_me: boolean
}

export interface OwnerFilterOptionsResponse {
  data: OwnerFilterOption[]
}

export interface SalesStageDetail {
  id: number
  stage_code: string
  stage_name: string
  win_probability: number
  sort_order: number
  description?: string
  is_active: number
  created_time: string
  last_modified_time: string
}

export interface OpportunityCreate {
  opportunity_name: string
  customer_id: number
  total_amount: number
  user_count: number
  license_type: LicenseType
  subscription_years?: number | null
  purchase_type: PurchaseType
  expected_closing_date: string
  procurement_method_id?: number | null
  procurement_stage_id?: number | null
  owner_id: string
  decision_maker_count?: number | null
}

export interface OpportunityUpdate {
  opportunity_name?: string
  total_amount?: number
  user_count?: number
  license_type?: LicenseType
  subscription_years?: number | null
  purchase_type?: PurchaseType
  decision_maker_count?: number | null
  expected_closing_date?: string
  procurement_method_id?: number | null
  procurement_stage_id?: number | null
}

export interface OpportunityMoveStageRequest {
  procurement_stage_id: number
}

export interface OpportunityStageUpdate {
  procurement_stage_id: number
}

export interface OpportunityWinRequest {
  actual_amount: number
  actual_closing_date: string
}

export interface OpportunityLossRequest {
  loss_reason: string
}

export interface OpportunityListParams {
  skip?: number
  limit?: number
  status?: string | number | null
  status_exclude?: string | number | null
  procurement_stage_id?: number | null
  owner_id?: string | null
  owner_id_exclude?: string | null
  customer_id?: number | null
  keyword?: string | null
  customer_keyword?: string | null
  license_type?: string | null
  license_type_exclude?: string | null
  purchase_type?: string | null
  purchase_type_exclude?: string | null
  stage_name?: string | null
  expected_closing_date_start?: string
  expected_closing_date_end?: string
  order_by?: string
  order_dir?: 'asc' | 'desc'
}

export interface SalesFunnelData {
  stage_id: number
  stage_name: string
  opportunity_count: number
  total_amount: number
  average_amount: number
  win_probability: number
}

export interface StageDurationData {
  stage_id: number
  stage_name: string
  avg_duration_days: number
  min_duration_days: number
  max_duration_days: number
  opportunity_count: number
}

export interface OpportunityListResponse {
  id: number
  opportunity_name: string
  customer_id: number
  procurement_method_id: number | null
  procurement_method_info: {
    id: number
    name: string
    description: string | null
    is_active: number
  } | null
  total_amount: number
  user_count: number
  unit_price: number
  license_type: string
  subscription_years: number | null
  purchase_type: string
  decision_maker_count: number | null
  expected_closing_date: string
  stage_id: number | null
  stage_name?: string
  win_probability: number
  owner_id: string
  creator_id: string
  current_stage_snapshot?: {
    id: number
    stage_name: string
    win_probability: number
    template_sort_order: number
    template_code: string
    entered_at: string
    exited_at: string | null
    procurement_method: {
      id: number
      code: string
      name: string
    }
  } | null
  stage: {
    id: number
    stage_code: string
    stage_name: string
    win_probability: number
    sort_order: number
    description: string | null
    is_active: number
    created_time: string
    last_modified_time: string
  } | null
  stage_info: {
    id: number
    stage_name: string
    win_probability: number
    is_default: number
  } | null
  status: number
  approval_phase: 'draft' | 'pending_review' | 'approved' | 'rejected'
  created_time: string
  last_modified_time: string
  customer_name?: string
  owner_info?: {
    id: string
    name: string
    avatar_url?: string | null
  }
}

export const opportunityApi = {
  getOpportunities: (params?: OpportunityListParams) => {
    return request.get<OpportunityListResponse[] | PaginatedResponse<OpportunityListResponse>>(`/v1/opportunities/`, { params })
  },

  getOpportunity: (opportunityId: number) => {
    return request.get<Opportunity>(`/v1/opportunities/${opportunityId}`)
  },

  getOpportunityDetail: (opportunityId: number) => {
    return request.get<Opportunity>(`/v1/opportunities/${opportunityId}`)
  },

  createOpportunity: (data: OpportunityCreate) => {
    return request.post<Opportunity>(`/v1/opportunities/`, data)
  },

  updateOpportunity: (opportunityId: number, data: OpportunityUpdate) => {
    return request.put<Opportunity>(`/v1/opportunities/${opportunityId}`, data)
  },

  moveOpportunityStage: (opportunityId: number, data: OpportunityMoveStageRequest) => {
    return request.post<null>(`/v1/opportunities/${opportunityId}/move-stage`, data)
  },

  markAsWon: (opportunityId: number, data: OpportunityWinRequest) => {
    return request.patch<null>(`/v1/opportunities/${opportunityId}/win`, data)
  },

  markAsLost: (opportunityId: number, data: OpportunityLossRequest) => {
    return request.patch<null>(`/v1/opportunities/${opportunityId}/lose`, data)
  },

  deleteOpportunity: (opportunityId: number) => {
    return request.delete<null>(`/v1/opportunities/${opportunityId}`)
  },

  getSalesFunnel: () => {
    return request.get<SalesFunnelData[]>(`/v1/opportunities/sales-funnel`)
  },

  getStageDuration: () => {
    return request.get<StageDurationData[]>(`/v1/opportunities/stage-duration`)
  },

  getAvailableForContract: (customerId: number) => {
    return request.get<OpportunityListResponse[]>(`/v1/opportunities/available-for-contract`, {
      params: { customer_id: customerId }
    })
  },

  getOwnerFilterOptions: (): Promise<OwnerFilterOptionsResponse> => {
    return request.get<OwnerFilterOptionsResponse>('/v1/filter-options/owners', { params: { resource: 'opportunity' } })
  }
}
