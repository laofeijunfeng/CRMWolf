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
| 放置文件 | system/ARCHITECTURE.md | 禁止跨模块 |
| 写 Vue 组件 | COMPONENTS.md | 禁止内联类型 |
| 用 Pinia | STATE-MANAGEMENT.md | 禁止 any 状态 |
| 写单测 | TESTING.md | 禁止跳过测试 |
| 改代码 | standards/DOCS-STANDARD.md | 必须同步文档 |
| 查权限码 | system/GLOSSARY.md | 禁止猜测编码 |
| 查业务流程 | system/SYSTEM-DESCRIPTION.md | 禁止猜测逻辑 |
| **提交代码** | **standards/GIT-STANDARD.md** | **任务完成主动提交** |
| **写 UI 样式** | **DESIGN-COMPONENTS.md** | **禁止纯色标签** |
| **写列表页** | **DESIGN-TABLE.md** | **禁止竖分割线** |
| **查状态色** | **DESIGN-QUICK-REF.md** | **禁止高饱和色** |
| **写二级页面** | **DESIGN-PAGE-LAYOUT.md** | **必须有 sticky 头部** |
| **复用逻辑** | **先搜索现有实现** | **禁止重复编写** |
| **改数据库表** | **Alembic migrations/** | **禁止独立脚本** |
| **新增业务表** | **必须添加 team_id** | **禁止遗漏隔离** |
| **打包部署** | **standards/DOCKER-PACKAGING.md** | **禁止遗漏 buildx** |
| **🤖 AI OpenAPI 开发** | **standards/AI-API-STANDARD.md** | **禁止绕过规范** |
| **🤖 AI OpenAPI 迭代** | **plans/AI-OPENAPI-IMPLEMENTATION-PLAN.md** | **禁止跳过检查清单** |

---

## 代码复用原则

**核心要求**：在实现任何功能前，必须先搜索项目中是否已有类似实现。

| 复用场景 | 搜索关键词 | 复用目标 |
|----------|------------|----------|
| 时间解析 | `parse_relative_time`, `parse_date` | `follow_up_parser_service` |
| ID 提取 | `extract_id`, `ID_PATTERN` | `follow_up_parser_service` |
| 枚举匹配 | `enum_mapping`, `get_enum` | `ai_enum_mapping_crud` |
| 跟进记录 | `follow_up`, `FollowUpHandler` | `follow_up_handler.py` |
| SSE 流式 | `SSE`, `stream`, `chatSSE` | `ai_assistant_api` |
| 权限检查 | `permission`, `has_permission` | `usePermissionStore` |

**实施流程**：
1. **搜索先行**：使用 `grep` 或文件搜索查找关键词
2. **评估复用**：确认现有实现是否可复用
3. **抽离共享**：如需多处使用，抽离到独立服务
4. **文档记录**：在服务注释中标注可复用场景

**违规示例**：
- ❌ 重复编写时间解析逻辑（应复用 `follow_up_parser_service`）
- ❌ 重复编写 ID 提取正则（应复用 `ID_PATTERN`）
- ❌ 重复编写 SSE 流式响应（应复用现有 SSE 模式）

**正确示例**：
- ✅ 新增 AI 功能复用 `follow_up_parser_service.parse_relative_time`
- ✅ FollowUpHandler 导入共享服务的正则和方法
- ✅ 多处调用统一抽离为独立服务文件

---

## 团队隔离规则

**核心要求**：所有新增业务表必须添加 `team_id` 字段，确保多租户数据隔离。

### 必须添加 team_id 的表类型

| 表类型 | 示例 | 说明 |
|--------|------|------|
| 业务实体表 | customers, leads, opportunities, contracts | 核心业务数据，必须隔离 |
| 配置表 | opportunity_stages, approval_flows, procurement_methods | 团队级配置，需要隔离 |
| 日志表 | operation_logs, conversation_logs, approval_records | 统计分析需要按团队 |
| 团队资源表 | ai_config, api_keys | 团队独立管理 |

### 不需要 team_id 的表类型

| 表类型 | 示例 | 说明 |
|--------|------|------|
| 系统级配置 | roles, permissions, ai_skills | 全局共享定义 |
| 团队关系表 | teams, user_teams | 团队定义本身 |
| 用户表 | users | 用户跨团队存在 |

### 新增表检查流程

```
1. 判断表类型 → 是否需要 team_id
2. 模型定义 → 添加 team_id 字段
   team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
3. Alembic 迁移 → 添加列 + 索引
4. CRUD 层 → 方法添加 team_id 参数
5. API 层 → 注入 get_current_user_team
6. 运行检查脚本 → scripts/check_team_isolation.py
```

### 检查脚本

```bash
# 验证所有表的 team_id 配置
python scripts/check_team_isolation.py

# 生成修复建议
python scripts/check_team_isolation.py --fix
```

---

## 数据库迁移规则

**核心要求**：所有数据库表结构变更必须使用 Alembic 迁移，禁止创建独立 Python 脚本。

| 操作 | 正确方式 | 错误方式 |
|------|----------|----------|
| 新增字段 | `alembic revision` → 编写 upgrade/downgrade | 独立 `.py` 脚本 |
| 修改字段 | Alembic migration | 直接改模型不写迁移 |
| 新建表 | Alembic migration | `Base.metadata.create_all()` |
| 数据迁移 | 在 migration 的 upgrade() 中用 op.execute() | 独立数据脚本 |

**标准流程**：
```bash
# 1. 创建迁移文件
alembic revision -m "描述变更内容"

# 2. 编辑 migrations/versions/xxx.py
#    编写 upgrade() 和 downgrade()

# 3. 执行迁移
alembic upgrade head

# 4. 验证
alembic current  # 查看当前版本
```

**迁移文件命名**：
- `001_initial.py` - 初始化
- `002_xxx.py` - 按顺序编号
- 文件头必须包含 `revision`、`down_revision`

**违规示例**：
- ❌ 创建 `migrations/add_xxx_column.py` 独立脚本
- ❌ 直接修改模型后不写迁移文件
- ❌ 在 main.py 启动时执行数据库变更

---

## 规范导航

```
CRMWolf/
├── AGENTS.md                    ← 本文件（唯一入口）
├── CRM-Docs/README.md           ← 文档目录导航
│   ├── standards/QUICK-START.md ← 团队快速上手（5分钟）
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
│   ├── system/                  ← 系统说明文档
│   │   ├── SYSTEM-DESCRIPTION.md ← 系统综合说明（功能模块、业务流程）
│   │   ├── ARCHITECTURE.md       ← 前后端目录、模块边界
│   │   ├── GLOSSARY.md           ← 术语、权限码、状态枚举
│   │   ├── BUSINESS-CHAIN-API.md ← 业务链路接口说明
│   │   ├── UI-DESIGN-SPEC.md     ← UI 设计规范
│   │   └── LOGGING-STANDARD.md   ← 日志规范
│   │
│   ├── standards/               ← 开发规范
│   │   ├── GIT-STANDARD.md       ← Git 提交规范（AI 自主执行）
│   │   ├── COMPLIANCE-STANDARD.md ← 合规报告模板
│   │   ├── DOCS-STANDARD.md      ← 文档同步规则
│   │   ├── SPEC-CHANGELOG.md     ← 规范变更日志
│   │   ├── AI-KNOWLEDGE.md       ← AI 知识沉淀
│   │   ├── AI-API-STANDARD.md    ← 🤖 AI OpenAPI 接口规范（必读）
│   │   └── QUICK-START.md        ← 快速上手指南
│   │
│   ├── plans/                    ← 实施计划
│   │   └── AI-OPENAPI-IMPLEMENTATION-PLAN.md ← 🤖 AI OpenAPI 实施计划
│   │
│   └── requirements/            ← 需求文档
│       ├── AI-OPENAPI-REQUIREMENTS.md ← AI 专用 OpenAPI 需求
│       └── OPEN-API-REQUIREMENTS.md   ← 开放接口需求规格
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
| 新增 API 端点 | system/ARCHITECTURE.md → api/层 → TYPESCRIPT.md 取类型 |
| 创建 Vue 页面 | COMPONENTS.md → 模板 → system/GLOSSARY.md 查状态码 |
| 新增 Pinia Store | STATE-MANAGEMENT.md → 模板 → TYPESCRIPT.md 取类型 |
| 写单测 | TESTING.md → 模板 → 先写测试再写代码 |
| 修复类型错误 | TYPESCRIPT.md → 查 Approved Types → 不用 any |
| 查权限码 | system/GLOSSARY.md → 权限码清单 |
| 查业务流程 | system/SYSTEM-DESCRIPTION.md → 业务模块说明 |
| 查 API 接口 | system/BUSINESS-CHAIN-API.md → 接口清单 |
| **提交代码** | **standards/GIT-STANDARD.md → 判断时机 → 执行校验 → 分组提交** |
| **写列表页表格** | **DESIGN-TABLE.md → 表头/行规范 → 状态标签用 DESIGN-QUICK-REF.md** |
| **写按钮/标签** | **DESIGN-COMPONENTS.md → 按钮规范 → DESIGN-QUICK-REF.md 查色** |
| **调整间距/圆角** | **DESIGN-SPACING.md → 间距 token → 圆角速查** |
| **写表单/管理页** | **DESIGN-PAGE-LAYOUT.md → 选择布局类型 → 模板复用** |
| **改数据库表** | **alembic revision → 编写 migrations/versions/*.py** |
| **打包部署** | **standards/DOCKER-PACKAGING.md → buildx 构建 → docker save 导出** |
| **🤖 AI OpenAPI 开发** | **standards/AI-API-STANDARD.md → 查协议规范 → plans/ 查进度** |

---

**版本：1.2 | 最后更新：2026-05-28 | 修改需人工审批**