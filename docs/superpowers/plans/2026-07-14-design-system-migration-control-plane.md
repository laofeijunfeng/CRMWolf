# Design System Migration Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立自动化迁移台账和“禁止新增遗留债务”门禁，使 CRMWolf 能按依赖顺序从 V1 令牌与旧框架收敛到唯一设计系统，并在台账归零后安全清退全部兼容层。

**Architecture:** `CRM-Docs/design-system/README.md` 保持唯一规则入口；Node 脚本扫描版本控制的前端文件，输出只读事实台账并通过基线识别新增债务。迁移期间门禁只阻止新增的 V1、旧框架和旧路径，P1–P4 按共享依赖和页面族逐批削减清单；P5 才删除运行时 V1 文件并切换为零容忍检查。

**Tech Stack:** Node.js 18 CommonJS（`fs`、`path`、`child_process`、`assert`）、Markdown、Git、GitHub Actions、POSIX shell、Vitest。

## Global Constraints

- `CRM-Docs/design-system/README.md` 是唯一设计规则入口；运行时令牌实现不得自行定义冲突的设计决策。
- 自动生成的 `v1-usage-inventory.md` 禁止人工编辑，必须由当前版本控制的前端文件完全重建。
- 扫描排除 `.git`、`node_modules`、`dist`、虚拟环境和 `.claude/worktrees`；仅扫描受 Git 跟踪文件。
- 遗留信号为：V1 样式导入、无 `-v2` 后缀的 `$wolf-*` 令牌、Element Plus/图标/API、旧设计文档路径和非权威原型。
- 迁移期间禁止在修改或新增文件中引入遗留信号；已存在存量仅可保留在清单中，删除永远允许。
- P0 直接删除七份非权威原型，不归档：四份根目录 navigation 原型和三份 `docs/ui-ux/customer-detail-*.html`。
- P5 前不得删除 `variables.scss`、`wolf-design.scss` 或 `element-plus-theme.scss`；其删除前提是扫描结果为零。
- 每个设计系统 Markdown 不超过 100 行，并通过现有链接、索引和旧路径检查。
- 不增加第三方 npm 依赖，不在扫描或 CI 检查中访问网络，不硬编码本机绝对路径。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `scripts/design-system-migration-lib.js` | 扫描、归类、基线比较和 Markdown 台账生成的纯函数库 |
| `scripts/generate-design-system-inventory.js` | 生成/覆盖 V1 使用台账的 CLI |
| `scripts/check-design-system-migration.js` | 对 Git diff 执行无新增遗留债务门禁的 CLI |
| `scripts/tests/design-system-migration-lib.test.js` | 使用临时 Git fixture 测试扫描、分类、基线与输出 |
| `scripts/tests/check-design-system-migration.test.js` | 测试 diff 门禁的通过、失败、删除例外和最终模式 |
| `CRM-Docs/design-system/migration/v1-usage-inventory.md` | 生成的当前存量台账 |
| `CRM-Docs/design-system/migration/migration-playbook.md` | 唯一迁移流程、P0–P5 批次和验收条件 |
| `CRM-Docs/design-system/migration/README.md` | 链接台账和迁移手册 |
| `CRM-Docs/design-system/governance/quality-checks.md` | 记录生成、门禁和最终模式命令 |
| `CRM-Client/.design-system-migration-baseline.json` | 已批准的遗留事实基线，含稳定指纹 |
| `.github/workflows/ci.yml` | 运行脚本测试、清单一致性和 diff 门禁 |
| `.husky/pre-commit` | 对暂存前端/设计文档文件运行 no-new-legacy 检查 |

---

### Task 1: 删除非权威原型并建立迁移入口

**Files:**
- Delete: `navigation-redesign.html`
- Delete: `navigation-redesign-v2.html`
- Delete: `navigation-redesign-v3.html`
- Delete: `navigation-problems.html`
- Delete: `docs/ui-ux/customer-detail-sidebar-final.html`
- Delete: `docs/ui-ux/customer-detail-tabs-comparison.html`
- Delete: `docs/ui-ux/customer-detail-improvements.html`
- Create: `CRM-Docs/design-system/migration/migration-playbook.md`
- Modify: `CRM-Docs/design-system/migration/README.md`
- Modify: `CRM-Docs/design-system/governance/quality-checks.md`

**Interfaces:**
- Produces: `migration-playbook.md` with P0–P5 scope, current-only authority, batch exit checks and P5 deletion preconditions.
- Produces: no tracked visual prototype outside the canonical design-system directory.

- [ ] **Step 1: Confirm the seven tracked prototype paths before deleting**

Run:

```bash
git ls-files navigation-redesign.html navigation-redesign-v2.html navigation-redesign-v3.html navigation-problems.html docs/ui-ux/customer-detail-sidebar-final.html docs/ui-ux/customer-detail-tabs-comparison.html docs/ui-ux/customer-detail-improvements.html
```

Expected: exactly seven paths, matching the Files list.

- [ ] **Step 2: Remove the confirmed non-authoritative prototypes**

```bash
git rm navigation-redesign.html navigation-redesign-v2.html navigation-redesign-v3.html navigation-problems.html
git rm docs/ui-ux/customer-detail-sidebar-final.html docs/ui-ux/customer-detail-tabs-comparison.html docs/ui-ux/customer-detail-improvements.html
```

- [ ] **Step 3: Write the migration playbook**

Create `CRM-Docs/design-system/migration/migration-playbook.md` with a metadata header, then document: P0 inventory/baseline and direct prototype deletion; P1 shared components/navigation; P2 list pages; P3 detail pages/Sheet/Drawer; P4 forms, approvals and finance; P5 zero-result deletion. Each phase must require inventory regeneration, affected tests, `node scripts/check-design-system-docs.js`, and no new legacy findings. State P5 preconditions exactly: zero inventory, V1 style files removed, old framework removed, old references absent.

- [ ] **Step 4: Link the new migration sources**

Add relative links to `migration-playbook.md` and `v1-usage-inventory.md` in `migration/README.md`. In `governance/quality-checks.md`, reserve the two commands that Tasks 3–5 will add:

```bash
node scripts/generate-design-system-inventory.js
node scripts/check-design-system-migration.js --diff --cached
```

- [ ] **Step 5: Verify links and file limits**

Run:

```bash
node scripts/check-design-system-docs.js
find CRM-Docs/design-system -name '*.md' -print0 | xargs -0 wc -l
git diff --check
```

Expected: documentation checker succeeds; every listed Markdown is at most 100 lines; whitespace check is clean.

- [ ] **Step 6: Commit the P0 document/prototype cleanup**

```bash
git add CRM-Docs/design-system/migration CRM-Docs/design-system/governance
git commit -m "docs: remove obsolete design prototypes"
```

### Task 2: Implement and test the migration scanning library

**Files:**
- Create: `scripts/design-system-migration-lib.js`
- Create: `scripts/tests/design-system-migration-lib.test.js`

**Interfaces:**
- Produces: `collectTrackedFiles(repoRoot, pathspecs) -> string[]`
- Produces: `scanLegacySignals(repoRoot, files) -> Array<{file, line, category, match, classification, replacement}>`
- Produces: `createFingerprint(finding) -> string` using `file`, `line`, `category`, and `match`.
- Produces: `buildInventory(findings, generatedAt) -> string`.
- Produces: `compareBaseline(findings, baseline) -> { added: Finding[], removed: Finding[] }`.

- [ ] **Step 1: Write failing fixture tests for the scanner contract**

```js
const assert = require('assert')
const fs = require('fs')
const os = require('os')
const path = require('path')
const {
  scanLegacySignals,
  createFingerprint,
  compareBaseline,
  buildInventory,
} = require('../design-system-migration-lib')

const root = fs.mkdtempSync(path.join(os.tmpdir(), 'design-migration-'))
const write = (name, text) => {
  const file = path.join(root, name)
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, text)
  return file
}

const page = write('CRM-Client/src/views/Customers.vue', "@use '@/styles/variables.scss';\nconst message = ElMessage.success('ok')\n")
const component = write('CRM-Client/src/components/Filter.vue', "<el-input />\n")
const docs = write('CRM-Client/docs/legacy.md', 'See CRM-Docs/design-system/MASTER.md\n')
const findings = scanLegacySignals(root, [page, component, docs])

assert.deepStrictEqual(findings.map(f => f.category).sort(), ['element-plus-api', 'element-plus-template', 'legacy-doc-path', 'v1-style-import'])
assert.ok(findings.every(f => f.line > 0 && f.replacement.length > 0))
assert.strictEqual(findings.find(f => f.file.endsWith('Customers.vue')).classification, 'page')
const baseline = { version: 1, findings: [findings[0]] }
assert.strictEqual(compareBaseline(findings, baseline).added.length, findings.length - 1)
assert.match(buildInventory(findings, '2026-07-14'), /禁止人工编辑/)
console.log('design-system-migration-lib tests passed')
```

- [ ] **Step 2: Run tests and confirm the missing-module failure**

Run: `node scripts/tests/design-system-migration-lib.test.js`

Expected: failure containing `Cannot find module '../design-system-migration-lib'`.

- [ ] **Step 3: Implement exact signal definitions and classification**

In `scripts/design-system-migration-lib.js`, define these categories and replacements:

```js
const SIGNALS = [
  ['v1-style-import', /(?:@use|@import)\s+['"][^'"]*(?:variables|wolf-design|element-plus-theme)\.scss['"]/, '使用 variables-v2.scss 或目标 shadcn-vue 样式'],
  ['v1-token', /\$wolf-(?![\w-]*-v2\b)[\w-]+/, '使用对应的 $wolf-*-v2 令牌'],
  ['element-plus-import', /from\s+['"](?:element-plus|@element-plus\/icons-vue)['"]/, '使用 CRM-Docs/design-system/migration/element-plus-to-shadcn-vue.md 中的目标组件'],
  ['element-plus-template', /<\/?el-[\w-]+\b/, '使用目标 shadcn-vue 组件'],
  ['element-plus-api', /\b(?:ElMessage|ElMessageBox|ElNotification)\b/, '使用 toast 或 AlertDialog'],
  ['legacy-doc-path', /(?:CRM-Docs\/design-system\/)?(?:MASTER\.md|ELEMENT-PLUS-MIGRATION\.md|pages\/(?:list-page|detail-page|form-page|approval-center)\.md)/, '链接 CRM-Docs/design-system/README.md 或精确主题文件'],
]
```

Classify relative paths: `src/styles/` → `全局样式`; `src/components/ui/` → `UI 基元`; `src/components/` → `共享组件`; `src/views/` → `页面`; `tests/`/`__tests__/` → `测试`; `*.config.*`/`components.json` → `配置`; `*.md` → `文档/计划`; otherwise `其他`.

Use a fresh non-global RegExp per line or reset `lastIndex` before every execution. Only examine tracked files returned by `git ls-files`; do not walk build outputs or worktrees.

- [ ] **Step 4: Implement deterministic baseline and inventory formatting**

Baseline JSON shape:

```json
{
  "version": 1,
  "findings": [{"file":"CRM-Client/src/views/Customers.vue","line":1,"category":"v1-style-import","match":"variables.scss","classification":"页面","replacement":"使用 variables-v2.scss 或目标 shadcn-vue 样式","fingerprint":"..."}]
}
```

Inventory must begin with `# V1 使用台账`, then generated date, `> 此文件由 ... 自动生成，禁止人工编辑。`, totals by category and classification, priority sections in this order: 全局样式, 共享组件, 页面, UI 基元, 测试, 配置, 文档/计划, 其他. Include one finding per line with `file:line`, signal, match and replacement.

- [ ] **Step 5: Run the scanner tests to verify success**

Run: `node scripts/tests/design-system-migration-lib.test.js`

Expected: `design-system-migration-lib tests passed`.

- [ ] **Step 6: Commit the tested scanning library**

```bash
git add scripts/design-system-migration-lib.js scripts/tests/design-system-migration-lib.test.js
git commit -m "feat: add design system migration scanner"
```

### Task 3: Generate the approved V1 inventory and baseline

**Files:**
- Create: `scripts/generate-design-system-inventory.js`
- Create: `CRM-Client/.design-system-migration-baseline.json`
- Modify: `CRM-Docs/design-system/migration/v1-usage-inventory.md`
- Test: `scripts/tests/design-system-migration-lib.test.js`

**Interfaces:**
- Consumes: `scanLegacySignals`, `createFingerprint`, and `buildInventory` from Task 2.
- Produces: an exact checked-in baseline and generated Markdown that describe the same finding set.

- [ ] **Step 1: Add a failing CLI-output test**

Append to `scripts/tests/design-system-migration-lib.test.js`:

```js
const { generateInventory } = require('../generate-design-system-inventory')
const output = path.join(root, 'inventory.md')
const baselinePath = path.join(root, 'baseline.json')
const result = generateInventory({ repoRoot: root, files: findings.map(f => path.join(root, f.file)), output, baselinePath, generatedAt: '2026-07-14' })
assert.strictEqual(JSON.parse(fs.readFileSync(baselinePath, 'utf8')).findings.length, findings.length)
assert.match(fs.readFileSync(output, 'utf8'), /# V1 使用台账/)
assert.strictEqual(result.findings.length, findings.length)
```

- [ ] **Step 2: Run test to confirm the missing generator export**

Run: `node scripts/tests/design-system-migration-lib.test.js`

Expected: failure containing `Cannot find module '../generate-design-system-inventory'`.

- [ ] **Step 3: Implement the generator CLI and export**

```js
function generateInventory({ repoRoot, files, output, baselinePath, generatedAt }) {
  const findings = scanLegacySignals(repoRoot, files || collectTrackedFiles(repoRoot, ['CRM-Client']))
  const withFingerprints = findings.map(finding => ({ ...finding, fingerprint: createFingerprint(finding) }))
  fs.writeFileSync(output, buildInventory(withFingerprints, generatedAt || new Date().toISOString().slice(0, 10)))
  fs.writeFileSync(baselinePath, JSON.stringify({ version: 1, findings: withFingerprints }, null, 2) + '\n')
  return { findings: withFingerprints }
}
```

The no-argument CLI must resolve all paths relative to its own file, write to:

```text
CRM-Docs/design-system/migration/v1-usage-inventory.md
CRM-Client/.design-system-migration-baseline.json
```

Print `✓ Generated <count> migration findings` and exit 0.

- [ ] **Step 4: Generate the real repository baseline and inventory**

Run:

```bash
node scripts/generate-design-system-inventory.js
node scripts/check-design-system-docs.js
```

Expected: both commands succeed; generated Markdown is at most 100 lines. If the real inventory cannot fit within 100 lines, change the generated file into a ≤100-line executive summary that links to a generated JSON detail file at `CRM-Client/.design-system-migration-baseline.json`; do not weaken the line-limit checker.

- [ ] **Step 5: Verify baseline and inventory describe identical findings**

Run:

```bash
node - <<'NODE'
const fs = require('fs')
const baseline = JSON.parse(fs.readFileSync('CRM-Client/.design-system-migration-baseline.json', 'utf8'))
console.log(`baseline findings: ${baseline.findings.length}`)
console.log(fs.readFileSync('CRM-Docs/design-system/migration/v1-usage-inventory.md', 'utf8').includes(`总计：${baseline.findings.length}`) ? 'inventory total matches' : 'inventory total mismatch')
NODE
```

Expected: a positive integer and `inventory total matches`.

- [ ] **Step 6: Commit the reproducible migration baseline**

```bash
git add scripts/generate-design-system-inventory.js CRM-Client/.design-system-migration-baseline.json CRM-Docs/design-system/migration/v1-usage-inventory.md scripts/tests/design-system-migration-lib.test.js
git commit -m "docs: add V1 migration inventory"
```

### Task 4: Add and test the no-new-legacy diff gate

**Files:**
- Create: `scripts/check-design-system-migration.js`
- Create: `scripts/tests/check-design-system-migration.test.js`
- Modify: `.husky/pre-commit`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: baseline JSON and scanner library from Tasks 2–3.
- Produces: `checkMigration({ repoRoot, diffRef, cached, finalMode }) -> { added, removed, staleInventory }`.
- Produces: CLI `node scripts/check-design-system-migration.js --diff <ref>` and `--cached`, each exit 1 only for added legacy findings, stale inventory, malformed baseline, or final-mode findings.

- [ ] **Step 1: Write failing Git-fixture tests for additive, subtractive and final-mode behavior**

```js
const assert = require('assert')
const childProcess = require('child_process')
const fs = require('fs')
const os = require('os')
const path = require('path')
const { checkMigration } = require('../check-design-system-migration')

const repo = fs.mkdtempSync(path.join(os.tmpdir(), 'migration-gate-'))
childProcess.execFileSync('git', ['init'], { cwd: repo })
childProcess.execFileSync('git', ['config', 'user.email', 'test@example.com'], { cwd: repo })
childProcess.execFileSync('git', ['config', 'user.name', 'Test'], { cwd: repo })
fs.mkdirSync(path.join(repo, 'CRM-Client/src/views'), { recursive: true })
fs.writeFileSync(path.join(repo, 'CRM-Client/src/views/Old.vue'), "@use '@/styles/variables.scss';\n")
childProcess.execFileSync('git', ['add', '.'], { cwd: repo })
childProcess.execFileSync('git', ['commit', '-m', 'baseline'], { cwd: repo })
fs.writeFileSync(path.join(repo, 'CRM-Client/src/views/New.vue'), "<el-button />\n")
let result = checkMigration({ repoRoot: repo, diffRef: 'HEAD' })
assert.strictEqual(result.added.length, 1)
fs.unlinkSync(path.join(repo, 'CRM-Client/src/views/New.vue'))
fs.writeFileSync(path.join(repo, 'CRM-Client/src/views/Old.vue'), '')
result = checkMigration({ repoRoot: repo, diffRef: 'HEAD' })
assert.strictEqual(result.added.length, 0)
assert.ok(result.removed.length > 0)
assert.throws(() => checkMigration({ repoRoot: repo, diffRef: 'HEAD', finalMode: true }), /final mode/)
console.log('check-design-system-migration tests passed')
```

- [ ] **Step 2: Run the gate tests and verify module-not-found failure**

Run: `node scripts/tests/check-design-system-migration.test.js`

Expected: failure containing `Cannot find module '../check-design-system-migration'`.

- [ ] **Step 3: Implement diff-aware scanning**

For `--diff <ref>`, obtain changed non-deleted files with:

```js
execFileSync('git', ['diff', '--name-only', '--diff-filter=ACMR', diffRef], { cwd: repoRoot, encoding: 'utf8' })
```

For `--cached`, replace `diff` with `diff --cached`. Scan only those files and compare each result fingerprint to the committed baseline. Do not fail a file only because a finding moved line numbers; identify an added signal by stable `file + category + match` key, while the JSON fingerprint retains line detail for reporting. A deleted file creates no added finding. `finalMode` must scan every tracked `CRM-Client` file and throw if any finding exists.

- [ ] **Step 4: Make inventory freshness a hard requirement**

At every CLI run, call the scanner for all tracked `CRM-Client` files and compare the sorted stable keys to the baseline. If they differ, report:

```text
✗ migration inventory is stale; run node scripts/generate-design-system-inventory.js
```

The CLI exits 1, except when invoked by the generator itself. This prevents code changes from silently leaving the checked-in inventory stale.

- [ ] **Step 5: Run tests and manual gate scenarios**

Run:

```bash
node scripts/tests/check-design-system-migration.test.js
node scripts/check-design-system-migration.js --diff HEAD
node scripts/check-design-system-migration.js --final-mode || true
```

Expected: fixture tests pass; current-branch diff check succeeds when baseline is fresh and no new findings were introduced; final mode reports current legacy findings and exits nonzero.

- [ ] **Step 6: Integrate the gate into hook and CI**

In `.husky/pre-commit`, before the success message, add a staged-file guard:

```sh
if git diff --cached --name-only | grep -qE '^(CRM-Client/|CRM-Docs/design-system/|scripts/)'; then
  node scripts/check-design-system-migration.js --cached
fi
```

In `.github/workflows/ci.yml`, add an independent Node 18 job named `design-system-migration` that runs, in order:

```yaml
      - name: Test migration scanner
        run: node scripts/tests/design-system-migration-lib.test.js
      - name: Test migration gate
        run: node scripts/tests/check-design-system-migration.test.js
      - name: Verify generated migration inventory
        run: |
          node scripts/generate-design-system-inventory.js
          git diff --exit-code -- CRM-Docs/design-system/migration/v1-usage-inventory.md CRM-Client/.design-system-migration-baseline.json
      - name: Block new legacy design dependencies
        run: node scripts/check-design-system-migration.js --diff HEAD~1
```

- [ ] **Step 7: Commit the enforced migration gate**

```bash
git add scripts/check-design-system-migration.js scripts/tests/check-design-system-migration.test.js .husky/pre-commit .github/workflows/ci.yml
git commit -m "ci: block new legacy design dependencies"
```

### Task 5: Converge external design guidance and remove stale references

**Files:**
- Modify: `CRM-Client/src/styles/variables-v2.scss`
- Modify: `CRM-Client/src/styles/element-plus-theme-v2.scss`
- Modify: `CRM-Client/stylelint.config.js`
- Modify: `CRM-Client/.stylelintrc.design-system.js`
- Modify: `CRM-Client/src/styles/variables.scss`
- Modify: `CRM-Client/docs/LAYOUT.md`
- Modify: `CRM-Client/docs/ANIMATION-GUIDELINES.md`
- Modify: `CRM-Client/docs/COMPONENTS.md`
- Modify: `CRM-Client/docs/DETAIL-SHEET-COMPONENT.md`
- Modify: `CRM-Client/docs/design-system/MIGRATION.md`
- Modify: `CRM-Docs/design-system/{foundations/motion-performance,components/modal-sheet,governance/authoring,migration/compatibility}.md`
- Modify: `CRM-Docs/design-system/migration/v1-usage-inventory.md`

**Interfaces:**
- Consumes: current inventory and no-new-legacy gate from Tasks 3–4.
- Produces: no source/config/client-doc reference to deleted `MASTER.md` or old `pages/*.md`; external client docs contain implementation/API details only.

- [ ] **Step 1: Capture failing stale-reference assertion**

Add to `scripts/tests/design-system-migration-lib.test.js` a fixture whose comment reads `CRM-Docs/design-system/MASTER.md`; assert it produces `legacy-doc-path` with a replacement pointing to `CRM-Docs/design-system/README.md` or a specific topic.

- [ ] **Step 2: Update runtime/config references to exact target documents**

Apply this mapping:

| Existing concern | New reference |
|---|---|
| V2 tokens and colors | `CRM-Docs/design-system/foundations/color-tokens.md` |
| V2 spacing, radius and responsive behavior | `foundations/spacing-layout.md`, `radius-elevation.md`, `responsive-mobile.md` |
| element theme/component migration | `migration/element-plus-to-shadcn-vue.md` |
| Stylelint constraints | `governance/authoring.md` and applicable foundation token file |
| modal/sheet z-index and portal behavior | `components/modal-sheet.md` |
| motion/reduced motion | `foundations/motion-performance.md` |

Change comments only; do not alter runtime token values in this task. In `variables.scss`, prepend a deprecation header: V1 transitional only, do not add consumers, see `migration-playbook.md`, removal only at P5.

- [ ] **Step 3: Extract unique rules before reducing client documents**

Move animation timing/reduced-motion rules from `ANIMATION-GUIDELINES.md` into `foundations/motion-performance.md` only when absent. Move portal/z-index contract rules from `LAYOUT.md` into `components/modal-sheet.md` only when absent. Move generic component authoring rules from `COMPONENTS.md` into `governance/authoring.md` only when absent. Move V1-to-V2 mapping from client `MIGRATION.md` into `migration/compatibility.md` only when absent. Keep each canonical Markdown ≤100 lines; split a canonical topic only by named subtopic if necessary.

- [ ] **Step 4: Reduce or remove superseded client documents**

For each source client document, retain only implementation/API material that cannot live in a framework-independent rule. If it has no remaining implementation/API content, delete it. Any retained file begins with a single sentence: `设计规则以 CRM-Docs/design-system/README.md 为准。` and uses relative links to its precise target rules.

- [ ] **Step 5: Regenerate inventory and validate stale-path removal**

Run:

```bash
node scripts/generate-design-system-inventory.js
git grep -nE 'CRM-Docs/design-system/(MASTER|ELEMENT-PLUS-MIGRATION|pages/)|MASTER\.md' -- ':!docs/superpowers/**' ':!CRM-Client/.claude/plans/**' ':!scripts/tests/**' ':!CRM-Docs/design-system/governance/check-config.json' || true
node scripts/tests/design-system-migration-lib.test.js
node scripts/check-design-system-docs.js
```

Expected: no command output from `git grep`; scanner and design-doc tests pass.

- [ ] **Step 6: Commit converged guidance**

```bash
git add CRM-Client/src/styles CRM-Client/docs CRM-Client/stylelint.config.js CRM-Client/.stylelintrc.design-system.js CRM-Docs/design-system scripts/tests/design-system-migration-lib.test.js
git commit -m "docs: align implementation guidance with design system"
```

### Task 6: Execute P1 shared component and navigation migration

**Files:**
- Modify: files listed in generated inventory under classification `共享组件` and `UI 基元`.
- Modify: `CRM-Docs/design-system/migration/v1-usage-inventory.md`
- Modify: `CRM-Client/.design-system-migration-baseline.json`
- Test: affected `CRM-Client/tests/components/**/*.spec.ts` and component-local tests.

**Interfaces:**
- Consumes: migration playbook, inventory and gate.
- Produces: zero V1 and Element Plus signals for all P1 shared components/navigation components.

- [ ] **Step 1: Capture the P1 worklist from generated inventory**

Run:

```bash
node scripts/generate-design-system-inventory.js
awk '/^## 共享组件/,/^## 页面/' CRM-Docs/design-system/migration/v1-usage-inventory.md
awk '/^## UI 基元/,/^## 测试/' CRM-Docs/design-system/migration/v1-usage-inventory.md
```

Expected: exact file/line worklist; use it as the task scope and do not migrate page-only files in this task.

- [ ] **Step 2: Add failing tests for each shared component behavior before migration**

For every component without a covering test, create a test under `CRM-Client/tests/components/` that mounts it with its existing public props and asserts the current public behavior. Example for a navigation component:

```ts
it('emits navigation when an enabled item is selected', async () => {
  const wrapper = mount(BottomNav, { props: { items, modelValue: 'customers' } })
  await wrapper.get('[data-nav-key="leads"]').trigger('click')
  expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['leads'])
})
```

- [ ] **Step 3: Migrate imports, tokens and old framework uses file by file**

For each P1 file: replace V1 style imports with `variables-v2.scss`; replace `$wolf-*` with the mapped `-v2` token; replace old framework UI primitives using `migration/element-plus-to-shadcn-vue.md`; preserve public props/events. Do not add compatibility aliases or new direct pixel/hex values.

- [ ] **Step 4: Run focused component tests after each component family**

Run, substituting the actual migrated test file list:

```bash
cd CRM-Client && npm run test:unit -- tests/components/BottomNav.spec.ts tests/components/AppLayout.spec.ts
```

Expected: all selected tests pass.

- [ ] **Step 5: Regenerate the inventory and prove P1 is zero**

Run:

```bash
node scripts/generate-design-system-inventory.js
node scripts/check-design-system-migration.js --diff HEAD
awk '/^## 共享组件/,/^## 页面/' CRM-Docs/design-system/migration/v1-usage-inventory.md
git diff --check
```

Expected: P1 sections report zero findings; gate and whitespace check pass.

- [ ] **Step 6: Commit P1 migration**

```bash
git add CRM-Client/src/components CRM-Client/tests/components CRM-Client/.design-system-migration-baseline.json CRM-Docs/design-system/migration/v1-usage-inventory.md
git commit -m "refactor: migrate shared UI components to V2"
```

### Task 7: Execute P2 list-page families

**Files:**
- Modify: generated-inventory page entries for list routes and their direct list-only dependencies.
- Modify: inventory and baseline files.
- Test: list-page view and table/filter tests identified from inventory.

**Interfaces:**
- Consumes: P1 V2 shared components.
- Produces: zero legacy signals for list route families: leads, customers, opportunities, contracts, payments, invoices and their list-only components.

- [ ] **Step 1: Generate and freeze the list-family worklist**

Run:

```bash
node scripts/generate-design-system-inventory.js
awk '/^## 页面/,/^## UI 基元/' CRM-Docs/design-system/migration/v1-usage-inventory.md | grep -E 'Leads|Customers|Opportunities|Contracts|Payments|Invoices|DataTable|FilterPanel'
```

Expected: a concrete file/line list for this batch.

- [ ] **Step 2: Write failing route-level tests for uncovered list pages**

For each untested route, add a test that mounts the page with mocked API data and verifies: filter interaction, table/empty state selection, and pagination or navigation action. Use the existing app test helper pattern; do not snapshot styling.

- [ ] **Step 3: Replace legacy signals in the list worklist**

Migrate each listed file to V2 tokens and target components. Keep the required design behavior from canonical list pattern: no page-body horizontal scroll, table container scroll allowed only when data density needs it. Do not repeat numeric visual values in page source.

- [ ] **Step 4: Run list route tests and type checks**

```bash
cd CRM-Client
npm run test:unit -- tests/views/Leads.spec.ts tests/views/Customers.spec.ts
npm run type-check
```

Expected: selected route tests pass; type-check must not introduce new errors relative to baseline.

- [ ] **Step 5: Regenerate and verify P2 exit**

Run:

```bash
node scripts/generate-design-system-inventory.js
node scripts/check-design-system-migration.js --diff HEAD
grep -A3 'P2 列表页族' CRM-Docs/design-system/migration/v1-usage-inventory.md
git diff --check
```

Expected: P2 summary shows zero direct legacy signals for the list family.

- [ ] **Step 6: Commit P2 migration**

```bash
git add CRM-Client/src/views CRM-Client/src/components CRM-Client/tests CRM-Client/.design-system-migration-baseline.json CRM-Docs/design-system/migration/v1-usage-inventory.md
git commit -m "refactor: migrate list pages to V2 design system"
```

### Task 8: Execute P3 detail pages, Sheet and Drawer migration

**Files:**
- Modify: generated inventory entries for detail routes, detail sheets/drawers and their direct panels.
- Modify: inventory and baseline files.
- Test: DetailSheet, Dialog/Sheet/Drawer and detail route tests.

**Interfaces:**
- Consumes: P1 shared contracts and canonical `components/modal-sheet.md`.
- Produces: zero legacy signals for detail pages, panels, Sheet/Drawer and modal composition.

- [ ] **Step 1: Generate the detail-family worklist**

Run:

```bash
node scripts/generate-design-system-inventory.js
grep -E 'Detail|DetailSheet|Sheet|Drawer|Panel' CRM-Docs/design-system/migration/v1-usage-inventory.md
```

- [ ] **Step 2: Write behavior tests before replacing UI primitives**

For each migrated detail surface, test opening from its trigger, correct title/content presence, escape/close behavior, and focus restoration. Example:

```ts
it('restores focus to the trigger when the detail sheet closes', async () => {
  const wrapper = mount(CustomerDetailSheet, { attachTo: document.body, props: { open: true, customer } })
  await wrapper.get('[aria-label="关闭"]').trigger('click')
  expect(wrapper.emitted('update:open')?.[0]).toEqual([false])
})
```

- [ ] **Step 3: Replace V1 styles and old framework detail primitives**

Use target Sheet/Drawer/Dialog primitives and V2 tokens. Follow `components/modal-sheet.md` for Portal and z-index behavior. Do not retain old overlay/theme helper styles after their last caller is gone.

- [ ] **Step 4: Run focused detail tests**

```bash
cd CRM-Client
npm run test:unit -- tests/components/CustomerDetailSheet.spec.ts tests/components/AppLayout.spec.ts
```

Expected: passing tests with no focus/portal regressions.

- [ ] **Step 5: Regenerate inventory and verify P3 exit**

Run:

```bash
node scripts/generate-design-system-inventory.js
node scripts/check-design-system-migration.js --diff HEAD
git diff --check
```

Expected: no P3-classified detail/sheet/drawer legacy findings.

- [ ] **Step 6: Commit P3 migration**

```bash
git add CRM-Client/src/components CRM-Client/src/views CRM-Client/tests CRM-Client/.design-system-migration-baseline.json CRM-Docs/design-system/migration/v1-usage-inventory.md
git commit -m "refactor: migrate detail surfaces to V2"
```

### Task 9: Execute P4 forms, approval, finance and special-flow migration

**Files:**
- Modify: remaining generated inventory source entries after P1–P3.
- Modify: inventory and baseline files.
- Test: affected form, approval and finance route/component tests.

**Interfaces:**
- Consumes: all prior phases and target migration mapping.
- Produces: only P5 global legacy files remain, with no page/component-level legacy signals.

- [ ] **Step 1: Generate the remaining production worklist**

Run:

```bash
node scripts/generate-design-system-inventory.js
grep -E 'Approval|Finance|Payment|Invoice|Form|Dialog|Config|License' CRM-Docs/design-system/migration/v1-usage-inventory.md
```

- [ ] **Step 2: Add failing public-flow tests**

For each untested feature, add a test covering its primary submit/approve/confirm flow with an error case. Use existing component props/events and mock network boundaries; do not assert legacy DOM tags.

- [ ] **Step 3: Replace all listed legacy tokens/framework APIs**

Use V2 tokens and mapped target components. Map notification APIs to `toast` and destructive confirmation to `AlertDialog`; preserve API requests, validation and user-visible semantics.

- [ ] **Step 4: Run affected tests in groups**

```bash
cd CRM-Client
npm run test:unit -- tests/views/AccountSettings.spec.ts tests/components/ApprovalProcess.spec.ts
npm run type-check
```

Expected: selected flows pass and no new type-check errors are introduced.

- [ ] **Step 5: Generate the final pre-cleanup inventory**

Run:

```bash
node scripts/generate-design-system-inventory.js
node scripts/check-design-system-migration.js --diff HEAD
```

Expected: only P5 global legacy style/theme files and their `main.ts` imports remain. If any page/component finding remains, keep it in P4 and do not start Task 10.

- [ ] **Step 6: Commit P4 migration**

```bash
git add CRM-Client/src CRM-Client/tests CRM-Client/.design-system-migration-baseline.json CRM-Docs/design-system/migration/v1-usage-inventory.md
git commit -m "refactor: migrate remaining flows to V2"
```

### Task 10: Execute P5 final V1 and old-framework cleanup

**Files:**
- Delete: `CRM-Client/src/styles/variables.scss`
- Delete: `CRM-Client/src/styles/wolf-design.scss`
- Delete: `CRM-Client/src/styles/element-plus-theme.scss`
- Modify: `CRM-Client/src/main.ts`
- Modify: `CRM-Client/package.json`
- Modify: `CRM-Client/package-lock.json`
- Modify: `CRM-Client/.design-system-migration-baseline.json`
- Modify: `CRM-Docs/design-system/migration/{compatibility,implementation-status,v1-usage-inventory,migration-playbook}.md`
- Modify: `scripts/check-design-system-migration.js`
- Modify: `scripts/tests/check-design-system-migration.test.js`

**Interfaces:**
- Consumes: a zero page/component inventory from Task 9.
- Produces: final-mode zero findings; no V1 style file, old framework dependency, compatibility alias, legacy reference or prototype remains.

- [ ] **Step 1: Assert zero legacy inventory before deletions**

Run:

```bash
node scripts/generate-design-system-inventory.js
node scripts/check-design-system-migration.js --final-mode
```

Expected before this task: final mode fails only on the known P5 files/imports. If any other finding is printed, return to the owning P1–P4 task.

- [ ] **Step 2: Write a failing final-mode test**

Add to `scripts/tests/check-design-system-migration.test.js` a fixture with no legacy files/signals and assert final mode returns zero findings. Then add a `variables.scss` import and assert final mode throws with the import path.

- [ ] **Step 3: Remove the final compatibility layer**

Remove legacy imports from `CRM-Client/src/main.ts`; delete the three V1 style files. Remove `element-plus` and `@element-plus/icons-vue` from `CRM-Client/package.json` with `npm uninstall element-plus @element-plus/icons-vue`, which updates the lockfile. Do not hand-edit the lockfile.

- [ ] **Step 4: Switch the migration checker to final mode**

Replace baseline comparison in the default production CLI with a full tracked-file scan that fails on any finding. Keep `--diff` as a diagnostic mode only. Remove all findings from `CRM-Client/.design-system-migration-baseline.json`, retaining only:

```json
{ "version": 1, "findings": [] }
```

Regenerate `v1-usage-inventory.md`; it must say `总计：0` and contain no finding section.

- [ ] **Step 5: Update migration documents for completed cleanup**

`compatibility.md` must remove active alias guidance; `implementation-status.md` records P5 complete with the date and verification command; `migration-playbook.md` marks P0–P5 complete and names the final check. Keep all Markdown ≤100 lines.

- [ ] **Step 6: Run complete frontend and documentation verification**

Run:

```bash
cd CRM-Client
npm run lint
npm run type-check
npm run test:unit
cd ..
node scripts/tests/design-system-migration-lib.test.js
node scripts/tests/check-design-system-migration.test.js
node scripts/generate-design-system-inventory.js
node scripts/check-design-system-migration.js --final-mode
node scripts/check-design-system-docs.js
git grep -nE 'variables\.scss|wolf-design\.scss|element-plus-theme\.scss|from ["'"']element-plus|from ["'"']@element-plus/icons-vue|MASTER\.md|ELEMENT-PLUS-MIGRATION\.md|design-system/pages/' -- ':!docs/superpowers/**' ':!scripts/tests/**' || true
git diff --check
```

Expected: all commands pass; final grep returns no production/design-doc matches; inventory total is zero.

- [ ] **Step 7: Commit final cleanup**

```bash
git add CRM-Client/src CRM-Client/package.json CRM-Client/package-lock.json CRM-Client/.design-system-migration-baseline.json CRM-Docs/design-system scripts/check-design-system-migration.js scripts/tests/check-design-system-migration.test.js
git commit -m "refactor: remove V1 design system compatibility"
```

## Final Acceptance Checklist

- [ ] `CRM-Docs/design-system/README.md` is the only design-rule entry point.
- [ ] All seven non-authoritative visual prototypes are deleted, not archived.
- [ ] Inventory generation is deterministic and its checked-in Markdown/baseline agree.
- [ ] CI and pre-commit block newly introduced V1, old framework and deleted-path debt.
- [ ] No active source/config/client-doc reference remains to `MASTER.md` or old page documents.
- [ ] P1–P4 each exit only after their inventory group reaches zero and focused tests pass.
- [ ] P5 removes V1 style/theme files, old framework packages and compatibility aliases.
- [ ] Final-mode scan, frontend lint/type/unit tests, design-doc tests and design-doc checker all pass.
