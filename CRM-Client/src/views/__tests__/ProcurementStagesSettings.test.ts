import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(resolve(process.cwd(), 'src/views/ProcurementStagesSettings.vue'), 'utf8')

describe('ProcurementStagesSettings', () => {
  it('renders stages in a DataTable instead of ListCard', () => {
    expect(source).toContain('<DataTable')
    expect(source).toContain(':get-row-actions="getRowActions"')
    expect(source).toContain('#mobile-actions')
    expect(source).not.toContain('ListCard')
  })

  it('defines settings list columns for stage fields', () => {
    expect(source).toContain("key: 'stage_name', label: '阶段'")
    expect(source).toContain("key: 'template_code', label: '编码'")
    expect(source).toContain("key: 'win_probability', label: '赢率'")
    expect(source).toContain("key: 'sort_order', label: '排序'")
    expect(source).toContain("key: 'is_default_start', label: '默认起点'")
    expect(source).toContain("key: 'can_skip', label: '可跳过'")
    expect(source).toContain('settingsListColumn')
    expect(source).toContain('ListFieldDefinition')
    expect(source).toContain(':fields="fields"')
  })
})
