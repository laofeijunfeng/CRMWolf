# 文档规范 - CRMWolf

**适用范围**：CRMWolf 全项目文档

---

## 一、文档与代码同步规则

### 1.1 代码变更映射表

| 代码变更类型 | 必须更新的文档 | 同步时机 |
|--------------|----------------|----------|
| 新增 API 端点 | system/BUSINESS-CHAIN-API.md + TYPESCRIPT.md | 同 PR |
| 修改 API 参数 | system/BUSINESS-CHAIN-API.md | 同 PR |
| 新增数据类型 | TYPESCRIPT.md + Zod Schema | 同 PR |
| 新增 Vue 组件 | COMPONENTS.md + Stories | 同 PR |
| 新增 Pinia Store | STATE-MANAGEMENT.md | 同 PR |
| 修改权限码 | system/GLOSSARY.md | 同 PR |
| 新增状态枚举 | system/GLOSSARY.md | 同 PR |
| 修改目录结构 | system/ARCHITECTURE.md | 同 PR |
| 新增测试模板 | TESTING.md | 同 PR |

### 1.2 同步检查清单

每次代码变更提交前必须完成：

```markdown
## 文档同步检查

- [ ] API 变更：已更新 system/BUSINESS-CHAIN-API.md
- [ ] 类型变更：已更新 TYPESCRIPT.md + Zod Schema
- [ ] 权限变更：已更新 system/GLOSSARY.md
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
│   ├── README.md                # 文档目录导航
│   │
│   ├── system/                  # 系统说明文档
│   │   ├── SYSTEM-DESCRIPTION.md # 系统综合说明
│   │   ├── ARCHITECTURE.md       # 架构规范
│   │   ├── GLOSSARY.md           # 术语定义
│   │   ├── BUSINESS-CHAIN-API.md # 业务链路接口
│   │   ├── UI-DESIGN-SPEC.md     # UI 设计规范
│   │   └── LOGGING-STANDARD.md   # 日志规范
│   │
│   ├── standards/               # 开发规范
│   │   ├── GIT-STANDARD.md       # Git 提交规范
│   │   ├── COMPLIANCE-STANDARD.md # 合规规范
│   │   ├── DOCS-STANDARD.md      # 本文档
│   │   ├── SPEC-CHANGELOG.md     # 规范变更日志
│   │   ├── AI-KNOWLEDGE.md       # AI 知识沉淀
│   │   └── QUICK-START.md        # 快速上手指南
│   │
│   └── requirements/            # 需求文档
│       ├── AI-OPENAPI-REQUIREMENTS.md
│       └── OPEN-API-REQUIREMENTS.md
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