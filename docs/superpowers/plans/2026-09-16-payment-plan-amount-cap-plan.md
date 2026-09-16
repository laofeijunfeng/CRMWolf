# 回款计划合计不超过合同金额 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 同一合同下全部回款计划金额之和不得超过合同总额；填写时即时红字，提交被前端拦住，后端按库重算兜底。

**Architecture:** `PaymentPlanCRUD` 抽出同一套分位合计断言，`create` / `batch_create` / `update` 在锁合同行后按库里全部计划重算。`PaymentPlanFormDialog` 在合同 ID 确定时拉一次该合同计划，本地算剩余可分配并预填/红字。商机详情把 `fixedContract.total_amount` 改回合同总额。

**Tech Stack:** FastAPI, SQLAlchemy, Decimal, pytest, Vue 3, TypeScript, Vitest, vue-test-utils.

**Spec:** `docs/superpowers/specs/2026-09-16-payment-plan-amount-cap-design.md`

## Global Constraints

- 不改无关脏工作区文件。当前工作区里 `CRM-Client/src/utils/opportunityProduct.ts`、`Opportunities.vue` 及其测试是别人的改动，禁止暂存或提交。
- 不改回款登记「累计实收 ≤ 该计划金额」、开票金额、合同 schema、`payment-summary.remaining_amount` 语义。
- 不给合同 API 增加 `allocated_planned_amount`。
- 金额变化时不请求后端。不禁用提交按钮。
- 不把商机详情「分完隐藏创建」扩到合同页和列表页。
- 不改 Agent 前端即时校验。Agent 只吃后端 400。
- 不做历史超限自动纠偏。编辑只拦会抬高合计的改动。
- 比较量化到分。后端禁止 `float(contract.total_amount)`。前端用 `Math.round(Number(value) * 100)`。
- 前端禁止 `any`、`as any`、`@ts-ignore` 和无必要的非空断言。
- 金额展示复用 `@/utils/format` 的 `formatCurrency`，不手拼 `¥`。
- 中间任务只跑聚焦测试；不要跑全量 lint / type-check / 浏览器 smoke，除非本任务步骤写明。
- 错误文案必须逐字：
  - 前端超限：`回款计划合计不能超过合同金额 {formatCurrency(合同总额)}，当前还可分配 {formatCurrency(剩余可分配)}`
  - 后端：`回款计划总额({合计})不能超过合同总额({合同额})`
  - 金额非法：`请输入大于 0 的计划金额`

## 文件结构与职责

- Modify: `CRM-Server/app/crud/payment.py` — `as_money`、合计断言、锁合同行、`create` / `batch_create` / `update` 接入。
- Modify: `CRM-Server/tests/unit/test_payment_plan_crud.py` — 假查询返回已有计划；合计用例。
- Modify: `CRM-Client/src/components/dialogs/PaymentPlanFormDialog.vue` — 拉计划、预填剩余、即时红字、本地拦提交。
- Modify: `CRM-Client/src/components/dialogs/__tests__/PaymentPlanFormDialog.test.ts` — mock 计划列表；预填/红字/拦提交。
- Modify: `CRM-Client/src/components/panels/OpportunityDetailContent.vue` — `fixedContract.total_amount` 改回合同总额。
- Modify: `CRM-Client/src/components/__tests__/PaymentPlansContract.test.ts` — 源码契约：禁止把剩余额赋给 `total_amount`。
- Modify: `docs/superpowers/specs/2026-09-16-payment-plan-amount-cap-design.md` — 状态改为已确认。

---

### Task 1: Backend contract-total cap in PaymentPlanCRUD

**Files:**
- Modify: `CRM-Server/tests/unit/test_payment_plan_crud.py`
- Modify: `CRM-Server/app/crud/payment.py`
- Modify: `docs/superpowers/specs/2026-09-16-payment-plan-amount-cap-design.md` 状态行改为 `已确认`

**Interfaces:**
- Consumes: existing `PaymentPlanCRUD.create` / `batch_create` / `update`; `PaymentPlanCreate`; `PaymentPlanUpdate`; `Contract.total_amount`; `PaymentPlan.planned_amount`.
- Produces: module-level `as_money(value) -> Decimal`; `PaymentPlanCRUD._lock_contract(db, contract_id) -> Contract`; `PaymentPlanCRUD._existing_planned_total(db, contract_id, exclude_plan_id: Optional[int] = None) -> Decimal`; `PaymentPlanCRUD._assert_planned_total_within_contract(contract, new_total: Decimal) -> None`. Create/batch_create reject when existing + requested > contract total. Update rejects only when new total > old total and new total > contract total.

#### Step 1: Extend the fake DB so contract queries can return existing plans

Replace `_FakeQuery` and `_FakeDb` in `CRM-Server/tests/unit/test_payment_plan_crud.py` with:

```python
class _FakeQuery:
    def __init__(self, value, *, rows=None):
        self._value = value
        self._rows = rows if rows is not None else ([] if value is None else [value])
        self._locked = False

    def filter(self, *args, **kwargs):
        return self

    def with_for_update(self):
        self._locked = True
        return self

    def first(self):
        return self._value

    def all(self):
        return list(self._rows)


class _FakeDb:
    def __init__(self, *, contract, customer, user, existing_plans=None):
        self.contract = contract
        self.customer = customer
        self.user = user
        self.existing_plans = list(existing_plans or [])
        self._next_id = 100
        self.added = []
        self.commits = 0
        self.locked_contracts = []

    def query(self, model):
        if model is PaymentPlan:
            return _FakeQuery(self.existing_plans[0] if self.existing_plans else None, rows=self.existing_plans)
        if model is PaymentPlan.planned_amount:
            return _FakeQuery(None, rows=[(plan.planned_amount,) for plan in self.existing_plans])
        values = {
            Contract: self.contract,
            Customer: self.customer,
            User: self.user,
        }
        query = _FakeQuery(values.get(model))

        original_with_for_update = query.with_for_update

        def with_for_update():
            if model is Contract:
                self.locked_contracts.append(self.contract)
            return original_with_for_update()

        query.with_for_update = with_for_update
        return query

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, PaymentPlan):
            obj.id = self._next_id
            self._next_id += 1
            obj.planned_amount = Decimal(str(obj.planned_amount))
            obj.status = obj.status or PaymentPlanStatus.PENDING
            obj.created_time = obj.created_time or business_now()
            obj.last_modified_time = obj.last_modified_time or obj.created_time
            obj.payment_records = []
            obj.invoice_applications = []

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        return None
```

Keep `_FakeDealJourneyService` and `test_batch_create_passes_team_id_to_operation_log` unchanged except that the existing test must still pass after `_FakeDb` grows the `existing_plans` argument (default empty).

Add this helper and tests after the existing test. Import `PaymentPlanUpdate` next to `PaymentPlanCreate`.

```python
from app.schemas.payment import PaymentPlanCreate, PaymentPlanUpdate


def _contract_40000():
    return SimpleNamespace(
        id=39,
        team_id=7,
        customer_id=137,
        deal_journey_id=501,
        total_amount=Decimal("40000.00"),
        contract_number="CT1",
        contract_name="合同",
    )


def _customer():
    return SimpleNamespace(id=137, team_id=7, account_name="客户")


def _user():
    return SimpleNamespace(id=1, name="Eddie")


def _plan(*, plan_id, amount, stage="已有"):
    return SimpleNamespace(
        id=plan_id,
        contract_id=39,
        planned_amount=Decimal(str(amount)),
        stage_name=stage,
        due_date=date(2026, 8, 31),
        notes=None,
        deal_journey_id=501,
    )


def _patch_create_deps(monkeypatch):
    generated_numbers = iter([f"PP{i}" for i in range(1, 20)])
    monkeypatch.setattr(
        "app.crud.payment.BusinessNumberGenerator.generate",
        lambda prefix, db: next(generated_numbers),
    )
    monkeypatch.setattr(
        "app.services.deal_journey_service.deal_journey_service",
        _FakeDealJourneyService(),
    )
    monkeypatch.setattr(
        "app.services.operation_log_service.operation_log_service.log",
        lambda **kwargs: SimpleNamespace(id=1),
    )
    monkeypatch.setattr(
        "app.crud.user.user_crud.get_by_id",
        lambda db, user_id: _user(),
    )
    monkeypatch.setattr(
        "app.crud.customer.customer_crud.get_by_id",
        lambda db, customer_id: _customer(),
    )


def test_batch_create_rejects_when_existing_plus_requested_exceeds_contract(monkeypatch):
    _patch_create_deps(monkeypatch)
    db = _FakeDb(
        contract=_contract_40000(),
        customer=_customer(),
        user=_user(),
        existing_plans=[_plan(plan_id=1, amount="12000.00")],
    )

    with pytest.raises(ValueError, match=r"回款计划总额\(42000\.00\)不能超过合同总额\(40000\.00\)"):
        payment_plan_crud.batch_create(
            db,
            contract_id=39,
            plans_data=[
                PaymentPlanCreate(stage_name="二期", planned_amount=30000, due_date=date(2026, 9, 30)),
            ],
            creator_id="1",
            team_id=7,
        )

    assert db.locked_contracts
    assert db.added == []


def test_batch_create_accepts_remaining_allocatable_amount(monkeypatch):
    _patch_create_deps(monkeypatch)
    db = _FakeDb(
        contract=_contract_40000(),
        customer=_customer(),
        user=_user(),
        existing_plans=[_plan(plan_id=1, amount="12000.00")],
    )

    result = payment_plan_crud.batch_create(
        db,
        contract_id=39,
        plans_data=[
            PaymentPlanCreate(stage_name="二期", planned_amount=28000, due_date=date(2026, 9, 30)),
        ],
        creator_id="1",
        team_id=7,
    )

    assert len(result) == 1
    assert result[0].planned_amount == Decimal("28000.00")
    assert db.locked_contracts


def test_batch_create_rejects_batch_over_contract_with_no_existing(monkeypatch):
    _patch_create_deps(monkeypatch)
    db = _FakeDb(contract=_contract_40000(), customer=_customer(), user=_user())

    with pytest.raises(ValueError, match="不能超过合同总额"):
        payment_plan_crud.batch_create(
            db,
            contract_id=39,
            plans_data=[
                PaymentPlanCreate(stage_name="A", planned_amount=20000, due_date=date(2026, 9, 1)),
                PaymentPlanCreate(stage_name="B", planned_amount=20001, due_date=date(2026, 9, 2)),
            ],
            creator_id="1",
            team_id=7,
        )


def test_batch_create_accepts_batch_equal_to_contract(monkeypatch):
    _patch_create_deps(monkeypatch)
    db = _FakeDb(contract=_contract_40000(), customer=_customer(), user=_user())

    result = payment_plan_crud.batch_create(
        db,
        contract_id=39,
        plans_data=[
            PaymentPlanCreate(stage_name="A", planned_amount=20000, due_date=date(2026, 9, 1)),
            PaymentPlanCreate(stage_name="B", planned_amount=20000, due_date=date(2026, 9, 2)),
        ],
        creator_id="1",
        team_id=7,
    )

    assert len(result) == 2


def test_create_rejects_when_existing_plus_requested_exceeds_contract(monkeypatch):
    _patch_create_deps(monkeypatch)
    db = _FakeDb(
        contract=_contract_40000(),
        customer=_customer(),
        user=_user(),
        existing_plans=[_plan(plan_id=1, amount="12000.00")],
    )

    with pytest.raises(ValueError, match="不能超过合同总额"):
        payment_plan_crud.create(
            db,
            contract_id=39,
            obj_in=PaymentPlanCreate(stage_name="二期", planned_amount=30000, due_date=date(2026, 9, 30)),
            team_id=7,
        )


def test_update_rejects_raising_total_above_contract(monkeypatch):
    monkeypatch.setattr("app.services.deal_journey_service.deal_journey_service", _FakeDealJourneyService())
    monkeypatch.setattr(
        payment_plan_crud,
        "update_status",
        lambda db, plan, commit=False: plan,
    )
    monkeypatch.setattr(
        "app.crud.payment.payment_record_crud._update_contract_payment_status",
        lambda db, contract_id, commit=False: None,
    )
    db_obj = _plan(plan_id=1, amount="12000.00", stage="一期")
    db = _FakeDb(contract=_contract_40000(), customer=_customer(), user=_user(), existing_plans=[db_obj])

    with pytest.raises(ValueError, match="不能超过合同总额"):
        payment_plan_crud.update(
            db,
            db_obj,
            PaymentPlanUpdate(planned_amount=41000),
        )


def test_update_allows_lowering_amount_when_already_over_cap(monkeypatch):
    monkeypatch.setattr("app.services.deal_journey_service.deal_journey_service", _FakeDealJourneyService())
    monkeypatch.setattr(
        payment_plan_crud,
        "update_status",
        lambda db, plan, commit=False: plan,
    )
    monkeypatch.setattr(
        "app.crud.payment.payment_record_crud._update_contract_payment_status",
        lambda db, contract_id, commit=False: None,
    )
    first = _plan(plan_id=1, amount="12000.00")
    second = _plan(plan_id=2, amount="30000.00", stage="二期")
    db = _FakeDb(
        contract=_contract_40000(),
        customer=_customer(),
        user=_user(),
        existing_plans=[first, second],
    )

    updated = payment_plan_crud.update(db, second, PaymentPlanUpdate(planned_amount=25000))
    assert Decimal(str(updated.planned_amount)) == Decimal("25000.00")


def test_update_allows_stage_only_change_when_already_over_cap(monkeypatch):
    monkeypatch.setattr("app.services.deal_journey_service.deal_journey_service", _FakeDealJourneyService())
    monkeypatch.setattr(
        payment_plan_crud,
        "update_status",
        lambda db, plan, commit=False: plan,
    )
    monkeypatch.setattr(
        "app.crud.payment.payment_record_crud._update_contract_payment_status",
        lambda db, contract_id, commit=False: None,
    )
    first = _plan(plan_id=1, amount="12000.00")
    second = _plan(plan_id=2, amount="30000.00", stage="二期")
    db = _FakeDb(
        contract=_contract_40000(),
        customer=_customer(),
        user=_user(),
        existing_plans=[first, second],
    )

    updated = payment_plan_crud.update(db, second, PaymentPlanUpdate(stage_name="尾款"))
    assert updated.stage_name == "尾款"
    assert Decimal(str(updated.planned_amount)) == Decimal("30000.00")


def test_batch_create_uses_cent_precision(monkeypatch):
    _patch_create_deps(monkeypatch)
    db = _FakeDb(
        contract=_contract_40000(),
        customer=_customer(),
        user=_user(),
        existing_plans=[_plan(plan_id=1, amount="12000.00")],
    )

    payment_plan_crud.batch_create(
        db,
        contract_id=39,
        plans_data=[
            PaymentPlanCreate(stage_name="二期", planned_amount=28000.00, due_date=date(2026, 9, 30)),
        ],
        creator_id="1",
        team_id=7,
    )

    db_over = _FakeDb(
        contract=_contract_40000(),
        customer=_customer(),
        user=_user(),
        existing_plans=[_plan(plan_id=1, amount="12000.00")],
    )
    with pytest.raises(ValueError, match="不能超过合同总额"):
        payment_plan_crud.batch_create(
            db_over,
            contract_id=39,
            plans_data=[
                PaymentPlanCreate(stage_name="二期", planned_amount=28000.01, due_date=date(2026, 9, 30)),
            ],
            creator_id="1",
            team_id=7,
        )
```

Add `import pytest` at the top of the test file.
Use `_plan()` SimpleNamespace objects for update tests. `update()` only needs `setattr` on `planned_amount` / `stage_name` plus `contract_id`, `id`, and `deal_journey_id`.

#### Step 2: Run the new tests and watch them fail

```bash
cd CRM-Server && uv run pytest tests/unit/test_payment_plan_crud.py -v
```

Expected: `test_batch_create_passes_team_id_to_operation_log` still passes. The new exceed cases FAIL because `batch_create` only sums the current request (`30000 <= 40000`) and `update` / `create` do not check contract total. `test_batch_create_accepts_remaining_allocatable_amount` may already pass for the wrong reason (it only looks at 28000 vs 40000). That is acceptable for this red step; after Step 3 it must pass because existing 12000 + 28000 = 40000.

#### Step 3: Implement the cap in CRUD

In `CRM-Server/app/crud/payment.py`, immediately after the existing `Decimal` import usage / before `class PaymentPlanCRUD`, add:

```python
TWOPLACES = Decimal("0.01")


def as_money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(TWOPLACES)
```

Inside `PaymentPlanCRUD`, add these methods (place them just above `create`):

```python
    def _lock_contract(self, db: Session, contract_id: int) -> Contract:
        contract = (
            db.query(Contract)
            .filter(Contract.id == contract_id)
            .with_for_update()
            .first()
        )
        if contract is None:
            raise ValueError("合同不存在")
        return contract

    def _existing_planned_total(
        self,
        db: Session,
        contract_id: int,
        exclude_plan_id: Optional[int] = None,
    ) -> Decimal:
        plans = db.query(PaymentPlan).filter(PaymentPlan.contract_id == contract_id).all()
        total = Decimal("0.00")
        for plan in plans:
            if exclude_plan_id is not None and getattr(plan, "id", None) == exclude_plan_id:
                continue
            total += as_money(plan.planned_amount)
        return total

    def _assert_planned_total_within_contract(self, contract: Contract, new_total: Decimal) -> None:
        contract_total = as_money(contract.total_amount)
        if new_total > contract_total:
            raise ValueError(
                f"回款计划总额({new_total})不能超过合同总额({contract_total})"
            )
```

Change `create` so the first thing after entering the method is:

```python
        contract = self._lock_contract(db, contract_id)
        new_total = self._existing_planned_total(db, contract_id) + as_money(obj_in.planned_amount)
        self._assert_planned_total_within_contract(contract, new_total)
```

Then keep generating `plan_number` and building `PaymentPlan`, but use the locked `contract.deal_journey_id` instead of a second unlocked query:

```python
            deal_journey_id=contract.deal_journey_id,
```

Remove the later `contract = db.query(Contract)...` if it is now redundant; reuse `contract` for the deal-journey event.

Change `batch_create` to replace the current `total_planned = sum(...)` / unlocked contract fetch / `float` compare with:

```python
        contract = self._lock_contract(db, contract_id)
        requested_total = sum((as_money(plan.planned_amount) for plan in plans_data), Decimal("0.00"))
        new_total = self._existing_planned_total(db, contract_id) + requested_total
        self._assert_planned_total_within_contract(contract, new_total)
```

Keep the rest of `batch_create` (number generation, add, commit, logs). For the operation log `totalPlannedAmount`, use `float(requested_total)` so the log still records this request's sum, not the all-time contract sum.

Change `update` to lock and assert **before** `setattr`:

```python
        update_data = obj_in.model_dump(exclude_unset=True)
        contract = self._lock_contract(db, db_obj.contract_id)
        old_total = self._existing_planned_total(db, db_obj.contract_id)
        if "planned_amount" in update_data:
            new_total = (
                self._existing_planned_total(db, db_obj.contract_id, exclude_plan_id=db_obj.id)
                + as_money(update_data["planned_amount"])
            )
            if new_total > old_total:
                self._assert_planned_total_within_contract(contract, new_total)

        for field, value in update_data.items():
            setattr(db_obj, field, value)
```

Then keep `update_status`, contract payment status, deal-journey refresh, commit, refresh.

Do not change payment-record amount checks. Do not change API routes. `_FakeQuery.filter` stays a no-op; exclusion of the current plan happens in the Python loop above so the fake does not need to evaluate SQLAlchemy expressions.

#### Step 4: Re-run the CRUD tests

```bash
cd CRM-Server && uv run pytest tests/unit/test_payment_plan_crud.py -v
```

Expected: PASS, including the original operation-log test.

Also change the spec status line from `已确认方向，待书面审阅` to `已确认`.

#### Step 5: Commit

```bash
git add CRM-Server/app/crud/payment.py CRM-Server/tests/unit/test_payment_plan_crud.py docs/superpowers/specs/2026-09-16-payment-plan-amount-cap-design.md
git commit -m "fix(payment): cap planned amounts to contract total"
```

Do not stage `CRM-Client/src/utils/opportunityProduct.ts` or `Opportunities.vue`.

---

### Task 2: Dialog remaining-amount load, prefill, and live validation

**Files:**
- Modify: `CRM-Client/src/components/dialogs/__tests__/PaymentPlanFormDialog.test.ts`
- Modify: `CRM-Client/src/components/dialogs/PaymentPlanFormDialog.vue`

**Interfaces:**
- Consumes: `paymentApi.getPaymentPlans(contractId)`; `contractApi.getContract(contractId)` (edit without `fixedContract` only); `formatCurrency`; existing `InputField` `error` / `helperText`.
- Produces: dialog-local `allocatedPlannedAmount` (cents of other plans), `contractTotalAmount` (cents), `remainingAllocatableAmount` (cents, floored at 0). Create prefills remaining decimal string after plans load. Live over-cap error on `#payment-plan-amount`. `validateForm()` blocks submit without calling create/update when over cap.

#### Step 1: Mock getPaymentPlans in existing tests and add failing cap tests

In `CRM-Client/src/components/dialogs/__tests__/PaymentPlanFormDialog.test.ts`:

1. Import `contractApi` and `formatCurrency` if needed. Default-mock `getPaymentPlans` to `[]` in `beforeEach` so existing tests do not hit a real request after the dialog starts loading plans.

```typescript
import contractApi from '@/api/contract'
import { formatCurrency } from '@/utils/format'

beforeEach(() => {
  vi.spyOn(paymentApi, 'getPaymentPlans').mockResolvedValue([])
})
```

Keep the existing `afterEach` `vi.restoreAllMocks()`.

2. Extend `InputStub` so it renders `helperText` / `error` from attrs/props. The current stub ignores them, so over-cap assertions cannot see the message. Replace `InputStub` with:

```typescript
const InputStub = defineComponent({
  inheritAttrs: false,
  props: {
    modelValue: { type: [String, Number], default: '' },
    error: { type: String, default: '' },
    helperText: { type: String, default: '' },
  },
  emits: ['update:modelValue'],
  setup(props, { emit, attrs }): () => VNode {
    return () => h('div', [
      h('input', {
        ...attrs,
        value: props.modelValue,
        onInput: (event: Event) => emit(
          'update:modelValue',
          (event.target as HTMLInputElement).value,
        ),
      }),
      props.error !== ''
        ? h('p', { 'data-testid': `${String(attrs.id)}-error` }, props.error)
        : props.helperText !== ''
          ? h('p', { 'data-testid': `${String(attrs.id)}-helper` }, props.helperText)
          : null,
    ])
  },
})
```

3. Add this fixture and tests after the existing cases:

```typescript
function existingPlan(amount: number, id = 9): PaymentPlanResponse {
  return {
    id,
    contract_id: 1,
    stage_name: '一期',
    planned_amount: amount,
    due_date: '2026-08-01',
    status: 'PENDING',
    payment_records: [],
    created_time: '2026-08-01T00:00:00.000Z',
    last_modified_time: '2026-08-01T00:00:00.000Z',
  }
}

it('prefills remaining allocatable amount after existing plans load', async () => {
  vi.spyOn(paymentApi, 'getPaymentPlans').mockResolvedValue([existingPlan(12000)])
  vi.spyOn(paymentApi, 'createPaymentPlans').mockResolvedValue([{ id: 2 } as PaymentPlanResponse])

  const wrapper = mount(PaymentPlanFormDialog, {
    props: {
      open: true,
      mode: 'create',
      fixedContract: { id: 1, contract_name: '合同', total_amount: 40000 },
    },
    global: { stubs: formStubs },
  })
  await flushPromises()

  expect((wrapper.get('#payment-plan-amount').element as HTMLInputElement).value).toBe('28000')
  expect(wrapper.get('[data-testid="payment-plan-amount-helper"]').text()).toBe(
    `还可分配 ${formatCurrency(28000)}`,
  )
  wrapper.unmount()
})

it('shows an over-cap field error on input and does not submit', async () => {
  vi.spyOn(paymentApi, 'getPaymentPlans').mockResolvedValue([existingPlan(12000)])
  const createSpy = vi.spyOn(paymentApi, 'createPaymentPlans').mockResolvedValue([{ id: 2 } as PaymentPlanResponse])

  const wrapper = mount(PaymentPlanFormDialog, {
    props: {
      open: true,
      mode: 'create',
      fixedContract: { id: 1, contract_name: '合同', total_amount: 40000 },
    },
    global: { stubs: formStubs },
  })
  await flushPromises()

  await wrapper.get('#payment-plan-amount').setValue('30000')
  await nextTick()

  expect(wrapper.get('[data-testid="payment-plan-amount-error"]').text()).toBe(
    `回款计划合计不能超过合同金额 ${formatCurrency(40000)}，当前还可分配 ${formatCurrency(28000)}`,
  )

  await wrapper.get('#payment-plan-stage').setValue('二期')
  await wrapper.get('#payment-plan-due-date').setValue('2026-09-04')
  await wrapper.get('form').trigger('submit')
  await flushPromises()

  expect(createSpy).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('clears the over-cap error and submits the remaining amount', async () => {
  vi.spyOn(paymentApi, 'getPaymentPlans').mockResolvedValue([existingPlan(12000)])
  const createSpy = vi.spyOn(paymentApi, 'createPaymentPlans').mockResolvedValue([{ id: 2 } as PaymentPlanResponse])

  const wrapper = mount(PaymentPlanFormDialog, {
    props: {
      open: true,
      mode: 'create',
      fixedContract: { id: 1, contract_name: '合同', total_amount: 40000 },
    },
    global: { stubs: formStubs },
  })
  await flushPromises()

  await wrapper.get('#payment-plan-amount').setValue('30000')
  await nextTick()
  await wrapper.get('#payment-plan-amount').setValue('28000')
  await nextTick()
  expect(wrapper.find('[data-testid="payment-plan-amount-error"]').exists()).toBe(false)

  await wrapper.get('#payment-plan-stage').setValue('二期')
  await wrapper.get('#payment-plan-due-date').setValue('2026-09-04')
  await wrapper.get('form').trigger('submit')
  await flushPromises()

  expect(createSpy).toHaveBeenCalled()
  wrapper.unmount()
})

it('does not flag an already-over contract when lowering the edited plan', async () => {
  const current = existingPlan(12000, 1)
  vi.spyOn(paymentApi, 'getPaymentPlans').mockResolvedValue([
    current,
    existingPlan(30000, 2),
  ])
  const updateSpy = vi.spyOn(paymentApi, 'updatePaymentPlan').mockResolvedValue({
    ...current,
    planned_amount: 11000,
  } as PaymentPlanResponse)

  const wrapper = mount(PaymentPlanFormDialog, {
    props: {
      open: true,
      mode: 'edit',
      plan: current,
      fixedContract: { id: 1, contract_name: '合同', total_amount: 40000 },
    },
    global: { stubs: formStubs },
  })
  await flushPromises()

  expect(wrapper.find('[data-testid="payment-plan-amount-error"]').exists()).toBe(false)

  await wrapper.get('#payment-plan-amount').setValue('13000')
  await nextTick()
  expect(wrapper.get('[data-testid="payment-plan-amount-error"]').text()).toContain('不能超过合同金额')

  await wrapper.get('#payment-plan-amount').setValue('11000')
  await nextTick()
  expect(wrapper.find('[data-testid="payment-plan-amount-error"]').exists()).toBe(false)

  await wrapper.get('#payment-plan-stage').setValue('一期')
  await wrapper.get('#payment-plan-due-date').setValue('2026-09-04')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(updateSpy).toHaveBeenCalled()
  wrapper.unmount()
})

it('skips over-cap errors when existing plans fail to load and still submits', async () => {
  vi.spyOn(paymentApi, 'getPaymentPlans').mockRejectedValue(new Error('network'))
  const createSpy = vi.spyOn(paymentApi, 'createPaymentPlans').mockResolvedValue([{ id: 2 } as PaymentPlanResponse])

  const wrapper = mount(PaymentPlanFormDialog, {
    props: {
      open: true,
      mode: 'create',
      fixedContract: { id: 1, contract_name: '合同', total_amount: 40000 },
    },
    global: { stubs: formStubs },
  })
  await flushPromises()

  expect((wrapper.get('#payment-plan-amount').element as HTMLInputElement).value).toBe('')
  expect(wrapper.find('[data-testid="payment-plan-amount-error"]').exists()).toBe(false)

  await fillAndSubmit(wrapper)
  expect(createSpy).toHaveBeenCalled()
  wrapper.unmount()
})
```

Add this list-page edit case in the same `describe`. It must mock `contractApi.getContract`. The edit+fixedContract case above must not call `getContract`.

```typescript
it('loads contract total when editing without a fixed contract', async () => {
  const current = existingPlan(12000, 1)
  vi.spyOn(paymentApi, 'getPaymentPlans').mockResolvedValue([current])
  vi.spyOn(contractApi, 'getContract').mockResolvedValue({
    id: 1,
    total_amount: '40000',
  } as Awaited<ReturnType<typeof contractApi.getContract>>)

  const wrapper = mount(PaymentPlanFormDialog, {
    props: {
      open: true,
      mode: 'edit',
      plan: current,
    },
    global: { stubs: formStubs },
  })
  await flushPromises()

  expect(contractApi.getContract).toHaveBeenCalledWith(1)
  expect(wrapper.get('[data-testid="payment-plan-amount-helper"]').text()).toContain(
    formatCurrency(28000),
  )
  wrapper.unmount()
})
```

#### Step 2: Run the dialog tests and watch the new cases fail

```bash
cd CRM-Client && npm run test:unit -- --run src/components/dialogs/__tests__/PaymentPlanFormDialog.test.ts
```

Expected: existing close/success tests stay green because `beforeEach` mocks `getPaymentPlans` to `[]`. New prefill/over-cap tests FAIL because the dialog still prefills `fixedContract.total_amount` (40000) and only validates `> 0`.

#### Step 3: Implement dialog allocation state

In `CRM-Client/src/components/dialogs/PaymentPlanFormDialog.vue`:

1. Import `formatCurrency` from `@/utils/format`. Keep the existing `contractApi` import.

2. Add state next to `contractsLoading`:

```typescript
const existingPlans = ref<PaymentPlanResponse[]>([])
const existingPlansLoading = ref(false)
const existingPlansFailed = ref(false)
const contractTotalOverride = ref<string | null>(null)
const contractTotalLoading = ref(false)
const contractTotalFailed = ref(false)
```

3. Add helpers (place near `getSelectedContractAmount`, then delete `getSelectedContractAmount`):

```typescript
function toCents(value: string | number): number | null {
  const amount = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(amount)) return null
  return Math.round(amount * 100)
}

function centsToAmountString(cents: number): string {
  return (cents / 100).toString()
}

const resolvedContractId = computed<number | null>(() => {
  const raw = form.contractId.trim()
  if (raw === '') return null
  const id = Number(raw)
  return Number.isInteger(id) && id > 0 ? id : null
})

const contractTotalCents = computed<number | null>(() => {
  if (contractTotalFailed.value) return null
  if (props.fixedContract !== null) {
    return toCents(props.fixedContract.total_amount)
  }
  if (contractTotalOverride.value !== null) {
    return toCents(contractTotalOverride.value)
  }
  const selected = contracts.value.find((contract) => String(contract.id) === form.contractId)
  return selected === undefined ? null : toCents(selected.total_amount)
})

const allocatedCents = computed<number>(() => {
  const currentId = props.plan?.id
  return existingPlans.value.reduce((total, plan) => {
    if (currentId !== undefined && plan.id === currentId) return total
    const cents = toCents(plan.planned_amount)
    return cents === null ? total : total + cents
  }, 0)
})

const remainingCents = computed<number | null>(() => {
  if (existingPlansFailed.value || contractTotalCents.value === null) return null
  if (existingPlansLoading.value || contractTotalLoading.value) return null
  return Math.max(0, contractTotalCents.value - allocatedCents.value)
})

const amountHelperText = computed<string>(() => {
  if (errors.plannedAmount !== '') return ''
  if (remainingCents.value === null) return ''
  return `还可分配 ${formatCurrency(remainingCents.value / 100)}`
})

function plannedAmountOverCapMessage(amountCents: number): string {
  if (remainingCents.value === null || contractTotalCents.value === null) return ''
  if (isCreateMode.value) {
    if (amountCents > remainingCents.value) {
      return `回款计划合计不能超过合同金额 ${formatCurrency(contractTotalCents.value / 100)}，当前还可分配 ${formatCurrency(remainingCents.value / 100)}`
    }
    return ''
  }
  const originalCents = toCents(props.plan?.planned_amount ?? 0) ?? 0
  const oldTotal = allocatedCents.value + originalCents
  const newTotal = allocatedCents.value + amountCents
  if (newTotal > oldTotal && newTotal > contractTotalCents.value) {
    return `回款计划合计不能超过合同金额 ${formatCurrency(contractTotalCents.value / 100)}，当前还可分配 ${formatCurrency(remainingCents.value / 100)}`
  }
  return ''
}

function validatePlannedAmount(trigger: 'input' | 'submit'): void {
  const raw = form.plannedAmount.trim()
  if (raw === '') {
    errors.plannedAmount = trigger === 'submit' ? '请输入大于 0 的计划金额' : ''
    return
  }
  const amount = Number(raw)
  if (!Number.isFinite(amount) || amount <= 0) {
    errors.plannedAmount = '请输入大于 0 的计划金额'
    return
  }
  const amountCents = toCents(raw)
  if (amountCents === null) {
    errors.plannedAmount = '请输入大于 0 的计划金额'
    return
  }
  errors.plannedAmount = plannedAmountOverCapMessage(amountCents)
}

async function loadExistingPlans(contractId: number): Promise<void> {
  existingPlansLoading.value = true
  existingPlansFailed.value = false
  try {
    existingPlans.value = await paymentApi.getPaymentPlans(contractId)
  } catch (error: unknown) {
    existingPlans.value = []
    existingPlansFailed.value = true
    handleApiError(error, '获取回款计划')
  } finally {
    existingPlansLoading.value = false
  }
}

async function loadContractTotalForEdit(contractId: number): Promise<void> {
  if (props.fixedContract !== null || isCreateMode.value) return
  contractTotalLoading.value = true
  contractTotalFailed.value = false
  try {
    const contract = await contractApi.getContract(contractId)
    contractTotalOverride.value = String(contract.total_amount)
  } catch (error: unknown) {
    contractTotalOverride.value = null
    contractTotalFailed.value = true
    handleApiError(error, '获取合同金额')
  } finally {
    contractTotalLoading.value = false
  }
}

function applyCreatePrefill(): void {
  if (!isCreateMode.value) return
  if (remainingCents.value === null) {
    form.plannedAmount = ''
    return
  }
  form.plannedAmount = remainingCents.value > 0 ? centsToAmountString(remainingCents.value) : ''
  initialForm.value = { ...form }
}
```

4. Change `resetForm` so create mode does **not** prefill from `getSelectedContractAmount()`. After setting ids/stage/date/notes:

```typescript
  form.plannedAmount = plan?.planned_amount !== undefined ? String(plan.planned_amount) : ''
```

5. Replace `validateForm`'s amount block with `validatePlannedAmount('submit')`. Keep customer/contract/stage/date checks.

6. Watch `form.plannedAmount` for live validation:

```typescript
watch(
  () => form.plannedAmount,
  () => {
    if (!visible.value) return
    validatePlannedAmount('input')
  },
)
```

7. Replace the `form.contractId` watcher that currently assigns `getSelectedContractAmount()` with one that loads plans (and does not prefill until remaining is known):

```typescript
watch(
  () => resolvedContractId.value,
  (contractId) => {
    if (!visible.value || contractId === null) {
      existingPlans.value = []
      return
    }
    void (async () => {
      await Promise.all([
        loadExistingPlans(contractId),
        loadContractTotalForEdit(contractId),
      ])
      applyCreatePrefill()
      validatePlannedAmount('input')
    })()
  },
)
```

The open watcher already calls `resetForm()` which sets `form.contractId`. The `resolvedContractId` watcher must also run on open via that assignment. Keep `{ immediate: true }` on the open watcher. Give the contract-id watcher `{ immediate: true }` as well so a pre-set fixed contract loads plans.

When `existingPlansLoading` is true, `applyCreatePrefill` must not run with stale remaining. `remainingCents` is `null` while loading, so `applyCreatePrefill` clears the amount until load finishes, then the async function calls it again. That matches spec: no flash of 40000.

8. On the amount `InputField`, add:

```vue
:helper-text="amountHelperText"
```

`error` already wins over helper in `InputField`.

9. Do not disable the submit button. Do not toast on local over-cap.

#### Step 4: Re-run the dialog suite

```bash
cd CRM-Client && npm run test:unit -- --run src/components/dialogs/__tests__/PaymentPlanFormDialog.test.ts
```

Expected: PASS, including the original four close/success tests (they mock empty plans, prefill `100` from remaining = contract 100, then `fillAndSubmit` sets amount to `100` again).

If prefill of `100` races `fillAndSubmit`, `fillAndSubmit` still sets `100` after mount; empty-plan remaining is 100 so live validation stays clean.

#### Step 5: Commit

```bash
git add CRM-Client/src/components/dialogs/PaymentPlanFormDialog.vue CRM-Client/src/components/dialogs/__tests__/PaymentPlanFormDialog.test.ts
git commit -m "fix(payment): validate payment-plan amount against remaining"
```

---

### Task 3: Stop passing remaining amount as contract total

**Files:**
- Modify: `CRM-Client/src/components/__tests__/PaymentPlansContract.test.ts`
- Modify: `CRM-Client/src/components/panels/OpportunityDetailContent.vue`

**Interfaces:**
- Consumes: `relatedContract.total_amount`; existing `remainingPaymentPlanAmount` (still used for `isPaymentPlanAmountComplete` / hide-create).
- Produces: `fixedContractForPaymentPlan.total_amount` is always `contract.total_amount`.

#### Step 1: Write the failing source contract test

Append to `CRM-Client/src/components/__tests__/PaymentPlansContract.test.ts`:

```typescript
describe('OpportunityDetailContent payment-plan fixed contract', () => {
  it('passes contract total_amount instead of remaining allocatable amount', () => {
    const source = readSource('src/components/panels/OpportunityDetailContent.vue')
    const blockStart = source.indexOf('const fixedContractForPaymentPlan')
    const blockEnd = source.indexOf('const paymentRecordDefaultAmount')
    const block = source.slice(blockStart, blockEnd)

    expect(block).toContain('total_amount: contract.total_amount')
    expect(block).not.toContain('remainingPaymentPlanAmount')
  })
})
```

#### Step 2: Run it and watch it fail

```bash
cd CRM-Client && npm run test:unit -- --run src/components/__tests__/PaymentPlansContract.test.ts
```

Expected: FAIL because the block currently assigns `remainingPaymentPlanAmount.value > 0 ? remainingPaymentPlanAmount.value : contract.total_amount`.

#### Step 3: Pass the real contract total

In `CRM-Client/src/components/panels/OpportunityDetailContent.vue`, change `fixedContractForPaymentPlan` to:

```typescript
const fixedContractForPaymentPlan = computed(() => {
  const contract = relatedContract.value
  if (contract === null) return null
  return {
    id: contract.id,
    contract_name: contract.contract_name,
    total_amount: contract.total_amount,
    customer_name: displayCustomerName.value
  }
})
```

Keep `remainingPaymentPlanAmount` and `isPaymentPlanAmountComplete` / `canCreatePaymentPlan` unchanged.

Do not change `ContractPaymentPlans.vue` (already passes contract total). Do not change `PaymentPlans.vue` (no `fixedContract`).

#### Step 4: Re-run focused tests

```bash
cd CRM-Client && npm run test:unit -- --run src/components/__tests__/PaymentPlansContract.test.ts src/components/dialogs/__tests__/PaymentPlanFormDialog.test.ts src/components/panels/OpportunityDetailContent.vue
```

`OpportunityDetailContent.vue` is not a test file. Run:

```bash
cd CRM-Client && npm run test:unit -- --run src/components/__tests__/PaymentPlansContract.test.ts src/components/dialogs/__tests__/PaymentPlanFormDialog.test.ts tests/components/OpportunityDetailContent.experience.spec.ts
```

Expected: PASS. Experience spec should stay green because it does not assert `fixedContract.total_amount`.

#### Step 5: Commit

```bash
git add CRM-Client/src/components/panels/OpportunityDetailContent.vue CRM-Client/src/components/__tests__/PaymentPlansContract.test.ts
git commit -m "fix(opportunity): pass contract total into payment-plan dialog"
```

---

## Self-Review Checklist

- [x] Spec §4 invariant: existing + requested ≤ contract total, equality allowed.
- [x] Spec §5.1 prefill remaining after plans load; empty string when remaining is 0; no 40000 flash.
- [x] Spec §5.2 helper `还可分配 {formatCurrency(...)}`.
- [x] Spec §5.3 live over-cap on input; empty amount errors only on submit; edit only flags raising the total.
- [x] Spec §5.4 plan-load failure: no over-cap, still submit.
- [x] Spec §5.5 opportunity hide-create unchanged; contract/list still open the dialog.
- [x] Spec §6.1 contract total sources, including list-page edit `getContract`.
- [x] Spec §6.2 opportunity `fixedContract.total_amount` is contract total.
- [x] Spec §7 Decimal cents, lock contract row, create/batch_create/update share assertion, raise-only update rule, error copy.
- [x] Spec §8 tests listed as concrete cases in Tasks 1–3.
- [x] No payment-record / invoice / payment-summary / allocated_planned_amount work.
- [x] No placeholders, no “similar to Task N”.
- [x] Dirty opportunityProduct files stay unstaged.

## Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-16-payment-plan-amount-cap-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks

**2. Inline Execution** — this session, executing-plans, checkpoints between tasks

Which approach?
