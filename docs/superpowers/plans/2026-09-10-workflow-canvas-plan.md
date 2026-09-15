# 工作流画布创建能力 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `/settings/approval-flows-new` 页面内交付通用工作流创建能力：Vue Flow 画布 + 五类节点配置 + CRMWolf Workflow DSL 持久化（draft/published/paused）。

**Architecture:** 后端新增 `crm_workflows` 表（migration 131）与 `/v1/workflows` REST API（Pydantic 边界、team 隔离、乐观锁、状态流转）；前端新增 `@vue-flow/*` 依赖、节点注册表、图校验模块、画布编辑器组件群，并挂载进现有新页面。DSL 是 CRMWolf 自有模型（`schema_version` 预留 AP-03），不接 Activepieces、无执行引擎。

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + Pydantic（后端）；Vue 3 + @vue-flow/core + shadcn-vue + Vitest（前端）。

**Spec:** `docs/superpowers/specs/2026-09-10-workflow-canvas-design.md`（已获用户批准）

## Global Constraints

- 数据库结构变更必须通过 Alembic migration 交付（migration 131）。
- 后端 API 入参/出参必须 Pydantic schema，不使用裸 dict 作为业务边界。
- 多租户数据必须携带 `team_id`，查询必须过滤 `team_id`；跨团队访问返回 404。
- 前端禁止 `any` / `as any` / `@ts-ignore` / 非必要非空断言；遵循 V2 设计规范与 shadcn-vue 语义类。
- 不实现执行引擎、Activepieces 同步、事件投递、模板中心、undo/redo、表达式引擎。
- vue-flow 只允许引入 `@vue-flow/core`、`@vue-flow/background`、`@vue-flow/controls` 三个包。
- DSL `schema_version` 固定为 1；节点 type 必须在前后端共享注册表内。
- 旧 `/settings/approval-flows` 页面行为保持不变。
- 权限 code 采用 `automation:read/create/edit/publish`，TEAM_ADMIN 通过 "all" 自动获得全部新权限（`ROLE_PERMISSIONS_MAPPING` 机制，无需改动映射）。
- 每个任务收尾运行该任务的覆盖测试；全量 lint 非任务范围（仓库既有 lint 问题不阻塞）。

## 共享契约（所有任务的唯一事实来源）

### 节点类型注册表（前端 TS / 后端 Python 各持一份，key 一致）

| type key | 分类 | 中文标签 | config 必填字段 |
|---|---|---|---|
| `trigger.opportunity_stage_changed` | trigger | 商机阶段变化 | `to_stage`（非空字符串） |
| `approval.step` | action | 审批节点 | `node_name`（非空）、`approve_role`（非空） |
| `control.condition` | control | 条件分支 | `field`、`operator`(eq/neq/gt/lt/in)、`value` |
| `action.create_follow_up_task` | action | 创建跟进任务 | `title`（非空） |
| `action.notify` | action | 发送通知 | `notify_target`(owner/role/users) |

### Workflow DSL JSON

```jsonc
{
  "schema_version": 1,
  "nodes": [ { "id": "n1", "type": "trigger.opportunity_stage_changed",
               "position": { "x": 100, "y": 200 },
               "config": { "from_stage": null, "to_stage": "QUOTE" } } ],
  "edges": [ { "id": "e1", "source": "n1", "target": "n2" } ]
}
```

### 后端校验规则（`app/services/workflow_dsl.py`，两端一致实现）

1. `schema_version == 1`；
2. nodes 非空列表；`id` 图内唯一非空字符串；`type` 在注册表内；
3. trigger 类型节点至多 1 个；
4. edges：source/target 必须存在；不允许自环；target 不得为 trigger 类型；
5. config 必填字段满足（按上表）；位置为数字对。

### API 形状

```text
GET    /v1/workflows                     → WorkflowSummary[]（无 dsl 字段）
POST   /v1/workflows                     → WorkflowDetail（201）
GET    /v1/workflows/{id}                → WorkflowDetail
PUT    /v1/workflows/{id}                → WorkflowDetail（乐观锁）
DELETE /v1/workflows/{id}                → 204（仅 draft）
PUT    /v1/workflows/{id}/status         → WorkflowDetail（合法迁移：draft→published、published→paused、paused→published）
```

错误：422 DSL/迁移非法（字段级 detail）；409 乐观锁或非 draft 删除；404 不存在/跨团队；403 无权限。

---

### Task 1: 后端模型、迁移与 DSL 校验服务

**Files:**
- Create: `CRM-Server/app/models/workflow.py`
- Create: `CRM-Server/migrations/versions/131_crm_workflows.py`
- Create: `CRM-Server/app/services/workflow_dsl.py`
- Modify: `CRM-Server/app/models/__init__.py`（导出 Workflow）
- Test: `CRM-Server/tests/unit/test_workflow_dsl.py`

**Interfaces:**
- Produces: `Workflow` model（表 `crm_workflows`）；`validate_workflow_dsl(dsl: dict) -> list[str]`（空列表=合法，否则错误消息列表，供 API 转 422）；`KNOWN_NODE_TYPES` frozenset；`NODE_CONFIG_REQUIREMENTS` dict。

- [ ] **Step 1: 写失败测试** `tests/unit/test_workflow_dsl.py`：

```python
import pytest
from app.services.workflow_dsl import validate_workflow_dsl, KNOWN_NODE_TYPES

VALID = {
    "schema_version": 1,
    "nodes": [
        {"id": "n1", "type": "trigger.opportunity_stage_changed",
         "position": {"x": 0, "y": 0}, "config": {"to_stage": "QUOTE"}},
        {"id": "n2", "type": "action.create_follow_up_task",
         "position": {"x": 200, "y": 0}, "config": {"title": "跟进"}},
    ],
    "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
}

def test_valid_dsl_passes():
    assert validate_workflow_dsl(VALID) == []

def test_unknown_node_type():
    dsl = {**VALID, "nodes": [{**VALID["nodes"][0], "type": "action.unknown"}]}
    errs = validate_workflow_dsl(dsl)
    assert any("未知" in e for e in errs)

def test_duplicate_node_id():
    dsl = {**VALID, "nodes": [VALID["nodes"][0], dict(VALID["nodes"][0])]}
    assert any("唯一" in e or "重复" in e for e in validate_workflow_dsl(dsl))

def test_two_triggers_rejected():
    d2 = {**VALID["nodes"][1], "id": "n0", "type": "trigger.opportunity_stage_changed",
          "config": {"to_stage": "PROPOSAL"}}
    dsl = {**VALID, "nodes": [d2] + VALID["nodes"]}
    assert any("至多 1 个" in e or "trigger" in e for e in validate_workflow_dsl(dsl))

def test_dangling_edge_rejected():
    dsl = {**VALID, "edges": [{"id": "e2", "source": "n1", "target": "nx"}]}
    assert any("不存在" in e for e in validate_workflow_dsl(dsl))

def test_self_loop_rejected():
    dsl = {**VALID, "edges": [{"id": "e2", "source": "n1", "target": "n1"}]}
    assert any("自环" in e for e in validate_workflow_dsl(dsl))

def test_edge_into_trigger_rejected():
    dsl = {**VALID, "edges": [{"id": "e2", "source": "n2", "target": "n1"}]}
    assert any("trigger" in e for e in validate_workflow_dsl(dsl))

def test_missing_required_config():
    dsl = {**VALID, "nodes": [
        VALID["nodes"][0],
        {"id": "n2", "type": "action.create_follow_up_task",
         "position": {"x": 0, "y": 0}, "config": {}},
    ]}
    assert any("title" in e for e in validate_workflow_dsl(dsl))

def test_wrong_schema_version():
    assert validate_workflow_dsl({**VALID, "schema_version": 2}) != []
```

- [ ] **Step 2: 运行确认失败**

```bash
cd CRM-Server && source venv/bin/activate
pytest tests/unit/test_workflow_dsl.py -v
```
Expected: collection error（模块不存在）。

- [ ] **Step 3: 实现 `app/services/workflow_dsl.py`**

```python
"""CRMWolf Workflow DSL 结构校验（schema_version 1）。"""

NODE_CONFIG_REQUIREMENTS: dict[str, list[str]] = {
    "trigger.opportunity_stage_changed": ["to_stage"],
    "approval.step": ["node_name", "approve_role"],
    "control.condition": ["field", "operator", "value"],
    "action.create_follow_up_task": ["title"],
    "action.notify": ["notify_target"],
}
KNOWN_NODE_TYPES = frozenset(NODE_CONFIG_REQUIREMENTS)
TRIGGER_TYPES = frozenset(t for t in KNOWN_NODE_TYPES if t.startswith("trigger."))
VALID_OPERATORS = frozenset({"eq", "neq", "gt", "lt", "in"})
VALID_NOTIFY_TARGETS = frozenset({"owner", "role", "users"})


def validate_workflow_dsl(dsl: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(dsl, dict):
        return ["DSL 必须是对象"]
    if dsl.get("schema_version") != 1:
        errors.append("schema_version 必须为 1")

    nodes = dsl.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return errors + ["nodes 必须是非空列表"]

    seen_ids: set[str] = set()
    trigger_count = 0
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"nodes[{i}] 必须是对象")
            continue
        nid = node.get("id")
        if not isinstance(nid, str) or not nid:
            errors.append(f"nodes[{i}].id 必须是非空字符串")
        elif nid in seen_ids:
            errors.append(f"节点 id 重复: {nid}")
        else:
            seen_ids.add(nid)

        ntype = node.get("type")
        if ntype not in KNOWN_NODE_TYPES:
            errors.append(f"节点 {nid} 类型未知: {ntype}")
        if ntype in TRIGGER_TYPES:
            trigger_count += 1

        pos = node.get("position")
        if not isinstance(pos, dict) or not isinstance(pos.get("x"), (int, float)) \
                or not isinstance(pos.get("y"), (int, float)):
            errors.append(f"节点 {nid} 缺少有效 position")

        config = node.get("config", {})
        if not isinstance(config, dict):
            config = {}
            errors.append(f"节点 {nid} config 必须是对象")
        for field in NODE_CONFIG_REQUIREMENTS.get(ntype, []):
            v = config.get(field)
            if v is None or (isinstance(v, str) and not v.strip()):
                errors.append(f"节点 {nid} 缺少必填配置: {field}")
        if ntype == "control.condition" and config.get("operator") not in VALID_OPERATORS:
            errors.append(f"节点 {nid} operator 非法，允许: eq/neq/gt/lt/in")
        if ntype == "action.notify" and config.get("notify_target") not in VALID_NOTIFY_TARGETS:
            errors.append(f"节点 {nid} notify_target 非法，允许: owner/role/users")

    if trigger_count > 1:
        errors.append("trigger 类型节点全图至多 1 个")

    edges = dsl.get("edges", [])
    if not isinstance(edges, list):
        edges = []
        errors.append("edges 必须是列表")
    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"edges[{i}] 必须是对象")
            continue
        src, tgt = edge.get("source"), edge.get("target")
        src_type = next((n.get("type") for n in nodes if isinstance(n, dict) and n.get("id") == src), None)
        tgt_type = next((n.get("type") for n in nodes if isinstance(n, dict) and n.get("id") == tgt), None)
        if src not in seen_ids or tgt not in seen_ids:
            errors.append(f"edges[{i}] 引用了不存在的节点: {src} -> {tgt}")
            continue
        if src == tgt:
            errors.append(f"edges[{i}] 不允许自环")
        if tgt_type in TRIGGER_TYPES:
            errors.append(f"edges[{i}] 目标不能是 trigger 节点: {tgt}")

    return errors
```

- [ ] **Step 4: 运行测试通过**（同 Step 2 命令，Expected: 9 passed）

- [ ] **Step 5: 实现 `app/models/workflow.py`**

```python
from sqlalchemy import Column, BigInteger, String, Text, DateTime, Index
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import relationship  # noqa: F401
from app.core.database import Base
from app.utils.time import business_now


class WorkflowStatus:
    DRAFT = "draft"
    PUBLISHED = "published"
    PAUSED = "paused"


VALID_TRANSITIONS = {
    WorkflowStatus.DRAFT: {WorkflowStatus.PUBLISHED},
    WorkflowStatus.PUBLISHED: {WorkflowStatus.PAUSED},
    WorkflowStatus.PAUSED: {WorkflowStatus.PUBLISHED},
}


class Workflow(Base):
    """CRMWolf 工作流（自有 DSL，schema_version 预留 Activepieces Adapter）"""
    __tablename__ = "crm_workflows"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=True, index=True, comment="团队ID（NULL表示系统级）")
    name = Column(String(100), nullable=False, comment="工作流名称")
    description = Column(Text, nullable=True, comment="描述")
    status = Column(String(20), nullable=False, default=WorkflowStatus.DRAFT, comment="draft/published/paused")
    dsl = Column(JSON().with_variant(Text(), "sqlite"), nullable=False, comment="Workflow DSL JSON")
    created_by = Column(BigInteger, nullable=True, comment="创建人用户ID")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    last_modified_time = Column(DateTime, nullable=False, default=business_now,
                                onupdate=business_now, comment="最后修改时间（兼乐观锁版本）")

    __table_args__ = (
        Index('idx_crm_workflows_team_id', 'team_id'),
        Index('idx_crm_workflows_status', 'status'),
        {'comment': 'CRMWolf 工作流定义表'}
    )
```

- [ ] **Step 6: migration 131**（`alembic revision -m "crm_workflows"` 生成后核对内容）：create_table `crm_workflows`（列同模型），两个索引，down_revision 指向 `130`（以实际 head 为准，生成时 alembic 会自动填充）。本地执行 `alembic upgrade head` + `alembic current` 验证。

- [ ] **Step 7: `app/models/__init__.py` 导出 Workflow**（跟随现有导出模式）。

- [ ] **Step 8: Commit**

```bash
git add CRM-Server/app/models/workflow.py CRM-Server/app/models/__init__.py \
  CRM-Server/migrations/versions/131_crm_workflows.py CRM-Server/app/services/workflow_dsl.py \
  CRM-Server/tests/unit/test_workflow_dsl.py
git commit -m "feat(server): add workflow model, migration and DSL validation"
```

---

### Task 2: 权限种子与 Workflows API

**Files:**
- Modify: `CRM-Server/app/constants/permissions.py`（ALL_PERMISSIONS 增 4 项）
- Create: `CRM-Server/app/schemas/workflow.py`
- Create: `CRM-Server/app/api/workflows.py`
- Modify: `CRM-Server/app/main.py`（注册 router）
- Test: `CRM-Server/tests/unit/api/test_workflows_api.py`

**Interfaces:**
- Consumes: Task 1 的 `Workflow`、`validate_workflow_dsl`、`VALID_TRANSITIONS`；现有 `get_db` / `get_current_active_user` / `get_current_user_team` / `require_permission`。
- Produces: `/v1/workflows` 全部端点（见共享契约 API 形状）。

- [ ] **Step 1: 权限种子**（插在"审批流程权限"块后）：

```python
    # 自动化工作流权限
    {"name": "查看自动化", "code": "automation:read", "resource": "automation", "action": "view"},
    {"name": "创建自动化", "code": "automation:create", "resource": "automation", "action": "create"},
    {"name": "编辑自动化", "code": "automation:edit", "resource": "automation", "action": "edit"},
    {"name": "发布自动化", "code": "automation:publish", "resource": "automation", "action": "publish"},
```

- [ ] **Step 2: 写失败 API 测试**（沿用现有 API 测试模式；参考 `tests/unit/api/test_acquisition_source_entities_api.py` 的 client/登录/team 隔离 fixture 惯例）。覆盖：创建 201 + 返回 dsl、创建非法 DSL 422、列表只含本团队、详情跨团队 404、PUT 乐观锁 409、DELETE 非 draft 409、DELETE draft 204、状态 draft→published 200、published→draft 422、无 automation:create 权限 403。fixture 内直接向权限表插入 automation:* code（或使用 TEAM_ADMIN 用户，其映射为 "all"）。

- [ ] **Step 3: 运行确认失败**（模块不存在）

- [ ] **Step 4: 实现 `app/schemas/workflow.py`**

```python
from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

WorkflowStatusLiteral = Literal["draft", "published", "paused"]


class WorkflowDslSchema(BaseModel):
    model_config = ConfigDict(extra="allow")
    schema_version: int = Field(..., description="DSL 版本，当前为 1")
    nodes: list[dict[str, Any]] = Field(..., description="节点列表")
    edges: list[dict[str, Any]] = Field(default_factory=list, description="边列表")


class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    dsl: WorkflowDslSchema


class WorkflowUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    dsl: WorkflowDslSchema
    expected_last_modified_time: datetime = Field(..., description="乐观锁：客户端读取时的 last_modified_time")


class WorkflowStatusUpdate(BaseModel):
    status: WorkflowStatusLiteral


class WorkflowSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: Optional[str] = None
    status: WorkflowStatusLiteral
    node_count: int
    created_time: datetime
    last_modified_time: datetime


class WorkflowDetail(WorkflowSummary):
    dsl: WorkflowDslSchema
    created_by: Optional[int] = None
```

- [ ] **Step 5: 实现 `app/api/workflows.py`**（要点，非全文）：

```python
router = APIRouter(prefix="/v1/workflows", tags=["自动化工作流"])

def _get_workflow_or_404(db, workflow_id: int, team_id: int) -> Workflow:
    wf = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.team_id == team_id).first()
    if not wf:
        raise HTTPException(404, "工作流不存在或不属于当前团队")
    return wf

def _detail(wf: Workflow) -> dict:
    return {
        "id": wf.id, "name": wf.name, "description": wf.description, "status": wf.status,
        "node_count": len((wf.dsl or {}).get("nodes", [])),
        "dsl": wf.dsl, "created_by": wf.created_by,
        "created_time": wf.created_time, "last_modified_time": wf.last_modified_time,
    }
```

各端点：GET 列表（`require_permission("automation:read")`，按 team 过滤，映射 summary 含 `node_count`）；POST（`automation:create`，先 `validate_workflow_dsl(dsl.model_dump())`，错误非空则 422 `{"detail": {"errors": [...]}}`）；GET 详情；PUT（`automation:edit`，`expected_last_modified_time` 与库中不匹配→409 "工作流已被修改"，再 DSL 校验）；DELETE（`automation:edit`，非 draft→409）；PUT status（`automation:publish`，查 `VALID_TRANSITIONS`，非法→422）。创建/更新后 `db.refresh` 取 onupdate 时间返回。

- [ ] **Step 6: main.py 注册** `from app.api.workflows import router as workflows_router` + `api_router.include_router(workflows_router)`。

- [ ] **Step 7: 运行测试通过**（Step 2 命令，全部绿）

- [ ] **Step 8: ruff/mypy 快速检查新增文件**

```bash
ruff check app/models/workflow.py app/services/workflow_dsl.py app/schemas/workflow.py app/api/workflows.py
mypy app/services/workflow_dsl.py app/api/workflows.py
```

- [ ] **Step 9: Commit** `git commit -m "feat(server): add workflows API with permissions and optimistic locking"`

---

### Task 3: 前端 API 客户端、节点注册表与图校验

**Files:**
- Create: `CRM-Client/src/api/workflow.ts`
- Create: `CRM-Client/src/components/workflow/workflowNodeRegistry.ts`
- Create: `CRM-Client/src/components/workflow/workflowValidation.ts`
- Test: `CRM-Client/src/components/workflow/__tests__/workflowValidation.test.ts`
- Test: `CRM-Client/src/components/workflow/__tests__/workflowNodeRegistry.test.ts`

**Interfaces:**
- Consumes: 共享契约的节点注册表与校验规则（与 Task 1 Python 实现语义一致）。
- Produces: `workflowApi`（list/create/get/update/remove/updateStatus）；`WORKFLOW_NODE_REGISTRY`（含 `label/icon/component/defaults/isTrigger`）；`validateWorkflow(graph, name): WorkflowValidationIssue[]`（`{ nodeId?, message }`）。

- [ ] **Step 1: 安装依赖**

```bash
cd CRM-Client && npm install @vue-flow/core @vue-flow/background @vue-flow/controls
```

- [ ] **Step 2: 写失败测试**（registry 完整性 + validation 各失败路径 + 合法图通过；断言与 Task 1 Step 1 同语义）。validation 额外含前端专属规则：名称非空≤100；恰好 1 个 trigger；从 trigger BFS 可达所有非孤立节点（孤立=无任何相连边）。测试数据用共享契约 DSL 示例。

- [ ] **Step 3: 运行确认失败**

- [ ] **Step 4: 实现三个模块**。registry 结构：

```ts
import type { Component } from 'vue'

export interface WorkflowNodeConfigPanelProps { config: Record<string, unknown>; 'onUpdate:config': (patch: Record<string, unknown>) => void }

export interface WorkflowNodeTypeDefinition {
  type: string
  label: string
  category: 'trigger' | 'control' | 'action'
  icon: Component
  defaults: () => Record<string, unknown>
  requiredFields: readonly string[]
  summary: (config: Record<string, unknown>) => string
}

export const WORKFLOW_NODE_REGISTRY: Record<string, WorkflowNodeTypeDefinition> = { /* 5 类型 */ }
```

api 客户端沿用 `request` 封装（同 `approvalFlow.ts` 模式，含 eslint-disable 注释惯例）；类型 `WorkflowSummary/WorkflowDetail/WorkflowDsl` 与后端 schema 对齐。

- [ ] **Step 5: 运行测试通过** + `npm run type-check`

- [ ] **Step 6: Commit** `git commit -m "feat(client): add workflow api client, node registry and validation"`

---

### Task 4: 画布编辑器组件群

**Files:**
- Create: `CRM-Client/src/components/workflow/WorkflowEditor.vue`（容器：VueFlow + Background + Controls + 工具栏[名称输入/保存/校验徽标] + palette + 右侧配置 Sheet）
- Create: `CRM-Client/src/components/workflow/WorkflowNodePalette.vue`
- Create: `CRM-Client/src/components/workflow/WorkflowNode.vue`（custom node：类型徽标+label+summary；校验失败红框）
- Create: `CRM-Client/src/components/workflow/nodeConfigPanels/*.vue`（5 个，全部 shadcn-vue 表单：Select/Input/Textarea）
- Test: `CRM-Client/src/components/workflow/__tests__/WorkflowEditor.test.ts`

**Interfaces:**
- Consumes: Task 3 全部产物；`opportunity_stages` 与角色 API（阶段/角色选项）。
- Produces: `WorkflowEditor` props `{ workflowId: number | null }`、emits `{ saved: [WorkflowDetail], cancelled: [] }`；内部完成 加载→编辑→校验→保存（POST/PUT 自动分派）→409/422 错误呈现。

- [ ] **Step 1: 写失败测试**（mock workflowApi + 阶段/角色 API）：挂载空画布显示 palette 5 项；拖入 trigger 后 palette 该项禁用；点击节点打开对应 configPanel 并回写 config；保存时 payload 含 `schema_version:1` + nodes/edges；校验失败（无 trigger）时保存被阻止且问题节点带错误标记；409 时显示"已被修改"提示。

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现组件群**。要点：
  - VueFlow `:nodes/:edges` v-model，`nodeTypes` 注册 custom node，`@connect` 时校验目标非 trigger/非自环（复用 validation 规则函数）；
  - palette 拖拽：HTML5 drag 事件 drop 到画布 `screenToFlowCoordinate` 落点；
  - configPanel 通用 props：`config` + `@update:config`（patch 合并）；阶段 Select 数据来自 procurement stage 模板/商机阶段 API，角色 Select 来自角色 API；
  - 保存流程：`validateWorkflow` → 空则调用 api → 成功 emit saved / 失败按状态码呈现（409 提示刷新重试、422 列出错误）；
  - 无 undo/redo、无自动布局（明确不实现）。

- [ ] **Step 4: 运行测试通过** + `npm run type-check`

- [ ] **Step 5: Commit** `git commit -m "feat(client): add workflow canvas editor with node config panels"`

---

### Task 5: 页面集成与端到端冒烟

**Files:**
- Modify: `CRM-Client/src/views/ApprovalFlowsNew.vue`（页头加"新建工作流"按钮[automation:create 权限]；列表区新增工作流区块：卡片=名称/状态徽标/节点数/最近运行暂未接入；操作=编辑/发布/暂停[automation:publish]/删除草稿[automation:edit]；编辑器以全屏 Dialog 或路由 query `?workflow=<id>` 承载）
- Modify: `CRM-Client/src/views/__tests__/ApprovalFlowsNew.test.ts`（新增工作流区块断言）
- Test: 手动冒烟（见下）

- [ ] **Step 1: 更新页面测试**（先失败）：工作流列表渲染（mock workflowApi.list 返回 1 条 draft，断言名称+草稿徽标+节点数）；"新建工作流"按钮仅 automation:create 可见；发布按钮调用 updateStatus('published')。

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现页面集成**（工作流区块复用现有卡片样式；状态徽标颜色：draft=secondary、published=default、paused=outline；编辑器打开时隐藏页面列表区）。

- [ ] **Step 4: 运行全部前端相关测试**

```bash
npm run test:unit -- --run src/views/__tests__/ApprovalFlowsNew.test.ts \
  src/components/workflow/__tests__/workflowValidation.test.ts \
  src/components/workflow/__tests__/workflowNodeRegistry.test.ts \
  src/components/workflow/__tests__/WorkflowEditor.test.ts \
  src/settingsNavigation.test.ts
npm run type-check
```

- [ ] **Step 5: 后端全量单测回归** `cd CRM-Server && pytest tests/unit -q`（确保无回归）

- [ ] **Step 6: 手动冒烟**（后端 `./run.sh` + 前端 `npm run dev`，浏览器走完整链路）：
  1. 新建工作流 → 拖入 trigger（商机阶段变化，选目标阶段）→ 审批节点（角色）→ 条件分支 → 创建跟进任务 → 通知；全连线；
  2. 保存 → 刷新页面重新打开 → DSL 完整往返（节点位置/配置/连线不丢）；
  3. 发布 → 状态变 published；暂停 → paused；删除 draft 正常；
  4. 故意制造校验失败（删 trigger）→ 保存被阻止并标注。

- [ ] **Step 7: `git diff --check`** + Commit `git commit -m "feat(client): integrate workflow canvas into approval flows new page"`

---

## Self-Review

- 覆盖检查：设计文档 §3 模型→Task 1；§4 API+权限→Task 2；§5 前端结构→Task 3/4；页面集成→Task 5；§6 错误处理→Task 4/5（409/422 呈现）；§7 测试策略→各任务测试步骤。无缺口。
- 占位符扫描：所有代码步骤给出完整代码或确定性要点+接口签名，无 TBD。
- 类型一致性：`WorkflowSummary/WorkflowDetail/WorkflowDsl` 前后端字段一致；`validate_workflow_dsl`/`validateWorkflow` 错误语义一致；节点 type key 两端同一张表。
- 风险提示：Vue Flow 拖拽事件在 jsdom 中的模拟有限，Task 4 测试对 drop 交互用组件方法/事件派发模拟，视觉交互依赖 Task 5 手动冒烟兜底。
