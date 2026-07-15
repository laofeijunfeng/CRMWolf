import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const readSource = (relativePath: string): string => {
  return readFileSync(resolve(process.cwd(), relativePath), 'utf-8')
}

describe('PaymentPlans V2 migration contract', () => {
  it('uses ListCard and shadcn-vue primitives without Element Plus imports or tags', () => {
    const source = readSource('src/components/PaymentPlans.vue')

    expect(source).toContain("@/components/crmwolf/ListCard.vue")
    expect(source).toContain("@/components/ui/button")
    expect(source).toContain("@/components/ui/dialog")
    expect(source).toContain("@/styles/variables-v2.scss")
    expect(source).not.toContain('element-plus')
    expect(source).not.toContain('@element-plus/icons-vue')
    expect(source).not.toMatch(/<\/?el-/)
    expect(source).not.toContain("@/styles/variables.scss")
  })

  it('keeps payment-plan dialogs outside the ListCard content shell', () => {
    const source = readSource('src/components/PaymentPlans.vue')
    const listCardStart = source.indexOf('<ListCard')
    const listCardEnd = source.indexOf('</ListCard>')
    const firstDialog = source.indexOf('<Dialog')

    expect(listCardStart).toBeGreaterThan(-1)
    expect(listCardEnd).toBeGreaterThan(listCardStart)
    expect(firstDialog).toBeGreaterThan(listCardEnd)
  })

  it('keeps payment dialog controls and menu items at accessible touch target sizes', () => {
    const source = readSource('src/components/PaymentPlans.vue')

    expect(source).toMatch(/<DropdownMenuItem[^>]*class="min-h-11"/)
    expect(source).toContain('class="h-11"')
    expect(source).toContain('class="min-h-20"')
    expect(source).toContain('text-wolf-danger-text')
    expect(source).not.toContain('text-wolf-danger-text-v2')
  })
})
