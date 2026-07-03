# 审批引擎泛化（回款/发票审批接入多级引擎）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前硬绑定合同的多级审批引擎泛化为支持任意业务单据（合同/回款/发票），并把回款登记、发票申请接入多级审批引擎。

**Architecture:** 在 `Approval` 实例表新增 `business_type`（CONTRACT/PAYMENT/INVOICE）+ `business_id` 通用外键，保持 `contract_id` 兼容旧数据；将 CRUD 层与合同的状态耦合抽象为"业务单据适配器"（按 `business_type` 调用对应单据的状态切换回调）；新增 `payment:*` 审批权限码与角色映射；前端 `ApprovalProcess.vue` 重构为 `entityType/entityId` 通用形态，新增/启用回款与发票审批页。

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy / Alembic（PostgreSQL）/ Vue 3 / TypeScript / Pinia / pytest / ruff / mypy

## 现状摘要（证据）

- 模型 `Approval`（`CRM-Server/app/models/approval.py:88`）表名 `crm_contract_approvals`，仅 `contract_id` 外键（:93）。
- 状态机 `create_approval/approve/cancel`（`CRM-Server/app/crud/approval.py:502-609`）硬编码 `contract.status = ContractStatus.PENDING_REVIEW/SIGNED/DRAFT`。
- `match_flow`（:172）按合同 `total_amount/license_type/team_id` 匹配。
- 发票现有**自管单步审批**（`crud/invoice.py:257-324`，状态 DRAFT/PENDING_REVIEW/APPROVED/REJECTED/ISSUED），未接引擎。
- 回款**无审批**，`PaymentRecord.confirmation_status`（PENDING/CONFIRMED/DISPUTED）字段存在但**无 confirm API 端点**（`crud/payment.py:460-492` 的 `confirm_payment` 无调用方，为准 dead code）。
- 权限码 `ALL_PERMISSIONS`（`CRM-Server/app/constants/permissions.py:8`，list[dict]，字段 name/code/resource/action[/scope]）；`payment:*` 三无 `approve`；`invoice:approve` 为 flat 无 scope。
- 角色映射 `ROLE_PERMISSIONS_MAPPING`（:173），`TEAM_ADMIN`="all" 旁路（:174），FINANCE 列表 :219-229。
- 权限初始化 `init_roles_permissions`（`app/services/init_service.py:99`）启动时幂等 insert，**无需迁移灌数据**，新增码后重启自动生效。
- 前端 `ApprovalProcess.vue`（`src/components/ApprovalProcess.vue:48-55`）props 强耦合合同；`src/api/approval.ts:6-18` 路径写死 `contracts/{contractId}`；`router/index.ts:313-320` finance 审批路由被注释；侧边栏 `AppLayout.vue:33` 无 finance 菜单。
- 通知模板 `notify_approval_pending/approved/rejected`（`app/services/notification.py:48/116/173`）签名含 `contract_name/contract_id`，需泛化。

## Global Constraints

- **team_id 必传**：所有 CRUD 操作必须传 team_id（CLAUDE.md 红线）。审批实例 `business_type+business_id` 必须在 team_id 隔离下解析。
- **CRUD 统一入口**：禁止裸 `db.query()` 在 api 层；新逻辑放 `app/crud/approval.py`。
- **Alembic 迁移**：禁止独立 DB 脚本；新迁移 `down_revision = '011_add_account_name_norm'`，遵循 `CRM-Server/docs/MIGRATION_RULES.md`；过 `scripts/check_migrations.py`。
- **Pydantic 强制校验**：所有 API 入参走 schema，禁止裸 dict。
- **防幻觉**：业务枚举必须查阅常量定义，禁止推断（`business_type` 新枚举放 `app/constants/`）。
- **TypeScript 四禁令**：前端禁 `any`/`as any`/`@ts-ignore`/`!`，props 必须类型化，API 响应走 Zod。
- **不破坏合同审批**：泛化全程保持现有合同审批行为不变（回归保护）。
- **frequent commits**：每个 Task 末尾 commit。

## File Structure

**后端新建**
- `CRM-Server/app/constants/business_types.py` — `BusinessType` 枚举（CONTRACT/PAYMENT/INVOICE）+ 展示名。
- `CRM-Server/app/services/approval_adapter.py` — 业务单据适配器层：按 `business_type` 提供 `get_entity/match_flow_kwargs/on_submit/on_approved/on_rejected/on_cancelled/get_submitter` 回调。
- `CRM-Server/app/schemas/approval_generic.py` — 通用审批 API schema（`entityType/entityId`）。
- `CRM-Server/migrations/versions/012_approval_generic_business.py` — 加 `business_type/business_id` 列 + 回填。
- `CRM-Server/tests/unit/test_approval_adapter.py`、`tests/unit/test_approval_generic_api.py` — 单测。

**后端修改**
- `CRM-Server/app/models/approval.py` — `Approval` 加 `business_type/business_id` 列与索引，保留 `contract_id`。
- `CRM-Server/app/crud/approval.py` — `create_approval/approve/cancel/match_flow/get_by_xxx` 解耦合同；改调适配器。
- `CRM-Server/app/api/approvals.py` — 新增通用端点 `POST /v1/approvals/{entity_type}/{entity_id}/submit|approve|cancel`、`GET /.../detail`；保留旧 `/contracts/{contract_id}/...` 为 thin wrapper（向后兼容）。
- `CRM-Server/app/api/payments.py` — 新增 `POST /{record_id}/submit-approval`、`/{record_id}/confirm`（审批通过后确认入账）。
- `CRM-Server/app/api/invoices.py` — `submit`/`review`/`withdraw` 改为调引擎；单步 `review` 标记 deprecated 保留兼容，或迁移期内下沉。
- `CRM-Server/app/constants/permissions.py` — 新增 `payment:submit/withdraw/approve/approve:own/approve:all`、`invoice:approve:own/withdraw`（视 Task 表）；更新 FINANCE/SALES_DIRECTOR 映射。
- `CRM-Server/app/services/notification.py` + `feishu_service` — 通知签名泛化 `entity_type/entity_id/entity_name`，保留旧参数为别名。
- `CRM-Server/app/schemas/approval.py`、`approval_ai.py` — 流程模板支持 `business_type` 过滤。
- `CRM-Docs/system/GLOSSARY.md` — 录入新权限码。

**前端新建**
- `CRM-Client/src/api/approvalGeneric.ts` — 通用审批 API（entityType/entityId）。
- `CRM-Client/src/components/ApprovalProcessGeneric.vue` — 通用审批操作组件（数据驱动，复用 `ApprovalTimeline`）。
- `CRM-Client/src/stores/approval.ts` — 审批 Pinia store（当前缺失）。

**前端修改**
- `CRM-Client/src/views/Payments.vue`、`InvoiceDetail.vue`/`Invoices.vue` — 嵌入通用审批组件 + `v-permission`。
- `CRM-Client/src/views/FinanceInvoiceApprovals.vue`、`FinancePaymentConfirmations.vue` — 接通用审批组件。
- `CRM-Client/src/router/index.ts:313-320` — 解除 finance 路由注释；新增 payments/invoices 审批路由。
- `CRM-Client/src/AppLayout.vue`、`src/types/sidebar.ts` — 加 finance 菜单项。
- `CRM-Client/src/stores/permissions.ts` — 确认 `canApproveOwn('payment')` 走冒号格式（已确认 :54-60）。

---

## 工程审查加固（plan-eng-review 产出，10 条全纳入）

> 本节由 `/plan-eng-review`（Architecture/Code Quality/Tests/Performance 4 节）产出，每条带 confidence 与落地 Task。3 P0 + 6 P1 + 1 P2。已应用 prior learning `permission-view-filter-missing` (conf 9/10)。

### P0 — 不补会坏/越权

| # | conf | 隐患 | 落地 |
|---|------|------|------|
| **E1** | 9/10 | **合同审批回归风险**：`match_flow`→`match_flow_generic(CONTRACT)` 改造后，合同旧 flow 多了 `business_type='CONTRACT'` 过滤条件。实现若遗漏 team_id+business_type 联合过滤，原本匹配的合同流会匹配不到，合同审批静默失效。 | Task A5：`match_flow_generic` 的 CONTRACT 分支**必须保持原 `match_flow` 匹配结果不变**（仅多加 business_type='CONTRACT' 条件，其余 team_id/金额/license_type/评分逻辑逐字沿用）；Task D2：新增"合同提交→匹配同一 flow→状态切换不变"端到端回归测试 `tests/unit/test_contract_approval_regression.py`。 |
| **E2** | 9/10 | **越权风险**（prior-learning 命中）：ApprovalCenter 列表若不按 `submitter_id==current_user`/当前节点角色过滤，全 team 数据可见。客户/合同/线索列表已有此前科（`leads.py`/`customers.py`/`opportunities.py`）。 | Task C3：ApprovalCenter 三 tab 严格过滤——"我发起的" `WHERE submitter_id=:uid AND team_id=:tid`；"待处理" `WHERE current_node.approve_role IN (user_roles) AND status=PENDING AND team_id=:tid`；"已完成"按 `ApprovalRecord.approver_id=:uid`。**禁止**仅按 team_id 拉全量。 |
| **E3** | 9/10 | **合同回归测试缺失**：`match_flow_generic` 改造无专项端到端回归。 | Task D2：见 E1 的回归测试，断言"同一合同+同一 flow 配置下，改造前后 match 结果与状态切换完全一致"，含金额边界/license_type 匹配/多 flow 评分排序三场景。 |

### P1 — 应该补

| # | conf | 隐患 | 落地 |
|---|------|------|------|
| **E4** | 8/10 | 适配器 `on_approved/on_rejected/on_cancelled` 缺 entity None 守卫：业务单据被软删/跨 team 时 `get_entity` 返 None，`None.status` AttributeError。现有合同代码 `crud/approval.py:578/585` 有 `if contract:` 守卫，泛化后丢失。 | Task A4/A5：所有适配器 `on_*` 方法首行 `if entity is None: return`；`approve/cancel` 内 `entity = adapter.get_entity(...)` 后判 None 跳过状态回写（与现有合同 `if contract:` 行为对齐）。 |
| **E5** | 7/10 | `match_flow_generic` 未匹配=None 时调用方契约未定：回款"提交审批"按钮在无 PAYMENT 流时该走免审批直通还是灰掉——UX/架构交界方案未明确。 | **【替你拍板】** Task B1/C3：回款登记后端点先调 `match_flow_generic(PAYMENT,...)`；匹配到流→建 Approval 走审批；未匹配→**不建 Approval，回款记录保持 `confirmation_status=PENDING` 待财务 `confirm`**（决策1的免审批直通=沿用现有财务确认路径，非自动 CONFIRMED）。前端 Payments.vue 回款记录行始终显示"提交审批"按钮——若后端返回"未配置审批流，已转为财务确认"则 toast 提示并隐藏审批入口。这样小额回款不被强制审批，大额配了流才走审批。如不合意可改为"未匹配=报错要求配流"。 |
| **E6** | 8/10 | 批量审批事务/部分失败策略未定：N 条逐条乐观锁，第 k 条被他人审批失败时前 k-1 条已 commit 还是回滚。 | **【替你拍板】** Task C3/A6：批量审批采用**逐条独立事务 + 部分成功汇总**（非整体事务，避免一条失败全回滚让审批人白做）。每条 try/except，失败行收集原因，结束后 **不依赖 toast**（toast 是辅助）：成功行实时从列表移除（动画过渡）；失败行保留在列表 + 红色徽章"审批失败"；失败弹窗显示失败原因 + "重试"按钮。乐观锁冲突行单列"已被他人处理"。如不合意可改为"整体事务全或全不"。符合 §8 error-recovery：错误包含清晰恢复路径。 |
| **E7** | 8/10 | 在途数据平迁测试缺失：B2 `INSERT INTO crm_contract_approvals` 补建 APPROVED 发票审批记录无平迁正确性测试。 | Task B2：补 `tests/unit/test_invoice_data_migration.py`，seed 旧 APPROVED/PENDING_REVIEW/ISSUED/REJECTED 发票，跑迁移后断言：APPROVED 行数==补建 Approval 行数且 status=APPROVED/business_type=INVOICE；PENDING_REVIEW 全回退 DRAFT；ISSUED/REJECTED 不动。 |
| **E8** | 8/10 | 批量审批部分失败测试缺失（与 E6 配对）。 | Task C3：补 `tests/unit/test_bulk_approval_partial_failure.spec.ts`，mock 第 3 条乐观锁冲突，断言前 2 条成功、第 3 条标失败、toast 汇总正确。 |
| **E9** | 7/10 | ApprovalCenter 列表 N+1：每行查 overdue_hours + 当前节点审批人 + 实体摘要，逐行查则 N+1。 | Task C3：列表查询用 joinedload 预加载 `Approval.current_node`、`Approval.flow`、`Approval.records`；overdue_hours 在 SQL 层算（`EXTRACT(EPOCH FROM now()-created_time)/3600`）而非 Python；实体摘要（客户名/合同号）按 business_type 批量预取后内存 join。 |

### P2 — 锦上添花

| # | conf | 隐患 | 落地 |
|---|------|------|------|
| **E10** | 7/10 | 通知铃铛 60s 轮询无退避/后台 tab 暂停，N 在线审批人持续打 /overdue。 | **【已对齐审批入口优化 plan】** Task C4：审批入口改为 Header Icon（唯一轻量入口），点击直接跳转 `/approvals`（无下拉预览）。轮询优化：`document.visibilitychange`——后台 tab 暂停轮询，前台恢复；失败指数退避（60→120→240s 封顶 5min）；可见时立即拉一次。参见：`.claude/plans/jolly-frolicking-shell.md` |

---

## Phase A — 后端引擎泛化（合同回归不破）

### Task A1: BusinessType 常量枚举

**Files:**
- Create: `CRM-Server/app/constants/business_types.py`
- Test: `CRM-Server/tests/unit/test_business_types.py`

**Interfaces:**
- Produces: `BusinessType` 类常量 `CONTRACT="CONTRACT"`、`PAYMENT="PAYMENT"`、`INVOICE="INVOICE"`；`ALL_BUSINESS_TYPES: list[str]`；`BUSINESS_TYPE_DISPLAY_NAMES: dict[str,str]`；`is_valid_business_type(bt: str) -> bool`。

- [ ] **Step 1: Write the failing test**

```python
# CRM-Server/tests/unit/test_business_types.py
from app.constants.business_types import (
    BusinessType, ALL_BUSINESS_TYPES, BUSINESS_TYPE_DISPLAY_NAMES, is_valid_business_type
)

def test_business_type_constants():
    assert BusinessType.CONTRACT == "CONTRACT"
    assert BusinessType.PAYMENT == "PAYMENT"
    assert BusinessType.INVOICE == "INVOICE"

def test_all_business_types():
    assert set(ALL_BUSINESS_TYPES) == {"CONTRACT", "PAYMENT", "INVOICE"}

def test_display_names():
    for bt in ALL_BUSINESS_TYPES:
        assert bt in BUSINESS_TYPE_DISPLAY_NAMES
    assert BUSINESS_TYPE_DISPLAY_NAMES["PAYMENT"] == "回款登记"

def test_is_valid():
    assert is_valid_business_type("CONTRACT") is True
    assert is_valid_business_type("UNKNOWN") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd CRM-Server && pytest tests/unit/test_business_types.py -v`
Expected: FAIL with `ModuleNotFoundError: app.constants.business_types`

- [ ] **Step 3: Write minimal implementation**

```python
# CRM-Server/app/constants/business_types.py
"""审批业务单据类型枚举（防幻觉：禁止推断，必须查本文件）"""

class BusinessType:
    CONTRACT = "CONTRACT"
    PAYMENT = "PAYMENT"
    INVOICE = "INVOICE"

ALL_BUSINESS_TYPES = [BusinessType.CONTRACT, BusinessType.PAYMENT, BusinessType.INVOICE]

BUSINESS_TYPE_DISPLAY_NAMES = {
    BusinessType.CONTRACT: "合同",
    BusinessType.PAYMENT: "回款登记",
    BusinessType.INVOICE: "发票申请",
}

def is_valid_business_type(business_type: str) -> bool:
    return business_type in ALL_BUSINESS_TYPES
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd CRM-Server && pytest tests/unit/test_business_types.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/constants/business_types.py CRM-Server/tests/unit/test_business_types.py
git commit -m "feat(approval): add BusinessType enum constant"
```

### Task A2: Approval 模型加 business_type/business_id 列

**Files:**
- Modify: `CRM-Server/app/models/approval.py:88-115`
- Test: `CRM-Server/tests/unit/test_approval_model_fields.py`

**Interfaces:**
- Produces: `Approval.business_type: str`（default `BusinessType.CONTRACT`）、`Approval.business_id: BigInteger`（nullable, indexed）；保留 `contract_id` 不变；新复合索引 `idx_approval_business` on `(business_type, business_id)`。

- [ ] **Step 1: Write the failing test**

```python
# CRM-Server/tests/unit/test_approval_model_fields.py
from app.models.approval import Approval
from app.constants.business_types import BusinessType

def test_approval_has_business_columns():
    cols = {c.name for c in Approval.__table__.columns}
    assert "business_type" in cols
    assert "business_id" in cols
    assert "contract_id" in cols  # 保留兼容

def test_approval_business_type_default():
    bt_col = Approval.__table__.columns.business_type
    assert bt_col.default is not None
    assert bt_col.default.arg == BusinessType.CONTRACT

def test_approval_business_index():
    idx_names = {idx.name for idx in Approval.__table__.indexes}
    assert "idx_approval_business" in idx_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd CRM-Server && pytest tests/unit/test_approval_model_fields.py -v`
Expected: FAIL — `business_type` 列不存在

- [ ] **Step 3: Modify model**

在 `CRM-Server/app/models/approval.py:88` `Approval` 类中，`contract_id` 列**之后**插入：

```python
    business_type = Column(String(20), nullable=False, default=BusinessType.CONTRACT, comment="业务单据类型：CONTRACT/PAYMENT/INVOICE")
    business_id = Column(BigInteger, nullable=True, index=True, comment="业务单据ID（与 business_type 联合定位单据）")
```

文件顶部 import 区加（靠近现有 import）：

```python
from app.constants.business_types import BusinessType
```

`__table_args__` 中 `Index('idx_approval_contract', 'contract_id')` 之后加：

```python
        Index('idx_approval_business', 'business_type', 'business_id'),
```

> 不删 `contract_id`、不改表名（兼容旧数据与回归）。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd CRM-Server && pytest tests/unit/test_approval_model_fields.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/models/approval.py CRM-Server/tests/unit/test_approval_model_fields.py
git commit -m "feat(approval): add business_type/business_id columns to Approval model"
```

### Task A3: Alembic 迁移 012 — 加列 + 回填旧数据

**Files:**
- Create: `CRM-Server/migrations/versions/012_approval_generic_business.py`
- Test: 手动 `alembic upgrade head` / `downgrade -1`

**Interfaces:**
- Produces: 迁移 `012_approval_generic_business`，`down_revision='011_add_account_name_norm'`。给 `crm_contract_approvals` 加 `business_type`（default 'CONTRACT' NOT NULL）+ `business_id`（nullable）；给 `crm_approval_flows` 加 `business_type`（default 'CONTRACT' NOT NULL，现有 flow 自动归类合同流，无需回填）；回填带 orphan 守卫（见决策 5）；加 `idx_approval_business` 与 `idx_flow_business_type`；upgrade 末尾非阻断校验日志。

- [ ] **Step 1: Write the migration**

```python
# CRM-Server/migrations/versions/012_approval_generic_business.py
"""Add business_type/business_id to crm_contract_approvals and business_type to crm_approval_flows
for generic approval engine (CONTRACT/PAYMENT/INVOICE).

Revision ID: 012_approval_generic_business
Revises: 011_add_account_name_norm
Create Date: 2026-07-02

"""
import logging
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision: str = '012_approval_generic_business'
down_revision: Union[str, None] = '011_add_account_name_norm'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.migration.012")

def upgrade() -> None:
    # 1. crm_contract_approvals 加 business_type / business_id
    op.add_column('crm_contract_approvals',
        sa.Column('business_type', sa.String(length=20), nullable=False, server_default='CONTRACT',
                  comment='业务单据类型：CONTRACT/PAYMENT/INVOICE/ORPHAN'))
    op.add_column('crm_contract_approvals',
        sa.Column('business_id', sa.BigInteger(), nullable=True, comment='业务单据ID'))

    # 2. 回填：有合同关联的旧记录 business_id = contract_id（带 orphan 守卫）
    op.execute(
        "UPDATE crm_contract_approvals SET business_id = contract_id, business_type='CONTRACT' "
        "WHERE business_id IS NULL AND contract_id IS NOT NULL"
    )
    # 2b. 孤儿行（合同已软删导致 contract_id IS NULL）标为 ORPHAN，避免 CONTRACT+NULL business_id 矛盾
    op.execute(
        "UPDATE crm_contract_approvals SET business_type='ORPHAN' "
        "WHERE business_id IS NULL AND contract_id IS NULL"
    )
    op.create_index('idx_approval_business', 'crm_contract_approvals', ['business_type', 'business_id'])

    # 3. crm_approval_flows 加 business_type（现有 flow 默认归类合同流，无需回填）
    op.add_column('crm_approval_flows',
        sa.Column('business_type', sa.String(length=20), nullable=False, server_default='CONTRACT',
                  comment='流程适用单据类型：CONTRACT/PAYMENT/INVOICE'))
    op.create_index('idx_flow_business_type', 'crm_approval_flows', ['business_type'])

    # 4. 非阻断校验：打印孤儿审批数（风格对齐 scripts/check_migrations.py，不阻断）
    bind = op.get_bind()
    orphan_count = bind.execute(
        text("SELECT COUNT(*) FROM crm_contract_approvals WHERE business_type='ORPHAN'")
    ).scalar() or 0
    logger.warning("[012] 孤儿审批记录（合同已删除）数量: %s", orphan_count)

def downgrade() -> None:
    op.drop_index('idx_flow_business_type', table_name='crm_approval_flows')
    op.drop_column('crm_approval_flows', 'business_type')
    op.drop_index('idx_approval_business', table_name='crm_contract_approvals')
    # 回滚前把 ORPHAN 还原为 CONTRACT（保持原 business_type 默认语义）
    op.execute("UPDATE crm_contract_approvals SET business_type='CONTRACT' WHERE business_type='ORPHAN'")
    op.drop_column('crm_contract_approvals', 'business_id')
    op.drop_column('crm_contract_approvals', 'business_type')
```

> 注：`ORPHAN` 作为 business_type 的合法值需要在 `BusinessType` 常量（Task A1）中追加，或仅作为 DB 内部标记、代码层 `is_valid_business_type` 不收录（API 层禁止主动创建 ORPHAN）。实施时选后者：`ORPHAN` 不进 `ALL_BUSINESS_TYPES`，仅供迁移标记与 `get_by_entity` 跳过。

- [ ] **Step 2: Run upgrade**

Run: `cd CRM-Server && alembic upgrade head`
Expected: `Running upgrade 011_add_account_name_norm -> 012_approval_generic_business`

- [ ] **Step 3: Run downgrade then upgrade to verify reversibility**

Run: `cd CRM-Server && alembic downgrade -1 && alembic upgrade head`
Expected: 两步均成功，无残留。

- [ ] **Step 4: Verify with migration checker**

Run: `cd CRM-Server && python scripts/check_migrations.py`
Expected: 通过（无 team_id 隔离回归，新列非唯一约束）。

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/migrations/versions/012_approval_generic_business.py
git commit -m "feat(migration): 012 add business_type/business_id for generic approval"
```

### Task A4: 业务单据适配器层

**Files:**
- Create: `CRM-Server/app/services/approval_adapter.py`
- Test: `CRM-Server/tests/unit/test_approval_adapter.py`

**Interfaces:**
- Produces: `ApprovalEntityAdapter` 协议（Protocol）含方法 `get_entity(db, business_id, team_id)`、`get_submitter(entity)`、`match_kwargs(entity) -> dict`、`on_submit(db, entity)`、`on_approved(db, entity)`、`on_rejected(db, entity)`、`on_cancelled(db, entity)`、`get_name(entity) -> str`。
- **E4 守卫规则（强制）**：所有 `on_submit/on_approved/on_rejected/on_cancelled` 实现首行 `if entity is None: return`——业务单据被软删/跨 team 时 `get_entity` 返 None，避免 `None.status` AttributeError（对齐现有合同 `crud/approval.py:578/585` 的 `if contract:` 守卫）。Contract/Payment 适配器所有 `on_*` 方法同样加守卫。
- Produces: 适配器注册表 `get_adapter(business_type: str) -> ApprovalEntityAdapter`，注册 `CONTRACT/PAYMENT/INVOICE` 三个实现。

- [ ] **Step 1: Write the failing test**

```python
# CRM-Server/tests/unit/test_approval_adapter.py
import pytest
from app.services.approval_adapter import get_adapter
from app.constants.business_types import BusinessType
from app.models.contract import ContractStatus

def test_get_contract_adapter():
    a = get_adapter(BusinessType.CONTRACT)
    assert a is not None

def test_get_payment_adapter():
    assert get_adapter(BusinessType.PAYMENT) is not None

def test_get_invoice_adapter():
    assert get_adapter(BusinessType.INVOICE) is not None

def test_invalid_business_type_raises():
    with pytest.raises(ValueError):
        get_adapter("UNKNOWN")

def test_contract_adapter_on_submit(db_session, seed_contract_draft):
    # seed_contract_draft fixture 提供一个 DRAFT 合同
    from app.services.approval_adapter import get_adapter
    a = get_adapter(BusinessType.CONTRACT)
    a.on_submit(db_session, seed_contract_draft)
    assert seed_contract_draft.status == ContractStatus.PENDING_REVIEW
```

> `db_session`/`seed_contract_draft` 由现有 `tests/conftest.py` 提供；若缺则在本 Task 的 conftest 增补 fixture（见 Step 3）。

- [ ] **Step 2: Run test to verify it fails**

Run: `cd CRM-Server && pytest tests/unit/test_approval_adapter.py -v`
Expected: FAIL — 模块不存在

- [ ] **Step 3: Write implementation**

```python
# CRM-Server/app/services/approval_adapter.py
"""审批引擎业务单据适配器：把审批 CRUD 与具体单据（合同/回款/发票）的状态机解耦。

每个 business_type 注册一个 ApprovalEntityAdapter，负责：
- 取实体、取提交人、取匹配审批流的维度
- 提交/通过/驳回/撤回时的单据状态切换
- 取单据展示名（通知用）
"""
from typing import Protocol, Any
from sqlalchemy.orm import Session

from app.constants.business_types import BusinessType
from app.models.contract import Contract, ContractStatus
from app.models.payment import PaymentRecord
from app.models.payment import PaymentConfirmationStatus
from app.models.invoice import InvoiceApplication, InvoiceApplicationStatus


class ApprovalEntityAdapter(Protocol):
    business_type: str

    def get_entity(self, db: Session, business_id: int, team_id: int) -> Any: ...
    def get_submitter(self, entity: Any) -> tuple[str, str | None]: ...
    def match_kwargs(self, entity: Any) -> dict: ...
    def on_submit(self, db: Session, entity: Any) -> None: ...
    def on_approved(self, db: Session, entity: Any) -> None: ...
    def on_rejected(self, db: Session, entity: Any) -> None: ...
    def on_cancelled(self, db: Session, entity: Any) -> None: ...
    def get_name(self, entity: Any) -> str: ...


class ContractAdapter:
    business_type = BusinessType.CONTRACT

    def get_entity(self, db, business_id, team_id):
        from app.crud.contract import contract_crud
        return contract_crud.get_by_id(db, business_id, team_id)

    def get_submitter(self, entity):
        return entity.creator_id, getattr(entity, "creator_name", None)

    def match_kwargs(self, entity):
        return {
            "amount": float(entity.total_amount) if entity.total_amount else 0,
            "license_type": getattr(entity, "license_type", None),
        }

    def on_submit(self, db, entity):
        entity.status = ContractStatus.PENDING_REVIEW

    def on_approved(self, db, entity):
        entity.status = ContractStatus.SIGNED

    def on_rejected(self, db, entity):
        entity.status = ContractStatus.DRAFT

    def on_cancelled(self, db, entity):
        entity.status = ContractStatus.DRAFT

    def get_name(self, entity):
        return getattr(entity, "name", None) or f"合同#{entity.id}"


class PaymentRecordAdapter:
    business_type = BusinessType.PAYMENT

    def get_entity(self, db, business_id, team_id):
        from app.crud.payment import payment_record_crud
        return payment_record_crud.get_by_id(db, business_id, team_id)

    def get_submitter(self, entity):
        return entity.creator_id, getattr(entity, "creator_name", None)

    def match_kwargs(self, entity):
        return {"amount": float(entity.actual_amount) if entity.actual_amount else 0, "license_type": None}

    def on_submit(self, db, entity):
        entity.confirmation_status = PaymentConfirmationStatus.PENDING

    def on_approved(self, db, entity):
        # 审批通过即确认入账
        entity.confirmation_status = PaymentConfirmationStatus.CONFIRMED

    def on_rejected(self, db, entity):
        # 驳回：保持 PENDING（待重新登记/修正），不改 CONFIRMED
        entity.confirmation_status = PaymentConfirmationStatus.PENDING

    def on_cancelled(self, db, entity):
        entity.confirmation_status = PaymentConfirmationStatus.PENDING

    def get_name(self, entity):
        return f"回款登记#{entity.id}"


class InvoiceApplicationAdapter:
    business_type = BusinessType.INVOICE

    def get_entity(self, db, business_id, team_id):
        from app.crud.invoice import invoice_application_crud
        return invoice_application_crud.get_by_id(db, business_id, team_id)

    # 发票提交人字段是 applicant_id（非 creator_id），见决策 3
    def get_submitter(self, entity):
        return entity.applicant_id, getattr(entity, "applicant_name", None)

    def match_kwargs(self, entity):
        # 开票金额字段是 invoice_amount（非 amount），见决策 3
        return {"amount": float(entity.invoice_amount or 0), "license_type": None}

    def on_submit(self, db, entity):
        entity.status = InvoiceApplicationStatus.PENDING_REVIEW

    def on_approved(self, db, entity):
        if entity is None: return  # E4 守卫：业务单据被软删/跨 team 时跳过
        # 引擎终态回写快照，InvoiceDetail.vue 仍读这三字段，见决策 2(c)
        entity.status = InvoiceApplicationStatus.APPROVED
        entity.reviewed_time = func.now()

    def on_rejected(self, db, entity):
        if entity is None: return  # E4
        entity.status = InvoiceApplicationStatus.REJECTED
        entity.reviewed_time = func.now()

    def on_cancelled(self, db, entity):
        entity.status = InvoiceApplicationStatus.DRAFT

    def get_name(self, entity):
        return f"发票申请#{entity.id}"


_REGISTRY: dict[str, ApprovalEntityAdapter] = {
    BusinessType.CONTRACT: ContractAdapter(),
    BusinessType.PAYMENT: PaymentRecordAdapter(),
    BusinessType.INVOICE: InvoiceApplicationAdapter(),
}


def get_adapter(business_type: str) -> ApprovalEntityAdapter:
    adapter = _REGISTRY.get(business_type)
    if adapter is None:
        raise ValueError(f"不支持的业务单据类型: {business_type}")
    return adapter
```

> 依赖前置：`payment_record_crud.get_by_id` 与 `invoice_application_crud.get_by_id`、`entity.creator_id`、`InvoiceApplication.amount` 需在 Task A4 实施时核验存在；若 `get_by_id` 不存在，本 Task 附带在对应 crud 中补同名方法（最小实现：按 id+team_id 查并返回 None）。`InvoiceApplication.amount` 若无，改用 `invoice_amount` —— 实施时读模型确认。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd CRM-Server && pytest tests/unit/test_approval_adapter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/approval_adapter.py CRM-Server/tests/unit/test_approval_adapter.py
git commit -m "feat(approval): add business entity adapter layer"
```

### Task A5: CRUD 层解耦合同

**Files:**
- Modify: `CRM-Server/app/crud/approval.py:172-285`（match_flow）、`:502-609`（create/approve/cancel）、`:412,427,481,645,655,683`（get_by_contract_id 等）
- Test: `CRM-Server/tests/unit/test_approval_crud_generic.py`

**Interfaces:**
- Produces: 新方法
  - `match_flow_generic(db, business_type, team_id, amount, license_type) -> tuple[ApprovalFlow|None, str|None]`
  - `create_approval_generic(db, business_type, business_id, team_id, flow, submitter_id, submitter_name) -> Approval`
  - `get_by_entity(db, business_type, business_id, team_id) -> Approval|None`
- 旧 `create_approval/approve/cancel` 改为 thin wrapper 调 generic 版（传入 `BusinessType.CONTRACT`），保持合同回归。

- [ ] **Step 1: Write the failing test**

```python
# CRM-Server/tests/unit/test_approval_crud_generic.py
import pytest
from app.crud.approval import approval_crud, ApprovalCRUD
from app.constants.business_types import BusinessType
from app.models.approval import ApprovalStatus

def test_get_by_entity_returns_none_when_absent(db_session):
    a = approval_crud.get_by_entity(db_session, BusinessType.INVOICE, 999999, team_id=1)
    assert a is None

def test_create_approval_generic_writes_business_columns(db_session, seed_flow_with_one_node, seed_invoice_draft):
    flow, _ = seed_flow_with_one_node
    ap = approval_crud.create_approval_generic(
        db_session, BusinessType.INVOICE, seed_invoice_draft.id,
        team_id=seed_invoice_draft.team_id, flow=flow,
        submitter_id="u1", submitter_name="eddie")
    assert ap.business_type == BusinessType.INVOICE
    assert ap.business_id == seed_invoice_draft.id
    assert ap.status == ApprovalStatus.PENDING

def test_contract_create_legacy_still_works(db_session, seed_contract_draft, seed_flow_with_one_node):
    flow, _ = seed_flow_with_one_node
    ap = approval_crud.create_approval(db_session, seed_contract_draft, flow, "u1", "eddie")
    assert ap.business_type == BusinessType.CONTRACT
    assert ap.business_id == seed_contract_draft.id
    assert ap.contract_id == seed_contract_draft.id  # 兼容
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd CRM-Server && pytest tests/unit/test_approval_crud_generic.py -v`
Expected: FAIL — `create_approval_generic` 不存在

- [ ] **Step 3: Refactor crud/approval.py**

(a) 新增 `match_flow_generic`：把 `match_flow`（:172-285）的金额计算与过滤逻辑抽入，入参改为 `(db, business_type, team_id, amount, license_type)`，flow 过滤增加 `ApprovalFlow.business_type == business_type` 条件（其他评分逻辑不变）。

> **E1 合同回归契约（P0）**：`match_flow_generic(business_type='CONTRACT')` 的匹配结果必须与改造前 `match_flow(contract)` **逐字一致**——仅多 `business_type='CONTRACT'` 一个过滤条件，team_id 隔离、金额范围比较、license_type 匹配、`calculate_flow_precision_score` 评分、`(-score, created_time)` 排序逻辑全部沿用原 `match_flow` 代码。原 `match_flow` 改为 thin wrapper 调 `match_flow_generic('CONTRACT', team_id, contract.total_amount, contract.license_type)`。Task D2 配 E3 回归测试三场景（金额边界/license_type/多 flow 评分排序）验证不变。

> **关键语义（决策 1）**：`match_flow_generic` 的"未匹配"返回值按 `business_type` 区分——
> - `CONTRACT`：未匹配返回 `(None, "未找到匹配的审批流程，请联系管理员配置")`（沿用合同"未匹配=报错阻断"语义，调用方报 400）；
> - `PAYMENT`/`INVOICE`：未匹配返回 `(None, None)`（**非报错**，调用方判定 None=免审批直通，见决策 1/5：未配置流=免审批）。
>
> 即 `match_flow_generic` 内部按 business_type 分支决定"未匹配"是 None 还是 error。合同原 `match_flow` 保持不变（仍调 generic 的 CONTRACT 分支并保留报错语义）。

(b) 在 `ApprovalFlow` 模型（`app/models/approval.py:21`）本 Task 附带加列 `business_type = Column(String(20), nullable=False, default=BusinessType.CONTRACT)`（同步需一条迁移或并入 012；并入 012 更优——回到 Task A3 补列）。**实施时把该列加进 012 迁移与模型，避免单独迁移。**

(c) `create_approval_generic`：

```python
    def create_approval_generic(self, db, business_type, business_id, team_id, flow, submitter_id, submitter_name) -> Approval:
        from app.models.approval import ApprovalNode, ApprovalRecord
        from app.services.approval_adapter import get_adapter
        adapter = get_adapter(business_type)
        entity = adapter.get_entity(db, business_id, team_id)
        if entity is None:
            raise ValueError("业务单据不存在")

        first_node = db.query(ApprovalNode).filter(
            ApprovalNode.flow_id == flow.id, ApprovalNode.node_order == 1
        ).first()

        db_approval = Approval(
            business_type=business_type,
            business_id=business_id,
            contract_id=business_id if business_type == BusinessType.CONTRACT else None,
            flow_id=flow.id,
            team_id=team_id,
            current_node_id=first_node.id if first_node else None,
            status=ApprovalStatus.PENDING,
            submitter_id=submitter_id,
            submitter_name=submitter_name,
        )
        db.add(db_approval)
        db.flush()

        db.add(ApprovalRecord(
            approval_id=db_approval.id, node_id=first_node.id if first_node else None,
            approver_id=submitter_id, approver_name=submitter_name,
            action=ApprovalAction.SUBMIT, comment=None, team_id=team_id,
        ))
        adapter.on_submit(db, entity)
        db.commit()
        db.refresh(db_approval)
        return db_approval
```

(d) `approve`（:541-589）改：把末节点/驳回处的 `contract.status =` 直写替换为调 `get_adapter(approval.business_type).on_approved/on_rejected(db, entity)`，其中 `entity = adapter.get_entity(db, approval.business_id, approval.team_id)`。**E4：`entity` 为 None 时跳过状态回写**（适配器 on_* 内已守卫，approve 处无需重复判 None，但 `approval.status=APPROVED/REJECTED` 仍写——审批实例本身终结与单据状态回写解耦，单据已删则仅终结审批）。

(e) `cancel`（:593-609）改：`on_cancelled` 同上。

(f) 旧 `create_approval(db, contract, flow, submitter_id, submitter_name)` 改为：

```python
    def create_approval(self, db, contract, flow, submitter_id, submitter_name) -> Approval:
        return self.create_approval_generic(
            db, BusinessType.CONTRACT, contract.id, contract.team_id, flow, submitter_id, submitter_name)
```

(g) 新增 `get_by_entity(db, business_type, business_id, team_id)`：`db.query(Approval).filter(Approval.business_type==bt, Approval.business_id==bid, Approval.team_id==team_id).order_by(Approval.created_time.desc()).first()`。旧 `get_by_contract_id` 内部调 `get_by_entity(CONTRACT, contract_id, team_id)`。

- [ ] **Step 4: Run test to verify it passes + 合同回归**

Run: `cd CRM-Server && pytest tests/unit/test_approval_crud_generic.py tests/unit/test_contract_delete_approval.py -v`
Expected: PASS（新测试 + 现有合同回归全绿）

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/crud/approval.py CRM-Server/app/models/approval.py CRM-Server/migrations/versions/012_approval_generic_business.py CRM-Server/tests/unit/test_approval_crud_generic.py
git commit -m "refactor(approval): decouple crud from contract via adapter (generic business support)"
```

### Task A6: 通用审批 API 端点

**Files:**
- Create: `CRM-Server/app/schemas/approval_generic.py`
- Modify: `CRM-Server/app/api/approvals.py`（新增 `/v1/approvals/{entity_type}/{entity_id}/...` 端点）
- Test: `CRM-Server/tests/unit/test_approval_generic_api.py`

**Interfaces:**
- Produces:
  - `POST /v1/approvals/{entity_type}/{entity_id}/submit` — body `ApprovalSubmitRequest{comment}`
  - `POST /v1/approvals/{entity_type}/{entity_id}/approve` — body `ApprovalActionRequest{action, comment, updated_time}`
  - `POST /v1/approvals/{entity_type}/{entity_id}/cancel`
  - `GET  /v1/approvals/{entity_type}/{entity_id}/detail`
- 旧 `/v1/approvals/contracts/{contract_id}/...` 保留为 wrapper（调通用逻辑），不删除以保回归。
- **E6 批量审批端点**：新增 `POST /v1/approvals/bulk-approve` — body `{entity_type, ids:[], action, comment, updated_times?:{}}`。后端**逐条独立事务**：对每个 id 单独开 `db.begin()` → try `approval_crud.approve(...)` → commit；except 收集失败行 `{id, reason}`（乐观锁冲突单列 reason="已被他人处理"）。返回 `{success_count, failed:[{id,reason}]}`。不整体事务——避免一条失败全回滚让审批人白做（E6 拍板）。前端 E6/E8 配套。

- [ ] **Step 1: Write the failing test**

```python
# CRM-Server/tests/unit/test_approval_generic_api.py
def test_submit_invoice_approval(client, auth_headers_finance, seed_invoice_draft, seed_flow_invoice_with_node):
    r = client.post(f"/v1/approvals/INVOICE/{seed_invoice_draft.id}/submit",
                    headers=auth_headers_finance, json={"comment": "请审批"})
    assert r.status_code == 200
    assert r.json()["status"] == "PENDING"

def test_invalid_entity_type_rejected(client, auth_headers_finance):
    r = client.post("/v1/approvals/UNKNOWN/1/submit", headers=auth_headers_finance, json={"comment": ""})
    assert r.status_code in (400, 422)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd CRM-Server && pytest tests/unit/test_approval_generic_api.py -v`
Expected: FAIL — 路由不存在

- [ ] **Step 3: Create schema + endpoints**

```python
# CRM-Server/app/schemas/approval_generic.py
from pydantic import BaseModel, constr
from typing import Optional
from datetime import datetime

class ApprovalSubmitRequest(BaseModel):
    comment: Optional[str] = None

class ApprovalActionRequest(BaseModel):
    action: str  # APPROVE / REJECT
    comment: Optional[str] = None
    updated_time: Optional[datetime] = None
```

在 `app/api/approvals.py` 末尾加（路径校验 entity_type 用 `is_valid_business_type`）：

```python
from app.constants.business_types import is_valid_business_type, BusinessType
from app.services.approval_adapter import get_adapter

@router.post("/{entity_type}/{entity_id}/submit")
async def submit_generic_approval(entity_type: str, entity_id: int,
        payload: ApprovalSubmitRequest,
        db: Session = Depends(get_db), team_id: int = Depends(get_current_user_team),
        current_user = Depends(get_current_active_user)):
    if not is_valid_business_type(entity_type):
        raise HTTPException(400, f"无效的业务单据类型: {entity_type}")
    adapter = get_adapter(entity_type)
    entity = adapter.get_entity(db, entity_id, team_id)
    if entity is None:
        raise HTTPException(404, "业务单据不存在")
    flow, err = approval_crud.match_flow_generic(db, entity_type, team_id, **adapter.match_kwargs(entity))
    if flow is None:
        raise HTTPException(400, err or "未匹配到审批流程")
    submitter_id, submitter_name = adapter.get_submitter(entity)
    ap = approval_crud.create_approval_generic(db, entity_type, entity_id, team_id, flow, submitter_id, submitter_name)
    # 通知（泛化版，见 Task A8）
    return {"approval_id": ap.id, "status": ap.status}

@router.post("/{entity_type}/{entity_id}/approve")
async def approve_generic_approval(...): ...

@router.post("/{entity_type}/{entity_id}/cancel")
async def cancel_generic_approval(...): ...

@router.get("/{entity_type}/{entity_id}/detail")
async def detail_generic_approval(...): ...
```

> 具体 import/依赖对齐现有 `submit_contract_approval`（:416）的写法。`approve` 内复用现有节点角色校验逻辑（:611-619），但 approval 经 `get_by_entity` 取。`cancel` 校验 `submitter_id == current_user.user_id`。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd CRM-Server && pytest tests/unit/test_approval_generic_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/schemas/approval_generic.py CRM-Server/app/api/approvals.py CRM-Server/tests/unit/test_approval_generic_api.py
git commit -m "feat(approval): add generic /v1/approvals/{entity_type}/{entity_id} endpoints"
```

### Task A7: 权限码 + 角色映射

**Files:**
- Modify: `CRM-Server/app/constants/permissions.py`（ALL_PERMISSIONS、ROLE_PERMISSIONS_MAPPING）
- Modify: `CRM-Docs/system/GLOSSARY.md`
- Test: `CRM-Server/tests/unit/test_permissions_payment_invoice_approval.py`

**Interfaces:**
- Produces: 新权限码 `payment:submit`、`payment:withdraw`、`payment:approve`、`payment:approve:own`、`payment:approve:all`、`invoice:approve:own`、`invoice:approve:all`。FINANCE 角色增 `payment:approve`、`payment:submit`；SALES_DIRECTOR 增 `payment:approve:own`、`invoice:approve:own`（可选，共识审自己提交）。重启服务自动 insert。

- [ ] **Step 1: Write the failing test**

```python
# CRM-Server/tests/unit/test_permissions_payment_invoice_approval.py
from app.constants.permissions import ALL_PERMISSIONS, ROLE_PERMISSIONS_MAPPING

def test_payment_approve_codes_exist():
    codes = {p["code"] for p in ALL_PERMISSIONS}
    assert "payment:submit" in codes
    assert "payment:approve" in codes
    assert "payment:approve:own" in codes
    assert "payment:approve:all" in codes

def test_invoice_approve_own_all_exist():
    codes = {p["code"] for p in ALL_PERMISSIONS}
    assert "invoice:approve:own" in codes
    assert "invoice:approve:all" in codes

def test_finance_has_payment_approve():
    finance_perms = ROLE_PERMISSIONS_MAPPING["FINANCE"]
    assert "payment:approve" in finance_perms or "payment:approve:all" in finance_perms
    assert "payment:submit" in finance_perms
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd CRM-Server && pytest tests/unit/test_permissions_payment_invoice_approval.py -v`
Expected: FAIL

- [ ] **Step 3: Add codes**

在 `constants/permissions.py` 的 payment 段（补充段 :154-156）加入：

```python
    {"name": "提交回款审批", "code": "payment:submit", "resource": "payment", "action": "submit"},
    {"name": "撤回回款审批", "code": "payment:withdraw", "resource": "payment", "action": "withdraw"},
    {"name": "审批回款", "code": "payment:approve", "resource": "payment", "action": "approve"},
    {"name": "审批自己的回款", "code": "payment:approve:own", "resource": "payment", "action": "approve", "scope": "own"},
    {"name": "审批所有回款", "code": "payment:approve:all", "resource": "payment", "action": "approve", "scope": "all"},
```

invoice 段（:142-151）把 flat `invoice:approve` 保留，并新增 own/all（不删旧码以免破坏现有调用）：

```python
    {"name": "审批自己的发票", "code": "invoice:approve:own", "resource": "invoice", "action": "approve", "scope": "own"},
    {"name": "审批所有发票", "code": "invoice:approve:all", "resource": "invoice", "action": "approve", "scope": "all"},
```

`ROLE_PERMISSIONS_MAPPING`：
- `FINANCE`（:219-229）追加 `"payment:submit", "payment:approve", "invoice:submit", "invoice:withdraw"`
- `SALES_DIRECTOR`（:175-198）追加 `contract:approve:own` 已有；按需追加 `"payment:approve:own"`（审自己提交的回款）、`"invoice:approve:own"`

`GLOSSARY.md` 1.6 回款权限段（:92-103）追加新码行；1.5 发票段追加 own/all。

- [ ] **Step 4: Run test + 同步验证**

Run: `cd CRM-Server && pytest tests/unit/test_permissions_payment_invoice_approval.py -v && ruff check app/constants/permissions.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/constants/permissions.py CRM-Docs/system/GLOSSARY.md CRM-Server/tests/unit/test_permissions_payment_invoice_approval.py
git commit -m "feat(permission): add payment/invoice approval permission codes and role mappings"
```

### Task A8: 通知模板泛化

**Files:**
- Modify: `CRM-Server/app/services/notification.py`（:48/116/173/234/292/364）、`app/services/feishu_service.py`（对应方法）
- Test: `CRM-Server/tests/unit/test_notification_generic.py`

**Interfaces:**
- Produces: `notify_approval_pending(entity_type, entity_name, flow_name, node_name, approver_open_id, approver_name, business_id)`（`contract_name/contract_id` 旧参数保留为 alias，内部转新签名）。其他通知方法同步。

- [ ] **Step 1: Write the failing test**

```python
# CRM-Server/tests/unit/test_notification_generic.py
def test_notify_pending_uses_entity_name(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.services.notification.feishu_service.notify_approval_pending",
                        lambda **kw: captured.update(kw))
    from app.services.notification import notify_approval_pending
    notify_approval_pending(entity_type="INVOICE", entity_name="发票申请#1",
                            flow_name="F", node_name="N", approver_open_id="o", approver_name="x", business_id=1)
    assert captured.get("entity_name") == "发票申请#1"
    assert captured.get("business_id") == 1
```

- [ ] **Step 2: Run to verify fail**, then **Step 3: refactor** 三个通知方法签名：把 `contract_name` 参数名改 `entity_name`、`contract_id` 改 `business_id`，加 `entity_type` 可选参数；`feishu_service` 对应方法同步。调用方（`api/approvals.py:471,491,524,538,550,659,695,716,732`）传 `entity_type=approval.business_type, entity_name=adapter.get_name(entity), business_id=approval.business_id`。

- [ ] **Step 4: Run tests** `pytest tests/unit/test_notification_generic.py tests/unit/test_approval_generic_api.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/notification.py CRM-Server/app/services/feishu_service.py CRM-Server/app/api/approvals.py CRM-Server/tests/unit/test_notification_generic.py
git commit -m "refactor(notification): generalize approval notifications to entity_type/business_id"
```

---

## Phase B — 回款/发票接入引擎

### Task B1: 回款审批 API 端点（payments 路由）

**Files:**
- Modify: `CRM-Server/app/api/payments.py`
- Test: `CRM-Server/tests/unit/test_payment_approval_api.py`

**Interfaces:**
- Produces: `POST /v1/payments/records/{record_id}/submit-approval`（提回款审批）、`POST /v1/payments/records/{record_id}/confirm`（非审批路径补齐 + 兼容）。其实通用端点 `/v1/approvals/PAYMENT/{id}/submit` 已可覆盖；本端点作为业务语义 sugar + `payment:submit` 权限校验入口。

- [ ] **Step 1: Write failing test** — submit-approval 触发后 `PaymentRecord.confirmation_status` 仍 PENDING，审批通过后置 CONFIRMED（走通用 approve 端点）。
- [ ] **Step 2: Run to fail.**
- [ ] **Step 3: Implement** — `submit-approval` 内部调 `approval_crud.create_approval_generic(PAYMENT, ...)` + 权限 `Depends(require_permission("payment:submit"))`。`/confirm` 端点保留为非审批财务直确认（用权限 `payment:confirm`，调 `payment_record_crud.confirm_payment`），覆盖文档缺失的 API。
- [ ] **Step 4: Run tests** → PASS + 回归 `tests/unit/test_payment_*`。
- [ ] **Step 5: Commit** — `feat(payment): add payment approval & confirm endpoints`

### Task B2: 发票审批迁移到引擎（硬废弃 /review + 在途数据平迁）

**Files:**
- Modify: `CRM-Server/app/api/invoices.py:234-313`（删除 `/review` 端点）、`app/crud/invoice.py:257-311`（删除 `review` 方法、改 `mark_issued` 判定源）
- Create: 在 012 迁移（Task A3）中追加发票在途数据平迁 SQL，或新建 013 迁移 `013_invoice_approval_data_migration.py`
- Test: `CRM-Server/tests/unit/test_invoice_approval_engine_migration.py`

**Interfaces:**
- Produces: 删除 `POST /{id}/review` 端点与 `InvoiceApplicationCRUD.review`（硬废弃，见决策 2a）；发票 submit 改为调通用审批 submit（`/v1/approvals/INVOICE/{id}/submit` 内部复用）；`mark_issued`（`crud/invoice.py:305`）的 `status==APPROVED` 判定改为查 `approval_crud.get_by_entity(INVOICE, id, team).status == APPROVED`；在途数据平迁 SQL。

- [ ] **Step 1: Write failing test**
```python
# CRM-Server/tests/unit/test_invoice_approval_engine_migration.py
def test_invoice_via_engine_becomes_approved(db_session, seed_invoice_draft, seed_flow_invoice):
    # 通用 submit → approve 后发票 APPROVED，reviewer 快照已回写
    ap = approval_crud.create_approval_generic(db_session, BusinessType.INVOICE,
        seed_invoice_draft.id, seed_invoice_draft.team_id, seed_flow_invoice, "u1", "eddie")
    approval_crud.approve(db_session, ap, ApprovalActionRequest(action="APPROVE", comment="ok"), "u2", "fin")
    db_session.refresh(seed_invoice_draft)
    assert seed_invoice_draft.status == "APPROVED"
    # mark_issued 现在能执行（依赖引擎 APPROVED）
    invoice_application_crud.mark_issued(db_session, seed_invoice_draft.id, team_id=seed_invoice_draft.team_id)
    assert seed_invoice_draft.status == "ISSUED"

def test_legacy_review_endpoint_removed(client, auth_headers_finance, seed_invoice_pending_review):
    r = client.post(f"/v1/invoices/{seed_invoice_pending_review.id}/review",
                    headers=auth_headers_finance, json={"action": "APPROVE", "comment": ""})
    assert r.status_code == 404  # 硬废弃
```

- [ ] **Step 2: Run to fail**（review 端点仍存在 → 测试期望 404 失败）。

- [ ] **Step 3: Implement**
  - 删除 `api/invoices.py:259-285` 的 `review` 端点；删除 `crud/invoice.py:270-298` 的 `review` 方法。
  - `invoice_application_crud.submit`（:257-268）保留但由通用端点 `submit_generic_approval` 调用（适配器 `on_submit` 已置 PENDING_REVIEW）。
  - `mark_issued`（:300-311）判定源改为查关联 Approval：
    ```python
    approval = approval_crud.get_by_entity(db, BusinessType.INVOICE, application_id, team_id)
    if not approval or approval.status != ApprovalStatus.APPROVED:
        raise ValueError("发票未通过审批，不可开票")
    ```
  - **reviewer 写法（Pre-Flight D3 统一为"端点回写"）**：适配器 `on_approved/on_rejected` 保持两参 `(db, entity)` 纯净，只切 `InvoiceApplication.status` 与 `reviewed_time`（Task A4 已实现）。`reviewer_id/review_comment` 由 Task A6 的通用 `approve_generic_approval` 端点在审批后直接写发票表：`entity.reviewer_id = approver_id; entity.review_comment = action_request.comment`。职责清晰——适配器管单据状态机，端点管审计信息，无扩参污染 Protocol。
  - 在途数据平迁 SQL（并入 012 或新建 013）：
  > **E7 平迁测试**：补 `tests/unit/test_invoice_data_migration.py`——seed 旧 APPROVED×2 / PENDING_REVIEW×1 / ISSUED×1 / REJECTED×1 发票，跑迁移后断言：补建 Approval 行数==2 且 status=APPROVED/business_type=INVOICE/business_id 对应；PENDING_REVIEW 那条回退 DRAFT；ISSUED/REJECTED 不动。
    ```sql
    -- APPROVED 旧发票补建 Approval + ApprovalRecord
    INSERT INTO crm_contract_approvals (team_id, business_type, business_id, flow_id, status, submitter_id, created_time, updated_time)
      SELECT team_id, 'INVOICE', id, NULL, 'APPROVED', applicant_id, created_time, last_modified_time
      FROM crm_invoice_applications WHERE status='APPROVED';
    -- （对应 ApprovalRecord 补建一条 APPROVE 记录，approver_id 取 reviewer_id）
    INSERT INTO crm_contract_approval_records (team_id, approval_id, node_id, approver_id, action, created_time)
      SELECT a.team_id, ap.id, NULL, a.reviewer_id, 'APPROVE', a.reviewed_time
      FROM crm_invoice_applications a JOIN crm_contract_approvals ap
        ON ap.business_type='INVOICE' AND ap.business_id=a.id
      WHERE a.status='APPROVED' AND a.reviewer_id IS NOT NULL;
    -- PENDING_REVIEW 旧记录回退 DRAFT，由申请人重新经引擎提交
    UPDATE crm_invoice_applications SET status='DRAFT', reviewer_id=NULL, review_comment=NULL, reviewed_time=NULL
      WHERE status='PENDING_REVIEW';
    ```
    > `flow_id` 留 NULL（历史数据无对应模板）是可接受的——只作审计快照，不再驱动状态机。

- [ ] **Step 4: Run tests** `pytest tests/unit/test_invoice_approval_engine_migration.py tests/unit/test_invoice_* -v` → PASS + 现有 invoice 回归（submit/withdraw/mark_issued 更新）。

- [ ] **Step 5: Commit**
```bash
git add CRM-Server/app/api/invoices.py CRM-Server/app/crud/invoice.py CRM-Server/migrations/ CRM-Server/tests/unit/test_invoice_approval_engine_migration.py
git commit -m "refactor(invoice): hard-deprecate /review, migrate approval to engine with data backfill"
```

### Task B3: 流程模板 business_type 支持（AI 解析器）

**Files:**
- Modify: `CRM-Server/app/services/approval_ai_parser.py`、`app/schemas/approval_ai.py`、`app/api/approval_ai.py`
- Modify: 前端 `approvalFlow` 模板表单加 business_type 选择
- Test: `CRM-Server/tests/unit/test_approval_ai_parser_business_type.py`

**Interfaces:**
- Produces: `ApprovalAIParsedFlow` 加 `business_type` 字段；AI system prompt 增加单据类型识别（用户说"回款审批"/"发票审批"→ PAYMENT/INVOICE）。`ApprovalFlow.business_type` 在 Task A5 已加。

- [ ] **Step 1-5**: TDD 循环（解析输入"金额超 5 万的回款需财务审批"→ 输出 `business_type=PAYMENT`）→ 实现 → 测试 → commit `feat(approval-ai): support business_type in flow parsing`。

---

## Phase C — 前端通用化与审批页落地

### Phase C 前端设计规范（设计审核产出，C1–C3 共同遵守）

> 本节由 `/plan-design-review` + `frontend-design` 产出，锁定 Phase C 的设计决策。设计基线来自 `CRM-Client/src/styles/variables.scss`（`$wolf-*` token）与 Element Plus 组件库——**不发明新配色/新字体**，一切引用现有 token。

**主题/受众/页面职责**：内部财务+销售审批工作流；受众 = FINANCE / SALES_DIRECTOR / TEAM_ADMIN（审批人）与 SALES_MEMBER（提交人）；页面职责 = 看到待办、做出决定、留下可审计痕迹。这是 B2B 内部工具，**没有营销 hero**，签名元素是**统一的审批状态语言**。

#### C-DSG-1 审批状态语义 Token + 状态徽章动画（签名元素）

**现状问题**（设计债）：3 个现有组件对 PENDING/APPROVED/REJECTED 各自映射——`ApprovalTimeline.vue` 用 success/primary/info，`ApprovalProgressCompact.vue` 用 warning/success/danger/info，`FinanceInvoiceApprovals.vue` 又是另一套 `statusMap`。同一审批状态在不同界面颜色不同，违背"可调试的品味"原则（不一致可追溯到缺规范状态语言）。

**方案**：在 `variables.scss` 追加审批状态语义层（映射到现有功能色，不新增色相），全 Phase C 组件**唯一引用源**：

```scss
// ==================== 审批状态语义色（Phase C 新增，唯一规范）====================
$wolf-approval-pending-text:   $wolf-warning-text;   // #7A4F1E 待审批/审批中：需关注，琥珀
$wolf-approval-pending-bg:     $wolf-warning-bg;     // #FFF6E8
$wolf-approval-approved-text:  $wolf-success-text;   // #2B633C 已通过：成功绿
$wolf-approval-approved-bg:    $wolf-success-bg;     // #EDF7EF
$wolf-approval-rejected-text:  $wolf-danger-text;    // #7A2828 已驳回：危险红
$wolf-approval-rejected-bg:    $wolf-danger-bg;      // #FCECEC
$wolf-approval-cancelled-text: $wolf-text-tertiary;  // #636363 已撤回：中性灰，终态但不强警示
$wolf-approval-cancelled-bg:   $wolf-bg-hover;       // #F5F5F5
```

并新建 **`ApprovalStatusBadge.vue`**（唯一状态徽章组件）：props `status: 'PENDING'|'APPROVED'|'REJECTED'|'CANCELLED'`，渲染 `el-tag` + 图标（Clock/CircleCheckFilled/CircleCloseFilled/Minus）+ 中文文案，颜色取上述 token。**取代**散落的三处 `statusMap/getStatusType`。Task C2、C3 所有状态展示统一用此组件。同时追加 `:root` CSS 变量映射层（对齐现有 `--wolf-*` 模式）供非 SCSS 场景。

**签名元素视觉强化（frontend-design 审查新增）**：

ApprovalStatusBadge 增加状态语义动画（**动画有目的，不是装饰**）：
- **PENDING**：琥珀色 + 微妙的呼吸动画（pulse，2s infinite，强调"需关注"）
  - 动画意图："等待你处理"，引导审批人注意到待处理项
  - CSS：`animation: pulse-warning 2s ease-in-out infinite;`
  
- **APPROVED**：绿色 + 短暂的成功动画（scale + fade，300ms once，强调"已完成")
  - 动画意图："闭环确认"，成功反馈
  - CSS：`animation: success-pop 300ms ease-out;`（仅在状态变更时触发，非持续）
  
- **REJECTED**：红色 + 静态（强调"需修改"，不动画避免焦虑）
  
- **CANCELLED**：灰色 + 较小字号（font-size: 12px，强调"中性终态"，降低视觉权重）

**prefers-reduced-motion 降级**：
- 系统偏好 `prefers-reduced-motion: reduce` 时，所有动画禁用（`animation: none;`）
- 状态徽章仅靠颜色 + 图标区分（符合无障碍规范）

> 这是 frontend-design 技能"在一点上投入大胆，其余保持克制"的应用：签名元素 = 统一状态语言 + 状态语义动画；其余全部复用现有 token 与组件，不添新色。动画服务于状态语义，不是装饰。

#### C-DSG-2 排版与材质

- 字体：用现有 scale（title16/body14/auxiliary13/caption12），**IBM Plex Mono**（项目既有 signature）用于申请单号/审批单号/回款单号等 ID 展示（`invoice_amount`/`application_number`），强化"技术 vernacular"。不引入新字体。
- 字重：normal400/medium500/semibold600，禁 700+。
- 圆角：卡片 `md8`，徽章 `sm4`，按钮用 `$wolf-radius-button`。
- 材质：`el-card` 白底（`$wolf-bg-card`）置于 `page` 暖灰底（`$wolf-bg-page`），"用色彩分层替代分割线"。

#### C-DSG-3 文案规范（接口口吻，主动语态，动作名贯穿全流程）

| 场景 | 文案 | 出现处 |
|------|------|--------|
| 提交按钮 | "提交审批" | 提交人侧 |
| 提交成功 toast | "已提交审批，等待审批人处理" | ElMessage.success |
| 同意按钮 | "同意" | 审批人侧 |
| 同意成功 toast | "已同意" | ElMessage.success |
| 驳回按钮 | "驳回" | 审批人侧 |
| 驳回成功 toast | "已驳回，申请人可修改后重新提交" | ElMessage.success |
| 撤回按钮 | "撤回审批" | 提交人侧 |
| 撤回确认 | "撤回后审批中止，需重新提交。确定撤回？" | ElMessageBox.confirm type=warning |
| 撤回成功 toast | "已撤回" | ElMessage.success |
| 乐观锁冲突 | "该审批已被其他人处理，已为你刷新最新状态" | ElMessage.warning + 自动重载 detail |
| 加载失败 | "审批信息加载失败" + "重新加载" 按钮 | 内联 ErrorState |

**原则**：动作名贯穿——"同意"按钮 → "已同意" toast（不出现"审批通过成功"等变体）。错误不道歉、不模糊。空状态是行动邀请，不是"暂无数据"。

#### C-DSG-4 交互状态全覆盖（现有方案最大缺口）

每个审批界面必须覆盖 5 态：

| 状态 | 实现 | 文案 |
|------|------|------|
| **Loading** | `v-loading` 指令包裹卡片；详情区用骨架（`el-skeleton` 3 行）避免空白闪烁 | — |
| **Empty**（无待审批/无审批单） | 复用 `WolfEmpty.vue`（已有，props title+description + `#action` 插槽） | title「暂无待审批事项」+ desc「所有回款与发票申请都已处理完毕」+ action「查看已处理记录」 |
| **Error**（加载/提交失败） | **新建 `ErrorState.vue`**（项目当前无统一错误态组件）：props `title` + `description` + `#action` 插槽，danger 文字色 | title「审批信息加载失败」+ action「重新加载」 |
| **Success** | `ElMessage.success`（已有） | 见 C-DSG-3 |
| **并发冲突**（乐观锁，审批独有） | `updated_time` 不匹配 → warning toast + 自动 `getApprovalDetail` 重载 | 见 C-DSG-3 |

#### C-DSG-5 组件构成与线框（ASCII，文本线框）

**ApprovalProcessGeneric.vue**（嵌入详情页的审批区，通用化 ApprovalProcess.vue）：

```
┌─ 审批进度 ────────────── [待处理●] ─┐   ← header: 标题 + ApprovalStatusBadge（呼吸动画）
│  ① 销售提交   ② 财务审批   ③ 总监审批 │   ← ApprovalTimeline 水平（宽屏）
│  ✓ eddie 06/28   ● 当前     ○ 待处理  │      窄屏降级 ApprovalProgressCompact 垂直
│  ─────────────────────────────────── │
│  节点意见：请尽快审批                 │   ← 当前节点意见（comment）
│                                       │
│  [  撤回审批  ]        [  驳回  ][  同意  ] │   ← 按角色显隐：提交人见撤回，审批人见同意/驳回
└───────────────────────────────────────┘
```

- Props：`entityType: 'CONTRACT'|'PAYMENT'|'INVOICE'`、`entityId: number`、`canApprove: boolean`、`isSubmitter: boolean`（控制按钮显隐）。
- 内部不直接调 API（遵守 COMPONENTS.md「组件禁直接调 API」），通过 `useApprovalStore()` actions。
- 宽屏 `>1024px` 用水平 timeline，`≤1024px` 自动切 `ApprovalProgressCompact` 垂直（响应式）。
- 无审批单时（草稿态，未提交）显示 `WolfEmpty`：title「尚未提交审批」+ action「提交审批」按钮（`v-permission="payment:submit|invoice:submit"`）。

**ApprovalCenter.vue**（审批中心路由后的统一入口，取代自写按钮的 FinanceInvoiceApprovals/FinancePaymentConfirmations）：

> ⚠️ **审批入口优化（2026-07-03）**：
> 根据「审批入口优化 plan（方案 A）」，审批入口改为 **Header Icon + Badge** 作为唯一轻量入口，
> 左侧菜单移除「财务审批」入口，路由改为 `/approvals`（不是 `/finance/approvals`）。
> 详见：`.claude/plans/jolly-frolicking-shell.md`

```
┌─ 审批中心 ───────────────────────────────────────┐
│ [ 待处理 ③ ] [ 已完成 ] [ 我发起的 ]                │   ← el-tabs，动词导向命名，徽章显示待办数
│ ┌筛选──────────────────────────────────────────────┐ │
│ │ 类型[全部▼] 客户[搜索___] 金额[___]~[___] 提交日期[___] │ │   ← el-form inline，完整筛选能力
│ │                    [ 高级筛选 ▼ ]                  │ │   ← 渐进式披露，高级筛选含超时状态/审批节点
│ └───────────────────────────────────────────────────┘ │
│ ┌table──────────────────────────────────────────────┐ │
│ │ 单号(mono)  类型 客户(bold) 金额(primary) 提交人 状态(signature) 操作 │ │ ← 视觉分层标注
│ │ INV-0231    发票 XX公司      ¥58,000    eddie  [待处理●pulse] [同意][驳回][详情] │ │
│ │ PAY-0042    回款 YY公司      ¥120,000   fin   [待处理●pulse] │ │ ← 快速审批：hover显示按钮
│ │ ...                                                 │ │ ← 超时徽章在状态旁
│ └───────────────────────────────────────────────────┘ │
│ 共 12 条                              < 1 2 3 >       │   ← el-pagination
└───────────────────────────────────────────────────────┘
```

**表格视觉分层设计（frontend-design 审查新增）**：

- **主列**（一眼看到，审批人关注）：
  - **类型**：字号 16px，颜色 `$wolf-text-primary`
  - **客户**：字号 16px，颜色 `$wolf-text-primary`，font-weight: 500，限制宽度（ellipsis + tooltip）
  - **金额**：字号 18px（突出），颜色 `$wolf-primary`（蓝色），font-weight: 600
  - **状态**：ApprovalStatusBadge（签名元素，呼吸动画）

- **次列**（需要细看）：
  - **单号**：字号 14px mono，颜色 `$wolf-text-tertiary`（技术 vernacular）
  - **提交人**：字号 14px，颜色 `$wolf-text-secondary`
  - **提交日期**：字号 14px，颜色 `$wolf-text-secondary`

- **操作列**：
  - 固定右侧，hover 显示快速审批按钮（淡入动画，150ms）
  - 快速审批按钮：小尺寸（`el-button size="small"`），同意 `$wolf-success`，驳回 `$wolf-danger`
  - 详情按钮：标准尺寸，文字"详情"

**抽屉三段视觉设计（frontend-design 审查新增）**：

```
┌─ 审批详情 ──────────────────────────────┐
│ ┌决策字段───────────────────────────┐   │ ← 背景色 `$wolf-bg-hover`（浅灰，区隔）
│ │ 开票金额：¥58,000 (蓝色/18px/600) │   │ ← 金额突出（审批人核心关注）
│ │ 抬头：XX公司科技发票抬头           │   │
│ │ 关联合同：CON-2026-001            │   │
│ └────────────────────────────────────┘   │
│                                          │
│ ┌Timeline───────────────────────────┐   │ ← 无背景色，融入抽屉
│ │ ① 销售提交 ✓ eddie 06/28          │   │
│ │ ② 财务审批 ● 当前                 │   │
│ │ ③ 总监审批 ○                      │   │
│ └────────────────────────────────────┘   │
│ ────────────────────────(分割线)──────   │ ← 分割线区隔操作区
│ [ 撤回 ]              [ 驳回 ][ 同意 ]   │ ← 吸底 + 背景色 `$wolf-bg-card`（白色）
└──────────────────────────────────────────┘
```

- **①决策字段**：`el-descriptions` + 背景色 `$wolf-bg-hover`，金额字号 18px + 蓝色
- **②timeline**：无背景色，融入抽屉主体
- **③操作区**：吸底 + 分割线 + 白色背景 `$wolf-bg-card`，强调"可操作"

**筛选区视觉设计（frontend-design 审查新增）**：

- 基础筛选：inline form + 浅灰背景 `$wolf-bg-hover`
- 高级筛选：`el-collapse` 折叠面板 + 点击展开
- 筛选条件激活指示：筛选区上方显示小徽章（如 "类型: 回款 | 金额: 10万+"）
- 清除筛选：徽章右侧"清除"按钮（X 图标）

**移动端卡片式列表（frontend-design 审查新增）**：

```
┌─ 卡片 ─────────────────────────────┐
│ INV-0231 (mono)        [待处理●]     │ ← 单号 + 状态徽章
│ XX公司   ¥58,000                   │ ← 客户 + 金额（18px/蓝色）
│ eddie 提交 2小时前                  │ ← 提交人 + 时间（次要）
│ ────────────────────────────────  │ ← 分割线
│ [同意] [驳回] [详情]               │ ← 按钮全宽
└───────────────────────────────────┘
```

- 卡片间距：`margin-bottom: $wolf-space-md`（16px）
- 金额突出：字号 18px + `$wolf-primary`
- 按钮排列：同意/驳回左右分布（`display: flex; justify-content: space-between`），详情右上角图标

**空态邀请性设计（frontend-design 审查新增）**：

```
┌─ 空态 ─────────────────────────────┐
│      [Clock 图标 96px 浅灰]        │ ← 大图标，微妙的摇摆动画（invitation）
│                                    │
│  暂无待审批事项                     │ ← 字号 16px
│  所有回款与发票申请都已处理完毕      │ ← 描述（字号 14px）
│                                    │
│  [ 查看已处理记录 ]                 │ ← 行动按钮（invitation to act）
└───────────────────────────────────┘
```

- 图标：Clock 96px + `$wolf-text-tertiary` + 微妙摇摆动画（3s ease-in-out infinite）
- 文案："暂无待审批事项" + "所有回款与发票申请都已处理完毕"
- 行动按钮："查看已处理记录"（`$wolf-primary`）
- prefers-reduced-motion 时禁用摇摆动画

> frontend-design 原则："An empty screen is an invitation to act." 空态不是"暂无数据"，而是邀请用户行动。

- 三个 tab 由权限驱动，动词导向命名：`待处理`（`v-any-permission` 含审批权限，Badge 显示待办数）、`已完成`、`我发起的`。
- 筛选保留完整能力：类型（business_type）+ 客户 + 金额范围 + 提交日期 + 高级筛选（超时状态/审批节点）。
- 详情用 **el-drawer 右抽屉**（非整页跳转），审批完留在列表上下文，减少跳转摩擦。
- 快速审批：列表行内"同意"、"驳回"按钮（hover 显示），高频审批不强制打开抽屉。
└───────────────────────────────────────────────────────┘
   行「详情」→ 右侧 el-drawer 抽屉：实体摘要(el-descriptions) + ApprovalProcessGeneric
```

- 三个 tab 由权限驱动，动词导向命名：`待处理`（`v-any-permission` 含审批权限，Badge 显示待办数）、`已完成`、`我发起的`。
- 筛选保留完整能力：类型（business_type）+ 客户 + 金额范围 + 提交日期 + 高级筛选（超时状态/审批节点）。
- 详情用 **el-drawer 右抽屉**（非整页跳转），审批完留在列表上下文，减少跳转摩擦。
- 快速审批：列表行内"同意"、"驳回"按钮（hover 显示），高频审批不强制打开抽屉。

#### C-DSG-6 响应式与无障碍 + 动画设计

**响应式**：
- `≥1024px`：表格列全显 + 水平 timeline + 抽屉宽度 480px。
- `768–1024px`：表格隐藏"提交人/日期"次要列，timeline 切垂直，抽屉 380px。
- `<768px`：表格降级为卡片列表（每条一卡片，单号+金额+状态+操作），审批按钮全宽，抽屉全屏。
- 触控目标 ≥44px（项目 token 已有，按钮高度对齐 `$wolf-height-button`）。

**无障碍**：
- `ApprovalStatusBadge` 加 `role="status"` + `aria-label`（"待审批"/"已通过"），颜色非唯一指示（必有图标+文字）。
- 审批按钮 `type="button"`，`v-permission` 隐藏时确保 Tab 顺序连贯（指令 removeChild 后不留 focus 陷阱）。
- 驳回弹窗 `ElMessageBox` 已内置焦点陷阱；确保 ESC 可取消。
- 表格行支持键盘上下导航（el-table 原生），"详情"操作可回车触发。
- `prefers-reduced-motion`：timeline 连接线无动画，ElMessage 不滑动，ApprovalStatusBadge 状态动画禁用（项目已遵循）。

**动画设计规范（frontend-design 审查新增）**：

> frontend-design 原则："Leverage motion deliberately. An orchestrated moment usually lands harder than scattered effects."
> 动画服务于状态语义和交互反馈，不是装饰。

**动画清单**：

| 动画 | 触发时机 | 持续时间 | 目的 | CSS |
|------|---------|---------|------|-----|
| **PENDING 呼吸** | 状态徽章显示时 | 2s infinite | "等待你处理"，引导注意 | `animation: pulse-warning 2s ease-in-out infinite;` |
| **APPROVED 成功弹** | 状态变更为 APPROVED 时 | 300ms once | "闭环确认"，成功反馈 | `animation: success-pop 300ms ease-out;` |
| **快速审批按钮淡入** | 行 hover 时 | 150ms | 揭示操作，不打断阅读 | `opacity: 0 → 1, transition: opacity 150ms;` |
| **行移除过渡** | 审批成功后行移除时 | 200ms | 平滑过渡，避免跳动 | `opacity: 1 → 0 + transform: translateX(-10px);` |
| **抽屉开/关** | 抽屉打开/关闭时 | 300ms | 空间连续性（shared element） | Element Plus 默认 |
| **空态图标摇摆** | 空态显示时 | 3s infinite | "等待"，invitation to act | `animation: clock-swing 3s ease-in-out infinite;` |
| **筛选折叠展开** | 高级筛选展开时 | 200ms | 渐进式披露 | `el-collapse` 默认 |

**prefers-reduced-motion 降级**：
- 所有无限循环动画（PENDING 呼吸、空态摇摆）禁用（`animation: none;`）
- 状态变更动画（APPROVED 成功弹）保留（300ms 短暂，不会引起焦虑）
- 过渡动画（淡入、移除、折叠）保留（200ms，符合 WCAG 动画阈值）

**CSS animation 定义示例**：

```scss
// PENDING 呼吸动画（琥珀色徽章）
@keyframes pulse-warning {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.85; }
}

// APPROVED 成功弹动画
@keyframes success-pop {
  0% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.05); }
  100% { transform: scale(1); opacity: 1; }
}

// 空态图标摇摆动画
@keyframes clock-swing {
  0%, 100% { transform: rotate(0deg); }
  25% { transform: rotate(-5deg); }
  75% { transform: rotate(5deg); }
}

// prefers-reduced-motion 降级
@media (prefers-reduced-motion: reduce) {
  .approval-badge-pending,
  .empty-clock-icon {
    animation: none;
  }
}
```

**动画原则**：
- ✅ **有目的**：每个动画都表达状态语义或交互反馈
- ✅ **短暂**：微交互 150-300ms，符合 UI/UX Pro Max §7
- ✅ **克制**：签名元素（PENDING 呼吸）是唯一持续动画
- ✅ **降级**：prefers-reduced-motion 时禁用持续动画

#### C-DSG-7 高频审批交互（ui-ux-pro-max 交互审查产出，18 条全纳入）

> 本节由交互审查补入，锁定审批人真实工作流的交互效率。每条标注落地 Task。
> 2026-07-03 更新：新增快速审批模式、筛选增强、移动端优化、Tab 命名优化。

**P0 必补（不补会回归/旅程断裂）**

1. **批量审批保留**（→Task C3）：`ApprovalCenter` 表格保留 `el-table-column type="selection"`，表头工具栏对选中行提供"批量同意 / 批量拒绝"（仅对当前用户可作为当前节点审批人的选中行启用，其余禁用并 tooltip 说明）。批量拒绝走统一"驳回理由"弹窗，理由对全部选中行应用。**不得因抽屉化单条审批而丢失现有 `FinanceInvoiceApprovals.vue:43` 的批量能力**。
2. **驳回强制理由 / 同意可选（对称破缺）**（→Task C2）：`ApprovalProcessGeneric` 的驳回弹窗 `rejectForm.reason` 必填 + `el-form` rule；同意 `comment` 可空。沿用现有 `ApprovalTimeline.vue:122` 约定。文案 C-DSG-3 追加驳回弹窗提示："请填写驳回理由，提交人将据此修改"。
3. **防双击/重复提交**（→Task C2/C3）：同意/驳回/撤回/批量审批按钮在 store action pending 期间 `:loading` + `:disabled`；驳回表单 `submit` 期间禁重复提交。后端乐观锁（`crud/approval.py:544`）是最后一道防线，前端按钮态是第一道。
4. **驳回→修改→重新提交回流**（→Task C3）：`ApprovalCenter` "我发起的" tab 对 REJECTED 行显示"修改并重新提交"按钮（先调实体 `update` 回 DRAFT，再 `submitApproval`）；抽屉 REJECTED 态同样提供此入口。用户旅程闭环：提交→驳回→改→重提，不补旅程断在 REJECTED。

**P1 应补（高频交互增强）**

5. **快速审批模式（新增，→Task C3）**：列表行内右侧增加"同意"、"驳回"按钮（hover 显示，无抽屉）：
   - 点击"同意"：ElMessageBox.confirm("确定同意该审批？") → 确认后直接提交 + toast "已同意" + 行从列表实时移除（动画过渡）
   - 点击"驳回"：弹窗输入理由 + 提交后行从列表移除
   - 仅对当前用户可作为当前节点审批人的行显示
   - 详情审批（打开抽屉）作为补充入口，高频审批不强制打开抽屉
   - 符合 §2 hover-vs-tap：Click/tap 作为主要交互，不需要打开抽屉也能审批

6. **超时/SLA 指示**（→Task C3）：复用后端 `GET /v1/approvals`（返回 `overdue_hours`）。待审批行对 `overdue_hours >= 48` 显示琥珀徽章"超时 N 小时"（用 `$wolf-warning-*` token，图标 Clock）；"待处理" tab 默认按 `overdue_hours` 降序排（积压最久顶）。**催办功能暂不实施**。

7. **审批入口对齐（更新，→Task C3）**：
   - ❌ 移除侧边栏"财务审批"菜单入口（对齐审批入口优化 plan 方案 A）
   - ✅ Header 增加审批 Icon + Badge（唯一轻量入口）
   - ✅ Badge 显示 `pendingCount`（待处理数量）
   - ✅ 点击 Icon 直接跳转 `/approvals`（无下拉预览）
   - ❌ 铃铛下拉预览暂不实施（简化交互，直接跳转页面）
   - 参见：`.claude/plans/jolly-frolicking-shell.md`

8. **筛选功能增强（新增，→Task C3）**：
   - 基础筛选：类型（全部/回款/发票/合同）、客户（搜索下拉）、金额范围、提交日期范围
   - 高级筛选（渐进式披露）：超时状态（overdue_hours >= 48）、当前审批节点、提交人
   - 筛选持久化：localStorage 保存筛选偏好，下次打开恢复
   - 符合 §8 progressive-disclosure：默认简单筛选，点击"高级筛选"展开更多

9. **抽屉信息层级固化**（→Task C3）：详情抽屉结构三段固定：①决策关键字段置顶（发票：开票金额/抬头/关联合同/回款状态；回款：入账金额/回款计划/合同回款进度），用 `el-descriptions`；②`ApprovalProcessGeneric` 审批 timeline；③操作区吸底（同意/驳回/撤回）。**审批人不该翻到底才看到关键金额**。

10. **乐观锁冲突保留输入**（→Task C2）：C-DSG-4 的"冲突→重载"修正为：冲突时不强制关弹窗、不清空已输入的驳回理由；toast "该审批已被他人处理，你的填写已保留" + 重载 detail；若重载后该审批已非 PENDING（已被他人终结），则禁用提交按钮并提示"该审批已由他人处理，无需重复操作"。

**P2 可选（效率增强）**

11. **键盘快捷键**（→Task C3）：审批中心表格 J/K 上下行、A 同意、R 驳回、Enter 开抽屉、Esc 关抽屉。配 `el-tooltip` 提示；`v-permission` 无审批权时不绑 A/R。`prefers-reduced-motion` 下禁用任何过渡。

12. **金额/日期格式化**（→Task C2/C3）：金额用 `Intl.NumberFormat('zh-CN', { style:'currency', currency:'CNY' })`（线框里的 `¥58,000` 不手拼字符串）；日期近用相对（"2 小时前"，<24h）、远用绝对（`YYYY-MM-DD HH:mm`）。建议抽 `src/utils/format.ts` 两个纯函数并配单测。

13. **移动端审批优化（新增，→Task C3）**：
   - 移动端审批入口：Header Icon 放大（touch-target ≥ 44pt）或 Bottom Tab Bar 增加"审批" Tab
   - 移动端列表：卡片式列表（不是表格），每卡片含"同意"、"驳回"、"详情"按钮
   - 移动端抽屉：驳回理由输入弹键盘时，操作区用 `position: sticky; bottom: 0` 吸底 + 安全区 `padding-bottom: env(safe-area-inset-bottom)`
   - 符合 §5 adaptive-navigation：移动端用 bottom nav 或放大的 Header Icon

14. **403 权限态 / deep link 兜底**（→Task C2 ErrorState 扩展）：`ErrorState.vue` 支持 `variant: 'error'|'forbidden'`，forbidden 用 `Lock` 图标 + "你没有该审批的操作权限"；深链直达被拒时显示此态，不白屏。

15. **抽屉关闭后焦点回归**（→Task C3）：审批完关抽屉，焦点回到触发行（或下一行），键盘用户不被甩到页首。Element Plus drawer `@closed` 钩子里 `rowRef.focus()`。

16. **单号点击复制**（→Task C3）：mono 字体的 `application_number`/回款单号单元格 `@click` 复制到剪贴板 + `ElMessage.success` "已复制单号"；用 `navigator.clipboard.writeText`，降级 `document.execCommand`。

17. **Tab 命名优化（新增，→Task C3）**：
   - 「待我审批」 → **「待处理」**（动词导向，符合收件箱心智模型）
   - 「我已处理」 → **「已完成」**（闭环状态）
   - 「我提交的」 → **「我发起的」**（主动视角）
   - Badge 显示：「待处理 ③」

18. **审批历史/审计追踪（新增，→Task C3）**：
   - "我发起的" tab 增加"历史记录"筛选（已完成的审批）
   - 或增加"审批记录"页面（审计追踪，查看所有审批历史）
   - 符合 §9 breadcrumb-web：深层页面需要面包屑导航
10. **金额/日期格式化**（→Task C2/C3）：金额用 `Intl.NumberFormat('zh-CN', { style:'currency', currency:'CNY' })`（线框里的 `¥58,000` 不手拼字符串）；日期近用相对（"2 小时前"，<24h）、远用绝对（`YYYY-MM-DD HH:mm`）。建议抽 `src/utils/format.ts` 两个纯函数并配单测。
11. **移动端抽屉操作区吸底**（→Task C3）：C-DSG-6 移动端补充：驳回理由输入弹键盘时，操作区用 `position: sticky; bottom: 0` 吸底 + 安全区 `padding-bottom: env(safe-area-inset-bottom)`，避免按钮被键盘遮挡。
12. **403 权限态 / deep link 兜底**（→Task C2 ErrorState 扩展）：`ErrorState.vue` 支持 `variant: 'error'|'forbidden'`，forbidden 用 `Lock` 图标 + "你没有该审批的操作权限"；深链直达被拒时显示此态，不白屏。
13. **抽屉关闭后焦点回归**（→Task C3）：审批完关抽屉，焦点回到触发行（或下一行），键盘用户不被甩到页首。Element Plus drawer `@closed` 钩子里 `rowRef.focus()`。
14. **单号点击复制**（→Task C3）：mono 字体的 `application_number`/回款单号单元格 `@click` 复制到剪贴板 + `ElMessage.success` "已复制单号"；用 `navigator.clipboard.writeText`，降级 `document.execCommand`。

**Pre-Delivery Checklist 对账**（zhom-ui-ux-pro-max 内联规则）：防双提交=条3；403 态=条12；其余（cursor-pointer/stable hover/transition 150-300ms/颜色非唯一指示/reduced-motion）已被 C-DSG-1/6 + Element Plus 默认覆盖，无新增。

### Task C1: 通用审批 API + Store

**Files:**
- Create: `CRM-Client/src/api/approvalGeneric.ts`
- Create: `CRM-Client/src/stores/approval.ts`
- Test: `CRM-Client/tests/unit/stores/approval.spec.ts`

**Interfaces:**
- Produces: `submitApproval(type, id, comment)`、`approveEntity(type, id, action, comment, updatedTime)`、`cancelApproval(type, id)`、`getApprovalDetail(type, id)`；store 持 `currentApprovalDetail` + actions。

- [ ] **Step 1: Write failing test**（store action 调 API 并落 detail）。
- [ ] **Step 2-4**: TDD。响应走 Zod schema `ApprovalDetailSchema`（含 records timeline）。
- [ ] **Step 5: Commit** — `feat(client): add generic approval api and store`

### Task C2: 审批状态 Token + 状态徽章 + 通用审批组件 + ErrorState

**Files:**
- Modify: `CRM-Client/src/styles/variables.scss`（追加 `C-DSG-1` 的 8 个 `$wolf-approval-*` token + `:root` CSS 变量映射）
- Create: `CRM-Client/src/components/ApprovalStatusBadge.vue`
- Create: `CRM-Client/src/components/ErrorState.vue`（项目首统一错误态）
- Create: `CRM-Client/src/components/ApprovalProcessGeneric.vue`
- Test: `CRM-Client/tests/unit/components/ApprovalStatusBadge.spec.ts`、`tests/unit/components/ApprovalProcessGeneric.spec.ts`
- Stories: `ApprovalStatusBadge.stories.ts`（4 态）、`ApprovalProcessGeneric.stories.ts`（待审批/审批中/已驳回/无审批单 4 态）

**Interfaces:**
- Produces: `ApprovalStatusBadge` props `status: 'PENDING'|'APPROVED'|'REJECTED'|'CANCELLED'`，渲染图标+中文+token 色。`ErrorState` props `title:string` `description?:string` 默认插槽或 `#action`。`ApprovalProcessGeneric` props（C-DSG-5）：`entityType`、`entityId`、`canApprove`、`isSubmitter`，通过 `useApprovalStore()` 调 actions，宽屏水平/窄屏垂直 timeline，空态用 `WolfEmpty`、错误态用 `ErrorState`、乐观锁冲突自动重载。
- Consumes: Task C1 的 `useApprovalStore` actions；现有 `ApprovalTimeline` / `ApprovalProgressCompact`（展示骨架复用，状态色改为读 `ApprovalStatusBadge` 同源 token）。

- [ ] **Step 1: Write failing tests**

```ts
// tests/unit/components/ApprovalStatusBadge.spec.ts
import { mount } from '@vue/test-utils'
import ApprovalStatusBadge from '@/components/ApprovalStatusBadge.vue'

describe('ApprovalStatusBadge', () => {
  it.each([
    ['PENDING', '待审批'],
    ['APPROVED', '已通过'],
    ['REJECTED', '已驳回'],
    ['CANCELLED', '已撤回'],
  ])('renders %s as %s', (status, label) => {
    const w = mount(ApprovalStatusBadge, { props: { status } })
    expect(w.text()).toContain(label)
    expect(w.attributes('aria-label')).toContain(label)
  })
  it('is not color-only (has icon)', () => {
    const w = mount(ApprovalStatusBadge, { props: { status: 'APPROVED' } })
    expect(w.find('svg').exists()).toBe(true)
  })
})

// tests/unit/components/ApprovalProcessGeneric.spec.ts
import { mount } from '@vue/test-utils'
import ApprovalProcessGeneric from '@/components/ApprovalProcessGeneric.vue'

describe('ApprovalProcessGeneric', () => {
  it('shows submit CTA empty state when no approval exists', async () => {
    // store mock: getApprovalDetail resolves null
    const w = mount(ApprovalProcessGeneric, { props: { entityType: 'INVOICE', entityId: 1, canApprove: true, isSubmitter: true } })
    await flushPromises()
    expect(w.text()).toContain('尚未提交审批')
  })
  it('shows approve/reject for approver when PENDING, not withdraw', async () => {
    // store mock: detail status PENDING, current_node role matches
    const w = mount(ApprovalProcessGeneric, { props: { entityType: 'PAYMENT', entityId: 5, canApprove: true, isSubmitter: false } })
    await flushPromises()
    expect(w.find('[data-testid="approve-btn"]').exists()).toBe(true)
    expect(w.find('[data-testid="withdraw-btn"]').exists()).toBe(false)
  })
  it('reloads on optimistic-lock conflict and shows warning', async () => {
    // store mock: approve rejects with conflict, watch for getApprovalDetail re-call + ElMessage warning spy
  })
  it('reject requires reason, approve does not', async () => {
    const w = mount(ApprovalProcessGeneric, { props: { entityType: 'INVOICE', entityId: 1, canApprove: true, isSubmitter: false } })
    await flushPromises()
    // 驳回弹窗 reason 必填（C-DSG-7 条2）
    await w.find('[data-testid="reject-btn"]').trigger('click')
    const form = w.findComponent(ElForm)
    // ElForm.validate() 模拟必填校验
  })
  it('blocks double-submit: approve button disabled while action pending', async () => {
    // store mock: approve is in-flight; assert button :loading + :disabled
  })
  it('optimistic-lock conflict preserves typed reject reason', async () => {
    // store mock: reject rejects conflict; assert rejectForm.reason 未清空（C-DSG-7 条8）
  })
})
```
> 测试新增覆盖 C-DSG-7 P0 条2/3/8。
```

- [ ] **Step 2: Run tests to verify fail** — `cd CRM-Client && npm run test:unit -- ApprovalStatusBadge ApprovalProcessGeneric` → 组件未创建，FAIL。

- [ ] **Step 3: Implement per C-DSG**
  - `variables.scss` 追加 C-DSG-1 的 8 个 token + `:root{ --wolf-approval-pending-text: #{$wolf-approval-pending-text}; ... }` CSS 变量层。
  - `ApprovalStatusBadge.vue`：`<script setup lang="ts">` props `status`（4 值字面量联合），`computed` 映射图标+文案+颜色 CSS 变量，`el-tag` + 图标，`role="status"` `aria-label`。
  - `ErrorState.vue`：props `title`(必)、`description?`、`#action` 插槽，`$wolf-danger-text` 图标 + 文字。**支持 `variant: 'error'|'forbidden'`**（C-DSG-7 条12），forbidden 用 `Lock` 图标。
  - `ApprovalProcessGeneric.vue`：`onMounted` 调 `store.getApprovalDetail(entityType, entityId)`；`v-loading` + 骨架；`detail===null` → `WolfEmpty`（提交 CTA，按 `isSubmitter` + `v-permission`）；`detail.status` → `ApprovalStatusBadge` + timeline；按钮 `data-testid` 匹配测试；监听 store 的 conflict → **保留已输入驳回理由**（不清空弹窗）+ `ElMessage.warning` "该审批已被他人处理，你的填写已保留" + 重载 detail；重载后若已非 PENDING 则禁用提交并提示（C-DSG-7 条8）。按钮在 action pending 期间 `:loading` + `:disabled`（条3）。驳回弹窗 `reason` 必填、同意可空（条2）。文案严格用 C-DSG-3 表。响应式：`useBreakpoint` 切水平/垂直 timeline。
  - 严格 scoped SCSS 引用 `$wolf-approval-*`，禁内联硬编码；遵循 `COMPONENTS.md` 9 段 SFC 顺序。

- [ ] **Step 4: Run tests + type-check + lint** — `npm run test:unit` → PASS；`npm run type-check && npm run lint` → 无 `any`/无 `!`。

- [ ] **Step 5: Commit**
```bash
git add CRM-Client/src/styles/variables.scss CRM-Client/src/components/{ApprovalStatusBadge,ErrorState,ApprovalProcessGeneric}.vue CRM-Client/tests/unit/components/ CRM-Client/src/components/*.stories.ts
git commit -m "feat(client): approval status tokens, badge, generic ApprovalProcessGeneric, ErrorState"
```

### Task C3: 回款/发票页接入 + FinanceApprovalCenter + 路由启用

**Files:**
- Create: `CRM-Client/src/views/FinanceApprovalCenter.vue`（取代自写按钮的 FinanceInvoiceApprovals/FinancePaymentConfirmations，对应被注释的 finance 路由）
- Modify: `CRM-Client/src/views/Payments.vue`（回款记录行加"提交审批"按钮）、`src/views/InvoiceDetail.vue`（嵌入 `ApprovalProcessGeneric`）
- Modify: `CRM-Client/src/router/index.ts:313-320`（解除 finance 路由注释，指向新 `FinanceApprovalCenter`）
- Modify: `CRM-Client/src/AppLayout.vue`、`src/types/sidebar.ts`（加"财务审批"侧边栏菜单，`v-any-permission="['invoice:approve','payment:approve']"` 控制；徽章显示待办数）
- Deprecate: `src/views/FinanceInvoiceApprovals.vue`、`FinancePaymentConfirmations.vue`（加 deprecation 注释指向 FinanceApprovalCenter，本期不删文件以免破坏 import）
- Test: `CRM-Client/tests/unit/views/financeApprovalCenter.spec.ts`、`tests/unit/views/paymentsApproval.spec.ts`

**Interfaces:**
- Produces: `ApprovalCenter` 三 tab（待处理/已完成/我发起的）+ 筛选（类型/客户/金额/日期/高级筛选）+ 表格 + 详情抽屉内嵌 `ApprovalProcessGeneric` + 快速审批（行内按钮），全状态走 `ApprovalStatusBadge`。
- Consumes: Task C1 store、Task C2 `ApprovalProcessGeneric` + `ApprovalStatusBadge` + `ErrorState`。

- [ ] **Step 1: Write failing tests**

```ts
// tests/unit/views/financeApprovalCenter.spec.ts
it('renders three role-driven tabs with unread badge on pending', async () => {
  // mock store: pendingCount=3
  const w = mount(FinanceApprovalCenter)
  expect(w.text()).toContain('待我审批')
  expect(w.text()).toContain('3')
  expect(w.text()).toContain('我已处理')
  expect(w.text()).toContain('我提交的')
})
it('shows WolfEmpty in pending tab when no rows', async () => {
  const w = mount(FinanceApprovalCenter)
  await flushPromises()
  expect(w.text()).toContain('暂无待审批事项')
})
it('opens drawer with ApprovalProcessGeneric on 详情 click', async () => {
  // mock table row click → assert drawer visible + ApprovalProcessGeneric mounted
})
it('preserves bulk approve/reject from legacy FinanceInvoiceApprovals', async () => {
  // selection 列 + 批量按钮存在（C-DSG-7 条1）
  const w = mount(FinanceApprovalCenter)
  expect(w.find('[data-testid="bulk-approve-btn"]').exists()).toBe(true)
  expect(w.find('[data-testid="bulk-reject-btn"]').exists()).toBe(true)
})
it('shows overdue badge and sorts pending by overdue_hours desc', async () => {
  // mock store: one row overdue_hours=72 → assert 琥珀徽章 + 排序在最前（条5）
})
it('shows 修改并重新提交 on REJECTED row in 我提交的 tab', async () => {
  // 条4 回流闭环
})
it('keyboard: J/K move, Enter opens drawer, Esc closes', async () => {
  // 条9
})

// tests/unit/views/paymentsApproval.spec.ts
it('shows 提交审批 button on payment record row only with payment:submit', async () => {
  // mock permissions store
  const w = mount(Payments)
  expect(w.find('[data-testid="submit-approval-btn"]').exists()).toBe(true)
})
```

- [ ] **Step 2: Run tests to verify fail.**

- [ ] **Step 3: Implement per C-DSG-5 + C-DSG-7**
  - `FinanceApprovalCenter.vue`：page-container + filter-card（el-form inline，类型 el-select = business_type）+ table-card；**表格保留 `type="selection"` 列 + 批量同意/拒绝按钮**（`data-testid` 一致，仅对当前用户可审批的选中行启用，C-DSG-7 条1）；**批量走 E6 端点 `/v1/approvals/bulk-approve`，逐条独立事务 + 部分成功汇总 toast "成功 N 条，失败 M 条" + 失败行可重试**（E6/E8）；状态列 = ApprovalStatusBadge；**新增"超时 N 小时"琥珀徽章列（`overdue_hours>=48`）+ "待我审批"默认按 overdue_hours 降序**（条5）；操作列"详情"。`el-drawer` 右抽屉内嵌 `ApprovalProcessGeneric`，**结构固化三元**：①决策字段 `el-descriptions` 置顶 ②timeline ③操作区吸底（条7）。空态 `WolfEmpty`（C-DSG-4 文案）；加载 `v-loading`；失败 `ErrorState`（"重新加载"，403 用 forbidden variant，条12）；三 tab 由权限可见性驱动（C-DSG-5）。
  - **E2 越权过滤（P0，prior-learning）**：三 tab 列表查询严格按角色过滤——"我提交的" `WHERE submitter_id=:uid AND team_id=:tid`；"待我审批" `JOIN current_node WHERE current_node.approve_role IN (:user_roles) AND status='PENDING' AND team_id=:tid`；"我已处理" `JOIN records WHERE records.approver_id=:uid AND team_id=:tid`。**禁止仅按 team_id 拉全量**（客户/合同/线索列表已有此前科）。
  - **E9 N+1 消除**：列表查询用 SQLAlchemy `joinedload(Approval.current_node)`、`joinedload(Approval.flow)`、`selectinload(Approval.records)` 预加载；`overdue_hours` 在 SQL 层算 `EXTRACT(EPOCH FROM now()-created_time)/3600` 而非 Python 逐行；实体摘要（客户名/合同号/回款金额）按 business_type 分组批量预取后内存 join，不逐行查。
  - **键盘快捷键 J/K/A/R/Enter/Esc** 绑定表格（条9）。**REJECTED 行在"我提交的"tab 显示"修改并重新提交"**（条4，先 `update` 回 DRAFT 再 `submitApproval`）。**抽屉关闭 `@closed` 焦点回到触发行**（条13）。**单号列 mono 字体 + 点击复制**（条14）。应用 `format.ts` 的金额/日期格式化（条10）。移动端操作区 `position:sticky;bottom:0` + 安全区 padding（条11）。
  - `Payments.vue`：回款记录表行加"提交审批" `el-button`（`data-testid="submit-approval-btn"`，`v-permission="payment:submit"`，文案 C-DSG-3，待审批中 `:loading`），点击调 `store.submitApproval('PAYMENT', recordId)` + ElMessage.success；金额列用 `format.ts`。
  - `InvoiceDetail.vue`：详情区底部嵌入 `<ApprovalProcessGeneric entityType="INVOICE" :entityId="id" .../>`，替换原 `ApprovalProcess` 的合同专属用法。
  - `utils/format.ts`（新建）：`formatCurrency(n)` `Intl.NumberFormat('zh-CN',{style:'currency',currency:'CNY'})`、`formatDateRelative(d)`（<24h 相对、否则绝对），配单测（条10）。
  - `router/index.ts`：解除 `finance/invoice-approvals` 与 `finance/payment-confirmations` 注释，**合并指向** `/finance/approvals` → `FinanceApprovalCenter`（INVOICE 与 PAYMENT 合一，因 business_type 筛选已分流）。
  - `AppLayout.vue` / `sidebar.ts`：新增"财务审批"菜单项（Icon `Checked`/`Document`），`v-any-permission="['invoice:approve','payment:approve']"`，右侧徽章数 = pendingCount。

- [ ] **Step 4: Run tests + type-check + lint + visual** — `npm run test:unit && npm run type-check && npm run lint`；手动 `npm run dev` 验证三 tab、空态、抽屉、移动端卡片降级。

- [ ] **Step 5: Commit**
```bash
git add CRM-Client/src/views/FinanceApprovalCenter.vue CRM-Client/src/views/{Payments,InvoiceDetail,FinanceInvoiceApprovals,FinancePaymentConfirmations}.vue CRM-Client/src/router/index.ts CRM-Client/src/AppLayout.vue CRM-Client/src/types/sidebar.ts CRM-Client/tests/unit/views/
git commit -m "feat(client): FinanceApprovalCenter, wire payment/invoice approval, enable finance routes"
```

### Task C4: 应用内通知铃铛（C-DSG-7 条6）

**Files:**
- Create: `CRM-Client/src/components/ApprovalNotificationCenter.vue`（顶栏铃铛下拉）
- Create: `CRM-Client/src/api/approvalOverdue.ts`（复用 `GET /v1/approvals/overdue`）+ 待审批列表聚合
- Modify: `CRM-Client/src/AppLayout.vue`（顶栏挂铃铛 + 轮询）
- Test: `CRM-Client/tests/unit/components/ApprovalNotificationCenter.spec.ts`

**Interfaces:**
- Produces: 顶栏铃铛，徽章 = 待我审批数；下拉列最近 N 条（含超时高亮），点击直跳审批中心抽屉。**不依赖飞书**。

- [ ] **Step 1: Write failing test** — 铃铛渲染 pendingCount；超时项高亮。
- [ ] **Step 2: Run to fail.**
- [ ] **Step 3: Implement** — 铃铛 `el-badge` + `el-dropdown`；数据源调 `approvalOverdue` + 待审批列表合并；定时轮询 60s（可配）；`v-any-permission` 控制可见。**E10 轮询优化**：监听 `document.visibilitychange`——后台 tab 暂停轮询、前台恢复且立即拉一次；请求失败指数退避 60→120→240s 封顶 5min；成功后重置退避。避免 N 在线审批人持续打 /overdue。
- [ ] **Step 4: Run tests** → PASS。
- [ ] **Step 5: Commit** — `feat(client): in-app approval notification bell (non-feishu discovery)`

### Task C5: 前端 Settings.vue 权限码修正

**Files:**
- Modify: `CRM-Client/src/views/Settings.vue:200`
- Det: 旧码 `approval:flow:update` → `approval:flow:edit`（对齐 commit 726b37f）。

- [ ] **Step 1-5]: grep 确认全局无残留 `approval:flow:update` → 改 → commit `fix(client): align approval:flow:edit permission code`。

---

## Phase D — 文档与回归

### Task D1: 文档更新

**Files:**
- Modify: `CRM-Docs/system/SYSTEM-DESCRIPTION.md`（回款审批新增、发票改为多级）
- Modify: `CRM-Docs/system/BUSINESS-CHAIN-API.md`（新端点）
- Modify: `CRM-Docs/system/AI-AGENT-ARCHITECTURE.md`（AI 解析器 business_type）

### Task D2: 全量回归

- [ ] `cd CRM-Server && pytest tests/unit -v`
- [ ] `cd CRM-Server && ruff check app/ && mypy app/`
- [ ] `cd CRM-Client && npm run lint && npm run type-check && npm run test:unit`
- [ ] 跑 `scripts/check_migrations.py`、`scripts/check_team_isolation.py`
- [ ] 手动：合同审批回归（提交→通过→驳回→撤回全链路）+ 回款审批 + 发票审批端到端
- [ ] **E1/E3 合同回归专项测试**（P0）：新建 `CRM-Server/tests/unit/test_contract_approval_regression.py`，三场景断言 `match_flow_generic('CONTRACT')` 与改造前 `match_flow` 结果逐字一致：
  - 场景1 金额边界：金额恰好等于 min_amount/max_amount 的合同匹配到对应 flow
  - 场景2 license_type 匹配：license_type 不匹配的 flow 被排除
  - 场景3 多 flow 评分排序：多个候选 flow 时按 `calculate_flow_precision_score` 选最优，与改造前同
  - 端到端：合同提交→approve 末节点→status=SIGNED；reject→DRAFT；cancel→DRAFT，全链路状态切换不变
- [ ] **E7 在途平迁测试**：跑 `tests/unit/test_invoice_data_migration.py`（Task B2 已建）
- [ ] **E8 批量部分失败测试**：跑 `tests/unit/test_bulk_approval_partial_failure.spec.ts`（Task C3 已建）

---

## Self-Review

1. **Spec coverage**: 发票迁移多级引擎 → Task B2/A8/A5；回款多级引擎 → Task B1/A5；模型泛化 business_type+business_id → Task A2/A3/A5；权限码+角色 → Task A7；前端审批落地 → Phase C；不破坏合同 → 每 Task 均对应回归测试 + 旧 wrapper 保留。
2. **Placeholder scan**: Task B1/B2/C1-C4 的 Step 3 代码骨架已给，仅 B3/C 系列为标准 TDD 骨架（明确测试输入输出），无 TBD。
3. **Type consistency**: `business_type`(str)、`business_id`(int)、`get_adapter` 返回值、`create_approval_generic` / `get_by_entity` / `match_flow_generic` 签名在各 Task 引用一致；前端 `submitApproval(type,id,...)` 与后端 `{entity_type}/{entity_id}` 对齐。

## 关键决策与依据（结合业务上下文与用户旅程）

以下 5 个决策点已结合系统真实业务流程、用户旅程与代码证据论证，**方案按此执行**，不再悬而未决。

### 决策 1：回款审批 = 可选叠加，"未匹配流 = 免审批直通财务确认"

**业务事实**（证据）：
- `SYSTEM-DESCRIPTION.md:143/154/167` 与 `BUSINESS-CHAIN-API.md:128` 明确：回款流程为"合同生效 → 创建回款计划 → 登记回款 → 更新计划状态"，**全程无审批环节**；FINANCE 对回款的职责是"确认"而非"审批"。
- 用户旅程（`api/payments.py:264` 登记 + `api/finance.py:32` 确认）：销售登记 → 财务确认入账，`actual_amount` 单值，**无金额分层**。
- `match_flow`（`crud/approval.py:172/240/263`）当前语义"未匹配=报错阻断"，合同审批依赖此语义，**不可改**。

**成熟方案**：回款**接入引擎但默认免审批**——保留你的"多级审批引擎"选择（回款具备走多级审批的能力），但基线行为仍是"财务确认入账"，审批仅作为大额/异常的**可选风控叠加**：
- `match_flow_generic` 在 `business_type=PAYMENT` 且未匹配任何流时，返回 `(None, None)`（**非报错**），由回款端点走"免审批 → 直接财务确认"分支。
- 团队若配置了 `business_type=PAYMENT` 的 ApprovalFlow（含 `min_amount` 阈值），大额回款才匹配并走多级审批；小额/未配置则免审批。
- 通过 `match_flow_generic` 的 `business_type` 分支隔离两套语义，不改 `match_flow` 的合同语义。
- `on_approved` 仍置 `confirmation_status=CONFIRMED`（审批通过即确认入账）；未走审批的回款由 `finance.py:confirm_payment_record` 原路径确认。

**受影响 Task**：A5（`match_flow_generic` 增未匹配=None 分支，按 business_type 区分语义）、B1（回款提交端点：匹配到流→建 Approval；未匹配→保持 PENDING 待财务确认）。

### 决策 2：发票 `/review` 单步端点 → 硬废弃；在途数据分类平迁

**业务事实**（证据）：
- 前端 `InvoiceDetail.vue:508/535`、`Invoices.vue:319/335` 仅调 submit/withdraw，**零 `/review` 调用**；`FinanceInvoiceApprovals.vue:311/341/370` 调的是 `/{id}/finance-approval`，该后端路由**不存在（404 死链）**；且 finance 审批路由在 `router/index.ts:312-314` 已被注释禁用。**`POST /{id}/review` 在线上前端无入口。**
- 发票枚举 `DRAFT/PENDING_REVIEW/APPROVED/REJECTED/ISSUED`（`models/invoice.py:11-16`）；`reviewer_id/review_comment/reviewed_time`（:68-70）由 `crud/invoice.py:292-294` 写入；`InvoiceDetail.vue:123/248-253` 仍依赖这三个字段展示审批人/时间线。

**成熟方案**：
- (a) **`POST /{id}/review` 硬废弃**（删端点 + `crud.review` 方法）。前端零调用、路由禁用、死链 404，硬废弃对线上零影响；删除前 grep 确认无 AI handler/脚本依赖。
- (b) **在途数据分类平迁**（写入 Alembic 数据迁移）：
  - `APPROVED` 旧记录 → 补建一条 `Approval(business_type=INVOICE, status=APPROVED)` + `ApprovalRecord` 保审计一致；
  - `PENDING_REVIEW` 旧记录 → 回退 `status=DRAFT`，由申请人经引擎重新提交（语义干净，避免把单步态硬塞进引擎）；
  - `ISSUED`/`REJECTED` → 不动（历史终态）。
- (c) **`reviewer_id/review_comment/reviewed_time` 保留为快照**，由引擎终态回写（`on_approved`/`on_rejected` 时同步写发票表），`InvoiceDetail.vue` 仍读这三个字段，避免双读与前端破坏。
- (d) **`mark_issued` 判定源改为查关联 Approval**：`crud/invoice.py:305` 的 `status==APPROVED` 改为校验 `approval_crud.get_by_entity(INVOICE, id, team).status == APPROVED`；`InvoiceApplication.status` 降级为引擎回写的冗余镜像。

**受影响 Task**：B2（改为硬废弃 + 数据迁移 + reviewer 快照回写 + mark_issued 判定源）、A4（InvoiceApplication 适配器 `on_approved/on_rejected` 增写 reviewer 三字段）。

### 决策 3：InvoiceApplication 提交人字段 = `applicant_id`（非 creator_id）

**事实**：`models/invoice.py:67` `applicant_id = Column(String(100), nullable=False, comment="申请人ID（飞书用户ID）")`；**无 `creator_id` 字段**。`PaymentRecord.creator_id` 在 `models/payment.py:55`。开票金额字段为 `invoice_amount`（`models/invoice.py:64`，非 `amount`）。

**方案**：`InvoiceApplicationAdapter.get_submitter` 用 `entity.applicant_id`（applicant_name 无则 None）；`match_kwargs` 用 `entity.invoice_amount`。`PaymentRecordAdapter` 仍用 `creator_id`。两单据字段不同，正是适配器层各自封装的价值。

**受影响 Task**：A4（修正 `InvoiceApplicationAdapter.get_submitter` 与 `match_kwargs`）。

### 决策 4：`ApprovalFlow.business_type` 列并入 012 迁移

**事实**：`ApprovalFlow`（`models/approval.py:21-52`）当前无 `business_type` 字段；`match_flow_generic` 必须按 `business_type` 过滤流否则回款/发票会误匹配合同流。`MIGRATION_RULES.md:154-187` 要求命名规范 + 完整 upgrade/downgrade + 数据回填，一个 feature 的 schema 变更允许多表多操作放同一迁移。

**成熟方案**：**并入 012 迁移**（一次 upgrade/downgrade 完成整个泛化 schema，减少迁移链环节，避免"实例有 business_type 但 flow 没有"的中间不一致态）：
- 012 同时给 `crm_contract_approvals` 加 `business_type/business_id` + 给 `crm_approval_flows` 加 `business_type`（default 'CONTRACT'，NOT NULL，现有 flow 自动归类合同流，**无需数据回填**）+ 索引 `idx_flow_business_type`。
- 不单开 013。

**受影响 Task**：A3（012 迁移追加 ApprovalFlow 列与索引）、A5（`ApprovalFlow` 模型加列）。

### 决策 5：回填加 orphan 守卫 + 非阻断校验脚本；PAYMENT/INVOICE 不预置默认流

**业务事实**（证据）：
- `Approval.contract_id` `ondelete=SET NULL, nullable=True`（`approval.py:93`）；合同是**软删除**（`migration 010`、`crud/contract.py:376-442` 置 `deleted_at`）。软删不触发 DB 级 ondelete，仅 `crud/contract.py:417` 在"PENDING_REVIEW 合同被软删"窄场景手动 `approval.contract_id=None`。`get_approvals_for_deleted_contracts`（`crud/approval.py:456-489`）专门查 `contract_id IS NULL`——这是**已知且接受的合规形态**，非病态脏数据。
- 风险：若回填 `business_id = contract_id`，对 `contract_id IS NULL` 的孤儿行会得到 `business_type='CONTRACT'` 但 `business_id=NULL` 的**语义自相矛盾**，`get_by_entity` 查不到、适配器 `get_entity` 拿 None 报错。

**成熟方案**：
- (a) **回填加守卫 + 孤儿标记**，避免 CONTRACT+NULL business_id 矛盾：
  ```sql
  UPDATE crm_contract_approvals SET business_id = contract_id, business_type='CONTRACT'
    WHERE business_id IS NULL AND contract_id IS NOT NULL;
  UPDATE crm_contract_approvals SET business_type='ORPHAN'
    WHERE business_id IS NULL AND contract_id IS NULL;
  ```
  孤儿行标为 `ORPHAN`，`get_by_entity` 对 ORPHAN 不查询，自然隔离。
- (b) **非阻断校验**：迁移 upgrade 末尾用 `op.get_bind().execute(text("SELECT COUNT(*) ..."))` + `logging.warning` 打印孤儿数（风格对齐 `scripts/check_migrations.py`、`check_team_isolation.py`，不阻断，退出码 0）。另建议新增 `scripts/check_orphan_approvals.py` 巡检脚本。
- (c) **不预置 PAYMENT/INVOICE 默认 flow**：留空 = 免审批（与决策 1 的"未匹配=免审批直通"语义一致）。"是否需要审批"是业务决策，不应由迁移强行写入；团队需要时手动新建 `business_type=PAYMENT/INVOICE` 的 flow。文档化此语义到 `CRM-Docs/best-practices/backend/`。

**受影响 Task**：A3（012 回填改为带守卫 + ORPHAN 标记 + 校验日志）、D1（文档化"未配置流=免审批"语义）。

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | DONE | 8 维度，初始 2–7/10 → 9/10；DESIGN_NOT_AVAILABLE 故文本线框；新增 C-DSG-1~6 + 重写 Task C1/C2/C3 |
| Design Review | `/zhom-ui-ux-pro-max` | 交互缺口 | 1 | DONE_WITH_CONCERNS | 14 条交互（P0×4+P1×4+P2×6），数据库未装改用内联规则+代码验证；新增 C-DSG-7 + Task C4 通知铃铛 |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | DONE | 10 工程隐患（3 P0 + 6 P1 + 1 P2）全补；应用 prior-learning permission-view-filter-missing (conf 9/10) |
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Outside Voice | codex-plan-review | 独立二审 | 1 | ERROR | Codex 流断（stream disconnected before finish_reason，5 次重连失败）；用户选默认跳过回退子代理 |

**Eng Review findings 明细**（10 条，全部已落到 Task 步骤 + 测试）：
- **P0** E1 合同 match_flow_generic 回归契约（Task A5/D2，回归测试 3 场景）、E2 FinanceApprovalCenter 越权过滤-prior learning 命中（Task C3 三 tab 严格 submitter/role 过滤）、E3 合同端到端回归测试（Task D2 `test_contract_approval_regression.py`）
- **P1** E4 适配器 on_* None 守卫（Task A4/A5）、E5 回款未匹配=免审批直通财务确认（Task B1/C3，替拍板）、E6 批量审批逐条独立事务+部分成功汇总（Task A6 端点 + C3，替拍板）、E7 在途平迁测试（Task B2）、E8 批量部分失败测试（Task C3）、E9 FinanceApprovalCenter N+1 消除 joinedload+SQL 层算 overdue（Task C3）
- **P2** E10 通知铃铛轮询 visibilitychange+指数退避（Task C4）

**NOT in scope**：vue-i18n 引入（项目零 i18n 基建，独立工作）；废发票单步审批的 dead code 物理删除（保留 deprecated 兼容）；FinanceInvoiceApprovals/FinancePaymentConfirmations 文件删除（加 deprecation 注释指向新页，不删以免破坏 import）；gstack 视觉 mockup 生成器安装（DESIGN_NOT_AVAILABLE，需另跑 `$D setup`）。

**What already exists**（复用，不重建）：`$wolf-*` 设计 token + status 功能色（variables.scss）、Element Plus、`WolfEmpty.vue`、`ApprovalTimeline/ApprovalProgressCompact` 骨架、后端 `GET /v1/approvals/overdue`（`approvals.py:115`）、三 CRUD `get_by_id`（contract/payment/invoice 均已存在）、乐观锁（`crud/approval.py:544`）、`payment_record_crud.confirm_payment`（`crud/payment.py:460`）。

**Failure modes**（关键路径）：合同 match_flow 泛化回归→E1 契约+E3 测试；适配器取到 None→E4 守卫；批量审批部分失败→E6 事务策略+E8 测试；FinanceApprovalCenter 越权→E2 过滤；在途平迁写错 status→E7 测试；铃铛轮询打爆 /overdue→E10 退避。均有测试或守卫覆盖，无"无测试+无处理+静默"的 critical gap。

**Parallelization**：Lane A（后端 models+migration+adapter+crud+generic API：A1-A8）顺序；Lane B（前端 C1-C5）依赖 A6 端点契约；Lane C（数据迁移 SQL：A3 尾/B2 平迁）依赖 A2 模型。A 顺序完成 → B+C 可并行（B 触前端、C 触 migrations/数据，无共享模块冲突）。

**VERDICT:** DESIGN + ENG CLEARED — 3 P0 工程隐患（合同回归/越权/回归测试）与 6 P1 + 1 P2 全部落到具体 Task 步骤与测试，prior-learning permission-view-filter-missing 已应用。Outside Voice 因 Codex 流断未取得独立二审，用户选默认跳过回退。E5/E6 两处业务语义替拍板已标注"如不合意可改"。

NO UNRESOLVED DECISIONS