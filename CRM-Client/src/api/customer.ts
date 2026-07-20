import request from '@/utils/request'
import { z } from 'zod'
import type { PaginatedResponse } from '@/types/pagination'
import { logger } from '@/utils/logger'
import {
  ConvertResponseSchema,
  CustomerResponseSchema,
  CustomerDetailResponseSchema,
  ContactResponseSchema,
  CustomerStatisticsSchema,
  CustomerReturnResponseSchema
} from '@/schemas/customer'

/**
 * 验证 API 响应数据
 *
 * @description 包装 request 方法并使用 Zod Schema 校验响应数据
 * 此辅助函数内部调用 request 方法，Zod 校验由调用方按需传入 schema 参数处理
 */
const api = {
  get: <T>(url: string, config?: Record<string, unknown>, schema?: z.ZodType): Promise<T> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = request.get<T>(url, config)
    return schema
      ? response.then(data => {
          try {
            return schema.parse(data) as T
          } catch (error) {
            logger.error('[CustomerAPI]', 'Zod 验证失败', { url, error })
            throw error
          }
        })
      : response
  },
  post: <T>(url: string, data?: unknown, config?: Record<string, unknown>, schema?: z.ZodType): Promise<T> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = request.post<T>(url, data, config)
    return schema
      ? response.then(d => {
          try {
            return schema.parse(d) as T
          } catch (error) {
            logger.error('[CustomerAPI]', 'Zod 验证失败', { url, error })
            throw error
          }
        })
      : response
  },
  put: <T>(url: string, data?: unknown, config?: Record<string, unknown>, schema?: z.ZodType): Promise<T> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = request.put<T>(url, data, config)
    return schema
      ? response.then(d => {
          try {
            return schema.parse(d) as T
          } catch (error) {
            logger.error('[CustomerAPI]', 'Zod 验证失败', { url, error })
            throw error
          }
        })
      : response
  },
  delete: <T>(url: string, config?: Record<string, unknown>, schema?: z.ZodType): Promise<T> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = request.delete<T>(url, config)
    return schema
      ? response.then(d => {
          try {
            return schema.parse(d) as T
          } catch (error) {
            logger.error('[CustomerAPI]', 'Zod 验证失败', { url, error })
            throw error
          }
        })
      : response
  },
  patch: <T>(url: string, data?: unknown, config?: Record<string, unknown>, schema?: z.ZodType): Promise<T> => {
    const response = request.patch<T>(url, data, config)
    return schema
      ? response.then(d => {
          try {
            return schema.parse(d) as T
          } catch (error) {
            logger.error('[CustomerAPI]', 'Zod 验证失败', { url, error })
            throw error
          }
        })
      : response
  }
}

export interface CustomerIndustryOption {
  value: string
  label: string
}

export interface ConvertLeadToCustomer {
  lead_id: number
  account_name?: string | null
  address?: string | null
  default_procurement_method_id?: number | null
}

export interface ConvertResponse {
  customer_id: number
  contact_id: number
  message: string
}

export interface CustomerCreate {
  account_name: string
  city: string
  address?: string | null
  company_scale?: string | null
  source?: string | null
  default_procurement_method_id?: number | null
}

export interface CustomerUpdate {
  account_name?: string | null
  city?: string | null
  address?: string | null
  company_scale?: string | null
  source?: string | null
  default_procurement_method_id?: number | null
  // 档案字段（支持手动编辑）
  company_background?: string | null
  company_website?: string | null
  main_business?: string | null
  project_background?: string | null
}

export type CustomerStatus = 0 | 1 | 2 | 3

export interface CustomerStatusUpdate {
  status: CustomerStatus
}

export interface UserBasicInfo {
  id: number
  name: string
  feishu_open_id: string
}

export interface ProcurementMethodInfo {
  id: number
  code: string
  name: string
  is_active: number
}

export interface CustomerIndustryInfo {
  code: string
  name: string  // 完整路径名称，如 "金融/证券"
  primary_code?: string | null  // 一级行业编码
  primary_name?: string | null  // 一级行业名称
  secondary_name?: string | null  // 二级行业名称（如果是二级行业）
}

export interface CustomerResponse {
  id: number
  account_name: string
  industry: string | null
  industry_info?: CustomerIndustryInfo | null
  city: string
  address: string | null
  company_scale: string | null
  source: string | null
  status: CustomerStatus
  owner_id: string | null
  source_lead_id: number | null
  default_procurement_method_id: number | null
  default_procurement_method_info?: ProcurementMethodInfo | null
  loss_reason: string | null
  return_reason: string | null
  returned_time: string | null
  creator_id: string
  created_time: string
  last_modified_time: string
  version: number
  license_expiry_date: string | null
  license_type: string | null
  score?: number | null
  score_updated_at?: string | null
  owner_info?: UserBasicInfo
  creator_info?: UserBasicInfo
}

export interface ContactResponse {
  id: number
  customer_id: number
  name: string
  gender: number | null
  position: string | null
  is_decision_maker: boolean
  mobile: string
  email: string | null
  wechat_id: string | null
  remark: string | null
  reports_to: number | null
  is_primary: boolean
  created_time: string
}

export interface CustomerDefaultOpportunity {
  total_amount: number | null
  user_count: number | null
  license_type: string | null
  subscription_years: number | null
  purchase_type: string | null
  expected_closing_date: string | null
  procurement_method_id: number | null
}

export interface CustomerDetailResponse {
  id: number
  account_name: string
  industry: string | null
  industry_info?: CustomerIndustryInfo | null
  city: string
  address: string | null
  company_scale: string | null
  source: string | null
  status: CustomerStatus
  owner_id: string
  source_lead_id: number | null
  default_procurement_method_id: number | null
  default_procurement_method_info?: ProcurementMethodInfo | null
  default_opportunity?: CustomerDefaultOpportunity | null
  creator_id: string
  created_time: string
  last_modified_time: string
  version: number
  license_expiry_date: string | null
  license_type: string | null
  contacts: ContactResponse[]
  owner_info?: UserBasicInfo
  creator_info?: UserBasicInfo
  // 档案字段
  company_background: string | null
  company_website: string | null
  main_business: string | null
  similar_customers: string | null  // JSON string
  project_background: string | null
  profile_status: string | null  // PENDING | GENERATING | COMPLETED | FAILED
  profile_generated_time: string | null
  profile_error_message: string | null
  // 客户概况字段
  customer_brief_json?: string | null
  customer_brief_markdown?: string | null
  customer_brief_citations?: string | null
  customer_brief_status?: string | null
  customer_brief_generated_time?: string | null
  customer_brief_error_message?: string | null
}

export interface ContactCreate {
  name: string
  gender?: string | null
  position?: string | null
  is_decision_maker?: boolean
  mobile: string
  email?: string | null
  wechat_id?: string | null
  remark?: string | null
  reports_to?: number | null
}

export interface ContactUpdate {
  name?: string | null
  gender?: string | null
  position?: string | null
  is_decision_maker?: boolean | null
  mobile?: string | null
  email?: string | null
  wechat_id?: string | null
  remark?: string | null
  reports_to?: number | null
}

export interface CustomerStatistics {
  total_customers: number
  by_status: {
    status: number
    count: number
  }[]
  by_industry: {
    industry: string | null
    count: number
  }[]
  by_city: {
    city: string
    count: number
  }[]
}

export interface CustomerTrend {
  date: string
  count: number
}

export interface CustomerQueryParams {
  skip?: number
  limit?: number
  status?: string
  status_exclude?: string
  industry?: string
  industry_exclude?: string
  city?: string
  source?: string
  source_exclude?: string
  company_scale?: string
  company_scale_exclude?: string
  owner_id?: string
  owner_id_exclude?: string
  keyword?: string
  created_time_start?: string
  created_time_end?: string
  order_by?: string
  order_dir?: 'asc' | 'desc'
}

export type ReturnReasonEnum = '丢单' | '无意向' | '信息错误' | '长期未跟进' | '预算不足' | '其他'

export interface CustomerReturnRequest {
  return_reason: ReturnReasonEnum
  detailed_reason: string
}

export interface CustomerReturnResponse {
  customer_id: number
  previous_owner: string
  returned_time: string
  return_reason: string
  message: string
}

export interface CustomerClaimRequest {
  owner_id: string
}

export type CustomerOpportunityTransferScope = 'none' | 'following' | 'all'

export interface CustomerAssignRequest {
  owner_id: string
  opportunity_transfer_scope: CustomerOpportunityTransferScope
  remark?: string
}

export interface CustomerAssignResponse {
  customer: CustomerResponse
  transferred_opportunities: number
  transferred_contracts: number
  message: string
}

export interface CustomerLoseRequest {
  loss_reason: string
}

export interface OwnerFilterOption {
  id: string
  name: string
  is_me: boolean
}

export interface OwnerFilterOptionsResponse {
  data: OwnerFilterOption[]
}

export interface PublicCustomerQueryParams {
  skip?: number
  limit?: number
  status?: CustomerStatus
  city?: string
  keyword?: string
  order_by?: string
  order_dir?: 'asc' | 'desc'
}

export interface ContractListResponse {
  id: number
  contract_number: string
  contract_name: string
  customer_id: number
  opportunity_id: number | null
  signing_contact_id: number | null
  user_count: number
  total_amount: string
  license_type: string
  license_type_name?: string
  subscription_years: number | null
  standard_unit_price: string
  status: string
  status_info?: {
    name: string
  }
  signing_date: string | null
  effective_date: string | null
  expiry_date: string | null
  created_time: string
  last_modified_time: string
  customer_name?: string
  opportunity_name?: string
  owner_info?: UserBasicInfo
}

export interface PaymentPlanResponse {
  id: number
  stage_name: string
  planned_amount: number
  due_date: string
  notes: string | null
  contract_id: number
  status: string
  created_time: string
  last_modified_time: string
  paid_amount: number | null
  remaining_amount: number | null
  contract_name?: string
  customer_name?: string
  opportunity_name?: string
}

export interface InvoiceApplicationResponse {
  id: number
  application_number: string
  customer_id: number
  contract_id: number
  opportunity_id: number
  payment_plan_id: number
  invoice_title_id: number
  invoice_amount: string
  invoice_type: string
  payment_record_id: number | null
  status: string
  approval_status: string
  rejection_reason: string | null
  applicant_id: string
  created_time: string
  last_modified_time: string
  contract_name?: string
  contract_number?: string
  stage_name?: string
  planned_amount?: number
  applicant_name?: string
}

const customerApi = {
  convertLeadToCustomer: (data: ConvertLeadToCustomer): Promise<ConvertResponse> =>
    api.post('/v1/customers/convert-from-lead', data, undefined, ConvertResponseSchema),

  createCustomer: (data: CustomerCreate): Promise<CustomerResponse> =>
    api.post('/v1/customers/', data, undefined, CustomerResponseSchema),

  getCustomers: (params?: CustomerQueryParams): Promise<CustomerResponse[] | PaginatedResponse<CustomerResponse>> =>
    api.get<CustomerResponse[] | PaginatedResponse<CustomerResponse>>('/v1/customers/', { params }),

  getCustomerDetail: (customerId: number): Promise<CustomerDetailResponse> =>
    api.get('/v1/customers/' + customerId, undefined, CustomerDetailResponseSchema),

  regenerateCustomerBrief: (customerId: number): Promise<{ message: string }> =>
    api.post('/v1/customers/' + customerId + '/regenerate-brief'),

  updateCustomer: (customerId: number, data: CustomerUpdate): Promise<CustomerResponse> =>
    api.put('/v1/customers/' + customerId, data, undefined, CustomerResponseSchema),

  updateCustomerStatus: (customerId: number, data: CustomerStatusUpdate): Promise<CustomerResponse> =>
    api.patch('/v1/customers/' + customerId + '/status', data, undefined, CustomerResponseSchema),

  markAsLost: (customerId: number, data: CustomerLoseRequest): Promise<CustomerResponse> =>
    api.patch('/v1/customers/' + customerId + '/lose', data, undefined, CustomerResponseSchema),

  deleteCustomer: (customerId: number): Promise<{ message: string }> =>
    api.delete('/v1/customers/' + customerId),

  returnToPool: (customerId: number, data: CustomerReturnRequest): Promise<CustomerReturnResponse> =>
    api.post('/v1/customers/' + customerId + '/return-to-pool', data, undefined, CustomerReturnResponseSchema),

  claimCustomer: (customerId: number, data: CustomerClaimRequest): Promise<CustomerResponse> =>
    api.post('/v1/customers/' + customerId + '/claim', data, undefined, CustomerResponseSchema),

  assignCustomer: (customerId: number, data: CustomerAssignRequest): Promise<CustomerAssignResponse> =>
    api.post<CustomerAssignResponse>('/v1/customers/' + customerId + '/assign', data),

  getPublicCustomers: (params?: PublicCustomerQueryParams): Promise<CustomerResponse[] | PaginatedResponse<CustomerResponse>> =>
    api.get<CustomerResponse[] | PaginatedResponse<CustomerResponse>>('/v1/customers/public/list', { params }),

  getOwnerFilterOptions: (): Promise<OwnerFilterOptionsResponse> =>
    api.get<OwnerFilterOptionsResponse>('/v1/filter-options/owners', { params: { resource: 'customer' } }),

  getIndustryOptions: (): Promise<CustomerIndustryOption[]> =>
    api.get<CustomerIndustryOption[]>('/v1/customers/industries'),

  createContact: (customerId: number, data: ContactCreate): Promise<ContactResponse> =>
    api.post('/v1/customers/' + customerId + '/contacts', data, undefined, ContactResponseSchema),

  getContacts: (customerId: number): Promise<ContactResponse[]> =>
    api.get<ContactResponse[]>('/v1/customers/' + customerId + '/contacts'),

  updateContact: (contactId: number, data: ContactUpdate): Promise<ContactResponse> =>
    api.put('/v1/customers/contacts/' + contactId, data, undefined, ContactResponseSchema),

  setPrimaryContact: (contactId: number): Promise<ContactResponse> =>
    api.patch('/v1/customers/contacts/' + contactId + '/set-primary', undefined, undefined, ContactResponseSchema),

  deleteContact: (contactId: number): Promise<{ message: string }> =>
    api.delete('/v1/customers/contacts/' + contactId),

  getStatistics: (): Promise<CustomerStatistics> =>
    api.get('/v1/customers/statistics/summary', undefined, CustomerStatisticsSchema),

  getTrend: (days = 30): Promise<CustomerTrend[]> =>
    api.get<CustomerTrend[]>('/v1/customers/statistics/trend', { params: { days } }),

  getContracts: (customerId: number, params?: { status?: string | null; skip?: number; limit?: number }): Promise<ContractListResponse[]> =>
    api.get<ContractListResponse[]>('/v1/customers/' + customerId + '/contracts', { params }),

  getPaymentPlans: (customerId: number, params?: { status?: string | null; skip?: number; limit?: number }): Promise<PaymentPlanResponse[]> =>
    api.get<PaymentPlanResponse[]>('/v1/customers/' + customerId + '/payment-plans', { params }),

  getInvoices: (customerId: number, params?: { status?: string | null; skip?: number; limit?: number }): Promise<InvoiceApplicationResponse[]> =>
    api.get<InvoiceApplicationResponse[]>('/v1/customers/' + customerId + '/invoices', { params }),

  regenerateProfile: (customerId: number): Promise<{ message: string }> =>
    api.post('/v1/customers/' + customerId + '/regenerate-profile')
}

export default customerApi
