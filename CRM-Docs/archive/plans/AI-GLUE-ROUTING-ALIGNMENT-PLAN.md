---
status: completed
created: 2026-05-26
updated: 2026-05-26
related_requirements: ../requirements/AI-GLUE-ROUTING-ALIGNMENT-RFC.md
related_pr: -
---

# AI GLUE 路由对齐整改计划

> 版本：2.0 | 创建日期：2026-05-26 | 状态：**已完成 ✅**
> 关联 RFC：CRM-Docs/requirements/AI-GLUE-ROUTING-ALIGNMENT-RFC.md
> 依据原则：单一写入者 + 分层信任边界 + Preview-Before-Write

---

## 一、违规诊断（已修复）

### 当前架构（违规 - 已整改）

```
glue/ActionExecutor (app/glue/core/executor.py)
  → DynamicSkillService.execute_action [已移除]
  → HandlerFactory.execute_handler [已移除]
  → Handler.execute [已移除]
  → CRUD 直接写 [已移除]
```

### 整改后架构（合规）

```
glue/ActionExecutor
  → INTENT_TO_ACTION_MAP 显式映射
  → AIActionExecutor (app/services/ai/action_executor.py)
  → CRUD 写操作 + 审计日志
```

### 问题点（已修复）

| 红线 | 违规位置 | 说明 | 状态 |
|------|---------|------|------|
| C-1 | `glue/core/executor.py` | glue 层调用 DynamicSkillService → Handler → CRUD | ✅ 已修复 |
| C-4 | `glue/core/executor.py` | Handler 被 glue 层直接调用 | ✅ 已修复 |
| C-5 | `glue/core/executor.py` | `self.db` session 被传入 glue 层 | ⚠️ 部分合规（见说明） |
| 原则1 | 整体链路 | 绕过 `/ai/actions/` 的 preview→execute 双步轨道 | ✅ 已修复 |
| 原则3 | 预览缺失 | DynamicSkillService 的 preview 不是 `/ai/actions/` 的 preview | ✅ 已修复 |

---

## 二、整改目标（已达成）

### 目标架构（合规 - 已实现）

```
glue/ActionExecutor
  → 调用 INTENT_TO_ACTION_MAP 显式映射
  → AIActionExecutor (app/services/ai/action_executor.py)
  → CRUD 写操作 + 审计日志
```

### 合规验收标准（已达成）

| 标准 | 说明 | 状态 |
|------|------|------|
| R-1 | 所有写操作必须通过 `/ai/actions/` 端点 | ✅ 已达成 |
| R-2 | 所有写操作必须经过 preview=true → 确认 → preview=false 双步 | ✅ 已达成 |
| R-3 | `/ai/logs` 审计体系中可见 glue 层触发的写操作 | ✅ 已达成 |
| R-4 | EntityResolver 使用只读端点，不直接查询 CRUD | ✅ 已达成 |
| R-5 | INTENT_TO_ACTION_MAP 是显式、可 grep 的映射表 | ✅ 已达成 |

---

## 三、执行任务清单（已完成）

### Phase 1：核心整改（glue/ActionExecutor）

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 1.1 | 创建 INTENT_TO_ACTION_MAP | `glue/core/action_map.py` | ✅ 已完成 |
| 1.2 | 重构 glue/ActionExecutor.execute | `glue/core/executor.py` | ✅ 已完成 |
| 1.3 | 重构 glue/ActionExecutor.preview | `glue/core/executor.py` | ✅ 已完成 |
| 1.4 | 移除 DynamicSkillService 调用 | `glue/core/executor.py` | ✅ 已完成 |

### Phase 2：完善实体解析只读路径

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 2.1 | 创建只读搜索服务 | `app/services/ai/entity_search.py` | ✅ 已完成 |
| 2.2 | 重构 EntityResolver | `glue/core/entity.py` | ✅ 已完成 |
| 2.3 | 移除 CRUD 直接查询 | `glue/core/entity.py` | ✅ 已完成 |

### Phase 3：完善预览和审计流程

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 3.1 | 统一 action_id 生成 | `glue/core/executor.py` | ✅ 已完成 |
| 3.2 | 添加 glue 调用审计标记 | `glue/core/executor.py` | ✅ 已完成 |
| 3.3 | 完善预览渲染 | `glue/core/renderer.py` | ✅ 已完成 |

### Phase 4：清理违规依赖

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 4.1 | 移除 HandlerFactory 引用 | `glue/` 所有文件 | ✅ 已完成 |
| 4.2 | 移除 DynamicSkillService 引用 | `glue/` 所有文件 | ✅ 已完成 |
| 4.3 | 移除违规 CRUD import | `glue/` 所有文件 | ✅ 已完成 |
| 4.4 | 重构 db session 传递 | `glue/api/inbound.py` | ⚠️ 部分合规 |
| 4.5 | 添加违规检测脚本 | `scripts/check_glue_compliance.py` | ✅ 已完成 |

### Phase 5：文档更新

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 5.1 | 补充红线约束 | `AI-GLUE-REQUIREMENTS.md` | ✅ 已完成 |
| 5.2 | 补充只读路径规范 | `AI-GLUE-REQUIREMENTS.md` | ✅ 已完成 |
| 5.3 | 补充显式映射规范 | `AI-GLUE-REQUIREMENTS.md` | ✅ 已完成 |
| 5.4 | 记录架构违规修复 | `AI-GLUE-REQUIREMENTS.md` Section 17 | ✅ 已完成 |

---

## 四、实际实现文件

| 文件 | 说明 |
|------|------|
| `app/glue/core/action_map.py` | INTENT_TO_ACTION_MAP 显式映射 |
| `app/glue/core/executor.py` | 重构为调用 AIActionExecutor |
| `app/glue/core/entity.py` | 重构为使用 EntitySearchService |
| `app/services/ai/entity_search.py` | 只读实体搜索服务 |
| `scripts/check_glue_compliance.py` | 红线约束合规检测脚本 |

---

## 五、合规检测结果

```
✅ glue 层架构合规
   📄 检查文件: 31 个
   
   C-1 ✅ 无 CRUD import
   C-4 ✅ 无 Handler import
   C-DS ✅ 无 DynamicSkillService import
   C-5 ⚠️ executor 持有 db session，但仅传递给 ai/ 层
```

**C-5 设计决策**：
- executor 持有 db session，但仅用于：
  1. 获取 User 对象（传递给 AIActionExecutor）
  2. 传递给 AIActionExecutor（所有写操作在 ai/ 层）
- 不直接调用 CRM CRUD 写操作
- 满足 **Single Writer 原则**

---

## 六、验收清单（已通过）

| # | 验收项 | 标准 | 状态 |
|---|--------|------|------|
| 1 | glue 层无 CRUD 写型 import | `scripts/check_glue_compliance.py` 检测通过 | ✅ |
| 2 | 所有写操作经过 `/ai/actions/` | 查看 `/ai/logs` 审计记录 | ✅ |
| 3 | preview→execute 双步完整 | 用户确认前有预览，确认后才执行 | ✅ |
| 4 | EntityResolver 使用只读端点 | 无 `customer_crud` 等 CRUD import | ✅ |
| 5 | INTENT_TO_ACTION_MAP 可 grep | `grep -r "create-follow-up" glue/` 可见 | ✅ |

---

> **文档版本**：2.0
> **最后更新**：2026-05-26
> **实现状态**：✅ 已完成
> **维护团队**：CRMWolf 开发团队