import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test, type Page, type Route } from '@playwright/test'

/**
 * Real invoice detail sheet with APIs intercepted.
 * Proves a twice-reissued invoice still offers 申请重开, keeps the latest record on top,
 * and blocks the original blue invoice.
 */
const evidence = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../.xwing-task/crmwolf/evidence')

const permission = (code: string, id: number) => ({
  id,
  code,
  name: code,
  resource: code.split(':')[0] ?? 'invoice',
  action: code.split(':')[1] ?? 'view',
  scope: null,
  description: null,
})

const reissue = (ordinal: 1 | 2) => {
  const second = ordinal === 2
  return {
    id: ordinal,
    application_number: second ? 'INVR-2' : 'INVR-1',
    original_invoice_application_id: 18,
    applicant_id: '7',
    applicant_name: '林晓',
    reason: second ? '税号再次更正' : '抬头写错',
    status: 'COMPLETED',
    approval_phase: 'approved',
    invoice_title_type: 'COMPANY',
    invoice_title_text: '武汉微派网络科技有限公司',
    invoice_taxpayer_id: second ? '91420100MA4K2N3X8C' : '91420100MA4K2N3X1A',
    invoice_bank_name: null,
    invoice_bank_account: null,
    invoice_address: null,
    invoice_phone: null,
    invoice_amount: '86000.00',
    invoice_type: 'VAT_SPECIAL',
    red_invoice_file_path: second ? 'invoices/red-2.pdf' : 'invoices/red-1.pdf',
    red_invoice_number: second ? '244220000000022345678' : '244220000000012349999',
    red_issued_time: second ? '2026-10-18T11:26:00' : '2026-08-03T09:12:00',
    new_invoice_file_path: second ? 'invoices/new-2.ofd' : 'invoices/new-1.pdf',
    new_invoice_number: second ? '244220000000032345678' : '244220000000012348888',
    new_issued_time: second ? '2026-10-18T11:26:00' : '2026-08-03T09:12:00',
    completed_time: second ? '2026-10-18T11:26:00' : '2026-08-03T09:12:00',
    created_time: second ? '2026-10-01T09:00:00' : '2026-08-01T09:00:00',
    last_modified_time: second ? '2026-10-18T11:26:00' : '2026-08-03T09:12:00',
  }
}

const invoice = () => ({
  id: 18,
  application_number: 'INV202607220001',
  customer_id: 'cus_weipai',
  contract_id: 7,
  opportunity_id: 3,
  payment_plan_id: 9,
  invoice_title_id: 4,
  invoice_type: 'VAT_SPECIAL',
  invoice_amount: '86000.00',
  payment_record_id: null,
  status: 'ISSUED',
  approval_phase: 'approved',
  applicant_id: '7',
  reviewer_id: '8',
  review_comment: null,
  reviewed_time: '2026-07-22T12:00:00',
  invoice_title_type: 'COMPANY',
  invoice_title_text: '武汉微派网络科技有限公司',
  invoice_taxpayer_id: '91420100MA4K2N3X00',
  invoice_bank_name: null,
  invoice_bank_account: null,
  invoice_address: null,
  invoice_phone: null,
  invoice_number: '244220000000012345678',
  invoice_file_path: 'invoices/original.pdf',
  issued_time: '2026-07-22T16:40:00',
  created_time: '2026-07-22T10:18:00',
  last_modified_time: '2026-10-18T11:26:00',
  customer_name: '武汉微派网络科技有限公司',
  contract_name: '微派网络 2026 采购合同',
  opportunity_name: null,
  payment_plan_stage_name: '首款',
  invoice_title_title: '武汉微派网络科技有限公司',
  applicant_name: '林晓',
  reviewer_name: '周衡',
  reissue_status: 'REISSUED',
  invoice_effective_status: 'REISSUED',
  current_invoice_file_kind: 'reissue_new',
  current_invoice_file_path: 'invoices/new-2.ofd',
  current_invoice_number: '244220000000032345678',
  current_reissue_id: 2,
  red_offsets: [],
  reissue_applications: [reissue(1), reissue(2)],
})

const approvalDetail = (businessType: string, businessId: number) => ({
  id: 400 + businessId,
  business_type: businessType,
  business_id: businessId,
  contract_id: null,
  flow_id: 3,
  flow_name: '发票重开申请审批流程',
  current_node_id: null,
  current_node_name: null,
  status: 'APPROVED',
  submitter_id: '7',
  submitter_name: '林晓',
  created_time: '2026-08-01T09:00:00',
  updated_time: '2026-08-02T09:00:00',
  flow_is_active: true,
  flow_disabled_warning: null,
  application_number: businessType === 'INVOICE' ? 'INV202607220001' : `INVR-${businessId}`,
  records: [],
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
        name: '林晓',
        email: 'linxiao@example.com',
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
        permissions: [permission('invoice_reissue:create', 1), permission('invoice:view:all', 2)],
        total: 2,
        cached: false,
      })
      return
    }
    if (pathname === '/api/v1/teams/user-teams') {
      await fulfill(route, {
        teams: [{ id: 1, name: '微派', code: 'WP', owner_id: '7', created_at: '2026-01-01T00:00:00' }],
        current_team_id: 1,
      })
      return
    }
    if (pathname.startsWith('/api/v1/view-preferences/') && pathname.endsWith('/custom-views')) {
      await fulfill(route, { view_key: 'invoices', items: [] })
      return
    }
    if (pathname.startsWith('/api/v1/view-preferences/')) {
      await fulfill(route, {
        view_key: 'invoices',
        personal: null,
        team: null,
        effective_scope: null,
        effective_config: null,
      })
      return
    }
    if (pathname === '/api/v1/customers/' || pathname === '/api/v1/customers') {
      await fulfill(route, { items: [], total: 0, page: 1, page_size: 100 })
      return
    }
    if (pathname === '/api/v1/invoice-applications') {
      await fulfill(route, { items: [invoice()], total: 1, page: 1, page_size: 20 })
      return
    }
    if (pathname === '/api/v1/invoice-applications/18') {
      await fulfill(route, invoice())
      return
    }
    const approval = pathname.match(/^\/api\/v1\/approvals\/(INVOICE|INVOICE_REISSUE)\/(\d+)\/detail$/)
    if (approval !== null) {
      await fulfill(route, approvalDetail(approval[1] ?? 'INVOICE', Number(approval[2])))
      return
    }
    await fulfill(route, {})
  })
}

test('已重开两次的发票详情仍可申请重开，并且当前发票是第二次', async ({ page }) => {
  test.setTimeout(60_000)
  const payload = Buffer.from(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 86_400 })).toString('base64url')
  await page.addInitScript((token) => {
    window.localStorage.setItem('token', token)
  }, `eyJhbGciOiJub25lIn0.${payload}.sig`)
  await installApi(page)
  await page.setViewportSize({ width: 1440, height: 1400 })
  await page.goto('/invoices')
  await page.getByRole('table').getByText('INV202607220001', { exact: true }).click()

  const sheet = page.locator('[role="dialog"]').last()
  await expect(sheet.getByRole('button', { name: '申请重开' })).toBeVisible()
  await expect(sheet.getByText('第 2 次 · 当前有效')).toBeVisible()
  await expect(sheet.getByText('第 1 次 · 已被下一次红冲')).toBeVisible()
  await expect(sheet.getByText('当前有效发票。列表和详情的下载都是这一份')).toBeVisible()
  await expect(sheet.getByText('原蓝字发票已红冲，不能下载')).toBeVisible()
  await expect(sheet.getByRole('button', { name: '不能下载' })).toBeDisabled()
  const headings = await sheet.locator('.reissue-card-meta').allTextContents()
  expect(headings.map((item) => item.trim())).toEqual([
    '第 2 次 · 当前有效',
    '第 1 次 · 已被下一次红冲',
  ])

  await sheet.getByText('第 2 次 · 当前有效').scrollIntoViewIfNeeded()
  await sheet.screenshot({ path: path.join(evidence, 'crm68-reissued-twice-detail.png') })
  await sheet.getByRole('button', { name: '不能下载' }).scrollIntoViewIfNeeded()
  await sheet.screenshot({ path: path.join(evidence, 'crm68-original-blocked.png') })
})
