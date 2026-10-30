import http from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test, type Page, type Route } from '@playwright/test'

/**
 * Real /assistant page, with CRM calls intercepted.
 * Proves the local process card stays during work and leaves after an authoritative write.
 */
const evidence = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../.xwing-task/crmwolf/evidence')
const at = '2026-10-30T02:00:00'
const userText = '今天和睿狐科技确认了 POC 部署，周三再跟进'
const failureText = '跟进整理超时，尚未写入客户活动。原始内容已保存，本次没有产生 CRM 活动。'
const unknownText = '客户活动写入结果待核对。请先刷新或查询结果，不要重复提交。'

const viewports = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'narrow', width: 375, height: 812 }
] as const

function task(overrides: Record<string, unknown> = {}) {
  return {
    public_id: 'ast_fixture',
    status: 'ACTIVE',
    goal: userText,
    activity_kind: 'FOLLOW_UP',
    version: 4,
    draft: {
      customer: { status: 'ACCEPTED', value: '睿狐科技' },
      content: { status: 'ACCEPTED', value: '确认 POC 部署' },
      next_action: { status: 'ACCEPTED', value: '周三再跟进' },
      next_follow_time: { status: 'MISSING' }
    },
    waiting: null,
    committed: [],
    budget_steps: 2,
    budget_max_steps: 50,
    processing_turn_id: null,
    processing_turn_status: null,
    reprocess_turn_id: null,
    ...overrides
  }
}

function envelope(blocks: ReadonlyArray<Record<string, unknown>>, state: 'final' | 'failed' = 'final') {
  return {
    schema_version: 'crm.agent.ui.v1',
    message_id: 30,
    turn_id: 'result-1',
    role: 'assistant',
    state,
    blocks,
    suggested_actions: [],
    metadata: { display: 'MESSAGE', route: 'WORKFLOW', accessibility_label: '销售助手结果' }
  }
}

function conversation(messages: ReadonlyArray<Record<string, unknown>>, version = 4) {
  return {
    public_id: 'asc_fixture',
    version,
    focused_task: task(),
    pending_choice: null,
    has_pending_request: false,
    older_cursor: null,
    messages
  }
}

const userMessage = { id: 'user-1', role: 'user', text: userText, at, task: null, boundary: null, outcome: null, ui: null }

function assistantMessage(id: string, text: string, outcome: string | null, ui: Record<string, unknown> | null) {
  return { id, role: 'assistant', text, at, task: task(), boundary: null, outcome, ui }
}

async function fulfill(route: Route, status: number, body: unknown): Promise<void> {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

async function install(page: Page, handler: (route: Route, path: string) => Promise<void>): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'ui.fixture.not-a-credential')
  })
  await page.route('**/api/v1/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname
    if (pathname.endsWith('/teams/user-teams')) {
      return fulfill(route, 200, { teams: [{ id: 1, name: '界面验证团队', code: 'UI', owner_id: 'fixture', created_at: at }], current_team_id: 1 })
    }
    if (pathname.endsWith('/auth/me')) {
      return fulfill(route, 200, { id: 2, name: '界面验证', email: 'fixture@example.invalid', status: 'ACTIVE', created_at: at, updated_at: at })
    }
    if (pathname.endsWith('/follow-up-tasks/confirmation-cases/pending-count')) return fulfill(route, 200, { count: 0 })
    if (pathname.endsWith('/auth/me/roles')) return fulfill(route, 200, [])
    if (pathname.endsWith('/auth/me/permissions')) return fulfill(route, 200, { permissions: [], total: 0, cached: false })
    if (pathname.endsWith('/logs/batch') || pathname.endsWith('/logs/beacon')) return fulfill(route, 200, { ok: true })
    await handler(route, pathname)
  })
}

function frame(event: string, data: Record<string, unknown>): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

async function listen(): Promise<{ url: string; close: () => Promise<void>; release: () => void }> {
  let release = (): void => undefined
  const gate = new Promise<void>((resolve) => { release = resolve })
  const server = http.createServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', Connection: 'keep-alive' })
    res.write(frame('accepted', { turn_id: 'atn_ok', seq: 1 }))
    res.write(frame('stage', { stage: 'classify', phase: 'start', seq: 2 }))
    void gate.then(() => {
      res.write(frame('stage', { stage: 'classify', phase: 'done', ms: 10, seq: 3 }))
      res.write(frame('waiting', { task: task({ version: 5, committed: [{ kind: 'customer_activity', public_id: 'act_ok' }] }), message: '活动已写入', seq: 4 }))
      res.end()
    })
  })
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  const address = server.address()
  if (address === null || typeof address === 'string') throw new Error('sse server did not bind')
  return {
    url: `http://127.0.0.1:${address.port}/submit`,
    release,
    close: () => new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()))
  }
}

async function openAssistant(page: Page, width: number, height: number): Promise<void> {
  await page.setViewportSize({ width, height })
  await page.goto('/assistant')
  await page.getByRole('textbox', { name: '客户沟通内容' }).fill(userText)
  await page.getByRole('button', { name: '发送', exact: true }).click()
}

for (const viewport of viewports) {
  test(`processing card stays visible on ${viewport.name}`, async ({ page }) => {
    const sse = await listen()
    let submitted = false
    try {
      await install(page, async (route, pathname) => {
        if (pathname.endsWith('/assistant/conversation/open') || (pathname.endsWith('/assistant/conversation') && route.request().method() === 'GET')) {
          return fulfill(route, 200, conversation(submitted ? [userMessage] : [], submitted ? 2 : 1))
        }
        if (pathname.endsWith('/assistant/conversation/messages')) {
          submitted = true
          return fulfill(route, 200, {
            conversation: conversation([userMessage], 2),
            submission: {
              task_public_id: 'ast_fixture', turn_id: 'atn_ok',
              input: { kind: 'text', text: userText, choice: null, client_request_id: 'conv-turn-card', action_id: null, expected_version: null }
            }
          })
        }
        if (pathname.endsWith('/submit')) return route.continue({ url: sse.url })
        return fulfill(route, 404, { detail: pathname })
      })
      await openAssistant(page, viewport.width, viewport.height)
      await expect(page.getByText('正在判断活动类型')).toBeVisible()
      await expect(page.getByText('处理中')).toBeVisible()
      await expect(page.getByText('原始内容已保存')).toBeVisible()
      await expect(page.getByText('活动已写入')).toHaveCount(0)
      await page.screenshot({ path: path.join(evidence, `process-card-processing-${viewport.name}.png`), fullPage: true })
    } finally {
      sse.release()
      await sse.close()
    }
  })

  test(`success hides the process card on ${viewport.name}`, async ({ page }) => {
    const sse = await listen()
    let submitted = false
    let showSuccess = false
    const success = assistantMessage('result-1', '活动已写入', 'activity_written', envelope([{
      id: 'b_result_1', type: 'action_result', action_id: 'result-1', status: 'SUCCESS', title: '活动已写入', message: '活动已写入'
    }]))
    try {
      await install(page, async (route, pathname) => {
        if (pathname.endsWith('/assistant/conversation/open') || (pathname.endsWith('/assistant/conversation') && route.request().method() === 'GET')) {
          const messages = showSuccess ? [userMessage, success] : submitted ? [userMessage] : []
          return fulfill(route, 200, conversation(messages, showSuccess ? 5 : submitted ? 2 : 1))
        }
        if (pathname.endsWith('/assistant/conversation/messages')) {
          submitted = true
          return fulfill(route, 200, {
            conversation: conversation([userMessage], 2),
            submission: {
              task_public_id: 'ast_fixture', turn_id: 'atn_ok',
              input: { kind: 'text', text: userText, choice: null, client_request_id: 'conv-turn-card', action_id: null, expected_version: null }
            }
          })
        }
        if (pathname.endsWith('/submit')) return route.continue({ url: sse.url })
        return fulfill(route, 404, { detail: pathname })
      })
      await openAssistant(page, viewport.width, viewport.height)
      await expect(page.getByText('正在判断活动类型')).toBeVisible()
      showSuccess = true
      sse.release()
      await expect(page.getByText('活动已写入').first()).toBeVisible()
      await expect(page.getByText('执行过程')).toHaveCount(0)
      await expect(page.getByText('原始内容已保存')).toHaveCount(0)
      await expect(page.getByText('已更新')).toHaveCount(0)
      await expect(page.getByText('写入客户活动')).toHaveCount(0)
      await page.screenshot({ path: path.join(evidence, `process-card-success-${viewport.name}.png`), fullPage: true })
    } finally {
      sse.release()
      await sse.close()
    }
  })

  test(`known failure does not show 已更新 on ${viewport.name}`, async ({ page }) => {
    let submitted = false
    const failure = assistantMessage('failure-1', failureText, 'failure', envelope([{
      id: 'b_error_1', type: 'error', code: 'UPSTREAM_TIMEOUT', title: '整理未完成', message: failureText, retryable: true, trace_id: null
    }], 'failed'))
    const body = [
      frame('accepted', { turn_id: 'atn_fail', seq: 1 }),
      frame('stage', { stage: 'structure', phase: 'start', seq: 2 }),
      frame('error', { code: 'UPSTREAM_TIMEOUT', retryable: true, message: failureText, seq: 3 })
    ].join('')
    await install(page, async (route, pathname) => {
      if (pathname.endsWith('/assistant/conversation/open') || (pathname.endsWith('/assistant/conversation') && route.request().method() === 'GET')) {
        return fulfill(route, 200, conversation(submitted ? [userMessage, failure] : [], submitted ? 3 : 1))
      }
      if (pathname.endsWith('/assistant/conversation/messages')) {
        submitted = true
        return fulfill(route, 200, {
          conversation: conversation([userMessage], 2),
          submission: {
            task_public_id: 'ast_fixture', turn_id: 'atn_fail',
            input: { kind: 'text', text: userText, choice: null, client_request_id: 'conv-turn-fail', action_id: null, expected_version: null }
          }
        })
      }
      if (pathname.endsWith('/submit')) {
        return route.fulfill({ status: 200, headers: { 'Content-Type': 'text/event-stream' }, body })
      }
      return fulfill(route, 404, { detail: pathname })
    })
    await openAssistant(page, viewport.width, viewport.height)
    await expect(page.getByText('整理未完成')).toBeVisible()
    await expect(page.getByText('执行过程')).toBeVisible()
    await expect(page.getByText('正在整理跟进内容')).toBeVisible()
    await expect(page.getByText('已更新')).toHaveCount(0)
    await expect(page.getByText('活动已写入')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '重新写入' })).toHaveCount(0)
    await page.screenshot({ path: path.join(evidence, `process-card-failure-${viewport.name}.png`), fullPage: true })
  })

  test(`unknown commit stays pending on ${viewport.name}`, async ({ page }) => {
    let submitted = false
    const unknown = assistantMessage('unknown-1', unknownText, 'failure', envelope([{
      id: 'b_notice_1', type: 'notice', tone: 'warning', title: '结果待核对', text: unknownText
    }]))
    const body = [
      frame('accepted', { turn_id: 'atn_unknown', seq: 1 }),
      frame('stage', { stage: 'write', phase: 'start', seq: 2 }),
      frame('error', { code: 'UNKNOWN_COMMIT_RESULT', retryable: false, message: unknownText, seq: 3 })
    ].join('')
    await install(page, async (route, pathname) => {
      if (pathname.endsWith('/assistant/conversation/open') || (pathname.endsWith('/assistant/conversation') && route.request().method() === 'GET')) {
        return fulfill(route, 200, conversation(submitted ? [userMessage, unknown] : [], submitted ? 3 : 1))
      }
      if (pathname.endsWith('/assistant/conversation/messages')) {
        submitted = true
        return fulfill(route, 200, {
          conversation: conversation([userMessage], 2),
          submission: {
            task_public_id: 'ast_fixture', turn_id: 'atn_unknown',
            input: { kind: 'text', text: userText, choice: null, client_request_id: 'conv-turn-unknown', action_id: null, expected_version: null }
          }
        })
      }
      if (pathname.endsWith('/submit')) {
        return route.fulfill({ status: 200, headers: { 'Content-Type': 'text/event-stream' }, body })
      }
      return fulfill(route, 404, { detail: pathname })
    })
    await openAssistant(page, viewport.width, viewport.height)
    await expect(page.getByText('结果待核对', { exact: true })).toBeVisible()
    await expect(page.getByText('执行过程')).toBeVisible()
    await expect(page.getByText('写入客户活动')).toBeVisible()
    await expect(page.getByText('已更新')).toHaveCount(0)
    await expect(page.getByText('活动已写入')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '重新写入' })).toHaveCount(0)
    await page.screenshot({ path: path.join(evidence, `process-card-unknown-${viewport.name}.png`), fullPage: true })
  })

  test(`history success does not restore a process card on ${viewport.name}`, async ({ page }) => {
    const success = assistantMessage('result-1', '活动已写入', 'activity_written', envelope([{
      id: 'b_result_1', type: 'action_result', action_id: 'result-1', status: 'SUCCESS', title: '活动已写入', message: '活动已写入'
    }]))
    await install(page, async (route, pathname) => {
      if (pathname.endsWith('/assistant/conversation/open') || pathname.endsWith('/assistant/conversation')) {
        return fulfill(route, 200, conversation([userMessage, success], 6))
      }
      return fulfill(route, 404, { detail: pathname })
    })
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await page.goto('/assistant')
    await expect(page.getByText('活动已写入').first()).toBeVisible()
    await expect(page.getByText('执行过程')).toHaveCount(0)
    await expect(page.getByText('原始内容已保存')).toHaveCount(0)
    await page.screenshot({ path: path.join(evidence, `process-card-history-${viewport.name}.png`), fullPage: true })
  })
}
