import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const viewSources = {
  invoices: readFileSync(resolve(process.cwd(), 'src/views/Invoices.vue'), 'utf8'),
  approvals: readFileSync(resolve(process.cwd(), 'src/views/ApprovalCenter.vue'), 'utf8'),
}

describe('invoice and approval list export contract', () => {
  it('binds export dialog through permission and composable handler', () => {
    expect(viewSources.invoices).toContain(':export-enabled="canExportInvoices"')
    expect(viewSources.invoices).toContain('export-title="发票申请列表"')
    expect(viewSources.invoices).toContain(':export-handler="exportInvoiceFields"')
    expect(viewSources.invoices).toContain("permissionStore.hasPermission('invoice:export')")

    expect(viewSources.approvals).toContain(':export-enabled="canExportApprovals"')
    expect(viewSources.approvals).toContain('export-title="审批列表"')
    expect(viewSources.approvals).toContain(':export-handler="exportApprovalFields"')
    expect(viewSources.approvals).toContain("permissionStore.hasPermission('approval:export')")
  })

  it('exports the current view context including materialized custom-view filters', () => {
    const invoicesContext = viewSources.invoices.slice(
      viewSources.invoices.indexOf('const currentInvoiceListContext'),
      viewSources.invoices.indexOf('const { exportFields: exportInvoiceFields }'),
    )
    expect(invoicesContext).toContain('[...activeFilters.value]')
    expect(invoicesContext).toContain('[...activeSorts.value]')
    expect(invoicesContext).toContain("search.value.trim() || undefined")
    expect(invoicesContext).toContain("'pending' || activeTab.value === 'approved' || activeTab.value === 'invoiced'")

    const approvalsContext = viewSources.approvals.slice(
      viewSources.approvals.indexOf('const currentApprovalListContext'),
      viewSources.approvals.indexOf('const { exportFields: exportApprovalFields }'),
    )
    expect(approvalsContext).toContain('[...activeFilters.value]')
    expect(approvalsContext).toContain('[...activeSorts.value]')
    expect(approvalsContext).toContain("search.value.trim() || undefined")
    expect(approvalsContext).toContain('tab: activeTab.value')
  })

  it('sends exports through the dedicated API methods', () => {
    expect(viewSources.invoices).toContain('invoiceApi.exportInvoiceApplications(payload)')
    expect(viewSources.approvals).toContain('approvalGenericApi.exportApprovals(payload)')
  })
})
