#!/usr/bin/env node
/**
 * P2-04 设计系统增量治理检查。
 *
 * 设计目标：只阻止新增设计系统债务，不把存量问题伪装成新问题。
 * 默认检查暂存文件；--all 仅输出全量审计结果，不作为迁移完成的替代品。
 */
import fs from 'node:fs'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const clientRoot = path.resolve(scriptDir, '..')
const repoRoot = path.resolve(clientRoot, '..')
const inventoryPath = path.join(repoRoot, 'CRM-Docs/design-system/migration/p2-pkg-04-inventory.json')
const exceptionsPath = path.join(repoRoot, 'CRM-Docs/design-system/migration/p2-pkg-04-exceptions.json')

const sourceExtensions = new Set(['.vue', '.scss', '.css', '.ts', '.tsx', '.js', '.jsx'])

const RULES = [
  {
    category: 'raw-color',
    pattern: /(?:^|[=:,(]|\s)(?:#[0-9a-f]{3,8}\b|rgba?\s*\(\s*(?:#?[0-9]|\d))/i,
    message: '新增 UI 颜色必须使用语义 Token；图表/可视化例外请登记。',
  },
  {
    category: 'legacy-token',
    pattern: /(?:variables\.scss(?!-v2)|\$wolf-[\w-]+-v1\b|--wolf-[\w-]+-v1\b)/i,
    message: '禁止新增旧 Token 入口，请使用 base.css 语义变量或已登记兼容层。',
  },
  {
    category: 'element-plus',
    pattern: /(?:<el-[a-z]|element-plus|\bEl[A-Z][A-Za-z]+\b)/,
    message: '禁止新增 Element Plus 组件入口。',
  },
  {
    category: 'status-color',
    pattern: /\b(?:text|bg|border)-(?:red|orange|amber|yellow|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|pink|rose|slate|gray)-(?:[1-9]\d?\d?)(?:\/[0-9]+)?\b/i,
    message: '状态颜色必须通过 StatusBadge/ApprovalStatusBadge 或登记例外表达。',
  },
]

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'))
}

function toRepoPath(filePath) {
  return path.relative(repoRoot, path.resolve(repoRoot, filePath)).split(path.sep).join('/')
}

function runGit(args) {
  try {
    return execFileSync('git', args, { cwd: repoRoot, encoding: 'utf8' })
  } catch {
    return ''
  }
}

function collectChangedPaths({ staged = true } = {}) {
  const diffArgs = staged
    ? ['diff', '--cached', '--name-only', '--diff-filter=ACMR']
    : ['diff', 'HEAD', '--name-only', '--diff-filter=ACMR']
  const tracked = runGit(diffArgs).split('\n').filter(Boolean)
  // 暂存模式只检查 index 中的文件；未跟踪文件可能尚未加入本次提交，不能误阻断提交。
  const untracked = staged
    ? []
    : runGit(['ls-files', '--others', '--exclude-standard']).split('\n').filter(Boolean)
  return [...new Set([...tracked, ...untracked])]
    .filter((file) => file.startsWith('CRM-Client/'))
    .filter((file) => sourceExtensions.has(path.extname(file)))
}

function collectAddedLines(filePath, { staged = true } = {}) {
  const absolutePath = path.join(repoRoot, filePath)
  if (!fs.existsSync(absolutePath)) return []

  const isUntracked = runGit(['ls-files', '--others', '--exclude-standard', '--', filePath]).trim() === filePath
  if (isUntracked) {
    return fs.readFileSync(absolutePath, 'utf8').split('\n').map((text, index) => ({ line: index + 1, text }))
  }

  const diffArgs = staged
    ? ['diff', '--cached', '--unified=0', '--no-color', '--', filePath]
    : ['diff', 'HEAD', '--unified=0', '--no-color', '--', filePath]
  const diff = runGit(diffArgs)
  const lines = []
  let currentLine = 0
  for (const rawLine of diff.split('\n')) {
    if (rawLine.startsWith('@@')) {
      const match = /\+(\d+)(?:,\d+)?/.exec(rawLine)
      currentLine = match ? Number(match[1]) : currentLine
      continue
    }
    if (rawLine.startsWith('+') && !rawLine.startsWith('+++')) {
      lines.push({ line: currentLine, text: rawLine.slice(1) })
      currentLine += 1
      continue
    }
    if (!rawLine.startsWith('-') && !rawLine.startsWith('\\')) currentLine += 1
  }
  return lines
}

function wildcardToRegExp(pattern) {
  return new RegExp(`^${pattern.split('*').map((part) => part.replace(/[.+?^${}()|[\]\\]/g, '\\$&')).join('.*')}$`)
}

function exceptionMatches(exception, filePath, category, text) {
  if (exception.status !== 'active' || exception.category !== category) return false
  if (!exception.files.some((file) => wildcardToRegExp(file).test(filePath))) return false
  return new RegExp(exception.match, 'i').test(text)
}

function validateGovernanceFiles() {
  const violations = []
  const inventory = readJson(inventoryPath)
  const exceptions = readJson(exceptionsPath)
  const requiredFields = ['id', 'file', 'category', 'target', 'owner', 'batch', 'risk', 'verification', 'status', 'lastVerified']
  for (const entry of inventory.entries ?? []) {
    for (const field of requiredFields) {
      if (entry[field] === undefined || entry[field] === '') {
        violations.push({ category: 'inventory', file: 'p2-pkg-04-inventory.json', line: 0, message: `${entry.id ?? 'unknown'} 缺少字段 ${field}` })
      }
    }
  }
  const today = new Date().toISOString().slice(0, 10)
  for (const exception of exceptions.exceptions ?? []) {
    for (const field of ['id', 'category', 'files', 'match', 'reason', 'owner', 'reviewDate', 'status']) {
      if (exception[field] === undefined || exception[field] === '' || (Array.isArray(exception[field]) && exception[field].length === 0)) {
        violations.push({ category: 'exception', file: 'p2-pkg-04-exceptions.json', line: 0, message: `${exception.id ?? 'unknown'} 缺少字段 ${field}` })
      }
    }
    if (exception.reviewDate && exception.reviewDate < today) {
      violations.push({ category: 'exception', file: 'p2-pkg-04-exceptions.json', line: 0, message: `${exception.id} reviewDate 已过期` })
    }
  }
  return violations
}

export function inspectLines(files, options = {}) {
  const exceptions = readJson(exceptionsPath).exceptions ?? []
  const violations = []
  for (const filePath of files) {
    for (const { line, text } of collectAddedLines(filePath, options)) {
      for (const rule of RULES) {
        const scanText = text.replace(/\/\/.*$/, '').replace(/\/\*.*?\*\//g, '')
        if (!rule.pattern.test(scanText)) continue
        if (exceptions.some((exception) => exceptionMatches(exception, filePath, rule.category, text))) continue
        violations.push({ category: rule.category, file: filePath, line, message: rule.message, text: text.trim() })
      }
    }
  }
  return violations
}

export function inspectContent(filePath, lines, exceptions = readJson(exceptionsPath).exceptions ?? []) {
  return inspectLinesFromContent(filePath, lines, exceptions)
}

export function inspectAll(files) {
  const violations = []
  for (const filePath of files) {
    const absolutePath = path.join(repoRoot, filePath)
    const lines = fs.readFileSync(absolutePath, 'utf8').split('\n')
    violations.push(...inspectLinesFromContent(filePath, lines))
  }
  return violations
}

function inspectLinesFromContent(filePath, lines, exceptions = readJson(exceptionsPath).exceptions ?? []) {
  const violations = []
  lines.forEach((text, index) => {
    for (const rule of RULES) {
      const scanText = text.replace(/\/\/.*$/, '').replace(/\/\*.*?\*\//g, '')
      if (!rule.pattern.test(scanText)) continue
      if (exceptions.some((exception) => exceptionMatches(exception, filePath, rule.category, text))) continue
      violations.push({ category: rule.category, file: filePath, line: index + 1, message: rule.message, text: text.trim() })
    }
  })
  return violations
}

function printViolations(violations) {
  for (const violation of violations) {
    console.error(`✗ ${violation.file}:${violation.line} [${violation.category}] ${violation.message}`)
    if (violation.text) console.error(`  ${violation.text}`)
  }
}

function main() {
  const args = new Set(process.argv.slice(2))
  const all = args.has('--all')
  const staged = !args.has('--worktree')
  const files = collectChangedPaths({ staged })
  const configViolations = validateGovernanceFiles()
  if (configViolations.length) printViolations(configViolations)

  if (all) {
    const sourceFiles = runGit(['ls-files', 'CRM-Client/src']).split('\n').filter((file) => sourceExtensions.has(path.extname(file)))
    const violations = inspectAll(sourceFiles)
    console.log(`设计系统全量审计：${sourceFiles.length} 个源码文件，发现 ${violations.length} 条未登记存量问题。`)
    printViolations(violations.slice(0, 40))
    if (violations.length > 40) console.log(`…其余 ${violations.length - 40} 条仅保留在审计统计中。`)
    process.exit(configViolations.length ? 1 : 0)
  }

  if (files.length === 0) {
    console.log('设计系统增量检查：没有暂存的前端源码文件。')
    process.exit(configViolations.length ? 1 : 0)
  }
  const violations = inspectLines(files, { staged })
  printViolations(violations)
  if (violations.length || configViolations.length) process.exit(1)
  console.log(`✓ 设计系统增量检查通过：${files.length} 个文件。`)
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) main()
