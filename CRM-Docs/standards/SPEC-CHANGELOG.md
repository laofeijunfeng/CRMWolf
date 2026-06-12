# 规范变更日志 - CRMWolf

**用途**：记录所有规范修改、新增、迭代，需人工审批

---

## Version 1.2 (2026-06-12)

### 新增文档
- 创建 `DOC-LIFECYCLE.md` 定义文档生命周期管理规范
  - 状态管理规则（draft → review → active → completed → archived）
  - 自动归档机制（CI 检测 + 迁移 + 导航更新）
  - 结果沉淀机制（changelog 目录结构 + 模板）
  - 文档与代码同步规则（扩展 GIT-STANDARD.md）
  - CI 自动化脚本清单

### 目录结构新增
- 创建 `archive/` 目录
  - `archive/requirements/` - 已实现需求（CI 自动归档）
  - `archive/plans/` - 已完成计划（CI 自动归档）
  - `archive/standards/` - 已废弃规范（人工迁移）
  - `archive/README.md` - 归档导航
- 创建 `changelog/` 目录
  - `changelog/enhancements/` - 功能优化实施总结
  - `changelog/issues/` - 重大缺陷修复总结
  - `changelog/technical/` - 技术重构总结
  - `changelog/README.md` - 变更日志导航
- 创建 `scripts/` 目录
  - `scripts/check-doc-status.sh` - 状态标签检查
  - `scripts/archive_docs.sh` - 自动归档
  - `scripts/update-doc-nav.sh` - 导航更新

### 导航文档新增
- 创建 `requirements/README.md` - 需求文档导航 + 状态汇总表
- 创建 `plans/README.md` - 计划文档导航 + 状态汇总表

### 文档更新
- 更新 `README.md` 添加归档和 changelog 目录导航
- 更新 `GIT-STANDARD.md` 新增文档同步规则章节
  - 文档状态同步规则
  - Commit Type 扩展（文档相关）
  - 同步检查清单
  - 文档变更分组策略

### 变更原因
- 建立自动化文档生命周期管理体系
- 解决需求/计划文档状态追踪混乱问题
- 提供结果沉淀机制，避免历史经验流失
- 与开发规范联动，确保文档与代码同步

### 影响分析
- **Affected docs**: README.md, GIT-STANDARD.md
- **New docs**: DOC-LIFECYCLE.md, archive/README.md, changelog/README.md, requirements/README.md, plans/README.md, scripts/README.md
- **New dirs**: archive/, changelog/, scripts/
- **Migration needed**: Yes（需为现有文档补全状态标签）
- **Breaking change**: No（现有文档不受影响）

---

## Version 1.1 (2026-06-12)

### 文档更新
- 更新 `SYSTEM-DESCRIPTION.md` 版本 1.1 → 1.2
  - 新增 2.3 AI Agent 模块详解章节（核心能力、架构层级、Workflow 流程、置信度护栏、配置开关）
  - 更新核心价值表格（添加 AI 智能助手、撤销保护、置信度护栏）
  - 更新技术栈表格（Redis 用途细化、AI 服务）
  - 更新功能模块架构图（添加 AI Agent 层）
  - 更新后端目录结构（补充 services/workflow/ 目录）
- 更新 `ARCHITECTURE.md` 版本 1.0 → 1.1
  - 更新后端目录结构（补充 AI 相关路由和 services/workflow/ 目录）
  - 更新后端分层表格（补充 ai_tool_service、handlers、workflow 层职责）
  - 更新后端通信规则（补充 AI 通信规则）

### 变更原因
- AI Agent 功能已完成全部实施（ReAct 循环 + Workflow 编排 + Control Plane）
- 系统文档需同步反映新增的核心功能模块
- 符合 DOCS-STANDARD.md "修改目录结构需更新 ARCHITECTURE.md" 规则

### 影响分析
- **Affected docs**: SYSTEM-DESCRIPTION.md, ARCHITECTURE.md
- **Migration needed**: No
- **Breaking change**: No

---

## Version 1.0 (2026-04-21)

### 新增
- 创建 `AGENTS.md` 作为 AI + 团队唯一行为准则入口
- 创建 `TYPESCRIPT.md` 定义 Approved Types 清单和四禁令
- 创建 `ARCHITECTURE.md` 定义前后端目录结构和模块边界
- 创建 `COMPONENTS.md` 定义 Vue 组件开发模板和 Props 规范
- 创建 `STATE-MANAGEMENT.md` 定义 Pinia Store 模板
- 创建 `TESTING.md` 定义 Vitest/pytest 测试规范
- 创建 `DOCS-STANDARD.md` 定义文档同步规则
- 创建 `GLOSSARY.md` 定义权限码、状态枚举、术语
- 创建 `COMPLIANCE-STANDARD.md` 定义合规报告模板

### 配置新增
- 创建 `eslint-custom-rules/` 实现四禁令校验
- 创建 `eslint.config.js` ESLint 配置
- 创建 `pyproject.toml` 后端 lint 配置
- 创建 `.husky/` Git hooks
- 创建 `.github/workflows/ci.yml` CI Pipeline
- 创建 `.compliance-baseline.json` 存量违规跟踪

---

## 变更申请模板

### Proposed Change
- **Document**: [文件名]
- **Section**: [章节]
- **Current**: [当前内容]
- **Proposed**: [建议内容]
- **Reason**: [变更原因]

### Impact Analysis
- **Affected code**: [受影响的代码文件]
- **Migration needed**: [ ] Yes [ ] No
- **Breaking change**: [ ] Yes [ ] No
- **Affected docs**: [需要同步更新的其他文档]

### Approval
- **Proposed by**: [申请人]
- **Approved by**: [审批人] (必须是 human)
- **Approval date**: [审批日期]
- **Implementation date**: [实施日期]

---

## 变更规则

| 规则 | 要求 |
|------|------|
| 变更审批 | 必须人工审批，AI 禁止自行修改规范 |
| 变更记录 | 所有变更必须记录到本文件 |
| 影响分析 | 必须分析对代码和其他文档的影响 |
| 同步更新 | 变更后必须同步更新相关文档 |

---

## 配置修改审批模板

### Proposed Config Change
- **Config file**: [tsconfig.json / eslint.config.js / pyproject.toml]
- **Current setting**: [当前配置]
- **Proposed setting**: [建议配置]
- **Reason**: [变更原因]

### Risk Assessment
- **Impact level**: [ ] Low [ ] Medium [ ] High
- **Affected features**: [受影响的功能]
- **Testing required**: [ ] Yes [ ] No

### Approval
- **Proposed by**: [申请人]
- **Approved by**: [审批人]
- **Approval date**: [日期]
- **Git hook override**: [ ] Required [ ] Not required

---

## 禁止行为

| 禁止 | 原因 |
|------|------|
| AI 自行修改规范 | 违反人类专属红线 |
| 未审批直接修改配置 | 违反配置锁定红线 |
| 未记录变更 | 违反变更记录规则 |

---

**版本：1.2 | 最后更新：2026-06-12**