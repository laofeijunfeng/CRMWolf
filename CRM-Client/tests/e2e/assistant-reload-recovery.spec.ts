import { expect } from '@playwright/test'
import { test } from './fixtures'

/**
 * E2E smoke 2: refresh recovery — an in-flight task survives a full page
 * reload; history replays and the current waiting card stays actionable.
 */
test('reload restores the in-flight task with its waiting card', async ({ page }) => {
  await page.goto('/assistant')

  // Create a task via the UI and cancel it is terminal; instead start a real
  // turn then reload mid-processing — server continues, task stays ACTIVE.
  const textarea = page.locator('textarea').first()
  await expect(textarea).toBeVisible()
  await textarea.fill('明天下午和广州睿狐科技有限公司复盘部署计划')
  await textarea.press('Enter')

  // Wait for the turn to reach any stable waiting (field question likely).
  await expect(page.getByText(/还差|属于哪种活动|确认后写入/).first()).toBeVisible({ timeout: 150_000 })

  await page.reload()
  await expect(page.locator('textarea').first()).toBeVisible({ timeout: 30_000 })

  // The continuous transcript restores without requiring a task sidebar.
  await expect(page.getByText('明天下午和广州睿狐科技有限公司复盘部署计划', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '新任务', exact: true })).toHaveCount(0)

  // Cancel it from the restored UI to leave a clean state.
  const giveUp = page.getByRole('button', { name: /算了/ })
  await expect(giveUp.first()).toBeVisible({ timeout: 30_000 })
  await giveUp.first().click()
  await expect(page.getByText('当前这件已停下，之前的对话和已写入的记录仍保留。').first()).toBeVisible({ timeout: 30_000 })
})
