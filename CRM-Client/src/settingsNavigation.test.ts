import { describe, expect, it } from 'vitest'
import { getSettingsNavigationItem, SETTINGS_NAVIGATION } from './settingsNavigation'

describe('settings navigation registry', () => {
  it('keeps one canonical route per settings module', () => {
    const paths = SETTINGS_NAVIGATION.map(item => item.path)
    expect(new Set(paths).size).toBe(paths.length)
    expect(getSettingsNavigationItem('procurement')?.path).toBe('/settings/procurement-methods')
  })

  it('keeps account settings available without team permissions', () => {
    const account = getSettingsNavigationItem('account')
    expect(account?.scope).toBe('personal')
    expect(account?.requiredAnyPermissions).toEqual([])
  })
})
