const fs = require('fs')
const path = require('path')

function collectMarkdownFiles(rootDir) {
  return fs.readdirSync(rootDir, { withFileTypes: true }).flatMap(entry => {
    const target = path.join(rootDir, entry.name)
    if (entry.isDirectory()) return collectMarkdownFiles(target)
    return entry.isFile() && entry.name.endsWith('.md') ? [target] : []
  })
}

function slugify(heading) {
  return heading.trim().toLowerCase().replace(/[\s]+/g, '-').replace(/[^\w\-一-鿿]/g, '')
}

function parseMarkdownLinks(source) {
  return source.split('\n').flatMap((line, index) => {
    const links = []
    for (const match of line.matchAll(/(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)/g)) {
      links.push({ target: match[1], line: index + 1 })
    }
    return links
  })
}

function validateDesignSystem({ rootDir, configPath }) {
  const config = JSON.parse(fs.readFileSync(configPath, 'utf8'))
  const files = collectMarkdownFiles(rootDir)
  const relative = file => path.relative(rootDir, file).split(path.sep).join('/')
  const violations = []
  const graph = new Map(files.map(file => [relative(file), new Set()]))

  for (const file of files) {
    const source = fs.readFileSync(file, 'utf8')
    const fileName = relative(file)
    if (source.split('\n').length > 100) violations.push(`${fileName}: exceeds 100 lines`)
    for (const forbidden of config.forbiddenText) {
      if (source.includes(forbidden)) violations.push(`${fileName}: forbidden text ${forbidden}`)
    }
    for (const { target, line } of parseMarkdownLinks(source)) {
      if (/^(https?:|mailto:)/.test(target)) continue
      const [rawPath, rawAnchor] = target.split('#', 2)
      const targetFile = rawPath ? path.resolve(path.dirname(file), rawPath) : file
      if (!fs.existsSync(targetFile)) {
        violations.push(`${fileName}:${line}: broken link ${target}`)
        continue
      }
      if (rawAnchor) {
        const targetSource = fs.readFileSync(targetFile, 'utf8')
        const targetAnchors = new Set(targetSource.split('\n')
          .filter(item => /^#{1,6}\s+/.test(item))
          .map(item => slugify(item.replace(/^#{1,6}\s+/, ''))))
        if (!targetAnchors.has(rawAnchor)) violations.push(`${fileName}:${line}: missing anchor ${target}`)
      }
      if (targetFile.endsWith('.md')) graph.get(fileName).add(relative(targetFile))
    }
  }

  const visited = new Set()
  const visit = name => {
    if (!visited.has(name)) {
      visited.add(name)
      graph.get(name).forEach(visit)
    }
  }
  visit('README.md')
  for (const file of files) {
    const name = relative(file)
    if (!config.ignoredFiles.includes(name) && !visited.has(name)) {
      violations.push(`${name}: not reachable from README.md`)
    }
  }
  return violations
}

if (require.main === module) {
  const rootDir = path.resolve(process.argv[2] || path.join(__dirname, '..', 'CRM-Docs', 'design-system'))
  const configPath = path.join(rootDir, 'governance', 'check-config.json')
  const violations = validateDesignSystem({ rootDir, configPath })
  if (violations.length) {
    console.error(violations.map(item => `✗ ${item}`).join('\n'))
    process.exit(1)
  }
  console.log(`✓ ${collectMarkdownFiles(rootDir).length} design-system Markdown files passed`)
}

module.exports = { collectMarkdownFiles, parseMarkdownLinks, validateDesignSystem }
