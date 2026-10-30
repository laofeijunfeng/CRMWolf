import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test, type Page, type Route } from '@playwright/test'

/**
 * Real /assistant page with the conversation API intercepted.
 * Proves the activity card keeps facts visible, folds explanation, and does not repeat success.
 */
const evidence = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../.xwing-task/crmwolf/evidence')
const at = '2026-10-30T02:00:00'
const widths = [375, 390, 768, 1024, 1440] as const

function task() {
  return {
    public_id: 'ast_fixture',
    status: 'ACTIVE',
    goal: '记录客户活动',
    activity_kind: 'WECHAT_FOLLOW_UP',
    version: 4,
    draft: {
      customer: { status: 'ACCEPTED', value: '上海期货信息技术有限公司' },
      content: { status: 'ACCEPTED', value: '今天通过微信对齐了合同和发票。' },
      next_action: { status: 'ACCEPTED', value: '11 月 15 日跟进付款' },
      next_follow_time: { status: 'ACCEPTED', value: '2026-11-15' }
    },
    waiting: null,
    committed: [{ kind: 'customer_activity', public_id: 'act_ok' }],
    budget_steps: 2,
    budget_max_steps: 50,
    processing_turn_id: null,
    processing_turn_status: null,
    reprocess_turn_id: null
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

function message(id: string, text: string, outcome: string | null, ui: Record<string, unknown> | null) {
  return { id, role: 'assistant', text, at, task: task(), boundary: null, outcome, ui }
}

const activityFacts = [
  { key: 'customer', label: '客户', value: '上海期货信息技术有限公司', group: 'write' },
  { key: 'summary', label: '摘要', value: '今天通过微信对齐了合同和发票。计划 11 月 15 日跟进付款。', group: 'write' },
  { key: 'next_action', label: '下一步', value: '11 月 15 日跟进付款', group: 'write' },
  { key: 'next_follow_time', label: '跟进时间', value: '11 月 15 日', group: 'write' },
  { key: 'activity_kind', label: '活动类型', value: '微信跟进', group: 'activity_kind', status_label: 'AI 已识别 · 高置信度', source: '从今天微信联系中识别' },
  { key: 'change_signal', label: '客户上下文判断', value: '推进', group: 'context', source: '这次出现了新的确认或下一步。' },
  { key: 'opportunity', label: '关联商机', value: '华东回款跟进 · 需求确认', group: 'context' },
  { key: 'context_evidence', label: '依据', value: '2026-09-23 微信沟通；2026-09-01 上次拜访', group: 'context' },
  { key: 'context_notice_1', label: '需要注意', value: '没有权限查看这部分内容', group: 'context' },
  { key: 'score', label: '内容质量', value: '76 / 100', group: 'score' },
  { key: 'score_reason', label: '评分依据', value: '主体、沟通内容和下一步都已整理', group: 'score' }
]

function activityBlock(state: 'ACTIVE' | 'READ_ONLY') {
  return {
    id: state === 'ACTIVE' ? 'b_confirm' : 'b_history',
    type: 'interaction',
    interaction_id: state === 'ACTIVE' ? 'ix_confirm' : 'ix_history',
    interaction_type: 'confirmation',
    business_action: 'confirm_activity_write',
    state,
    prompt: '确认后写入这条客户活动？',
    facts: activityFacts,
    options: [
      { value: 'confirm', label: '确认写入', disabled: false },
      { value: 'cancel', label: '取消', disabled: false }
    ],
    selection_mode: 'single',
    submit_on_select: true,
    submit_action_id: state === 'ACTIVE' ? 'act_confirm' : null
  }
}

async function fulfill(route: Route, status: number, body: unknown): Promise<void> {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

async function openWith(page: Page, blocks: ReadonlyArray<Record<string, unknown>>, outcome: string | null, text: string, state: 'final' | 'failed' = 'final'): Promise<void> {
  const ui = envelope(blocks, state)
  const conversation = {
    public_id: 'asc_fixture',
    version: 4,
    focused_task: task(),
    pending_choice: null,
    has_pending_request: false,
    older_cursor: null,
    messages: [
      { id: 'user-1', role: 'user', text: '今天微信联系了上海期货信息技术有限公司，11 月 15 日再跟进付款。', at, task: null, boundary: null, outcome: null, ui: null },
      message('assistant-1', text, outcome, ui)
    ]
  }
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
    if (pathname.endsWith('/assistant/conversation/open') || pathname.endsWith('/assistant/conversation')) {
      return fulfill(route, 200, conversation)
    }
    return fulfill(route, 404, { detail: pathname })
  })
  await page.goto('/assistant')
}

async function assertNoOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(1)
}

test('activity confirmation keeps facts visible and folds the basis', async ({ page }) => {
  await openWith(page, [activityBlock('ACTIVE')], null, '确认后写入这条客户活动？')
  await expect(page.getByRole('heading', { name: '确认写入客户活动' })).toBeVisible()
  await expect(page.getByText('待确认', { exact: true })).toBeVisible()
  await expect(page.getByText('本次将写入 CRM')).toHaveCount(0)
  await expect(page.getByText('等待你确认')).toHaveCount(0)
  await expect(page.getByText('今天通过微信对齐了合同和发票。计划 11 月 15 日跟进付款。')).toBeVisible()
  await expect(page.getByText('没有权限查看这部分内容')).toBeVisible()
  await expect(page.getByText('从今天微信联系中识别')).toBeHidden()
  await expect(page.getByText('2026-09-23 微信沟通')).toBeHidden()
  await expect(page.getByRole('button', { name: '推进' })).toHaveCount(0)
  const confirm = page.getByRole('button', { name: '确认写入' })
  const cancel = page.getByRole('button', { name: '取消' })
  await expect(confirm).toBeVisible()
  await expect(cancel).toBeVisible()
  const confirmBox = await confirm.boundingBox()
  expect(confirmBox?.height ?? 0).toBeGreaterThanOrEqual(44)
  const basis = page.getByText('查看依据', { exact: true })
  const basisBox = await basis.boundingBox()
  expect(basisBox?.height ?? 0).toBeGreaterThanOrEqual(44)
  await page.evaluate(() => {
    document.querySelectorAll('.overflow-y-auto').forEach((node) => { node.scrollTop = 0 })
  })

  await page.setViewportSize({ width: 1440, height: 900 })
  await assertNoOverflow(page)
  await page.locator('.activity-card').screenshot({ path: path.join(evidence, 'crm66-confirm-1440.png') })
  await page.setViewportSize({ width: 390, height: 844 })
  await assertNoOverflow(page)
  await page.screenshot({ path: path.join(evidence, 'crm66-confirm-390.png'), fullPage: true })
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 })
    await assertNoOverflow(page)
  }
  await page.setViewportSize({ width: 768, height: 900 })
  await assertNoOverflow(page)
  await page.screenshot({ path: path.join(evidence, 'crm66-confirm-768.png'), fullPage: true })

  await basis.focus()
  await expect(basis).toBeFocused()
  await basis.click()
  await expect(page.getByText('从今天微信联系中识别')).toBeVisible()
  await expect(page.getByText('2026-09-23 微信沟通')).toBeVisible()
})

test('success receipt states the write once', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await openWith(page, [{
    id: 'b_result_1',
    type: 'action_result',
    action_id: 'result-1',
    status: 'SUCCESS',
    title: '活动已写入',
    message: '客户：上海期货信息技术有限公司\n活动类型：微信跟进\n下一步：11 月 15 日跟进付款'
  }], 'activity_written', '活动已写入')
  await expect(page.getByText('活动已写入')).toHaveCount(1)
  await expect(page.getByText('客户：上海期货信息技术有限公司')).toBeVisible()
  await expect(page.getByText('活动类型：微信跟进')).toBeVisible()
  await expect(page.getByText('下一步：11 月 15 日跟进付款')).toBeVisible()
  await expect(page.getByText('执行过程')).toHaveCount(0)
  await expect(page.getByText('原始内容已保存')).toHaveCount(0)
  await assertNoOverflow(page)
  await page.screenshot({ path: path.join(evidence, 'crm66-success-1440.png'), fullPage: true })
  await page.setViewportSize({ width: 375, height: 812 })
  await assertNoOverflow(page)
  await page.screenshot({ path: path.join(evidence, 'crm66-success-375.png'), fullPage: true })
})

test('unknown commit stays a warning without a write retry', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  const text = '客户活动写入结果待核对。请先刷新或查询结果，不要重复提交。'
  await openWith(page, [{
    id: 'b_notice_1', type: 'notice', tone: 'warning', title: '结果待核对', text
  }], 'failure', text)
  await expect(page.getByText('结果待核对', { exact: true })).toBeVisible()
  await expect(page.getByText('活动已写入')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '重试' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '重新写入' })).toHaveCount(0)
  await assertNoOverflow(page)
  await page.screenshot({ path: path.join(evidence, 'crm66-unknown-1440.png'), fullPage: true })
})

test('safe failure keeps the saved-content sentence and no unauthorized retry', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 900 })
  const text = '活动类型判断未完成，尚未写入客户活动。原始内容已保存，本次没有产生 CRM 活动。'
  await openWith(page, [{
    id: 'b_error_1', type: 'error', code: 'UPSTREAM_TIMEOUT', title: '活动类型判断未完成', message: text, retryable: true, trace_id: null
  }], 'failure', text, 'failed')
  await expect(page.getByText('活动类型判断未完成', { exact: true })).toBeVisible()
  await expect(page.getByText('原始内容已保存，本次没有产生 CRM 活动。')).toBeVisible()
  await expect(page.getByText('活动已写入')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '重试' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '重新处理' })).toHaveCount(0)
  await assertNoOverflow(page)
  await page.screenshot({ path: path.join(evidence, 'crm66-failure-1024.png'), fullPage: true })
})

test('history replay has frozen facts and no write actions', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await openWith(page, [activityBlock('READ_ONLY')], null, '确认后写入这条客户活动？')
  await expect(page.getByRole('heading', { name: '客户活动' })).toBeVisible()
  await expect(page.getByText('历史只读')).toBeVisible()
  await expect(page.getByText('仅回看当时冻结的内容，不代表当前客户状态。')).toBeVisible()
  await expect(page.getByText('今天通过微信对齐了合同和发票。计划 11 月 15 日跟进付款。')).toBeVisible()
  await expect(page.getByRole('button', { name: '确认写入' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '取消' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '修改类型' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '推进' })).toHaveCount(0)
  await expect(page.getByText('从今天微信联系中识别')).toBeHidden()
  await assertNoOverflow(page)
  await page.screenshot({ path: path.join(evidence, 'crm66-history-1440.png'), fullPage: true })
})
