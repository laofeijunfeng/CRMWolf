import type { CustomerUpdate } from '@/api/customer'

export interface CustomerEditableSnapshot {
  account_name: string | null
  city: string | null
  address: string | null
  company_scale: string | null
  source_public_id: string | null
  default_procurement_method_id: number | null
  industry: string | null
  status: 0 | 1 | null
  license_type: 'TRIAL' | 'OFFICIAL' | null
  license_expiry_date: string | null
}

type CustomerDiffField =
  | 'account_name'
  | 'city'
  | 'address'
  | 'company_scale'
  | 'source_public_id'
  | 'default_procurement_method_id'
  | 'industry'
  | 'status'
  | 'license'

const customerDiffFields: readonly CustomerDiffField[] = [
  'account_name',
  'city',
  'address',
  'company_scale',
  'source_public_id',
  'default_procurement_method_id',
  'industry',
  'status',
  'license',
]

function normalizeText(value: string | null): string | null {
  const normalized = value?.trim() ?? ''
  return normalized === '' ? null : normalized
}

function normalizeDate(value: string | null): string | null {
  return normalizeText(value)
}

function normalizeProcurementId(value: number | null): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function normalizeLicense(snapshot: CustomerEditableSnapshot): {
  license_type: 'TRIAL' | 'OFFICIAL' | null
  license_expiry_date: string | null
} {
  const normalizedExpiry = normalizeDate(snapshot.license_expiry_date)
  const normalizedType = normalizedExpiry === null ? null : snapshot.license_type
  return {
    license_type: normalizedType,
    license_expiry_date: normalizedExpiry,
  }
}

export function buildCustomerUpdatePayload(
  current: CustomerEditableSnapshot,
  baseline: CustomerEditableSnapshot,
  expectedVersion: number,
): (CustomerUpdate & { expected_version: number }) | null {
  const payload: CustomerUpdate & { expected_version: number } = {
    expected_version: expectedVersion,
  }
  let hasChanges = false

  for (const key of customerDiffFields) {
    switch (key) {
      case 'account_name': {
        const currentValue = normalizeText(current.account_name)
        const baselineValue = normalizeText(baseline.account_name)
        if (currentValue !== baselineValue) {
          payload.account_name = currentValue
          hasChanges = true
        }
        break
      }
      case 'city': {
        const currentValue = normalizeText(current.city)
        const baselineValue = normalizeText(baseline.city)
        if (currentValue !== baselineValue) {
          payload.city = currentValue
          hasChanges = true
        }
        break
      }
      case 'address': {
        const currentValue = normalizeText(current.address)
        const baselineValue = normalizeText(baseline.address)
        if (currentValue !== baselineValue) {
          payload.address = currentValue
          hasChanges = true
        }
        break
      }
      case 'company_scale': {
        const currentValue = normalizeText(current.company_scale)
        const baselineValue = normalizeText(baseline.company_scale)
        if (currentValue !== baselineValue) {
          payload.company_scale = currentValue
          hasChanges = true
        }
        break
      }
      case 'source_public_id': {
        const currentValue = normalizeText(current.source_public_id)
        const baselineValue = normalizeText(baseline.source_public_id)
        if (currentValue !== baselineValue) {
          payload.source_public_id = currentValue
          hasChanges = true
        }
        break
      }
      case 'default_procurement_method_id': {
        const currentValue = normalizeProcurementId(current.default_procurement_method_id)
        const baselineValue = normalizeProcurementId(baseline.default_procurement_method_id)
        if (currentValue !== baselineValue) {
          payload.default_procurement_method_id = currentValue
          hasChanges = true
        }
        break
      }
      case 'industry': {
        const currentValue = normalizeText(current.industry)
        const baselineValue = normalizeText(baseline.industry)
        if (currentValue !== baselineValue) {
          payload.industry = currentValue
          hasChanges = true
        }
        break
      }
      case 'status': {
        const currentValue = current.status === 0 || current.status === 1 ? current.status : null
        const baselineValue = baseline.status === 0 || baseline.status === 1 ? baseline.status : null
        if (currentValue !== baselineValue && currentValue !== null) {
          payload.status = currentValue
          hasChanges = true
        }
        break
      }
      case 'license': {
        const currentLicense = normalizeLicense(current)
        const baselineLicense = normalizeLicense(baseline)
        if (
          currentLicense.license_type !== baselineLicense.license_type
          || currentLicense.license_expiry_date !== baselineLicense.license_expiry_date
        ) {
          payload.license_type = currentLicense.license_type
          payload.license_expiry_date = currentLicense.license_expiry_date
          hasChanges = true
        }
        break
      }
    }
  }

  return hasChanges ? payload : null
}
