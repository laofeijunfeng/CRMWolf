import { test, expect, type Page } from '@playwright/test'
import type { AssistantTaskView, ConversationView } from '../../src/schemas/assistant-contracts'

/**
 * Isolated browser contract, not a real-account/provider acceptance test.
 * Every API request is intercepted. The storage marker authenticates no account.
 * Backend ownership, durable routing and writes are separately tested at the service/API seam.
 */
async function isolatedConversation(page: Page) {
  const old: AssistantTaskView = {
    public_id: 'ast_fixture_old', status: 'COMPLETED', goal: '今天下午和睿狐科技开了个线上会议，聊了 POC 部署。',
    activity_kind: 'ONLINE_MEETING', version: 8, draft: {
      customer: { status: 'ACCEPTED', value: '睿狐科技' }, content: { status: 'ACCEPTED', value: '会议记录' },
      next_action: { status: 'MISSING' }, next_follow_time: { status: 'MISSING' }
    }, waiting: null, committed: [{ kind: 'customer_activity', public_id: 'act_fixture_old' }], budget_steps: 3, budget_max_steps: 50
  }
  const at = '2026-10-23T15:40:00'
  const textUi = (id: string, message: string) => ({
    schema_version: 'crm.agent.ui.v1' as const, message_id: id.length, turn_id: `${id}-turn`, role: 'assistant' as const,
    state: 'final' as const, blocks: [{ id: `${id}-block`, type: 'text' as const, format: 'plain' as const, text: message }],
    suggested_actions: [], metadata: { display: 'MESSAGE' as const, route: 'WORKFLOW' as const }
  })
  const boundary = { entry_id: 'acm_fixture_pending', prompt: '这句是接着刚才的睿狐科技，还是另记一件？' }
  let state: ConversationView = {
    public_id: 'asc_fixture', version: 2, focused_task: old, pending_choice: boundary, has_pending_request: false, older_cursor: null,
    messages: [
      { id: 'user-1', role: 'user', text: old.goal, at, task: null, boundary: null, outcome: null, ui: null },
      { id: 'receipt', role: 'assistant', text: '已记录这条客户活动。', at, task: old, boundary: null, outcome: 'activity_written', ui: textUi('receipt', '已记录这条客户活动。') },
      { id: 'user-2', role: 'user', text: '下午和对方技术经理通了电话，说 POC 下周可以部署。', at, task: null, boundary: null, outcome: null, ui: null },
      { id: 'question', role: 'assistant', text: boundary.prompt, at, task: null, boundary, outcome: null, ui: {
        schema_version: 'crm.agent.ui.v1', message_id: 4, turn_id: 'boundary-turn', role: 'assistant', state: 'final',
        blocks: [{ id: 'boundary-block', type: 'interaction', interaction_id: 'boundary-interaction', interaction_type: 'choice',
          business_action: 'assistant_boundary', state: 'ACTIVE', prompt: boundary.prompt,
          options: [{ value: 'CONTINUE', label: '接着刚才', disabled: false }, { value: 'NEW', label: '另记一件', disabled: false }],
          selection_mode: 'single', min_selections: 1, max_selections: 1, fields: [], facts: [], allow_cancel: false,
          submit_on_select: true, submit_action_id: 'boundary-action' }],
        suggested_actions: [], metadata: { display: 'MESSAGE', route: 'WORKFLOW', accessibility_label: '对话边界' }
      } }
    ]
  }
  const calls = { choices: 0, texts: 0, unexpected: [] as string[] }
  await page.addInitScript(() => {
    // Deliberately invalid outside this fully intercepted UI fixture, not a login credential.
    localStorage.setItem('token', 'ui.fixture.not-a-credential')
  })
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const json = async (body: unknown) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    if (path.endsWith('/teams/user-teams')) return json({ teams: [{ id: 1, name: '界面验证团队', code: 'UI', owner_id: 'fixture', created_at: at }], current_team_id: 1 })
    if (path.endsWith('/auth/me')) return json({ id: 2, name: '界面验证', email: 'fixture@example.invalid', status: 'ACTIVE', created_at: at, updated_at: at })
    if (path.endsWith('/follow-up-tasks/confirmation-cases/pending-count')) return json({ count: 0 })
    if (path.endsWith('/auth/me/roles')) return json([])
    if (path.endsWith('/auth/me/permissions')) return json({ permissions: [], total: 0, cached: false })
    if (path.endsWith('/assistant/conversation/open') || path.endsWith('/assistant/conversation')) return json(state)
    if (path.endsWith('/assistant/conversation/choices')) {
      calls.choices++
      const input: { choice: string; entry_id: string } = route.request().postDataJSON()
      expect(input.entry_id).toBe(boundary.entry_id)
      expect(input.choice).toBe('NEW')
      state = { ...state, version: 3, pending_choice: null, messages: [...state.messages,
        { id: 'choice', role: 'user', text: '另记一件', at, task: null, boundary: null, outcome: null, ui: null },
        { id: 'new-result', role: 'assistant', text: '请补充这次沟通的客户名称。', at, task: null, boundary: null, outcome: null, ui: textUi('new-result', '请补充这次沟通的客户名称。') }
      ] }
      return json({ conversation: state, submission: null })
    }
    if (path.endsWith('/assistant/conversation/messages')) {
      calls.texts++
      const input: { text: string } = route.request().postDataJSON()
      state = { ...state, version: 4, messages: [...state.messages,
        { id: 'user-3', role: 'user', text: input.text, at, task: null, boundary: null, outcome: null, ui: null },
        { id: 'answer', role: 'assistant', text: '已收到这次补充。', at, task: null, boundary: null, outcome: null, ui: textUi('answer', '已收到这次补充。') }
      ] }
      return json({ conversation: state, submission: null })
    }
    calls.unexpected.push(path)
    return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'Unexpected isolated fixture request' }) })
  })
  return calls
}

test('restored history settles at the latest conversation', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  const at = '2026-11-09T08:00:00'
  const messages = Array.from({ length: 32 }, (_, index) => ({
    id: `message-${index}`,
    role: index % 2 === 0 ? 'user' as const : 'assistant' as const,
    text: index % 2 === 0
      ? `历史客户沟通第 ${index + 1} 轮：请记录较长的沟通内容。`
      : `历史助手回复第 ${index + 1} 轮：已整理这次沟通并保留最新结果。`,
    at,
    task: null,
    boundary: null,
    outcome: null,
    ui: index % 2 === 0 ? null : {
      schema_version: 'crm.agent.ui.v1' as const, message_id: index + 1,
      turn_id: `turn-${index}`, role: 'assistant' as const, state: 'final' as const,
      blocks: [{ id: `text-${index}`, type: 'text' as const, format: 'plain' as const,
        text: `历史助手回复第 ${index + 1} 轮：已整理这次沟通并保留最新结果。` }],
      suggested_actions: [], metadata: { display: 'MESSAGE' as const, route: 'WORKFLOW' as const }
    }
  }))
  const state: ConversationView = {
    public_id: 'asc_scroll_fixture',
    version: 32,
    focused_task: null,
    pending_choice: null,
    has_pending_request: false,
    older_cursor: 1,
    messages
  }
  await page.addInitScript(() => localStorage.setItem('token', 'ui.fixture.not-a-credential'))
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const json = (body: unknown) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    if (path.endsWith('/teams/user-teams')) return json({ teams: [{ id: 1, name: '界面验证团队', code: 'UI', owner_id: 'fixture', created_at: at }], current_team_id: 1 })
    if (path.endsWith('/auth/me')) return json({ id: 2, name: '界面验证', email: 'fixture@example.invalid', status: 'ACTIVE', created_at: at, updated_at: at })
    if (path.endsWith('/follow-up-tasks/confirmation-cases/pending-count')) return json({ count: 0 })
    if (path.endsWith('/auth/me/roles')) return json([])
    if (path.endsWith('/auth/me/permissions')) return json({ permissions: [], total: 0, cached: false })
    if (path.endsWith('/assistant/conversation') && new URL(route.request().url()).searchParams.has('before')) {
      return json({ ...state, older_cursor: null, messages: messages.slice(0, 12).map(message => ({ ...message, id: `older-${message.id}` })) })
    }
    if (path.endsWith('/assistant/conversation/open') || path.endsWith('/assistant/conversation')) return json(state)
    return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'Unexpected isolated fixture request' }) })
  })
  await page.goto('/assistant')
  const scroller = page.locator('.overflow-y-auto')
  await expect(scroller).toBeVisible()
  await expect(page.getByText('历史助手回复第 32 轮：已整理这次沟通并保留最新结果。', { exact: true })).toBeVisible()
  await expect.poll(() => scroller.evaluate((element) => element.scrollHeight - element.clientHeight - element.scrollTop)).toBeLessThanOrEqual(2)
  const position = await scroller.evaluate((element) => ({ top: element.scrollTop, height: element.scrollHeight, client: element.clientHeight }))
  expect(position.height).toBeGreaterThan(position.client)
  await page.screenshot({ path: testInfo.outputPath('crm90-restored-latest-scroll.png'), fullPage: true })
  await page.getByRole('button', { name: '查看更早对话', exact: true }).scrollIntoViewIfNeeded()
  const before = await scroller.evaluate((element) => ({ top: element.scrollTop, height: element.scrollHeight }))
  await page.getByRole('button', { name: '查看更早对话', exact: true }).click()
  await expect(page.getByRole('button', { name: '查看更早对话', exact: true })).toHaveCount(0)
  await expect.poll(() => scroller.evaluate((element) => element.scrollHeight)).toBeGreaterThan(before.height)
  const after = await scroller.evaluate((element) => ({ top: element.scrollTop, height: element.scrollHeight, client: element.clientHeight }))
  expect(Math.abs(after.top - (before.top + after.height - before.height))).toBeLessThanOrEqual(2)
  expect(after.height - after.client - after.top).toBeGreaterThan(100)
  state.messages.push({ id: 'latest-user', role: 'user', text: '最新用户补充', at, task: null, boundary: null, outcome: null, ui: null })
  await page.reload()
  await expect(page.getByText('最新用户补充', { exact: true })).toBeVisible()
  await expect.poll(() => scroller.evaluate((element) => element.scrollHeight - element.clientHeight - element.scrollTop)).toBeLessThanOrEqual(2)
  await page.screenshot({ path: testInfo.outputPath('crm90-latest-user.png'), fullPage: true })
  state.messages = []
  await page.reload()
  await expect(page.getByText('发送一句话开始，例如', { exact: false })).toBeVisible()
  await expect(page.getByRole('textbox', { name: '客户沟通内容' })).toBeEnabled()
})

test('single-column history, one boundary choice, reload and continued input', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  const calls = await isolatedConversation(page)
  await page.goto('/assistant')
  await expect(page.getByRole('button', { name: '另记一件', exact: true })).toBeVisible()
  await expect(page.getByText('已记录这条客户活动。')).toBeVisible()
  await expect(page.getByRole('button', { name: '新任务', exact: true })).toHaveCount(0)
  await expect(page.getByText('最近任务', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '取消任务', exact: true })).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath('crm28-desktop-boundary.png'), fullPage: true })
  await page.getByRole('button', { name: '另记一件', exact: true }).click()
  await expect(page.locator('.justify-end').filter({ hasText: '另记一件' })).toBeVisible()
  await expect(page.getByText('请补充这次沟通的客户名称。')).toBeVisible()
  await page.reload()
  await expect(page.getByText('已记录这条客户活动。')).toBeVisible()
  await expect(page.getByText('请补充这次沟通的客户名称。')).toBeVisible()
  await page.getByRole('textbox', { name: '客户沟通内容' }).fill('河南双汇，技术经理确认下周部署。')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByText('河南双汇，技术经理确认下周部署。', { exact: true })).toBeVisible()
  await expect(page.getByText('已收到这次补充。')).toBeVisible()
  await expect(page.getByText('已记录这条客户活动。')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('crm28-desktop-continuous.png'), fullPage: true })
  expect(calls.choices).toBe(1)
  expect(calls.texts).toBe(1)
  expect(calls.unexpected).toEqual([])
})

test('narrow viewport keeps the same receipt and two-choice card without overflow', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const calls = await isolatedConversation(page)
  await page.goto('/assistant')
  await expect(page.getByRole('button', { name: '接着刚才', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '另记一件', exact: true })).toBeVisible()
  await expect(page.getByText('已记录这条客户活动。')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('crm28-mobile-boundary.png'), fullPage: true })
  expect(calls.unexpected).toEqual([])
})


test('schema mismatch explains the migration failure and does not start a record', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.addInitScript(() => {
    localStorage.setItem('token', 'ui.fixture.not-a-credential')
  })
  const writes: string[] = []
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const json = (status: number, body: unknown) => route.fulfill({
      status, contentType: 'application/json', body: JSON.stringify(body)
    })
    const at = '2026-10-23T15:40:00'
    if (path.endsWith('/teams/user-teams')) {
      return json(200, { teams: [{ id: 1, name: '界面验证团队', code: 'UI', owner_id: 'fixture', created_at: at }], current_team_id: 1 })
    }
    if (path.endsWith('/auth/me')) {
      return json(200, { id: 2, name: '界面验证', email: 'fixture@example.invalid', status: 'ACTIVE', created_at: at, updated_at: at })
    }
    if (path.endsWith('/follow-up-tasks/confirmation-cases/pending-count')) return json(200, { count: 0 })
    if (path.endsWith('/auth/me/roles')) return json(200, [])
    if (path.endsWith('/auth/me/permissions')) return json(200, { permissions: [], total: 0, cached: false })
    if (path.endsWith('/assistant/conversation/open')) {
      return json(500, { error_code: 'DATABASE_SCHEMA_MISMATCH', detail: '数据库结构与当前代码版本不一致，请执行数据库迁移后重试。' })
    }
    if (route.request().method() !== 'GET') writes.push(path)
    return json(404, { detail: 'Unexpected isolated fixture request' })
  })
  await page.goto('/assistant')
  await expect(page.getByRole('alert')).toContainText('数据库结构与当前版本不一致，请联系管理员执行数据库迁移后重试；不会自动开始新的记录。')
  await expect(page.getByRole('button', { name: '重试同步' })).toBeVisible()
  const shot = testInfo.outputPath('crm43-schema-mismatch.png')
  await page.screenshot({ path: shot, fullPage: true })
  expect(writes).toEqual([])
})
