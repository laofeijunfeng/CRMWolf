#!/usr/bin/env node
/**
 * 设计系统治理门禁。
 *
 * 默认检查暂存文件的新增行；--worktree 检查工作区改动；--all 全量审计 CRM-Client/src（CI 阻断）。
 * 标记 incremental 的组件门禁只在增量模式生效，存量登记在 governance/inventory.json，阶段 3 去掉标记后进入 --all。
 */
import fs from 'node:fs'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const clientRoot = path.resolve(scriptDir, '..')
const repoRoot = path.resolve(clientRoot, '..')
const governanceDir = path.join(repoRoot, 'CRM-Docs/design-system/governance')
const inventoryPath = path.join(governanceDir, 'inventory.json')
const exceptionsPath = path.join(governanceDir, 'exceptions.json')
const ratchetPath = path.join(governanceDir, 'ratchet.json')

const sourceExtensions = new Set(['.vue', '.scss', '.css', '.ts', '.tsx', '.js', '.jsx'])

const SRC = 'CRM-Client/src/'
const UI = `${SRC}components/ui/`
const CRMWOLF = `${SRC}components/crmwolf/`
const COMPONENTS = `${SRC}components/`
const VIEWS = `${SRC}views/`
const IMPORT_SPECIFIER = /(?:\bfrom\s+|\bimport\s*\(\s*|^\s*import\s+)['"]([^'"]+)['"]/g
const RESTRICTED_PRIMITIVE = /^CRM-Client\/src\/components\/ui\/(?:alert-dialog|sheet|table|form)(?:\/|$)/
// ui/form 已由 restricted-primitive 拦截，这里只补 input、label。
const PAGE_FORM_PRIMITIVE = /^CRM-Client\/src\/components\/ui\/(?:input|label)(?:\/|$)/
const STYLES = `${SRC}styles/`
// GATE-06：任意值只允许引用令牌（var(...)）；*Content 上的像素宽度另行拦截。
const GEOMETRY_LITERALS = [
  /(?<![\w-])text-\[\d+(?:\.\d+)?px\]/,
  /(?<![\w-])h-\[(?!var\()[^\]]+\]/,
  /(?<![\w-])rounded(?:-[trblse]{1,2})?-\[(?!var\()[^\]]+\]/,
  /(?<![\w-])p[xytrblse]?-\[\d+(?:\.\d+)?px\]/,
  /\bfont-size\s*:\s*\d+(?:\.\d+)?px/,
]
const CONTENT_PX_WIDTH = /(?<![\w-])(?:[a-z]+:)?max-w-\[\d+px\]/

function isTestFile(filePath) {
  return /\/__tests__\/|\.(?:test|spec)\.[cm]?[jt]sx?$/.test(filePath)
}

function resolveImports(filePath, text) {
  const targets = []
  for (const [, specifier] of text.matchAll(IMPORT_SPECIFIER)) {
    if (specifier.startsWith('@/')) targets.push(`${SRC}${specifier.slice(2)}`)
    else if (specifier.startsWith('.')) targets.push(path.posix.join(path.posix.dirname(filePath), specifier))
  }
  return targets
}

function layerOf(repoPath) {
  const dir = `${repoPath}/`
  if (dir.startsWith(UI)) return 'ui'
  if (dir.startsWith(CRMWOLF)) return 'crmwolf'
  if (dir.startsWith(COMPONENTS)) return 'components'
  if (dir.startsWith(VIEWS)) return 'views'
  return null
}

// 层级只能向下依赖：views → components → crmwolf → ui。
const FORBIDDEN_LAYERS = {
  ui: new Set(['crmwolf', 'components', 'views']),
  crmwolf: new Set(['components', 'views']),
  components: new Set(['views']),
}

const RULES = [
  {
    category: 'raw-color',
    pattern: /(?:^|[=:,(]|\s)(?:#[0-9a-f]{3,8}\b|rgba?\s*\(\s*(?:#?[0-9]|\d))/i,
    message: 'UI 颜色必须使用 base.css 语义 Token。',
    // 唯一数值源：base.css :root 定义 Token 原始值。
    exemptFiles: ['CRM-Client/src/styles/base.css'],
  },
  {
    category: 'dark-mode',
    pattern: /(?:(?:^|[\s"'`])dark:|\.dark\b|-dark-v2\b|prefers-color-scheme)/,
    message: '当前只有浅色主题，禁止 dark 写法。',
  },
  {
    category: 'palette-color',
    pattern: /\b(?:text|bg|border|ring)-(?:red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|slate|gray|zinc|neutral|stone)-(?:[1-9]\d?\d?)(?:\/[0-9]+)?\b/i,
    message: '禁止 Tailwind 调色板类；状态色用 data-tone / Badge variant="status"，其余用语义 Token。',
  },
  {
    category: 'layer-direction',
    incremental: true,
    appliesTo: (filePath) => Boolean(FORBIDDEN_LAYERS[layerOf(filePath)]),
    test: (text, filePath) => {
      const forbidden = FORBIDDEN_LAYERS[layerOf(filePath)]
      return resolveImports(filePath, text).some((target) => forbidden.has(layerOf(target)))
    },
    message: '组件层级只能向下依赖（views → components → crmwolf → ui），禁止反向引用。',
  },
  {
    category: 'barrel-reexport',
    incremental: true,
    appliesTo: (filePath) => filePath === `${CRMWOLF}index.ts`,
    test: (text, filePath) => resolveImports(filePath, text).some((target) => layerOf(target) === 'ui'),
    message: 'crmwolf/index.ts 不得转出 ui 原件；需要原件能力时在 crmwolf 中封装。',
  },
  {
    category: 'restricted-primitive',
    incremental: true,
    appliesTo: (filePath) => !filePath.startsWith(UI) && !filePath.startsWith(CRMWOLF),
    test: (text, filePath) => resolveImports(filePath, text).some((target) => RESTRICTED_PRIMITIVE.test(target)),
    message: 'ui 的 alert-dialog / sheet / table / form 只能经 crmwolf 组件或 ui/detail-sheet 使用，见 components/registry.md。',
  },
  {
    category: 'native-dialog',
    incremental: true,
    appliesTo: (filePath) => !isTestFile(filePath),
    pattern: /(?:\b(?:window|globalThis)\.|(?<![\w$.]|function\s+))(?:confirm|alert|prompt)\s*\(/,
    message: '禁止浏览器原生 confirm / alert / prompt，使用 confirmDialog / confirmDelete。',
  },
  {
    category: 'page-status-style',
    incremental: true,
    appliesTo: (filePath) => filePath.endsWith('.vue') && filePath !== `${CRMWOLF}StatusBadge.vue`,
    pattern: /\.status-(?:success|warning|danger|info|muted|default)(?![\w-])/,
    message: '页面不得自定义 .status-* 色板，业务状态统一用 StatusBadge。',
  },
  {
    category: 'page-status-style',
    incremental: true,
    exemptFiles: [`${SRC}utils/statusPresentation.ts`, `${CRMWOLF}StatusBadge.vue`],
    pattern: /\b(?:function\s+|(?:const|let|var)\s+)get\w*Status\w*(?:Class|Color|Tone|Variant)\w*\b/,
    message: '状态映射只在 utils/statusPresentation.ts 定义，页面不得自写 get*Status* 映射函数。',
  },
  {
    category: 'geometry-token',
    incremental: true,
    appliesTo: (filePath) => /\.(?:vue|s?css)$/.test(filePath) && !filePath.startsWith(UI) && !filePath.startsWith(STYLES),
    test: (text, _filePath, tag) => GEOMETRY_LITERALS.some((pattern) => pattern.test(text)) || ((/Content\b/.test(text) || /Content$/.test(tag)) && CONTENT_PX_WIDTH.test(text)),
    message: '宽度、字号、高度、圆角、内边距走令牌：弹窗用 size，其余用 --control-h-* / --radius-* / 字号令牌，见 foundations/token-values.md。',
  },
  {
    category: 'page-form-primitive',
    incremental: true,
    appliesTo: (filePath) => filePath.startsWith(VIEWS) && !isTestFile(filePath),
    test: (text, filePath) => resolveImports(filePath, text).some((target) => PAGE_FORM_PRIMITIVE.test(target)),
    message: '页面表单用 crmwolf *Field 组件，不得直接组合 ui/input、ui/label；存量见 governance/inventory.json。',
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

function ruleApplies(rule, filePath, { full }) {
  if (full && rule.incremental) return false
  if (rule.exemptFiles?.includes(filePath)) return false
  return rule.appliesTo ? rule.appliesTo(filePath) : true
}

function ruleMatches(rule, text, filePath, tag) {
  const scanText = text.replace(/\/\/.*$/, '').replace(/\/\*.*?\*\//g, '')
  return rule.test ? rule.test(scanText, filePath, tag) : rule.pattern.test(scanText)
}

// 行落在多行开始标签内部时返回该标签名（如 `<DialogContent` 换行写 class），否则为空串。
function enclosingTag(lines, index) {
  const before = lines.slice(Math.max(0, index - 30), index).join('\n')
  return /<([A-Za-z][\w.-]*)\b[^<>]*$/.exec(before)?.[1] ?? ''
}

function inspectLine(filePath, line, text, exceptions, options, tag = '') {
  const violations = []
  for (const rule of RULES) {
    if (!ruleApplies(rule, filePath, options)) continue
    if (!ruleMatches(rule, text, filePath, tag)) continue
    if (exceptions.some((exception) => exceptionMatches(exception, filePath, rule.category, text))) continue
    violations.push({ category: rule.category, file: filePath, line, message: rule.message, text: text.trim() })
  }
  return violations
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
        violations.push({ category: 'inventory', file: 'governance/inventory.json', line: 0, message: `${entry.id ?? 'unknown'} 缺少字段 ${field}` })
      }
    }
  }
  const today = new Date().toISOString().slice(0, 10)
  for (const exception of exceptions.exceptions ?? []) {
    for (const field of ['id', 'category', 'files', 'match', 'reason', 'owner', 'reviewDate', 'status']) {
      if (exception[field] === undefined || exception[field] === '' || (Array.isArray(exception[field]) && exception[field].length === 0)) {
        violations.push({ category: 'exception', file: 'governance/exceptions.json', line: 0, message: `${exception.id ?? 'unknown'} 缺少字段 ${field}` })
      }
    }
    if (exception.reviewDate && exception.reviewDate < today) {
      violations.push({ category: 'exception', file: 'governance/exceptions.json', line: 0, message: `${exception.id} reviewDate 已过期` })
    }
  }
  return violations
}

// 暂存模式读 index 中的内容（与本次提交一致），否则读工作区。
function readSourceLines(filePath, { staged = true } = {}) {
  const content = staged ? runGit(['show', `:${filePath}`]) : ''
  if (content) return content.split('\n')
  const absolutePath = path.join(repoRoot, filePath)
  return fs.existsSync(absolutePath) ? fs.readFileSync(absolutePath, 'utf8').split('\n') : []
}

export function inspectLines(files, options = {}) {
  const exceptions = readJson(exceptionsPath).exceptions ?? []
  const violations = []
  for (const filePath of files) {
    const added = collectAddedLines(filePath, options)
    if (added.length === 0) continue
    const source = readSourceLines(filePath, options)
    for (const { line, text } of added) {
      violations.push(...inspectLine(filePath, line, text, exceptions, { full: false }, enclosingTag(source, line - 1)))
    }
  }
  return violations
}

/**
 * 检查给定内容。默认按增量模式运行全部规则；{ full: true } 与 --all 一致，跳过 incremental 规则。
 */
export function inspectContent(filePath, lines, exceptions = readJson(exceptionsPath).exceptions ?? [], { full = false } = {}) {
  return lines.flatMap((text, index) => inspectLine(filePath, index + 1, text, exceptions, { full }, enclosingTag(lines, index)))
}

export function inspectAll(files) {
  const exceptions = readJson(exceptionsPath).exceptions ?? []
  return files.flatMap((filePath) => {
    const lines = fs.readFileSync(path.join(repoRoot, filePath), 'utf8').split('\n')
    return inspectContent(filePath, lines, exceptions, { full: true })
  })
}

function printViolations(violations) {
  for (const violation of violations) {
    console.error(`✗ ${violation.file}:${violation.line} [${violation.category}] ${violation.message}`)
    if (violation.text) console.error(`  ${violation.text}`)
  }
}

// GATE-07：components/**/*.vue（ui 除外）必须有生产代码消费方；经桶文件转出时要求消费方使用转出名。
export function findOrphanComponents(sources, exceptions = []) {
  const resolveTarget = (target) => [target, `${target}.vue`, `${target}.ts`, `${target}/index.ts`].find((candidate) => sources.has(candidate))
  const importers = new Map()
  for (const [filePath, content] of sources) {
    for (const target of resolveImports(filePath, content)) {
      const resolved = resolveTarget(target)
      if (!resolved || resolved === filePath) continue
      if (!importers.has(resolved)) importers.set(resolved, new Set())
      importers.get(resolved).add(filePath)
    }
  }
  const barrelNames = (barrel, component) => {
    const names = []
    for (const [, list, specifier] of sources.get(barrel).matchAll(/export\s*\{([^}]*)\}\s*from\s*['"]([^'"]+)['"]/g)) {
      if (resolveImports(barrel, `from '${specifier}'`).map(resolveTarget)[0] !== component) continue
      names.push(...list.split(',').map((name) => name.trim().split(/\s+as\s+/).pop()).filter(Boolean))
    }
    return names
  }
  const isConsumed = (component) => [...(importers.get(component) ?? [])].some((importer) => {
    if (!importer.endsWith('/index.ts')) return true
    const names = barrelNames(importer, component)
    return [...(importers.get(importer) ?? [])].some((consumer) => consumer !== component
      && names.some((name) => new RegExp(`\\b${name}\\b`).test(sources.get(consumer))))
  })
  return [...sources.keys()]
    .filter((filePath) => filePath.startsWith(COMPONENTS) && !filePath.startsWith(UI) && filePath.endsWith('.vue'))
    .filter((filePath) => !isConsumed(filePath))
    .filter((filePath) => !exceptions.some((exception) => exceptionMatches(exception, filePath, 'orphan-component', filePath)))
    .map((filePath) => ({ category: 'orphan-component', file: filePath, line: 0, message: '组件没有生产代码消费方：删除，或在 governance/exceptions.json 登记到期日。' }))
}

// GATE-08：views 私有样式只减不增，基线在 governance/ratchet.json。
export function measureViewStyles(sources) {
  let styleLines = 0
  let deepSelectors = 0
  for (const [filePath, content] of sources) {
    if (!filePath.startsWith(VIEWS) || !filePath.endsWith('.vue')) continue
    for (const [, body] of content.matchAll(/<style\b[^>]*>([\s\S]*?)<\/style>/g)) {
      styleLines += body.replace(/^\n|\n$/g, '').split('\n').length
      deepSelectors += body.match(/:deep\(/g)?.length ?? 0
    }
  }
  return { styleLines, deepSelectors }
}

export function checkStyleRatchet(measured, baseline) {
  return Object.entries(measured)
    .filter(([key, value]) => value > baseline[key])
    .map(([key, value]) => ({ category: 'style-ratchet', file: 'governance/ratchet.json', line: 0, message: `views ${key} ${value} 超过基线 ${baseline[key]}，样式下沉到 crmwolf 或令牌。` }))
}

// GATE-09：只有图标的 Button 必须有 aria-label。自闭合与嵌套 Button 不参与匹配。
const BUTTON_ELEMENT = /<Button\b((?:[^>"'/]|\/(?!>)|"[^"]*"|'[^']*')*)>((?:(?!<Button\b)[\s\S])*?)<\/Button>/g

export function findIconOnlyButtons(filePath, content, exceptions = []) {
  if (!filePath.endsWith('.vue') || filePath.startsWith(UI) || isTestFile(filePath)) return []
  const violations = []
  for (const match of content.matchAll(BUTTON_ELEMENT)) {
    const [element, attrs, inner] = match
    if (/(?:^|\s)(?::|v-bind:)?aria-label(?:ledby)?=|\sv-bind=/.test(attrs)) continue
    const visibleText = inner.replace(/<!--[\s\S]*?-->/g, '').replace(/<[^>]*>/g, '').trim()
    if (visibleText || !/<[A-Z]\w*/.test(inner)) continue
    const text = element.split('\n')[0].trim()
    if (exceptions.some((exception) => exceptionMatches(exception, filePath, 'icon-button-label', text))) continue
    violations.push({ category: 'icon-button-label', file: filePath, line: content.slice(0, match.index).split('\n').length, message: '只有图标的 Button 必须提供 aria-label。', text })
  }
  return violations
}

// 暂存模式只看 index：未跟踪或未暂存的半成品不能阻断本次提交。
function readRepositorySources({ staged }) {
  const sources = new Map()
  if (staged) {
    const entries = runGit(['ls-files', '-s', '--', SRC]).split('\n').filter(Boolean)
      .map((entry) => { const [meta, filePath] = entry.split('\t'); return { sha: meta.split(' ')[1], filePath } })
      .filter(({ filePath }) => sourceExtensions.has(path.extname(filePath)) && !isTestFile(filePath))
    const batch = execFileSync('git', ['cat-file', '--batch'], { cwd: repoRoot, input: entries.map(({ sha }) => sha).join('\n') + '\n', maxBuffer: 1 << 30 })
    let offset = 0
    for (const { filePath } of entries) {
      const headerEnd = batch.indexOf(10, offset)
      const size = Number(batch.toString('utf8', offset, headerEnd).split(' ')[2])
      sources.set(filePath, batch.toString('utf8', headerEnd + 1, headerEnd + 1 + size))
      offset = headerEnd + 1 + size + 1
    }
    return sources
  }
  for (const filePath of runGit(['ls-files', '--cached', '--others', '--exclude-standard', SRC]).split('\n')) {
    if (!sourceExtensions.has(path.extname(filePath)) || isTestFile(filePath)) continue
    const absolutePath = path.join(repoRoot, filePath)
    if (fs.existsSync(absolutePath)) sources.set(filePath, fs.readFileSync(absolutePath, 'utf8'))
  }
  return sources
}

function inspectRepository({ staged }) {
  const exceptions = readJson(exceptionsPath).exceptions ?? []
  const sources = readRepositorySources({ staged })
  const measured = measureViewStyles(sources)
  const baseline = readJson(ratchetPath)
  for (const [key, value] of Object.entries(measured)) {
    if (value < baseline[key]) console.log(`views ${key} 已降到 ${value}（基线 ${baseline[key]}），请同步下调 governance/ratchet.json。`)
  }
  return [
    ...findOrphanComponents(sources, exceptions),
    ...checkStyleRatchet(measured, baseline),
    ...[...sources].flatMap(([filePath, content]) => findIconOnlyButtons(filePath, content, exceptions)),
  ]
}

function main() {
  const args = new Set(process.argv.slice(2))
  const all = args.has('--all')
  const staged = !args.has('--worktree')
  const files = collectChangedPaths({ staged })
  const configViolations = validateGovernanceFiles()
  if (configViolations.length) printViolations(configViolations)
  const repositoryViolations = inspectRepository({ staged: staged && !all })
  printViolations(repositoryViolations)
  const blocked = configViolations.length > 0 || repositoryViolations.length > 0

  if (all) {
    const sourceFiles = runGit(['ls-files', '--cached', '--others', '--exclude-standard', 'CRM-Client/src']).split('\n')
      .filter((file) => sourceExtensions.has(path.extname(file)) && fs.existsSync(path.join(repoRoot, file)))
    const violations = inspectAll(sourceFiles)
    console.log(`设计系统全量审计：${sourceFiles.length} 个源码文件，发现 ${violations.length} 条违规（incremental 组件门禁不参与全量，存量见 governance/inventory.json）。`)
    printViolations(violations.slice(0, 40))
    if (violations.length > 40) console.log(`…其余 ${violations.length - 40} 条仅保留在审计统计中。`)
    process.exit(violations.length || blocked ? 1 : 0)
  }

  if (files.length === 0) {
    console.log('设计系统增量检查：没有暂存的前端源码文件。')
    process.exit(blocked ? 1 : 0)
  }
  const violations = inspectLines(files, { staged })
  printViolations(violations)
  if (violations.length || blocked) process.exit(1)
  console.log(`✓ 设计系统增量检查通过：${files.length} 个文件。`)
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) main()
