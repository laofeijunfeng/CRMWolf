import { describe, expect, it } from 'vitest'
import { cn } from '../utils'

describe('cn', () => {
  it('lets wolf overlay radius replace the control radius', () => {
    expect(cn('rounded-md shadow-wolf-hover', 'rounded-wolf-overlay shadow-wolf-overlay'))
      .toBe('rounded-wolf-overlay shadow-wolf-overlay')
  })

  it('lets the tooltip surface replace overlay defaults', () => {
    expect(cn('rounded-wolf-overlay shadow-wolf-overlay', 'rounded-md shadow-wolf-hover'))
      .toBe('rounded-md shadow-wolf-hover')
  })
})
