import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const viewSources = {
  customers: readFileSync(resolve(process.cwd(), 'src/views/Customers.vue'), 'utf8'),
  leads: readFileSync(resolve(process.cwd(), 'src/views/Leads.vue'), 'utf8'),
}

describe('customer and lead list export contract', () => {
  it('exposes the public_id export-only field before regular columns', () => {
    for (const source of [viewSources.customers, viewSources.leads]) {
      const registryStart = source.indexOf('const fields = computed<ListFieldDefinition[]>')
      const firstField = source.indexOf('key:', registryStart)
      const publicId = source.indexOf("key: 'public_id'", registryStart)
      expect(registryStart).toBeGreaterThanOrEqual(0)
      expect(publicId).toBeGreaterThanOrEqual(0)
      expect(publicId).toBeGreaterThan(firstField - 6)
      expect(source.slice(publicId - 30, publicId + 120)).toContain('export: true')
    }
  })

  it('binds the export dialog through permission and composable handler', () => {
    expect(viewSources.customers).toContain(':export-enabled="canExportCustomers"')
    expect(viewSources.customers).toContain('export-title="客户列表"')
    expect(viewSources.customers).toContain(':export-handler="exportCustomerFields"')
    expect(viewSources.customers).toContain("permissionStore.hasPermission('customer:export')")

    expect(viewSources.leads).toContain(':export-enabled="canExportLeads"')
    expect(viewSources.leads).toContain('export-title="线索列表"')
    expect(viewSources.leads).toContain(':export-handler="exportLeadFields"')
    expect(viewSources.leads).toContain("permissionStore.hasPermission('lead:export')")
  })

  it('exports the current view context including materialized custom-view filters', () => {
    const customersContext = viewSources.customers.slice(
      viewSources.customers.indexOf('const currentCustomerListContext'),
      viewSources.customers.indexOf('const { exportFields: exportCustomerFields }'),
    )
    expect(customersContext).toContain('[...activeFilters.value]')
    expect(customersContext).toContain('[...activeSorts.value]')
    expect(customersContext).toContain("search.value.trim() || undefined")
    expect(customersContext).toContain("activeTab.value === 'public' || activeTab.value === 'collaborated' ? activeTab.value : 'all'")

    const leadsContext = viewSources.leads.slice(
      viewSources.leads.indexOf('const currentLeadListContext'),
      viewSources.leads.indexOf('const { exportFields: exportLeadFields }'),
    )
    expect(leadsContext).toContain('[...activeFilters.value]')
    expect(leadsContext).toContain('[...activeSorts.value]')
    expect(leadsContext).toContain("search.value.trim() || undefined")
    expect(leadsContext).toContain("'public' ? 'public' : 'all'")
  })

  it('sends exports through the dedicated API methods', () => {
    expect(viewSources.customers).toContain('customerApi.exportCustomers(payload)')
    expect(viewSources.leads).toContain('leadApi.exportLeads(payload)')
  })
})
