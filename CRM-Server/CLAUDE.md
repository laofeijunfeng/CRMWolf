# CRM-Server 后端模块

**Claude Code 进入此目录时自动加载**

---

## 模块结构地图

```
CRM-Server/
├── app/
│   ├── api/           # API 端点层
│   ├── crud/          # CRUD 操作层（统一入口）
│   ├── models/        # SQLAlchemy 模型
│   ├── schemas/       # Pydantic schema
│   ├── services/      # 业务逻辑层
│   │   ├── agent/     # ReAct AI 助手（手写循环，当前生产路径）
│   │   ├── skills/    # Skills Handlers
│   │   ├── workflow/  # Workflow 定义（保留）
│   │   └── ai/        # AI 相关服务（ActionEntry / EntitySearch 等）
│   ├── glue/          # AI Glue 层（DialogueEngine / EntityResolver）
│   ├── constants/     # 业务常量定义（防幻觉关键）
│   ├── utils/         # 通用工具（SSEJsonEncoder 等）
│   └── core/          # 配置、依赖注入
├── migrations/        # Alembic 迁移文件
├── tests/             # 测试文件
└── run.sh             # 启动脚本
```

> ⚠ `app/services/langgraph/` 已于 2026-07-02 整合清理中删除（StateGraph 从未编译落地，
> checkpointer/state/nodes/sse_wrapper 零 live 引用；SSEJsonEncoder 迁至 `app/utils/sse_encoder.py`）。
> `langgraph` PyPI 依赖已移除。详见 `docs/superpowers/plans/2026-07-02-ai-assistant-consolidation-plan.md`。

---

## AI 助手架构（现状 2026-07-02）

当前有**两条** AI 助手路径（整合中，目标收敛为 Glue 单路径，见整合计划）：

| 路径 | 端点 | 状态 |
|------|------|------|
| ReAct agent | `POST /v1/agent/chat`（`app/api/agent_assistant.py`） | **当前唯一能端到端跑通**；手写 ReAct 循环（`app/services/agent/core.py`） |
| Glue DialogueEngine | `POST /api/glue/v1/inbound`（`app/glue/`） | 端点可达，核心路径修复中（整合计划 Phase 2-3） |
| /ai/actions + ActionEntry | `POST /api/ai/actions/*` | 写动作唯一前门契约，设计健全 |

**注意**：`CRM-Docs/system/AI-AGENT-ARCHITECTURE.md` 描述的 LangGraph StateGraph 三层架构是**规划态，磁盘未落地**。当前生产路径以 ReAct 为准，整合方向见 `docs/superpowers/plans/2026-07-02-ai-assistant-consolidation-plan.md`。

### 已删除的旧文件

| 文件 | 大小 | 历史替代 | 现状 |
|------|------|----------|------|
| `ai_tool_service.py` | 108KB | 曾计划由 `langgraph/graph.py` + `nodes/` 替代 | langgraph 已清理，未落地 |
| `workflow_orchestrator.py` | 55KB | 曾计划由 `nodes/workflow.py` 替代 | 未落地 |
| `session_store.py` | 11KB | 曾计划由 `langgraph/checkpointer.py` 替代 | checkpointer 已删，会话由 Glue SessionManager / ReAct AgentMemory（Redis）承担 |
| `app/services/langgraph/*` | — | — | 2026-07-02 清理删除（零 live 引用） |

---

## 开发命令

```bash
./run.sh             # 启动服务
ruff check app/      # Python lint
mypy app/            # 类型检查
pytest tests/unit -v # 单元测试
pytest tests/unit/utils -v  # 工具单测（含 SSEJsonEncoder）
alembic revision -m "描述"  # 创建迁移
alembic upgrade head         # 执行迁移
```

---

## 防幻觉指令（禁止推断）

Claude **绝对禁止推断**以下业务常量，必须查阅代码定义：

| 禁止推断 | 定义位置 |
|----------|----------|
| 客户阶段映射 | `app/constants/customer_stages.py` |
| 商机状态枚举 | `app/constants/opportunity_status.py` |
| 发票类型 | `app/constants/invoice_types.py` |
| 权限码 | `CRM-Docs/system/GLOSSARY.md` |
| API 响应格式 | `CRM-Docs/best-practices/backend/api-design.md` |
| team_id 获取方式 | `app/core/deps.py` → `get_current_user_team` |

---

## 核心规则

- **Pydantic 强制校验**：所有外部输入必须校验，禁止裸 dict
- **CRUD 统一入口**：禁止直接 `db.query()`
- **team_id 必传**：所有 CRUD 操作必须传入 team_id
- **Alembic 迁移**：禁止独立数据库脚本
- **Preview 模式**：CRITICAL 操作必须先 Preview
- **AI 助手入口**：当前 ReAct `/v1/agent/chat`；写动作唯一前门为 `/api/ai/actions/*` + `ActionEntry`（整合中，详见 `docs/superpowers/plans/2026-07-02-ai-assistant-consolidation-plan.md`）

**详细规则**：`.claude/rules/backend.md`, `.claude/rules/workflow-engine.md`, `.claude/rules/dangerous-actions.md`

---

## API 入口（AI 助手相关）

| 端点 | 用途 | 实现 |
|------|------|------|
| `POST /v1/agent/chat` | ReAct 主对话入口（当前生产路径） | `app/services/agent/core.py` ReAct 循环 + SSE |
| `GET/DELETE /v1/agent/session/{id}` | ReAct 会话查询/取消 | Redis（`AgentMemory`） |
| `POST /api/glue/v1/inbound` | Glue 对话入口（整合中） | `app/glue/` DialogueEngine |
| `POST /api/ai/actions/*` | 写动作唯一前门 | `ActionEntry`（Preview + Gate + Audit） |

---

**详细规范（按需查阅）**：`CRM-Docs/best-practices/backend/crud-patterns.md`, `CRM-Docs/best-practices/backend/team-isolation.md`

---

**版本：ReAct + Glue 双路径（整合中） | 最后更新：2026-07-02**