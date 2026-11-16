import { describe, expect, it } from 'vitest'
import { defineListFields, projectListFieldCatalog } from '../listFieldCatalog'

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
      { key: 'collaborators', label: '协作者', type: 'text', column: { align: 'center', hideable: false, configurable: false } }
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
        },
        { key: 'collaborators', label: '协作者', type: 'text' }
      ],
      sortFields: [
        {
          key: 'owner_id',
          label: '负责人',
          type: 'enum',
          options: [{ value: 'u1', label: '张三' }]
        },
        { key: 'issued_time', label: '开票时间', type: 'date' },
        { key: 'collaborators', label: '协作者', type: 'text' }
      ],
      exportFields: [
        { fieldKey: 'owner', key: 'owner', label: '负责人', source: 'column' },
        { fieldKey: 'collaborators', key: 'collaborators', label: '协作者', source: 'column' }
      ]
    })
  })

  it('does not infer query capabilities for keyword, action, or decoration columns', () => {
    const projected = projectListFieldCatalog([
      { key: 'keyword', label: '关键字', type: 'text', role: 'keyword', column: true },
      { key: 'status_badge', label: '状态标记', role: 'decoration', column: true },
      { key: 'actions', label: '操作', role: 'action', column: true }
    ])

    expect(projected.columns.map((column) => column.key)).toEqual([
      'keyword',
      'status_badge',
      'actions'
    ])
    expect(projected.filterFields).toEqual([])
    expect(projected.sortFields).toEqual([])
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
        filterDisabledReason: 'owner options are not ready in this example',
        sort: { apiKey: 'owner_id' }
      }
    ])

    expect(projected.columns.map((column) => column.key)).toEqual(['owner'])
    expect(projected.filterFields).toEqual([])
    expect(projected.sortFields.map((field) => field.key)).toEqual(['owner_id'])
  })

  it('rejects duplicate catalog keys so later fields cannot silently fork the same source', () => {
    expect(() => projectListFieldCatalog([
      { key: 'owner', label: '负责人', type: 'text', column: true },
      { key: 'owner', label: '客户负责人', type: 'text', filter: { apiKey: 'owner_id' } }
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

  it('defaults business columns to filter and sort, and rejects a missing type', () => {
    expect(projectListFieldCatalog([
      { key: 'license_status', label: '授权状态', type: 'enum', column: { width: '100px' } }
    ])).toEqual({
      columns: [{ key: 'license_status', title: '授权状态', width: '100px' }],
      filterFields: [{ key: 'license_status', label: '授权状态', type: 'enum' }],
      sortFields: [{ key: 'license_status', label: '授权状态', type: 'enum' }],
      exportFields: [{ fieldKey: 'license_status', key: 'license_status', label: '授权状态', source: 'column' }]
    })

    expect(() => projectListFieldCatalog([
      { key: 'collaborators', label: '协作者', column: { width: '100px' } }
    ])).toThrow('List field "collaborators" enables filter/sort but has no type')
  })

  it('rejects a business column that disables filter or sort without a reason', () => {
    expect(() => defineListFields([
      { key: 'owner', label: '负责人', type: 'enum', column: true, filter: false }
    ])).toThrow('List field "owner" disables filter without filterDisabledReason')

    expect(() => projectListFieldCatalog([
      { key: 'created_time', label: '创建时间', type: 'date', column: true, sort: false }
    ])).toThrow('List field "created_time" disables sort without sortDisabledReason')
  })

  it('projects export fields with safe aliases and rejects unsafe explicit keys', () => {
    expect(projectListFieldCatalog([
      { key: 'public_id', label: '业务 ID', export: true },
      { key: 'name', label: '名称', type: 'text', column: true },
      { key: 'owner_id', label: '负责人', type: 'enum', column: true, export: { key: 'owner' } },
      { key: 'badge', label: '标记', role: 'decoration', column: true },
    ])).toMatchObject({
      exportFields: [
        { fieldKey: 'public_id', key: 'public_id', label: '业务 ID', source: 'export-only' },
        { fieldKey: 'name', key: 'name', label: '名称', source: 'column' },
        { fieldKey: 'owner_id', key: 'owner', label: '负责人', source: 'column' },
      ],
    })

    expect(projectListFieldCatalog([
      { key: 'keyword', label: '关键字', type: 'text', role: 'keyword', filter: true },
      { key: 'badge', label: '标记', role: 'decoration', column: true },
    ]).exportFields).toEqual([])

    expect(() => defineListFields([{ key: 'id', label: 'ID', export: true }]))
      .toThrow('List field export key "id" is unsafe')
    expect(() => defineListFields([{ key: 'owner_id', label: '负责人', type: 'enum', column: true, export: true }]))
      .toThrow('List field export key "owner_id" is unsafe')
    expect(() => defineListFields([
      { key: 'name', label: '名称', type: 'text', column: true },
      { key: 'alias', label: '别名', type: 'text', column: true, export: { key: 'name' } },
    ])).toThrow('Duplicate list export field key: name')
  })

  it('keeps keyword and action fields from inheriting business-column defaults', () => {
    const projected = projectListFieldCatalog([
      { key: 'keyword', label: '关键字', type: 'text', role: 'keyword', filter: true },
      { key: 'actions', label: '操作', role: 'action', column: { width: '80px' } }
    ])
    expect(projected.columns.map((column) => column.key)).toEqual(['actions'])
    expect(projected.filterFields.map((field) => field.key)).toEqual(['keyword'])
    expect(projected.sortFields).toEqual([])
  })
})
