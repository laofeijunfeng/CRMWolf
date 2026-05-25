# 规范变更日志 - CRMWolf

**用途**：记录所有规范修改、新增、迭代，需人工审批

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

**版本：1.0 | 最后更新：2026-04-21**