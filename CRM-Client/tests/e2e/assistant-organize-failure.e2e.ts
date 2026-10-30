import { expect, test, type Page, type Route } from '@playwright/test'

/**
 * Browser proof for organize/quality technical failure.
 * Every CRM request is intercepted. The storage token is not a credential.
 */
const evidence = '/Users/eddie/Code/CRMWolf/.worktrees/crm-61-model-failure-e2e/.xwing-task/crmwolf/evidence'
const at = '2026-10-29T09:40:00'
const userText = '今天下午和睿狐科技开了个线上会议，聊了 POC 部署。'
const failureText = '跟进整理超时，尚未写入客户活动。原始内容已保存，本次没有产生 CRM 活动。'

function task(overrides: Record<string, unknown> = {}) {
  return {
    public_id: 'ast_fixture',
    status: 'ACTIVE',
    goal: userText,
    activity_kind: 'FOLLOW_UP',
    version: 3,
    draft: {
      customer: { status: 'MISSING' },
      content: { status: 'MISSING' },
      next_action: { status: 'MISSING' },
      next_follow_time: { status: 'MISSING' },
      source_segments: [userText],
    },
    waiting: null,
    committed: [],
    budget_steps: 1,
    budget_max_steps: 50,
    processing_turn_id: null,
    processing_turn_status: null,
    reprocess_turn_id: null,
    ...overrides,
  }
}

function failureUi(retryable: boolean) {
  return {
    schema_version: 'crm.agent.ui.v1',
    message_id: 21,
    turn_id: 'acm_org:atn_org:4',
    role: 'assistant',
    state: 'failed',
    blocks: [{
      id: 'b_error_1',
      type: 'error',
      code: retryable ? 'UPSTREAM_TIMEOUT' : 'CONFIGURATION_ERROR',
      title: '整理未完成',
      message: failureText,
      retryable,
      trace_id: null,
    }],
    suggested_actions: [],
    metadata: { display: 'MESSAGE', route: 'WORKFLOW', accessibility_label: '整理未完成' },
  }
}

function conversation(retryable: boolean) {
  return {
    public_id: 'asc_fixture',
    version: 3,
    focused_task: task({ reprocess_turn_id: retryable ? 'atn_org' : null }),
    pending_choice: null,
    has_pending_request: false,
    older_cursor: null,
    messages: [
      { id: 'acm_org:user', role: 'user', text: userText, at, task: null, boundary: null, outcome: null, ui: null },
      {
        id: 'acm_org:atn_org:4',
        role: 'assistant',
        text: failureText,
        at,
        task: task({ reprocess_turn_id: retryable ? 'atn_org' : null }),
        boundary: null,
        outcome: 'failure',
        ui: failureUi(retryable),
      },
    ],
  }
}

async function fulfill(route: Route, status: number, body: unknown): Promise<void> {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

async function install(page: Page, handler: (route: Route, path: string) => Promise<void>): Promise<string[]> {
  const calls: string[] = []
  await page.addInitScript(() => {
    localStorage.setItem('token', 'ui.fixture.not-a-credential')
  })
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    calls.push(`${route.request().method()} ${path}`)
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
  return calls
}

test('retryable organize failure keeps the saved sentence and reuses the turn', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  let retried = 0
  const calls = await install(page, async (route, path) => {
    if (path.endsWith('/assistant/conversation/open') || path.endsWith('/assistant/conversation')) {
      return fulfill(route, 200, conversation(true))
    }
    if (path.endsWith('/turns/atn_org')) {
      return fulfill(route, 200, {
        turn_id: 'atn_org', status: 'FAILED', lease_version: 2, reprocess_allowed: true, events: [], task: task({ reprocess_turn_id: 'atn_org' }),
      })
    }
    if (path.endsWith('/turns/atn_org/retry')) {
      retried += 1
      return fulfill(route, 200, {
        turn_id: 'atn_org', status: 'PENDING', lease_version: 3, reprocess_allowed: false, events: [],
        task: task({ processing_turn_id: 'atn_org', processing_turn_status: 'PENDING', reprocess_turn_id: null }),
      })
    }
    return fulfill(route, 404, { detail: path })
  })
  await page.goto('http://127.0.0.1:5174/assistant')
  await expect(page.getByText(failureText)).toBeVisible()
  await expect(page.getByRole('alert').getByText('整理未完成', { exact: true })).toBeVisible()
  await expect(page.getByText('可以重试')).toBeVisible()
  await expect(page.getByRole('button', { name: '重试', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '重新处理' })).toBeVisible()
  await expect(page.getByText(userText)).toHaveCount(1)
  await page.screenshot({ path: `${evidence}/01-organize-failure-reprocess.png`, fullPage: true })
  await page.getByRole('button', { name: '重新处理' }).click()
  await expect.poll(() => retried).toBe(1)
  await expect(page.getByText(userText)).toHaveCount(1)
  expect(calls.some((call) => call.includes('/conversation/messages'))).toBe(false)
  expect(calls.some((call) => call.includes('cancel') || call.endsWith('/choices'))).toBe(false)
  await page.screenshot({ path: `${evidence}/02-organize-reprocess-same-turn.png`, fullPage: true })
})

test('non-retryable organize failure has no reprocess button', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await install(page, async (route, path) => {
    if (path.endsWith('/assistant/conversation/open') || path.endsWith('/assistant/conversation')) {
      return fulfill(route, 200, conversation(false))
    }
    return fulfill(route, 404, { detail: path })
  })
  await page.goto('http://127.0.0.1:5174/assistant')
  await expect(page.getByText(failureText)).toBeVisible()
  await expect(page.getByText('不能盲目重试')).toBeVisible()
  await expect(page.getByRole('button', { name: '重新处理' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '重试', exact: true })).toHaveCount(0)
  await page.screenshot({ path: `${evidence}/03-organize-failure-no-reprocess.png`, fullPage: true })
})

test('processing hint after one minute does not promise refresh will always continue', async ({ page }) => {
  await page.clock.install()
  await page.setViewportSize({ width: 1280, height: 800 })
  const calls = await install(page, async (route, path) => {
    if (path.endsWith('/assistant/conversation/open') || path.endsWith('/assistant/conversation')) {
      return fulfill(route, 200, {
        public_id: 'asc_fixture', version: 1, focused_task: null, pending_choice: null,
        has_pending_request: false, older_cursor: null, messages: [],
      })
    }
    if (path.endsWith('/assistant/conversation/messages')) {
      return fulfill(route, 200, {
        conversation: {
          public_id: 'asc_fixture', version: 2, focused_task: task(), pending_choice: null,
          has_pending_request: false, older_cursor: null,
          messages: [{ id: 'user-1', role: 'user', text: userText, at, task: null, boundary: null, outcome: null, ui: null }],
        },
        submission: {
          task_public_id: 'ast_fixture', turn_id: 'atn_slow',
          input: { kind: 'text', text: userText, choice: null, client_request_id: 'conv-turn-slow', action_id: null, expected_version: null },
        },
      })
    }
    if (path.endsWith('/submit')) return new Promise<void>(() => undefined)
    return fulfill(route, 404, { detail: path })
  })
  await page.goto('http://127.0.0.1:5174/assistant')
  await page.getByRole('textbox', { name: '客户沟通内容' }).fill(userText)
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByText('内容已保存，处理仍在后台继续；关闭或刷新不会取消')).toBeVisible()
  await page.clock.fastForward(60_000)
  await expect(page.getByText('内容已保存，处理仍在后台继续；关闭或刷新不会取消')).toBeVisible()
  await expect(page.getByText('刷新后可继续')).toHaveCount(0)
  expect(calls.filter((call) => call.startsWith('POST') && call.includes('/submit'))).toHaveLength(1)
  expect(calls.some((call) => call.includes('cancel') || call.endsWith('/choices'))).toBe(false)
  await page.screenshot({ path: `${evidence}/04-processing-keeps-running.png`, fullPage: true })
})

test('successful activity receipt shows the persisted write sentence', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  const written = '活动已写入'
  const ui = {
    schema_version: 'crm.agent.ui.v1',
    message_id: 22,
    turn_id: 'acm_org:atn_org:5',
    role: 'assistant',
    state: 'final',
    blocks: [{ id: 'b_result_1', type: 'action_result', action_id: 'receipt', status: 'SUCCESS', title: written, message: written }],
    suggested_actions: [],
    metadata: { display: 'MESSAGE', route: 'WORKFLOW', accessibility_label: written },
  }
  await install(page, async (route, path) => {
    if (path.endsWith('/assistant/conversation/open') || path.endsWith('/assistant/conversation')) {
      return fulfill(route, 200, {
        public_id: 'asc_fixture', version: 4, focused_task: task({ status: 'ACTIVE' }), pending_choice: null,
        has_pending_request: false, older_cursor: null,
        messages: [
          { id: 'acm_org:user', role: 'user', text: userText, at, task: null, boundary: null, outcome: null, ui: null },
          { id: 'acm_org:atn_org:5', role: 'assistant', text: written, at, task: task(), boundary: null, outcome: 'activity_written', ui },
        ],
      })
    }
    return fulfill(route, 404, { detail: path })
  })
  await page.goto('http://127.0.0.1:5174/assistant')
  await expect(page.getByText(written).first()).toBeVisible()
  await page.screenshot({ path: `${evidence}/05-activity-written.png`, fullPage: true })
})

test('unknown activity commit offers refresh and not another write', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  const notice = '客户活动写入结果待核对。请先刷新或查询结果，不要重复提交。'
  const ui = {
    schema_version: 'crm.agent.ui.v1',
    message_id: 23,
    turn_id: 'acm_org:atn_org:6',
    role: 'assistant',
    state: 'final',
    blocks: [{ id: 'b_notice_1', type: 'notice', tone: 'warning', title: '结果待核对', text: notice }],
    suggested_actions: [],
    metadata: { display: 'MESSAGE', route: 'WORKFLOW', accessibility_label: '结果待核对' },
  }
  await install(page, async (route, path) => {
    if (path.endsWith('/assistant/conversation/open') || path.endsWith('/assistant/conversation')) {
      return fulfill(route, 200, {
        public_id: 'asc_fixture', version: 5, focused_task: task(), pending_choice: null,
        has_pending_request: false, older_cursor: null,
        messages: [
          { id: 'acm_org:user', role: 'user', text: userText, at, task: null, boundary: null, outcome: null, ui: null },
          { id: 'acm_org:atn_org:6', role: 'assistant', text: notice, at, task: task(), boundary: null, outcome: 'failure', ui },
        ],
      })
    }
    return fulfill(route, 404, { detail: path })
  })
  await page.goto('http://127.0.0.1:5174/assistant')
  await expect(page.getByText(notice)).toBeVisible()
  await expect(page.getByRole('button', { name: '重新写入' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '重新处理' })).toHaveCount(0)
  await page.screenshot({ path: `${evidence}/06-unknown-commit.png`, fullPage: true })
})
