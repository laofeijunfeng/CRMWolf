import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const viewSources = {
  paymentPlans: readFileSync(resolve(process.cwd(), 'src/views/PaymentPlans.vue'), 'utf8'),
  paymentRecords: readFileSync(resolve(process.cwd(), 'src/views/PaymentRecords.vue'), 'utf8'),
}

describe('payment list export contract', () => {
  it('binds export dialog through permission and composable handler', () => {
    expect(viewSources.paymentPlans).toContain(':export-enabled="canExportPlans"')
    expect(viewSources.paymentPlans).toContain('export-title="回款计划列表"')
    expect(viewSources.paymentPlans).toContain(':export-handler="exportPaymentPlanFields"')
    expect(viewSources.paymentPlans).toContain("permissionStore.hasPermission('payment:plan:export')")

    expect(viewSources.paymentRecords).toContain(':export-enabled="canExportRecords"')
    expect(viewSources.paymentRecords).toContain('export-title="回款记录列表"')
    expect(viewSources.paymentRecords).toContain(':export-handler="exportPaymentRecordFields"')
    expect(viewSources.paymentRecords).toContain("permissionStore.hasPermission('payment:record:export')")
  })

  it('exports the current view context including materialized custom-view filters', () => {
    const plansContext = viewSources.paymentPlans.slice(
      viewSources.paymentPlans.indexOf('const currentPaymentPlanListContext'),
      viewSources.paymentPlans.indexOf('const { exportFields: exportPaymentPlanFields }'),
    )
    expect(plansContext).toContain('[...activeFilters.value]')
    expect(plansContext).toContain('[...activeSorts.value]')
    expect(plansContext).toContain("search.value.trim() || undefined")
    expect(plansContext).toContain("'pending' || activeTab.value === 'partial' || activeTab.value === 'completed'")

    const recordsContext = viewSources.paymentRecords.slice(
      viewSources.paymentRecords.indexOf('const currentPaymentRecordListContext'),
      viewSources.paymentRecords.indexOf('const { exportFields: exportPaymentRecordFields }'),
    )
    expect(recordsContext).toContain('[...activeFilters.value]')
    expect(recordsContext).toContain('[...activeSorts.value]')
    expect(recordsContext).toContain("search.value.trim() || undefined")
    expect(recordsContext).toContain("'pending_submit'")
    expect(recordsContext).toContain("'confirmed'")
  })

  it('sends exports through the dedicated API methods', () => {
    expect(viewSources.paymentPlans).toContain('paymentApi.exportPaymentPlans(payload)')
    expect(viewSources.paymentRecords).toContain('paymentApi.exportPaymentRecords(payload)')
  })
})
