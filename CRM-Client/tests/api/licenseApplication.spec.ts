import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getDateAfterDays } from '@/utils/format'

const { requestMock } = vi.hoisted(() => ({
  requestMock: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('@/utils/request', () => ({
  default: requestMock,
}))

import licenseApplicationApi from '@/api/licenseApplication'

function buildLicenseApplicationResponse(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    team_id: 1,
    application_number: 'LIC202608200001',
    customer_id: '103',
    deployment_info_id: null,
    contract_id: null,
    authorized_users: 10,
    expiry_date: getDateAfterDays(14),
    license_type: 'TRIAL',
    enterprise_id: null,
    supported_modules: null,
    server_license_code: null,
    client_license_code: null,
    remark: null,
    license_code: null,
    status: 'ISSUED',
    applicant_id: 'u1',
    approver_id: null,
    approved_time: null,
    created_time: '2026-08-20T09:46:47',
    last_modified_time: '2026-08-20T09:46:47',
    customer_name: '广州市粤港澳大湾区气象智能装备研究中心',
    deployment_name: null,
    contract_name: null,
    ...overrides,
  }
}

describe('license application API', () => {
  beforeEach(() => {
    requestMock.get.mockReset()
  })

  it('keeps expired historical applications when listing by customer', async () => {
    requestMock.get.mockResolvedValue([
      buildLicenseApplicationResponse({
        id: 11,
        application_number: 'LIC202607210001',
        expiry_date: getDateAfterDays(-16),
      }),
      buildLicenseApplicationResponse({
        id: 12,
        application_number: 'LIC202608200001',
        expiry_date: getDateAfterDays(14),
      }),
    ])

    const result = await licenseApplicationApi.list('103')

    expect(requestMock.get).toHaveBeenCalledWith('/v1/license-applications/', {
      params: { customer_id: '103' },
    })
    expect(result.map((item) => item.application_number)).toEqual([
      'LIC202607210001',
      'LIC202608200001',
    ])
  })
})
