# 设计系统文档架构重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将设计规范迁移为一个可按主题精准检索、每个 Markdown 不超过 100 行、并受自动质量门禁保护的目标状态规范库。

**Architecture:** 以 `CRM-Docs/design-system/README.md` 为唯一根入口；领域 README 将读者导向单一事实来源（SSOT）主题文件。页面模式只定义组合与例外，基础、组件、迁移规则各自拥有唯一权威文件。依赖零第三方包的 CommonJS 检查器遍历文档图，验证行数、链接/锚点、索引可达性及废弃路径，并在 CI 阻断失败。

**Tech Stack:** Markdown、Node.js 18 CommonJS（`fs`/`path`/`assert`）、GitHub Actions、POSIX shell。

## Global Constraints

- `CRM-Docs/design-system/` 下全部 Markdown 文件（包含 README）必须不超过 **100 行**。
- 不保留 `MASTER.md`、`ELEMENT-PLUS-MIGRATION.md` 或旧 `pages/*.md` 路径的兼容入口、重定向或引用。
- 规范是 **目标状态**；未落地的迁移内容必须清晰标为目标状态，不能冒充当前实现。
- 单一事实来源：页面特有规则 > 交互模式 > 组件规则 > 基础规范；同级不得存在冲突规则。
- 实现只使用设计令牌；文档可在令牌表展示解析后的 px/hex 值，示例代码只使用令牌名。
- 圆角默认 6px；4px（紧凑控件）、8px（大尺寸控件/用户菜单/移动 Sheet）仅能作为命名例外出现。
- 禁用态默认 opacity 为 **0.38**，主题差异只能由令牌显式定义。
- 768px 宽度使用可折叠侧栏；更窄移动端使用底部导航或抽屉。页面主体不得横向滚动，只有信息密集表格容器可横向滚动。
- 桌面审批入口仅为顶部铃铛；移动端位于“更多”；上下文业务页可以提供审批处理深链接。铃铛数字表示待处理数量，访问审批中心不清零。
- 目标页面模式不得出现 Element Plus 名称或代码；相关名称、映射、遗留示例只存在于 `migration/`。
- 设计系统仅保留通用详情页模式；客户/合同等实体字段、Tab 和业务快捷入口移至功能文档。
- 确认 `CRM-Docs/design-system/` 为唯一权威来源；发现的非权威旧 master 删除或归档，且不得被索引或引用。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `CRM-Docs/design-system/README.md` | 唯一根入口：阅读路径、优先级、领域导航、检查命令 |
| `CRM-Docs/design-system/foundations/*.md` | 视觉令牌、无障碍、响应式、动效等基础 SSOT |
| `CRM-Docs/design-system/components/*.md` | 可复用组件视觉与状态 SSOT |
| `CRM-Docs/design-system/patterns/*.md` | 列表、详情、表单、审批中心的组合与页面例外 |
| `CRM-Docs/design-system/migration/*.md` | Element Plus 到目标组件体系的迁移事实、映射和状态 |
| `CRM-Docs/design-system/governance/*.md` | 文档优先级、写作边界与质量门禁使用说明 |
| `CRM-Docs/design-system/governance/check-config.json` | 检查器范围、受管 README、废弃标识与零豁免配置 |
| `scripts/check-design-system-docs.js` | 可执行的文档质量检查器和可复用校验函数 |
| `scripts/tests/check-design-system-docs.test.js` | 检查器的临时 fixture 自动化测试 |
| `.github/workflows/ci.yml` | Node 18 CI 质量门禁 job |
| `.husky/pre-commit` | 对暂存设计系统文档的快速本地阻断检查 |

### Planned documentation inventory

所有下列 Markdown 都要控制在 100 行内，每份都采用统一头部（用途、适用范围、权威性/优先级、相关规范）和结尾“相关规范”链接。

```text
README.md
foundations/{README,principles,color-tokens,typography,spacing-layout,radius-elevation,
             motion-performance,accessibility,responsive-mobile}.md
components/{README,button,input,table,card,tabs,sidebar,topbar,user-menu,
            bottom-navigation,status-badge,modal-sheet,approval-notification}.md
patterns/{README,list-page,detail-page,form-page,approval-center}.md
migration/{README,overview,element-plus-to-shadcn-vue,compatibility,implementation-status}.md
governance/{README,document-precedence,authoring,quality-checks}.md
```

---

### Task 1: 建立检查器的可测试接口与红灯测试

**Files:**
- Create: `scripts/tests/check-design-system-docs.test.js`
- Create: `scripts/check-design-system-docs.js`

**Interfaces:**
- Produces: `collectMarkdownFiles(rootDir) -> string[]`
- Produces: `parseMarkdownLinks(source, sourceFile) -> Array<{ target: string, line: number }>`
- Produces: `validateDesignSystem({ rootDir, configPath }) -> string[]` where an empty array means success.
- Produces: CLI `node scripts/check-design-system-docs.js [designSystemRoot]` that prints each violation and exits 1 if violations exist.

- [ ] **Step 1: Write fixture helpers and failing tests**

```js
// scripts/tests/check-design-system-docs.test.js
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
assert.match(check({ 'README.md': `${'x\n'.repeat(101)}` })[0], /exceeds 100 lines/)
assert.match(check({ 'README.md': '[Missing](missing.md)\n' })[0], /broken link/)
assert.match(check({ 'README.md': '[Section](other.md#missing)\n', 'other.md': '# Present\n' })[0], /missing anchor/)
assert.match(check({ 'README.md': '# Root\n', 'foundations/README.md': '# Foundation\n', 'foundations/color.md': '# Color\n' })[0], /not reachable/)
assert.match(check({ 'README.md': 'Read MASTER.md\n' })[0], /forbidden text/)
console.log('check-design-system-docs tests passed')
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node scripts/tests/check-design-system-docs.test.js`

Expected: failure because `scripts/check-design-system-docs.js` does not exist.

- [ ] **Step 3: Implement the minimal dependency-free validator**

```js
// scripts/check-design-system-docs.js
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
    const anchors = new Set(source.split('\n').filter(line => /^#{1,6}\s+/.test(line)).map(line => slugify(line.replace(/^#{1,6}\s+/, ''))))
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
        const targetAnchors = new Set(targetSource.split('\n').filter(item => /^#{1,6}\s+/.test(item)).map(item => slugify(item.replace(/^#{1,6}\s+/, ''))))
        if (!targetAnchors.has(rawAnchor)) violations.push(`${fileName}:${line}: missing anchor ${target}`)
      }
      if (targetFile.endsWith('.md')) graph.get(fileName).add(relative(targetFile))
    }
  }

  const visited = new Set()
  const visit = name => { if (!visited.has(name)) { visited.add(name); graph.get(name).forEach(visit) } }
  visit('README.md')
  for (const file of files) {
    const name = relative(file)
    if (!config.ignoredFiles.includes(name) && !visited.has(name)) violations.push(`${name}: not reachable from README.md`)
  }
  return violations
}

if (require.main === module) {
  const rootDir = path.resolve(process.argv[2] || path.join(__dirname, '..', 'CRM-Docs', 'design-system'))
  const configPath = path.join(rootDir, 'governance', 'check-config.json')
  const violations = validateDesignSystem({ rootDir, configPath })
  if (violations.length) { console.error(violations.map(item => `✗ ${item}`).join('\n')); process.exit(1) }
  console.log(`✓ ${collectMarkdownFiles(rootDir).length} design-system Markdown files passed`)
}

module.exports = { collectMarkdownFiles, parseMarkdownLinks, validateDesignSystem }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node scripts/tests/check-design-system-docs.test.js`

Expected: `check-design-system-docs tests passed`.

- [ ] **Step 5: Commit the tested checker foundation**

```bash
git add scripts/check-design-system-docs.js scripts/tests/check-design-system-docs.test.js
git commit -m "test: add design system documentation checker"
```

### Task 2: Create the governed documentation skeleton and root index

**Files:**
- Delete: `CRM-Docs/design-system/MASTER.md`
- Delete: `CRM-Docs/design-system/ELEMENT-PLUS-MIGRATION.md`
- Delete: `CRM-Docs/design-system/pages/list-page.md`
- Delete: `CRM-Docs/design-system/pages/detail-page.md`
- Delete: `CRM-Docs/design-system/pages/form-page.md`
- Delete: `CRM-Docs/design-system/pages/approval-center.md`
- Modify: `CRM-Docs/design-system/README.md`
- Create: `CRM-Docs/design-system/{foundations,components,patterns,migration,governance}/README.md`
- Create: `CRM-Docs/design-system/governance/check-config.json`
- Create: `CRM-Docs/design-system/governance/{document-precedence,authoring,quality-checks}.md`

**Interfaces:**
- Consumes: `validateDesignSystem({ rootDir, configPath }) -> string[]` from Task 1.
- Produces: a complete, direct-link documentation graph from root `README.md` to every reader-facing Markdown file.

- [ ] **Step 1: Write the governance documents before moving content**

Create `governance/document-precedence.md` with the exact precedence, SSOT and target-state decisions in Global Constraints. Create `governance/authoring.md` with the required metadata header, one-topic boundary, relative-link rule, and no-duplication rule. Create `governance/quality-checks.md` with the local command `node scripts/check-design-system-docs.js`, an explanation of all four failure types, and the remediation procedure. Keep each file below 100 lines.

- [ ] **Step 2: Replace the root README with the only root navigation document**

Use task-oriented navigation only: “新建或调整页面” → patterns; “调整组件” → components; “令牌与响应式” → foundations; “Element Plus 迁移” → migration; “维护规范” → governance. Include the precedence order and command, but no duplicated component or token rules. Link every domain README using relative Markdown links.

- [ ] **Step 3: Add five domain README indexes**

Each domain README must contain a one-sentence scope, a table or list of its owned topic documents, their use case, and a link back to root. It must not restate rules owned by topic documents. Ensure root links each domain README and each domain README links all its topic documents.

- [ ] **Step 4: Add the explicit checker configuration**

```json
{
  "managedReadmes": [
    "README.md",
    "foundations/README.md",
    "components/README.md",
    "patterns/README.md",
    "migration/README.md",
    "governance/README.md"
  ],
  "ignoredFiles": [],
  "forbiddenText": [
    "MASTER.md",
    "ELEMENT-PLUS-MIGRATION.md",
    "pages/list-page.md",
    "pages/detail-page.md",
    "pages/form-page.md",
    "pages/approval-center.md"
  ]
}
```

- [ ] **Step 5: Remove old source files only after replacement indexes link all new documents**

Use `git rm` for the six old source files. Do not create stub or redirect files. Search repository references with:

```bash
git grep -nE 'MASTER\.md|ELEMENT-PLUS-MIGRATION\.md|design-system/pages/(list-page|detail-page|form-page|approval-center)\.md'
```

Update every reference that points to the removed design-system paths; historical plans/specifications may be excluded only if they are not operational documentation and the checker scope does not include them.

- [ ] **Step 6: Run the checker and line-count audit**

Run:

```bash
node scripts/check-design-system-docs.js
find CRM-Docs/design-system -name '*.md' -print0 | xargs -0 wc -l
```

Expected: checker succeeds; every displayed Markdown count is at most 100.

- [ ] **Step 7: Commit the navigable skeleton**

```bash
git add CRM-Docs/design-system
git commit -m "docs: modularize design system navigation"
```

### Task 3: Migrate foundations and resolve global-rule duplication

**Files:**
- Create: `CRM-Docs/design-system/foundations/{principles,color-tokens,typography,spacing-layout,radius-elevation,motion-performance,accessibility,responsive-mobile}.md`
- Modify: `CRM-Docs/design-system/foundations/README.md`

**Interfaces:**
- Consumes: governance precedence and authoring rules from Task 2.
- Produces: foundation-level SSOT files linked by component and pattern documents in later tasks.

- [ ] **Step 1: Extract each foundation topic from old master material into one owner**

Use this exact assignment: values/decision priority → `principles.md`; light/dark/status palettes and semantic token names → `color-tokens.md`; hierarchy and mobile typography → `typography.md`; spacing, page/container/card geometry → `spacing-layout.md`; default 6px and named 4px/8px exceptions plus elevations → `radius-elevation.md`; transition tokens, reduced motion and response budgets → `motion-performance.md`; contrast, focus, screen-reader and disabled opacity 0.38 → `accessibility.md`; breakpoints, safe areas, scroll rules and 768px collapsible sidebar → `responsive-mobile.md`.

- [ ] **Step 2: Apply the approved conflict resolutions in the owner documents**

Write “页面主体不得横向滚动；信息密集表格可在自身容器横向滚动” only in `responsive-mobile.md`, with a link to `components/table.md`. State all resolved numeric values as token tables: a token name, resolved display value, and usage; code snippets may refer only to token names. Do not repeat the rule elsewhere.

- [ ] **Step 3: Remove non-authoritative and obsolete source text during migration**

Do not migrate emoji-as-icon samples, a blanket card lift animation, duplicated global anti-pattern lists, or claims that unimplemented V2 components are current production components. Replace any needed icon guidance with Lucide component names. Mark the set as target architecture in `principles.md`.

- [ ] **Step 4: Verify foundation isolation and line limits**

Run:

```bash
node scripts/check-design-system-docs.js
grep -RInE 'opacity: ?0\.5|禁止.*水平滚动|Sidebar.*隐藏' CRM-Docs/design-system/foundations
```

Expected: checker passes; grep shows only the approved wording or explanatory migration references.

- [ ] **Step 5: Commit foundation SSOTs**

```bash
git add CRM-Docs/design-system/foundations
git commit -m "docs: split design foundations into owned topics"
```

### Task 4: Migrate component contracts without framework-specific leakage

**Files:**
- Create: `CRM-Docs/design-system/components/{button,input,table,card,tabs,sidebar,topbar,user-menu,bottom-navigation,status-badge,modal-sheet,approval-notification}.md`
- Modify: `CRM-Docs/design-system/components/README.md`

**Interfaces:**
- Consumes: all foundation files from Task 3.
- Produces: reusable component contracts cited by patterns; framework-independent target rules.

- [ ] **Step 1: Move the duplicated visual component contracts to their unique owners**

Move button/input/table/card/tab and navigation rules from the historical master into the matching component files. Move duplicated table header, row height, hover and alignment requirements from historical list/detail content only to `table.md`. Move all status palettes to `status-badge.md`; page patterns must no longer carry status hex tables.

- [ ] **Step 2: Encode approved responsive and approval decisions**

In `sidebar.md`, declare 768px as a collapsible sidebar breakpoint and link to `responsive-mobile.md`. In `bottom-navigation.md`, define the mobile “更多” destination. In `approval-notification.md`, define desktop top-bell-only entry, permitted contextual deep links, and pending-work count semantics that update after action/transfer/withdrawal rather than visit.

- [ ] **Step 3: Reference foundations instead of copying them**

Every component document should link to the owning token/motion/accessibility document for colors, radius, transitions, focus and disabled state. Do not reproduce source tables or state rules. Use “遵循 [无障碍](../foundations/accessibility.md)” rather than copying opacity or focus values.

- [ ] **Step 4: Exclude Element Plus and implementation pseudo-code**

Search and remove target-document occurrences of `el-`, `Element Plus`, `el-table-column`, `ElPagination`, and legacy component-specific APIs. Describe behavior semantically; place legacy framework mapping only in Task 6 migration documents.

- [ ] **Step 5: Verify the component domain**

Run:

```bash
node scripts/check-design-system-docs.js
grep -RInE 'Element Plus|el-[a-z]|el-table-column|ElPagination' CRM-Docs/design-system/components CRM-Docs/design-system/patterns
```

Expected: checker succeeds and grep has no matches.

- [ ] **Step 6: Commit reusable component contracts**

```bash
git add CRM-Docs/design-system/components
git commit -m "docs: extract component design contracts"
```

### Task 5: Rewrite page documents as composition patterns

**Files:**
- Create: `CRM-Docs/design-system/patterns/{list-page,detail-page,form-page,approval-center}.md`
- Modify: `CRM-Docs/design-system/patterns/README.md`

**Interfaces:**
- Consumes: component contracts from Task 4 and foundations from Task 3.
- Produces: page-level composition/exception guidance, free of copied general rules and CRM entity-specific feature content.

- [ ] **Step 1: Write framework-agnostic list and form patterns**

`list-page.md` owns filter/search-to-table-to-pagination composition, column density, empty-state placement, and the table-container scroll exception. `form-page.md` owns grouping, label/helper/error sequence, action placement, modal-form boundary and page-specific spacing exceptions. Both link to shared components rather than repeat their metrics.

- [ ] **Step 2: Reduce detail-page content to reusable layout principles**

`detail-page.md` owns contextual tabs, information hierarchy, property groups, embedded tables and responsive composition. Remove customer/contract tab names, license content, payment-plan quick creation and other feature-specific values; relocate any required surviving guidance to the appropriate CRM feature documentation outside the design system in a separate follow-up change.

- [ ] **Step 3: Write approval-center as a target composition pattern**

`approval-center.md` owns the target shell composition: desktop bell entry, mobile More entry, approval-type tabs, task table, status presentation, progress/timeline placement, and pending count semantics. It must not specify route redirects or claim that visiting clears the badge. Link generic notification/table/tabs/modal contracts.

- [ ] **Step 4: Check for duplicated general rules and old paths**

Run:

```bash
grep -RInE '220px|56px|48px|150ms|#[0-9A-Fa-f]{6}|MASTER\.md|ELEMENT-PLUS-MIGRATION\.md' CRM-Docs/design-system/patterns
node scripts/check-design-system-docs.js
```

Expected: patterns contain no duplicated global numeric contracts or removed paths, and the checker succeeds.

- [ ] **Step 5: Commit concise page composition guides**

```bash
git add CRM-Docs/design-system/patterns
git commit -m "docs: rewrite page rules as composition patterns"
```

### Task 6: Isolate migration material and revalidate its claims

**Files:**
- Create: `CRM-Docs/design-system/migration/{overview,element-plus-to-shadcn-vue,compatibility,implementation-status}.md`
- Modify: `CRM-Docs/design-system/migration/README.md`
- Modify: `CRM-Client/docs/design-system/MIGRATION.md` only if it links to removed design-system paths.

**Interfaces:**
- Consumes: target component/pattern names from Tasks 4–5.
- Produces: the only location where Element Plus terms, legacy mappings, target/current state comparison and dated migration status are allowed.

- [ ] **Step 1: Separate timeless policy from time-sensitive status**

Write `overview.md` for scope and target-state designation. Write `element-plus-to-shadcn-vue.md` for legacy-to-target mappings and any needed legacy code fragments. Write `compatibility.md` for permitted temporary aliases and removal conditions. Write `implementation-status.md` for date-stamped, evidence-backed status only; remove unsupported fixed usage counts and references to nonexistent scan/checklist tools.

- [ ] **Step 2: Correct known false or stale migration references**

Remove references to nonexistent `docs/ELEMENT-PLUS-MIGRATION-CHECKLIST.md` and absent scan scripts. Confirm target component claims against `CRM-Client/src` before marking a target contract as implemented. Where no implementation exists, say “目标状态，尚未在现有组件中全面落地.”

- [ ] **Step 3: Link migration from target documents, never copy it into them**

Component and pattern documents may use one link such as “迁移现有 Element Plus 实现时，见 [迁移映射](../migration/element-plus-to-shadcn-vue.md)”; they must not include framework name or mapping content themselves.

- [ ] **Step 4: Verify migration boundaries and link validity**

Run:

```bash
node scripts/check-design-system-docs.js
grep -RInE 'Element Plus|el-[a-z]|el-table-column|ElPagination' CRM-Docs/design-system --include='*.md'
```

Expected: legacy terms occur only below `CRM-Docs/design-system/migration/`.

- [ ] **Step 5: Commit migration isolation**

```bash
git add CRM-Docs/design-system/migration CRM-Client/docs/design-system/MIGRATION.md
git commit -m "docs: isolate design system migration guidance"
```

### Task 7: Complete content review, resolve references, and enforce the gate locally and in CI

**Files:**
- Modify: `scripts/check-design-system-docs.js`
- Modify: `scripts/tests/check-design-system-docs.test.js`
- Modify: `.github/workflows/ci.yml`
- Modify: `.husky/pre-commit`
- Modify: all relevant new design-system Markdown files only when review identifies a remaining duplicate, broken link, or line-limit violation.

**Interfaces:**
- Consumes: complete Markdown graph and `check-config.json`.
- Produces: repeatable local, hook and CI enforcement of all documentary acceptance criteria.

- [ ] **Step 1: Extend fixture tests for all required quality gates**

Add tests that prove a 101-line Markdown file fails, a missing relative file fails, a nonexistent anchor fails, an unlinked Markdown file fails, and each configured forbidden legacy identifier fails. Add a passing fixture whose root README links a domain README, which links a content document. Keep tests self-contained with `fs.mkdtempSync`; do not depend on the working tree.

- [ ] **Step 2: Verify tests fail before any new validator change**

Run: `node scripts/tests/check-design-system-docs.test.js`

Expected: failure if one newly asserted behavior is not yet implemented. If all tests already pass because the initial implementation covers the behavior, record that no production change is needed and proceed without artificial code churn.

- [ ] **Step 3: Update the checker only for demonstrated gaps**

Keep the command portable by deriving the default root with `path.join(__dirname, '..', 'CRM-Docs', 'design-system')`. Do not add npm packages, network checks or an absolute repository path. The CLI must show `source:line`, violation category, and exit 1 for failures.

- [ ] **Step 4: Add a dedicated CI job**

Append this job to `.github/workflows/ci.yml`:

```yaml
  design-system-docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '18'
      - name: Test design-system documentation checker
        run: node scripts/tests/check-design-system-docs.test.js
      - name: Check design-system documentation
        run: node scripts/check-design-system-docs.js
```

Ensure the job has no dependency on frontend/backend jobs so documentation failures are reported quickly.

- [ ] **Step 5: Add staged-document hook enforcement**

In `.husky/pre-commit`, inside the existing `CRM-Docs/` staged-file conditional, add:

```sh
if git diff --cached --name-only | grep -q '^CRM-Docs/design-system/'; then
  node scripts/check-design-system-docs.js
fi
```

The hook must run the full design-system graph only when a design-system Markdown/config file is staged; do not run it for unrelated docs or every frontend commit.

- [ ] **Step 6: Run the complete validation sequence**

Run:

```bash
node scripts/tests/check-design-system-docs.test.js
node scripts/check-design-system-docs.js
find CRM-Docs/design-system -name '*.md' -print0 | xargs -0 wc -l
git grep -nE 'CRM-Docs/design-system/(MASTER|ELEMENT-PLUS-MIGRATION|pages/(list-page|detail-page|form-page|approval-center))\.md' -- ':!docs/superpowers/**' || true
git diff --check
```

Expected: tests and checker pass; every Markdown count is at most 100; no operational old-path references remain; whitespace check is clean.

- [ ] **Step 7: Review all claims and duplicates before final commit**

Perform a two-column review: each new file’s rules vs. its owner listed in Tasks 3–6. Delete duplicate prose; replace it with relative links. Confirm every existing rule is either migrated, deliberately removed as obsolete, or recorded as a product/feature-document follow-up. No unresolved semantic conflicts may remain because the user decisions in Global Constraints are final.

- [ ] **Step 8: Commit the enforcement and final review**

```bash
git add scripts/check-design-system-docs.js scripts/tests/check-design-system-docs.test.js .github/workflows/ci.yml .husky/pre-commit CRM-Docs/design-system
git commit -m "ci: enforce design system documentation quality"
```

## Final Acceptance Checklist

- [ ] All documentation files under `CRM-Docs/design-system/` are 100 lines or less.
- [ ] Root and local indexes form a complete clickable graph; the checker reports every document reachable from root.
- [ ] Every global rule has one owner and page patterns do not reproduce component/foundation contracts.
- [ ] No old design-system filename/path remains in operational documentation.
- [ ] All approved semantic decisions in Global Constraints appear only in their SSOT document(s).
- [ ] Target documents are framework-independent; Element Plus occurs only under `migration/`.
- [ ] Checker fixtures, direct CLI checker, staged pre-commit behavior and CI job all succeed.
