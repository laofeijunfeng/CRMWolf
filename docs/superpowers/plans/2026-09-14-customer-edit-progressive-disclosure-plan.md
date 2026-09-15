# 客户编辑弹窗渐进披露与统一保存实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将客户创建与编辑弹窗收敛为“基础资料 + 默认收起的更多客户信息 + 一个保存按钮”，通过普通客户创建和更新契约一次性维护行业、受控客户状态以及授权汇总，同时不改变显式状态操作和正式 License 流程。

**Architecture:** 创建接口在一个数据库事务内写入客户、联系人和可选客户字段；编辑接口使用带 `expected_version` 的普通 `PUT /v1/customers/{customer_id}`，在客户行锁内校验并一次性写入所有 dirty 字段，实际发生变化时只递增一次 `version`。前端弹窗不再调用生命周期或授权专用 PATCH，而是把更多信息字段纳入同一份 dirty diff；现有专用 PATCH 路由继续作为兼容入口服务原有调用者。

**Tech Stack:** Vue 3 + TypeScript + VeeValidate + Zod + shadcn-vue/Reka UI；FastAPI + Pydantic v2 + SQLAlchemy；Vitest；Pytest。

## Global Constraints

- 业务合同是 `docs/superpowers/specs/2026-09-11-customer-edit-progressive-disclosure-design.md`。
- 当前工作树已经包含行业层级选择器、客户字段 diff、独立生命周期 PATCH、独立授权快照 PATCH以及部分弹窗测试；本计划要求将这些中间实现切换到最终的普通客户资料保存语义。
- 不创建数据库 migration；客户表已经存在 `industry`、`status`、`license_type`、`license_expiry_date`。
- 弹窗创建和编辑不得创建 `LicenseApplication`、审批实例、授权码、正式发放记录，也不得调用正式 License 服务。
- 弹窗状态只允许 `0` 跟进中和 `1` 已成交；编辑当前为 `2` 输单或 `3` 失效时只读，不能覆盖。
- 列表中的赢单、输单、失效、公海、领取、移交和正式 License 流程保持原有入口、通知、原因和审计语义。
- 授权到期日非空时必须有授权类型；弹窗不提供清除日期按钮，只允许新增或改选日期。
- 创建时未选择状态由后端默认 `0`；创建为 `1` 只代表初始客户资料，不发送显式赢单通知。
- 编辑更多字段与普通资料共用一次 PUT；一次提交中的实际变化只递增一次客户 `version`。
- 所有客户写入继续执行 team 隔离、客户编辑权限和乐观锁；stale version 返回 HTTP 409 且不发生字段突变。
- 前端禁止 `any`、`as any`、`@ts-ignore` 和无必要的非空断言；客户响应继续经过 Zod schema。
- 不新增通用多业务保存抽象。
- 不重置、覆盖或提交与本功能无关的 dirty/staged 文件；提交时只加入本任务拥有的文件和明确 hunks。
- 中间任务只运行目标测试；类型检查、lint 和浏览器 smoke 统一放在最后一个任务。

## File Map

### Backend

- Modify `CRM-Server/app/schemas/customer.py`: 创建/更新客户字段类型、创建授权组合校验、行业信息响应字段。
- Modify `CRM-Server/app/crud/customer.py`: 创建事务提交开关、创建字段规范化、统一锁定更新、状态和授权组合校验、稳定审计快照。
- Modify `CRM-Server/app/api/customers.py`: 创建客户原子事务、普通 PUT 统一审计和智能档案刷新；保留专用 PATCH 路由。
- Keep `CRM-Server/app/services/customer_status_transition_service.py`: 专用生命周期 PATCH 的既有决策矩阵不被普通 PUT 复用。
- Keep `CRM-Server/app/schemas/industry.py` and `CRM-Server/app/api/industry.py`: 使用已有类型化行业层级响应。
- Modify `CRM-Server/tests/unit/test_customer_edit_contracts.py`。
- Modify `CRM-Server/tests/unit/test_customer_snapshot_crud.py`。
- Modify `CRM-Server/tests/unit/test_customer_update_concurrency.py`。
- Modify `CRM-Server/tests/unit/test_customer_status_transition_service.py`。
- Modify `CRM-Server/tests/unit/api/test_customer_edit_api.py`。

### Frontend

- Modify `CRM-Client/src/api/customer.ts`。
- Modify `CRM-Client/src/schemas/customer.ts`。
- Modify `CRM-Client/src/schemas/customer-form.ts`。
- Keep or modify `CRM-Client/src/components/crmwolf/IndustryHierarchySelectField.vue`。
- Keep `CRM-Client/src/components/crmwolf/index.ts` export。
- Modify `CRM-Client/src/components/crmwolf/__tests__/IndustryHierarchySelectField.test.ts`。
- Modify `CRM-Client/src/components/dialogs/customerFormDiff.ts`。
- Modify `CRM-Client/src/components/dialogs/__tests__/customerFormDiff.test.ts`。
- Modify `CRM-Client/src/components/dialogs/CustomerFormDialog.vue`。
- Modify `CRM-Client/src/components/dialogs/__tests__/CustomerFormDialog.test.ts`。
- Modify `CRM-Client/src/api/__tests__/customer.test.ts`。
- Modify `CRM-Client/src/schemas/__tests__/acquisition-source.test.ts`。
- Modify `CRM-Client/src/views/Customers.vue`。
- Modify `CRM-Client/src/views/CustomerDetailSheet.vue`。

---

## Task 1: Reconcile the final request and form contracts

**Files:**
- Modify: `CRM-Server/app/schemas/customer.py:195-275`
- Modify: `CRM-Client/src/api/customer.ts:133-165`
- Modify: `CRM-Client/src/schemas/customer.ts:17-145,291-303`
- Modify: `CRM-Client/src/schemas/customer-form.ts:12-85`
- Modify: `CRM-Server/tests/unit/test_customer_edit_contracts.py`
- Modify: `CRM-Client/src/schemas/__tests__/acquisition-source.test.ts`

**Interfaces:**

```python
# CRM-Server/app/schemas/customer.py
CustomerLifecycleStatus = Literal[0, 1]
CustomerLicenseType = Literal["TRIAL", "OFFICIAL"]

class CustomerCreate(CustomerBase):
    status: CustomerLifecycleStatus = 0
    license_type: Optional[CustomerLicenseType] = None
    license_expiry_date: Optional[date] = None
    owner_id: Optional[str] = None
    default_procurement_method_id: Optional[int] = None
    primary_contact: Optional[ContactCreate] = None

class CustomerUpdate(BaseModel):
    expected_version: Optional[int] = Field(None, ge=1)
    account_name: Optional[str] = Field(None, min_length=1, max_length=255)
    industry: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, min_length=1, max_length=100)
    address: Optional[str] = Field(None, max_length=500)
    company_scale: Optional[str] = Field(None, max_length=50)
    source: Optional[str] = Field(None, max_length=50)
    source_public_id: Optional[str] = None
    default_procurement_method_id: Optional[int] = None
    status: Optional[CustomerLifecycleStatus] = None
    license_type: Optional[CustomerLicenseType] = None
    license_expiry_date: Optional[date] = None
```

```typescript
// CRM-Client/src/api/customer.ts
export type CustomerLifecycleStatus = 0 | 1
export type CustomerLicenseType = 'TRIAL' | 'OFFICIAL'

export interface CustomerCreate {
  account_name: string
  city: string
  address?: string | null
  industry?: string | null
  company_scale?: string | null
  source_public_id?: string | null
  default_procurement_method_id?: number | null
  status?: CustomerLifecycleStatus
  license_type?: CustomerLicenseType | null
  license_expiry_date?: string | null
  primary_contact?: ContactCreate | null
}

export interface CustomerUpdate {
  expected_version?: number | null
  account_name?: string | null
  city?: string | null
  address?: string | null
  industry?: string | null
  company_scale?: string | null
  source_public_id?: string | null
  default_procurement_method_id?: number | null
  status?: CustomerLifecycleStatus
  license_type?: CustomerLicenseType | null
  license_expiry_date?: string | null
}
```

### Step 1: Write failing contract tests

Append these tests to `CRM-Server/tests/unit/test_customer_edit_contracts.py`:

```python
from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.customer import CustomerCreate, CustomerUpdate


def test_customer_create_defaults_to_following_and_empty_license_snapshot() -> None:
    payload = CustomerCreate(account_name="客户 A", city="上海")
    assert payload.status == 0
    assert payload.license_type is None
    assert payload.license_expiry_date is None


def test_customer_create_accepts_initial_won_and_complete_license_snapshot() -> None:
    payload = CustomerCreate(
        account_name="客户 A",
        city="上海",
        status=1,
        license_type="TRIAL",
        license_expiry_date=date(2026, 12, 31),
    )
    assert payload.status == 1
    assert payload.license_type == "TRIAL"
    assert payload.license_expiry_date == date(2026, 12, 31)


def test_customer_create_rejects_expiry_without_license_type() -> None:
    with pytest.raises(ValidationError, match="授权到期日期"):
        CustomerCreate(
            account_name="客户 A",
            city="上海",
            license_expiry_date=date(2026, 12, 31),
        )


def test_customer_create_normalizes_type_without_expiry_to_empty_snapshot() -> None:
    payload = CustomerCreate(account_name="客户 A", city="上海", license_type="TRIAL")
    assert payload.license_type is None
    assert payload.license_expiry_date is None


def test_customer_update_accepts_partial_license_fields_for_database_pair_resolution() -> None:
    payload = CustomerUpdate(expected_version=4, license_expiry_date=date(2027, 1, 1))
    assert payload.license_expiry_date == date(2027, 1, 1)
    assert "license_expiry_date" in payload.model_fields_set
    assert "license_type" not in payload.model_fields_set


def test_customer_update_rejects_status_two_and_three() -> None:
    with pytest.raises(ValidationError):
        CustomerUpdate(status=2)
    with pytest.raises(ValidationError):
        CustomerUpdate(status=3)
```

Append these cases to `CRM-Client/src/schemas/__tests__/acquisition-source.test.ts`:

```typescript
it('accepts optional more-information values on create', () => {
  const result = customerCreateSchema.safeParse({
    account_name: '示例客户',
    city: '上海',
    company_scale: '1-50人',
    source_public_id: 'acq_referral',
    default_procurement_method_id: 1,
    industry: 'internet_saas',
    status: 1,
    license_type: 'TRIAL',
    license_expiry_date: '2026-12-31',
    contact_name: '张三',
    contact_mobile: '13800138000',
    contact_position: '经理',
    contact_gender: '男',
  })
  expect(result.success).toBe(true)
})

it('rejects a non-empty expiry date without a license type', () => {
  const result = customerCreateSchema.safeParse({
    account_name: '示例客户',
    city: '上海',
    company_scale: '1-50人',
    source_public_id: 'acq_referral',
    default_procurement_method_id: 1,
    license_expiry_date: '2026-12-31',
    contact_name: '张三',
    contact_mobile: '13800139000',
    contact_position: '经理',
    contact_gender: '男',
  })
  expect(result.success).toBe(false)
})
```

Run:

```bash
cd CRM-Server && pytest tests/unit/test_customer_edit_contracts.py -q
cd CRM-Client && npm run test:unit -- --run src/schemas/__tests__/acquisition-source.test.ts
```

Expected: the new tests fail because the final create/update contracts are not fully exposed.

### Step 2: Implement the contracts

In `CustomerCreate`, add the three optional more-information fields and normalize the pair with this validator:

```python
@model_validator(mode="after")
def normalize_license_pair(self) -> "CustomerCreate":
    if self.license_expiry_date is None:
        self.license_type = None
    elif self.license_type is None:
        raise ValueError("授权到期日期不为空时必须选择授权类型")
    return self
```

Do not put the complete license-pair validation on `CustomerUpdate`: an edit that changes only the date must retain the current database type, and an edit that changes only the type must retain the current database date. The CRUD layer resolves and validates the effective pair after loading the locked customer.

Extend `CustomerUpdate` with `status`, `license_type`, and `license_expiry_date`, preserving `model_fields_set` so omitted fields remain distinguishable from explicit null values.

Extend `CustomerIndustryInfo` with these optional response fields because the detail builder already supplies them:

```python
primary_code: Optional[str] = None
primary_name: Optional[str] = None
secondary_name: Optional[str] = None
```

In `CRM-Client/src/schemas/customer.ts`, define `CustomerLicenseTypeSchema`, `CustomerLifecycleStatusSchema`, and keep the existing hierarchy schemas. Extend `CustomerCreateSchema` and `CustomerUpdateSchema` with status and license fields. Preserve nullable response parsing for legacy customer rows.

In `CRM-Client/src/schemas/customer-form.ts`, add the same optional fields to both create and edit form schemas. Add a shared refinement that rejects a non-empty `license_expiry_date` when `license_type` is empty, while allowing an empty pair. Keep company scale, source, procurement method, and contact validation unchanged.

### Step 3: Run green tests and commit

Run:

```bash
cd CRM-Server && pytest tests/unit/test_customer_edit_contracts.py -q
cd CRM-Client && npm run test:unit -- --run src/schemas/__tests__/acquisition-source.test.ts
```

Expected: PASS. Commit only the files owned by this task:

```bash
git add CRM-Server/app/schemas/customer.py CRM-Server/tests/unit/test_customer_edit_contracts.py CRM-Client/src/api/customer.ts CRM-Client/src/schemas/customer.ts CRM-Client/src/schemas/customer-form.ts CRM-Client/src/schemas/__tests__/acquisition-source.test.ts
git commit -m "feat(customer): define unified customer field contracts"
```

## Task 2: Make manual customer creation atomic and field-complete

**Files:**
- Modify: `CRM-Server/app/crud/customer.py:218-264,1000-1045`
- Modify: `CRM-Server/app/api/customers.py:1210-1250`
- Modify: `CRM-Server/tests/unit/api/test_customer_edit_api.py`
- Modify: `CRM-Server/tests/unit/test_customer_service.py` only for fixtures that assert created field values

**Interfaces:**

```python
customer_crud.create(
    db: Session,
    obj_in: CustomerCreate,
    creator_id: str,
    team_id: int,
    operator_name: Optional[str] = None,
    *,
    commit: bool = True,
) -> Customer

contact_crud.create(
    db: Session,
    obj_in: ContactCreate,
    customer_id: int,
    team_id: int,
    is_primary: bool = False,
    *,
    commit: bool = True,
) -> Contact
```

When `commit=False`, both methods flush but do not commit or refresh independently. Existing callers that omit `commit` retain commit behavior.

### Step 1: Write failing transaction tests

Add these helpers and tests to `CRM-Server/tests/unit/api/test_customer_edit_api.py`:

```python
from app.schemas.customer import CustomerCreate


def _created_customer() -> SimpleNamespace:
    return SimpleNamespace(
        id=31,
        public_id="cus_created",
        team_id=8,
        account_name="新客户",
        city="上海",
        industry="internet_saas",
        status=1,
        license_type="TRIAL",
        license_expiry_date=date(2026, 12, 31),
        owner_id="9",
        version=1,
    )


@pytest.mark.asyncio
async def test_create_customer_commits_customer_and_contact_as_one_transaction(monkeypatch):
    customer = _created_customer()
    calls = SimpleNamespace(customer=[], contact=[], refreshes=[], notifications=[])
    db = MagicMock()

    def create_customer(**kwargs):
        calls.customer.append(kwargs)
        return customer

    def create_contact(**kwargs):
        calls.contact.append(kwargs)
        return SimpleNamespace(id=41, name="李华")

    _allow_edit_permission(monkeypatch, customer)
    monkeypatch.setattr(customers_api.customer_crud, "create", create_customer)
    monkeypatch.setattr(customers_api.contact_crud, "create", create_contact)
    monkeypatch.setattr(
        customers_api.customer_business_object_intelligence_service,
        "enqueue_object_change_refresh_after_commit",
        lambda **kwargs: calls.refreshes.append(kwargs),
    )
    monkeypatch.setattr(
        customers_api.outbound_notification_job_service,
        "queue_committed",
        lambda *args, **kwargs: calls.notifications.append(kwargs),
    )
    monkeypatch.setattr(customers_api, "_customer_response", lambda db_session, value: value)

    response = await customers_api.create_customer(
        CustomerCreate(
            account_name="新客户",
            city="上海",
            industry="internet_saas",
            status=1,
            license_type="TRIAL",
            license_expiry_date=date(2026, 12, 31),
            primary_contact={
                "name": "李华",
                "mobile": "13800138000",
                "position": "CTO",
                "gender": "1",
                "is_decision_maker": False,
            },
        ),
        team_id=8,
        current_user=SimpleNamespace(id=9, name="操作人"),
        db=db,
    )

    assert response is customer
    assert calls.customer[0]["commit"] is False
    assert calls.contact[0]["commit"] is False
    assert calls.customer[0]["obj_in"].status == 1
    assert calls.customer[0]["obj_in"].license_type == "TRIAL"
    db.commit.assert_called_once()
    assert calls.notifications == []
    assert calls.refreshes[0]["scope"] == "full"


@pytest.mark.asyncio
async def test_create_customer_rolls_back_when_contact_write_fails(monkeypatch):
    customer = _created_customer()
    db = MagicMock()
    monkeypatch.setattr(customers_api.customer_crud, "create", lambda **kwargs: customer)
    monkeypatch.setattr(
        customers_api.contact_crud,
        "create",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("联系人写入失败")),
    )
    monkeypatch.setattr(
        customers_api.customer_business_object_intelligence_service,
        "enqueue_object_change_refresh_after_commit",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("失败事务不能刷新客户档案")),
    )

    with pytest.raises(customers_api.HTTPException) as exc_info:
        await customers_api.create_customer(
            CustomerCreate(
                account_name="不会留下半成品",
                city="上海",
                primary_contact={
                    "name": "李华",
                    "mobile": "13800138000",
                    "position": "CTO",
                    "gender": "1",
                    "is_decision_maker": False,
                },
            ),
            team_id=8,
            current_user=SimpleNamespace(id=9, name="操作人"),
            db=db,
        )

    assert exc_info.value.status_code == 400
    db.rollback.assert_called_once()
    db.commit.assert_not_called()
```

Run:

```bash
cd CRM-Server && pytest tests/unit/api/test_customer_edit_api.py -q
```

Expected: the new tests fail because the route commits the customer and contact separately.

### Step 2: Implement the commit switch and create field handling

In `CustomerCRUD.create`:

1. Call `obj_in.model_dump(exclude={"primary_contact", "source_public_id", "source"})`.
2. Preserve source resolution and team assignment.
3. Set `status=obj_in.status` instead of forcing `0`.
4. Store the normalized license pair from `CustomerCreate`.
5. Resolve a supplied industry to a canonical active code. Accept an active code directly; accept one exact active industry name as a compatibility input and store its code; reject missing, ambiguous, and inactive values with `ValueError("行业代码不存在或已停用")`.
6. Add the customer, flush when `commit=False`, otherwise commit and refresh.
7. Pass `commit=False` to `operation_log_service.log` when the customer create is not committing, so `CUSTOMER_CREATED` remains inside the caller transaction.

In `ContactCRUD.create`, add the keyword-only `commit` argument. After adding the contact, call `db.flush()` for `commit=False`; retain the existing commit/refresh sequence for `commit=True`.

Replace the body of `create_customer` with this transaction boundary:

```python
try:
    new_customer = customer_crud.create(
        db=db,
        obj_in=customer,
        creator_id=str(current_user.id),
        team_id=team_id,
        operator_name=current_user.name,
        commit=False,
    )
    if customer.primary_contact is not None:
        contact_crud.create(
            db=db,
            obj_in=customer.primary_contact,
            customer_id=new_customer.id,
            team_id=team_id,
            is_primary=True,
            commit=False,
        )
    db.commit()
    db.refresh(new_customer)
except AcquisitionSourceError as exc:
    db.rollback()
    _raise_source_error(exc)
except ValueError as exc:
    db.rollback()
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
except IntegrityError as exc:
    db.rollback()
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="客户或联系人数据已被其他操作占用") from exc
```

Keep the intelligence full refresh after this block. Do not enqueue an outbound status notification for `customer.status == 1` in this route.

### Step 3: Run compatibility tests and commit

Run:

```bash
cd CRM-Server && pytest tests/unit/api/test_customer_edit_api.py tests/unit/test_customer_service.py -q
```

Expected: PASS. Commit:

```bash
git add CRM-Server/app/crud/customer.py CRM-Server/app/api/customers.py CRM-Server/tests/unit/api/test_customer_edit_api.py CRM-Server/tests/unit/test_customer_service.py
git commit -m "feat(customer): make manual customer creation atomic"
```

## Task 3: Implement one locked ordinary customer update with complete audit

**Files:**
- Modify: `CRM-Server/app/crud/customer.py:266-346`
- Modify: `CRM-Server/app/api/customers.py:1957-2032`
- Modify: `CRM-Server/tests/unit/test_customer_snapshot_crud.py`
- Modify: `CRM-Server/tests/unit/test_customer_update_concurrency.py`
- Modify: `CRM-Server/tests/unit/api/test_customer_edit_api.py`

**Interfaces:**

```python
customer_crud.update_with_audit(
    db: Session,
    db_obj: Customer,
    obj_in: CustomerUpdate,
) -> tuple[Customer, dict[str, object], dict[str, object]]

customer_crud.update(
    db: Session,
    db_obj: Customer,
    obj_in: CustomerUpdate,
) -> Customer
```

`update` delegates to `update_with_audit` and returns only the customer. The ordinary PUT route calls `update_with_audit` exactly once.

### Step 1: Write failing update and concurrency tests

Add this complete helper to `CRM-Server/tests/unit/test_customer_snapshot_crud.py`:

```python
def _locked_customer_for_update(db: MagicMock, **overrides: object) -> SimpleNamespace:
    values = {
        "id": 1,
        "team_id": 9,
        "version": 4,
        "account_name": "测试客户",
        "city": "北京",
        "address": None,
        "company_scale": "1-50人",
        "source_id": None,
        "source": None,
        "industry": "internet_saas",
        "status": 0,
        "license_type": "TRIAL",
        "license_expiry_date": date(2026, 1, 1),
    }
    values.update(overrides)
    customer = SimpleNamespace(**values)
    locked_query = db.query.return_value.filter.return_value.populate_existing.return_value.with_for_update.return_value
    locked_query.first.return_value = customer
    return customer
```

Add these tests:

```python
@pytest.mark.parametrize("current_status", [2, 3])
def test_update_with_audit_rejects_status_write_from_read_only_customer(current_status: int) -> None:
    db = MagicMock()
    customer = _locked_customer_for_update(db, status=current_status)

    with pytest.raises(ValueError, match="仅允许更新跟进中或已成交客户的状态"):
        customer_crud.update_with_audit(
            db,
            customer,
            CustomerUpdate(expected_version=4, status=1),
        )

    assert customer.status == current_status
    assert customer.version == 4
    db.commit.assert_not_called()


def test_update_with_audit_rejects_new_inactive_industry_without_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    customer = _locked_customer_for_update(db)
    monkeypatch.setattr(
        "app.crud.customer.industry_crud.get_by_code_with_parent",
        lambda db_session, code: SimpleNamespace(code=code, is_active=0),
    )

    with pytest.raises(ValueError, match="行业代码不存在或已停用"):
        customer_crud.update_with_audit(
            db,
            customer,
            CustomerUpdate(expected_version=4, industry="inactive_new"),
        )

    assert customer.industry == "internet_saas"
    assert customer.version == 4
    db.commit.assert_not_called()


def test_update_with_audit_resolves_partial_license_date_against_current_type() -> None:
    db = MagicMock()
    customer = _locked_customer_for_update(db)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "app.crud.customer.industry_crud.get_by_code_with_parent",
        lambda db_session, code: SimpleNamespace(code=code, is_active=1),
    )
    try:
        updated, before, after = customer_crud.update_with_audit(
            db,
            customer,
            CustomerUpdate(expected_version=4, license_expiry_date=date(2027, 1, 1)),
        )
    finally:
        monkeypatch.undo()

    assert updated is customer
    assert customer.license_type == "TRIAL"
    assert customer.license_expiry_date == date(2027, 1, 1)
    assert before == {"license_expiry_date": date(2026, 1, 1)}
    assert after == {"license_expiry_date": date(2027, 1, 1)}
    assert customer.version == 5
    db.commit.assert_called_once()


def test_update_with_audit_rejects_effective_license_pair_without_type() -> None:
    db = MagicMock()
    customer = _locked_customer_for_update(db, license_type=None, license_expiry_date=None)

    with pytest.raises(ValueError, match="授权到期日期不为空时必须选择授权类型"):
        customer_crud.update_with_audit(
            db,
            customer,
            CustomerUpdate(expected_version=4, license_expiry_date=date(2027, 1, 1)),
        )

    assert customer.license_type is None
    assert customer.license_expiry_date is None
    assert customer.version == 4
    db.commit.assert_not_called()


def test_update_with_audit_does_not_increment_version_for_no_actual_change() -> None:
    db = MagicMock()
    customer = _locked_customer_for_update(db)

    updated, before, after = customer_crud.update_with_audit(
        db,
        customer,
        CustomerUpdate(expected_version=4, city="北京"),
    )

    assert updated is customer
    assert before == {}
    assert after == {}
    assert customer.version == 4
    db.commit.assert_not_called()
```

Add this route-level test to `CRM-Server/tests/unit/api/test_customer_edit_api.py`:

```python
@pytest.mark.asyncio
async def test_customer_put_updates_profile_status_industry_and_license_once(monkeypatch):
    customer = _customer(status=0, version=4)
    customer.city = "北京"
    customer.industry = "internet_saas"
    customer.license_type = "TRIAL"
    customer.license_expiry_date = date(2026, 1, 1)
    calls = SimpleNamespace(logs=[], refreshes=[], notifications=[])
    _allow_edit_permission(monkeypatch, customer)
    monkeypatch.setattr(
        customers_api.customer_crud,
        "update_with_audit",
        lambda db, db_customer, payload: (
            setattr(db_customer, "city", "上海") or
            setattr(db_customer, "status", 1) or
            setattr(db_customer, "industry", "finance_securities") or
            setattr(db_customer, "license_type", "OFFICIAL") or
            setattr(db_customer, "license_expiry_date", date(2027, 1, 1)) or
            setattr(db_customer, "version", 5) or
            (db_customer,
             {"city": "北京", "status": 0, "industry": "internet_saas", "license_type": "TRIAL", "license_expiry_date": date(2026, 1, 1)},
             {"city": "上海", "status": 1, "industry": "finance_securities", "license_type": "OFFICIAL", "license_expiry_date": date(2027, 1, 1)})
        ),
    )
    monkeypatch.setattr(customers_api.operation_log_service, "log", lambda **kwargs: calls.logs.append(kwargs))
    monkeypatch.setattr(customers_api, "_persist_customer_business_object_refresh_after_commit", lambda **kwargs: calls.refreshes.append(kwargs))
    monkeypatch.setattr(customers_api.outbound_notification_job_service, "queue_committed", lambda *args, **kwargs: calls.notifications.append(kwargs))
    monkeypatch.setattr(customers_api, "_customer_response", lambda db_session, value: value)

    response = await customers_api.update_customer(
        customer.public_id,
        CustomerUpdate(
            expected_version=4,
            city="上海",
            status=1,
            industry="finance_securities",
            license_type="OFFICIAL",
            license_expiry_date=date(2027, 1, 1),
        ),
        team_id=customer.team_id,
        current_user=SimpleNamespace(id=9, name="操作人"),
        db=MagicMock(),
    )

    assert response.version == 5
    assert calls.logs[0]["event_type"] == customers_api.EventTypes.CUSTOMER_UPDATED
    assert calls.logs[0]["content"] == {
        "changed_fields": ["city", "status", "industry", "license_type", "license_expiry_date"],
        "before": {
            "city": "北京",
            "status": 0,
            "industry": "internet_saas",
            "license_type": "TRIAL",
            "license_expiry_date": "2026-01-01",
        },
        "after": {
            "city": "上海",
            "status": 1,
            "industry": "finance_securities",
            "license_type": "OFFICIAL",
            "license_expiry_date": "2027-01-01",
        },
    }
    assert calls.refreshes[0]["scope"] == "partial"
    assert calls.notifications == []
```

The test double above is deliberately self-contained: it mutates the customer exactly once and returns before/after data so the route audit contract can be tested independently from SQLAlchemy.

Run:

```bash
cd CRM-Server && pytest tests/unit/test_customer_snapshot_crud.py tests/unit/test_customer_update_concurrency.py tests/unit/api/test_customer_edit_api.py -q
```

Expected: the new tests fail because the ordinary route still has a second lock path and does not accept status/license fields.

### Step 2: Implement the single locked update

Implement `CustomerCRUD.update_with_audit` using this order:

1. Lock by both `Customer.id == db_obj.id` and `Customer.team_id == db_obj.team_id` with `.populate_existing().with_for_update().first()`.
2. Raise `ConflictException("客户已不存在，请刷新后确认最新状态")` when the row is absent.
3. Compare the locked version with `obj_in.expected_version` before assigning any field. Raise `ConflictException("客户已发生变化，请刷新后确认最新状态")` on mismatch.
4. Resolve a supplied industry as a canonical active code. Permit the customer’s current inactive code only when the submitted code equals the current code. Reject another inactive code and missing code with `ValueError("行业代码不存在或已停用")`.
5. When `status` is explicitly supplied, reject a locked current status outside `{0, 1}` with `ValueError("仅允许更新跟进中或已成交客户的状态")`. Do not call the status transition service and do not queue a notification.
6. When either license field is explicit, resolve the effective pair from the request and locked row:

```python
license_type = obj_in.license_type if "license_type" in fields_set else locked_customer.license_type
license_expiry_date = obj_in.license_expiry_date if "license_expiry_date" in fields_set else locked_customer.license_expiry_date
if license_expiry_date is None:
    license_type = None
elif license_type is None:
    raise ValueError("授权到期日期不为空时必须选择授权类型")
```

7. Resolve source public IDs using the existing acquisition-source helper. Never expose `source_id` in the audit result.
8. Compare fields in this exact order: `account_name`, `city`, `address`, `company_scale`, `source_public_id`, `default_procurement_method_id`, `industry`, `status`, `license_type`, `license_expiry_date`.
9. Build `before` and `after` dictionaries only for fields whose persisted values differ. Convert dates to ISO strings when building the route log; retain native date values in the CRUD return for unit-level comparison.
10. When at least one actual field differs, assign all requested values, increment `version` once, commit once, refresh once, and return the customer plus snapshots. When no field differs, return empty snapshots without commit.

The compatibility `update` method calls `update_with_audit` and discards the two snapshots. Do not retain a second optimistic-lock implementation.

### Step 3: Move ordinary route audit to the unified update result

In `update_customer`:

- Remove the route-level manual lock query.
- Keep `_get_editable_customer` and account-name uniqueness validation.
- Call `customer_crud.update_with_audit` once.
- Map `ConflictException` to 409, `AcquisitionSourceError` to the existing source response, and `ValueError` to 400.
- Serialize the returned date values with `.isoformat()`.
- Use the insertion order of the returned snapshots as `changed_fields`.
- When changes exist, write exactly one `EventTypes.CUSTOMER_UPDATED` entry whose content has only `changed_fields`, `before`, and `after`.
- Trigger exactly one partial customer intelligence refresh with `change_type="updated"` and the same changed field list.
- Do not call `customer_status_transition_service`, `outbound_notification_job_service`, License application code, or approval code.

### Step 4: Run focused backend tests and commit

Run:

```bash
cd CRM-Server && pytest tests/unit/test_customer_snapshot_crud.py tests/unit/test_customer_update_concurrency.py tests/unit/api/test_customer_edit_api.py -q
```

Expected: PASS. Commit:

```bash
git add CRM-Server/app/crud/customer.py CRM-Server/app/api/customers.py CRM-Server/tests/unit/test_customer_snapshot_crud.py CRM-Server/tests/unit/test_customer_update_concurrency.py CRM-Server/tests/unit/api/test_customer_edit_api.py
git commit -m "feat(customer): unify versioned customer updates"
```

## Task 4: Preserve explicit lifecycle and formal License boundaries

**Files:**
- Keep: `CRM-Server/app/services/customer_status_transition_service.py`
- Keep: `CRM-Server/app/api/customers.py:1742-1863,2035-2075`
- Modify: `CRM-Server/tests/unit/test_customer_status_transition_service.py`
- Modify: `CRM-Server/tests/unit/api/test_customer_edit_api.py`

**Interfaces:**

- `PATCH /v1/customers/{customer_id}/lifecycle-status` remains the specialized 0/1 route and retains its existing won notification, `CUSTOMER_STATUS_CHANGED` audit, and partial refresh.
- `PATCH /v1/customers/{customer_id}/license-snapshot` remains the specialized complete-pair route and retains `CUSTOMER_LICENSE_SNAPSHOT_UPDATED`.
- The customer dialog does not call either route.

### Step 1: Lock the specialized lifecycle matrix

Keep these exact service tests in `test_customer_status_transition_service.py`:

```python
def test_plans_following_to_won_with_won_notification():
    decision = customer_status_transition_service.plan(current_status=0, target_status=1)
    assert decision.previous_status == 0
    assert decision.new_status == 1
    assert decision.notification_event == OutboundNotificationEventType.ACCOUNT_STATUS_WON


def test_plans_won_to_following_without_notification():
    decision = customer_status_transition_service.plan(current_status=1, target_status=0)
    assert decision.previous_status == 1
    assert decision.new_status == 0
    assert decision.notification_event is None


@pytest.mark.parametrize("current_status", [2, 3])
def test_rejects_non_lifecycle_current_status(current_status: int):
    with pytest.raises(CustomerStatusTransitionError):
        customer_status_transition_service.plan(current_status=current_status, target_status=0)


@pytest.mark.parametrize("target_status", [2, 3])
def test_rejects_non_lifecycle_target_status(target_status: int):
    with pytest.raises(CustomerStatusTransitionError):
        customer_status_transition_service.plan(current_status=0, target_status=target_status)


def test_rejects_noop_transition():
    with pytest.raises(CustomerStatusTransitionError):
        customer_status_transition_service.plan(current_status=0, target_status=0)
```

Add a route assertion that the specialized lifecycle route still queues `ACCOUNT_STATUS_WON`, while the ordinary PUT test in Task 3 records no notification.

### Step 2: Keep the formal License boundary observable

Retain the existing dedicated snapshot route tests for:

- valid trial and official pairs;
- empty date normalizing type to `None`;
- stale version returning 409;
- permission denial returning 403;
- dedicated audit event and partial refresh;
- no mutation on validation failure.

Add this assertion to the ordinary PUT test:

```python
assert calls.notifications == []
assert calls.logs[0]["event_type"] == customers_api.EventTypes.CUSTOMER_UPDATED
assert customers_api.EventTypes.CUSTOMER_STATUS_CHANGED not in [entry["event_type"] for entry in calls.logs]
```

The customer create test from Task 2 must assert that a status `1` initial record also produces no outbound notification. No test should invoke a License application service for either ordinary create or ordinary PUT.

### Step 3: Run regression tests and commit

Run:

```bash
cd CRM-Server && pytest tests/unit/test_customer_status_transition_service.py tests/unit/api/test_customer_edit_api.py -q
```

Expected: PASS. Commit only when compatibility code or tests changed:

```bash
git add CRM-Server/app/services/customer_status_transition_service.py CRM-Server/app/api/customers.py CRM-Server/tests/unit/test_customer_status_transition_service.py CRM-Server/tests/unit/api/test_customer_edit_api.py
git commit -m "test(customer): preserve specialized workflow boundaries"
```

## Task 5: Complete frontend schemas, API clients, and the unified dirty diff

**Files:**
- Modify: `CRM-Client/src/api/customer.ts:529-630`
- Modify: `CRM-Client/src/schemas/customer.ts:37-145,291-303`
- Modify: `CRM-Client/src/components/dialogs/customerFormDiff.ts`
- Modify: `CRM-Client/src/api/__tests__/customer.test.ts`
- Modify: `CRM-Client/src/components/dialogs/__tests__/customerFormDiff.test.ts`

**Interfaces:**

```typescript
export interface CustomerEditableSnapshot {
  account_name: string | null
  city: string | null
  address: string | null
  company_scale: string | null
  source_public_id: string | null
  default_procurement_method_id: number | null
  industry: string | null
  status: 0 | 1 | null
  license_type: 'TRIAL' | 'OFFICIAL' | null
  license_expiry_date: string | null
}

export function buildCustomerUpdatePayload(
  current: CustomerEditableSnapshot,
  baseline: CustomerEditableSnapshot,
  expectedVersion: number,
): (CustomerUpdate & { expected_version: number }) | null
```

### Step 1: Write failing diff tests

Replace the old baseline in `customerFormDiff.test.ts` with this complete value:

```typescript
const baselineSnapshot: CustomerEditableSnapshot = {
  account_name: '客户 A',
  city: '上海',
  address: '浦东',
  company_scale: '51-200人',
  source_public_id: 'acq_source',
  default_procurement_method_id: 8,
  industry: 'internet_saas',
  status: 0,
  license_type: 'TRIAL',
  license_expiry_date: '2026-12-31',
}
```

Add these tests:

```typescript
it('sends one changed ordinary field and expected version', () => {
  const current: CustomerEditableSnapshot = {
    account_name: '客户 A',
    city: '深圳',
    address: '浦东',
    company_scale: '51-200人',
    source_public_id: 'acq_source',
    default_procurement_method_id: 8,
    industry: 'internet_saas',
    status: 0,
    license_type: 'TRIAL',
    license_expiry_date: '2026-12-31',
  }
  expect(buildCustomerUpdatePayload(current, baselineSnapshot, 12)).toEqual({
    expected_version: 12,
    city: '深圳',
  })
})

it('includes status in the ordinary update diff', () => {
  const current: CustomerEditableSnapshot = {
    account_name: '客户 A',
    city: '上海',
    address: '浦东',
    company_scale: '51-200人',
    source_public_id: 'acq_source',
    default_procurement_method_id: 8,
    industry: 'internet_saas',
    status: 1,
    license_type: 'TRIAL',
    license_expiry_date: '2026-12-31',
  }
  expect(buildCustomerUpdatePayload(current, baselineSnapshot, 12)).toEqual({
    expected_version: 12,
    status: 1,
  })
})

it('sends the complete license pair when only the type changes', () => {
  const current: CustomerEditableSnapshot = {
    account_name: '客户 A',
    city: '上海',
    address: '浦东',
    company_scale: '51-200人',
    source_public_id: 'acq_source',
    default_procurement_method_id: 8,
    industry: 'internet_saas',
    status: 0,
    license_type: 'OFFICIAL',
    license_expiry_date: '2026-12-31',
  }
  expect(buildCustomerUpdatePayload(current, baselineSnapshot, 12)).toEqual({
    expected_version: 12,
    license_type: 'OFFICIAL',
    license_expiry_date: '2026-12-31',
  })
})

it('normalizes an empty license date to an empty pair', () => {
  const current: CustomerEditableSnapshot = {
    account_name: '客户 A',
    city: '上海',
    address: '浦东',
    company_scale: '51-200人',
    source_public_id: 'acq_source',
    default_procurement_method_id: 8,
    industry: 'internet_saas',
    status: 0,
    license_type: 'OFFICIAL',
    license_expiry_date: '',
  }
  expect(buildCustomerUpdatePayload(current, baselineSnapshot, 12)).toEqual({
    expected_version: 12,
    license_type: null,
    license_expiry_date: null,
  })
})

it('returns null when every business value is unchanged', () => {
  expect(buildCustomerUpdatePayload(baselineSnapshot, baselineSnapshot, 12)).toBeNull()
})
```

### Step 2: Implement the typed helper

In `customerFormDiff.ts`:

- export `CustomerEditableSnapshot`;
- normalize text and date-only strings by trimming empty values to `null`;
- normalize procurement IDs to finite numbers or `null`;
- compare ordinary fields in a fixed tuple order;
- compare status as `0 | 1 | null`;
- treat license type and expiry as one logical group;
- when either license value differs, assign both normalized license keys to the payload;
- return `null` when no business field differs;
- construct the payload through explicit property assignments and a `switch`, never through a broad object cast.

The license normalization must follow this exact rule:

```typescript
const normalizedExpiry = normalizeDate(current.license_expiry_date)
const normalizedType = normalizedExpiry === null ? null : current.license_type
```

This prevents a type-only value from creating an “authorized” snapshot without a date.

### Step 3: Complete API schema plumbing and tests

In `customer.ts`, keep these methods and ensure each response uses `CustomerResponseSchema`:

```typescript
getIndustryHierarchy: (): Promise<CustomerIndustryHierarchy> =>
  api.get('/v1/industries/hierarchy', undefined, CustomerIndustryHierarchySchema),

updateCustomer: (customerId: string, data: CustomerUpdate): Promise<CustomerResponse> =>
  api.put('/v1/customers/' + customerId, data, undefined, CustomerResponseSchema),

updateCustomerLifecycleStatus: (customerId: string, data: CustomerLifecycleStatusUpdate): Promise<CustomerResponse> =>
  api.patch('/v1/customers/' + customerId + '/lifecycle-status', data, undefined, CustomerResponseSchema),

updateCustomerLicenseSnapshot: (customerId: string, data: CustomerLicenseSnapshotUpdate): Promise<CustomerResponse> =>
  api.patch('/v1/customers/' + customerId + '/license-snapshot', data, undefined, CustomerResponseSchema),
```

Extend `customer.test.ts` request mocks to include `post` and `put`. Add exact assertions for the ordinary PUT path and payload, plus malformed response rejection through Zod. Keep the existing exact hierarchy and compatibility PATCH assertions.

Run:

```bash
cd CRM-Client && npm run test:unit -- --run src/components/dialogs/__tests__/customerFormDiff.test.ts src/api/__tests__/customer.test.ts
```

Expected: PASS. Commit:

```bash
git add CRM-Client/src/api/customer.ts CRM-Client/src/schemas/customer.ts CRM-Client/src/components/dialogs/customerFormDiff.ts CRM-Client/src/api/__tests__/customer.test.ts CRM-Client/src/components/dialogs/__tests__/customerFormDiff.test.ts
git commit -m "feat(customer): add unified frontend customer diff"
```

## Task 6: Verify the database-backed industry selector

**Files:**
- Keep or modify: `CRM-Client/src/components/crmwolf/IndustryHierarchySelectField.vue`
- Keep: `CRM-Client/src/components/crmwolf/index.ts:16`
- Modify: `CRM-Client/src/components/crmwolf/__tests__/IndustryHierarchySelectField.test.ts`

**Interfaces:**

```typescript
interface Props {
  modelValue?: string
  hierarchy?: CustomerIndustryHierarchy
  retainedIndustryInfo?: CustomerIndustryInfo | null
  id?: string
  label?: string
  placeholder?: string
  helperText?: string
  error?: string
  disabled?: boolean
  loading?: boolean
}

'update:modelValue': [value: string]
```

### Step 1: Keep public-surface tests green

Use this hierarchy fixture in the existing selector test file:

```typescript
const hierarchy = {
  internet: {
    name: '互联网',
    children: [
      { code: 'internet_saas', name: 'SaaS公司' },
      { code: 'internet_social', name: '社交媒体' },
    ],
  },
}
```

The test suite must contain complete tests for:

```typescript
it('renders the selected full path', () => {
  const wrapper = mount(IndustryHierarchySelectField, {
    props: { modelValue: 'internet_saas', hierarchy },
  })
  expect(wrapper.get('button[role="combobox"]').text()).toContain('互联网 / SaaS公司')
  wrapper.unmount()
})

it('searches both primary and secondary names', async () => {
  const wrapper = mount(IndustryHierarchySelectField, {
    props: { modelValue: '', hierarchy },
    attachTo: document.body,
  })
  await wrapper.get('button[role="combobox"]').trigger('click')
  await wrapper.get('input[placeholder="搜索行业"]').setValue('互联网')
  expect(document.body.textContent).toContain('SaaS公司')
  await wrapper.get('input[placeholder="搜索行业"]').setValue('社交媒体')
  expect(document.body.textContent).toContain('社交媒体')
  wrapper.unmount()
})

it('emits a child code', async () => {
  const wrapper = mount(IndustryHierarchySelectField, {
    props: { modelValue: '', hierarchy },
    attachTo: document.body,
  })
  await wrapper.get('button[role="combobox"]').trigger('click')
  const option = Array.from(document.body.querySelectorAll('[role="option"]')).find((element) => element.textContent?.includes('社交媒体') === true)
  expect(option).toBeInstanceOf(HTMLElement)
  if (!(option instanceof HTMLElement)) throw new Error('行业选项未渲染')
  option.click()
  expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['internet_social'])
  wrapper.unmount()
})

it('emits a primary code for a group without children', async () => {
  const wrapper = mount(IndustryHierarchySelectField, {
    props: { modelValue: '', hierarchy: { manufacturing: { name: '制造业', children: [] } } },
    attachTo: document.body,
  })
  await wrapper.get('button[role="combobox"]').trigger('click')
  const option = Array.from(document.body.querySelectorAll('[role="option"]')).find((element) => element.textContent?.includes('制造业') === true)
  expect(option).toBeInstanceOf(HTMLElement)
  if (!(option instanceof HTMLElement)) throw new Error('一级行业选项未渲染')
  option.click()
  expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['manufacturing'])
  wrapper.unmount()
})

it('renders a retained inactive value as a disabled option', async () => {
  const wrapper = mount(IndustryHierarchySelectField, {
    props: {
      modelValue: 'legacy_industry',
      hierarchy: {},
      retainedIndustryInfo: { code: 'legacy_industry', name: '传统行业 / 已停用' },
    },
    attachTo: document.body,
  })
  await wrapper.get('button[role="combobox"]').trigger('click')
  const option = Array.from(document.body.querySelectorAll('[role="option"]')).find((element) => element.textContent?.includes('传统行业 / 已停用') === true)
  expect(option?.hasAttribute('data-disabled')).toBe(true)
  wrapper.unmount()
})
```

### Step 2: Implement only missing selector behavior

Flatten active hierarchy groups to `{ primaryCode, primaryName, code, name, label }`. Use the primary and child names in `text-value`. For a primary group with no children, make the primary code selectable. For a current value absent from active hierarchy, render a disabled `当前行业` option and preserve its full detail label.

The trigger must expose the supplied `id`, visible label, `role="combobox"`, `aria-expanded`, `aria-invalid`, and `aria-describedby`. The list must use the shared input height and its own vertical scroll. `loading` and `error` must disable only this selector; they must not remove the retained current value.

### Step 3: Run selector tests and commit

Run:

```bash
cd CRM-Client && npm run test:unit -- --run src/components/crmwolf/__tests__/IndustryHierarchySelectField.test.ts
```

Expected: PASS. Commit only when the selector or its tests changed:

```bash
git add CRM-Client/src/components/crmwolf/IndustryHierarchySelectField.vue CRM-Client/src/components/crmwolf/index.ts CRM-Client/src/components/crmwolf/__tests__/IndustryHierarchySelectField.test.ts
git commit -m "feat(customer): verify hierarchy industry selector"
```

## Task 7: Cut `CustomerFormDialog` over to one flat progressive form

**Files:**
- Modify: `CRM-Client/src/components/dialogs/CustomerFormDialog.vue`
- Modify: `CRM-Client/src/components/dialogs/__tests__/CustomerFormDialog.test.ts`

**Interfaces:**

```typescript
'update:open': [value: boolean]
'success': [payload?: FormSuccessPayload]
```

Remove the dialog-only `refresh` event. The dialog closes after a successful create or edit and emits the existing `success` payload. There is no inline save event.

### Step 1: Replace intermediate separate-save tests with final behavior tests

In `CustomerFormDialog.test.ts`, retain the existing mount stubs and add or replace tests with these assertions:

```typescript
it('renders the more-information trigger collapsed in create and edit modes', async () => {
  const createWrapper = mountCreate()
  const editWrapper = mountEdit()
  await flushPromises()
  expect(createWrapper.get('#customer-more-info-trigger').attributes('aria-expanded')).toBe('false')
  expect(editWrapper.get('#customer-more-info-trigger').attributes('aria-expanded')).toBe('false')
  createWrapper.unmount()
  editWrapper.unmount()
})

it('renders one flat more-information group without independent save actions', async () => {
  const wrapper = mountEdit({ ...customerDetail, status: 0 })
  await flushPromises()
  await wrapper.get('#customer-more-info-trigger').trigger('click')
  expect(wrapper.text()).toContain('行业')
  expect(wrapper.text()).toContain('客户状态')
  expect(wrapper.text()).toContain('授权类型')
  expect(wrapper.text()).toContain('授权到期日')
  expect(wrapper.findAll('button').some((button) => button.text() === '应用状态变更')).toBe(false)
  expect(wrapper.findAll('button').some((button) => button.text() === '保存授权信息')).toBe(false)
  expect(wrapper.findAll('button').some((button) => button.text() === '清除日期')).toBe(false)
  expect(wrapper.findAll('button').filter((button) => button.text() === '保存客户资料')).toHaveLength(1)
  wrapper.unmount()
})

it('saves profile, industry, status, and license in one ordinary PUT', async () => {
  const updateCustomer = vi.spyOn(customerApi, 'updateCustomer').mockResolvedValue({
    id: 'customer-1',
    public_id: 'CUS-001',
    account_name: '测试客户',
    industry: 'finance_securities',
    city: '上海',
    address: '测试地址',
    company_scale: 'small',
    source: null,
    status: 1,
    owner_id: '1',
    source_lead_id: null,
    default_procurement_method_id: 1,
    return_reason: null,
    returned_time: null,
    creator_id: '1',
    created_time: '2026-09-04T00:00:00Z',
    last_modified_time: '2026-09-14T00:00:00Z',
    version: 4,
    license_expiry_date: '2027-01-01',
    license_type: 'OFFICIAL',
  })
  const wrapper = mountEdit({ ...customerDetail, status: 0, version: 3 })
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    setValues: (values: Record<string, unknown>) => void
    industryValue: string
    lifecycleStatusValue: 0 | 1 | null
    licenseTypeValue: 'TRIAL' | 'OFFICIAL' | null
    licenseExpiryDateValue: string | null
    onSubmit: (event: Event) => Promise<void>
  }
  vm.setValues({ city: '上海' })
  vm.industryValue = 'finance_securities'
  vm.lifecycleStatusValue = 1
  vm.licenseTypeValue = 'OFFICIAL'
  vm.licenseExpiryDateValue = '2027-01-01'
  await vm.onSubmit(new Event('submit'))
  await flushPromises()

  expect(updateCustomer).toHaveBeenCalledTimes(1)
  expect(updateCustomer).toHaveBeenCalledWith('customer-1', {
    expected_version: 3,
    city: '上海',
    industry: 'finance_securities',
    status: 1,
    license_type: 'OFFICIAL',
    license_expiry_date: '2027-01-01',
  })
  expect(wrapper.emitted('update:open')).toContainEqual([false])
  expect(wrapper.emitted('success')).toHaveLength(1)
  wrapper.unmount()
})
```

Add this create test using the existing required-field setup in the file:

```typescript
it('sends optional more-information values through the create POST', async () => {
  const createCustomer = vi.spyOn(customerApi, 'createCustomer').mockResolvedValue({
    id: 'customer-created',
    public_id: 'CUS-CREATED',
    account_name: '新客户',
    industry: 'internet_saas',
    city: '上海',
    address: null,
    company_scale: '1-50人',
    source: null,
    status: 1,
    owner_id: '1',
    source_lead_id: null,
    default_procurement_method_id: 1,
    return_reason: null,
    returned_time: null,
    creator_id: '1',
    created_time: '2026-09-14T00:00:00Z',
    last_modified_time: '2026-09-14T00:00:00Z',
    version: 1,
    license_expiry_date: '2026-12-31',
    license_type: 'TRIAL',
  })
  const wrapper = mountCreateAndFillRequiredFields()
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    industryValue: string
    lifecycleStatusValue: 0 | 1 | null
    licenseTypeValue: 'TRIAL' | 'OFFICIAL' | null
    licenseExpiryDateValue: string | null
    onSubmit: (event: Event) => Promise<void>
  }
  vm.industryValue = 'internet_saas'
  vm.lifecycleStatusValue = 1
  vm.licenseTypeValue = 'TRIAL'
  vm.licenseExpiryDateValue = '2026-12-31'
  await vm.onSubmit(new Event('submit'))
  await flushPromises()

  expect(createCustomer).toHaveBeenCalledWith(expect.objectContaining({
    industry: 'internet_saas',
    status: 1,
    license_type: 'TRIAL',
    license_expiry_date: '2026-12-31',
  }))
  wrapper.unmount()
})
```

Run the focused dialog suite before changing the component. The new assertions must fail against the current separate-button implementation.

### Step 2: Use one form-session state

In `CustomerFormDialog.vue`:

- retain typed refs for `moreInfoOpen`, `industryValue`, `retainedIndustryInfo`, `lifecycleStatusValue`, `licenseTypeValue`, and `licenseExpiryDateValue`;
- retain matching edit baselines and `loadedVersion`;
- remove `lifecycleSubmitting`, `licenseSubmitting`, `lifecycleError`, `licenseError`, `saveLifecycleStatus`, `saveLicenseSnapshot`, and `clearLicenseExpiryDate`;
- define `writeSubmitting` as `computed(() => submitting.value)`;
- keep one `submitError` for the ordinary save;
- reset all more-information state, errors, retained industry info, and `moreInfoOpen` on every create/edit/customer session change;
- initialize create status and license values to `null`, allowing the backend to default status to `0`;
- initialize edit status to `0` or `1`; map status `2` and `3` to a read-only display with no editable status value;
- start `getIndustryHierarchy()` on first expand in both modes;
- when hierarchy loading fails, disable only the industry control and render a retry button;
- keep ordinary profile controls, status control, and license controls enabled when industry loading fails.

Build the edit baseline as a complete `CustomerEditableSnapshot`. For status `2` or `3`, store `status: null` in the editable baseline so the ordinary PUT cannot overwrite it.

Before submit, validate the complete more-information snapshot with the shared form refinement. A non-empty date without a type must produce a field error on `license_expiry_date`; no network write may occur.

### Step 3: Render the flat disclosure area

Change the `Collapsible` from edit-only to both modes. Use this trigger contract:

```vue
<Collapsible
  :open="moreInfoOpen"
  class="space-y-3 border-t border-slate-200 pt-4"
  @update:open="handleMoreInfoChange"
>
  <CollapsibleTrigger as-child>
    <button
      id="customer-more-info-trigger"
      type="button"
      class="flex h-input-mobile min-h-input-mobile w-full items-center justify-between rounded-wolf-lg border border-blue-200 bg-blue-50/60 px-3 text-left text-sm font-semibold text-blue-900"
      :aria-expanded="moreInfoOpen"
      aria-controls="customer-more-info-content"
    >
      <span>{{ moreInfoOpen ? '收起更多客户信息' : '更多客户信息' }}</span>
      <span class="text-xs font-semibold text-blue-700">已填写 {{ moreInfoCount }} 项</span>
    </button>
  </CollapsibleTrigger>
  <CollapsibleContent id="customer-more-info-content" class="grid gap-4 px-1 pt-1">
    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <IndustryHierarchySelectField
        id="customer-industry"
        v-model="industryValue"
        :hierarchy="industryHierarchy"
        :loading="industryHierarchyLoading"
        :error="industryHierarchyError?.description ?? industryErrorMessage"
        :disabled="industryHierarchyError !== null"
        :retained-industry-info="retainedIndustryInfo"
        label="行业"
      />
      <SelectField
        id="customer-lifecycle-status"
        :model-value="lifecycleStatusValue ?? ''"
        label="客户状态"
        :options="[{ value: 0, label: '跟进中' }, { value: 1, label: '已成交' }]"
        :disabled="statusIsReadOnly || writeSubmitting"
        @update:model-value="handleLifecycleStatusChange"
      />
      <SelectField
        id="customer-license-type"
        :model-value="licenseTypeValue ?? ''"
        label="授权类型"
        :options="[{ value: 'TRIAL', label: '试用' }, { value: 'OFFICIAL', label: '正式' }]"
        :disabled="writeSubmitting"
        @update:model-value="handleLicenseTypeChange"
      />
      <DateField
        id="customer-license-expiry-date"
        label="授权到期日"
        :model-value="licenseExpiryDateValue === null ? null : new Date(`${licenseExpiryDateValue}T00:00:00`)"
        :disabled="writeSubmitting"
        @update:model-value="licenseExpiryDateValue = $event === null ? null : formatLocalDate($event)"
      />
    </div>
    <p v-if="statusIsReadOnly" class="text-xs leading-relaxed text-slate-500">该客户状态由其他流程管理，暂不支持在此修改。</p>
    <p class="text-xs leading-relaxed text-slate-500">此处只更新客户授权汇总信息，不创建 License 申请、不发起审批，也不修改正式 License 记录。</p>
    <p class="text-sm text-slate-700"><span class="font-medium">授权状态：</span>{{ licenseStatusLabel(licenseExpiryDateValue, licenseTypeValue) }}</p>
  </CollapsibleContent>
</Collapsible>
```

Do not render any save button inside the content. The footer is the only place containing `创建客户` or `保存客户资料`.

### Step 4: Implement the unified submit path

For create, construct `CustomerCreate` with required values and add optional properties only when their values are present:

```typescript
const createPayload: CustomerCreate = {
  account_name: createData.account_name,
  city: createData.city,
  address: normalizeOptionalText(createData.address),
  company_scale: createData.company_scale ?? null,
  source_public_id: createData.source_public_id,
  default_procurement_method_id: createData.default_procurement_method_id ?? null,
  primary_contact: {
    name: createData.contact_name,
    mobile: createData.contact_mobile,
    position: createData.contact_position,
    gender: mapContactGenderToApi(createData.contact_gender),
    is_decision_maker: false,
  },
}
const createIndustry = normalizeIndustryValue(industryValue.value)
if (createIndustry !== null) createPayload.industry = createIndustry
if (lifecycleStatusValue.value !== null) createPayload.status = lifecycleStatusValue.value
const createExpiry = normalizeDateValue(licenseExpiryDateValue.value)
if (createExpiry !== null && licenseTypeValue.value !== null) {
  createPayload.license_type = licenseTypeValue.value
  createPayload.license_expiry_date = createExpiry
}
```

For edit, construct `currentSnapshot` and `baselineSnapshot`, then call `buildCustomerUpdatePayload`. If it returns `null`, close through the ordinary clean-success path without a PUT. Otherwise call `updateCustomer` once with the returned payload. On success, update every baseline and `loadedVersion`, clear dirty state, approve close, emit `update:open=false`, then emit the existing success payload.

On any failed write, keep all current input and the dialog open. Map server field errors to the matching controls and expand the more-information area before focusing an error in that area. Never call the compatibility lifecycle or snapshot methods from this component.

### Step 5: Implement conflict recovery for all fields

`refreshConflict(false)` loads the latest detail, replaces all form and more-information values, resets every baseline, clears errors, and leaves the dialog open.

`refreshConflict(true)` loads the latest detail and applies these exact rules:

- preserve each ordinary profile field only when it differs from the old profile baseline;
- preserve industry only when it differs from the old industry baseline;
- preserve the status target only when the old status target differs from its baseline;
- preserve the license type and expiry as one pair only when either differs from its old baseline;
- replace untouched values with latest server values;
- update `loadedVersion` and all new baselines from latest server data;
- discard a preserved status target when latest server status is `2` or `3` and render the read-only message;
- clear field errors after a successful refresh.

### Step 6: Run dialog tests and commit

Run:

```bash
cd CRM-Client && npm run test:unit -- --run src/components/dialogs/__tests__/CustomerFormDialog.test.ts
```

Expected: PASS. Commit:

```bash
git add CRM-Client/src/components/dialogs/CustomerFormDialog.vue CRM-Client/src/components/dialogs/__tests__/CustomerFormDialog.test.ts
git commit -m "feat(customer): unify progressive customer form save"
```

## Task 8: Remove obsolete parent refresh wiring

**Files:**
- Modify: `CRM-Client/src/views/Customers.vue:687-748,1374-1381`
- Modify: `CRM-Client/src/views/CustomerDetailSheet.vue:792-813,1953-1962`
- Modify: `CRM-Client/src/components/dialogs/CustomerFormDialog.vue` only when a removed event remains in the final diff
- Modify: `CRM-Client/src/components/dialogs/__tests__/CustomerFormDialog.test.ts` only when a parent contract test exposes a real break

**Interfaces:**

- `Customers.vue` handles ordinary dialog `success` by closing the dialog and refreshing list/detail data.
- `CustomerDetailSheet.vue` handles ordinary dialog `success` by closing the dialog, reloading the current customer, and emitting its generic `refresh` event.
- `CustomerFormDialog` emits no dialog-specific `refresh` event.

### Step 1: Remove the obsolete event paths

In `Customers.vue`:

1. Delete `handleCustomerFormRefresh`.
2. Remove `@refresh="handleCustomerFormRefresh"` from `CustomerFormDialog`.
3. Keep `handleCustomerFormSuccess` and its existing list/detail recovery behavior.

In `CustomerDetailSheet.vue`:

1. Delete `handleCustomerEditRefresh`.
2. Remove `@refresh="handleCustomerEditRefresh"` from `CustomerFormDialog`.
3. Keep `handleCustomerEditSuccess` and its existing detail reload/parent refresh behavior.

Do not remove generic `refresh` handlers for unrelated panels or the backend compatibility PATCH routes.

### Step 2: Run parent-adjacent tests and commit

Run:

```bash
cd CRM-Client && npm run test:unit -- --run src/components/dialogs/__tests__/CustomerFormDialog.test.ts src/components/crmwolf/__tests__/IndustryHierarchySelectField.test.ts
```

Expected: PASS. Commit:

```bash
git add CRM-Client/src/views/Customers.vue CRM-Client/src/views/CustomerDetailSheet.vue CRM-Client/src/components/dialogs/CustomerFormDialog.vue CRM-Client/src/components/dialogs/__tests__/CustomerFormDialog.test.ts
git commit -m "refactor(customer): remove dialog inline refresh path"
```

## Task 9: Add final authorization, recovery, and accessibility coverage

**Files:**
- Modify: `CRM-Server/tests/unit/api/test_customer_edit_api.py`
- Modify: `CRM-Server/tests/unit/test_customer_snapshot_crud.py`
- Modify: `CRM-Server/tests/unit/test_customer_update_concurrency.py`
- Modify: `CRM-Client/src/components/dialogs/__tests__/CustomerFormDialog.test.ts`
- Modify: `CRM-Client/src/components/crmwolf/__tests__/IndustryHierarchySelectField.test.ts`
- Modify: `CRM-Client/src/schemas/__tests__/acquisition-source.test.ts`

**Interfaces:**

All tests exercise public API behavior or rendered component behavior. The only private-call assertions are exact request path and payload assertions in `customer.test.ts`.

### Step 1: Backend authorization and isolation cases

Add route tests with these exact outcomes:

```python
@pytest.mark.asyncio
async def test_customer_put_denies_user_without_edit_permission(monkeypatch):
    customer = _customer(status=0)
    _deny_edit_permission(monkeypatch, customer)
    with pytest.raises(customers_api.HTTPException) as exc_info:
        await customers_api.update_customer(
            customer.public_id,
            CustomerUpdate(expected_version=4, city="上海"),
            team_id=customer.team_id,
            current_user=SimpleNamespace(id=9, name="操作人"),
            db=MagicMock(),
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_customer_put_does_not_cross_team_boundary(monkeypatch):
    customer = _customer(status=0)
    _allow_edit_permission(monkeypatch, customer)
    monkeypatch.setattr(customers_api.customer_crud, "get_by_public_id", lambda db, public_id, team_id: None)
    with pytest.raises(customers_api.HTTPException) as exc_info:
        await customers_api.update_customer(
            customer.public_id,
            CustomerUpdate(expected_version=4, city="上海"),
            team_id=customer.team_id + 1,
            current_user=SimpleNamespace(id=9, name="操作人"),
            db=MagicMock(),
        )
    assert exc_info.value.status_code == 404
```

Add CRUD cases proving a current inactive industry code remains editable without changing it, while a different inactive code is rejected before mutation. Assert no commit, no audit, and no refresh in rejected cases.

### Step 2: Backend audit and version cases

Cover ordinary updates that change only:

- industry;
- status;
- the complete license pair;
- all ordinary and more-information fields together.

For each successful case assert exactly one version increment, one `CUSTOMER_UPDATED` audit, one partial refresh, no `CUSTOMER_STATUS_CHANGED`, and no outbound notification. For no-op updates assert no version increment, audit, or refresh.

### Step 3: Frontend recovery and accessibility cases

Add rendered tests covering:

```typescript
it('disables only industry after hierarchy loading failure and retries successfully', async () => {
  vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
  vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
  const getHierarchy = vi.spyOn(customerApi, 'getIndustryHierarchy')
    .mockRejectedValueOnce(new Error('hierarchy failed'))
    .mockResolvedValueOnce({ manufacturing: { name: '制造业', children: [] } })
  const wrapper = mountRecoveryEdit()
  await wrapper.get('#customer-more-info-trigger').trigger('click')
  await flushPromises()
  expect(wrapper.get('#customer-industry').attributes('disabled')).toBeDefined()
  expect(wrapper.get('#customer-account-name').attributes('disabled')).toBeUndefined()
  await wrapper.findAll('button').find((button) => button.text() === '重试')?.trigger('click')
  await flushPromises()
  expect(getHierarchy).toHaveBeenCalledTimes(2)
  expect(wrapper.get('#customer-industry').attributes('disabled')).toBeUndefined()
  wrapper.unmount()
})

it('keeps entered values and the dialog open after ordinary PUT failure', async () => {
  vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
  vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
  vi.spyOn(customerApi, 'updateCustomer').mockRejectedValue(new Error('update failed'))
  const wrapper = mountRecoveryEdit()
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    setValues: (values: Record<string, unknown>) => void
    values: Record<string, unknown>
    onSubmit: (event: Event) => Promise<void>
  }
  vm.setValues({ account_name: '当前输入' })
  await vm.onSubmit(new Event('submit'))
  await flushPromises()
  expect(vm.values.account_name).toBe('当前输入')
  expect(wrapper.props('open')).toBe(true)
  wrapper.unmount()
})

it('preserves dirty more-information values across a 409 recovery', async () => {
  vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
  vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
  vi.spyOn(customerApi, 'updateCustomer').mockRejectedValue({ response: { status: 409 } })
  vi.spyOn(customerApi, 'getCustomerDetail').mockResolvedValue({
    ...customerDetail,
    version: 11,
    city: '深圳',
    status: 0,
    industry: 'finance_securities',
    license_type: 'TRIAL',
    license_expiry_date: '2027-01-01',
  })
  const wrapper = mountRecoveryEdit({ ...customerDetail, version: 10, status: 0 })
  await flushPromises()
  const vm = wrapper.vm as unknown as {
    setValues: (values: Record<string, unknown>) => void
    industryValue: string
    lifecycleStatusValue: 0 | 1 | null
    licenseTypeValue: 'TRIAL' | 'OFFICIAL' | null
    licenseExpiryDateValue: string | null
    onSubmit: (event: Event) => Promise<void>
  }
  vm.setValues({ account_name: '当前输入' })
  vm.industryValue = 'internet_saas'
  vm.lifecycleStatusValue = 1
  vm.licenseTypeValue = 'OFFICIAL'
  vm.licenseExpiryDateValue = '2026-12-31'
  await vm.onSubmit(new Event('submit'))
  await flushPromises()
  await wrapper.findAll('button').find((button) => button.text() === '保留当前输入并继续编辑')?.trigger('click')
  await flushPromises()
  expect(vm.industryValue).toBe('internet_saas')
  expect(vm.lifecycleStatusValue).toBe(1)
  expect(vm.licenseTypeValue).toBe('OFFICIAL')
  expect(vm.licenseExpiryDateValue).toBe('2026-12-31')
  wrapper.unmount()
})

it.each([2, 3])('renders status %s as read-only and clean', async (status) => {
  const wrapper = mountRecoveryEdit({ ...customerDetail, status: status as 2 | 3 })
  await flushPromises()
  await wrapper.get('#customer-more-info-trigger').trigger('click')
  expect(wrapper.text()).toContain('该客户状态由其他流程管理，暂不支持在此修改。')
  const vm = wrapper.vm as unknown as { handleCancel: () => void; showConfirmDialog: boolean }
  vm.handleCancel()
  expect(vm.showConfirmDialog).toBe(false)
  wrapper.unmount()
})
```

Also assert `aria-expanded`, `aria-controls`, visible labels, `aria-invalid`, `aria-describedby`, 44px trigger classes, one footer save button, absence of all three removed button labels, and the fixed License explanation.

### Step 4: Run focused coverage and commit

Run:

```bash
cd CRM-Server && pytest tests/unit/api/test_customer_edit_api.py tests/unit/test_customer_snapshot_crud.py tests/unit/test_customer_update_concurrency.py tests/unit/test_customer_status_transition_service.py -q
cd CRM-Client && npm run test:unit -- --run src/components/dialogs/__tests__/CustomerFormDialog.test.ts src/components/crmwolf/__tests__/IndustryHierarchySelectField.test.ts src/components/dialogs/__tests__/customerFormDiff.test.ts src/api/__tests__/customer.test.ts src/schemas/__tests__/acquisition-source.test.ts
```

Expected: PASS. Commit:

```bash
git add CRM-Server/tests/unit/api/test_customer_edit_api.py CRM-Server/tests/unit/test_customer_snapshot_crud.py CRM-Server/tests/unit/test_customer_update_concurrency.py CRM-Server/tests/unit/test_customer_status_transition_service.py CRM-Client/src/components/dialogs/__tests__/CustomerFormDialog.test.ts CRM-Client/src/components/crmwolf/__tests__/IndustryHierarchySelectField.test.ts CRM-Client/src/schemas/__tests__/acquisition-source.test.ts
git commit -m "test(customer): cover unified form recovery boundaries"
```

## Task 10: Final verification and actual UI smoke test

**Files:**
- No planned production-file changes.
- Modify an affected source or test file only when a final verification command demonstrates a real contract failure.

### Step 1: Run focused backend verification

```bash
cd CRM-Server && pytest \
  tests/unit/test_customer_edit_contracts.py \
  tests/unit/test_customer_snapshot_crud.py \
  tests/unit/test_customer_status_transition_service.py \
  tests/unit/test_customer_update_concurrency.py \
  tests/unit/api/test_customer_edit_api.py -q
```

Expected: all selected backend tests pass.

### Step 2: Run focused frontend verification

```bash
cd CRM-Client && npm run test:unit -- --run \
  src/components/dialogs/__tests__/CustomerFormDialog.test.ts \
  src/components/crmwolf/__tests__/IndustryHierarchySelectField.test.ts \
  src/components/dialogs/__tests__/customerFormDiff.test.ts \
  src/api/__tests__/customer.test.ts \
  src/schemas/__tests__/acquisition-source.test.ts
```

Expected: all selected frontend tests pass.

### Step 3: Run type checks and lint once

```bash
cd CRM-Client && npm run type-check && npm run lint
cd CRM-Server && ruff check app/ tests/unit/test_customer_edit_contracts.py tests/unit/test_customer_snapshot_crud.py tests/unit/test_customer_status_transition_service.py tests/unit/test_customer_update_concurrency.py tests/unit/api/test_customer_edit_api.py && mypy app/
```

Expected: no TypeScript, ESLint, Ruff, or MyPy errors. Do not loosen strictness settings.

### Step 4: Run the actual browser smoke path

Start the existing client development command from `CRM-Client` and open the customer management page in Chromium. Verify these observable scenarios:

1. Create and edit dialogs open with `更多客户信息` collapsed.
2. Expanding the section in either mode loads the grouped industry hierarchy on demand.
3. Searching by primary or secondary industry name finds the expected option, and selection displays the full path.
4. A retained inactive industry remains visible and disabled.
5. Creating with only required fields sends no more-information values and the backend defaults status to `0`.
6. Creating with industry, status `1`, trial type, and a date sends one POST and the refreshed list displays the values.
7. Editing profile, industry, status, and authorization sends exactly one PUT with one `expected_version`; no lifecycle or license PATCH request is made.
8. The disclosure area contains no `应用状态变更`, `保存授权信息`, or `清除日期` action, and the footer contains one primary save button.
9. Editing a status `2` or `3` customer renders the read-only message and does not trigger the discard guard.
10. A failed PUT preserves all entered values and keeps the dialog open; a 409 offers latest-data and preserve-input recovery.
11. The License explanation is visible and no License application or approval UI opens.
12. At a narrow viewport, fields stack, the primary save button precedes cancel, the dialog scrolls internally, and the page has no horizontal overflow.

If Chromium cannot be used in the environment, run a throwaway rendered-component smoke harness and report visual verification as unavailable rather than treating unit tests as visual proof.

### Step 5: Review the owned diff

Run:

```bash
git diff --check
```

Review only the files listed in this plan. Confirm that:

- `CustomerFormDialog.vue` does not call either compatibility PATCH method;
- no removed independent save function, removed button label, clear-date action, or dialog-only refresh event remains;
- `CustomerCreate` and `CustomerUpdate` callers compile;
- specialized lifecycle, snapshot, and formal License routes remain available;
- unrelated dirty/staged changes were not reset, reformatted, or committed.

## Self-Review Checklist

- [x] Creation and editing are both covered.
- [x] Ordinary PUT is the single dialog edit boundary.
- [x] Customer and primary contact creation share one transaction.
- [x] Status `0/1` and read-only status `2/3` are specified at schema, CRUD, API, UI, and test levels.
- [x] Partial license updates resolve against the locked database pair; full create and dedicated snapshot requests validate complete pairs.
- [x] License date clearing is absent from the dialog while compatibility APIs retain their existing null behavior.
- [x] Industry hierarchy search, primary-only groups, retained inactive values, and retry behavior are covered.
- [x] Ordinary PUT audit uses actual changed fields and ISO date values.
- [x] Specialized status notification and dedicated snapshot audit remain isolated.
- [x] Existing partial implementation is treated as a cutover target rather than a second workflow.
- [x] No database migration, generic multi-business abstraction, pre-save confirmation, or unrelated refactor is proposed.
- [x] Targeted tests, final type/lint commands, and actual UI smoke scenarios are explicit.

## Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-14-customer-edit-progressive-disclosure-plan.md`.

Two execution options:

1. **Subagent-Driven (recommended):** dispatch a fresh worker per task, review the diff after each task, and integrate in order.
2. **Inline Execution:** execute the tasks in this session with checkpoint reviews and the final verification task last.
