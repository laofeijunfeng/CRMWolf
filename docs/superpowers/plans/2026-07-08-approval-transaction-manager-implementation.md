# ApprovalTransactionManager 重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 ApprovalTransactionManager 重构，彻底统一审批流程状态系统，新增 approval_phase 数据库字段，修复 Payment 驳回状态和 License 审批拒绝状态问题。

**Architecture:** 采用"方案 1：单表单状态系统"（激进重构），新增 approval_phase 作为数据库字段，双字段职责分离（ApprovalPhase 专注审批流程，原有 status 保留业务语义）。

**Tech Stack:** Python 3.11 + SQLAlchemy 2.0 + Alembic + Pydantic 2.0

## Global Constraints

- **方案选择**: 方案 1 - 单表单状态系统（approval_phase 作为数据库字段）
- **双字段职责分离**: ApprovalPhase 专注审批流程，原有 status 保留业务语义
- **强制审批规则**: 所有单据（合同/回款/发票/License）必须走审批流程
- **审批未匹配处理**: 报错提示，保留单据，approval_phase = DRAFT
- **审批失败处理**: 保留单据，approval_phase = REJECTED，用户可重新提交
- **无免审批直通**: 删除当前 LICENSE/INVOICE 的免审批直通逻辑
- **事务边界明确**: 所有数据库写入在 ApprovalTransactionManager 中统一 commit
- **异常分支完整**: 覆盖未匹配、查询失败、通知失败等所有场景
- **数据迁移完整**: 新增 approval_phase 字段 + 历史数据映射 + 紧急修复

### 业务规则确认

| 规则 | 说明 |
|------|------|
| **ApprovalPhase 统一状态** | draft → pending_review → approved/rejected |
| **原有 status 语义分离** | Contract.status（生命周期）、Payment.confirmation_status（确认状态） |
| **多级审批中间节点** | approval_phase 保持 pending_review，只有最后节点通过才切 approved |
| **驳回后重新提交** | approval_phase = REJECTED → DRAFT → PENDING_REVIEW，删除旧 Approval 实例 |

---

## File Structure

### 新建文件

| 文件路径 | 负责内容 |
|---------|---------|
| `CRM-Server/app/constants/approval_phase.py` | ApprovalPhase 统一状态枚举 |
| `CRM-Server/app/services/approval_transaction_manager.py` | ApprovalTransactionManager 核心类 |
| `CRM-Server/migrations/versions/018_add_approval_phase_field.py` | approval_phase 字段迁移 + 数据迁移 |
| `CRM-Server/tests/unit/approval/test_transaction_manager.py` | ApprovalTransactionManager 单元测试 |

### 修改文件

| 文件路径 | 修改内容 |
|---------|---------|
| `CRM-Server/app/models/contract.py` | 新增 approval_phase 字段 |
| `CRM-Server/app/models/payment.py` | 新增 approval_phase 字段，PaymentConfirmationStatus 新增 DRAFT |
| `CRM-Server/app/models/invoice.py` | 新增 approval_phase 字段 |
| `CRM-Server/app/models/license_application.py` | 新增 approval_phase 字段，PENDING → PENDING_REVIEW |
| `CRM-Server/app/crud/approval.py` | ApprovalCRUD 改造（_create_approval_impl） |
| `CRM-Server/app/crud/payment.py` | 删除内部 commit，使用 TransactionManager |
| `CRM-Server/app/crud/contract.py` | 删除内部 commit，使用 TransactionManager |
| `CRM-Server/app/crud/crud_license_application.py` | 删除免审批直通，使用 TransactionManager |
| `CRM-Server/app/api/approvals.py` | 审批流转联动 approval_phase |
| `CRM-Server/app/services/approval_adapter.py` | Adapter 状态切换调整 |

---

## Version Plan

| 版本 | 内容 | 预估时间 |
|------|------|---------|
| **v1.0** | 数据库迁移（新增 approval_phase 字段） | 1 天 |
| **v1.1** | ApprovalTransactionManager 核心类 | 2 天 |
| **v1.2** | Approval Engine 联动 approval_phase | 1 天 |
| **v1.3** | Adapter 状态切换调整 | 1 天 |
| **v1.4** | 前端状态判断逻辑调整 | 2 天 |
| **v1.5** | 删除免审批直通逻辑 | 1 天 |
| **v1.6** | 测试用例编写 | 2 天 |
| **总计** | — | **10 天** |

---

## v1.0: 数据库迁移（新增 approval_phase 字段）

**Files:**
- Create: `CRM-Server/migrations/versions/018_add_approval_phase_field.py`
- Modify: `CRM-Server/app/models/contract.py`
- Modify: `CRM-Server/app/models/payment.py`
- Modify: `CRM-Server/app/models/invoice.py`
- Modify: `CRM-Server/app/models/license_application.py`

**Interfaces:**
- Produces: approval_phase 字段（所有业务单据表）
- Produces: ApprovalPhase 枚举值映射

**Reference:** Spec §1.2（数据库新增 approval_phase 字段）§5.1（数据迁移方案）

### Task 1.0.1: 创建 ApprovalPhase 统一状态枚举

- [ ] **Step 1: 创建 approval_phase.py 文件**

```python
# app/constants/approval_phase.py

from enum import Enum


class ApprovalPhase(str, Enum):
    """
    审批流程状态（数据库直接映射）

    所有业务单据的审批流程状态统一使用此枚举。
    """
    DRAFT = "draft"           # 草稿/待提交审批
    PENDING_REVIEW = "pending_review"  # 待审批（整个审批流程中）
    APPROVED = "approved"     # 审批通过
    REJECTED = "rejected"     # 审批拒绝

    @classmethod
    def from_approval_status(cls, approval_status: str) -> ApprovalPhase:
        """从 Approval.status 映射到 ApprovalPhase"""
        from app.models.approval import ApprovalStatus
        mapping = {
            ApprovalStatus.PENDING: cls.PENDING_REVIEW,
            ApprovalStatus.APPROVED: cls.APPROVED,
            ApprovalStatus.REJECTED: cls.REJECTED,
        }
        return mapping.get(approval_status, cls.DRAFT)
```

- [ ] **Step 2: 验证枚举文件创建成功**

```bash
# 在 CRM-Server 目录执行
ls -la app/constants/approval_phase.py
# 应显示文件存在
```

### Task 1.0.2: 修改 Contract 模型新增 approval_phase 字段

- [ ] **Step 1: 读取 contract.py 文件**

Read: `CRM-Server/app/models/contract.py`

- [ ] **Step 2: 在 Contract 类中新增 approval_phase 字段**

在 Contract 类中（status 字段附近）添加：

```python
from app.constants.approval_phase import ApprovalPhase

# 在 Contract 类中添加
approval_phase = Column(
    String(20),
    nullable=False,
    default=ApprovalPhase.DRAFT,
    comment="审批流程状态：draft/pending_review/approved/rejected"
)
```

- [ ] **Step 3: 验证修改正确**

```bash
cd CRM-Server
python -c "from app.models.contract import Contract; print('approval_phase field added')"
```

### Task 1.0.3: 修改 Payment 模型新增 approval_phase 字段

- [ ] **Step 1: 读取 payment.py 文件**

Read: `CRM-Server/app/models/payment.py`

- [ ] **Step 2: 新增 PaymentConfirmationStatus.DRAFT**

在 PaymentConfirmationStatus 类中添加：

```python
class PaymentConfirmationStatus:
    DRAFT = "DRAFT"          # 新增：草稿状态
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    DISPUTED = "DISPUTED"
```

- [ ] **Step 3: 在 PaymentRecord 类中新增 approval_phase 字段**

在 PaymentRecord 类中（confirmation_status 字段附近）添加：

```python
from app.constants.approval_phase import ApprovalPhase

# 在 PaymentRecord 类中添加
approval_phase = Column(
    String(20),
    nullable=False,
    default=ApprovalPhase.DRAFT,
    comment="审批流程状态：draft/pending_review/approved/rejected"
)
```

### Task 1.0.4: 修改 Invoice 模型新增 approval_phase 字段

- [ ] **Step 1: 读取 invoice.py 文件**

Read: `CRM-Server/app/models/invoice.py`

- [ ] **Step 2: 在 InvoiceApplication 类中新增 approval_phase 字段**

在 InvoiceApplication 类中添加：

```python
from app.constants.approval_phase import ApprovalPhase

approval_phase = Column(
    String(20),
    nullable=False,
    default=ApprovalPhase.DRAFT,
    comment="审批流程状态：draft/pending_review/approved/rejected"
)
```

### Task 1.0.5: 修改 License 模型新增 approval_phase 字段

- [ ] **Step 1: 读取 license_application.py 文件**

Read: `CRM-Server/app/models/license_application.py`

- [ ] **Step 2: 修改 LicenseApplicationStatus（PENDING → PENDING_REVIEW）**

修改 LicenseApplicationStatus 类：

```python
class LicenseApplicationStatus:
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"  # 改名：统一命名
    APPROVED = "APPROVED"
    ISSUED = "ISSUED"
    REJECTED = "REJECTED"
```

- [ ] **Step 3: 在 LicenseApplication 类中新增 approval_phase 字段**

添加：

```python
from app.constants.approval_phase import ApprovalPhase

approval_phase = Column(
    String(20),
    nullable=False,
    default=ApprovalPhase.DRAFT,
    comment="审批流程状态：draft/pending_review/approved/rejected"
)
```

### Task 1.0.6: 创建数据库迁移脚本

- [ ] **Step 1: 创建迁移文件**

```bash
cd CRM-Server
alembic revision -m "add_approval_phase_field"
```

- [ ] **Step 2: 编辑迁移文件**

编辑生成的迁移文件（假设为 018_add_approval_phase_field.py）：

```python
"""add approval_phase field to all business entity tables

Revision ID: 018_add_approval_phase_field
Revises: 017_license_approval_field
Create Date: 2026-07-08

"""
from alembic import op
import sqlalchemy as sa
from app.constants.approval_phase import ApprovalPhase


revision = '018_add_approval_phase_field'
down_revision = '017_license_approval_field'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Contract 表新增 approval_phase 字段
    op.add_column(
        'crm_contracts',
        sa.Column('approval_phase', sa.String(20), nullable=False,
                  server_default=ApprovalPhase.DRAFT,
                  comment='审批流程状态：draft/pending_review/approved/rejected')
    )

    # 2. PaymentRecord 表新增 approval_phase 字段
    op.add_column(
        'crm_payment_records',
        sa.Column('approval_phase', sa.String(20), nullable=False,
                  server_default=ApprovalPhase.DRAFT,
                  comment='审批流程状态：draft/pending_review/approved/rejected')
    )

    # 3. InvoiceApplication 表新增 approval_phase 字段
    op.add_column(
        'crm_invoice_applications',
        sa.Column('approval_phase', sa.String(20), nullable=False,
                  server_default=ApprovalPhase.DRAFT,
                  comment='审批流程状态：draft/pending_review/approved/rejected')
    )

    # 4. LicenseApplication 表新增 approval_phase 字段
    op.add_column(
        'crm_license_applications',
        sa.Column('approval_phase', sa.String(20), nullable=False,
                  server_default=ApprovalPhase.DRAFT,
                  comment='审批流程状态：draft/pending_review/approved/rejected')
    )

    # 5. 数据迁移：Contract（status → approval_phase）
    op.execute("""
        UPDATE crm_contracts
        SET approval_phase = CASE
            WHEN status = 'DRAFT' THEN 'draft'
            WHEN status = 'PENDING_REVIEW' THEN 'pending_review'
            WHEN status IN ('SIGNED', 'EFFECTIVE', 'EXPIRED', 'TERMINATED') THEN 'approved'
            ELSE 'draft'
        END
    """)

    # 6. 数据迁移：PaymentRecord（复杂逻辑，修复驳回状态）
    op.execute("""
        -- 未提交审批的 PENDING → draft
        UPDATE crm_payment_records
        SET approval_phase = 'draft'
        WHERE confirmation_status = 'PENDING' AND approval_id IS NULL;

        -- 审批中的 PENDING → pending_review
        UPDATE crm_payment_records pr
        SET approval_phase = 'pending_review'
        FROM crm_contract_approvals a
        WHERE pr.approval_id = a.id AND a.status = 'PENDING';

        -- 审批通过的 CONFIRMED → approved
        UPDATE crm_payment_records
        SET approval_phase = 'approved'
        WHERE confirmation_status = 'CONFIRMED';

        -- 审批拒绝的 PENDING → rejected（关键修复）
        UPDATE crm_payment_records pr
        SET approval_phase = 'rejected'
        FROM crm_contract_approvals a
        WHERE pr.approval_id = a.id AND a.status = 'REJECTED';

        -- 有争议的 DISPUTED → rejected
        UPDATE crm_payment_records
        SET approval_phase = 'rejected'
        WHERE confirmation_status = 'DISPUTED';
    """)

    # 7. 数据迁移：InvoiceApplication
    op.execute("""
        UPDATE crm_invoice_applications
        SET approval_phase = CASE
            WHEN status = 'DRAFT' THEN 'draft'
            WHEN status = 'PENDING_REVIEW' THEN 'pending_review'
            WHEN status IN ('APPROVED', 'ISSUED') THEN 'approved'
            WHEN status = 'REJECTED' THEN 'rejected'
            ELSE 'draft'
        END
    """)

    # 8. 数据迁移：LicenseApplication（修复审批拒绝但 status = PENDING）
    op.execute("""
        UPDATE crm_license_applications
        SET approval_phase = CASE
            WHEN status = 'DRAFT' THEN 'draft'
            WHEN status IN ('PENDING', 'PENDING_REVIEW') THEN 'pending_review'
            WHEN status IN ('APPROVED', 'ISSUED') THEN 'approved'
            WHEN status = 'REJECTED' THEN 'rejected'
            ELSE 'draft'
        END
    """)

    # 9. LicenseApplication.status PENDING → PENDING_REVIEW（统一命名）
    op.execute("""
        UPDATE crm_license_applications
        SET status = 'PENDING_REVIEW'
        WHERE status = 'PENDING'
    """)


def downgrade():
    # 删除所有 approval_phase 字段
    op.drop_column('crm_contracts', 'approval_phase')
    op.drop_column('crm_payment_records', 'approval_phase')
    op.drop_column('crm_invoice_applications', 'approval_phase')
    op.drop_column('crm_license_applications', 'approval_phase')

    # LicenseApplication.status 恢复 PENDING
    op.execute("""
        UPDATE crm_license_applications
        SET status = 'PENDING'
        WHERE status = 'PENDING_REVIEW'
    """)
```

- [ ] **Step 3: 执行迁移（开发环境）**

```bash
cd CRM-Server
alembic upgrade head
```

- [ ] **Step 4: 验证迁移成功**

```bash
# 检查字段是否新增
python -c "
from app.core.database import SessionLocal
from app.models.contract import Contract
from app.models.payment import PaymentRecord

db = SessionLocal()
try:
    # 验证 Contract 表
    contract = db.query(Contract).first()
    if contract:
        print(f'Contract approval_phase: {contract.approval_phase}')

    # 验证 PaymentRecord 表
    payment = db.query(PaymentRecord).first()
    if payment:
        print(f'Payment approval_phase: {payment.approval_phase}')
finally:
    db.close()
"
```

---

## v1.1: ApprovalTransactionManager 核心类

**Files:**
- Create: `CRM-Server/app/services/approval_transaction_manager.py`

**Interfaces:**
- `create_with_approval(db, business_type, entity_create_func, match_flow_kwargs, submitter_id, submitter_name, team_id) -> (entity, approval, error_message)`
- `submit_for_approval(db, business_type, entity_id, team_id, submitter_id, submitter_name) -> (approval, error_message)`
- `_send_notification_async(...) -> None`
- `resend_notification(approval_id, team_id) -> (success, error_message)`

**Reference:** Spec §2（ApprovalTransactionManager 核心类设计）

### Task 1.1.1: 创建 ApprovalTransactionManager 类骨架

- [ ] **Step 1: 创建 approval_transaction_manager.py 文件**

```python
# app/services/approval_transaction_manager.py

"""
审批事务管理器（拒绝妥协设计）

核心职责：
1. 事务原子性保证：业务单据创建 + approval_phase 切换 + Approval 创建在同一事务
2. approval_phase 状态流转统一管理
3. 异常友好处理：保留单据，approval_phase 回退到 DRAFT
4. 原有 status 字段联动：通过 adapter 触发业务状态切换

设计原则：
1. 拒绝"最小改动"妥协 - approval_phase 作为数据库字段，彻底统一状态系统
2. 业务语义分离 - approval_phase 专注审批流程，原有 status 保留业务语义
3. 事务边界明确 - 所有数据库写入在此类中统一 commit
4. 异常分支完整 - 覆盖未匹配、查询失败、通知失败等所有场景
"""

from typing import Any, Optional, Tuple, Callable
from sqlalchemy.orm import Session
import logging

from app.constants.approval_phase import ApprovalPhase
from app.services.approval_adapter import get_adapter
from app.crud.approval import approval_crud
from app.models.approval import Approval

logger = logging.getLogger(__name__)


class ApprovalTransactionManager:
    """审批事务管理器"""

    def create_with_approval(
        self,
        db: Session,
        business_type: str,
        entity_create_func: Callable[[], Any],
        match_flow_kwargs: dict,
        submitter_id: str,
        submitter_name: str,
        team_id: int
    ) -> Tuple[Any, Optional[Approval], Optional[str]]:
        """
        创建业务单据 + 自动提交审批（Contract/Payment 场景）

        流程：
        1. 创建业务单据（approval_phase = DRAFT）
        2. 匹配审批流程（捕获查询异常）
        3. 创建审批实例（create_approval_only，不 commit）
        4. 切换 approval_phase = PENDING_REVIEW
        5. adapter.on_submit() 触发原有 status 联动
        6. 统一 commit
        7. 异步发送通知（失败记录日志，提供补发入口）

        Returns:
            (entity, approval, error_message)
        """
        # TODO: 实现完整流程
        pass

    def submit_for_approval(
        self,
        db: Session,
        business_type: str,
        entity_id: int,
        team_id: int,
        submitter_id: str,
        submitter_name: str
    ) -> Tuple[Optional[Approval], Optional[str]]:
        """
        手动提交审批（Invoice/License 场景）

        流程：
        1. 获取业务单据（approval_phase 必须 = DRAFT 或 REJECTED）
        2. 如果 approval_phase = REJECTED，删除旧 Approval 实例
        3. 匹配审批流程（捕获查询异常）
        4. 创建新审批实例
        5. 切换 approval_phase = PENDING_REVIEW
        6. adapter.on_submit() 触发原有 status 联动
        7. 统一 commit
        8. 异步发送通知

        Returns:
            (approval, error_message)
        """
        # TODO: 实现完整流程
        pass

    def _send_notification_async(self, approval: Approval, entity: Any, team_id: int) -> None:
        """
        异步发送审批通知（失败不阻断业务流程）

        设计决策：
        1. 通知失败不阻断审批流程（业务数据已 commit）
        2. 失败记录日志（approval.id + entity.id）
        3. 提供手动补发入口（ApprovalService.resend_notification）
        """
        # TODO: 实现异步通知发送
        pass

    def resend_notification(self, approval_id: int, team_id: int) -> Tuple[bool, Optional[str]]:
        """
        手动补发审批通知（失败通知的补救入口）

        Returns:
            (success, error_message)
        """
        # TODO: 实现通知补发逻辑
        pass
```

### Task 1.1.2: 实现 create_with_approval 方法

- [ ] **Step 1: 实现 create_with_approval 核心逻辑**

在 `approval_transaction_manager.py` 中实现：

```python
def create_with_approval(
    self,
    db: Session,
    business_type: str,
    entity_create_func: Callable[[], Any],
    match_flow_kwargs: dict,
    submitter_id: str,
    submitter_name: str,
    team_id: int
) -> Tuple[Any, Optional[Approval], Optional[str]]:
    """创建业务单据 + 自动提交审批"""
    try:
        # 1. 创建业务单据（approval_phase = DRAFT）
        entity = entity_create_func()
        db.flush()  # 获取 entity.id

        # 2. 匹配审批流程（捕获查询异常）
        try:
            from app.crud.approval import approval_flow_crud
            flow = approval_flow_crud.match_flow(
                db,
                business_type=business_type,
                team_id=team_id,
                **match_flow_kwargs
            )
        except Exception as e:
            logger.error(f"审批流程查询失败: {e}")
            db.rollback()
            return (None, None, f"系统异常：审批流程查询失败，请稍后重试")

        # 3. 审批流程未匹配 → commit 单据，返回提示
        if flow is None:
            entity.approval_phase = ApprovalPhase.DRAFT
            db.commit()
            return (entity, None, "请先配置审批流程")

        # 4. 创建审批实例（不 commit）
        try:
            approval = approval_crud.create_approval_only(
                db,
                business_type=business_type,
                business_id=entity.id,
                team_id=team_id,
                flow=flow,
                submitter_id=submitter_id,
                submitter_name=submitter_name
            )
        except Exception as e:
            logger.error(f"审批创建失败: {e}")
            db.rollback()
            return (None, None, f"系统异常：审批创建失败，请稍后重试")

        # 5. 切换 approval_phase = PENDING_REVIEW
        entity.approval_phase = ApprovalPhase.PENDING_REVIEW

        # 6. adapter.on_submit() 触发原有 status 联动
        adapter = get_adapter(business_type)
        adapter.on_submit(db, entity)

        # 7. 统一 commit
        db.commit()
        db.refresh(entity)
        db.refresh(approval)

        # 8. 异步发送通知（失败不阻断）
        self._send_notification_async(approval, entity, team_id)

        return (entity, approval, None)

    except Exception as e:
        logger.error(f"create_with_approval 异常: {e}")
        db.rollback()
        return (None, None, f"系统异常：{str(e)}")
```

### Task 1.1.3: 实现 submit_for_approval 方法

- [ ] **Step 1: 实现 submit_for_approval 核心逻辑**

```python
def submit_for_approval(
    self,
    db: Session,
    business_type: str,
    entity_id: int,
    team_id: int,
    submitter_id: str,
    submitter_name: str
) -> Tuple[Optional[Approval], Optional[str]]:
    """手动提交审批（Invoice/License 场景）"""
    try:
        # 1. 获取业务单据
        adapter = get_adapter(business_type)
        entity = adapter.get_entity(db, entity_id, team_id)

        if entity is None:
            return (None, "业务单据不存在")

        # 2. 验证 approval_phase 必须 = DRAFT 或 REJECTED
        if entity.approval_phase not in [ApprovalPhase.DRAFT, ApprovalPhase.REJECTED]:
            return (None, "单据状态不允许提交审批")

        # 3. 如果 approval_phase = REJECTED，删除旧 Approval 实例
        if entity.approval_phase == ApprovalPhase.REJECTED:
            from app.crud.approval import approval_crud
            old_approval = approval_crud.get_by_entity(db, business_type, entity_id, team_id)
            if old_approval:
                db.delete(old_approval)

        # 4. 匹配审批流程
        match_kwargs = adapter.match_kwargs(entity)
        try:
            from app.crud.approval import approval_flow_crud
            flow = approval_flow_crud.match_flow(
                db,
                business_type=business_type,
                team_id=team_id,
                **match_kwargs
            )
        except Exception as e:
            logger.error(f"审批流程查询失败: {e}")
            db.rollback()
            return (None, f"系统异常：审批流程查询失败")

        if flow is None:
            return (None, "请先配置审批流程")

        # 5. 创建新审批实例
        approval = approval_crud.create_approval_only(
            db,
            business_type=business_type,
            business_id=entity.id,
            team_id=team_id,
            flow=flow,
            submitter_id=submitter_id,
            submitter_name=submitter_name
        )

        # 6. 切换 approval_phase = PENDING_REVIEW
        entity.approval_phase = ApprovalPhase.PENDING_REVIEW

        # 7. adapter.on_submit() 触发原有 status 联动
        adapter.on_submit(db, entity)

        # 8. 统一 commit
        db.commit()
        db.refresh(approval)

        # 9. 异步发送通知
        self._send_notification_async(approval, entity, team_id)

        return (approval, None)

    except Exception as e:
        logger.error(f"submit_for_approval 异常: {e}")
        db.rollback()
        return (None, f"系统异常：{str(e)}")
```

### Task 1.1.4: 实现异步通知发送逻辑

- [ ] **Step 1: 实现 _send_notification_async 方法**

```python
def _send_notification_async(self, approval: Approval, entity: Any, team_id: int) -> None:
    """异步发送审批通知（失败不阻断）"""
    try:
        # 使用后台任务发送通知
        from app.services.notification_service import notification_service
        notification_service.send_approval_notification(
            approval=approval,
            entity=entity,
            team_id=team_id
        )
    except Exception as e:
        # 记录日志，不阻断业务流程
        logger.error(
            f"审批通知发送失败（approval_id={approval.id}, entity_id={entity.id}）: {e}"
        )
```

- [ ] **Step 2: 实现 resend_notification 方法**

```python
def resend_notification(self, approval_id: int, team_id: int) -> Tuple[bool, Optional[str]]:
    """手动补发审批通知"""
    try:
        from app.crud.approval import approval_crud
        approval = approval_crud.get_by_id(db=None, approval_id=approval_id, team_id=team_id)

        if approval is None:
            return (False, "审批实例不存在")

        adapter = get_adapter(approval.business_type)
        entity = adapter.get_entity(db=None, business_id=approval.business_id, team_id=team_id)

        if entity is None:
            return (False, "业务单据不存在")

        self._send_notification_async(approval, entity, team_id)
        return (True, None)

    except Exception as e:
        logger.error(f"补发通知失败: {e}")
        return (False, f"系统异常：{str(e)}")
```

---

## v1.2: Approval Engine 联动 approval_phase

**Files:**
- Modify: `CRM-Server/app/api/approvals.py`

**Reference:** Spec §4（Approval Engine 的 approval_phase 联动逻辑）

### Task 1.2.1: 修改 approve 方法联动 approval_phase

- [ ] **Step 1: 读取 approvals.py 文件**

Read: `CRM-Server/app/api/approvals.py`

- [ ] **Step 2: 在 approve 方法中添加 approval_phase 切换逻辑**

找到 approve 函数，修改核心逻辑：

```python
def approve(db: Session, approval_id: int, ...) -> Tuple[Optional[Approval], Optional[str]]:
    """审批通过（支持多级审批）"""
    # ... 现有逻辑 ...

    # 判断是否最后节点
    is_last_node = (approval.current_node_id == flow.nodes[-1].id)

    if is_last_node:
        # Approval.status = APPROVED
        approval.status = ApprovalStatus.APPROVED

        # 切换 entity.approval_phase = APPROVED
        adapter = get_adapter(approval.business_type)
        entity = adapter.get_entity(db, approval.business_id, approval.team_id)
        if entity:
            entity.approval_phase = ApprovalPhase.APPROVED
            adapter.on_approved(db, entity)

    # else: 移动到下一节点，approval_phase 保持 PENDING_REVIEW

    db.commit()
    # ...
```

### Task 1.2.2: 修改 reject 方法联动 approval_phase

- [ ] **Step 1: 在 reject 方法中添加 approval_phase 切换逻辑**

```python
def reject(db: Session, approval_id: int, ...) -> Tuple[Optional[Approval], Optional[str]]:
    """审批拒绝"""
    # ... 现有逻辑 ...

    # Approval.status = REJECTED
    approval.status = ApprovalStatus.REJECTED

    # 切换 entity.approval_phase = REJECTED
    adapter = get_adapter(approval.business_type)
    entity = adapter.get_entity(db, approval.business_id, approval.team_id)
    if entity:
        entity.approval_phase = ApprovalPhase.REJECTED
        adapter.on_rejected(db, entity)

    db.commit()
    # ...
```

### Task 1.2.3: 修改 cancel 方法联动 approval_phase

- [ ] **Step 1: 在 cancel 方法中添加 approval_phase 切换逻辑**

```python
def cancel(db: Session, approval_id: int, ...) -> Tuple[Optional[Approval], Optional[str]]:
    """撤回审批"""
    # ... 现有逻辑 ...

    # Approval.status = REJECTED（撤回视为拒绝）
    approval.status = ApprovalStatus.REJECTED

    # 切换 entity.approval_phase = DRAFT（允许重新提交）
    adapter = get_adapter(approval.business_type)
    entity = adapter.get_entity(db, approval.business_id, approval.team_id)
    if entity:
        entity.approval_phase = ApprovalPhase.DRAFT
        adapter.on_cancelled(db, entity)

    db.commit()
    # ...
```

---

## v1.3: Adapter 状态切换调整

**Files:**
- Modify: `CRM-Server/app/services/approval_adapter.py`

**Reference:** Spec §3.2（Adapter 状态切换调整）

### Task 1.3.1: 调整 ContractAdapter

- [ ] **Step 1: 修改 ContractAdapter.on_rejected**

保持 approval_phase 由 Approval Engine 管理，此处不切原有 status：

```python
def on_rejected(self, db, entity):
    if entity is None: return
    # approval_phase 切换由 Approval Engine 管理
    # 此处不切换原有 status（保持 PENDING_REVIEW）
    # 不做任何操作
    pass
```

### Task 1.3.2: 调整 PaymentRecordAdapter

- [ ] **Step 1: 修改 PaymentRecordAdapter.on_rejected**

```python
def on_rejected(self, db, entity):
    if entity is None: return
    # approval_phase 切换由 Approval Engine 管理
    # 此处不切换 confirmation_status（保持 PENDING）
    pass
```

- [ ] **Step 2: 修改 PaymentRecordAdapter.on_cancelled**

```python
def on_cancelled(self, db, entity):
    if entity is None: return
    # approval_phase 切换由 Approval Engine 管理
    # 此处切回 DRAFT（允许重新提交）
    entity.confirmation_status = PaymentConfirmationStatus.DRAFT
```

### Task 1.3.3: 调整 InvoiceApplicationAdapter

- [ ] **Step 1: 修改 InvoiceApplicationAdapter.on_rejected**

Invoice 驳回后显示 REJECTED：

```python
def on_rejected(self, db, entity):
    if entity is None: return
    # approval_phase 切换由 Approval Engine 管理
    # Invoice 驳回后显示 REJECTED
    entity.status = InvoiceApplicationStatus.REJECTED
    entity.reviewed_time = func.now()
```

### Task 1.3.4: 调整 LicenseApplicationAdapter

- [ ] **Step 1: 修改 LicenseApplicationAdapter.on_submit**

统一命名 PENDING → PENDING_REVIEW：

```python
def on_submit(self, db, entity):
    if entity is None: return
    entity.status = LicenseApplicationStatus.PENDING_REVIEW
```

---

## v1.4: 前端状态判断逻辑调整

**Files:**
- Modify: 前端文件（20+ 处状态判断逻辑）

**Reference:** Spec §5.3（前端改动清单）

**注意:** 前端改动涉及多个文件，需要逐个调整。这里只列出核心改动原则。

### Task 1.4.1: 前端状态判断逻辑统一

- [ ] **Step 1: 从 `status === 'PENDING'` 改为 `approval_phase === 'pending_review'`**

所有前端文件中涉及审批状态判断的逻辑，统一改为：

```javascript
// 旧逻辑
if (entity.status === 'PENDING') {
  // ...
}

// 新逻辑
if (entity.approval_phase === 'pending_review') {
  // ...
}
```

- [ ] **Step 2: 审批状态徽章显示逻辑**

```javascript
function getApprovalBadgeColor(entity) {
  switch (entity.approval_phase) {
    case 'draft': return 'gray';
    case 'pending_review': return 'blue';
    case 'approved': return 'green';
    case 'rejected': return 'red';
  }
}
```

- [ ] **Step 3: 按钮状态判断逻辑**

```javascript
function canSubmitApproval(entity) {
  return entity.approval_phase === 'draft';
}

function canResubmitApproval(entity) {
  return entity.approval_phase === 'rejected';
}
```

---

## v1.5: 删除免审批直通逻辑

**Files:**
- Modify: `CRM-Server/app/crud/crud_license_application.py`

**Reference:** Spec §5.2（文件改动清单）

### Task 1.5.1: 删除 License 免审批直通逻辑

- [ ] **Step 1: 读取 crud_license_application.py 文件**

Read: `CRM-Server/app/crud/crud_license_application.py`

- [ ] **Step 2: 删除免审批直通逻辑**

找到免审批直通的代码逻辑，删除或注释掉，改为使用 ApprovalTransactionManager。

---

## v1.6: 测试用例编写

**Files:**
- Create: `CRM-Server/tests/unit/approval/test_transaction_manager.py`

**Reference:** Spec §5.4（测试计划）

### Task 1.6.1: 编写 ApprovalTransactionManager 单元测试

- [ ] **Step 1: 创建测试文件骨架**

```python
# tests/unit/approval/test_transaction_manager.py

import pytest
from sqlalchemy.orm import Session
from app.services.approval_transaction_manager import ApprovalTransactionManager
from app.constants.approval_phase import ApprovalPhase


class TestApprovalTransactionManager:
    """ApprovalTransactionManager 单元测试"""

    @pytest.fixture
    def transaction_manager(self):
        return ApprovalTransactionManager()

    # TODO: 编写完整测试用例
```

- [ ] **Step 2: 编写 create_with_approval 测试用例**

```python
def test_create_with_approval_success(self, db: Session, transaction_manager):
    """测试创建单据 + 审批成功"""
    # ...

def test_create_with_approval_no_flow(self, db: Session, transaction_manager):
    """测试审批流程未匹配"""
    # ...

def test_create_with_approval_flow_query_failure(self, db: Session, transaction_manager):
    """测试审批流程查询失败"""
    # ...
```

- [ ] **Step 3: 编写 submit_for_approval 测试用例**

```python
def test_submit_for_approval_success(self, db: Session, transaction_manager):
    """测试手动提交审批成功"""
    # ...

def test_submit_for_approval_resubmit_after_rejected(self, db: Session, transaction_manager):
    """测试驳回后重新提交"""
    # ...
```

- [ ] **Step 4: 编写 Approval Engine 联动测试**

```python
def test_approve_phase_transition(self, db: Session):
    """测试审批通过 approval_phase 流转"""
    # ...

def test_reject_phase_transition(self, db: Session):
    """测试审批拒绝 approval_phase 流转"""
    # ...

def test_cancel_phase_transition(self, db: Session):
    """测试撤回审批 approval_phase 流转"""
    # ...
```

---

## Testing Plan

### 测试场景清单

| 测试场景 | 验证点 | 优先级 |
|---------|-------|--------|
| 创建单据 + 审批成功 | approval_phase 正确流转 | HIGH |
| 审批流程未匹配 | 单据保留（approval_phase = draft） | HIGH |
| 审批创建失败 | rollback，单据未创建 | HIGH |
| 通知发送失败 | 不阻断业务，approval_phase 正确 | MEDIUM |
| 多级审批流转 | approval_phase 保持 pending_review | HIGH |
| 审批通过/拒绝/撤回 | approval_phase 和原有 status 联动正确 | HIGH |
| 驳回后重新提交 | approval_phase 流转正确，旧 Approval 删除 | HIGH |
| 数据迁移验证 | 历史数据 approval_phase 映射正确 | HIGH |

---

## Deployment Plan

### 部署步骤

1. **Pre-deployment Check**
   - 确认所有模型文件已修改
   - 确认迁移脚本已创建
   - 确认测试通过

2. **Deployment Sequence**
   - Step 1: 执行数据库迁移（alembic upgrade head）
   - Step 2: 部署后端代码（ApprovalTransactionManager + Approval Engine）
   - Step 3: 部署前端代码（状态判断逻辑调整）
   - Step 4: 验证端到端流程

3. **Rollback Plan**
   - 如迁移失败：alembic downgrade head
   - 如代码部署失败：回滚到上一版本

---

## Progress Tracking

| 版本 | 状态 | 完成时间 |
|------|------|---------|
| v1.0 | ⏳ 待开始 | — |
| v1.1 | ⏳ 待开始 | — |
| v1.2 | ⏳ 待开始 | — |
| v1.3 | ⏳ 待开始 | — |
| v1.4 | ⏳ 待开始 | — |
| v1.5 | ⏳ 待开始 | — |
| v1.6 | ⏳ 待开始 | — |

---

**Plan Version:** v1.0
**Created:** 2026-07-08
**Author:** Claude
**Status:** Ready for Implementation