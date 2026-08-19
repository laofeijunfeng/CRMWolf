import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineListFields, projectListFieldCatalog } from '../listFieldCatalog'

const srcDir = resolve(process.cwd(), 'src')
const viewsDir = resolve(srcDir, 'views')
const dataTableSource = readFileSync(resolve(srcDir, 'components/crmwolf/DataTable.vue'), 'utf8')

function listVueFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const fullPath = resolve(dir, entry.name)
    if (entry.isDirectory()) return listVueFiles(fullPath)
    return entry.name.endsWith('.vue') ? [fullPath] : []
  })
}

describe('projectListFieldCatalog', () => {
  it('projects one catalog into columns, filters, and sorts without duplicating labels', () => {
    const fields = defineListFields([
      { key: 'keyword', label: '关键字', type: 'text', filter: true },
      {
        key: 'owner',
        label: '负责人',
        type: 'enum',
        options: [{ value: 'u1', label: '张三' }],
        column: { width: '100px' },
        filter: { apiKey: 'owner_id' },
        sort: { apiKey: 'owner_id' }
      },
      { key: 'issued_time', label: '开票时间', type: 'date', sort: true },
      { key: 'collaborators', label: '协作者', column: { align: 'center', hideable: false, configurable: false } }
    ])

    expect(projectListFieldCatalog(fields)).toEqual({
      columns: [
        { key: 'owner', title: '负责人', width: '100px' },
        { key: 'collaborators', title: '协作者', align: 'center', hideable: false, configurable: false }
      ],
      filterFields: [
        { key: 'keyword', label: '关键字', type: 'text' },
        {
          key: 'owner_id',
          label: '负责人',
          type: 'enum',
          options: [{ value: 'u1', label: '张三' }]
        }
      ],
      sortFields: [
        {
          key: 'owner_id',
          label: '负责人',
          type: 'enum',
          options: [{ value: 'u1', label: '张三' }]
        },
        { key: 'issued_time', label: '开票时间', type: 'date' }
      ]
    })
  })

  it('keeps filter-only and sort-only fields out of column configuration', () => {
    const projected = projectListFieldCatalog([
      { key: 'keyword', label: '关键字', type: 'text', filter: true },
      { key: 'account_name', label: '客户名称', type: 'text', column: true, filter: true, sort: true },
      { key: 'last_modified_time', label: '最后更新', type: 'date', sort: true }
    ])

    expect(projected.columns.map((column) => column.key)).toEqual(['account_name'])
    expect(projected.filterFields.map((field) => field.key)).toEqual(['keyword', 'account_name'])
    expect(projected.sortFields.map((field) => field.key)).toEqual(['account_name', 'last_modified_time'])
  })

  it('treats explicit false as a disabled capability', () => {
    const projected = projectListFieldCatalog([
      {
        key: 'owner',
        label: '负责人',
        type: 'enum',
        column: { width: '100px' },
        filter: false,
        sort: { apiKey: 'owner_id' }
      }
    ])

    expect(projected.columns.map((column) => column.key)).toEqual(['owner'])
    expect(projected.filterFields).toEqual([])
    expect(projected.sortFields.map((field) => field.key)).toEqual(['owner_id'])
  })

  it('rejects duplicate catalog keys so later fields cannot silently fork the same source', () => {
    expect(() => projectListFieldCatalog([
      { key: 'owner', label: '负责人', column: true },
      { key: 'owner', label: '客户负责人', filter: { apiKey: 'owner_id' } }
    ])).toThrow('Duplicate list field key: owner')
  })

  it('rejects filter or sort capabilities that omit the query control type', () => {
    expect(() => defineListFields([
      { key: 'created_time', label: '创建时间', filter: true }
    ])).toThrow('List field "created_time" enables filter/sort but has no type')

    expect(() => projectListFieldCatalog([
      { key: 'issued_time', label: '开票时间', sort: true }
    ])).toThrow('List field "issued_time" enables filter/sort but has no type')
  })

  it('allows column-only fields to omit type', () => {
    expect(projectListFieldCatalog([
      { key: 'collaborators', label: '协作者', column: { width: '100px' } }
    ]).columns.map((column) => column.key)).toEqual(['collaborators'])
  })
})

describe('DataTable list field catalog contract', () => {
  it('accepts only the catalog and no longer exposes dual field sources', () => {
    expect(dataTableSource).toContain('fields: ListFieldDefinition[]')
    expect(dataTableSource).toContain('projectListFieldCatalog(props.fields)')
    expect(dataTableSource).not.toContain('filterFields?: ListFilterField[]')
    expect(dataTableSource).not.toContain('sortFields?: ListSortField[]')
    expect(dataTableSource).not.toContain('columns: Column[]')
    expect(dataTableSource).not.toContain('filterable?:')
    expect(dataTableSource).not.toContain('sortable?:')
    expect(dataTableSource).not.toMatch(/if \(props\.filterFields/)
    expect(dataTableSource).not.toMatch(/if \(props\.sortFields/)
  })

  it('requires every DataTable consumer to feed one catalog', () => {
    const consumers = listVueFiles(srcDir).filter((filePath) => {
      if (filePath.endsWith('/components/crmwolf/DataTable.vue')) return false
      return readFileSync(filePath, 'utf8').includes('<DataTable')
    }).sort()

    expect(consumers.map((filePath) => filePath.slice(srcDir.length + 1))).toEqual([
      'views/ApprovalCenter.vue',
      'views/Contracts.vue',
      'views/CustomerTracking.vue',
      'views/Customers.vue',
      'views/Invoices.vue',
      'views/Leads.vue',
      'views/Opportunities.vue',
      'views/PaymentPlans.vue',
      'views/PaymentRecords.vue'
    ])

    for (const filePath of consumers) {
      const source = readFileSync(filePath, 'utf8')
      expect(source).toContain(':fields="fields"')
      expect(source).toContain('ListFieldDefinition')
      expect(source).not.toContain(':columns="')
      expect(source).not.toContain(':filter-fields')
      expect(source).not.toContain(':sort-fields')
      expect(source).not.toContain('buildSortFieldsFromFilterFields')
      expect(source).toContain(':get-row-actions="getRowActions"')
      expect(source).toContain('#mobile-actions')
      expect(source).not.toContain('#cell-actions')
      expect(source).not.toMatch(/key:\s*'actions'/)
    }
  })

  it('keeps ApprovalCenter approve/reject on mobile only', () => {
    const source = readFileSync(resolve(viewsDir, 'ApprovalCenter.vue'), 'utf8')
    const desktopActions = source.match(/const getRowActions[\s\S]*?return \{[\s\S]*?\n\}/)
    expect(desktopActions?.[0]).toBeDefined()
    expect(desktopActions?.[0]).not.toContain('通过')
    expect(desktopActions?.[0]).not.toContain('驳回')
    expect(source).toContain('data-testid="mobile-approve-btn"')
    expect(source).toContain('data-testid="mobile-reject-btn"')
  })

  it('puts public-sea claim into getRowActions instead of a desktop button', () => {
    for (const viewName of ['Customers.vue', 'Leads.vue']) {
      const source = readFileSync(resolve(viewsDir, viewName), 'utf8')
      expect(source).toContain("label: '领取'")
      expect(source).not.toMatch(/<Button[\s\S]{0,240}领取[\s\S]{0,80}<\/Button>/)
    }
  })

  it('does not leave a second catalog helper that rebuilds sort fields from filters', () => {
    const listSorts = readFileSync(resolve(process.cwd(), 'src/utils/listSorts.ts'), 'utf8')
    expect(listSorts).not.toContain('buildSortFieldsFromFilterFields')

    const leftover = listVueFiles(viewsDir)
      .filter((filePath) => readFileSync(filePath, 'utf8').includes('buildSortFieldsFromFilterFields'))
    expect(leftover).toEqual([])
  })
})
