import request from '@/utils/request'

export type LicenseApplicationStatus = 'DRAFT' | 'PENDING' | 'APPROVED' | 'REJECTED' | 'ISSUED'
export type LicenseType = 'TRIAL' | 'OFFICIAL'

export interface LicenseApplicationCreate {
  customer_id: number
  deployment_info_id?: number | null
  contract_id?: number | null
  license_type: LicenseType
  expiry_date: string
  remark?: string | null  // 补充需求：备注字段
}

export interface LicenseApplicationUpdate {
  deployment_info_id?: number | null
  contract_id?: number | null
  expiry_date?: string | null
  remark?: string | null  // 补充需求：备注字段
}

export interface LicenseApplicationApprove {
  license_code: string
}

export interface LicenseApplicationApproveFull {
  license_info: string
  comment?: string | null
}

export interface LicenseApplicationResponse {
  id: number
  team_id: number
  application_number: string
  customer_id: number
  deployment_info_id: number | null
  contract_id: number | null
  expiry_date: string
  license_type: string
  // 补充需求字段
  enterprise_id: string | null
  supported_modules: string | null
  server_license_code: string | null
  client_license_code: string | null
  remark: string | null
  // 原有字段
  license_code: string | null
  status: LicenseApplicationStatus
  applicant_id: string
  approver_id: string | null
  approved_time: string | null
  created_time: string
  last_modified_time: string
  customer_name?: string | null
  deployment_name?: string | null
  contract_name?: string | null
}

const licenseApplicationApi = {
  createApplication: (data: LicenseApplicationCreate) => {
    return request.post<LicenseApplicationResponse>('/v1/license-applications/', data)
  },

  getApplications: (customerId: number) => {
    return request.get<LicenseApplicationResponse[]>('/v1/license-applications/', {
      params: { customer_id: customerId }
    })
  },

  getApplication: (applicationId: number) => {
    return request.get<LicenseApplicationResponse>(`/v1/license-applications/${applicationId}`)
  },

  updateApplication: (applicationId: number, data: LicenseApplicationUpdate) => {
    return request.put<LicenseApplicationResponse>(`/v1/license-applications/${applicationId}`, data)
  },

  deleteApplication: (applicationId: number) => {
    return request.delete<void>(`/v1/license-applications/${applicationId}`)
  },

  submitApplication: (applicationId: number) => {
    return request.post<LicenseApplicationResponse>(`/v1/license-applications/${applicationId}/submit`)
  },

  approveApplication: (applicationId: number, data: LicenseApplicationApprove) => {
    return request.post<LicenseApplicationResponse>(`/v1/license-applications/${applicationId}/approve`, data)
  },

  // 补充需求：完整审批版本（解析 License 信息）
  approveApplicationFull: (applicationId: number, data: LicenseApplicationApproveFull) => {
    return request.post<LicenseApplicationResponse>(`/v1/license-applications/${applicationId}/approve-full`, data)
  },

  rejectApplication: (applicationId: number, reason: string) => {
    return request.post<LicenseApplicationResponse>(`/v1/license-applications/${applicationId}/reject`, null, {
      params: { reason }
    })
  },

  // 导出 Word 文档
  exportDocument: (applicationId: number) => {
    return request.get(`/v1/license-applications/${applicationId}/export`, {
      responseType: 'blob'
    })
  }
}

export default licenseApplicationApi