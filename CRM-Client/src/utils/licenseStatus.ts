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

/** 展示态：永久正式授权在列表/详情徽标上单独呈现，但不是筛选/后端状态值。 */
export const LICENSE_DISPLAY_STATUS_PERMANENT = 'permanent'
export type LicenseDisplayStatusValue = LicenseStatusValue | typeof LICENSE_DISPLAY_STATUS_PERMANENT

export const LICENSE_PERMANENT_TEXT = '永久'

/** 客户/合同授权汇总字段（与 API 字段同名，可直接传入响应行）。 */
export interface LicenseSnapshot {
  license_expiry_date?: string | Date | null | undefined
  license_type?: string | null | undefined
  license_is_permanent?: boolean | null | undefined
}

/** 永久仅对正式授权成立（permanent ⇒ OFFICIAL 且无到期日）。 */
export function isPermanentLicense(license: LicenseSnapshot): boolean {
  return license.license_is_permanent === true && license.license_type === 'OFFICIAL'
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
  license: LicenseSnapshot,
  today: Date = new Date()
): LicenseStatusValue {
  if (isPermanentLicense(license)) return LICENSE_STATUS_OFFICIAL
  const expiryDate = license.license_expiry_date
  if (expiryDate === null || expiryDate === undefined || expiryDate === '') {
    return LICENSE_STATUS_NONE
  }
  const expiry = toDateOnly(expiryDate)
  if (expiry === null) return LICENSE_STATUS_NONE
  const todayDate = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  if (expiry < todayDate) return LICENSE_STATUS_EXPIRED
  if (license.license_type === 'TRIAL') return LICENSE_STATUS_TRIAL
  return LICENSE_STATUS_OFFICIAL
}

export function licenseDisplayStatus(
  license: LicenseSnapshot,
  today?: Date
): LicenseDisplayStatusValue {
  return isPermanentLicense(license) ? LICENSE_DISPLAY_STATUS_PERMANENT : classifyLicenseStatus(license, today)
}

export function licenseStatusLabel(
  license: LicenseSnapshot,
  today?: Date
): string {
  return LICENSE_STATUS_LABELS[classifyLicenseStatus(license, today)]
}

/** 授权到期展示文本：永久 → 「永久」，否则日期（YYYY-MM-DD）；无授权为空。 */
export function formatLicenseExpiry(license: LicenseSnapshot): string {
  if (isPermanentLicense(license)) return LICENSE_PERMANENT_TEXT
  const expiryDate = license.license_expiry_date
  if (expiryDate === null || expiryDate === undefined || expiryDate === '') return ''
  const expiry = toDateOnly(expiryDate)
  return expiry === null ? '' : formatDateOnly(expiry)
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
  license: LicenseSnapshot & { license_authorized_users?: number | null | undefined },
  today: Date = new Date()
): LicenseSummary {
  const userText = `${license.license_authorized_users ?? '-'} 人`
  if (isPermanentLicense(license)) {
    return {
      primary: LICENSE_PERMANENT_TEXT,
      secondary: `${LICENSE_STATUS_LABELS.official} · ${userText}`,
      tone: 'normal'
    }
  }
  const expiryDate = license.license_expiry_date
  const expiry = expiryDate === null || expiryDate === undefined || expiryDate === ''
    ? null
    : toDateOnly(expiryDate)
  if (expiry === null) {
    return { primary: '未授权', secondary: '-', tone: 'none' }
  }

  const todayDate = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const days = Math.round((expiry.getTime() - todayDate.getTime()) / 86_400_000)
  const expiryText = formatDateOnly(expiry)
  if (days < 0) {
    return {
      primary: `已过期 ${-days} 天`,
      secondary: `${userText} · ${expiryText}`,
      tone: 'urgent'
    }
  }

  const statusText = licenseStatusLabel({ license_expiry_date: expiry, license_type: license.license_type }, today)
  return {
    primary: days < RENEWAL_WINDOW_DAYS ? `${days} 天后到期` : expiryText,
    secondary: `${statusText} · ${userText}`,
    tone: days < RENEWAL_WINDOW_DAYS ? 'soon' : 'normal'
  }
}
