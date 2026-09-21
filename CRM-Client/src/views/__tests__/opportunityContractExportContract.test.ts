import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const viewSources = {
  opportunities: readFileSync(resolve(process.cwd(), 'src/views/Opportunities.vue'), 'utf8'),
  contracts: readFileSync(resolve(process.cwd(), 'src/views/Contracts.vue'), 'utf8'),
}

describe('opportunity and contract list export contract', () => {
  it('exposes opportunity public_id as an export-only field', () => {
    const source = viewSources.opportunities
    const registryStart = source.indexOf('const fields = computed<ListFieldDefinition[]>')
    const publicId = source.indexOf("key: 'public_id'", registryStart)
    expect(registryStart).toBeGreaterThanOrEqual(0)
    expect(publicId).toBeGreaterThanOrEqual(0)
    expect(source.slice(publicId, publicId + 120)).toContain('export: true')
  })

  it('aliases contract owner_id to export key owner', () => {
    const source = viewSources.contracts
    const ownerField = source.indexOf("key: 'owner_id'")
    expect(ownerField).toBeGreaterThanOrEqual(0)
    expect(source.slice(ownerField, ownerField + 400)).toContain("export: { key: 'owner', label: '负责人' }")
  })
  it('binds export dialog through permission and composable handler', () => {
    expect(viewSources.opportunities).toContain(':export-enabled="canExportOpportunities"')
    expect(viewSources.opportunities).toContain('export-title="商机列表"')
    expect(viewSources.opportunities).toContain(':export-handler="exportOpportunityFields"')
    expect(viewSources.opportunities).toContain("permissionStore.hasPermission('opportunity:export')")

    expect(viewSources.contracts).toContain(':export-enabled="canExportContracts"')
    expect(viewSources.contracts).toContain('export-title="合同列表"')
    expect(viewSources.contracts).toContain(':export-handler="exportContractFields"')
    expect(viewSources.contracts).toContain("permissionStore.hasPermission('contract:export')")
  })

  it('exports the current view context including materialized custom-view filters', () => {
    const opportunitiesContext = viewSources.opportunities.slice(
      viewSources.opportunities.indexOf('const currentOpportunityListContext'),
      viewSources.opportunities.indexOf('const { exportFields: exportOpportunityFields }'),
    )
    expect(opportunitiesContext).toContain('[...activeFilters.value]')
    expect(opportunitiesContext).toContain('[...activeSorts.value]')
    expect(opportunitiesContext).toContain("search.value.trim() || undefined")
    expect(opportunitiesContext).toContain("'active' || activeTab.value === 'won' || activeTab.value === 'lost'")

    const contractsContext = viewSources.contracts.slice(
      viewSources.contracts.indexOf('const currentContractListContext'),
      viewSources.contracts.indexOf('const { exportFields: exportContractFields }'),
    )
    expect(contractsContext).toContain('[...activeFilters.value]')
    expect(contractsContext).toContain('[...activeSorts.value]')
    expect(contractsContext).toContain("search.value.trim() || undefined")
    expect(contractsContext).toContain("'DRAFT' || activeTab.value === 'PENDING_REVIEW' || activeTab.value === 'SIGNED'")
  })

  it('sends exports through the dedicated API methods', () => {
    expect(viewSources.opportunities).toContain('opportunityApi.exportOpportunities(payload)')
    expect(viewSources.contracts).toContain('contractApi.exportContracts(payload)')
  })
})
