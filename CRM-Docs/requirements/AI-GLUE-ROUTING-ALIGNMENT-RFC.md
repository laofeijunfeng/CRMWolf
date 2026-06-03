# AI GLUE 路由对齐 RFC

> 版本：1.0 | 创建日期：2026-05-26 | 状态：**提案**
> 目标：修复 glue 层违规调用，建立合规路由架构

---

## 一、问题诊断

### 当前架构（违规）

```
glue/ActionExecutor (app/glue/core/executor.py:178)
  → DynamicSkillService.execute_action (app/services/skills/dynamic_skill_service.py:138)
  → HandlerFactory.execute_handler (app/services/skills/handlers/handler_factory.py:100)
  → Handler.execute (如 StageAdvanceHandler:148)
  → CRUD 直接写 (如 opportunity_crud.move_to_stage)
```

**违规点**：绕过 `/ai/actions/` 的 preview→execute 双步轨道，直接调用 CRUD。

### 源码证据

**glue/core/executor.py:178**：
```python
result = await dynamic_skill_service.execute_action(
    db=self.db,
    skill_name=skill_name,
    action_name=action_name,
    params=pending.slots,
    user_id=self.user_id,
)
```

**handlers/stage_advance_handler.py:148-153**：
```python
from app.crud.opportunity import opportunity_crud
updated = opportunity_crud.move_to_stage(
    db, opportunity.id, target_stage.id, str(user.id)
)
```

---

## 二、核心原则

| 原则 | 说明 |
|------|------|
| **单一写入者** | 所有写操作只在 `/ai/actions/` 层，glue 只是编排，不直接写 |
| **分层信任边界** | Layer Boundary = Trust Boundary，glue 层不可突破 |
| **Preview-Before-Write** | 所有操作 preview→confirm→execute，不可跳过 |
| **显式映射 > 隐式分发** | INTENT_TO_ACTION_MAP 必须显式、可 grep |
| **最小权限 + 审计设计** | glue 层只知道必要的 user_id + tenant_id，不持有 db session |

---

## 三、需求规格

| 需求 ID | 需求 | 说明 |
|---------|------|------|
| **R-1** | 对话驱动写操作必须通过 `/ai/actions/` | glue 层所有写操作必须调用 `/ai/actions/` 端点 |
| **R-2** | preview→确认双步轨道不可省略 | 所有写操作必须 preview=true → 确认 → preview=false |
| **R-3** | 审计可追溯性 | `/ai/logs` 中可见 glue 层触发的写操作，包含 source="glue" 标记 |
| **R-4** | 实体解析只读路径 | EntityResolver 只使用只读端点，不直接查询 CRUD |
| **R-5** | 意图→动作映射必须可审查 | INTENT_TO_ACTION_MAP 是显式映射表，可 grep 检查 |

---

## 四、红线约束

| 约束 ID | 约束 | 检测方式 |
|---------|------|---------|
| **C-1** | `glue/` 不得 import CRM Core 写型 CRUD | `grep -r "from app.crud import" glue/` |
| **C-2** | 不得跳过 preview | `/ai/logs` 检查每个 action_id 必有 preview=true 先于 preview=false |
| **C-3** | `glue/` 不得成为 CRM 业务规则第二实现地 | glue 层不应包含业务规则逻辑 |
| **C-4** | 不得 Handler 被 glue 直接 execute() | `grep -r "from app.services.skills.handlers import" glue/` |
| **C-5** | 不得把 db session 传给胶水层 | `grep -r "self.db" glue/core/executor.py` |

---

## 五、验收标准

| 标准 | 说明 |
|------|------|
| 所有写操作经过 `/ai/actions/` | `/ai/logs` 可见所有 glue 触发的写操作 |
| Preview 强制执行 | preview=true → 确认 → preview=false 双步完整 |
| 审计可见 | source="glue" 标记在 `/ai/logs` 中可查询 |
| 实体解析只读 | EntityResolver 无 CRUD import |
| 映射可审查 | INTENT_TO_ACTION_MAP 可 grep |

---

## 六、预期成果

1. **架构合规**：glue 层不再直接调用 DynamicSkillService → Handler → CRUD
2. **审计完整**：所有写操作在 `/ai/logs` 中可追溯
3. **最小权限**：glue 层只持有 user_id + tenant_id，不持有 db session
4. **显式映射**：意图→动作映射表显式可见，可 grep 检查

---

> **文档版本**：1.0
> **创建日期**：2026-05-26
> **维护团队**：CRMWolf 开发团队