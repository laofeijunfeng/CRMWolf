import request from '@/utils/request'
import {
  AcquisitionSourceListSchema,
  AcquisitionSourceOptionListSchema,
  AcquisitionSourceSchema,
  type AcquisitionSource,
  type AcquisitionSourceCreate,
  type AcquisitionSourceOption,
  type AcquisitionSourceReorderRequest,
  type AcquisitionSourceUpdate,
} from '@/schemas/acquisition-source'

export type {
  AcquisitionSource,
  AcquisitionSourceCreate,
  AcquisitionSourceInfo,
  AcquisitionSourceOption,
  AcquisitionSourceReorderRequest,
  AcquisitionSourceUpdate,
} from '@/schemas/acquisition-source'

export const acquisitionSourceApi = {
  listOptions: async (includeInactive = false): Promise<AcquisitionSourceOption[]> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get('/v1/acquisition-sources/options', {
      params: { include_inactive: includeInactive },
    })
    return AcquisitionSourceOptionListSchema.parse(raw)
  },

  list: async (): Promise<AcquisitionSource[]> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get('/v1/acquisition-sources/')
    return AcquisitionSourceListSchema.parse(raw)
  },

  create: async (data: AcquisitionSourceCreate): Promise<AcquisitionSource> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.post('/v1/acquisition-sources/', data)
    return AcquisitionSourceSchema.parse(raw)
  },

  update: async (publicId: string, data: AcquisitionSourceUpdate): Promise<AcquisitionSource> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.put(`/v1/acquisition-sources/${publicId}`, data)
    return AcquisitionSourceSchema.parse(raw)
  },

  reorder: async (data: AcquisitionSourceReorderRequest): Promise<AcquisitionSource[]> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.put('/v1/acquisition-sources/reorder', data)
    return AcquisitionSourceListSchema.parse(raw)
  },
}

export default acquisitionSourceApi
