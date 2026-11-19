const assert = require('assert')
const fs = require('fs')
const os = require('os')
const path = require('path')
const { validateDesignSystem } = require('../check-design-system-docs')

function makeFixture(files, extraConfig = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'design-system-docs-'))
  for (const [relativePath, content] of Object.entries(files)) {
    const file = path.join(root, relativePath)
    fs.mkdirSync(path.dirname(file), { recursive: true })
    fs.writeFileSync(file, content, 'utf8')
  }
  fs.mkdirSync(path.join(root, 'governance'), { recursive: true })
  fs.writeFileSync(path.join(root, 'governance/check-config.json'), JSON.stringify({
    ignoredFiles: [],
    ...extraConfig
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

// Test: hex/px values fail outside the exempt token-values file
const rawValueConfig = {
  forbiddenPatterns: [{
    name: 'raw-ui-value',
    pattern: '(?<![\\w/.(#-])#[0-9a-fA-F]{3,8}\\b|\\b\\d+(?:\\.\\d+)?px\\b',
    exemptFiles: ['foundations/token-values.md'],
    message: 'hex/px values belong only in foundations/token-values.md'
  }]
}
function checkWith(files, extraConfig) {
  const rootDir = makeFixture(files, extraConfig)
  return validateDesignSystem({ rootDir, configPath: path.join(rootDir, 'governance/check-config.json') })
}
const rawHex = checkWith({ 'README.md': '| primary | #17191b |\n' }, rawValueConfig)
assert.strictEqual(rawHex.length, 1)
assert.strictEqual(rawHex[0].category, 'forbidden-pattern')
assert.strictEqual(rawHex[0].line, 1)
const rawPx = checkWith({ 'README.md': 'Title\n按钮高度 32px\n' }, rawValueConfig)
assert.deepStrictEqual(rawPx.map(v => [v.category, v.line]), [['forbidden-pattern', 2]])
assert.deepStrictEqual(checkWith({
  'README.md': '[Tokens](foundations/token-values.md)\n[Anchor](foundations/token-values.md#add)\n使用 `--control-h-md`\n',
  'foundations/token-values.md': '# Tokens\n## add\n| --primary | #17191b | 32px |\n'
}, rawValueConfig), [])

console.log('check-design-system-docs tests passed')
