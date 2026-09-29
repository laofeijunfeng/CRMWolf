import { expect, type Locator, type Page } from '@playwright/test'
import { test } from './fixtures'

const CUSTOMER = '广州睿狐科技有限公司'
const CONTENT =
  '客户方王总确认POC部署可行预算下季度；李经理要求先交安全测评报告；我方张工承诺周五前交数据出境说明；下周三王总反馈批复'
const NEXT_ACTION = '下周三王总反馈立项批复结果'

import { readFileSync } from 'node:fs'

const TOKEN = readFileSync('/tmp/e2e_token.txt', 'utf-8').trim()
async function submitCount(page: Page): Promise<number> {
  try {
    const latest = await page.request.get(
      'http://localhost:8000/api/v1/assistant/tasks/latest/active',
      { headers: TOKEN_HEADER, timeout: 15_000 }
    )
    if (latest.status() !== 200) return -1
    const body = (await latest.json()) as { public_id: string } | null
    if (body === null || body === undefined) return -1
    const acts = await page.request.get(
      `http://localhost:8000/api/v1/assistant/tasks/${body.public_id}/actions`,
      { headers: TOKEN_HEADER, timeout: 15_000 }
    )
    const list = (await acts.json()) as Array<{ action: string }>
    return list.filter((a) => a.action === 'submit_field').length
  } catch {
    return -1
  }
}

async function confirmCount(page: Page): Promise<number> {
  try {
    const latest = await page.request.get(
      'http://localhost:8000/api/v1/assistant/tasks/latest/active',
      { headers: TOKEN_HEADER, timeout: 15_000 }
    )
    if (latest.status() !== 200) return -1
    const body = (await latest.json()) as { public_id: string } | null
    if (body === null || body === undefined) return -1
    const acts = await page.request.get(
      `http://localhost:8000/api/v1/assistant/tasks/${body.public_id}/actions`,
      { headers: TOKEN_HEADER, timeout: 15_000 }
    )
    const list = (await acts.json()) as Array<{ action: string }>
    return list.filter((a) => a.action === 'confirm_write').length
  } catch {
    return -1
  }
}

const TOKEN_HEADER = { Authorization: `Bearer ${TOKEN}` }

interface Waiting {
  type: 'FIELD' | 'CONFIRMATION' | 'ACTIVITY_KIND' | null
  field?: string | null
}

const stateCache: { at: number; value: { status: string; waiting: Waiting } } = {
  at: 0,
  value: { status: 'UNKNOWN', waiting: { type: null } }
}

async function taskState(page: Page): Promise<{ status: string; waiting: Waiting }> {
  // Poll at most every 1.5s; transient connection resets fall back to cache
  // instead of failing the test.
  const now = Date.now()
  if (now - stateCache.at < 1_500 && stateCache.value.status !== 'UNKNOWN') {
    return stateCache.value
  }
  try {
    const resp = await page.request.get('http://localhost:8000/api/v1/assistant/tasks/latest/active', {
      headers: TOKEN_HEADER,
      timeout: 15_000
    })
    if (resp.status() === 204) {
      stateCache.at = now
      stateCache.value = { status: 'NONE', waiting: { type: null } }
      return stateCache.value
    }
    const body = (await resp.json()) as { status: string; waiting: Waiting | null } | null
    if (body === null || body === undefined) {
      stateCache.at = now
      stateCache.value = { status: 'NONE', waiting: { type: null } }
      return stateCache.value
    }
    stateCache.at = now
    stateCache.value = { status: body.status, waiting: body.waiting ?? { type: null } }
    return stateCache.value
  } catch {
    // Never act on a stale snapshot after a failed poll: mark unknown so the
    // next loop iteration re-reads before touching the composer.
    stateCache.at = 0
    stateCache.value = { status: 'UNKNOWN', waiting: { type: null } }
    return stateCache.value
  }
}

async function visible(locator: Locator, ms = 300): Promise<boolean> {
  return locator.first().isVisible({ timeout: ms }).catch(() => false)
}

/**
 * E2E smoke 1 (real model). State-driven: poll the authoritative task state
 * via API, act through the REAL UI controls, and assert what the user sees.
 */
test('visible turn: cards -> confirm -> proposals -> completed', async ({ page }) => {
  test.setTimeout(600_000)
  await page.goto('/assistant')

  const textarea = page.locator('textarea').first()
  await expect(textarea).toBeVisible()
  await textarea.fill(`今天下午和${CUSTOMER}的王总线上会议，评审了POC部署方案，${CONTENT}`)
  await textarea.press('Enter')

  const completed = page.getByText('本次任务已完成')
  const confirmBtn = page.getByRole('button', { name: '确认写入' })
  const refuseBtn = page.getByRole('button', { name: '暂不处理' })
  const hint = page.getByText(/正在回答[：:](客户名称|沟通内容|下一步行动|下次跟进时间)/)

  for (let round = 0; round < 24; round++) {
    const state = await taskState(page)
    if (state.status !== 'ACTIVE' || state.waiting.type === null) {
      if (await visible(completed, 300)) break
    }

    if (state.waiting.type === 'FIELD') {
      // The controlled input must be usable and show the field label.
      if (!(await textarea.isEnabled())) continue
      await expect(hint.first()).toBeVisible({ timeout: 60_000 })
      const label = (await hint.first().textContent()) ?? ''
      const answer = label.includes('客户名称')
        ? CUSTOMER
        : label.includes('下一步行动')
          ? NEXT_ACTION
          : CONTENT
      const answeredField = state.waiting.field ?? ''
      const submitsBefore = await submitCount(page)
      let delivered = false
      const sendDeadline = Date.now() + 150_000
      while (!delivered && Date.now() < sendDeadline) {
        // The composer disables the moment the answer is accepted; a blocking
        // fill() would hang on that transition, so probe actionability first.
        const fillable = await textarea
          .isEnabled({ timeout: 1_000 })
          .catch(() => false)
        if (!fillable) {
          delivered = (await submitCount(page)) > submitsBefore
          break
        }
        await textarea.fill(answer, { timeout: 5_000 }).catch(() => undefined)
        await textarea.press('Enter').catch(() => undefined)
        await page.waitForTimeout(5_000)
        delivered = (await submitCount(page)) > submitsBefore
        if (!delivered) await page.waitForTimeout(8_000)
      }
      // Block until the authoritative wait changes (model round 30-90s).
      const changeDeadline = Date.now() + 180_000
      let fieldAdvanced = false
      while (Date.now() < changeDeadline) {
        await page.waitForTimeout(5_000)
        const next = await taskState(page)
        if (next.waiting.field !== answeredField || next.waiting.type !== 'FIELD') {
          fieldAdvanced = true
          break
        }
      }
      expect(fieldAdvanced, 'field answer was never accepted (wait stuck)').toBe(true)
      continue
    }

    if (state.waiting.type === 'ACTIVITY_KIND') {
      const kindBtn = page.getByRole('button', { name: /线上会议/, exact: false })
      await expect(kindBtn.last()).toBeEnabled({ timeout: 60_000 })
      await kindBtn.last().click()
      await page.waitForTimeout(3_000)
      continue
    }

    if (state.waiting.type === 'CONFIRMATION') {
      const field = state.waiting.field ?? ''
      if (field === 'activity_write') {
        const confirmsBefore = await confirmCount(page)
        let confirmed = false
        const confirmDeadline = Date.now() + 150_000
        while (!confirmed && Date.now() < confirmDeadline) {
          const enabled = await confirmBtn.last().isEnabled({ timeout: 10_000 }).catch(() => false)
          if (enabled) await confirmBtn.last().click()
          await page.waitForTimeout(6_000)
          confirmed = (await confirmCount(page)) > confirmsBefore
        }
        // Write round is 30-90s; block until the wait changes or task ends.
        const writeDeadline = Date.now() + 180_000
        let writeAdvanced = false
        while (Date.now() < writeDeadline) {
          await page.waitForTimeout(6_000)
          const next = await taskState(page)
          if (next.status !== 'ACTIVE' || (next.waiting.field ?? '') !== 'activity_write') {
            writeAdvanced = true
            break
          }
        }
        expect(writeAdvanced, 'confirm click was never delivered (activity_write wait stuck)').toBe(true)
        continue
      }
      if (field.startsWith('proposal:')) {
        if (await visible(refuseBtn, 1_000)) {
          await refuseBtn.last().click()
          await page.waitForTimeout(500)
        }
        continue
      }
    }

    // Model still working: wait for any state change, then re-poll.
    await page.waitForTimeout(5_000)
  }

  // Settle the tail: state-driven until terminal or budget exhausted.
  // Each model round is 30-60s, so budget on wall time, not turn count.
  const tailDeadline = Date.now() + 300_000
  while (Date.now() < tailDeadline) {
    const state = await taskState(page)
    if (state.status !== 'ACTIVE') break
    const field = state.waiting.field ?? ''
    if (state.waiting.type === 'CONFIRMATION' && field === 'activity_write') {
      const enabled = await confirmBtn
        .last()
        .isEnabled({ timeout: 10_000 })
        .catch(() => false)
      if (enabled) {
        await confirmBtn.last().click()
        await page.waitForTimeout(3_000)
      } else {
        await page.waitForTimeout(3_000)
      }
      continue
    }
    if (state.waiting.type === 'CONFIRMATION' && field.startsWith('proposal:')) {
      if (await visible(refuseBtn, 1_000)) {
        await refuseBtn.last().click()
        await page.waitForTimeout(800)
        continue
      }
    }
    if (state.waiting.type === 'FIELD') {
      const label = (await hint.first().textContent().catch(() => '')) ?? ''
      if (label !== '') {
        const answer = label.includes('customer')
          ? CUSTOMER
          : label.includes('next_action')
            ? NEXT_ACTION
            : CONTENT
        await textarea.fill(answer)
        await textarea.press('Enter')
        await page.waitForTimeout(3_000)
        continue
      }
    }
    await page.waitForTimeout(3_000)
  }

  await expect(completed.first()).toBeVisible({ timeout: 180_000 })
  await expect(page.getByText('已完成').first()).toBeVisible()
})
