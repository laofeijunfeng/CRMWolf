---
status: completed
created: 2026-06-12
updated: 2026-06-12
related_requirements: -
related_pr: -
---

# CRMWolf Claude Code 规范体系重构方案

> 版本：1.0 | 日期：2026-06-12 | 状态：设计方案

---

## 一、设计原则

### 1.1 核心目标

将分散在 **28 个文件（9,000+ 行）** 的规范重构为**四层结构**，实现：

| 目标 | 说明 |
|------|------|
| **低认知成本** | Claude 启动时仅加载 ~700 行核心规则，而非 9,000 行 |
| **可审计性** | 每条红线有唯一来源，避免多文件重复导致的局部不同步 |
| **可回滚性** | Preview 模式强制执行，所有改动可预览、可阻断、可回滚 |
| **防幻觉** | 业务常量禁止推断，必须查阅代码定义 |

### 1.2 分层逻辑

```
┌─────────────────────────────────────────────────────────────┐
│                    Claude Code 加载顺序                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ① 宪法层 CLAUDE.md                                          │
│     └── 技术栈锁定 + 红线禁令 + 设计流程                        │
│     └── 最高优先级，全项目通用                                  │
│                                                             │
│  ② 规则层 .claude/rules/*.md                                 │
│     ├── frontend.md      (TypeScript + Vue + Pinia)         │
│     ├── backend.md       (Pydantic + CRUD + team_id)        │
│     ├── design.md        (UI 红线 + Design Token 引用)       │
│     ├── testing.md       (覆盖率 + 禁止跳过)                  │
│     ├── workflow-engine.md   (AI 编排 + 幂等性)              │
│     └── dangerous-actions.md  (CRITICAL 操作阻断)           │
│     └── 每个文件 80-160 行，总计 ~700 行                       │
│                                                             │
│  ③ 模块入口层 [Module]/CLAUDE.md                              │
│     ├── CRM-Client/CLAUDE.md    (前端模块入口)               │
│     ├── CRM-Server/CLAUDE.md    (后端模块入口)               │
│     ├── CRM-Server/app/services/CLAUDE.md  (AI 服务约束)    │
│     └── CRM-Client/src/stores/CLAUDE.md     (Store 约束)   │
│     └── 作业地图 + 防幻觉指令 + 指向 rules 层                   │
│                                                             │
│  ④ 只读参考库 CRM-Docs/                                       │
│     ├── ⚠️ Claude 启动时不自动加载                            │
│     ├── system/          (架构 + 业务链路)                    │
│     ├── best-practices/  (详细模板 + 最佳实践)                │
│     ├── standards/       (AI API 详细规范)                   │
│     └── CRM-Client/docs/ (前端详细规范)                       │
│     └── 按需查阅，作为"电子词典"                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、最终目录结构

```
CRMWolf/
│
├── CLAUDE.md                              # 【宪法层】项目宪法（~80行）
│   ├── 技术栈锁定（Vue3 + FastAPI + MySQL + Redis）
│   ├── 红线禁令（TypeScript 四禁令 + 配置审批 + 迁移强制）
│   ├── 设计流程红线（暂停编码 → 分析 → 查最佳实践 → 方案 → 确认 → 执行）
│   ├── 规则加载顺序说明
│   └── Claude 定位声明（"代码提案者"，无权限触碰生产配置）
│
├── .claude/
│   ├── settings.json                      # 权限配置（已有）
│   │
│   └── rules/                             # 【规则层】日常高频硬性规范（~700行）
│       ├── frontend.md                    # 前端规则（~160行）
│       ├── backend.md                     # 后端规则（~154行）
│       ├── design.md                      # 设计规范（~100行）
│       ├── testing.md                     # 测试规则（~100行）
│       ├── workflow-engine.md             # 🆕 AI Workflow 编排（~80行）
│       └── dangerous-actions.md           # 🆕 CRITICAL 操作阻断（~60行）
│
├── CRM-Client/
│   ├── CLAUDE.md                          # 【模块入口】前端模块（~50行）
│   │   ├── 模块结构地图
│   │   ├── 开发命令速查
│   │   ├── 防幻觉指令（禁止推断客户阶段、发票类型等）
│   │   └── 指向 rules/frontend.md
│   │
│   └── src/
│       └── stores/
│           └── CLAUDE.md                  # 【子目录约束】Store 专属（~40行）
│               ├── State 禁止 any
│               ├── SSE 状态管理
│               └── 解构规则（storeToRefs）
│
├── CRM-Server/
│   ├── CLAUDE.md                          # 【模块入口】后端模块（~50行）
│   │   ├── 模块结构地图
│   │   ├── 开发命令速查
│   │   ├── 防幻觉指令（禁止推断权限码、业务枚举）
│   │   └── 指向 rules/backend.md
│   │
│   └── app/
│       └── services/
│           └── CLAUDE.md                  # 【子目录约束】AI 服务专属（~60行）
│               ├── AI 输出必须结构化（Pydantic）
│               ├── Handler 只能通过 CRUD 操作数据库
│               ├── Guardrails 校验（权限 + 二次确认）
│               └── 代码复用清单
│
└── CRM-Docs/                              # 【只读参考库】不自动加载
    ├── README.md                          # ⚠️ 声明："Claude 启动时不加载本目录"
    │
    ├── system/                            # 系统架构（按需查阅）
    │   ├── ARCHITECTURE.md                # 分层职责详解
    │   ├── BUSINESS-CHAIN-API.md          # 业务链路接口清单
    │   ├── LOGGING-STANDARD.md            # 日志规范
    │   ├── GLOSSARY.md                    # 权限码 + 术语表
    │   └── MODULE-CUSTOMER.md             # 客户模块业务逻辑
    │
    ├── best-practices/                    # 最佳实践（按需查阅）
    │   ├── backend/
    │   │   ├── crud-patterns.md           # CRUD 详细模板
    │   │   ├── team-isolation.md          # team_id 三层架构详解
    │   │   ├── api-design.md              # API 响应格式详解
    │   │   └── database.md                # Model 定义规范
    │   └── frontend/
    │       ├── api-requests.md            # API 请求详细规范
    │       ├── components.md              # 组件开发最佳实践
    │       ├── state-management.md        # 状态管理原则
    │       └── forms.md                   # 表单校验规范
    │
    ├── standards/                         # 开发规范（按需查阅）
    │   ├── AI-API-STANDARD.md             # AI OpenAPI 详细规范
    │   ├── AI-API-IMPLEMENTATION.md       # AI 实现状态
    │   ├── GIT-STANDARD.md                # Git 提交规范
    │   ├── COMPLIANCE-STANDARD.md         # 合规处理
    │   └── DOCKER-PACKAGING.md            # 打包规范
    │
    ├── plans/                             # 实施计划（历史文档）
    ├── requirements/                      # 需求文档（历史文档）
    │
    └── CRM-Client/docs/                   # 前端详细规范（按需查阅）
        ├── TYPESCRIPT.md                  # Approved Types 清单
        ├── COMPONENTS.md                  # Vue 组件完整模板
        ├── STATE-MANAGEMENT.md            # Pinia Store 完整模板
        ├── TESTING.md                     # 测试完整模板
        └── DESIGN-*.md                    # 设计详细规范（5个文件）
```

---

## 三、各层文件详细内容设计

### 3.1 宪法层：CLAUDE.md（~80行）

```markdown
# CRMWolf 项目宪法

**Claude Code 启动时自动加载** - 最高优先级

---

## Claude 定位声明

Claude 在本项目中的定位为**代码提案者**：
- ✅ 编写测试、解释代码逻辑、生成代码提案
- ✅ 在 Preview 模式下展示变更计划，等待用户确认
- ❌ **禁止**直接触碰生产环境配置
- ❌ **禁止**直接推送 `main` 或 `master` 分支
- ❌ **禁止**执行未经审批的 CRITICAL 级别操作

---

## 技术栈锁定（不可修改）

| 层级 | 技术栈 | 版本 | 用途说明 |
|------|--------|------|----------|
| 前端 | Vue + TypeScript + Element Plus + Pinia + Vite | 3.5 / 5.7 | SPA 应用 |
| 后端 | FastAPI + SQLAlchemy + Pydantic | 0.115 | RESTful API |
| 数据库 | MySQL + Redis | 8.0 / 7.x | MySQL 业务实体，Redis Session 幂等 |

---

## 红线禁令（人类专属 - AI 禁止修改）

| 红线 | 内容 | 违规处理 |
|------|------|----------|
| TypeScript | 禁用 `any` `as any` `@ts-ignore` `!` | 拒绝执行，报告 COMPLIANCE |
| 配置修改 | tsconfig/eslint.config/pyproject.toml | 需人工审批 |
| 数据库变更 | 必须使用 Alembic 迁移 | 拒绝独立脚本 |
| 团队隔离 | 新增业务表必须添加 team_id | 拒绝遗漏 |
| 新代码要求 | 单测必写，组件必配 Stories | 拒绝提交 |
| 外部数据 | Zod/Pydantic 边界校验强制 | 拒绝绕开校验 |
| 分支纪律 | 修改前必须新建特性分支 | 拒绝直接推送 main |

---

## 设计流程红线

面对任何非 trivial 问题必须遵循：

```
1. 暂停编码 → 不立即改代码
2. 深入分析 → 理解架构、数据流、影响范围
3. 查阅最佳实践 → CRM-Docs/best-practices/README.md
4. 设计方案 → 写完整方案（数据流、改动清单、影响分析）
5. 用户确认 → 等待确认
6. 统一执行 → 一次性修改所有相关位置
7. 验证完整性 → 测试流程正常
```

**违规判定**：直接改代码不分析 = 🔴 高级违规

---

## 规则加载顺序

```
① 本文件（宪法）→ 最高优先级
② .claude/rules/*.md → 类型专属规则
③ [Module]/CLAUDE.md → 模块入口（按需加载）
④ CRM-Docs/ → 只读参考库（不自动加载，按需查阅）
```

---

## 详细规范索引（按需查阅）

| 需要什么 | 查阅位置 |
|----------|----------|
| TypeScript Approved Types | `CRM-Client/docs/TYPESCRIPT.md` |
| Vue 组件完整模板 | `CRM-Client/docs/COMPONENTS.md` |
| CRUD 详细模板 | `CRM-Docs/best-practices/backend/crud-patterns.md` |
| team_id 三层架构详解 | `CRM-Docs/best-practices/backend/team-isolation.md` |
| AI OpenAPI 详细规范 | `CRM-Docs/standards/AI-API-STANDARD.md` |
| 业务链路接口清单 | `CRM-Docs/system/BUSINESS-CHAIN-API.md` |
| 权限码/术语表 | `CRM-Docs/system/GLOSSARY.md` |

---

**版本：2.0 | 最后更新：2026-06-12 | 修改需人工审批**
```

---

### 3.2 规则层：.claude/rules/*.md（~700行）

#### 3.2.1 frontend.md（~160行）- 已存在，需微调

**核心内容**：
- TypeScript 四禁令（`: any` `as any` `@ts-ignore` `!`）
- Vue Props/Emits 必须类型化
- Pinia State 禁止 any，必须 storeToRefs 解构
- API 请求必须 Zod 校验
- 禁止行为汇总表

**微调要点**：删除重复的代码示例，仅保留禁令 + 替代方案要点。

---

#### 3.2.2 backend.md（~154行）- 已存在，需微调

**核心内容**：
- Pydantic 强制校验，禁止裸 dict
- CRUD 层统一入口，命名规范表
- team_id 必传规则（三层架构表）
- API 响应格式统一，错误码表
- 数据库迁移：Alembic 标准流程
- 禁止行为汇总表

---

#### 3.2.3 design.md（~100行）- 已存在，需重写

**核心内容**：
- **品牌色权威来源声明**：唯一来源 `variables.scss`
- 设计红线汇总（7项）
- 颜色/圆角/间距速查表（引用变量名而非硬编码值）
- 表格/页面布局规范要点
- 禁止魔数声明

**重写要点**：

```markdown
# UI 设计规范

**适用范围**：CRM-Client 所有 UI 开发

---

## 品牌色权威来源

**唯一来源**：`CRM-Client/src/styles/variables.scss`

⚠️ **禁止在 Markdown 中重复定义颜色值**，所有 UI 代码必须引用 Sass 变量：

| 用途 | Sass 变量 | 禁止行为 |
|------|-----------|----------|
| 品牌主色 | `$wolf-primary` | 禁止硬编码 `#4A6FA5` |
| 成功状态 | `$wolf-success-text` / `$wolf-success-bg` | 禁止硬编码颜色值 |
| 警告状态 | `$wolf-warning-text` / `$wolf-warning-bg` | 禁止硬编码颜色值 |
| 危险状态 | `$wolf-danger-text` / `$wolf-danger-bg` | 禁止硬编码颜色值 |

---

## 设计红线汇总

| 红线 | 说明 |
|------|------|
| 禁止纯色填充标签 | 必须用浅底色 + 同色系文字（引用 `$wolf-*-bg` + `$wolf-*-text`） |
| 禁用 700+ 字重 | 最大使用 600 (semibold) |
| 禁止高饱和色 | 使用 `$wolf-*` 低饱和色系 |
| 禁止多层阴影 | 卡片仅用一级阴影 |
| 禁止竖分割线 | 仅保留行分割线 |
| 禁止斑马纹 | 用 hover 高亮代替 |
| 禁止魔数 | 所有间距/圆角必须引用 Design Token |

---

## Design Token 速查

| Token | Sass 变量 | 用途 |
|-------|-----------|------|
| 页面内边距 | `$wolf-page-padding` | 24px |
| 卡片圆角 | `$wolf-radius-lg` | 12px |
| 按钮圆角 | `$wolf-radius-sm` | 4px/8px |
| 表头高度 | `$wolf-table-header-height` | 44px |

⚠️ **禁止在 CSS 中写魔数如 `margin: 13px`，必须向 4px 基准网格对齐**

---

**详细参考**：`CRM-Client/docs/DESIGN-*.md`（5个文件）
```

---

#### 3.2.4 testing.md（~100行）- 已存在，保持不变

---

#### 3.2.5 workflow-engine.md（~80行）- 🆕 新建

```markdown
# AI Workflow 编排规则

**适用范围**：CRM-Server/app/services/ AI 相关开发

---

## ReAct 循环规则

| 参数 | 值 | 说明 |
|------|-----|------|
| `max_rounds` | 5 | 最大轮数，防止无限循环 |
| `preview` | True（默认） | 执行前必须预览变更计划 |
| `action_id` | 必填（执行时） | 幂等性 ID，防止重复执行 |

---

## Preview 模式强制

所有 Action 层接口必须支持 Preview 模式：

```
用户请求 → Intent 解析 → Preview 返回变更计划 → 用户确认 → 执行
```

**禁止**：直接执行未经 Preview 的操作

---

## 幂等性管理

| 规则 | 要求 |
|------|------|
| action_id 生成 | UUID 或用户提供 |
| Redis 存储 | Session 幂等检查 |
| 重复请求 | 返回相同结果，不重复执行 |

---

## 回滚机制

| 场景 | 回滚行为 |
|------|----------|
| 单 Action 失败 | 自动回滚该 Action |
| 多 Action 部分失败 | 回滚已执行的 Actions |
| 用户取消 | 回滚所有未提交的变更 |

---

## 编排调度

```
Orchestrator 调度流程：
1. 接收 Intent → 解析为 Action 序列
2. 逐个执行 Action（Preview → Confirm → Execute）
3. 记录审计日志
4. 返回最终结果
```

---

**详细参考**：`CRM-Docs/standards/AI-API-STANDARD.md`, `CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md`
```

---

#### 3.2.6 dangerous-actions.md（~60行）- 🆕 新建

```markdown
# CRITICAL 操作阻断清单

**适用范围**：所有 Claude 执行的操作

---

## CRITICAL 级别操作清单

以下操作被标记为 CRITICAL，**必须强制阻断**：

| 操作类型 | 触发条件 | 阻断措施 |
|----------|----------|----------|
| 删除客户 | `delete_customer` intent | Preview + 二次确认 + 审批流 |
| 批量修改 | 批量数量 > 10 | Preview + 二次确认 |
| 合同作废 | 合同状态变更为作废 | Preview + 审批流校验 |
| 修改生产配置 | 涉及 config 文件 | 拒绝执行，需人工审批 |
| 推送 main 分支 | 目标分支为 main/master | 拒绝执行 |

---

## AI 禁止执行的操作

| 操作 | 原因 |
|------|------|
| 直接推送 main 分支 | 违反分支纪律 |
| 修改 tsconfig/eslint.config/pyproject.toml | 需人工审批 |
| 修改 Alembic 迁移文件 | 需人工审批 |
| 执行未 Preview 的 CRITICAL 操作 | 违反 Preview 强制规则 |
| 绕过 CRUD 直接操作数据库 | 违反 CRUD 统一入口规则 |

---

## 阻断后处理

```
触发阻断 → 停止执行 → 填写 COMPLIANCE 报告 → 等待人工审批
```

---

**详细参考**：`CRM-Docs/standards/COMPLIANCE-STANDARD.md`, `CRM-Docs/standards/AI-API-STANDARD.md`
```

---

### 3.3 模块入口层：[Module]/CLAUDE.md

#### 3.3.1 CRM-Client/CLAUDE.md（~50行）- 已存在，需增加防幻觉指令

```markdown
# CRM-Client 前端模块

**Claude Code 进入此目录时自动加载**

---

## 模块结构地图

```
CRM-Client/
├── src/
│   ├── api/           # API 请求层（复用 baseURL，禁止硬编码）
│   ├── components/    # 共享组件（必须配 .stories.ts）
│   ├── views/         # 页面组件
│   ├── stores/        # Pinia 状态管理（详见 stores/CLAUDE.md）
│   ├── schemas/       # TypeScript 类型 + Zod schema
│   ├── styles/        # Design Token 唯一来源（variables.scss）
│   └── utils/         # 工具函数
```

---

## 开发命令

```bash
npm run dev          # 启动开发服务器
npm run lint         # ESLint 校验
npm run type-check   # TypeScript 校验
npm run test:unit    # 单元测试
```

---

## 防幻觉指令（禁止推断）

Claude **绝对禁止推断**以下业务常量，必须查阅代码定义：

| 禁止推断 | 定义位置 |
|----------|----------|
| 客户状态枚举 | `CRM-Server/app/constants/customer_status.py` |
| 商机阶段映射 | `CRM-Server/app/constants/opportunity_stages.py` |
| 权限码 | `CRM-Docs/system/GLOSSARY.md` |
| 设计 Token | `CRM-Client/src/styles/variables.scss` |

---

## 核心规则

- **TypeScript 四禁令**：禁用 `any` `as any` `@ts-ignore` `!`
- **组件 Props/Emits**：必须类型化
- **设计 Token**：引用 variables.scss，禁止魔数

**详细规则**：`.claude/rules/frontend.md`, `.claude/rules/design.md`
```

---

#### 3.3.2 CRM-Server/CLAUDE.md（~50行）- 已存在，需增加防幻觉指令

```markdown
# CRM-Server 后端模块

**Claude Code 进入此目录时自动加载**

---

## 模块结构地图

```
CRM-Server/
├── app/
│   ├── api/           # API 端点层
│   ├── crud/          # CRUD 操作层（统一入口）
│   ├── models/        # SQLAlchemy 模型
│   ├── schemas/       # Pydantic schema
│   ├── services/      # 业务逻辑层（详见 services/CLAUDE.md）
│   ├── constants/     # 业务常量定义
│   └── core/          # 配置、依赖注入
├── migrations/        # Alembic 迁移文件
```

---

## 开发命令

```bash
./run.sh             # 启动服务
ruff check app/      # Python lint
pytest tests/unit -v # 单元测试
alembic revision -m "描述"  # 创建迁移
```

---

## 防幻觉指令（禁止推断）

Claude **绝对禁止推断**以下业务常量，必须查阅代码定义：

| 禁止推断 | 定义位置 |
|----------|----------|
| 客户阶段映射 | `app/constants/customer_stages.py` |
| 商机状态枚举 | `app/constants/opportunity_status.py` |
| 发票类型 | `app/constants/invoice_types.py` |
| 权限码 | `CRM-Docs/system/GLOSSARY.md` |

---

## 核心规则

- **Pydantic 强制校验**：禁止裸 dict
- **CRUD 统一入口**：禁止直接 query
- **team_id 必传**：三层架构

**详细规则**：`.claude/rules/backend.md`
```

---

### 3.4 只读参考库：CRM-Docs/README.md

**新增开头声明**：

```markdown
# CRM-Docs 只读参考库

⚠️ **Claude Code 启动时不自动加载本目录**

本目录为深度知识库，仅在 Claude 需要调取具体知识时**按需查阅**：

| 需要什么 | 查阅位置 |
|----------|----------|
| 详细模板 | `CRM-Client/docs/` 或 `best-practices/` |
| 业务链路 | `system/BUSINESS-CHAIN-API.md` |
| AI 详细规范 | `standards/AI-API-STANDARD.md` |
| 权限码/术语 | `system/GLOSSARY.md` |

---

## 目录结构

（保持原有内容）

---

**维护团队**：CRMWolf 开发团队
```

---

## 四、迁移与清理计划

### 4.1 新建文件（2个）

| 文件 | 内容 | 行数 |
|------|------|------|
| `.claude/rules/workflow-engine.md` | AI Workflow 编排规则 | ~80行 |
| `.claude/rules/dangerous-actions.md` | CRITICAL 操作阻断清单 | ~60行 |

### 4.2 修改文件（5个）

| 文件 | 修改内容 |
|------|----------|
| `CLAUDE.md` | 增加 Claude 定位声明 + 分支纪律红线 |
| `.claude/rules/design.md` | 重写，增加品牌色权威来源声明 + 禁止魔数 |
| `CRM-Client/CLAUDE.md` | 增加防幻觉指令表格 |
| `CRM-Server/CLAUDE.md` | 增加防幻觉指令表格 |
| `CRM-Docs/README.md` | 新增开头声明："Claude 启动时不自动加载" |

### 4.3 清理建议（可选）

| 文件 | 处理建议 | 原因 |
|------|----------|------|
| `CRM-Client/docs/CRMWolf 设计规范.md` | **删除或合并** | 2541行完整备份，与 variables.scss 冗余 |
| `CRM-Client/docs/前端组件库迁移与UI标准化方案.md` | **删除** | 空文件，无内容 |
| `CRM-Docs/system/UI-DESIGN-SPEC.md` | **保留但标记为历史文档** | 与 variables.scss 品牌色一致，但内容与 CRMWolf 设计规范有重叠 |

### 4.4 不删除的文件

以下文件保留作为只读参考库：
- `CRM-Client/docs/TYPESCRIPT.md` - Approved Types 清单
- `CRM-Client/docs/COMPONENTS.md` - Vue 组件完整模板
- `CRM-Client/docs/STATE-MANAGEMENT.md` - Pinia Store 完整模板
- `CRM-Client/docs/TESTING.md` - 测试完整模板
- `CRM-Client/docs/DESIGN-*.md` - 设计详细规范（5个）
- `CRM-Docs/best-practices/backend/*.md` - CRUD/API 详细模板（4个）
- `CRM-Docs/system/*.md` - 系统架构 + 业务链路（7个）
- `CRM-Docs/standards/*.md` - AI API + Git + 合规（7个）

---

## 五、预期效果

### 5.1 Claude 启动时加载量对比

| 对比项 | 重构前 | 重构后 | 降低比例 |
|--------|--------|--------|----------|
| 自动加载文件数 | 28 个 | **10 个** | -64% |
| 自动加载行数 | ~9,000 行 | **~700 行** | -92% |
| 规则重复度 | team_id 在 6 个文件 | **1 个文件** | -83% |

### 5.2 规则唯一来源

| 规则 | 重构前 | 重构后 |
|------|--------|--------|
| TypeScript 四禁令 | 3 个文件重复 | **frontend.md（唯一）** |
| team_id 规则 | 6 个文件重复 | **backend.md（唯一）** |
| 品牌色 | 4 个文件冲突 | **variables.scss（唯一）** |
| 设计红线 | 7 个文件分散 | **design.md（唯一）** |

### 5.3 认知成本降低

| 场景 | 重构前 | 重构后 |
|------|--------|--------|
| Claude 启动时 | 加载 28 个文件，认知负担重 | 仅加载宪法 + rules（~700行），专注核心红线 |
| 查阅详细模板 | 不知道去哪找 | 模块入口明确指向 CRM-Docs/ 只读参考库 |
| 执行危险操作 | 可能直接执行 | dangerous-actions.md 强制阻断 + Preview |
| 生成 UI 代码 | 可能使用魔数或硬编码颜色 | design.md 强制引用 variables.scss |

---

## 六、执行顺序建议

```
Phase 1: 新建规则文件（2个）
  ├── workflow-engine.md
  └── dangerous-actions.md

Phase 2: 修改现有文件（5个）
  ├── CLAUDE.md（增加定位声明 + 分支纪律）
  ├── design.md（重写，增加品牌色权威来源）
  ├── CRM-Client/CLAUDE.md（增加防幻觉指令）
  ├── CRM-Server/CLAUDE.md（增加防幻觉指令）
  └── CRM-Docs/README.md（增加只读声明）

Phase 3: 清理冗余文件（可选）
  ├── 删除空文件：前端组件库迁移与UI标准化方案.md
  └── 标记历史文档：CRMWolf 设计规范.md、UI-DESIGN-SPEC.md

Phase 4: 验证
  ├── 启动 Claude Code 新会话
  ├── 检查自动加载的文件数量（应为 10 个）
  ├── 测试规则唯一来源是否生效
  └── 测试防幻觉指令是否阻止 Claude 推断业务常量
```

---

**方案版本：1.0 | 设计日期：2026-06-12 | 设计者：CRMWolf 团队**