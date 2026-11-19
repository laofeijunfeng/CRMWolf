import { describe, expect, it } from 'vitest'
import { cn } from '../utils'

describe('cn with control-size tokens', () => {
  it('lets caller overrides replace token size utilities', () => {
    expect(cn('size-control', 'size-7')).toBe('size-7')
    expect(cn('h-control px-control', 'h-auto px-3')).toBe('h-auto px-3')
    expect(cn('h-control-sm gap-control', 'h-8 gap-2')).toBe('h-8 gap-2')
  })

  it('lets later token utilities replace standard ones', () => {
    expect(cn('h-9 px-4', 'h-control-lg px-control-lg')).toBe('h-control-lg px-control-lg')
  })
})
