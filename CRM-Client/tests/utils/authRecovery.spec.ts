import { beforeEach, describe, expect, it } from 'vitest'
import {
  AUTH_RETURN_PATH_KEY,
  OAUTH_RETURN_PATH_KEY,
  consumeOAuthReturnPath,
  consumeAuthReturnPath,
  getSafeAuthReturnPath,
  rememberAuthReturnPath,
  rememberOAuthReturnPath,
} from '@/utils/authRecovery'

describe('auth recovery route state', () => {
  beforeEach(() => {
    sessionStorage.clear()
    window.history.replaceState({}, '', '/customers?page=2&customerId=42')
  })

  it('persists and consumes the current internal route including query and hash', () => {
    const remembered = rememberAuthReturnPath()

    expect(remembered).toBe('/customers?page=2&customerId=42')
    expect(sessionStorage.getItem(AUTH_RETURN_PATH_KEY)).toBe('/customers?page=2&customerId=42')
    expect(consumeAuthReturnPath()).toBe('/customers?page=2&customerId=42')
    expect(sessionStorage.getItem(AUTH_RETURN_PATH_KEY)).toBeNull()
  })

  it('keeps OAuth callback recovery isolated from normal auth recovery', () => {
    const remembered = rememberOAuthReturnPath('/settings/account?tab=security')

    expect(remembered).toBe('/settings/account?tab=security')
    expect(sessionStorage.getItem(OAUTH_RETURN_PATH_KEY)).toBe('/settings/account?tab=security')
    expect(sessionStorage.getItem(AUTH_RETURN_PATH_KEY)).toBeNull()
    expect(consumeOAuthReturnPath()).toBe('/settings/account?tab=security')
    expect(sessionStorage.getItem(OAUTH_RETURN_PATH_KEY)).toBeNull()
  })

  it('rejects external or authentication routes', () => {
    expect(getSafeAuthReturnPath('https://evil.example.com')).toBeNull()
    expect(getSafeAuthReturnPath('//evil.example.com/path')).toBeNull()
    expect(getSafeAuthReturnPath('/login')).toBeNull()
    expect(getSafeAuthReturnPath('/customers?filters=%5B%5D')).toBe('/customers?filters=%5B%5D')
  })
})
