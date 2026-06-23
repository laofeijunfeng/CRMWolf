---
priority: high
status: active
---

# AI OpenAPI 接口规范

> 版本：1.1 | 创建日期：2026-05-25 | 更新日期：2026-06-12 | 状态：生效
> **所有 AI OpenAPI 相关开发必须首先阅读本规范**

**权威说明**：本文档是 AI OpenAPI 开发的单一事实来源，AI 相关接口开发必须遵循本规范。

---

## 一、适用范围

本规范适用于 `/ai/` 路径下的所有接口开发：
- 业务意图层（Intent Layer）
- 原子动作层（Action Layer）
- 系统元数据层（Metadata Layer）
- 编排与审计（Orchestration & Audit）

---

## 二、架构约束

### 2.1 分层职责

| 层级 | 被责 | 禁止行为 |
|------|------|---------|
| **Intent Layer** | 意图解析、实体提取、规则匹配 | 直接操作数据库、执行业务逻辑 |
| **Action Layer** | 执行原子操作、Preview 返回变更计划 | 维护会话状态、管理对话流 |
| **Metadata Layer** | 暴露系统配置、业务规则、权限范围 | 动态修改配置、执行写操作 |
| **Orchestration** | 多动作编排、幂等性管理、审计日志 | 绕过 Action Layer 直接操作 |

### 2.2 目录结构

```
CRM-Server/app/
├── api/ai/                      # 路由层（仅定义接口）
│   ├── deps.py                  # 认证依赖
│   ├── intents.py               # 意图层路由
│   ├── actions.py               # 动作层路由
│   ├── metadata.py              # 元数据路由
│   ├── orchestrate.py           # 编排路由
│   └── logs.py                  # 审计日志路由
│
├── services/ai/                 # 业务逻辑层
│   ├── intent_parser.py         # 意图解析
│   ├── entity_extractor.py      # 实体提取
│   ├── rule_engine.py           # 规则匹配
│   ├── action_executor.py       # 动作执行（桥接现有 services）
│   ├── orchestrator.py          # 编排调度
│   ├── idempotency.py           # 幂等性管理
│   └── audit_logger.py          # 审计日志
│
├── schemas/ai/                  # Pydantic 模型
│   ├── common.py                # 通用请求/响应结构
│   ├── intent.py                # 意图相关
│   ├── action.py                # 动作相关
│   ├── metadata.py              # 元数据相关
│   └── audit.py                 # 审计相关
│
└── constants/
    └── ai_rules.py              # 意图枚举、风险分级、业务规则
```

### 2.3 桥接原则

**ActionExecutor 必须桥接现有 services，禁止直接操作数据库**：

```python
# ✅ 正确：调用现有 service
class ActionExecutor:
    async def create_follow_up(self, db, user, customer_id, content):
        return await follow_up_service.create(db, customer_id, content, user.id)

# ❌ 错误：直接操作数据库
class ActionExecutor:
    async def create_follow_up(self, db, customer_id, content):
        follow_up = FollowUp(customer_id=customer_id, content=content)
        db.add(follow_up)  # 禁止！
```

---

## 三、接口协议规范

### 3.1 统一请求结构

所有 Action 层接口必须遵循：

```python
class AIRequestBase(BaseModel):
    preview: bool = True                    # 是否仅预览（默认 True）
    action_id: Optional[str] = None         # 幂等 ID（执行时必填）
    context: Optional[Dict[str, Any]] = None  # 上下文信息

    @validator('action_id')
    def validate_action_id(cls, v, values):
        # 执行模式必须提供 action_id
        if not values.get('preview') and not v:
            raise ValueError('action_id required when preview=False')
        return v
```

### 3.2 统一响应结构

```python
class AIResponseBase(BaseModel):
    action_id: str
    status: Literal["preview", "completed", "failed", "rejected"]
    plan: Optional[ActionPlan] = None       # preview 时必填
    confidence: float = Field(ge=0.0, le=1.0)
    requires_confirmation: bool             # 是否需要人工确认
    message: str
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None   # completed 时返回实体数据

class ActionPlan(BaseModel):
    description: str                        # 变更描述（人类可读）
    changes: List[FieldChange]
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None

class FieldChange(BaseModel):
    field: str
    from_value: Optional[Any] = None
    to_value: Any
```

### 3.3 Preview 协议

| 模式 | preview | action_id | 行为 |
|------|---------|-----------|------|
| **预览** | `true` | 可选 | 返回 ActionPlan，不执行 |
| **执行** | `false` | 必填 | 执行操作，返回结果 |

**Preview 必须返回与执行一致的参数**：

```python
# ✅ 正确：Preview 返回实际将执行的参数
if request.preview:
    return AIResponseBase(
        action_id=action_id,
        status="preview",
        plan=ActionPlan(
            description=f"更新商机金额为 {request.amount}",
            changes=[FieldChange(field="amount", to_value=request.amount)]
        ),
        confidence=0.95,
        requires_confirmation=self._needs_confirm(request)
    )

# ❌ 错误：Preview 返回与执行不一致的信息
if request.preview:
    return {"message": "即将更新金额"}  # 缺少 changes 详情
```

---

## 四、风险分级规范

### 4.1 风险等级定义

| 等级 | 值 | 动作类型 | 自动执行阈值 | 强制确认 |
|------|-----|---------|-------------|---------|
| LOW | `low` | 创建跟进、设置提醒 | ≥ 0.85 | False |
| MEDIUM | `medium` | 更新金额/阶段、关联实体 | ≥ 0.90 | False |
| HIGH | `high` | 赢单/输单、线索转化 | 1.0 | True |
| CRITICAL | `critical` | 审批流、财务操作 | - | 禁止执行 |

### 4.2 配置结构

```python
# constants/ai_rules.py
class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

RISK_CONFIG = {
    RiskLevel.LOW: {
        "auto_threshold": 0.85,
        "force_confirm": False
    },
    RiskLevel.MEDIUM: {
        "auto_threshold": 0.90,
        "force_confirm": False
    },
    RiskLevel.HIGH: {
        "auto_threshold": 1.0,
        "force_confirm": True
    },
    RiskLevel.CRITICAL: {
        "auto_threshold": 1.0,
        "force_confirm": True,
        "dry_run_only": True  # 仅生成草稿，禁止执行
    }
}
```

### 4.3 确认判断逻辑

```python
def requires_confirmation(risk_level: RiskLevel, confidence: float) -> bool:
    config = RISK_CONFIG[risk_level]
    
    # CRITICAL 永远禁止执行
    if config.get("dry_run_only"):
        return True
    
    # 强制确认的永远需确认
    if config["force_confirm"]:
        return True
    
    # 置信度低于阈值需确认
    return confidence < config["auto_threshold"]
```

---

## 五、意图层规范

### 5.1 意图枚举池

**必须使用固定枚举，禁止 LLM 输出非标意图**：

```python
# constants/ai_rules.py
class IntentType(Enum):
    CREATE_FOLLOW_UP = "create_follow_up"
    CREATE_OPPORTUNITY = "create_opportunity"
    UPDATE_OPPORTUNITY = "update_opportunity"
    ADVANCE_STAGE = "advance_stage"
    WIN_OPPORTUNITY = "win_opportunity"
    LOSE_OPPORTUNITY = "lose_opportunity"
    CONVERT_LEAD = "convert_lead"
    SET_REMINDER = "set_reminder"
    QUERY_INFO = "query_info"
    UNKNOWN = "unknown"

# 禁止在代码中新增意图，必须先更新此枚举
```

### 5.2 意图解析输出结构

```python
class IntentResult(BaseModel):
    intent: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str                          # 判断依据（必填）
    entities: Optional[Dict[str, Any]] = None  # 提取的实体
    missing_fields: Optional[List[str]] = None  # 缺失字段提示
```

### 5.3 上下文继承

```python
class ExtractContext(BaseModel):
    previous_entity_id: Optional[int] = None
    previous_entity_type: Optional[str] = None
    conversation_history: Optional[List[Dict]] = None

# 当用户说"把那个改一下"时，必须从 context.previous_entity_id 继承
```

---

## 六、幂等性规范

### 6.1 Action ID 格式

```python
# 格式：act_{timestamp}_{random_suffix}
def generate_action_id() -> str:
    timestamp = int(time.time() * 1000)
    suffix = uuid.uuid4().hex[:8]
    return f"act_{timestamp}_{suffix}"
```

### 6.2 幂等性校验流程

```python
async def execute_with_idempotency(action_id: str, action: Callable):
    # 1. 检查是否已执行
    if await idempotency_manager.exists(action_id):
        # 返回已有结果（不重复执行）
        return await idempotency_manager.get_result(action_id)
    
    # 2. 锁定 action_id
    await idempotency_manager.lock(action_id)
    
    # 3. 执行操作
    result = await action()
    
    # 4. 记录结果
    await idempotency_manager.record_result(action_id, result)
    
    return result
```

### 6.3 Redis Key 设计

```
ai:action:{action_id}           # 锁定状态，TTL=3600s
ai:action:{action_id}:result    # 执行结果，TTL=3600s
```

---

## 七、审计日志规范

### 7.1 强制标记 source

```python
# 所有 AI 操作必须标记 source="ai"
log_entry = {
    "action_id": action_id,
    "action_type": action_type,
    "entity_type": entity_type,
    "entity_id": entity_id,
    "user_id": user.id,
    "source": "ai",               # 强制！
    "timestamp": datetime.utcnow()
}
```

### 7.2 链路追溯字段

```python
class AIAuditLog(BaseModel):
    intent_id: Optional[str] = None       # 意图 ID
    action_id: str                        # 动作 ID
    execution_id: Optional[str] = None    # 执行 ID（编排时）
    action_type: str
    entity_type: str
    entity_id: int
    user_id: int
    source: Literal["ai"] = "ai"
    status: str
    confidence: float
    timestamp: datetime
```

---

## 八、元数据接口规范

### 8.1 商机阶段返回格式

```json
{
  "stages": [
    {
      "name": "需求确认",
      "win_rate": 0.2,
      "next_stages": ["方案报价", "方案演示"],
      "allowed_actions": ["edit", "advance"]
    }
  ]
}
```

### 8.2 实体关系返回格式

```json
{
  "entities": [
    {
      "name": "Opportunity",
      "required_fields": ["customer_id", "name"],
      "optional_fields": ["amount", "expected_close_date", "stage"],
      "relations": ["Customer", "FollowUp", "Contract"]
    }
  ]
}
```

### 8.3 权限范围返回格式

```json
{
  "data_scope": "own",
  "allowed_actions": ["create", "view", "edit"],
  "restricted_actions": ["delete", "approve"]
}
```

---

## 九、错误处理规范

### 9.1 错误响应结构

```python
class AIErrorResponse(BaseModel):
    action_id: str
    status: Literal["failed", "rejected"]
    message: str
    error: str
    error_code: Optional[str] = None
    missing_fields: Optional[List[str]] = None  # 缺失字段提示
    suggested_actions: Optional[List[str]] = None  # 推荐下一步
```

### 9.2 错误码定义

| 错误码 | 说明 | 响应示例 |
|--------|------|---------|
| `AI_MISSING_FIELD` | 缺失必填字段 | `"missing_fields": ["customer_id"]` |
| `AI_ENTITY_NOT_FOUND` | 实体不存在 | `"message": "商机 #123 不存在"` |
| `AI_PERMISSION_DENIED` | 无权限 | `"restricted_actions": ["delete"]` |
| `AI_DUPLICATE_ACTION` | 重复 action_id | `"message": "操作已执行"` |
| `AI_RISK_REJECTED` | 高风险被拒绝 | `"status": "rejected"` |

---

## 十、测试规范

### 10.1 必测场景

| 场景 | 测试内容 |
|------|---------|
| Preview 模式 | `preview=true` 返回 ActionPlan，不执行 |
| 执行模式 | `preview=false` + `action_id` 正确执行 |
| 幂等性 | 相同 `action_id` 重复调用无副作用 |
| 风险分级 | 各风险等级的确认逻辑正确 |
| 上下文继承 | `context.previous_entity_id` 正确补全 |

### 10.2 测试覆盖率

- 单元测试：≥ 80%
- 集成测试：核心流程覆盖
- E2E 测试：多轮对话场景

---

> **文档版本**：1.0
> **最后更新**：2026-05-25
> **修改需人工审批**