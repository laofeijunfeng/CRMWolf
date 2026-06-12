---
status: completed
created: 2026-05-26
updated: 2026-05-26
related_requirements: ../requirements/AI-GLUE-ROUTING-ALIGNMENT-RFC.md
related_pr: -
---

# AI GLUE 架构深度整改计划（v0.2 对齐）

> **状态：✅ 已完成** | 完成日期：2026-05-26
> 版本：1.0 | 创建日期：2026-05-26
> 关联需求：用户提供的《优化需求 & 原则（v0.2 对齐版）》
> 核心问题：ActionExecutor 是 CRUD 包装而非入口函数，双份 Preview 违反 Single Source of Truth

---

## 一、当前架构违规诊断

### 1.1 R-1 违规：末级调用是 CRUD

```python
# app/services/ai/action_executor.py:79-88
follow_up = customer_follow_up_crud.create(
    self.db,
    obj_in=follow_up_data,
    customer_id=customer_id,
    ...
)
```

**判定**：末级调用是 `crud.create()`，未经过 `/ai/actions/` 门控（权限、业务校验、幂等锚点）。

### 1.2 R-2 违规：双份 Preview

**位置 1**：`/ai/actions/` 端点
```python
# app/api/ai/actions.py:57-76
if request.preview:
    plan = ActionPlan(
        description=f"为客户 #{request.customer_id} 创建跟进记录",
        changes=[FieldChange(...)],
    )
    return AIResponseBase(action_id=..., status="preview", plan=plan)
```

**位置 2**：glue/executor.py
```python
# app/glue/core/executor.py:321-345
def _build_preview_from_slots(self, intent_type: str, slots: Dict[str, Any]) -> Dict[str, Any]:
    preview = {
        "intent_type": intent_type,
        "params": slots.copy(),
        "changes": [],
    }
    # ... 自建 Preview 逻辑
```

**判定**：两套独立实现，违反 R-2 "Preview 必须是单一 truth"。

### 1.3 R-3 违规：未调用入口函数

```python
# app/glue/core/executor.py:203-210
executor = AIActionExecutor(self.db, user)
result = await self._execute_by_intent(executor, intent_type, pending.slots)
```

glue 直接调用 ActionExecutor（CRUD 包装），未调用 `/ai/actions/` 的入口函数。

---

## 二、整改目标架构

### 2.1 目标：入口函数模式

**定义**：
- **入口函数** = `/ai/actions/` 端点的核心逻辑函数
- **职责** = preview → gate（权限/校验/风险） → execute → audit
- **Contract** = `(params, user_context, preview: bool) → ActionPlan | ExecuteResult`

### 2.2 目标架构图

```
┌─────────────────────────────────────────────────────────────┐
│  glue/core/executor.py                                       │
│  - 不持有 CRUD 引用                                          │
│  - 调用 action_entry.create_follow_up(preview=True/False)   │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼ (进程内调用)
┌─────────────────────────────────────────────────────────────┐
│  /ai/actions/ 入口函数层                                     │
│  - action_entry.py (新建)                                   │
│  - 每个方法：                                                │
│    1. 权限校验                                               │
│    2. 业务校验                                               │
│    3. preview=True → 返回 ActionPlan                        │
│    4. preview=False → 调用 CRUD → 记录审计                   │
│  - 返回：ActionPlan | ExecuteResult                         │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼ (execute 态)
┌─────────────────────────────────────────────────────────────┐
│  CRUD 层                                                     │
│  - 仅在 preview=False 时被入口函数调用                       │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 关键设计决策

**入口函数位置**：
- 方案 A：重构 ActionExecutor 为入口函数（增加 preview/gate 逻辑）
- 方案 B：新建 `action_entry.py` 作为入口函数，ActionExecutor 降级为 CRUD 调用层

**选择方案 B**：
- 原因：入口函数需要清晰的 preview/gate 逻辑，当前 ActionExecutor 职责混乱
- 入口函数职责：preview + gate + audit orchestration
- ActionExecutor 职责：纯 CRUD 调用（被入口函数调用）

---

## 三、执行任务清单

### Phase 1：定义入口函数层

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 1.1 | 创建 action_entry.py | `app/services/ai/action_entry.py` | 入口函数层，preview + gate + audit |
| 1.2 | 定义 ActionEntryResult | `action_entry.py` | 统一返回类型（ActionPlan 或 ExecuteResult） |
| 1.3 | 实现 create_follow_up 入口 | `action_entry.py` | 权限→校验→preview→execute→audit |
| 1.4 | 实现 set_reminder 入口 | `action_entry.py` | 同上 |
| 1.5 | 实现 init_opportunity 入口 | `action_entry.py` | 同上 |
| 1.6 | 实现 update_amount 入口 | `action_entry.py` | 同上 |
| 1.7 | 实现 update_stage 入口 | `action_entry.py` | 同上 |
| 1.8 | 实现 win_opportunity 入口 | `action_entry.py` | 同上（高风险强制确认） |
| 1.9 | 实现 lose_opportunity 入口 | `action_entry.py` | 同上（高风险强制确认） |

### Phase 2：重构 glue/executor.py

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 2.1 | 移除 AIActionExecutor import | `glue/core/executor.py` | 改为 import action_entry |
| 2.2 | 移除 _build_preview_from_slots | `glue/core/executor.py` | **删除第二套 Preview** |
| 2.3 | 重构 preview 方法 | `glue/core/executor.py` | 调用 action_entry(preview=True) |
| 2.4 | 重构 execute 方法 | `glue/core/executor.py` | 调用 action_entry(preview=False) |
| 2.5 | 统一 action_id 生成 | `glue/core/executor.py` | 从入口函数获取，不自建 |

### Phase 3：重构 /ai/actions/ 端点

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 3.1 | 重构 create-follow-up 端点 | `app/api/ai/actions.py` | 调用 action_entry 替代 ActionExecutor |
| 3.2 | 重构其他端点 | `app/api/ai/actions.py` | 同上 |
| 3.3 | 移除端点的 preview 逻辑 | `app/api/ai/actions.py` | preview 逻辑移至 action_entry |

### Phase 4：重构 ActionExecutor

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 4.1 | 降级为 CRUD 调用层 | `app/services/ai/action_executor.py` | 移除审计日志（由 action_entry 负责） |
| 4.2 | 移除 _log_ai_action | `action_executor.py` | 审计职责上移 |
| 4.3 | 保持 CRUD 调用职责 | `action_executor.py` | 仅被 action_entry 调用 |

### Phase 5：合规检测更新

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 5.1 | 更新 C-1 检测规则 | `scripts/check_glue_compliance.py` | 检测 glue 是否 import ActionExecutor |
| 5.2 | 新增 C-PREVIEW 检测规则 | `check_glue_compliance.py` | 检测 glue 是否有自建 Preview 逻辑 |
| 5.3 | 新增末级调用检测 | `check_glue_compliance.py` | 追踪 glue → action_entry → CRUD 路径 |

### Phase 6：文档更新

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 6.1 | 更新 AI-GLUE-REQUIREMENTS.md | `CRM-Docs/requirements/` | 补充 R-1~R-5 验收标准 |
| 6.2 | 更新架构图 | 各文档 | 反映入口函数架构 |

---

## 四、入口函数设计详细说明

### 4.1 action_entry.py 核心结构

```python
"""AI Actions 入口函数层

职责：
1. 权限校验（当前用户能否对该实体做该操作）
2. 业务校验（阶段流合法性、字段约束、必填语义）
3. Preview 构造（单一 truth）
4. Execute 执行（调用 CRUD）
5. 审计留痕（source="ai"、action_id）

Contract: (params, user_context, preview: bool) → ActionEntryResult
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.ai import ActionPlan, FieldChange, generate_action_id
from app.services.ai.action_executor import ActionExecutor  # 仅在 execute 时调用
from app.services.operation_log_service import operation_log_service


@dataclass
class ActionEntryResult:
    """入口函数统一返回类型"""
    action_id: str
    status: str  # "preview" | "completed" | "failed"
    plan: Optional[ActionPlan] = None  # preview 态
    data: Optional[Dict[str, Any]] = None  # execute 态
    error: Optional[str] = None
    requires_confirmation: bool = False


class ActionEntry:
    """入口函数层"""
    
    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user
        self.executor = ActionExecutor(db, user)  # CRUD 调用层
    
    def create_follow_up(
        self,
        customer_id: int,
        content: str,
        follow_up_time: Optional[datetime] = None,
        method: Optional[str] = "电话",
        next_action: Optional[str] = None,
        opportunity_id: Optional[int] = None,
        preview: bool = True,
        action_id: Optional[str] = None,
    ) -> ActionEntryResult:
        """创建跟进入口函数
        
        流程：
        1. 权限校验：用户是否有该客户的操作权限
        2. 业务校验：客户是否存在
        3. preview=True → 返回 ActionPlan
        4. preview=False → 调用 CRUD → 记录审计
        """
        # Step 1: 权限校验
        customer = self._check_customer_permission(customer_id)
        if not customer:
            return ActionEntryResult(
                action_id=action_id or generate_action_id(),
                status="failed",
                error=f"无权限或客户 {customer_id} 不存在",
            )
        
        # Step 2: 生成 action_id
        action_id = action_id or generate_action_id()
        
        # Step 3: Preview 态
        if preview:
            plan = ActionPlan(
                description=f"为客户 #{customer_id} 创建跟进记录",
                changes=[
                    FieldChange(field="content", to_value=content),
                    FieldChange(field="method", to_value=method),
                    FieldChange(field="follow_up_time", to_value=follow_up_time.isoformat() if follow_up_time else None),
                ],
                entity_type="FollowUp",
            )
            return ActionEntryResult(
                action_id=action_id,
                status="preview",
                plan=plan,
                requires_confirmation=False,  # LOW 风险
            )
        
        # Step 4: Execute 态
        try:
            follow_up = self.executor.create_follow_up(
                customer_id=customer_id,
                content=content,
                follow_up_time=follow_up_time,
                method=method,
                next_action=next_action,
                opportunity_id=opportunity_id,
            )
            
            # Step 5: 审计留痕（由入口函数统一负责）
            self._log_action(
                action_id=action_id,
                action_type="create_follow_up",
                resource_type="CUSTOMER",
                resource_id=customer_id,
                secondary_resource_type="FOLLOW_UP",
                secondary_resource_id=follow_up.id,
                content={
                    "followUpContent": content,
                    "customerId": customer_id,
                    "source": "ai",
                    "action_id": action_id,
                },
            )
            
            return ActionEntryResult(
                action_id=action_id,
                status="completed",
                data={
                    "follow_up_id": follow_up.id,
                    "customer_id": customer_id,
                    "content": content,
                },
            )
        except ValueError as e:
            return ActionEntryResult(
                action_id=action_id,
                status="failed",
                error=str(e),
            )
    
    def _check_customer_permission(self, customer_id: int) -> Optional[Customer]:
        """权限校验：用户是否有该客户的操作权限"""
        from app.crud.customer import customer_crud
        customer = customer_crud.get_by_id(self.db, customer_id)
        if not customer:
            return None
        if customer.team_id != self.user.team_id:
            return None  # 租户隔离
        return customer
    
    def _log_action(self, action_id: str, ...):
        """统一审计入口"""
        content["action_id"] = action_id
        content["source"] = "ai"
        operation_log_service.log(...)
```

### 4.2 glue/executor.py 重构后

```python
"""ActionExecutor（合规版）

不再持有 CRUD 引用，不再自建 Preview。
调用 action_entry 入口函数，遵守 Single Writer 原则。
"""

from app.services.ai.action_entry import ActionEntry, ActionEntryResult


class ActionExecutor:
    """动作执行器（合规版）
    
    调用入口函数，不自建 Preview，不直接调用 CRUD。
    """
    
    async def preview(self, pending: PendingAction) -> PreviewResult:
        """生成预览
        
        调用 action_entry(preview=True)，返回单一 truth 的 ActionPlan。
        """
        # 获取用户
        user = self._get_user()
        if not user:
            return PreviewResult(success=False, error="user_not_found")
        
        # 获取入口函数
        entry = ActionEntry(self.db, user)
        
        # 调用入口函数的 preview 态
        result = entry.create_follow_up(
            customer_id=pending.slots.get("customer_id"),
            content=pending.slots.get("content"),
            preview=True,  # ← Preview 态
        )
        
        # 渲染 ActionPlan 为对话文本
        if result.status == "preview":
            return PreviewResult(
                success=True,
                action_id=result.action_id,
                preview_data=result.plan.model_dump(),
                requires_confirmation=result.requires_confirmation,
            )
    
    async def execute(
        self,
        pending: PendingAction,
        action_id: str,  # ← 从 preview 继承的 action_id
    ) -> ExecutionResult:
        """执行动作
        
        调用 action_entry(preview=False)，使用同一 action_id。
        """
        user = self._get_user()
        entry = ActionEntry(self.db, user)
        
        # 调用入口函数的 execute 态
        result = entry.create_follow_up(
            customer_id=pending.slots.get("customer_id"),
            content=pending.slots.get("content"),
            preview=False,  # ← Execute 态
            action_id=action_id,  # ← 绑定同一 action_id
        )
        
        if result.status == "completed":
            return ExecutionResult(
                success=True,
                action_id=result.action_id,
                data=result.data,
            )
```

---

## 五、验收清单

| # | 验收项 | 验收方法 | 状态 |
|---|--------|---------|------|
| 1 | glue 不 import ActionExecutor | `grep -rn "from app.services.ai.action_executor" app/glue/` | 待验证 |
| 2 | glue 不自建 Preview 逻辑 | `grep -rn "_build_preview" app/glue/` | 待验证 |
| 3 | glue 末级调用是 action_entry | 代码追踪：glue → action_entry → CRUD | 待验证 |
| 4 | Preview 单一 truth | `/ai/actions/` 和 glue 使用同一入口函数 | 待验证 |
| 5 | action_id 绑定 preview→execute | 同一 action_id 在两态可见 | 待验证 |
| 6 | 审计在 `/ai/logs` 可归因 | `event_type=WRITE` + `action_id` | 待验证 |

---

## 六、风险评估

| 风险 | 影响 | 对策 |
|------|------|------|
| 入口函数重构工作量 | 7 个 action 需要重构 | 逐个迁移，优先高频 action |
| ActionExecutor 降级影响 | 需要修改调用点 | 只有 `/ai/actions/` 和新 action_entry 调用 |
| glue preview 流程变化 | 需要测试完整流程 | 单元测试 + 集成测试 |

---

> **文档版本**：1.0
> **最后更新**：2026-05-26
> **状态**：待审批
> **维护团队**：CRMWolf 开发团队