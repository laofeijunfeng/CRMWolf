import { expect, test, type Page } from '@playwright/test'
import { ConversationViewSchema, type AssistantTaskView, type ConversationView } from '../../src/schemas/assistant-contracts'

/**
 * CRM-101 layout regression on the real /assistant page with synthetic candidates.
 * API responses are intercepted; this is not original-conversation acceptance evidence.
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
      fingerprint: 'a'.repeat(64),
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
      interaction_type: 'choice',
      business_action: 'resolve_temporal_choice',
      state: 'ACTIVE',
      prompt: '请确认哪一项是你的下一步。',
      fields: [], facts: [],
      options: [
        { value: 'long-cn', label: '跟进定制场景，确认客户的集成需求、交付时间和验收方案，完整保留候选内容以便销售比较后选择。'.repeat(3), description: 'Synthetic Chinese layout boundary', disabled: false },
        { value: 'long-en', label: 'UninterruptedEnglishCandidate'.repeat(6), description: 'https://example.invalid/' + 'longpath'.repeat(35), disabled: false },
        { value: 'disabled', label: '不可选候选'.repeat(25), disabled: true }
      ],
      selection_mode: 'single', min_selections: 1, max_selections: 1, submit_on_select: true,
      submit_label: '提交', allow_cancel: false, submit_action_id: 'act_confirm'

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
  const state = ConversationViewSchema.parse(conversation(card))
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


for (const width of [1440, 375]) {
  test(`temporal candidates wrap within actual assistant card at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1100 })
    await installStubs(page, { state: 'ACTIVE', said: '稍后跟进', followTime: { value: '稍后' } })
    let submissions = 0
    let submitted: unknown
    await page.route('**/assistant/conversation/commands', async route => {
      submissions++
      submitted = route.request().postDataJSON()
      // Keep the request pending to observe the real processing/disabled state.
      await new Promise(resolve => setTimeout(resolve, 1500))
      await route.abort()
    })
    await page.goto('/assistant')
    const card = page.locator('.agent-ui-interaction')
    const options = card.getByRole('group').getByRole('button')
    await expect(options).toHaveCount(3)
    async function assertContained() {
      const layout = await card.evaluate(el => {
        const bounds = el.getBoundingClientRect()
        const buttons = [...el.querySelectorAll('button')]
        return {
          overflow: el.scrollWidth - el.clientWidth,
          outside: buttons.some(button => {
            const box = button.getBoundingClientRect()
            if (box.left < bounds.left || box.right > bounds.right + 1 || button.scrollWidth > button.clientWidth + 1) return true
            return [...button.querySelectorAll('span, small')].some(text => {
              const range = document.createRange(); range.selectNodeContents(text)
              return [...range.getClientRects()].some(rect => rect.left < box.left || rect.right > box.right + 1)
            })
          }),
          columns: getComputedStyle(el.querySelector('[role="group"]') ?? el).gridTemplateColumns.split(' ').length,
          heights: buttons.map(button => button.getBoundingClientRect().height)
        }
      })
      expect(layout.overflow).toBeLessThanOrEqual(1)
      expect(layout.outside).toBe(false)
      expect(layout.columns).toBe(width === 375 ? 1 : 2)
      expect(layout.heights[0]).toBeGreaterThan(44)
    }
    await page.screenshot({ path: testInfo.outputPath(`candidates-${width}.png`), fullPage: true })
    await assertContained()
    await expect(options.nth(2)).toBeDisabled()
    const date = card.getByPlaceholder('例如：2026-10-30')
    await date.scrollIntoViewIfNeeded()
    await expect(date).toBeVisible()
    const labels = await options.allTextContents()
    await options.first().click()
    await expect(options.first()).toContainText('处理中…')
    await expect(options.nth(1)).toBeDisabled()
    await assertContained()
    await page.screenshot({ path: testInfo.outputPath(`processing-${width}.png`), fullPage: true })
    expect(submissions).toBe(1)
    expect(submitted).toMatchObject({ input: { action_id: 'act_confirm', kind: 'submit_field', choice: 'long-cn' } })
    expect(await options.first().textContent()).toContain(labels[0]?.trim().split('Synthetic')[0]?.trim() ?? '')
  })
}
