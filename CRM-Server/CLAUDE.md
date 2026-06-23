# CRM-Server 后端模块

**Claude Code 进入此目录时自动加载**

---

## 模块结构地图

```
CRM-Server/
├── app/
│   ├── api/           # API 端点层
│   │   └── web_assistant.py  # AI 助手入口（LangGraph 架构）
│   ├── crud/          # CRUD 操作层（统一入口）
│   ├── models/        # SQLAlchemy 模型
│   ├── schemas/       # Pydantic schema
│   ├── services/      # 业务逻辑层
│   │   ├── langgraph/ # LangGraph AI 助手服务（新架构）
│   │   ├── skills/    # Skills Handlers
│   │   ├── workflow/  # Workflow 定义（保留）
│   │   └── ai/        # AI 相关服务
│   ├── glue/          # AI Glue 层（EntityResolver、ActionEntry）
│   ├── constants/     # 业务常量定义（防幻觉关键）
│   └── core/          # 配置、依赖注入
├── migrations/        # Alembic 迁移文件
├── tests/             # 测试文件
│   └── unit/services/langgraph/  # LangGraph 单元测试
└── run.sh             # 启动脚本
```

---

## LangGraph AI 助手架构（v1.0）

### 核心组件

| 组件 | 路径 | 职责 |
|------|------|------|
| **API 入口** | `app/api/web_assistant.py` | SSE 流式响应，单一入口 |
| **StateGraph** | `app/services/langgraph/graph.py` | LangGraph 编排引擎 |
| **AgentState** | `app/services/langgraph/state.py` | TypedDict 状态定义 |
| **Nodes** | `app/services/langgraph/nodes/` | Router、Intent、Entity、Preview、Execute 等 |
| **Tools** | `app/services/langgraph/tools/` | EntitySearch、ActionEntry、Handler 封装 |
| **Checkpointer** | `app/services/langgraph/checkpointer.py` | Redis 持久化（TTL 30min） |
| **SSE Wrapper** | `app/services/langgraph/sse_wrapper.py` | LangGraph → CRMWolf SSE 格式转换 |

### Graph 流程

```
router → workflow | intent_detector
intent_detector → entity_resolver | slot_collector | preview
entity_resolver → ambiguity_resolver | preview | ask_user
preview → confirm | execute | ask_user
execute → workflow | intent_detector (ReAct 循环) | end
workflow → workflow (下一步) | ask_user | rollback | complete
ask_user → intent_detector (恢复)
```

### 已删除的旧文件

| 文件 | 大小 | 替代方案 |
|------|------|----------|
| `ai_tool_service.py` | 108KB | `langgraph/graph.py` + `nodes/` |
| `workflow_orchestrator.py` | 55KB | `nodes/workflow.py` |
| `session_store.py` | 11KB | `langgraph/checkpointer.py` |

---

## 开发命令

```bash
./run.sh             # 启动服务
ruff check app/      # Python lint
mypy app/            # 类型检查
pytest tests/unit -v # 单元测试
pytest tests/unit/services/langgraph -v  # LangGraph 测试
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
- **LangGraph 单一入口**：AI 助手请求统一通过 `/v1/assistant/chat`

**详细规则**：`.claude/rules/backend.md`, `.claude/rules/workflow-engine.md`, `.claude/rules/dangerous-actions.md`

---

## API 入口（统一）

| 端点 | 用途 | 实现 |
|------|------|------|
| `POST /v1/assistant/chat` | 主对话入口 | LangGraph stream |
| `POST /v1/assistant/workflow/continue` | Human-in-the-Loop 恢复 | LangGraph resume |
| `GET /v1/assistant/session/{id}` | 查询 Session 状态 | LangGraph get_state |
| `DELETE /v1/assistant/session/{id}` | 取消 Session | LangGraph delete |

---

**详细规范（按需查阅）**：`CRM-Docs/best-practices/backend/crud-patterns.md`, `CRM-Docs/best-practices/backend/team-isolation.md`

---

**版本：LangGraph v1.0 | 最后更新：2026-06-18**