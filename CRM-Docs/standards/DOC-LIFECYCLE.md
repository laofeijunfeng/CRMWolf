# 文档生命周期规范

**适用范围**：CRM-Docs 所有文档的生命周期管理

---

## 一、生命周期阶段定义

### 1.1 需求文档 (requirements/)

| 状态 | 标签 | 定义 | 触发条件 |
|------|------|------|----------|
| 草稿 | `draft` | 初稿编写，待评审 | 文档创建 |
| 评审中 | `review` | 团队评审阶段 | 草稿完成 |
| 进行中 | `active` | 开发实施阶段 | 评审通过 |
| 已完成 | `completed` | 功能已上线 | 代码合并 + 测试通过 |
| 已归档 | `archived` | 迁移至归档目录 | 自动归档（CI） |

### 1.2 计划文档 (plans/)

| 状态 | 标签 | 定义 | 触发条件 |
|------|------|------|----------|
| 草稿 | `draft` | 技术方案初稿 | 文档创建 |
| 评审中 | `review` | 技术评审阶段 | 草稿完成 |
| 进行中 | `active` | 实施执行阶段 | 评审通过 |
| 已完成 | `completed` | 实施完成 | 代码合并 + 验证通过 |
| 已归档 | `archived` | 迁移至归档目录 | 自动归档（CI） |

### 1.3 系统文档 (system/)

| 状态 | 标签 | 定义 | 触发条件 |
|------|------|------|----------|
| 活跃 | `active` | 持续维护的参考文档 | 文档创建/更新 |
| 已废弃 | `deprecated` | 内容过时但保留参考 | 新版本替代 |
| 已删除 | `deleted` | 完全移除 | 无参考价值 |

### 1.4 规范文档 (standards/)

| 状态 | 标签 | 定义 | 触发条件 |
|------|------|------|----------|
| 活跃 | `active` | 当前生效的规范 | 文档创建/审批通过 |
| 已废弃 | `deprecated` | 旧规范，不再执行 | 新规范替代 |
| 已归档 | `archived` | 历史规范参考 | 自动归档 |

---

## 二、目录结构

```
CRM-Docs/
│
├── requirements/              ← 活跃需求（未开始/进行中）
│   ├── README.md              ← 导航入口 + 状态汇总表
│   └── *.md                   ← 各需求文档（含状态标签）
│
├── plans/                     ← 活跃计划（进行中）
│   ├── README.md              ← 导航入口 + 状态汇总表
│   └── *.md                   ← 各计划文档（含状态标签）
│
├── archive/                   ← 🆕 自动归档目录
│   ├── requirements/          ← 已实现需求（CI 自动迁移）
│   ├── plans/                 ← 已完成计划（CI 自动迁移）
│   └── standards/             ← 已废弃规范（人工迁移）
│   └── README.md              ← 归档导航（CI 自动更新）
│
├── changelog/                 ← 🆕 结果沉淀目录
│   ├── enhancements/          ← 功能优化（按需求汇总）
│   │   └── YYYY-MM-DD-feature-name.md
│   ├── issues/                ← 缺陷修复（重大缺陷单独）
│   │   └── YYYY-MM-DD-bug-fix.md
│   ├── technical/             ← 技术重构
│   │   └ YYYY-MM-DD-refactor-name.md
│   └── README.md              ← 变更日志导航
│
├── standards/                 ← 开发规范（持续维护）
│   ├── GIT-STANDARD.md        ← Git 提交规范 + 文档同步规则
│   ├── DOC-LIFECYCLE.md       ← 本文档
│   ├── SPEC-CHANGELOG.md      ← 规范变更日志
│   └── ...
│
├── system/                    ← 系统说明（持续维护）
│   ├── modules/               ← 模块功能说明
│   ├── design/                ← 设计规范
│   └── ...
│
└── best-practices/            ← 最佳实践（持续维护）
```

---

## 三、状态管理规则

### 3.1 状态标签格式

每个文档必须在开头声明状态：

```markdown
---
status: active
created: 2026-06-12
updated: 2026-06-12
related_plan: AI-OPENAPI-IMPLEMENTATION-PLAN.md  ← 关联计划文档
related_pr: #123                                 ← 关联 PR
---
```

### 3.2 状态流转规则

#### 需求文档流转

```
draft → review → active → completed → archived
  ↓       ↓        ↓         ↓          ↓
 创建    评审    开发中    上线       自动归档
```

| 流转 | 触发条件 | 操作 |
|------|----------|------|
| `draft → review` | 草稿完成，提交评审 | 更新 `status` 标签 |
| `review → active` | 评审通过，开始开发 | 更新 `status` + 创建关联 Plan |
| `active → completed` | 功能上线，PR 合并 | 更新 `status` + 记录 PR 号 |
| `completed → archived` | CI 检测 `completed` 状态 | 自动迁移至 `archive/` |

#### 计划文档流转

```
draft → review → active → completed → archived
  ↓       ↓        ↓         ↓          ↓
 创建    评审    实施中    完成       自动归档
```

| 流转 | 触发条件 | 操作 |
|------|----------|------|
| `draft → review` | 方案完成，提交评审 | 更新 `status` 标签 |
| `review → active` | 评审通过，开始实施 | 更新 `status` + 创建任务 |
| `active → completed` | 实施完成，验证通过 | 更新 `status` + 记录结果 |
| `completed → archived` | CI 检测 `completed` 状态 | 自动迁移至 `archive/` |

---

## 四、自动归档机制

### 4.1 归档触发条件

| 文档类型 | 归档触发 | 检测时机 |
|----------|----------|----------|
| requirements/ | `status: completed` + PR 合并 | 每次 CI 运行 |
| plans/ | `status: completed` + 验证通过 | 每次 CI 运行 |

### 4.2 归档流程（CI 自动执行）

```bash
# scripts/archive_docs.sh（示例）

#!/bin/bash

# 1. 检测 requirements/ 中 status: completed 的文档
for doc in CRM-Docs/requirements/*.md; do
  status=$(grep "status:" "$doc" | head -1 | cut -d' ' -f2)
  if [ "$status" == "completed" ]; then
    # 2. 迁移至 archive/requirements/
    mv "$doc" CRM-Docs/archive/requirements/
    echo "Archived: $doc"
  fi
done

# 3. 检测 plans/ 中 status: completed 的文档
for doc in CRM-Docs/plans/*.md; do
  status=$(grep "status:" "$doc" | head -1 | cut -d' ' -f2)
  if [ "$status" == "completed" ]; then
    mv "$doc" CRM-Docs/archive/plans/
    echo "Archived: $doc"
  fi
done

# 4. 更新归档导航 README
update_archive_readme()
```

### 4.3 归档后处理

| 操作 | 执行者 | 要求 |
|------|--------|------|
| 更新 `archive/README.md` | CI | 添加归档记录 |
| 更新 `requirements/README.md` | CI | 移除活跃记录 |
| 更新 `plans/README.md` | CI | 移除活跃记录 |
| 创建 `changelog/` 结果文档 | 开发者 | 记录实施结果 |

---

## 五、结果沉淀机制

### 5.1 Changelog 目录结构

```
changelog/
├── enhancements/              ← 功能优化（按需求汇总）
│   └── 2026-06-12-ai-openapi.md
│
├── issues/                    ← 缺陷修复（重大缺陷单独）
│   └── 2026-06-12-sse-parser-fix.md
│
├── technical/                 ← 技术重构
│   └── 2026-06-12-team-isolation.md
│
└── README.md                  ← 变更日志导航
```

### 5.2 Changelog 文档模板

```markdown
# [功能名称] 实施总结

**实施日期**：YYYY-MM-DD
**关联需求**：[需求文档链接]
**关联计划**：[计划文档链接]
**关联 PR**：#XXX

---

## 一、实施结果

### 功能完成情况

| 功能项 | 完成状态 | 备注 |
|--------|----------|------|
| 功能 1 | ✅ 完成 | 正常上线 |
| 功能 2 | ⚠️ 部分完成 | 待后续迭代 |
| 功能 3 | ❌ 未完成 | 需重新规划 |

---

## 二、技术实现要点

### 核心改动

| 文件 | 改动说明 | 影响范围 |
|------|----------|----------|
| file.py | 新增功能 | API 层 |
| component.vue | UI 更新 | 前端页面 |

### 技术难点

1. [难点描述]
   - 解决方案：[方案说明]
   - 经验总结：[教训]

---

## 三、遗留问题

| 问题 | 影响 | 处理建议 |
|------|------|----------|
| 问题 1 | 低 | 后续迭代优化 |
| 问题 2 | 中 | 需专项处理 |

---

## 四、经验沉淀

### 最佳实践

- [实践总结 1]
- [实践总结 2]

### 教训

- [教训 1]
- [教训 2]

---

**归档位置**：`CRM-Docs/archive/plans/[计划文档名]`
```

### 5.3 创建时机

| 场景 | 创建要求 | 创建者 |
|------|----------|--------|
| 功能上线 | 必须创建 changelog | 开发者 |
| 缺陷修复 | 重大缺陷必须创建 | 开发者 |
| 技术重构 | 复杂重构必须创建 | 开发者 |

---

## 六、导航文档维护规则

### 6.1 requirements/README.md 模板

```markdown
# 需求文档导航

**活跃需求**：开发中或待开发的需求文档

---

## 状态汇总表

| 文档 | 状态 | 创建日期 | 更新日期 | 关联计划 |
|------|------|----------|----------|----------|
| [需求 A](AI-OPENAPI-REQUIREMENTS.md) | active | 2026-06-01 | 2026-06-12 | [计划 A](../plans/AI-OPENAPI-IMPLEMENTATION-PLAN.md) |
| [需求 B](AI-TOOL-ENHANCEMENT.md) | review | 2026-06-10 | 2026-06-10 | - |

---

## 已归档需求

> 自动迁移至 `../archive/requirements/`，详见 [归档导航](../archive/README.md)

---

## 文档创建规则

1. 新需求文档必须包含 `status: draft` 标签
2. 评审通过后更新 `status: active`
3. 完成后更新 `status: completed`，CI 自动归档

---

**最后更新**：2026-06-12 | 由 CI 自动维护
```

### 6.2 plans/README.md 模板

```markdown
# 计划文档导航

**活跃计划**：正在实施或待实施的技术计划

---

## 状态汇总表

| 文档 | 状态 | 创建日期 | 更新日期 | 关联需求 |
|------|------|----------|----------|----------|
| [计划 A](AI-OPENAPI-IMPLEMENTATION-PLAN.md) | active | 2026-06-05 | 2026-06-12 | [需求 A](../requirements/AI-OPENAPI-REQUIREMENTS.md) |
| [计划 B](AI-TOOL-ENHANCEMENT-PLAN.md) | draft | 2026-06-10 | 2026-06-10 | [需求 B](../requirements/AI-TOOL-ENHANCEMENT.md) |

---

## 已归档计划

> 自动迁移至 `../archive/plans/`，详见 [归档导航](../archive/README.md)

---

## 文档创建规则

1. 新计划文档必须包含 `status: draft` 标签
2. 评审通过后更新 `status: active`
3. 完成后更新 `status: completed`，CI 自动归档

---

**最后更新**：2026-06-12 | 由 CI 自动维护
```

### 6.3 archive/README.md 模板

```markdown
# 归档文档导航

**归档文档**：已完成的需求和计划，保留历史参考

---

## 归档记录

| 文档 | 原位置 | 归档日期 | 关联 PR | 结果文档 |
|------|--------|----------|---------|----------|
| [需求 A](requirements/AI-GLUE-REQUIREMENTS.md) | requirements/ | 2026-06-12 | #123 | [changelog](../changelog/enhancements/2026-06-12-ai-glue.md) |
| [计划 A](plans/AI-GLUE-IMPLEMENTATION-PLAN.md) | plans/ | 2026-06-12 | #123 | [changelog](../changelog/enhancements/2026-06-12-ai-glue.md) |

---

## 归档规则

| 规则 | 说明 |
|------|------|
| 自动归档 | CI 检测 `status: completed` 自动迁移 |
| 保留历史 | 归档文档只读，不修改 |
| 结果沉淀 | 归档前需创建 changelog 文档 |

---

**最后更新**：2026-06-12 | 由 CI 自动维护
```

---

## 七、文档与代码同步规则

### 7.1 同步触发点

| 代码变更类型 | 必须同步的文档 | 同步时机 |
|--------------|----------------|----------|
| 功能完成 | 创建 changelog 文档 | PR 合并时 |
| API 变更 | system/BUSINESS-CHAIN-API.md | 同 PR |
| 类型变更 | CRM-Client/docs/TYPESCRIPT.md | 同 PR |
| 权限变更 | system/GLOSSARY.md | 同 PR |
| 架构变更 | system/ARCHITECTURE.md | 同 PR |
| 模块变更 | system/modules/*.md | 同 PR |

### 7.2 同步检查清单

每个 PR 必须包含：

```markdown
## 文档同步检查

- [ ] 需求文档状态：已更新为 `completed`（如适用）
- [ ] 计划文档状态：已更新为 `completed`（如适用）
- [ ] Changelog 文档：已创建（功能上线）
- [ ] API 文档：已同步（如适用）
- [ ] 类型文档：已同步（如适用）
- [ ] 权限文档：已同步（如适用）
```

### 7.3 CI 校验规则

| 校验项 | 校验逻辑 | 失败处理 |
|--------|----------|----------|
| 状态标签 | 检查文档是否包含 `status` 标签 | 阻止合并 |
| 状态一致性 | `active` 文档必须有对应 PR | 阻止合并 |
| Changelog 存在 | `completed` 文档必须有 changelog | 阻止合并 |

---

## 八、Git Commit 规范扩展

### 8.1 文档相关 Commit Type

| Type | 说明 | 示例 |
|------|------|------|
| `docs(requirements)` | 需求文档变更 | `docs(requirements): 新增 AI-TOOL-ENHANCEMENT 需求` |
| `docs(plans)` | 计划文档变更 | `docs(plans): 更新 AI-OPENAPI 计划状态为 active` |
| `docs(archive)` | 归档操作 | `docs(archive): 彘档 AI-GLUE 需求和计划` |
| `docs(changelog)` | 结果沉淀 | `docs(changelog): 创建 AI-GLUE 实施总结` |
| `docs(system)` | 系统文档更新 | `docs(system): 更新 ARCHITECTURE.md` |

### 8.2 文档变更分组策略

| 分组 | 文件类型 | 提交时机 |
|------|----------|----------|
| 需求组 | requirements/*.md | 需求评审通过 |
| 计划组 | plans/*.md | 计划评审通过 |
| 完成组 | requirements/*.md + plans/*.md + changelog/*.md | 功能上线 |
| 归档组 | archive/*.md + README.md 更新 | CI 自动归档 |
| 同步组 | system/*.md + CRM-Client/docs/*.md | 代码变更同步 |

---

## 九、最佳实践

### 9.1 需求 → 计划 → 实施 → 沉淀 流程

```
1. 创建需求文档 (requirements/XXX-REQUIREMENTS.md)
   → status: draft

2. 需求评审通过
   → status: active
   → 创建计划文档 (plans/XXX-PLAN.md)

3. 计划评审通过
   → status: active
   → 开始实施

4. 功能上线
   → requirements: status: completed
   → plans: status: completed
   → 创建 changelog (changelog/enhancements/YYYY-MM-DD-xxx.md)

5. CI 自动归档
   → 迁移至 archive/
   → 更新导航 README
```

### 9.2 文档命名规范

| 类型 | 命名格式 | 示例 | 说明 |
|------|----------|------|------|
| 需求文档 | `[模块]-REQUIREMENTS.md` | `AI-OPENAPI-REQUIREMENTS.md` | 长期维护，无需时间标记 |
| 计划文档 | `YYYY-MM-DD-HHMM-[模块]-PLAN.md` | `2026-06-12-1801-workflow-fix-PLAN.md` | 时间敏感，精确到分钟 |
| Changelog | `YYYY-MM-DD-HHMM-[主题].md` | `2026-06-12-1744-workflow-fix.md` | 时间敏感，精确到分钟 |

**时间戳方案优势**：
- ✅ 自动避免冲突（时间不会重复）
- ✅ 按时间自动排序
- ✅ 一眼看出创建时间（17:44 = 下午 5:44）
- ✅ 零维护成本（无需手动维护序列号）

**冲突处理**：
如果极罕见地同一分钟创建两个相似主题文档，手动添加 `-2`：
```
2026-06-12-1744-workflow-fix.md     ← 第一个
2026-06-12-1744-workflow-fix-2.md   ← 同一分钟第二个
```

**业界依据**：
- 日志系统命名规范：`YYYY-MM-DD-HHMM.log`
- ISO 8601 标准：时间戳精确到秒
- Git commit 时间戳：`%Y-%m-%d-%H%M`

### 9.3 关联文档追踪

每个文档必须包含关联信息：

```markdown
---
status: active
created: 2026-06-12
updated: 2026-06-12
related_requirements: ../requirements/AI-OPENAPI-REQUIREMENTS.md  ← 计划文档必须关联
related_plan: ../plans/AI-OPENAPI-IMPLEMENTATION-PLAN.md          ← 需求文档可选关联
related_pr: #123                                                  ← 完成时填写
---
```

---

## 十、禁止行为

| 禁止 | 原因 | 检测方式 |
|------|------|----------|
| 手动归档文档 | 违反自动归档机制 | CI 校验 |
| 影子文档（未声明状态） | 违反状态管理规则 | `check-doc-status.sh` |
| 归档文档修改内容 | 违反归档只读原则 | CI 校验 |
| 未创建 changelog 即归档 | 违反结果沉淀规则 | CI 校验 |
| 未同步文档直接合并 | 违反同步检查规则 | PR 校验 |
| **根目录散落 md 文档** | **违反目录结构规范** | **`check-doc-location.sh`** |
| **创建 PHASE-X-SUMMARY 等临时文档** | **应使用 changelog/ 目录** | **pre-commit hook** |

### 10.1 CRM-Docs 根目录规范

**根目录唯一允许的 md 文件**：`README.md`（导航入口）

**所有其他文档必须放入子目录**：
```
CRM-Docs/
├── README.md              ← ✅ 唯一允许的根目录 md 文件
├── requirements/*.md      ← 需求文档
├── plans/*.md             ← 计划文档
├── changelog/**/*.md      ← 实施总结（包括 Phase 总结）
├── archive/**/*.md        ← 归档文档
├── standards/*.md         ← 规范文档
├── system/**/*.md         ← 系统说明
└── best-practices/**/*.md ← 最佳实践
```

### 10.2 进度跟踪文档替代方案

| 场景 | ❌ 禁止行为 | ✅ 正确做法 |
|------|------------|------------|
| 多阶段任务进度 | 创建 PHASE-X-SUMMARY.md | 使用 TaskCreate/TaskUpdate 工具 |
| 任务完成总结 | 创建 FINAL-SUMMARY.md | 创建 `changelog/technical/YYYY-MM-DD-xxx.md` |
| 实施进度跟踪 | 创建 IMPLEMENTATION-PROGRESS.md | 使用内存系统或 Task 工具 |
| 下一步指引 | 创建 NEXT-STEPS-GUIDE.md | 创建 `plans/xxx-NEXT-STEPS.md` |

---

## 十一、工具支持

### 11.1 CI Pipeline 扩展

```yaml
# .github/workflows/ci.yml 新增步骤

jobs:
  docs-lifecycle:
    runs-on: ubuntu-latest
    steps:
      - name: Check document status
        run: scripts/check-doc-status.sh

      - name: Archive completed docs
        run: scripts/archive_docs.sh

      - name: Update navigation README
        run: scripts/update-doc-nav.sh
```

### 11.2 校验脚本清单

| 脚本 | 用途 | 执行时机 |
|------|------|----------|
| `scripts/check-doc-status.sh` | 检查状态标签完整性 | 每次 PR |
| `scripts/check-doc-sync.sh` | 检查文档与代码同步 | 每次 PR |
| `scripts/check-doc-location.sh` | **检查根目录散落文档** | **pre-commit + CI** |
| `scripts/archive_docs.sh` | 自动归档已完成文档 | 每次 CI |
| `scripts/update-doc-nav.sh` | 更新导航 README | 归档后 |

### 11.3 根目录散落文档检测脚本

```bash
#!/bin/bash
# scripts/check-doc-location.sh - 检测 CRM-Docs 根目录散落文档

set -e

echo "检查 CRM-Docs 根目录散落文档..."

# CRM-Docs 根目录允许的 md 文件（白名单）
ALLOWED_ROOT_MD="README.md"

# 检查根目录是否有散落的 md 文件
STRAY_FILES=$(find CRM-Docs -maxdepth 1 -name "*.md" ! -name "$ALLOWED_ROOT_MD")

if [ -n "$STRAY_FILES" ]; then
    echo "❌ 发现根目录散落文档："
    echo "$STRAY_FILES"
    echo ""
    echo "根目录唯一允许的 md 文件：README.md"
    echo "请将文档移动到正确的子目录："
    echo "  - 进度总结 → changelog/technical/"
    echo "  - 实施计划 → plans/ 或 archive/plans/"
    echo "  - 需求文档 → requirements/"
    exit 1
fi

echo "✅ 根目录文档结构符合规范"
exit 0
```

---

## 十二、实施路线

### Phase 0：目录结构创建

```bash
mkdir -p CRM-Docs/archive/{requirements,plans,standards}
mkdir -p CRM-Docs/changelog/{enhancements,issues,technical}
touch CRM-Docs/archive/README.md
touch CRM-Docs/changelog/README.md
touch CRM-Docs/requirements/README.md
touch CRM-Docs/plans/README.md
```

### Phase 1：状态标签补全

为现有文档添加状态标签：

| 文档 | 当前状态 | 标签 |
|------|----------|------|
| AI-OPENAPI-REQUIREMENTS.md | active | `status: active` |
| AI-GLUE-REQUIREMENTS.md | completed | `status: completed`（待归档） |

### Phase 2：CI 脚本开发

开发自动化脚本：

1. `scripts/check-doc-status.sh` - 状态检查
2. `scripts/archive_docs.sh` - 自动归档
3. `scripts/update-doc-nav.sh` - 导航更新

### Phase 3：CI Pipeline 集成

将脚本集成到 CI Pipeline：

- PR 校验：检查文档同步
- 自动归档：检测 `completed` 状态

### Phase 4：存量文档归档

手动触发首次归档：

```bash
# 影子文档迁移
mv CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md CRM-Docs/archive/requirements/
mv CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md CRM-Docs/archive/plans/

# 更新导航
scripts/update-doc-nav.sh
```

---

**版本：1.1 | 创建日期：2026-06-12 | 最后更新：2026-06-12**