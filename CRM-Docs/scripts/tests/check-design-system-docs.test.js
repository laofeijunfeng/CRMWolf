const assert = require('assert')
const fs = require('fs')
const os = require('os')
const path = require('path')
const { validateDesignSystem } = require('../check-design-system-docs')

function makeFixture(files) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'design-system-docs-'))
  for (const [relativePath, content] of Object.entries(files)) {
    const file = path.join(root, relativePath)
    fs.mkdirSync(path.dirname(file), { recursive: true })
    fs.writeFileSync(file, content, 'utf8')
  }
  fs.mkdirSync(path.join(root, 'governance'), { recursive: true })
  fs.writeFileSync(path.join(root, 'governance/check-config.json'), JSON.stringify({
    managedReadmes: ['README.md', 'foundations/README.md'],
    ignoredFiles: [],
    forbiddenText: [
      'MASTER.md',
      'ELEMENT-PLUS-MIGRATION.md',
      'pages/list-page.md',
      'pages/detail-page.md',
      'pages/form-page.md',
      'pages/approval-center.md'
    ]
  }), 'utf8')
  return root
}

function check(files) {
  const rootDir = makeFixture(files)
  return validateDesignSystem({ rootDir, configPath: path.join(rootDir, 'governance/check-config.json') })
}

// Test: valid graph passes
assert.deepStrictEqual(check({
  'README.md': '[Foundations](foundations/README.md)\n',
  'foundations/README.md': '[Color](color.md)\n',
  'foundations/color.md': '# Color\n'
}), [])

// Test: 100 lines passes
assert.deepStrictEqual(check({ 'README.md': 'x\n'.repeat(100) }), [])

// Test: 101 lines fails
const lineViolation = check({ 'README.md': `${'x\n'.repeat(101)}` })[0]
assert.strictEqual(lineViolation.category, 'line-limit')
assert.strictEqual(lineViolation.line, 0)
assert.match(lineViolation.message, /exceeds 100 lines/)

// Test: broken link fails
const brokenLink = check({ 'README.md': '[Missing](missing.md)\n' })[0]
assert.strictEqual(brokenLink.category, 'broken-link')
assert.strictEqual(brokenLink.line, 1)
assert.match(brokenLink.message, /broken link/)

// Test: missing anchor fails
const missingAnchor = check({ 'README.md': '[Section](other.md#missing)\n', 'other.md': '# Present\n' })[0]
assert.strictEqual(missingAnchor.category, 'missing-anchor')
assert.strictEqual(missingAnchor.line, 1)
assert.match(missingAnchor.message, /missing anchor/)

// Test: unlinked file fails
const unreachable = check({ 'README.md': '# Root\n', 'foundations/README.md': '# Foundation\n', 'foundations/color.md': '# Color\n' })[0]
assert.strictEqual(unreachable.category, 'unreachable')
assert.strictEqual(unreachable.line, 0)
assert.match(unreachable.message, /not reachable/)

// Test: each forbidden legacy identifier fails with correct category and line number
const forbidden1 = check({ 'README.md': 'Read MASTER.md\n' })[0]
assert.strictEqual(forbidden1.category, 'forbidden-text')
assert.strictEqual(forbidden1.line, 1)
assert.match(forbidden1.message, /forbidden text MASTER\.md/)

const forbidden2 = check({ 'README.md': 'See ELEMENT-PLUS-MIGRATION.md\n' })[0]
assert.strictEqual(forbidden2.category, 'forbidden-text')
assert.match(forbidden2.message, /forbidden text ELEMENT-PLUS-MIGRATION\.md/)

const forbidden3 = check({ 'README.md': 'Old pages/list-page.md ref\n' })[0]
assert.strictEqual(forbidden3.category, 'forbidden-text')
assert.match(forbidden3.message, /forbidden text pages\/list-page\.md/)

const forbidden4 = check({ 'README.md': 'Old pages/detail-page.md ref\n' })[0]
assert.strictEqual(forbidden4.category, 'forbidden-text')
assert.match(forbidden4.message, /forbidden text pages\/detail-page\.md/)

const forbidden5 = check({ 'README.md': 'Old pages/form-page.md ref\n' })[0]
assert.strictEqual(forbidden5.category, 'forbidden-text')
assert.match(forbidden5.message, /forbidden text pages\/form-page\.md/)

const forbidden6 = check({ 'README.md': 'Old pages/approval-center.md ref\n' })[0]
assert.strictEqual(forbidden6.category, 'forbidden-text')
assert.match(forbidden6.message, /forbidden text pages\/approval-center\.md/)

console.log('check-design-system-docs tests passed')
