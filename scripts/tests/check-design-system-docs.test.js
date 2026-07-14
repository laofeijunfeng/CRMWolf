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
    forbiddenText: ['MASTER.md', 'ELEMENT-PLUS-MIGRATION.md', 'pages/list-page.md']
  }), 'utf8')
  return root
}

function check(files) {
  const rootDir = makeFixture(files)
  return validateDesignSystem({ rootDir, configPath: path.join(rootDir, 'governance/check-config.json') })
}

assert.deepStrictEqual(check({
  'README.md': '[Foundations](foundations/README.md)\n',
  'foundations/README.md': '[Color](color.md)\n',
  'foundations/color.md': '# Color\n'
}), [])
assert.deepStrictEqual(check({ 'README.md': 'x\n'.repeat(100) }), [])
assert.match(check({ 'README.md': `${'x\n'.repeat(101)}` })[0], /exceeds 100 lines/)
assert.match(check({ 'README.md': '[Missing](missing.md)\n' })[0], /broken link/)
assert.match(check({ 'README.md': '[Section](other.md#missing)\n', 'other.md': '# Present\n' })[0], /missing anchor/)
assert.match(check({ 'README.md': '# Root\n', 'foundations/README.md': '# Foundation\n', 'foundations/color.md': '# Color\n' })[0], /not reachable/)
assert.match(check({ 'README.md': 'Read MASTER.md\n' })[0], /forbidden text/)
console.log('check-design-system-docs tests passed')
