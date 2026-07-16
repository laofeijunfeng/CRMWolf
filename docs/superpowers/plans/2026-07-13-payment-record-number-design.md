# 回款记录编号字段实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为回款记录添加系统自动生成的编号字段 `record_number`，格式为 `PAYYYYYMMDD序号`，支持旧数据迁移回填。

**Architecture:** 重构现有 `ContractNumberGenerator` 为通用 `BusinessNumberGenerator`，支持可配置前缀（CT/PAY），复用线程安全的每日重置序号生成逻辑。通过 Alembic 迁移添加字段并回填历史数据。

**Tech Stack:** Python/SQLAlchemy/Alembic, TypeScript/Vue

## Global Constraints

- 编号格式：`PAYYYYYMMDD序号`（无分隔符，如 `PAY202607130001`）
- 序号策略：每日重置（当天从 0001 开始）
- 唯一性：全局唯一（数据库 `unique=True`）
- 旧数据迁移：按 `created_time` 回填，同一天按 ID 排序分配序号
- TypeScript 四禁令：禁用 `any` `as any` `@ts-ignore` `!`
- 迁移文件命名：`019_payment_record_number.py`

---

## File Structure

| 文件 | 负责内容 |
|------|----------|
| `CRM-Server/app/services/business_number_generator.py` | 新建：通用编号生成器（重构自 ContractNumberGenerator） |
| `CRM-Server/app/services/contract.py` | 修改：删除 ContractNumberGenerator，改用 BusinessNumberGenerator |
| `CRM-Server/app/models/payment.py` | 修改：PaymentRecord 添加 `record_number` 字段 |
| `CRM-Server/app/schemas/payment.py` | 修改：PaymentRecordResponse 添加 `record_number` 字段 |
| `CRM-Server/app/crud/contract.py` | 修改：导入路径调整 |
| `CRM-Server/app/crud/payment.py` | 修改：PaymentRecordCRUD.create() 调用生成器 |
| `CRM-Server/app/crud/approval.py` | 修改：审批摘要使用 `record_number` 替代合成编号 |
| `CRM-Server/migrations/versions/019_payment_record_number.py` | 新建：添加字段 + 回填迁移 |
| `CRM-Client/src/api/payment.ts` | 修改：PaymentRecordResponse 添加 `record_number` 类型 |
| `CRM-Client/src/views/PaymentRecords.vue` | 修改：使用 `record_number` 替代 `id` 显示 |

---

### Task 1: 创建通用编号生成器

**Files:**
- Create: `CRM-Server/app/services/business_number_generator.py`
- Modify: `CRM-Server/app/services/contract.py:9-45`

**Interfaces:**
- Produces: `BusinessNumberGenerator.generate(prefix, db) -> str`

- [ ] **Step 1: 创建 BusinessNumberGenerator 类**

```python
# CRM-Server/app/services/business_number_generator.py
"""通用业务编号生成器"""
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text
import threading


class BusinessNumberGenerator:
    """
    通用业务编号生成器（线程安全）
    
    支持可配置前缀，每日重置序号。
    
    格式：{PREFIX}{YYYYMMDD}{四位序号}
    例如：CT202602060001, PAY202607130001
    """
    
    _lock = threading.Lock()
    
    # 表名映射：前缀 -> (表名, 编号字段名)
    TABLE_MAPPING = {
        'CT': ('crm_contracts', 'contract_number'),
        'PAY': ('crm_payment_records', 'record_number'),
    }
    
    @classmethod
    def generate(cls, prefix: str, db: Session) -> str:
        """
        生成业务编号
        
        Args:
            prefix: 业务前缀（CT/PAY 等）
            db: 数据库会话
            
        Returns:
            str: 业务编号
            
        Raises:
            ValueError: 未注册的前缀
        """
        if prefix not in cls.TABLE_MAPPING:
            raise ValueError(f"未注册的业务编号前缀: {prefix}")
        
        table_name, number_field = cls.TABLE_MAPPING[prefix]
        
        with cls._lock:
            today = datetime.now()
            date_str = today.strftime("%Y%m%d")
            
            result = db.execute(text(f"""
                SELECT {number_field}
                FROM {table_name}
                WHERE {number_field} LIKE :pattern
                ORDER BY id DESC
                LIMIT 1
            """), {"pattern": f"{prefix}{date_str}%"}).fetchone()
            
            if result:
                last_number = result[0]
                sequence = int(last_number[-4:]) + 1
            else:
                sequence = 1
            
            return f"{prefix}{date_str}{sequence:04d}"
    
    @classmethod
    def register_table(cls, prefix: str, table_name: str, number_field: str) -> None:
        """
        注册新的业务编号表
        
        Args:
            prefix: 业务前缀
            table_name: 数据库表名
            number_field: 编号字段名
        """
        cls.TABLE_MAPPING[prefix] = (table_name, number_field)
```

- [ ] **Step 2: 重构 contract.py，移除 ContractNumberGenerator**

修改 `CRM-Server/app/services/contract.py`，删除原有 `ContractNumberGenerator` 类，保留 `ContractPricingService`：

```python
# CRM-Server/app/services/contract.py
"""合同相关服务"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

# ContractNumberGenerator 已迁移到 business_number_generator.py


class ContractPricingService:
    """合同价格计算服务"""
    # ... 保持原有实现不变（第 48-100 行）
```

- [ ] **Step 3: 更新 contract.py CRUD 导入**

修改 `CRM-Server/app/crud/contract.py` 第 10 行：

```python
# 原导入
# from app.services.contract import ContractNumberGenerator, ContractPricingService

# 新导入
from app.services.business_number_generator import BusinessNumberGenerator
from app.services.contract import ContractPricingService
```

- [ ] **Step 4: 更新 contract.py CRUD 调用**

修改 `CRM-Server/app/crud/contract.py` 中所有 `ContractNumberGenerator.generate_contract_number(db)` 调用：

第 214 行：
```python
# 原调用
# contract_number = ContractNumberGenerator.generate_contract_number(db)

# 新调用
contract_number = BusinessNumberGenerator.generate('CT', db)
```

第 287 行：
```python
# 原调用
# contract_number = ContractNumberGenerator.generate_contract_number(db)

# 新调用
contract_number = BusinessNumberGenerator.generate('CT', db)
```

- [ ] **Step 5: 运行类型检查**

```bash
cd CRM-Server && mypy app/services/business_number_generator.py app/services/contract.py app/crud/contract.py
```

Expected: PASS（无类型错误）

- [ ] **Step 6: Commit**

```bash
git add CRM-Server/app/services/business_number_generator.py CRM-Server/app/services/contract.py CRM-Server/app/crud/contract.py
git commit -m "refactor: abstract BusinessNumberGenerator from ContractNumberGenerator"
```

---

### Task 2: 添加 PaymentRecord.record_number 字段

**Files:**
- Modify: `CRM-Server/app/models/payment.py:93-130`
- Modify: `CRM-Server/app/schemas/payment.py:146-162, 243-248`

**Interfaces:**
- Consumes: BusinessNumberGenerator（Task 1）
- Produces: PaymentRecord.record_number 属性

- [ ] **Step 1: 修改 PaymentRecord 模型**

在 `CRM-Server/app/models/payment.py` 的 `PaymentRecord` 类中添加 `record_number` 字段（第 96 行后）：

```python
class PaymentRecord(Base):
    __tablename__ = "crm_payment_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    
    # 新增：记录编号
    record_number = Column(String(50), unique=True, nullable=False, comment="回款记录编号（系统自动生成）")
    
    payment_plan_id = Column(BigInteger, ForeignKey('crm_contract_payment_plans.id', ondelete='CASCADE'), nullable=False, comment="关联的回款计划ID")
    # ... 其余字段保持不变
```

添加索引（在 `__table_args__` 中）：

```python
__table_args__ = (
    Index('idx_payment_record_team_id', 'team_id'),
    Index('idx_payment_record_number', 'record_number'),  # 新增索引
)
```

- [ ] **Step 2: 修改 PaymentRecordResponse schema**

在 `CRM-Server/app/schemas/payment.py` 第 146-162 行的 `PaymentRecordResponse` 中添加 `record_number`：

```python
class PaymentRecordResponse(PaymentRecordBase):
    id: int
    payment_plan_id: int
    record_number: str = Field(..., description="回款记录编号")  # 新增
    creator_id: str
    creator_name: Optional[str]
    created_time: datetime
    # ... 其余字段保持不变
```

- [ ] **Step 3: 修改 PaymentRecordListItem schema**

第 243-248 行的 `PaymentRecordListItem` 继承自 `PaymentRecordResponse`，无需额外修改（自动继承 `record_number`）。

- [ ] **Step 4: 运行类型检查**

```bash
cd CRM-Server && mypy app/models/payment.py app/schemas/payment.py
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/models/payment.py CRM-Server/app/schemas/payment.py
git commit -m "feat: add record_number field to PaymentRecord model and schema"
```

---

### Task 3: 创建数据库迁移（添加字段 + 回填）

**Files:**
- Create: `CRM-Server/migrations/versions/019_payment_record_number.py`

**Interfaces:**
- Consumes: PaymentRecord 模型变更（Task 2）

- [ ] **Step 1: 创建迁移文件**

```python
# CRM-Server/migrations/versions/019_payment_record_number.py
"""add record_number to payment_records with backfill

Revision ID: 019_payment_record_number
Revises: 018_add_approval_phase_field
Create Date: 2026-07-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from datetime import datetime


# revision identifiers, used by Alembic.
revision = '019_payment_record_number'
down_revision = '018_add_approval_phase_field'
branch_labels = None
depends_on = None


def upgrade():
    # Step 1: Add record_number column (nullable first for backfill)
    op.add_column(
        'crm_payment_records',
        sa.Column('record_number', sa.String(50), nullable=True, comment='回款记录编号（系统自动生成）')
    )
    
    # Step 2: Add index
    op.create_index('idx_payment_record_number', 'crm_payment_records', ['record_number'])
    
    # Step 3: Backfill existing records (按 created_time 日期分组，同一天按 ID 排序)
    conn = op.get_bind()
    
    # 获取所有记录，按 created_time 日期分组
    records = conn.execute(text("""
        SELECT id, created_time
        FROM crm_payment_records
        ORDER BY created_time, id
    """)).fetchall()
    
    if records:
        # 按日期分组生成编号
        date_groups = {}
        for record in records:
            record_id = record[0]
            created_time = record[1]
            date_str = created_time.strftime('%Y%m%d') if created_time else datetime.now().strftime('%Y%m%d')
            
            if date_str not in date_groups:
                date_groups[date_str] = []
            date_groups[date_str].append(record_id)
        
        # 为每组分配序号并更新
        for date_str, record_ids in date_groups.items():
            for idx, record_id in enumerate(record_ids, start=1):
                record_number = f"PAY{date_str}{idx:04d}"
                conn.execute(text("""
                    UPDATE crm_payment_records
                    SET record_number = :record_number
                    WHERE id = :id
                """), {"record_number": record_number, "id": record_id})
    
    # Step 4: Set NOT NULL constraint after backfill
    op.alter_column('crm_payment_records', 'record_number', nullable=False)
    
    # Step 5: Add unique constraint
    op.create_unique_constraint('uq_payment_record_number', 'crm_payment_records', ['record_number'])


def downgrade():
    # Remove unique constraint
    op.drop_constraint('uq_payment_record_number', 'crm_payment_records', type_='unique')
    
    # Remove index
    op.drop_index('idx_payment_record_number', 'crm_payment_records')
    
    # Remove column
    op.drop_column('crm_payment_records', 'record_number')
```

- [ ] **Step 2: 执行迁移（先检查 dry-run）**

```bash
cd CRM-Server && alembic upgrade head --sql  # 查看 SQL
```

检查生成的 SQL 是否正确。

- [ ] **Step 3: 执行迁移**

```bash
cd CRM-Server && alembic upgrade head
```

Expected: 迁移成功执行，无错误。

- [ ] **Step 4: 验证迁移结果**

```bash
# 连接数据库验证
# MySQL: 
mysql -u root -p crmwolf -e "SELECT id, record_number, created_time FROM crm_payment_records LIMIT 5;"
```

Expected: 所有记录都有 `record_number`，格式为 `PAYYYYYMMDD序号`。

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/migrations/versions/019_payment_record_number.py
git commit -m "feat: add migration for payment record_number field with backfill"
```

---

### Task 4: 更新 PaymentRecordCRUD.create() 调用生成器

**Files:**
- Modify: `CRM-Server/app/crud/payment.py:392-462`

**Interfaces:**
- Consumes: BusinessNumberGenerator（Task 1）
- Consumes: PaymentRecord.record_number（Task 2）

- [ ] **Step 1: 添加导入**

在 `CRM-Server/app/crud/payment.py` 第 1-13 行导入区域添加：

```python
from app.services.business_number_generator import BusinessNumberGenerator
```

- [ ] **Step 2: 修改 create 方法**

修改 `PaymentRecordCRUD.create()` 方法（第 392-462 行），在创建记录时生成编号：

```python
def create(self, db: Session, plan_id: int, obj_in: PaymentRecordCreate, creator_id: str, creator_name: str, team_id: int) -> PaymentRecord:
    from app.crud.user import user_crud
    from app.crud.customer import customer_crud
    from app.services.operation_log_service import operation_log_service

    plan = db.query(PaymentPlan).filter(PaymentPlan.id == plan_id).first()
    if not plan:
        raise ValueError("回款计划不存在")

    total_paid = sum(float(r.actual_amount) for r in plan.payment_records)
    planned = float(plan.planned_amount)

    if total_paid + obj_in.actual_amount > planned:
        raise ValueError(f"回款金额超出计划，计划金额: {planned}，已回款: {total_paid}，本次: {obj_in.actual_amount}")

    # 新增：生成记录编号
    record_number = BusinessNumberGenerator.generate('PAY', db)

    db_record = PaymentRecord(
        payment_plan_id=plan_id,
        team_id=team_id,
        record_number=record_number,  # 新增
        **obj_in.model_dump(),
        creator_id=creator_id,
        creator_name=creator_name
    )
    # ... 后续代码保持不变
```

- [ ] **Step 3: 运行类型检查**

```bash
cd CRM-Server && mypy app/crud/payment.py
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add CRM-Server/app/crud/payment.py
git commit -m "feat: use BusinessNumberGenerator in PaymentRecordCRUD.create"
```

---

### Task 5: 更新审批摘要使用 record_number

**Files:**
- Modify: `CRM-Server/app/crud/approval.py:1134-1150`

**Interfaces:**
- Consumes: PaymentRecord.record_number（Task 2）

- [ ] **Step 1: 修改审批摘要生成逻辑**

修改 `CRM-Server/app/crud/approval.py` 第 1146-1150 行，使用真实的 `record_number` 替代合成编号：

```python
# 原代码（第 1146-1150 行）
# summaries[(BusinessType.PAYMENT, pr.id)] = {
#     "application_number": f"PAY-{pr.id}",
#     "entity_name": contract_name,
#     "entity_amount": float(pr.actual_amount) if pr.actual_amount is not None else None,
# }

# 新代码
summaries[(BusinessType.PAYMENT, pr.id)] = {
    "application_number": pr.record_number or f"PAY-{pr.id}",  # 使用真实编号，兜底合成编号
    "entity_name": contract_name,
    "entity_amount": float(pr.actual_amount) if pr.actual_amount is not None else None,
}
```

- [ ] **Step 2: 运行类型检查**

```bash
cd CRM-Server && mypy app/crud/approval.py
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add CRM-Server/app/crud/approval.py
git commit -m "feat: use record_number in approval summary for payment records"
```

---

### Task 6: 更新前端 API 类型定义

**Files:**
- Modify: `CRM-Client/src/api/payment.ts:122-134, 202-211`

**Interfaces:**
- Consumes: 后端 PaymentRecordResponse 变更（Task 2）
- Produces: PaymentRecordResponse.record_number 类型

- [ ] **Step 1: 修改 PaymentRecordResponse 类型**

在 `CRM-Client/src/api/payment.ts` 第 122-134 行的 `PaymentRecordResponse` 接口添加 `record_number`：

```typescript
export interface PaymentRecordResponse {
  id: number
  payment_plan_id: number
  record_number: string  // 新增：回款记录编号
  actual_amount: number
  payment_date: string
  proof_attachment?: string
  notes?: string
  creator_id?: string
  creator_name?: string
  created_time: string
  last_modified_time: string
}
```

- [ ] **Step 2: 修改 PaymentRecordWithDetails 类型**

第 202-211 行的 `PaymentRecordWithDetails` 继承自 `PaymentRecordResponse`，无需额外修改（自动继承 `record_number`）。

- [ ] **Step 3: 运行类型检查**

```bash
cd CRM-Client && npm run type-check
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add CRM-Client/src/api/payment.ts
git commit -m "feat: add record_number to PaymentRecordResponse type"
```

---

### Task 7: 更新前端 PaymentRecords.vue 显示

**Files:**
- Modify: `CRM-Client/src/views/PaymentRecords.vue:74-82`

**Interfaces:**
- Consumes: PaymentRecordWithDetails.record_number（Task 6）

- [ ] **Step 1: 修改 DataTable 列定义**

修改 `CRM-Client/src/views/PaymentRecords.vue` 第 74-82 行的 `columns` 数组：

```typescript
// 原代码
// const columns = [
//   { key: 'record_number', title: '记录编号', width: '120px' },
//   ...

// 新代码：字段名保持不变，但现在是真实字段
const columns = [
  { key: 'record_number', title: '记录编号', width: '120px' },
  { key: 'customer_name', title: '客户名称' },
  { key: 'contract_name', title: '合同名称' },
  { key: 'actual_amount', title: '回款金额', align: 'right' as const },
  { key: 'payment_date', title: '回款日期' },
  { key: 'confirmation_status', title: '状态', align: 'center' as const },
  { key: 'actions', title: '操作', align: 'center' as const, width: '220px' }
]
```

注意：前端列定义中 `record_number` 已存在，只需确认后端返回真实数据后即可正确显示。

- [ ] **Step 2: 添加 record_number 显示模板（可选）**

如果需要自定义显示样式，可在 DataTable 的 template 中添加：

```vue
<!-- 记录编号 -->
<template #cell-record_number="{ row }">
  <span class="record-number-cell">{{ row.record_number || '-' }}</span>
</template>
```

添加样式：

```scss
.record-number-cell {
  font-family: $wolf-font-mono-v2;
  font-variant-numeric: tabular-nums;
}
```

- [ ] **Step 3: 运行类型检查**

```bash
cd CRM-Client && npm run type-check
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add CRM-Client/src/views/PaymentRecords.vue
git commit -m "fix: display real record_number in PaymentRecords.vue"
```

---

### Task 8: 集成测试验证

**Files:**
- 无文件变更，仅测试验证

**Interfaces:**
- Consumes: 所有前序任务完成

- [ ] **Step 1: 启动后端服务**

```bash
cd CRM-Server && ./run.sh
```

- [ ] **Step 2: 创建新回款记录测试**

通过 API 或前端界面创建一条新的回款记录，验证：
1. `record_number` 自动生成
2. 编号格式为 `PAYYYYYMMDD序号`
3. 同一天多条记录序号递增

- [ ] **Step 3: 查看回款记录列表**

访问 `/payments/records` 页面，验证：
1. 列表正确显示 `record_number`
2. 旧数据已回填编号
3. 编号列不再显示 `-`

- [ ] **Step 4: 查看审批中心**

访问审批中心，验证回款记录审批项显示真实编号而非 `PAY-{id}`。

- [ ] **Step 5: Final Commit（如有遗漏文件）**

```bash
git status  # 检查是否有未提交的变更
git add -A
git commit -m "feat: complete payment record_number implementation"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|------------------|------|
| 编号格式 `PAYYYYYMMDD序号` | Task 1（生成器） |
| 每日重置序号 | Task 1（生成器逻辑） |
| 全局唯一约束 | Task 3（迁移 unique constraint） |
| 旧数据按 created_time 回填 | Task 3（迁移 backfill） |
| PaymentRecord 模型添加字段 | Task 2 |
| PaymentRecordCRUD.create() 生成编号 | Task 4 |
| 前端显示真实编号 | Task 7 |
| 审批摘要使用真实编号 | Task 5 |

## Placeholder Scan

- ✅ 无 TBD/TODO
- ✅ 无 "implement later"
- ✅ 无 "add appropriate error handling"
- ✅ 无 "similar to Task N"（每个 task 独立代码）
- ✅ 所有代码步骤都有完整代码块

## Type Consistency Check

- ✅ `BusinessNumberGenerator.generate('PAY', db)` 返回 `str`
- ✅ `PaymentRecord.record_number: str`（模型）
- ✅ `PaymentRecordResponse.record_number: str`（schema）
- ✅ `PaymentRecordWithDetails.record_number`（继承自 PaymentRecordResponse）
- ✅ 前端 `PaymentRecordResponse.record_number: string`

---

**Plan complete and saved to `docs/superpowers/plans/2026-07-13-payment-record-number-design.md`.**

**Two execution options:**

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**