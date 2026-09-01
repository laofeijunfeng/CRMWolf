import { describe, expect, it } from 'vitest'
import { isTeamOwner } from '../useSettingsAccess'

describe('useSettingsAccess', () => {
  it('compares owner identifiers without depending on response primitive types', () => {
    expect(isTeamOwner(12, '12')).toBe(true)
    expect(isTeamOwner('12', 13)).toBe(false)
  })

  it('does not treat missing team or user context as owner', () => {
    expect(isTeamOwner(undefined, '12')).toBe(false)
    expect(isTeamOwner(12, null)).toBe(false)
  })
})
