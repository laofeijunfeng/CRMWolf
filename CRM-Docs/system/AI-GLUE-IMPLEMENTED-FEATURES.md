# AI 对话胶水层已实现功能说明

> 版本：3.1 | 创建日期：2026-05-26 | 状态：**已实现**
> 关联需求：[AI-GLUE-REQUIREMENTS.md](../requirements/AI-GLUE-REQUIREMENTS.md)
> 关联计划：[AI-GLUE-IMPLEMENTATION-PLAN.md](../plans/AI-GLUE-IMPLEMENTATION-PLAN.md)
> 架构合规：[AI-GLUE-ROUTING-ALIGNMENT-PLAN.md](../plans/AI-GLUE-ROUTING-ALIGNMENT-PLAN.md) ✅ 已完成
> 深度整改：[AI-GLUE-DEEP-REMEDIATION-PLAN.md](../plans/AI-GLUE-DEEP-REMEDIATION-PLAN.md) ✅ 已完成
> v0.3 终态：[AI-GLUE-REQUIREMENTS.md](../requirements/AI-GLUE-REQUIREMENTS.md) 17.3 R-A~R-E ✅ 已实现

---

## 一、功能概述

**定位**：纯文本对话驱动的安全写操作层，解决"口语表达"→"系统操作"的交互范式不匹配问题。

**架构合规**：所有写操作通过入口函数层（`action_entry`），满足 **Single Writer 原则** 和 **Preview 单一 Truth 原则**。

**核心能力**：

| 能力 | 说明 |
|------|------|
| **自然语言理解** | 强依赖 LLM，支持口语表达（如"跟进张三客户"、"改成35万"） |
| **多意图分解** | 复合指令拆解（如"跟进张三并设置下周提醒"→两个独立意图） |
| **实体消解** | 模糊引用→精确 ID（"那个客户"、"张三的商机"），通过只读 EntitySearchService |
| **歧义消解** | 多候选追问+描述性选择（"选谈判中的那个"） |
| **槽位收集** | 缺失字段多轮追问 |
| **预览确认** | 所有写操作 preview→确认→execute 安全闭环（单一 truth） |
| **修正处理** | 预览后修正字段重新预览 |
| **上下文继承** | recent_entities + pending 生命周期管理 |
| **显式映射** | INTENT_TO_ACTION_MAP 可 grep 的意图→端点映射 |
| **入口函数模式** | 所有写操作通过 ActionEntry 入口函数（R-1~R-5 合规） |

---

## 二、核心组件一览

| 组件 | 文件 | 核心职责 | LLM 依赖 | 合规状态 |
|------|------|---------|---------|---------|
| **IntentDetector** | `app/glue/core/intent.py` | 意图解析 + 多意图分解 | ✅ 强依赖 | ✅ 合规 |
| **EntityResolver** | `app/glue/core/entity.py` | 实体引用消解（#ID/代词/名称） | ✅ 强依赖 | ✅ 使用 EntitySearchService |
| **SlotCollector** | `app/glue/core/collector.py` | 槽位补充语义理解 | ✅ 强依赖 | ✅ 合规 |
| **CorrectionResolver** | `app/glue/core/corrector.py` | 修正意图检测 + 值提取 | ✅ 强依赖 | ✅ 合规 |
| **CancelDetector** | `app/glue/core/cancel.py` | 取消意图检测 | ✅ 强依赖 | ✅ 合规 |
| **ConfirmationDetector** | `app/glue/core/confirm.py` | 确认意图检测 | ✅ 强依赖 | ✅ 合规 |
| **AmbiguityResolver** | `app/glue/core/ambiguity.py` | 歧义选择理解 | ✅ 描述性选择 | ✅ 合规 |
| **ActionExecutor** | `app/glue/core/executor.py` | 调用 ActionEntry 入口函数 | ❌ 无 LLM | ✅ **R-1~R-3合规** |
| **ActionEntry** | `app/services/ai/action_entry.py` | 入口函数层（新增） | ❌ 规则 + CRUD | ✅ **核心入口** |
| **UserExecCtx** | `app/services/ai/action_entry.py` | 用户执行上下文（R-D 合规） | ❌ 无 LLM | ✅ **R-D合规** |
| **ActionExecutor(CRUD层)** | `app/services/ai/action_executor.py` | CRUD 调用层（降级） | ❌ 仅 CRUD | ✅ **纯 CRUD** |
| **INTENT_TO_ACTION_MAP** | `app/glue/core/action_map.py` | 显式意图→端点映射 | ❌ 无 LLM | ✅ **R-5合规** |
| **PreviewRenderer** | `app/glue/core/renderer.py` | 预览文本渲染 | ❌ 模板渲染 | ✅ 合规 |
| **SafetyGateway** | `app/glue/core/safety.py` | 风险分级判断 | ❌ 规则查询 | ✅ 合规 |
| **DialogueEngine** | `app/glue/core/dialogue.py` | 状态机管理 | 整合所有组件 | ✅ 合规 |
| **SessionManager** | `app/glue/core/session.py` | Session 生命周期 | ❌ Redis 操作 | ✅ 合规 |
| **UserMappingService** | `app/glue/core/user_mapper.py` | 渠道用户映射 | ❌ DB 查询 | ✅ 合规 |
| **DedupManager** | `app/glue/core/dedup.py` | 消息去重 | ❌ Redis SETNX | ✅ 合规 |
| **EntitySearchService** | `app/services/ai/entity_search.py` | 只读实体搜索服务 | ❌ 无 LLM | ✅ **R-4合规** |

---

## 三、入口函数架构（深度整改后新增）

### 3.1 调用链

```
glue/core/executor.py
       │ (进程内调用)
       ▼
app/services/ai/action_entry.py  ← 入口函数层
       │ Preview + Gate + Audit
       │
       ▼ (execute 态)
app/services/ai/action_executor.py  ← CRUD 调用层（降级）
       │
       ▼
CRUD 层
```

### 3.2 ActionEntry 入口函数职责

| 职责 | 说明 |
|------|------|
| **权限校验** | 当前用户能否对该实体做该操作 |
| **业务校验** | 阶段流合法性、字段约束、必填语义 |
| **Preview 构造** | 单一 truth，不重复逻辑 |
| **Execute 执行** | 调用 CRUD 层 |
| **审计留痕** | source="ai"、action_id |

### 3.3 UserExecCtx 用户执行上下文（R-D 合规）

替代裸 db: Session 参数，提供干净的用户上下文：

```python
@dataclass
class UserExecCtx:
    user_id: int               # 用户 ID
    tenant_id: int             # 租户/团队 ID
    roles: List[str]           # 用户角色列表
    is_ai: bool = False        # 是否为 AI 调用
    source: str = "web"        # 调用来源 ("web" | "ai" | "glue")
    user_name: Optional[str] = None  # 用户名称（审计用）

    @classmethod
    def from_user(cls, user: User, is_ai=False, source="web"):
        """从 User 模型创建 UserExecCtx"""
        ...
```

**设计原则**：
- 调用方（HTTP adapter、glue executor）不暴露 db: Session
- 使用 UserExecCtx 作为干净的参数接口
- ActionEntry 内部管理 db Session

### 3.4 入口函数签名

```python
class ActionEntry:
    def __init__(self, db: Session, user_ctx: UserExecCtx):
        # R-D: 使用 UserExecCtx 替代裸 User 参数
        
    def create_follow_up(
        customer_id: int,
        content: str,
        preview: bool = True,
        action_id: Optional[str] = None,
    ) -> ActionEntryResult:
        # 1. 权限校验
        # 2. 生成 action_id
        # 3. Preview 态 → 返回 ActionPlan
        # 4. Execute 态 → 调用 executor → 返回结果
```

### 3.5 R-1~R-5 + R-A~R-E 合规验证

| 规则 | 内容 | 验收结果 |
|------|------|---------|
| **R-1** | 末级调用是入口函数 | ✅ glue → action_entry → CRUD层 |
| **R-2** | Preview 单一 truth | ✅ 无 `_build_preview_from_slots` |
| **R-3** | 入口函数签名 | ✅ `(preview: bool) → ActionEntryResult` |
| **R-4** | action_id 统一归因 | ✅ preview→execute 同一 action_id |
| **R-5** | EntityResolver 只读路径 | ✅ EntitySearchService 调用 |
| **R-A** | Tools 层单一入口 | ✅ C-WRITE-ACCESS 合规检测 |
| **R-B** | HTTP 适配层纯转发 | ✅ GUARDRAIL 注释 + 无业务逻辑 |
| **R-C** | Preview 作为 Gate | ✅ preview→execute 强制闭环 |
| **R-D** | UserExecCtx | ✅ 不暴露 db Session 给调用方 |
| **R-E** | 审计归因 | ✅ action_id + source 字段 |

---

## 三、状态流转

### 3.1 状态枚举

```python
class SessionMode(Enum):
    IDLE = "idle"                   # 空闲，无 pending
    COLLECTING = "collecting"       # 槽位收集
    RESOLVING_ENTITY = "resolving_entity"     # 实体消解
    RESOLVING_AMBIGUITY = "resolving_ambiguity" # 歧义消解
    PREVIEW = "preview"             # 预览等待确认
    EXECUTING = "executing"         # 执行中
    ERROR = "error"                 # 不可恢复错误
```

### 3.2 状态流转图

```
用户输入
   │
   ▼
[IDLE]
   │
   ├─ detect_multi() 检测多意图
   │    ├─ is_multi=true → 创建 pending_queue，取第一个作为 pending
   │    └─ is_multi=false → 单意图处理
   │
   ├─ detect() 意图解析
   │    ├─ needs_entity_resolution → [RESOLVING_ENTITY]
   │    │    │
   │    │    └─ EntityResolver.resolve()
   │    │         ├─ 单候选 → [COLLECTING] 或 [PREVIEW]
   │    │         └─ 多候选 → [RESOLVING_AMBIGUITY]
   │    │              │
   │    │              └─ AmbiguityResolver.resolve()
   │    │                   ├─ 选择成功 → [COLLECTING] 或 [PREVIEW]
   │    │                   └─ 取消 → [IDLE]
   │    │
   │    ├─ missing_slots → [COLLECTING]
   │    │    │
   │    │    └─ SlotCollector.collect()
   │    │         ├─ 补齐 → [PREVIEW]
   │    │         └─ 取消 → [IDLE]
   │    │
   │    └─ 槽位完整 → [PREVIEW]
   │
   ▼
[PREVIEW]
   │
   ├─ CancelDetector.detect() → 取消 → [IDLE]
   ├─ ConfirmationDetector.detect() → 确认 → [EXECUTING]
   ├─ CorrectionResolver.resolve() → 修正
   │    ├─ 涉及实体 → [RESOLVING_ENTITY]
   │    └─ 重新预览 → [PREVIEW]
   │
   ▼
[EXECUTING]
   │
   ├─ ActionExecutor.execute()
   │    ├─ 成功 → 更新 recent_entities → 检查 pending_queue
   │    │    ├─ 有下一个 → 取出作为 pending → [COLLECTING] 或 [PREVIEW]
   │    │    └─ 无下一个 → [IDLE]
   │    └─ 失败 → [ERROR] → [IDLE]
```

---

## 四、核心数据结构

### 4.1 GlueSession（Redis 存储）

```python
@dataclass
class GlueSession:
    v: int = 1                      # 版本号
    tenant_id: str = ""             # 租户 ID
    crm_user_id: int = 0            # CRM 用户 ID
    mode: str = SessionMode.IDLE    # 当前状态
    updated_at: int = 0             # 更新时间戳

    pending: Optional[PendingAction] = None  # 当前待执行动作
    pending_queue: list = None              # 多意图队列（多个 PendingAction）

    recent_entities: Optional[RecentEntities] = None  # 最近操作实体
    history_last_n: list = None                        # 对话历史（最多20条）

    entity_resolution_context: Optional[Dict] = None  # 实体消解上下文
    ambiguity_context: Optional[Dict] = None          # 消歧上下文
```

### 4.2 PendingAction

```python
@dataclass
class PendingAction:
    action_id: str                  # 动作唯一标识
    skill_name: Optional[str]       # Skill 名称
    slots: Dict[str, Any]           # 槽位数据
    missing_slots: list             # 缺失的槽位列表
    preview_snapshot: Dict          # 预览快照
    ambiguity: Optional[Dict]       # 消歧候选
    expires_at: Optional[int]       # 过期时间戳（3分钟）
```

### 4.3 组件返回数据类

```python
# 意图检测结果
@dataclass
class IntentResult:
    skill_id: str                   # Skill ID
    skill_name: str                 # Skill 名称
    slots: Dict[str, Any]           # 提取的槽位
    missing_slots: List[str]        # 缺失的槽位
    needs_entity_resolution: bool   # 是否需要实体消解
    entity_type_hint: Optional[str] # 实体类型提示
    entity_keyword: Optional[str]   # 实体关键词
    error: Optional[str]            # 错误信息

# 多意图检测结果
@dataclass
class MultiIntentResult:
    is_multi: bool                  # 是否为多意图
    intents: List[IntentResult]     # 意图列表
    reasoning: str                  # 判断依据
    error: Optional[str]            # 错误信息

# 实体消解结果
@dataclass
class EntityResolveResult:
    entity_id: Optional[int]        # 消解后的实体 ID
    entity_type: Optional[str]      # 实体类型
    candidates: List[EntityCandidate]  # 候选列表
    error: Optional[str]            # 错误信息

# 修正解析结果
@dataclass
class CorrectionResult:
    is_correction: bool             # 是否为修正意图
    updated_slots: Dict[str, Any]   # 更新后的槽位
    error: Optional[str]            # 错误信息

# 执行结果
@dataclass
class ExecutionResult:
    success: bool                   # 是否成功
    message: str                    # 回执消息
    data: Optional[Dict]            # 返回数据
    error: Optional[str]            # 错误信息
```

---

## 五、LLM 系统提示词模板

### 5.1 IntentDetector - 意图解析

```python
INTENT_PARSE_PROMPT = """你是一个意图识别助手。
从用户输入中识别意图，匹配 Skill，并提取相关实体和槽位。

输出 JSON 格式：
{
    "skill_id": "skill_xxx",
    "skill_name": "创建跟进",
    "slots": {"content": "客户说下周反馈"},
    "missing_slots": ["opportunity_id"],
    "needs_entity_resolution": false,
    "entity_type_hint": null,
    "entity_keyword": null
}
"""
```

### 5.2 IntentDetector - 多意图分解

```python
MULTI_INTENT_PARSE_PROMPT = """你是一个多意图识别助手。
从用户输入中识别是否包含多个意图，并分解为独立的意图列表。

输出 JSON 格式：
{
    "is_multi_intent": true,
    "intents": [
        {"skill_name": "创建跟进", "slots": {...}},
        {"skill_name": "设置提醒", "slots": {...}}
    ],
    "reasoning": "用户同时表达了跟进和设置提醒两个意图"
}
"""
```

### 5.3 EntityResolver - 实体提取

```python
ENTITY_EXTRACTION_PROMPT = """你是一个实体提取助手。
从用户输入中提取实体类型和名称关键词。

输出 JSON 格式：
{
    "entity_type": "Customer" | "Opportunity",
    "name_keyword": "张三",
    "context": "可选的上下文描述"
}
"""
```

### 5.4 CorrectionResolver - 修正意图

```python
CORRECTION_PARSE_PROMPT = """你是一个修正意图识别助手。
判断用户输入是否为修正意图，并提取修正的字段和值。

输出 JSON 格式：
{
    "is_correction": true,
    "corrections": [
        {"field": "amount", "semantic_value": "38万"}
    ]
}
"""
```

---

## 六、使用流程示例

### 6.1 单意图流程

```
用户："给#456加个跟进：客户说下周反馈"

[IDLE]
   │ IntentDetector.detect()
   ├─ skill_name: "创建跟进"
   ├─ slots: {opportunity_id: 456, content: "客户说下周反馈"}
   └─ missing_slots: [] (完整)
   │
   ▼ [PREVIEW]
   │ ActionExecutor.preview()
   ├─ INTENT_TO_ACTION_MAP 查询: ("create_follow_up", "default") → "/ai/actions/create-follow-up"
   ├─ 预览文本："⏱ 预览：创建跟进记录..."
   └─ pending 设置，等待确认
   │
   用户："确认"
   │ ConfirmationDetector.detect() → 确认意图
   │
   ▼ [EXECUTING]
   │ ActionExecutor.execute()
   ├─ 调用 AIActionExecutor.create_follow_up()
   ├─ 创建跟进记录成功 + 审计日志
   └─ 回执："✅ 已记录跟进"
   │
   ▼ [IDLE]
```

### 6.2 实体消解流程

```
用户："跟进张三客户"

[IDLE]
   │ IntentDetector.detect()
   ├─ needs_entity_resolution: true
   ├─ entity_type_hint: "Customer"
   └─ entity_keyword: "张三"
   │
   ▼ [RESOLVING_ENTITY]
   │ EntityResolver.resolve()
   ├─ LLM 提取: entity_type="Customer", name_keyword="张三"
   ├─ EntitySearchService.search_customers(keyword="张三")  ← 只读服务
   └─ 结果: 2个候选 [EntitySearchResult(id=1, name="张三科技"), ...]
   │
   ▼ [RESOLVING_AMBIGUITY]
   │ 系统追问："① 张三科技，② 张三贸易"
   │
   用户："选第一个"
   │ AmbiguityResolver.resolve()
   ├─ 序号匹配 → customer_id=1
   │
   ▼ [COLLECTING]
   │ SlotCollector.collect()
   ├─ 补充跟进内容
   │
   用户："他想了解一下价格"
   │ LLM 理解 → content="他想了解一下价格"
   │
   ▼ [PREVIEW] → ... → [EXECUTING] → [IDLE]
```

### 6.3 多意图流程

```
用户："跟进张三客户，并设置下周提醒"

[IDLE]
   │ IntentDetector.detect_multi()
   ├─ is_multi: true
   ├─ intents: [
   │    {"skill_name": "创建跟进", "slots": {...}},
   │    {"skill_name": "设置提醒", "slots": {...}}
   │ ]
   │
   ▼ pending_queue: [跟进, 设置提醒]
   │ 取第一个作为 pending
   │
   ▼ [RESOLVING_ENTITY] → ... → [PREVIEW] → [EXECUTING]
   │ 执行"创建跟进"成功
   │ recent_entities 更新: customer_id=101
   │
   ▼ 检查 pending_queue
   │ 取第二个作为 pending
   │ customer_id 自动继承（101）
   │
   ▼ [COLLECTING]
   │ 补充提醒日期
   │
   用户："下周三"
   │ LLM 理解 → date_description="下周三"
   │
   ▼ [PREVIEW] → [EXECUTING] → [IDLE]
```

---

## 七、接口契约

### 7.1 入口接口

**POST /glue/v1/inbound**

```yaml
Headers:
  X-Glue-Channel: feishu | wecom | web | test
  X-Glue-Signature: sha256=...  # IM 渠道验签

Body:
{
  "channel_user_id": "ou_xxxx",   # IM open_id
  "channel_chat_id": "oc_xxxx",   # 单聊/群（可选）
  "message_id": "msg_xxx",        # 去重用
  "text": "给#456加个跟进：客户说下周反馈",
  "timestamp": 1719220000,

  # 网页直连时
  "crm_user_id_override": null,
  "session_token": ""             # JWT
}

响应（IM 异步）:
{
  "ok": true,
  "delivery": "async",
  "reply_token": "rp_xxx"
}

响应（网页同步）:
{
  "ok": true,
  "delivery": "sync",
  "reply": {
    "text": "⏱ 预览：...",
    "mode": "preview"
  }
}
```

### 7.2 管理/调试接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/glue/v1/sessions/{tenant}/{crm_user_id}` | GET | 查看 session 状态 |
| `/glue/v1/sessions/{tenant}/{crm_user_id}` | DELETE | 强制清会话 |
| `/glue/v1/health` | GET | 健康检查 |

---

## 八、Redis Key 设计

| Key 模式 | TTL | 用途 |
|---------|-----|------|
| `ai:glue:session:{tenant_id}:{crm_user_id}` | 30分钟 | Session 存储 |
| `ai:glue:action_lock:{action_id}` | 60秒 | 幂等性保护 |
| `ai:glue:message:{message_id}` | 5分钟 | 消息去重 |
| `ai:glue:push:{user}:{opp}:{reason}` | 24小时 | 推送去重 |

---

## 九、开发指引

### 9.1 新增 LLM 增强组件

**模板**：

```python
from app.services.ai_service import ai_service

class NewLLMComponent:
    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    async def process(self, text: str, ...) -> Result:
        # 1. 代码优先处理（强关键词、精确匹配）
        if strong_keyword_match(text):
            return Result(...)

        # 2. LLM 语义理解
        config, api_key = ai_service.get_config_and_key(self.db)
        if not config or not api_key:
            return Result(error="AI 服务未配置，请联系管理员")

        response = await ai_service._stream_chat_collect(
            api_host=config.api_host,
            api_key=api_key,
            model=config.model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ],
            temperature=0.1,
            max_tokens=256,
            response_format={"type": "json_object"}
        )

        # 3. 解析 LLM 响应
        result_data = json.loads(response)
        # 4. 代码计算具体值
        # 5. 返回结果
        return Result(...)
```

### 9.2 新增 Skill/Action 支持

**步骤**：

1. 在 `/ai/actions/` 端点定义 Action（app/api/ai/actions.py）
2. 在 AIActionExecutor 中添加执行方法
3. 在 INTENT_TO_ACTION_MAP 中添加显式映射（**合规要求**）
4. 在 IntentDetector.INTENT_SKILL_MAP 中添加意图映射
5. 在 PreviewRenderer 中添加预览模板（如需特殊渲染）

**INTENT_TO_ACTION_MAP 示例**：

```python
# app/glue/core/action_map.py

INTENT_TO_ACTION_MAP = {
    ("create_follow_up", "default"): "/ai/actions/create-follow-up",
    ("set_reminder", "default"): "/ai/actions/set-reminder",
    ("init_opportunity", "default"): "/ai/actions/init-opportunity",
    ("update_amount", "default"): "/ai/actions/update-amount",
    ("update_stage", "default"): "/ai/actions/update-stage",
    ("win_opportunity", "default"): "/ai/actions/win-opportunity",
    ("lose_opportunity", "default"): "/ai/actions/lose-opportunity",
}
```

**合规检测**：

```bash
# CI/CD 自动检测红线违规
python scripts/check_glue_compliance.py

# 预期输出
✅ glue 层架构合规
   C-1 ✅ 无 CRUD import
   C-4 ✅ 无 Handler import
   C-DS ✅ 无 DynamicSkillService import
```

---

## 十、架构合规说明

### 10.1 红线约束

| 约束 | 说明 | 状态 |
|------|------|------|
| **C-1** | glue 层不得直接导入写型 CRUD | ✅ 已合规 |
| **C-2** | 不得跳过 preview | ✅ 已合规 |
| **C-3** | glue 层不得成为 CRM 业务规则第二实现地 | ✅ 已合规 |
| **C-4** | Handler 不得被 glue 直接 execute() | ✅ 已合规 |
| **C-5** | 不得把 db session 传给胶水层写操作 | ✅ 仅传给 action_entry |
| **C-ACTION** | glue 不得直接导入 ActionExecutor（CRUD层） | ✅ 使用 ActionEntry |
| **C-PREVIEW** | glue 不得自建 Preview 逻辑 | ✅ 单一 truth |

### 10.2 R-1~R-5 + R-A~R-E 合规原则（v0.3 终态）

| 规则 | 内容 | 状态 |
|------|------|------|
| **R-1** | 末级调用是入口函数，不是 CRUD | ✅ 已合规 |
| **R-2** | Preview 必须是单一 truth | ✅ 已合规 |
| **R-3** | 内部调用使用入口函数签名 | ✅ 已合规 |
| **R-4** | action_id 统一归因 | ✅ 已合规 |
| **R-5** | EntityResolver 只读路径 | ✅ 已合规 |
| **R-A** | Tools 层单一入口 | ✅ C-WRITE-ACCESS 检测 |
| **R-B** | HTTP 适配层纯转发（GUARDRAIL） | ✅ 已合规 |
| **R-C** | Preview 作为 Gate | ✅ 已合规 |
| **R-D** | UserExecCtx 替代裸 db Session | ✅ 已合规 |
| **R-E** | 审计归因 | ✅ 已合规 |

### 10.3 C-5 + R-D 设计决策

executor 持有 db session，但：
1. 仅用于创建 UserExecCtx（不暴露裸 db Session）
2. 传递给 ActionEntry（所有写操作在入口函数层）

调用方（HTTP adapter、glue executor）使用 UserExecCtx，不直接传递 db Session，满足 **Single Writer 原则** 和 **R-D 合规**。

### 10.4 合规检测脚本

```bash
# CI/CD 自动检测红线违规
python scripts/check_glue_compliance.py

# 预期输出（v0.3 终态）
✅ glue 层架构合规
   C-1 ✅ 无 CRUD import
   C-4 ✅ 无 Handler import
   C-DS ✅ 无 DynamicSkillService import
   C-ACTION ✅ 无 ActionExecutor import（使用 ActionEntry）
   C-PREVIEW ✅ 无自建 Preview 逻辑
   C-WRITE-ACCESS ✅ 无直接写型数据操作（R-A 合规）

合规路径验证：
   R-3 ✅ glue → action_entry 入口函数
```

---

## 十一、限制与注意事项

| 限制 | 说明 |
|------|------|
| **强依赖 AI** | 所有语义理解组件必须依赖 LLM，AI 不可用时返回错误，不降级 |
| **Preview 强制** | 所有写操作必须先 preview，确认后执行 |
| **pending 过期** | 3分钟过期，过期后需重新开始 |
| **历史长度** | 对话历史最多保留 20 条 |
| **候选数量** | 歧义候选最多显示 5 个 |

---

## 十二、测试验收标准

| # | 场景 | 验收标准 |
|---|------|---------|
| 1 | 单意图完整流程 | `"给#456加跟进"` → preview → 确认 → execute → 回执 |
| 2 | 多意图流程 | `"跟进张三并设置提醒"` → 两个意图依次执行 |
| 3 | 实体消解 | `"跟进张三"` → LLM 提取 → EntitySearchService 搜索 → 候选追问 |
| 4 | 歧义消解 | `"选第一个"` → 序号匹配 → 锁定 ID |
| 5 | 修正句 | `"金额改成38万"` → LLM 检测修正 → 重新 preview |
| 6 | 取消 | `"取消"` → LLM 检测取消 → 清 pending → IDLE |
| 7 | 确认 | `"可以"` → LLM 检测确认 → EXECUTING |
| 8 | pending 过期 | 过期后确认 → 提示"已过期" → 不执行 |
| 9 | **架构合规** | `scripts/check_glue_compliance.py` 检测通过 |

---

> **文档版本**：3.1
> **最后更新**：2026-05-26（v0.3 终态 Phase 7-10 完成）
> **实现状态**：✅ 已完成 + ✅ 深度整改完成 + ✅ v0.3 终态完成
> **维护团队**：CRMWolf 开发团队