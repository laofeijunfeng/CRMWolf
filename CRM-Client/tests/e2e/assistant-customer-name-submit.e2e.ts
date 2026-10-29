import { expect, test, type Page } from '@playwright/test'
import type { AssistantTaskView, ConversationView } from '../../src/schemas/assistant-contracts'

/**
 * Isolated browser contract for the customer-name text input.
 * API calls are intercepted. The storage marker is not a login credential.
 */

const at = '2026-10-29T10:00:00'
const prompt = '未找到对应客户，请核对并提供客户准确名称。'

function task(waitingPrompt = prompt, actionId = 'action1'): AssistantTaskView {
  return {
    public_id: 'ast_customer_name',
    status: 'ACTIVE',
    goal: '今天下午和星河科技通了电话',
    activity_kind: 'FOLLOW_UP',
    version: 1,
    draft: {
      customer: { status: 'MISSING' },
      content: { status: 'ACCEPTED', value: '电话沟通' },
      next_action: { status: 'MISSING' },
      next_follow_time: { status: 'MISSING' }
    },
    waiting: {
      type: 'FIELD',
      field: 'customer',
      question_id: 'q_customer',
      prompt: waitingPrompt,
      action_id: actionId,
      expected_version: 1
    },
    committed: [],
    budget_steps: 1,
    budget_max_steps: 50
  }
}

function envelope(messageId: string, active: boolean, cardPrompt: string, actionId: string, label = '客户名称') {
  return {
    schema_version: 'crm.agent.ui.v1',
    message_id: 1,
    turn_id: messageId,
    role: 'assistant',
    state: 'final',
    suggested_actions: [],
    metadata: { display: 'MESSAGE', route: 'WORKFLOW', accessibility_label: cardPrompt },
    blocks: [{
      id: 'b_interaction_1',
      type: 'interaction',
      interaction_id: `ix-${messageId}`,
      interaction_type: 'text_input',
      business_action: 'collect_field',
      state: active ? 'ACTIVE' : 'READ_ONLY',
      prompt: cardPrompt,
      fields: [{
        key: 'customer',
        label,
        field_type: 'text',
        required: true,
        min_length: 1,
        max_length: 2000,
        default_value: null,
        options: []
      }],
      facts: [],
      options: [],
      allow_blank: false,
      allow_cancel: false,
      submit_label: '提交',
      submit_action_id: active ? actionId : null
    }]
  }
}

function conversation(current: AssistantTaskView, messages: ConversationView['messages']): ConversationView {
  return {
    public_id: 'asc_customer_name',
    version: 2,
    focused_task: current,
    pending_choice: null,
    has_pending_request: false,
    older_cursor: null,
    messages
  }
}

async function installStubs(page: Page, mode: 'success' | 'rejected' | 'offline'): Promise<{ commands: unknown[] }> {
  const current = task()
  let state = conversation(current, [
    { id: 'ask', role: 'assistant', text: prompt, at, task: current, boundary: null, outcome: null, ui: envelope('ask', true, prompt, 'action1') }
  ])
  const commands: unknown[] = []
  await page.addInitScript(() => {
    localStorage.setItem('token', 'ui.fixture.not-a-credential')
  })
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const json = (status: number, body: unknown) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body)
    })
    if (path.endsWith('/teams/user-teams')) {
      return json(200, { teams: [{ id: 1, name: '界面验证团队', code: 'UI', owner_id: 'fixture', created_at: at }], current_team_id: 1 })
    }
    if (path.endsWith('/auth/me')) {
      return json(200, { id: 2, name: '界面验证', email: 'fixture@example.invalid', status: 'ACTIVE', created_at: at, updated_at: at })
    }
    if (path.endsWith('/follow-up-tasks/confirmation-cases/pending-count')) return json(200, { count: 0 })
    if (path.endsWith('/auth/me/roles')) return json(200, [])
    if (path.endsWith('/auth/me/permissions')) return json(200, { permissions: [], total: 0, cached: false })
    if (path.endsWith('/assistant/conversation/open') || path.endsWith('/assistant/conversation')) return json(200, state)
    if (path.endsWith('/assistant/conversation/commands')) {
      const body = route.request().postDataJSON() as {
        expected_version: number
        input: { kind: string, text?: string, action_id?: string, expected_version?: number, client_request_id?: string }
      }
      commands.push(body)
      if (mode === 'offline') return route.abort('failed')
      if (mode === 'rejected') return json(422, { detail: '客户名称没有通过校验' })
      const followed = task('请补充沟通内容', 'action2')
      followed.waiting = {
        type: 'FIELD',
        field: 'content',
        question_id: 'q_content',
        prompt: '请补充沟通内容',
        action_id: 'action2',
        expected_version: 2
      }
      const previous = state.messages[0]
      state = {
        ...state,
        version: 3,
        focused_task: followed,
        messages: [
          previous === undefined ? previous : { ...previous, ui: envelope('ask', false, prompt, 'action1') },
          { id: 'typed', role: 'user', text: body.input.text ?? '', at, task: null, boundary: null, outcome: null, ui: null },
          { id: 'next', role: 'assistant', text: '请补充沟通内容', at, task: followed, boundary: null, outcome: null, ui: envelope('next', true, '请补充沟通内容', 'action2', '沟通内容') }
        ]
      }
      return json(200, { conversation: state, submission: null })
    }
    return json(404, { detail: `Unexpected isolated fixture request ${path}` })
  })
  return { commands }
}

test('customer name card submits once and leaves the processing label', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  const calls = await installStubs(page, 'success')
  await page.goto('/assistant')
  await expect(page.getByText(prompt)).toBeVisible()
  await page.screenshot({ path: evidence('01-customer-card.png'), fullPage: true })
  await page.getByLabel('客户名称').fill('  星河  科技  ')
  await page.getByRole('button', { name: '提交', exact: true }).click()
  await expect(page.getByText('请补充沟通内容')).toBeVisible()
  await expect(page.getByRole('button', { name: '提交处理中…' })).toHaveCount(0)
  expect(calls.commands).toHaveLength(1)
  expect(calls.commands[0]).toMatchObject({
    expected_version: 2,
    input: {
      kind: 'submit_field',
      text: '星河  科技',
      action_id: 'action1',
      expected_version: 1
    }
  })
  const sent = calls.commands[0] as { input: { client_request_id?: string } }
  expect(sent.input.client_request_id && sent.input.client_request_id.length >= 8).toBe(true)
  await page.screenshot({ path: evidence('02-after-submit.png'), fullPage: true })
})

test('explicit validation failure unlocks the customer card', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  const calls = await installStubs(page, 'rejected')
  await page.goto('/assistant')
  await page.getByLabel('客户名称').fill('星河科技')
  await page.getByRole('button', { name: '提交', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('这次提交没有被接受，请按当前提示修改后再提交。')
  await expect(page.getByRole('button', { name: '提交', exact: true })).toBeEnabled()
  expect(calls.commands).toHaveLength(1)
  await page.screenshot({ path: evidence('03-explicit-rejection.png'), fullPage: true })
})

test('unknown network result stays locked without another command', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  const calls = await installStubs(page, 'offline')
  await page.goto('/assistant')
  await page.getByLabel('客户名称').fill('星河科技')
  await page.getByRole('button', { name: '提交', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('发送状态待确认')
  await expect(page.getByRole('button', { name: '提交处理中…' })).toBeVisible()
  await page.waitForTimeout(300)
  expect(calls.commands).toHaveLength(1)
  await page.screenshot({ path: evidence('04-unknown-network.png'), fullPage: true })
})

function evidence(name: string): string {
  return `${process.env.CRM58_EVIDENCE ?? 'test-results/crm58'}/${name}`
}
