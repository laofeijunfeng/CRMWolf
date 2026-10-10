import { describe, expect, it } from 'vitest'
import {
  classifyLicenseStatus,
  formatLicenseSummary,
  LICENSE_STATUS_EXPIRED,
  LICENSE_STATUS_NONE,
  LICENSE_STATUS_OFFICIAL,
  LICENSE_STATUS_TRIAL,
  licenseStatusLabel
} from '../licenseStatus'

const today = new Date('2026-08-20T12:00:00')

describe('classifyLicenseStatus', () => {
  it('matches the backend license status matrix', () => {
    expect(classifyLicenseStatus(null, 'OFFICIAL', today)).toBe(LICENSE_STATUS_NONE)
    expect(classifyLicenseStatus('', 'TRIAL', today)).toBe(LICENSE_STATUS_NONE)
    expect(classifyLicenseStatus('2026-08-19', 'OFFICIAL', today)).toBe(LICENSE_STATUS_EXPIRED)
    expect(classifyLicenseStatus('2026-08-19', 'TRIAL', today)).toBe(LICENSE_STATUS_EXPIRED)
    expect(classifyLicenseStatus('2026-08-20', 'TRIAL', today)).toBe(LICENSE_STATUS_TRIAL)
    expect(classifyLicenseStatus('2026-08-21', 'OFFICIAL', today)).toBe(LICENSE_STATUS_OFFICIAL)
    expect(classifyLicenseStatus('2026-08-21', null, today)).toBe(LICENSE_STATUS_OFFICIAL)
    expect(licenseStatusLabel('2026-08-21', 'PERPETUAL', today)).toBe('正式')
  })
})

describe('formatLicenseSummary', () => {
  it('prioritizes renewal timing while keeping authorization scale secondary', () => {
    expect(formatLicenseSummary('2026-11-18', 'OFFICIAL', 32, today)).toEqual({
      primary: '2026-11-18',
      secondary: '正式 · 32 人',
      tone: 'normal'
    })
    expect(formatLicenseSummary('2026-11-17', 'TRIAL', 8, today)).toEqual({
      primary: '89 天后到期',
      secondary: '试用 · 8 人',
      tone: 'soon'
    })
    expect(formatLicenseSummary('2026-08-19', 'OFFICIAL', 120, today)).toEqual({
      primary: '已过期 1 天',
      secondary: '120 人 · 2026-08-19',
      tone: 'urgent'
    })
    expect(formatLicenseSummary(null, null, null, today)).toEqual({
      primary: '未授权',
      secondary: '-',
      tone: 'none'
    })
  })
})
