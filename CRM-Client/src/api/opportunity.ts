import request from '@/utils/request'
import type { PaginatedResponse } from '@/types/pagination'
import {
  OpportunityApiResponseSchema,
  OpportunityListApiResponseSchema,
  OpportunityListItemApiSchema,
  OpportunityOwnerFilterOptionsResponseSchema,
  SalesFunnelDataSchema,
  StageDurationDataSchema
} from '@/schemas/opportunity'
import { z } from 'zod'

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
  } | null
  total_amount: number
  user_count: number
  unit_price: number
  license_type: LicenseType
  subscription_years: number | null
  purchase_type: PurchaseType
  decision_maker_count: number | null
  expected_closing_date: string
  procurement_stage_id: number | null
  stage_name?: string
  win_probability: number
  current_stage_snapshot?: {
    id: number
    stage_name: string
    win_probability: number
    template_sort_order: number
    template_code?: string | null
    entered_at: string
    exited_at: string | null
    procurement_method?: {
      id: number
      code: string
      name: string
    } | null
  } | null
  owner_id: string
  owner_info?: OwnerInfo
  creator_id: string
  creator_info?: OwnerInfo
  status: OpportunityStatus
  approval_phase: 'draft' | 'pending_review' | 'approved' | 'rejected'
  actual_amount?: number | null
  actual_closing_date?: string | null
  loss_reason?: string | null
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
  opportunity_name?: string
  customer_id: number
  total_amount: number
  user_count: number
  license_type: LicenseType
  subscription_years?: number | null
  purchase_type: PurchaseType
  expected_closing_date: string
  procurement_method_id?: number | null
  procurement_stage_id?: number | null
  owner_id?: string
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
  getOpportunities: async (params?: OpportunityListParams): Promise<OpportunityListResponse[] | PaginatedResponse<OpportunityListResponse>> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.get<OpportunityListResponse[] | PaginatedResponse<OpportunityListResponse>>(`/v1/opportunities/`, { params })
    return OpportunityListApiResponseSchema.parse(response) as OpportunityListResponse[] | PaginatedResponse<OpportunityListResponse>
  },

  getOpportunity: async (opportunityId: number): Promise<Opportunity> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.get<Opportunity>(`/v1/opportunities/${opportunityId}`)
    return OpportunityApiResponseSchema.parse(response) as Opportunity
  },

  getOpportunityDetail: async (opportunityId: number): Promise<Opportunity> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.get<Opportunity>(`/v1/opportunities/${opportunityId}`)
    return OpportunityApiResponseSchema.parse(response) as Opportunity
  },

  createOpportunity: async (data: OpportunityCreate): Promise<Opportunity> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.post<Opportunity>(`/v1/opportunities/`, data)
    return OpportunityApiResponseSchema.parse(response) as Opportunity
  },

  updateOpportunity: async (opportunityId: number, data: OpportunityUpdate): Promise<Opportunity> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.put<Opportunity>(`/v1/opportunities/${opportunityId}`, data)
    return OpportunityApiResponseSchema.parse(response) as Opportunity
  },

  moveOpportunityStage: async (opportunityId: number, data: OpportunityMoveStageRequest): Promise<null> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.post<null>(`/v1/opportunities/${opportunityId}/move-stage`, data)
    return z.null().parse(response)
  },

  markAsWon: async (opportunityId: number, data: OpportunityWinRequest): Promise<null> => {
    const response = await request.patch<null>(`/v1/opportunities/${opportunityId}/win`, data)
    return z.null().parse(response)
  },

  markAsLost: async (opportunityId: number, data: OpportunityLossRequest): Promise<null> => {
    const response = await request.patch<null>(`/v1/opportunities/${opportunityId}/lose`, data)
    return z.null().parse(response)
  },

  deleteOpportunity: async (opportunityId: number): Promise<null> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.delete<null>(`/v1/opportunities/${opportunityId}`)
    return z.null().parse(response)
  },

  getSalesFunnel: async (): Promise<SalesFunnelData[]> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.get<SalesFunnelData[]>(`/v1/opportunities/sales-funnel`)
    return z.array(SalesFunnelDataSchema).parse(response) as SalesFunnelData[]
  },

  getStageDuration: async (): Promise<StageDurationData[]> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.get<StageDurationData[]>(`/v1/opportunities/stage-duration`)
    return z.array(StageDurationDataSchema).parse(response) as StageDurationData[]
  },

  getAvailableForContract: async (customerId: number): Promise<OpportunityListResponse[]> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.get<OpportunityListResponse[]>(`/v1/opportunities/available-for-contract`, {
      params: { customer_id: customerId }
    })
    return z.array(OpportunityListItemApiSchema).parse(response) as OpportunityListResponse[]
  },

  getOwnerFilterOptions: async (): Promise<OwnerFilterOptionsResponse> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.get<OwnerFilterOptionsResponse>('/v1/filter-options/owners', { params: { resource: 'opportunity' } })
    return OpportunityOwnerFilterOptionsResponseSchema.parse(response) as OwnerFilterOptionsResponse
  }
}
