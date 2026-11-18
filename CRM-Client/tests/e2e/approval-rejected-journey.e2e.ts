import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { test, expect, type Route } from '@playwright/test'

const evidence = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../.xwing-task/crmwolf/evidence')
const journeyId = `djy_${'a'.repeat(32)}`
const customerId = `cus_${'b'.repeat(32)}`
const opportunityId = `opp_${'c'.repeat(32)}`
const date = '2026-11-16T09:00:00'
const user = { id: 7, name: '李娜', email: 'lina@example.com', mobile: null, avatar_url: null, employee_no: 'E007', region: null, status: 'active', created_at: date, updated_at: date, roles: [] }
const permissions = ['customer:view:all', 'customer:edit:all', 'opportunity:view:all', 'opportunity:edit:all', 'opportunity:create'].map((code, index) => ({ id: index + 1, code, name: code, resource: code.split(':')[0], action: code.split(':')[1], scope: null, description: null }))
const baseOpportunity = {
  id: opportunityId, public_id: opportunityId, deal_journey_id: journeyId,
  opportunity_number: 'OPP-123', opportunity_name: '星河 CRM 升级', customer_id: customerId,
  customer_name: '星河科技', procurement_method_id: null, total_amount: 320000,
  user_count: 20, unit_price: 16000, license_type: 'SUBSCRIPTION', subscription_years: 1,
  purchase_type: 'NEW', decision_maker_count: 1, expected_closing_date: '2026-12-30',
  procurement_stage_id: null, stage_name: '方案沟通', win_probability: 80,
  owner_id: '7', owner_info: { id: '7', name: '李娜' }, creator_id: '7', status: 0,
  approval_phase: 'rejected', created_time: date, updated_time: date, version: 1,
  customer_info: { id: customerId, account_name: '星河科技' }
}
const approval = {
  id: 123, business_type: 'OPPORTUNITY', business_id: 123, contract_id: null,
  flow_id: 1, flow_name: '商机立项审批', current_node_id: null, current_node_name: null,
  status: 'REJECTED', submitter_id: '7', submitter_name: '李娜', created_time: date,
  updated_time: date, flow_is_active: true, flow_disabled_warning: null,
  records: [{ id: 1, approval_id: 123, node_id: 1, node_name: '主管审批', approver_id: '8', approver_name: '王明', approver_status: 'active', approver_status_display: '在职', action: 'REJECT', comment: '请补充采购预算与决策人信息', created_time: date }]
}
const stages = [['early_communication', '早期沟通'], ['active_progress', '持续推进'], ['closing_soon', '即将签约'], ['contract_processing', '签约中'], ['payment_processing', '回款中'], ['invoice_processing', '开票中'], ['completed', '已完成'], ['lost', '已流失'], ['approval_rejected', '审批未通过']]
const pageResponse = (items: unknown[]) => ({ items, total: items.length, page: 1, page_size: 20, total_pages: items.length ? 1 : 0 })
const fulfill = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

// Browser fixtures exercise the production UI and schema boundary, not live approval writes.
test('rejected journey has paused progress across list, board and detail', async ({ page }) => {
  test.setTimeout(90000)
  let approved = false
  const requests: Array<{ path: string, tab: string | null }> = []
  const journey = () => ({ id: journeyId, public_id: journeyId, name: '星河 CRM 升级', status: 'ACTIVE', current_board_stage: approved ? 'closing_soon' : 'approval_rejected', current_board_stage_label: approved ? '即将签约' : '审批未通过', cumulative_progress_percent: approved ? 75 : 0, amount: 320000, purchase_type: 'NEW', started_at: date, closed_at: null, last_event_at: date, primary_opportunity: { public_id: opportunityId, opportunity_name: '星河 CRM 升级', status: 0, approval_phase: approved ? 'approved' : 'rejected', win_probability: 80, expected_closing_date: '2026-12-30', product_name: 'CRM' } })
  const row = () => ({ ...journey(), customer_id: customerId, customer_name: '星河科技', owner: { id: '7', name: '李娜' }, primary_opportunity_name: '星河 CRM 升级', product_name: 'CRM', created_time: date, expected_closing_date: '2026-12-30' })
  const lostRow = () => ({ ...row(), id: `djy_${'d'.repeat(32)}`, public_id: `djy_${'d'.repeat(32)}`, name: '已明确输单项目', status: 'LOST', current_board_stage: 'lost', current_board_stage_label: '已流失' })
  await page.addInitScript(() => localStorage.setItem('token', 'eyJhbGciOiJub25lIn0.eyJleHAiOjQxMDAwMDAwMDB9.sig'))
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    const p = url.pathname
    const tab = url.searchParams.get('tab')
    requests.push({ path: p, tab })
    if (p.endsWith('/auth/me')) return fulfill(route, user)
    if (p.endsWith('/auth/me/roles')) return fulfill(route, [])
    if (p.endsWith('/auth/me/permissions')) return fulfill(route, { permissions, total: permissions.length, cached: false })
    if (p.endsWith('/teams/user-teams')) return fulfill(route, { teams: [{ id: 1, name: '星河', code: 'XH', owner_id: 7, created_at: date }], current_team_id: 1 })
    if (p.includes('/view-preferences/') && p.endsWith('/custom-views')) return fulfill(route, { view_key: 'business-journeys.list', items: [] })
    if (p.includes('/view-preferences/')) return fulfill(route, { view_key: 'business-journeys.list', personal: null, team: null, effective_scope: null, effective_config: null })
    if (p.endsWith('/business-journeys/owner-options') || p.endsWith('/filter-options/owners')) return fulfill(route, { data: [{ id: '7', name: '李娜', is_me: true }] })
    if (p.endsWith('/business-journeys/board')) {
      const selected = row()
      const card = { ...selected, journey_name: selected.name, contract_summary: { count: 0, signed_count: 0, amount: 0 }, payment_summary: { plan_count: 0, record_count: 0, planned_amount: 0, paid_amount: 0, remaining_amount: 0 }, invoice_summary: { application_count: 0, issued_count: 0, applied_amount: 0, issued_amount: 0 }, primary_opportunity: { public_id: opportunityId, opportunity_name: selected.name, amount: 320000, status: 0, current_stage_name: '方案沟通', win_probability: 80 } }
      return fulfill(route, { columns: stages.map(([key, title]) => ({ key, title, description: title, count: key === selected.current_board_stage ? 1 : 0, amount: key === selected.current_board_stage ? 320000 : 0, cards: key === selected.current_board_stage ? [card] : [] })), summary: { total_count: 1, total_amount: 320000, active_count: 1, completed_count: 0, lost_count: 0 }, truncated: false })
    }
    if (p.endsWith(`/business-journeys/${journeyId}`)) return fulfill(route, { journey: journey(), primary_opportunity: { ...baseOpportunity, approval_phase: approved ? 'approved' : 'rejected' } })
    if (p.endsWith('/business-journeys')) return fulfill(route, pageResponse(tab === 'active' ? (approved ? [row()] : []) : tab === 'approval_rejected' ? (approved ? [] : [row()]) : tab === 'lost' ? [lostRow()] : [row(), lostRow()]))
    if (p.endsWith(`/approvals/OPPORTUNITY/${opportunityId}/detail`)) return fulfill(route, { ...approval, status: approved ? 'APPROVED' : 'REJECTED' })
    if (p.includes('/contracts/opportunity/')) return fulfill(route, { detail: 'No contract' }, 404)
    if (p.includes('/license') || p.includes('/deployment') || p.endsWith('/members')) return fulfill(route, [])
    if (p.endsWith(`/customers/${customerId}`)) return fulfill(route, { id: customerId, public_id: customerId, account_name: '星河科技', owner_id: '7', status: 0, lifecycle_status: 0, created_time: date, updated_time: date })
    if (p.includes('/opportunity-stages/') || p.includes('/procurement')) return fulfill(route, [])
    if (p.endsWith('/pending-count')) return fulfill(route, { count: 0 })
    return fulfill(route, {})
  })
  await page.setViewportSize({ width: 1440, height: 1100 })
  await page.goto('/business-journeys')
  await expect(page.getByTestId('business-journey-name-link').filter({ hasText: '星河 CRM 升级' })).toBeVisible()
  const rejectedRow = page.locator('tbody tr').filter({ has: page.getByTestId('business-journey-name-link').filter({ hasText: '星河 CRM 升级' }) })
  await expect(rejectedRow).toContainText('审批未通过')
  await expect(rejectedRow.getByTestId('business-journey-progress')).toContainText('0%')
  await expect(rejectedRow).not.toContainText('80%')
  await expect(page.locator('tbody tr').filter({ hasText: '已明确输单项目' })).toContainText('已流失')
  await page.screenshot({ path: path.join(evidence, 'crm123-all-list.png'), fullPage: true })
  await page.getByRole('tab', { name: '进行中', exact: true }).click()
  await expect(page.getByTestId('business-journey-name-link').filter({ hasText: '星河 CRM 升级' })).toHaveCount(0)
  await page.getByRole('tab', { name: '审批未通过', exact: true }).click()
  await expect(page.getByTestId('business-journey-name-link')).toHaveText('星河 CRM 升级')
  expect(requests.some(r => r.path.endsWith('/business-journeys') && r.tab === 'approval_rejected')).toBe(true)
  await page.getByRole('tab', { name: '看板', exact: true }).click()
  const column = page.locator('.business-board-column').filter({ has: page.getByRole('heading', { name: '审批未通过', exact: true }) })
  await column.scrollIntoViewIfNeeded()
  await expect(column.getByRole('button', { name: '查看业务旅程：星河 CRM 升级' })).toContainText('0%')
  await expect(column).not.toContainText('赢率')
  await page.screenshot({ path: path.join(evidence, 'crm123-rejected-board.png'), fullPage: true })
  await column.getByRole('button', { name: '查看业务旅程：星河 CRM 升级' }).click()
  const detail = page.getByTestId('deal-journey-detail')
  await expect(detail.getByTestId('deal-journey-header')).toContainText('审批未通过')
  await expect(detail).toContainText('暂停销售推进')
  await expect(detail).toContainText('0%')
  await expect(detail).toContainText('请补充采购预算与决策人信息')
  await expect(detail.getByRole('button', { name: '修改并重新提交', exact: true })).toBeVisible()
  await expect(detail).not.toContainText('80%')
  await page.screenshot({ path: path.join(evidence, 'crm123-rejected-detail.png'), fullPage: true })
  await detail.getByRole('button', { name: '修改并重新提交', exact: true }).click()
  await expect(page.getByRole('dialog').filter({ hasText: '修改并重新提交' }).last()).toBeVisible()
  // Simulate the later approved read: UI must retain identity and recover the original stage.
  approved = true
  await page.goto('/business-journeys')
  const restoredRow = page.locator('tbody tr').filter({
    has: page.getByTestId('business-journey-name-link').filter({ hasText: '星河 CRM 升级' }),
  })
  await expect(restoredRow).toContainText('即将签约')
  await expect(restoredRow.getByTestId('business-journey-progress')).toContainText('75%')
  await expect(restoredRow).not.toContainText('审批未通过')
  await page.screenshot({ path: path.join(evidence, 'crm123-approved-restored.png'), fullPage: true })
})
