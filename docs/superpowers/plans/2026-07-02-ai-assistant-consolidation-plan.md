# AI 助手整合收口实施计划（Option B：扶正 Glue，废弃 ReAct）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **本计划已合并前后端**：Phase 1-4 为后端，Phase 5 为前端（含 UI 视觉契约）。两段共享同一份 SSE 事件契约与 `outcome_type` 字段，执行时视为一份文档。

**Goal:** 把 AI 助手从"唯一能跑但绕过好设计的 ReAct 手写循环"整合收口到"设计更好但当前断裂的 Glue DialogueEngine"为唯一生产路径，同时清除 LangGraph 残骸与全部旁路死码，并重构前端从"ReAct 思考流 + 单步 PreviewCard"为"Glue 语义阶段驱动的统一确认/歧义/补全交互"，达到生产级可用稳定。

**Architecture:** 五阶段递进——Phase 1 纯清理（删死码，两条路径都仍能跑）；Phase 2 修 Glue 的 5 个阻塞性 bug（让 Glue 核心路径真正能跑通，成为第二条可用路径）；Phase 3 把 ReAct 独有的 5 项能力（SSE 流式 / Session API / 危险工具门 / Preview 快照 / 轮次管理）迁移进 Glue 后退役 ReAct；Phase 4 按面向 Agent 的工具设计原则重写 Glue 的 LLM-facing intent 契约与错误/响应格式；Phase 5 前端对齐 Glue 语义阶段、复活孤儿交互能力、清除 ReAct 专有包装与孤儿死码。每个 Phase 结束都是可独立 ship 的状态。

**Tech Stack:** 后端 FastAPI + Pydantic + Redis + SQLAlchemy CRUD 层 + OpenAI 兼容 LLM（`ai_service._stream_chat_collect`，已支持 `response_format={"type":"json_object"}`）+ SSE。前端 Vue 3 + Element Plus 2.13 + Pinia + wolf-* SCSS 设计 token（`$wolf-primary: #4A6FA5`，IBM Plex Sans/Mono）+ 原生 fetch ReadableStream SSE（非 EventSource）+ markdown-it，无深色模式。

**关键决策（已定，贯穿全计划）：**
- **不建 AI 路径 undo**：WON/LOST 是代码+文档强制的业务终态不可逆；控制点在执行前（Preview/Gate）而非执行后。前端无 UndoToast，HIGH 风险确认在 DangerConfirmCard 明示"不可撤销"。
- **win/lose 视觉分态**：赢单=success-green climax，输单=neutral-grey 终态，通用高风险=danger-red。由后端 `preview` 事件 `outcome_type` 字段驱动（Phase 3.1/3.3 产出，Phase 5.1 消费）。
- **4 个表单型 AI parser 不收口到 Glue**：审批/采购是配置生成工具（异业务域），客户/线索是单轮弹窗（异心智）；本次整合不动，仅建议（非本计划范围）做 parser 间内部去重。

## Global Constraints

- **红线**：遵循 `CRM-Server/CLAUDE.md`——CRUD 统一入口禁止 `db.query()`；`team_id` 必传；CRITICAL 操作必须 Preview；**禁止推断**客户阶段/商机状态/发票类型/权限码枚举，需查 `app/constants/*.py`。
- **封口版契约不动**：`ActionEntry.method(user_ctx, params, preview=, action_id=) → ActionEntryResult` 是唯一写动作前门；glue executor 末级必须经 ActionEntry，不得直连 CRUD（Single Writer 已审计成立，保持）。
- **SSE 事件兼容**：前端当前消费 ReAct 的 `start` / `result` / `complete` / `error` 事件名与 payload 字段（`sse_streamer.py:57-139`）。Glue 流式化必须保留这 4 个事件名 + 关键字段（`result.content`、`complete.is_partial`、`complete.answer`），可新增 Glue 语义中间事件但不得破坏上述 4 个。
- **会话寻址**：迁移后统一为 uuid `session_id`（保留 ReAct 多会话语义），Glue 现有 `(tenant_id, crm_user_id)` 寻址在 Phase 3.2 改造。
- **诚实失败**：任何未实现的异步渠道（IM 队列）必须显式 503，禁止返回 `ok=True` 假装成功。
- **删除即删除**：每个删除 Task 必须先 grep 确认零 live 引用（本计划已附审计结论，但执行时仍需重跑 grep 复核，防止本计划之后有新代码引用）。
- **每个 Task 末尾 commit**；分支 `approval-engine-generalization` 已有未提交改动，本计划建议另开分支 `ai-assistant-consolidation`。

---

## 现状基线（已审计事实，非推测）

### 三条 AI 路径的真实状态

| 路径 | 端点 | 注册 | 状态 |
|------|------|------|------|
| ReAct agent | `POST /v1/agent/chat` | `app/main.py:107` 未注释 | **唯一能端到端跑通**；但绕过 ActionEntry/EntitySearch，正则 `re.search(r'\{[\s\S]*\}')` 抓 JSON（`core.py:1018`）是稳定性炸弹 |
| Glue DialogueEngine | `POST /api/glue/v1/inbound` | `app/main.py:120` 未注释 | 端点可达但**核心路径崩**：实体消解主用例必 500，EXECUTE 必 TypeError，预览恒空 |
| /ai/actions + ActionEntry | `POST /api/ai/actions/*` | `app/main.py:114` 未注释 | 端点可达但**零内部调用方**（唯一 caller ActionPlanner 已死）；ActionEntry 链路本身健全，Single Writer 已确认 |

### Glue 阻塞性 bug 清单（Phase 2 修）

| # | 位置 | bug | 后果 |
|---|------|-----|------|
| B1 | `dialogue.py:438-442` | 调 `resolve(text, entity_type_hint=..., keyword=...)`，签名实为 `resolve(text, entity_type, session)` | "跟进张三"等需实体消解的主用例 TypeError → 500 |
| B2 | `dialogue.py:733` | 调 `execute(pending)`，签名实为 `execute(pending, action_id)` | EXECUTE 分支 TypeError |
| B3 | `dialogue.py:800-803` | 读 `exec_result.skill_name / .action_name`，`ExecutionResult` 无此二字段（仅 success/message/action_id/data/error） | AttributeError |
| B4 | `app/glue/core/safety.py:21` | `Optional[str]` 注解但 `from typing import Dict, Any` 未含 `Optional` | 模块被 import 即 NameError |
| B5 | `executor.py:108-168` | `preview()` 实现完整但 `dialogue.py` 从不调用 | PREVIEW 状态恒为"空预览"，`PendingAction.preview_snapshot` 永远空 dict |

### LangGraph 组件可达性（Phase 1 清理依据）

| 文件 | live 引用 | 结论 |
|------|-----------|------|
| `app/services/langgraph/checkpointer.py` | 零 | DEAD，直接删 |
| `app/services/langgraph/state.py` | 零（仅被同样 dead 的 intent.py import） | DEAD，直接删 |
| `app/services/langgraph/nodes/intent.py` | 零（无 graph.py，无 add_node 调用） | DEAD，直接删 |
| `app/services/langgraph/sse_wrapper.py` | `SSEJsonEncoder`(33-48行) 被 `app/api/approval_ai.py:19,61` 活用；其余（Pregel/SSE_EVENT_TYPES/build_*/stream_sse_events）全死 | PARTIAL，先迁移 Encoder 再删整文件 |

### 旁路死码（与 LangGraph 无关，Phase 1 一并清）

| 死码 | 证据 |
|------|------|
| `app/glue/core/planner.py` + `action_map.py` | 零引用，`ActionPlanner` 仅 tests 实例化，httpx 永不发出 |
| `ActionEntry.create_customer` / `query_customer` (`action_entry.py:649,745`) | 零 caller；Glue executor 7 个 if/elif 也不覆盖 |
| `app/constants/tools.py` 的 `TOOLS` / `get_tools_schema()` / `get_tool_handler_config()` | 仅 `tests/unit/test_contract_tools.py` 引用；`TOOL_HANDLER_MAP` 仍 live（ReAct 用），Phase 3 再删 |
| `app/api/ai_skills.py` / `ai_skill_generator.py` / `app/services/ai_skill_main.py` / `skill_generator_service.py` | router 从未 include，零调用方 |
| `app/services/agent/prompt_versions.py` | 全仓零引用 |

### 能力迁移对照（Phase 3 依据）

| 能力 | ReAct | Glue | 迁移动作 |
|------|-------|------|---------|
| SSE 流式 | `sse_streamer.py` 7 类 event | 完全没有 | 拆 `dispatch` 为 async generator + `StreamingResponse` |
| Session API | uuid session_id，GET/DELETE | (tenant,user) 寻址，GET/DELETE | 统一 uuid 寻址 + 对齐响应 schema |
| 危险工具门 | `DANGEROUS_TOOLS` + ConfidenceGuardrail 分级 | `SafetyGateway` 已写但孤儿+NameError | 修 B4 + 接入 dialogue 替代 universal confirm |
| Preview 快照 | `ToolResult.preview_data` | `executor.preview()` 已写但不调用 | 接通 preview()，填 preview_snapshot |
| 轮次管理 | `MAX_ROUNDS=10` + 超限 `is_partial` | 完全没有 | 给 Glue 多意图 pending_queue 加全局轮次上限 + 降级 |

---

## 文件改动总表

| Phase | Task | 操作 | 文件 |
|-------|------|------|------|
| 1 | 1.1 | 迁移+删 | `app/services/langgraph/sse_wrapper.py` → `app/utils/sse_encoder.py`；改 `app/api/approval_ai.py:19` |
| 1 | 1.2 | 删 | `app/services/langgraph/checkpointer.py`、`state.py`、`nodes/intent.py`、`nodes/` |
| 1 | 1.3 | 改 | `pyproject.toml:29,102-112` 移除 langgraph |
| 1 | 1.4 | 删 | `app/glue/core/planner.py`、`action_map.py` |
| 1 | 1.5 | 改+删 | `app/services/ai/action_entry.py:649-788` 删两方法 |
| 1 | 1.6 | 改 | `app/constants/tools.py` 删 `TOOLS`/`get_tools_schema`/`get_tool_handler_config` |
| 1 | 1.7 | 删 | `app/api/ai_skills.py`、`ai_skill_generator.py`、`app/services/ai_skill_main.py`、`skill_generator_service.py` |
| 1 | 1.8 | 删 | `app/services/agent/prompt_versions.py` |
| 1 | 1.9 | 删/移 | `tests/unit/services/langgraph/*`、`tests/test_state.py`、`tests/test_sse_wrapper.py` |
| 1 | 1.10 | 改 | `CRM-Server/CLAUDE.md`、`app/services/CLAUDE.md`、`CRM-Docs/system/AI-AGENT-ARCHITECTURE.md` |
| 2 | 2.1 | 改 | `app/glue/core/dialogue.py:438-442` |
| 2 | 2.2 | 改 | `app/glue/core/dialogue.py:733` |
| 2 | 2.3 | 改 | `app/glue/core/dialogue.py:800-803` |
| 2 | 2.4 | 改 | `app/glue/core/safety.py:9` |
| 2 | 2.5 | 改 | `app/glue/api/inbound.py:130-138` |
| 2 | 2.6 | 测 | 新增 `tests/glue/test_e2e_web_sync.py` |
| 2 | 2.7 | 改 | `app/glue/core/dialogue.py` PREVIEW 分支接通 `executor.preview()` |
| 3 | 3.1 | 改+新 | `app/glue/core/dialogue.py`（dispatch→generator）；`app/glue/api/inbound.py`（StreamingResponse）；新增 `app/glue/core/sse_streamer.py` |
| 3 | 3.2 | 改 | `app/glue/core/session.py`（uuid 寻址）；`app/glue/api/admin.py`（session 端点对齐） |
| 3 | 3.3 | 改 | `app/glue/core/dialogue.py` 接入 `SafetyGateway`；`app/constants/ai_rules.py` 确认 risk 阈值接线 |
| 3 | 3.4 | 改 | `app/glue/core/dialogue.py` 轮次上限 + `is_partial` |
| 3 | 3.5 | 改 | `app/api/agent_assistant.py` 代理到 Glue 或新统一入口 |
| 3 | 3.6 | 删 | `app/services/agent/`、`app/api/agent_assistant.py`、ReAct-only handlers、`constants/tools.py` 余下 |
| 4 | 4.1-4.7 | 改 | `app/glue/core/intent.py`、`app/constants/ai_rules.py`、`app/services/ai_service.py`、错误信息各 handler |
| 5 | 5.1-5.14 | 改/新/删 | 前端 `CRM-Client/src/`：Glue 事件类型、复活组件（EntityPicker/DangerConfirmCard/SlotFillForm/ErrorCard/PhaseSummary）、AIAssistant 接线、删孤儿死码 |

---

# Phase 1：死代码清理（无分叉，先做，两条路径仍能跑）

**Ship gate**：Phase 1 结束后，`pytest` 全绿（删测试后）、`uvicorn app.main:app` 启动无 import 错误、`/v1/agent/chat` 与 `/api/glue/v1/inbound` 端点仍可达、`langgraph` 不再是运行时依赖。

### Task 1.1：迁移 SSEJsonEncoder，删除 langgraph/sse_wrapper.py

**Files:**
- Create: `app/utils/sse_encoder.py`
- Modify: `app/api/approval_ai.py:19,61`（改 import 来源）
- Delete: `app/services/langgraph/sse_wrapper.py`

**Interfaces:**
- Produces: `app.utils.sse_encoder.SSEJsonEncoder`（与原 `SSEJsonEncoder` 完全同构，仅换路径）

- [ ] **Step 1: 读取原 Encoder 实现确认依赖**

Run: 读 `app/services/langgraph/sse_wrapper.py:26-48`（`from langchain_core.messages import BaseMessage` + `SSEJsonEncoder` 类体）。确认 Encoder 仅依赖 `langchain_core`，不依赖 `langgraph`/`Pregel`。

- [ ] **Step 2: 创建新 util 文件**

```python
# app/utils/sse_encoder.py
"""SSE JSON 编码器（从 langgraph/sse_wrapper.py 迁出，仅保留 SSEJsonEncoder）"""
import json
from datetime import datetime
from langchain_core.messages import BaseMessage


class SSEJsonEncoder(json.JSONEncoder):
    """处理 LangChain BaseMessage 等非原生可序列化对象的 JSON 编码。"""

    def default(self, obj):
        if isinstance(obj, BaseMessage):
            return {"type": obj.__class__.__name__, "content": obj.content}
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)
```

- [ ] **Step 3: 改 approval_ai.py 的 import**

`app/api/approval_ai.py:19` 把 `from app.services.langgraph.sse_wrapper import SSEJsonEncoder` 改为 `from app.utils.sse_encoder import SSEJsonEncoder`。其余 `json.dumps(..., cls=SSEJsonEncoder)` 用法不变。

- [ ] **Step 4: 删除原文件**

Run: `rm app/services/langgraph/sse_wrapper.py`

- [ ] **Step 5: 验证 approval_ai 仍工作**

Run: `pytest tests/unit/api/test_approval_ai_api.py -v`
Expected: PASS（该测试 import SSEJsonEncoder，需同步改 import 来源——见 Task 1.9）

- [ ] **Step 6: Commit**

```bash
git add app/utils/sse_encoder.py app/api/approval_ai.py
git commit -m "refactor(sse): migrate SSEJsonEncoder out of langgraph dir"
```

### Task 1.2：删除 langgraph 死文件

**Files:**
- Delete: `app/services/langgraph/checkpointer.py`、`app/services/langgraph/state.py`、`app/services/langgraph/nodes/intent.py`

- [ ] **Step 1: 复核零 live 引用**

Run: `grep -rn "langgraph.checkpointer\|RedisCheckpointer\|get_checkpointer\|langgraph.graph\|langgraph.nodes\|intent_detector_node\|AgentState" app/ --include=*.py | grep -v "^app/services/langgraph/"`
Expected: 仅 tests/ 命中（无 live 引用）。

- [ ] **Step 2: 删除文件**

Run: `rm app/services/langgraph/checkpointer.py app/services/langgraph/state.py && rm -rf app/services/langgraph/nodes`

- [ ] **Step 3: 验证 app 仍可 import**

Run: `python -c "import app.main"`
Expected: 无 ImportError。

- [ ] **Step 4: Commit**

```bash
git add -A app/services/langgraph/
git commit -m "chore(langgraph): remove dead checkpointer/state/intent files"
```

### Task 1.3：移除 langgraph PyPI 依赖

**Files:**
- Modify: `pyproject.toml:29`（依赖）、`pyproject.toml:102-112`（mypy override）

- [ ] **Step 1: 复核无运行时 import**

Run: `grep -rn "from langgraph" app/ --include=*.py`
Expected: 零命中（Task 1.2 已删全部 `from langgraph.*`）。

- [ ] **Step 2: 从 pyproject 删除依赖**

`pyproject.toml:29` 删除 `"langgraph>=0.2.0"` 行。`pyproject.toml:102-112` 删除 `module = "langgraph.*"` 的 mypy override 块。

- [ ] **Step 3: 验证依赖树**

Run: `pip check && python -c "import app.main"`
Expected: 无 langgraph 相关报错。**注意**：不卸载已装包（开发环境保留无妨），仅从声明移除。

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore(deps): drop langgraph from pyproject (no runtime imports)"
```

### Task 1.4：删除 glue 死文件 planner.py / action_map.py

**Files:**
- Delete: `app/glue/core/planner.py`、`app/glue/core/action_map.py`

- [ ] **Step 1: 复核零引用**

Run: `grep -rn "from app.glue.core.planner\|from app.glue.core.action_map\|ActionPlanner\|INTENT_ACTION_MAP\|INTENT_TO_ACTION_MAP" app/ --include=*.py | grep -v "app/glue/core/planner.py\|app/glue/core/action_map.py"`
Expected: 零命中（确认除文件自身外无引用）。

- [ ] **Step 2: 删除文件**

Run: `rm app/glue/core/planner.py app/glue/core/action_map.py`

- [ ] **Step 3: 验证 glue 仍可 import**

Run: `python -c "from app.glue.core.dialogue import DialogueEngine"`
Expected: 无 ImportError。

- [ ] **Step 4: Commit**

```bash
git add -A app/glue/core/
git commit -m "chore(glue): remove dead ActionPlanner and INTENT_TO_ACTION_MAP"
```

### Task 1.5：删除 ActionEntry 孤儿方法 create_customer / query_customer

**Files:**
- Modify: `app/services/ai/action_entry.py:649-788`（删两方法）

- [ ] **Step 1: 复核零 caller**

Run: `grep -rn "\.create_customer\|\.query_customer\|entry\.create_customer\|entry\.query_customer" app/ --include=*.py | grep -v "action_entry.py"`
Expected: 零命中。

- [ ] **Step 2: 删除两方法**

读 `action_entry.py:649` 到 `query_customer` 方法结束（约 `:788`），删除 `create_customer` 与 `query_customer` 两个 `async def` 块。保留文件其余部分。

- [ ] **Step 3: 同步风险映射（如引用）**

Run: `grep -n "create_customer\|query_customer" app/constants/ai_rules.py`
Expected: 若 `ACTION_RISK_MAPPING` 含这两条，一并删除其映射项（保持 dict 一致）。

- [ ] **Step 4: 验证 entry 仍可 import**

Run: `python -c "from app.services.ai.action_entry import ActionEntry"`
Expected: 无错。

- [ ] **Step 5: Commit**

```bash
git add app/services/ai/action_entry.py app/constants/ai_rules.py
git commit -m "refactor(action_entry): remove orphan create_customer/query_customer"
```

### Task 1.6：删除 constants/tools.py 死段（保留 TOOL_HANDLER_MAP）

**Files:**
- Modify: `app/constants/tools.py`（删 `TOOLS` list `:9-1366`、`get_tools_schema()` `:1753`、`get_tool_handler_config()` `:1758`；保留 `TOOL_HANDLER_MAP` `:1369-1750`）

- [ ] **Step 1: 确认保留项仍被引用**

Run: `grep -rn "TOOL_HANDLER_MAP" app/ --include=*.py`
Expected: `app/services/agent/tools.py:468` 命中（ReAct 仍用，Phase 3 再删）。

- [ ] **Step 2: 确认删除项无 live 引用**

Run: `grep -rn "from app.constants.tools import\|constants\.tools\.\|get_tools_schema\|get_tool_handler_config\| TOOLS\b" app/ --include=*.py | grep -v "app/constants/tools.py"`
Expected: 仅 `app/services/agent/tools.py` 的 `TOOL_HANDLER_MAP` import 命中，`TOOLS`/`get_tools_schema`/`get_tool_handler_config` 零 live 命中（仅 tests）。

- [ ] **Step 3: 删除三段**

删除 `TOOLS = [...]` 常量、`def get_tools_schema()`、`def get_tool_handler_config()`。保留 `TOOL_HANDLER_MAP` 与文件头必要的 import。

- [ ] **Step 4: 验证 ReAct 仍工作**

Run: `python -c "from app.services.agent.tools import ToolRegistry; print('ok')"`
Expected: ok（ToolRegistry 只用 TOOL_HANDLER_MAP）。

- [ ] **Step 5: Commit**

```bash
git add app/constants/tools.py
git commit -m "chore(tools): remove dead TOOLS list and schema getters"
```

### Task 1.7：删除从未 include 的死路由与服务

**Files:**
- Delete: `app/api/ai_skills.py`、`app/api/ai_skill_generator.py`、`app/services/ai_skill_main.py`、`app/services/skills/skill_generator_service.py`

- [ ] **Step 1: 复核 router 未 include**

Run: `grep -rn "ai_skills\.router\|ai_skill_generator\.router\|ai_skill_main" app/main.py app/ --include=*.py | grep -v "app/api/ai_skills.py\|app/api/ai_skill_generator.py\|app/services/ai_skill_main.py"`
Expected: 零命中。

- [ ] **Step 2: 确认 skill_generator_service 仅被死 router 调**

Run: `grep -rn "skill_generator_service\|SkillGeneratorService" app/ --include=*.py | grep -v "skill_generator_service.py"`
Expected: 仅 `app/api/ai_skill_generator.py` 命中（该 router 已确认死）。

- [ ] **Step 3: 删除四文件**

Run: `rm app/api/ai_skills.py app/api/ai_skill_generator.py app/services/ai_skill_main.py app/services/skills/skill_generator_service.py`

- [ ] **Step 4: 验证 app 启动**

Run: `python -c "import app.main"`
Expected: 无 ImportError。

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove dead ai_skills/ai_skill_generator routers and services"
```

### Task 1.8：删除 agent/prompt_versions.py

**Files:**
- Delete: `app/services/agent/prompt_versions.py`

- [ ] **Step 1: 复核零引用**

Run: `grep -rn "prompt_versions" app/ --include=*.py | grep -v "app/services/agent/prompt_versions.py"`
Expected: 零命中。

- [ ] **Step 2: 删除**

Run: `rm app/services/agent/prompt_versions.py`

- [ ] **Step 3: Commit**

```bash
git add -A app/services/agent/
git commit -m "chore(agent): remove dead prompt_versions.py"
```

### Task 1.9：清理/迁移死测试

**Files:**
- Delete: `tests/unit/services/langgraph/test_state.py`、`tests/unit/services/langgraph/test_intent_detector.py`、`tests/unit/services/langgraph/test_nodes.py`（已 collection-error，import 不存在节点）、`tests/test_state.py`
- Modify: `tests/test_sse_wrapper.py`、`tests/unit/services/langgraph/test_sse_wrapper.py`、`tests/unit/api/test_approval_ai_api.py`（import 改到 `app.utils.sse_encoder`）然后移到 `tests/unit/utils/test_sse_encoder.py`

- [ ] **Step 1: 删测死码的测试**

Run: `rm tests/unit/services/langgraph/test_state.py tests/unit/services/langgraph/test_intent_detector.py tests/unit/services/langgraph/test_nodes.py tests/test_state.py && rmdir tests/unit/services/langgraph 2>/dev/null || true`

- [ ] **Step 2: 迁移 SSE encoder 测试**

把 `tests/test_sse_wrapper.py` 与 `tests/unit/services/langgraph/test_sse_wrapper.py` 中测 `SSEJsonEncoder` 的用例合并到新文件 `tests/unit/utils/test_sse_encoder.py`，import 改为 `from app.utils.sse_encoder import SSEJsonEncoder`，删除原 sse_wrapper 测试文件。同步 `tests/unit/api/test_approval_ai_api.py` 的 import。

- [ ] **Step 3: 跑迁移后测试**

Run: `pytest tests/unit/utils/test_sse_encoder.py tests/unit/api/test_approval_ai_api.py -v`
Expected: PASS。

- [ ] **Step 4: 全量回归**

Run: `pytest -x --ignore=tests/unit/services/langgraph 2>/dev/null || pytest -x`
Expected: 无新增失败（已有失败另案处理，本 Task 只保证不引入新失败）。

- [ ] **Step 5: Commit**

```bash
git add -A tests/
git commit -m "test: remove dead langgraph tests, migrate SSE encoder tests"
```

### Task 1.10：更新失效文档

**Files:**
- Modify: `CRM-Server/CLAUDE.md`、`app/services/CLAUDE.md`、`CRM-Docs/system/AI-AGENT-ARCHITECTURE.md`

- [ ] **Step 1: 修正 CLAUDE.md 技术地图**

`CRM-Server/CLAUDE.md` 中删除"LangGraph v1.0"、`langgraph/graph.py`、`workflow_orchestrator.py`、`ai_tool_service.py`、`app/services/langgraph/tools/` 等已删文件的描述。改为：当前 AI 助手有两条路径（ReAct `/v1/agent/chat` + Glue `/api/glue/v1/inbound`），整合方向为扶正 Glue（见本计划）。

- [ ] **Step 2: 修正 AI-AGENT-ARCHITECTURE.md**

`CRM-Docs/system/AI-AGENT-ARCHITECTURE.md` §1.3 的"StateGraph 三层"标注为"规划态，磁盘未落地"；保留 Redis Checkpointer 段落但标注"实现已随 langgraph 目录清理移除，会话改由 Glue SessionManager（Redis）承担"。在文档顶部加 `> ⚠ 本文档描述的 LangGraph StateGraph 架构尚未在代码中编译落地；当前生产路径见 docs/superpowers/plans/2026-07-02-ai-assistant-consolidation-plan.md`。

- [ ] **Step 3: Commit**

```bash
git add CRM-Server/CLAUDE.md app/services/CLAUDE.md CRM-Docs/system/AI-AGENT-ARCHITECTURE.md
git commit -m "docs: correct stale LangGraph architecture references"
```

---

# Phase 2：修复 Glue 阻塞性 bug（让 Glue 核心路径能跑通）

**Ship gate**：Phase 2 结束后，Glue web 同步路径端到端跑通——一个 happy path（slots 齐全的写意图，如"创建商机金额1000万"）走完 IDLE→PREVIEW→EXECUTE→ActionEntry→CRUD 不报错；一个实体消解路径（如"跟进张三"）走完 IDLE→RESOLVING_ENTITY→（消解成功）→PREVIEW 不 500。ReAct 仍正常运行未受影响。

### Task 2.1：修复 resolve() 签名不匹配（B1，实体消解主用例）

**Files:**
- Modify: `app/glue/core/dialogue.py:438-442`

**Interfaces:**
- Consumes: `EntityResolver.resolve(self, text, entity_type, session) -> EntityResolveResult`（`entity.py:81-86`，已存在不改）
- Produces: 调用点签名对齐，`RESOLVING_ENTITY` 分支不再 TypeError

- [ ] **Step 1: 确认调用点上下文**

读 `app/glue/core/dialogue.py:415-450`，确认 `_handle_resolving_entity` 方法签名含 `session` 参数（dispatch 传入），以及 `context` dict 的 `entity_type` 键来源。

- [ ] **Step 2: 写失败测试**

`tests/glue/test_dialogue_entity_resolution.py`:
```python
import pytest
from app.glue.core.dialogue import DialogueEngine
from app.glue.core.session import GlueSession

@pytest.mark.asyncio
async def test_resolving_entity_does_not_typeerror(monkeypatch, fake_session):
    """B1: resolve(text, entity_type_hint=...) 签名错配已修，不再 TypeError"""
    engine = DialogueEngine(...)  # 按现有构造补全依赖
    # 让 entity_resolver.resolve 返回一个消解成功结果
    async def fake_resolve(text, entity_type, session):
        from app.glue.core.types import EntityResolveResult
        return EntityResolveResult(entity_id=1, entity_type=entity_type, confidence=0.9)
    monkeypatch.setattr(engine.entity_resolver, "resolve", fake_resolve)
    result = await engine.dispatch("跟进张三", fake_session, context={"entity_type": "Customer"})
    assert result.action.name != "ERROR"  # 不再因 TypeError 进 ERROR
```
（`fake_session` fixture 按 `GlueSession` 现有构造补全。）

- [ ] **Step 3: 跑测试确认失败**

Run: `pytest tests/glue/test_dialogue_entity_resolution.py -v`
Expected: FAIL（TypeError: unexpected keyword argument 'entity_type_hint'）

- [ ] **Step 4: 修签名**

`dialogue.py:438-442` 改为：
```python
resolve_result = await self.entity_resolver.resolve(
    text,
    entity_type=context.get("entity_type"),
    session=session,
)
```
（`keyword` 不再传——`resolve` 内部已用 LLM 抽取 `name_keyword`，见 `entity.py:226-249`。）

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/glue/test_dialogue_entity_resolution.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/glue/core/dialogue.py tests/glue/test_dialogue_entity_resolution.py
git commit -m "fix(glue): align resolve() call signature with EntityResolver (B1)"
```

### Task 2.2：修复 execute() 缺 action_id（B2，EXECUTE 分支）

**Files:**
- Modify: `app/glue/core/dialogue.py:733`

**Interfaces:**
- Consumes: `ActionExecutor.execute(self, pending, action_id: str) -> ExecutionResult`（`executor.py:170`，已存在不改；action_id 用于审计归因，透传到 `entry.<method>(..., action_id=action_id)`）

- [ ] **Step 1: 确认调用点上下文**

读 `dialogue.py:720-745`，确认 `_handle_executing` 分支，以及是否已有 pending.action_id 可复用（`PendingAction` 可能已生成 action_id）。

- [ ] **Step 2: 写失败测试**

`tests/glue/test_dialogue_execute.py`:
```python
@pytest.mark.asyncio
async def test_execute_branch_does_not_typeerror(monkeypatch, fake_session_with_pending):
    """B2: execute(pending) 缺 action_id 已修"""
    engine = DialogueEngine(...)
    async def fake_execute(pending, action_id):
        from app.glue.core.executor import ExecutionResult
        assert action_id  # action_id 非空
        return ExecutionResult(success=True, message="ok", action_id=action_id)
    monkeypatch.setattr(engine.action_executor, "execute", fake_execute)
    result = await engine.dispatch("确认", fake_session_with_pending)
    assert result.success
```

- [ ] **Step 3: 跑测试确认失败**

Run: `pytest tests/glue/test_dialogue_execute.py -v`
Expected: FAIL（TypeError: missing 1 required positional argument: 'action_id'）

- [ ] **Step 4: 修调用，生成 action_id**

`dialogue.py:733` 改为（确认 `dialogue.py` 顶部已 import uuid，否则加 `import uuid`）：
```python
action_id = pending.action_id or str(uuid.uuid4())
exec_result = await self.action_executor.execute(pending, action_id)
```
（若 `PendingAction` 无 `action_id` 字段，直接 `action_id = str(uuid.uuid4())`。）

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/glue/test_dialogue_execute.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/glue/core/dialogue.py tests/glue/test_dialogue_execute.py
git commit -m "fix(glue): pass action_id to execute() (B2)"
```

### Task 2.3：修复 exec_result 不存在字段访问（B3，AttributeError）

**Files:**
- Modify: `app/glue/core/dialogue.py:800-803`

**Interfaces:**
- Consumes: `ExecutionResult` 字段 = `success / message / action_id / data / error`（`executor.py:32-40`，无 `skill_name`/`action_name`）

- [ ] **Step 1: 读 800-803 确认意图**

读 `dialogue.py:795-815`，确认原代码想从 exec_result 取什么（多半是给用户回显"已执行 X 动作"）。`skill_name`/`action_name` 应替换为 `pending.intent_type`（PendingAction 上有意图类型）+ `exec_result.message`。

- [ ] **Step 2: 写失败测试**

`tests/glue/test_dialogue_exec_result_fields.py`:
```python
@pytest.mark.asyncio
async def test_exec_result_message_renders_without_attributeerror(monkeypatch, fake_session_with_pending):
    engine = DialogueEngine(...)
    async def fake_execute(pending, action_id):
        from app.glue.core.executor import ExecutionResult
        return ExecutionResult(success=True, message="跟进已创建", action_id=action_id)
    monkeypatch.setattr(engine.action_executor, "execute", fake_execute)
    result = await engine.dispatch("确认", fake_session_with_pending)
    assert "跟进" in (result.message or "")
    assert result.success
```

- [ ] **Step 3: 跑测试确认失败**

Run: `pytest tests/glue/test_dialogue_exec_result_fields.py -v`
Expected: FAIL（AttributeError: 'ExecutionResult' object has no attribute 'skill_name'）

- [ ] **Step 4: 修字段访问**

`dialogue.py:800-803` 把 `exec_result.skill_name` / `exec_result.action_name` 替换为：
```python
intent_label = pending.intent_type
exec_msg = exec_result.message or ("成功" if exec_result.success else "失败")
# 用 intent_label + exec_msg 构造回显文本，原 skill_name/action_name 用法替换之
```
（具体回显语句按现有文案风格补全，不引入新字段。）

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/glue/test_dialogue_exec_result_fields.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/glue/core/dialogue.py tests/glue/test_dialogue_exec_result_fields.py
git commit -m "fix(glue): use ExecutionResult.message instead of nonexistent fields (B3)"
```

### Task 2.4：修复 safety.py Optional 未导入（B4，NameError）

**Files:**
- Modify: `app/glue/core/safety.py:9`

- [ ] **Step 1: 写失败测试**

`tests/glue/test_safety_imports.py`:
```python
def test_safety_module_imports_clean():
    """B4: safety.py 被 import 不应 NameError"""
    import importlib
    mod = importlib.import_module("app.glue.core.safety")
    assert hasattr(mod, "SafetyGateway")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/glue/test_safety_imports.py -v`
Expected: FAIL（NameError: name 'Optional' is not defined）—— 注：仅当有代码 import safety 才触发；若当前无人 import，先手动 `python -c "import app.glue.core.safety"` 复现。

- [ ] **Step 3: 修 import**

`safety.py:9` 把 `from typing import Dict, Any` 改为 `from typing import Dict, Any, Optional`。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/glue/test_safety_imports.py -v && python -c "import app.glue.core.safety"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/glue/core/safety.py tests/glue/test_safety_imports.py
git commit -m "fix(glue): import Optional in safety.py (B4)"
```

### Task 2.5：IM 异步 stub 改为显式 503（诚实失败）

**Files:**
- Modify: `app/glue/api/inbound.py:130-138`

- [ ] **Step 1: 写失败测试**

`tests/glue/test_inbound_async_503.py`:
```python
@pytest.mark.asyncio
async def test_im_async_channel_returns_503_not_fake_ok(client, monkeypatch):
    """IM 异步队列未实现，必须 503 而非 ok=True 假装成功"""
    req = {  # async_delivery=True 的 IM 渠道
        "channel_user_id": "u1", "message_id": "m1", "text": "hi",
        "timestamp": 1700000000, "channel_chat_id": "c1",
    }
    # 构造 channel_config 使 async_delivery=True（按 inbound.py:125 的判定补全）
    resp = await client.post("/api/glue/v1/inbound", json=req)
    assert resp.status_code == 503
    assert "异步" in resp.json()["detail"] or "未实现" in resp.json()["detail"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/glue/test_inbound_async_503.py -v`
Expected: FAIL（当前返回 200 + ok=True + 假 reply_token）

- [ ] **Step 3: 改为 503**

`inbound.py:130-138` 把"生成 reply_token 然后 return"替换为：
```python
# IM 异步队列尚未实现（原 TODO），诚实返回 503
raise HTTPException(
    status_code=503,
    detail="IM 异步投递队列尚未实现，请使用 web 同步渠道或联系管理员",
)
```
（`from fastapi import HTTPException` 若未 import 则补。）

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/glue/test_inbound_async_503.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/glue/api/inbound.py tests/glue/test_inbound_async_503.py
git commit -m "fix(glue): return 503 for unimplemented IM async delivery"
```

### Task 2.6：接通 executor.preview()，让 PREVIEW 状态生成真实快照（B5）

**Files:**
- Modify: `app/glue/core/dialogue.py`（PREVIEW 进入分支调用 `action_executor.preview(pending)`，填 `pending.preview_snapshot`）

**Interfaces:**
- Consumes: `ActionExecutor.preview(self, pending) -> PreviewResult`（`executor.py:108-168`，已实现未调用）
- Produces: `PendingAction.preview_snapshot` 不再恒空；PREVIEW 状态向用户展示真实变更预览

- [ ] **Step 1: 读 PREVIEW 进入逻辑**

读 `dialogue.py:320-340`（`_handle_idle` slots 齐全时 `next_mode=PREVIEW`）与 `_handle_preview` `:590-711`。确认进入 PREVIEW 前在何处能插入 `preview()` 调用并写 `pending.preview_snapshot`。

- [ ] **Step 2: 写失败测试**

`tests/glue/test_dialogue_preview_snapshot.py`:
```python
@pytest.mark.asyncio
async def test_preview_generates_snapshot(monkeypatch, fake_session):
    engine = DialogueEngine(...)
    captured = {}
    async def fake_preview(pending):
        from app.glue.core.executor import PreviewResult
        captured["called"] = True
        return PreviewResult(success=True, changes=[{"field":"amount","old":None,"new":1000}], message="将创建商机")
    monkeypatch.setattr(engine.action_executor, "preview", fake_preview)
    # 触发一个 slots 齐全的 init_opportunity 意图进入 PREVIEW
    result = await engine.dispatch("创建商机金额1000万", fake_session)
    assert captured.get("called") is True
    assert result.data and result.data.get("preview_snapshot")
```
（`PreviewResult` 字段以 `executor.py:108-168` 实际返回为准，按实际结构调整断言。）

- [ ] **Step 3: 跑测试确认失败**

Run: `pytest tests/glue/test_dialogue_preview_snapshot.py -v`
Expected: FAIL（preview 从未被调用，captured 为空）

- [ ] **Step 4: 接通 preview()**

在 `_handle_idle` 写入 `next_mode=SessionMode.PREVIEW` 之前（约 `dialogue.py:326`），插入：
```python
preview_result = await self.action_executor.preview(pending)
if preview_result.success:
    pending.preview_snapshot = {
        "changes": preview_result.changes,
        "message": preview_result.message,
    }
    # 把 preview 内容带进本轮 DialogueResult.data 供前端展示
else:
    return DialogueResult(action=DialogueAction.ERROR, success=False,
                          message=preview_result.message or "生成预览失败")
```
（`preview_result` 字段名按 `executor.py` 实际返回对齐；若 `preview()` 返回 `ActionEntryResult` 而非独立 PreviewResult，按其 `plan.changes` / `message` 取值。）

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/glue/test_dialogue_preview_snapshot.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/glue/core/dialogue.py tests/glue/test_dialogue_preview_snapshot.py
git commit -m "fix(glue): wire executor.preview() so PREVIEW state shows real snapshot (B5)"
```

### Task 2.7：Glue web 同步路径端到端验证

**Files:**
- Test: `tests/glue/test_e2e_web_sync.py`（新增）

- [ ] **Step 1: 写端到端 happy path 测试**

```python
@pytest.mark.asyncio
async def test_e2e_create_opportunity_happy_path(client, fake_authed_user, monkeypatch):
    """Glue web 同步路径: 创建商机金额1000万 → PREVIEW(带快照) → 确认 → EXECUTE → ActionEntry"""
    # 第一轮: 进 PREVIEW
    r1 = await client.post("/api/glue/v1/inbound", json={
        "channel_user_id": "u1", "message_id": "m1",
        "text": "创建商机金额1000万", "timestamp": 1700000000,
    })
    assert r1.status_code == 200
    body1 = r1.json()["reply"]
    assert body1["mode"] == "preview"
    assert body1["data"].get("preview_snapshot")
    # 第二轮: 确认 → EXECUTE
    r2 = await client.post("/api/glue/v1/inbound", json={
        "channel_user_id": "u1", "message_id": "m2",
        "text": "确认", "timestamp": 1700000001,
    })
    assert r2.status_code == 200
    assert r2.json()["reply"]["mode"] in ("completed", "execute_done")
```
（断言的 mode 字面量按 `dialogue.py` `next_mode` 实际值对齐。）

- [ ] **Step 2: 写实体消解路径测试**

```python
@pytest.mark.asyncio
async def test_e2e_entity_resolution_path(client, fake_authed_user, seed_customer_named_zhangsan):
    """Glue web: '跟进张三' → RESOLVING_ENTITY → 消解 → PREVIEW，不 500"""
    r = await client.post("/api/glue/v1/inbound", json={
        "channel_user_id": "u1", "message_id": "m1",
        "text": "跟进张三", "timestamp": 1700000000,
    })
    assert r.status_code == 200  # 不再 500
    body = r.json()["reply"]
    # 要么消解成功进 preview，要么歧义返回候选列表
    assert body["mode"] in ("preview", "ambiguity", "collect")
```

- [ ] **Step 3: 跑端到端测试**

Run: `pytest tests/glue/test_e2e_web_sync.py -v`
Expected: PASS（若 Task 2.1-2.6 都已过，此处应绿）

- [ ] **Step 4: 全量回归**

Run: `pytest -x`
Expected: 无新增失败。

- [ ] **Step 5: Commit**

```bash
git add tests/glue/test_e2e_web_sync.py
git commit -m "test(glue): e2e web sync happy path + entity resolution path"
```

---

# Phase 3：能力迁移 ReAct → Glue，退役 ReAct（高风险，建议 subagent-driven）

**Ship gate**：Phase 3 结束后，`/v1/agent/chat` 流量由 Glue 承担（或端点代理到 Glue），前端 SSE 事件兼容不破；Glue 具备 SSE 流式 / uuid Session / 风险分级门 / 真实 Preview 快照 / 轮次管理；`app/services/agent/` 删除后 `pytest` 全绿、app 启动正常。

> **执行建议**：本 Phase 风险最高，每个 Task 建议用 subagent-driven-development 派独立 subagent + 两阶段 review。Task 3.1（SSE）与 3.6（删 ReAct）是最大改动点，务必在 3.6 之前完成 3.1-3.5 并全量回归。

### Task 3.1：Glue inbound SSE 流式化

**Files:**
- Create: `app/glue/core/sse_streamer.py`
- Modify: `app/glue/core/dialogue.py`（新增 `dispatch_stream` async generator）
- Modify: `app/glue/api/inbound.py`（web 渠道改 `StreamingResponse`）

**Interfaces:**
- Consumes: ReAct SSE 事件契约 `app/services/agent/sse_streamer.py:57-139`（7 类 event：`start`/`react_start`/`round_start`/`tool_call`/`tool_result`/`round_completed`/`react_complete`/`result`/`complete`/`error`）。前端依赖 `start`/`result`/`complete`/`error`。
- Produces: `GlueSSEStreamer.stream(dispatch, session, session_id) -> AsyncGenerator[str]`，yield `f"event: {name}\ndata: {json}\n\n"`；保留 `start`/`result`/`complete`/`error` 事件名与关键字段，新增 Glue 语义中间事件 `intent`/`entity`/`preview`/`execute`。其中 `preview` 事件 data 必含 `outcome_type: "win"|"lose"|"generic"`（供前端 DangerConfirmCard 区分赢单=success-green / 输单=neutral-grey / 通用高风险=danger-red，见前端方案「UI 设计补充」；取值由 Task 3.3 SafetyGateway 透出）。

- [ ] **Step 1: 读 ReAct SSE streamer 全文，记录事件契约**

读 `app/services/agent/sse_streamer.py:27-139`。记录：`start` payload `{session_id}`；`result` payload `{event:'result', success, message, content, answer, rounds, is_partial}`；`complete` payload `{answer, rounds, is_partial}`；`error` payload `{message}`。

- [ ] **Step 2: 写失败测试——SSE 事件序列**

`tests/glue/test_sse_stream.py`:
```python
@pytest.mark.asyncio
async def test_glue_sse_emits_start_result_complete(monkeypatch, fake_session):
    from app.glue.core.sse_streamer import GlueSSEStreamer
    from app.glue.core.dialogue import DialogueEngine
    engine = DialogueEngine(...)
    streamer = GlueSSEStreamer()
    events = []
    async for ev in streamer.stream(engine, fake_session, "sess-1", text="创建商机金额1000万"):
        events.append(ev)
    joined = "".join(events)
    assert "event: start" in joined
    assert "event: result" in joined
    assert "event: complete" in joined
    assert '"is_partial"' in joined
```

- [ ] **Step 3: 跑测试确认失败**

Run: `pytest tests/glue/test_sse_stream.py -v`
Expected: FAIL（`GlueSSEStreamer` 不存在）

- [ ] **Step 4: 实现 GlueSSEStreamer**

`app/glue/core/sse_streamer.py`:
```python
import json
from typing import AsyncGenerator
from app.glue.core.dialogue import DialogueEngine
from app.glue.core.session import GlueSession


class GlueSSEStreamer:
    """Glue 对话 SSE 流式封装，事件契约对齐 ReAct sse_streamer（兼容前端）。"""

    async def stream(self, engine: DialogueEngine, session: GlueSession,
                     session_id: str, text: str) -> AsyncGenerator[str, None]:
        try:
            yield self._evt("start", {"session_id": session_id})
            # dispatch_stream 是 DialogueEngine 新增的 async generator，
            # yield 中间状态 (intent/entity/preview/execute) 与最终结果
            final = None
            async for phase in engine.dispatch_stream(text, session):
                name = phase.get("event")  # "intent"|"entity"|"preview"|"execute"
                yield self._evt(name, phase.get("data", {}))
                if name == "execute":
                    final = phase
            answer = (final or {}).get("data", {}).get("message", "")
            yield self._evt("result", {
                "event": "result", "success": True,
                "message": answer, "content": answer, "answer": answer,
                "rounds": 1, "is_partial": False,
            })
            yield self._evt("complete", {"answer": answer, "rounds": 1, "is_partial": False})
        except Exception as e:
            yield self._evt("error", {"message": str(e)})

    @staticmethod
    def _evt(name: str, data: dict) -> str:
        return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
```

- [ ] **Step 5: 在 DialogueEngine 增加 dispatch_stream**

在 `dialogue.py` 现有 `dispatch` 基础上抽出 `dispatch_stream`（async generator），在状态机关键节点 yield：
```python
async def dispatch_stream(self, text: str, session: GlueSession):
    # 进入 IDLE → 意图解析后 yield {"event":"intent","data":{...}}
    # 实体消解后 yield {"event":"entity","data":{...}}
    # preview 生成后 yield {"event":"preview","data":{"preview_snapshot":..., "outcome_type":"win"|"lose"|"generic"}}
    # execute 后 yield {"event":"execute","data":{"message":..., "success":...}}
    ...
# dispatch（同步返回 DialogueResult）改为消费 dispatch_stream 的最后一个 phase
async def dispatch(self, text, session, context=None):
    final = None
    async for phase in self.dispatch_stream(text, session):
        if phase.get("event") == "execute":
            final = phase
    # 由 final 构造并返回 DialogueResult
```
（具体在哪些行 yield，按 `dispatch` 现有状态机分支逐个插入；保持 `dispatch` 返回值兼容 Phase 2 的测试。）

- [ ] **Step 6: inbound web 渠道改 StreamingResponse**

`inbound.py` web 分支（`async_delivery=False`）改为：
```python
from fastapi.responses import StreamingResponse
from app.glue.core.sse_streamer import GlueSSEStreamer

session_id = str(uuid.uuid4())  # 或复用 session 既有 id
engine = DialogueEngine(...)
streamer = GlueSSEStreamer()
return StreamingResponse(
    streamer.stream(engine, session, session_id, request.text),
    media_type="text/event-stream",
    headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
)
```
（保留 `InboundResponse` schema 用于非流式场景；web 流式路径不再返回 `InboundResponse`。）

- [ ] **Step 7: 跑测试确认通过**

Run: `pytest tests/glue/test_sse_stream.py tests/glue/test_e2e_web_sync.py -v`
Expected: PASS（e2e 测试若因响应从 JSON 改 SSE 需调整断言，同步更新）

- [ ] **Step 8: Commit**

```bash
git add app/glue/core/sse_streamer.py app/glue/core/dialogue.py app/glue/api/inbound.py tests/glue/test_sse_stream.py
git commit -m "feat(glue): SSE streaming for web channel, event-compatible with ReAct"
```

### Task 3.2：统一 Session API 为 uuid 寻址

**Files:**
- Modify: `app/glue/core/session.py:62-275`（key 改 uuid）
- Modify: `app/glue/api/admin.py:75-120`（session 端点改 session_id 寻址，对齐 ReAct 响应 schema）

**Interfaces:**
- Produces: `SessionManager.load(session_id) / save(session) / clear(session_id)`；`GET /api/glue/v1/sessions/{session_id}` 返回 `{session_id, messages, tool_history, recent_entities}`（对齐 `agent_assistant.py:132`）；`DELETE` 返回 `{message, session_id}`。

- [ ] **Step 1: 写失败测试——uuid 寻址**

`tests/glue/test_session_uuid.py`:
```python
@pytest.mark.asyncio
async def test_session_crud_by_session_id(redis_client):
    from app.glue.core.session import SessionManager
    sm = SessionManager(redis_client)
    sid = await sm.create(tenant_id=1, crm_user_id=2)  # 返回 uuid session_id
    assert await sm.load(sid) is not None
    await sm.clear(sid)
    assert await sm.load(sid) is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/glue/test_session_uuid.py -v`
Expected: FAIL（当前 `load(tenant_id, crm_user_id)` 签名）

- [ ] **Step 3: 改 SessionManager key 与签名**

`session.py`：key 从 `ai:glue:session:{tenant}:{user}` 改为 `ai:glue:session:{session_id}`；`GlueSession` 增加 `session_id` 字段（uuid4）；新增 `async create(tenant_id, crm_user_id) -> str` 生成 session_id 并存；`load/save/clear` 改为 `session_id` 入参。保留 `(tenant, user)` 作为 session 内字段用于权限校验。

- [ ] **Step 4: 改 admin 端点对齐 ReAct schema**

`admin.py:75-120` 路由改 `/sessions/{session_id}`，GET 返回完整 messages/tool_history/recent_entities（脱敏 pending 可选），DELETE 返回 `{message, session_id}`。加 session 归属校验（验证 session.team_id/user_id 匹配当前用户，修 ReAct DELETE 无校验的缺陷）。

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/glue/test_session_uuid.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/glue/core/session.py app/glue/api/admin.py tests/glue/test_session_uuid.py
git commit -m "refactor(glue): session keyed by uuid session_id, align API with ReAct"
```

### Task 3.3：接通 SafetyGateway，风险分级门替代 universal confirm

**Files:**
- Modify: `app/glue/core/dialogue.py`（import SafetyGateway，在 PREVIEW/EXECUTE 决策点按 risk 等级分流）
- Verify: `app/constants/ai_rules.py:114-74` risk 阈值接线

**Interfaces:**
- Consumes: `SafetyGateway`（`safety.py`，B4 已修可 import）的 `INTENT_RISK_MAP` + `RISK_CONFIG`（0.85/0.90/1.0）
- Produces: LOW + confidence≥0.85 自动放行；MEDIUM + ≥0.90 自动放行；HIGH（win/lose）强制确认；不达标进 HUMAN_LOOP。`RiskDecision` 含 `outcome_type: "win"|"lose"|"generic"`（win=`win_opportunity`、lose=`lose_opportunity`、其余 HIGH=`generic`），随 `preview` 事件透出供前端 DangerConfirmCard 分态染色（见前端方案「UI 设计补充」）。

- [ ] **Step 1: 写失败测试——风险分级**

`tests/glue/test_safety_gate.py`:
```python
@pytest.mark.asyncio
async def test_low_risk_high_confidence_auto_executes(monkeypatch, fake_session):
    """create_follow_up(LOW) + confidence 0.9 → 不等用户确认直接 EXECUTE"""
    engine = DialogueEngine(...)
    # 让 intent 返回 create_follow_up, confidence 0.9
    result = await engine.dispatch("跟进张三，刚通了电话", fake_session)
    assert result.action.name == "EXECUTE_ACTION"  # 跳过 PREVIEW 等待

@pytest.mark.asyncio
async def test_high_risk_forces_confirm(monkeypatch, fake_session_with_pending_win):
    """win_opportunity(HIGH) → 必须等用户确认"""
    engine = DialogueEngine(...)
    result = await engine.dispatch("确认赢单", fake_session_with_pending_win)
    # 一次性"确认赢单"不应直接执行 HIGH，需二次确认
    assert result.action.name == "PREVIEW_ACTION"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/glue/test_safety_gate.py -v`
Expected: FAIL（当前 Glue 所有 action 都 universal confirm / 或全走同一逻辑）

- [ ] **Step 3: 接入 SafetyGateway**

`dialogue.py` 顶部 import 加 `from app.glue.core.safety import SafetyGateway`；构造 `self.safety = SafetyGateway()`。在 `_handle_idle` slots 齐全判定处：
```python
risk = self.safety.assess(pending.intent_type, intent_confidence)
if risk.level == "LOW" and risk.confidence >= 0.85:
    next_mode = SessionMode.EXECUTING  # 自动放行
elif risk.level == "MEDIUM" and risk.confidence >= 0.90:
    next_mode = SessionMode.EXECUTING
else:
    next_mode = SessionMode.PREVIEW  # HIGH 或不达标 → 人工确认
# outcome_type 随 preview 事件透出，供前端 DangerConfirmCard 分态染色（见前端方案「UI 设计补充」）
outcome_type = (
    "win" if pending.intent_type == "win_opportunity"
    else "lose" if pending.intent_type == "lose_opportunity"
    else "generic"
)
```
（`SafetyGateway.assess` 方法名/返回按 `safety.py` 实际对齐；若该方法不存在，按 `INTENT_RISK_MAP`+`RISK_CONFIG` 在 SafetyGateway 上补一个 `assess(intent, confidence) -> RiskDecision`。`RiskDecision` 须带 `outcome_type` 字段，由上面三元推导填充，并经 `preview` 事件 data 透出。）

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/glue/test_safety_gate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/glue/core/dialogue.py app/glue/core/safety.py tests/glue/test_safety_gate.py
git commit -m "feat(glue): risk-tiered safety gate replaces universal confirm"
```

### Task 3.4：Glue 轮次管理（MAX_ROUNDS + 超限降级）

**Files:**
- Modify: `app/glue/core/dialogue.py`（多意图 pending_queue 加全局轮次计数 + 上限 + is_partial）
- Modify: `app/glue/core/session.py`（`GlueSession` 加 `round_count` 字段）

- [ ] **Step 1: 写失败测试——轮次上限**

`tests/glue/test_round_limit.py`:
```python
@pytest.mark.asyncio
async def test_multi_intent_exceeds_max_rounds_marks_partial(monkeypatch, fake_session):
    """超过 MAX_ROUNDS 时 is_partial=True，不再继续执行"""
    engine = DialogueEngine(...)
    engine.MAX_ROUNDS = 3
    # 构造一个会无限循环/超 3 轮的多意图场景
    result = await engine.dispatch("...", fake_session)
    assert result.data.get("is_partial") is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/glue/test_round_limit.py -v`
Expected: FAIL（无轮次管理）

- [ ] **Step 3: 加轮次计数**

`GlueSession` 加 `round_count: int = 0`。`dispatch_stream` 每次 consume 一个 pending 前自增 `session.round_count`，超过 `self.MAX_ROUNDS`（默认 10，对齐 ReAct）则 yield `execute` 失败 + `is_partial=True` 并停止。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/glue/test_round_limit.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/glue/core/dialogue.py app/glue/core/session.py tests/glue/test_round_limit.py
git commit -m "feat(glue): MAX_ROUNDS turn limit with is_partial degradation"
```

### Task 3.5：路由收敛——/v1/agent/chat 代理到 Glue

**Files:**
- Modify: `app/api/agent_assistant.py:54-106`（POST /v1/agent/chat 内部转调 Glue SSE，或保留端点作 thin proxy）

> **决策点**：保留 `/v1/agent/chat` 作为前端兼容入口，内部代理到 Glue（避免前端改路由）；或前端改调 `/api/glue/v1/inbound`。本 Task 采用前者（最小前端改动）。

- [ ] **Step 1: 写失败测试——/v1/agent/chat 走 Glue**

`tests/api/test_agent_chat_proxy.py`:
```python
@pytest.mark.asyncio
async def test_agent_chat_streams_via_glue(client, fake_authed_user, monkeypatch):
    resp = await client.post("/v1/agent/chat", json={"content": "创建商机金额1000万"})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    body = resp.text
    assert "event: start" in body and "event: complete" in body
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/api/test_agent_chat_proxy.py -v`
Expected: FAIL（仍走 ReAct streamer）

- [ ] **Step 3: 改端点为 Glue 代理**

`agent_assistant.py:54` 的 `POST /v1/agent/chat` 把 `AgentSSEStreamer().stream_agent_run(agent, ...)` 替换为构造 `DialogueEngine` + `GlueSSEStreamer().stream(engine, session, session_id, request.content)`。保留 `session_id` 生成与 SSE headers。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/api/test_agent_chat_proxy.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/agent_assistant.py tests/api/test_agent_chat_proxy.py
git commit -m "refactor: /v1/agent/chat proxies to Glue SSE"
```

### Task 3.6：退役 ReAct agent

**Files:**
- Delete: `app/services/agent/`（core.py, tools.py, prompts.py, memory.py, sse_streamer.py, edge_scenarios.py, fallback_handler.py, summary_monitor.py, phase_contracts.py, handlers/, __init__.py）
- Delete: ReAct-only skills handlers（确认 `app/services/skills/handlers/` 中仅 ReAct 用、HandlerFactory 不再需要的；HandlerFactory 经 calendar 路径仍 live 的保留）
- Delete: `app/constants/tools.py` 余下 `TOOL_HANDLER_MAP`（ReAct 唯一引用已删）
- Delete: `app/api/agent_assistant.py` 的 ReAct session 端点（`GET/DELETE /v1/agent/session/{id}` 改由 Glue admin 端点承担，Task 3.2 已就绪）；或保留代理

- [ ] **Step 1: 复核 agent/ 无残留引用**

Run: `grep -rn "from app.services.agent\|app.services.agent\." app/ --include=*.py | grep -v "app/services/agent/"`
Expected: 仅 `app/api/agent_assistant.py` 命中（Task 3.5 已改为 Glue 代理，不再 import ReAct core）。

- [ ] **Step 2: 确认 skills/handlers 哪些仅 ReAct 用**

Run: `grep -rn "from app.services.skills.handlers\|skills.handlers\." app/ --include=*.py | grep -v "app/services/skills/"`
Expected: 若 HandlerFactory（calendar 路径）仍 import 一批 handler，则那批保留；仅被 `app/services/agent/tools.py` 引用且 HandlerFactory 不用的可删。逐个判定后列删除清单。

- [ ] **Step 3: 删除 agent/ 与 ReAct-only handlers**

Run: `rm -rf app/services/agent/` + 按上一步清单删 ReAct-only handlers。

- [ ] **Step 4: 删 constants/tools.py 余下**

若 `TOOL_HANDLER_MAP` 无其他引用（Run: `grep -rn "TOOL_HANDLER_MAP" app/` 零命中），删除整个 `app/constants/tools.py` 或其中 `TOOL_HANDLER_MAP` 段。

- [ ] **Step 5: 全量回归 + 启动**

Run: `pytest -x && python -c "import app.main"`
Expected: 全绿、无 ImportError。

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: retire ReAct agent, Glue is sole AI assistant path"
```

---

# Phase 4：面向 Agent 的工具设计质量（Glue intent 契约优化）

**Ship gate**：Phase 4 结束后，Glue 的 LLM-facing intent 契约符合 muratcankoylan 工具设计技能——每个 intent 描述回答 what/when/inputs/returns；intent 字面量与枚举一致；错误信息 actionable；响应有 concise/detailed 双档；多意图置信度真实；结构化输出硬化。

### Task 4.1：统一 intent prompt 字面量与 IntentType 枚举

**Files:**
- Modify: `app/glue/core/intent.py:67-80,123-133`（prompt 里的 `update_stage`/`init_opportunity` 等与 `app/constants/ai_rules.py:79-95` `IntentType` 对齐）

- [ ] **Step 1: 列出不一致项**

读 `ai_rules.py:79-95` `IntentType` 与 `intent.py:67-80` prompt 字面量。已知不一致：prompt 用 `update_stage`，枚举有 `ADVANCE_STAGE="advance_stage"`；prompt 用 `init_opportunity`，枚举有 `CREATE_OPPORTUNITY`。逐项列清单。

- [ ] **Step 2: 写测试——intent 输出值必在枚举内**

`tests/glue/test_intent_enum_consistency.py`:
```python
def test_intent_prompt_literals_match_enum():
    from app.glue.core.intent import INTENT_PARSE_PROMPT
    from app.constants.ai_rules import IntentType
    valid = {e.value for e in IntentType}
    # 抽取 prompt 里列出的 intent 名，断言每个都在 valid 内
    ...
```

- [ ] **Step 3: 对齐**

以枚举为准改 prompt 字面量（或以业务命名为准改枚举——二选一，建议改 prompt 对齐枚举，因枚举被代码引用更广）。同步 `executor.py:236-407` if/elif 的 `intent_type ==` 字面量。

- [ ] **Step 4: 跑测试 + Commit**

Run: `pytest tests/glue/test_intent_enum_consistency.py -v` → PASS
```bash
git add app/glue/core/intent.py app/glue/core/executor.py tests/glue/test_intent_enum_consistency.py
git commit -m "fix(glue): align intent prompt literals with IntentType enum"
```

### Task 4.2：intent prompt 注入各 intent 真实必填 slots

**Files:**
- Modify: `app/glue/core/intent.py`（prompt 中每个 intent 标注 required fields，而非扁平固定 slots schema）

- [ ] **Step 1: 抽取 `_check_missing_fields` 的 required_fields 表**

读 `intent.py:559-594`，把硬编码 `required_fields` dict 整理成 intent→required 映射。

- [ ] **Step 2: 重写 prompt 的 slots 段**

在 `INTENT_PARSE_PROMPT` 里，把扁平 slots schema 改为按 intent 分组：
```
各意图必填字段：
- create_follow_up: entity_reference(客户名), content(跟进内容)
- init_opportunity: entity_reference(客户名), amount(金额)
- update_stage: entity_reference(商机名), stage(目标阶段: 需求确认/方案沟通/报价谈判/合同签订)
- win_opportunity / lose_opportunity: entity_reference(商机名)
- set_reminder: reminder_time(YYYY-MM-DD), content
```
（stage 枚举值查 `app/constants/opportunity_status.py`，禁止推断。）

- [ ] **Step 3: 测试 LLM 能看到 required + Commit**

写测试断言 prompt 字符串包含各 intent 的必填字段名。Run pass 后 commit。

### Task 4.3：错误信息升级为 actionable

**Files:**
- Modify: `app/glue/core/entity.py:121,150,175`、`app/glue/core/dialogue.py:498-503`、`app/services/agent/handlers/__init__.py`（若仍存在）的 0 结果/缺参错误

- [ ] **Step 1: 改 0 结果错误带恢复策略**

`entity.py:175` `f"未找到匹配的{entity_type}"` 改为：
```python
f"未找到匹配的{entity_type}。可尝试：1) 用更完整的名称（如'光大证券股份有限公司'）2) 用 #ID 引用（如'#123'）3) 描述更多特征"
```

- [ ] **Step 2: 改缺参错误带该用哪个参数**

`dialogue.py:498-503` 0 结果包装改为带具体重述建议；各 handler 缺参错误加"该参数从 X 工具结果获取"提示。

- [ ] **Step 3: 测试 + Commit**

断言错误字符串包含恢复关键词（"尝试"/"#ID"/"重新描述"）。

### Task 4.4：响应格式 concise/detailed 双档

**Files:**
- Modify: `app/services/ai/action_entry.py` 的 `get_entity_context` 等价（Phase 3 后由 Glue executor 的 query 路径承担）增加 `format` 参数

- [ ] **Step 1: 在 ActionEntry 的查询方法加 format 参数**

`concise` 返回 `{id, name, hint}`；`detailed` 返回完整 `{基本信息 + 关联实体 + 最近活动}`。description 标注何时用哪个。

- [ ] **Step 2: 测试 + Commit**

### Task 4.5：验证 ask_user / COLLECTING 伞形接通

**Files:**
- Verify: `app/glue/core/dialogue.py` `_handle_collecting` + `SlotCollector`

- [ ] **Step 1: 写测试——缺参时 Glue 主动追问**

`tests/glue/test_ask_user.py`: 输入"创建商机"（缺金额）→ Glue 进 COLLECTING 返回追问"请提供商机金额"，而非 ERROR。

- [ ] **Step 2: 若未接通则修复 + Commit**

### Task 4.6：多意图置信度不再硬编码 0.85

**Files:**
- Modify: `app/glue/core/intent.py:362`

- [ ] **Step 1: 用 LLM 返回的真实 confidence**

`intent.py:362` 把硬编码 `0.85` 改为读取多意图解析 LLM 输出的 `confidence` 字段。

- [ ] **Step 2: 测试 + Commit**

### Task 4.7：原生结构化输出硬化

**Files:**
- Modify: `app/services/ai_service.py:_stream_chat_collect`（增加严格 JSON 校验 + 重试，逐步替代 fence 剥离兜底）

- [ ] **Step 1: 加 json_schema 校验**

若供应商支持 `response_format={"type":"json_schema","json_schema":{...}}`，对关键调用（intent/entity）改用 json_schema 并加一次重试。否则保留 json_object + 严格 `json.loads` 失败则重试一次。

- [ ] **Step 2: 测试 + Commit**

---

# Phase 5：前端对齐 Glue 语义阶段（含 UI 视觉契约）

> **Ship gate**：Phase 5 结束后，前端从"ReAct 思考流 + 单步 PreviewCard"重构为"Glue 语义阶段驱动的统一确认/歧义/补全交互"；5 条核心路径（LOW 自动执行 / HIGH 二次确认 / 多候选选择 / 缺字段补全 / 0 结果 actionable 错误）端到端跑通；孤儿死码删除后 `npm run build` + `vitest` 全绿；触控 ≥44px、focus 环、对比度 ≥4.5:1、reduced-motion 达标。

**启动时机**：5.1-5.9 仅依赖类型契约，后端 Phase 2（Glue bug 修复）后即可 mock 联调；5.10 接线需后端 Phase 3.1（SSE 流式）+ 3.5（路由代理）就绪；5.12 删孤儿纯独立。建议 subagent-driven——5.1-5.4 一批、5.5-5.9 一批、5.10-5.14 一批，每批后 review。

## 5.0 现状基线（已审计事实）

### 活跃主线（能跑但轻量）

`src/views/AIAssistant.vue`（路由 `/ai-assistant`，仅左侧导航进入）= 对话气泡 + 紧贴的 `CompactExecutionLog` 步骤列表 + 单步 `PreviewCard` 确认。SSE 消费：`fetch` POST + `getReader()`（非 EventSource）→ `api/aiAssistant.ts:166-271 chatSSE`。

**活跃主线只接住了这些事件**：
- `content` → 流式追加 AI 气泡文本
- `parsed`/`awaiting_confirmation` → 内嵌 PreviewCard（字段配置来自 `previewFieldConfig.ts` 静态映射）
- `result`/`complete`/`react_complete` → 收尾
- `error` → 追加错误

**活跃主线用户接触不到的交互**（代码在孤儿里已实现但未挂载）：
- 多意图 `parsed_multi`（一句话多动作依次确认）—— `handleSSEEvent` 无此分支
- 歧义候选选择 `disambiguation_required` —— composable 落了 `step.data` 但**没设 `confirmationType`**，ExpandedView 的 `InlineCandidate` 分支永远不点亮
- 缺字段提问 `waiting_for_user`（missing_fields/options）—— `AIAssistant.vue` 只追加步骤，**无用户交互组件**，用户无法回答
- 危险富确认 `ConfirmationCard`（evidence_chain/undo_ttl/allow_edit）—— 仅孤儿

### 孤儿（封存但含完整能力，4092 行）

`src/components/MagicWandDialog.vue` + 9 个专用子组件 + `api/workflow.ts` 硬编码 `WORKFLOW_DEFINITIONS` + `composables/useSidebarState.ts` + `types/sidebar.ts`。`grep` 确认除自身外零 `.vue` 引用。前端最完整的交互能力在此，从未挂载——Phase 5 把其中歧义选择/危险富确认/表单补全能力抽出来复活，对齐 Glue 语义。

### 死码（可删，无活跃引用）

`ThinkingBubble.vue`（仅注释提及）、`ReactProgress.vue`/`AgentProgress.vue`（仅孤儿用）、`UndoToast.vue`（仅孤儿引用，按 undo 决策删除）、`aiAssistantApi.continueReactSSE`（`@deprecated`，但 PreviewCard confirm 当前竟走这条！）、`continueReactWithUserResponse`、`getReactSessionStatus`、`api/workflow.ts` 全套。

### 应保留作为重构基础

ChatBubble/ChatInput/HistoryList/WelcomeScreen/MarkdownContent/PreviewField、wolf-* token、aiConversation store、`useAgentExecutionLog` 的"步骤持久化回写 + localStorage 缓存 + auto-collapse"基础设施、`DynamicParamForm` + `ParamDefinition` schema 驱动表单能力。

## 5.1 新交互模型 + 可弃用清单

### 中心模型："对话为主线 + 语义阶段卡片"

放弃 ReAct 的"思考过程步骤流"作为视觉中心（用户关心的是"AI 要做什么/我要不要确认"，不是"AI 第 3 轮调了 search_customer"）。新的视觉中心：

```
一条用户消息 → 一条 AI 对话气泡（流式 content）
                ↓ 紧贴气泡内的语义阶段卡片（按 Glue phase 渐进出现）
   [意图识别] → [实体消解] → [预览快照] → [执行结果]
                ↑ 仅在"需要用户介入"时挂载交互组件
                  · 歧义候选选择（多实体命中）
                  · 缺字段补全表单
                  · 危险操作二次确认
```

**渐进披露**（ui-ux-pro-max `progressive-disclosure`）：默认折叠成一行摘要，用户点击展开看详情。与现有 `CollapsedView`/`ExpandedView` + auto-collapse 3s 基础设施契合。

### 五个语义阶段 ↔ 组件映射

| Glue SSE 事件 | 前端组件 | 交互 | 来源 |
|--------------|----------|------|------|
| `intent` | `PhaseSummary`（新建） | 不可交互的意图摘要；LOW+高置信自动放行 | 新建（薄） |
| `entity` + 唯一命中 | `PhaseSummary` | 不可交互的消解成功摘要 | 新建（薄） |
| `entity` + 多候选 | `EntityPicker`（从孤儿 `InlineCandidate`/`EntitySelectDialog` 合并复活） | **用户选一个候选** → 回传 entity_id | 复活孤儿 |
| `preview`（LOW/MEDIUM 自动放行） | `PhaseSummary` | 不可交互的预览摘要 + 自动执行 | 复用 PreviewCard 字段 |
| `preview`（HIGH 待确认） | `DangerConfirmCard`（从孤儿 `ConfirmationCard` 抽简复活） | **二次确认/取消** → 按 outcome 分态染色 | 复活孤儿 |
| 缺字段（`entity` 后判定 slots 不足） | `SlotFillForm`（复用 `DynamicParamForm` + `ParamDefinition`） | **填缺失字段** → 回传补全 slots | 复用现有 |
| `execute` | `PhaseSummary` | 执行中 → 成功摘要（无 UndoToast，按 undo 决策） | 复用 |
| `result`/`complete` | 对话气泡收尾 | 不可交互 | 现有 |
| `error` | `ErrorCard`（新建，带 actionable 恢复提示） | **按后端 error.recovery 提示**重述/换 ID/补充 | 新建 |

### 可弃用清单（按方案批准后执行）

| 组件/文件 | 处置 | 理由 |
|-----------|------|------|
| `MagicWandDialog.vue`（4092 行） | 删 | 孤儿，能力抽出后整体删除；`grep` 确认无活跃引用 |
| `api/workflow.ts` + `WORKFLOW_DEFINITIONS` | 删 | 仅孤儿用；硬编码工作流模板不属前端职责 |
| `composables/useSidebarState.ts` + `types/sidebar.ts` | 删 | 仅孤儿用 |
| `ReactProgress.vue`、`AgentProgress.vue` | 删 | 仅孤儿用，ReAct 轮次概念 |
| `ThinkingBubble.vue` | 删 | 死码（注释提及但无渲染） |
| `UndoToast.vue` | 删 | 仅孤儿引用；按 undo 决策不建 AI undo，删 UI 占位避免误导 |
| `WorkflowMiniMap.vue`、`StatusCard.vue`、`InlinePill.vue`、`ConfirmationCard.vue`、`EntitySelectDialog.vue` | 抽能力后删 | 能力合并进 `EntityPicker`/`DangerConfirmCard` 后删除原孤儿组件 |
| `aiAssistantApi.continueReactSSE`/`continueReactWithUserResponse`/`getReactSessionStatus` | 删 | `@deprecated` + 孤儿端点 |
| `useAgentExecutionLog` 中 `REACT_START/ROUND_START/ROUND_COMPLETED/REACT_COMPLETE/MAX_ROUNDS_REACHED` 分支 | 删 | ReAct 循环包装，Glue 无对应语义 |
| `SSEEventType` 中 `react_start/round_start/...` 等全部 ReAct/workflow 专有枚举 | 替换 | 换成 Glue 事件枚举 |
| `ExpandedView.vue` 的 WAITING 分支（InlineCandidate/CompactConfirmSummary/CompactInfoGap 三选一） | 删 | `confirmationType` 从未被设置，分支半死；由统一组件替代 |

## 5.2 UI 视觉契约（设计在既有 wolf-* token 体系内增量，零新增色相）

> 本节为 Task 5.4 / 5.5 / 5.6 / 5.7 / 5.9 的视觉契约，组件实现以本节为准。

### 设计定位

- **主体**：CRMWolf AI 助手——销售的交易副驾驶，把口语意图变成正确、可信任的 CRM 写操作。
- **受众**：中国 B2B 销售，高频日常使用，节奏快、容错低。
- **页面单职**：让一笔交易在几轮对话内从「已表达」走到「已执行且盖章确认」，且不犯不可逆的错。

### 既有体系（不推翻，在之上增量）

`variables.scss` 是成熟的克制系统：暖灰画布 `#F8F6F2`、低饱和商务蓝 `#4A6FA5`、IBM Plex Sans（display）+ IBM Plex Mono（AI/数据 vernacular）、仅 4 档字号、禁 700+ 字重、已有 AI signature（AI 消息 = 微蓝底 `#F0F4F8` + Mono 字）。它明确拒绝模板 warm cream 与通用 SaaS 配色。本补充只补新组件所需、而现有 token 尚未覆盖的视觉语言。

### 一处可论证的美学风险（仅此一处）

**把 lose 从 danger-red 降级为 neutral-grey 终态，把 win 提升为 stamp 式 success-green climax。**

- **论证**：销售丢单是正当业务结果（数据，不是错误），赢单是整条 AI phase pipeline 服务的目标。两者都染红既语义错位又打击士气。产品自己的审批状态已编码此区分（APPROVED=success-green / CANCELLED=neutral-grey / REJECTED=danger-red）——本设计是延伸既有约定，不是发明新色。
- **风险**：lose 不警示可能让销售误确认输单。
- **缓解**：防误放在文案与按钮不对称上（`我确认输单` 显式动作 + `▲ 不可撤销` Plex Mono 眉标 + 取消按钮始终可见），不放在警示色上。落地 `destructive-emphasis`：危险操作防误靠「确认按钮显式 + 不可逆声明」，不靠全局染红。
- **风险边界**：仅 win/lose 两态享受此分态；通用高风险（如未来 delete 类）仍走 danger-red。

### Token 增量（极小，全部指向既有 token，零新增色相）

新增至 `CRM-Client/src/styles/variables.scss`「审批状态语义色」段之后：

```scss
// ==================== AI phase 语义别名（指向既有功能色，不新增色相）====================
$wolf-phase-done:    $wolf-text-secondary;   // 已完成节点（#3A3A3A）
$wolf-phase-active:  $wolf-warning-text;     // 待用户介入 = 暂停关注 = 琥珀（#7A4F1E）
$wolf-phase-pending: $wolf-text-placeholder; // 未到达节点（#7A7A7A）

// ==================== deal outcome 语义（对齐既有审批状态约定）====================
// win = APPROVED = 成功绿；lose = CANCELLED = 中性灰终态（非错误）；generic risk = 危险红。
$wolf-outcome-win:      $wolf-success-text;  // 赢单 #2B633C
$wolf-outcome-win-bg:   $wolf-success-bg;    // #EDF7EF
$wolf-outcome-lose:     $wolf-text-tertiary; // 输单 #636363（中性灰终态）
$wolf-outcome-lose-bg:  $wolf-bg-hover;      // #F5F5F5
$wolf-outcome-risk:     $wolf-danger-text;   // 通用高风险 #7A2828
$wolf-outcome-risk-bg:  $wolf-danger-bg;     // #FCECEC

// ==================== 数字等宽特性（防 layout shift，number-tabular）====================
$wolf-numeric: tabular-nums lining-nums;
```

字体、间距、圆角、阴影零增量。phase 标签与盖印直接复用 `$wolf-font-mono`。

### 布局一：phase rail（嵌在 AI 消息内，复用 AI 专属底色 `#F0F4F8`）

rail 横向，因为销售的心智模型本就是横向 pipeline（需求确认→方案沟通→报价谈判→合同签订）。AI 四阶段与之同构——结构装置编码真实顺序，非装饰性编号。

```
┌─ AI ─── 微蓝底 #F0F4F8 ────────────────────────────────┐
│ 来跟进光大证券。                                       │
│                                                        │
│  意图 ── 实体 ── 预览 ── 执行     ← Plex Mono 12px 标签 │
│   ●       ●       ◐       ○      ← done/active/pending │
│  已识别  光大证券  待确认                              │
│                                                        │
│  ┌─ 预览 ─────────────────────────────────────────┐   │
│  │ 客户   光大证券股份有限公司                      │   │
│  │ 金额   ¥1,000 万        ← Plex Mono + tabular   │   │
│  └─────────────────────────────────────────────────┘   │
│                          [ 取消 ]  [ 确认跟进 ]        │
└────────────────────────────────────────────────────────┘
```

- 节点：已完成 `●` + `$wolf-phase-done`；未到 `○` + `$wolf-phase-pending`；当前待介入 `◐`（半填充）+ `$wolf-phase-active`。
- 连线 `──` 用 `$wolf-border-light`，1px。默认折叠为一行摘要（`意图✓ 实体✓ 预览·`），3s auto-collapse。

### 布局二：deal-outcome 盖印（signature——win/lose 执行成功后，替代通用 success toast）

盖印 = Plex Mono + 既有 success-green / neutral-grey + 1px 边框 + `$wolf-radius-sm`。每个 win/lose 仅出现一次。这是把 AI 整条 phase pipeline 的产物落成「这笔交易此刻状态变了」的视觉收据——thesis-as-hero 适配到产品时刻。

```
  赢单 climax：              输单 climax：
  ┌────────────┐            ┌────────────┐
  │ 赢单 · WON │            │ 输单 · LOST│   ← 中性灰，非红
  │ ¥1,000 万  │            │ 原因：价格 │
  └────────────┘            └────────────┘
   success-green 边框+底      neutral-grey 边框+底
   $wolf-outcome-win          $wolf-outcome-lose
```

盖印停留 5s 后淡出（`opacity 0.2s`，遵守 reduced-motion）。

### 五个 UX 组件的视觉契约

| 组件 | 视觉契约 |
|------|---------|
| **PhaseSummary**（5.4） | phase rail 节点；已完成 `●`+`$wolf-phase-done`，未到 `○`+`$wolf-phase-pending`，待介入 `◐`+`$wolf-phase-active`；标签 Plex Mono 12px；默认折叠为一行摘要，3s auto-collapse 复用既有计时 |
| **EntityPicker**（5.5） | 候选行 `① 光大证券股份有限公司 · 最近跟进 5/20`；整行可点 ≥44px；选中 = `$wolf-primary` 1px 边框 + `$wolf-primary-light` 底；`role=listbox`、候选项 `role=option`+`aria-selected`；hint 用 `$wolf-text-tertiary` 12px |
| **DangerConfirmCard**（5.6） | 三态：**win** → `$wolf-outcome-win` 边框+底 + 按钮 `我确认赢单`；**lose** → `$wolf-outcome-lose` 边框+底 + 按钮 `我确认输单`；**generic** → `$wolf-outcome-risk` 边框+底 + 按钮 `我确认执行`。顶部 `▲ 不可撤销` Plex Mono 12px 眉标（`$wolf-outcome-risk` 文字色，三态统一）。阶段迁移 `报价谈判 → 赢单` 用箭头可视化（Plex Mono）。取消按钮始终中性 `$wolf-btn-text-color`，与确认按钮左右分离 ≥8px。确认按钮 min-height 44px |
| **SlotFillForm**（5.7） | 复用 `DynamicParamForm`；金额/日期字段 Plex Mono + `$wolf-numeric`；可见 label（非占位符）；blur 校验（`inline-validation`）；字段分组（`field-grouping`） |
| **ErrorCard**（5.4） | `role=alert` + `aria-live=polite`；`$wolf-outcome-risk` 文字 + `$wolf-outcome-risk-bg` 底；`recovery.suggestions` 渲染为 ≥44px 小按钮（`用更完整的名称重试` / `用 #ID 引用`），按钮点击回填 ChatInput |
| **PreviewCard**（5.9） | 风险标签改后端 `preview.risk_level` 驱动；字段值 Plex Mono + `$wolf-numeric`；confirm 端点换 Glue |

### 文案 / 语态

- 主动语态、以用户控制物命名：`为 光大证券 创建跟进` 而非 `跟进记录将被创建`。
- 确认按钮显式带动作：`我确认赢单` / `我确认输单` / `确认跟进`，非泛 `确认`。动作名贯穿全流程（按钮 `我确认赢单` → 盖印 `赢单 · WON`）。
- 取消用 `取消`（清晰优于温情）。
- 错误不道歉、不模糊：`未找到「张三」的客户。可尝试用更完整的名称，或用 #ID 引用`——带恢复路径。
- 空态是行动邀请：无历史对话时 WelcomeScreen 的 4 条快捷操作即邀请，不写 `暂无数据`。

### 动效与克制

- phase rail active 节点 **不加 pulse 动画**（自审砍掉）：`◐` 半填充 + `$wolf-phase-active` 琥珀色已足够，pulse 是多余装饰，且 reduced-motion 下本就要禁。
- 盖印淡出 `opacity 0→1 / 1→0` 各 0.2s，仅 transform/opacity（`transform-performance`）。
- 全部动效 `@media (prefers-reduced-motion: reduce)` 下时长降为 0.01ms（复用既有 `$wolf-reduced-motion-duration`）。

### 可达性质量底线（默默达标）

- 触控目标 ≥44×44px（EntityPicker 候选行、DangerConfirmCard 按钮、ErrorCard 恢复按钮）。
- focus 环可见（复用既有 `$wolf-focus-ring-width: 2px` + `$wolf-focus-ring-color`）。
- 对比度 ≥4.5:1：`$wolf-outcome-lose #636363` 在 `#F5F5F5` 底上约 4.6:1，达标；`$wolf-phase-pending #7A7A7A` 在 `#F0F4F8` 底上达标。
- `aria-live="polite"` 用于 ErrorCard 动态播报；盖印用 `role="status"`。
- 375px 视口：phase rail 在窄屏保持单行横向（标签可缩短为 `意图/实体/预览/执行`），盖印宽度自适应不溢出。

## 5.3 Task 实现清单

> 各 Task 均为 TDD：写失败测试 → 跑确认失败 → 实现 → 跑确认通过 → commit。下方仅列关键代码/命令；标准 TDD 步骤参见各 Task。

### 文件改动总表

| Task | 操作 | 文件 |
|------|------|------|
| 5.1 | 新建类型 | `CRM-Client/src/types/aiAssistant.ts`（Glue 事件契约 TS 类型，含 `outcome_type`） |
| 5.2 | 改 | `CRM-Client/src/api/aiAssistant.ts`（事件枚举换 Glue；删 deprecated 方法） |
| 5.3 | 新建 | `CRM-Client/src/composables/useGluePhases.ts`（SSE→Glue phase 列表，替代 ReAct step） |
| 5.4 | 新建 | `CRM-Client/src/components/ai-assistant/PhaseSummary.vue`、`ErrorCard.vue` |
| 5.5 | 复活抽简 | `CRM-Client/src/components/ai-assistant/EntityPicker.vue`（合并 InlineCandidate+EntitySelectDialog） |
| 5.6 | 复活抽简 | `CRM-Client/src/components/ai-assistant/DangerConfirmCard.vue`（从 ConfirmationCard 抽，按 outcome 分态） |
| 5.7 | 复用改造 | `DynamicParamForm.vue` → `SlotFillForm.vue` 包装 |
| 5.8 | 新建 | `CRM-Client/src/styles/variables.scss`（追加 phase/outcome/numeric token，见 5.2） |
| 5.9 | 改 | `PreviewCard.vue`（风险改后端驱动；confirm 端点换 Glue） |
| 5.10 | 改 | `AIAssistant.vue`（事件分发重写、挂载新组件、删 ReAct step 透传） |
| 5.11 | 改 | `CompactExecutionLog.vue`/`ExpandedView.vue`（删 WAITING 分支、phase 驱动） |
| 5.12 | 删 | 孤儿与死码清单（含 UndoToast） |
| 5.13 | 改 | `config/previewFieldConfig.ts`（仅留字段格式化，风险下放后端） |
| 5.14 | 测试 | `CRM-Client/tests/`（组件单测 + SSE 事件映射单测） |

### Task 5.1：Glue SSE 事件契约 TS 类型

**Files:** Create `CRM-Client/src/types/aiAssistant.ts`
**Consumes:** 后端 `GlueSSEStreamer`（Phase 3.1）事件契约
**Produces:** `GlueSSEEvent` discriminated union + 子类型，含 `outcome_type`

- [ ] **Step 1: 定义事件联合类型**

```typescript
// CRM-Client/src/types/aiAssistant.ts
export type GlueSSEEvent =
  | { event: 'start'; data: { session_id: string } }
  | { event: 'intent'; data: PhaseData.Intent }
  | { event: 'entity'; data: PhaseData.Entity }
  | { event: 'preview'; data: PhaseData.Preview }
  | { event: 'execute'; data: PhaseData.Execute }
  | { event: 'result'; data: { event: 'result'; success: boolean; message: string; content: string; answer: string; rounds: number; is_partial: boolean } }
  | { event: 'complete'; data: { answer: string; rounds: number; is_partial: boolean } }
  | { event: 'error'; data: { message: string; recovery?: RecoveryHint } };

export namespace PhaseData {
  export interface Intent { intent_type: string; confidence: number; slots: Record<string, unknown>; auto_executed?: boolean }
  export interface Entity {
    entity_type: string;
    status: 'resolved' | 'ambiguous' | 'not_found';
    resolved_id?: number;
    candidates?: EntityCandidate[];
    recovery?: RecoveryHint;
  }
  export interface Preview {
    intent_type: string;
    risk_level: RiskLevel;
    requires_confirmation: boolean;
    outcome_type: 'win' | 'lose' | 'generic'; // 见 5.2：win=success-green / lose=neutral-grey / generic=danger-red
    preview_snapshot?: PreviewSnapshot;
  }
  export interface Execute { success: boolean; message: string; action_id?: string }
}

export interface EntityCandidate { id: number; name: string; hint: string; matched_by: string }
export interface PreviewSnapshot { changes: Array<{ field: string; old: unknown; new: unknown }>; message: string }
export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH';
export interface RecoveryHint { suggestions: string[]; retryable: boolean }
```

- [ ] **Step 2: Commit**

```bash
git add CRM-Client/src/types/aiAssistant.ts
git commit -m "feat(ai-fe): add Glue SSE event contract types"
```

### Task 5.2：aiAssistantApi 换 Glue 事件契约、删 deprecated

**Files:** Modify `CRM-Client/src/api/aiAssistant.ts:65-84`（`SSEEventType`）、`:282-439`（删 deprecated/orphan）
**Consumes:** `GlueSSEEvent`（5.1） | **Produces:** `chatSSE()` 返回 `GlueSSEEvent`

- [ ] **Step 1: 写失败测试** `CRM-Client/tests/api/chatSSE.spec.ts`：喂 `event: preview` + HIGH + `outcome_type:"win"` 的 SSE chunk，断言产出对应 `GlueSSEEvent`。
- [ ] **Step 2: 跑确认失败** `npx vitest run tests/api/chatSSE.spec.ts` → FAIL
- [ ] **Step 3: 改 `SSEEventType` 枚举**：删全部 ReAct/workflow 专有名，改为 `start/intent/entity/preview/execute/result/complete/error`；`chatSSE()` yield `GlueSSEEvent`。
- [ ] **Step 4: 删** `continueReactSSE`、`continueReactWithUserResponse`、`getReactSessionStatus`（`api/workflow.ts` 5.12 统一删）。
- [ ] **Step 5: 跑确认通过 + Commit** `refactor(ai-fe): switch chatSSE to Glue event contract, drop deprecated`

### Task 5.3：useGluePhases composable（替代 ReAct step）

**Files:** Create `CRM-Client/src/composables/useGluePhases.ts`
**Consumes:** `GlueSSEEvent`（5.1） | **Produces:** `Phase[]` + localStorage 缓存/auto-collapse（复用旧模式）

- [ ] **Step 1: 写测试** `tests/composables/useGluePhases.spec.ts`：投 `start→intent→entity(ambiguous)→preview(HIGH,outcome=win)→execute`，断言 5 phase 且 entity 项 `awaitingUser=true`、preview 项 `interaction='danger_confirm'` 且带 `outcome_type='win'`。
- [ ] **Step 2: 跑确认失败** → FAIL
- [ ] **Step 3: 实现**

```typescript
// CRM-Client/src/composables/useGluePhases.ts
import { shallowRef, type Ref } from 'vue';
import type { GlueSSEEvent } from '@/types/aiAssistant';

export interface Phase {
  id: string;
  type: 'intent' | 'entity' | 'preview' | 'execute' | 'result' | 'error';
  summary: string;
  detail?: unknown;
  awaitingUser: boolean;
  interaction?: 'entity_pick' | 'slot_fill' | 'danger_confirm';
  outcomeType?: 'win' | 'lose' | 'generic';
  data?: unknown;
  status: 'running' | 'done' | 'failed';
}

export function useGluePhases(conversationId: Ref<string>) {
  const phases = shallowRef<Phase[]>([]);
  const handleSSEEvent = (ev: GlueSSEEvent) => {
    switch (ev.event) {
      case 'intent': phases.value = [...phases.value, mkIntentPhase(ev.data)]; break;
      case 'entity': phases.value = appendEntityPhase(phases.value, ev.data); break;
      case 'preview': phases.value = appendPreviewPhase(phases.value, ev.data); break;
      case 'execute': phases.value = appendExecutePhase(phases.value, ev.data); break;
      case 'result': /* 收尾 */ break;
      case 'error': phases.value = [...phases.value, mkErrorPhase(ev.data)]; break;
    }
    persistToLocalStorage(conversationId.value, phases.value);
  };
  return { phases, handleSSEEvent, clear: () => (phases.value = []) };
}
```
（`appendEntityPhase`：ambiguous→`awaitingUser=true, interaction='entity_pick'`；`appendPreviewPhase`：HIGH→`interaction='danger_confirm'`，透传 `outcome_type`。）

- [ ] **Step 4: 跑确认通过 + Commit**

### Task 5.4：PhaseSummary + ErrorCard（不可交互语义卡片）

**Files:** Create `CRM-Client/src/components/ai-assistant/PhaseSummary.vue`、`ErrorCard.vue`
**视觉契约**：见 5.2「五个 UX 组件的视觉契约」。

- [ ] **Step 1: PhaseSummary**——渲染 phase rail 节点（`●/◐/○` + 对应 token），点击展开 detail，3s auto-collapse 复用既有计时。props `{ phase: Phase }`。
- [ ] **Step 2: ErrorCard**——props `{ message; recovery?: RecoveryHint }`，渲染 `recovery.suggestions` 为 ≥44px 小按钮，点击 emit `retry-with`。`role=alert`+`aria-live=polite`，`$wolf-outcome-risk` 文字 + `$wolf-outcome-risk-bg` 底。
- [ ] **Step 3: 单测 + Commit**

### Task 5.5：EntityPicker（复活孤儿歧义选择）

**Files:** Create `CRM-Client/src/components/ai-assistant/EntityPicker.vue`
**Consumes:** `EntityCandidate[]` | **Produces:** `emit('pick', id)`/`emit('cancel')`
**视觉契约**：候选行 `① 名称 · hint`，整行 ≥44px，选中 `$wolf-primary` 边框，`role=listbox`/`role=option`/`aria-selected`。

- [ ] **Step 1: 从孤儿 InlineCandidate + EntitySelectDialog 抽取候选渲染**
- [ ] **Step 2: 触控与可达性**——整行可点（hitSlop），键盘 Tab 可达
- [ ] **Step 3: 单测（选候选回传 id）+ Commit**

### Task 5.6：DangerConfirmCard（复活危险富确认，按 outcome 分态）

**Files:** Create `CRM-Client/src/components/ai-assistant/DangerConfirmCard.vue`
**Consumes:** `PreviewSnapshot` + `RiskLevel` + `outcome_type` | **Produces:** `emit('confirm')`/`emit('cancel')`/`emit('edit')`
**视觉契约**：见 5.2——三态分染色：win=`$wolf-outcome-win`+按钮`我确认赢单`；lose=`$wolf-outcome-lose`+`我确认输单`；generic=`$wolf-outcome-risk`+`我确认执行`。顶部 `▲ 不可撤销` Plex Mono 12px 眉标（三态统一 `$wolf-outcome-risk` 文字色）。阶段迁移箭头可视化。取消按钮中性、与确认左右分离 ≥8px、确认 min-height 44px。

- [ ] **Step 1: 从孤儿 ConfirmationCard 抽简**——按 `outcome_type` 三态分支选配色与按钮文案，非全部 danger-red
- [ ] **Step 2: 危险确认 destructive-emphasis**——确认按钮文案显式带动作名防误点；`▲ 不可撤销` 眉标落实 undo 决策（控制点前置，非事后 undo）
- [ ] **Step 3: 单测（三态渲染 + confirm/cancel emit）+ Commit**

### Task 5.7：SlotFillForm（复用 DynamicParamForm）

**Files:** Create `CRM-Client/src/components/ai-assistant/SlotFillForm.vue`（薄包装 `DynamicParamForm` + `ParamDefinition`）
**Produces:** `emit('fill', filledSlots)`
**视觉契约**：金额/日期字段 Plex Mono + `$wolf-numeric`；可见 label；blur 校验；字段分组。

- [ ] **Step 1: 包装**——props `{ missingFields: ParamDefinition[]; prefill? }`，映射 Glue 缺字段到 `DynamicParamForm`
- [ ] **Step 2: 单测 + Commit**

### Task 5.8：追加 phase/outcome/numeric token

**Files:** Modify `CRM-Client/src/styles/variables.scss`（在「审批状态语义色」段之后追加 5.2「Token 增量」整段 SCSS）

- [ ] **Step 1: 追加 5.2 给出的 SCSS 块**（phase 语义别名 + outcome 语义 + `$wolf-numeric`），零新增色相，全部指向既有 token
- [ ] **Step 2: 构建验证** `cd CRM-Client && npm run build` 无 SCSS 报错
- [ ] **Step 3: Commit** `style(ai-fe): add phase/outcome/numeric tokens (zero new hues)`

### Task 5.9：PreviewCard 改后端驱动风险 + Glue confirm 端点

**Files:** Modify `CRM-Client/src/components/ai-assistant/PreviewCard.vue`、`config/previewFieldConfig.ts`

- [ ] **Step 1: 风险来源改后端**——`risk_level` 从 `previewFieldConfig` 静态查改为接收 Preview 事件的 `risk_level`；`previewFieldConfig.ts` 删 `RISK_LEVEL_CONFIG`，只留 `getActionConfig`/`formatFieldValue`。
- [ ] **Step 2: confirm 端点换 Glue**——`handleConfirmPreview` 从 deprecated `continueReactSSE` 改为 Glue 确认端点（对齐 Phase 3.5 `/v1/agent/chat` 代理）。修复现状 bug：传当前用户消息而非 `messages[0]`。
- [ ] **Step 3: 单测 + Commit**

### Task 5.10：AIAssistant.vue 事件分发重写 + 挂载新组件

**Files:** Modify `CRM-Client/src/views/AIAssistant.vue:420-520`（`handleSSEEvent`）、`:67-78`（slot 区改语义阶段卡区）

- [ ] **Step 1: handleSSEEvent 按 Glue 事件重写**——`start`→清；`intent/entity/preview/execute`→`useGluePhases.handleSSEEvent`；设 `awaiting` 状态；`result/complete`→气泡收尾；`error`→`ErrorCard`。

```vue
<template #phases>
  <PhaseSummary v-for="p in phases" :key="p.id" :phase="p" @expand="..." />
  <EntityPicker v-if="awaiting==='entity_pick'" :candidates="..." @pick="onPick" @cancel="onCancel" />
  <DangerConfirmCard v-if="awaiting==='danger_confirm'" :snapshot="..." :outcome-type="..." @confirm="..." @cancel="..." />
  <SlotFillForm v-if="awaiting==='slot_fill'" :missing-fields="..." @fill="..." />
  <ErrorCard v-if="errorPhase" :message="..." :recovery="..." @retry-with="fillInput" />
</template>
```
- [ ] **Step 2: 删 ReAct step 透传**——删 `:430-434` 给 `agentLog.handleSSEEvent` 的透传（改用 useGluePhases）
- [ ] **Step 3: 兼容性验证**——mock Glue SSE 跑通 5 核心路径：(a) LOW 自动执行 (b) HIGH 二次确认（win 分态）(c) 多候选选择 (d) 缺字段补全 (e) 0 结果 actionable 错误
- [ ] **Step 4: 端到端联调**——后端 Phase 3.1 就绪后切真实 SSE，验证 `start/result/complete/error` 前端兼容不破
- [ ] **Step 5: Commit**

### Task 5.11：CompactExecutionLog/ExpandedView 删 ReAct 轮次、改 phase 驱动

**Files:** Modify `CRM-Client/src/components/CompactExecutionLog.vue`、`ExpandedView.vue`

- [ ] **Step 1: 删 ExpandedView WAITING 分支**——InlineCandidate/CompactConfirmSummary/CompactInfoGap 三选一删除（`confirmationType` 半死逻辑），只保留通用 Phase/InlineStep 渲染
- [ ] **Step 2: 轮次徽章改 phase 序号**——`R1/N` 改 phase 序号（P1/P2…）或去掉
- [ ] **Step 3: 单测 + Commit**

### Task 5.12：删除孤儿与死码

**Files:** Delete 见 5.1「可弃用清单」（含 `UndoToast.vue`）

- [ ] **Step 1: 逐项 grep 复核零引用** `grep -rn "<MagicWandDialog\|<ReactProgress\|<ThinkingBubble\|<UndoToast\|<InlinePill\|<ConfirmationCard\|<EntitySelectDialog\|<WorkflowMiniMap\|<StatusCard" CRM-Client/src --include="*.vue"`，确认除自身与测试外无命中
- [ ] **Step 2: 删除**

```bash
cd CRM-Client
rm src/components/MagicWandDialog.vue \
   src/components/ReactProgress.vue src/components/AgentProgress.vue \
   src/components/ThinkingBubble.vue src/components/UndoToast.vue \
   src/components/InlinePill.vue src/components/ConfirmationCard.vue \
   src/components/EntitySelectDialog.vue src/components/WorkflowMiniMap.vue \
   src/components/StatusCard.vue src/components/InlineCandidate.vue \
   src/components/CompactConfirmSummary.vue src/components/CompactInfoGap.vue \
   src/composables/useSidebarState.ts src/types/sidebar.ts \
   src/api/workflow.ts
```
- [ ] **Step 3: 全量构建验证** `npm run build && npx vitest run` 无 import error
- [ ] **Step 4: Commit** `refactor(ai-fe): remove orphan MagicWand subtree, UndoToast, ReAct-only wrappers`

### Task 5.13：previewFieldConfig 精简

**Files:** Modify `CRM-Client/src/config/previewFieldConfig.ts`

- [ ] **Step 1: 删 `RISK_LEVEL_CONFIG`**（风险下放后端）
- [ ] **Step 2: 保留 `getActionConfig`/`formatFieldValue`**（字段格式化仍用）
- [ ] **Step 3: 单测 + Commit**

### Task 5.14：组件与 SSE 单测回归

**Files:** Test `CRM-Client/tests/`

- [ ] **Step 1: SSE 事件映射覆盖**——`chatSSE` × `useGluePhases` × 5 核心路径全链路单测（含 outcome 三态）
- [ ] **Step 2: 组件单测**——PhaseSummary/EntityPicker/DangerConfirmCard(三态)/SlotFillForm/ErrorCard 的 props→emit + 可触达性（44px、aria）断言
- [ ] **Step 3: 全量回归 + a11y 抽查** `npx vitest run && npm run build`；手动跑 375px 视口 + 键盘 Tab 全流程 + `prefers-reduced-motion`
- [ ] **Step 4: Commit**

---

## Self-Review（计划作者自查）

**1. Spec 覆盖**：用户要求「正式完整详细的整合方案」+「LangGraph 清理方案」+「前端用户交互 + UI 设计」+「两未决项定案」+「合并成一份」。Phase 1 覆盖 LangGraph 清理（1.1-1.3）+ 旁路死码（1.4-1.9）+ 文档（1.10）；Phase 2-4 后端整合；Phase 5 前端对齐（含 UI 视觉契约）；两未决项在头部「关键决策」定案。Option B「扶正 Glue 废弃 ReAct」由 Phase 2+3+5 承担。✓

**2. 占位符扫描**：Phase 3.1 Step 5、Task 3.3 Step 3 等含"按实际对齐"措辞——因目标文件需执行时读取确认字段名（计划已给主结构 + 指明读取位置），非空泛占位。其余步骤均含真实代码或确切命令。

**3. 类型一致性**：`ExecutionResult` 字段（success/message/action_id/data/error）在 Task 2.2/2.3 一致；`GlueSSEStreamer` 在 3.1 定义、3.5 复用一致；`session_id` uuid 寻址在 3.1/3.2/3.5 一致；`SafetyGateway.assess` 在 3.3 定义并自洽；`outcome_type` 在后端 3.1/3.3 产出、前端 5.1 类型声明、5.6 消费分态——端到端闭合。

**4. 矛盾消除**：合并时修正了前端原方案的过时片段——UndoToast 从"复活接线"改为"删除"（对齐 undo 决策）；win/lose 从"统一 danger-red"改为"outcome 分态"（对齐 UI 设计）；4 parser 未决改为"已决不收口"；B5 bug 补进 Phase 2（原头部说"4 个 bug"实为 5 个）。

**5. 风险标注**：Phase 3 为高风险，建议 subagent-driven；Task 3.6 删除前有 grep 复核。Phase 1/2 低风险。Phase 5 中 5.10 接线依赖后端 3.1/3.5，建议先 mock 联调。

---

## 执行建议

- **Phase 1**：低风险，可 inline 批量执行，每个 Task 末 commit。
- **Phase 2**：中等风险，TDD 小步，建议 inline executing-plans 带 checkpoint。
- **Phase 3**：高风险，**强烈建议 subagent-driven-development**——每个 Task 派独立 subagent + 两阶段 review，Task 3.1 与 3.6 完成后做全量回归门禁。
- **Phase 4**：低-中风险，可在 Phase 3 稳定后增量做。
- **Phase 5**：5.1-5.9 可在后端 Phase 2 后 mock 联调并行推进；5.10-5.11 接线等后端 3.1/3.5；5.12 删孤儿纯独立可早做。建议分三批 subagent-driven + 每批 review。

## 已定事项（原未决，现已在头部「关键决策」定案，执行时不再讨论）

1. **AI 路径 undo**：不建。WON/LOST 业务终态不可逆；控制点前置到 Preview/Gate + DangerConfirmCard「不可撤销」声明。前端删 UndoToast，不接线也不占位。
2. **4 个表单型 AI parser 收口**：不收口。审批/采购是配置生成工具（异域），客户/线索是单轮弹窗（异心智）。本次整合不动；真正能省维护成本的是 parser 间内部去重（`_clean_json_response`/SSE httpx 循环/prompt 枚举段/前端 5 套 TS 类型抽基类），非本计划范围，可另立小需求。

## 待执行时确认（不阻塞计划启动）

1. Task 3.5 路由策略：保留 `/v1/agent/chat` 代理 vs 前端改调 glue 入口——本计划默认前者（最小前端改动），若前端愿改可简化 3.5。
2. Task 3.6 skills/handlers 去留：HandlerFactory 经 calendar 路径仍 live，哪些 handler 仅 ReAct 用需执行时逐个 grep 判定。
3. IM 异步队列：Task 2.5 改 503 是诚实失败；若产品需要 IM，需另立计划实现队列推送（不在本计划范围）。
