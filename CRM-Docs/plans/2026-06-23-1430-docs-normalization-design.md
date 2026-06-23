# CRM-Docs 文档规范化设计

**创建日期**: 2026-06-23
**设计目标**: 全面规范化 CRM-Docs/plans 目录，建立完整的文档生命周期管理
**依据规范**: [DOC-LIFECYCLE.md](../standards/DOC-LIFECYCLE.md)

---

## 一、现状分析

### 1.1 当前问题

**CRM-Docs/plans/ 目录 14 个文档的分类问题**：

| 类别 | 数量 | 当前状态 | 规范要求 |
|-----|-----|---------|---------|
| 已完成计划 | 2 | `status: completed` | 应归档到 `archive/plans/` |
| 进行中计划 | 1 | `status: ready` (非标准) | 保留，补全标准状态标签 |
| 设计文档 | 3 | 无状态标签 | 应迁移到 `system/design/` |
| 阶段总结 | 5 | 无状态标签，违反红线 | 应迁移到 `changelog/technical/` |
| 进度文档 | 1 | 无状态标签，违反红线 | 应删除，使用 Task 工具 |
| 验证报告 | 1 | 无状态标签 | 应迁移到 `changelog/technical/` |
| 导航文档 | 1 | README.md | 更新状态汇总表 |

### 1.2 业界最佳实践参考

| 项目 | 文档生命周期方案 | 核心机制 |
|-----|-----------------|---------|
| React | RFC 流程 | draft → review → approved → implemented |
| Vue.js | ADR + 状态标签 | Architecture Decision Records + 状态管理 |
| TypeScript | RFC + PR review | 正式化提案流程 + 代码审查 |
| GitHub Docs | GitHub Flow | draft → review → approved → published → archived |

**共性特征**：
- 明确的状态流转
- 自动化检查（CI/CD 集成）
- 结构化目录（活跃文档 vs 归档文档）
- 导航维护（README 状态汇总表自动更新）

---

## 二、目录结构架构

### 2.1 目标目录结构

```
CRM-Docs/
│
├── plans/                          ← 活跃计划（仅保留 draft/active）
│   ├── README.md                   ← 状态汇总表 + 导航
│   └── AI-ASSISTANT-PAGE-IMPLEMENTATION-PLAN.md
│
├── system/design/                  ← 🆕 设计文档目录
│   ├── README.md                   ← 设计文档导航
│   ├── AI-ASSISTANT-PAGE-DESIGN.md (status: active)
│   ├── AI-THINKING-PROCESS-DESIGN.md (status: active)
│   └── SYSTEM-WIDE-DESIGN-OPTIMIZATION-GUIDE.md (status: active)
│
├── archive/plans/                  ← 已完成计划（只读归档）
│   ├── README.md                   ← 归档导航（已存在，需更新）
│   ├── AI-ASSISTANT-SIDEBAR-UI-OPTIMIZATION-PLAN.md (status: archived)
│   └── 2026-06-22-2230-agent-safety-mechanism-plan.md (status: archived)
│
├── changelog/technical/            ← 技术总结（历史记录）
│   ├── README.md                   ← 变更日志导航（已存在）
│   ├── 2026-06-17-ai-assistant-sidebar-ui-phase-0.md
│   ├── 2026-06-17-ai-assistant-sidebar-ui-phase-1.md
│   ├── 2026-06-17-ai-assistant-sidebar-ui-phase-2.md
│   ├── 2026-06-17-ai-assistant-sidebar-ui-phase-3.md
│   ├── 2026-06-17-ai-assistant-sidebar-ui-phase-4.md
│   └── 2026-06-17-ai-assistant-sidebar-ui-verification.md
│
└── scripts/                        ← 🆕 CI 检查脚本目录
    ├── check-doc-status.sh         ← 状态标签完整性检查
    ├── check-doc-location.sh       ← 根目录散落文档检测
    └── archive_docs.sh             ← 自动归档脚本（未来 CI）
```

### 2.2 目录职责定义

| 目录 | 文档类型 | 状态范围 | 维护方式 |
|-----|---------|---------|---------|
| `plans/` | 实施计划 | `draft → active → completed` | 开发者手动 + CI 自动归档 |
| `system/design/` | 设计文档 | `active`（长期维护） | 开发者手动更新 |
| `archive/plans/` | 已完成计划 | `archived`（只读） | CI 自动迁移 |
| `changelog/technical/` | 技术总结 | 无状态标签（历史记录） | 开发者手动创建 |
| `scripts/` | 检查脚本 | - | CI 自动执行 |

---

## 三、状态管理机制

### 3.1 状态流转规则

| 文档类型 | 状态流转 | 状态标签 | 归档触发 |
|---------|---------|---------|---------|
| **plans/*.md** | draft → active → completed → archived | `status: draft/active/completed` | CI 检测 `completed` 自动迁移 |
| **system/design/*.md** | active（长期维护） | `status: active` | 无归档（持续更新） |
| **archive/plans/*.md** | archived（只读） | `status: archived` | 无流转（历史记录） |
| **changelog/technical/*.md** | 无状态标签 | 无 | 无流转（历史记录） |

### 3.2 状态标签格式（强制要求）

**所有 plans/ 和 system/design/ 文档必须包含 frontmatter**：

```markdown
---
status: draft
created: YYYY-MM-DD
updated: YYYY-MM-DD
related_requirements: ../requirements/[需求文档].md  ← plans 必须关联
related_pr: -                                          ← 完成时填写
---

# [计划名称]

...
```

### 3.3 README 导航维护规则

**plans/README.md 状态汇总表**：

```markdown
## 状态汇总表

| 文档 | 状态 | 创建日期 | 更新日期 | 关联需求 |
|------|------|----------|----------|----------|
| [AI-ASSISTANT-PAGE-IMPLEMENTATION-PLAN.md](AI-ASSISTANT-PAGE-IMPLEMENTATION-PLAN.md) | active | 2026-06-17 | 2026-06-23 | [需求](../requirements/AI-ASSISTANT-PAGE-REQUIREMENTS.md) |

## 待归档计划

> status: completed，等待 CI 自动归档

_暂无待归档计划_

## 已归档计划

> 自动迁移至 `../archive/plans/`，详见 [归档导航](../archive/README.md)
```

**archive/README.md 归档记录**：

```markdown
## 归档记录

| 文档 | 原位置 | 归档日期 | 关联 PR | 结果文档 |
|------|--------|----------|---------|----------|
| [AI-ASSISTANT-SIDEBAR-UI-OPTIMIZATION-PLAN.md](AI-ASSISTANT-SIDEBAR-UI-OPTIMIZATION-PLAN.md) | plans/ | 2026-06-23 | - | [changelog](../changelog/technical/) |
| [2026-06-22-2230-agent-safety-mechanism-plan.md](2026-06-22-2230-agent-safety-mechanism-plan.md) | plans/ | 2026-06-23 | - | - |
```

---

## 四、文档迁移执行计划

### 4.1 文档分类迁移清单

| 当前位置 | 文档类型 | 目标位置 | 操作 |
|---------|---------|---------|------|
| AI-ASSISTANT-SIDEBAR-UI-OPTIMIZATION-PLAN.md | 已完成计划 | archive/plans/ | 迁移 + 更新状态为 archived |
| 2026-06-22-2230-agent-safety-mechanism-plan.md | 已完成计划 | archive/plans/ | 迁移 + 更新状态为 archived |
| AI-ASSISTANT-PAGE-IMPLEMENTATION-PLAN.md | 进行中计划 | 保留在 plans/ | 补全状态标签为 active |
| AI-ASSISTANT-PAGE-DESIGN.md | 设计文档 | system/design/ | 迁移 + 补全状态标签为 active |
| AI-THINKING-PROCESS-DESIGN.md | 设计文档 | system/design/ | 迁移 + 补全状态标签为 active |
| SYSTEM-WIDE-DESIGN-OPTIMIZATION-GUIDE.md | 设计文档 | system/design/ | 迁移 + 补全状态标签为 active |
| PHASE-0~4-SUMMARY.md | 阶段总结 | changelog/technical/ | 迁移 + 重命名（添加日期） |
| VERIFICATION-REPORT.md | 验证报告 | changelog/technical/ | 迁移 + 重命名（添加日期） |
| SYSTEM-WIDE-DESIGN-OPTIMIZATION-PROGRESS.md | 进度文档 | - | **删除** |

### 4.2 文档重命名规则

**changelog/technical/ 文档命名**：`YYYY-MM-DD-[主题].md`

| 原名称 | 新名称 |
|-------|-------|
| PHASE-0-SUMMARY.md | 2026-06-17-ai-assistant-sidebar-ui-phase-0.md |
| PHASE-1-SUMMARY.md | 2026-06-17-ai-assistant-sidebar-ui-phase-1.md |
| PHASE-2-SUMMARY.md | 2026-06-17-ai-assistant-sidebar-ui-phase-2.md |
| PHASE-3-SUMMARY.md | 2026-06-17-ai-assistant-sidebar-ui-phase-3.md |
| PHASE-4-SUMMARY.md | 2026-06-17-ai-assistant-sidebar-ui-phase-4.md |
| VERIFICATION-REPORT.md | 2026-06-17-ai-assistant-sidebar-ui-verification.md |

---

## 五、CI 检查脚本设计

### 5.1 检查脚本清单

| 脚本 | 职责 | 执行时机 | 失败处理 |
|-----|-----|---------|---------|
| `check-doc-status.sh` | 检查状态标签完整性 | 每次 PR + pre-commit hook | 阻止合并，报错提示 |
| `check-doc-location.sh` | 检查根目录散落文档 | pre-commit hook + CI | 阻止提交，报错提示 |
| `archive_docs.sh` | 自动归档已完成文档 | 每次 CI 运行（未来） | 自动执行，更新导航 |

### 5.2 Pre-commit Hook 配置

```bash
#!/bin/bash

echo "检查文档规范..."

# 1. 检查根目录散落文档
scripts/check-doc-location.sh
if [ $? -ne 0 ]; then
  echo "❌ 文档位置检查失败，阻止提交"
  exit 1
fi

# 2. 检查状态标签完整性
scripts/check-doc-status.sh
if [ $? -ne 0 ]; then
  echo "❌ 文档状态检查失败，阻止提交"
  exit 1
fi

echo "✅ 文档规范检查通过"
exit 0
```

---

## 六、执行顺序与风险控制

### 6.1 执行顺序

```
Step 1: 创建新目录结构
├── mkdir system/design/
└── mkdir scripts/

Step 2: 删除违规文档
├── 删除 SYSTEM-WIDE-DESIGN-OPTIMIZATION-PROGRESS.md

Step 3: 迁移文档（按类型）
├── 迁移已完成计划 → archive/plans/
├── 迁移设计文档 → system/design/
├── 迁移阶段总结 → changelog/technical/ + 重命名
└── 迁移验证报告 → changelog/technical/ + 重命名

Step 4: 补全状态标签
├── plans/ 保留文档 → 补全 frontmatter
├── system/design/ 文档 → 补全 frontmatter
└── archive/plans/ 文档 → 更新为 archived + 添加归档日期

Step 5: 更新 README 导航
├── plans/README.md → 更新状态汇总表
├── archive/README.md → 添加归档记录
├── system/design/README.md → 创建设计文档导航（新建）
└── CRM-Docs/README.md → 更新目录结构说明

Step 6: 创建检查脚本
├── scripts/check-doc-status.sh
├── scripts/check-doc-location.sh
└── scripts/archive_docs.sh
```

### 6.2 执行前验证清单

- [ ] Git 状态干净：`git status` 无未提交更改
- [ ] 目录结构确认：archive/plans/ 和 changelog/technical/ 已存在
- [ ] 文档分类确认：14 个文档的分类正确
- [ ] 执行权限确认：有权限创建目录、迁移文件

### 6.3 执行后验证清单

- [ ] 目录结构正确：
  - plans/ 仅保留 README + 1 个计划
  - system/design/ 有 3 个设计文档
  - archive/plans/ 有 2 个已完成计划
  - changelog/technical/ 有 6 个技术总结

- [ ] 状态标签完整：
  - `scripts/check-doc-status.sh` 全部通过
  - 手动检查每个文档 frontmatter 格式正确

- [ ] README 导航正确：
  - plans/README.md 状态汇总表列出 1 个活跃计划
  - archive/README.md 归档记录列出 2 个已完成计划
  - system/design/README.md 列出 3 个设计文档
  - CRM-Docs/README.md 目录结构更新

- [ ] 根目录干净：
  - `scripts/check-doc-location.sh` 全部通过
  - CRM-Docs/ 根目录仅保留 README.md

---

## 七、预期结果

### 7.1 迁移后文档分布

| 目录 | 文档数量 | 文档类型 |
|-----|---------|---------|
| plans/ | 2 | README + 1 个活跃计划 |
| system/design/ | 4 | README + 3 个设计文档 |
| archive/plans/ | 3 | README + 2 个已完成计划 |
| changelog/technical/ | 7 | README + 6 个技术总结 |
| scripts/ | 3 | 3 个检查脚本 |

### 7.2 规范化收益

- ✅ **符合 DOC-LIFECYCLE 规范**：100% 执行现有规范
- ✅ **建立完整生命周期管理**：draft → active → completed → archived
- ✅ **自动化检查机制**：CI 检查 + pre-commit hook
- ✅ **导航维护自动化**：README 状态汇总表实时更新
- ✅ **文档类型清晰分离**：计划/设计/归档/总结 各司其职
- ✅ **违规文档清零**：无 PHASE-SUMMARY、无进度文档、无根目录散落

---

**设计完成日期**: 2026-06-23
**下一步**: invoke writing-plans skill 创建实施计划