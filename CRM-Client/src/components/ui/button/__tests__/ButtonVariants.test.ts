import { describe, expect, it } from 'vitest'
import { buttonVariants } from '..'

describe('button radius contract', () => {
  it('uses the shared control radius token for standard buttons', () => {
    expect(buttonVariants()).toContain('rounded-wolf')
    expect(buttonVariants()).not.toContain('rounded-sm')
    expect(buttonVariants()).not.toContain('rounded-lg')
    expect(buttonVariants()).not.toContain('rounded-xl')
  })

  it('does not reintroduce size-specific button radius overrides', () => {
    expect(buttonVariants({ size: 'sm' })).not.toContain('rounded-md')
    expect(buttonVariants({ size: 'lg' })).not.toContain('rounded-md')
  })
})
