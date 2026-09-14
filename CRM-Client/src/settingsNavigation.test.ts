import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { getSettingsNavigationItem, SETTINGS_NAVIGATION } from './settingsNavigation'

const readSettingsModulePageSource = (): string => readFileSync(
  resolve(process.cwd(), 'src/views/SettingsModulePage.vue'),
  'utf8',
)

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

  it('allows automation permissions to enter the new approval workflow page', () => {
    const item = getSettingsNavigationItem('approval-flows-new')

    expect(item?.requiredAnyPermissions).toEqual(expect.arrayContaining([
      'automation:read',
      'automation:create',
      'automation:edit',
    ]))
  })
  it('registers canonical products entry with explicit permission and no owner bypass', () => {
    const item = getSettingsNavigationItem('products')
    expect(item).toMatchObject({
      path: '/settings/products',
      requiredAnyPermissions: ['product:view'],
      scope: 'team',
      requiresTeam: true,
      allowOwnerBypass: false,
    })
  })

  it('keeps separate AI and products legacy component mappings', () => {
    const source = readSettingsModulePageSource()

    expect(source).toContain("ai: defineAsyncComponent(() => import('@/components/system-config/AIConfigSheet.vue'))")
    expect(source).toContain("products: defineAsyncComponent(() => import('@/components/system-config/ProductPanel.vue'))")
  })
})
