---
status: completed
created: 2026-06-10
updated: 2026-06-10
related_requirements: ../requirements/AI-AGENT-SAFETY-ENHANCEMENT-REQUIREMENTS.md
related_pr: -
---

# Agent 交互安全与决策增强 - 实施计划

> **状态：✅ 已完成** | 完成日期：2026-06-10

| 文档版本 | V 1.0 |
| :--- | :--- |
| **基于需求** | AI-AGENT-SAFETY-ENHANCEMENT-REQUIREMENTS.md |
| **实施原则** | 不计成本，以成熟、稳健为首要 |
| **更新日期** | 2026-06-10 |

---

## 一、实施阶段划分

### 总览

| Phase | 内容 | 优先级 | 工期 |
|-------|------|--------|------|
| **Phase 1** | 基础设施：显式确认 + 撤销机制 + EntityRenderer | P0（灰度必需） | 3-5 天 |
| **Phase 2** | 增强体验：参数修改 + 证据链 + 撤销提示 | P1 | 2-3 天 |
| **Phase 3** | 系统集成：与现有系统深度集成 | P1 | 2-3 天 |

---

## 二、Phase 1：基础设施（P0）

### 2.1 目标
- 所有写操作默认需要确认
- 支持单步和流程级撤销
- EntityRenderer 标准化实体展示

### 2.2 后端实施

#### 2.2.1 Operation Log 表扩展

**文件**：`CRM-Server/app/models/operation_log.py`

```python
# 新增字段
class OperationLog(Base):
    __tablename__ = "operation_log"
    
    # 原有字段...
    
    # 撤销相关（新增）
    undoable = Column(Boolean, default=False)
    undo_ttl = Column(Integer, default=10)
    undo_deadline = Column(DateTime)
    undone = Column(Boolean, default=False)
    undo_by = Column(Integer)
    undo_at = Column(DateTime)
    
    # 流程关联（新增）
    workflow_session_id = Column(String(64))
    step_id = Column(String(32))
    parent_operation_id = Column(Integer)
    
    # 快照（新增）
    before_snapshot = Column(JSON)
    after_snapshot = Column(JSON)
```

**数据库迁移**：
```bash
alembic revision -m "add_undo_fields_to_operation_log"
alembic upgrade head
```

---

#### 2.2.2 Undo Service 实现

**新增文件**：`CRM-Server/app/services/workflow/undo_service.py`

**核心类设计**：

```python
class UndoService:
    """撤销服务"""
    
    def can_undo(self, operation_id: int) -> bool
    def undo_single(self, operation_id: int, user_id: int) -> UndoResult
    def undo_workflow(self, session_id: str, user_id: int) -> UndoResult
    def get_undo_handler(self, event_type: str) -> UndoHandler
```

**撤销处理器注册表**：

| Handler | 操作类型 | 撤销方式 |
|---------|----------|----------|
| `FollowUpUndoHandler` | FOLLOW_UP_CREATED | 软删除 |
| `OpportunityWinUndoHandler` | OPPORTUNITY_WON | 状态恢复 + 阶段恢复 |
| `OpportunityStageUndoHandler` | OPPORTUNITY_STAGE_CHANGED | 阶段快照恢复 |
| `LeadConvertUndoHandler` | LEAD_CONVERTED | 恢复线索 + 删除客户/商机 |
| `ContractUndoHandler` | CONTRACT_CREATED | 软删除 |
| `CustomerCreateUndoHandler` | CUSTOMER_CREATED | 软删除 |

---

#### 2.2.3 撤销处理器实现

**新增文件**：`CRM-Server/app/services/workflow/undo_handlers.py`

**核心实现**：

1. **FollowUpUndoHandler**：软删除跟进记录
2. **OpportunityWinUndoHandler**：恢复商机状态、赢率、删除成交信息、恢复阶段快照
3. **LeadConvertUndoHandler**：恢复线索状态、删除创建的客户和商机（若无其他关联）

---

#### 2.2.4 Undo API 接口

**新增文件**：`CRM-Server/app/api/workflow_undo.py`

```python
@router.post("/undo/{operation_id}")
async def undo_operation(operation_id: int, user_id: int, db: Session)

@router.post("/undo/workflow/{session_id}")
async def undo_workflow(session_id: str, user_id: int, db: Session)

@router.get("/undo/status/{operation_id}")
async def get_undo_status(operation_id: int, db: Session)
```

---

#### 2.2.5 Workflow 步骤配置扩展

**改动文件**：`CRM-Server/app/services/workflow/workflow_definitions.py`

**扩展结构**：

```python
# customer_win_flow 步骤改造
{
    "id": "create_follow_up",
    "type": "tool",
    "tool_name": "follow_up_customer",
    "require_confirmation": True,     # 新增：需要确认
    "confirmation_config": {
        "ttl": 10,
        "allow_param_edit": True,
        "risk_level": "medium",
    },
    "undo_support": True,
    "undo_ttl": 10,
},
{
    "id": "win_opportunity",
    "type": "tool",
    "tool_name": "win_opportunity",
    "require_confirmation": True,
    "confirmation_config": {
        "ttl": 30,
        "allow_param_edit": False,    # 赢单不允许修改参数
        "risk_level": "high",
    },
    "undo_support": True,
    "undo_ttl": 30,
}
```

---

#### 2.2.6 Workflow Orchestrator 扩展

**改动文件**：`CRM-Server/app/services/workflow/workflow_orchestrator.py`

**新增方法**：

```python
def _execute_tool_with_confirmation(
    self,
    step: Dict,
    session: Dict,
    db: Session
) -> AsyncGenerator[SSEEvent, None]:
    """执行工具（带确认）"""
    
    # 1. 检查是否需要确认
    if step.get("require_confirmation"):
        # 2. 发送 pending_confirmation 事件
        yield {
            "event": "pending_confirmation",
            "step_id": step["id"],
            "tool_name": step["tool_name"],
            "params": mapped_params,
            "risk_level": step["confirmation_config"]["risk_level"],
            "undo_config": {
                "ttl": step.get("undo_ttl", 10),
                "scope": "workflow" if step["id"] == "win_opportunity" else "single"
            },
            "display": self._build_confirmation_display(step, params, session)
        }
        
        # 3. 等待用户确认
        session["waiting_for_confirmation"] = step["id"]
        self._save_session(session)
        return
    
    # 4. 无需确认，直接执行
    yield from self._execute_tool_directly(step, session, db)

def _handle_user_confirmation(
    self,
    session: Dict,
    user_response: Dict,
    db: Session
) -> AsyncGenerator[SSEEvent, None]:
    """处理用户确认"""
    
    step_id = session.get("waiting_for_confirmation")
    step = self._get_step_by_id(step_id)
    
    # 1. 检查用户响应
    action = user_response.get("action")
    
    if action == "cancel":
        yield {"event": "step_cancelled", "step_id": step_id}
        return
    
    if action == "edit_params":
        # 用户修改参数
        updated_params = user_response.get("params")
        yield from self._execute_tool_with_confirmation(step, session, db, updated_params)
        return
    
    if action == "confirm":
        # 执行工具
        result = await self._execute_tool(step, session, db)
        
        # 记录操作日志（含撤销配置）
        operation_log_service.log(
            undoable=step.get("undo_support", True),
            undo_ttl=step.get("undo_ttl", 10),
            workflow_session_id=session["session_id"],
            step_id=step_id,
            before_snapshot=self._capture_before_snapshot(session),
            after_snapshot=self._capture_after_snapshot(result)
        )
        
        yield {"event": "step_result", "step_id": step_id, "result": result}
        
        # 发送 undo_available 事件
        if step.get("undo_support"):
            yield {
                "event": "undo_available",
                "step_id": step_id,
                "undo_ttl": step.get("undo_ttl", 10),
                "undo_endpoint": f"/undo/{result['operation_id']}"
            }
```

---

#### 2.2.7 EntityRenderer 服务

**新增文件**：`CRM-Server/app/services/workflow/entity_renderer.py`

**核心实现**：

```python
class EntityRenderer:
    """实体展示数据渲染"""
    
    DISPLAY_CONFIGS = {
        "opportunity": {
            "name_field": "opportunity_name",
            "key_fields": [
                {"field": "total_amount", "label": "金额", "format": "currency"},
                {"field": "current_stage_name", "label": "阶段"},
                {"field": "win_probability", "label": "赢率", "format": "percent"},
                {"field": "updated_at", "label": "更新时间", "format": "datetime"},
            ]
        },
        "customer": {...},
        "lead": {...},
        "contract": {...}
    }
    
    def render_for_selection(
        self,
        entity_type: str,
        entities: List[Any]
    ) -> List[Dict[str, Any]]:
        """渲染实体选择列表"""
        ...
```

---

#### 2.2.8 Handler 快照记录

**改动文件**：`CRM-Server/app/services/skills/handlers/base_handler.py`

**新增方法**：

```python
class BaseHandler:
    def capture_snapshot(self, entity: Any) -> Dict[str, Any]:
        """捕获实体快照"""
        snapshot = {}
        for field in self.get_snapshot_fields():
            snapshot[field] = getattr(entity, field, None)
        return snapshot
    
    def log_with_undo(
        self,
        db: Session,
        result: Dict[str, Any],
        undo_config: Dict[str, Any],
        session_id: str = None,
        step_id: str = None
    ):
        """记录操作日志（含撤销配置）"""
        operation_log_service.log(
            db=db,
            event_type=self.event_type,
            event_action=self.event_action,
            resource_type=self.resource_type,
            resource_id=result.get("entity_id"),
            undoable=undo_config.get("undoable", True),
            undo_ttl=undo_config.get("ttl", 10),
            undo_deadline=datetime.now() + timedelta(seconds=undo_config.get("ttl", 10)),
            workflow_session_id=session_id,
            step_id=step_id,
            before_snapshot=result.get("before_snapshot"),
            after_snapshot=result.get("after_snapshot"),
            operator_id=result.get("user_id")
        )
```

---

### 2.3 前端实施

#### 2.3.1 确认卡片组件

**新增文件**：`CRM-Client/src/components/ConfirmationCard.vue`

**组件设计**：

```vue
<template>
  <div class="confirmation-card" :class="`risk-${riskLevel}`">
    <!-- 标题 -->
    <div class="card-title">
      <el-icon :class="riskLevelClass"><Warning /></el-icon>
      <span>{{ title }}</span>
    </div>
    
    <!-- 实体信息 -->
    <div class="entity-info">
      <div class="info-label">操作对象：</div>
      <div class="info-value">{{ entityDisplay }}</div>
    </div>
    
    <!-- 参数列表 -->
    <div class="params-list">
      <div class="params-label">操作参数：</div>
      <div v-for="(value, key) in params" :key="key" class="param-item">
        <span class="param-key">{{ key }}:</span>
        <span class="param-value">{{ value }}</span>
        <el-button v-if="allowEdit" size="small" @click="editParam(key)">
          修改
        </el-button>
      </div>
    </div>
    
    <!-- 证据链 -->
    <div v-if="evidenceChain" class="evidence-chain">
      <div class="evidence-label">识别依据：</div>
      <div class="evidence-content">{{ evidenceChain }}</div>
    </div>
    
    <!-- 操作按钮 -->
    <div class="card-actions">
      <el-button @click="handleCancel">取消</el-button>
      <el-button v-if="allowEdit" @click="handleEditAll">修改参数</el-button>
      <el-button type="primary" @click="handleConfirm">确认执行</el-button>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  title: String,
  riskLevel: 'low' | 'medium' | 'high',
  entityDisplay: String,
  params: Object,
  allowEdit: Boolean,
  evidenceChain: String,
  undoTtl: Number
})
</script>
```

---

#### 2.3.2 撤销 Toast 组件

**新增文件**：`CRM-Client/src/components/UndoToast.vue`

**组件设计**：

```vue
<template>
  <div class="undo-toast" v-if="visible">
    <div class="toast-message">
      {{ message }} <span class="countdown">{{ remainingSeconds }}秒</span>
    </div>
    <el-button size="small" type="warning" @click="handleUndo">
      撤销
    </el-button>
  </div>
</template>

<script setup>
const props = defineProps({
  operationId: Number,
  undoEndpoint: String,
  ttl: Number,
  message: String
})

const visible = ref(true)
const remainingSeconds = ref(props.ttl)

// 倒计时
const timer = setInterval(() => {
  remainingSeconds.value -= 1
  if (remainingSeconds.value <= 0) {
    visible.value = false
    clearInterval(timer)
  }
}, 1000)

// 撤销
const handleUndo = async () => {
  await api.post(props.undoEndpoint)
  visible.value = false
  emit('undo-success')
}
</script>
```

---

#### 2.3.3 实体选择组件优化

**改动文件**：`CRM-Client/src/components/EntitySelectDialog.vue`

**增强展示**：

```vue
<template>
  <el-dialog title="请选择实体">
    <el-radio-group v-model="selectedId">
      <el-radio v-for="option in options" :key="option.id" :value="option.id">
        <div class="entity-option">
          <div class="entity-name">{{ option.name }}</div>
          <div class="entity-fields">
            <span v-for="(value, label) in option.fields" :key="label">
              {{ label }}: {{ value }}
            </span>
          </div>
        </div>
      </el-radio>
    </el-radio-group>
  </el-dialog>
</template>
```

---

#### 2.3.4 SSE 事件处理扩展

**改动文件**：`CRM-Client/src/components/MagicWandDialog.vue`

**新增事件处理**：

```typescript
case 'pending_confirmation':
  handlePendingConfirmation(event)
  break

case 'undo_available':
  showUndoToast(event)
  break

case 'undo_expired':
  hideUndoToast(event)
  break

function handlePendingConfirmation(event) {
  // 显示确认卡片
  confirmationCard.value = {
    title: getToolDisplayName(event.tool_name),
    riskLevel: event.risk_level,
    params: event.params,
    allowEdit: event.confirmation_config?.allow_param_edit,
    undoTtl: event.undo_config?.ttl,
    ...
  }
  stage.value = 'pending-confirmation'
}

function handleConfirm(action, updatedParams) {
  // 发送确认请求
  workflowApi.continueWorkflow(sessionId, {
    action: action,
    params: updatedParams
  })
}
```

---

#### 2.3.5 Workflow API 扩展

**改动文件**：`CRM-Client/src/api/workflow.ts`

**新增接口**：

```typescript
export function undoOperation(operationId: number) {
  return axios.post(`/workflow/undo/${operationId}`)
}

export function undoWorkflow(sessionId: string) {
  return axios.post(`/workflow/undo/workflow/${sessionId}`)
}

export function getUndoStatus(operationId: number) {
  return axios.get(`/workflow/undo/status/${operationId}`)
}
```

---

### 2.4 测试验证

#### 2.4.1 后端单元测试

**新增文件**：`CRM-Server/tests/unit/test_undo_service.py`

```python
async def test_follow_up_undo():
    """测试跟进记录撤销"""
    # 1. 创建跟进记录
    result = await handler.handle(...)
    operation_id = result["operation_id"]
    
    # 2. 撤销
    undo_result = undo_service.undo_single(operation_id, user_id)
    
    # 3. 验证
    assert undo_result.success
    follow_up = crud.get_by_id(db, result["entity_id"])
    assert follow_up.deleted == True

async def test_opportunity_win_undo():
    """测试赢单撤销"""
    # 1. 赢单
    result = await handler.handle(...)
    
    # 2. 撤销
    undo_result = undo_service.undo_single(...)
    
    # 3. 验证
    opportunity = crud.get_by_id(db, result["entity_id"])
    assert opportunity.status == OpportunityStatus.FOLLOWING
    assert opportunity.win_probability == before_snapshot["win_probability"]
    assert opportunity.actual_amount == None

async def test_workflow_undo():
    """测试流程级撤销"""
    # 1. 执行整个流程
    session_id = await execute_workflow(...)
    
    # 2. 撤销流程
    undo_result = undo_service.undo_workflow(session_id, user_id)
    
    # 3. 验证所有步骤都被撤销
    assert undo_result.undone_count == 5
```

---

#### 2.4.2 前端组件测试

**新增文件**：`CRM-Client/src/components/__tests__/ConfirmationCard.spec.ts`

```typescript
describe('ConfirmationCard', () => {
  it('renders risk level correctly', () => {
    const wrapper = mount(ConfirmationCard, {
      props: { riskLevel: 'high' }
    })
    expect(wrapper.find('.risk-high')).exists()
  })
  
  it('shows countdown', () => {
    const wrapper = mount(UndoToast, {
      props: { ttl: 10 }
    })
    expect(wrapper.find('.countdown').text()).toBe('10秒')
  })
})
```

---

## 三、Phase 2：增强体验（P1）

### 3.1 目标
- 参数修改功能
- 证据链展示
- 撤销提示优化

### 3.2 实施内容

#### 3.2.1 参数编辑表单

**新增文件**：`CRM-Client/src/components/ParamEditForm.vue`

```vue
<template>
  <el-form :model="editedParams">
    <el-form-item v-for="field in editableFields" :key="field.key">
      <el-input v-model="editedParams[field.key]" />
    </el-form-item>
  </el-form>
</template>
```

#### 3.2.2 证据链展示

**改动文件**：`CRM-Server/app/services/workflow/workflow_orchestrator.py`

```python
def _build_evidence_chain(self, session: Dict) -> Dict:
    """构建证据链"""
    return {
        "entity_source": session.get("entity_context", {}).get("source"),
        "recognition_method": "context_injection",  # 或 "user_specified"
        "original_text": session.get("user_input"),
        "extracted_entities": [...]
    }
```

#### 3.2.3 撤销倒计时动画

**改动文件**：`CRM-Client/src/components/UndoToast.vue`

```vue
<div class="undo-progress-bar">
  <el-progress 
    :percentage="(remainingSeconds / ttl) * 100"
    :show-text="false"
    status="warning"
  />
</div>
```

---

## 四、Phase 3：系统集成（P1）

### 4.1 目标
- 与 Operation Log 深度集成
- 与 Guardrails 协同
- Workflow 步骤配置完善

### 4.2 实施内容

#### 4.2.1 Handler 自动记录撤销日志

**改动文件**：每个 Handler

```python
# FollowUpHandler
def handle(self, db, params, user_id, session_id=None, step_id=None):
    # 1. 捕获前快照
    before_snapshot = None
    
    # 2. 执行
    result = self._execute(db, params, user_id)
    
    # 3. 捕获后快照
    after_snapshot = self._capture_snapshot(follow_up)
    
    # 4. 记录日志（含撤销配置）
    self.log_with_undo(
        db=db,
        result={
            "entity_id": follow_up.id,
            "before_snapshot": before_snapshot,
            "after_snapshot": after_snapshot,
            "user_id": user_id
        },
        undo_config={
            "undoable": True,
            "ttl": 10
        },
        session_id=session_id,
        step_id=step_id
    )
    
    return result
```

#### 4.2.2 Guardrails 协同

**改动文件**：`CRM-Server/app/services/workflow/guardrails.py`

```python
def check_with_confirmation(self, confidence: float, operation_type: str) -> CheckResult:
    """带确认机制的检查"""
    
    # 置信度检查
    if confidence < 0.70:
        return CheckResult(action="reject", reason="置信度过低")
    
    # 所有写操作需要确认（灰度期）
    if operation_type in [CREATE, UPDATE, DELETE]:
        return CheckResult(
            action="pending_confirmation",
            confidence=confidence,
            risk_level=self._get_risk_level(operation_type)
        )
    
    return CheckResult(action="execute")
```

---

## 五、文件改动清单

### 5.1 新增文件

| 文件 | 类型 | Phase | 说明 |
|------|------|-------|------|
| `app/models/operation_log.py` | 模型扩展 | P1 | Operation Log 表扩展 |
| `app/services/workflow/undo_service.py` | 新增 | P1 | 撤销服务 |
| `app/services/workflow/undo_handlers.py` | 新增 | P1 | 撤销处理器 |
| `app/services/workflow/entity_renderer.py` | 新增 | P1 | 实体展示渲染 |
| `app/api/workflow_undo.py` | 新增 | P1 | Undo API |
| `CRM-Client/src/components/ConfirmationCard.vue` | 新增 | P1 | 确认卡片组件 |
| `CRM-Client/src/components/UndoToast.vue` | 新增 | P1 | 撤销 Toast |
| `CRM-Client/src/components/ParamEditForm.vue` | 新增 | P2 | 参数编辑表单 |
| `tests/unit/test_undo_service.py` | 新增 | P1 | 撤销服务测试 |

### 5.2 改动文件

| 文件 | Phase | 改动内容 |
|------|-------|----------|
| `app/services/workflow/workflow_definitions.py` | P1 | 步骤配置扩展（require_confirmation） |
| `app/services/workflow/workflow_orchestrator.py` | P1 | 确认流程 + 撤销支持 |
| `app/services/skills/handlers/base_handler.py` | P1 | 快照记录 + 撤销日志 |
| `app/services/skills/handlers/*.py` | P3 | 各 Handler 撤销支持 |
| `app/services/workflow/guardrails.py` | P3 | 与确认机制协同 |
| `CRM-Client/src/components/MagicWandDialog.vue` | P1 | 确认事件处理 |
| `CRM-Client/src/components/EntitySelectDialog.vue` | P1 | 实体展示优化 |
| `CRM-Client/src/api/workflow.ts` | P1 | Undo API |

---

## 六、验收清单

### 6.1 Phase 1 验收

| 验收项 | 标准 | 测试方式 |
|--------|------|----------|
| 所有写操作需要确认 | 100% 写操作显示确认卡片 | 手动测试 Workflow 流程 |
| 单步撤销 | 10秒内可撤销跟进记录 | 单元测试 |
| 流程撤销 | 30秒内可撤销赢单流程 | 单元测试 |
| EntityRenderer | 商机选择展示金额、阶段等 | 手动测试 |

### 6.2 Phase 2 验收

| 验收项 | 标准 | 测试方式 |
|--------|------|----------|
| 参数修改 | 用户可在确认前修改参数 | 手动测试 |
| 证据链展示 | 确认卡片显示实体来源 | 手动测试 |
| 撤销倒计时 | Toast 显示剩余时间 | 手动测试 |

### 6.3 Phase 3 验收

| 验收项 | 标准 | 测试方式 |
|--------|------|----------|
| Handler 自动记录 | 所有 Handler 记录撤销日志 | 单元测试 |
| Guardrails 协同 | 低置信度 + 写操作都触发确认 | 单元测试 |
| Workflow 配置 | 步骤可配置 require_confirmation | 手动测试 |

---

## 七、风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 撤销失败 | 数据无法恢复 | 撤销前验证可撤销性 + 快照机制 |
| 确认流程卡顿 | 用户体验差 | 前端优化加载 + 后端异步处理 |
| 撤销窗口过期 | 用户无法撤销 | 延长高风险操作窗口 + 提供历史撤销 |

---

## 八、实施顺序

```
Day 1: 
  - Operation Log 表扩展
  - Undo Service 基础实现
  - FollowUpUndoHandler

Day 2:
  - OpportunityWinUndoHandler
  - LeadConvertUndoHandler
  - EntityRenderer

Day 3:
  - Workflow Orchestrator 扩展
  - Undo API
  - 前端 ConfirmationCard

Day 4:
  - 前端 UndoToast
  - EntitySelectDialog 优化
  - SSE 事件处理

Day 5:
  - 单元测试
  - 集成测试
  - 验收

Day 6-7: Phase 2 实施

Day 8-10: Phase 3 实施 + 系统测试
```

---

> **实施计划状态**：定义完成
> **下一步**：按 Phase 顺序实施