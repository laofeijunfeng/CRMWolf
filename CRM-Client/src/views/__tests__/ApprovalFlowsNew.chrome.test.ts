import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('ApprovalFlowsNew chrome', () => {
  it('does not draw a second approval-flows heading', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/views/ApprovalFlowsNew.vue'), 'utf8')
    expect(source).toContain('SettingsContent')
    expect(source).toContain('useTopBarRegistration')
    expect(source).not.toContain('text-2xl font-semibold tracking-tight')
  })
})
