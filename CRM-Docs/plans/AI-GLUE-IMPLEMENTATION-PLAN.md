# AI 对话胶水层实施计划

> 版本：3.0 | 创建日期：2026-05-25 | 更新日期：2026-05-26 | 状态：**已实现 ✅**
> 配套需求：[AI-GLUE-REQUIREMENTS.md](../requirements/AI-GLUE-REQUIREMENTS.md)
> 架构合规：[AI-GLUE-ROUTING-ALIGNMENT-PLAN.md](AI-GLUE-ROUTING-ALIGNMENT-PLAN.md) ✅ 已完成

---

## 一、实施阶段概览

| Phase | 内容 | 工时估算 | 状态 | 完成日期 |
|-------|------|---------|------|---------|
| Phase 0 | 目录结构搭建 + 配置基础 | 0.5 天 | ✅ 已完成 | 2026-05-25 |
| Phase 1 | inbound 接口 + session 管理 | 1.5 天 | ✅ 已完成 | 2026-05-25 |
| Phase 2 | 状态机 + IntentDetector + EntityResolver（**LLM 增强**） | 2.5 天 | ✅ 已完成 | 2026-05-26 |
| Phase 3 | ActionPlanner + PreviewRenderer + SafetyGateway | 1.5 天 | ✅ 已完成 | 2026-05-25 |
| Phase 4 | CorrectionResolver + 歧义消解 + 确认/取消检测（**LLM 增强**） | 1.5 天 | ✅ 已完成 | 2026-05-26 |
| Phase 5 | 渠道适配（飞书/企微/web） | 1 天 | ✅ 已完成 | 2026-05-25 |
| Phase 6 | ActionExecutor + 多意图解析 + 测试 | 1 天 | ✅ 已完成 | 2026-05-26 |
| Phase 7 | **架构合规整改**（路由对齐 + 红线约束） | 1 天 | ✅ 已完成 | 2026-05-26 |
| **总计** | | **~10 天** | **✅ 已完成** | |

---

## 已实现文件清单

| 文件 | 状态 | 说明 |
|------|------|------|
| `app/glue/__init__.py` | ✅ | 模块初始化 |
| `app/glue/config.py` | ✅ | Redis key、TTL、渠道配置、SessionMode |
| `app/glue/router.py` | ✅ | Glue 路由注册 |
| `app/glue/api/inbound.py` | ✅ | POST /glue/v1/inbound，支持多意图 |
| `app/glue/api/admin.py` | ✅ | session 查看/清除/health |
| `app/glue/core/session.py` | ✅ | GlueSession, PendingAction, SessionManager，支持 pending_queue |
| `app/glue/core/dialogue.py` | ✅ | DialogueEngine 状态机，整合所有组件，支持多意图队列 |
| `app/glue/core/intent.py` | ✅ | IntentDetector + MultiIntentResult，detect_multi 多意图分解 |
| `app/glue/core/entity.py` | ✅ | EntityResolver，LLM 语义提取 + **EntitySearchService 只读搜索** |
| `app/glue/core/collector.py` | ✅ | SlotCollector，LLM 槽位理解 |
| `app/glue/core/corrector.py` | ✅ | CorrectionResolver，LLM 修正意图检测 |
| `app/glue/core/ambiguity.py` | ✅ | AmbiguityResolver，LLM 描述性选择 |
| `app/glue/core/cancel.py` | ✅ | CancelDetector，LLM 取消意图检测 |
| `app/glue/core/confirm.py` | ✅ | ConfirmationDetector，LLM 确认意图检测 |
| `app/glue/core/planner.py` | ✅ | ActionPlanner，slots → /ai/actions/ preview |
| `app/glue/core/renderer.py` | ✅ | PreviewRenderer，diff 文本生成 |
| `app/glue/core/safety.py` | ✅ | SafetyGateway，风险分级判断 |
| `app/glue/core/executor.py` | ✅ | ActionExecutor，**通过 AIActionExecutor 调用 CRUD（合规版）** |
| `app/glue/core/action_map.py` | ✅ | **INTENT_TO_ACTION_MAP 显式映射（R-5合规）** |
| `app/glue/core/user_mapper.py` | ✅ | UserMappingService，channel_user_id → crm_user_id |
| `app/glue/core/dedup.py` | ✅ | DedupManager，消息去重 |
| `app/glue/core/dnd.py` | ✅ | 免打扰策略 |
| `app/glue/channels/base.py` | ✅ | ChannelSender 抽象接口 |
| `app/glue/channels/feishu.py` | ✅ | 飞书适配骨架 |
| `app/glue/channels/wecom.py` | ✅ | 企微适配骨架 |
| `app/glue/channels/web.py` | ✅ | 网页直连适配 |
| `app/glue/worker/push.py` | ✅ | 推送任务骨架 |
| `app/services/ai/entity_search.py` | ✅ | **只读实体搜索服务（R-4合规）** |
| `scripts/check_glue_compliance.py` | ✅ | **红线约束合规检测脚本** |

---

## 一、实施阶段概览（原文档保留）

---

## 二、Phase 0：目录结构搭建

### 2.1 任务清单

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 0.1 | 创建 glue 目录结构 | `glue/__init__.py` | 初始化 |
| 0.2 | 创建配置文件 | `glue/config.py` | Redis key、TTL、渠道配置 |
| 0.3 | 创建测试骨架 | `tests/glue/__init__.py` | 测试目录 |

### 2.2 config.py 内容

```python
# glue/config.py

class GlueConfig:
    # Redis Key 前缀
    SESSION_KEY_PREFIX = "ai:glue:session"
    ACTION_LOCK_KEY_PREFIX = "ai:glue:action_lock"
    PUSH_KEY_PREFIX = "ai:glue:push"

    # TTL 配置（秒）
    SESSION_TTL = 1800          # 30 分钟
    PENDING_EXPIRE = 180        # 3 分钟
    ACTION_LOCK_TTL = 60        # 60 秒

    # 历史记录限制
    HISTORY_MAX_LENGTH = 20

    # 渠道配置
    SUPPORTED_CHANNELS = ["feishu", "wecom", "web", "test"]
```

---

## 三、Phase 1：inbound 接口 + session 管理

### 3.1 任务清单

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 1.1 | inbound 接口骨架 | `glue/api/inbound.py` | POST /glue/v1/inbound |
| 1.2 | admin 接口 | `glue/api/admin.py` | session 查看/清除/health |
| 1.3 | session 管理 | `glue/core/session.py` | Redis load/save/clear |
| 1.4 | 用户映射服务 | `glue/core/user_mapper.py` | channel_user_id → crm_user_id |
| 1.5 | 消息去重 | `glue/core/dedup.py` | message_id 去重 |

### 3.2 session.py 核心接口

```python
class SessionManager:
    def load(self, tenant_id: str, crm_user_id: int) -> GlueSession
    def save(self, session: GlueSession) -> bool
    def clear(self, tenant_id: str, crm_user_id: int) -> bool
    def set_pending(self, session: GlueSession, pending: PendingAction) -> bool
    def clear_pending(self, session: GlueSession) -> bool
    def update_recent_entities(self, session: GlueSession, entity_type: str, entity_id: int) -> bool
    def add_history(self, session: GlueSession, role: str, text: str) -> bool
```

### 3.3 inbound.py 接口定义

```python
@router.post("/inbound")
async def inbound(
    request: InboundRequest,
    x_glue_channel: str = Header(...),
    x_glue_signature: Optional[str] = Header(None),
):
    """
    1. 验签（按渠道）
    2. message_id 去重
    3. 解析 crm_user_id
    4. 推入队列（IM 异步）或直接处理（web 同步）
    5. 返回 reply_token
    """
```

---

## 四、Phase 2：状态机 + IntentDetector + EntityResolver（LLM 增强）

### 4.1 任务清单

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 2.1 | 状态机定义 | `glue/core/dialogue.py` | SessionMode 枚举 + dispatch |
| 2.2 | IntentDetector | `glue/core/intent.py` | **强依赖 LLM** 调 `/ai/intents/parse` + `/ai/intents/extract` |
| 2.3 | EntityResolver | `glue/core/entity.py` | **强依赖 LLM** #ID / "这个/那个" / 自然语言消歧 |
| 2.4 | 槽位收集逻辑 | `glue/core/collector.py` | missing_fields → COLLECTING，**强依赖 LLM** 语义理解 |

### 4.2 核心原则：强依赖 AI

**所有语义理解组件必须强依赖 AI 服务**：
- AI 服务不可用时，返回友好错误提示，不降级到规则匹配
- 用户体验优先：支持自然表达，而非强制用户学习关键词

### 4.3 intent.py IntentDetector（LLM 增强）

```python
class IntentDetector:
    async def detect(self, text: str, session: GlueSession) -> DetectResult:
        # 1. 调 /ai/intents/parse（LLM 意图解析）
        # 2. 调 /ai/intents/extract（LLM 实体提取）
        # 3. 结合 recent_entities 补全
        # 4. 返回 intent + slots + missing_fields + ambiguity
        # 5. AI 不可用时返回 error，不降级
```

### 4.4 entity.py EntityResolver（LLM 增强）

```python
class EntityResolver:
    """强依赖 LLM 语义理解"""

    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    async def resolve(self, text: str, entity_type: str, session: GlueSession) -> EntityResolveResult:
        # 1. #ID 精确匹配 → entity_id（置信度 0.90）【代码逻辑】
        # 2. "这个客户" → session.recent_entities.customer_id（置信度 0.85）【代码逻辑】
        # 3. "张三客户"/"张三的商机" → LLM 提取语义 → CRUD 搜索 → 返回 ID 或 candidates
        # 4. 返回 EntityResolveResult(entity_id, entity_type, confidence, candidates, error)
        # 5. AI 服务不可用时返回 error，不降级
```

**LLM 职责**: 从自然语言提取实体类型 + 名称关键词
**代码职责**: CRUD 搜索 + 候选构建 + 准确性保障

---

## 五、Phase 3：ActionPlanner + PreviewRenderer

### 5.1 任务清单

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 3.1 | ActionPlanner | `glue/core/planner.py` | slots → /ai/actions/ preview |
| 3.2 | PreviewRenderer | `glue/core/renderer.py` | ActionPlan → diff 文本 |
| 3.3 | SafetyGateway | `glue/core/safety.py` | requires_confirmation 判断 |

### 5.2 planner.py ActionPlanner

```python
class ActionPlanner:
    # intent → /ai/actions/ 端点映射
    INTENT_ACTION_MAP = {
        "create_follow_up": "/ai/actions/create-follow-up",
        "init_opportunity": "/ai/actions/init-opportunity",
        "update_opportunity": "/ai/actions/update-amount",
        ...
    }

    def plan(self, intent: str, slots: Dict) -> PlanResult:
        # 1. 确定端点
        # 2. 组装请求（preview=true）
        # 3. 调用 /ai/actions/
        # 4. 返回 action_id + plan + requires_confirmation
```

### 5.3 renderer.py PreviewRenderer

```python
class PreviewRenderer:
    def render(self, plan: ActionPlan, entity_info: Dict) -> str:
        """
        输出:
        ⏱ 预览：更新商机金额
          商机：CRM项目升级（#456）
          金额：300,000 → 350,000
          阶段：（不变）方案报价

        回「确认」执行；要改就说如「金额 38 万」；取消回「取消」。
        """
```

---

## 六、Phase 4：CorrectionResolver +歧义消解（LLM 增强）

### 6.1 任务清单

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 4.1 | CorrectionResolver | `glue/core/corrector.py` | **强依赖 LLM** "不对/改/应该是" 语义解析 |
| 4.2 | AmbiguityResolver | `glue/core/ambiguity.py` | **强依赖 LLM** 描述性选择理解（如"选谈判中的那个"） |
| 4.3 | CancelDetector | `glue/core/cancel.py` | **强依赖 LLM** "取消/算了/不用了/等等" 意图判断 |
| 4.4 | ConfirmationDetector | `glue/core/confirm.py` | **强依赖 LLM** 确认意图判断（如"可以/那就这样吧"） |

### 6.2 corrector.py CorrectionResolver（LLM 增强）

```python
class CorrectionResolver:
    """强依赖 LLM 语义理解"""

    async def resolve(self, text: str, pending: PendingAction) -> CorrectionResult:
        # 1. LLM 判断是否修正意图 + 提取修正字段和修正值
        # 2. 代码计算具体值（如 "35万" → 350000）
        # 3. merge 到 pending.slots
        # 4. 返回更新后的 slots
        # 5. AI 服务不可用时返回 error，不降级到关键词匹配
```

**LLM 职责**: 判断修正意图 + 提取修正字段（amount/stage/customer等）+ 提取语义值
**代码职责**: 数值计算（35万→350000）、日期计算、数据校验

### 6.3 ambiguity.py AmbiguityResolver（LLM 增强）

```python
class AmbiguityResolver:
    """强依赖 LLM 描述性选择理解"""

    async def resolve(self, text: str, candidates: List[EntityCandidate]) -> AmbiguityResult:
        # 1. 检测序号选择（①②③ / 1 2 3）【代码逻辑，优先级最高】
        # 2. 检测名称精确匹配【代码逻辑，优先级次高】
        # 3. LLM 理解描述性选择（如"选谈判中的那个"/"最近跟进的那个"）
        # 4. 检测取消（"取消/都不是"）
        # 5. 返回 selected_id 或 None
        # 6. AI 服务不可用时，仅支持序号/名称选择，返回提示
```

**LLM 职责**: 理解描述性选择意图
**代码职责**: 序号解析、名称精确匹配、候选列表构建

### 6.4 cancel.py CancelDetector（LLM 增强）

```python
class CancelDetector:
    """强依赖 LLM 意图判断"""

    async def detect(self, text: str) -> CancelResult:
        # 1. LLM 判断是否取消/暂停意图
        # 2. 支持自然表达："算了"/"等等，我再想想"/"不，先别"
        # 3. AI 服务不可用时返回 error，不降级
```

### 6.5 confirm.py ConfirmationDetector（LLM 增强）

```python
class ConfirmationDetector:
    """强依赖 LLM 意图判断"""

    async def detect(self, text: str) -> ConfirmationResult:
        # 1. LLM 判断是否确认意图
        # 2. 支持自然表达："可以"/"那就这样吧"/"没问题"/"行"
        # 3. AI 服务不可用时返回 error，不降级
```

---

## 七、Phase 5：渠道适配

### 7.1 任务清单

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 5.1 | ChannelSender 抽象 | `glue/channels/base.py` | 抽象接口定义 |
| 5.2 | 飞书适配 | `glue/channels/feishu.py` | open_id 解析 + 飞书 API |
| 5.3 | 企微适配 | `glue/channels/wecom.py` | userid 解析 +企微回调 |
| 5.4 | 网页适配 | `glue/channels/web.py` | JWT session + 同步返回 |

### 7.2 base.py ChannelSender

```python
class ChannelSender(ABC):
    channel: str

    @abstractmethod
    async def send(self, reply_token: str, text: str) -> bool:
        pass

    @abstractmethod
    async def resolve_user(self, channel_user_id: str) -> Optional[int]:
        pass

    @abstractmethod
    def verify_signature(self, body: bytes, signature: str) -> bool:
        pass
```

### 7.3 渠道配置

| 渠道 | 用户映射 | 验签方式 | 回复方式 |
|------|---------|---------|---------|
| 飞书 | open_id → UserMapping 表 |飞书签名算法 | reply_token → 飞书 API |
| 企微 | userid → UserMapping 表 |企微签名算法 | reply_token →企微 API |
| 网页 | JWT session | 无 | 直接 HTTP 返回 |

---

## 八、Phase 6：主动推送 + ActionExecutor + 测试

### 8.1 任务清单

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 6.1 | 推送任务 | `glue/worker/push.py` | 定时任务：停留提醒 |
| 6.2 | 免打扰策略 | `glue/core/dnd.py` | active_hours + 用户设置 |
| 6.3 | ActionExecutor 初版 | `glue/core/executor.py` | 调用 DynamicSkillService（**后重构为合规版**） |
| 6.4 | 单元测试 | `tests/glue/` | session/intent/planner/renderer |

### 8.2 ActionExecutor 合规重构

**重构前（违规）**：
```python
from app.services.skills import dynamic_skill_service

result = await dynamic_skill_service.execute_action(
    db=self.db,
    skill_name=skill_name,
    action_name=action_name,
    params=pending.slots,
    user_id=self.user_id,
)
```

**重构后（合规）**：
```python
from app.glue.core.action_map import get_action_endpoint
from app.services.ai.action_executor import ActionExecutor as AIActionExecutor

# 获取显式映射端点
endpoint = get_action_endpoint(intent_type, "default")

# 直接调用 AI 层 ActionExecutor
executor = AIActionExecutor(self.db, user)
result = executor.create_follow_up(...)  # 或其他方法
```

---

## 九、Phase 7：架构合规整改（路由对齐）

### 9.1 整改背景

发现 glue 层违反红线约束：
- **C-1 违规**：glue → DynamicSkillService → Handler → CRUD 间接写操作
- **C-4 违规**：Handler 被 glue 层直接调用
- **C-5 部分**：db session 被传入 glue 层

### 9.2 任务清单

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 7.1 | 创建 INTENT_TO_ACTION_MAP | `glue/core/action_map.py` | 显式映射表（R-5合规） |
| 7.2 | 重构 ActionExecutor | `glue/core/executor.py` | 调用 AIActionExecutor 而非 DynamicSkillService |
| 7.3 | 创建只读搜索服务 | `services/ai/entity_search.py` | EntitySearchService（R-4合规） |
| 7.4 | 重构 EntityResolver | `glue/core/entity.py` | 使用 EntitySearchService |
| 7.5 | 创建合规检测脚本 | `scripts/check_glue_compliance.py` | CI/CD 阶段自动检测 |
| 7.6 | 更新需求文档 | `AI-GLUE-REQUIREMENTS.md` | 补充 C-1~C-5 红线约束 |

### 9.3 合规验收结果

```
✅ glue 层架构合规
   C-1 ✅ 无 CRUD import
   C-4 ✅ 无 Handler import
   C-DS ✅ 无 DynamicSkillService import
   C-5 ⚠️ executor 持有 db session，但仅传递给 ai/ 层（满足 Single Writer 原则）
```

### 9.4 核心设计决策

**C-5 部分合规说明**：
- executor 持有 db session，但仅用于：
  1. 获取 User 对象（传递给 AIActionExecutor）
  2. 传递给 AIActionExecutor（所有写操作在 ai/ 层）
- 不直接调用 CRM CRUD 写操作
- 满足 **Single Writer 原则**：所有写操作通过 `/ai/actions/` 层

---

## 十、技术依赖

### 10.1 外部依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| Redis | 7.x | Session 存储、幂等性锁 |
| HTTPX | 0.24+ | 调用 `/ai/` 内部接口 |
| FastAPI | 0.100+ | inbound 接口 |

### 10.2 内部依赖

| 依赖 | 状态 | 用途 |
|------|------|------|
| `/ai/intents/parse` | 已实现 | 意图解析 |
| `/ai/intents/extract` | 已实现 | 实体提取 |
| `/ai/actions/*` | 已实现 | preview/execute（**所有写操作入口**） |
| `/ai/metadata/entities` | 已实现 | 实体定义 |
| `ai_rules.py` | 已实现 | 风险分级、意图枚举 |
| `AIActionExecutor` | 已实现 | AI 层写操作执行器 |
| `EntitySearchService` | 已实现 | 只读实体搜索（**glue 专用**） |

---

## 十一、风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| IM webhook 超时 | 企微/飞书要求 ≤3s 响应 | 推队列 + worker 异步处理 |
| pending 过期处理 | 用户可能回复慢 | expires_at 检测 + 提示过期 |
| 用户映射缺失 | open_id 未绑定 | 返回友好提示："请先绑定账号" |
|歧义候选过多 | 用户选择困难 | 最多显示 5 个候选 |
| 修正句识别不准 | 误判为新意图 | 关键词优先 + 意图置信度辅助 |
| **架构违规** | 绕过 `/ai/actions/` 写操作 | **合规检测脚本 + CI/CD** |

---

## 十二、验收标准

| # | 场景 | 验收标准 |
|---|------|---------|
| 1 | 标准流程 | `"给#456加跟进"` → preview → 确认 → execute → `/ai/logs` 可查 |
| 2 | 取消 | `"取消"` → pending 清空 → 无副作用 |
| 3 |歧义 | `"跟进张三"`（2候选） → 追问 → 选择 → 锁定 |
| 4 | 修正 | `"金额改成38万"` → re-preview → →380000 |
| 5 | 幂等 | 重复 `"确认"` → 不重复执行 |
| 6 | 权限 | 无权限操作 → 友好文本提示 |
| 7 | 超时 | pending 过期 → 提示重新开始 |
| 8 | 代词 | `"改成35万"` → 自动补全 opportunity_id |
| 9 | **合规** | `scripts/check_glue_compliance.py` 检测通过 |

---

## 十三、后续扩展

| 功能 | Phase | 说明 |
|------|-------|------|
| 多轮复合意图 | Phase+ | "跟进+改金额+推进"一次性处理（需 LLM 多意图分解） |
| 卡片交互 | Phase+ |飞书/企微富文本卡片确认 |
| 会话持久化 | Phase+ | DB 存储（当前仅 Redis） |
| 查询语义理解 | Phase+ | 自然语言查询（如"看看我负责的商机"、"本月赢单了几个"） |

> **注**: LLM 语义增强已整合至 Phase 2-4 核心实现，不再作为后续扩展。

---

> **文档版本**：3.0
> **最后更新**：2026-05-26
> **实现状态**：✅ 已完成（含架构合规整改）
> **维护团队**：CRMWolf 开发团队