import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const viewSource = readFileSync(resolve(process.cwd(), 'src/views/CustomerTracking.vue'), 'utf8')

describe('customer tracking list export contract', () => {
  it('exposes the public_id export-only field before regular columns', () => {
    const registryStart = viewSource.indexOf('const fields: ListFieldDefinition[]')
    const firstField = viewSource.indexOf('key:', registryStart)
    const publicId = viewSource.indexOf("key: 'public_id'", registryStart)
    expect(registryStart).toBeGreaterThanOrEqual(0)
    expect(publicId).toBeGreaterThanOrEqual(0)
    expect(publicId).toBeGreaterThan(firstField - 6)
    expect(viewSource.slice(publicId - 30, publicId + 120)).toContain('export: true')
  })

  it('binds the export dialog through permission and composable handler', () => {
    expect(viewSource).toContain(':export-enabled="canExportFollowUpTasks"')
    expect(viewSource).toContain('export-title="客户追踪列表"')
    expect(viewSource).toContain(':export-handler="exportFollowUpTaskFields"')
    expect(viewSource).toContain("permissionStore.hasPermission('follow_up_task:export')")
  })

  it('exports the current view context including materialized custom-view filters', () => {
    const context = viewSource.slice(
      viewSource.indexOf('const currentFollowUpTaskListContext'),
      viewSource.indexOf('const { exportFields: exportFollowUpTaskFields }'),
    )
    expect(context).toContain('[...activeFilters.value]')
    expect(context).toContain('[...activeSorts.value]')
    expect(context).toContain('search.value.trim() || undefined')
    expect(context).toContain('taskStatusForTab(activeTab.value)')
  })

  it('sends exports through the dedicated API method', () => {
    expect(viewSource).toContain('followUpTaskApi.exportFollowUpTasks(payload)')
  })
})
