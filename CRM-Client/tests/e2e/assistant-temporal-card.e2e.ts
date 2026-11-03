import { expect, test, type Page } from '@playwright/test'
import type { AssistantTaskView, ConversationView } from '../../src/schemas/assistant-contracts'

/**
 * Real /assistant page for the CRM-62/CRM-76 confirmation card.
 * The conversation is intercepted; the card itself is the worktree Vue component.
 */

interface FollowTimeFact {
  value: string
  status_label?: string
  source?: string
}

interface CardCase {
  state: 'ACTIVE' | 'READ_ONLY'
  /** What the rep said about follow-up time; the user message and card evidence both come from it. */
  said: string
  followTime: FollowTimeFact
}

const at = '2026-10-30T09:00:00'
const prompt = '确认后写入这条客户活动？'

function task(said: string): AssistantTaskView {
  const utterance = `客户说下个月初付款，${said}跟进下付款进展`
  return {
    public_id: 'ast_temporal',
    status: 'ACTIVE',
    goal: utterance,
    activity_kind: 'FOLLOW_UP',
    version: 4,
    draft: {
      customer: { status: 'ACCEPTED', value: '通力电梯' },
      content: { status: 'CANDIDATE', value: utterance },
      next_action: { status: 'CANDIDATE', value: '跟进付款进展' },
      next_follow_time: { status: 'CANDIDATE', value: said }
    },
    waiting: {
      type: 'CONFIRMATION',
      field: 'activity_write',
      question_id: 'q_confirm',
      prompt,
      action_id: 'act_confirm',
      expected_version: 4,
      fingerprint: 'a' * 64,
      confirmation_payload: {
        kind: 'activity_write',
        preview: {
          customer_name: '通力电梯',
          activity_kind: 'PHONE_FOLLOW_UP',
          channel_status: 'recognized',
          channel_status_label: '已识别',
          title: '电话跟进',
          summary: `${utterance}。`,
          content_json: {},
          source_content: utterance,
          score: 80,
          score_reason: '客户承诺和跟进时间已分开',
          next_action: '跟进付款进展',
          next_follow_time_text: said,
          next_follow_time_granularity: 'DATE'
        }
      }
    },
    committed: [],
    budget_steps: 2,
    budget_max_steps: 50
  }
}

function envelope(card: CardCase) {
  return {
    schema_version: 'crm.agent.ui.v1',
    message_id: 1,
    turn_id: 'card',
    role: 'assistant',
    state: 'final',
    suggested_actions: [],
    metadata: { display: 'MESSAGE', route: 'WORKFLOW', accessibility_label: prompt },
    blocks: [{
      id: 'b_interaction_1',
      type: 'interaction',
      interaction_id: 'ix-card',
      interaction_type: 'confirmation',
      business_action: 'confirm_activity_write',
      state: card.state,
      prompt,
      fields: [],
      facts: [
        { key: 'customer', label: '客户', value: '通力电梯', group: 'write', options: [] },
        { key: 'summary', label: '摘要', value: `客户说下个月初付款，${card.said}跟进下付款进展。`, group: 'write', options: [] },
        { key: 'next_action', label: '下一步', value: '跟进付款进展', group: 'write', options: [] },
        { key: 'customer_commitment', label: '客户承诺', value: '下个月初付款（模糊时间，未确定具体日期）', group: 'write', options: [] },
        { key: 'next_follow_time', label: '跟进时间', group: 'write', options: [], ...card.followTime },
        { key: 'activity_kind', label: '活动类型', value: '电话跟进', group: 'activity_kind', status_label: '已识别', options: [] }
      ],
      options: [
        { value: 'confirm', label: '确认写入', disabled: false },
        { value: 'cancel', label: '取消', disabled: false }
      ],
      selection_mode: 'single',
      submit_on_select: true,
      submit_label: '提交',
      allow_cancel: false,
      submit_action_id: card.state === 'ACTIVE' ? 'act_confirm' : null
    }]
  }
}

function conversation(card: CardCase): ConversationView {
  const current = task(card.said)
  return {
    public_id: 'asc_temporal',
    version: 4,
    focused_task: current,
    pending_choice: null,
    has_pending_request: false,
    older_cursor: null,
    messages: [
      {
        id: 'user-1',
        role: 'user',
        text: current.goal,
        at,
        task: null,
        boundary: null,
        outcome: null,
        ui: null
      },
      {
        id: 'card',
        role: 'assistant',
        text: prompt,
        at,
        task: current,
        boundary: null,
        outcome: null,
        ui: envelope(card)
      }
    ]
  }
}

async function installStubs(page: Page, card: CardCase): Promise<void> {
  const state = conversation(card)
  await page.addInitScript(() => {
    localStorage.setItem('token', 'ui.fixture.not-a-credential')
  })
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const json = (body: unknown) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body)
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
    return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: path }) })
  })
}

const cases: Array<CardCase & { name: string, shot: string }> = [
  {
    name: 'date without a spoken time shows the 09:00 default tag',
    shot: 'crm76-date-default-time.png',
    state: 'ACTIVE',
    said: '11 月 5 号',
    followTime: { value: '2026-11-05（周四）09:00', status_label: '未说时刻，默认 09:00 提醒', source: '原话：“11 月 5 号”' }
  },
  {
    name: 'spoken time shows no default tag',
    shot: 'crm76-datetime-spoken.png',
    state: 'ACTIVE',
    said: '11 月 5 号下午 3 点',
    followTime: { value: '2026-11-05（周四）15:00', source: '原话：“11 月 5 号下午 3 点”' }
  },
  {
    name: 'history card keeps the frozen year',
    shot: 'crm76-history-frozen-year.png',
    state: 'READ_ONLY',
    said: '明年 1 月 15 号',
    followTime: { value: '2027-01-15（周五）09:00', status_label: '未说时刻，默认 09:00 提醒', source: '原话：“明年 1 月 15 号”' }
  }
]

for (const card of cases) {
  test(`confirmation card follow time: ${card.name}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1280, height: 900 })
    await installStubs(page, card)
    await page.goto('/assistant')
    await expect(page.getByText('客户承诺', { exact: true })).toBeVisible()
    await expect(page.getByText('下个月初付款（模糊时间，未确定具体日期）', { exact: true })).toBeVisible()
    await expect(page.getByText('跟进时间', { exact: true })).toBeVisible()
    const time = page.locator('.activity-time')
    await expect(time.locator('.activity-time-value')).toHaveText(card.followTime.value)
    const tag = time.locator('.activity-pill')
    if (card.followTime.status_label) await expect(tag).toHaveText(card.followTime.status_label)
    else await expect(tag).toHaveCount(0)
    await expect(page.locator('.activity-time + .activity-caption')).toHaveText(card.followTime.source ?? '')
    await page.screenshot({ path: testInfo.outputPath(card.shot), fullPage: true })
  })
}
