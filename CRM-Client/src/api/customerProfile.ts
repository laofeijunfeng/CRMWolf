import request from '@/utils/request'
import { logger } from '@/utils/logger'
import {
  CustomerProfileEnvelopeSchema,
  CustomerProfileRefreshResponseSchema,
  CustomerProfileResponseSchema,
  CustomerProfileSubresourceResponseSchema,
  CustomerProfileEvidenceSchema,
  type CustomerProfileEvidence,
  type CustomerProfileRefreshResponse,
  type CustomerProfileResponse
} from '@/schemas/customerProfile'
import type { z } from 'zod'

const parseResponse = <T>(schema: z.ZodType<T>, data: unknown, url: string): T => {
  try {
    return schema.parse(data)
  } catch (error) {
    logger.error('[CustomerProfileAPI]', 'Zod 验证失败', { url, error })
    throw error
  }
}

const unwrap = <T>(schema: z.ZodType<T>, data: unknown, url: string): T => {
  const envelope = parseResponse(CustomerProfileEnvelopeSchema, data, url)
  if (envelope.error !== null || envelope.data === null) {
    throw new Error(envelope.error?.message ?? '客户档案接口未返回数据')
  }
  return parseResponse(schema, envelope.data, url)
}

const customerProfileApi = {
  getProfile: async (customerId: string): Promise<CustomerProfileResponse> => {
    const url = `/v1/customers/${encodeURIComponent(customerId)}/profile`
    return unwrap(
      CustomerProfileResponseSchema,
      CustomerProfileEnvelopeSchema.parse(await request.get<unknown>(url)),
      url
    )
  },

  getEvidence: async (customerId: string, evidenceRef?: string): Promise<CustomerProfileEvidence[]> => {
    const params = evidenceRef === undefined ? '' : `?evidence_ref=${encodeURIComponent(evidenceRef)}`
    const url = `/v1/customers/${encodeURIComponent(customerId)}/profile/evidence${params}`
    const data = unwrap(
      CustomerProfileSubresourceResponseSchema,
      CustomerProfileEnvelopeSchema.parse(await request.get<unknown>(url)),
      url
    )
    return data.items.flatMap((item) => {
      const parsed = CustomerProfileEvidenceSchema.safeParse(item)
      return parsed.success ? [parsed.data] : []
    })
  },

  refresh: async (
    customerId: string,
    payload: { scope?: 'partial' | 'full'; reason?: 'manual_refresh' | 'migration' | 'correction'; expected_current_version?: number | null } = {}
  ): Promise<CustomerProfileRefreshResponse> => {
    const url = `/v1/customers/${encodeURIComponent(customerId)}/profile/refresh`
    return unwrap(
      CustomerProfileRefreshResponseSchema,
      CustomerProfileEnvelopeSchema.parse(await request.post<unknown>(url, payload)),
      url
    )
  }
}

export default customerProfileApi
