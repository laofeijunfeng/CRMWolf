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

export interface LicenseSummary {
  primary: string
  secondary: string
  tone: 'normal' | 'soon' | 'urgent' | 'none'
}

const RENEWAL_WINDOW_DAYS = 90
function formatDateOnly(value: Date): string {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function formatLicenseSummary(
  expiryDate: string | Date | null | undefined,
  licenseType: string | null | undefined,
  authorizedUsers: number | null | undefined,
  today: Date = new Date()
): LicenseSummary {
  const expiry = expiryDate === null || expiryDate === undefined || expiryDate === ''
    ? null
    : toDateOnly(expiryDate)
  if (expiry === null) {
    return { primary: '未授权', secondary: '-', tone: 'none' }
  }

  const todayDate = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const days = Math.round((expiry.getTime() - todayDate.getTime()) / 86_400_000)
  const expiryText = formatDateOnly(expiry)
  const userText = `${authorizedUsers ?? '-'} 人`
  if (days < 0) {
    return {
      primary: `已过期 ${-days} 天`,
      secondary: `${userText} · ${expiryText}`,
      tone: 'urgent'
    }
  }

  const statusText = licenseStatusLabel(expiry, licenseType, today)
  return {
    primary: days < RENEWAL_WINDOW_DAYS ? `${days} 天后到期` : expiryText,
    secondary: `${statusText} · ${userText}`,
    tone: days < RENEWAL_WINDOW_DAYS ? 'soon' : 'normal'
  }
}
