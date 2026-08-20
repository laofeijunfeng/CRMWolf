import request from '@/utils/request'
import type { PaginatedResponse } from '@/types/pagination'
import { OptionalNullableStringSchema, OptionalStringFromNullableSchema } from '@/schemas/common'
import { z } from 'zod'

export type LicenseType = 'SUBSCRIPTION' | 'PERPETUAL'
export type PurchaseType = 'NEW' | 'RENEWAL' | 'EXPANSION'

export type ContractStatus = 'DRAFT' | 'PENDING_REVIEW' | 'SIGNED' | 'EFFECTIVE' | 'EXPIRED' | 'TERMINATED'
export type ApprovalPhase = 'draft' | 'pending_review' | 'approved' | 'rejected'

export interface ContractCreate {
  contract_name: string
  customer_id: string
  opportunity_id: string
  signing_contact_id: number
  user_count: number
  total_amount: number
  license_type: LicenseType
  subscription_years?: number | null
  signing_date?: string | null
  effective_date?: string | null
  owner_id?: string | null
}

export interface ContractCreateWithFile {
  data: ContractCreate
  file: File
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
  customer_id: string
  customer_name?: string
  opportunity_id: string | null
  opportunity_name?: string
  purchase_type?: PurchaseType | null
  signing_contact_id: number
  user_count: number
  total_amount: string
  license_type: LicenseType
  subscription_years: number | null
  license_authorized_users?: number | null
  license_expiry_date?: string | null
  standard_unit_price: string
  status: ContractStatus
  approval_phase?: ApprovalPhase | null
  signing_date: string | null
  effective_date: string | null
  expiry_date: string | null
  owner_id: string
  creator_id: string
  created_time: string
  last_modified_time: string
  customer_info?: CustomerBasicInfo | null
  opportunity_info?: OpportunityBasicInfo | null
  signing_contact_info?: ContactBasicInfo
  owner_info?: CreatorBasicInfo | null
  creator_info?: CreatorBasicInfo | null
  contract_file_path?: string | null
  contract_file_name?: string | null
  contract_file_size?: number | null
  contract_file_mime_type?: string | null
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
  id: string
  public_id?: string
  account_name: string
}

export interface OpportunityBasicInfo {
  id: string
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
  customer_id: string
  opportunity_id: string | null
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
  customer_info?: CustomerBasicInfo | null
  opportunity_info?: OpportunityBasicInfo | null
  contact_info?: ContactBasicInfo
  owner_info?: CreatorBasicInfo | null
  creator_info?: CreatorBasicInfo | null
  contract_file_path?: string | null
  contract_file_name?: string | null
  contract_file_size?: number | null
  contract_file_mime_type?: string | null
  contacts?: {
    id: number
    name: string
    mobile: string
  }[]
}

export interface ContractQueryParams {
  filters?: string
  sorts?: string
  skip?: number
  limit?: number
  customer_id?: string | null
  status?: string | null
  status_exclude?: string | null
  license_type?: string | null
  license_type_exclude?: string | null
  purchase_type?: string | null
  purchase_type_exclude?: string | null
  subscription_years?: number | null
  subscription_years_exclude?: number | null
  license_authorized_users?: number | null
  license_authorized_users_exclude?: number | null
  standard_unit_price?: number | null
  standard_unit_price_exclude?: number | null
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
  license_expiry_date_start?: string
  license_expiry_date_end?: string
  order_by?: string
  order_dir?: 'asc' | 'desc'
}

export interface ContractFromOpportunityParams {
  contract_name: string
  signing_contact_id: number
  file: File
}

const AmountStringSchema = z.union([z.string(), z.number()]).transform(String)

const CreatorBasicInfoSchema = z.object({
  id: z.string(),
  name: z.string(),
  avatar_url: OptionalNullableStringSchema
})

const CustomerBasicInfoSchema = z.object({
  id: z.string(),
  public_id: z.string().optional(),
  account_name: z.string()
})

const OpportunityBasicInfoSchema = z.object({
  id: z.string(),
  opportunity_name: z.string()
})

const ContactBasicInfoSchema = z.object({
  id: z.number(),
  name: z.string(),
  mobile: z.string().optional(),
  position: OptionalNullableStringSchema
})

const ContractStatusSchema = z.enum(['DRAFT', 'PENDING_REVIEW', 'SIGNED', 'EFFECTIVE', 'EXPIRED', 'TERMINATED'])

const ContractListItemSchema = z.object({
  id: z.number(),
  contract_number: z.string(),
  contract_name: z.string(),
  customer_id: z.string(),
  customer_name: OptionalStringFromNullableSchema,
  opportunity_id: z.string().nullable(),
  opportunity_name: OptionalStringFromNullableSchema,
  purchase_type: z.enum(['NEW', 'RENEWAL', 'EXPANSION']).nullable().optional(),
  signing_contact_id: z.number(),
  user_count: z.number(),
  total_amount: AmountStringSchema,
  license_type: z.enum(['SUBSCRIPTION', 'PERPETUAL']),
  subscription_years: z.number().nullable(),
  license_authorized_users: z.number().nullable().optional(),
  license_expiry_date: z.string().nullable().optional(),
  standard_unit_price: AmountStringSchema,
  status: ContractStatusSchema,
  signing_date: z.string().nullable(),
  effective_date: z.string().nullable(),
  expiry_date: z.string().nullable(),
  owner_id: z.string(),
  creator_id: z.string(),
  created_time: z.string(),
  last_modified_time: z.string(),
  customer_info: CustomerBasicInfoSchema.nullable().optional(),
  opportunity_info: OpportunityBasicInfoSchema.nullable().optional(),
  signing_contact_info: ContactBasicInfoSchema.optional(),
  owner_info: CreatorBasicInfoSchema.nullable().optional(),
  creator_info: CreatorBasicInfoSchema.nullable().optional(),
  contract_file_path: OptionalNullableStringSchema,
  contract_file_name: OptionalNullableStringSchema,
  contract_file_size: z.number().nullable().optional(),
  contract_file_mime_type: OptionalNullableStringSchema
})

const ContractResponseSchema = ContractListItemSchema.extend({
  contact_info: ContactBasicInfoSchema.optional(),
  contacts: z.array(z.object({
    id: z.number(),
    name: z.string(),
    mobile: z.string()
  })).optional()
})

const PaginatedContractListResponseSchema = z.object({
  items: z.array(ContractListItemSchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
  total_pages: z.number()
})

const ContractListApiResponseSchema = z.union([
  z.array(ContractListItemSchema),
  PaginatedContractListResponseSchema
])

const OwnerFilterOptionSchema = z.object({
  id: z.string(),
  name: z.string(),
  is_me: z.boolean()
})

const OwnerFilterOptionsResponseSchema = z.object({
  data: z.array(OwnerFilterOptionSchema)
})

const contractApi = {
  createContract: async (payload: ContractCreateWithFile): Promise<ContractResponse> => {
    const formData = new FormData()
    formData.append('contract_payload', JSON.stringify(payload.data))
    formData.append('file', payload.file)

    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.post('/v1/contracts/', formData)
    return ContractResponseSchema.parse(response) as ContractResponse
  },

  getContracts: async (params?: ContractQueryParams): Promise<ContractListResponse[] | PaginatedResponse<ContractListResponse>> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.get('/v1/contracts/', { params })
    return ContractListApiResponseSchema.parse(response) as ContractListResponse[] | PaginatedResponse<ContractListResponse>
  },

  getContract: async (contractId: number): Promise<ContractResponse> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.get(`/v1/contracts/${contractId}`)
    return ContractResponseSchema.parse(response) as ContractResponse
  },

  updateContract: async (contractId: number, data: ContractUpdate): Promise<ContractResponse> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.put(`/v1/contracts/${contractId}`, data)
    return ContractResponseSchema.parse(response) as ContractResponse
  },

  deleteContract: async (contractId: number): Promise<{ message: string }> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.delete(`/v1/contracts/${contractId}`)
    return z.object({ message: z.string() }).parse(response)
  },

  createContractFromOpportunity: async (opportunityId: string, params: ContractFromOpportunityParams): Promise<ContractResponse> => {
    const formData = new FormData()
    formData.append('contract_name', params.contract_name)
    formData.append('signing_contact_id', String(params.signing_contact_id))
    formData.append('file', params.file)

    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.post(`/v1/contracts/from-opportunity/${opportunityId}`, formData)
    return ContractResponseSchema.parse(response) as ContractResponse
  },

  getContractByOpportunity: async (opportunityId: string): Promise<ContractListResponse | null> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.get(`/v1/contracts/opportunity/${opportunityId}`, {
      skipErrorNotification: true
    })
    return z.union([ContractListItemSchema, z.null()]).parse(response) as ContractListResponse | null
  },

  getCustomerContracts: async (customerId: string, params?: { skip?: number; limit?: number }): Promise<ContractListResponse[]> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.get(`/v1/customers/${customerId}/contracts`, { params })
    return z.array(ContractListItemSchema).parse(response) as ContractListResponse[]
  },

  getOwnerFilterOptions: async (): Promise<OwnerFilterOptionsResponse> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.get('/v1/filter-options/owners', { params: { resource: 'contract' } })
    return OwnerFilterOptionsResponseSchema.parse(response) as OwnerFilterOptionsResponse
  }
}

export default contractApi
