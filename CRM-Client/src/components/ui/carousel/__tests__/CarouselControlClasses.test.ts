import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const readComponent = (name: string): string => readFileSync(
  resolve(process.cwd(), `src/components/ui/carousel/${name}.vue`),
  'utf8'
)

describe('carousel control positioning', () => {
  it('keeps the original horizontal and vertical center points with 44px controls', () => {
    const next = readComponent('CarouselNext')
    const previous = readComponent('CarouselPrevious')

    expect(next).toContain('size-11')
    expect(next).toContain('-right-[54px]')
    expect(next).toContain('-bottom-[54px]')
    expect(previous).toContain('size-11')
    expect(previous).toContain('-left-[54px]')
    expect(previous).toContain('-top-[54px]')
  })
})
