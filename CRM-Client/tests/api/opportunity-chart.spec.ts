import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('@/utils/request', () => ({ default: { get } }))

import { opportunityApi } from '@/api/opportunity'

describe('opportunity chart API', () => {
  beforeEach(() => {
    get.mockReset()
  })

  it('requests the complete chart population with list context', async () => {
    const response = {
      population: 0,
      total_amount: 0,
      cards: [],
    }
    get.mockResolvedValue(response)

    await opportunityApi.getOpportunityChart({
      status: 0,
      search: '企业',
      filters: '[]',
      sorts: '[]',
    })

    expect(get).toHaveBeenCalledWith('/v1/opportunities/chart', {
      params: { status: 0, search: '企业', filters: '[]', sorts: '[]' },
    })
  })

  it('requests a bucket through the concise bucket method', async () => {
    get.mockResolvedValue({
      chart: 'status',
      bucket: 'active',
      total: 0,
      opportunities: [],
    })

    await opportunityApi.getOpportunityChartBucket({
      chart: 'status',
      bucket: 'active',
      status: 0,
      filters: '[]',
      sorts: '[]',
    })

    expect(get).toHaveBeenCalledWith('/v1/opportunities/chart/opportunities', {
      params: {
        chart: 'status',
        bucket: 'active',
        status: 0,
        filters: '[]',
        sorts: '[]',
      },
    })
  })
})
