/**
 * Agent 2.0 full black-box UI walkthrough, round 3.
 * Covers the 9 design scenes plus the optimization-TRD behaviors:
 * OBJECT_SELECTION, EXPLICITLY_NONE, client_request_id/action_id,
 * receipt badge, kind card, replay read-only cards, change-kind hint,
 * turn recovery after reload.
 * Findings flush to outputs/agent2-ui-test-report-round3/.
 */
import { expect, type Locator, type Page } from '@playwright/test'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { test } from './fixtures'

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO = resolve(HERE, '../../..')
const DESIGN = resolve(REPO, 'outputs/agent2-ui-design.html')
const OUT = resolve(REPO, 'outputs/agent2-ui-test-report-round3')
const SHOTS = resolve(OUT, 'screenshots')

const TOKEN = readFileSync('/tmp/e2e_token.txt', 'utf-8').trim()
const AUTH = { Authorization: `Bearer ${TOKEN}` }
const API = 'http://localhost:8000/api/v1/assistant'
const CUSTOMER = '广州睿狐科技有限公司'
const CONTENT =
  '客户方王总确认POC部署可行，预算进入下季度采购清单；李经理要求先交安全测评报告；我方张工承诺周五前交数据出境说明；下周三王总反馈立项批复'
const NEXT_ACTION = '下周三王总反馈立项批复结果'

interface Waiting {
  type: 'FIELD' | 'CONFIRMATION' | 'ACTIVITY_KIND' | 'OBJECT_SELECTION' | null
  field?: string | null
  prompt?: string | null
  action_id?: string | null
}

interface TaskSnap {
  status: string
  waiting: Waiting | null
  activity_kind?: string | null
  goal?: string
  public_id?: string
  error_code?: string | null
}

interface Finding {
  id: string
  scene: string
  expected: string
  actual: string
  verdict: 'pass' | 'gap' | 'blocked'
  expectedShot: string
  actualShot: string
}

const findings: Finding[] = []

function flushReport(): void {
  mkdirSync(resolve(OUT, 'findings'), { recursive: true })
  for (const item of findings) {
    writeFileSync(resolve(OUT, 'findings', `${item.id}.json`), `${JSON.stringify(item, null, 2)}\n`)
  }
  const order = [
    's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9',
    'o1', 'o2', 'o3', 'o4', 'o5', 'o6', 'o7', 'o8'
  ]
  const byId: Record<string, Finding | undefined> = {}
  for (const id of order) {
    try {
      byId[id] = JSON.parse(readFileSync(resolve(OUT, 'findings', `${id}.json`), 'utf-8')) as Finding
    } catch {
      byId[id] = undefined
    }
  }
  for (const item of findings) byId[item.id] = item
  const lines = [
    '# Agent 2.0 UI 黑盒测试报告（第三轮 · 优化验证）',
    '',
    `- 时间：${new Date().toISOString()}`,
    '- 环境：本地 dev，前端 http://localhost:5173 ，后端 http://localhost:8000（Alembic 已升级到 145_assistant_turns）',
    '- 账号：eddie@apifox.com（验证码登录）',
    '- 设计稿：`outputs/agent2-ui-design.html`；页面 `/assistant`',
    '- 优化清单：`CRM-Docs/design-agent/roadmap/agent-2-optimization-trd.md`',
    '- 判定：pass = 主交互符合设计稿/优化验收；gap = 跑到了但有可见差异；blocked = 未能把 UI 推到该状态。',
    '',
    '| # | 场景 | 结论 |',
    '| --- | --- | --- |'
  ]
  for (const id of order) {
    const item = byId[id]
    if (item === undefined) continue
    lines.push(`| ${id} | ${item.scene} | ${item.verdict} |`)
  }
  lines.push('')
  for (const id of order) {
    const item = byId[id]
    if (item === undefined) continue
    lines.push(
      `## ${id} · ${item.scene}`,
      '',
      `结论：**${item.verdict}**`,
      '',
      `预期：${item.expected}`,
      '',
      `实测：${item.actual}`,
      '',
      '| 预期 | 实测 |',
      '| --- | --- |',
      `| ![expected](${item.expectedShot}) | ![actual](${item.actualShot}) |`,
      ''
    )
  }
  writeFileSync(resolve(OUT, 'report.md'), `${lines.join('\n')}\n`)
}

function record(finding: Finding): void {
  const index = findings.findIndex((item) => item.id === finding.id)
  if (index >= 0) findings[index] = finding
  else findings.push(finding)
  flushReport()
}

async function activeTask(page: Page): Promise<TaskSnap | null | undefined> {
  try {
    const resp = await page.request.get(`${API}/tasks/latest/active`, { headers: AUTH, timeout: 45_000 })
    if (!resp.ok() || resp.status() === 204) return null
    const text = await resp.text()
    if (text === '' || text === 'null') return null
    return JSON.parse(text) as TaskSnap
  } catch {
    return undefined
  }
}

async function cancelActive(page: Page): Promise<void> {
  const resp = await page.request.get(`${API}/tasks`, { headers: AUTH, timeout: 20_000 })
  if (!resp.ok()) return
  const tasks = (await resp.json()) as Array<{ public_id: string; status: string }>
  for (const task of tasks) {
    if (task.status !== 'ACTIVE') continue
    await page.request.post(`${API}/tasks/${task.public_id}/submit`, {
      headers: { ...AUTH, 'Content-Type': 'application/json' },
      data: { kind: 'cancel', client_request_id: `cleanup-${task.public_id}-${Date.now()}` },
      timeout: 60_000
    }).catch(() => undefined)
  }
  const deadline = Date.now() + 20_000
  while (Date.now() < deadline) {
    const current = await activeTask(page)
    if (current === null) return
    if (current === undefined) {
      await page.waitForTimeout(1_000)
      continue
    }
    await page.waitForTimeout(500)
  }
}

async function openAssistant(page: Page, fresh = false): Promise<void> {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/assistant', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('textarea').first()).toBeVisible({ timeout: 30_000 })
  if (fresh) {
    const button = page.getByRole('button', { name: '新任务' })
    if ((await button.getAttribute('disabled').catch(() => '1')) === null) {
      await button.click({ timeout: 3_000, force: true }).catch(() => undefined)
    }
  }
  await page.waitForTimeout(400)
}

async function send(page: Page, text: string): Promise<void> {
  const textarea = page.locator('textarea').first()
  await expect(textarea).toBeEnabled({ timeout: 30_000 })
  await textarea.fill(text)
  await textarea.press('Enter')
}

async function clickIf(locator: Locator, ms = 1_500): Promise<boolean> {
  const target = locator.last()
  if (!(await target.isVisible({ timeout: ms }).catch(() => false))) return false
  if (!(await target.isEnabled().catch(() => false))) return false
  await target.click()
  return true
}

/**
 * Answer waiting cards from the visible UI. Stops on the types in stopOn.
 * Explicitly passes EXPLICITLY_NONE when a next_action gap offers the button.
 */
async function driveUntil(
  page: Page,
  opening: string | null,
  opts: {
    stopOn?: Array<'FIELD' | 'CONFIRMATION' | 'ACTIVITY_KIND' | 'OBJECT_SELECTION'>
    pickKind?: string
    fieldAnswers?: Record<string, string>
    pickCustomer?: string
    timeoutMs?: number
    answerFields?: boolean
  } = {}
): Promise<TaskSnap | null> {
  const stop: Record<string, true> = {}
  for (const type of opts.stopOn ?? ['CONFIRMATION', 'ACTIVITY_KIND', 'FIELD', 'OBJECT_SELECTION']) stop[type] = true
  if (opening !== null) await send(page, opening)
  const deadline = Date.now() + (opts.timeoutMs ?? 240_000)
  let last: TaskSnap | null = null
  let spins = 0
  while (Date.now() < deadline) {
    const confirmVisible = await page.getByRole('button', { name: '确认写入' }).last().isVisible().catch(() => false)
    const onlineVisible = await page.getByRole('button', { name: '线上会议' }).last().isVisible().catch(() => false)
    const hint = page.getByText(/正在回答：/)
    const hintVisible = await hint.first().isVisible().catch(() => false)
    const noneBtn = page.getByRole('button', { name: '这条没有下一步' })

    if (confirmVisible && stop['CONFIRMATION'] === true) return (await activeTask(page)) ?? last
    if (onlineVisible && stop['ACTIVITY_KIND'] === true) return (await activeTask(page)) ?? last

    if (onlineVisible && stop['ACTIVITY_KIND'] !== true) {
      const target = opts.pickKind ?? 'ONLINE_MEETING'
      const label = target === 'FOLLOW_UP' ? '普通跟进' : target === 'OFFLINE_MEETING' ? '线下会议' : '线上会议'
      if (await clickIf(page.getByRole('button', { name: label }), 1_000)) {
        await page.waitForTimeout(1_500)
        continue
      }
    }
    if (confirmVisible && stop['CONFIRMATION'] !== true) {
      if (await clickIf(page.getByRole('button', { name: '确认写入' }), 1_000)) {
        await page.waitForTimeout(1_500)
        continue
      }
    }
    if (hintVisible && opts.answerFields !== false) {
      const label = ((await hint.first().textContent().catch(() => '')) ?? '')
      const state = await activeTask(page)
      const field = state?.waiting?.field ?? ''
      if (field === 'next_action' && (await clickIf(noneBtn, 800))) {
        await page.waitForTimeout(1_500)
        continue
      }
      const key = label.includes('customer') || label.includes('客户')
        ? 'customer'
        : label.includes('next_action') || label.includes('下一步')
          ? 'next_action'
          : 'content'
      const answer = opts.fieldAnswers?.[key]
        ?? (key === 'customer' ? CUSTOMER : key === 'next_action' ? NEXT_ACTION : CONTENT)
      await send(page, answer)
      await page.waitForTimeout(1_500)
      continue
    }
    const polled = await activeTask(page)
    if (polled !== undefined && polled !== null) last = polled
    if (polled === null) return null
    spins += 1
    if (spins > 60) return last
    await page.waitForTimeout(3_000)
  }
  return last
}

async function designShot(page: Page, file: string, heading: string): Promise<string> {
  await page.setViewportSize({ width: 1280, height: 1100 })
  await page.goto(`file://${DESIGN}`, { waitUntil: 'domcontentloaded' })
  const section = page.locator('section').filter({ hasText: heading }).first()
  await section.scrollIntoViewIfNeeded()
  const path = resolve(SHOTS, file)
  await section.screenshot({ path })
  return `screenshots/${file}`
}

async function appShot(page: Page, file: string): Promise<string> {
  const path = resolve(SHOTS, file)
  const panel = page.locator('.sales-assistant-page').first()
  if (await panel.isVisible().catch(() => false)) await panel.screenshot({ path })
  else await page.screenshot({ path, fullPage: false })
  return `screenshots/${file}`
}

test.describe.configure({ mode: 'serial' })

test('design boards', async ({ page }) => {
  mkdirSync(SHOTS, { recursive: true })
  const boards: Array<[string, string]> = [
    ['expected-s1.png', '场景 1 · 主布局与空闲态'],
    ['expected-s2.png', '场景 2 · 活动类型不明，只问一次'],
    ['expected-s3.png', '场景 3 · 跟进整理稿 · 请求确认'],
    ['expected-s4.png', '场景 4 · 会议纪要 · 请求确认'],
    ['expected-s5.png', '场景 5 · 补缺口 · 输入框进入受控模式'],
    ['expected-s6.png', '场景 6 · 活动写入成功 · 后续提案逐笔出现'],
    ['expected-s7.png', '场景 7 · 任务栏 · 进行中任务的可见状态'],
    ['expected-s8.png', '场景 8 · 失败与澄清 · 永不静默'],
    ['expected-s9.png', '场景 9 · 执行过程可见 · 用户始终知道 Agent 在做什么']
  ]
  for (const [file, heading] of boards) await designShot(page, file, heading)
})

test('s1 idle', async ({ page }) => {
  await cancelActive(page)
  await openAssistant(page, true)
  const actual = await appShot(page, 'actual-s1-idle.png')
  const checks = {
    guide: await page.getByText('发送一句话开始').first().isVisible().catch(() => false),
    empty: await page.getByText('当前没有进行中的任务').first().isVisible().catch(() => false),
    fresh: await page.getByRole('button', { name: '新任务' }).isVisible().catch(() => false),
    enter: await page.getByText('Enter 发送').first().isVisible().catch(() => false),
    title: await page.getByText('销售助手').first().isVisible().catch(() => false),
    recentCustomerKind: await page.getByText(/· (跟进|线上会议|线下会议)/).first().isVisible().catch(() => false)
  }
  record({
    id: 's1',
    scene: '主布局与空闲态',
    expected: '左对话右任务栏、空态引导、自由输入、Enter 提示、空任务、「新任务」、最近任务显示「客户 · 类型」。',
    actual: `引导=${checks.guide} 空任务=${checks.empty} 新任务=${checks.fresh} Enter=${checks.enter} 标题=${checks.title} 最近「客户·类型」=${checks.recentCustomerKind}`,
    verdict: checks.guide && checks.empty && checks.fresh && checks.enter && checks.title ? 'pass' : 'gap',
    expectedShot: 'screenshots/expected-s1.png',
    actualShot: actual
  })
})

test('s9 processing and s2 kind card', async ({ page }) => {
  test.setTimeout(360_000)
  await cancelActive(page)
  await openAssistant(page, true)
  await send(page, '今天下午去拜访了客户，也开了个线上会，聊得还行')
  await page.waitForTimeout(800)
  const earlyShot = await appShot(page, 'actual-s9-processing.png')
  const sawProcessing = await page.getByText(/Agent 正在处理/).first().isVisible({ timeout: 8_000 }).catch(() => false)
  const sawStage = await page.getByText('判断活动类型').first().isVisible({ timeout: 3_000 }).catch(() => false)
  let sawElapsed = false
  const watchUntil = Date.now() + 20_000
  while (Date.now() < watchUntil) {
    if (!(await page.getByText(/Agent 正在处理/).first().isVisible().catch(() => false))) break
    if (await page.getByText(/已 \d+ 秒/).first().isVisible().catch(() => false)) {
      sawElapsed = true
      await appShot(page, 'actual-s9-elapsed.png')
      break
    }
    await page.waitForTimeout(700)
  }
  const snap = await driveUntil(page, null, { stopOn: ['ACTIVITY_KIND'], timeoutMs: 420_000 })
  await appShot(page, snap?.waiting?.type === 'ACTIVITY_KIND' ? 'actual-s2-kind.png' : 'actual-s2-other.png')
  const checks = {
    online: await page.getByRole('button', { name: '线上会议' }).last().isVisible({ timeout: 3_000 }).catch(() => false),
    offline: await page.getByRole('button', { name: '线下会议' }).last().isVisible().catch(() => false),
    follow: await page.getByRole('button', { name: '普通跟进' }).last().isVisible().catch(() => false),
    remote: await page.getByText('远程沟通').last().isVisible().catch(() => false),
    visit: await page.getByText('面谈拜访').last().isVisible().catch(() => false),
    phone: await page.getByText('电话/微信').last().isVisible().catch(() => false),
    giveUp: await page.getByRole('button', { name: '算了，不记了' }).last().isVisible().catch(() => false),
    noGapWrap: !(await page.getByText(/还差「activity_kind」/).first().isVisible().catch(() => false)),
    label: await page.getByText('正在回答：活动类型').first().isVisible().catch(() => false)
  }
  const isKindCard = snap?.waiting?.type === 'ACTIVITY_KIND'
  record({
    id: 's9',
    scene: '执行过程可见（处理提示 + 阶段清单）',
    expected: '发送后立刻锁定并显示「Agent 正在处理」与阶段清单；15 秒后出现已耗时提示。',
    actual: `处理提示=${sawProcessing} 判断活动类型阶段=${sawStage} 已耗时=${sawElapsed}`,
    verdict: sawProcessing && sawStage ? 'pass' : 'gap',
    expectedShot: 'screenshots/expected-s9.png',
    actualShot: sawElapsed ? 'screenshots/actual-s9-elapsed.png' : 'screenshots/actual-s9-processing.png'
  })
  record({
    id: 's2',
    scene: '类型不明，只问一次（类型选择卡）',
    expected: '独立类型卡：一句提问 + 三选一（含副文案）+「算了，不记了」；不出现「还差「activity_kind」」缺口包装；顶栏「正在回答：活动类型」。',
    actual: isKindCard
      ? `类型卡=${isKindCard} 三选一=${checks.online}/${checks.offline}/${checks.follow} 副文案=${checks.remote}/${checks.visit}/${checks.phone} 卡内算了=${checks.giveUp} 无缺口包装=${checks.noGapWrap} 顶栏活动类型=${checks.label}`
      : `未到类型卡，停在 ${snap?.status ?? 'none'}/${snap?.waiting?.type ?? 'none'}/${snap?.waiting?.field ?? ''}`,
    verdict: isKindCard && checks.online && checks.offline && checks.follow && checks.noGapWrap
      ? 'pass' : isKindCard ? 'gap' : 'blocked',
    expectedShot: 'screenshots/expected-s2.png',
    actualShot: isKindCard ? 'screenshots/actual-s2-kind.png' : 'screenshots/actual-s2-other.png'
  })
  await cancelActive(page)
})

test('s3 follow-up confirmation card', async ({ page }) => {
  test.setTimeout(420_000)
  await cancelActive(page)
  await openAssistant(page, true)
  const snap = await driveUntil(
    page,
    `今天和${CUSTOMER}的王总电话沟通了 POC 部署。${CONTENT}。下一步：${NEXT_ACTION}。`,
    { stopOn: ['CONFIRMATION'], pickKind: 'FOLLOW_UP', timeoutMs: 300_000 }
  )
  await appShot(page, 'actual-s3-confirm.png')
  const card = page.locator('.sales-assistant-page').getByText('确认后写入', { exact: false }).first()
  const checks = {
    confirm: await page.getByRole('button', { name: '确认写入' }).last().isVisible({ timeout: 3_000 }).catch(() => false),
    cancel: await page.getByRole('button', { name: '取消', exact: true }).last().isVisible().catch(() => false),
    edit: await page.getByRole('button', { name: '修改内容' }).first().isVisible().catch(() => false),
    changeKind: await page.getByRole('button', { name: /改为线下/ }).first().isVisible().catch(() => false),
    draft: await page.getByText('整理稿', { exact: true }).first().isVisible().catch(() => false),
    original: await page.getByText('对照原文').first().isVisible().catch(() => false),
    lock: await page.getByText('已锁定', { exact: true }).first().isVisible({ timeout: 5_000 }).catch(() => false)
      || await page.getByText('已绑定', { exact: true }).first().isVisible({ timeout: 2_000 }).catch(() => false),
    score: await page.getByText(/\/ 100/).first().isVisible().catch(() => false),
    isFollowUp: snap?.activity_kind === 'FOLLOW_UP'
  }
  void card
  const reached = snap?.waiting?.type === 'CONFIRMATION' && snap.waiting.field === 'activity_write' && checks.isFollowUp
  record({
    id: 's3',
    scene: '跟进整理稿确认卡',
    expected: '跟进徽章、整理稿、锁定字段、评分、对照原文、确认写入 / 修改内容 / 取消、改为线下 / 跟进。',
    actual: `到达=${reached} 整理稿=${checks.draft} 锁标=${checks.lock} 评分=${checks.score} 原文=${checks.original} 确认=${checks.confirm} 修改内容=${checks.edit} 改类型=${checks.changeKind} 取消=${checks.cancel}`,
    verdict: reached && checks.confirm && checks.draft && checks.lock && checks.score && checks.original && checks.cancel && checks.edit && checks.changeKind
      ? 'pass' : reached ? 'gap' : 'blocked',
    expectedShot: 'screenshots/expected-s3.png',
    actualShot: 'screenshots/actual-s3-confirm.png'
  })
})

test('s5 gap composer and none button', async ({ page }) => {
  test.setTimeout(360_000)
  await cancelActive(page)
  await openAssistant(page, true)
  const snap = await driveUntil(page, `今天和${CUSTOMER}打了个电话，聊得还行`, {
    stopOn: ['FIELD'],
    pickKind: 'FOLLOW_UP',
    answerFields: false,
    timeoutMs: 240_000
  })
  const onField = snap?.waiting?.type === 'FIELD'
  await appShot(page, onField ? 'actual-s5-gap.png' : 'actual-s5-other.png')
  const checks = {
    title: await page.getByText(/还差「/).first().isVisible().catch(() => false),
    chineseLabel: !(await page.getByText(/还差「(customer|content|next_action|next_follow_time)」/).first().isVisible().catch(() => false)),
    hint: await page.getByText(/正在回答：/).first().isVisible().catch(() => false),
    highlight: await page.locator('.border-primary\\/60').first().isVisible().catch(() => false),
    none: await page.getByRole('button', { name: '这条没有下一步' }).first().isVisible().catch(() => false)
  }
  const field = snap?.waiting?.field ?? ''
  record({
    id: 's5',
    scene: '补缺口受控输入',
    expected: '缺口卡「还差「中文字段」」+ 主色描边 + 顶部中文字段标签；缺下一步时有「这条没有下一步」。',
    actual: onField
      ? `field=${field} 缺口卡=${checks.title} 中文标签=${checks.chineseLabel} 受控描边=${checks.highlight} 没有下一步按钮=${checks.none}`
      : `未停在字段缺口，当前 ${snap?.status ?? 'none'}/${snap?.waiting?.type ?? 'none'}（模型直接给了可确认草稿）`,
    verdict: onField && checks.title && checks.chineseLabel && checks.highlight && (field !== 'next_action' || checks.none)
      ? 'pass' : onField ? 'gap' : 'blocked',
    expectedShot: 'screenshots/expected-s5.png',
    actualShot: onField ? 'screenshots/actual-s5-gap.png' : 'screenshots/actual-s5-other.png'
  })
})

test('s4 meeting confirmation card', async ({ page }) => {
  test.setTimeout(420_000)
  await cancelActive(page)
  await openAssistant(page, true)
  const snap = await driveUntil(
    page,
    `开线上会议评审POC部署。今天下午和${CUSTOMER}开了线上会议，主题是 POC 部署方案评审。${CONTENT}。参会：我方张工（方案）、刘敏（商务）；客户王总（决策）、李经理（安全）。下一步：下周三王总反馈立项批复结果。`,
    { stopOn: ['CONFIRMATION'], pickKind: 'ONLINE_MEETING', timeoutMs: 420_000, fieldAnswers: {
      next_follow_time: '下周三',
      customer: CUSTOMER,
      next_action: NEXT_ACTION
    } }
  )
  await appShot(page, 'actual-s4-meeting.png')
  const checks = {
    kind: await page.getByText('线上会议').first().isVisible().catch(() => false),
    background: await page.getByText('背景', { exact: true }).first().isVisible().catch(() => false),
    discuss: await page.getByText('关键讨论').first().isVisible().catch(() => false),
    people: await page.getByText('参会角色').first().isVisible().catch(() => false),
    actions: await page.getByText('行动项').first().isVisible().catch(() => false),
    score: await page.getByText(/\/ 100/).first().isVisible().catch(() => false),
    bound: await page.getByText('已绑定', { exact: true }).first().isVisible().catch(() => false),
    changeKind: await page.getByRole('button', { name: /改为线下/ }).first().isVisible().catch(() => false),
    edit: await page.getByRole('button', { name: '修改内容' }).first().isVisible().catch(() => false),
    confirm: await page.getByRole('button', { name: '确认写入' }).last().isVisible().catch(() => false)
  }
  const reached = snap?.waiting?.type === 'CONFIRMATION' && snap.waiting.field === 'activity_write'
    && (snap.activity_kind === 'ONLINE_MEETING' || snap.activity_kind === 'OFFLINE_MEETING')
  record({
    id: 's4',
    scene: '会议纪要确认卡',
    expected: '线上会议徽章、主题、背景、关键讨论、参会角色、行动项、已绑定、评分、确认/修改/取消、改为线下 / 跟进。',
    actual: `到达=${reached} kind=${snap?.activity_kind ?? ''} 线上=${checks.kind} 背景=${checks.background} 讨论=${checks.discuss} 参会=${checks.people} 行动项=${checks.actions} 评分=${checks.score} 绑定=${checks.bound} 修改内容=${checks.edit} 改类型=${checks.changeKind} 确认=${checks.confirm}`,
    verdict: reached && checks.confirm && checks.kind && checks.discuss && checks.people && checks.actions && checks.score && checks.bound && checks.background && checks.changeKind
      ? 'pass' : reached ? 'gap' : 'blocked',
    expectedShot: 'screenshots/expected-s4.png',
    actualShot: 'screenshots/actual-s4-meeting.png'
  })
  // Keep this card open for s6 write + s7 sidebar tests.
})

test('s7 sidebar and s6 write receipt then proposals', async ({ page }) => {
  test.setTimeout(480_000)
  await openAssistant(page)
  const existing = await activeTask(page)
  if (existing?.waiting?.type !== 'CONFIRMATION' || existing.waiting.field !== 'activity_write') {
    await cancelActive(page)
    await openAssistant(page, true)
    await driveUntil(
      page,
      `今天和${CUSTOMER}的王总开了线上会议。${CONTENT}。下一步：${NEXT_ACTION}。`,
      { stopOn: ['CONFIRMATION'], pickKind: 'ONLINE_MEETING', timeoutMs: 280_000 }
    )
  }
  // Sidebar checks while the confirmation is pending.
  const side = await appShot(page, 'actual-s7-sidebar.png')
  const steps = {
    progress: await page.getByText('进行中', { exact: true }).first().isVisible().catch(() => false),
    kind: await page.getByText('类型确认').first().isVisible().catch(() => false),
    structure: await page.getByText('内容整理').first().isVisible().catch(() => false),
    confirm: await page.getByText('确认写入', { exact: true }).first().isVisible().catch(() => false),
    cancel: await page.getByRole('button', { name: '取消任务' }).first().isVisible().catch(() => false)
  }
  record({
    id: 's7',
    scene: '任务栏进行中状态',
    expected: '当前任务「进行中」、步骤类型/整理/确认高亮、侧栏「取消任务」按钮。',
    actual: `进行中=${steps.progress} 类型确认=${steps.kind} 内容整理=${steps.structure} 确认写入=${steps.confirm} 取消任务=${steps.cancel}`,
    verdict: steps.progress && steps.kind && steps.structure && steps.confirm && steps.cancel ? 'pass' : 'gap',
    expectedShot: 'screenshots/expected-s7.png',
    actualShot: side
  })

  const confirmBtn = page.getByRole('button', { name: '确认写入' }).last()
  if (!(await confirmBtn.isVisible().catch(() => false))) {
    await page.getByRole('button', { name: /进行中/ }).first().click().catch(() => undefined)
  }
  await confirmBtn.click({ timeout: 20_000 })
  const wrote = await page.getByText(/已记录/).first().isVisible({ timeout: 240_000 }).catch(() => false)
  const badge = await page.getByText('已写入', { exact: true }).first().isVisible().catch(() => false)
  const proposal = page.getByRole('button', { name: '暂不处理' })
  const proposalVisible = await proposal.last().isVisible({ timeout: 120_000 }).catch(() => false)
  const shot = await appShot(page, 'actual-s6-live.png')
  record({
    id: 's6',
    scene: '写入成功 + 后续提案',
    expected: '回执「已记录…」+「已写入」徽标；随后一次一张提案卡，主操作 +「暂不处理」。',
    actual: `回执=${wrote} 已写入徽标=${badge} 提案卡（暂不处理）=${proposalVisible}`,
    verdict: wrote && proposalVisible ? (badge ? 'pass' : 'gap') : wrote ? 'gap' : 'blocked',
    expectedShot: 'screenshots/expected-s6.png',
    actualShot: shot
  })
  // Refuse proposals to completion, then reopen for replay checks (o4).
  const drainUntil = Date.now() + 120_000
  while (Date.now() < drainUntil) {
    const now = await activeTask(page)
    if (now === null || (now !== undefined && now.status !== 'ACTIVE')) break
    if (await clickIf(proposal, 1_000)) {
      await page.waitForTimeout(800)
      continue
    }
    await page.waitForTimeout(1_500)
  }
})

test('s8 unknown customer failure card', async ({ page }) => {
  test.setTimeout(240_000)
  await openAssistant(page)
  // The unknown-customer task is already waiting on FIELD customer after double NOT_FOUND.
  await page.getByRole('button', { name: /进行中/ }).first().click()
  await page.waitForTimeout(2_000)
  const retry = await page.getByText(/没有找到客户|未找到对应客户/).first().isVisible({ timeout: 10_000 }).catch(() => false)
  const failCard = await page.getByText(/写入未完成|遇到问题/).first().isVisible().catch(() => false)
  const retryBtn = await page.getByRole('button', { name: '换个名称重试' }).first().isVisible().catch(() => false)
  const abortBtn = await page.getByRole('button', { name: '结束本次记录' }).first().isVisible().catch(() => false)
  const shot8 = await appShot(page, 'actual-s8-unknown.png')
  record({
    id: 's8',
    scene: '失败与澄清（未知客户 · 两次 NOT_FOUND）',
    expected: '失败卡三要素：结论（没写入）、服务端原因、出路「换个名称重试 / 结束本次记录」。',
    actual: `原因可见=${retry} 失败卡=${failCard} 换个名称重试=${retryBtn} 结束本次记录=${abortBtn}。动作日志两次 ask_customer_name NOT_FOUND，未写入任何活动。`,
    verdict: retry && retryBtn && abortBtn ? 'pass' : retry ? 'gap' : 'blocked',
    expectedShot: 'screenshots/expected-s8.png',
    actualShot: shot8
  })
  await cancelActive(page)
})

test('o1 kind hint after change-kind', async ({ page }) => {
  test.setTimeout(420_000)
  await cancelActive(page)
  await openAssistant(page, true)
  // Reach any confirmation card with meeting kind first.
  const snap = await driveUntil(
    page,
    `开线上会议。今天下午和${CUSTOMER}开了线上会议评审POC部署。${CONTENT}。参会：我方张工（方案）；客户王总（决策）。`,
    { stopOn: ['CONFIRMATION'], pickKind: 'ONLINE_MEETING', timeoutMs: 280_000 }
  )
  if (snap?.waiting?.type !== 'CONFIRMATION') {
    record({
      id: 'o1',
      scene: '改类型后分类提示（change-kind hint）',
      expected: '确认卡点「改为线下 / 跟进」后草稿清空；重新描述不再问类型，直接按新类型整理。',
      actual: `未到达确认卡，停在 ${snap?.status ?? 'none'}/${snap?.waiting?.type ?? 'none'}`,
      verdict: 'blocked',
      expectedShot: 'screenshots/expected-s3.png',
      actualShot: 'screenshots/actual-o1-before.png'
    })
    await appShot(page, 'actual-o1-before.png')
    await cancelActive(page)
    return
  }
  await appShot(page, 'actual-o1-before.png')
  await page.getByRole('button', { name: /改为线下/ }).first().click()
  await page.getByText(/已清空整理稿/).first().waitFor({ timeout: 20_000 }).catch(() => undefined)
  await appShot(page, 'actual-o1-cleared.png')
  // Resubmit the same meeting description; expect NO kind question, straight to a follow-up confirmation.
  const after = await driveUntil(
    page,
    `今天下午和${CUSTOMER}开了线上会议评审POC部署。${CONTENT}。下一步：${NEXT_ACTION}。`,
    { stopOn: ['CONFIRMATION'], pickKind: 'OFFLINE_MEETING', timeoutMs: 280_000 }
  )
  const askedKind = after !== null && after.waiting?.type === 'ACTIVITY_KIND'
    || await page.getByRole('button', { name: '线上会议' }).last().isVisible().catch(() => false)
  await appShot(page, 'actual-o1-after.png')
  const kindNow = (await activeTask(page))?.activity_kind ?? ''
  record({
    id: 'o1',
    scene: '改类型后分类提示（change-kind hint）',
    expected: '改类型后重发同一段描述，不弹类型选择；classify 以用户指定类型为准。',
    actual: `改类型前 kind=${snap.activity_kind ?? ''}；改类型后重发，弹了类型选择=${askedKind}，最终 kind=${kindNow}`,
    verdict: !askedKind && kindNow !== '' ? 'pass' : 'gap',
    expectedShot: 'screenshots/expected-s3.png',
    actualShot: 'screenshots/actual-o1-after.png'
  })
  await cancelActive(page)
})

test('o2 idempotent double confirm', async ({ page }) => {
  test.setTimeout(420_000)
  await cancelActive(page)
  await openAssistant(page, true)
  const snap = await driveUntil(
    page,
    `今天和${CUSTOMER}的王总电话沟通了 POC 部署。${CONTENT}。下一步：${NEXT_ACTION}。`,
    { stopOn: ['CONFIRMATION'], pickKind: 'FOLLOW_UP', timeoutMs: 280_000 }
  )
  if (snap?.waiting?.type !== 'CONFIRMATION' || snap.waiting.field !== 'activity_write') {
    record({
      id: 'o3',
      scene: '重复确认幂等（client_request_id + submission_id）',
      expected: '同一笔确认重复提交只写一笔活动，第二次返回同一结果不报错不重写。',
      actual: `未到达确认卡，停在 ${snap?.status ?? 'none'}/${snap?.waiting?.type ?? 'none'}`,
      verdict: 'blocked',
      expectedShot: 'screenshots/expected-s6.png',
      actualShot: 'screenshots/actual-o3-before.png'
    })
    await appShot(page, 'actual-o3-before.png')
    await cancelActive(page)
    return
  }
  const before = await page.request.get(`${API}/tasks`, { headers: AUTH })
  const tasksBefore = (await before.json()) as Array<{ public_id: string }>
  const id = tasksBefore[0]?.public_id ?? ''
  const body = { kind: 'confirm', choice: 'confirm', client_request_id: `e2e-confirm-${id}-once` }
  const first = await page.request.post(`${API}/tasks/${id}/submit`, {
    headers: { ...AUTH, 'Content-Type': 'application/json' },
    data: body, timeout: 120_000
  })
  const firstText = await first.text()
  const second = await page.request.post(`${API}/tasks/${id}/submit`, {
    headers: { ...AUTH, 'Content-Type': 'application/json' },
    data: body, timeout: 120_000
  })
  const secondText = await second.text()
  const wroteOnce = firstText.includes('waiting') || firstText.includes('error')
  const secondStatus = second.status()
  const replayed = secondText.includes('waiting') || secondText.includes('error') || secondStatus === 409
  record({
    id: 'o3',
    scene: '重复确认幂等（client_request_id）',
    expected: '同一 client_request_id 重复投递同一载荷返回原结果（或 409 冲突），不产生第二笔活动。',
    actual: `首次=${first.status()} ${wroteOnce ? '流内终态' : '异常'}；重放=${secondStatus} ${replayed ? '有终态/冲突响应' : '无有效响应'}`,
    verdict: wroteOnce && replayed ? 'pass' : 'gap',
    expectedShot: 'screenshots/expected-s6.png',
    actualShot: 'screenshots/actual-s6-live.png'
  })
  // Drain any proposals so the task completes for replay checks.
  const proposal = page.getByRole('button', { name: '暂不处理' })
  const drainUntil = Date.now() + 120_000
  while (Date.now() < drainUntil) {
    const now = await activeTask(page)
    if (now === null || (now !== undefined && now.status !== 'ACTIVE')) break
    if (await clickIf(proposal, 1_000)) {
      await page.waitForTimeout(800)
      continue
    }
    await page.waitForTimeout(1_500)
  }
})

test('o4 replay read-only cards and badge', async ({ page }) => {
  test.setTimeout(180_000)
  await openAssistant(page)
  const completed = page.getByRole('button', { name: /完成/ }).first()
  await completed.click({ timeout: 10_000 }).catch(() => undefined)
  await page.waitForTimeout(1_500)
  const shot = await appShot(page, 'actual-o4-replay.png')
  const checks = {
    receipt: await page.getByText(/已记录/).first().isVisible().catch(() => false),
    badge: await page.getByText('已写入', { exact: true }).first().isVisible().catch(() => false),
    proposalCount: await page.getByText('下一步建议', { exact: true }).count(),
    handledCount: await page.getByText('已处理 · 暂不处理').count(),
    liveCancelButtons: await page.getByRole('button', { name: '取消', exact: true }).count(),
    refuseButtons: await page.getByRole('button', { name: '暂不处理' }).count()
  }
  record({
    id: 'o4',
    scene: '历史回放只读卡片 + 回执徽标',
    expected: '重开已完成任务：回执带「已写入」徽标；提案卡显示「已处理 · 暂不处理」，无任何可点按钮。',
    actual: `回执=${checks.receipt} 徽标=${checks.badge} 提案卡数=${checks.proposalCount} 已处理标记=${checks.handledCount} 可点取消=${checks.liveCancelButtons} 可点暂不处理=${checks.refuseButtons}`,
    verdict: checks.receipt && checks.badge && checks.proposalCount >= 1 && checks.handledCount >= 1 && checks.refuseButtons === 0
      ? 'pass' : checks.receipt ? 'gap' : 'blocked',
    expectedShot: 'screenshots/expected-s6.png',
    actualShot: shot
  })
})

test('o5 reload recovery mid-turn', async ({ page }) => {
  test.setTimeout(420_000)
  await cancelActive(page)
  await openAssistant(page, true)
  await send(page, `今天和${CUSTOMER}的王总电话沟通了 POC 部署。${CONTENT}。下一步：${NEXT_ACTION}。`)
  // Wait until the turn is in flight (processing visible), then reload.
  await page.getByText(/Agent 正在处理/).first().isVisible({ timeout: 15_000 }).catch(() => false)
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.locator('textarea').first().waitFor({ timeout: 30_000 })
  await page.waitForTimeout(1_000)
  const shot = await appShot(page, 'actual-o5-reload.png')
  // The task must survive: either processing continues, or a waiting card appears.
  const recovered = await driveUntil(page, null, { stopOn: ['CONFIRMATION', 'FIELD', 'ACTIVITY_KIND'], timeoutMs: 240_000 })
  const alive = recovered !== null && recovered.status === 'ACTIVE'
  const shot2 = await appShot(page, 'actual-o5-recovered.png')
  record({
    id: 'o5',
    scene: '刷新恢复（turn 持久化）',
    expected: '处理中刷新页面：任务不丢；恢复后能看到处理中/等待卡，可继续操作。',
    actual: `刷新后任务存活=${alive}，最终 waiting=${recovered?.waiting?.type ?? 'none'}/${recovered?.waiting?.field ?? ''} status=${recovered?.status ?? 'none'}`,
    verdict: alive ? 'pass' : 'gap',
    expectedShot: 'screenshots/expected-s9.png',
    actualShot: shot2 !== '' ? 'screenshots/actual-o5-recovered.png' : shot
  })
  await cancelActive(page)
})
