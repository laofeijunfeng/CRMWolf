import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(resolve(process.cwd(), 'src/views/ApprovalCenter.vue'), 'utf8')

describe('ApprovalCenter accessibility contract', () => {
  it('enables interactive table rows and uses a semantic copy button', () => {
    expect(source).toContain('row-interactive')
    expect(source).toMatch(/<Button[\s\S]{0,220}data-testid="copy-number"/)
    expect(source).toContain('复制审批单号')
    expect(source).toMatch(/<Copy[^>]*aria-hidden="true"/)
    expect(source).toContain('@click.stop="copyNumber(row.application_number)"')
  })

  it('keeps approval actions strictly single-instance', () => {
    expect(source).not.toContain(':selectable=')
    expect(source).not.toContain(':selected-row-keys=')
    expect(source).not.toContain(':get-row-selectable=')
    expect(source).not.toContain('批量')
    expect(source).not.toContain('selectedRowKeys')
    expect(source).not.toContain('bulkApprove')
    expect(source).toContain('data-testid="mobile-approve-btn"')
    expect(source).toContain('data-testid="mobile-reject-btn"')
  })
})
