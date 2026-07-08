# ApprovalTransactionManager 重构设计方案（拒绝妥协版）

**方案选择：方案 1 - 单表单状态系统（激进重构）**

---

## 设计背景

### 原始设计方案的问题诊断

原始设计方案（`docs/superpowers/specs/2026-07-08-approval-transaction-manager-design.md`）因"最小改动"妥协导致以下系统性问题：

| 问题 | 严重性 | 原因 |
|------|--------|------|
| **ApprovalPhase 作为"逻辑枚举"** | CRITICAL | 双重状态系统维护成本高，开发者易混淆 |
| **数据迁移不完整** | HIGH | 只考虑未提交审批，漏掉审批拒绝/撤回的状态迁移 |
| **异常处理分支缺失** | HIGH | 只考虑"未匹配"，未考虑查询失败、通知失败等场景 |
| **代码重复风险** | MEDIUM | create_approval_only 复制逻辑而非委托通用方法 |
| **历史数据兼容性缺失** | MEDIUM | 删除免审批直通后，历史数据无处理方案 |

### 业务规则确认

| 规则 | 说明 |
|------|------|
| **强制审批** | 所有单据（合同/回款/发票/License）必须走审批流程 |
| **审批未匹配处理** | 报错提示，保留单据，approval_phase = DRAFT |
| **审批失败处理** | 保留单据，approval_phase = REJECTED，用户可重新提交 |
| **无免审批直通** | 删除当前 LICENSE/INVOICE 的免审批直通逻辑 |
| **状态系统彻底统一** | ApprovalPhase 作为数据库字段，拒绝"最小改动"妥协 |

---

## 核心设计决策

### 方案 1：单表单状态系统

**核心设计**：
- **彻底统一状态系统**：ApprovalPhase 作为数据库字段（新增 approval_phase 列），直接映射到数据库
- **原有 status 字段保留语义分离**：Contract.status 仍表示合同生命周期（DRAFT/SIGNED/EFFECTIVE），Payment.confirmation_status 仍表示回款确认（DRAFT/PENDING/CONFIRMED/DISPUTED）
- **双字段职责分离**：approval_phase 专注审批流程，原有 status 保留业务语义

**关键改进**：
1. 拒绝"最小改动"妥协 - approval_phase 不再是"逻辑枚举"，而是数据库字段
2. 审批流程与业务语义解耦 - 审批系统可独立演进，不影响业务逻辑
3. 前端统一性 - 审批列表、审批统计等场景统一使用 approval_phase
4. 业务语义完整 - 原有 status 承载完整业务生命周期

---

## 第一部分：核心架构设计

### 1.1 ApprovalPhase 统一状态枚举（数据库直接映射）

```python
# app/constants/approval_phase.py

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
        mapping = {
            ApprovalStatus.PENDING: cls.PENDING_REVIEW,
            ApprovalStatus.APPROVED: cls.APPROVED,
            ApprovalStatus.REJECTED: cls.REJECTED,
        }
        return mapping.get(approval_status, cls.DRAFT)
```

### 1.2 数据库新增 approval_phase 字段

**新增字段（所有业务单据表）**：

```python
# 所有业务单据模型（Contract/Payment/Invoice/License）新增字段

approval_phase = Column(
    String(20), 
    nullable=False, 
    default=ApprovalPhase.DRAFT,
    comment="审批流程状态：draft/pending_review/approved/rejected"
)
```

**原有 status 字段保留语义分离**：

| 业务单据 | 原有 status 字段 | 新增 approval_phase 字段 | 语义分离说明 |
|---------|-----------------|------------------------|-------------|
| Contract | ContractStatus（生命周期：DRAFT/SIGNED/EFFECTIVE） | ApprovalPhase | 合同生命周期 vs 审批流程状态 |
| Payment | PaymentConfirmationStatus（确认状态：DRAFT/PENDING/CONFIRMED/DISPUTED） | ApprovalPhase | 回款确认语义 vs 审批流程状态 |
| Invoice | InvoiceApplicationStatus（开票状态：DRAFT/PENDING_REVIEW/APPROVED/ISSUED） | ApprovalPhase | 开票流程 vs 审批流程状态 |
| License | LicenseApplicationStatus（申请状态：DRAFT/PENDING_REVIEW/APPROVED/ISSUED） | ApprovalPhase | License 申请 vs 审批流程状态 |

---

## 第二部分：ApprovalTransactionManager 核心类设计

### 2.1 核心职责与设计原则

```python
# app/services/approval_transaction_manager.py

class ApprovalTransactionManager:
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
```

### 2.2 create_with_approval 方法（自动审批场景）

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
    
    异常处理（完整分支）：
    - match_flow 查询失败 → rollback，返回（None, None, "系统异常：审批流程查询失败")
    - 审批流程未匹配 → commit 单据，返回（entity, None, "请先配置审批流程")
    - create_approval 失败 → rollback，返回（None, None, "系统异常：审批创建失败")
    - 通知发送失败 → 不阻断，记录日志，返回
    
    Returns:
        (entity, approval, error_message)
    """
```

### 2.3 submit_for_approval 方法（手动审批场景）

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
    """
    手动提交审批（Invoice/License 场景）
    
    流程：
    1. 获取业务单据（approval_phase 必须 = DRAFT 或 REJECTED）
    2. 如果 approval_phase = REJECTED，删除旧 Approval 实例（避免重复审批）
    3. 匹配审批流程（捕获查询异常）
    4. 创建新审批实例
    5. 切换 approval_phase = PENDING_REVIEW
    6. adapter.on_submit() 触发原有 status 联动
    7. 统一 commit
    8. 异步发送通知
    
    Returns:
        (approval, error_message)
    """
```

### 2.4 通知发送机制（失败不阻断，提供补发入口）

```python
def _send_notification_async(...) -> None:
    """
    异步发送审批通知（失败不阻断业务流程）
    
    设计决策：
    1. 通知失败不阻断审批流程（业务数据已 commit）
    2. 失败记录日志（approval.id + entity.id）
    3. 提供手动补发入口（ApprovalService.resend_notification）
    """

def resend_notification(approval_id: int, team_id: int) -> Tuple[bool, Optional[str]]:
    """
    手动补发审批通知（失败通知的补救入口）
    """
```

---

## 第三部分：ApprovalCRUD 改造与 Adapter 状态切换调整

### 3.1 ApprovalCRUD 改造（避免代码重复）

```python
# app/crud/approval.py

class ApprovalCRUD:
    def _create_approval_impl(
        self,
        db: Session,
        business_type: str,
        business_id: int,
        team_id: int,
        flow: ApprovalFlow,
        submitter_id: str,
        submitter_name: str,
        auto_commit: bool = False
    ) -> Approval:
        """
        审批实例创建核心实现（避免代码重复）
        
        流程：
        1. 获取业务单据（验证存在）
        2. 获取 contract_id（兼容旧外键字段）
        3. 补充 submitter_name
        4. 获取首个审批节点
        5. 创建 Approval 实例
        6. 创建 ApprovalRecord(SUBMIT)
        7. 回写 entity.approval_id
        
        Returns:
            Approval: 审批实例（已 flush，未 commit）
        """
    
    def create_approval_only(...) -> Approval:
        """
        创建审批实例（不执行 commit）
        
        委托 _create_approval_impl(auto_commit=False)
        """
    
    def create_approval_generic(...) -> Approval:
        """
        创建审批实例（自动 commit）
        
        委托 _create_approval_impl(auto_commit=True)
        注意：此处自动切 approval_phase 和原有 status（兼容旧调用方）
        """
```

### 3.2 Adapter 状态切换调整

```python
# app/services/approval_adapter.py

class ContractAdapter:
    def on_submit(self, db, entity):
        """提交审批时的状态切换"""
        # approval_phase 切换由 TransactionManager 管理
        # 此处只切换原有 status（保持业务语义）
        entity.status = ContractStatus.PENDING_REVIEW
    
    def on_approved(self, db, entity):
        """审批通过时的状态切换"""
        # approval_phase 切换由 Approval Engine 管理
        # 此处只切换原有 status（业务终态）
        entity.status = ContractStatus.SIGNED
    
    def on_rejected(self, db, entity):
        """审批拒绝时的状态切换"""
        # approval_phase 切换由 Approval Engine 管理
        # 此处不切换原有 status（保持原状态）
        pass
    
    def on_cancelled(self, db, entity):
        """撤回审批时的状态切换"""
        # approval_phase 切换由 Approval Engine 管理
        # 此处不切换原有 status
        pass

class PaymentRecordAdapter:
    def on_submit(self, db, entity):
        entity.confirmation_status = PaymentConfirmationStatus.PENDING
    
    def on_approved(self, db, entity):
        entity.confirmation_status = PaymentConfirmationStatus.CONFIRMED
    
    def on_rejected(self, db, entity):
        # 不切换 confirmation_status（保持 PENDING）
        pass
    
    def on_cancelled(self, db, entity):
        # 撤回后切回 DRAFT（允许重新提交）
        entity.confirmation_status = PaymentConfirmationStatus.DRAFT

class InvoiceApplicationAdapter:
    def on_rejected(self, db, entity):
        # Invoice 驳回后显示 REJECTED
        entity.status = InvoiceApplicationStatus.REJECTED
    
    def on_cancelled(self, db, entity):
        # 撤回后回退到 DRAFT
        entity.status = InvoiceApplicationStatus.DRAFT

class LicenseApplicationAdapter:
    def on_submit(self, db, entity):
        # 统一命名：PENDING → PENDING_REVIEW
        entity.status = LicenseApplicationStatus.PENDING_REVIEW
    
    def on_approved(self, db, entity):
        # 不切换 status（审批人手动设置 ISSUED）
        pass
    
    def on_rejected(self, db, entity):
        entity.status = LicenseApplicationStatus.REJECTED
```

---

## 第四部分：Approval Engine 的 approval_phase 联动逻辑

### 4.1 Approval Engine 审批流转改造

```python
# app/api/approvals.py

def approve(db: Session, approval_id: int, ...) -> Tuple[Optional[Approval], Optional[str]]:
    """
    审批通过（支持多级审批）
    
    流程：
    1. 验证审批实例存在且状态为 PENDING
    2. 创建 ApprovalRecord(APPROVE)
    3. 判断是否最后节点：
       - 是：Approval.status = APPROVED，切换 entity.approval_phase = APPROVED
       - 否：移动到下一节点，approval_phase 保持 PENDING_REVIEW
    4. adapter.on_approved() 触发原有 status 联动
    5. 发送通知
    6. 统一 commit
    """

def reject(db: Session, approval_id: int, ...) -> Tuple[Optional[Approval], Optional[str]]:
    """
    审批拒绝（多级审批任一级拒绝）
    
    流程：
    1. 验证审批实例存在且状态为 PENDING
    2. 创建 ApprovalRecord(REJECT)
    3. Approval.status = REJECTED
    4. 切换 entity.approval_phase = REJECTED
    5. adapter.on_rejected() 触发原有 status 联动
    6. 发送通知给申请人
    7. 统一 commit
    """

def cancel(db: Session, approval_id: int, ...) -> Tuple[Optional[Approval], Optional[str]]:
    """
    撤回审批（申请人撤回）
    
    流程：
    1. 验证审批实例存在且状态为 PENDING
    2. 创建 ApprovalRecord(CANCEL)
    3. Approval.status = REJECTED（撤回视为拒绝）
    4. 切换 entity.approval_phase = DRAFT（允许重新提交）
    5. adapter.on_cancelled() 触发原有 status 联动
    6. 统一 commit
    """
```

### 4.2 审批拒绝后重新提交的处理逻辑

```python
def submit_for_approval(...) -> Tuple[Optional[Approval], Optional[str]]:
    """
    手动提交审批（支持驳回后重新提交）
    
    流程：
    1. 获取业务单据（approval_phase 必须 = DRAFT 或 REJECTED）
    2. 如果 approval_phase = REJECTED，删除旧 Approval 实例（避免重复审批）
    3. 匹配审批流程
    4. 创建新审批实例
    5. 切换 approval_phase = PENDING_REVIEW
    6. adapter.on_submit() 触发原有 status 联动
    7. 统一 commit
    """
```

### 4.3 approval_phase 状态流转完整图

```
┌─────────────────────────────────────────────────────────────────────┐
│                ApprovalPhase 状态流转（方案 1：单表单状态系统）          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  用户创建单据 → approval_phase = DRAFT                              │
│                                                                     │
│  提交审批（TransactionManager）                                      │
│  approval_phase = DRAFT → PENDING_REVIEW                           │
│  Approval.status = PENDING                                          │
│  adapter.on_submit() 切原有 status                                  │
│                                                                     │
│  多级审批流转（Approval.current_node_id 移动）                       │
│  approval_phase 保持 PENDING_REVIEW                                 │
│                                                                     │
│  最后节点通过                                                         │
│  approval_phase = PENDING_REVIEW → APPROVED                        │
│  Approval.status = APPROVED                                         │
│  adapter.on_approved() 切原有 status                                │
│                                                                     │
│  任一级拒绝                                                           │
│  approval_phase = PENDING_REVIEW → REJECTED                        │
│  Approval.status = REJECTED                                         │
│  adapter.on_rejected() 切原有 status                                │
│                                                                     │
│  撤回审批                                                             │
│  approval_phase = PENDING_REVIEW → DRAFT                           │
│  Approval.status = REJECTED                                         │
│  adapter.on_cancelled() 切原有 status                               │
│                                                                     │
│  驳回后重新提交                                                       │
│  approval_phase = REJECTED → DRAFT → PENDING_REVIEW                │
│  删除旧 Approval 实例                                                │
│  创建新 Approval 实例                                                │
│                                                                     │
│  注：ApprovalPhase 专注审批流程                                      │
│      原有 status 保留业务语义                                        │
│      两者分离，各有职责                                              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 第五部分：数据迁移方案与文件改动清单

### 5.1 数据库迁移方案

```python
# migrations/versions/020_add_approval_phase_field.py

"""
ApprovalPhase 统一状态字段迁移

改动范围：
1. 所有业务单据表新增 approval_phase 字段
2. 数据迁移：将原有 status 映射到 approval_phase
3. 紧急修复：Payment 驳回后状态修正
4. 紧急修复：License 审批拒绝但 status = PENDING
"""

def upgrade():
    # 1. 新增 approval_phase 字段（所有业务单据表）
    # ...
    
    # 2. 数据迁移：Contract（status → approval_phase）
    op.execute("""
        UPDATE crm_contracts
        SET approval_phase = CASE
            WHEN status = 'DRAFT' THEN 'draft'
            WHEN status = 'PENDING_REVIEW' THEN 'pending_review'
            WHEN status IN ('SIGNED', 'EFFECTIVE', 'EXPIRED', 'TERMINATED') THEN 'approved'
            ELSE 'draft'
        END
    """)
    
    # 3. 数据迁移：Payment（confirmation_status → approval_phase）
    # 关键修复：审批拒绝的 PENDING → rejected
    op.execute("""
        -- 未提交审批的 PENDING → draft
        UPDATE crm_payment_records
        SET approval_phase = 'draft'
        WHERE confirmation_status = 'PENDING' AND approval_id IS NULL
        
        -- 审批中的 PENDING → pending_review
        UPDATE crm_payment_records pr
        SET approval_phase = 'pending_review'
        FROM crm_approvals a
        WHERE pr.approval_id = a.id AND a.status = 'PENDING'
        
        -- 审批通过的 CONFIRMED → approved
        UPDATE crm_payment_records
        SET approval_phase = 'approved'
        WHERE confirmation_status = 'CONFIRMED'
        
        -- 审批拒绝的 PENDING → rejected（关键修复）
        UPDATE crm_payment_records pr
        SET approval_phase = 'rejected'
        FROM crm_approvals a
        WHERE pr.approval_id = a.id AND a.status = 'REJECTED'
        
        -- 有争议的 DISPUTED → rejected
        UPDATE crm_payment_records
        SET approval_phase = 'rejected'
        WHERE confirmation_status = 'DISPUTED'
    """)
    
    # 4. 数据迁移：Invoice（status → approval_phase）
    # ...
    
    # 5. 数据迁移：License（status → approval_phase）
    # 关键修复：审批拒绝但 status = PENDING → rejected
    # ...
```

### 5.2 文件改动清单

| 文件路径 | 改动类型 | 改动内容 |
|---------|---------|---------|
| `app/constants/approval_phase.py` | 新增 | ApprovalPhase 统一状态枚举 |
| `app/services/approval_transaction_manager.py` | 新增 | ApprovalTransactionManager 核心类 |
| `app/models/contract.py` | 修改 | 新增 approval_phase 字段 |
| `app/models/payment.py` | 修改 | 新增 approval_phase 字段，PaymentConfirmationStatus 新增 DRAFT |
| `app/models/invoice.py` | 修改 | 新增 approval_phase 字段 |
| `app/models/license_application.py` | 修改 | 新增 approval_phase 字段，PENDING → PENDING_REVIEW |
| `app/crud/approval.py` | 修改 | ApprovalCRUD 改造（_create_approval_impl） |
| `app/crud/payment.py` | 修改 | 删除内部 commit，使用 TransactionManager |
| `app/crud/contract.py` | 修改 | 删除内部 commit，使用 TransactionManager |
| `app/crud/crud_license_application.py` | 修改 | 删除免审批直通，使用 TransactionManager |
| `app/api/approvals.py` | 修改 | 审批流转联动 approval_phase |
| `app/services/approval_adapter.py` | 修改 | Adapter 状态切换调整 |
| `migrations/versions/020_add_approval_phase_field.py` | 新增 | 数据迁移脚本 |

### 5.3 前端改动清单

| 前端改动点 | 改动内容 | 影响范围 |
|-----------|---------|---------|
| 状态判断逻辑 | 从 `status === 'PENDING'` 改为 `approval_phase === 'pending_review'` | 20+ 处 |
| 审批状态徽章 | 根据 approval_phase 显示颜色和文本 | 所有单据详情页 |
| 按钮状态判断 | approval_phase 判断是否可点击 | 所有单据详情页 |
| 错误提示处理 | 新增审批流程未配置提示 | 提交审批失败时 |

### 5.4 测试计划

| 测试场景 | 验证点 |
|---------|-------|
| 创建单据 + 审批成功 | approval_phase 正确流转 |
| 审批流程未匹配 | 单据保留（approval_phase = draft） |
| 审批创建失败 | rollback，单据未创建 |
| 通知发送失败 | 不阻断业务，approval_phase 正确 |
| 多级审批流转 | approval_phase 保持 pending_review |
| 审批通过/拒绝/撤回 | approval_phase 和原有 status 联动正确 |
| 驳回后重新提交 | approval_phase 流转正确，旧 Approval 删除 |
| 数据迁移验证 | 历史数据 approval_phase 映射正确 |

### 5.5 版本规划

| 版本 | 内容 | 预估时间 |
|------|------|---------|
| v1.0 | 数据库迁移（新增 approval_phase 字段） | 1 天 |
| v1.1 | ApprovalTransactionManager 核心类 | 2 天 |
| v1.2 | Approval Engine 联动 approval_phase | 1 天 |
| v1.3 | Adapter 状态切换调整 | 1 天 |
| v1.4 | 前端状态判断逻辑调整 | 2 天 |
| v1.5 | 删除免审批直通逻辑 | 1 天 |
| v1.6 | 测试用例编写 | 2 天 |
| 总计 | — | **10 天** |

---

## 第六部分：ApprovalPhase 与原有 status 的语义分离详细说明

### 6.1 双字段职责分离原则

```
ApprovalPhase（审批流程状态）：
- 专注审批流程：draft → pending_review → approved/rejected
- 由 ApprovalTransactionManager 和 Approval Engine 管理
- 所有业务单据统一命名（彻底拒绝妥协）
- 前端审批相关逻辑统一使用此字段

原有 status（业务语义状态）：
- 保留各自业务语义
- 由 adapter.on_submit/on_approved/on_rejected/on_cancelled 管理
- 各业务单据保持独特语义
- 前端业务详情显示使用此字段

职责分离的核心价值：
1. 避免"最小改动"妥协：ApprovalPhase 作为数据库字段
2. 审批流程与业务语义解耦：审批系统可独立演进
3. 前端统一性：审批列表、审批统计统一使用 approval_phase
4. 业务语义完整：原有 status 承载完整业务生命周期
```

### 6.2 各业务单据的双字段联动规则

| 业务单据 | approval_phase | 原有 status | 联动规则 |
|---------|--------------|------------|---------|
| Contract | draft → pending_review → approved | DRAFT → PENDING_REVIEW → SIGNED | adapter.on_approved 切业务终态 |
| Contract 驳回 | rejected | PENDING_REVIEW（不变） | adapter.on_rejected 不切 status |
| Payment | draft → pending_review → approved | DRAFT → PENDING → CONFIRMED | adapter.on_approved 切业务终态 |
| Payment 驳回 | rejected | PENDING（不变） | adapter.on_rejected 不切 status |
| Payment 撤回 | draft | DRAFT（切回） | adapter.on_cancelled 切回 DRAFT |
| Invoice | draft → pending_review → approved | DRAFT → PENDING_REVIEW → APPROVED | adapter.on_approved 切业务中间态 |
| Invoice 驳回 | rejected | REJECTED | adapter.on_rejected 切 status |
| License | draft → pending_review → approved | DRAFT → PENDING_REVIEW → APPROVED | adapter.on_approved 不切 status |
| License 审批人填写 | approved | ISSUED | 审批人手动设置 |

### 6.3 前端双字段显示指南

```javascript
// 审批状态徽章（统一使用 approval_phase）
function getApprovalBadgeColor(entity) {
  switch (entity.approval_phase) {
    case 'draft': return 'gray';
    case 'pending_review': return 'blue';
    case 'approved': return 'green';
    case 'rejected': return 'red';
  }
}

// 业务状态显示（使用原有 status）
function getContractStatusDisplay(contract) {
  switch (contract.status) {
    case 'DRAFT': return '草稿';
    case 'SIGNED': return '已签署';
    case 'EFFECTIVE': return '生效中';
    // ...
  }
}

// 按钮状态判断（统一使用 approval_phase）
function canSubmitApproval(entity) {
  return entity.approval_phase === 'draft';
}

function canResubmitApproval(entity) {
  return entity.approval_phase === 'rejected';
}
```

### 6.4 常见问题 FAQ

**Q1: 为什么需要双字段？**

A: 职责分离原则。ApprovalPhase 专注审批流程，原有 status 承载业务语义。

**Q2: approval_phase 和原有 status 是否有冲突？**

A: 无冲突。两者职责明确，联动规则清晰。

**Q3: 前端应该使用哪个字段判断审批状态？**

A: 统一使用 approval_phase。

**Q4: 前端应该使用哪个字段显示业务状态？**

A: 使用原有 status（Contract.status, Payment.confirmation_status 等）。

**Q5: 审批拒绝后，原有 status 如何处理？**

A: 各业务单据不同。Contract/Payment 不变，Invoice/License 切为 REJECTED。

**Q6: 用户重新提交审批时，原有 status 如何处理？**

A: adapter.on_submit 再次触发。

**Q7: 多级审批中间节点通过时，approval_phase 是否变化？**

A: 不变，保持 pending_review。只有最后节点通过才切 approved。

**Q8: 数据迁移如何处理历史数据？**

A: 见 5.1 数据迁移方案。覆盖未提交、审批中、审批通过、审批拒绝、撤回等所有场景。

---

## 关键决策总结

1. **方案 1：单表单状态系统** - approval_phase 作为数据库字段，彻底拒绝妥协
2. **双字段职责分离** - ApprovalPhase 专注审批流程，原有 status 保留业务语义
3. **ApprovalTransactionManager 核心职责** - 事务原子性 + approval_phase 状态流转
4. **异常处理完整分支** - match_flow 查询失败、未匹配、create_approval 失败、通知失败全覆盖
5. **数据迁移方案** - 新增 approval_phase 字段 + 历史数据映射 + 紧急修复
6. **前端改动范围** - 20+ 处状态判断逻辑统一使用 approval_phase
7. **版本规划** - 7 个版本，总计 10 天

---

**设计文档版本：v2.0（拒绝妥协版）**
**创建时间：2026-07-08**
**作者：Claude**