import { describe, expect, it } from 'vitest'
import { getDateAfterDays, getTodayLocalDate } from '@/utils/format'
import {
  LicenseApplicationCreateSchema,
  LicenseApplicationSchema,
  LicenseApplicationUpdateSchema,
  type LicenseApplication
} from '../licenseApplication'

function buildLicenseApplication(
  overrides: Partial<LicenseApplication> = {}
): LicenseApplication {
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
    ...overrides
  }
}

describe('LicenseApplicationSchema', () => {
  it('parses a mixed list that contains an expired historical application', () => {
    const result = LicenseApplicationSchema.array().safeParse([
      buildLicenseApplication({
        id: 11,
        application_number: 'LIC202607210001',
        expiry_date: getDateAfterDays(-16)
      }),
      buildLicenseApplication({
        id: 12,
        application_number: 'LIC202608200001',
        expiry_date: getDateAfterDays(14)
      })
    ])

    expect(result.success).toBe(true)
    if (!result.success) return
    expect(result.data.map((item) => item.application_number)).toEqual([
      'LIC202607210001',
      'LIC202608200001'
    ])
  })

  it('still rejects a non YYYY-MM-DD expiry date', () => {
    expect(LicenseApplicationSchema.safeParse(
      buildLicenseApplication({ expiry_date: '2026/09/03' })
    ).success).toBe(false)
  })
})

describe('LicenseApplicationCreateSchema', () => {
  const validCreate = {
    customer_id: '103',
    deployment_info_id: null,
    contract_id: null,
    authorized_users: 10,
    expiry_date: getDateAfterDays(14),
    license_type: 'TRIAL' as const,
    remark: null
  }

  it('accepts an expiry date later than local today', () => {
    expect(LicenseApplicationCreateSchema.safeParse(validCreate).success).toBe(true)
  })

  it('rejects expiry dates on local today or earlier', () => {
    expect(LicenseApplicationCreateSchema.safeParse({
      ...validCreate,
      expiry_date: getTodayLocalDate()
    }).success).toBe(false)
    expect(LicenseApplicationCreateSchema.safeParse({
      ...validCreate,
      expiry_date: getDateAfterDays(-1)
    }).success).toBe(false)
  })
})

describe('LicenseApplicationUpdateSchema', () => {
  it('keeps the future-date rule while allowing a null expiry', () => {
    expect(LicenseApplicationUpdateSchema.safeParse({
      deployment_info_id: null,
      contract_id: null,
      authorized_users: 10,
      expiry_date: getTodayLocalDate(),
      remark: null
    }).success).toBe(false)
    expect(LicenseApplicationUpdateSchema.safeParse({
      deployment_info_id: null,
      contract_id: null,
      authorized_users: 10,
      expiry_date: getDateAfterDays(-1),
      remark: null
    }).success).toBe(false)
    expect(LicenseApplicationUpdateSchema.safeParse({
      deployment_info_id: null,
      contract_id: null,
      authorized_users: 10,
      expiry_date: null,
      remark: null
    }).success).toBe(true)
  })
})
