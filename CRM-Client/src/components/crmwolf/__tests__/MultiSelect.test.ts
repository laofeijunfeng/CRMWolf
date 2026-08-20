import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const readComponent = (name: string): string => readFileSync(
  resolve(process.cwd(), `src/components/crmwolf/${name}.vue`),
  'utf8'
)

const multiSelectSource = readComponent('MultiSelect')
const filterPopoverSource = readComponent('ListFilterPopover')

describe('MultiSelect control sizing', () => {
  it('uses the shared input height tokens so filter value controls align with field and operator selects', () => {
    expect(multiSelectSource).toMatch(
      /\.wolf-multi-select-trigger\s*\{[^}]*height:\s*\$wolf-input-height-v2;/s
    )
    expect(multiSelectSource).toMatch(
      /@media\s*\(max-width:\s*767px\)\s*\{[\s\S]*?\.wolf-multi-select-trigger\s*\{[^}]*height:\s*\$wolf-input-height-mobile-v2;/s
    )
    expect(multiSelectSource).not.toContain('height: 32px')
    expect(filterPopoverSource).toMatch(
      /@media\s*\(max-width:\s*767px\)\s*\{[\s\S]*?\.filter-field-select,[\s\S]*?height:\s*\$wolf-input-height-mobile-v2;/s
    )
  })
})
