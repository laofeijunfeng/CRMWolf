import request from '@/utils/request'
import {
  SalesDashboardFunnelResponseSchema,
  SalesDashboardOwnerFilterOptionsResponseSchema,
  type SalesDashboardFunnelResponse,
  type SalesDashboardOwnerFilterOptionsResponse
} from '@/schemas/salesDashboard'

export type {
  SalesDashboardScope,
  SalesDashboardMetricValueType,
  SalesDashboardMetric,
  SalesDashboardOwnerFilterOption,
  SalesDashboardFunnelResponse,
  SalesDashboardOwnerFilterOptionsResponse
} from '@/schemas/salesDashboard'

export interface SalesDashboardFunnelParams {
  start_date?: string | null
  end_date?: string | null
  owner_id?: string | null
}

const salesDashboardApi = {
  async getFunnel(params?: SalesDashboardFunnelParams): Promise<SalesDashboardFunnelResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get('/v1/sales-dashboard/funnel', { params })
    return SalesDashboardFunnelResponseSchema.parse(raw)
  },

  async getOwnerFilterOptions(): Promise<SalesDashboardOwnerFilterOptionsResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get('/v1/filter-options/owners', {
      params: { resource: 'sales_dashboard' }
    })
    return SalesDashboardOwnerFilterOptionsResponseSchema.parse(raw)
  }
}

export default salesDashboardApi
