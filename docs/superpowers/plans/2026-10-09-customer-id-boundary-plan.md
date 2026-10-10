# 客户 ID 边界统一 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一 License、部署信息和合同创建接口的 public ID / 内部整数 ID 边界，修复有效 `cus_...` 客户创建失败，并将预期业务校验错误返回为 HTTP 400。

**Architecture:** FastAPI 请求 schema 只承载 public ID；API 完成当前团队内的 public ID 解析和权限校验后，构造独立的内部 Pydantic create schema。License、部署和合同 CRUD 只接受内部整数 ID，继续在所有多租户查询中带 `team_id`。响应继续通过现有 mapper 返回 public ID。

**Tech Stack:** Python 3、FastAPI、Pydantic v2、SQLAlchemy、pytest、ruff、mypy。

## Global Constraints

- 外部 API schema 只表达 public ID；内部 CRUD 只表达整数主键。
- 不允许 CRUD 同时兼容 public ID 和内部整数 ID。
- API 层是 public ID 到内部整数 ID 的转换边界。
- 所有客户、商机、部署和合同关联查询必须带当前 `team_id`。
- 不对外部请求模型执行把 public ID 改写成内部 ID 的 `model_copy(update=...)`。
- License 创建和部署创建的预期 `ValueError` 必须映射为 HTTP 400；未知异常和数据库异常不转换为业务 400。
- 外部请求和响应契约保持不变；不修改 CRM-Client API 契约。
- 不修改数据库模型，不新增 Alembic migration。
- 不修改 Assistant 相关脏改动。
- 创建失败不得触发业务智能刷新或其他成功后副作用。
- 生产验证前不得重复提交原 License 创建请求。
- 每个任务先写能够证明行为的失败测试，确认按预期失败后再改生产代码。
- 任务实现者跳过 formatter、lint、mypy 和项目级测试；只运行任务内的 focused pytest 命令。最终统一运行全局检查。

---

## 文件与职责映射

- `CRM-Server/app/schemas/license_application.py`: 外部 License schema 与内部 `LicenseApplicationInternalCreate`。
- `CRM-Server/app/schemas/deployment.py`: 外部部署 schema 与内部 `DeploymentInfoInternalCreate`。
- `CRM-Server/app/schemas/contract.py`: 外部合同 schema 与内部 `ContractInternalCreate`。
- `CRM-Server/app/schemas/__init__.py`: 按现有项目导出约定导出新增内部 schema。
- `CRM-Server/app/api/license_application.py`: public 客户 ID解析、内部 schema 构造和 License 创建错误映射。
- `CRM-Server/app/crud/crud_license_application.py`: 只接收内部 License schema，按整数客户主键查询。
- `CRM-Server/app/api/deployment.py`: public 客户 ID解析、内部 schema 构造和部署创建错误映射。
- `CRM-Server/app/crud/crud_deployment.py`: 只接收内部部署 schema。
- `CRM-Server/app/api/contracts.py`: public 客户/商机 ID解析、内部合同 schema 构造和两条创建路径的错误边界。
- `CRM-Server/app/crud/contract.py`: 只接收内部合同 schema；补齐从商机创建的团队过滤。
- `CRM-Server/tests/unit/test_customer_id_boundary_schemas.py`: 内部 schema 的 ID 类型边界测试。
- `CRM-Server/tests/unit/test_customer_business_object_intelligence_api.py`: License、部署、合同 API 创建路径和副作用回归测试。
- `CRM-Server/tests/unit/test_license_approval.py`: 直接 License CRUD 调用迁移为内部 schema/内部整数 ID。
- `CRM-Server/tests/unit/test_contract_source_transaction.py`: 合同两条创建路径的内部参数边界回归测试。

---

### Task 1: Add typed internal create schemas

**Files:**
- Create: `CRM-Server/tests/unit/test_customer_id_boundary_schemas.py`
- Modify: `CRM-Server/app/schemas/license_application.py`
- Modify: `CRM-Server/app/schemas/deployment.py`
- Modify: `CRM-Server/app/schemas/contract.py`
- Modify: `CRM-Server/app/schemas/__init__.py`

**Interfaces:**
- Produces `LicenseApplicationInternalCreate` with `customer_id: int`, optional `deployment_info_id: int`, optional `contract_id: int`, `license_type: LicenseType`, `authorized_users: int`, `expiry_date: date`, and optional `remark`.
- Produces `DeploymentInfoInternalCreate` with `customer_id: int`, `deployment_name: str`, `server_address: str`, optional `authorized_users: int`, and `is_default: bool`.
- Produces `ContractInternalCreate` with `customer_id: int`, `opportunity_id: int`, `signing_contact_id: int`, `contract_name: str`, `user_count: int`, `total_amount: Decimal`, `license_type: LicenseTypeEnum`, optional `subscription_years`, `signing_date`, `effective_date`, and `owner_id`.
- Existing external `LicenseApplicationCreate`, `DeploymentInfoCreate`, and `ContractCreate` remain public-ID request models.

- [ ] **Step 1: Write the failing schema boundary tests**

Create tests that exercise the public/internal distinction through Pydantic validation:

```python
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.contract import ContractInternalCreate, LicenseTypeEnum
from app.schemas.deployment import DeploymentInfoInternalCreate
from app.schemas.license_application import LicenseApplicationInternalCreate, LicenseType


def test_internal_create_schemas_accept_integer_foreign_keys():
    license_input = LicenseApplicationInternalCreate(
        customer_id=230,
        deployment_info_id=50,
        contract_id=74,
        license_type=LicenseType.OFFICIAL,
        authorized_users=10,
        expiry_date=date(2027, 12, 31),
    )
    deployment_input = DeploymentInfoInternalCreate(
        customer_id=230,
        deployment_name="生产环境",
        server_address="https://crm.example.com",
    )
    contract_input = ContractInternalCreate(
        customer_id=230,
        opportunity_id=301,
        signing_contact_id=201,
        contract_name="企业版采购合同",
        user_count=10,
        total_amount=Decimal("1000"),
        license_type=LicenseTypeEnum.SUBSCRIPTION,
        subscription_years=1,
    )

    assert license_input.customer_id == 230
    assert deployment_input.customer_id == 230
    assert contract_input.customer_id == 230
    assert contract_input.opportunity_id == 301


@pytest.mark.parametrize(
    "model, payload",
    [
        (LicenseApplicationInternalCreate, {"customer_id": "cus_230"}),
        (DeploymentInfoInternalCreate, {"customer_id": "cus_230"}),
        (ContractInternalCreate, {"customer_id": "cus_230", "opportunity_id": "opp_301"}),
    ],
)
def test_internal_create_schemas_reject_public_foreign_keys(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)
```

Use complete valid payloads where the model requires additional fields; the assertion must fail before the new classes exist because the imports are unavailable.

- [ ] **Step 2: Run the focused tests and verify the expected RED state**

Run:

```bash
cd CRM-Server
pytest tests/unit/test_customer_id_boundary_schemas.py -q
```

Expected: collection failure mentioning the three missing internal schema classes, not an unrelated environment or syntax error.

- [ ] **Step 3: Add the internal models without changing external contracts**

Implement the three classes in their existing schema modules. Reuse existing validation rules through shared non-ID bases or explicit validators; do not duplicate a weaker model that bypasses current external validation. The new internal models must preserve:

- License `authorized_users > 0`, future `expiry_date`, and official-license contract requirement.
- Deployment non-empty trimmed name and `http://`/`https://` server address.
- Contract positive user count/amount, contract name validation, and subscription-year validation.

Use these exact public names:

```python
LicenseApplicationInternalCreate
DeploymentInfoInternalCreate
ContractInternalCreate
```

Export them from `app.schemas.__init__` if the module's existing public export convention requires it.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run:

```bash
cd CRM-Server
pytest tests/unit/test_customer_id_boundary_schemas.py -q
```

Expected: all schema boundary tests pass.

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/schemas CRM-Server/tests/unit/test_customer_id_boundary_schemas.py
git commit -m "refactor(server): add internal customer ID create schemas"
```

---

### Task 2: Migrate License creation to the internal boundary

**Files:**
- Modify: `CRM-Server/tests/unit/test_customer_business_object_intelligence_api.py`
- Modify: `CRM-Server/tests/unit/test_license_approval.py`
- Modify: `CRM-Server/app/api/license_application.py:123-140`
- Modify: `CRM-Server/app/crud/crud_license_application.py:111-181,681-688`

**Interfaces:**
- `create_license_application(db, team_id, obj_in: LicenseApplicationInternalCreate, applicant_id)`.
- `LicenseApplicationCRUD.create(db, team_id, applicant_id, obj_in: LicenseApplicationInternalCreate)`.
- API continues to accept `LicenseApplicationCreate` and returns `LicenseApplicationResponse`.

- [ ] **Step 1: Add failing API regression tests**

In `test_customer_business_object_intelligence_api.py`, add a test that supplies a public customer ID, captures the object passed to `create_license_application`, and asserts the route resolves it once:

```python
def test_create_license_application_converts_public_customer_id_to_internal_schema(monkeypatch):
    captured = []
    application = _license_application()

    monkeypatch.setattr(
        license_application_api,
        "check_customer_edit_permission",
        lambda customer_id, team_id, current_user, db: _customer(),
    )
    monkeypatch.setattr(
        license_application_api,
        "create_license_application",
        lambda db, team_id, obj_in, applicant_id: captured.append(obj_in) or application,
    )
    monkeypatch.setattr(
        license_application_api,
        "_enqueue_license_application_intelligence_refresh",
        lambda *args, **kwargs: None,
    )

    result = license_application_api.create_application(
        _RequestData(
            customer_id="cus_101",
            deployment_info_id=901,
            contract_id=401,
            license_type="OFFICIAL",
            authorized_users=80,
            expiry_date=date(2027, 8, 2),
            remark="正式授权",
        ),
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=object(),
    )

    assert result.id == 1001
    assert len(captured) == 1
    assert isinstance(captured[0], LicenseApplicationInternalCreate)
    assert captured[0].customer_id == 101
```

Add a second test where the fake create function raises `ValueError("部署信息不存在或不属于该客户")`; assert `HTTPException.status_code == 400`, detail is preserved, and the enqueue spy remains empty.

- [ ] **Step 2: Run the new focused tests and verify RED**

Run:

```bash
cd CRM-Server
pytest tests/unit/test_customer_business_object_intelligence_api.py -q -k "license_application_converts_public_customer_id or license_application_value_error"
```

Expected: failure because the route currently passes the external stand-in model and does not map create-time `ValueError`.

- [ ] **Step 3: Migrate direct CRUD tests before changing the CRUD type**

In `test_license_approval.py`, import `LicenseApplicationInternalCreate` and replace the three direct `LicenseApplicationCreate(customer_id=test_customer.public_id, ...)` constructions with `LicenseApplicationInternalCreate(customer_id=test_customer.id, ...)`. Keep the existing approval assertions unchanged; they verify the persisted internal customer relation through the public approval behavior.

- [ ] **Step 4: Implement the License API conversion and error boundary**

In `create_application`:

```python
customer = check_customer_edit_permission(application.customer_id, team_id, current_user, db)
internal_application = LicenseApplicationInternalCreate(
    customer_id=customer.id,
    deployment_info_id=application.deployment_info_id,
    contract_id=application.contract_id,
    license_type=application.license_type,
    authorized_users=application.authorized_users,
    expiry_date=application.expiry_date,
    remark=application.remark,
)
try:
    created = create_license_application(db, team_id, internal_application, current_user.id)
except ValueError as exc:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=str(exc),
    ) from exc
```

Keep intelligence enqueue and response mapping after the successful create only.

- [ ] **Step 5: Implement the License CRUD integer boundary**

Change imports and annotations to `LicenseApplicationInternalCreate`. Replace the customer lookup with:

```python
customer = db.query(Customer).filter(
    Customer.id == obj_in.customer_id,
    Customer.team_id == team_id,
).first()
```

Keep deployment and contract association checks exactly team-scoped and compare their integer `customer_id` values to `customer.id`. Keep the database object write and commit behavior unchanged.

- [ ] **Step 6: Run focused License tests and verify GREEN**

Run:

```bash
cd CRM-Server
pytest tests/unit/test_customer_business_object_intelligence_api.py -q -k "license_application"
pytest tests/unit/test_license_approval.py -q
```

Expected: all selected API and approval tests pass, including the new 400 regression.

- [ ] **Step 7: Commit**

```bash
git add CRM-Server/app/api/license_application.py CRM-Server/app/crud/crud_license_application.py CRM-Server/tests/unit/test_customer_business_object_intelligence_api.py CRM-Server/tests/unit/test_license_approval.py
git commit -m "fix(server): separate License customer ID boundaries"
```

---

### Task 3: Migrate deployment creation to the internal boundary

**Files:**
- Modify: `CRM-Server/tests/unit/test_customer_business_object_intelligence_api.py`
- Modify: `CRM-Server/app/api/deployment.py:73-90`
- Modify: `CRM-Server/app/crud/crud_deployment.py:1-46,238-239`

**Interfaces:**
- `create_deployment_info(db, team_id, obj_in: DeploymentInfoInternalCreate)`.
- `DeploymentInfoCRUD.create(db, team_id, obj_in: DeploymentInfoInternalCreate)`.
- API continues to accept `DeploymentInfoCreate` and returns `DeploymentInfoResponse`.

- [ ] **Step 1: Add failing deployment boundary and error tests**

Capture the object passed to `create_deployment_info` and assert it is an internal schema with `customer_id == 101` when the request contains `customer_id="cus_101"`. Add a separate test where the fake CRUD raises `ValueError("部署信息创建失败")`; assert HTTP 400 and no intelligence enqueue.

Use the existing `_deployment_info()` fixture and this request shape:

```python
_RequestData(
    customer_id="cus_101",
    deployment_name="生产环境",
    server_address="https://crm.example.com",
    authorized_users=200,
    is_default=True,
)
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
cd CRM-Server
pytest tests/unit/test_customer_business_object_intelligence_api.py -q -k "deployment_info_converts_public_customer_id or deployment_value_error"
```

Expected: failure because the route currently passes the external stand-in and lets `ValueError` escape.

- [ ] **Step 3: Implement explicit deployment conversion and HTTP 400 mapping**

In `create_deployment`, resolve permissions from the external `deployment.customer_id`, construct `DeploymentInfoInternalCreate` with `customer.id`, and wrap only the CRUD call in `except ValueError`. Keep enqueue and response after successful creation.

- [ ] **Step 4: Change deployment CRUD to the internal schema**

Change imports, annotations, and wrapper signature to `DeploymentInfoInternalCreate`. The existing default-clearing query must use the integer `deployment_data['customer_id']`; do not add public-ID lookup logic. Preserve `team_id` in the update query and existing commit behavior.

- [ ] **Step 5: Run focused deployment tests and verify GREEN**

Run:

```bash
cd CRM-Server
pytest tests/unit/test_customer_business_object_intelligence_api.py -q -k "deployment_info"
```

Expected: selected deployment intelligence, public-ID conversion, and 400 error tests pass.

- [ ] **Step 6: Commit**

```bash
git add CRM-Server/app/api/deployment.py CRM-Server/app/crud/crud_deployment.py CRM-Server/tests/unit/test_customer_business_object_intelligence_api.py
git commit -m "fix(server): separate deployment customer ID boundaries"
```

---

### Task 4: Migrate manual and opportunity-based contract creation

**Files:**
- Modify: `CRM-Server/tests/unit/test_customer_business_object_intelligence_api.py`
- Modify: `CRM-Server/tests/unit/test_contract_source_transaction.py`
- Modify: `CRM-Server/app/api/contracts.py:47-55,349-438,496-587`
- Modify: `CRM-Server/app/crud/contract.py:442-628`

**Interfaces:**
- `contract_crud.create(db, obj_in: ContractInternalCreate, creator_id: str, team_id: int)`.
- `contract_crud.create_from_opportunity(db, opportunity_id: int, customer_id: int, signing_contact_id: int, contract_name: str, creator_id: str, team_id: int)` remains integer-only.
- Manual and opportunity-based HTTP routes continue receiving public customer/opportunity IDs and returning public IDs.

- [ ] **Step 1: Add failing manual contract boundary test**

Add a test that uses a real `ContractCreate` payload with `customer_id="cus_101"` and `opportunity_id="opp_301"`, monkeypatches the public-ID resolvers, captures `contract_crud.create`, and asserts:

```python
assert isinstance(captured[0], ContractInternalCreate)
assert captured[0].customer_id == 101
assert captured[0].opportunity_id == 301
```

The test must also preserve the existing successful file-storage/approval path so it proves the route still completes and returns the contract response.

Add an error test where `contract_crud.create` raises `ValueError("该商机已创建合同")`; assert HTTP 400 and no successful post-create side effect is recorded.

- [ ] **Step 2: Add failing from-opportunity integer argument test**

In `test_contract_source_transaction.py` or a focused contract API test, capture `create_from_opportunity` kwargs when the route is called with `opportunity_id="opp_301"`. Assert `opportunity_id == 301`, `customer_id == 101`, and `team_id == 2`. Keep the existing file-storage behavior assertions.

- [ ] **Step 3: Run the focused contract tests and verify RED**

Run:

```bash
cd CRM-Server
pytest tests/unit/test_customer_business_object_intelligence_api.py -q -k "create_contract"
pytest tests/unit/test_contract_source_transaction.py -q
```

Expected: the new type/argument assertions fail because manual creation currently passes the mutated external object and the route tests use public-ID-shaped stand-ins.

- [ ] **Step 4: Add `ContractInternalCreate` to API imports and construct it explicitly**

In manual `create_contract`:

1. Keep `check_customer_edit_permission(contract.customer_id, team_id, current_user, db)` on the external public ID.
2. Resolve `contract.opportunity_id` with `_get_opportunity_by_public_id_or_404`.
3. Compare contact and opportunity customer relations using `customer.id`.
4. Construct `ContractInternalCreate` with the resolved integer IDs and all validated business fields.
5. Pass it to `contract_crud.create`.

Do not call `model_copy(update=...)` on `ContractCreate`.

- [ ] **Step 5: Keep the opportunity route integer-only and strengthen CRUD team filters**

In `create_contract_from_opportunity`, preserve public-ID route resolution and pass `opportunity.id` and `opportunity.customer_id` as integers to `create_from_opportunity`.

In `ContractCRUD.create_from_opportunity`, change the queries to include:

```python
Opportunity.id == opportunity_id,
Opportunity.team_id == team_id,

Customer.id == customer_id,
Customer.team_id == team_id,
```

Do not alter the existing contract-number, owner, deal-journey, commit, file, approval, or post-commit behavior.

- [ ] **Step 6: Keep error mapping scoped to expected business errors**

Retain the existing `except ValueError` blocks in both contract creation routes. Ensure the manual route catches errors from the internal CRUD call and the opportunity route continues to return 400 for CRUD business validation. Do not catch `SQLAlchemyError`, `FileStorageError`, or unknown exceptions in the ValueError block.

- [ ] **Step 7: Run focused contract tests and verify GREEN**

Run:

```bash
cd CRM-Server
pytest tests/unit/test_customer_business_object_intelligence_api.py -q -k "contract"
pytest tests/unit/test_contract_source_transaction.py -q
```

Expected: manual and opportunity-based creation tests pass, including public-ID response mapping, integer internal arguments, file-storage rollback, and 400 business errors.

- [ ] **Step 8: Commit**

```bash
git add CRM-Server/app/api/contracts.py CRM-Server/app/crud/contract.py CRM-Server/tests/unit/test_customer_business_object_intelligence_api.py CRM-Server/tests/unit/test_contract_source_transaction.py
 git commit -m "fix(server): separate contract customer and opportunity IDs"
```

---

### Task 5: Migrate remaining callers and remove stale public-ID CRUD assumptions

**Files:**
- Modify: `CRM-Server/app/schemas/__init__.py` if exports were incomplete.
- Modify: any direct callers found by `lsp` references for `create_license_application`, `create_deployment_info`, and `contract_crud.create`.
- Modify: `CRM-Server/tests/unit/test_license_approval.py` if any public-ID direct CRUD calls remain.

**Interfaces:**
- All direct License/Deployment/Contract CRUD callers use internal integer IDs and the exact internal schema signatures from Tasks 1–4.
- Agent tool paths remain unchanged because they call HTTP APIs and continue sending public IDs.

- [ ] **Step 1: Resolve symbol references before editing**

Use the language server reference operation for the exported create functions and `contract_crud.create`. Confirm every caller is either an API boundary that now performs conversion or an internal caller that already has integer IDs. Do not use a broad text replacement for symbol migration.

- [ ] **Step 2: Add a focused failure for each stale caller**

For every direct caller still constructing an external create schema with a public customer/opportunity ID, add or update the narrowest behavior test so the caller must pass the internal schema/int IDs. Do not add tests for callers that only invoke the HTTP API.

- [ ] **Step 3: Migrate the callers**

Update only stale direct callers to use `LicenseApplicationInternalCreate`, `DeploymentInfoInternalCreate`, or `ContractInternalCreate` and integer IDs. Remove no-longer-valid imports of external create schemas from CRUD-only tests or internal modules.

- [ ] **Step 4: Search for stale boundary mutations**

Run:

```bash
python - <<'PY'
from pathlib import Path
roots = [Path("CRM-Server/app/api"), Path("CRM-Server/app/crud")]
for root in roots:
    for path in root.rglob("*.py"):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if "model_copy(update={\"customer_id\": customer.id})" in line or "model_copy(update={'customer_id': customer.id})" in line:
                print(f"{path}:{number}:{line}")
PY
```

Expected: no output in the three target creation paths. This is a fact-finding command, not a replacement operation.

- [ ] **Step 5: Run focused caller tests and verify GREEN**

Run:

```bash
cd CRM-Server
pytest tests/unit/test_license_approval.py -q
pytest tests/unit/test_customer_business_object_intelligence_api.py -q -k "license_application or deployment_info or contract"
```

- [ ] **Step 6: Commit**

```bash
git add CRM-Server/app CRM-Server/tests/unit
git commit -m "refactor(server): migrate internal ID create callers"
```

Do not stage or commit Assistant files, unrelated frontend changes, or unrelated design documents.

---

### Task 6: Integrated verification and final review

**Files:**
- No planned source changes. Only modify code if a focused verification exposes a defect covered by the plan.

**Interfaces:**
- All three creation families expose unchanged public API contracts and use internal integer CRUD contracts.

- [ ] **Step 1: Run the complete focused regression set**

Run:

```bash
cd CRM-Server
pytest tests/unit/test_customer_id_boundary_schemas.py -q
pytest tests/unit/test_customer_business_object_intelligence_api.py -q -k "license_application or deployment_info or contract"
pytest tests/unit/test_license_approval.py -q
pytest tests/unit/test_contract_source_transaction.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run backend static checks required by the repository**

Run:

```bash
cd CRM-Server
ruff check app/
mypy app/
```

Expected: both commands exit 0. Do not reformat unrelated files.

- [ ] **Step 3: Run the required unit suite**

Run:

```bash
cd CRM-Server
pytest tests/unit -v
```

Expected: the unit suite passes. If an existing unrelated Assistant test fails because of pre-existing dirty changes, record the exact failure and do not modify Assistant files as part of this work.

- [ ] **Step 4: Inspect the final diff boundary**

Run:

```bash
git diff --name-only main...HEAD
```

Expected: only the customer-ID design/plan docs and the listed CRM-Server schema/API/CRUD/test files are present in the implementation commits; pre-existing dirty Assistant files are not staged or committed.

- [ ] **Step 5: Verify the original failure path without a production write**

Use a focused test or local request fixture to prove a valid public customer ID resolves to an internal integer before License CRUD and that an invalid association returns HTTP 400. Do not repeat the production POST. Production deployment verification is limited to observing the deployed build and, if a controlled read-only smoke route exists, exercising that route without creating another License application.

- [ ] **Step 6: Commit only if final fixes were required**

```bash
git add CRM-Server/app CRM-Server/tests/unit
git commit -m "test(server): verify customer ID boundary migration"
```

Skip this commit when no final source fix was needed.

---

## Plan self-review

- Spec coverage: public API compatibility, three internal schemas, License/deployment/contract conversion, integer-only CRUD, team filters, 400 error mapping, transaction preservation, intelligence side-effect ordering, regression coverage, no migration, no Assistant changes, and controlled production verification are covered by Tasks 1–6.
- Placeholder scan: no `TBD`, `TODO`, `FIXME`, “implement later”, or unspecified validation steps are used as task requirements.
- Type consistency: the exact internal class names and CRUD signatures are established in Task 1 and reused in Tasks 2–5.
- Dependency order: Task 1 precedes all consumers; License and deployment can be reviewed independently after Task 1; contract changes are isolated; Task 5 verifies remaining references; Task 6 is final-only.
