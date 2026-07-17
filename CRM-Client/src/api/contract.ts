import request from '@/utils/request'
import type { PaginatedResponse } from '@/types/pagination'

export type LicenseType = 'SUBSCRIPTION' | 'PERPETUAL'

export type ContractStatus = 'DRAFT' | 'PENDING_REVIEW' | 'SIGNED' | 'EFFECTIVE' | 'EXPIRED' | 'TERMINATED'

export interface ContractCreate {
  contract_name: string
  customer_id: number
  opportunity_id: number
  signing_contact_id: number
  user_count: number
  total_amount: number
  license_type: LicenseType
  subscription_years?: number | null
  signing_date?: string | null
  effective_date?: string | null
  owner_id?: string | null
}

export interface ContractUpdate {
  contract_name?: string | null
  signing_contact_id?: number | null
  user_count?: number | null
  total_amount?: number | null
  license_type?: LicenseType | null
  subscription_years?: number | null
  signing_date?: string | null
  effective_date?: string | null
}

export interface ContractListResponse {
  id: number
  contract_number: string
  contract_name: string
  customer_id: number
  customer_name?: string
  opportunity_id: number
  opportunity_name?: string
  signing_contact_id: number
  user_count: number
  total_amount: string
  license_type: LicenseType
  subscription_years: number | null
  standard_unit_price: string
  status: ContractStatus
  signing_date: string | null
  effective_date: string | null
  expiry_date: string | null
  owner_id: string
  creator_id: string
  created_time: string
  last_modified_time: string
  customer_info?: CustomerBasicInfo
  opportunity_info?: OpportunityBasicInfo
  signing_contact_info?: ContactBasicInfo
  owner_info?: CreatorBasicInfo
  creator_info?: CreatorBasicInfo
}

export interface CreatorBasicInfo {
  id: string
  name: string
  avatar_url?: string
}

export interface OwnerFilterOption {
  id: string
  name: string
  is_me: boolean
}

export interface OwnerFilterOptionsResponse {
  data: OwnerFilterOption[]
}

export interface CustomerBasicInfo {
  id: number
  account_name: string
}

export interface OpportunityBasicInfo {
  id: number
  opportunity_name: string
}

export interface ContactBasicInfo {
  id: number
  name: string
  mobile?: string
  position?: string | null
}

export interface ContractResponse {
  id: number
  contract_number: string
  contract_name: string
  customer_id: number
  opportunity_id: number
  signing_contact_id: number
  user_count: number
  total_amount: string
  license_type: LicenseType
  subscription_years: number | null
  standard_unit_price: string
  status: ContractStatus
  signing_date: string | null
  effective_date: string | null
  expiry_date: string | null
  owner_id: string
  creator_id: string
  created_time: string
  last_modified_time: string
  customer_info?: CustomerBasicInfo
  opportunity_info?: OpportunityBasicInfo
  contact_info?: ContactBasicInfo
  owner_info?: CreatorBasicInfo
  creator_info?: CreatorBasicInfo
  contacts?: {
    id: number
    name: string
    mobile: string
  }[]
}

export interface ContractQueryParams {
  skip?: number
  limit?: number
  customer_id?: number | null
  status?: string | null
  status_exclude?: string | null
  license_type?: string | null
  license_type_exclude?: string | null
  contract_number?: string | null
  keyword?: string | null
  customer_keyword?: string | null
  opportunity_keyword?: string | null
  owner_id?: string | null  // 新增：负责人ID筛选（用于「我的合同」）
  owner_id_exclude?: string | null
  signing_date_start?: string
  signing_date_end?: string
  effective_date_start?: string
  effective_date_end?: string
  expiry_date_start?: string
  expiry_date_end?: string
  order_by?: string
  order_dir?: 'asc' | 'desc'
}

export interface ContractFromOpportunityParams {
  contract_name: string
  signing_contact_id: number
}

const contractApi = {
  createContract: async (data: ContractCreate): Promise<ContractResponse> => {
    const response = await request.post<ContractResponse>('/v1/contracts/', data)
    return response
  },

  getContracts: async (params?: ContractQueryParams): Promise<ContractListResponse[] | PaginatedResponse<ContractListResponse>> => {
    const response = await request.get<ContractListResponse[] | PaginatedResponse<ContractListResponse>>('/v1/contracts/', { params })
    return response
  },

  getContract: async (contractId: number): Promise<ContractResponse> => {
    const response = await request.get<ContractResponse>(`/v1/contracts/${contractId}`)
    return response
  },

  updateContract: async (contractId: number, data: ContractUpdate): Promise<ContractResponse> => {
    const response = await request.put<ContractResponse>(`/v1/contracts/${contractId}`, data)
    return response
  },

  deleteContract: async (contractId: number): Promise<{ message: string }> => {
    const response = await request.delete<{ message: string }>(`/v1/contracts/${contractId}`)
    return response
  },

  createContractFromOpportunity: async (opportunityId: number, params: ContractFromOpportunityParams): Promise<ContractResponse> => {
    const response = await request.post<ContractResponse>(`/v1/contracts/from-opportunity/${opportunityId}`, null, {
      params
    })
    return response
  },

  getContractByOpportunity: async (opportunityId: number): Promise<ContractListResponse> => {
    const response = await request.get<ContractListResponse>(`/v1/contracts/opportunity/${opportunityId}`, {
      skipErrorNotification: true
    })
    return response
  },

  getCustomerContracts: async (customerId: number, params?: { skip?: number; limit?: number }): Promise<ContractListResponse[]> => {
    const response = await request.get<ContractListResponse[]>(`/v1/customers/${customerId}/contracts`, { params })
    return response
  },

  getOwnerFilterOptions: async (): Promise<OwnerFilterOptionsResponse> => {
    const response = await request.get<OwnerFilterOptionsResponse>('/v1/filter-options/owners', { params: { resource: 'contract' } })
    return response
  }
}

export default contractApi
