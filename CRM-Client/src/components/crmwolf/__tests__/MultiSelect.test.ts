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
    expect(multiSelectSource).toContain('h-input-desktop')
    expect(multiSelectSource).toContain('min-h-input-desktop')
    expect(multiSelectSource).toContain('max-[767px]:h-input-mobile')
    expect(multiSelectSource).toContain('max-[767px]:min-h-input-mobile')
    expect(multiSelectSource).toContain('py-0')
    expect(multiSelectSource).toContain('!text-wolf-body')
    expect(filterPopoverSource).toMatch(
      /@media\s*\(max-width:\s*767px\)\s*\{[\s\S]*?\.filter-field-select,[\s\S]*?height:\s*\$wolf-input-height-mobile-v2;/s
    )
  })
})
