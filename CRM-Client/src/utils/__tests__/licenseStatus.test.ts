import { describe, expect, it } from 'vitest'
import {
  classifyLicenseStatus,
  formatLicenseExpiry,
  formatLicenseSummary,
  LICENSE_STATUS_EXPIRED,
  LICENSE_STATUS_NONE,
  LICENSE_STATUS_OFFICIAL,
  LICENSE_STATUS_TRIAL,
  licenseDisplayStatus,
  licenseStatusLabel
} from '../licenseStatus'

const today = new Date('2026-08-20T12:00:00')

describe('classifyLicenseStatus', () => {
  it('matches the backend license status matrix', () => {
    expect(classifyLicenseStatus({ license_expiry_date: null, license_type: 'OFFICIAL' }, today)).toBe(LICENSE_STATUS_NONE)
    expect(classifyLicenseStatus({ license_expiry_date: '', license_type: 'TRIAL' }, today)).toBe(LICENSE_STATUS_NONE)
    expect(classifyLicenseStatus({ license_expiry_date: '2026-08-19', license_type: 'OFFICIAL' }, today)).toBe(LICENSE_STATUS_EXPIRED)
    expect(classifyLicenseStatus({ license_expiry_date: '2026-08-19', license_type: 'TRIAL' }, today)).toBe(LICENSE_STATUS_EXPIRED)
    expect(classifyLicenseStatus({ license_expiry_date: '2026-08-20', license_type: 'TRIAL' }, today)).toBe(LICENSE_STATUS_TRIAL)
    expect(classifyLicenseStatus({ license_expiry_date: '2026-08-21', license_type: 'OFFICIAL' }, today)).toBe(LICENSE_STATUS_OFFICIAL)
    expect(classifyLicenseStatus({ license_expiry_date: '2026-08-21', license_type: null }, today)).toBe(LICENSE_STATUS_OFFICIAL)
    expect(licenseStatusLabel({ license_expiry_date: '2026-08-21', license_type: 'PERPETUAL' }, today)).toBe('正式')
  })

  it('treats a permanent official license as official without an expiry date', () => {
    const permanent = { license_expiry_date: null, license_type: 'OFFICIAL', license_is_permanent: true }
    expect(classifyLicenseStatus(permanent, today)).toBe(LICENSE_STATUS_OFFICIAL)
    expect(licenseDisplayStatus(permanent, today)).toBe('permanent')
  })

  it('ignores the permanent flag on a trial license', () => {
    const trial = { license_expiry_date: null, license_type: 'TRIAL', license_is_permanent: true }
    expect(classifyLicenseStatus(trial, today)).toBe(LICENSE_STATUS_NONE)
    expect(licenseDisplayStatus(trial, today)).toBe(LICENSE_STATUS_NONE)
  })
})

describe('formatLicenseExpiry', () => {
  it('shows 永久 for permanent and the date otherwise', () => {
    expect(formatLicenseExpiry({ license_expiry_date: null, license_type: 'OFFICIAL', license_is_permanent: true })).toBe('永久')
    expect(formatLicenseExpiry({ license_expiry_date: '2026-12-31T00:00:00', license_type: 'OFFICIAL', license_is_permanent: false })).toBe('2026-12-31')
    expect(formatLicenseExpiry({ license_expiry_date: null, license_type: null, license_is_permanent: false })).toBe('')
  })
})

describe('formatLicenseSummary', () => {
  it('prioritizes renewal timing while keeping authorization scale secondary', () => {
    expect(formatLicenseSummary({ license_expiry_date: '2026-11-18', license_type: 'OFFICIAL', license_authorized_users: 32 }, today)).toEqual({
      primary: '2026-11-18',
      secondary: '正式 · 32 人',
      tone: 'normal'
    })
    expect(formatLicenseSummary({ license_expiry_date: '2026-11-17', license_type: 'TRIAL', license_authorized_users: 8 }, today)).toEqual({
      primary: '89 天后到期',
      secondary: '试用 · 8 人',
      tone: 'soon'
    })
    expect(formatLicenseSummary({ license_expiry_date: '2026-08-19', license_type: 'OFFICIAL', license_authorized_users: 120 }, today)).toEqual({
      primary: '已过期 1 天',
      secondary: '120 人 · 2026-08-19',
      tone: 'urgent'
    })
    expect(formatLicenseSummary({ license_expiry_date: null, license_type: null, license_authorized_users: null }, today)).toEqual({
      primary: '未授权',
      secondary: '-',
      tone: 'none'
    })
  })

  it('shows 永久 with no countdown or expiry for a permanent license', () => {
    expect(formatLicenseSummary({
      license_expiry_date: null,
      license_type: 'OFFICIAL',
      license_is_permanent: true,
      license_authorized_users: 200
    }, today)).toEqual({
      primary: '永久',
      secondary: '正式 · 200 人',
      tone: 'normal'
    })
  })
})
