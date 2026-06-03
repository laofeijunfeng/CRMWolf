# AI OpenAPI 实现状态

> 版本：1.0 | 创建日期：2026-05-25 | 状态：已实现
> 基于 [AI-API-STANDARD.md](AI-API-STANDARD.md) 规范完成

---

## 一、实现概述

AI OpenAPI 层已完成全部四阶段实现，为 AI Agent 提供标准化的 CRM 系统交互接口。

**核心能力**：
- 意图解析 → 实体提取 → 规则匹配 → 动作执行 → 审计追踪
- 全流程 Preview 模式支持
- 幂等性保证（Redis SETNX）
- 风险分级自动确认

---

## 二、端点清单

| 路径 | 数量 | 说明 |
|------|------|------|
| `/ai/metadata/` | 5 | 系统配置暴露 |
| `/ai/actions/` | 8 | 原子动作执行 |
| `/ai/intents/` | 5 | 意图解析服务 |
| `/ai/logs/` | 3 | 审计日志查询 |
| **总计** | **21** | |

### 2.1 Metadata Layer（5 个）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/ai/metadata/stages` | GET | 商机阶段与赢率映射 |
| `/ai/metadata/rules` | GET | 业务规则库 |
| `/ai/metadata/entities` | GET | 实体定义（字段、关系） |
| `/ai/metadata/permissions` | GET | 当前用户权限范围 |
| `/ai/metadata/enums` | GET | 状态枚举值 |

**返回格式示例**：

```json
// /ai/metadata/stages
{
  "procurement_methods": [
    {
      "method_id": 1,
      "method_name": "标准采购",
      "stages": [
        {
          "stage_id": 1,
          "name": "需求确认",
          "win_rate": 0.2,           // 0-1 范围
          "next_stages": ["方案报价"],
          "allowed_actions": ["edit", "advance", "lose"]
        }
      ]
    }
  ]
}

// /ai/metadata/entities
{
  "entities": [
    {
      "name": "Opportunity",
      "display_name": "商机",
      "required_fields": [
        {"name": "customer_id", "type": "integer", "description": "关联客户ID"}
      ],
      "relations": [
        {"name": "Customer", "type": "belongs_to", "field": "customer_id"}
      ]
    }
  ]
}
```

### 2.2 Action Layer（8 个）

| 端点 | 方法 | 风险等级 | 说明 |
|------|------|---------|------|
| `/ai/actions/create-follow-up` | POST | LOW | 创建跟进记录 |
| `/ai/actions/set-reminder` | POST | LOW | 设置提醒 |
| `/ai/actions/init-opportunity` | POST | MEDIUM | 初始化商机 |
| `/ai/actions/update-amount` | POST | MEDIUM | 更新金额 |
| `/ai/actions/update-stage` | POST | MEDIUM | 更新阶段 |
| `/ai/actions/win-opportunity` | POST | HIGH | 赢单（强制确认） |
| `/ai/actions/lose-opportunity` | POST | HIGH | 输单（强制确认） |
| `/ai/actions/orchestrate` | POST | - | 多动作编排 |

**统一请求结构**：

```python
class AIRequestBase:
    preview: bool = True              # 默认预览
    action_id: Optional[str] = None   # 执行时必填（validator 校验）
    context: Optional[Dict] = None    # 上下文继承
```

**统一响应结构**：

```python
class AIResponseBase:
    action_id: str
    status: Literal["preview", "completed", "failed", "rejected"]
    plan: Optional[ActionPlan]        # Preview 时返回
    confidence: float                 # 0.0-1.0
    requires_confirmation: bool       # 是否需人工确认
    message: str
    data: Optional[Dict]              # Completed 时返回
```

**Preview 示例**：

```json
// POST /ai/actions/update-amount?preview=true
{
  "action_id": "act_1748056800000_abc123",
  "status": "preview",
  "plan": {
    "description": "更新商机 #123 金额为 50000",
    "changes": [
      {"field": "amount", "to_value": 50000}
    ],
    "entity_type": "Opportunity",
    "entity_id": 123
  },
  "confidence": 0.9,
  "requires_confirmation": false,
  "message": "预览：即将更新金额为 50000"
}
```

### 2.3 Intent Layer（5 个）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/ai/intents/parse` | POST | 解析单个意图 |
| `/ai/intents/parse-multi` | POST | 解析多个意图（复合输入） |
| `/ai/intents/extract` | POST | 实体提取 |
| `/ai/intents/rules/match` | POST | 规则匹配 → Action 推荐 |
| `/ai/intents/rules/list` | GET | 意图类型列表 |

**意图枚举池**（固定，禁止 LLM 输出非标意图）：

```python
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
```

**IntentResult 结构**：

```python
@dataclass
class IntentResult:
    intent: IntentType
    confidence: float
    reasoning: str                    # 判断依据
    entities: Dict[str, Any] = None   # 提取的实体
    missing_fields: List[str] = None  # 缺失字段提示
```

**实体提取能力**：

| 实体类型 | 示例 | 正则 |
|---------|------|------|
| 金额 | "10万"、"5000元" | `(\d+\.?\d*)\s*(万|w|元|k)?` |
| 日期 | "明天"、"下周三" | 预定义关键词 |
| 客户引用 | "#123"、"这个客户" | `#(\d+)` + 上下文继承 |
| 商机引用 | "商机#456" | `商机\s*#(\d+)` |

### 2.4 Logs Layer（3 个）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/ai/logs` | GET | 审计日志列表（多维度筛选） |
| `/ai/logs/stats` | GET | AI 操作统计 |
| `/ai/logs/{log_id}` | GET | 单条日志详情 |

**筛选参数**：

- `action_id` - 精确匹配
- `action_type` - 动作类型
- `resource_type` - 资源类型
- `event_type` - 事件类型
- `start_date` / `end_date` - 时间范围
- `page` / `page_size` - 分页

**查询逻辑**：通过 `event_type LIKE 'AI_%'` 筛选 AI 操作。

---

## 三、核心组件

### 3.1 目录结构

```
CRM-Server/app/
├── api/ai/
│   ├── __init__.py              # 路由聚合
│   ├── deps.py                  # 认证依赖
│   ├── metadata.py              # 元数据层（5 端点）
│   ├── actions.py               # 动作层（8 端点含编排）
│   ├── intents.py               # 意图层（5 端点）
│   └── logs.py                  # 审计日志（3 端点）
│
├── services/ai/
│   ├── __init__.py              # 服务导出
│   ├── intent_parser.py         # IntentParser + EntityExtractor + RuleMatcher
│   ├── action_executor.py       # Action 执行器（桥接现有 CRUD）
│   └── idempotency.py           # 幂等性管理器（Redis）
│
├── schemas/ai/
│   └ common.py                  # AIRequestBase + AIResponseBase + 错误结构
│
└── constants/
    └── ai_rules.py              # IntentType + RiskLevel + BUSINESS_RULES + AIErrorCode
```

### 3.2 幂等性管理器

**Redis Key 设计**：

```
ai:action:{action_id}           # 锁定状态，TTL=3600s
ai:action:{action_id}:result    # 执行结果，TTL=3600s
```

**核心方法**：

```python
class IdempotencyManager:
    def check_or_lock(self, action_id: str) -> bool:
        # SETNX 原子性检查+锁定
        # 返回 True: 可执行；False: 已执行/已锁定

    def record_result(self, action_id: str, result: Dict) -> bool:
        # 记录执行结果供后续查询

    def get_result(self, action_id: str) -> Optional[Dict]:
        # 获取已执行结果（幂等性返回）
```

**Action ID 格式**：

```python
def generate_action_id() -> str:
    # act_{timestamp}_{random_suffix}
    # 例：act_1748056800000_abc123
```

### 3.3 风险分级系统

| 等级 | auto_threshold | force_confirm | dry_run_only | 动作类型 |
|------|---------------|---------------|--------------|---------|
| LOW | 0.85 | False | False | 创建跟进、设置提醒 |
| MEDIUM | 0.90 | False | False | 更新金额/阶段、初始化商机 |
| HIGH | 1.0 | True | False | 赢单/输单、线索转化 |
| CRITICAL | 1.0 | True | **True** | 审批流、财务操作 |

**确认逻辑**：

```python
def requires_confirmation(risk_level: RiskLevel, confidence: float) -> bool:
    config = RISK_CONFIG[risk_level]

    # CRITICAL 禁止执行
    if config.get("dry_run_only"):
        return True

    # 强制确认
    if config["force_confirm"]:
        return True

    # 置信度不足
    return confidence < config["auto_threshold"]
```

### 3.4 ActionExecutor 桥接模式

**设计原则**：不直接操作数据库，桥接现有 CRUD/Service。

```python
class ActionExecutor:
    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user
        self.operator_id = str(user.id)

    def create_follow_up(self, customer_id, content, ...):
        # 调用 customer_follow_up_crud.create
        follow_up = customer_follow_up_crud.create(...)
        # 记录审计日志
        self._log_ai_action("AI_CREATE_FOLLOW_UP", ...)
        return follow_up
```

**审计日志字段**：

```python
content = {
    "source": "ai",              # 强制标记
    "operator_type": "ai",
    "action_type": "create_follow_up",
    "action_id": action_id,
    ...
}
```

---

## 四、错误码定义

| 错误码 | 说明 | 触发场景 |
|--------|------|---------|
| `AI_MISSING_FIELD` | 缺失必填字段 | 意图解析时提示 |
| `AI_ENTITY_NOT_FOUND` | 实体不存在 | 执行时查询失败 |
| `AI_PERMISSION_DENIED` | 无权限 | 权限校验失败 |
| `AI_DUPLICATE_ACTION` | 重复 action_id | 幂等性检查 |
| `AI_RISK_REJECTED` | 高风险被拒绝 | CRITICAL 禁止执行 |
| `AI_INVALID_PARAM` | 参数格式无效 | 数据校验失败 |
| `AI_EXECUTION_FAILED` | 执行失败 | 业务异常 |
| `AI_LOCKED` | action_id 被锁定 | 并发冲突 |

---

## 五、编排执行流程

### 5.1 单动作流程

```
1. 接收请求（preview=true/false）
2. 解析参数 + 风险评估
3. Preview: 返回 ActionPlan
4. Execute:
   - 幂等性检查（check_or_lock）
   - 执行动作（ActionExecutor）
   - 记录审计（source="ai"）
   - 返回结果
```

### 5.2 多动作编排流程

```
POST /ai/actions/orchestrate
{
  "steps": [
    {"action": "create_follow_up", "params": {...}, "order": 1},
    {"action": "init_opportunity", "params": {...}, "order": 2}
  ],
  "stop_on_failure": true
}

响应：
{
  "action_id": "act_orchestrate_xxx",
  "status": "completed",
  "results": [
    {"step_order": 1, "action": "create_follow_up", "status": "success"},
    {"step_order": 2, "action": "init_opportunity", "status": "success"}
  ],
  "success_count": 2,
  "failed_count": 0
}
```

---

## 六、上下文继承机制

当用户说"跟进一下这个客户"时，系统从 context 继承实体引用：

```python
context = {
    "current_entity_type": "Customer",
    "current_entity_id": 123
}

# EntityExtractor 优先级：
# 1. context.current_entity_id（置信度 0.95）
# 2. 文本中的 #123（置信度 0.90）
# 3. "这个客户"代词引用（置信度 0.85）
```

---

## 七、业务规则触发

```python
BUSINESS_RULES = [
    {
        "trigger": "keyword",
        "keyword": "签合同",
        "action": "update_stage",
        "target": "合同谈判",
        "description": "用户提到签合同→阶段推进到合同谈判"
    },
    {
        "trigger": "keyword",
        "keyword": "赢单",
        "action": "win_opportunity"
    }
]
```

规则匹配优先级高于关键词匹配（置信度 0.95）。

---

## 八、测试场景

| 场景 | 测试点 |
|------|-------|
| Preview 模式 | `preview=true` 返回 ActionPlan，不执行 |
| 执行模式 | `preview=false` + `action_id` 正确执行 |
| 幂等性 | 相同 `action_id` 返回缓存结果 |
| 风险分级 | LOW/MEDIUM/HIGH 确认逻辑 |
| 上下文继承 | `context.current_entity_id` 补全 |
| 编排执行 | 多步骤顺序执行 + 失败跳过 |
| CRITICAL 拦截 | `dry_run_only=True` 禁止执行 |

---

## 九、后续扩展

| 功能 | 状态 | 说明 |
|------|------|------|
| LLM 意图解析 | 待实现 | 当前仅关键词+规则匹配 |
| 流式响应 | 待实现 | SSE 支持 |
| 多轮对话状态 | 待实现 | Session 管理 |
| 更多 Action 类型 | 按需添加 | 扩展 ACTION_RISK_MAPPING |

---

> **文档版本**：1.0
> **最后更新**：2026-05-25
> **实现状态**：完整（21 端点 + 幂等性 + 风险分级 + 审计）