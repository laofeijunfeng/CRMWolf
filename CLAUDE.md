# CRMWolf 项目宪法

**Claude Code 启动时自动加载** - 最高优先级

---

## Claude 定位声明

Claude 在本项目中的定位为**代码提案者**：

| 允许行为 | 禁止行为 |
|----------|----------|
| ✅ 编写测试、解释代码逻辑 | ❌ 直接触碰生产环境配置 |
| ✅ 在 Preview 模式下展示变更计划 | ❌ 直接推送 `main` 或 `master` 分支 |
| ✅ 生成代码提案、重构建议 | ❌ 执行未经审批的 CRITICAL 级别操作 |
| ✅ 查阅只读参考库获取详细模板 | ❌ 绕过 CRUD 直接操作数据库 |

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
| **分支纪律** | **修改前必须新建特性分支，禁止直接推送 main** | **拒绝执行** |
| **文档位置** | **CRM-Docs 根目录只允许 README.md，禁止创建散落 md** | **pre-commit 阻止提交** |
| **进度文档** | **禁止创建 PHASE-X-SUMMARY 等临时进度文档** | **使用 Task 工具替代** |

---

## 文档位置红线

**CRM-Docs 目录结构规范**：

```
CRM-Docs/
├── README.md              ← ✅ 唯一允许的根目录 md 文件（导航入口）
├── requirements/*.md      ← 需求文档
├── plans/*.md             ← 计划文档
├── changelog/**/*.md      ← 实施总结（包括阶段总结）
├── archive/**/*.md        ← 归档文档
├── standards/*.md         ← 规范文档
├── system/**/*.md         ← 系统说明
└── best-practices/**/*.md ← 最佳实践
└── scripts/*.sh           ← CI 脚本
```

**禁止创建以下文档在根目录**：

| ❌ 禁止行为 | ✅ 正确做法 |
|------------|------------|
| `CRM-Docs/PHASE-X-SUMMARY.md` | `CRM-Docs/changelog/technical/YYYY-MM-DD-xxx.md` |
| `CRM-Docs/FINAL-SUMMARY.md` | `CRM-Docs/changelog/technical/YYYY-MM-DD-final.md` |
| `CRM-Docs/IMPLEMENTATION-PROGRESS.md` | 使用 TaskCreate/TaskUpdate 工具 |
| `CRM-Docs/NEXT-STEPS-GUIDE.md` | `CRM-Docs/plans/xxx-NEXT-STEPS.md` |
| `CRM-Docs/index.md` | 删除（已有 README.md） |

**进度跟踪替代方案**：
- 使用 `TaskCreate` / `TaskUpdate` 工具跟踪任务进度
- 使用 Claude Code 内存系统记录临时状态
- 不要创建临时文档记录进度

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

### 违规判定

| 行为 | 等级 |
|------|------|
| 直接改代码不分析 | 🔴 高 |
| 只改一处不考虑其他影响 | 🔴 高 |
| 凭直觉设计方案（不查业界实践） | 🔴 高 |
| 零散改动导致逻辑不一致 | 🔴 高 |
| 写死动态数据 | 🔴 高 |

---

## 规则加载顺序

Claude Code 按以下顺序加载规则：

```
① 本文件（宪法）→ 最高优先级

② .claude/rules/ → 类型专属规则（自动加载）
   ├── frontend.md      - TypeScript + Vue + Pinia
   ├── backend.md       - Pydantic + CRUD + team_id
   ├── design.md        - UI 红线 + Design Token
   ├── testing.md       - 覆盖率 + 禁止跳过
   ├── workflow-engine.md   - AI 编排 + 幂等性
   └── dangerous-actions.md - CRITICAL 操作阻断

③ [Module]/CLAUDE.md → 模块入口（按需加载）
   ├── CRM-Client/CLAUDE.md
   ├── CRM-Server/CLAUDE.md
   ├── CRM-Server/app/services/CLAUDE.md
   └── CRM-Client/src/stores/CLAUDE.md

④ CRM-Docs/ → 只读参考库（不自动加载，按需查阅）
```

---

## 权威文档（单一事实来源）

**重要**：当多个文档信息冲突时，按以下优先级裁决：

| 优先级 | 文档 | 主题 | 其他文档仅允许引用 |
|--------|------|------|-------------------|
| **critical** | `CLAUDE.md`（本文件） | 项目宪法 | ✅ 所有文档遵循 |
| **high** | `CRM-Client/docs/TYPESCRIPT.md` | TypeScript 类型定义 | ✅ 禁止重新定义类型 |
| **high** | `CRM-Client/docs/COMPONENTS.md` | Vue 组件规范 | ✅ 禁止重新定义组件模板 |
| **high** | `CRM-Docs/system/GLOSSARY.md` | 权限码/状态枚举 | ✅ 禁止臆测枚举值 |
| **high** | `CRM-Docs/system/BUSINESS-CHAIN-API.md` | API 接口规范 | ✅ 禁止臆测接口参数 |
| **high** | `CRM-Docs/standards/AI-API-STANDARD.md` | AI OpenAPI 规范 | ✅ AI 开发遵循 |
| normal | 其他规范文档 | 各主题规范 | 按需查阅 |

**冲突裁决规则**：
- `priority: critical` 覆盖所有其他文档
- `priority: high` 覆盖 `priority: normal` 和 `low`
- 同优先级时，更新日期较新的文档优先

---

## 详细规范索引（按需查阅）

| 需要什么 | 查阅位置 |
|----------|----------|
| TypeScript Approved Types | `CRM-Client/docs/TYPESCRIPT.md` |
| Vue 组件完整模板 | `CRM-Client/docs/COMPONENTS.md` |
| Pinia Store 完整模板 | `CRM-Client/docs/STATE-MANAGEMENT.md` |
| CRUD 详细模板 | `CRM-Docs/best-practices/backend/crud-patterns.md` |
| team_id 三层架构详解 | `CRM-Docs/best-practices/backend/team-isolation.md` |
| AI OpenAPI 详细规范 | `CRM-Docs/standards/AI-API-STANDARD.md` |
| 业务链路接口清单 | `CRM-Docs/system/BUSINESS-CHAIN-API.md` |
| 权限码/术语表 | `CRM-Docs/system/GLOSSARY.md` |

---

## 开发命令速查

```bash
# 前端
cd CRM-Client && npm run dev          # 启动开发
npm run lint                          # ESLint 校验
npm run type-check                    # TypeScript 校验
npm run test:unit                     # 单测

# 后端
cd CRM-Server && ./run.sh             # 启动服务
ruff check app/                       # Python lint
mypy app/                             # 类型检查
pytest tests/unit -v                  # 单测
alembic revision -m "描述"            # 创建迁移
alembic upgrade head                  # 执行迁移
```

---

**版本：2.2 | 最后更新：2026-06-12 | 修改需人工审批**