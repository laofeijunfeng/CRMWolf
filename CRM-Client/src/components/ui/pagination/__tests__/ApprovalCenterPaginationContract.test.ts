import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(
  resolve(process.cwd(), 'src/views/ApprovalCenter.vue'),
  'utf8'
)

describe('ApprovalCenter mobile pagination contract', () => {
  it('uses PaginationItem directly without nested Button/asChild composition', () => {
    expect(source).not.toMatch(/<PaginationItem[\s\S]{0,160}as-child/)
    expect(source).not.toMatch(/<PaginationItem[\s\S]{0,240}<Button/)
    expect(source).toContain('<PaginationItem')
    expect(source).toContain(':value="item"')
  })
})
