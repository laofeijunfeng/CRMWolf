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
  const boundary = { entry_id: 'acm_fixture_pending', prompt: '这句是接着刚才的睿狐科技，还是另记一件？' }
  let state: ConversationView = {
    public_id: 'asc_fixture', version: 2, focused_task: old, pending_choice: boundary, has_pending_request: false, older_cursor: null,
    messages: [
      { id: 'user-1', role: 'user', text: old.goal, at, task: null, boundary: null, outcome: null },
      { id: 'receipt', role: 'assistant', text: '已记录这条客户活动。', at, task: old, boundary: null, outcome: 'activity_written' },
      { id: 'user-2', role: 'user', text: '下午和对方技术经理通了电话，说 POC 下周可以部署。', at, task: null, boundary: null, outcome: null },
      { id: 'question', role: 'assistant', text: boundary.prompt, at, task: null, boundary, outcome: null }
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
        { id: 'choice', role: 'user', text: '另记一件', at, task: null, boundary: null, outcome: null },
        { id: 'new-result', role: 'assistant', text: '请补充这次沟通的客户名称。', at, task: null, boundary: null, outcome: null }
      ] }
      return json({ conversation: state, submission: null })
    }
    if (path.endsWith('/assistant/conversation/messages')) {
      calls.texts++
      const input: { text: string } = route.request().postDataJSON()
      state = { ...state, version: 4, messages: [...state.messages,
        { id: 'user-3', role: 'user', text: input.text, at, task: null, boundary: null, outcome: null },
        { id: 'answer', role: 'assistant', text: '已收到这次补充。', at, task: null, boundary: null, outcome: null }
      ] }
      return json({ conversation: state, submission: null })
    }
    calls.unexpected.push(path)
    return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'Unexpected isolated fixture request' }) })
  })
  return calls
}

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
  await expect(page.getByText('请补充这次沟通的客户名称。')).toBeVisible()
  await expect(page.getByRole('button', { name: '另记一件', exact: true })).toBeDisabled()
  await page.reload()
  await expect(page.getByText('已记录这条客户活动。')).toBeVisible()
  await expect(page.getByText('请补充这次沟通的客户名称。')).toBeVisible()
  await page.getByRole('textbox', { name: '客户沟通内容' }).fill('河南双汇，技术经理确认下周部署。')
  await page.getByRole('button', { name: '发送', exact: true }).click()
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
