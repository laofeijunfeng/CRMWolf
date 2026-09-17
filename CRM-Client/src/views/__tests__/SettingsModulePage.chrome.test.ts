import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('settings host chrome', () => {
  it.each([
    'src/views/SettingsModulePage.vue',
    'src/views/ProcurementStagesSettings.vue',
    'src/views/TeamSettings.vue',
  ])('stops %s from drawing a second page title', (relativePath) => {
    const source = readFileSync(resolve(process.cwd(), relativePath), 'utf8')
    expect(source).toContain('SettingsContent')
    expect(source).not.toContain('max-w-6xl')
    expect(source).not.toContain('text-2xl font-semibold tracking-tight')
    expect(source).not.toContain('系统设置 /')
  })
})
