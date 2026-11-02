import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test, type Page, type Route } from '@playwright/test'

const evidence = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../.xwing-task/crmwolf/evidence')

const permission = (code: string, id: number) => ({
  id,
  code,
  name: code,
  resource: code.split(':')[0] ?? 'payment',
  action: code.split(':')[1] ?? 'view',
  scope: null,
  description: null,
})

const composition = {
  renewal: { headcount: 100, amount: 100000 },
  expansion: { headcount: 50, amount: 50000 },
}

const paymentRecord = () => ({
  id: 77,
  payment_plan_id: 9,
  record_number: 'PAY202611020001',
  actual_amount: 150000,
  actual_payer_name: '星河科技',
  payment_date: '2026-11-02',
  proof_attachment: null,
  composition,
  commission_member_id: '7',
  commission_member_name: '李娜',
  notes: null,
  creator_id: '7',
  creator_name: '李娜',
  approval_phase: 'pending_review',
  confirmation_status: 'PENDING',
  license_type: 'SUBSCRIPTION',
  purchase_type: 'RENEWAL',
  customer_id: 'cus_xinghe',
  customer_name: '星河科技',
  contract_id: 3,
  contract_name: '2026 订阅续约',
  stage_name: '续约款',
  owner_name: '李娜',
  created_time: '2026-11-02T09:00:00',
  updated_time: '2026-11-02T09:00:00',
  last_modified_time: '2026-11-02T09:00:00',
  payment_plan: {
    id: 9,
    plan_number: 'PLAN-2026-009',
    stage_name: '续约款',
    planned_amount: 150000,
    paid_amount: 0,
    remaining_amount: 150000,
    due_date: '2026-11-02',
    status: 'PENDING',
    last_modified_time: '2026-11-02T09:00:00',
  },
})

const paymentPlan = () => ({
  id: 9,
  contract_id: 3,
  plan_number: 'PLAN-2026-009',
  stage_name: '续约款',
  planned_amount: 150000,
  plan_amount: 150000,
  due_date: '2026-11-02',
  status: 'PENDING',
  status_name: '待登记',
  created_time: '2026-11-01T09:00:00',
  last_modified_time: '2026-11-02T09:00:00',
  paid_amount: 0,
  remaining_amount: 150000,
  payment_records: [],
  contract_name: '2026 订阅续约',
  customer_id: 'cus_xinghe',
  customer_name: '星河科技',
  opportunity_name: '2026 订阅续约',
})

async function fulfill(route: Route, body: unknown): Promise<void> {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

async function installApi(page: Page): Promise<void> {
  await page.route('**/api/v1/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname
    if (pathname === '/api/v1/auth/me') {
      await fulfill(route, {
        id: 7,
        name: '李娜',
        email: 'lina@example.com',
        mobile: null,
        avatar_url: null,
        employee_no: null,
        region: null,
        status: 'active',
        created_at: '2026-01-01T00:00:00',
        updated_at: '2026-01-01T00:00:00',
        roles: [],
      })
      return
    }
    if (pathname === '/api/v1/auth/me/roles') {
      await fulfill(route, [])
      return
    }
    if (pathname === '/api/v1/auth/me/permissions') {
      await fulfill(route, {
        permissions: [
          permission('payment:view', 1),
          permission('payment:confirm', 2),
          permission('payment:record:view', 3),
          permission('payment:record:edit', 4),
          permission('payment:record:export', 5),
          permission('approval:view', 6),
        ],
        total: 6,
        cached: false,
      })
      return
    }
    if (pathname === '/api/v1/teams/user-teams') {
      await fulfill(route, {
        teams: [{ id: 1, name: '星河', code: 'XH', owner_id: '7', created_at: '2026-01-01T00:00:00' }],
        current_team_id: 1,
      })
      return
    }
    if (pathname.startsWith('/api/v1/view-preferences/') && pathname.endsWith('/custom-views')) {
      await fulfill(route, { view_key: 'payment', items: [] })
      return
    }
    if (pathname.startsWith('/api/v1/view-preferences/')) {
      await fulfill(route, {
        view_key: 'payment',
        personal: null,
        team: null,
        effective_scope: null,
        effective_config: null,
      })
      return
    }
    if (pathname === '/api/v1/payments/payment-records') {
      await fulfill(route, {
        items: [paymentRecord()],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
        pending_approval_me_count: 0,
      })
      return
    }
    if (pathname === '/api/v1/payments/payment-records/77') {
      await fulfill(route, paymentRecord())
      return
    }
    if (pathname === '/api/v1/payments/payment-plans') {
      await fulfill(route, { items: [paymentPlan()], total: 1, page: 1, page_size: 20, total_pages: 1 })
      return
    }
    if (pathname === '/api/v1/payments/payment-plans/9') {
      await fulfill(route, paymentPlan())
      return
    }
    if (pathname === '/api/v1/customers/cus_xinghe/member-candidates') {
      await fulfill(route, [{ id: 7, name: '李娜', already_member: true }])
      return
    }
    if (pathname === '/api/v1/approvals') {
      await fulfill(route, {
        items: [{
          id: 501,
          business_type: 'PAYMENT',
          business_id: 77,
          application_number: 'PAY202611020001',
          entity_name: '2026 订阅续约',
          entity_amount: 150000,
          actual_payer_name: '星河科技',
          submitter_id: '7',
          submitter_name: '李娜',
          status: 'PENDING',
          created_time: '2026-11-02T09:00:00',
          updated_time: '2026-11-02T09:00:00',
          overdue_hours: null,
        }],
        total: 1,
        pending_count: 1,
      })
      return
    }
    if (pathname === '/api/v1/approvals/PAYMENT/77/detail') {
      await fulfill(route, {
        id: 501,
        business_type: 'PAYMENT',
        business_id: 77,
        contract_id: null,
        flow_id: 3,
        flow_name: '回款审批',
        current_node_id: 1,
        current_node_name: '财务',
        flow_is_active: true,
        flow_disabled_warning: null,
        application_number: 'PAY202611020001',
        status: 'PENDING',
        submitter_id: '7',
        submitter_name: '李娜',
        created_time: '2026-11-02T09:00:00',
        updated_time: '2026-11-02T09:00:00',
        records: [],
        entity_detail: {
          record_number: 'PAY202611020001',
          actual_amount: 150000,
          actual_payer_name: '星河科技',
          payment_date: '2026-11-02',
          contract_name: '2026 订阅续约',
          renewal_headcount: 100,
          renewal_amount: 100000,
          expansion_headcount: 50,
          expansion_amount: 50000,
        },
      })
      return
    }
    await fulfill(route, {})
  })
}

test('同一笔回款可以记下续购和增购', async ({ page }) => {
  test.setTimeout(90_000)
  const payload = Buffer.from(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 86_400 })).toString('base64url')
  await page.addInitScript((token) => {
    window.localStorage.setItem('token', token)
  }, `eyJhbGciOiJub25lIn0.${payload}.sig`)
  await installApi(page)
  await page.setViewportSize({ width: 1440, height: 1200 })

  await page.goto('/payments/plans')
  await page.getByRole('button', { name: '确认回款' }).click()
  const dialog = page.getByRole('dialog').last()
  await expect(dialog.getByRole('heading', { name: '登记回款' })).toBeVisible()
  await expect(dialog.getByText('登记实际到账信息；提交后将重算回款计划与合同状态。')).toBeVisible()
  await dialog.screenshot({ path: path.join(evidence, '01-register-collapsed.png') })

  await dialog.getByRole('button', { name: '补充信息' }).click()
  await dialog.locator('#payment-record-renewal-headcount').fill('100')
  await dialog.locator('#payment-record-renewal-amount').fill('100000.00')
  await expect(dialog.getByText('两段合计 ¥100,000.00，比这笔回款少 ¥50,000.00。')).toBeVisible()
  await dialog.screenshot({ path: path.join(evidence, '02-register-shortfall.png') })

  await dialog.locator('#payment-record-expansion-headcount').fill('50')
  await dialog.locator('#payment-record-expansion-amount').fill('50000.00')
  await expect(dialog.getByText('两段合计 ¥150,000.00，等于这笔回款。')).toBeVisible()
  await dialog.screenshot({ path: path.join(evidence, '03-register-balanced.png') })

  await page.goto('/payments/records')
  await expect(page.getByRole('columnheader', { name: '续购人数' })).toBeVisible()
  await expect(page.getByRole('cell', { name: '100', exact: true })).toBeVisible()
  await page.screenshot({ path: path.join(evidence, '04-record-list.png'), fullPage: true })
  await page.getByRole('table').getByText('PAY202611020001', { exact: true }).click()
  const sheet = page.getByRole('dialog').last()
  await expect(sheet.getByText('构成')).toBeVisible()
  await expect(sheet.getByText('续购人数')).toBeVisible()
  await sheet.screenshot({ path: path.join(evidence, '05-record-detail.png') })

  await page.goto('/approvals')
  await page.getByRole('cell', { name: '2026 订阅续约' }).click()
  const approval = page.getByRole('dialog').last()
  await expect(approval.getByText('续购人数')).toBeVisible()
  await expect(approval.getByText('增购金额')).toBeVisible()
  await approval.screenshot({ path: path.join(evidence, '06-approval-detail.png') })
})
