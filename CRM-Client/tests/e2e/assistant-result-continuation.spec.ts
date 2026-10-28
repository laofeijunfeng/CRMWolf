import http from 'node:http'
import { expect, test, type Page, type Route } from '@playwright/test'

/**
 * Isolated browser proof for the normal assistant path.
 * Every CRM request is intercepted. The storage token is not a credential.
 */

const evidence = '/Users/eddie/Code/CRMWolf/.worktrees/crm-46-assistant-continuation/.xwing-task/crmwolf/evidence'
const at = '2026-10-28T02:00:33'
const userText = '今天和睿狐科技确认了 POC 部署，周三再跟进'

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
    committed: [{ kind: 'customer_activity', public_id: 'act_ok' }],
    budget_steps: 4,
    budget_max_steps: 50,
    processing_turn_id: null,
    processing_turn_status: null,
    reprocess_turn_id: null,
    ...overrides
  }
}

function frame(event: string, data: Record<string, unknown>): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

function stageFrames(): string {
  const stages = ['classify', 'structure', 'quality_gate', 'write'] as const
  const chunks = [frame('accepted', { turn_id: 'atn_ok', seq: 1 })]
  let seq = 2
  for (const stage of stages) {
    chunks.push(frame('stage', { stage, phase: 'start', seq }))
    seq += 1
    const elapsed = { classify: 820, structure: 1460, quality_gate: 980, write: 540 }[stage]
    chunks.push(frame('stage', { stage, phase: 'done', ms: elapsed, seq, ...(stage === 'quality_gate' ? { score: 86 } : {}) }))
    seq += 1
  }
  return chunks.join('')
}

function waitingFrame(): string {
  return frame('waiting', { task: task(), message: '已记录这条客户活动。', seq: 10 })
}

async function fulfill(route: Route, status: number, body: unknown): Promise<void> {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

async function installShell(page: Page, handler: (route: Route, path: string) => Promise<void>): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'ui.fixture.not-a-credential')
  })
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/teams/user-teams')) {
      return fulfill(route, 200, { teams: [{ id: 1, name: '界面验证团队', code: 'UI', owner_id: 'fixture', created_at: at }], current_team_id: 1 })
    }
    if (path.endsWith('/auth/me')) {
      return fulfill(route, 200, { id: 2, name: '界面验证', email: 'fixture@example.invalid', status: 'ACTIVE', created_at: at, updated_at: at })
    }
    if (path.endsWith('/follow-up-tasks/confirmation-cases/pending-count')) return fulfill(route, 200, { count: 0 })
    if (path.endsWith('/auth/me/roles')) return fulfill(route, 200, [])
    if (path.endsWith('/auth/me/permissions')) return fulfill(route, 200, { permissions: [], total: 0, cached: false })
    if (path.endsWith('/logs/batch') || path.endsWith('/logs/beacon')) return fulfill(route, 200, { ok: true })
    await handler(route, path)
  })
}

function conversation(withResult: boolean) {
  const messages = [
    { id: 'user-1', role: 'user', text: userText, at, task: null, boundary: null, outcome: null }
  ]
  if (withResult) {
    messages.push({ id: 'result-1', role: 'assistant', text: '已记录这条客户活动。', at, task: task(), boundary: null, outcome: 'activity_written' } as never)
  }
  return {
    public_id: 'asc_fixture',
    version: withResult ? 4 : 2,
    focused_task: task(),
    pending_choice: null,
    has_pending_request: false,
    older_cursor: null,
    messages
  }
}

test('normal send shows every stage and the written result', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  let releaseResult: () => void = () => undefined
  const resultGate = new Promise<void>((resolve) => { releaseResult = resolve })
  const server = http.createServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', Connection: 'keep-alive' })
    res.write(stageFrames())
    void resultGate.then(() => {
      res.write(waitingFrame())
      res.end()
    })
  })
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  const address = server.address()
  if (address === null || typeof address === 'string') throw new Error('sse server did not bind')
  const submitUrl = `http://127.0.0.1:${address.port}/submit`
  let submitted = false
  try {
    await installShell(page, async (route, path) => {
      if (path.endsWith('/assistant/conversation/open') || (path.endsWith('/assistant/conversation') && route.request().method() === 'GET')) {
        return fulfill(route, 200, conversation(submitted))
      }
      if (path.endsWith('/assistant/conversation/messages')) {
        submitted = true
        return fulfill(route, 200, {
          conversation: conversation(false),
          submission: {
            task_public_id: 'ast_fixture',
            turn_id: 'atn_ok',
            input: { kind: 'text', text: userText, choice: null, client_request_id: 'conv-turn-ok', action_id: null, expected_version: null }
          }
        })
      }
      if (path.endsWith('/submit')) return route.continue({ url: submitUrl })
      return fulfill(route, 404, { detail: path })
    })
    await page.goto('/assistant')
    await page.getByRole('textbox', { name: '客户沟通内容' }).fill(userText)
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByText('判断活动类型')).toBeVisible()
    await expect(page.getByText('整理内容')).toBeVisible()
    await expect(page.getByText('评估记录质量')).toBeVisible()
    await expect(page.getByText('写入客户活动')).toBeVisible()
    await expect(page.getByText('86 分')).toBeVisible()
    await page.screenshot({ path: `${evidence}/01-normal-stages.png`, fullPage: true })
    releaseResult()
    await expect(page.getByText('已记录这条客户活动。')).toBeVisible()
    await expect(page.getByText('已写入')).toBeVisible()
    await expect(page.getByRole('button', { name: '重试同步' })).toHaveCount(0)
    await expect(page.getByText('遇到问题')).toHaveCount(0)
    await expect(page.getByText('稍后重试')).toHaveCount(0)
    await page.screenshot({ path: `${evidence}/02-normal-result.png`, fullPage: true })
  } finally {
    releaseResult()
    await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve()))
  }
})

test('a lost submit still finishes on the written result', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  let submitted = false
  const submits: string[] = []
  await installShell(page, async (route, path) => {
    if (path.endsWith('/assistant/conversation/open') || (path.endsWith('/assistant/conversation') && route.request().method() === 'GET')) {
      return fulfill(route, 200, conversation(submitted))
    }
    if (path.endsWith('/assistant/conversation/messages')) {
      submitted = true
      return fulfill(route, 200, {
        conversation: conversation(false),
        submission: {
          task_public_id: 'ast_fixture',
          turn_id: 'atn_ok',
          input: { kind: 'text', text: userText, choice: null, client_request_id: 'conv-turn-ok', action_id: null, expected_version: null }
        }
      })
    }
    if (path.endsWith('/submit')) {
      submits.push(new URL(route.request().url()).pathname)
      return fulfill(route, 405, { detail: 'not allowed' })
    }
    if (path.includes('/turns/') && route.request().method() === 'GET') {
      return fulfill(route, 200, {
        turn_id: 'atn_ok',
        status: 'SUCCEEDED',
        lease_version: 1,
        reprocess_allowed: false,
        events: [
          { seq: 2, event: 'stage', data: { stage: 'classify', phase: 'done', ms: 820 } },
          { seq: 4, event: 'stage', data: { stage: 'structure', phase: 'done', ms: 1460 } },
          { seq: 6, event: 'stage', data: { stage: 'quality_gate', phase: 'done', ms: 980, score: 86 } },
          { seq: 8, event: 'stage', data: { stage: 'write', phase: 'done', ms: 540 } },
          { seq: 9, event: 'waiting', data: { message: '已记录这条客户活动。' } }
        ],
        task: task()
      })
    }
    return fulfill(route, 404, { detail: path })
  })
  await page.goto('/assistant')
  await page.getByRole('textbox', { name: '客户沟通内容' }).fill(userText)
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByText('已记录这条客户活动。')).toBeVisible()
  await expect(page.getByText('已写入')).toBeVisible()
  await expect(page.getByText('写入客户活动')).toBeVisible()
  await expect(page.getByRole('button', { name: '重试同步' })).toHaveCount(0)
  await expect(page.getByText('遇到问题')).toHaveCount(0)
  await expect(page.getByText('稍后重试')).toHaveCount(0)
  expect(submits).toEqual(['/api/v1/assistant/tasks/ast_fixture/submit'])
  await page.screenshot({ path: `${evidence}/03-recovered-written-result.png`, fullPage: true })
})
