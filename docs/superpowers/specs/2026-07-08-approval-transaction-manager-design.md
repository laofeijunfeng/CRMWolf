# ApprovalTransactionManager 架构设计文档

## 设计背景

### 问题诊断

当前 CRM-Server 审批模块存在以下 Critical 问题：

| 问题 | 严重性 | 影响 |
|------|--------|------|
| **事务边界断裂** | CRITICAL | 业务单据与审批实例分别提交，无法原子性保证 |
| **审批失败无回滚** | CRITICAL | PAYMENT 审批失败后，单据已持久化，产生孤儿数据 |
| **状态命名不一致** | HIGH | PENDING vs PENDING_REVIEW，缺少 DRAFT 状态 |
| **免审批直通逻辑** | HIGH | LICENSE/INVOICE 未匹配审批流程时直通，不符合业务规则 |
| **异常处理缺失** | MEDIUM | CONTRACT 审批失败静默吞掉，用户无感知 |

### 业务规则确认

| 规则 | 说明 |
|------|------|
| **强制审批** | 所有单据（合同/回款/发票/License）必须走审批流程 |
| **审批未匹配处理** | 报错提示，保留单据，状态为 DRAFT（待提交审批） |
| **审批失败处理** | 保留单据，状态为 DRAFT，用户可重新提交 |
| **无免审批直通** | 删除当前 LICENSE/INVOICE 的免审批直通逻辑 |
| **状态统一** | 所有业务单据审批流程状态统一命名 |

---

## 设计目标

1. **事务原子性**：单据创建与审批创建在同一事务中完成
2. **状态一致性**：统一所有业务单据的审批流程状态命名
3. **异常友好**：审批失败时保留单据，提供清晰的错误提示
4. **架构统一**：所有审批入口通过 ApprovalTransactionManager

---

## 核心设计

### 1. ApprovalTransactionManager 类设计

```python
# app/services/approval_transaction_manager.py

class ApprovalTransactionManager:
    """
    审批事务管理器
    
    负责管理所有业务单据的审批创建流程，确保事务原子性。
    
    设计原则：
    1. 单据创建与审批创建在同一事务中
    2. 审批失败时保留单据，状态回退到 DRAFT
    3. 通知发送在事务成功后异步执行
    4. 所有审批入口统一通过此管理器
    """
    
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
        创建业务单据 + 自动提交审批
        
        用于自动审批场景（创建单据后立即审批）
        
        Args:
            db: 数据库会话
            business_type: 业务类型（CONTRACT/PAYMENT/INVOICE/LICENSE）
            entity_create_func: 业务单据创建函数（不执行 commit）
            match_flow_kwargs: 审批流程匹配参数
            submitter_id: 提交人 ID
            submitter_name: 提交人姓名
            team_id: 团队 ID
            
        Returns:
            (entity, approval, error_message)
            - entity: 业务单据（失败时为 None）
            - approval: 审批实例（未匹配流程时为 None）
            - error_message: 错误信息（成功时为 None）
            
        业务规则：
        1. 审批流程未匹配 → 报错，保留单据（状态=DRAFT）
        2. 审批创建失败 → 报错，保留单据（状态=DRAFT）
        3. 审批创建成功 → 单据状态=PENDING_REVIEW
        """
        
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
        手动提交审批
        
        用于手动审批场景（用户点击"提交审批"按钮）
        
        Args:
            db: 数据库会话
            business_type: 业务类型
            entity_id: 业务单据 ID
            team_id: 团队 ID
            submitter_id: 提交人 ID
            submitter_name: 提交人姓名
            
        Returns:
            (approval, error_message)
            - approval: 审批实例（未匹配流程时为 None）
            - error_message: 错误信息（成功时为 None）
            
        业务规则：
        1. 单据状态必须为 DRAFT
        2. 审批流程未匹配 → 报错，单据保持 DRAFT
        3. 审批创建成功 → 单据状态=PENDING_REVIEW
        """
```

---

### 2. 统一审批流程状态

#### 2.1 状态枚举统一

**新增通用状态枚举（仅用于逻辑判断）：**

```python
# app/constants/approval_phase.py

class ApprovalPhase(str, Enum):
    """通用审批阶段（用于逻辑判断，不直接映射到数据库）"""
    DRAFT = "draft"           # 草稿/待提交审批
    PENDING_REVIEW = "pending_review"  # 待审批（提交审批后）
    APPROVED = "approved"     # 审批通过
    REJECTED = "rejected"     # 审批拒绝
```

#### 2.2 各业务单据状态统一

| 业务类型 | 状态枚举类 | 改动内容 |
|---------|-----------|---------|
| **Contract** | ContractStatus | ✅ 已符合规范（DRAFT → PENDING_REVIEW → SIGNED） |
| **Payment** | PaymentConfirmationStatus | ⚠️ **新增 DRAFT 状态** |
| **Invoice** | InvoiceApplicationStatus | ✅ 已符合规范（DRAFT → PENDING_REVIEW → APPROVED） |
| **License** | LicenseApplicationStatus | ⚠️ **PENDING → PENDING_REVIEW** |

#### 2.3 PaymentConfirmationStatus 改造

**改造前：**
```python
class PaymentConfirmationStatus:
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    DISPUTED = "DISPUTED"
```

**改造后：**
```python
class PaymentConfirmationStatus:
    DRAFT = "DRAFT"          # 新增：草稿/待提交审批
    PENDING = "PENDING"      # 待审批
    CONFIRMED = "CONFIRMED"  # 已确认（审批通过）
    DISPUTED = "DISPUTED"    # 有争议
```

#### 2.4 LicenseApplicationStatus 改造

**改造前：**
```python
class LicenseApplicationStatus:
    DRAFT = "DRAFT"
    PENDING = "PENDING"      # 不一致
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ISSUED = "ISSUED"
```

**改造后：**
```python
class LicenseApplicationStatus:
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"  # 统一命名
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ISSUED = "ISSUED"
```

---

### 3. 状态流转统一

| 阶段 | 状态 | 触发操作 | adapter 方法 |
|------|------|---------|-------------|
| **创建单据** | DRAFT | 用户创建 | - |
| **提交审批** | PENDING_REVIEW | 自动/手动提交 | on_submit() |
| **审批中（多级）** | PENDING_REVIEW | Approval 流转 | - |
| **审批通过** | APPROVED 或业务终态 | 最后节点通过 | on_approved() |
| **审批拒绝** | DRAFT | 任一级拒绝 | on_rejected() |
| **审批撤回** | DRAFT | 用户撤回 | on_cancelled() |

---

### 4. 事务流程设计

#### 4.1 自动审批场景（CONTRACT/PAYMENT）

```
用户创建单据
    ↓
API Endpoint
    ↓
ApprovalTransactionManager.create_with_approval()
    ↓
┌─────────────────────────────────────────────────────────────┐
│ try:                                                         │
│   # 1. 创建业务单据                                           │
│   entity = entity_create_func()                              │
│   entity.status = DRAFT                                       │
│   db.flush()  # 获取 ID                                       │
│                                                               │
│   # 2. 匹配审批流程                                           │
│   flow, err = match_flow_generic(business_type, ...)         │
│   if flow is None:                                            │
│       db.commit()  # 保留单据                                 │
│       return (entity, None, "请先配置审批流程")               │
│                                                               │
│   # 3. 创建审批实例                                           │
│   approval = approval_crud.create_approval_only(db, ...)      │
│   db.flush()                                                  │
│                                                               │
│   # 4. 切单据状态                                             │
│   adapter.on_submit(db, entity)  # DRAFT → PENDING_REVIEW     │
│                                                               │
│   # 5. 统一提交                                               │
│   db.commit()                                                 │
│                                                               │
│   # 6. 异步发送通知                                           │
│   asyncio.create_task(notification_service.notify(...))      │
│                                                               │
│   return (entity, approval, None)                             │
│                                                               │
│ except Exception:                                             │
│   db.rollback()                                               │
│   raise                                                       │
└─────────────────────────────────────────────────────────────┘
```

#### 4.2 手动审批场景（INVOICE/LICENSE）

```
用户创建单据 → DRAFT 状态 → db.commit()
    ↓
用户点击"提交审批"
    ↓
API Endpoint (submit)
    ↓
ApprovalTransactionManager.submit_for_approval()
    ↓
┌─────────────────────────────────────────────────────────────┐
│ try:                                                         │
│   # 1. 获取单据（状态=DRAFT）                                  │
│   entity = adapter.get_entity(db, entity_id, team_id)        │
│   if entity.status != DRAFT:                                 │
│       return (None, "单据状态不正确，无法提交")               │
│                                                               │
│   # 2. 匹配审批流程                                           │
│   flow, err = match_flow_generic(...)                        │
│   if flow is None:                                            │
│       return (None, "请先配置审批流程")                       │
│                                                               │
│   # 3. 创建审批实例                                           │
│   approval = approval_crud.create_approval_only(...)         │
│   db.flush()                                                  │
│                                                               │
│   # 4. 切单据状态                                             │
│   adapter.on_submit(db, entity)  # DRAFT → PENDING_REVIEW     │
│                                                               │
│   # 5. 统一提交                                               │
│   db.commit()                                                 │
│                                                               │
│   # 6. 异步发送通知                                           │
│   asyncio.create_task(notification_service.notify(...))      │
│                                                               │
│   return (approval, None)                                     │
│                                                               │
│ except Exception:                                             │
│   db.rollback()                                               │
│   raise                                                       │
└─────────────────────────────────────────────────────────────┘
```

---

### 5. ApprovalCRUD 改造

**新增 `create_approval_only` 方法：**

```python
# app/crud/approval.py

def create_approval_only(
    self,
    db: Session,
    business_type: str,
    business_id: int,
    team_id: int,
    flow: ApprovalFlow,
    submitter_id: str,
    submitter_name: str
) -> Approval:
    """
    创建审批实例（不执行 commit）
    
    与 create_approval_generic 的区别：
    - 不执行 db.commit()
    - 由调用方控制事务边界
    
    Returns:
        Approval: 审批实例（已 flush，未 commit）
    """
    # ... 创建逻辑与 create_approval_generic 相同 ...
    db.flush()
    # 不执行 commit
    return db_approval
```

---

### 6. 删除免审批直通逻辑

**需要修改的文件：**

| 文件 | 删除内容 |
|------|---------|
| `crud_license_application.py:462-466` | 未匹配流程时 status=ISSUED 的直通逻辑 |
| `api/approvals.py` submit 端点 | 未匹配流程返回 approval_id=0 的直通逻辑 |

---

### 7. 异常处理策略

| 异常场景 | 处理方式 | 单据状态 | 用户提示 |
|---------|---------|---------|---------|
| **审批流程未匹配** | 保留单据 | DRAFT | "请先配置审批流程" |
| **审批流程无节点** | 保留单据 | DRAFT | "审批流程未配置审批节点" |
| **数据库写入失败** | 全部回滚 | 不创建 | 系统异常提示 |
| **通知发送失败** | 不阻断 | PENDING_REVIEW | 不影响业务（后台记录） |

---

### 8. 多级审批兼容性

**关键结论：本设计不影响多级审批逻辑**

| 审批阶段 | Approval.status | 单据状态 | 说明 |
|---------|-----------------|---------|------|
| 提交审批 | PENDING | PENDING_REVIEW | adapter.on_submit() |
| 第1级审批中 | PENDING | PENDING_REVIEW | 单据状态不变 |
| 第1级通过→第2级 | PENDING | PENDING_REVIEW | Approval.current_node_id 移动 |
| 最后节点通过 | APPROVED | APPROVED/终态 | adapter.on_approved() |
| 任一级拒绝 | REJECTED | DRAFT | adapter.on_rejected() |

**原因：**
- 单据状态只在提交/通过/拒绝三个时刻切换
- 多级审批通过 Approval.current_node_id 控制
- 单据状态保持 PENDING_REVIEW 不变

---

## 文件改动清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `app/services/approval_transaction_manager.py` | **新增** | 事务管理器核心类 |
| `app/constants/approval_phase.py` | **新增** | 通用审批阶段枚举 |
| `app/models/payment.py` | **修改** | PaymentConfirmationStatus 新增 DRAFT |
| `app/models/license_application.py` | **修改** | PENDING → PENDING_REVIEW |
| `app/crud/approval.py` | **修改** | 新增 create_approval_only 方法 |
| `app/crud/payment.py` | **修改** | 删除 _auto_submit_approval，使用 TransactionManager |
| `app/crud/contract.py` | **修改** | 删除 submit_for_approval，使用 TransactionManager |
| `app/crud/crud_license_application.py` | **修改** | 删除 submit 免审批直通，使用 TransactionManager |
| `app/api/approvals.py` | **修改** | submit 端点删除免审批直通 |
| `migrations/versions/018_payment_draft_status.py` | **新增** | PaymentConfirmationStatus 新增 DRAFT |
| `migrations/versions/019_license_pending_review.py` | **新增** | LicenseApplicationStatus PENDING → PENDING_REVIEW |

---

## 数据迁移计划

### 迁移 1：PaymentConfirmationStatus 新增 DRAFT

```python
# migrations/versions/018_payment_draft_status.py

def upgrade():
    # 1. 修改 confirmation_status 列默认值
    op.alter_column(
        'crm_payment_records',
        'confirmation_status',
        server_default='DRAFT'
    )
    
    # 2. 将现有 PENDING 状态改为 DRAFT（未提交审批）
    # 注意：已提交审批的记录保持 PENDING
    op.execute("""
        UPDATE crm_payment_records
        SET confirmation_status = 'DRAFT'
        WHERE confirmation_status = 'PENDING'
        AND approval_id IS NULL
    """)
```

### 迁移 2：LicenseApplicationStatus PENDING → PENDING_REVIEW

```python
# migrations/versions/019_license_pending_review.py

def upgrade():
    # 1. 更新状态值
    op.execute("""
        UPDATE crm_license_applications
        SET status = 'PENDING_REVIEW'
        WHERE status = 'PENDING'
    """)
```

---

## API 改动清单

| API 端点 | 改动 |
|---------|------|
| `POST /payments/records` | 使用 TransactionManager.create_with_approval() |
| `POST /contracts` | 使用 TransactionManager.create_with_approval() |
| `POST /invoices` | 创建 DRAFT 状态单据 |
| `POST /v1/approvals/{type}/{id}/submit` | 使用 TransactionManager.submit_for_approval() |

---

## 前端改动清单

| 前端组件 | 改动 |
|---------|------|
| 回款登记表单 | 处理新的错误提示（审批流程未配置） |
| 合同创建表单 | 处理新的错误提示 |
| 发票/License 创建 | 移除免审批直通的 UI 提示 |
| 单据详情页 | 状态显示统一（DRAFT/PENDING_REVIEW/APPROVED） |

---

## 错误提示规范

| 错误码 | 提示文案 |
|-------|---------|
| `APPROVAL_FLOW_NOT_FOUND` | "未找到审批流程，请先配置审批流程" |
| `APPROVAL_FLOW_NO_NODES` | "审批流程未配置审批节点" |
| `APPROVAL_ALREADY_EXISTS` | "单据已提交审批，请勿重复提交" |
| `APPROVAL_STATUS_INVALID` | "单据状态不正确，无法提交审批" |

---

## 测试计划

| 测试场景 | 验证点 |
|---------|-------|
| **创建单据+审批成功** | 单据和审批同时存在，状态正确 |
| **审批流程未匹配** | 单据保留（DRAFT），错误提示正确 |
| **审批创建失败** | 单据保留（DRAFT），错误提示正确 |
| **通知发送失败** | 不影响业务数据，后台记录日志 |
| **多级审批流转** | 单据状态保持 PENDING_REVIEW |
| **审批拒绝后重新提交** | 单据状态正确流转 |
| **并发审批** | 乐观锁生效 |

---

## 版本规划

| 版本 | 内容 |
|------|------|
| **v1.0** | ApprovalTransactionManager 核心 + 状态统一 |
| **v1.1** | 删除免审批直通逻辑 |
| **v1.2** | 前端错误提示优化 |

---

## 附录：状态流转图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        统一审批流程状态流转                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐                                                   │
│  │ 用户创建单据  │                                                   │
│  └──────────┬───┘                                                   │
│             ↓                                                       │
│  ┌──────────────┐                                                   │
│  │ DRAFT        │  ← 草稿/待提交审批                                 │
│  │ (新创建)     │                                                   │
│  └──────────┬───┘                                                   │
│             │                                                       │
│             │ 用户点击"提交审批" 或 自动审批                          │
│             ↓                                                       │
│  ┌──────────────┐                                                   │
│  │ PENDING_     │  ← 待审批                                         │
│  │ REVIEW       │    (提交审批后，整个审批过程中保持)                 │
│  │              │                                                   │
│  └──────────┬───┘                                                   │
│             │                                                       │
│     ┌───────┴───────┐                                               │
│     ↓               ↓                                               │
│ ┌─────────┐  ┌──────────────────┐                                  │
│ │ APPROVED│  │ REJECTED         │                                  │
│ │ 或终态  │  │ (审批拒绝)       │                                  │
│ │         │  └──────────┬───────┘                                  │
│ └─────────┘             │                                          │
│                         ↓                                          │
│                  ┌──────────────┐                                   │
│                  │ DRAFT        │  ← 回到待提交审批                  │
│                  │ (可重新提交) │    用户可重新点击"提交审批"          │
│                  └──────────────┘                                   │
│                                                                     │
│  注：Approval.status 为 PENDING → APPROVED/REJECTED                  │
│      单据状态为 DRAFT → PENDING_REVIEW → APPROVED/终态               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

**设计文档版本：v1.0**
**创建时间：2026-07-08**
**作者：Claude**