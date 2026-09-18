import { describe, expect, it } from 'vitest'
import { defineListFields, projectListFieldCatalog } from '@/components/crmwolf/listFieldCatalog'
import { SETTINGS_LIST_QUERY_DISABLED_REASON, settingsListColumn } from '../settingsListCatalog'

describe('settingsListColumn', () => {
  it('defines a business column that DataTable will not treat as filterable or sortable', () => {
    const fields = defineListFields([
      settingsListColumn({ key: 'name', label: '名称', column: true }),
    ])
    const projected = projectListFieldCatalog(fields)
    expect(projected.columns.map((column) => column.key)).toEqual(['name'])
    expect(projected.filterFields).toEqual([])
    expect(projected.sortFields).toEqual([])
    expect(fields[0]?.filterDisabledReason).toBe(SETTINGS_LIST_QUERY_DISABLED_REASON)
    expect(fields[0]?.sortDisabledReason).toBe(SETTINGS_LIST_QUERY_DISABLED_REASON)
  })
})
