import { defineConfig } from '@playwright/test'

/**
 * Sales-assistant e2e smoke.
 * Targets already-running dev servers (5173 front / 8000 back); reuseExistingServer
 * prevents Playwright from spawning duplicates.
 */
export default defineConfig({
  outputDir: './test-results/design',
  testDir: './tests/e2e',
  timeout: 240_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  use: {
    baseURL: 'http://localhost:5173',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'off',
    locale: 'zh-CN'
  },
  reporter: [['list']],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 60_000
  }
})
