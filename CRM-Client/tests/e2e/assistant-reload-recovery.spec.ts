import { expect } from '@playwright/test'
import { test } from './fixtures'

/**
 * E2E smoke 2: refresh recovery — an in-flight task survives a full page
 * reload; history replays and the current waiting card stays actionable.
 */
test('reload restores the in-flight task with its waiting card', async ({ page }) => {
  const note = '2026年11月10日和广州睿狐科技有限公司沟通了私有化部署计划，对方认可分两期上线'
  const stopped = '已停下这件事'
  // The composer cancel button only renders while a non-terminal task is active.
  const giveUp = page.getByRole('button', { name: '算了', exact: true })
  const noteEcho = page.getByText(note, { exact: true })
  const waiting = page.getByText(/还差|属于哪种活动|确认后写入/)
  const stoppedNotice = page.getByText(stopped, { exact: true })
  const restoring = page.getByRole('status').filter({ hasText: '正在恢复对话' })

  await page.goto('/assistant')
  const textarea = page.locator('textarea').first()
  await expect(textarea).toBeVisible()
  await expect(restoring).toHaveCount(0, { timeout: 60_000 })

  // The shared account keeps its transcript: release any leftover active task
  // (no CRM write) and measure every assertion against this baseline.
  if (await giveUp.count() > 0) {
    const before = await stoppedNotice.count()
    await expect(giveUp).toBeEnabled({ timeout: 180_000 })
    await giveUp.click()
    await expect.poll(() => stoppedNotice.count(), { timeout: 30_000 }).toBeGreaterThan(before)
  }
  await expect(giveUp).toHaveCount(0)
  const baseWaiting = await waiting.count()

  await textarea.fill(note)
  await textarea.press('Enter')

  // Only a waiting card produced by this turn counts; a model failure fails the test.
  await expect.poll(() => waiting.count(), { timeout: 180_000 }).toBeGreaterThan(baseWaiting)
  await expect(giveUp).toBeEnabled({ timeout: 30_000 })

  await page.reload()
  await expect(page.locator('textarea').first()).toBeVisible({ timeout: 30_000 })
  await expect(restoring).toHaveCount(0, { timeout: 60_000 })

  // The transcript is paginated, so counts are not comparable across a reload.
  // The active task (absent at baseline) must come back, and the latest waiting
  // card must follow the latest echo of this note.
  await expect(giveUp).toBeEnabled({ timeout: 30_000 })
  await expect(noteEcho.last()).toBeVisible({ timeout: 30_000 })
  await expect(waiting.last()).toBeVisible({ timeout: 30_000 })
  const latestEcho = await noteEcho.last().elementHandle()
  expect(
    await waiting.last().evaluate(
      (card, echo) => Boolean(echo && echo.compareDocumentPosition(card) & Node.DOCUMENT_POSITION_FOLLOWING),
      latestEcho
    )
  ).toBe(true)
  await expect(page.getByRole('button', { name: '新任务', exact: true })).toHaveCount(0)

  // The restored waiting card stays actionable; cancelling writes no CRM activity.
  const stoppedAfterReload = await stoppedNotice.count()
  await giveUp.click()
  await expect.poll(() => stoppedNotice.count(), { timeout: 30_000 }).toBe(stoppedAfterReload + 1)
  await expect(giveUp).toHaveCount(0)
})
