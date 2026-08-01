import type { AxiosRequestConfig } from 'axios'
import { z } from 'zod'
import request from '@/utils/request'

export type ViewPreferenceScope = 'personal' | 'team'

export interface ViewPreferenceColumn {
  key: string
  order?: number | null | undefined
  visible?: boolean | null | undefined
  width?: number | null | undefined
  fixed?: 'left' | 'right' | null | undefined
}

export interface ViewPreferenceConfig {
  version: number
  columns: ViewPreferenceColumn[]
  sorts?: Record<string, unknown>[] | undefined
  filters?: Record<string, unknown>[] | undefined
  density?: string | null | undefined
}

export interface ViewPreferenceItem {
  id: number
  team_id: number
  user_id: number
  view_key: string
  scope: ViewPreferenceScope
  preference_key: string
  name: string | null
  is_default: boolean
  sort_order: number | null
  config: ViewPreferenceConfig
  created_by: number
  updated_by: number
  created_time: string
  updated_time: string
}

export interface ViewPreferenceResponse {
  view_key: string
  personal: ViewPreferenceItem | null
  team: ViewPreferenceItem | null
  effective_scope: ViewPreferenceScope | null
  effective_config: ViewPreferenceConfig | null
}

export interface ViewPreferenceSaveRequest {
  scope: ViewPreferenceScope
  config: ViewPreferenceConfig
  name?: string | null
  is_default?: boolean
}

export interface ViewPreferenceCustomViewListResponse {
  view_key: string
  items: ViewPreferenceItem[]
}

export interface ViewPreferenceCustomViewCreateRequest {
  config: ViewPreferenceConfig
}

export interface ViewPreferenceCustomViewUpdateRequest {
  name?: string
  config?: ViewPreferenceConfig
  sort_order?: number
}

const ViewPreferenceScopeSchema = z.enum(['personal', 'team'])
const ViewPreferenceConfigSchema: z.ZodType<ViewPreferenceConfig> = z.object({
  version: z.number(),
  columns: z.array(z.object({
    key: z.string(),
    order: z.number().nullable().optional(),
    visible: z.boolean().nullable().optional(),
    width: z.number().nullable().optional(),
    fixed: z.enum(['left', 'right']).nullable().optional(),
  })),
  sorts: z.array(z.record(z.string(), z.unknown())).optional(),
  filters: z.array(z.record(z.string(), z.unknown())).optional(),
  density: z.string().nullable().optional(),
})
const ViewPreferenceItemSchema: z.ZodType<ViewPreferenceItem> = z.object({
  id: z.number(),
  team_id: z.number(),
  user_id: z.number(),
  view_key: z.string(),
  scope: ViewPreferenceScopeSchema,
  preference_key: z.string(),
  name: z.string().nullable(),
  is_default: z.boolean(),
  sort_order: z.number().nullable(),
  config: ViewPreferenceConfigSchema,
  created_by: z.number(),
  updated_by: z.number(),
  created_time: z.string(),
  updated_time: z.string(),
})
const ViewPreferenceResponseSchema: z.ZodType<ViewPreferenceResponse> = z.object({
  view_key: z.string(),
  personal: ViewPreferenceItemSchema.nullable(),
  team: ViewPreferenceItemSchema.nullable(),
  effective_scope: ViewPreferenceScopeSchema.nullable(),
  effective_config: ViewPreferenceConfigSchema.nullable(),
})
const ViewPreferenceCustomViewListResponseSchema: z.ZodType<ViewPreferenceCustomViewListResponse> = z.object({
  view_key: z.string(),
  items: z.array(ViewPreferenceItemSchema),
})

export const viewPreferenceApi = {
  get: (
    viewKey: string,
    config?: AxiosRequestConfig & { skipErrorNotification?: boolean }
  ): Promise<ViewPreferenceResponse> =>
    // eslint-disable-next-line crmwolf/require-zod-schema
    request
      .get<ViewPreferenceResponse>(`/v1/view-preferences/${encodeURIComponent(viewKey)}`, config)
      .then((data) => ViewPreferenceResponseSchema.parse(data)),

  save: (viewKey: string, data: ViewPreferenceSaveRequest): Promise<ViewPreferenceResponse> =>
    // eslint-disable-next-line crmwolf/require-zod-schema
    request
      .put<ViewPreferenceResponse>(`/v1/view-preferences/${encodeURIComponent(viewKey)}`, data)
      .then((response) => ViewPreferenceResponseSchema.parse(response)),

  reset: (viewKey: string, scope: ViewPreferenceScope): Promise<ViewPreferenceResponse> =>
    // eslint-disable-next-line crmwolf/require-zod-schema
    request
      .delete<ViewPreferenceResponse>(
        `/v1/view-preferences/${encodeURIComponent(viewKey)}?scope=${encodeURIComponent(scope)}`
      )
      .then((response) => ViewPreferenceResponseSchema.parse(response)),

  listCustomViews: (
    viewKey: string,
    config?: AxiosRequestConfig & { skipErrorNotification?: boolean }
  ): Promise<ViewPreferenceCustomViewListResponse> =>
    // eslint-disable-next-line crmwolf/require-zod-schema
    request
      .get<ViewPreferenceCustomViewListResponse>(
        `/v1/view-preferences/${encodeURIComponent(viewKey)}/custom-views`,
        config
      )
      .then((response) => ViewPreferenceCustomViewListResponseSchema.parse(response)),

  createCustomView: (viewKey: string, data: ViewPreferenceCustomViewCreateRequest): Promise<ViewPreferenceItem> =>
    // eslint-disable-next-line crmwolf/require-zod-schema
    request
      .post<ViewPreferenceItem>(`/v1/view-preferences/${encodeURIComponent(viewKey)}/custom-views`, data)
      .then((response) => ViewPreferenceItemSchema.parse(response)),

  updateCustomView: (
    viewKey: string,
    id: number,
    data: ViewPreferenceCustomViewUpdateRequest
  ): Promise<ViewPreferenceItem> =>
    request
      .patch<ViewPreferenceItem>(
        `/v1/view-preferences/${encodeURIComponent(viewKey)}/custom-views/${encodeURIComponent(String(id))}`,
        data
      )
      .then((response) => ViewPreferenceItemSchema.parse(response)),

  deleteCustomView: (viewKey: string, id: number): Promise<null> =>
    // eslint-disable-next-line crmwolf/require-zod-schema
    request.delete<null>(`/v1/view-preferences/${encodeURIComponent(viewKey)}/custom-views/${encodeURIComponent(String(id))}`)
}
