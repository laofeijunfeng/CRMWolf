---
status: completed
created: 2026-05-25
updated: 2026-05-25
related_requirements: ../requirements/AI-OPENAPI-REQUIREMENTS.md
related_pr: -
---

# AI OpenAPI 实施计划

> **状态：✅ 已完成** | 完成日期：2026-05-25
> 版本：1.0 | 创建日期：2026-05-25
> 配套需求文档：[AI-OPENAPI-REQUIREMENTS.md](../requirements/AI-OPENAPI-REQUIREMENTS.md)

---

## 一、项目概览

### 1.1 目标
创建 `/ai/` 专用 API 层，解决现有 `/api/v1/` RESTful API 与 AI 使用方式的"三层架构不匹配"问题。

### 1.2 核心收益

| 收益 | 说明 |
|------|------|
| AI 可知晓业务规则 | 元数据接口暴露阶段赢率、联动逻辑 |
| AI 可最小化字段输入 | 原子动作支持最小字段集 + 渐进补全 |
| AI 操作风险可控 | preview 模式 + 风险分级 + 强制确认 |
| 操作可追溯 | action_id 幂等性 + 全链路审计 |

### 1.3 工作量评估

| 层级 | 工作量 | 优先级 | 风险 |
|------|--------|--------|------|
| Phase 0：基础设施 | 2 天 | P0 | 低 |
| Phase 1：元数据层 | 3 天 | P1 | 低 |
| Phase 2：原子动作层 | 10 天 | P2 | 中 |
| Phase 3：意图层 | 7 天 | P3 | 高 |
| Phase 4：编排与审计 | 4 天 | P4 | 中 |

**总计**：约 26 工作日（可并行压缩至 15-20 天）

---

## 二、分阶段实施计划

### Phase 0：基础设施搭建

**目标**：建立代码骨架和通用协议

#### 2.0.1 目录结构

```
CRM-Server/app/
├── api/ai/                      # AI 专用路由
│   ├── __init__.py
│   ├── deps.py                  # 依赖注入（认证、权限）
│   ├── intents.py               # 意图层路由
│   ├── actions.py               # 动作层路由
│   ├── metadata.py              # 元数据层路由
│   └── orchestrate.py           # 编排路由
│   └── logs.py                  # 审计日志路由
│
├── services/ai/                 # AI 业务逻辑
│   ├── __init__.py
│   ├── intent_parser.py         # 意图解析服务
│   ├── rule_engine.py           # 规则匹配引擎
│   ├── action_executor.py       # 动作执行器
│   ├── orchestrator.py          # 编排调度器
│   └── audit_logger.py          # 审计日志服务
│
├── schemas/ai/                  # AI 专用 Schema
│   ├── __init__.py
│   ├── common.py                # 通用响应结构
│   ├── intent.py                # 意图相关 Schema
│   ├── action.py                # 动作相关 Schema
│   ├── metadata.py              # 元数据 Schema
│   └── audit.py                 # 审计 Schema
│
└── constants/
    └── ai_rules.py              # AI 可读业务规则配置
```

#### 2.0.2 通用交互协议

**请求结构** (`schemas/ai/common.py`)：
```python
class AIRequestBase(BaseModel):
    preview: bool = True           # 是否仅预览
    action_id: Optional[str] = None # 幂等 ID（执行时必填）
    context: Optional[dict] = None  # 上下文信息

class AIResponseBase(BaseModel):
    action_id: str
    status: Literal["preview", "completed", "failed", "rejected"]
    plan: Optional[ActionPlan] = None
    confidence: float
    requires_confirmation: bool
    message: str
    error: Optional[str] = None

class ActionPlan(BaseModel):
    description: str               # 变更描述（人类可读）
    changes: List[FieldChange]     # 变更详情

class FieldChange(BaseModel):
    field: str
    from_value: Optional[Any] = None
    to_value: Any
```

#### 2.0.3 认证依赖

```python
# api/ai/deps.py
async def get_ai_user(
    token: str = Depends(oauth2_scheme),
    api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> User:
    """
    双重认证：
    1. JWT Token（Web 端）
    2. API Key（MCP/外部调用）
    """
    # 复用现有 auth 服务
    user = await authenticate_user(token)
    if api_key:
        validate_api_key(api_key)
    return user
```

#### 2.0.4 任务清单

| 任务 | 文件 | 状态 |
|------|------|------|
| 创建目录结构 | `api/ai/`, `services/ai/`, `schemas/ai/` | 待办 |
| 定义通用 Schema | `schemas/ai/common.py` | 待办 |
| 定义认证依赖 | `api/ai/deps.py` | 待办 |
| 注册路由到 main.py | `main.py` | 待办 |
| 编写单元测试骨架 | `tests/unit/test_ai_base.py` | 待办 |

---

### Phase 1：元数据层（Metadata Layer）

**目标**：向 AI 暴露系统静态配置与业务规则

#### 2.1.1 接口清单

| 接口 | 路径 | 说明 |
|------|------|------|
| 商机阶段赢率 | `GET /ai/metadata/stages` | 阶段→赢率映射 |
| 业务规则库 | `GET /ai/metadata/rules` | 关键词→动作映射 |
| 实体关系 | `GET /ai/metadata/entities` | 必填字段、关联实体 |
| 权限范围 | `GET /ai/metadata/permissions` | 当前用户可操作范围 |
| 状态枚举 | `GET /ai/metadata/enums` | 所有状态枚举值 |

#### 2.1.2 返回示例

**商机阶段** (`/ai/metadata/stages`)：
```json
{
  "stages": [
    {
      "name": "需求确认",
      "win_rate": 0.2,
      "next_stages": ["方案报价", "方案演示"],
      "allowed_actions": ["edit", "advance"]
    },
    {
      "name": "方案报价",
      "win_rate": 0.4,
      "next_stages": ["商务谈判", "合同谈判"],
      "allowed_actions": ["edit", "advance", "lose"]
    }
  ]
}
```

**实体关系** (`/ai/metadata/entities`)：
```json
{
  "entities": [
    {
      "name": "Opportunity",
      "required_fields": ["customer_id", "name"],
      "optional_fields": ["amount", "expected_close_date"],
      "relations": ["Customer", "FollowUp", "Contract"]
    }
  ]
}
```

#### 2.1.3 实现文件

| 文件 | 内容 |
|------|------|
| `api/ai/metadata.py` | 路由定义 |
| `services/ai/metadata_service.py` | 数据聚合逻辑 |
| `constants/ai_rules.py` | 业务规则配置 |

#### 2.1.4 数据来源

| 元数据 | 来源 |
|--------|------|
| 商机阶段 | `opportunity_stage_template` 表 |
| 业务规则 | `constants/ai_rules.py`（新增配置文件） |
| 实体关系 | 硬编码 Schema 定义 |
| 权限范围 | `permission_service.get_user_permissions()` |
| 状态枚举 | `GLOSSARY.md` 对应代码常量 |

#### 2.1.5 任务清单

| 任务 | 文件 | 状态 |
|------|------|------|
| 创建业务规则配置 | `constants/ai_rules.py` | 待办 |
| 实现阶段元数据接口 | `api/ai/metadata.py` | 待办 |
| 实现规则元数据接口 | 同上 | 待办 |
| 实现实体关系接口 | 同上 | 待办 |
| 实现权限范围接口 | 同上 | 待办 |
| 编写单元测试 | `tests/unit/test_ai_metadata.py` | 待办 |

---

### Phase 2：原子动作层（Action Layer）

**目标**：执行具体系统操作，支持 preview 模式

#### 2.2.1 接口清单

| 接口 | 路径 | 风险等级 | 置信度阈值 |
|------|------|---------|-----------|
| 创建跟进 | `POST /ai/actions/create-follow-up` | 低 | ≥ 0.85 |
| 设置提醒 | `POST /ai/actions/set-reminder` | 低 | ≥ 0.85 |
| 初始化商机 | `POST /ai/actions/init-opportunity` | 中 | ≥ 0.90 |
| 更新金额 | `POST /ai/actions/update-amount` | 中 | ≥ 0.90 |
| 更新阶段 | `POST /ai/actions/update-stage` | 中 | ≥ 0.90 |
| 关联实体 | `POST /ai/actions/link-opportunity` | 中 | ≥ 0.90 |
| 赢单 | `POST /ai/actions/win-opportunity` | 高 | 强制确认 |
| 输单 | `POST /ai/actions/lose-opportunity` | 高 | 强制确认 |
| 线索转化 | `POST /ai/actions/convert-lead` | 高 | 强制确认 |

#### 2.2.2 风险分级策略

```python
class RiskLevel(Enum):
    LOW = "low"       # 自动执行（置信度≥阈值）
    MEDIUM = "medium" # 置信度不足需确认
    HIGH = "high"     # 强制人工确认
    CRITICAL = "critical" # 禁止执行，仅生成草稿

RISK_CONFIG = {
    RiskLevel.LOW: {"auto_threshold": 0.85, "force_confirm": False},
    RiskLevel.MEDIUM: {"auto_threshold": 0.90, "force_confirm": False},
    RiskLevel.HIGH: {"auto_threshold": 1.0, "force_confirm": True},
    RiskLevel.CRITICAL: {"auto_threshold": 1.0, "force_confirm": True, "dry_run_only": True}
}
```

#### 2.2.3 核心动作实现示例

**创建跟进** (`actions/create-follow-up`)：
```python
async def create_follow_up(
    request: CreateFollowUpRequest,
    user: User = Depends(get_ai_user),
    db: Session = Depends(get_db)
):
    action_id = request.action_id or generate_action_id()

    # Preview 模式
    if request.preview:
        plan = ActionPlan(
            description=f"为客户 {request.customer_id} 创建跟进记录",
            changes=[FieldChange(field="content", to_value=request.content)]
        )
        return AIResponseBase(
            action_id=action_id,
            status="preview",
            plan=plan,
            confidence=calculate_confidence(request),
            requires_confirmation=False  # 低风险
        )

    # 执行模式
    follow_up = await action_executor.create_follow_up(
        db, user, request.customer_id, request.content, request.follow_up_time
    )
    await audit_logger.log(action_id, "create_follow_up", follow_up.id, user)

    return AIResponseBase(
        action_id=action_id,
        status="completed",
        message="跟进记录已创建",
        confidence=1.0
    )
```

#### 2.2.4 动作执行器设计

```python
# services/ai/action_executor.py
class ActionExecutor:
    """桥接现有 services，不直接操作数据库"""

    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user

    async def create_follow_up(self, customer_id, content, follow_up_time):
        # 调用现有 follow_up_service
        return await follow_up_service.create(
            self.db, customer_id, content, follow_up_time, self.user.id
        )

    async def init_opportunity(self, customer_id, name):
        # 最小字段集初始化
        return await opportunity_service.create_minimal(
            self.db, customer_id, name, self.user.id
        )
```

#### 2.2.5 任务清单

| 任务 | 文件 | 状态 |
|------|------|------|
| 定义动作 Schema | `schemas/ai/action.py` | 待办 |
| 实现风险分级配置 | `constants/ai_rules.py` | 待办 |
| 实现 create-follow-up | `api/ai/actions.py` | 待办 |
| 实现 set-reminder | 同上 | 待办 |
| 实现 init-opportunity | 同上 | 待办 |
| 实现 update-amount | 同上 | 待办 |
| 实现 update-stage | 同上 | 待办 |
| 实现 win/lose（强制确认） | 同上 | 待办 |
| 实现 convert-lead（强制确认） | 同上 | 待办 |
| 编写单元测试 | `tests/unit/test_ai_actions.py` | 待办 |

---

### Phase 3：意图层（Intent Layer）

**目标**：自然语言 → 结构化意图 + 实体

#### 2.3.1 意图枚举池

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

INTENT_DESCRIPTIONS = {
    IntentType.CREATE_FOLLOW_UP: "创建跟进记录",
    IntentType.CREATE_OPPORTUNITY: "创建商机",
    # ...
}
```

#### 2.3.2 接口设计

| 接口 | 路径 | 说明 |
|------|------|------|
| 意图解析 | `POST /ai/intents/parse` | 用户文本→意图列表+置信度 |
| 实体提取 | `POST /ai/intents/extract` | 用户文本→结构化实体 |
| 规则匹配 | `GET /ai/rules/match` | 意图→推荐动作序列 |

#### 2.3.3 意图解析实现

```python
# services/ai/intent_parser.py
class IntentParser:
    def __init__(self, llm_client):
        self.llm = llm_client

    async def parse(self, text: str, context: dict = None) -> IntentResult:
        prompt = f"""
        分析用户意图，返回最可能的意图类型。

        可选意图：{[i.value for i in IntentType]}

        用户输入：{text}
        上下文：{context or "无"}

        返回 JSON 格式：
        {{
          "intent": "意图类型",
          "confidence": 0.0-1.0,
          "reasoning": "判断依据"
        }}
        """
        result = await self.llm.chat(prompt)
        return IntentResult.parse(result)
```

#### 2.3.4 上下文继承机制

```python
class EntityExtractor:
    async def extract(self, text: str, target_entity: str, context: dict):
        # 上下文补全：如用户说"把那个改一下"
        # 从 context.previous_entities 中继承实体
        if "那个" in text and context.get("previous_entity_id"):
            entity_id = context["previous_entity_id"]
            # 补全实体信息
            return ExtractedEntity(
                id=entity_id,
                confidence=0.95,
                source="context_inherit"
            )
        # 正常提取
        return await self._extract_from_text(text, target_entity)
```

#### 2.3.5 任务清单

| 任务 | 文件 | 状态 |
|------|------|------|
| 定义意图枚举 | `constants/ai_rules.py` | 待办 |
| 实现意图解析服务 | `services/ai/intent_parser.py` | 待办 |
| 实现实体提取服务 | `services/ai/entity_extractor.py` | 待办 |
| 实现规则匹配服务 | `services/ai/rule_engine.py` | 待办 |
| 实现意图路由 | `api/ai/intents.py` | 待办 |
| 编写单元测试 | `tests/unit/test_ai_intents.py` | 待办 |

---

### Phase 4：编排与审计

**目标**：多动作编排 + 全链路追溯

#### 2.4.1 编排接口

```python
# POST /ai/actions/orchestrate
class OrchestrateRequest(BaseModel):
    actions: List[ActionRequest]     # 动作序列
    depends_on: Dict[str, str]       # 依赖关系
    confidence_threshold: float = 0.9

class OrchestrateResponse(BaseModel):
    orchestration_id: str
    status: Literal["preview", "executing", "completed", "partial_failed"]
    results: List[ActionResult]
    rollback_available: bool
```

#### 2.4.2 幂等性机制

```python
# services/ai/idempotency.py
class IdempotencyManager:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.ttl = 3600  # 1 小时过期

    async def check_or_lock(self, action_id: str) -> bool:
        """检查是否已执行，未执行则锁定"""
        key = f"ai:action:{action_id}"
        if await self.redis.exists(key):
            return False  # 已执行
        await self.redis.setex(key, self.ttl, "locked")
        return True  # 可执行

    async def record_result(self, action_id: str, result: dict):
        """记录执行结果"""
        key = f"ai:action:{action_id}:result"
        await self.redis.setex(key, self.ttl, json.dumps(result))
```

#### 2.4.3 审计日志

```python
# services/ai/audit_logger.py
class AuditLogger:
    async def log(self, action_id: str, action_type: str, entity_id: int, user: User):
        log_entry = {
            "action_id": action_id,
            "intent_id": user.context.get("intent_id"),
            "action_type": action_type,
            "entity_id": entity_id,
            "user_id": user.id,
            "source": "ai",
            "timestamp": datetime.utcnow()
        }
        # 写入操作日志表（标记 source="ai"）
        await operation_log_service.create(log_entry)

    async def query_logs(self, filters: LogFilters) -> List[LogEntry]:
        return await operation_log_service.query(
            source="ai",
            **filters
        )
```

#### 2.4.4 任务清单

| 任务 | 文件 | 状态 |
|------|------|------|
| 实现幂等性管理 | `services/ai/idempotency.py` | 待办 |
| 实现编排服务 | `services/ai/orchestrator.py` | 待办 |
| 实现审计日志服务 | `services/ai/audit_logger.py` | 待办 |
| 实现编排路由 | `api/ai/orchestrate.py` | 待办 |
| 实现日志查询路由 | `api/ai/logs.py` | 待办 |
| 编写单元测试 | `tests/unit/test_ai_orchestrate.py` | 待办 |

---

## 三、依赖关系

```
Phase 0 ──┬── Phase 1（可并行）
          │
          └── Phase 2（依赖 Phase 0）
                   │
                   └── Phase 3（依赖 Phase 2 Schema）
                            │
                            └── Phase 4（依赖 Phase 2+3）
```

**并行建议**：
- Phase 0 + Phase 1 可并行开发（约 3 天）
- Phase 2 独立开发（约 10 天）
- Phase 3 可在 Phase 2 完成前启动 Schema 定义（约 5 天提前量）
- Phase 4 在 Phase 2 完成后启动（约 4 天）

---

## 四、验收标准

### 4.1 功能验收

| 验收项 | 标准 |
|--------|------|
| 元数据接口 | 所有 5 个接口返回正确数据 |
| Preview 模式 | preview=true 返回变更计划，不执行 |
| 执行模式 | preview=false + action_id 正确执行 |
| 幂等性 | 相同 action_id 重复调用无副作用 |
| 风险分级 | 高风险动作强制 requires_confirmation=true |
| 审计日志 | 所有操作标记 source="ai"，可查询 |

### 4.2 测试验收

| 测试类型 | 覆盖率要求 |
|----------|-----------|
| 单元测试 | ≥ 80% |
| 集成测试 | 核心流程覆盖 |
| E2E 测试 | 多轮对话场景 |

---

## 五、风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|---------|
| LLM 意图解析不稳定 | 误判意图 | 固定枚举池 + 置信度阈值 + 人工兜底 |
| 现有 services 不兼容 | 需改动核心代码 | ActionExecutor 桥接层隔离变更 |
| Preview 与执行不一致 | 用户误操作 | Preview 返回实际将执行的 SQL/参数 |
| 幂等性存储依赖 Redis | Redis 故障降级 | Redis 不可用时启用数据库唯一约束 |

---

## 六、后续集成

| 集成形态 | 技术路径 | 依赖条件 |
|---------|---------|---------|
| MCP Server | OpenAPI Spec → MCP Tools | Phase 1-2 完成 |
| CLI 工具 | HTTP 客户端封装 | Phase 1-2 完成 |
| IM 机器人 | IM 消息 → `/ai/` → 卡片回传 | Phase 1-3 完成 |

---

> **文档版本**：1.0
> **最后更新**：2026-05-25
> **维护团队**：CRMWolf 开发团队