import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const readView = (name: string): string => readFileSync(
  resolve(process.cwd(), `src/views/${name}.vue`),
  'utf8'
)

describe('payment DataTable pagination contracts', () => {
  it.each([
    ['Payments', 'fetchData'],
    ['PaymentPlans', 'fetchPaymentPlans'],
    ['PaymentRecords', 'fetchPaymentRecords']
  ])('%s updates page size, resets page, and fetches once', (viewName, fetchName) => {
    const source = readView(viewName)
    expect(source).toContain('@update:page-size="handlePageSizeChange"')
    expect(source).toMatch(new RegExp(
      `const handlePageSizeChange = \\(pageSize: number\\): void => \\{[\\s\\S]*?pagination\\.pageSize = pageSize[\\s\\S]*?pagination\\.current = 1[\\s\\S]*?${fetchName}\\(\\)`
    ))
  })

  it('Payments page changes fetch the selected page exactly through the handler', () => {
    const source = readView('Payments')
    expect(source).toContain('@update:page="handlePageChange"')
    expect(source).toMatch(/const handlePageChange = \(page: number\): void => \{[\s\S]*?pagination\.current = page[\s\S]*?fetchData\(\)/)
  })
})
