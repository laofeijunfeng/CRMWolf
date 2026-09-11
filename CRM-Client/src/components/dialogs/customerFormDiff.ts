import type { CustomerUpdate } from '@/api/customer'

type CustomerEditableField =
  | 'account_name'
  | 'city'
  | 'address'
  | 'company_scale'
  | 'source_public_id'
  | 'default_procurement_method_id'
  | 'industry'

const customerEditableFields: readonly CustomerEditableField[] = [
  'account_name',
  'city',
  'address',
  'company_scale',
  'source_public_id',
  'default_procurement_method_id',
  'industry',
]

function normalizeText(value: string | null | undefined): string | null {
  const normalized = value?.trim() ?? ''
  return normalized === '' ? null : normalized
}

export function buildCustomerUpdatePayload(
  current: CustomerUpdate,
  baseline: CustomerUpdate,
  expectedVersion: number,
): (CustomerUpdate & { expected_version: number }) | null {
  const payload: CustomerUpdate & { expected_version: number } = { expected_version: expectedVersion }
  let hasChanges = false

  for (const key of customerEditableFields) {
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
        const currentValue = current.default_procurement_method_id ?? null
        const baselineValue = baseline.default_procurement_method_id ?? null
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
    }
  }

  return hasChanges ? payload : null
}
