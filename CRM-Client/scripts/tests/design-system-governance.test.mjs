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
    message: '新增 UI 颜色必须使用语义 Token；图表/可视化例外请登记。',
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


test('rejects direct utility status colors', () => {
  const violations = inspectContent('CRM-Client/src/components/Example.vue', [
    '  <span class=\"text-red-600 bg-red-50\">已驳回</span>',
  ], [])

  assert.deepEqual(violations.map((violation) => violation.category), [
    'status-color',
  ])
})

test('rejects new legacy and Element Plus entries', () => {
  const violations = inspectContent('CRM-Client/src/views/Example.vue', [
    "@use '@/styles/variables.scss';",
    '<el-button>保存</el-button>',
  ], [])

  assert.deepEqual(violations.map((violation) => violation.category), [
    'legacy-token',
    'element-plus',
  ])
})
