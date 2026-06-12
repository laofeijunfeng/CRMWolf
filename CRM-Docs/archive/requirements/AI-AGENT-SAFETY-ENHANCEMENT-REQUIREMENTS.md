---
status: completed
created: 2026-06-10
updated: 2026-06-10
related_plan: ../plans/AI-AGENT-SAFETY-ENHANCEMENT-PLAN.md
related_pr: -
---

# 需求文档：Agent 交互安全与决策增强规范

> **状态：✅ 已实现** | 完成日期：2026-06-10

| 文档版本 | V 3.1 |
| :--- | :--- |
| **项目名称** | CRM 智能流程推进 Agent |
| **关键词** | Human-in-the-loop, 决策透明度, 数据安全, 撤销机制, 歧义消解 |
| **更新日期** | 2026-06-10 |

---

## 一、需求背景 (Context & Problem Statement)

### 1.1 现状
基于 V3.0 的实施成果，系统已具备：
- **Workflow Orchestrator**：硬编码业务流程（赢单、转化）
- **ReAct 循环**：AI 自主判断多轮操作
- **Control Plane**：Redis Session、Guardrails、TraceId、资源隔离
- **Handler 系统**：17+ 业务工具

核心流程已通过状态机和业务不变式保证刚性，系统处于上线前的验证阶段。

### 1.2 核心挑战

在灰度测试前夕，发现两个系统性风险：

#### 风险 1：数据污染风险（隐式操作）

**现状**：Workflow 中 `type: tool` 的步骤默认自动执行。

```python
# 当前 Workflow 定义
{
    "id": "create_follow_up",
    "type": "tool",          # ← 自动执行，无确认
    "tool_name": "follow_up_customer",
}
```

**问题**：
- AI 实体识别存在误判率（如"客户A"误认为"客户B"）
- 自动执行会将错误信息写入 CRM 核心数据库
- 数据清洗成本极高且难以追溯
- 无撤销入口，用户无法补救误操作

**影响评估**：
| 误判场景 | 污染类型 | 清洗成本 |
|----------|----------|----------|
| 实体识别错误 | 跟进记录归属错误 | 需人工逐条修正 |
| 参数提取错误 | 跟进内容错误 | 需用户自行修改 |
| 意图识别错误 | 操作类型错误 | 需管理员介入 |

#### 风险 2：决策信息不足（歧义处理）

**现状**：多商机选择仅展示名称。

```
当前展示：
- 商机A (ID: 123)
- 商机B (ID: 456)

用户困惑：哪个是刚才跟进的？金额多少？阶段如何？
```

**问题**：
- 缺乏区分度高的信息（金额、阶段、更新时间）
- 用户需要在上下文切换中回忆细节
- 增加认知负担和操作失误概率

### 1.3 解决思路

通过系统层面引入：
- **显式确认机制**：所有写操作必须确认
- **撤销即服务**：短时间内可回滚误操作
- **增强型上下文**：展示完整决策辅助信息
- **渐进式自动化**：根据准确率逐步放开权限

---

## 二、核心原则 (Core Principles)

### 2.1 零信任执行原则 (Zero-Trust Execution)

**默认拒绝，显式批准。**

#### 风险分层定义

| 操作类型 | 风险等级 | 灰度期策略 | 稳定后策略 |
|----------|---------|-----------|-----------|
| **查询（Read）** | 低 | 自动执行 | 自动执行 |
| **创建跟进记录** | 中 | ⚠️ 待确认 | 待确认（阈值监控） |
| **赢单/输单** | 高 | ❌ 必须确认 | 必须确认 |
| **线索转化** | 高 | ❌ 必须确认 | 必须确认 |
| **创建商机** | 高 | ❌ 必须确认 | 必须确认 |
| **创建合同** | 高 | ❌ 必须确认 | 必须确认 |

#### 自动化权限开放条件

满足以下条件方可调整为自动执行：
1. **样本量**：至少 1000 次成功执行
2. **准确率**：用户撤销率 < 0.1%
3. **参数准确率**：用户修改率 < 0.5%
4. **人工复核**：至少 10% 样本经人工验证无误
5. **业务评审**：经业务负责人审批

### 2.2 决策透明原则 (Decision Transparency)

**AI 必须展示"思考依据"，而非仅展示"结论"。**

#### 证据链可视化

确认卡片必须展示：
```
即将执行：创建跟进记录

实体信息：
- 客户：张三科技（ID: 123）
- 来源：客户详情页上下文

操作参数：
- 跟进方式：微信
- 跟进内容：客户反馈产品适用，确认采购
- 下次跟进：3天后

[取消] [修改参数] [确认执行]
```

#### 上下文完整性

多实体选择必须展示：

| 字段 | 商机A | 商机B |
|------|-------|-------|
| 名称 | XX软件采购 | YY系统升级 |
| **金额** | 50万 | 120万 |
| **阶段** | 需求确认 | 商务谈判 |
| **赢率** | 60% | 30% |
| **更新时间** | 2026-06-09 | 2026-06-05 |

### 2.3 最小干扰原则 (Minimal Interruption)

**确认是为了安全，而非阻碍。**

#### 智能降噪策略

| 操作 | 策略 | 理由 |
|------|------|------|
| 只读查询 | 自动执行 | 无数据污染风险 |
| 标签操作 | 待确认（简化版） | 低风险但需感知 |
| 多步流程 | 批量确认 | 减少弹窗次数 |

#### 批量确认设计

一次流程涉及多个连续操作时：
```
即将执行 3 个操作：

1. ✅ 创建跟进记录（低风险）
2. ⚠️ 推进商机到"商务谈判"阶段（中风险）
3. ❌ 标记赢单（高风险）

[全部确认] [逐个确认] [取消]
```

### 2.4 可恢复性原则 (Recoverability)

**任何操作必须可撤销。**

#### 撤销窗口

| 操作类型 | 撤销窗口 | 撤销范围 |
|----------|---------|----------|
| 创建跟进记录 | 10秒 | 单步撤销 |
| 赢单 | 30秒 | 流程撤销（含跟进） |
| 线索转化 | 60秒 | 流程撤销（含客户+商机） |

#### 撤销入口

1. **即时撤销**：确认后的 Toast 弹窗提供撤销按钮
2. **历史撤销**：操作记录列表提供撤销入口
3. **批量撤销**：支持撤销整个 Workflow 流程

---

## 三、技术方案 (Technical Design)

### 3.1 显式确认机制

#### 3.1.1 Workflow 步骤状态扩展

```python
# 扩展步骤类型
class StepType(Enum):
    TOOL = "tool"                    # 工具执行
    ASK_USER = "ask_user"            # 用户询问
    DECISION = "decision"            # 条件判断
    TOOL_PENDING = "tool_pending"    # 工具待确认（新增）

# 步骤配置扩展
{
    "id": "create_follow_up",
    "type": "tool",
    "tool_name": "follow_up_customer",
    "require_confirmation": True,     # 新增：是否需要确认
    "confirmation_config": {          # 新增：确认配置
        "ttl": 10,                    # 撤销窗口（秒）
        "allow_param_edit": True,     # 是否允许参数修改
        "risk_level": "medium",       # 风险等级
    },
    "undo_support": True,             # 新增：是否支持撤销
}
```

#### 3.1.2 执行状态机扩展

```python
# 步骤执行状态
class StepExecutionStatus(Enum):
    PENDING = "pending"               # 待执行
    WAITING_CONFIRMATION = "waiting_confirmation"  # 待确认（新增）
    CONFIRMED = "confirmed"           # 已确认（新增）
    EXECUTING = "executing"           # 执行中
    SUCCESS = "success"               # 成功
    FAILED = "failed"                 # 失败
    UNDO_AVAILABLE = "undo_available" # 可撤销（新增）
    UNDONE = "undone"                 # 已撤销（新增）

# 状态流转
PENDING → WAITING_CONFIRMATION → CONFIRMED → EXECUTING → SUCCESS → UNDO_AVAILABLE → UNDONE
                                    ↑______________|
                                    (用户取消或修改参数)
```

#### 3.1.3 SSE 事件扩展

```typescript
// 新增事件类型
interface SSEEvent {
  event: 'pending_confirmation' | 'undo_available' | 'undo_expired' | ...
  
  // pending_confirmation 事件结构
  pending_confirmation: {
    step_id: string
    tool_name: string
    risk_level: 'low' | 'medium' | 'high'
    
    // 展示信息
    display: {
      title: string              // "创建跟进记录"
      entity_info: {...}         // 实体信息
      params: {...}              // 操作参数
      evidence_chain: {...}      // 证据链
    }
    
    // 操作选项
    actions: {
      can_cancel: boolean
      can_edit_params: boolean
      can_confirm: boolean
    }
    
    // 撤销配置
    undo_config: {
      ttl: number                // 撤销窗口
      undo_scope: 'single' | 'workflow'
    }
  }
  
  // undo_available 事件结构
  undo_available: {
    step_id: string
    undo_ttl: number             // 剩余撤销时间
    undo_endpoint: string        // 撤销 API
  }
}
```

### 3.2 撤销机制设计

#### 3.2.1 操作日志扩展

```python
# OperationLog 表扩展
class OperationLog(Base):
    id: int
    event_type: str               # 操作类型
    event_action: str             # 动作（CREATE/UPDATE/DELETE）
    resource_type: str            # 资源类型
    resource_id: int              # 资源ID
    
    # 新增字段
    undoable: bool                # 是否可撤销
    undo_ttl: int                 # 撤销窗口（秒）
    undo_deadline: datetime       # 撤销截止时间
    undone: bool                  # 是否已撤销
    undo_by: int                  # 撤销操作人
    undo_at: datetime             # 撤销时间
    
    # 关联信息（用于流程撤销）
    workflow_session_id: str      # Workflow Session ID
    step_id: str                  # 步骤ID
    parent_operation_id: int      # 父操作ID（用于级联撤销）
    
    # 快照数据（用于恢复）
    before_snapshot: JSON         # 操作前状态快照
    after_snapshot: JSON          # 操作后状态快照
```

#### 3.2.2 Undo Service 设计

```python
# app/services/workflow/undo_service.py

class UndoService:
    """撤销服务"""
    
    def can_undo(self, operation_id: int) -> bool:
        """检查是否可撤销"""
        log = operation_log_crud.get_by_id(operation_id)
        if not log:
            return False
        
        return (
            log.undoable and
            not log.undone and
            datetime.now() < log.undo_deadline
        )
    
    def undo_single(self, operation_id: int, user_id: int) -> UndoResult:
        """单步撤销"""
        # 1. 验证可撤销
        if not self.can_undo(operation_id):
            return UndoResult(success=False, reason="撤销窗口已过期")
        
        # 2. 根据操作类型执行撤销
        log = operation_log_crud.get_by_id(operation_id)
        undo_handler = self._get_undo_handler(log.event_type)
        
        result = undo_handler.undo(log)
        
        # 3. 更新日志状态
        operation_log_crud.update(log.id, {
            "undone": True,
            "undo_by": user_id,
            "undo_at": datetime.now()
        })
        
        return result
    
    def undo_workflow(self, session_id: str, user_id: int) -> UndoResult:
        """流程级撤销"""
        # 1. 获取流程所有操作
        operations = operation_log_crud.get_by_workflow_session(session_id)
        
        # 2. 按时间倒序撤销
        for op in reversed(operations):
            if self.can_undo(op.id):
                self.undo_single(op.id, user_id)
        
        return UndoResult(success=True, undone_count=len(operations))
    
    def _get_undo_handler(self, event_type: str) -> UndoHandler:
        """获取撤销处理器"""
        handlers = {
            "FOLLOW_UP_CREATED": FollowUpUndoHandler,
            "OPPORTUNITY_WON": OpportunityWinUndoHandler,
            "OPPORTUNITY_STAGE_CHANGED": OpportunityStageUndoHandler,
            "LEAD_CONVERTED": LeadConvertUndoHandler,
            "CONTRACT_CREATED": ContractUndoHandler,
            ...
        }
        return handlers.get(event_type, DefaultUndoHandler)
```

#### 3.2.3 撤销处理器设计

```python
# app/services/workflow/undo_handlers.py

class UndoHandler(ABC):
    """撤销处理器基类"""
    
    @abstractmethod
    def undo(self, log: OperationLog) -> UndoResult:
        """执行撤销"""
        pass
    
    @abstractmethod
    def get_undo_impact(self, log: OperationLog) -> List[UndoImpact]:
        """获取撤销影响范围"""
        pass

class FollowUpUndoHandler(UndoHandler):
    """跟进记录撤销"""
    
    def undo(self, log: OperationLog) -> UndoResult:
        """软删除跟进记录"""
        from app.crud.lead_follow_up import lead_follow_up_crud
        from app.crud.customer_follow_up import customer_follow_up_crud
        
        # 根据资源类型选择 CRUD
        if log.resource_type == "LEAD_FOLLOW_UP":
            crud = lead_follow_up_crud
        else:
            crud = customer_follow_up_crud
        
        # 软删除
        crud.soft_delete(log.resource_id)
        
        return UndoResult(
            success=True,
            message="跟进记录已撤销",
            impact=[UndoImpact(
                type="soft_delete",
                resource_type=log.resource_type,
                resource_id=log.resource_id
            )]
        )

class OpportunityWinUndoHandler(UndoHandler):
    """赢单撤销"""
    
    def undo(self, log: OperationLog) -> UndoResult:
        """恢复商机状态"""
        from app.crud.opportunity import opportunity_crud
        from app.models.opportunity import OpportunityStatus
        
        # 1. 恢复商机状态
        before = log.before_snapshot
        opportunity_crud.update(log.resource_id, {
            "status": OpportunityStatus.FOLLOWING.value,
            "win_probability": before["win_probability"],
            "actual_amount": None,
            "actual_closing_date": None
        })
        
        # 2. 恢复阶段快照（如果有）
        if "stage_snapshot_id" in before:
            # 删除新创建的快照，恢复旧快照
            ...
        
        return UndoResult(
            success=True,
            message="赢单已撤销，商机恢复跟进状态",
            impact=[
                UndoImpact(type="status_revert", ...),
                UndoImpact(type="stage_revert", ...)
            ]
        )

class LeadConvertUndoHandler(UndoHandler):
    """线索转化撤销"""
    
    def undo(self, log: OperationLog) -> UndoResult:
        """撤销客户创建 + 商机创建"""
        # 1. 恢复线索状态
        ...
        
        # 2. 删除创建的客户（如果无其他关联）
        ...
        
        # 3. 删除创建的商机
        ...
        
        return UndoResult(success=True, ...)
```

#### 3.2.4 Undo API 设计

```python
# app/api/workflow.py

@router.post("/undo/{operation_id}")
async def undo_operation(
    operation_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """撤销单步操作"""
    undo_service = UndoService()
    result = undo_service.undo_single(operation_id, user_id)
    
    if result.success:
        return {"success": True, "message": result.message}
    else:
        return {"success": False, "reason": result.reason}

@router.post("/undo/workflow/{session_id}")
async def undo_workflow(
    session_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """撤销整个流程"""
    undo_service = UndoService()
    result = undo_service.undo_workflow(session_id, user_id)
    
    return {
        "success": True,
        "undone_count": result.undone_count,
        "message": f"已撤销 {result.undone_count} 个操作"
    }

@router.get("/undo/status/{operation_id}")
async def get_undo_status(
    operation_id: int,
    db: Session = Depends(get_db)
):
    """获取撤销状态"""
    undo_service = UndoService()
    can_undo = undo_service.can_undo(operation_id)
    
    if can_undo:
        log = operation_log_crud.get_by_id(operation_id)
        ttl = (log.undo_deadline - datetime.now()).seconds
        return {
            "can_undo": True,
            "ttl": ttl,
            "undo_endpoint": f"/undo/{operation_id}"
        }
    else:
        return {"can_undo": False}
```

### 3.3 增强型歧义消解

#### 3.3.1 EntityRenderer 服务设计

```python
# app/services/workflow/entity_renderer.py

class EntityRenderer:
    """实体展示数据渲染服务"""
    
    # 实体展示配置
    DISPLAY_CONFIGS = {
        "opportunity": {
            "name_field": "opportunity_name",
            "key_fields": [
                {"field": "total_amount", "label": "金额", "format": "currency"},
                {"field": "current_stage_name", "label": "阶段"},
                {"field": "win_probability", "label": "赢率", "format": "percent"},
                {"field": "updated_at", "label": "更新时间", "format": "datetime"},
            ],
            "sort_by": "updated_at",
            "sort_order": "desc"
        },
        "customer": {
            "name_field": "account_name",
            "key_fields": [
                {"field": "industry", "label": "行业"},
                {"field": "status", "label": "状态", "format": "enum"},
                {"field": "updated_at", "label": "更新时间", "format": "datetime"},
            ],
            "sort_by": "updated_at",
            "sort_order": "desc"
        },
        "lead": {
            "name_field": "lead_name",
            "key_fields": [
                {"field": "source", "label": "来源", "format": "enum"},
                {"field": "status", "label": "状态", "format": "enum"},
                {"field": "created_at", "label": "创建时间", "format": "datetime"},
            ],
            "sort_by": "created_at",
            "sort_order": "desc"
        },
        "contract": {
            "name_field": "contract_name",
            "key_fields": [
                {"field": "contract_amount", "label": "金额", "format": "currency"},
                {"field": "status", "label": "状态", "format": "enum"},
                {"field": "signed_date", "label": "签约日期", "format": "datetime"},
            ],
            "sort_by": "signed_date",
            "sort_order": "desc"
        }
    }
    
    def render_for_selection(
        self,
        entity_type: str,
        entities: List[Any],
        context: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """渲染实体选择列表"""
        config = self.DISPLAY_CONFIGS.get(entity_type)
        if not config:
            return self._render_default(entities)
        
        rendered = []
        for entity in entities:
            item = {
                "id": entity.id,
                "name": getattr(entity, config["name_field"]),
                "fields": {}
            }
            
            # 渲染关键字段
            for field_config in config["key_fields"]:
                field_name = field_config["field"]
                value = getattr(entity, field_name, None)
                
                # 格式化
                formatted_value = self._format_value(
                    value, field_config.get("format"), field_config
                )
                
                item["fields"][field_config["label"]] = formatted_value
            
            # 添加上下文相关性分数
            if context:
                item["relevance_score"] = self._calculate_relevance(entity, context)
            
            rendered.append(item)
        
        # 排序
        if config["sort_by"]:
            rendered.sort(
                key=lambda x: getattr(
                    entities[rendered.index(x)], config["sort_by"]
                ) or datetime.min,
                reverse=(config["sort_order"] == "desc")
            )
        
        return rendered
    
    def _format_value(self, value: Any, format_type: str, config: Dict) -> str:
        """格式化值"""
        if value is None:
            return "未知"
        
        if format_type == "currency":
            return f"{value}万" if value else "未知"
        elif format_type == "percent":
            return f"{value}%"
        elif format_type == "datetime":
            return value.strftime("%Y-%m-%d") if hasattr(value, 'strftime') else str(value)
        elif format_type == "enum":
            # 获取枚举显示名称
            return self._get_enum_display(value, config["field"])
        else:
            return str(value)
    
    def _calculate_relevance(self, entity: Any, context: Dict) -> float:
        """计算与上下文的相关性分数"""
        # 1. 名称相似度
        # 2. 时间接近度
        # 3. 状态匹配度
        ...
        return 0.8  # 示例
```

#### 3.3.2 ask_user 步骤配置扩展

```python
# Workflow 步骤配置扩展
{
    "id": "ask_select_opportunity",
    "type": "ask_user",
    "description": "选择商机（多个商机时）",
    
    # 新增：实体展示配置
    "entity_display": {
        "entity_type": "opportunity",
        "use_renderer": True,          # 使用 EntityRenderer
        "custom_fields": [             # 可选：自定义字段
            {"field": "product_name", "label": "产品"},
        ],
        "sort_by": "relevance_score",  # 按相关性排序
    },
    
    # 原配置
    "question_template": "客户有多个跟进中商机，请选择确认采购的是哪个？",
    "options_template": lambda session: [
        # 自动填充展示数据
        entity_renderer.render_for_selection(
            "opportunity",
            session.get("opportunities", [])
        )
    ],
}
```

#### 3.3.3 SSE 事件数据扩展

```typescript
// waiting_for_user 事件扩展
interface WaitingForUserEvent {
  event: 'waiting_for_user'
  
  // 选择列表数据
  options: Array<{
    id: number
    name: string
    fields: Record<string, string>    // 关键字段
    
    // 展示格式
    display: string                   // "商机A | 金额:50万 | 阶段:需求确认"
    detail: string                    // 详情文本
  }>
  
  // 排序信息
  sort_info: {
    by: string                        // 排序字段
    order: 'asc' | 'desc'
  }
}
```

### 3.4 与现有系统集成

#### 3.4.1 与 Guardrails 的关系

```python
# 两道防线协同

# 第一道防线：Guardrails（置信度拦截）
if confidence < 0.70:
    return "拒绝执行，要求用户明确指令"
elif confidence < 0.95:
    # 进入显式确认
    pass
else:
    # 高置信度仍需确认（灰度期）
    pass

# 第二道防线：显式确认（所有写操作）
if operation_type in [CREATE, UPDATE, DELETE]:
    return pending_confirmation_event
```

#### 3.4.2 与 Operation Log 的关系

```python
# Handler 执行时自动记录
class BaseHandler:
    def handle(self, db, params, user_id):
        # 1. 执行前记录快照
        before_snapshot = self._capture_snapshot(entity)
        
        # 2. 执行操作
        result = self._execute(db, params, user_id)
        
        # 3. 记录操作日志（含撤销配置）
        operation_log_service.log(
            db=db,
            event_type=self.get_event_type(),
            event_action=self.get_event_action(),
            resource_type=self.get_resource_type(),
            resource_id=result.get("entity_id"),
            undoable=True,
            undo_ttl=self.get_undo_ttl(),
            undo_deadline=datetime.now() + timedelta(seconds=self.get_undo_ttl()),
            workflow_session_id=params.get("session_id"),
            step_id=params.get("step_id"),
            before_snapshot=before_snapshot,
            after_snapshot=self._capture_snapshot(entity),
            operator_id=user_id
        )
        
        return result
```

---

## 四、需求清单 (Requirements)

### 4.1 显性确认机制

| ID | 需求 | 优先级 | 验收标准 |
|----|------|--------|----------|
| REQ-01 | 所有写操作（Create/Update/Delete）步骤默认状态为 `pending_confirmation` | P0 | 灰度期所有写操作都需要确认 |
| REQ-02 | 前端渲染标准化确认卡片，展示操作详情、实体信息、参数 | P0 | 用户明确知道即将执行什么操作 |
| REQ-03 | 确认卡片支持参数修改功能 | P1 | 用户可在确认前调整参数 |
| REQ-04 | 确认卡片展示证据链（实体来源、识别依据） | P1 | 用户了解 AI 如何识别实体 |
| REQ-05 | 按风险等级分层显示确认卡片样式 | P1 | 高风险操作用醒目样式 |

### 4.2 撤销机制

| ID | 需求 | 优先级 | 验收标准 |
|----|------|--------|----------|
| REQ-06 | 提供单步撤销接口，支持在 TTL 内回滚操作 | P0 | 用户可在撤销窗口内一键撤销 |
| REQ-07 | 提供流程级撤销，支持回滚整个 Workflow | P0 | 用户可撤销整个流程 |
| REQ-08 | 撤销操作记录到 Operation Log | P0 | 撤销操作可追溯 |
| REQ-09 | 撤销窗口按风险等级分层（10秒/30秒/60秒） | P1 | 高风险操作有更长撤销时间 |
| REQ-10 | 前端在确认后显示撤销 Toast（带倒计时） | P1 | 用户清楚撤销窗口剩余时间 |
| REQ-11 | Handler 执行前自动记录快照 | P0 | 撤销可恢复到操作前状态 |

### 4.3 增强型歧义消解

| ID | 需求 | 优先级 | 验收标准 |
|----|------|--------|----------|
| REQ-12 | EntityRenderer 服务提供标准化的实体展示数据 | P0 | 所有实体选择使用统一展示格式 |
| REQ-13 | 商机选择展示：名称、金额、阶段、赢率、更新时间 | P0 | 用户无需切换上下文即可判断 |
| REQ-14 | 客户选择展示：名称、行业、状态、更新时间 | P0 | 同 REQ-13 |
| REQ-15 | 选项按相关性或时间倒序排列 | P1 | 最相关选项出现在顶部 |
| REQ-16 | 支持上下文相关性评分 | P2 | AI 可根据上下文计算相关性 |

### 4.4 与现有系统集成

| ID | 需求 | 优先级 | 验收标准 |
|----|------|--------|----------|
| REQ-17 | 撤销机制与 Operation Log 集成 | P0 | Handler 自动记录撤销日志 |
| REQ-18 | 显式确认与 Guardrails 协同 | P0 | 两道防线正确协同 |
| REQ-19 | Workflow 步骤配置支持 `require_confirmation` | P0 | 可配置哪些步骤需要确认 |
| REQ-20 | SSE 事件扩展支持 `pending_confirmation` | P0 | 前端正确接收和处理事件 |

---

## 五、成功指标 (Success Metrics)

### 5.1 数据安全指标

| 指标 | 目标 | 测量方式 |
|------|------|----------|
| 数据污染率 | 0 | 因 AI 误判导致的人工数据清洗工单数 |
| 撤销成功率 | 100% | 撤销请求的成功执行比例 |
| 撤销覆盖率 | 100% | 所有写操作都支持撤销 |

### 5.2 决策效率指标

| 指标 | 目标 | 测量方式 |
|------|------|----------|
| 决策耗时（多实体） | 缩短 50% | 用户在歧义选择场景的平均耗时 |
| 确认准确率 | 100% | 用户确认与最终业务结果的一致性 |
| 参数修改率 | < 5% | 用户在确认卡片修改参数的比例 |

### 5.3 系统成熟度指标

| 指标 | 目标 | 测量方式 |
|------|------|----------|
| 撤销使用率（初期） | > 1% | 撤销功能使用率（灰度期） |
| 撤销使用率（稳定） | < 0.1% | 撤销功能使用率（稳定后） |
| 自动化覆盖率（稳定） | > 80% | 低风险操作自动执行比例 |

---

## 六、实施路径建议

### Phase 1：基础设施（灰度必需）
- REQ-01, 02, 06, 07, 12, 13, 14
- 工期：3-5 天
- 目标：所有写操作需要确认，支持撤销

### Phase 2：增强体验
- REQ-03, 04, 05, 09, 10, 15
- 工期：2-3 天
- 目标：优化确认卡片，完善撤销提示

### Phase 3：系统优化
- REQ-11, 16, 17, 18, 19, 20
- 工期：2-3 天
- 目标：与现有系统深度集成

---

## 七、附录

### 7.1 风险等级定义表

| 风险等级 | 操作类型 | 撤销窗口 | 确认样式 |
|----------|----------|----------|----------|
| 低 | 查询、标签 | 无 | 无（自动执行） |
| 中 | 跟进记录、阶段推进 | 10秒 | 普通（蓝色） |
| 高 | 赢单/输单、转化、创建实体 | 30-60秒 | 警示（橙色） |

### 7.2 撤销窗口配置

| 操作 | TTL | 撤销范围 | 撤销方式 |
|------|-----|----------|----------|
| 创建跟进记录 | 10秒 | 单步 | 软删除 |
| 推进阶段 | 10秒 | 单步 | 恢复快照 |
| 赢单 | 30秒 | 流程 | 恢复状态+阶段 |
| 线索转化 | 60秒 | 流程 | 恢复线索+删除客户/商机 |

---

> **文档状态**：需求定义完成
> **下一步**：形成实施计划