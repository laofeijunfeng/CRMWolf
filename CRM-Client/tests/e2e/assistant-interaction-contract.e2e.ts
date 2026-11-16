import { writeFile } from 'node:fs/promises'
import { expect, test, type Page } from '@playwright/test'
import { ConversationViewSchema } from '../../src/schemas/assistant-contracts'

// Real /assistant surface with synthetic protocol fixtures, not backend acceptance.
const at = '2026-11-13T09:00:00'
const options = [
  { value: 'i1:complete', label: '已完成，请将这项历史跟进任务标记完成', disabled: false },
  { value: 'i1:hold', label: '先放着，保留当前未完成任务', disabled: false },
  { value: 'i1:skip', label: '本次不可跳过', disabled: true },
] as const

function conversation(readonly = false) {
  const task = {
    public_id: 'ast_contract', status: 'ACTIVE', goal: '核对历史跟进任务', activity_kind: 'FOLLOW_UP', version: 4,
    draft: {
      customer: { status: 'ACCEPTED', value: '界面验证客户' },
      content: { status: 'CANDIDATE', value: '核对历史跟进任务' },
      next_action: { status: 'MISSING' },
      next_follow_time: { status: 'MISSING' },
    }, waiting: readonly ? null : {
      type: 'FOLLOW_UP_DISPOSITION', field: 'follow_up_disposition', question_id: 'q_history',
      prompt: '历史跟进任务', action_id: 'act_history', expected_version: 4,
    }, committed: [], budget_steps: 2, budget_max_steps: 50,
  }
  const history = {
    id: 'history', type: 'interaction', interaction_id: 'ix_history', interaction_type: 'choice',
    business_action: 'settle_follow_up_disposition', presentation: 'OPEN_FOLLOW_UP_DISPOSITION',
    selection_mode: 'single', min_selections: 1, max_selections: 1,
    submit_on_select: !readonly, state: readonly ? 'READ_ONLY' : 'ACTIVE',
    prompt: '历史跟进任务', hint: '请逐条核对，不会改变其他客户任务。', fields: [], options,
    disposition_items: ['current', 'waiting', 'complete', 'unknown', 'failed', 'hold', 'skip'].map((state, i) => ({
      item_id: `i${i + 1}`, title: i === 0 ? '确认客户预算与验收计划' : `历史任务 ${i + 1}`,
      owner_line: '负责人：我 · 计划 11 月 13 日', related: i === 0,
      evidence_quote: i === 0 ? '已向客户确认预算和验收安排' : null,
      state: readonly && state === 'current' ? 'complete' : state,
      result_title: { complete: '已完成', unknown: '待确认', failed: '处理失败', hold: '先放着', skip: '已跳过' }[state],
      result_message: ['complete', 'unknown', 'failed'].includes(state) ? '处理结果仍保留文字说明' : null,
    })),
    submit_label: '提交', submit_action_id: readonly ? null : 'act_history',
  }
  const choice = {
    id: 'choice', type: 'interaction', interaction_id: 'ix_choice', interaction_type: 'choice',
    state: readonly ? 'READ_ONLY' : 'ACTIVE', prompt: '请选择沟通方式',
    fields: [], options: [{ value: 'phone', label: '电话沟通', disabled: false }, { value: 'meeting', label: '线上会议', disabled: false }],
    selection_mode: 'single', min_selections: 1, max_selections: 1, submit_on_select: false,
    submit_label: '确认选择', submit_action_id: readonly ? null : 'act_choice',
  }
  const confirmation = {
    id: 'confirm', type: 'interaction', interaction_id: 'ix_confirm', interaction_type: 'confirmation',
    state: readonly ? 'READ_ONLY' : 'ACTIVE', prompt: '确认创建商机？', fields: [], selection_mode: 'single',
    facts: [{ key: 'customer', label: '客户', value: '界面验证客户', status_label: '已确认' }],
    options: [{ value: 'confirm', label: '确认创建', disabled: false }, { value: 'cancel', label: '取消', disabled: false }],
    submit_label: '提交', submit_action_id: readonly ? null : 'act_confirm',
  }
  const compact = {
    id: 'compact', type: 'interaction', interaction_id: 'ix_compact', interaction_type: 'choice',
    presentation: 'COMPACT_TASK_COMPLETION', state: readonly ? 'SUBMITTED' : 'ACTIVE', prompt: '确认合同交付时间',
    fields: [], options: [{ value: 'complete', label: '标记完成', disabled: false }],
    selection_mode: 'single', min_selections: 1, max_selections: 1, submit_on_select: true,
    submit_label: '完成', submit_action_id: readonly ? null : 'act_compact',
  }
  return ConversationViewSchema.parse({
    public_id: 'asc_contract', version: 4, focused_task: task, pending_choice: null, has_pending_request: false, older_cursor: null,
    messages: [{
      id: 'contract', role: 'assistant', text: '核对任务', at, task, boundary: null, outcome: null,
      ui: {
        schema_version: 'crm.agent.ui.v1', message_id: 1, turn_id: 'contract', role: 'assistant', state: 'final', suggested_actions: [],
        metadata: { display: 'MESSAGE', route: 'WORKFLOW', accessibility_label: '核对任务' },
        blocks: [history, choice, confirmation, compact],
      },
    }],
  })
}

async function install(page: Page, dark: boolean, readonly = false) {
  const state = conversation(readonly)
  await page.addInitScript(({ dark }) => {
    localStorage.setItem('token', 'ui.fixture.not-a-credential')
    document.documentElement.classList.toggle('dark', dark)
  }, { dark })
  await page.emulateMedia({ colorScheme: dark ? 'dark' : 'light', reducedMotion: 'reduce' })
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    let body: unknown = null
    if (path.endsWith('/teams/user-teams')) body = { teams: [{ id: 1, name: '界面验证团队', code: 'UI', owner_id: 'fixture', created_at: at }], current_team_id: 1 }
    else if (path.endsWith('/auth/me')) body = { id: 2, name: '界面验证', email: 'fixture@example.invalid', status: 'ACTIVE', created_at: at, updated_at: at }
    else if (path.endsWith('/pending-count')) body = { count: 0 }
    else if (path.endsWith('/auth/me/roles')) body = []
    else if (path.endsWith('/auth/me/permissions')) body = { permissions: [], total: 0, cached: false }
    else if (path.endsWith('/assistant/conversation/open') || path.endsWith('/assistant/conversation')) body = state
    return route.fulfill({ status: body === null ? 404 : 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
  await page.goto('/assistant')
  await page.evaluate(dark => document.documentElement.classList.toggle('dark', dark), dark)
  await expect(page.locator('html')).toHaveClass(dark ? /dark/ : /^(?!.*\bdark\b).*$/)
  await expect(page.locator('#history-prompt')).toBeVisible()
}

function measureText(cards: Element[]) {
  const rgb = (value: string) => (value.match(/[\d.]+/g) ?? []).map(Number)
  const composite = (front: number[], behind: number[]) => front.slice(0, 3).map((value, index) => value * (front[3] ?? 1) + (behind[index] ?? 255) * (1 - (front[3] ?? 1)))
  function background(element: Element | null): number[] {
    return element === null ? [255, 255, 255] : composite(rgb(getComputedStyle(element).backgroundColor), background(element.parentElement))
  }
  function luminance(channels: number[]) {
    return channels.map(value => { const channel = value / 255; return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4 })
      .reduce((sum, channel, index) => sum + channel * ([0.2126, 0.7152, 0.0722][index] ?? 0), 0)
  }
  return cards.flatMap(card => [...card.querySelectorAll('*')].filter(element =>
    element.getBoundingClientRect().width > 0 && [...element.childNodes].some(node => node.nodeType === Node.TEXT_NODE && (node.textContent ?? '').trim() !== '')
  ).map(element => {
    const surface = background(element)
    const text = rgb(getComputedStyle(element).color)
    const values = [luminance(composite(text, surface)), luminance(surface)]
    return { text: element.textContent, color: getComputedStyle(element).color, surface, disabled: element.closest(':disabled') !== null,
      contrast: (Math.max(...values) + 0.05) / (Math.min(...values) + 0.05) }
  }))
}

for (const dark of [false, true]) {
  for (const width of [375, 1440]) {
    test(`interaction contrast and touch contract ${dark ? 'dark' : 'light'} ${width}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 1100 })
      await install(page, dark)
      await page.locator('#history-prompt').scrollIntoViewIfNeeded()
      await page.screenshot({ path: testInfo.outputPath('interaction.png'), fullPage: true })
      const measurements = await page.locator('.agent-ui-interaction').evaluateAll(cards => {
        function luminance(rgb: number[]) {
          return rgb.map(v => { const c = v / 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4 })
            .reduce((sum, c, i) => sum + c * ([0.2126, 0.7152, 0.0722][i] ?? 0), 0)
        }
        return cards.map(card => {
          const text = card.querySelector('[id$="-prompt"]') ?? card
          const rgb = (s: string) => (s.match(/[\d.]+/g) ?? []).map(Number)
          function background(element: Element | null): number[] {
            if (element === null) return [255, 255, 255]
            const channels = rgb(getComputedStyle(element).backgroundColor)
            const alpha = channels[3] ?? 1
            const behind = background(element.parentElement)
            return channels.slice(0, 3).map((v, i) => v * alpha + (behind[i] ?? 255) * (1 - alpha))
          }
          const textColor = getComputedStyle(text).color
          const surfaceColor = background(text)
          const labels = [...card.querySelectorAll('header span, li > div > span, [data-agent-ui-related-toggle]')].map(label => {
            const colors = [luminance(rgb(getComputedStyle(label).color).slice(0, 3)), luminance(background(label))]
            return { text: label.textContent, color: getComputedStyle(label).color, contrast: (Math.max(...colors) + 0.05) / (Math.min(...colors) + 0.05) }
          })
          const values = [luminance(rgb(textColor).slice(0, 3)), luminance(surfaceColor)]
          return { prompt: text.id, textColor, surfaceColor, labels, contrast: (Math.max(...values) + 0.05) / (Math.min(...values) + 0.05), overflow: card.scrollWidth - card.clientWidth,
            buttons: [...card.querySelectorAll('button')].map(b => ({ height: b.getBoundingClientRect().height, width: b.getBoundingClientRect().width, overflow: b.scrollWidth - b.clientWidth })) }
        })
      })
      for (const card of measurements) {
        expect(card.contrast, JSON.stringify(card)).toBeGreaterThanOrEqual(4.5)
        expect(card.overflow).toBeLessThanOrEqual(1)
        for (const label of card.labels) expect(label.contrast, JSON.stringify(label)).toBeGreaterThanOrEqual(4.5)
        for (const button of card.buttons) { expect(button.height).toBeGreaterThanOrEqual(44); expect(button.width).toBeGreaterThanOrEqual(44); expect(button.overflow).toBeLessThanOrEqual(1) }
      }
      await testInfo.attach('computed-contract.json', { body: JSON.stringify(measurements, null, 2), contentType: 'application/json' })
      const boxes = await page.locator('.agent-ui-interaction').first().locator('button[aria-pressed]').evaluateAll(buttons => buttons.map(button => ({ x: button.getBoundingClientRect().x, y: button.getBoundingClientRect().y })))
      expect(boxes).toHaveLength(3)
      if (width === 375) {
        expect(new Set(boxes.map(box => box.y)).size).toBe(3)
        expect(new Set(boxes.map(box => box.x)).size).toBe(1)
      } else {
        expect(new Set(boxes.map(box => box.y)).size).toBe(1)
        expect(new Set(boxes.map(box => box.x)).size).toBe(3)
      }
      const historyOption = page.locator('.agent-ui-interaction').first().getByRole('button', { name: options[0]?.label, exact: true })
      const restingBackground = await historyOption.evaluate(button => getComputedStyle(button).backgroundColor)
      await historyOption.hover()
      await expect.poll(() => historyOption.evaluate(button => getComputedStyle(button).backgroundColor)).not.toBe(restingBackground)
      await page.keyboard.press('Tab')
      await historyOption.focus()
      expect(await historyOption.evaluate(button => button.matches(':focus-visible'))).toBe(true)
      expect(await historyOption.evaluate(button => getComputedStyle(button).boxShadow)).not.toBe('none')
      expect(await historyOption.evaluate(button => parseFloat(getComputedStyle(button).transitionDuration))).toBeLessThanOrEqual(0.01)
      await page.locator('.agent-ui-interaction').first().screenshot({ path: testInfo.outputPath('history-focus.png') })
      const history = page.locator('.agent-ui-interaction').first()
      const disclosure = history.getByRole('button', { name: '查看关联信息', exact: true })
      await disclosure.focus()
      await page.keyboard.press('Enter')
      await expect(disclosure).toHaveAttribute('aria-expanded', 'true')
      const target = await disclosure.getAttribute('aria-controls')
      await expect(page.locator(`[id="${target}"]`)).toContainText('已向客户确认预算和验收安排')
      await expect(history.getByRole('button', { name: options[2]?.label, exact: true })).toBeDisabled()
      const choice = page.locator('.agent-ui-interaction').nth(1)
      await choice.getByRole('button', { name: '电话沟通', exact: true }).click()
      await expect(choice.getByRole('button', { name: '电话沟通', exact: true })).toHaveAttribute('aria-pressed', 'true')
      const textMeasurements = await page.locator('.agent-ui-interaction').evaluateAll(measureText)
      for (const text of textMeasurements.filter(text => !text.disabled)) expect(text.contrast, JSON.stringify(text)).toBeGreaterThanOrEqual(4.5)
      await writeFile(testInfo.outputPath('computed-contract.json'), JSON.stringify({ measurements, boxes, textMeasurements }, null, 2))
      await writeFile(testInfo.outputPath('conversation.json'), JSON.stringify(conversation(), null, 2))
      await page.screenshot({ path: testInfo.outputPath('expanded-selected.png'), fullPage: true })
      for (const [index, name] of ['history', 'choice', 'confirmation', 'compact'].entries()) {
        await page.locator('.agent-ui-interaction').nth(index).screenshot({ path: testInfo.outputPath(`${name}-card.png`) })
      }
    })
  }
}

test('history keyboard submission exposes selected processing state and blocks duplicates', async ({ page }, testInfo) => {
  await install(page, true)
  let calls = 0
  let payload: unknown
  await page.route('**/assistant/conversation/commands', async route => {
    calls++; payload = route.request().postDataJSON()
    await new Promise(resolve => setTimeout(resolve, 1500))
    await route.abort()
  })
  const card = page.locator('.agent-ui-interaction').first()
  const option = card.locator('button').filter({ hasText: options[0]?.label ?? '' })
  await option.focus()
  await page.keyboard.press('Space')
  await expect(option).toContainText('处理中')
  await expect(option).toHaveAttribute('aria-pressed', 'true')
  await expect(card).toHaveAttribute('aria-busy', 'true')
  await expect(card.getByRole('button', { name: options[1]?.label, exact: true })).toBeDisabled()
  const otherBorder = await card.getByRole('button', { name: options[1]?.label, exact: true }).evaluate(button => getComputedStyle(button).borderColor)
  await expect.poll(() => option.evaluate(button => getComputedStyle(button).borderColor)).not.toBe(otherBorder)
  await card.screenshot({ path: testInfo.outputPath('processing-card.png') })
  const textMeasurements = await card.evaluateAll(measureText)
  const selectedText = textMeasurements.find(text => text.text?.includes('处理中'))
  expect(selectedText?.contrast).toBeGreaterThanOrEqual(4.5)
  await writeFile(testInfo.outputPath('processing-contract.json'), JSON.stringify({ textMeasurements, payload }, null, 2))
  await page.keyboard.press('Space')
  await page.keyboard.press('Enter')
  await page.screenshot({ path: testInfo.outputPath('processing.png'), fullPage: true })
  await expect.poll(() => calls).toBe(1)
  expect(payload).toMatchObject({ task_public_id: 'ast_contract', expected_version: 4, input: { action_id: 'act_history', expected_version: 4, client_request_id: expect.stringMatching(/^[0-9a-f-]{36}$/), choice: 'i1:complete', kind: 'submit_field' } })
})

test('readonly history retains evidence but exposes no mutation controls', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1400 })
  await install(page, true, true)
  const cards = page.locator('.agent-ui-interaction')
  await expect(cards.first().getByRole('button')).toHaveCount(1)
  await cards.first().getByRole('button', { name: '查看关联信息' }).click()
  await expect(page.locator('[data-agent-ui-related-line]')).toBeVisible()
  await expect(cards.nth(1).getByRole('button')).toHaveCount(0)
  await expect(cards.nth(2).getByRole('button')).toHaveCount(0)
  await expect(cards.nth(3).getByRole('button')).toHaveCount(0)
  await expect(cards.nth(3)).toContainText('已完成')
  await cards.first().screenshot({ path: testInfo.outputPath('readonly-history-card.png') })
  await cards.nth(3).screenshot({ path: testInfo.outputPath('readonly-compact-card.png') })
  await page.screenshot({ path: testInfo.outputPath('readonly.png'), fullPage: true })
})
