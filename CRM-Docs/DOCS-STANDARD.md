# 文档规范 - CRMWolf

**适用范围**：CRMWolf 全项目文档

---

## 一、文档与代码同步规则

### 1.1 代码变更映射表

| 代码变更类型 | 必须更新的文档 | 同步时机 |
|--------------|----------------|----------|
| 新增 API 端点 | CRM-Docs/05-API接口.md + TYPESCRIPT.md | 同 PR |
| 修改 API 参数 | CRM-Docs/05-API接口.md | 同 PR |
| 新增数据类型 | TYPESCRIPT.md + Zod Schema | 同 PR |
| 新增 Vue 组件 | COMPONENTS.md + Stories | 同 PR |
| 新增 Pinia Store | STATE-MANAGEMENT.md | 同 PR |
| 修改权限码 | GLOSSARY.md + CRM-Docs/06-权限体系.md | 同 PR |
| 新增状态枚举 | GLOSSARY.md | 同 PR |
| 修改目录结构 | ARCHITECTURE.md | 同 PR |
| 新增测试模板 | TESTING.md | 同 PR |

### 1.2 同步检查清单

每次代码变更提交前必须完成：

```markdown
## 文档同步检查

- [ ] API 变更：已更新 05-API接口.md
- [ ] 类型变更：已更新 TYPESCRIPT.md + Zod Schema
- [ ] 权限变更：已更新 GLOSSARY.md + 权限体系.md
- [ ] 组件变更：已创建/更新 Stories 文件
- [ ] 变更说明：已填写 PR 描述
```

---

## 二、文档目录结构

```
CRMWolf/
├── AGENTS.md                    # AI 行为准则入口
│
├── CRM-Client/docs/
│   ├── TYPESCRIPT.md            # TypeScript 类型规范
│   ├── COMPONENTS.md            # Vue 组件规范
│   ├── STATE-MANAGEMENT.md      # Pinia Store 规范
│   └── TESTING.md               # 测试规范
│
├── CRM-Docs/
│   ├── 01-系统概述.md            # 系统简介
│   ├── 02-技术架构.md            # 技术栈说明
│   ├── 03-业务模块.md            # 业务模块说明
│   ├── 04-数据库设计.md          # 数据库表结构
│   ├── 05-API接口.md             # API 接口文档
│   ├── 06-权限体系.md            # 权限定义
│   ├── 07-开发指南.md            # 开发环境指南
│   ├── 08-部署运维.md            # 部署说明
│   ├── ARCHITECTURE.md          # 架构规范
│   ├── DOCS-STANDARD.md         # 本文档
│   ├── GLOSSARY.md              # 术语定义
│   ├── COMPLIANCE-STANDARD.md   # 合规规范
│   ├── SPEC-CHANGELOG.md        # 规范变更日志
│   └── AI-KNOWLEDGE.md          # AI 知识沉淀
│
├── CRM-Server/docs/
│   ├── README.md                # 后端说明
│   ├── technical/               # 技术文档
│   ├── business/                # 业务文档
│   └── prd/                     # PRD 文档
```

---

## 三、文档格式规范

### 3.1 Markdown 结构

```markdown
# 文档标题

**适用范围**：[明确的适用范围]

---

## 一、一级章节

### 1.1 二级章节

| 列表项 | 说明 |
|--------|------|

```代码块```

**重点内容加粗**
```

### 3.2 表格规范

- 表头必须有明确的字段名
- 表格行必须完整，无空单元格
- 对齐使用 Markdown 标准

### 3.3 代码块规范

```markdown
// 语言标记必须指定
```typescript
const x: number = 1
```

```python
def test_func():
    pass
```
```

---

## 四、变更日志规范

### 4.1 SPEC-CHANGELOG.md 模板

```markdown
# 规范变更日志

## Version 1.0 (2026-04-21)

### 新增
- 创建 AGENTS.md 作为 AI 行为准则入口
- 创建 TYPESCRIPT.md 定义 Approved Types 清单
- 创建完整的 Harness 规范体系

---

## 变更申请模板

### Proposed Change
- Document: [文件名]
- Section: [章节]
- Current: [当前内容]
- Proposed: [建议内容]
- Reason: [原因]

### Impact Analysis
- Affected code: [受影响的代码]
- Migration needed: [ ] Yes [ ] No
- Breaking change: [ ] Yes [ ] No

### Approval
- Proposed by: [申请人]
- Approved by: [审批人] (human)
- Approval date: [日期]
```

---

## 五、文档版本控制

| 规则 | 要求 |
|------|------|
| 版本声明 | 每个规范文档末尾标注版本和日期 |
| 修改审批 | 规范文档修改需人工审批 |
| 变更记录 | 所有变更记录到 SPEC-CHANGELOG.md |

---

## 六、校验规则

| 校验点 | 工具 | 时机 |
|--------|------|------|
| API 文档同步 | scripts/check-doc-sync.js | CI |
| 类型文档同步 | scripts/check-doc-sync.js | CI |
| 权限文档同步 | scripts/check-doc-sync.js | CI |

---

**版本：1.0 | 最后更新：2026-04-21 | 修改需人工审批**