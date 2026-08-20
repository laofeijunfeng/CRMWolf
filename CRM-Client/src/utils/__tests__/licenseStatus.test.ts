import { describe, expect, it } from 'vitest'
import {
  classifyLicenseStatus,
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
