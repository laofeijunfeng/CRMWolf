import { test as base } from '@playwright/test'
import { readFileSync } from 'node:fs'

/**
 * Authenticated fixture: injects the dev token before app load.
 * Token is minted out-of-band (verification-code login on dev).
 */
export const test = base.extend({
  // eslint-disable-next-line no-empty-pattern
  page: async ({ page }, use) => {
    const token = readFileSync('/tmp/e2e_token.txt', 'utf-8').trim()
    await page.addInitScript((t) => {
      window.localStorage.setItem('token', t)
    }, token)
    await use(page)
  }
})

export { expect } from '@playwright/test'
