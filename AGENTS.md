# CRMWolf AI 行为准则 - 唯一入口

**读取优先级：最高** - AI Agent 启动后必须首先读取此文件

---

## 红线锁定（人类专属 - AI 禁止修改）

| 红线 | 内容 | 违规处理 |
|------|------|----------|
| 技术栈 | Vue 3.5 + FastAPI 0.115 | 拒绝执行，报告 COMPLIANCE |
| TypeScript | `any` `as` `@ts-ignore` `!` 禁用 | 拒绝执行，报告 COMPLIANCE |
| 配置修改 | tsconfig/eslint.config/pyproject.toml | 需人工审批，禁止自行修改 |
| 新代码要求 | 单测必写，组件必配 Stories | 未完成拒绝提交 |
| 外部数据 | Zod 边界校验强制 | 拒绝绕开校验 |

---

## AI 必守规则

| 场景 | 必查文档 | 违规后果 |
|------|----------|----------|
| 定义类型 | TYPESCRIPT.md | 禁止创建新类型 |
| 放置文件 | ARCHITECTURE.md | 禁止跨模块 |
| 写 Vue 组件 | COMPONENTS.md | 禁止内联类型 |
| 用 Pinia | STATE-MANAGEMENT.md | 禁止 any 状态 |
| 写单测 | TESTING.md | 禁止跳过测试 |
| 改代码 | DOCS-STANDARD.md | 必须同步文档 |
| 查权限码 | GLOSSARY.md | 禁止猜测编码 |
| **写 UI 样式** | **DESIGN-COMPONENTS.md** | **禁止纯色标签** |
| **写列表页** | **DESIGN-TABLE.md** | **禁止竖分割线** |
| **查状态色** | **DESIGN-QUICK-REF.md** | **禁止高饱和色** |
| **写二级页面** | **DESIGN-PAGE-LAYOUT.md** | **必须有 sticky 头部** |

---

## 规范导航

```
CRMWolf/
├── AGENTS.md                    ← 本文件（唯一入口）
├── CRM-Docs/QUICK-START.md      ← 团队快速上手（5分钟）
│
├── CRM-Client/docs/
│   ├── TYPESCRIPT.md            ← 类型定义、禁令替代方案
│   ├── COMPONENTS.md            ← Vue 组件模板、Props 规范
│   ├── STATE-MANAGEMENT.md      ← Pinia Store 模板
│   ├── TESTING.md               ← Vitest/pytest 模板
│   │
│   │  ─── 设计规范（前端 UI 开发必读）───
│   ├── DESIGN-PRINCIPLES.md     ← 设计原则、色彩、字体（基础 Token）
│   ├── DESIGN-SPACING.md        ← 间距、圆角、阴影、布局规范
│   ├── DESIGN-COMPONENTS.md     ← 按钮、标签、卡片、弹窗规范
│   ├── DESIGN-TABLE.md          ← 表格规范（列表页必读）
│   ├── DESIGN-QUICK-REF.md      ← 快速参考、状态码速查
│   ├── DESIGN-PAGE-LAYOUT.md    ← 二级页面布局（表单页、管理页）
│
├── CRM-Docs/
│   ├── ARCHITECTURE.md          ← 前后端目录、模块边界
│   ├── DOCS-STANDARD.md         ← 文档同步规则
│   ├── GLOSSARY.md              ← 术语、权限码、状态枚举
│   ├── COMPLIANCE-STANDARD.md   ← 合规报告模板
│   ├── SPEC-CHANGELOG.md        ← 规范变更日志
│   └── AI-KNOWLEDGE.md          ← AI 知识沉淀
│
└── 示例代码（参考）
    ├── CRM-Client/src/api/example-customer.ts
    ├── CRM-Client/src/stores/example-customer.ts
    ├── CRM-Client/src/components/CustomerCard.example.vue
    ├── CRM-Client/tests/example-components.test.ts
    ├── CRM-Server/app/services/example_customer_service.py
    └── CRM-Server/tests/unit/test_customer_service.py
```

---

## 校验流程（自动执行）

| 阶段 | 校验内容 | 失败处理 |
|------|----------|----------|
| pre-commit | ESLint + type-check + config-lock | 阻止提交 |
| pre-push | 单测 + coverage ≥ 80% | 阻止推送 |
| CI | 全量 lint + test + doc-sync | 阻止合并 |

---

## 合规问题处理

遇到无法合规的情况：
1. **停止执行** - 不尝试绕开红线
2. **填写报告** - 使用 COMPLIANCE-STANDARD.md 模板
3. **等待审批** - 人工决定处理方案

---

## 快速参考

| 任务 | 起点 |
|------|------|
| 新增 API 端点 | ARCHITECTURE.md → api/层 → TYPESCRIPT.md 取类型 |
| 创建 Vue 页面 | COMPONENTS.md → 模板 → GLOSSARY.md 查状态码 |
| 新增 Pinia Store | STATE-MANAGEMENT.md → 模板 → TYPESCRIPT.md 取类型 |
| 写单测 | TESTING.md → 模板 → 先写测试再写代码 |
| 修复类型错误 | TYPESCRIPT.md → 查 Approved Types → 不用 any |
| **写列表页表格** | **DESIGN-TABLE.md → 表头/行规范 → 状态标签用 DESIGN-QUICK-REF.md** |
| **写按钮/标签** | **DESIGN-COMPONENTS.md → 按钮规范 → DESIGN-QUICK-REF.md 查色** |
| **调整间距/圆角** | **DESIGN-SPACING.md → 间距 token → 圆角速查** |
| **写表单/管理页** | **DESIGN-PAGE-LAYOUT.md → 选择布局类型 → 模板复用** |

---

**版本：1.0 | 最后更新：2026-04-21 | 修改需人工审批**