import assert from 'node:assert/strict'
import test from 'node:test'
import { inspectContent } from '../check-design-system-governance.mjs'

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

test('rejects legacy token entries and Element Plus', () => {
  const violations = inspectContent('CRM-Client/src/views/Example.vue', [
    "@use '@/styles/variables.scss';",
    "@use '@/styles/variables-v2.scss' as *;",
    '  <div class="rounded-wolf-md px-wolf-sm"></div>',
    '  padding: $wolf-page-padding-v2;',
    '<el-button>保存</el-button>',
  ], [])

  assert.deepEqual(violations.map((violation) => violation.category), [
    'legacy-token',
    'legacy-token',
    'legacy-token',
    'legacy-token',
    'element-plus',
  ])
})
