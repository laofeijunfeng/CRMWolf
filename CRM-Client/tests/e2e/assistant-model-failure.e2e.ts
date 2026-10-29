import { expect, test, type Page } from '@playwright/test'

/**
 * Browser proof for Root model failure cards.
 * The API is intercepted, matching the existing assistant conversation e2e.
 * It does not call a configured model provider.
 */
const at = '2026-10-29T03:00:00'

function failureEnvelope(retry: boolean) {
  return {
    schema_version: 'crm.agent.ui.v1',
    message_id: 11,
    turn_id: 'acm_fixture_retry:reply',
    role: 'assistant',
    state: 'failed',
    blocks: [{
      id: 'b_error_1',
      type: 'error',
      code: retry ? 'UPSTREAM_TIMEOUT' : 'CONFIGURATION_ERROR',
      title: retry ? '模型服务响应超时' : '模型配置不可用',
      message: retry
        ? '模型服务响应超时，本次没有写入客户活动。'
        : '模型配置暂不可用，本次没有写入客户活动，请联系管理员。',
      retryable: retry,
      trace_id: 'acm_fixture_retry',
    }],
    suggested_actions: retry
      ? [{ type: 'retry', action_id: 'retry:acm_fixture_retry', label: '重试' }]
      : [],
    metadata: {
      display: 'MESSAGE',
      route: 'WORKFLOW',
      accessibility_label: retry ? '模型服务响应超时' : '模型配置不可用',
    },
  }
}

function conversation(retry: boolean) {
  return {
    public_id: 'asc_fixture',
    version: retry ? 7 : 8,
    focused_task: null,
    pending_choice: null,
    has_pending_request: false,
    older_cursor: null,
    messages: [
      {
        id: 'acm_fixture_retry:user',
        role: 'user',
        text: '今天下午和睿狐科技开了个线上会议，聊了 POC 部署。',
        at,
        task: null,
        boundary: null,
        outcome: null,
        ui: null,
      },
      {
        id: 'acm_fixture_retry:reply',
        role: 'assistant',
        text: retry
          ? '模型服务响应超时，本次没有写入客户活动。'
          : '已重新开始处理。',
        at,
        task: null,
        boundary: null,
        outcome: retry ? 'failure' : null,
        ui: retry
          ? failureEnvelope(true)
          : {
              schema_version: 'crm.agent.ui.v1',
              message_id: 12,
              turn_id: 'acm_fixture_retry:reply',
              role: 'assistant',
              state: 'final',
              blocks: [{ id: 'b_text_1', type: 'text', format: 'plain', text: '已重新开始处理。' }],
              suggested_actions: [],
              metadata: { display: 'MESSAGE', route: 'WORKFLOW', accessibility_label: '已重新开始处理。' },
            },
      },
    ],
  }
}

async function installFixture(page: Page, initialRetry: boolean) {
  let state = conversation(initialRetry)
  const calls = { retries: 0, texts: 0 }
  await page.addInitScript(() => {
    localStorage.setItem('token', 'ui.fixture.not-a-credential')
  })
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const json = (body: unknown, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })
    if (path.endsWith('/teams/user-teams')) {
      return json({ teams: [{ id: 1, name: '界面验证团队', code: 'UI', owner_id: 'fixture', created_at: at }], current_team_id: 1 })
    }
    if (path.endsWith('/auth/me')) {
      return json({ id: 2, name: '界面验证', email: 'fixture@example.invalid', status: 'ACTIVE', created_at: at, updated_at: at })
    }
    if (path.endsWith('/follow-up-tasks/confirmation-cases/pending-count')) return json({ count: 0 })
    if (path.endsWith('/auth/me/roles')) return json([])
    if (path.endsWith('/auth/me/permissions')) return json({ permissions: [], total: 0, cached: false })
    if (path.endsWith('/assistant/conversation/open') || path.endsWith('/assistant/conversation')) return json(state)
    if (path.endsWith('/assistant/conversation/entries/acm_fixture_retry/retry')) {
      calls.retries += 1
      const body = route.request().postDataJSON() as Record<string, unknown>
      expect(body).toEqual({ expected_version: 7 })
      state = conversation(false)
      return json({ conversation: state, submission: null })
    }
    if (path.endsWith('/assistant/conversation/messages')) {
      calls.texts += 1
      return json({ detail: 'ordinary send is not used for retry' }, 500)
    }
    return json({ detail: 'unexpected' }, 404)
  })
  return calls
}

test('root timeout shows retry and reuses the entry', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  const calls = await installFixture(page, true)
  await page.goto('/assistant')
  await expect(page.getByText('模型服务响应超时，本次没有写入客户活动。')).toBeVisible()
  await expect(page.getByText('追踪编号：acm_fixture_retry')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('root-timeout-retry.png'), fullPage: true })
  await page.getByRole('button', { name: '重试', exact: true }).click()
  await expect(page.getByText('已重新开始处理。')).toBeVisible()
  await expect(page.getByRole('button', { name: '重试', exact: true })).toHaveCount(0)
  await expect(page.getByText('今天下午和睿狐科技开了个线上会议，聊了 POC 部署。')).toHaveCount(1)
  expect(calls.retries).toBe(1)
  expect(calls.texts).toBe(0)
  await page.screenshot({ path: testInfo.outputPath('root-timeout-after-retry.png'), fullPage: true })
})

test('configuration failure has no retry button', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await installFixture(page, false)
  // Replace the success fixture with a configuration failure before navigation.
  await page.unroute('**/api/v1/**')
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const json = (body: unknown) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    if (path.endsWith('/teams/user-teams')) {
      return json({ teams: [{ id: 1, name: '界面验证团队', code: 'UI', owner_id: 'fixture', created_at: at }], current_team_id: 1 })
    }
    if (path.endsWith('/auth/me')) {
      return json({ id: 2, name: '界面验证', email: 'fixture@example.invalid', status: 'ACTIVE', created_at: at, updated_at: at })
    }
    if (path.endsWith('/follow-up-tasks/confirmation-cases/pending-count')) return json({ count: 0 })
    if (path.endsWith('/auth/me/roles')) return json([])
    if (path.endsWith('/auth/me/permissions')) return json({ permissions: [], total: 0, cached: false })
    if (path.endsWith('/assistant/conversation/open') || path.endsWith('/assistant/conversation')) {
      const failed = conversation(true)
      failed.messages[1] = {
        ...failed.messages[1],
        text: '模型配置暂不可用，本次没有写入客户活动，请联系管理员。',
        outcome: 'failure',
        ui: failureEnvelope(false),
      }
      return json(failed)
    }
    return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'unexpected' }) })
  })
  await page.goto('/assistant')
  await expect(page.getByText('模型配置暂不可用，本次没有写入客户活动，请联系管理员。')).toBeVisible()
  await expect(page.getByText('不能盲目重试')).toBeVisible()
  await expect(page.getByRole('button', { name: '重试', exact: true })).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath('root-configuration-no-retry.png'), fullPage: true })
})
