/**
 * Authentication recovery state shared by the HTTP boundary and auth routes.
 *
 * The value is deliberately limited to an internal path.  It is not a general
 * redirect URL and must never be used to navigate to another origin.
 */
export const AUTH_RETURN_PATH_KEY = 'crmwolf.auth.return-path'
export const OAUTH_RETURN_PATH_KEY = 'crmwolf.oauth.return-path'

const AUTHENTICATION_PATH_PREFIXES = ['/login', '/signup', '/invite', '/auth/']

const firstString = (value: unknown): string => {
  if (typeof value === 'string') return value
  if (Array.isArray(value) && typeof value[0] === 'string') return value[0]
  return ''
}

export const getSafeAuthReturnPath = (value: unknown): string | null => {
  const candidate = firstString(value).trim()
  if (candidate === '' || !candidate.startsWith('/') || candidate.startsWith('//')) return null
  if (AUTHENTICATION_PATH_PREFIXES.some(prefix => candidate === prefix || candidate.startsWith(`${prefix}/`) || candidate.startsWith(`${prefix}?`))) {
    return null
  }

  try {
    const parsed = new URL(candidate, window.location.origin)
    if (parsed.origin !== window.location.origin) return null
    return `${parsed.pathname}${parsed.search}${parsed.hash}`
  } catch {
    return null
  }
}

export const getCurrentAuthReturnPath = (): string | null => {
  if (typeof window === 'undefined') return null
  return getSafeAuthReturnPath(`${window.location.pathname}${window.location.search}${window.location.hash}`)
}

export const rememberAuthReturnPath = (path?: unknown): string | null => {
  const safePath = getSafeAuthReturnPath(path ?? getCurrentAuthReturnPath())
  if (safePath === null) return null

  try {
    sessionStorage.setItem(AUTH_RETURN_PATH_KEY, safePath)
  } catch {
    // Storage can be unavailable in private browsing or restricted webviews.
  }
  return safePath
}

export const consumeAuthReturnPath = (explicitPath?: unknown): string | null => {
  const explicit = getSafeAuthReturnPath(explicitPath)
  if (explicit !== null) {
    try {
      sessionStorage.removeItem(AUTH_RETURN_PATH_KEY)
    } catch {
      // Ignore unavailable storage.
    }
    return explicit
  }

  let stored: string | null = null
  try {
    stored = sessionStorage.getItem(AUTH_RETURN_PATH_KEY)
    sessionStorage.removeItem(AUTH_RETURN_PATH_KEY)
  } catch {
    return null
  }
  return getSafeAuthReturnPath(stored)
}

export const createAuthReturnQuery = (path: string | null): Record<string, string> => {
  return path === null ? {} : { redirect: path }
}


/**
 * OAuth providers leave the SPA and later return to a fresh callback route.
 * Keep this return path separate from 401 recovery so the two flows cannot
 * consume or overwrite each other's navigation context.
 */
export const rememberOAuthReturnPath = (path?: unknown): string | null => {
  const safePath = getSafeAuthReturnPath(path ?? getCurrentAuthReturnPath())
  if (safePath === null) return null

  try {
    sessionStorage.setItem(OAUTH_RETURN_PATH_KEY, safePath)
  } catch {
    // Storage can be unavailable in private browsing or restricted webviews.
  }
  return safePath
}

export const consumeOAuthReturnPath = (explicitPath?: unknown): string | null => {
  const explicit = getSafeAuthReturnPath(explicitPath)
  if (explicit !== null) {
    try {
      sessionStorage.removeItem(OAUTH_RETURN_PATH_KEY)
    } catch {
      // Ignore unavailable storage.
    }
    return explicit
  }

  let stored: string | null = null
  try {
    stored = sessionStorage.getItem(OAUTH_RETURN_PATH_KEY)
    sessionStorage.removeItem(OAUTH_RETURN_PATH_KEY)
  } catch {
    return null
  }
  return getSafeAuthReturnPath(stored)
}
