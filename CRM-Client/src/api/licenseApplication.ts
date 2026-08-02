import request from '@/utils/request'
import { z } from 'zod'
import {
  LicenseApplicationApproveFullSchema,
  LicenseApplicationSchema,
  type LicenseApplication,
  type LicenseApplicationCreate,
  type LicenseApplicationUpdate
} from '@/schemas/licenseApplication'

export type LicenseApplicationStatus = 'DRAFT' | 'PENDING' | 'PENDING_REVIEW' | 'APPROVED' | 'REJECTED' | 'ISSUED'
export type LicenseType = 'TRIAL' | 'OFFICIAL'
export type ApprovalPhase = 'draft' | 'pending_review' | 'approved' | 'rejected'

export type LicenseApplicationResponse = LicenseApplication

const LicenseApplicationListSchema = z.array(LicenseApplicationSchema)

const licenseApplicationApi = {
  // 创建申请
  async create(data: LicenseApplicationCreate): Promise<LicenseApplicationResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.post<LicenseApplicationResponse>('/v1/license-applications/', data)
    return LicenseApplicationSchema.parse(response)
  },

  // 获取申请列表（别名）
  async list(customerId: number): Promise<LicenseApplicationResponse[]> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.get<LicenseApplicationResponse[]>('/v1/license-applications/', {
      params: { customer_id: customerId }
    })
    return LicenseApplicationListSchema.parse(response)
  },

  // 原方法名（向后兼容）
  async createApplication(data: LicenseApplicationCreate): Promise<LicenseApplicationResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.post<LicenseApplicationResponse>('/v1/license-applications/', data)
    return LicenseApplicationSchema.parse(response)
  },

  async getApplications(customerId: number): Promise<LicenseApplicationResponse[]> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.get<LicenseApplicationResponse[]>('/v1/license-applications/', {
      params: { customer_id: customerId }
    })
    return LicenseApplicationListSchema.parse(response)
  },

  async getApplication(applicationId: number): Promise<LicenseApplicationResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.get<LicenseApplicationResponse>(`/v1/license-applications/${applicationId}`)
    return LicenseApplicationSchema.parse(response)
  },

  async updateApplication(applicationId: number, data: LicenseApplicationUpdate): Promise<LicenseApplicationResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.put<LicenseApplicationResponse>(`/v1/license-applications/${applicationId}`, data)
    return LicenseApplicationSchema.parse(response)
  },

  async deleteApplication(applicationId: number): Promise<unknown> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.delete<unknown>(`/v1/license-applications/${applicationId}`)
    return z.unknown().parse(response)
  },

  async submitApplication(applicationId: number): Promise<LicenseApplicationResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.post<LicenseApplicationResponse>(`/v1/license-applications/${applicationId}/submit`)
    return LicenseApplicationSchema.parse(response)
  },

  // 导出 Word 文档
  exportDocument: (applicationId: number): Promise<Blob> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    return request.get(`/v1/license-applications/${applicationId}/export`, {
      responseType: 'blob'
    })
  },

  /**
   * 发放 License（审批通过后调用）
   * @param applicationId License 申请 ID
   * @param data 发放数据（license_info 必填）
   */
  issueLicense: (applicationId: number, data: {
    license_info: string
    comment?: string
  }): Promise<LicenseApplicationResponse> => {
    const payload = LicenseApplicationApproveFullSchema.parse({
      license_info: data.license_info,
      comment: data.comment ?? null
    })
    // eslint-disable-next-line crmwolf/require-zod-schema
    return request.post<LicenseApplicationResponse>(
      `/v1/license-applications/${applicationId}/issue`,
      payload
    ).then((response) => LicenseApplicationSchema.parse(response))
  }
}

export default licenseApplicationApi
