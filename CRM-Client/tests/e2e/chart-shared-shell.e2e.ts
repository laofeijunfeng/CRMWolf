import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test, type Page, type Route } from '@playwright/test'

const evidence = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../.xwing-task/crmwolf/evidence')

type Entity = 'contracts' | 'customers' | 'opportunities' | 'payments'
type RequestRecord = { pathname: string, query: Record<string, string> }
type FixtureState = {
  requests: RequestRecord[]
  chartFailures: Partial<Record<Entity, number>>
  bucketFailures: Partial<Record<Entity, number>>
}

const permission = (code: string, id: number) => ({
  id,
  code,
  name: code,
  resource: code.split(':')[0] ?? 'crm',
  action: code.split(':')[1] ?? 'view',
  scope: null,
  description: null,
})

const user = {
  id: 7,
  name: '李娜',
  email: 'lina@example.com',
  mobile: null,
  avatar_url: null,
  employee_no: 'E007',
  region: null,
  status: 'active',
  created_at: '2026-01-01T00:00:00',
  updated_at: '2026-01-01T00:00:00',
  roles: [],
}

const team = { id: 1, name: '星河', code: 'XH', owner_id: 7, created_at: '2026-01-01T00:00:00' }

const previewContract = (id: number, name: string, amount = 120000) => ({
  id,
  name,
  customer_name: '星河科技',
  owner_name: '李娜',
  amount,
  signing_date: '2026-11-02',
})

const previewCustomer = (id: string, name: string) => ({ id, name, owner_name: '李娜' })

const previewOpportunity = (id: string, name: string, amount = 180000) => ({
  id,
  name,
  customer_name: '星河科技',
  owner_name: '李娜',
  amount,
  expected_closing_date: '2026-12-15',
})

const previewPayment = (id: number, number: string, amount = 150000) => ({
  id,
  record_number: number,
  customer_name: '星河科技',
  amount,
  payment_date: '2026-11-02',
})

const bucket = <T>(key: string, label: string, count: number, preview: T, amount = 120000) => ({
  key,
  label,
  count,
  amount,
  ratio: count === 0 ? 0 : 100,
  amount_ratio: count === 0 ? 0 : 100,
  preview: count === 0 ? [] : [preview],
  preview_total: count === 0 ? 0 : 11,
})

const contractChart = {
  population: 11,
  total_amount: 1320000,
  cards: [
    { key: 'license_type', title: '授权模式', description: '订阅和买断各占多少金额。', buckets: [bucket('SUBSCRIPTION', '订阅', 10, previewContract(1, '订阅续约')), bucket('PERPETUAL', '买断', 0, previewContract(2, '买断合同'))] },
    { key: 'purchase_type', title: '采购类型', description: '新购、续购、增购。', buckets: [bucket('NEW', '新购', 6, previewContract(3, '新购合同')), bucket('RENEWAL', '续购', 5, previewContract(4, '续购合同'))] },
    { key: 'amount_band', title: '金额档', description: '按合同金额分档。', buckets: [bucket('100000_500000', '10万-50万', 11, previewContract(5, '金额合同'))] },
    { key: 'signing_month', title: '签署月份', description: '按签署月份汇总。', buckets: [bucket('2026-11', '2026年11月', 11, previewContract(6, '十一月合同'))] },
  ],
}

const customerChart = {
  population: 11,
  cards: [
    { key: 'status', title: '客户状态', description: '按客户状态汇总。', buckets: [bucket('following', '跟进中', 8, previewCustomer('cus_1', '星河科技')), bucket('invalid', '失效', 0, previewCustomer('cus_2', '空客户'))] },
    { key: 'license', title: '授权模式', description: '按授权模式汇总。', buckets: [bucket('SUBSCRIPTION', '订阅', 11, previewCustomer('cus_3', '订阅客户'))] },
    { key: 'scale', title: '公司规模', description: '按公司规模汇总。', buckets: [bucket('LARGE', '大型', 11, previewCustomer('cus_4', '大型客户'))] },
    { key: 'industry', title: '行业', description: '数量最多的行业。', buckets: [bucket('technology', '科技', 11, previewCustomer('cus_5', '科技客户'))] },
    { key: 'city', title: '城市', description: '数量最多的城市。', buckets: [bucket('shanghai', '上海', 11, previewCustomer('cus_6', '上海客户'))] },
    { key: 'created_month', title: '创建月份', description: '按创建月份汇总。', buckets: [bucket('2026-11', '2026年11月', 11, previewCustomer('cus_7', '十一月客户'))] },
  ],
}

const opportunityChart = {
  population: 11,
  total_amount: 1980000,
  cards: [
    { key: 'status', buckets: [bucket('active', '跟进中', 8, previewOpportunity('opp_1', '星河续约')), bucket('lost', '已输单', 0, previewOpportunity('opp_2', '空商机'))] },
    { key: 'win_probability', buckets: [bucket('50', '50%', 11, previewOpportunity('opp_3', '中赢率商机'))] },
    { key: 'purchase_type', buckets: [bucket('NEW', '新购', 11, previewOpportunity('opp_4', '新购商机'))] },
    { key: 'license_type', buckets: [bucket('SUBSCRIPTION', '订阅', 11, previewOpportunity('opp_5', '订阅商机'))] },
    { key: 'amount_band', buckets: [bucket('100000_500000', '10万-50万', 11, previewOpportunity('opp_6', '金额商机'))] },
    { key: 'product', buckets: [bucket('crm', 'CRM', 11, previewOpportunity('opp_7', 'CRM商机'))] },
    { key: 'expected_closing_month', buckets: [bucket('2026-12', '2026年12月', 11, previewOpportunity('opp_8', '十二月商机'))] },
  ],
}

const paymentChart = {
  population: 11,
  total_amount: 1650000,
  cards: [
    { key: 'license_type', title: '授权模式', description: '按授权模式汇总。', buckets: [bucket('SUBSCRIPTION', '订阅', 10, previewPayment(77, 'PAY202611020001')), bucket('PERPETUAL', '买断', 0, previewPayment(78, 'PAY202611020002'))] },
    { key: 'purchase_type', title: '采购类型', description: '按采购类型汇总。', buckets: [bucket('RENEWAL', '续购', 11, previewPayment(79, 'PAY202611020003'))] },
    { key: 'amount_band', title: '金额档', description: '按回款金额分档。', buckets: [bucket('100000_500000', '10万-50万', 11, previewPayment(80, 'PAY202611020004'))] },
    { key: 'payment_month', title: '回款月份', description: '按回款月份汇总。', buckets: [bucket('2026-01', '2026年1月', 0, previewPayment(81, 'PAY202611020005'))] },
    { key: 'arr_ratio', title: 'ARR 比例', description: '按 ARR 比例汇总。', buckets: [
      { ...bucket('2026-10', '2026年10月', 11, previewPayment(82, 'PAY202611020006')), plotted_ratio: null, annualized_subscription: null, buyout_amount: 0 },
      { ...bucket('2026-11', '2026年11月', 11, previewPayment(83, 'PAY202611020007')), plotted_ratio: 0, annualized_subscription: 0, buyout_amount: 0 },
    ] },
  ],
}

const listContract = {
  id: 1, contract_number: 'CON-2026-001', contract_name: '订阅续约', customer_id: 'cus_1', opportunity_id: 'opp_1', signing_contact_id: 1, owner_id: '7', creator_id: '7',
  user_count: 100, total_amount: '120000', license_type: 'SUBSCRIPTION', license_type_name: '订阅', subscription_years: 1,
  standard_unit_price: '1200', status: 'SIGNED', status_info: { name: '已签署' }, signing_date: '2026-11-02', effective_date: '2026-11-02', expiry_date: '2027-11-02',
  created_time: '2026-11-02T09:00:00', last_modified_time: '2026-11-02T09:00:00', customer_name: '星河科技', opportunity_name: '星河续约', owner_info: { id: '7', name: '李娜' },
}

const listCustomer = {
  id: 'cus_1', account_name: '星河科技', industry: 'technology', city: '上海', address: null, company_scale: 'LARGE', source_public_id: null,
  product_public_id: null, default_procurement_method_id: null, status: 1, lifecycle_status: 1, owner_id: '7', owner_name: '李娜', created_time: '2026-11-02T09:00:00', updated_time: '2026-11-02T09:00:00',
}


const listPayment = {
  id: 77, payment_plan_id: 9, record_number: 'PAY202611020001', actual_amount: 150000, actual_payer_name: '星河科技', payment_date: '2026-11-02', proof_attachment: null,
  commission_member_id: '7', commission_member_name: '李娜', notes: null, creator_id: '7', creator_name: '李娜', approval_phase: 'approved', confirmation_status: 'CONFIRMED', license_type: 'SUBSCRIPTION', purchase_type: 'RENEWAL',
  customer_id: 'cus_1', customer_name: '星河科技', contract_id: 1, contract_name: '订阅续约', stage_name: '续约款', owner_name: '李娜', created_time: '2026-11-02T09:00:00', updated_time: '2026-11-02T09:00:00', last_modified_time: '2026-11-02T09:00:00',
  payment_plan: { id: 9, plan_number: 'PLAN-2026-009', stage_name: '续约款', planned_amount: 150000, paid_amount: 150000, remaining_amount: 0, due_date: '2026-11-02', status: 'COMPLETED', last_modified_time: '2026-11-02T09:00:00' },
}

const pageResponse = (items: unknown[]) => ({ items, total: items.length, page: 1, page_size: 20, total_pages: 1 })

async function fulfill(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

// Read-only fixtures intentionally replace the backend; no live-data assertion is made.

function chartEntity(pathname: string): Entity | null {
  if (pathname.includes('/contracts/chart')) return 'contracts'
  if (pathname.includes('/customers/chart')) return 'customers'
  if (pathname.includes('/opportunities/chart')) return 'opportunities'
  if (pathname.includes('/payments/payment-records/chart')) return 'payments'
  return null
}

async function installApi(page: Page, state: FixtureState): Promise<void> {
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    const pathname = url.pathname
    state.requests.push({ pathname, query: Object.fromEntries(url.searchParams.entries()) })
    const entity = chartEntity(pathname)
    if (entity !== null && !pathname.includes('/chart/contracts') && !pathname.includes('/chart/customers') && !pathname.includes('/chart/opportunities') && !pathname.includes('/chart/records')) {
      const failures = state.chartFailures[entity] ?? 0
      if (failures > 0) {
        state.chartFailures[entity] = failures - 1
        await fulfill(route, { detail: 'fixture chart failure' }, 500)
        return
      }
    }
    if (entity !== null && (pathname.endsWith('/chart/contracts') || pathname.endsWith('/chart/customers') || pathname.endsWith('/chart/opportunities') || pathname.endsWith('/chart/records'))) {
      const failures = state.bucketFailures[entity] ?? 0
      if (failures > 0) {
        state.bucketFailures[entity] = failures - 1
        await fulfill(route, { detail: 'fixture bucket failure' }, 500)
        return
      }
    }
    if (pathname === '/api/v1/auth/me') return fulfill(route, user)
    if (pathname === '/api/v1/auth/me/roles') return fulfill(route, [])
    if (pathname === '/api/v1/auth/me/permissions') {
      return fulfill(route, { permissions: [
        permission('contract:view:all', 1), permission('customer:view:all', 2), permission('opportunity:view:all', 3), permission('payment:view', 4), permission('payment:record:view', 5), permission('payment:record:edit', 6), permission('payment:record:delete', 7), permission('contract:edit:all', 8), permission('customer:edit:all', 9), permission('opportunity:edit:all', 10),
      ], total: 10, cached: false })
    }
    if (pathname === '/api/v1/teams/user-teams') return fulfill(route, { teams: [team], current_team_id: 1 })
    if (pathname.startsWith('/api/v1/view-preferences/') && pathname.endsWith('/custom-views')) return fulfill(route, { view_key: pathname.split('/').slice(-2, -1)[0] ?? 'list', items: [] })
    if (pathname.startsWith('/api/v1/view-preferences/')) return fulfill(route, { view_key: pathname.split('/').pop() ?? 'list', personal: null, team: null, effective_scope: null, effective_config: null })
    if (pathname === '/api/v1/filter-options/owners') return fulfill(route, { data: [{ id: '7', name: '李娜', owner_id: '7', owner_name: '李娜', is_me: true }] })
    if (pathname === '/api/v1/customers/industries') return fulfill(route, [])
    if (pathname === '/api/v1/industries/hierarchy') return fulfill(route, {})
    if (pathname === '/api/v1/follow-up-tasks/confirmation-cases/pending-count') return fulfill(route, { count: 0 })
    if (pathname === '/api/v1/payments/payment-plans/badge-counts') return fulfill(route, { pending: 0, partial: 0, overdue: 0, pending_submit: 0, pending_approval: 0, pending_approval_me: 0 })
    if (pathname === '/api/v1/contracts/chart') return fulfill(route, contractChart)
    if (pathname === '/api/v1/customers/chart') return fulfill(route, customerChart)
    if (pathname === '/api/v1/opportunities/chart') return fulfill(route, opportunityChart)
    if (pathname === '/api/v1/payments/payment-records/chart') return fulfill(route, paymentChart)
    const skip = Number(url.searchParams.get('skip') ?? 0)
    const count = skip === 0 ? 10 : 1
    if (pathname === '/api/v1/contracts/chart/contracts') return fulfill(route, { chart: url.searchParams.get('chart'), bucket: url.searchParams.get('bucket'), total: 11, contracts: Array.from({ length: count }, (_, index) => previewContract(skip + index + 1, `合同明细 ${skip + index + 1}`)) })
    if (pathname === '/api/v1/customers/chart/customers') return fulfill(route, { chart: url.searchParams.get('chart'), bucket: url.searchParams.get('bucket'), total: 11, customers: Array.from({ length: count }, (_, index) => previewCustomer(`cus_${skip + index + 1}`, `客户明细 ${skip + index + 1}`)) })
    if (pathname === '/api/v1/opportunities/chart/opportunities') return fulfill(route, { chart: url.searchParams.get('chart'), bucket: url.searchParams.get('bucket'), total: 11, opportunities: Array.from({ length: count }, (_, index) => previewOpportunity(`opp_${skip + index + 1}`, `商机明细 ${skip + index + 1}`)) })
    if (pathname === '/api/v1/payments/payment-records/chart/records') return fulfill(route, { chart: url.searchParams.get('chart'), bucket: url.searchParams.get('bucket'), total: 11, records: Array.from({ length: count }, (_, index) => previewPayment(skip + index + 1, `PAY${String(skip + index + 1).padStart(3, '0')}`)) })
    if (pathname === '/api/v1/contracts' || pathname === '/api/v1/contracts/') return fulfill(route, pageResponse([listContract]))
    if (pathname === '/api/v1/customers' || pathname === '/api/v1/customers/') return fulfill(route, pageResponse([listCustomer]))
    if (pathname === '/api/v1/opportunities' || pathname === '/api/v1/opportunities/') return fulfill(route, pageResponse([]))
    if (pathname === '/api/v1/payments/payment-records') return fulfill(route, pageResponse([listPayment]))
    if (pathname === '/api/v1/contracts/1') return fulfill(route, listContract)
    if (pathname === '/api/v1/customers/cus_1') return fulfill(route, listCustomer)
    if (pathname === '/api/v1/payments/payment-records/77') return fulfill(route, listPayment)
    if (pathname === '/api/v1/acquisition-sources/options') return fulfill(route, [{ public_id: 'direct', name: '直销', code: 'DIRECT', is_system: true, is_active: true, sort_order: 1 }])
    if (pathname === '/api/v1/procurement-methods/options') return fulfill(route, [{ id: 1, code: 'STANDARD', name: '标准采购' }])
    if (pathname === '/api/v1/logs/batch') return fulfill(route, { received: 0 })
    await fulfill(route, {})
  })
}

async function seedSession(page: Page): Promise<void> {
  const payload = Buffer.from(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 86_400 })).toString('base64url')
  await page.addInitScript((token) => window.localStorage.setItem('token', token), `eyJhbGciOiJub25lIn0.${payload}.sig`)
}

const routeConfig: Array<{
  entity: Entity
  path: string
  section: string
  chartTitle: RegExp
  enabled: RegExp
  disabled: RegExp
  chartKey: string
  bucketKey: string
  endpoint: string
  firstRecord: string
}> = [
  { entity: 'contracts', path: '/contracts', section: '合同图表', chartTitle: /^11 份/, enabled: /^订阅/, disabled: /^买断/, chartKey: 'license_type', bucketKey: 'SUBSCRIPTION', endpoint: '/api/v1/contracts/chart/contracts', firstRecord: '合同明细 1' },
  { entity: 'customers', path: '/customers', section: '客户图表', chartTitle: /^11 家/, enabled: /^跟进中/, disabled: /^失效/, chartKey: 'status', bucketKey: 'following', endpoint: '/api/v1/customers/chart/customers', firstRecord: '客户明细 1' },
  { entity: 'opportunities', path: '/opportunities', section: '商机分析', chartTitle: /^11 条/, enabled: /^跟进中/, disabled: /^已输单/, chartKey: 'status', bucketKey: 'active', endpoint: '/api/v1/opportunities/chart/opportunities', firstRecord: '商机明细 1' },
  { entity: 'payments', path: '/payments/records', section: '回款图表', chartTitle: /^11 笔/, enabled: /^订阅/, disabled: /^买断/, chartKey: 'license_type', bucketKey: 'SUBSCRIPTION', endpoint: '/api/v1/payments/payment-records/chart/records', firstRecord: 'PAY001' },
]

test.describe('fixture-backed chart shared shell regression', () => {
  test.beforeEach(async ({ page }) => {
    await seedSession(page)
  })

  for (const config of routeConfig) {
    test(`${config.entity}: chart mode, bucket dialog, keyboard return and 375px layout`, async ({ page }) => {
      const state: FixtureState = { requests: [], chartFailures: {}, bucketFailures: {} }
      await installApi(page, state)
      await page.setViewportSize({ width: 1440, height: 1200 })
      await page.goto(config.path)
      await page.getByRole('tab', { name: '图表', exact: true }).click()
      const chartSection = page.locator(`section[aria-label="${config.section}"]`)
      await expect(chartSection.getByRole('heading', { name: config.chartTitle })).toBeVisible()
      await expect(page.getByText('数据格式异常', { exact: true })).toHaveCount(0)
      const chartRequest = state.requests.find((request) => request.pathname.endsWith('/chart'))
      expect(chartRequest?.query).toMatchObject({ filters: '[]', sorts: '[]' })
      if (config.entity === 'customers') expect(chartRequest?.query['scope']).toBe('owned_or_collaborated')

      const disabled = chartSection.getByRole('button', { name: config.disabled }).first()
      await expect(disabled).toBeDisabled()
      await expect(page.getByRole('dialog')).toHaveCount(0)
      const enabled = chartSection.getByRole('button', { name: config.enabled }).first()
      await enabled.focus()
      await enabled.press('Enter')
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByText(config.firstRecord, { exact: true })).toBeVisible()
      expect(state.requests.find((request) => request.pathname === config.endpoint)?.query).toMatchObject({
        chart: config.chartKey, bucket: config.bucketKey, skip: '0', limit: '10', filters: '[]', sorts: '[]',
      })
      await page.keyboard.press('Escape')
      await expect(dialog).toHaveCount(0)
      await expect(enabled).toBeFocused()
      await page.screenshot({ path: path.join(evidence, `chart-final-${config.entity}-desktop.png`), fullPage: true })

      await page.getByRole('tab', { name: '列表', exact: true }).click()
      await expect(chartSection).toHaveCount(0)
      await expect(page.getByRole('tab', { name: '列表', exact: true })).toHaveAttribute('aria-selected', 'true')
      await expect(page.getByRole('table')).toBeVisible()
      await page.setViewportSize({ width: 375, height: 900 })
      await page.getByRole('tab', { name: '图表', exact: true }).click()
      await expect(chartSection.getByRole('heading', { name: config.chartTitle })).toBeVisible()
      await enabled.scrollIntoViewIfNeeded()
      await enabled.click()
      await expect(dialog).toBeVisible()
      const bounds = await dialog.boundingBox()
      expect(bounds).not.toBeNull()
      expect(bounds?.x).toBeGreaterThanOrEqual(0)
      expect((bounds?.x ?? 0) + (bounds?.width ?? 0)).toBeLessThanOrEqual(375)
      await page.screenshot({ path: path.join(evidence, `chart-final-${config.entity}-mobile-dialog.png`), fullPage: true })
      await page.keyboard.press('Escape')
      await expect(dialog).toHaveCount(0)
      await expect(enabled).toBeFocused()
      await expect(page.getByText('数据格式异常', { exact: true })).toHaveCount(0)
      await chartSection.getByRole('heading', { name: config.chartTitle }).scrollIntoViewIfNeeded()
      await expect(chartSection.getByRole('heading', { name: config.chartTitle })).toBeVisible()
      await chartSection.evaluate((element) => { element.scrollTop = 0 })
      await page.screenshot({ path: path.join(evidence, `chart-final-${config.entity}-mobile.png`), fullPage: true })
      const widths = await chartSection.evaluate((element) => ({ client: element.clientWidth, scroll: element.scrollWidth }))
      expect(widths.scroll).toBeLessThanOrEqual(widths.client + 1)
    })
  }

  test('payments: zero-count month opens while ARR null cannot open and zero percent can', async ({ page }) => {
    const state: FixtureState = { requests: [], chartFailures: {}, bucketFailures: {} }
    await installApi(page, state)
    await page.setViewportSize({ width: 1440, height: 1200 })
    await page.goto('/payments/records')
    await page.getByRole('tab', { name: '图表', exact: true }).click()
    const zeroMonth = page.getByTestId('payment-chart-month-2026-01')
    await expect(zeroMonth).toBeEnabled()
    await zeroMonth.focus()
    await zeroMonth.press('Enter')
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    expect(state.requests.filter((request) => request.pathname.endsWith('/chart/records')).at(-1)?.query).toMatchObject({ chart: 'payment_month', bucket: '2026-01' })
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(zeroMonth).toBeFocused()

    const arrCard = page.getByTestId('payment-chart-card-arr_ratio')
    const nullRatio = page.getByTestId('payment-chart-arr-2026-10')
    const zeroRatio = page.getByTestId('payment-chart-arr-2026-11')
    await expect(nullRatio).toBeDisabled()
    await expect(zeroRatio).toBeEnabled()
    await expect(page.getByTestId('payment-chart-arr-label-2026-10')).toHaveCount(0)
    await expect(page.getByTestId('payment-chart-arr-label-2026-11')).toHaveText('0%')
    await zeroRatio.focus()
    await zeroRatio.press('Enter')
    await expect(dialog).toBeVisible()
    expect(state.requests.filter((request) => request.pathname.endsWith('/chart/records')).at(-1)?.query).toMatchObject({ chart: 'arr_ratio', bucket: '2026-11' })
    await expect(dialog.getByText('PAY001', { exact: true })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(zeroRatio).toBeFocused()
    await expect(arrCard).toBeVisible()
  })

  test('contracts: selected status and applied search reach chart and bucket requests', async ({ page }) => {
    const state: FixtureState = { requests: [], chartFailures: {}, bucketFailures: {} }
    await installApi(page, state)
    await page.goto('/contracts')
    await page.getByRole('tab', { name: '已签署', exact: true }).click()
    await page.getByRole('searchbox', { name: '搜索合同编号、合同名称、客户或商机' }).fill('星河')
    await page.getByRole('button', { name: '搜索', exact: true }).click()
    await page.getByRole('tab', { name: '图表', exact: true }).click()
    const chartSection = page.locator('section[aria-label="合同图表"]')
    await expect(chartSection.getByRole('heading', { name: /^11 份/ })).toBeVisible()
    expect(state.requests.filter((request) => request.pathname === '/api/v1/contracts/chart').at(-1)?.query).toMatchObject({ status: 'SIGNED', search: '星河', filters: '[]', sorts: '[]' })
    await chartSection.getByRole('button', { name: /^订阅/ }).first().click()
    await expect(page.getByRole('dialog').getByText('合同明细 1', { exact: true })).toBeVisible()
    expect(state.requests.filter((request) => request.pathname.endsWith('/chart/contracts')).at(-1)?.query).toMatchObject({ status: 'SIGNED', search: '星河', chart: 'license_type', bucket: 'SUBSCRIPTION', skip: '0', limit: '10', filters: '[]', sorts: '[]' })
  })

  test('contracts: chart retry, initial bucket retry and ten-record pagination', async ({ page }) => {
    const state: FixtureState = { requests: [], chartFailures: { contracts: 1 }, bucketFailures: { contracts: 1 } }
    await installApi(page, state)
    await page.setViewportSize({ width: 1440, height: 1200 })
    await page.goto('/contracts')
    await page.getByRole('tab', { name: '图表', exact: true }).click()
    const chartSection = page.locator('section[aria-label="合同图表"]')
    const chartRetry = chartSection.getByRole('button', { name: '重试', exact: true })
    await expect(chartSection.getByRole('alert')).toBeVisible()
    await chartRetry.click()
    await expect(chartSection.getByRole('heading', { name: /^11 份/ })).toBeVisible()
    await chartSection.getByRole('button', { name: /^订阅/ }).first().click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByRole('button', { name: '重试', exact: true })).toBeVisible()
    await dialog.getByRole('button', { name: '重试', exact: true }).click()
    await expect(dialog.getByText('合同明细 1', { exact: true })).toBeVisible()
    await expect(dialog.getByText('合同明细 10', { exact: true })).toBeVisible()
    await dialog.getByRole('button', { name: '查看更多', exact: true }).click()
    await expect(dialog.getByText('合同明细 11', { exact: true })).toBeVisible()
    await expect(dialog.getByRole('button', { name: '查看更多', exact: true })).toHaveCount(0)
    const bucketRequests = state.requests.filter((request) => request.pathname.endsWith('/chart/contracts'))
    expect(bucketRequests.map((request) => request.query['skip'])).toEqual(['0', '0', '10'])
    for (const request of bucketRequests) {
      expect(request.query).toMatchObject({ chart: 'license_type', bucket: 'SUBSCRIPTION', limit: '10', filters: '[]', sorts: '[]' })
    }
  })
})
