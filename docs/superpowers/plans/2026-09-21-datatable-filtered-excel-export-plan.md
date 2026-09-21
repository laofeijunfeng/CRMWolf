# DataTable Filtered Excel Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add permission-gated `.xlsx` export for the nine core paginated DataTables, exporting every row in the current list context and a user-selected set of registered fields.

**Architecture:** The frontend extends the existing `ListFieldDefinition` registry and DataTable toolbar with a responsive export dialog. Each page reuses one typed current-query builder for both list loading and export. The backend exposes nine typed resource endpoints, reuses each resource's permission/scoping/query pipeline without pagination, projects rows through a controlled export catalog, and writes a temporary workbook through one shared `openpyxl` service.

**Tech Stack:** Vue 3, TypeScript, Vitest, Pinia, Axios, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, `openpyxl==3.1.5`, pytest, Ruff, MyPy.

## Global Constraints

- Export all rows matching the current page tab, search, filters, sorts, team, and user-visible scope; never export only the current page.
- Cover Customers, CustomerTracking, Leads, Opportunities, Contracts, PaymentPlans, PaymentRecords, Invoices, and ApprovalCenter.
- Default field selection is the current visible DataTable columns in current preference order. Hidden registered columns are optional and unchecked. `public_id` is an optional unchecked “业务 ID” where supported.
- Never expose database `id` or internal foreign keys as export candidates or workbook values. Missing legacy business numbers stay blank.
- Use resource-specific typed POST endpoints and independent permissions. `TEAM_ADMIN` alone receives the nine new permissions by default.
- Generate valid `.xlsx` synchronously. Do not silently truncate, paginate, create async jobs, or impose a product-level row cap.
- Stream ORM rows with SQLAlchemy `stream_results` + `yield_per`; no `.all()` over the full export and no row-by-row N+1 queries.
- Use the request Session only for the server-side streaming cursor. Use a separate short-lived projection Session for per-batch display-data queries, and call `query.enable_eagerloads(False)` before `yield_per`, avoiding collection eager-load conflicts and PyMySQL commands-out-of-sync failures.
- Text beginning, after leading whitespace, with `=`, `+`, `-`, or `@` must be written as safe text, not an Excel formula.
- Only export requests override Axios's 30-second timeout with `timeout: 0`.
- Preserve current uncommitted work in `CRM-Server/app/api/opportunities.py`; re-read and integrate it. Never reset or overwrite unrelated changes.
- Spec: `docs/superpowers/specs/2026-09-21-datatable-filtered-excel-export-design.md`.

## File Structure

### Backend shared infrastructure

- Create `CRM-Server/app/core/list_export/__init__.py` — public export-catalog API.
- Create `CRM-Server/app/core/list_export/catalog.py` — field/catalog validation and selected-column resolution.
- Create `CRM-Server/app/core/list_export/errors.py` — domain validation error with a user-facing detail string.
- Create `CRM-Server/app/core/list_export/http.py` — converts export catalog errors to HTTP 400.
- Create `CRM-Server/app/core/list_export/catalogs/` with one catalog module per covered resource.
- Create `CRM-Server/app/core/list_export/manifest.py` — generated frontend contract projection.
- Create `CRM-Server/app/schemas/list_export.py` — base and resource-specific request schemas.
- Create `CRM-Server/app/services/list_export_service.py` — safe cell conversion, streaming workbook writer, temporary-file response and cleanup.
- Create `CRM-Server/scripts/generate_list_export_manifest.py` — generates the committed frontend manifest.
- Resource export iterators receive a `projection_session_factory` (production: `SessionLocal`) and close one projection Session per 500-row batch.
- Modify `CRM-Server/app/core/list_query/engine.py` — expose a no-pagination filtered/ordered query builder reused by list CRUD and export.

### Backend resource integration

- Modify each resource CRUD/service to expose its current filtered ordered query before pagination.
- Modify each resource API module to share scope resolution and row serialization between list and export.
- Create focused export tests per resource pair instead of one large cross-resource test file.

### Frontend shared infrastructure

- Create `CRM-Client/src/components/crmwolf/DataTableExportDialog.vue`.
- Create generated `CRM-Client/src/components/crmwolf/listExportCatalogManifest.json`.
- Create `CRM-Client/src/api/listExport.ts` — typed Blob POST helper.
- Create `CRM-Client/src/utils/downloadBlob.ts` — object URL lifecycle and deterministic file naming.
- Create `CRM-Client/src/composables/useDataTableExport.ts` — exporting state and feedback.
- Modify `listFieldCatalog.ts`, `ListAdvancedTools.vue`, `DataTable.vue`, and `components/crmwolf/index.ts`.
- Modify the nine page/API pairs to add permission checks, a single current-query builder, export request methods, and DataTable wiring.

---

### Task 1: Add the Excel dependency and shared export engine

**Files:**
- Modify: `CRM-Server/requirements.txt`
- Modify: `CRM-Server/requirements.lock` (generated)
- Modify: `CRM-Server/requirements-dev.txt`
- Modify: `CRM-Server/requirements-dev.lock` (generated)
- Modify: `CRM-Server/pyproject.toml`
- Create: `CRM-Server/app/core/list_export/__init__.py`
- Create: `CRM-Server/app/core/list_export/errors.py`
- Create: `CRM-Server/app/core/list_export/catalog.py`
- Create: `CRM-Server/app/core/list_export/http.py`
- Create: `CRM-Server/app/schemas/list_export.py`
- Create: `CRM-Server/app/services/list_export_service.py`
- Test: `CRM-Server/tests/unit/test_list_export_service.py`

**Interfaces:**
- Produces `ListExportError`, `is_unsafe_export_key()`, `run_list_export_or_400()`, `ListExportField`, `ListExportCatalog`, `BaseListExportRequest`, nine resource request models, `iter_batches()`, `create_list_export_file()`, and `list_export_file_response()`.
- Every resource endpoint in Tasks 6–10 consumes these interfaces.

- [ ] **Step 1: Write the failing shared-engine tests**

Create `CRM-Server/tests/unit/test_list_export_service.py`:

```python
from datetime import date, datetime
from pathlib import Path

from fastapi import HTTPException
from openpyxl import load_workbook
import pytest

from app.core.list_export import ListExportCatalog, ListExportField, run_list_export_or_400
from app.services.list_export_service import create_list_export_file, iter_batches, safe_excel_text


def test_catalog_rejects_unsafe_and_unknown_fields() -> None:
    with pytest.raises(ValueError, match="不安全导出字段"):
        ListExportCatalog("bad", "Bad", (ListExportField("id", "ID", "text"),))

    catalog = ListExportCatalog(
        "customers",
        "客户",
        (ListExportField("account_name", "客户名称", "text"),),
    )
    with pytest.raises(ValueError, match="未知导出字段"):
        catalog.select(["missing"])


def test_http_helper_converts_catalog_error_to_400() -> None:
    catalog = ListExportCatalog(
        "customers",
        "客户",
        (ListExportField("account_name", "客户名称", "text"),),
    )
    with pytest.raises(HTTPException) as error:
        run_list_export_or_400(lambda: catalog.select(["missing"]))
    assert error.value.status_code == 400
    assert error.value.detail == "未知导出字段: missing"


def test_safe_excel_text_checks_prefix_after_leading_whitespace() -> None:
    assert safe_excel_text("=1+1") == "'=1+1"
    assert safe_excel_text("  @SUM(A1:A2)") == "'  @SUM(A1:A2)"
    assert safe_excel_text("Acme") == "Acme"


def test_iter_batches_never_loads_the_full_iterator() -> None:
    assert list(iter_batches(iter(range(5)), batch_size=2)) == [[0, 1], [2, 3], [4]]
    with pytest.raises(ValueError, match="batch_size must be positive"):
        list(iter_batches(iter(()), batch_size=0))


def test_writer_creates_typed_workbook_and_zero_row_workbook(tmp_path: Path) -> None:
    catalog = ListExportCatalog(
        "customers",
        "客户列表",
        (
            ListExportField("public_id", "业务 ID", "text"),
            ListExportField("amount", "金额", "currency"),
            ListExportField("signed_on", "签署日期", "date"),
            ListExportField("created_at", "创建时间", "datetime"),
        ),
    )
    generated = create_list_export_file(
        catalog=catalog,
        selected_keys=["public_id", "amount", "signed_on", "created_at"],
        rows=iter(({
            "public_id": "CUS-0001",
            "amount": 1200.5,
            "signed_on": date(2026, 9, 21),
            "created_at": datetime(2026, 9, 21, 14, 30),
        },)),
        file_stem="客户列表-所有客户",
        directory=tmp_path,
    )
    workbook = load_workbook(generated.path, read_only=True, data_only=False)
    assert list(workbook.active.values) == [
        ("业务 ID", "金额", "签署日期", "创建时间"),
        ("CUS-0001", 1200.5, date(2026, 9, 21), datetime(2026, 9, 21, 14, 30)),
    ]
    assert generated.row_count == 1

    empty = create_list_export_file(
        catalog=catalog,
        selected_keys=["public_id"],
        rows=iter(()),
        file_stem="空列表",
        directory=tmp_path,
    )
    assert list(load_workbook(empty.path, read_only=True).active.values) == [("业务 ID",)]
```

- [ ] **Step 2: Run the tests and confirm RED**

```bash
cd CRM-Server
.venv/bin/python -m pytest tests/unit/test_list_export_service.py -q --no-cov
```

Expected: collection fails because `openpyxl` and `app.core.list_export` do not exist.

- [ ] **Step 3: Pin dependencies and regenerate both lock files**

Add `openpyxl==3.1.5` to `requirements.txt` and `project.dependencies`. Add `types-openpyxl==3.1.5.20260827` to `requirements-dev.txt` and `project.optional-dependencies.dev`.

```bash
cd CRM-Server
uv pip compile requirements.txt --universal --generate-hashes --python-version 3.11 --output-file requirements.lock
uv pip compile requirements-dev.txt --constraint requirements.lock --universal --generate-hashes --python-version 3.11 --output-file requirements-dev.lock
uv pip install --python .venv/bin/python --require-hashes -r requirements.lock -r requirements-dev.lock
```

Expected: production lock contains `openpyxl==3.1.5` and `et-xmlfile`; development lock contains `types-openpyxl==3.1.5.20260827`.

- [ ] **Step 4: Implement export errors, catalog validation, and HTTP conversion**

`errors.py`:

```python
class ListExportError(ValueError):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)
```

`catalog.py`:

```python
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from app.core.list_export.errors import ListExportError

ListExportCellType = Literal["text", "number", "date", "datetime", "currency"]
ExportRow = Mapping[str, object]


def is_unsafe_export_key(key: str) -> bool:
    return key == "id" or (
        key.endswith("_id")
        and key != "public_id"
        and not key.endswith("_public_id")
    )


@dataclass(frozen=True)
class ListExportField:
    key: str
    label: str
    cell_type: ListExportCellType
    value_getter: Callable[[ExportRow], object] | None = None

    def value_from(self, row: ExportRow) -> object:
        return self.value_getter(row) if self.value_getter is not None else row.get(self.key)


@dataclass(frozen=True)
class ListExportCatalog:
    resource: str
    sheet_name: str
    fields: Sequence[ListExportField]
    _index: Mapping[str, ListExportField] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        index: dict[str, ListExportField] = {}
        for export_field in self.fields:
            key = export_field.key
            if is_unsafe_export_key(key):
                raise ListExportError(f"不安全导出字段: {key}")
            if key in index:
                raise ListExportError(f"重复导出字段: {key}")
            index[key] = export_field
        object.__setattr__(self, "_index", index)

    def select(self, keys: Sequence[str]) -> tuple[ListExportField, ...]:
        if not keys:
            raise ListExportError("至少选择一个导出字段")
        if len(set(keys)) != len(keys):
            raise ListExportError("导出字段不能重复")
        selected: list[ListExportField] = []
        for key in keys:
            export_field = self._index.get(key)
            if export_field is None:
                raise ListExportError(f"未知导出字段: {key}")
            selected.append(export_field)
        return tuple(selected)
```

`http.py`:

```python
from collections.abc import Callable
from typing import TypeVar

from fastapi import HTTPException

from app.core.list_export.errors import ListExportError

T = TypeVar("T")


def run_list_export_or_400(func: Callable[[], T]) -> T:
    try:
        return func()
    except ListExportError as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc
```

- [ ] **Step 5: Implement strict typed request models**

Create `app/schemas/list_export.py` with `ConfigDict(extra="forbid")`, `fields: list[str] = Field(min_length=1, max_length=64)`, optional `search`, `filters`, and `sorts`. The field validator must call `is_unsafe_export_key` and reject duplicates. Add these exact tab models:

```python
class CustomerListExportRequest(BaseListExportRequest):
    tab: Literal["all", "collaborated", "public"] = "all"

class LeadListExportRequest(BaseListExportRequest):
    tab: Literal["all", "public"] = "all"

class OpportunityListExportRequest(BaseListExportRequest):
    tab: Literal["all", "active", "won", "lost"] = "all"

class ContractListExportRequest(BaseListExportRequest):
    tab: Literal["all", "DRAFT", "PENDING_REVIEW", "SIGNED"] = "all"

class PaymentPlanListExportRequest(BaseListExportRequest):
    tab: Literal["all", "pending", "partial", "completed"] = "all"

class PaymentRecordListExportRequest(BaseListExportRequest):
    tab: Literal["all", "pending_submit", "pending_approval", "rejected", "confirmed"] = "all"

class InvoiceListExportRequest(BaseListExportRequest):
    tab: Literal["all", "pending", "approved", "invoiced"] = "all"

class FollowUpTaskListExportRequest(BaseListExportRequest):
    tab: Literal["all", "open", "completed", "cancelled"] = "open"

class ApprovalListExportRequest(BaseListExportRequest):
    tab: Literal["pending", "processed", "submitted"] = "pending"
```

Re-export all public names from `app/core/list_export/__init__.py`.

- [ ] **Step 6: Implement the workbook writer and batching helper**

In `list_export_service.py`, implement:

```python
def iter_batches(rows: Iterable[T], batch_size: int = 500) -> Iterator[list[T]]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    iterator = iter(rows)
    while batch := list(islice(iterator, batch_size)):
        yield batch
```

Implement `safe_excel_text`, filename/sheet sanitization, typed `WriteOnlyCell` creation, and `create_list_export_file()` exactly as specified by the Step 1 tests. Use `Workbook(write_only=True)`, bold headers, freeze `A2`, auto-filter over the populated range, `#,##0.00` currency, `0.00` number, `yyyy-mm-dd`, `yyyy-mm-dd hh:mm:ss`, a `NamedTemporaryFile(delete=False)`, and unlink the partial file on save failure.

`list_export_file_response()` must return a `FileResponse` with the XLSX media type, UTF-8 `Content-Disposition`, and `BackgroundTask(generated.path.unlink, missing_ok=True)`.

- [ ] **Step 7: Verify GREEN and static checks**

```bash
cd CRM-Server
.venv/bin/python -m pytest tests/unit/test_list_export_service.py -q --no-cov
.venv/bin/ruff check app/core/list_export app/schemas/list_export.py app/services/list_export_service.py tests/unit/test_list_export_service.py
.venv/bin/mypy app/core/list_export app/schemas/list_export.py app/services/list_export_service.py
```

- [ ] **Step 8: Commit Task 1**

```bash
git add CRM-Server/requirements.txt CRM-Server/requirements.lock CRM-Server/requirements-dev.txt CRM-Server/requirements-dev.lock CRM-Server/pyproject.toml CRM-Server/app/core/list_export CRM-Server/app/schemas/list_export.py CRM-Server/app/services/list_export_service.py CRM-Server/tests/unit/test_list_export_service.py
git commit -m "feat(export): add shared Excel export engine"
```

---

### Task 2: Define all nine export catalogs and generated contract manifest

**Files:**
- Create: `CRM-Server/app/core/list_export/catalogs/__init__.py`
- Create: `CRM-Server/app/core/list_export/catalogs/customers.py`
- Create: `CRM-Server/app/core/list_export/catalogs/follow_up_tasks.py`
- Create: `CRM-Server/app/core/list_export/catalogs/leads.py`
- Create: `CRM-Server/app/core/list_export/catalogs/opportunities.py`
- Create: `CRM-Server/app/core/list_export/catalogs/contracts.py`
- Create: `CRM-Server/app/core/list_export/catalogs/payment_plans.py`
- Create: `CRM-Server/app/core/list_export/catalogs/payment_records.py`
- Create: `CRM-Server/app/core/list_export/catalogs/invoices.py`
- Create: `CRM-Server/app/core/list_export/catalogs/approvals.py`
- Create: `CRM-Server/app/core/list_export/manifest.py`
- Create: `CRM-Server/scripts/generate_list_export_manifest.py`
- Create generated: `CRM-Client/src/components/crmwolf/listExportCatalogManifest.json`
- Test: `CRM-Server/tests/unit/list_export/test_catalog_manifest.py`

**Interfaces:**
- Produces: `LIST_EXPORT_CATALOGS: dict[str, ListExportCatalog]` keyed by the same names used in the list-query manifest.
- Consumers: frontend contract tests and all export endpoints.

**Exact catalog fields:**

| Resource | `key: label (type)` |
| --- | --- |
| `customers` | `public_id: 业务 ID (text)`, `account_name: 客户名称 (text)`, `owner: 负责人 (text)`, `collaborators: 协作者 (text)`, `city: 城市 (text)`, `company_scale: 规模 (text)`, `status: 状态 (text)`, `license_status: 授权状态 (text)`, `license_expiry_date: 授权到期 (date)`, `default_procurement_method: 默认采购方式 (text)`, `industry: 行业 (text)`, `source: 来源 (text)`, `product_name: 产品 (text)`, `creator: 创建人 (text)`, `created_time: 创建时间 (datetime)` |
| `follow_up_tasks` | `public_id: 业务 ID (text)`, `customer_name: 客户 (text)`, `tracking_content: 追踪内容 (text)`, `status_label: 状态 (text)`, `tracking_time: 跟进时效 (datetime)` |
| `leads` | `public_id: 业务 ID (text)`, `lead_name: 线索名称 (text)`, `owner: 负责人 (text)`, `contact_name: 联系人 (text)`, `contact_phone: 联系电话 (text)`, `source: 来源 (text)`, `product_name: 产品 (text)`, `city: 城市 (text)`, `company_scale: 规模 (text)`, `status: 状态 (text)`, `created_time: 创建时间 (datetime)` |
| `opportunities` | `public_id: 业务 ID (text)`, `opportunity_name: 商机名称 (text)`, `owner: 负责人 (text)`, `customer_name: 客户名称 (text)`, `product_name: 产品 (text)`, `total_amount: 预计金额 (currency)`, `user_count: 用户数 (number)`, `license_type: 授权模式 (text)`, `purchase_type: 采购类型 (text)`, `expected_closing_date: 预计成交日期 (date)`, `stage: 销售阶段 (text)`, `win_probability: 赢率 (number)`, `status: 状态 (text)`, `approval_phase: 审批 (text)`, `created_time: 创建时间 (datetime)` |
| `contracts` | `contract_number: 合同编号 (text)`, `contract_name: 合同名称 (text)`, `customer_name: 客户名称 (text)`, `opportunity_name: 商机名称 (text)`, `total_amount: 合同金额 (currency)`, `license_type: 授权模式 (text)`, `purchase_type: 采购类型 (text)`, `subscription_years: 采购年限 (number)`, `license_authorized_users: 授权数量 (number)`, `standard_unit_price: 客单价 (currency)`, `license_expiry_date: 授权时间 (date)`, `signing_date: 签署日期 (date)`, `created_time: 创建时间 (datetime)`, `owner: 负责人 (text)` |
| `payment_plans` | `plan_number: 计划编号 (text)`, `stage_name: 阶段名称 (text)`, `customer_name: 客户名称 (text)`, `contract_name: 合同名称 (text)`, `plan_amount: 计划金额 (currency)`, `due_date: 计划日期 (date)`, `status: 状态 (text)` |
| `payment_records` | `record_number: 回款编号 (text)`, `customer_name: 客户名称 (text)`, `actual_payer_name: 实际付款方 (text)`, `invoice_title_text: 发票抬头 (text)`, `contract_name: 合同名称 (text)`, `actual_amount: 回款金额 (currency)`, `owner_name: 负责人 (text)`, `commission_member_name: 团队成员 (text)`, `payment_date: 回款日期 (date)`, `confirmation_status: 状态 (text)`, `created_time: 创建时间 (datetime)` |
| `invoices` | `application_number: 申请单号 (text)`, `customer_name: 客户名称 (text)`, `contract_name: 合同名称 (text)`, `invoice_type: 发票类型 (text)`, `invoice_amount: 开票金额 (currency)`, `invoice_title_text: 开票抬头 (text)`, `status: 状态 (text)`, `invoice_effective_status: 发票状态 (text)`, `applicant_name: 申请人 (text)`, `created_time: 创建时间 (datetime)` |
| `approvals` | `application_number: 单号 (text)`, `business_type: 类型 (text)`, `entity_name: 实体 (text)`, `entity_amount: 金额 (currency)`, `submitter_name: 提交人 (text)`, `created_time: 提交时间 (datetime)`, `status: 状态 (text)`, `overdue_hours: 超时 (number)` |

- [ ] **Step 1: Write failing catalog/manifest tests**

Create tests asserting exact labels/types, all nine resources, and the absence of `id`:

```python
import json
from pathlib import Path

from app.core.list_export.catalogs import LIST_EXPORT_CATALOGS
from app.core.list_export.manifest import build_list_export_manifest, write_list_export_manifest

CLIENT_MANIFEST = Path(__file__).resolve().parents[4] / "CRM-Client/src/components/crmwolf/listExportCatalogManifest.json"


def test_all_core_datatables_have_export_catalogs_without_internal_id() -> None:
    assert set(LIST_EXPORT_CATALOGS) == {
        "approvals", "contracts", "customers", "follow_up_tasks", "invoices",
        "leads", "opportunities", "payment_plans", "payment_records",
    }
    for catalog in LIST_EXPORT_CATALOGS.values():
        assert "id" not in {field.key for field in catalog.fields}


def test_manifest_contains_user_facing_contract() -> None:
    manifest = build_list_export_manifest(LIST_EXPORT_CATALOGS)
    assert manifest["customers"]["public_id"] == {"label": "业务 ID", "type": "text"}
    assert manifest["payment_records"]["actual_amount"] == {"label": "回款金额", "type": "currency"}


def test_committed_export_manifest_matches_backend(tmp_path: Path) -> None:
    generated = tmp_path / "listExportCatalogManifest.json"
    write_list_export_manifest(generated, LIST_EXPORT_CATALOGS)
    assert json.loads(CLIENT_MANIFEST.read_text(encoding="utf-8")) == json.loads(generated.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run RED**

```bash
cd CRM-Server
.venv/bin/python -m pytest tests/unit/list_export/test_catalog_manifest.py -q --no-cov
```

Expected: import/manifest failures.

- [ ] **Step 3: Implement resource catalogs and registry**

Each module exports one constant. The customer module is exactly:

```python
CUSTOMERS_LIST_EXPORT_CATALOG = ListExportCatalog(
    resource="customers",
    sheet_name="客户列表",
    fields=(
        ListExportField("public_id", "业务 ID", "text"),
        ListExportField("account_name", "客户名称", "text"),
        ListExportField("owner", "负责人", "text"),
        ListExportField("collaborators", "协作者", "text"),
        ListExportField("city", "城市", "text"),
        ListExportField("company_scale", "规模", "text"),
        ListExportField("status", "状态", "text"),
        ListExportField("license_status", "授权状态", "text"),
        ListExportField("license_expiry_date", "授权到期", "date"),
        ListExportField("default_procurement_method", "默认采购方式", "text"),
        ListExportField("industry", "行业", "text"),
        ListExportField("source", "来源", "text"),
        ListExportField("product_name", "产品", "text"),
        ListExportField("creator", "创建人", "text"),
        ListExportField("created_time", "创建时间", "datetime"),
    ),
)
```

Implement the other eight modules with every field from the exact matrix in this task; do not infer labels from ORM attributes.
- [ ] **Step 4: Implement and generate the manifest**

`manifest.py` must emit:

```python
ListExportManifest = dict[str, dict[str, dict[str, str]]]


def build_list_export_manifest(catalogs):
    return {
        resource: {
            field.key: {"label": field.label, "type": field.cell_type}
            for field in catalog.fields
        }
        for resource, catalog in sorted(catalogs.items())
    }
```

Run:

```bash
cd CRM-Server
.venv/bin/python scripts/generate_list_export_manifest.py
.venv/bin/python -m pytest tests/unit/list_export/test_catalog_manifest.py -q --no-cov
```

Expected: generated client JSON and all tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add CRM-Server/app/core/list_export/catalogs CRM-Server/app/core/list_export/manifest.py CRM-Server/scripts/generate_list_export_manifest.py CRM-Server/tests/unit/list_export/test_catalog_manifest.py CRM-Client/src/components/crmwolf/listExportCatalogManifest.json
git commit -m "feat(export): define list export catalogs"
```

---

### Task 3: Add independent export permissions and merge the migration heads

**Files:**
- Modify: `CRM-Server/app/constants/permissions.py`
- Create: `CRM-Server/migrations/versions/137_datatable_export_permissions.py`
- Create: `CRM-Server/tests/unit/test_datatable_export_permissions_migration.py`
- Modify: `CRM-Server/tests/unit/test_permission_catalog.py`

**Interfaces:**
- Produces permissions: `customer:export`, `follow_up_task:export`, `lead:export`, `opportunity:export`, `contract:export`, `payment:plan:export`, `payment:record:export`, `invoice:export`, `approval:export`.
- Default grant: `TEAM_ADMIN` only.

- [ ] **Step 1: Write failing permission tests**

Add assertions:

```python
EXPORT_PERMISSION_CODES = {
    "customer:export", "follow_up_task:export", "lead:export", "opportunity:export",
    "contract:export", "payment:plan:export", "payment:record:export",
    "invoice:export", "approval:export",
}


def test_datatable_export_permissions_are_assignable_and_admin_only_by_default() -> None:
    active = {item["code"] for item in ALL_PERMISSIONS}
    assert EXPORT_PERMISSION_CODES <= active
    assert ROLE_PERMISSIONS_MAPPING["TEAM_ADMIN"] == "all"
    for role_code in ("SALES_DIRECTOR", "SALES_MEMBER", "FINANCE"):
        assert EXPORT_PERMISSION_CODES.isdisjoint(ROLE_PERMISSIONS_MAPPING[role_code])
```

Migration test must load revision `137_datatable_export_permissions`, assert `down_revision == ("136_business_journey_saved_views", "136_customer_initial_enrichment")`, and verify only `TEAM_ADMIN` is used in role assignment SQL.

- [ ] **Step 2: Run RED**

```bash
cd CRM-Server
.venv/bin/python -m pytest tests/unit/test_permission_catalog.py tests/unit/test_datatable_export_permissions_migration.py -q --no-cov
```

- [ ] **Step 3: Add catalog entries and migration**

Add nine permission records with `action: "export"` and resource values matching each permission prefix. The migration must:

```python
revision = "137_datatable_export_permissions"
down_revision = ("136_business_journey_saved_views", "136_customer_initial_enrichment")
```

Use idempotent `INSERT ... WHERE NOT EXISTS`; populate `is_active=1` when that column exists; add role links only for `r.code = 'TEAM_ADMIN'`; downgrade removes those links and permissions.

- [ ] **Step 4: Verify migration behavior**

```bash
cd CRM-Server
.venv/bin/python -m pytest tests/unit/test_permission_catalog.py tests/unit/test_datatable_export_permissions_migration.py -q --no-cov
.venv/bin/alembic heads
.venv/bin/alembic upgrade head
.venv/bin/alembic current
```

Expected: one head, `137_datatable_export_permissions`.

- [ ] **Step 5: Commit Task 3**

```bash
git add CRM-Server/app/constants/permissions.py CRM-Server/migrations/versions/137_datatable_export_permissions.py CRM-Server/tests/unit/test_datatable_export_permissions_migration.py CRM-Server/tests/unit/test_permission_catalog.py
git commit -m "feat(auth): add datatable export permissions"
```

---

### Task 4: Add export projection and responsive DataTable dialog

**Files:**
- Modify: `CRM-Client/src/components/crmwolf/listFieldCatalog.ts`
- Create: `CRM-Client/src/components/crmwolf/DataTableExportDialog.vue`
- Modify: `CRM-Client/src/components/crmwolf/ListAdvancedTools.vue`
- Modify: `CRM-Client/src/components/crmwolf/DataTable.vue`
- Modify: `CRM-Client/src/components/crmwolf/index.ts`
- Modify: `CRM-Client/src/components/crmwolf/__tests__/listFieldCatalog.test.ts`
- Modify: `CRM-Client/src/components/crmwolf/__tests__/ListAdvancedTools.test.ts`
- Create: `CRM-Client/src/components/crmwolf/__tests__/DataTableExportDialog.test.ts`
- Modify: `CRM-Client/src/components/crmwolf/__tests__/DataTableInteraction.test.ts`

**Interfaces:**
- Produces `ListFieldExportConfig`, `DataTableExportField`, `ProjectedListFields.exportFields`.
- Adds DataTable props `exportEnabled`, `exportTitle`, `exportHandler`.
- Adds advanced-tool props `exportFields`, `exportEnabled`, `exportTitle`, `exportTotal`, `exportHandler`.

- [ ] **Step 1: Write failing field projection tests**

Add tests for default/export-only/forbidden behavior:

```ts
expect(projectListFieldCatalog([
  { key: 'public_id', label: '业务 ID', export: true },
  { key: 'name', label: '名称', type: 'text', column: true },
  { key: 'owner_id', label: '负责人', type: 'enum', column: true, export: { key: 'owner' } },
  { key: 'badge', label: '标记', role: 'decoration', column: true },
])).toMatchObject({
  exportFields: [
    { fieldKey: 'public_id', key: 'public_id', label: '业务 ID', source: 'export-only' },
    { fieldKey: 'name', key: 'name', label: '名称', source: 'column' },
    { fieldKey: 'owner_id', key: 'owner', label: '负责人', source: 'column' },
  ],
})
expect(() => defineListFields([{ key: 'id', label: 'ID', export: true }]))
  .toThrow('List field export key "id" is unsafe')
expect(() => defineListFields([{ key: 'owner_id', label: '负责人', type: 'enum', column: true, export: true }]))
  .toThrow('List field export key "owner_id" is unsafe')
```

- [ ] **Step 2: Write failing dialog behavior tests**

`DataTableExportDialog.test.ts` must assert:

- visible fields selected on every open;
- hidden fields and `public_id` unchecked;
- `public_id` is passed first to `exportHandler` when selected;
- zero total and zero selection disable submit;
- a pending `exportHandler` Promise prevents duplicate calls;
- handler resolution closes the dialog;
- handler rejection keeps the dialog and current selections;
- closing/reopening discards the previous temporary selection.

Use exact props:

```ts
const fields = [
  { fieldKey: 'name', key: 'name', label: '名称', source: 'column', visible: true },
  { fieldKey: 'owner', key: 'owner', label: '负责人', source: 'column', visible: false },
  { fieldKey: 'public_id', key: 'public_id', label: '业务 ID', source: 'export-only', visible: false },
] as const
```

- [ ] **Step 3: Run RED**

```bash
cd CRM-Client
npm run test:unit -- src/components/crmwolf/__tests__/listFieldCatalog.test.ts src/components/crmwolf/__tests__/DataTableExportDialog.test.ts src/components/crmwolf/__tests__/ListAdvancedTools.test.ts src/components/crmwolf/__tests__/DataTableInteraction.test.ts
```

- [ ] **Step 4: Extend the field catalog**

Add:

```ts
export interface ListFieldExportConfig {
  key?: string
  label?: string
}
export interface DataTableExportField {
  fieldKey: string
  key: string
  label: string
  source: 'column' | 'export-only'
}
```

`resolveListFieldExport()` rules:

- explicit `false` disables;
- explicit `true`/object enables;
- safe business columns default enabled;
- action/decoration and keyword/filter-only/sort-only fields do not default enabled;
- effective export keys equal to `id`, or ending in `_id` other than `public_id`/`*_public_id`, never default-enable;
- explicitly enabling an unsafe effective export key throws;
- `export: { key: 'owner' }` maps a table/query field such as `owner_id` to a safe request key;
- duplicate effective export keys throw.

Add `exportFields` to `ProjectedListFields`.

- [ ] **Step 5: Implement `DataTableExportDialog.vue`**

Use the existing `Dialog`, `Checkbox`, `Button`, and `TableToolbarButton`. Public contract:

```ts
const props = defineProps<{
  fields: Array<DataTableExportField & { visible: boolean }>
  total: number
  title: string
  exportHandler: (fieldKeys: string[]) => Promise<void>
}>()
```

The dialog owns `submitting`. On submit it awaits `exportHandler(selectedKeys)`, closes only after resolution, and leaves the dialog and selections intact when the Promise rejects.

Render a toolbar trigger labeled `导出`, dialog title `导出 Excel`, description `将导出当前筛选结果，共 ${total} 条。`, groups `当前显示字段` and `其他可选字段`, and footer buttons `取消`/`导出`.

- [ ] **Step 6: Wire responsive tools and DataTable state**

In `DataTable.vue`:

```ts
exportEnabled?: boolean
exportTitle?: string
exportHandler?: (fieldKeys: string[]) => Promise<void>
```

Defaults: `false`, `'列表'`, `undefined`. Compute export fields by joining projected `fieldKey` metadata to `preferredColumns`: column fields inherit current order/visibility; export-only fields follow after columns. Add export to `hasAdvancedTools`; pass the async handler unchanged.

In `ListAdvancedTools.vue`, render `DataTableExportDialog` inside the existing teleported tool target after `ColumnConfigPopover`. This automatically produces desktop first-level visibility and compact “更多设置” behavior.

- [ ] **Step 7: Verify GREEN**

```bash
cd CRM-Client
npm run test:unit -- src/components/crmwolf/__tests__/listFieldCatalog.test.ts src/components/crmwolf/__tests__/DataTableExportDialog.test.ts src/components/crmwolf/__tests__/ListAdvancedTools.test.ts src/components/crmwolf/__tests__/DataTableInteraction.test.ts
npx eslint src/components/crmwolf/listFieldCatalog.ts src/components/crmwolf/DataTableExportDialog.vue src/components/crmwolf/ListAdvancedTools.vue src/components/crmwolf/DataTable.vue src/components/crmwolf/index.ts src/components/crmwolf/__tests__/DataTableExportDialog.test.ts --max-warnings=0
```

- [ ] **Step 8: Commit Task 4**

```bash
git add CRM-Client/src/components/crmwolf/listFieldCatalog.ts CRM-Client/src/components/crmwolf/DataTableExportDialog.vue CRM-Client/src/components/crmwolf/ListAdvancedTools.vue CRM-Client/src/components/crmwolf/DataTable.vue CRM-Client/src/components/crmwolf/index.ts CRM-Client/src/components/crmwolf/__tests__
git commit -m "feat(datatable): add export field dialog"
```

---

### Task 5: Add frontend export transport, filename, and composable

**Files:**
- Create: `CRM-Client/src/api/listExport.ts`
- Create: `CRM-Client/src/utils/downloadBlob.ts`
- Create: `CRM-Client/src/composables/useDataTableExport.ts`
- Create: `CRM-Client/src/api/__tests__/listExport.test.ts`
- Create: `CRM-Client/src/utils/__tests__/downloadBlob.test.ts`
- Create: `CRM-Client/src/composables/__tests__/useDataTableExport.test.ts`

**Interfaces:**
- Produces `ListExportPayload<TTab>`, `postListExport()`, `buildDataTableExportFileName()`, `downloadBlob()`, and `useDataTableExport()`.
- Consumers: all nine page/API integrations.

- [ ] **Step 1: Write failing transport and lifecycle tests**

`listExport.test.ts` asserts:

```ts
expect(post).toHaveBeenCalledWith('/v1/customers/export', payload, {
  responseType: 'blob',
  timeout: 0,
})
```

`downloadBlob.test.ts` asserts this filename:

```ts
expect(buildDataTableExportFileName('客户列表', '所有客户', new Date('2026-09-21T14:35:00')))
  .toBe('客户列表-所有客户-20260921-143500.xlsx')
```

It must also assert `createObjectURL`, anchor append/click/remove, and `revokeObjectURL` in `finally`.

`useDataTableExport.test.ts` asserts the composable ignores a second call while pending, downloads once on success, rethrows after `handleApiError` on failure, and always restores `exporting=false`.

- [ ] **Step 2: Run RED**

```bash
cd CRM-Client
npm run test:unit -- src/api/__tests__/listExport.test.ts src/utils/__tests__/downloadBlob.test.ts src/composables/__tests__/useDataTableExport.test.ts
```

- [ ] **Step 3: Implement typed Blob transport**

```ts
export interface ListExportPayload<TTab extends string> {
  fields: string[]
  tab: TTab
  search?: string
  filters: ListFilterCondition[]
  sorts: ListSortCondition[]
}

export async function postListExport<TTab extends string>(
  path: string,
  payload: ListExportPayload<TTab>,
): Promise<Blob> {
  const response = BlobPartResponseSchema.parse(await request.post<unknown>(path, payload, {
    responseType: 'blob',
    timeout: 0,
  }))
  return response instanceof Blob ? response : new Blob([response])
}
```

- [ ] **Step 4: Implement filename and download lifecycle**

`buildDataTableExportFileName(title, tabLabel, now)` removes `\\/:*?\"<>|` and line breaks, falls back to `列表导出`, and formats local time as `YYYYMMDD-HHmmss.xlsx`.

`downloadBlob(blob, fileName)` must create an object URL, append/click/remove an `<a download>`, and call `URL.revokeObjectURL(url)` in `finally`.

- [ ] **Step 5: Implement `useDataTableExport`**

```ts
export function useDataTableExport(options: {
  request: (fields: string[]) => Promise<Blob>
  fileName: () => string
  successMessage?: string
}): {
  exporting: Readonly<Ref<boolean>>
  exportFields: (fields: string[]) => Promise<void>
}
```

If already exporting, return immediately. Otherwise request, download, and show `toast.success(options.successMessage ?? '导出完成')`. On failure call `handleApiError(error, '导出 Excel')` and rethrow so `DataTableExportDialog` remains open. Reset state in `finally`.

- [ ] **Step 6: Verify and commit**

```bash
cd CRM-Client
npm run test:unit -- src/api/__tests__/listExport.test.ts src/utils/__tests__/downloadBlob.test.ts src/composables/__tests__/useDataTableExport.test.ts
npx eslint src/api/listExport.ts src/utils/downloadBlob.ts src/composables/useDataTableExport.ts src/api/__tests__/listExport.test.ts src/utils/__tests__/downloadBlob.test.ts src/composables/__tests__/useDataTableExport.test.ts --max-warnings=0
git add src/api/listExport.ts src/utils/downloadBlob.ts src/composables/useDataTableExport.ts src/api/__tests__/listExport.test.ts src/utils/__tests__/downloadBlob.test.ts src/composables/__tests__/useDataTableExport.test.ts
git commit -m "feat(export): add frontend download workflow"
```

---

### Task 6: Export Customers and Leads end to end

**Files:**
- Modify: `CRM-Server/app/core/list_query/engine.py`
- Modify: `CRM-Server/app/crud/customer.py`
- Modify: `CRM-Server/app/crud/lead.py`
- Modify: `CRM-Server/app/api/customers.py`
- Modify: `CRM-Server/app/api/leads.py`
- Create: `CRM-Server/tests/unit/test_customer_lead_export_api.py`
- Modify: `CRM-Server/tests/unit/test_lead_list_api.py`
- Modify: `CRM-Client/src/api/customer.ts`
- Modify: `CRM-Client/src/api/lead.ts`
- Modify: `CRM-Client/src/views/Customers.vue`
- Modify: `CRM-Client/src/views/Leads.vue`
- Create: `CRM-Client/src/views/__tests__/customerLeadExportContract.test.ts`

**Interfaces:**
- Adds `POST /v1/customers/export` and `POST /v1/leads/export`.
- Adds export-only `public_id` fields and permissions `customer:export` / `lead:export`.

- [ ] **Step 1: Write failing backend tests**

Create `test_customer_lead_export_api.py` with these concrete tests:

- `test_customer_export_requires_export_permission`: call the FastAPI route without `customer:export`; expect `403`.
- `test_customer_export_keeps_view_scope`: seed two owners, grant `customer:export` plus `customer:view:own`, export tab `all`; reopen the workbook and assert only the current user's customer appears.
- `test_customer_export_public_tab_uses_public_pool_query`: seed owned and ownerless customers; export tab `public`; assert only ownerless rows.
- `test_customer_export_writes_all_76_filtered_rows`: seed 76 matching customers, request two fields, assert 77 worksheet rows including the header.
- `test_lead_export_public_tab_uses_user_readable_values`: seed public leads and assert business ID, Chinese status, source name, owner name, and product name.
- `test_customer_and_lead_export_reject_unsafe_fields`: POST `fields=["id"]`; expect `422`. POST `fields=["missing"]`; expect `400`.

Reuse the SQLite/TestClient fixture style from `tests/unit/test_lead_list_api.py`. Read `FileResponse.path` or response bytes before the background cleanup and reopen with `openpyxl`.

- [ ] **Step 2: Run RED**

```bash
cd CRM-Server
.venv/bin/python -m pytest tests/unit/test_customer_lead_export_api.py tests/unit/test_lead_list_api.py -q --no-cov
```

- [ ] **Step 3: Expose a no-pagination ordered query path**

Add `build_optional_list_query()` in `engine.py` returning `(filtered_query, ordered_query)` without offset/limit. Refactor `apply_optional_list_query()` to count `filtered_query` and return `ordered_query, total`, preserving existing behavior.

Add these exact unified-protocol CRUD methods; `Query` means `sqlalchemy.orm.Query`:

```python
def build_list_query(
    self, db: Session, *, team_id: int, owner_id: str | None,
    scope: str | None, current_user_id: str | None,
    include_collaborated: bool, search: str | None,
    filters: list[FilterCondition], sorts: list[SortCondition],
) -> Query:
    """Return the filtered, ordered customer query without count or pagination."""

def build_public_list_query(
    self, db: Session, *, team_id: int, search: str | None,
    filters: list[FilterCondition], sorts: list[SortCondition],
) -> Query:
    """Return the filtered, ordered public-pool query without pagination."""
```

Implement one customer pair and one lead pair with the same signatures minus unsupported scope inputs. Append `Customer.id.asc()` / `Lead.id.asc()` after business sorting. Existing paginated methods call these builders then count/offset/limit. Legacy query branches remain intact.

- [ ] **Step 4: Extract batch response projection and implement endpoints**
- Move the existing customer list batch enrichment into `_build_customer_list_responses(db, customers, team_id)`; both list and export consume it in batches.
- Reuse existing `_build_lead_list_responses` per streamed batch.
- Add explicit row mappers with complete output keys:

```python
def _customer_export_row(item: CustomerListResponse) -> dict[str, object]:
    return {
        "public_id": item.public_id,
        "account_name": item.account_name,
        "owner": item.owner_info.name if item.owner_info else None,
        "collaborators": "、".join(user.name for user in item.collaborator_infos),
        "city": item.city,
        "company_scale": item.company_scale,
        "status": CUSTOMER_STATUS_LABELS[item.status],
        "license_status": customer_license_status_label(item),
        "license_expiry_date": item.license_expiry_date,
        "default_procurement_method": item.default_procurement_method_info.name if item.default_procurement_method_info else None,
        "industry": item.industry_info.name if item.industry_info else None,
        "source": item.source_info.name if item.source_info else item.source,
        "product_name": item.product_name,
        "creator": item.creator_info.name if item.creator_info else None,
        "created_time": item.created_time,
    }

def _lead_export_row(item: LeadListResponse) -> dict[str, object]:
    return {
        "public_id": item.public_id,
        "lead_name": item.lead_name,
        "owner": item.owner_info.name if item.owner_info else None,
        "contact_name": item.contact_name,
        "contact_phone": item.contact_phone,
        "source": item.source_info.name if item.source_info else item.source,
        "product_name": item.product_name,
        "city": item.city,
        "company_scale": item.company_scale,
        "status": LEAD_STATUS_LABELS[item.status],
        "created_time": item.created_time,
    }
```

Define the two status-label maps and `customer_license_status_label()` in the API module. The customer helper must use `classify_license_status(..., business_now().date())` and labels `{none: 未授权, expired: 已过期, trial: 试用, official: 正式}`. Names come from batch-projected response objects, never internal IDs.
Implement endpoints with complete dependency signatures:

```python
@router.post("/export", dependencies=[Depends(require_permission("customer:export"))])
def export_customers(
    request: CustomerListExportRequest,
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    query = _resolve_customer_export_query(request, team_id, current_user, db)
    stream = query.enable_eagerloads(False).execution_options(stream_results=True).yield_per(500)
    rows = _iter_customer_export_rows(
        stream, team_id, projection_session_factory=SessionLocal,
    )
    generated = create_list_export_file(
        catalog=CUSTOMERS_LIST_EXPORT_CATALOG,
        selected_keys=request.fields,
        rows=rows,
        file_stem=_customer_export_file_stem(request.tab),
    )
    return list_export_file_response(generated)
```
Implement `_resolve_customer_export_query`, `_iter_customer_export_rows`, and `_customer_export_file_stem` as private typed helpers. `_iter_customer_export_rows` uses `iter_batches(stream, 500)`; for each batch it opens `projection_db = projection_session_factory()`, batch-projects display values, yields mappings, and closes `projection_db` in `finally` before the next stream batch. The lead endpoint mirrors these helpers with `LeadListExportRequest` and `lead:export`. Place static `/export` before any `/{customer_id}` or `/{lead_id}` route.


- [ ] **Step 5: Add domain API methods and one current-query builder per page**

Add:

```ts
exportCustomers(payload: ListExportPayload<CustomerExportTab>): Promise<Blob>
exportLeads(payload: ListExportPayload<LeadExportTab>): Promise<Blob>
```

In `Customers.vue`, use one builder for list and export:

```ts
const currentCustomerListContext = () => ({
  tab: activeTab.value === 'public' || activeTab.value === 'collaborated' ? activeTab.value : 'all' as const,
  search: search.value.trim() || undefined,
  filters: activeFilters.value,
  sorts: activeSorts.value,
})
```

Custom-view IDs map to `all` because `useCustomFilterViews` materializes the custom view's effective filters/sorts into `activeFilters`/`activeSorts` before refresh. Repeat with `all|public` for Leads. Add `{ key: 'public_id', label: '业务 ID', export: true }`, permission computed, `:export-enabled`, `export-title`, `:export-handler="exportFields"`, and `useDataTableExport`. There is no separate `exporting` prop.

- [ ] **Step 6: Verify and commit**

```bash
cd CRM-Server
.venv/bin/python -m pytest tests/unit/test_customer_lead_export_api.py tests/unit/test_lead_list_api.py tests/unit/test_permission_catalog.py -q --no-cov
.venv/bin/ruff check app/core/list_query/engine.py app/crud/customer.py app/crud/lead.py app/api/customers.py app/api/leads.py tests/unit/test_customer_lead_export_api.py
cd ../CRM-Client
npm run test:unit -- src/views/__tests__/customerLeadExportContract.test.ts src/api/__tests__/customer.test.ts src/components/crmwolf/__tests__/listFieldCatalog.test.ts
npx eslint src/api/customer.ts src/api/lead.ts src/views/Customers.vue src/views/Leads.vue src/views/__tests__/customerLeadExportContract.test.ts --max-warnings=0
git add CRM-Server/app/core/list_query/engine.py CRM-Server/app/crud/customer.py CRM-Server/app/crud/lead.py CRM-Server/app/api/customers.py CRM-Server/app/api/leads.py CRM-Server/tests/unit/test_customer_lead_export_api.py CRM-Server/tests/unit/test_lead_list_api.py CRM-Client/src/api/customer.ts CRM-Client/src/api/lead.ts CRM-Client/src/views/Customers.vue CRM-Client/src/views/Leads.vue CRM-Client/src/views/__tests__/customerLeadExportContract.test.ts
git commit -m "feat(export): export customer and lead lists"
```
---

### Task 7: Export Opportunities and Contracts end to end

**Files:**
- Modify: `CRM-Server/app/crud/opportunity.py`
- Modify: `CRM-Server/app/crud/contract.py`
- Modify: `CRM-Server/app/api/opportunities.py`
- Modify: `CRM-Server/app/api/contracts.py`
- Create: `CRM-Server/tests/unit/test_opportunity_contract_export_api.py`
- Modify: `CRM-Client/src/api/opportunity.ts`
- Modify: `CRM-Client/src/api/contract.ts`
- Modify: `CRM-Client/src/views/Opportunities.vue`
- Modify: `CRM-Client/src/views/Contracts.vue`
- Create: `CRM-Client/src/views/__tests__/opportunityContractExportContract.test.ts`

**Interfaces:**
- Adds `POST /v1/opportunities/export`, `POST /v1/contracts/export`.
- Adds optional Opportunity `public_id`; Contracts use `contract_number` and never internal ID.

- [ ] **Step 1: Re-read and preserve current `opportunities.py` changes, then write RED tests**

Before editing, read the current diff for `CRM-Server/app/api/opportunities.py`; integrate rather than replacing it. Tests cover 403, owner scope, tab status, 76 rows, status labels, money/date types, and missing contract numbers remaining blank rather than `id` fallback.

- [ ] **Step 2: Extract ordered query builders**

Add `build_list_query()` to both CRUD classes. Use existing unified filters/sorts/search and append stable ORM ID ordering. Existing GET methods paginate the builder result.

- [ ] **Step 3: Replace list N+1 projection with reusable batch projection**
- Opportunities: create `_build_opportunity_list_responses(projection_db, opportunities, team_id)` that batch-loads customers, users, stages/snapshots, approval phases, journey public IDs, and product/module data for one streamed batch.
- Contracts: create `_build_contract_list_responses(projection_db, contracts, team_id)` that batch-loads customers, opportunities, users, and latest issued official License values. Do not call `_get_latest_official_license_info()` once per contract in export/list batches. Export iterators open and close one projection Session per batch.

Export mappings use the Task 2 matrices and Chinese enum labels. The contract field `owner_id` must declare `export: { key: 'owner', label: '负责人' }`; the backend contract catalog and request use only `owner` and write the owner name.

- [ ] **Step 4: Add endpoints and frontend wiring**

Normalize page tabs:

```ts
// Opportunities custom views normalize to all.
'all' | 'active' | 'won' | 'lost'
// Contracts custom views normalize to all.
'all' | 'DRAFT' | 'PENDING_REVIEW' | 'SIGNED'
```

Add Opportunity `{ key: 'public_id', label: '业务 ID', export: true }`; do not add an internal/business-ID field to Contracts beyond `contract_number`.

- [ ] **Step 5: Verify and commit**

```bash
cd CRM-Server
.venv/bin/python -m pytest tests/unit/test_opportunity_contract_export_api.py tests/unit/test_contract_permission_deps.py tests/unit/test_opportunity_schema.py -q --no-cov
.venv/bin/ruff check app/crud/opportunity.py app/crud/contract.py app/api/opportunities.py app/api/contracts.py tests/unit/test_opportunity_contract_export_api.py
cd ../CRM-Client
npm run test:unit -- src/views/__tests__/opportunityContractExportContract.test.ts
npx eslint src/api/opportunity.ts src/api/contract.ts src/views/Opportunities.vue src/views/Contracts.vue src/views/__tests__/opportunityContractExportContract.test.ts --max-warnings=0
git add CRM-Server/app/crud/opportunity.py CRM-Server/app/crud/contract.py CRM-Server/app/api/opportunities.py CRM-Server/app/api/contracts.py CRM-Server/tests/unit/test_opportunity_contract_export_api.py CRM-Client/src/api/opportunity.ts CRM-Client/src/api/contract.ts CRM-Client/src/views/Opportunities.vue CRM-Client/src/views/Contracts.vue CRM-Client/src/views/__tests__/opportunityContractExportContract.test.ts
git commit -m "feat(export): export opportunity and contract lists"
```

---

### Task 8: Export Payment Plans and Payment Records end to end

**Files:**
- Modify: `CRM-Server/app/crud/payment.py`
- Modify: `CRM-Server/app/api/payments.py`
- Create: `CRM-Server/tests/unit/test_payment_export_api.py`
- Modify: `CRM-Server/tests/unit/test_payment_list_query_crud.py`
- Modify: `CRM-Client/src/api/payment.ts`
- Modify: `CRM-Client/src/views/PaymentPlans.vue`
- Modify: `CRM-Client/src/views/PaymentRecords.vue`
- Create: `CRM-Client/src/views/__tests__/paymentExportContract.test.ts`

**Interfaces:**
- Adds `POST /v1/payments/payment-plans/export` and `POST /v1/payments/payment-records/export`.
- No `public_id`; plan/record numbers are business identifiers.

- [ ] **Step 1: Write RED tests**

Create `test_payment_export_api.py` with:

- `test_payment_plan_export_requires_permission_and_preserves_view_own_scope`;
- `test_payment_plan_export_maps_pending_tab_and_exports_all_rows`;
- `test_payment_record_export_maps_confirmed_tab_to_approved`;
- `test_payment_record_export_projects_latest_invoice_title_and_owner_name`;
- `test_payment_exports_leave_missing_business_numbers_blank`.

Each workbook assertion reopens the response bytes with `openpyxl` and checks exact headers, values, and row counts.

- [ ] **Step 2: Extract query builders and batch enrichment**

Add exact methods:

```python
def build_list_query(
    self, db: Session, *, team_id: int, status: str | None,
    current_user_id: str | None, search: str | None,
    filters: list[FilterCondition], sorts: list[SortCondition],
) -> Query:
    """Return ordered payment plans without pagination."""

def build_list_query(
    self, db: Session, *, team_id: int, approval_status: str | None,
    current_user_id: str | None, search: str | None,
    filters: list[FilterCondition], sorts: list[SortCondition],
) -> Query:
    """Return ordered payment records without pagination."""
```

These methods live on `PaymentPlanCRUD` and `PaymentRecordCRUD` respectively. Refactor current unified-protocol list methods to count/paginate them. Remove the existing payment-plan per-row Contract/Customer/Opportunity re-query loop and consume joined relationships. Extract `_build_payment_record_list_items(projection_db, records, team_id)` for latest invoice title and owner-name batch enrichment. Export batches use a separate `SessionLocal()` projection Session and close it before consuming the next stream batch.

- [ ] **Step 3: Add endpoints and row mappings**

Map tabs to fixed status inputs before removing duplicate filter fields:

```text
Payment plans: pending→PENDING, partial→PARTIAL, completed→COMPLETED
Payment records: confirmed→approved; pending_submit/pending_approval/rejected unchanged
```

Add `_payment_plan_export_row(PaymentPlanResponse)` and `_payment_record_export_row(PaymentRecordListItem)` that return every key in the Task 2 catalogs. Status labels are `{PENDING: 待登记, PARTIAL: 部分回款, COMPLETED: 已登记, OVERDUE: 已逾期}` and `{PENDING: 待确认, CONFIRMED: 已确认, DISPUTED: 有争议}`. Business-number fields use the stored number or `None`, never ORM IDs. Stream 500-row batches through the shared workbook service.

- [ ] **Step 4: Add frontend API/page wiring**

Use `payment:plan:export` and `payment:record:export`. Add API methods with `ListExportPayload`, extract one current-context builder in each page, and map custom-view IDs to `all` because effective filters/sorts are already materialized by `useCustomFilterViews`. Wire `:export-enabled`, `export-title`, and `:export-handler="exportFields"` with the shared composable.

- [ ] **Step 5: Verify and commit**

```bash
cd CRM-Server
.venv/bin/python -m pytest tests/unit/test_payment_export_api.py tests/unit/test_payment_list_query_crud.py tests/test_payment_record_list.py tests/test_payment_plan_api.py -q --no-cov
.venv/bin/ruff check app/crud/payment.py app/api/payments.py tests/unit/test_payment_export_api.py
cd ../CRM-Client
npm run test:unit -- src/views/__tests__/paymentExportContract.test.ts src/components/__tests__/PaymentPlansContract.test.ts
npx eslint src/api/payment.ts src/views/PaymentPlans.vue src/views/PaymentRecords.vue src/views/__tests__/paymentExportContract.test.ts --max-warnings=0
git add CRM-Server/app/crud/payment.py CRM-Server/app/api/payments.py CRM-Server/tests/unit/test_payment_export_api.py CRM-Server/tests/unit/test_payment_list_query_crud.py CRM-Client/src/api/payment.ts CRM-Client/src/views/PaymentPlans.vue CRM-Client/src/views/PaymentRecords.vue CRM-Client/src/views/__tests__/paymentExportContract.test.ts
git commit -m "feat(export): export payment lists"
```

---

### Task 9: Export Invoices and Approvals end to end

**Files:**
- Modify: `CRM-Server/app/crud/invoice.py`
- Modify: `CRM-Server/app/crud/approval.py`
- Modify: `CRM-Server/app/api/invoices.py`
- Modify: `CRM-Server/app/api/approvals.py`
- Create: `CRM-Server/tests/unit/test_invoice_approval_export_api.py`
- Modify: `CRM-Server/tests/unit/test_approval_list_api.py`
- Modify: `CRM-Client/src/api/invoice.ts`
- Modify: `CRM-Client/src/api/approvalGeneric.ts`
- Modify: `CRM-Client/src/schemas/approvalGeneric.ts`
- Modify: `CRM-Client/src/views/Invoices.vue`
- Modify: `CRM-Client/src/views/ApprovalCenter.vue`
- Create: `CRM-Client/src/views/__tests__/invoiceApprovalExportContract.test.ts`

**Interfaces:**
- Adds `POST /v1/invoice-applications/export`, `POST /v1/approvals/export`.
- Approval export preserves pending/processed/submitted role scope and omits approval/business internal IDs.

- [ ] **Step 1: Write RED tests**

Create `test_invoice_approval_export_api.py` with:

- `test_invoice_export_requires_permission_and_keeps_view_own_customer_scope`;
- `test_invoice_export_maps_invoiced_tab_and_writes_formula_safe_title`;
- `test_approval_export_keeps_pending_role_scope`;
- `test_approval_export_keeps_processed_and_submitted_scope`;
- `test_invoice_and_approval_exports_write_all_matching_rows`.

- [ ] **Step 2: Extract invoice and approval query/projection paths**
- Invoice: add `InvoiceApplicationCRUD.build_list_query(...) -> Query`; replace `_populate_application_info` per-row calls for list/export with `_populate_application_list_info(projection_db, applications, team_id)` using batch customer/contract/payment-plan/applicant/effective-status lookups. Export opens and closes one projection Session per batch.
- Approval: add `ApprovalCRUD.build_list_query(...) -> tuple[Query, bool]`, where the boolean records whether legacy summary-field filtering is required; add `build_list_items(projection_db, rows, team_id)`. Unified requests—including `filters=[]`, `sorts=[]`—must paginate SQL before batch projection. Export iterates ordered rows in 500-row batches, opens a projection Session for each batch, calls `build_list_items`, then closes it before advancing the streaming cursor.

- [ ] **Step 3: Add endpoints, row mappings, and frontend wiring**

Invoice tab mapping is pending→PENDING_REVIEW, approved→APPROVED, invoiced→ISSUED. Approval uses pending/processed/submitted unchanged. Add explicit row mappers for every Task 2 catalog key using Chinese invoice type/status/effective-status and approval type/status labels; parse approval ISO timestamps with `datetime.fromisoformat` before workbook writing. Add Blob API methods, independent permission computations, current-context builders, and DataTable async handlers. Custom invoice view IDs map to all because effective filters/sorts are already materialized.

- [ ] **Step 4: Verify and commit**

```bash
cd CRM-Server
.venv/bin/python -m pytest tests/unit/test_invoice_approval_export_api.py tests/unit/test_approval_list_api.py tests/test_invoice_management.py -q --no-cov
.venv/bin/ruff check app/crud/invoice.py app/crud/approval.py app/api/invoices.py app/api/approvals.py tests/unit/test_invoice_approval_export_api.py
cd ../CRM-Client
npm run test:unit -- src/views/__tests__/invoiceApprovalExportContract.test.ts src/components/ui/pagination/__tests__/ApprovalCenterPaginationContract.test.ts
npx eslint src/api/invoice.ts src/api/approvalGeneric.ts src/schemas/approvalGeneric.ts src/views/Invoices.vue src/views/ApprovalCenter.vue src/views/__tests__/invoiceApprovalExportContract.test.ts --max-warnings=0
git add CRM-Server/app/crud/invoice.py CRM-Server/app/crud/approval.py CRM-Server/app/api/invoices.py CRM-Server/app/api/approvals.py CRM-Server/tests/unit/test_invoice_approval_export_api.py CRM-Server/tests/unit/test_approval_list_api.py CRM-Client/src/api/invoice.ts CRM-Client/src/api/approvalGeneric.ts CRM-Client/src/schemas/approvalGeneric.ts CRM-Client/src/views/Invoices.vue CRM-Client/src/views/ApprovalCenter.vue CRM-Client/src/views/__tests__/invoiceApprovalExportContract.test.ts
git commit -m "feat(export): export invoice and approval lists"
```

---

### Task 10: Export Customer Tracking end to end

**Files:**
- Modify: `CRM-Server/app/crud/sales_commitment.py`
- Modify: `CRM-Server/app/services/follow_up_task_query_service.py`
- Modify: `CRM-Server/app/api/follow_up_tasks.py`
- Create: `CRM-Server/tests/unit/test_follow_up_task_export_api.py`
- Modify: `CRM-Server/tests/unit/test_follow_up_tasks_api.py`
- Modify: `CRM-Client/src/api/followUpTask.ts`
- Modify: `CRM-Client/src/views/CustomerTracking.vue`
- Create: `CRM-Client/src/views/__tests__/customerTrackingExportContract.test.ts`

**Interfaces:**
- Adds `POST /v1/follow-up-tasks/export` guarded by `follow_up_task:export`.
- Always preserves the current page's fixed `owner_scope='mine'`.

- [ ] **Step 1: Write RED tests**

Create `test_follow_up_task_export_api.py` with:

- `test_follow_up_export_requires_permission`;
- `test_follow_up_export_is_always_scoped_to_current_owner`;
- `test_follow_up_export_maps_all_status_tabs_and_search_filters`;
- `test_follow_up_export_writes_all_76_rows_with_business_id`;
- `test_follow_up_export_batch_loads_customers_users_and_confirmations`.

Add `build_for_owner_query(...) -> Query` and `build_for_customer_query(...) -> Query` in `FollowUpTaskCRUD`. Refactor `FollowUpTaskQueryService.list_tasks` to count/paginate the ordered query and expose `build_task_payloads(projection_db, tasks, team_id, user_id)` that loads customers, users, and pending confirmations once per batch. Export uses owner scope `mine`, a separate projection Session per 500-row batch, and never invokes semantic retrieval because the DataTable page submits no semantic query input.


- [ ] **Step 3: Add endpoint and frontend wiring**

Add export-only `{ key: 'public_id', label: '业务 ID', export: true }`. Map tracking rows to `public_id`, `customer_name`, `tracking_content`, `status_label`, and `tracking_time`; write the real `due_at` datetime while keeping the existing derived status-label semantics. Custom-view IDs map to tab `all` because effective filters/sorts are materialized; built-in tabs remain all/open/completed/cancelled. Add API method, `follow_up_task:export` permission, current-context builder, and DataTable async handler.

- [ ] **Step 4: Verify and commit**

```bash
cd CRM-Server
.venv/bin/python -m pytest tests/unit/test_follow_up_task_export_api.py tests/unit/test_follow_up_tasks_api.py -q --no-cov
.venv/bin/ruff check app/crud/sales_commitment.py app/services/follow_up_task_query_service.py app/api/follow_up_tasks.py tests/unit/test_follow_up_task_export_api.py
cd ../CRM-Client
npm run test:unit -- src/views/__tests__/customerTrackingExportContract.test.ts
npx eslint src/api/followUpTask.ts src/views/CustomerTracking.vue src/views/__tests__/customerTrackingExportContract.test.ts --max-warnings=0
git add CRM-Server/app/crud/sales_commitment.py CRM-Server/app/services/follow_up_task_query_service.py CRM-Server/app/api/follow_up_tasks.py CRM-Server/tests/unit/test_follow_up_task_export_api.py CRM-Server/tests/unit/test_follow_up_tasks_api.py CRM-Client/src/api/followUpTask.ts CRM-Client/src/views/CustomerTracking.vue CRM-Client/src/views/__tests__/customerTrackingExportContract.test.ts
git commit -m "feat(export): export customer tracking list"
```

---

### Task 11: Lock cross-resource contracts, update design docs, and run end-to-end verification

**Files:**
- Create: `CRM-Client/src/components/crmwolf/__tests__/listExportContract.test.ts`
- Modify: `CRM-Client/src/components/crmwolf/__tests__/listPageQueryContract.test.ts`
- Modify: `CRM-Docs/design-system/patterns/list-page.md`
- Modify generated: `CRM-Client/src/components/crmwolf/listExportCatalogManifest.json`
- Test existing/new backend export files from Tasks 1–10.

**Interfaces:**
- Final proof that all nine pages, permissions, manifests, APIs, and UI contracts agree.

- [ ] **Step 1: Add static frontend/backend export contract test**

Parse the nine page field registries and generated manifest. Assert:

```ts
const dataTableViews = {
  'ApprovalCenter.vue': { resource: 'approvals', permission: 'approval:export' },
  'Contracts.vue': { resource: 'contracts', permission: 'contract:export' },
  'CustomerTracking.vue': { resource: 'follow_up_tasks', permission: 'follow_up_task:export' },
  'Customers.vue': { resource: 'customers', permission: 'customer:export' },
  'Invoices.vue': { resource: 'invoices', permission: 'invoice:export' },
  'Leads.vue': { resource: 'leads', permission: 'lead:export' },
  'Opportunities.vue': { resource: 'opportunities', permission: 'opportunity:export' },
  'PaymentPlans.vue': { resource: 'payment_plans', permission: 'payment:plan:export' },
  'PaymentRecords.vue': { resource: 'payment_records', permission: 'payment:record:export' },
} as const
```

For each page, require DataTable `:export-enabled`, `export-title`, and `:export-handler` bindings, the required permission string, one current-query builder used by list and export, no unsafe export key, and exact label agreement with the manifest.

- [ ] **Step 2: Update the list-page design contract**

Add a concise `导出` section to `CRM-Docs/design-system/patterns/list-page.md` stating:

- export shares the field registry and current query context;
- visible columns default selected, hidden fields optional;
- full filtered result, not current page;
- internal IDs forbidden;
- desktop direct action / compact advanced tools;
- server permission enforcement.

- [ ] **Step 3: Run all focused frontend verification**

```bash
cd CRM-Client
npm run test:unit -- \
  src/components/crmwolf/__tests__/listFieldCatalog.test.ts \
  src/components/crmwolf/__tests__/DataTableExportDialog.test.ts \
  src/components/crmwolf/__tests__/ListAdvancedTools.test.ts \
  src/components/crmwolf/__tests__/DataTableInteraction.test.ts \
  src/components/crmwolf/__tests__/listExportContract.test.ts \
  src/components/crmwolf/__tests__/listPageQueryContract.test.ts \
  src/views/__tests__/customerLeadExportContract.test.ts \
  src/views/__tests__/opportunityContractExportContract.test.ts \
  src/views/__tests__/paymentExportContract.test.ts \
  src/views/__tests__/invoiceApprovalExportContract.test.ts \
  src/views/__tests__/customerTrackingExportContract.test.ts
npm run type-check
npm run lint
```

Expected: focused tests pass. Full type/lint must not introduce any diagnostic in changed files; if unrelated pre-existing failures remain, capture their exact file list and verify changed files independently with ESLint/LSP.

- [ ] **Step 4: Run all focused backend verification**

```bash
cd CRM-Server
.venv/bin/python -m pytest \
  tests/unit/test_list_export_service.py \
  tests/unit/list_export/test_catalog_manifest.py \
  tests/unit/test_datatable_export_permissions_migration.py \
  tests/unit/test_customer_lead_export_api.py \
  tests/unit/test_opportunity_contract_export_api.py \
  tests/unit/test_payment_export_api.py \
  tests/unit/test_invoice_approval_export_api.py \
  tests/unit/test_follow_up_task_export_api.py \
  -q --no-cov
.venv/bin/ruff check app/core/list_export app/services/list_export_service.py app/schemas/list_export.py app/api app/crud app/services tests/unit
.venv/bin/mypy app/core/list_export app/services/list_export_service.py app/schemas/list_export.py
.venv/bin/alembic heads
.venv/bin/alembic current
```

Expected: export tests pass; one Alembic head at revision 137.

- [ ] **Step 5: Perform real UI and workbook smoke verification**

Run the actual client/server. In the customer list:

1. apply a filter yielding more than one page;
2. hide one field in field configuration;
3. open Export and verify visible columns are checked, hidden column and Business ID unchecked;
4. check hidden column and Business ID;
5. export and open the `.xlsx` with `openpyxl` or Excel;
6. assert worksheet data rows equal the current filtered total, not the current page size;
7. assert selected column order, Chinese labels/statuses, and absence of any internal ID.

Repeat a minimal export on the other eight pages, checking the permission gate and one resource-specific value mapping each.

- [ ] **Step 6: Commit final contracts/docs**

```bash
git add CRM-Client/src/components/crmwolf/__tests__/listExportContract.test.ts CRM-Client/src/components/crmwolf/__tests__/listPageQueryContract.test.ts CRM-Docs/design-system/patterns/list-page.md CRM-Client/src/components/crmwolf/listExportCatalogManifest.json
git commit -m "test(export): lock datatable export contracts"
```

- [ ] **Step 7: Request code review**

Use `requesting-code-review` against the implementation base and final HEAD. Fix every Critical/Important finding, rerun the focused commands, and only then use `verification-before-completion` for final delivery.
