import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(
  resolve(process.cwd(), 'src/views/ApprovalCenter.vue'),
  'utf8'
)
const dataTableSource = readFileSync(
  resolve(process.cwd(), 'src/components/crmwolf/DataTable.vue'),
  'utf8'
)

describe('ApprovalCenter mobile pagination contract', () => {
  it('reuses DataTable pagination instead of owning a separate mobile paginator', () => {
    expect(source).toContain('<DataTable')
    expect(source).toContain('mobile-mode="card"')
    expect(source).not.toContain('<PaginationItem')
    expect(source).not.toMatch(/<PaginationItem[\s\S]{0,160}as-child/)
    expect(source).not.toMatch(/<PaginationItem[\s\S]{0,240}<Button/)

    expect(dataTableSource).toContain('<PaginationItem')
    expect(dataTableSource).toContain(':value="entry.value"')
    expect(dataTableSource).not.toMatch(/<PaginationItem[\s\S]{0,160}as-child/)
    expect(dataTableSource).not.toMatch(/<PaginationItem[\s\S]{0,240}<Button/)
  })
})
