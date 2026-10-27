import { expect, test } from '@playwright/test'

/**
 * Renders the sales-assistant page with a server projection.
 * The browser does not parse dates; these fixtures are what the API would return.
 */

const draftBase = {
  customer: { status: 'ACCEPTED', value: '通力电梯' },
  content: { status: 'CANDIDATE', value: '叶老师反馈本月底会完成部署服务器准备。' },
  next_action: { status: 'CANDIDATE', value: '联系叶老师，确认部署服务器的准备情况' },
  next_follow_time: { status: 'CANDIDATE', value: '30 号' },
  quality_score: { status: 'CANDIDATE', value: '86' }
}

const monthTask = {
  public_id: 'ast_temporal_month',
  status: 'ACTIVE',
  goal: '记录跟进',
  activity_kind: 'FOLLOW_UP',
  draft: draftBase,
  waiting: {
    type: 'FIELD',
    field: 'temporal_choice',
    question_id: 'q_time_month',
    prompt: '“30号”是指本月30号还是下月30号？',
    action_id: 'act_month',
    expected_version: 4,
    candidates: [
      { id: 'month-current', label: '本月30号' },
      { id: 'month-next', label: '下月30号' }
    ]
  },
  committed: [],
  budget_steps: 2,
  budget_max_steps: 50,
  version: 4,
  last_modified_time: '2026-10-27T07:00:00',
  processing_turn_id: null,
  processing_turn_status: null
}

const confirmTask = {
  ...monthTask,
  public_id: 'ast_temporal_confirm',
  version: 5,
  draft: {
    ...draftBase,
    next_follow_time: { status: 'CANDIDATE', value: '30 号' },
    content_json: {
      customer_commitments: [{ text: '叶老师预计本月底完成部署服务器准备。' }],
      sales_follow_up_text: '你将在10月30号联系叶老师，确认部署服务器的准备情况。',
      temporal_notices: ['已识别下次跟进日期为2026-10-30，未指定具体时刻。']
    }
  },
  waiting: {
    type: 'CONFIRMATION',
    field: 'activity_write',
    question_id: 'q_confirm',
    prompt: '确认后写入这条客户活动。',
    action_id: 'act_confirm',
    expected_version: 5,
    fingerprint: 'abc',
    candidates: [],
    confirmation_payload: {
      kind: 'activity_write',
      preview: {
        customer_name: '通力电梯',
        activity_kind: 'OTHER_FOLLOW_UP',
        title: '其他跟进',
        summary: '叶老师反馈本月底会完成部署服务器准备。',
        content_json: {
          customer_commitments: [{ text: '叶老师预计本月底完成部署服务器准备。' }],
          sales_follow_up_text: '你将在10月30号联系叶老师，确认部署服务器的准备情况。',
          temporal_notices: ['已识别下次跟进日期为2026-10-30，未指定具体时刻。']
        },
        source_content: '叶老师反馈本月底会完成；等 30 号再找叶老师确认。',
        score: 86,
        score_reason: '客户承诺和下一步都清楚。',
        next_action: '联系叶老师，确认部署服务器的准备情况',
        next_follow_time: '2026-10-30T00:00:00',
        next_follow_time_text: '30 号',
        next_follow_time_granularity: 'DATE'
      }
    }
  }
}

const conversationFor = (task: typeof monthTask) => ({
  public_id: 'conv_temporal',
  version: 1,
  focused_task: task,
  pending_choice: null,
  has_pending_request: false,
  messages: [
    {
      id: `msg_${task.public_id}`,
      role: 'assistant',
      text: task.waiting.prompt,
      at: '2026-10-27T07:00:00Z',
      task,
      boundary: null,
      outcome: null
    }
  ],
  older_cursor: null
})

const token = (() => {
  const encode = (value: object) =>
    Buffer.from(JSON.stringify(value))
      .toString('base64')
      .replace(/=/g, '')
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
  const exp = Math.floor(Date.now() / 1000) + 86_400
  return `${encode({ alg: 'none', typ: 'JWT' })}.${encode({ exp })}.sig`
})()

test.beforeEach(async ({ page }) => {
  await page.addInitScript((value) => {
    window.localStorage.setItem('token', value)
  }, token)
  await page.route('**/api/v1/**', async (route) => {
    const url = route.request().url()
    if (url.includes('/v1/teams/user-teams')) {
      await route.fulfill({
        json: {
          teams: [{ id: 1, name: '验证团队', code: 'VERIFY', owner_id: '2', created_at: '2026-10-01T00:00:00' }],
          current_team_id: 1
        }
      })
      return
    }
    if (url.includes('/v1/auth/me/permissions')) {
      await route.fulfill({
        json: {
          permissions: [{ id: 1, code: 'customer:activity:create', name: '创建活动', resource: 'customer', action: 'create', scope: null, description: null }],
          total: 1,
          cached: false
        }
      })
      return
    }
    if (url.includes('/v1/auth/me')) {
      await route.fulfill({
        json: {
          id: 2, name: '验证销售', email: 'verify@example.invalid', mobile: null, avatar_url: null,
          employee_no: null, region: null, status: 'ACTIVE', created_at: '2026-10-01T00:00:00', updated_at: null, roles: []
        }
      })
      return
    }
    if (!url.includes('/v1/assistant/conversation/open')) {
      await route.fulfill({ status: 200, json: {} })
    } else {
      await route.fallback()
    }
  })
})

test('month choice and confirmation card render the server projection', async ({ page }) => {
  const shots = '/Users/eddie/Code/CRMWolf/.worktrees/crm-44-temporal-evidence/.xwing-task/crmwolf/evidence'
  await page.route('**/api/v1/assistant/conversation/open', async (route) => {
    await route.fulfill({ json: conversationFor(monthTask) })
  })
  await page.goto('/assistant')
  await expect(page.getByText('“30号”是指本月30号还是下月30号？')).toBeVisible()
  await expect(page.getByRole('button', { name: '本月30号' })).toBeVisible()
  await expect(page.getByRole('button', { name: '下月30号' })).toBeVisible()
  await page.screenshot({ path: `${shots}/01-month-choice.png`, fullPage: true })

  await page.unroute('**/api/v1/assistant/conversation/open')
  await page.route('**/api/v1/assistant/conversation/open', async (route) => {
    await route.fulfill({ json: conversationFor(confirmTask) })
  })
  await page.goto('/assistant')
  await expect(page.getByText('客户事实')).toBeVisible()
  await expect(page.getByText('叶老师预计本月底完成部署服务器准备。')).toBeVisible()
  await expect(page.getByText('你将在10月30号联系叶老师，确认部署服务器的准备情况。')).toBeVisible()
  await expect(page.getByText('已识别下次跟进日期为2026-10-30，未指定具体时刻。')).toBeVisible()
  await expect(page.getByText('2026-10-30', { exact: true })).toBeVisible()
  await page.screenshot({ path: `${shots}/02-confirmation-card.png`, fullPage: true })
})
