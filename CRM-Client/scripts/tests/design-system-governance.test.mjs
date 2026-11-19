import assert from 'node:assert/strict'
import test from 'node:test'
import {
  checkStyleRatchet,
  findIconOnlyButtons,
  findOrphanComponents,
  inspectContent,
  measureViewStyles,
} from '../check-design-system-governance.mjs'

test('rejects newly added UI raw colors', () => {
  const violations = inspectContent('CRM-Client/src/components/Example.vue', [
    '.example {',
    '  color: #2563eb;',
    '}',
  ], [])

  assert.equal(violations.length, 1)
  assert.deepEqual(violations[0], {
    category: 'raw-color',
    file: 'CRM-Client/src/components/Example.vue',
    line: 2,
    message: 'UI 颜色必须使用 base.css 语义 Token。',
    text: 'color: #2563eb;',
  })
})

test('allows a documented visualization exception only for matching files', () => {
  const exception = {
    id: 'DS-EX-TEST',
    category: 'raw-color',
    files: ['CRM-Client/src/views/SalesDashboard.vue'],
    match: 'background:#2563eb',
    reason: '图表序列色',
    owner: 'frontend',
    reviewDate: '2026-12-04',
    status: 'active',
  }

  assert.equal(inspectContent(
    'CRM-Client/src/views/SalesDashboard.vue',
    ['<i style="background:#2563eb"></i>'],
    [exception],
  ).length, 0)

  assert.equal(inspectContent(
    'CRM-Client/src/components/Example.vue',
    ['<i style="background:#2563eb"></i>'],
    [exception],
  ).length, 1)
})


test('rejects nested raw colors in shadows and gradients', () => {
  const violations = inspectContent('CRM-Client/src/components/Example.vue', [
    '  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);',
    '  background: linear-gradient(90deg, #2563eb, rgba(96, 165, 250, 0.16));',
  ], [])

  assert.equal(violations.filter((violation) => violation.category === 'raw-color').length, 2)
})

test('ignores colors that only appear in source comments', () => {
  const violations = inspectContent('CRM-Client/src/components/Example.vue', [
    '  color: hsl(var(--foreground)); // #020817',
  ], [])

  assert.equal(violations.length, 0)
})


test('rejects Tailwind palette classes including ring and zinc', () => {
  const violations = inspectContent('CRM-Client/src/components/Example.vue', [
    '  <span class="text-red-600 bg-red-50">已驳回</span>',
    '  <div class="ring-blue-500"></div>',
    '  <div class="border-zinc-200"></div>',
  ], [])

  assert.deepEqual(violations.map((violation) => [violation.category, violation.line]), [
    ['palette-color', 1],
    ['palette-color', 2],
    ['palette-color', 3],
  ])
})

test('allows semantic token classes and data-tone status badges', () => {
  assert.deepEqual(inspectContent('CRM-Client/src/components/Example.vue', [
    '  <Badge variant="status" :data-tone="tone" class="text-muted-foreground bg-brand/10 ring-ring" />',
    '  color: hsl(var(--status-danger) / 0.3);',
  ], []), [])
})

test('rejects dark-mode variants', () => {
  const violations = inspectContent('CRM-Client/src/components/Example.vue', [
    '  <div class="bg-card dark:bg-background"></div>',
    '.dark .card { color: inherit; }',
    '  color: var(--wolf-text-dark-v2);',
    '@media (prefers-color-scheme: dark) {',
  ], [])

  assert.deepEqual(violations.filter((violation) => violation.category === 'dark-mode').map((violation) => violation.line), [1, 2, 3, 4])
})

test('exempts only base.css from raw colors as the single value source', () => {
  const shadow = ['  --shadow-1: 0 1px 2px rgb(0 0 0 / 0.05);']
  assert.deepEqual(inspectContent('CRM-Client/src/styles/base.css', shadow, []), [])
  assert.deepEqual(inspectContent('CRM-Client/src/styles/touch-safety.css', shadow, []).map((violation) => violation.category), ['raw-color'])
})

test('registered exceptions no longer allow palette or raw colors anywhere', () => {
  assert.deepEqual(inspectContent('CRM-Client/src/components/business-journey/BusinessJourneyBoardView.vue', [
    "countBadge: 'bg-blue-50 text-blue-700 border-blue-100'",
    '  background: rgb(240 249 255);',
  ]).map((violation) => violation.category), ['palette-color', 'raw-color'])
})

const categories = (filePath, lines) => inspectContent(filePath, lines, []).map((violation) => violation.category)

test('GATE-01 rejects upward imports by alias, relative path and dynamic import', () => {
  assert.deepEqual(categories('CRM-Client/src/components/agent/Chat.vue', [
    "import CustomerDetailSheet from '@/views/CustomerDetailSheet.vue'",
    "const Sheet = defineAsyncComponent(() => import('../../views/ContractDetailSheet.vue'))",
  ]), ['layer-direction', 'layer-direction'])
  assert.deepEqual(categories('CRM-Client/src/components/crmwolf/index.ts', [
    "export { default as StatusBadge } from '../StatusBadge.vue'",
  ]), ['layer-direction'])
  assert.deepEqual(categories('CRM-Client/src/components/ui/button/Button.vue', [
    "import { DataTable } from '@/components/crmwolf'",
  ]), ['layer-direction'])
})

test('GATE-01 allows downward imports', () => {
  assert.deepEqual(categories('CRM-Client/src/views/Customers.vue', [
    "import CustomerList from '@/components/customer/CustomerList.vue'",
    "import { DataTable } from '@/components/crmwolf'",
  ]), [])
  assert.deepEqual(categories('CRM-Client/src/components/crmwolf/DataTable.vue', [
    "import { Button } from '@/components/ui/button'",
    "import Empty from './EmptyHint.vue'",
  ]), [])
})

test('GATE-02 rejects ui re-exports only in the crmwolf barrel', () => {
  const line = ["export { Button } from '@/components/ui/button'"]
  assert.deepEqual(categories('CRM-Client/src/components/crmwolf/index.ts', line), ['barrel-reexport'])
  assert.deepEqual(categories('CRM-Client/src/components/crmwolf/ConfirmDialog.vue', line), [])
})

test('GATE-03 restricts alert-dialog, sheet, table and form to ui and crmwolf', () => {
  assert.deepEqual(categories('CRM-Client/src/views/Customers.vue', [
    "import { AlertDialog } from '@/components/ui/alert-dialog'",
    "import { Sheet } from '@/components/ui/sheet'",
    "import { Table } from '@/components/ui/table'",
    "import { FormField } from '@/components/ui/form'",
  ]), ['restricted-primitive', 'restricted-primitive', 'restricted-primitive', 'restricted-primitive'])
  assert.deepEqual(categories('CRM-Client/src/views/Customers.vue', [
    "import { DetailSheetContent } from '@/components/ui/detail-sheet'",
  ]), [])
  assert.deepEqual(categories('CRM-Client/src/components/crmwolf/ConfirmDialog.vue', [
    "import { AlertDialog } from '@/components/ui/alert-dialog'",
  ]), [])
})

test('GATE-04 rejects native dialogs outside test files', () => {
  assert.deepEqual(categories('CRM-Client/src/views/settings/Roles.vue', [
    "if (!confirm('确定删除？')) return",
    "window.alert('done')",
    "if (confirm ('继续？')) save()",
  ]), ['native-dialog', 'native-dialog', 'native-dialog'])
  assert.deepEqual(categories('CRM-Client/src/views/settings/Roles.vue', [
    "await useConfirm().confirm({ title: '删除' })",
    'function confirm(): void {}',
  ]), [])
  assert.deepEqual(categories('CRM-Client/src/schemas/__tests__/agent-ui.test.ts', [
    "const payload = '<img onerror=alert(1)>'",
  ]), [])
})

test('GATE-05 rejects page status palettes and status mapping functions', () => {
  assert.deepEqual(categories('CRM-Client/src/views/LeadDetailSheet.vue', [
    '.status-success {',
    'const getStatusClass = (status: number): string => {',
    'function getInvoiceStatusTone(status: string) {',
    'function getStatusToneClass(status: string): string {',
  ]), ['page-status-style', 'page-status-style', 'page-status-style', 'page-status-style'])
  assert.deepEqual(categories('CRM-Client/src/views/LeadDetailSheet.vue', [
    '.status-success-banner {',
  ]), [])
})

test('GATE-05 allows the single status source', () => {
  assert.deepEqual(categories('CRM-Client/src/utils/statusPresentation.ts', [
    'export function getContractStatusTone(status: number) {',
  ]), [])
  assert.deepEqual(categories('CRM-Client/src/components/crmwolf/StatusBadge.vue', [
    '.status-success {',
  ]), [])
})

test('full audit mode skips incremental component gates but keeps token rules', () => {
  const lines = [
    "import CustomerDetailSheet from '@/views/CustomerDetailSheet.vue'",
    "if (!confirm('确定删除？')) return",
    '  color: #2563eb;',
  ]
  assert.deepEqual(
    inspectContent('CRM-Client/src/components/agent/Chat.vue', lines, [], { full: true }).map((violation) => violation.category),
    ['raw-color'],
  )
})

test('GATE-06 rejects new geometry literals outside ui and styles', () => {
  assert.deepEqual(categories('CRM-Client/src/views/Customers.vue', [
    '<span class="text-[13px]">',
    '<div class="h-[38px]">',
    '<div class="rounded-[10px]">',
    '<div class="px-[12px]">',
    '  font-size: 14px;',
    '<DialogContent class="max-w-[600px]">',
  ]), Array(6).fill('geometry-token'))
  assert.deepEqual(categories('CRM-Client/src/views/Customers.vue', [
    '<div class="h-[var(--control-h-md)] max-w-[600px]">',
  ]), [])
  assert.deepEqual(categories('CRM-Client/src/components/ui/button/Button.vue', ['<span class="text-[13px]">']), [])
  assert.deepEqual(
    inspectContent('CRM-Client/src/views/Customers.vue', ['<span class="text-[13px]">'], [], { full: true }).map((violation) => violation.category),
    [],
  )
})

test('GATE-10 rejects form primitives imported by views only', () => {
  assert.deepEqual(categories('CRM-Client/src/views/Leads.vue', ["import { Input } from '@/components/ui/input'"]), ['page-form-primitive'])
  assert.deepEqual(categories('CRM-Client/src/components/crmwolf/InputField.vue', ["import { Input } from '@/components/ui/input'"]), [])
})

test('GATE-07 reports components without production consumers unless registered', () => {
  const sources = new Map([
    ['CRM-Client/src/components/Used.vue', '<template />'],
    ['CRM-Client/src/components/Orphan.vue', '<template />'],
    ['CRM-Client/src/components/crmwolf/Exported.vue', '<template />'],
    ['CRM-Client/src/components/crmwolf/Unnamed.vue', '<template />'],
    ['CRM-Client/src/components/crmwolf/index.ts', "export { default as Exported } from './Exported.vue'\nexport { default as Unnamed } from './Unnamed.vue'"],
    ['CRM-Client/src/views/Page.vue', "import Used from '@/components/Used.vue'\nimport { Exported } from '@/components/crmwolf'"],
  ])
  const orphans = (exceptions) => findOrphanComponents(sources, exceptions).map((violation) => violation.file)
  assert.deepEqual(orphans([]), ['CRM-Client/src/components/Orphan.vue', 'CRM-Client/src/components/crmwolf/Unnamed.vue'])
  assert.deepEqual(orphans([{
    id: 'EXC-T', category: 'orphan-component', files: ['CRM-Client/src/components/Orphan.vue'], match: '.*',
    reason: 'test', owner: 'frontend-platform', reviewDate: '2999-01-01', status: 'active',
  }]), ['CRM-Client/src/components/crmwolf/Unnamed.vue'])
})

test('GATE-08 blocks view style growth above the ratchet', () => {
  const measured = measureViewStyles(new Map([
    ['CRM-Client/src/views/A.vue', '<template />\n<style scoped>\n.a { color: red; }\n:deep(.b) { margin: 0; }\n</style>'],
    ['CRM-Client/src/components/B.vue', '<style>\n.b {}\n</style>'],
  ]))
  assert.deepEqual(measured, { styleLines: 2, deepSelectors: 1 })
  assert.deepEqual(checkStyleRatchet(measured, { styleLines: 2, deepSelectors: 1 }), [])
  assert.deepEqual(checkStyleRatchet(measured, { styleLines: 1, deepSelectors: 1 }).map((violation) => violation.category), ['style-ratchet'])
})

test('GATE-09 requires accessible names on icon-only buttons', () => {
  const found = (template) => findIconOnlyButtons('CRM-Client/src/views/A.vue', template).length
  assert.equal(found('<Button size="icon" title="删除"><Trash2 /></Button>'), 1)
  assert.equal(found('<Button size="icon" aria-label="删除"><Trash2 /></Button>'), 0)
  assert.equal(found('<Button size="icon" :aria-label="label"><Trash2 /></Button>'), 0)
  assert.equal(found('<Button><Plus /> 新建</Button>'), 0)
})
