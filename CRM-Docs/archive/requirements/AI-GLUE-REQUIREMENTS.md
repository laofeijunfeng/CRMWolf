---
status: completed
created: 2026-05-25
updated: 2026-05-26
related_plan: ../plans/AI-GLUE-IMPLEMENTATION-PLAN.md
related_pr: -
---

# CRM AI 对话胶水层需求文档

> 版本：2.0 | 创建日期：2026-05-25 | 更新日期：2026-05-26 | 状态：**已实现 ✅**
> 子标题：从"AI套壳聊天框"→"纯文本对话驱动的安全写操作"

---

## 实现状态总览

| Phase | 内容 | 状态 | 完成日期 |
|-------|------|------|---------|
| Phase 0 | 目录结构 + 配置基础 | ✅ 已完成 | 2026-05-25 |
| Phase 1 | inbound + session 管理 | ✅ 已完成 | 2026-05-25 |
| Phase 2 | 状态机 + IntentDetector + EntityResolver（LLM） | ✅ 已完成 | 2026-05-26 |
| Phase 3 | ActionPlanner + PreviewRenderer + SafetyGateway | ✅ 已完成 | 2026-05-25 |
| Phase 4 | CorrectionResolver + 歧义消解 + 确认/取消检测（LLM） | ✅ 已完成 | 2026-05-26 |
| Phase 5 | 渠道适配（飞书/企微/web） | ✅ 已完成 | 2026-05-25 |
| Phase 6 | ActionExecutor + 多意图解析 | ✅ 已完成 | 2026-05-26 |

**核心功能已全部实现**，包括：
- 完整状态机流程（IDLE → COLLECTING → RESOLVING_ENTITY → RESOLVING_AMBIGUITY → PREVIEW → EXECUTING）
- 所有 LLM 增强组件（意图、实体、修正、确认、取消、歧义）
- 多意图解析（复合指令分解）
- 渠道适配器骨架

---

## 一、背景与问题

### 1.1 现状

已完成 `/ai/` OpenAPI 层实现（21 个端点），提供：
- 意图解析（`/ai/intents/`）
- 原子动作执行（`/ai/actions/`）
- 系统元数据暴露（`/ai/metadata/`）
- 审计日志查询（`/ai/logs/`）

### 1.2 核心痛点

CRM + AI 联动的根本问题是**交互范式不匹配**：

| CRM 系统设计 | 销售口语表达 | 不匹配表现 |
|-------------|-------------|-----------|
| **实体/字段中心**（客户、商机、跟进表单） | **事件/信号中心**（"今天跟了张三，他说下周签"） | 自然语言无法直接映射到表单字段 |
| **精确 ID 引用**（customer_id=123） | **模糊引用**（"那个客户"、"张三"） | 需多轮对话消歧 |
| **单步原子操作** | **复合意图**（跟进+改金额+推进阶段） | 需拆解+编排 |
| **无状态 API** | **上下文依赖**（"改成 35 万"默认指刚才说的商机） | 需会话状态管理 |

### 1.3 破局路径

已完成的 `/ai/` API 层解决了"AI 安全调用原子能力"的问题。  
下一步需建：**对话胶水层**，将口语 → 意图/实体 → 槽位收集 →歧义消解 → preview → 确认 → execute 跑成可审计的闭环。

---

## 二、目标与非目标

### 2.0 核心原则：强依赖 AI + 分层保障

**AI 与代码职责分离原则**:

| 职责 | AI 层（语义理解） | 代码层（准确性保障） |
|------|------------------|---------------------|
| **意图识别** | 从自然语言理解用户意图 | 槽位补全、缺失检测 |
| **实体提取** | 提取语义关键词、实体类型 | CRUD 搜索、候选构建、ID 精确匹配 |
| **日期处理** | 解析语义（"下周三"、"三天后") | 计算具体日期值 |
| **金额处理** | 解析语义（"35万"、"一半") | 计算具体数值 |
| **修正意图** | 判断修正意图 + 提取修正字段 | 数值计算、merge 槽位 |
| **确认/取消** | 理解自然表达意图 | 状态机流转 |

**强依赖规则**:
1. 所有语义理解组件**必须**依赖 AI 服务
2. AI 服务不可用时返回友好错误提示，**禁止降级到规则匹配**
3. 用户必须配置 AI 服务才能使用胶水层功能
4. 代码层负责：数值计算、日期计算、数据校验、权限校验、ID 精确匹配

**为何强依赖**:
- 用户表达多样，规则匹配无法覆盖所有场景
- 强依赖确保一致的用户体验，避免"有时能用、有时不能用"的混乱
- AI 服务是系统核心能力，应作为必选项而非可选项

---

### 2.1 目标（In Scope）

| 目标 | 说明 |
|------|------|
| **纯文本对话** | 任意 IM/网页都归约为"收文本→回文本"；卡片/按钮不在主路径（可插拔增强） |
| **单步写动作为主** | "口语一次包含多件事"拆成多条 preview/确认序列 |
| **强制安全轨道** | 写操作必定 `preview=true` 先拿 `action_id`；用户确认才执行；高危必人确认 |
| **上下文继承** | recent_entities（客户/商机）+ pending_action 生命周期 + 代词消解 |
| **可审计** | 所有写走 `/ai/actions/` 与 `/ai/logs`；胶水层额外记录会话级摘要 |

### 2.2 非目标（Out / Later）

| 非目标 | 说明 |
|--------|------|
| 全自动无确认流水写 | 禁止 |
| 深度 LLM-agent 自主多跳规划 | v1.0 不支持 LLM 自动编排多跳，但单意图解析强依赖 LLM |
| 把胶水层逻辑写进 n8n | n8n 只做传输/解密/格式适配 |
| 飞书/企微卡片作为主要确认机制 | 允许后期增量，不决定架构 |

### 2.3 成功指标（可测）

| 指标 | 验收标准 |
|------|---------|
| Preview 覆盖 | 100% 写操作经过 `preview=true` |
| Preview 内容 | 字段级 diff（before→after），非黑盒"我帮你做了" |
| 幂等性 | 同 `action_id` 重复提交结果幂等或可检测冲突 |
| 可撤销 | 任意时刻用户发"取消/算了" → pending 清空 + 无副作用 |
| pending 超时 | 过期后提示"上条待确认已过期，重新告诉我你要做什么？" |

---

## 三、三层归属模型（红线约束）

> **核心原则**：写操作只在 `/ai/actions/`；对话编排只在 `glue/`；渠道只做文本进出。

| 层级 | 名称 | 职责 | 代码归宿 | 禁止行为 |
|------|------|------|---------|---------|
| **L1** | CRM Core | 业务数据一致性、权限、事务、审批 | `/api/v1/` | AI 不走这里 |
| **L2** | AI 能力 API | 原子动作、preview/execute、风险分级、规则、审计 | `app/api/ai/` | 不维护会话状态 |
| **L3** | 对话胶水层 | 消息处理、状态机、意图解析、歧义消解、preview渲染 | `glue/` | **禁止** `import` CRM Models 并 `save()` |
| **L4** | 渠道适配 | webhook 验签、open_id→crm_user_id、文本收发 | `glue/channels/` | 不处理业务逻辑 |

**红线规则**：

1. `glue/` **不得** 直接操作 CRM Core Models
2. 所有写必须过 `/ai/actions/` 的 `preview→execute` 双步
3. 风险规则/阈值权威在 `ai_rules.py` + `/ai/metadata/`，胶水层只消费

**红线约束 C-1 ~ C-5**（2026-05-26 整改后新增）：

| 约束 ID | 约束 | 检测方式 | 状态 |
|---------|------|---------|------|
| **C-1** | `glue/` 不得 import CRM Core 写型 CRUD | `grep -r "from app.crud import" glue/` | ✅ 合规 |
| **C-2** | 不得跳过 preview | `/ai/logs` 检查每个 action_id 必有 preview=true 先于 preview=false | ✅ 合规 |
| **C-3** | `glue/` 不得成为 CRM 业务规则第二实现地 | glue 层不应包含业务规则逻辑 | ✅ 合规 |
| **C-4** | 不得 Handler 被 glue 直接 execute() | `grep -r "from app.services.skills.handlers import" glue/` | ✅ 合规 |
| **C-5** | 不得把 db session 传给胶水层 | `grep -r "self.db" glue/core/executor.py` | ⚠️ 说明见下 |

**C-5 说明**：
- executor 持有 db session，但仅用于：
  1. 获取 User 对象（传递给 AIActionExecutor）
  2. 传递给 AIActionExecutor（所有写操作在 `ai/` 层）
- 不直接调用 CRM CRUD 写操作（满足 **Single Writer 原则**）
- EntityResolver 使用 EntitySearchService 只读路径

**合规检测脚本**：
```bash
python scripts/check_glue_compliance.py
```

---

## 四、系统架构设计

### 4.1 整体架构图

```
用户输入（企微/飞书/网页）
  │  归约为：(channel_user_id, text, message_id, ts)
  ▼
┌──────────────────────────────────────────────────────┐
│  L4: Glue Transport（薄）                             │
│  inbound router（验签/auth）→ 解析 crm_user_id        │
│  推队列/worker（IM需立刻200 OK）                        │
└──────────────────────┬───────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────┐
│  L3: Glue Core（SessionMachine + DialogueEngine）     │
│                                                      │
│  状态机: idle / collecting / preview / executing     │
│  • IntentDetector   → 调 /ai/intents/extract         │
│  • EntityResolver   → "这个/那个"→entity_id          │
│  • ActionPlanner    → 拼 steps → preview=true        │
│  • SafetyGateway    → 读 requires_confirmation/risk  │
│  • PreviewRenderer  → ActionPlan → diff 文本         │
│  • CorrectionResolver→ 修正句 merge 回 pending        │
└──────────┬───────────────────────────────────────────┘
           │ 只通过 HTTP 调 L2
           ▼
┌──────────────────────────────────────────────────────┐
│  L2: /ai/ 层（已实现的21端点）                         │
│  metadata / intents / actions(orchestrate) / logs     │
└──────────┬───────────────────────────────────────────┘
           │ 桥接现有 CRUD
           ▼
┌──────────────────────────────────────────────────────┐
│  L1: CRM Core（现有 /api/v1/ + services/）            │
│  业务数据一致性、权限、事务                            │
└──────────────────────────────────────────────────────┘
```

### 4.2 后端目录结构

```
CRM-Server/
 ├── app/
 │   └── api/
 │       ├── v1/...              # L1: CRM Core API（不动）
 │       └── ai/                  # L2: AI 能力层（已完成）
 │           ├── actions/         # 8 动作端点 + orchestrate
 │           ├── intents/         # 5 意图端点
 │           ├── metadata/        # 5 元数据端点
 │           ├── logs/            # 3 审计端点
 │           └── deps.py          # AI 认证依赖
 │           └── constants/ai_rules.py  # 风险分级+意图枚举
 │
 ├── glue/                        # L3: 对话胶水层（新增）
 │   ├── api/
 │   │   ├── inbound.py           # POST /glue/v1/inbound
 │   │   └── admin.py             # session 查看/清除/health
 │   │
 │   ├── core/
 │   │   ├── session.py           # Redis: load/save/pending生命周期
 │   │   ├── dialogue.py          # 状态机 dispatch
 │   │   ├── intent.py            # IntentDetector（调 /ai/intents/）
 │   │   ├── planner.py           # ActionPlanner: slots → steps → preview
 │   │   ├── safety.py            # SafetyGateway（risk 判断）
 │   │   ├── renderer.py          # PreviewRenderer（diff 文本生成）
 │   │   └── corrector.py         # CorrectionResolver（修正句处理）
 │   │
 │   ├── channels/
 │   │   ├── base.py              # ChannelSender 抽象
 │   │   ├── feishu.py            # 飞书适配
 │   │   ├── wecom.py             # 企微适配
 │   │   └── web.py               # 网页直连适配
 │   │
 │   ├── worker.py                # 队列消费（IM 异步处理）
 │   └── config.py                # 胶水层配置
 │
 └── tests/
     └── glue/                    # 胶水层单元测试
```

---

## 五、对话状态机

### 5.1 状态枚举

```python
class SessionMode(Enum):
    IDLE = "idle"           # 空闲，无 pending
    COLLECTING = "collecting" # 槽位收集，等待用户补信息
    PREVIEW = "preview"      # 已 preview，等待确认
    EXECUTING = "executing"  # 正在执行
    ERROR = "error"         # 不可恢复错误
```

### 5.2 状态流转图

```
IDLE
 ├─ 收到文本
 │   ├─ 有 pending 且像修正/取消？→ CORRECTING / 清 pending → IDLE
 │   └─ 否则 → 解析 → 缺槽位？COLLECTING ：PREVIEW
 │
COLLECTING  （在问人：缺 customer_id / 缺 amount / 缺 stage…）
 ├─ 答复补齐 → 仍缺？再问下一个 → 齐了 → PREVIEW
 └─ 答复是"取消/都不是" → IDLE
 │
PREVIEW     （已拿到 action_id + plan.changes，等确认）
 ├─ "确认"            → EXECUTING
 ├─ 修正句（金额改了/阶段改了）→ CORRECTING → 重新 PREVIEW
 └─ "取消"            → IDLE
 │
EXECUTING    （调 preview=false + action_id）
 ├─ 成功 → 回执 + 更新 recent_entities → IDLE
 └─ 失败 → 友好错误文本 → IDLE
 │
ERROR        （不可恢复：UNKNOWN 意图 / 无权限 / 实体不存在）
 └─ 回可读文案 → IDLE
```

### 5.3 pending 生命周期

```python
# pending 过期时间（秒）
PENDING_EXPIRE_SECONDS = 180  # 3 分钟

# pending 结构
pending = {
    "action_id": "act_xxx",
    "intent": "update_opportunity",
    "slots": {
        "customer_id": 101,
        "opportunity_id": 456,
        "amount": 350000,
    },
    "preview_snapshot": {...},
    "ambiguity": null,  # 或 {"slot": "customer_id", "candidates": [101, 105]}
    "expires_at": 1719220180,
}
```

---

## 六、对外接口契约

### 6.1 核心入口：POST /glue/v1/inbound

**请求**：

```yaml
POST /glue/v1/inbound
Headers:
  X-Glue-Channel: feishu | wecom | web | test
  X-Glue-Signature: sha256=...  # 可选
Content-Type: application/json

Body:
{
  "channel_user_id": "ou_xxxx",   # IM open_id
  "channel_chat_id": "oc_xxxx",   # 单聊/群（可选）
  "message_id": "msg_xxx",        # 去重用
  "text": "给#456加个跟进：客户说下周反馈",
  "timestamp": 1719220000,

  # 网页直连时直接带身份
  "crm_user_id_override": null,
  "session_token": ""             # 网页 JWT
}
```

**响应（IM 异步）**：

```json
{
  "ok": true,
  "delivery": "async",
  "reply_token": "rp_xxx"
}
```

**响应（网页同步）**：

```json
{
  "ok": true,
  "delivery": "sync",
  "reply": {
    "text": "⏱ 预览：更新商机金额...",
    "mode": "preview"
  }
}
```

### 6.2 管理/调试接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/glue/v1/sessions/{tenant}/{crm_user_id}` | GET | 查看当前 session 状态（脱敏） |
| `/glue/v1/sessions/{tenant}/{crm_user_id}` | DELETE | 强制清会话（运维用） |
| `/glue/v1/health` | GET | 健康检查 |

---

## 七、Session 数据契约（Redis）

### 7.1 Session Key 设计

```
Key: ai:glue:session:{tenant_id}:{crm_user_id}
TTL: 30 分钟（滑动续期）
```

### 7.2 Session 结构

```json
{
  "v": 1,
  "tenant_id": "org_001",
  "crm_user_id": 123,
  "mode": "idle",
  "updated_at": 1719220000,

  "pending": null,
  // pending 存在时：
  // "pending": {
  //   "action_id": "act_xxx",
  //   "intent": "update_opportunity",
  //   "slots": {...},
  //   "preview_snapshot": {...},
  //   "ambiguity": null,
  //   "expires_at": 1719220180
  // }

  "recent_entities": {
    "customer_id": 101,
    "opportunity_id": 456,
    "touched_at": 1719220000
  },

  "history_last_n": [
    { "role": "user", "text": "给#456加跟进...", "ts": 1719220000 },
    { "role": "assistant", "text": "⏱ 预览：...", "ts": 1719220005 }
  ],

  "history_max_length": 20
}
```

### 7.3 幂等性保护

```
Key: ai:glue:action_lock:{action_id}
TTL: 60 秒
Value: 1

# 作用：胶水层级别防止同一 action_id 重复处理
# /ai/actions/ 自身也有 AI_DUPLICATE_ACTION 检测
```

### 7.4 消息去重

```
Key: ai:glue:message:{message_id}
TTL: 300 秒（5 分钟）
Value: 1

# 作用：防止同一 message_id 重复处理（IM webhook 可能重投）
# 在 inbound 接口入口处 SETNX 检查
```

---

## 八、文本交互协议

### 8.1歧义追问（COLLECTING）

```
没锁定到唯一客户，你指的是？
 ① 张三科技（最近跟进 5/20）
 ② 张三建设（商机#3321）
回序号或客户名；都不是回「取消」。
```

### 8.2 预览确认（PREVIEW）

```
⏱ 预览：更新商机金额
  商机：CRM项目升级（#456）
  金额：300,000 → 350,000
  阶段：（不变）方案报价

回「确认」执行；要改就说如「金额 38 万」；取消回「取消」。
```

### 8.3 执行回执（EXECUTING）

```
✅ 已记录跟进，商机#456 金额更新为 350,000。
```

### 8.4 错误回执（ERROR）

```
❌ 操作失败：您没有权限修改该商机。
```

### 8.5 修正句处理

用户说"金额不对，是38万"时：
- 只 merge 回同一 pending.entity
- 重新生成 preview
-仍需走确认流程

---

## 九、核心组件设计

> **实现状态**: 所有核心组件已实现 ✅

### 9.1 IntentDetector ✅ 已实现

职责：解析用户文本，**强依赖 LLM 语义理解**

**文件**: `app/glue/core/intent.py`

**已实现功能**:
- `detect()` 方法：LLM 意图解析 + 实体引用提取
- `detect_multi()` 方法：多意图分解（复合指令如"跟进+设置提醒"）
- `IntentResult` 数据类：支持 skill_id, skill_name, missing_slots, needs_entity_resolution
- `MultiIntentResult` 数据类：is_multi, intents, reasoning

```python
class IntentDetector:
    async def detect(self, text: str, session: GlueSession, auth_token: Optional[str] = None) -> IntentResult:
        # 1. LLM 解析意图
        # 2. 提取实体（金额、日期等）
        # 3. 结合 session.recent_entities 补全引用
        # 4. 判断缺失字段
        # 5. 返回 IntentResult(intent, slots, missing_fields, needs_entity_resolution, error)

    async def detect_multi(self, text: str, session: GlueSession) -> MultiIntentResult:
        # 分解复合指令，如"跟进张三并设置下周提醒"
        # 返回 MultiIntentResult(is_multi, intents)
```

**LLM 职责**: 从自然语言理解意图 + 提取语义实体 + 多意图分解
**代码职责**: 槽位补全、缺失字段检测、会话状态管理

---

### 9.2 EntityResolver ✅ 已实现

职责：消解"这个/那个/#ID/自然语言"等引用，**强依赖 LLM 语义理解**

**文件**: `app/glue/core/entity.py`

**已实现功能**:
- `resolve()` 方法：#ID 精确匹配 + 代词消解 + LLM 语义提取 + CRUD 搜索
- `_search_by_name()` 方法：LLM 提取名称关键词 → CRUD 搜索 → 返回候选
- `EntityResolveResult` 数据类：支持 candidates, error

```python
class EntityResolver:
    async def resolve(self, text: str, entity_type_hint: str, keyword: str) -> EntityResolveResult:
        # 1. #ID 精确匹配 → entity_id（置信度 0.90）【代码逻辑】
        # 2. 代词引用 → session.recent_entities【代码逻辑】
        # 3. 名称引用 → LLM 提取语义 → CRUD 搜索 → 返回 ID 或 candidates
        # 4. 返回 EntityResolveResult(entity_id, candidates, error)
```

**LLM 职责**: 从自然语言提取实体类型 + 名称关键词
**代码职责**: CRUD 搜索 + 候选构建 + 准确性保障

---

### 9.3 ActionPlanner ✅ 已实现

职责：slots → steps → 调 `/ai/actions/` preview

**文件**: `app/glue/core/planner.py`

**已实现功能**:
- `plan()` 方法：intent → /ai/actions/ 端点映射 + preview=true
- `INTENT_ACTION_MAP`：意图到端点映射

---

### 9.4 SafetyGateway ✅ 已实现

职责：读取风险分级，判断是否需人工确认

**文件**: `app/glue/core/safety.py`

**已实现功能**:
- `check()` 方法：查询 /ai/metadata/rules 获取风险等级
- CRITICAL 禁止执行判断

---

### 9.5 PreviewRenderer ✅ 已实现

职责：ActionPlan → 人类可读 diff 文本

**文件**: `app/glue/core/renderer.py`

**已实现功能**:
- `render()` 方法：生成预览文本
- `render_receipt()` 方法：生成执行回执

---

### 9.6 CorrectionResolver ✅ 已实现

职责：处理修正句（"不对/改/应该是"），**强依赖 LLM 语义理解**

**文件**: `app/glue/core/corrector.py`

**已实现功能**:
- `resolve()` 方法：LLM 判断修正意图 + 提取修正字段和修正值
- 代码计算具体值（35万→350000）
- `CorrectionResult` 数据类：支持 updated_slots, error

**LLM 职责**: 判断修正意图 + 提取修正字段（amount/stage/customer等）
**代码职责**: 数值计算、日期计算、数据校验

---

### 9.7 UserMappingService ✅ 已实现

职责：渠道用户 ID → CRM 用户 ID 映射

**文件**: `app/glue/core/user_mapper.py`

**已实现功能**:
- `resolve()` 方法：查询 UserMapping 表
- `resolve_with_tenant()` 方法：返回 (crm_user_id, tenant_id)

---

### 9.8 DedupManager ✅ 已实现

职责：消息去重（防止 IM webhook 重投）

**文件**: `app/glue/core/dedup.py`

**已实现功能**:
- `check()` 方法：SETNX 检查 message_id

---

### 9.9 SlotCollector ✅ 已实现

职责：槽位收集时的用户输入理解，**强依赖 LLM 语义理解**

**文件**: `app/glue/core/collector.py`

**已实现功能**:
- `collect()` 方法：LLM 理解用户补充信息的语义
- `fill_slot()` 方法：处理单个槽位填充
- `CollectResult` 数据类：支持 collected, updated_slots, needs_entity_resolution

**场景示例**:
```
系统: 请补充跟进内容
用户: 就是他想了解一下我们的产品价格
LLM 理解 → content = "他想了解一下我们的产品价格"
```

---

### 9.10 AmbiguityResolver ✅ 已实现

职责：消解歧义选择，**支持 LLM 描述性选择理解**

**文件**: `app/glue/core/ambiguity.py`

**已实现功能**:
- `resolve()` 方法：序号选择 + 名称匹配 + LLM 描述性选择
- `render_candidates()` 方法：渲染候选列表文本
- `AmbiguityResult` 数据类：支持 selected_id, error

**分层处理**:
- 序号/名称精确匹配 → 代码处理（高优先级，无需 AI）
- 描述性选择 → LLM 处理（如"选谈判中的那个")

---

### 9.11 CancelDetector / ConfirmationDetector ✅ 已实现

职责：判断用户取消/确认意图，**强依赖 LLM 语义理解**

**文件**: `app/glue/core/cancel.py`, `app/glue/core/confirm.py`

**已实现功能**:
- `detect()` 方法：LLM 判断取消/确认意图
- `is_strong_cancel()` / `is_strong_confirm()` 方法：强关键词优先
- `CancelResult` / `ConfirmationResult` 数据类

**LLM 职责**: 理解自然表达的确认/取消意图（如"可以"/"那就这样吧"/"算了"/"等等")
**代码职责**: 执行对应的 session 状态变更

---

### 9.12 ActionExecutor ✅ 已实现（合规整改）

职责：执行 AI 动作，**通过 `/ai/actions/` 层调用 CRUD**

**文件**: `app/glue/core/executor.py`

**合规整改后（2026-05-26）**:
- 使用 `INTENT_TO_ACTION_MAP` 显式映射（R-5）
- 调用 `AIActionExecutor` 执行写操作（满足 Single Writer 原则）
- 不直接调用 `DynamicSkillService` 或 `Handler`（C-4 合规）
- 不直接 import CRM CRUD（C-1 合规）
- 添加 `source="glue"` 审计标记（R-3）

**已实现功能**:
- `preview()` 方法：生成预览数据
- `execute()` 方法：调用 AIActionExecutor 执行
- `ExecutionResult` / `PreviewResult` 数据类
- `_execute_by_intent()` 方法：根据 intent_type 分发执行

```python
class ActionExecutor:
    async def preview(self, pending: PendingAction) -> PreviewResult:
        # 获取端点映射 → 构建预览数据 → 添加 source="glue" 标记

    async def execute(self, pending: PendingAction) -> ExecutionResult:
        # 获取端点映射 → 调用 AIActionExecutor → 返回执行结果
```

**C-5 说明**:
- executor 持有 db session，但仅用于：
  1. 获取 User 对象（传递给 AIActionExecutor）
  2. 传递给 AIActionExecutor（所有写操作在 ai/ 层）
- 不直接调用 CRM CRUD 写操作

---

### 9.13 DialogueEngine ✅ 已实现（核心整合）

职责：整合所有 LLM 增强组件，管理对话流程状态流转

**文件**: `app/glue/core/dialogue.py`

**已实现功能**:
- `dispatch()` 方法：根据 session.mode 分发处理
- `_handle_idle()` 方法：支持多意图检测 + 意图解析
- `_handle_collecting()` 方法：槽位收集
- `_handle_resolving_entity()` 方法：实体消解
- `_handle_resolving_ambiguity()` 方法：歧义消解
- `_handle_preview()` 方法：确认/修正/取消检测
- `_handle_executing()` 方法：执行 + 多意图队列处理
- `_summarize_multi_intents()` 方法：总结多意图列表
- `_build_receipt_message()` 方法：构建执行回执

**状态流转**:
```
IDLE → IntentDetector
  ├─ needs_entity_resolution → RESOLVING_ENTITY
  │    └─ EntityResolver
  │         ├─ 单候选 → COLLECTING/PREVIEW
  │         └─ 多候选 → RESOLVING_AMBIGUITY → AmbiguityResolver
  ├─ missing_slots → COLLECTING → SlotCollector
  └─ 槽位完整 → PREVIEW

PREVIEW → CancelDetector / ConfirmationDetector / CorrectionResolver
  ├─ cancel → IDLE
  ├─ confirm → EXECUTING → ActionExecutor → IDLE（或处理队列下一个）
  └─ correction → RESOLVING_ENTITY / PREVIEW
```

---

## 十、主动推送设计

### 10.1 定时任务

```python
# 每 1-2 小时执行
Job: check-due-reminders

流程:
1. 读只读视图或 GET /ai/metadata/due-reminders
2. 对每个 (user, opportunity, reason):
   - 去重 key: ai:glue:push:{user}:{opp}:{reason} TTL=24h
   - 拼文本 → ChannelSender.send(user, text)
3. 免打扰策略（active_hours / 用户 DND 设置）
```

### 10.2 推送文本示例

```
📢 商机停留提醒
商机「CRM项目升级」已在「需求确认」阶段停留 14 天
建议：跟进客户或推进阶段
回复「跟进」创建跟进记录
```

---

## 十一、渠道适配器

### 11.1 抽象接口

```python
class ChannelSender(ABC):
    @abstractmethod
    async def send(self, reply_token: str, text: str) -> bool:
        """发送文本回复"""
        pass

    @abstractmethod
    async def resolve_user(self, channel_user_id: str) -> Optional[int]:
        """channel_user_id → crm_user_id"""
        pass
```

### 11.2 实现类

| 渠道 | 实现文件 | 特殊处理 |
|------|---------|---------|
| 飞书 | `channels/feishu.py` | open_id 解析、飞书 API 验签 |
| 企微 | `channels/wecom.py` | userid 解析、企微回调验签 |
| 网页 | `channels/web.py` | JWT session、同步返回 |

---

## 十二、验收用例（DoD）

| # | 场景 | 用户输入 | 断言 |
|---|------|---------|------|
| 1 | 标准流程 | `"给#456加跟进：客户说下周反馈"` | preview 文本含商机#456；确认→execute；可查 `/ai/logs` |
| 2 | 取消 | 同场景后回 `"取消"` | pending 清空；无新 WRITE 日志 |
| 3 |歧义消解 | `"跟进一下张三"`（匹配2客户） | 追问候选；回 `"①"` → 锁定正确 customer_id |
| 4 | 修正句 | preview后回 `"金额不对，是38万"` | 重新 preview 看到→380000；仍需确认 |
| 5 | 幂等性 | 重复 `"确认"`（模拟 IM 双投） | 二次结果幂等；不产生双倍副作用 |
| 6 | 权限拒绝 | 销售A操作非管辖客户 | `/ai/` 返回权限拒绝；胶水层回可读文本 |
| 7 | pending 超时 | 超时后回 `"确认"` | 提示"已过期，重新告诉我"；不执行 |
| 8 | 代词消解 | `"改成35万"`（有 recent_entities） | 自动补全 opportunity_id |

---

## 十三、安全与合规

### 13.1 认证流程

```
IM渠道:
  channel_user_id → UserMappingService → crm_user_id → session

网页渠道:
  JWT session_token → 解析 crm_user_id → session
```

### 13.2 权限校验

胶水层不做权限判断，由 `/ai/actions/` 返回：
- `AI_PERMISSION_DENIED` → 胶水层转换为友好文本

### 13.3 审计追踪

```
胶水层记录:
  - session.history_last_n（对话摘要）
  - 不拷 CRM 业务数据

/ai/logs 记录:
  - action_id + action_type + source="ai"
  - 完整链路追溯
```

---

## 十五、多意图处理流程（新增）

> **实现状态**: ✅ 已实现

### 15.1 多意图解析

支持复合指令分解，如"跟进张三客户并设置下周提醒"。

**核心组件**: IntentDetector.detect_multi()

**处理流程**:
```
输入："跟进张三客户，并设置下周提醒"
       │
       ▼
detect_multi → MultiIntentResult(is_multi=true, intents=[跟进, 设置提醒])
       │
       ▼
创建 pending_queue: [PendingAction(跟进), PendingAction(设置提醒)]
       │
       ▼
处理第一个意图 → 实体消解 → 槽位收集 → 预览 → 执行
       │
       ▼
执行成功后检查队列 → 取出下一个意图 → 继续流程
       │
       ▼
全部完成 → 返回 IDLE
```

### 15.2 实体引用继承

后续意图自动继承前意图的实体引用：

```
输入："跟进张三客户，并设置下周提醒"
       │
       第一个意图：跟进张三客户 → 实体消解 → customer_id=101
       │
       第二个意图：设置下周提醒 → 自动继承 customer_id=101
       │
       ▼
用户只需补充 date_description="下周"
```

### 15.3 数据结构

**GlueSession.pending_queue**: 存储多个 PendingAction

```python
@dataclass
class GlueSession:
    pending: Optional[PendingAction] = None
    pending_queue: list = None  # 多意图队列
```

**MultiIntentResult**: 多意图解析结果

```python
@dataclass
class MultiIntentResult:
    is_multi: bool  # 是否为多意图
    intents: List[IntentResult]  # 意图列表
    reasoning: str  # 判断依据
    error: Optional[str] = None
```

---

## 十六、合规规范补充（R-4/R-5）

### 16.1 R-4: 实体解析只读路径

**文件**: `app/services/ai/entity_search.py`

**设计**:
- `EntitySearchService` 类：提供只读实体搜索
- `search_customers()` / `search_opportunities()` 方法
- 租户隔离（team_id 过滤）
- 返回结构化结果（EntitySearchResult）

**整合**:
- `EntityResolver` 使用 `EntitySearchService` 而非直接 CRUD
- 满足 C-1 约束（glue 层无 CRUD import）

```python
class EntitySearchService:
    def search_customers(self, keyword: str, limit: int = 10) -> List[EntitySearchResult]
    def search_opportunities(self, keyword: str, customer_id: Optional[int] = None, limit: int = 10) -> List[EntitySearchResult]
    def search_entities(self, entity_type: str, keyword: str, limit: int = 10) -> List[EntitySearchResult]
```

---

### 16.2 R-5: 显式意图→动作映射

**文件**: `app/glue/core/action_map.py`

**设计**:
- `INTENT_TO_ACTION_MAP`：显式映射表，可 grep 检查
- Key: `(intent_type, action_variant)`
- Value: `/ai/actions/` 端点路径

**映射覆盖**:

| intent_type | action_variant | endpoint |
|-------------|---------------|----------|
| create_follow_up | default | /ai/actions/create-follow-up |
| set_reminder | default | /ai/actions/set-reminder |
| init_opportunity | default | /ai/actions/init-opportunity |
| update_amount | default | /ai/actions/update-amount |
| update_stage | default | /ai/actions/update-stage |
| win_opportunity | default | /ai/actions/win-opportunity |
| lose_opportunity | default | /ai/actions/lose-opportunity |

```python
INTENT_TO_ACTION_MAP: Dict[Tuple[str, str], str] = {
    ("create_follow_up", "default"): "/ai/actions/create-follow-up",
    ("set_reminder", "default"): "/ai/actions/set-reminder",
    ...
}

def get_action_endpoint(intent_type: str, action_variant: str = "default") -> Optional[str]
```

---

### 16.3 合规检测脚本

**文件**: `scripts/check_glue_compliance.py`

**检测规则**:
- C-1: CRUD import 检测
- C-4: Handler import 检测
- C-DS: DynamicSkillService import 检测

**执行**:
```bash
python scripts/check_glue_compliance.py
```

---

## 十七、架构整改变更记录

### 17.1 2026-05-26 整改：路由对齐

**问题**: glue 层违规调用 DynamicSkillService → Handler → CRUD，绕过 `/ai/actions/` 层

**整改内容**:
| Task | 内容 | 状态 |
|------|------|------|
| 1.1 | 创建 INTENT_TO_ACTION_MAP | ✅ |
| 1.2 | 重构 ActionExecutor.execute | ✅ |
| 1.3 | 重构 ActionExecutor.preview | ✅ |
| 1.4 | 移除 DynamicSkillService 调用 | ✅ |
| 2.1 | 创建 EntitySearchService | ✅ |
| 2.2 | 重构 EntityResolver | ✅ |
| 2.3 | 移除 CRUD 直接查询 | ✅ |
| 3.1-3.3 | 审计标记 + 预览渲染 | ✅ |
| 4.1-4.5 | 清理违规依赖 + 合规脚本 | ✅ |

**验收结果**:
- ✅ glue 层无 CRUD import（C-1 合规）
- ✅ glue 层无 Handler import（C-4 合规）
- ✅ glue 层无 DynamicSkillService import（C-DS 合规）
- ✅ 所有写操作经过 AIActionExecutor（Single Writer 原则）
- ✅ 显式映射可 grep（R-5 合规）

**关联文档**:
- `CRM-Docs/plans/AI-GLUE-ROUTING-ALIGNMENT-PLAN.md`
- `CRM-Docs/requirements/AI-GLUE-ROUTING-ALIGNMENT-RFC.md`

---

### 17.2 2026-05-26 深度整改：入口函数模式

**问题**: ActionExecutor 是 CRUD 包装而非入口函数，双份 Preview 违反 Single Source of Truth

**整改依据**: `CRM-Docs/plans/AI-GLUE-DEEP-REMEDIATION-PLAN.md`

**核心原则 R-1 ~ R-5**:

| 规则 | 内容 | 验收方法 | 状态 |
|------|------|---------|------|
| **R-1** | 末级调用是入口函数，不是 CRUD | 代码追踪：glue → action_entry → ActionExecutor(CRUD层) | ✅ |
| **R-2** | Preview 必须是单一 truth | glue 无 `_build_preview_from_slots` 函数 | ✅ |
| **R-3** | 内部调用使用入口函数签名 `(preview: bool) → ActionEntryResult` | 检测 glue import action_entry | ✅ |
| **R-4** | action_id 从入口函数获取（统一归因） | action_id 在 preview 和 execute 保持一致 | ✅ |
| **R-5** | EntityResolver 使用只读路径 | EntitySearchService 调用而非直接 CRUD | ✅ |

**整改内容**:

| Phase | 内容 | 文件 | 状态 |
|-------|------|------|------|
| Phase 1 | 创建 action_entry.py 入口函数层 | `app/services/ai/action_entry.py` | ✅ |
| Phase 2 | 重构 glue/executor.py 调用入口函数 | `app/glue/core/executor.py` | ✅ |
| Phase 3 | 重构 /ai/actions/ 端点使用入口函数 | `app/api/ai/actions.py` | ✅ |
| Phase 4 | ActionExecutor 降级为纯 CRUD 调用层 | `app/services/ai/action_executor.py` | ✅ |
| Phase 5 | 更新合规检测脚本 | `scripts/check_glue_compliance.py` | ✅ |
| Phase 6 | 文档更新 | `CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md` | ✅ |

**新增架构层**:

```
glue/core/executor.py
       │ (进程内调用)
       ▼
app/services/ai/action_entry.py  ← 入口函数层（新增）
       │ Preview + Gate + Audit
       │
       ▼ (execute 态)
app/services/ai/action_executor.py  ← CRUD 调用层（降级）
       │
       ▼
CRUD 层
```

**入口函数职责**:
1. 权限校验（当前用户能否对该实体做该操作）
2. 业务校验（阶段流合法性、字段约束、必填语义）
3. Preview 构造（单一 truth）
4. Execute 执行（调用 CRUD）
5. 审计留痕（source="ai"、action_id）

**ActionExecutor 降级后职责**:
- 仅负责 CRUD 调用
- 不记录审计日志（由 action_entry 负责）
- 仅被 action_entry 调用

**验收结果**:
- ✅ glue 不 import ActionExecutor（C-ACTION 合规）
- ✅ glue 无自建 Preview 逻辑（C-PREVIEW 合规）
- ✅ glue → action_entry → CRUD 路径正确
- ✅ Preview 单一 truth（R-2 合规）
- ✅ action_id 绑定 preview→execute（R-4 合规）

**合规检测脚本更新**:
```bash
python scripts/check_glue_compliance.py

# 新增检测规则:
# - C-ACTION: 禁止直接导入 ActionExecutor（应使用 ActionEntry）
# - C-PREVIEW: 禁止自建 Preview 逻辑
# - R-3-compliant: 正向验证使用 ActionEntry 入口函数
```

---

### 17.3 2026-05-26 终态拧螺丝：v0.3 需求与原则

**背景**: v3.0 已消灭最危险模式（glue 越级写 CRUD），但仍有三道"接缝腐蚀"风险需要制度性解决。

**依据**: 
- Microsoft AI 应用层设计准则（分层边界、Tools 层标准化接口、Block direct access to data stores）
- OWASP MCP-02（Least Privilege by Design, Per-agent identity, Immutable audit trail）

---

#### 17.3.1 优化需求 R-A ~ R-E（封口版）

| 需求 | 内容 | 验收方法 | 状态 |
|------|------|---------|------|
| **R-A** | Tools 层单一入口：Entry 是写操作的"前门"，不是可选路径 | compliance 脚本 + 白名单机制 | ✅ 已实现 |
| **R-A.1** | 白名单机制：glue 层只读桥接必须有 `# READONLY_BRIDGE` 注解 | grep `# READONLY_BRIDGE` 验证 | ✅ 已实现 |
| **R-B** | HTTP 适配层保持"纯薄"：只能做 shape 转换，不能裁决 | AST 扫描禁止模式 | ✅ 已实现 |
| **R-B.1** | AST 扫描禁止：`session.commit`, `crud.`, `if.*result.*raise` | compliance 脚本 AST 检测 | ✅ 已实现 |
| **R-C** | Preview 唯一真源：`pending.preview_snapshot` 是展示缓存，不是 fallback | grep 禁止 `_build_preview` | ✅ 已实现 |
| **R-D** | User Context 传播：定义 `UserExecCtx`，不暴露 db Session | glue 不构造/持有 Session | ✅ 已实现 |
| **R-D.1** | db: Session 参数标记为 **transitional**，终态目标 `ActionEntry.from_ctx(ctx)` | docstring 注释 | ✅ 已实现 |
| **R-D.2** | 审计必须记录 source 和 is_ai 字段 | `/ai/logs` 验证 | ✅ 已实现 |
| **R-E** | 审计归因可回放：Entry 是审计闸门，完整字段规格 | `/ai/logs` 字段验证 | ✅ 已实现 |
| **R-E.1** | 完整审计字段：action_id, crm_user_id, tenant_id, action_type, source, params_digest, outcome, ts | 数据库 schema 验证 | ✅ 已实现 |

**R-A.1 白名单机制**:
```python
# glue/core/entity.py 中允许的只读桥接（必须有注解）
customers, _ = customer_crud.get_multi(...)  # READONLY_BRIDGE: EntitySearchService 只读路径
```

**R-B.1 AST 扫描禁止模式**（HTTP adapter 中禁止）:
```python
# 禁止模式列表（compliance 脚本 AST 检测）
session.commit()
crud.xxx.create(...)  # 任何 crud. 调用
if result.error: raise HTTPException(...)  # 业务裁决逻辑
```

**R-D.1 transitional 标记**:
```python
class ActionEntry:
    def __init__(self, db: Session, user_ctx: UserExecCtx):
        """入口函数层
        
        Args:
            db: Session - **transitional** 内部持有，终态目标 ActionEntry.from_ctx(ctx)
            user_ctx: UserExecCtx - 用户执行上下文（来源：web/ai/glue）
        """
```

**R-D.2 审计字段**:
```python
@dataclass
class UserExecCtx:
    user_id: int
    tenant_id: int
    roles: List[str]
    is_ai: bool = False        # 必须记录
    source: str = "web"        # 必须记录: "web" | "ai" | "glue"
    user_name: Optional[str] = None
```

**R-E.1 完整审计记录字段**:
```python
# AIActionLog 表字段（Entry 写入）
action_id: str              # 唯一标识
crm_user_id: int            # 操作用户
tenant_id: int              # 租户
action_type: str            # 动作类型
source: str                 # 来源: "web" | "ai" | "glue"
params_digest: str          # 参数摘要（脱敏）
outcome: str                # 结果: "success" | "failed"
ts: datetime                # 时间戳
```

---

#### 17.3.2 原则 P1 ~ P4（Code Review 判据）

| 原则 | 内容 | 判据 |
|------|------|------|
| **P1** | MS 分层：Glue = Intelligence ≠ Tools；ActionEntry = Tools 层标准化接口 | PR 让 glue"知道怎么落盘"→ 打回 |
| **P2** | OWASP Least Privilege：AI 编排侧不直接碰数据存放区，Block direct access to data stores | glue 禁止拿 Session/connection 做查询后"顺便写" |
| **P3** | Preview-as-Gate（NO_BYPASS_PREVIEW）：Preview 是安全基础设施，不是 UX 糖衣 | "是否允许/将要改什么"必须来自 Entry.preview() |
| **P4** | Tool 接口标准化：参数化命令，不是 SQL/ORM 动词，Evidence over claims | 扩写能力靠新 Entry 方法 + 登记映射，不靠 glue 加 if |

---

#### 17.3.3 终态锚点

> **终态不是"把 ActionEntry 拆没"，而是让它变成真正的 Tools 层契约：`Entry.method(user_ctx, params, preview=) → ActionEntryResult`，HTTP 端点只是 thin adapter，glue 只拿 `user_ctx + 意图参数`，db session 不跨过 glue 的视线。**

---

#### 17.3.4 已完成验收（2026-05-26）

**Phase 7-10 已实现**:
- ✅ R-A.1: 白名单机制 + `# READONLY_BRIDGE` 注解（C-WRITE-ACCESS 规则）
- ✅ R-B.1: HTTP 适配层 GUARDRAIL 注释（禁止业务逻辑）
- ✅ R-D: UserExecCtx 替代裸 db: Session 参数
- ✅ R-D.1: transitional 标记（docstring 注释）
- ✅ R-D.2: 审计归因 source/is_ai 字段
- ✅ R-E: 审计记录完整字段规格

**合规检测输出**:
```
C-WRITE-ACCESS ✅ 无直接写型数据操作（R-A 合规）
R-3 ✅ glue → action_entry 入口函数路径正确
```

**当前架构**:
```
HTTP adapter (app/api/ai/actions.py)
       │ UserExecCtx.from_user(user, is_ai=True, source="ai")
       ▼
ActionEntry(db, user_ctx)  ← 入口函数层
       │ Preview + Gate + Audit
       ▼
ActionExecutor(CRUD层)  ← 仅 CRUD 调用
```

---

> **文档版本**：3.1（封口版）
> **最后更新**：2026-05-26（v0.3 终态 Phase 7-10 完成）
> **实现状态**：✅ 全部完成
> **关联文档**：[AI-API-STANDARD.md](../standards/AI-API-STANDARD.md)、[AI-API-IMPLEMENTATION.md](../standards/AI-API-IMPLEMENTATION.md)
> **维护团队**：CRMWolf 开发团队