export const LICENSE_STATUS_NONE = 'none'
export const LICENSE_STATUS_EXPIRED = 'expired'
export const LICENSE_STATUS_TRIAL = 'trial'
export const LICENSE_STATUS_OFFICIAL = 'official'

export type LicenseStatusValue =
  | typeof LICENSE_STATUS_NONE
  | typeof LICENSE_STATUS_EXPIRED
  | typeof LICENSE_STATUS_TRIAL
  | typeof LICENSE_STATUS_OFFICIAL

export const LICENSE_STATUS_LABELS: Record<LicenseStatusValue, string> = {
  none: '未授权',
  expired: '已过期',
  trial: '试用',
  official: '正式'
}

function toDateOnly(value: string | Date): Date | null {
  if (value instanceof Date) {
    if (Number.isNaN(value.getTime())) return null
    return new Date(value.getFullYear(), value.getMonth(), value.getDate())
  }
  const text = value.trim()
  if (text === '') return null
  const date = new Date(`${text.slice(0, 10)}T00:00:00`)
  if (Number.isNaN(date.getTime())) return null
  return date
}

export function classifyLicenseStatus(
  expiryDate: string | Date | null | undefined,
  licenseType: string | null | undefined,
  today: Date = new Date()
): LicenseStatusValue {
  if (expiryDate === null || expiryDate === undefined || expiryDate === '') {
    return LICENSE_STATUS_NONE
  }
  const expiry = toDateOnly(expiryDate)
  if (expiry === null) return LICENSE_STATUS_NONE
  const todayDate = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  if (expiry < todayDate) return LICENSE_STATUS_EXPIRED
  if (licenseType === 'TRIAL') return LICENSE_STATUS_TRIAL
  return LICENSE_STATUS_OFFICIAL
}

export function licenseStatusLabel(
  expiryDate: string | Date | null | undefined,
  licenseType: string | null | undefined,
  today?: Date
): string {
  return LICENSE_STATUS_LABELS[classifyLicenseStatus(expiryDate, licenseType, today)]
}

export function licenseStatusClass(
  expiryDate: string | Date | null | undefined,
  licenseType: string | null | undefined,
  today?: Date
): string {
  return `license-badge--${classifyLicenseStatus(expiryDate, licenseType, today)}`
}
