import request from '@/utils/request'

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

export interface ContractStatusUpdate {
  status: ContractStatus
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
  creator_id: string
  created_time: string
  last_modified_time: string
  customer_info?: CustomerBasicInfo
  opportunity_info?: OpportunityBasicInfo
  signing_contact_info?: ContactBasicInfo
  creator_info?: CreatorBasicInfo
}

export interface CreatorBasicInfo {
  id: string
  name: string
  avatar_url?: string
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
  creator_id: string
  created_time: string
  last_modified_time: string
  customer_info?: CustomerBasicInfo
  opportunity_info?: OpportunityBasicInfo
  contact_info?: ContactBasicInfo
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
  status?: ContractStatus | null
  license_type?: LicenseType | null
  contract_number?: string | null
  keyword?: string | null
  owner_id?: string | null  // 新增：负责人ID筛选（用于「我的合同」）
  order_by?: string
  order_dir?: 'asc' | 'desc'
}

export interface ContractFromOpportunityParams {
  contract_name: string
  signing_contact_id: number
}

type ApiResponse<T> = Promise<T>

const contractApi = {
  createContract: (data: ContractCreate): ApiResponse<ContractResponse> => {
    return request.post<ContractResponse>('/v1/contracts/', data) as any
  },

  getContracts: (params?: ContractQueryParams): ApiResponse<ContractListResponse[]> => {
    return request.get<ContractListResponse[]>('/v1/contracts/', { params }) as any
  },

  getContract: (contractId: number): ApiResponse<ContractResponse> => {
    return request.get<ContractResponse>(`/api/v1/contracts/${contractId}`) as any
  },

  updateContract: (contractId: number, data: ContractUpdate): ApiResponse<ContractResponse> => {
    return request.put<ContractResponse>(`/api/v1/contracts/${contractId}`, data) as any
  },

  updateContractStatus: (contractId: number, data: ContractStatusUpdate): ApiResponse<ContractResponse> => {
    return request.patch<ContractResponse>(`/api/v1/contracts/${contractId}/status`, data) as any
  },

  deleteContract: (contractId: number): ApiResponse<{ message: string }> => {
    return request.delete<{ message: string }>(`/api/v1/contracts/${contractId}`) as any
  },

  createContractFromOpportunity: (opportunityId: number, params: ContractFromOpportunityParams): ApiResponse<ContractResponse> => {
    return request.post<ContractResponse>(`/api/v1/contracts/from-opportunity/${opportunityId}`, null, {
      params
    }) as any
  },

  getContractByOpportunity: (opportunityId: number): ApiResponse<ContractListResponse> => {
    return request.get<ContractListResponse>(`/api/v1/contracts/opportunity/${opportunityId}`, {
      skipErrorNotification: true
    } as any) as any
  },

  getCustomerContracts: (customerId: number, params?: { skip?: number; limit?: number }): ApiResponse<ContractListResponse[]> => {
    return request.get<ContractListResponse[]>(`/api/v1/customers/${customerId}/contracts`, { params }) as any
  }
}

export default contractApi
