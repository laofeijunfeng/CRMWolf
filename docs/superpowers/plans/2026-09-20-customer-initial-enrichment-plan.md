# 客户初始智能补全与行业历史回填 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 客户创建接口提交后异步、可恢复地补齐缺失行业；第一期直接从启用行业目录选 code 写入，历史空行业客户使用同一 Workflow 回填，并让首次档案优先读取补全结果、技术失败时按时降级。

**Architecture:** 新增独立 `CustomerEnrichmentJob` 作为执行真相，复用数据库持久队列、租约、重试和 LangGraph 模式，但不混入现有 Profile Projection run。`CustomerLifecyclePostCommitCoordinator` 在客户事务内登记补全 job 和 profile run，提交后只 kick；`CustomerProfileReadinessGate` 在 profile run claim 前持久延后，第一次补全结束或 gate deadline 到期后释放。未来字段由版本化 plan + field registry 复用同一模型调用和一次原子条件写入。

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic v2, LangGraph, LangChain structured output, pytest.

**Spec:** `docs/superpowers/specs/2026-09-20-customer-initial-enrichment-design.md`

## Global Constraints

- 客户保存接口不等待 LLM、重试或档案生成；模型/队列失败不得回滚客户。
- 第一版无人工确认、无置信度门槛；业务无法判断返回启用一级行业 `other`。
- 技术失败、无 AI 配置、非法 code、目录缺失不得伪装成 `other`，必须重试或耗尽。
- 模型只能输出执行时启用的 `crm_industries.code`；禁止自由文本落库。
- 自动补全只允许空值写入；已有行业永不覆盖。
- 模型期间目标字段被用户填写 → SKIPPED；其它版本变化且行业仍空 → RETRY_PENDING，以最新上下文重算。
- Profile Graph 保持只读，不直接修改 Customer。
- 同一客户、同一 `plan_version` 只有一个 job；重复登记必须 no-op。
- 一个 plan 一次模型调用返回所有 requested fields；全部 decision 先校验，再一次事务条件写入，Customer.version 只增加一次；不得部分写入。
- 新客户与历史回填使用同一 Workflow；历史迁移不得使用一次性 SQL 或在 Alembic 内调用模型。
- `INITIAL_CREATION` profile gate 有最大 deadline，worker 停摆时档案不能无限等待。
- 普通客户编辑、跟进、商机、合同、回款和手动档案刷新不得创建新的 initial-enrichment job。
- Agent 不单独接线；其 `create_customer` tool 继续调用标准 `POST /v1/customers/`。
- 不新增 `industry_source`、置信度、一级/二级行业客户字段；来源与 reason 留在 job result / 操作日志。
- 不引入 Redis、Celery 或新的消息中间件。
- 不触碰用户工作区里无关的 `CRM-Client/src/components/crmwolf/*` 改动。
- 中间任务只跑本任务列出的聚焦测试；不跑全量测试、lint 或 formatter。

## 文件结构与职责

- Create: `CRM-Server/migrations/versions/136_customer_initial_enrichment.py` — job 表、profile run `not_before_at`、索引。
- Create: `CRM-Server/app/models/customer_enrichment_job.py` — durable job ORM。
- Create: `CRM-Server/app/services/customer_enrichment_contracts.py` — purpose/status/request/result/decision 合同。
- Create: `CRM-Server/app/crud/customer_enrichment_job.py` — ensure/claim/terminal/retry/requeue/fair recovery selection。
- Create: `CRM-Server/app/services/customer_enrichment_plan.py` — `customer-initial-v1` 和 field registry。
- Create: `CRM-Server/app/services/customer_enrichment_context_service.py` — 有界、去 PII 的上下文。
- Create: `CRM-Server/app/services/customer_enrichment_inference_service.py` — 单次 structured-output 推断。
- Create: `CRM-Server/app/services/customer_enrichment_write_service.py` — 原子条件写、行业复核、操作日志。
- Create: `CRM-Server/app/services/agent/customer_initial_enrichment_graph.py` — 纯计算 LangGraph。
- Create: `CRM-Server/app/services/agent/customer_initial_enrichment_workflow.py` — Graph runner seam。
- Create: `CRM-Server/app/services/customer_enrichment_job_service.py` — lease / workflow / write / failure lifecycle。
- Create: `CRM-Server/app/services/customer_enrichment_profile_coordinator.py` — gate release 和 profile refresh receipt。
- Create: `CRM-Server/app/services/customer_profile_readiness_gate.py` — profile claim 前 gate。
- Create: `CRM-Server/app/services/customer_lifecycle_post_commit_coordinator.py` — 创建事务登记和提交后 kick。
- Create: `CRM-Server/app/services/customer_enrichment_backfill_service.py` — 空行业历史 job 登记。
- Create: `CRM-Server/app/services/customer_enrichment_reconciliation_service.py` — 漏 job、过期 lease/gate、缺 refresh 回执修复。
- Create: `CRM-Server/app/tasks/customer_enrichment_recovery.py` — initial/backfill 公平恢复 worker。
- Create: `CRM-Server/app/tasks/customer_enrichment_backfill.py` — 历史 job 调度。
- Create: `CRM-Server/app/tasks/customer_enrichment_reconciliation.py` — reconciliation scheduler。
- Modify: `CRM-Server/app/models/customer_intelligence_run.py`、`customer_intelligence_run_service.py`、`customer_intelligence_refresh_service.py` — `not_before_at` 和 gate。
- Create: `CRM-Server/app/api/customer_enrichment.py` — diagnostics、requeue、dry-run 独立 router；在 `customers.router` 之前注册，避免 `/{customer_id}` 动态路由吞掉 `/enrichment/*`。
- Modify: `CRM-Server/app/api/customers.py`、`customer_ai.py` — 创建 Coordinator 接入。
- Modify: `CRM-Server/app/services/ai_parser/customer_parser.py` — 旧入口不再独立触发档案刷新。
- Modify: `CRM-Server/app/core/config.py`、`app/main.py`、`app/models/__init__.py`、`app/schemas/system_recovery.py`、`app/schemas/customer.py`。
- Modify: `CONTEXT.md`、`CRM-Docs/design-agent/runtime/customer-intelligence-profile.md`、`CRM-Docs/deployment/README.md`。

---

### Task 1: Persistence contracts, migration, and configuration

**Files:**
- Create: `CRM-Server/migrations/versions/136_customer_initial_enrichment.py`
- Create: `CRM-Server/app/models/customer_enrichment_job.py`
- Create: `CRM-Server/app/services/customer_enrichment_contracts.py`
- Create: `CRM-Server/tests/unit/test_customer_enrichment_jobs_migration.py`
- Modify: `CRM-Server/app/models/customer_intelligence_run.py`
- Modify: `CRM-Server/app/models/__init__.py`
- Modify: `CRM-Server/app/core/config.py`
- Modify: `CRM-Server/app/schemas/system_recovery.py`

**Interfaces:**
- Produces `CustomerEnrichmentPurpose`, `CustomerEnrichmentJobStatus`, `CustomerEnrichmentJobRequest`, `CustomerEnrichmentDecision`, `CustomerEnrichmentInferenceResult`, `CustomerEnrichmentRunResult`.
- Produces ORM `CustomerEnrichmentJob` and nullable `CustomerIntelligenceRun.not_before_at`.
- Migration revision is exactly `136_customer_initial_enrichment`, down revision `135_deal_journey_public_ids`.

- [ ] **Step 1: Write the structural migration test**

Create `CRM-Server/tests/unit/test_customer_enrichment_jobs_migration.py`:

```python
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


class _RecordingOperations:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name: str):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
        return record


def _load_migration() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "136_customer_initial_enrichment.py"
    spec = importlib.util.spec_from_file_location("customer_initial_enrichment_136", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_136_creates_enrichment_jobs_and_profile_gate_column():
    migration = _load_migration()
    operations = _RecordingOperations()
    migration.op = operations

    migration.upgrade()

    assert migration.revision == "136_customer_initial_enrichment"
    assert migration.down_revision == "135_deal_journey_public_ids"
    create_table = next(call for call in operations.calls if call[0] == "create_table")
    assert create_table[1][0] == "crm_customer_enrichment_jobs"
    items = create_table[1][1:]
    columns = {item.name for item in items if hasattr(item, "name")}
    assert {
        "public_id", "team_id", "customer_id", "purpose", "plan_version",
        "requested_fields_json", "status", "available_at", "profile_gate_deadline_at",
        "attempt_count", "max_attempts", "next_attempt_at", "lease_token",
        "lease_expires_at", "run_id", "graph_thread_id", "first_attempt_finished_at",
        "profile_refresh_request_id", "profile_refresh_enqueued_at", "requeue_count",
        "result_json", "error_message", "started_at", "finished_at", "created_time", "updated_time",
    } <= columns
    constraints = {item.name for item in items if getattr(item, "name", None)}
    assert "uq_customer_enrichment_job_plan" in constraints
    assert "ck_customer_enrichment_job_status" in constraints
    assert "ck_customer_enrichment_job_purpose" in constraints
    add_column = next(call for call in operations.calls if call[0] == "add_column")
    assert add_column[1][0] == "crm_customer_intelligence_runs"
    assert add_column[1][1].name == "not_before_at"
```

- [ ] **Step 2: Run RED**

Run: `cd CRM-Server && PYTHONPATH=. ./venv/bin/pytest tests/unit/test_customer_enrichment_jobs_migration.py -q --no-cov`

Expected: FAIL because migration `136_customer_initial_enrichment.py` does not exist.

- [ ] **Step 3: Add canonical contracts**

Create `CRM-Server/app/services/customer_enrichment_contracts.py`:

```python
from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CustomerEnrichmentPurpose(StrEnum):
    INITIAL_CREATION = "INITIAL_CREATION"
    HISTORICAL_BACKFILL = "HISTORICAL_BACKFILL"


class CustomerEnrichmentJobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    RETRY_PENDING = "RETRY_PENDING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    EXHAUSTED = "EXHAUSTED"


class CustomerEnrichmentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    field: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=500)


class CustomerEnrichmentInferenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    decisions: list[CustomerEnrichmentDecision] = Field(min_length=1, max_length=20)


class CustomerEnrichmentJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    team_id: int = Field(gt=0)
    job_public_id: str = Field(pattern=r"^cej_[A-Za-z0-9_-]+$")


class CustomerEnrichmentRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    job_public_id: str
    customer_id: int
    execution_status: str
    success: bool
    retryable: bool = False
    applied_fields: list[str] = Field(default_factory=list)
    skip_reason: str | None = None
    error: str | None = None
    profile_refresh_action: Literal["RELEASED", "ENQUEUED", "NONE"] = "NONE"
```

- [ ] **Step 4: Add ORM model and export**

Create `CRM-Server/app/models/customer_enrichment_job.py` with all columns from the spec, `generate_public_id("cej")`, status/purpose checks, unique `(team_id, customer_id, plan_version)`, and recovery indexes. Add `not_before_at = Column(DateTime, nullable=True, index=True)` to `CustomerIntelligenceRun`. Export `CustomerEnrichmentJob` from `app/models/__init__.py`.

Use these constraints verbatim:

```python
CheckConstraint(
    "status IN ('QUEUED', 'RUNNING', 'RETRY_PENDING', 'COMPLETED', 'SKIPPED', 'EXHAUSTED')",
    name="ck_customer_enrichment_job_status",
)
CheckConstraint(
    "purpose IN ('INITIAL_CREATION', 'HISTORICAL_BACKFILL')",
    name="ck_customer_enrichment_job_purpose",
)
UniqueConstraint("team_id", "customer_id", "plan_version", name="uq_customer_enrichment_job_plan")
```

- [ ] **Step 5: Add migration**

Create migration `136_customer_initial_enrichment.py`. `upgrade()` creates the job table, adds `not_before_at` to `crm_customer_intelligence_runs`, and creates an index named `idx_customer_intelligence_run_not_before`. `downgrade()` drops that index/column before the job table.

- [ ] **Step 6: Add configuration and recovery candidate**

Add exact defaults to `Settings`:

```python
CUSTOMER_INITIAL_ENRICHMENT_SETTLE_SECONDS: int = 5
CUSTOMER_INITIAL_ENRICHMENT_PROFILE_GATE_MAX_SECONDS: int = 30
CUSTOMER_INITIAL_ENRICHMENT_MAX_ATTEMPTS: int = 3
CUSTOMER_INITIAL_ENRICHMENT_LEASE_SECONDS: int = 120
CUSTOMER_INITIAL_ENRICHMENT_RECOVERY_ENABLED: bool = True
CUSTOMER_INITIAL_ENRICHMENT_RECOVERY_INTERVAL_SECONDS: int = 60
CUSTOMER_INITIAL_ENRICHMENT_BATCH_SIZE: int = 20
CUSTOMER_INITIAL_ENRICHMENT_BACKFILL_ENABLED: bool = True
CUSTOMER_INITIAL_ENRICHMENT_BACKFILL_BATCH_SIZE: int = 5
CUSTOMER_INITIAL_ENRICHMENT_BACKFILL_INTERVAL_SECONDS: int = 300
CUSTOMER_INITIAL_ENRICHMENT_RECONCILIATION_ENABLED: bool = True
CUSTOMER_INITIAL_ENRICHMENT_RECONCILIATION_INTERVAL_SECONDS: int = 300
CUSTOMER_INITIAL_ENRICHMENT_RECONCILIATION_BATCH_SIZE: int = 50
```

Add frozen schema:

```python
class CustomerEnrichmentJobRecoveryCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)
    team_id: int
    job_public_id: str
    purpose: str
```

- [ ] **Step 7: Run GREEN and migration smoke**

Run:

```text
cd CRM-Server && PYTHONPATH=. ./venv/bin/pytest tests/unit/test_customer_enrichment_jobs_migration.py -q --no-cov
cd CRM-Server && ./venv/bin/alembic upgrade head && ./venv/bin/alembic current
```

Expected: pytest PASS; Alembic current ends with `136_customer_initial_enrichment (head)`.

- [ ] **Step 8: Commit**

```bash
git add CRM-Server/migrations/versions/136_customer_initial_enrichment.py CRM-Server/app/models/customer_enrichment_job.py CRM-Server/app/models/customer_intelligence_run.py CRM-Server/app/models/__init__.py CRM-Server/app/services/customer_enrichment_contracts.py CRM-Server/app/core/config.py CRM-Server/app/schemas/system_recovery.py CRM-Server/tests/unit/test_customer_enrichment_jobs_migration.py
git commit -m "feat(customer): add durable initial enrichment jobs"
```

---

### Task 2: Enrichment job CRUD lifecycle

**Files:**
- Create: `CRM-Server/app/crud/customer_enrichment_job.py`
- Create: `CRM-Server/tests/unit/test_customer_enrichment_job.py`

**Interfaces:**
- Produces `CustomerEnrichmentJobCRUD.ensure`, `get_by_identity`, `get_by_public_id`, `claim_for_execution`, `mark_completed_if_lease_owner`, `mark_retry_pending_if_lease_owner`, `mark_exhausted_if_lease_owner`, `requeue_exhausted`, and `list_system_recovery_candidates`.
- `available_at` gates QUEUED claims; live leases remain BUSY; first-attempt terminal/retry transitions set `first_attempt_finished_at`; initial/backfill quotas are independent.

- [ ] **Step 1: Write the failing lifecycle tests**

Create `CRM-Server/tests/unit/test_customer_enrichment_job.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.crud.customer_enrichment_job import CustomerEnrichmentJobCRUD
from app.models.customer_enrichment_job import CustomerEnrichmentJob
from app.services.customer_enrichment_contracts import (
    CustomerEnrichmentJobStatus,
    CustomerEnrichmentPurpose,
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ANN001, ANN003
    return "INTEGER"


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[CustomerEnrichmentJob.__table__])
    return sessionmaker(bind=engine)()


def _ensure(
    crud: CustomerEnrichmentJobCRUD,
    db,
    *,
    customer_id: int = 101,
    purpose: str = CustomerEnrichmentPurpose.INITIAL_CREATION.value,
    available_at: datetime | None = None,
):
    now = datetime(2026, 9, 20, 10, 0, 0)
    return crud.ensure(
        db,
        team_id=2,
        customer_id=customer_id,
        purpose=purpose,
        plan_version="customer-initial-v1",
        requested_fields=["industry"],
        available_at=available_at or now,
        profile_gate_deadline_at=(available_at or now) + timedelta(seconds=30)
        if purpose == CustomerEnrichmentPurpose.INITIAL_CREATION.value
        else None,
        max_attempts=3,
    )


def test_ensure_is_idempotent_for_customer_and_plan():
    db = _session()
    crud = CustomerEnrichmentJobCRUD()
    first = _ensure(crud, db)
    second = _ensure(crud, db, purpose=CustomerEnrichmentPurpose.HISTORICAL_BACKFILL.value)
    assert second.id == first.id
    assert second.purpose == CustomerEnrichmentPurpose.INITIAL_CREATION.value
    assert db.query(CustomerEnrichmentJob).count() == 1


def test_claim_honors_available_at_and_live_lease():
    db = _session()
    crud = CustomerEnrichmentJobCRUD()
    now = datetime(2026, 9, 20, 10, 0, 0)
    job = _ensure(crud, db, available_at=now + timedelta(seconds=5))
    assert crud.claim_for_execution(
        db,
        team_id=2,
        public_id=job.public_id,
        lease_token="early",
        lease_expires_at=now + timedelta(seconds=120),
        now=now,
    ) is None
    claimed = crud.claim_for_execution(
        db,
        team_id=2,
        public_id=job.public_id,
        lease_token="owner",
        lease_expires_at=now + timedelta(seconds=125),
        now=now + timedelta(seconds=5),
    )
    assert claimed is not None
    assert claimed.status == CustomerEnrichmentJobStatus.RUNNING.value
    assert claimed.attempt_count == 1
    assert crud.claim_for_execution(
        db,
        team_id=2,
        public_id=job.public_id,
        lease_token="other",
        lease_expires_at=now + timedelta(seconds=130),
        now=now + timedelta(seconds=10),
    ) is None


def test_retry_sets_first_attempt_finished_at():
    db = _session()
    crud = CustomerEnrichmentJobCRUD()
    now = datetime(2026, 9, 20, 10, 0, 0)
    job = _ensure(crud, db, available_at=now)
    crud.claim_for_execution(
        db,
        team_id=2,
        public_id=job.public_id,
        lease_token="owner",
        lease_expires_at=now + timedelta(seconds=120),
        now=now,
    )
    updated = crud.mark_retry_pending_if_lease_owner(
        db,
        team_id=2,
        public_id=job.public_id,
        lease_token="owner",
        error_message="timeout",
        next_attempt_at=now + timedelta(seconds=60),
        result_json={"first_attempt_outcome": "RETRY_PENDING"},
        now=now + timedelta(seconds=2),
    )
    assert updated is not None
    assert updated.status == CustomerEnrichmentJobStatus.RETRY_PENDING.value
    assert updated.first_attempt_finished_at == now + timedelta(seconds=2)
    assert updated.lease_token is None


def test_completed_lease_owner_clears_lease():
    db = _session()
    crud = CustomerEnrichmentJobCRUD()
    now = datetime(2026, 9, 20, 10, 0, 0)
    job = _ensure(crud, db, available_at=now)
    crud.claim_for_execution(
        db,
        team_id=2,
        public_id=job.public_id,
        lease_token="owner",
        lease_expires_at=now + timedelta(seconds=120),
        now=now,
    )
    updated = crud.mark_completed_if_lease_owner(
        db,
        team_id=2,
        public_id=job.public_id,
        lease_token="owner",
        result_json={"applied_fields": ["industry"]},
        now=now + timedelta(seconds=3),
    )
    assert updated is not None
    assert updated.status == CustomerEnrichmentJobStatus.COMPLETED.value
    assert updated.finished_at == now + timedelta(seconds=3)
    assert updated.lease_token is None


def test_exhausted_job_can_be_requeued_in_place():
    db = _session()
    crud = CustomerEnrichmentJobCRUD()
    now = datetime(2026, 9, 20, 10, 0, 0)
    job = _ensure(crud, db, available_at=now)
    crud.claim_for_execution(
        db,
        team_id=2,
        public_id=job.public_id,
        lease_token="owner",
        lease_expires_at=now + timedelta(seconds=120),
        now=now,
    )
    exhausted = crud.mark_exhausted_if_lease_owner(
        db,
        team_id=2,
        public_id=job.public_id,
        lease_token="owner",
        error_message="model down",
        result_json={"terminal": "EXHAUSTED"},
        now=now + timedelta(seconds=3),
    )
    requeued = crud.requeue_exhausted(
        db,
        team_id=2,
        public_id=job.public_id,
        available_at=now + timedelta(minutes=1),
        now=now + timedelta(seconds=4),
    )
    assert exhausted is not None and requeued is not None
    assert requeued.id == job.id
    assert requeued.status == CustomerEnrichmentJobStatus.QUEUED.value
    assert requeued.attempt_count == 0
    assert requeued.requeue_count == 1
    assert requeued.result_json["previous_terminal"]["terminal"] == "EXHAUSTED"


def test_recovery_candidates_take_initial_and_backfill_quotas():
    db = _session()
    crud = CustomerEnrichmentJobCRUD()
    now = datetime(2026, 9, 20, 10, 0, 0)
    for customer_id in range(1, 31):
        _ensure(crud, db, customer_id=customer_id, available_at=now)
    for customer_id in range(101, 111):
        _ensure(
            crud,
            db,
            customer_id=customer_id,
            purpose=CustomerEnrichmentPurpose.HISTORICAL_BACKFILL.value,
            available_at=now,
        )
    candidates = crud.list_system_recovery_candidates(
        db,
        initial_limit=20,
        backfill_limit=5,
        now=now,
    )
    assert len(candidates) == 25
    assert sum(item.purpose == CustomerEnrichmentPurpose.INITIAL_CREATION.value for item in candidates) == 20
    assert sum(item.purpose == CustomerEnrichmentPurpose.HISTORICAL_BACKFILL.value for item in candidates) == 5
```

- [ ] **Step 2: Run RED**

Run: `cd CRM-Server && PYTHONPATH=. ./venv/bin/pytest tests/unit/test_customer_enrichment_job.py -q --no-cov`

Expected: FAIL because CRUD module is missing.

- [ ] **Step 3: Implement CRUD with exact public signatures**

Create `CRM-Server/app/crud/customer_enrichment_job.py` with:

```python
class CustomerEnrichmentJobCRUD:
    def ensure(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        purpose: str,
        plan_version: str,
        requested_fields: list[str],
        available_at: datetime,
        profile_gate_deadline_at: datetime | None,
        max_attempts: int,
        commit: bool = True,
    ) -> CustomerEnrichmentJob:
        # Lookup unique identity first; otherwise insert inside begin_nested().
        # On IntegrityError, reload and return the winner. Never reset existing lifecycle.

    def get_by_identity(
        self, db: Session, *, team_id: int, customer_id: int, plan_version: str,
    ) -> CustomerEnrichmentJob | None:
        # one_or_none() by tenant/customer/plan

    def get_by_public_id(
        self, db: Session, *, team_id: int, public_id: str, for_update: bool = False,
    ) -> CustomerEnrichmentJob | None:
        # tenant-scoped query; populate_existing().with_for_update() when requested

    def claim_for_execution(
        self,
        db: Session,
        *,
        team_id: int,
        public_id: str,
        lease_token: str,
        lease_expires_at: datetime,
        now: datetime | None = None,
        commit: bool = True,
    ) -> CustomerEnrichmentJob | None:
        # QUEUED requires available_at <= now; RETRY_PENDING requires next_attempt_at <= now;
        # RUNNING requires expired/missing lease. Terminal/attempt-exhausted returns None.
        # Successful claim increments attempt exactly once and clears prior error/retry fields.

    def mark_completed_if_lease_owner(
        self,
        db: Session,
        *,
        team_id: int,
        public_id: str,
        lease_token: str,
        result_json: dict[str, object],
        skipped: bool = False,
        now: datetime | None = None,
        commit: bool = True,
    ) -> CustomerEnrichmentJob | None:
        # Only RUNNING row with matching lease. Set COMPLETED/SKIPPED, terminal timestamps,
        # clear lease/retry, and set first_attempt_finished_at if null.

    def mark_retry_pending_if_lease_owner(
        self,
        db: Session,
        *,
        team_id: int,
        public_id: str,
        lease_token: str,
        error_message: str,
        next_attempt_at: datetime,
        result_json: dict[str, object],
        now: datetime | None = None,
        commit: bool = True,
    ) -> CustomerEnrichmentJob | None:
        # Matching RUNNING lease → RETRY_PENDING; clear lease; set first attempt timestamp if null.

    def mark_exhausted_if_lease_owner(
        self,
        db: Session,
        *,
        team_id: int,
        public_id: str,
        lease_token: str,
        error_message: str,
        result_json: dict[str, object],
        now: datetime | None = None,
        commit: bool = True,
    ) -> CustomerEnrichmentJob | None:
        # Matching RUNNING lease → EXHAUSTED; terminal timestamps; clear lease/retry.

    def requeue_exhausted(
        self,
        db: Session,
        *,
        team_id: int,
        public_id: str,
        available_at: datetime,
        now: datetime | None = None,
        commit: bool = True,
    ) -> CustomerEnrichmentJob | None:
        # Lock tenant row; require EXHAUSTED. Preserve old result under previous_terminal,
        # reset status/attempt/lease/error/start/finish/first_attempt/profile receipt,
        # increment requeue_count, and keep the same id/public_id.

    def list_system_recovery_candidates(
        self,
        db: Session,
        *,
        initial_limit: int,
        backfill_limit: int,
        now: datetime | None = None,
    ) -> list[CustomerEnrichmentJobRecoveryCandidate]:
        # Run the same recoverable predicate separately per purpose, order available/retry/created/id,
        # and concatenate INITIAL then HISTORICAL candidates.
```

Define module constants `_TERMINAL` and `_RECOVERABLE` explicitly. Use `business_now()`, clamp attempts to `max_attempts`, and follow the existing nested-transaction `IntegrityError` recovery pattern. No method may mutate a terminal row except `requeue_exhausted`.

- [ ] **Step 4: Run GREEN**

Run: `cd CRM-Server && PYTHONPATH=. ./venv/bin/pytest tests/unit/test_customer_enrichment_job.py -q --no-cov`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/crud/customer_enrichment_job.py CRM-Server/tests/unit/test_customer_enrichment_job.py
git commit -m "feat(customer): add enrichment job lifecycle"
```

---
### Task 3: Versioned plan, field registry, bounded context, and LLM inference

**Files:**
- Create: `CRM-Server/app/services/customer_enrichment_plan.py`
- Create: `CRM-Server/app/services/customer_enrichment_context_service.py`
- Create: `CRM-Server/app/services/customer_enrichment_inference_service.py`
- Create: `CRM-Server/tests/unit/test_customer_enrichment_inference_service.py`

**Interfaces:**
- Produces frozen `CustomerEnrichmentPlan` and `ACTIVE_CUSTOMER_ENRICHMENT_PLAN`.
- Produces `CustomerEnrichmentFieldRegistry.get(field)`, `catalogs(db, team_id, fields)`, and `validate(decisions, requested_fields, catalogs)`.
- Produces `CustomerEnrichmentContextService.build(db, team_id, customer_id, fields) -> dict[str, object]`.
- Produces `CustomerEnrichmentInferenceService.infer(db, team_id, context, requested_fields) -> CustomerEnrichmentInferenceResult`.

- [ ] **Step 1: Write the failing plan/context/inference tests**

Create `CRM-Server/tests/unit/test_customer_enrichment_inference_service.py`:

```python
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.customer_enrichment_contracts import (
    CustomerEnrichmentDecision,
    CustomerEnrichmentInferenceResult,
)
from app.services.customer_enrichment_context_service import CustomerEnrichmentContextService
from app.services.customer_enrichment_inference_service import (
    CustomerEnrichmentInferenceError,
    CustomerEnrichmentInferenceService,
)
from app.services.customer_enrichment_plan import (
    ACTIVE_CUSTOMER_ENRICHMENT_PLAN,
    CustomerEnrichmentFieldRegistry,
)


class _Query:
    def __init__(self, rows):
        self.rows = list(rows)
    def options(self, *args):
        return self
    def filter(self, *args):
        return self
    def order_by(self, *args):
        return self
    def limit(self, value):
        self.rows = self.rows[:value]
        return self
    def first(self):
        return self.rows[0] if self.rows else None
    def all(self):
        return list(self.rows)


class _ContextDb:
    def __init__(self):
        self.customer = SimpleNamespace(
            id=101,
            team_id=2,
            account_name="星云研发科技",
            city="上海",
            company_scale="51-200人",
            source="线上注册",
            version=4,
            source_lead_id=None,
            product_links=[SimpleNamespace(product=SimpleNamespace(public_id="prd_hifox", name="Hifox"))],
        )
        self.contact = SimpleNamespace(
            customer_id=101, team_id=2, is_primary=1,
            name="张三", mobile="13800138000", email="secret@example.com", position="研发负责人",
        )
        self.activities = [
            SimpleNamespace(
                customer_id=101,
                team_id=2,
                activity_kind="电话",
                source_content=("客户主营软件研发和 AI Coding。" * 40) + str(index),
                summary=None,
                occurred_at=index,
                id=index,
            )
            for index in range(7)
        ]
    def query(self, model):
        name = getattr(model, "__name__", "")
        if name == "Customer":
            return _Query([self.customer])
        if name == "Contact":
            return _Query([self.contact])
        if name == "CustomerActivity":
            return _Query(list(reversed(self.activities)))
        return _Query([])


class _Runtime:
    def __init__(self, result):
        self.result = result
        self.calls = []
    async def ainvoke_structured(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def _industries():
    primary = SimpleNamespace(code="internet", name="互联网", level=1, parent=None, is_active=1)
    secondary = SimpleNamespace(
        code="internet_saas",
        name="SaaS公司",
        level=2,
        parent=primary,
        is_active=1,
    )
    other = SimpleNamespace(code="other", name="其他", level=1, parent=None, is_active=1)
    return [primary, secondary, other]


def test_active_plan_is_frozen_and_versioned():
    assert ACTIVE_CUSTOMER_ENRICHMENT_PLAN.version == "customer-initial-v1"
    assert ACTIVE_CUSTOMER_ENRICHMENT_PLAN.fields == ("industry",)
    assert ACTIVE_CUSTOMER_ENRICHMENT_PLAN.backfill_enabled is True
    with pytest.raises(Exception):
        ACTIVE_CUSTOMER_ENRICHMENT_PLAN.version = "changed"


def test_context_is_bounded_and_does_not_include_contact_pii(monkeypatch):
    monkeypatch.setattr(
        "app.services.customer_enrichment_context_service.industry_crud.get_all_active",
        lambda db: _industries(),
    )
    payload = CustomerEnrichmentContextService().build(
        _ContextDb(), team_id=2, customer_id=101, fields=("industry",)
    )
    assert payload["customer"] == {
        "account_name": "星云研发科技",
        "city": "上海",
        "company_scale": "51-200人",
        "source": "线上注册",
        "version": 4,
    }
    assert payload["products"] == [{"public_id": "prd_hifox", "name": "Hifox"}]
    assert payload["primary_contact"] == {"position": "研发负责人"}
    assert len(payload["recent_activities"]) == 5
    assert all(len(item["text"]) <= 500 for item in payload["recent_activities"])
    serialized = str(payload)
    assert "张三" not in serialized
    assert "13800138000" not in serialized
    assert "secret@example.com" not in serialized
    catalog = payload["catalogs"]["industry"]
    assert {item["code"] for item in catalog} == {"internet", "internet_saas", "other"}
    saas = next(item for item in catalog if item["code"] == "internet_saas")
    assert saas["parent_code"] == "internet"
    assert saas["parent_name"] == "互联网"


@pytest.mark.asyncio
async def test_inference_calls_structured_runtime_once_and_validates_code(monkeypatch):
    runtime = _Runtime(
        CustomerEnrichmentInferenceResult(
            decisions=[
                CustomerEnrichmentDecision(
                    field="industry",
                    value="internet_saas",
                    reason="客户主营软件研发",
                )
            ]
        )
    )
    monkeypatch.setattr(
        "app.services.customer_enrichment_inference_service.ai_config_crud.get_config",
        lambda db, team_id: SimpleNamespace(api_host="https://ai", model_name="model", temperature=0.7),
    )
    monkeypatch.setattr(
        "app.services.customer_enrichment_inference_service.ai_config_crud.get_decrypted_api_key",
        lambda db, team_id: "key",
    )
    service = CustomerEnrichmentInferenceService(runtime=runtime)
    context = {"catalogs": {"industry": [
        {"code": "internet_saas", "name": "SaaS公司", "level": 2, "parent_code": "internet", "parent_name": "互联网"},
        {"code": "other", "name": "其他", "level": 1, "parent_code": None, "parent_name": None},
    ]}}
    result = await service.infer(object(), team_id=2, context=context, requested_fields=("industry",))
    assert result.decisions[0].value == "internet_saas"
    assert len(runtime.calls) == 1
    assert runtime.calls[0]["structured_output_strategy"] == "tool"
    assert runtime.calls[0]["temperature"] == 0.1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        CustomerEnrichmentInferenceResult(decisions=[CustomerEnrichmentDecision(field="unknown", value="x", reason="x")]),
        CustomerEnrichmentInferenceResult(decisions=[
            CustomerEnrichmentDecision(field="industry", value="other", reason="x"),
            CustomerEnrichmentDecision(field="industry", value="internet_saas", reason="y"),
        ]),
        CustomerEnrichmentInferenceResult(decisions=[CustomerEnrichmentDecision(field="industry", value="missing", reason="x")]),
    ],
)
async def test_inference_rejects_unknown_duplicate_or_invalid_decisions(monkeypatch, result):
    monkeypatch.setattr(
        "app.services.customer_enrichment_inference_service.ai_config_crud.get_config",
        lambda db, team_id: SimpleNamespace(api_host="https://ai", model_name="model", temperature=0.1),
    )
    monkeypatch.setattr(
        "app.services.customer_enrichment_inference_service.ai_config_crud.get_decrypted_api_key",
        lambda db, team_id: "key",
    )
    service = CustomerEnrichmentInferenceService(runtime=_Runtime(result))
    context = {"catalogs": {"industry": [
        {"code": "internet_saas", "name": "SaaS公司", "level": 2, "parent_code": "internet", "parent_name": "互联网"},
        {"code": "other", "name": "其他", "level": 1, "parent_code": None, "parent_name": None},
    ]}}
    with pytest.raises(CustomerEnrichmentInferenceError):
        await service.infer(object(), team_id=2, context=context, requested_fields=("industry",))


@pytest.mark.asyncio
async def test_missing_ai_config_is_retryable_and_never_returns_other(monkeypatch):
    monkeypatch.setattr(
        "app.services.customer_enrichment_inference_service.ai_config_crud.get_config",
        lambda db, team_id: None,
    )
    service = CustomerEnrichmentInferenceService(runtime=_Runtime(None))
    with pytest.raises(CustomerEnrichmentInferenceError) as exc:
        await service.infer(
            object(),
            team_id=2,
            context={"catalogs": {"industry": []}},
            requested_fields=("industry",),
        )
    assert exc.value.retryable is True
```

- [ ] **Step 2: Run RED**

Run: `cd CRM-Server && PYTHONPATH=. ./venv/bin/pytest tests/unit/test_customer_enrichment_inference_service.py -q --no-cov`

Expected: FAIL because modules do not exist.

- [ ] **Step 3: Implement plan and registry**

Create `customer_enrichment_plan.py` with frozen `CustomerEnrichmentPlan`, `IndustryEnrichmentField.catalog(db)`, `validate(value, catalog)`, and registry methods:

```python
@dataclass(frozen=True)
class CustomerEnrichmentPlan:
    version: str
    fields: tuple[str, ...]
    backfill_enabled: bool


ACTIVE_CUSTOMER_ENRICHMENT_PLAN = CustomerEnrichmentPlan(
    version="customer-initial-v1",
    fields=("industry",),
    backfill_enabled=True,
)


class CustomerEnrichmentFieldRegistry:
    def __init__(self, handlers=None) -> None:
        values = handlers or (IndustryEnrichmentField(),)
        self._handlers = {item.field_key: item for item in values}

    def get(self, field_key: str):
        try:
            return self._handlers[field_key]
        except KeyError as exc:
            raise CustomerEnrichmentInferenceError(f"未注册的客户补全字段: {field_key}") from exc

    def catalogs(self, db, fields: tuple[str, ...]) -> dict[str, list[dict[str, object]]]:
        return {field: self.get(field).catalog(db) for field in fields}

    def validate(self, decisions, requested_fields, catalogs):
        requested = tuple(requested_fields)
        if len(decisions) != len(requested) or {item.field for item in decisions} != set(requested):
            raise CustomerEnrichmentInferenceError("客户补全结果必须逐字段完整返回")
        if len({item.field for item in decisions}) != len(decisions):
            raise CustomerEnrichmentInferenceError("客户补全结果字段重复")
        for decision in decisions:
            self.get(decision.field).validate(decision.value, catalogs[decision.field])
        return tuple(decisions)
```

`IndustryEnrichmentField.catalog` must return active rows with `code/name/level/parent_code/parent_name`; `validate` requires exact code membership and requires active `other` when value is `other`.

- [ ] **Step 4: Implement bounded context**

`CustomerEnrichmentContextService.build` performs tenant-scoped queries for Customer, primary Contact, latest five CustomerActivity rows, and optional source Lead/LeadFollowUp. It returns exactly the keys asserted in the test, uses `product_intent_payload(customer.product_links)`, and truncates each selected activity/follow-up text with `text[:500]`. Raise `CustomerEnrichmentInferenceError("客户不存在")` when the customer is absent.

- [ ] **Step 5: Implement one structured-output call**

Create `CustomerEnrichmentInferenceError(message, retryable=True)`. `infer` loads AI config/key, builds the catalogs from `context["catalogs"]`, invokes `AgentLangChainRuntime.ainvoke_structured` exactly once, then delegates exact-set and code validation to the registry. If config/key is missing, runtime returns `None`, or structured output raises, wrap as retryable error. The prompt must state: every requested field appears once; industry chooses a provided code; inability to classify returns `other`; never include confidence or unregistered fields.

- [ ] **Step 6: Run GREEN**

Run: `cd CRM-Server && PYTHONPATH=. ./venv/bin/pytest tests/unit/test_customer_enrichment_inference_service.py -q --no-cov`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add CRM-Server/app/services/customer_enrichment_plan.py CRM-Server/app/services/customer_enrichment_context_service.py CRM-Server/app/services/customer_enrichment_inference_service.py CRM-Server/tests/unit/test_customer_enrichment_inference_service.py
git commit -m "feat(customer): infer initial enrichment fields"
```

---
### Task 4: Atomic conditional customer enrichment write

**Files:**
- Create: `CRM-Server/app/services/customer_enrichment_write_service.py`
- Create: `CRM-Server/tests/unit/test_customer_enrichment_write_service.py`

**Interfaces:**
- Produces enum-like outcomes `APPLIED`, `SKIPPED`, `RETRY` and frozen `CustomerEnrichmentWriteResult`.
- Produces `CustomerEnrichmentWriteService.apply(db, *, team_id, customer_id, expected_version, decisions, plan_version, job_public_id) -> CustomerEnrichmentWriteResult`.
- Field registry provides `get(field).customer_column`, `validate(value, catalog)`, and write-time `catalog(db)`.

- [ ] **Step 1: Write the failing write-service tests**

Create SQLite tests with `Customer`, `Industry`, and `OperationLog` tables. Use a real `CustomerEnrichmentFieldRegistry` for industry. Add:

```python
def test_apply_sets_null_industry_and_logs_once():
    db, customer = _seed_customer(industry=None, version=4)
    result = _service().apply(
        db,
        team_id=2,
        customer_id=customer.id,
        expected_version=4,
        decisions=(CustomerEnrichmentDecision(field="industry", value="internet_saas", reason="软件研发"),),
        plan_version="customer-initial-v1",
        job_public_id="cej_1",
    )
    db.refresh(customer)
    assert result.outcome == "APPLIED"
    assert result.applied_fields == ("industry",)
    assert customer.industry == "internet_saas"
    assert customer.version == 5
    log = db.query(OperationLog).one()
    assert log.event_type == EventTypes.CUSTOMER_UPDATED
    assert log.content["source"] == "CUSTOMER_INITIAL_ENRICHMENT"
    assert log.content["job_public_id"] == "cej_1"


def test_apply_does_not_overwrite_existing_industry():
    db, customer = _seed_customer(industry="finance", version=4)
    result = _service().apply(
        db,
        team_id=2,
        customer_id=customer.id,
        expected_version=4,
        decisions=(CustomerEnrichmentDecision(field="industry", value="internet_saas", reason="软件研发"),),
        plan_version="customer-initial-v1",
        job_public_id="cej_1",
    )
    assert result.outcome == "SKIPPED"
    assert result.reason == "FIELD_ALREADY_FILLED"
    assert db.query(OperationLog).count() == 0


def test_apply_retries_when_customer_version_changed_but_field_still_null():
    db, customer = _seed_customer(industry=None, version=5)
    result = _service().apply(
        db,
        team_id=2,
        customer_id=customer.id,
        expected_version=4,
        decisions=(CustomerEnrichmentDecision(field="industry", value="internet_saas", reason="软件研发"),),
        plan_version="customer-initial-v1",
        job_public_id="cej_1",
    )
    assert result.outcome == "RETRY"
    assert result.reason == "CUSTOMER_CHANGED_DURING_ENRICHMENT"
    assert customer.industry is None


def test_apply_revalidates_active_industry_before_write():
    db, customer = _seed_customer(industry=None, version=4, active_saas=False)
    with pytest.raises(CustomerEnrichmentWriteError):
        _service().apply(
            db,
            team_id=2,
            customer_id=customer.id,
            expected_version=4,
            decisions=(CustomerEnrichmentDecision(field="industry", value="internet_saas", reason="软件研发"),),
            plan_version="customer-initial-v1",
            job_public_id="cej_1",
        )
    assert customer.industry is None


def test_apply_rolls_back_when_operation_log_fails(monkeypatch):
    db, customer = _seed_customer(industry=None, version=4)
    monkeypatch.setattr(
        "app.services.customer_enrichment_write_service.operation_log_service.log",
        lambda **kwargs: None,
    )
    with pytest.raises(CustomerEnrichmentWriteError):
        _service().apply(
            db,
            team_id=2,
            customer_id=customer.id,
            expected_version=4,
            decisions=(CustomerEnrichmentDecision(field="industry", value="internet_saas", reason="软件研发"),),
            plan_version="customer-initial-v1",
            job_public_id="cej_1",
        )
    db.expire_all()
    assert db.get(Customer, customer.id).industry is None


def test_future_multi_field_plan_is_all_or_nothing():
    registry = _registry_with_industry_and_address()
    db, customer = _seed_customer(industry=None, address=None, version=4)
    service = CustomerEnrichmentWriteService(field_registry=registry)
    result = service.apply(
        db,
        team_id=2,
        customer_id=customer.id,
        expected_version=4,
        decisions=(
            CustomerEnrichmentDecision(field="industry", value="internet_saas", reason="软件研发"),
            CustomerEnrichmentDecision(field="address", value="上海市", reason="明确地址"),
        ),
        plan_version="test-v2",
        job_public_id="cej_2",
    )
    db.refresh(customer)
    assert result.outcome == "APPLIED"
    assert customer.industry == "internet_saas"
    assert customer.address == "上海市"
    assert customer.version == 5

    db2, customer2 = _seed_customer(industry=None, address=None, version=4)
    with pytest.raises(CustomerEnrichmentWriteError):
        service.apply(
            db2,
            team_id=2,
            customer_id=customer2.id,
            expected_version=4,
            decisions=(
                CustomerEnrichmentDecision(field="industry", value="missing", reason="非法"),
                CustomerEnrichmentDecision(field="address", value="上海市", reason="明确地址"),
            ),
            plan_version="test-v2",
            job_public_id="cej_3",
        )
    assert customer2.industry is None and customer2.address is None and customer2.version == 4
```

The helper `_seed_customer` must commit a tenant-scoped Customer, primary active `internet`/`internet_saas` and `other` industries, and return `(db, customer)`. `_registry_with_industry_and_address` adds a test-only handler whose `customer_column = Customer.address`, catalog is empty, and validation requires nonblank text.

- [ ] **Step 2: Run RED**

Run: `cd CRM-Server && PYTHONPATH=. ./venv/bin/pytest tests/unit/test_customer_enrichment_write_service.py -q --no-cov`

Expected: FAIL because service is missing.

- [ ] **Step 3: Implement conditional write with this contract**

```python
@dataclass(frozen=True)
class CustomerEnrichmentWriteResult:
    outcome: Literal["APPLIED", "SKIPPED", "RETRY"]
    applied_fields: tuple[str, ...] = ()
    customer_version: int | None = None
    reason: str | None = None

class CustomerEnrichmentWriteError(RuntimeError):
    """Validated enrichment decisions could not be applied safely."""
```


`CustomerEnrichmentWriteService` has this exact public signature:

```text
__init__(*, field_registry: CustomerEnrichmentFieldRegistry | None = None,
         log_service: OperationLogService | None = None)

apply(db: Session, *, team_id: int, customer_id: int, expected_version: int,
      decisions: tuple[CustomerEnrichmentDecision, ...], plan_version: str,
      job_public_id: str) -> CustomerEnrichmentWriteResult
```

Inside `apply`: validate every decision and build one `values` dict before any write; execute one `sqlalchemy.update(Customer)` with tenant/id/version and every target column `IS NULL`; set `version=Customer.version + 1` and `last_modified_time=business_now()`. If `rowcount == 0`, reload tenant-scoped customer and return SKIPPED when any target is filled, otherwise RETRY. After a successful update, write one operation log with `commit=False`; if logging returns None, raise so the surrounding transaction rolls back. Commit and return the new version.

Log content is exactly:

```python
{
    "changed_fields": applied_fields,
    "before": {field: None for field in applied_fields},
    "after": applied_values,
    "source": "CUSTOMER_INITIAL_ENRICHMENT",
    "plan_version": plan_version,
    "job_public_id": job_public_id,
}
```

Use `operator_id="system"`, `operator_name="系统"`, `EventTypes.CUSTOMER_UPDATED`, `EventActions.UPDATE`, `ResourceTypes.CUSTOMER`.

- [ ] **Step 4: Run GREEN**

Run: `cd CRM-Server && PYTHONPATH=. ./venv/bin/pytest tests/unit/test_customer_enrichment_write_service.py -q --no-cov`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/customer_enrichment_write_service.py CRM-Server/tests/unit/test_customer_enrichment_write_service.py
git commit -m "feat(customer): apply enrichment fields atomically"
```

---
### Task 5: Initial-enrichment Graph and durable execution service

**Files:**
- Create: `CRM-Server/app/services/agent/customer_initial_enrichment_graph.py`
- Create: `CRM-Server/app/services/agent/customer_initial_enrichment_workflow.py`
- Create: `CRM-Server/app/services/customer_enrichment_job_service.py`
- Create: `CRM-Server/tests/unit/test_customer_initial_enrichment_graph.py`
- Create: `CRM-Server/tests/unit/test_customer_enrichment_job_service.py`

**Interfaces:**
- `CustomerInitialEnrichmentRequest(team_id, customer_id, plan_version, requested_fields, run_id, thread_id)`.
- `CustomerInitialEnrichmentResult(customer_id, expected_version, decisions=(), skip_reason=None)`.
- `CustomerEnrichmentCompletionPort.on_first_attempt_finished(job)` and `on_terminal_success(job, result)` are sync best-effort callbacks.
- `CustomerEnrichmentJobService.run(CustomerEnrichmentJobRequest) -> CustomerEnrichmentRunResult`.
- `CustomerEnrichmentJobService.__init__(*, job_crud=None, workflow=None, write_service=None, completion_port, session_factory=SessionLocal)` is dependency-injectable for tests and smoke verification.

- [ ] **Step 1: Write RED graph tests**

Create `test_customer_initial_enrichment_graph.py` with injected fake context/inference services:

```python
@pytest.mark.asyncio
async def test_graph_skips_without_calling_inference_when_no_fields_missing():
    context = FakeContextService(payload={"customer": {"version": 4, "industry": "finance"}})
    inference = FakeInferenceService()
    graph = CustomerInitialEnrichmentGraphService(
        context_service=context,
        inference_service=inference,
        checkpointer=InMemorySaver(),
    )
    result = await graph.run(
        CustomerInitialEnrichmentRequest(
            team_id=2,
            customer_id=101,
            plan_version="customer-initial-v1",
            requested_fields=("industry",),
            run_id="run-1",
            thread_id="customer-enrichment:2:101:customer-initial-v1",
        )
    )
    assert result.skip_reason == "NO_MISSING_FIELDS"
    assert result.expected_version == 4
    assert inference.calls == []


@pytest.mark.asyncio
async def test_graph_returns_validated_decisions_for_missing_industry():
    decision = CustomerEnrichmentDecision(field="industry", value="internet_saas", reason="软件研发")
    context = FakeContextService(payload={"customer": {"version": 4, "industry": None}})
    inference = FakeInferenceService(result=CustomerEnrichmentInferenceResult(decisions=[decision]))
    graph = CustomerInitialEnrichmentGraphService(
        context_service=context,
        inference_service=inference,
        checkpointer=InMemorySaver(),
    )
    result = await graph.run(_request())
    assert result.expected_version == 4
    assert result.decisions == (decision,)
    assert inference.calls[0]["requested_fields"] == ("industry",)
```

The graph implementation must declare and wire exactly:

```text
START → load_context → collect_missing_fields
collect_missing_fields → END (no missing) | infer_fields
infer_fields → validate_decisions → END
```

- [ ] **Step 2: Write RED job-service tests**

Create fake collaborators that record calls. Tests:

```python
@pytest.mark.asyncio
async def test_terminal_job_returns_persisted_result_without_compute():
    crud = FakeJobCrud(existing=_job(status="COMPLETED", result_json={"execution_status": "COMPLETED", "success": True}))
    service = _service(crud=crud)
    result = await service.run(_job_request())
    assert result.execution_status == "COMPLETED"
    assert service.workflow.calls == []


@pytest.mark.asyncio
async def test_busy_job_does_not_compute():
    crud = FakeJobCrud(existing=_job(status="QUEUED"), claimed=None)
    service = _service(crud=crud)
    result = await service.run(_job_request())
    assert result.execution_status == "BUSY"
    assert service.workflow.calls == []


@pytest.mark.asyncio
async def test_success_completes_job_and_calls_completion_port_in_order():
    service = _service(
        workflow_result=CustomerInitialEnrichmentResult(
            customer_id=101,
            expected_version=4,
            decisions=(CustomerEnrichmentDecision(field="industry", value="internet_saas", reason="软件研发"),),
        ),
        write_result=CustomerEnrichmentWriteResult(
            outcome="APPLIED", applied_fields=("industry",), customer_version=5
        ),
    )
    result = await service.run(_job_request())
    assert result.execution_status == "COMPLETED"
    assert result.applied_fields == ["industry"]
    assert service.completion_port.calls == ["first_attempt", "terminal_success"]


@pytest.mark.asyncio
async def test_first_failure_retries_and_releases_profile_gate():
    service = _service(workflow_error=CustomerEnrichmentInferenceError("timeout"), attempt_count=1)
    result = await service.run(_job_request())
    assert result.execution_status == "RETRY_PENDING"
    assert result.retryable is True
    assert service.completion_port.calls == ["first_attempt"]
    assert service.crud.retry_next_attempt_at_delta == timedelta(seconds=60)


@pytest.mark.asyncio
async def test_third_failure_exhausts():
    service = _service(workflow_error=CustomerEnrichmentInferenceError("timeout"), attempt_count=3)
    result = await service.run(_job_request())
    assert result.execution_status == "EXHAUSTED"
    assert result.retryable is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("write_result", "expected_status"),
    [
        (CustomerEnrichmentWriteResult(outcome="SKIPPED", reason="FIELD_ALREADY_FILLED"), "SKIPPED"),
        (CustomerEnrichmentWriteResult(outcome="RETRY", reason="CUSTOMER_CHANGED_DURING_ENRICHMENT"), "RETRY_PENDING"),
    ],
)
async def test_write_outcome_controls_terminal_state(write_result, expected_status):
    service = _service(workflow_result=_decision_result(), write_result=write_result)
    result = await service.run(_job_request())
    assert result.execution_status == expected_status


@pytest.mark.asyncio
async def test_stale_lease_cannot_finalize():
    service = _service(workflow_result=_decision_result(), mark_completed_result=None)
    result = await service.run(_job_request())
    assert result.execution_status == "BUSY"
    assert result.success is False
```

Fake CRUD must expose the same signatures from Task 2; fake workflow exposes `run(request)`; fake write service exposes `apply`; fake completion port records order.

- [ ] **Step 3: Run RED**

Run:

```text
cd CRM-Server && PYTHONPATH=. ./venv/bin/pytest tests/unit/test_customer_initial_enrichment_graph.py tests/unit/test_customer_enrichment_job_service.py -q --no-cov
```

Expected: FAIL because graph/service modules are missing.

- [ ] **Step 4: Implement pure compute Graph and runner seam**

Use Pydantic frozen request/result and a JSON-safe TypedDict state. `run()` compiles/executes LangGraph using config thread id from the request and returns the typed final result. It computes missing fields by consulting the active plan handlers against `context["customer"]`; it never opens a write transaction or mutates job rows.

`customer_initial_enrichment_workflow.py` mirrors the profile workflow runner with a `run(request)` method around the graph service.

- [ ] **Step 5: Implement durable job service**

Create:

```python
class CustomerEnrichmentCompletionPort(Protocol):
    def on_first_attempt_finished(self, job: CustomerEnrichmentJob) -> None:
        """Release the first-profile gate after the first real attempt."""

    def on_terminal_success(
        self, job: CustomerEnrichmentJob, result: CustomerEnrichmentRunResult
    ) -> None:
        """Release or enqueue exactly one profile refresh after terminal success."""


def build_customer_enrichment_job_service(completion_port):
    return CustomerEnrichmentJobService(completion_port=completion_port)
```

`run()` follows this exact transaction sequence:

1. session A: load existing; return persisted terminal result; finalize already-exhausted; attempt lease claim; load claimed job snapshot; commit; close;
2. run workflow outside DB under `ai_generation_semaphore`;
3. session B: call write service, then matching lease-owned completed/skipped/retry mutation and commit;
4. technical exception: session B marks RETRY_PENDING with 60 seconds after attempt 1, 300 seconds after attempt 2, EXHAUSTED at attempt 3;
5. after the DB mutation, call `on_first_attempt_finished` only when the mutation first sets `first_attempt_finished_at`; call `on_terminal_success` only for COMPLETED/SKIPPED; catch/log callback errors without changing job state;
6. stale lease mutation returning None yields BUSY and never calls completion port;
7. `kick(request)` schedules guarded `run()` only when an event loop exists.

Do not create the production singleton until Task 6 supplies the concrete completion port.

- [ ] **Step 6: Run GREEN**

Run the Step 3 command.

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add CRM-Server/app/services/agent/customer_initial_enrichment_graph.py CRM-Server/app/services/agent/customer_initial_enrichment_workflow.py CRM-Server/app/services/customer_enrichment_job_service.py CRM-Server/tests/unit/test_customer_initial_enrichment_graph.py CRM-Server/tests/unit/test_customer_enrichment_job_service.py
git commit -m "feat(customer): run durable initial enrichment workflow"
```

---
### Task 6: Profile readiness gate and enrichment/profile coordination

**Files:**
- Create: `CRM-Server/app/services/customer_profile_readiness_gate.py`
- Create: `CRM-Server/app/services/customer_enrichment_profile_coordinator.py`
- Create: `CRM-Server/tests/unit/test_customer_profile_readiness_gate.py`
- Modify: `CRM-Server/app/services/customer_intelligence_run_service.py`
- Modify: `CRM-Server/app/services/customer_intelligence_refresh_service.py`
- Modify: `CRM-Server/tests/unit/test_customer_intelligence_run_service.py`
- Modify: `CRM-Server/tests/unit/test_customer_intelligence_refresh_service.py`
- Modify: `CRM-Server/app/services/customer_enrichment_job_service.py`

**Interfaces:**
- `CustomerProfileReadinessGate.defer_if_needed(db, *, event, run, now) -> datetime | None`.
- `CustomerIntelligenceRunService.defer_until(db, *, team_id, run_id, not_before_at)` and `release_deferred_for_customer(db, *, team_id, customer_id)`.
- `CustomerEnrichmentProfileCoordinator` implements Task 5 completion port.

- [ ] **Step 1: Add concrete RED run-service tests**

Append to `test_customer_intelligence_run_service.py`:

```python
def test_future_not_before_is_not_due_or_claimable():
    db = _session()
    now = datetime(2026, 9, 20, 10, 0, 0)
    run_input = _input()
    run = customer_intelligence_run_service.ensure_pending(db, run_input)
    customer_intelligence_run_service.defer_until(
        db, team_id=2, run_id=run.id, not_before_at=now + timedelta(seconds=20)
    )
    assert customer_intelligence_run_service.list_due(db, now=now, team_id=2) == []
    claim = customer_intelligence_run_service.claim_for_execution(db, run_input, now=now)
    assert claim.status == CustomerIntelligenceRunClaimStatus.BUSY
    assert claim.run.attempt_count == 0


def test_not_before_past_is_claimable():
    db = _session()
    now = datetime(2026, 9, 20, 10, 0, 0)
    run_input = _input()
    run = customer_intelligence_run_service.ensure_pending(db, run_input)
    customer_intelligence_run_service.defer_until(
        db, team_id=2, run_id=run.id, not_before_at=now - timedelta(seconds=1)
    )
    claim = customer_intelligence_run_service.claim_for_execution(db, run_input, now=now)
    assert claim.status == CustomerIntelligenceRunClaimStatus.CLAIMED


def test_release_deferred_for_customer_is_tenant_scoped():
    db = _session()
    now = datetime(2026, 9, 20, 10, 0, 0)
    own = customer_intelligence_run_service.ensure_pending(db, _input(event_key="own", team_id=2, customer_id=101))
    other = customer_intelligence_run_service.ensure_pending(db, _input(event_key="other", team_id=3, customer_id=101))
    customer_intelligence_run_service.defer_until(db, team_id=2, run_id=own.id, not_before_at=now)
    customer_intelligence_run_service.defer_until(db, team_id=3, run_id=other.id, not_before_at=now)
    released = customer_intelligence_run_service.release_deferred_for_customer(
        db, team_id=2, customer_id=101
    )
    assert released == [own.id]
    assert db.get(CustomerIntelligenceRun, own.id).not_before_at is None
    assert db.get(CustomerIntelligenceRun, other.id).not_before_at == now
```

- [ ] **Step 2: Create RED gate and refresh tests**

Create `test_customer_profile_readiness_gate.py` with helpers `_now()`, `_event(trigger)`, `_job(...)`, and `_gate(job)`. `_event` returns a minimal `CustomerIntelligenceEvent` with team=tenant=2 and customer=101. `FakeRunService.defer_until` records `(team_id, run_id, not_before_at)`.

```python
def test_customer_created_event_is_gated():
    deadline = _now() + timedelta(seconds=30)
    gate = _gate(_job(
        purpose="INITIAL_CREATION",
        first_attempt_finished_at=None,
        profile_gate_deadline_at=deadline,
    ))
    deferred = gate.defer_if_needed(
        object(), event=_event("customer_created"), run=SimpleNamespace(id=7), now=_now()
    )
    assert deferred == _now() + timedelta(seconds=5)
    assert gate.run_service.defer_calls == [(2, 7, deferred)]


def test_customer_activity_created_event_is_gated():
    deadline = _now() + timedelta(seconds=30)
    gate = _gate(_job(
        purpose="INITIAL_CREATION",
        first_attempt_finished_at=None,
        profile_gate_deadline_at=deadline,
    ))
    assert gate.defer_if_needed(
        object(), event=_event("customer_activity_created"), run=SimpleNamespace(id=7), now=_now()
    ) == _now() + timedelta(seconds=5)


def test_historical_job_does_not_gate():
    gate = _gate(_job(
        purpose="HISTORICAL_BACKFILL",
        first_attempt_finished_at=None,
        profile_gate_deadline_at=None,
    ))
    assert gate.defer_if_needed(
        object(), event=_event("customer_created"), run=SimpleNamespace(id=7), now=_now()
    ) is None
    assert gate.run_service.defer_calls == []


def test_gate_deadline_passed_does_not_gate():
    gate = _gate(_job(
        purpose="INITIAL_CREATION",
        first_attempt_finished_at=None,
        profile_gate_deadline_at=_now() - timedelta(seconds=1),
    ))
    assert gate.defer_if_needed(
        object(), event=_event("customer_created"), run=SimpleNamespace(id=7), now=_now()
    ) is None
    assert gate.run_service.defer_calls == []


def test_missing_job_does_not_gate():
    gate = _gate(None)
    assert gate.defer_if_needed(
        object(), event=_event("customer_created"), run=SimpleNamespace(id=7), now=_now()
    ) is None
    assert gate.run_service.defer_calls == []
```

Add one focused async test to `test_customer_intelligence_refresh_service.py`: construct a service with readiness gate returning `_now()+5s`; monkeypatch `_claim_run` to raise `AssertionError`; call `_run_event_refresh` for a customer-created event; assert `scheduled/deferred` are true, `not_before_at` is returned, and the fake profile projection service has no `updating_calls`.

- [ ] **Step 3: Run RED**

Run:

```text
cd CRM-Server && PYTHONPATH=. ./venv/bin/pytest tests/unit/test_customer_intelligence_run_service.py tests/unit/test_customer_profile_readiness_gate.py tests/unit/test_customer_intelligence_refresh_service.py -q --no-cov
```

Expected: FAIL on missing not-before methods/gate.

- [ ] **Step 4: Implement persistent run deferral and gate**

`defer_until` locks tenant/run, only changes non-terminal runs, and sets the later of current/new `not_before_at`. `release_deferred_for_customer` locks all tenant/customer non-terminal rows whose `not_before_at` is non-null, clears it, flushes, and returns run ids. `claim_for_execution` returns BUSY before attempt checks when `not_before_at > now`. `list_due` filters future values.

`CustomerProfileReadinessGate` calls `CustomerEnrichmentJobCRUD.get_by_identity(db, team_id=event.team_id, customer_id=event.customer_id, plan_version=ACTIVE_CUSTOMER_ENRICHMENT_PLAN.version)`. Gate only when purpose INITIAL_CREATION, `first_attempt_finished_at is None`, and deadline future. It calls `defer_until` with `min(deadline, now + timedelta(seconds=5))`.

Inject the gate into `CustomerIntelligenceRefreshService`; in `_run_event_refresh`, build/find the persisted run, check the gate before `_claim_run`, and return:

```python
{
    "success": True,
    "scheduled": True,
    "deferred": True,
    "request_id": request_id,
    "event_key": event.event_key,
    "not_before_at": deferred.isoformat(),
}
```

- [ ] **Step 5: Implement profile coordinator**

`on_first_attempt_finished(job)` opens a short session, calls `release_deferred_for_customer`, commits, then best-effort invokes `run_due_retries(team_id=job.team_id, limit=max(1, len(released)))` only when an event loop exists.

`on_terminal_success(job, result)` locks the job. If a deferred profile run was released, persist `profile_refresh_request_id=f"released:{run_id}"`; otherwise create one customer business-object updated event with payload `change_origin=CUSTOMER_INITIAL_ENRICHMENT`, enqueue it after commit, and persist its request id/time. If receipt already exists, no-op. Callback errors are logged for reconciliation.

Wire `customer_enrichment_job_service = build_customer_enrichment_job_service(customer_enrichment_profile_coordinator)`.

- [ ] **Step 6: Run GREEN**

Run the Step 3 command plus `tests/unit/test_customer_enrichment_job_service.py`.

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add CRM-Server/app/services/customer_profile_readiness_gate.py CRM-Server/app/services/customer_enrichment_profile_coordinator.py CRM-Server/app/services/customer_intelligence_run_service.py CRM-Server/app/services/customer_intelligence_refresh_service.py CRM-Server/app/services/customer_enrichment_job_service.py CRM-Server/tests/unit/test_customer_profile_readiness_gate.py CRM-Server/tests/unit/test_customer_intelligence_run_service.py CRM-Server/tests/unit/test_customer_intelligence_refresh_service.py CRM-Server/tests/unit/test_customer_enrichment_job_service.py
git commit -m "feat(customer): gate initial profile on enrichment attempt"
```

---
### Task 7: Customer lifecycle coordinator and creation entrypoints

**Files:**
- Create: `CRM-Server/app/services/customer_lifecycle_post_commit_coordinator.py`
- Create: `CRM-Server/tests/unit/test_customer_lifecycle_post_commit_coordinator.py`
- Modify: `CRM-Server/app/services/customer_business_object_intelligence_service.py`
- Modify: `CRM-Server/app/api/customers.py`
- Modify: `CRM-Server/app/api/customer_ai.py`
- Modify: `CRM-Server/app/services/ai_parser/customer_parser.py`
- Modify: `CRM-Server/tests/unit/api/test_customer_edit_api.py`
- Modify: `CRM-Server/tests/unit/test_customers_customer_intelligence_api.py`

**Interfaces:**
- `CustomerLifecyclePostCommitWork(enrichment_request, profile_request, warnings)` frozen dataclass.
- `prepare_in_transaction(db, *, customer, actor_id, trigger_type, source_lead_id=None) -> CustomerLifecyclePostCommitWork`.
- `enqueue_after_commit(*, customer, actor_id, trigger_type, source_lead_id=None) -> CustomerLifecyclePostCommitWork`.
- `kick(work) -> tuple[str, ...]` returns warning strings; never raises.

- [ ] **Step 1: Write concrete coordinator RED tests**

Create `test_customer_lifecycle_post_commit_coordinator.py` with fake job service, business-object intelligence service, and profile refresh service. Tests:

```python
def test_prepare_registers_enrichment_and_profile_for_null_industry():
    coordinator, fakes = _coordinator()
    work = coordinator.prepare_in_transaction(
        object(),
        customer=_customer(industry=None),
        actor_id="9",
        trigger_type="customer_created",
    )
    assert work.enrichment_request.job_public_id == "cej_1"
    assert work.profile_request.request_id == "profile-1"
    assert fakes.job_service.ensure_calls[0]["purpose"] == "INITIAL_CREATION"
    assert fakes.intelligence.calls[0]["trigger_type"] == "customer_created"


def test_prepare_skips_enrichment_when_industry_already_filled():
    coordinator, fakes = _coordinator()
    work = coordinator.prepare_in_transaction(
        object(), customer=_customer(industry="finance"), actor_id="9", trigger_type="customer_created"
    )
    assert work.enrichment_request is None
    assert work.profile_request.request_id == "profile-1"
    assert fakes.job_service.ensure_calls == []


def test_prepare_isolates_job_registration_failure():
    coordinator, _ = _coordinator(job_error=RuntimeError("job store down"))
    work = coordinator.prepare_in_transaction(
        FakeDb(), customer=_customer(industry=None), actor_id="9", trigger_type="customer_created"
    )
    assert work.enrichment_request is None
    assert "job store down" in work.warnings[0]
    assert work.profile_request.request_id == "profile-1"


def test_repeated_prepare_reuses_same_job():
    coordinator, fakes = _coordinator()
    first = coordinator.prepare_in_transaction(object(), customer=_customer(industry=None), actor_id="9", trigger_type="customer_created")
    second = coordinator.prepare_in_transaction(object(), customer=_customer(industry=None), actor_id="9", trigger_type="customer_created")
    assert first.enrichment_request.job_public_id == second.enrichment_request.job_public_id
    assert len(fakes.job_service.ensure_calls) == 2


def test_kick_attempts_both_workers_and_returns_warnings():
    coordinator, fakes = _coordinator(enrichment_kick_error=RuntimeError("enrichment down"))
    warnings = coordinator.kick(_work_with_both_requests())
    assert fakes.profile_service.kick_calls == ["profile-1"]
    assert any("enrichment down" in item for item in warnings)
```

`FakeDb.begin_nested()` returns a context manager, so failure isolation is exercised without swallowing the profile registration.

- [ ] **Step 2: Write concrete entrypoint RED tests**

In `tests/unit/api/test_customer_edit_api.py`, extend the existing `create_customer` harness:

- monkeypatch `customer_lifecycle_post_commit_coordinator.prepare_in_transaction` to record before `db.commit`;
- monkeypatch `kick` to raise internally/return warning and assert the endpoint still returns the created CustomerResponse;
- assert no inference service is imported/called.

In `test_customers_customer_intelligence_api.py`, add two conversion tests using the existing direct-call pattern: legacy conversion calls `enqueue_after_commit` once; modern conversion calls `prepare_in_transaction` before commit and `kick` after commit. Both pass `source_lead_id` and trigger `customer_converted_from_lead`.

Add `test_customer_ai_submit_uses_lifecycle_coordinator` by monkeypatching parser `create_entity` and `post_create_actions`; assert coordinator `enqueue_after_commit` + `kick` once, and assert `post_create_actions` does not call `trigger_customer_created_refresh` after its implementation change.

- [ ] **Step 3: Run RED**

Run:

```text
cd CRM-Server && PYTHONPATH=. ./venv/bin/pytest tests/unit/test_customer_lifecycle_post_commit_coordinator.py tests/unit/api/test_customer_edit_api.py tests/unit/test_customers_customer_intelligence_api.py -q --no-cov
```

Expected: FAIL because Coordinator is missing and APIs use old after-commit calls.

- [ ] **Step 4: Add in-transaction lifecycle publication seam**

Add `enqueue_customer_lifecycle_refresh(db, *, customer, actor_id, trigger_type, source_lead_id=None, scope="full")` to `CustomerBusinessObjectIntelligenceService`. It builds the existing stable lifecycle event and calls `publication_service.persist_in_transaction_request`; it must not kick while the transaction is open.

- [ ] **Step 5: Implement Coordinator**

`prepare_in_transaction` uses one savepoint around enrichment ensure and one around profile request registration; either failure becomes a warning and cannot poison the other receipt. `available_at=now+settle`, `profile_gate_deadline_at=available_at+gate_max`. `enqueue_after_commit` opens a short `SessionLocal` for enrichment ensure and uses existing post-commit profile publication. `kick` calls `customer_enrichment_job_service.kick` and `customer_intelligence_refresh_service.kick_committed_event_refresh` independently.

- [ ] **Step 6: Wire all entrypoints**

- Standard create: prepare after customer/contact flush, before commit; kick after commit.
- Modern conversion: prepare before command transaction commit; kick after commit.
- Legacy conversion: enqueue-after-commit after conversion commit.
- Old AI submit: enqueue-after-commit immediately after `create_entity`; remove profile trigger from parser `post_create_actions`, leaving activity creation only.

Never call model synchronously. Agent keeps using standard `/v1/customers/`.

- [ ] **Step 7: Run GREEN**

Run the exact Step 3 command.

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add CRM-Server/app/services/customer_lifecycle_post_commit_coordinator.py CRM-Server/app/services/customer_business_object_intelligence_service.py CRM-Server/app/api/customers.py CRM-Server/app/api/customer_ai.py CRM-Server/app/services/ai_parser/customer_parser.py CRM-Server/tests/unit/test_customer_lifecycle_post_commit_coordinator.py CRM-Server/tests/unit/api/test_customer_edit_api.py CRM-Server/tests/unit/test_customers_customer_intelligence_api.py
git commit -m "feat(customer): enqueue enrichment after customer creation"
```

---

### Task 8: Recovery worker, fair backfill, and startup wiring

**Files:**
- Create: `CRM-Server/app/services/customer_enrichment_backfill_service.py`
- Create: `CRM-Server/app/tasks/customer_enrichment_recovery.py`
- Create: `CRM-Server/app/tasks/customer_enrichment_backfill.py`
- Create: `CRM-Server/tests/unit/test_customer_enrichment_recovery.py`
- Create: `CRM-Server/tests/unit/test_customer_enrichment_backfill_scheduler.py`
- Modify: `CRM-Server/app/main.py`

**Interfaces:**
- `CustomerEnrichmentBackfillResult(success, scanned, eligible, scheduled, skipped, customer_ids, next_customer_id, dry_run)`.
- `scan_and_ensure(db, *, team_id=None, limit, after_customer_id=None, dry_run=False)`.
- Recovery scheduler processes initial quota then backfill quota every cycle.

- [ ] **Step 1: Write RED recovery tests**

Create `test_customer_enrichment_recovery.py` with fake CRUD returning 2 initial + 1 backfill candidates and fake job service returning COMPLETED, RETRY_PENDING, BUSY. Assert call order is initial ids first, counts are exact, and both purpose quotas passed to CRUD equal settings. Add a failure case where one run raises; scheduler increments `failed` and continues remaining requests.

- [ ] **Step 2: Write RED backfill tests**

Create SQLite-backed `test_customer_enrichment_backfill_scheduler.py` using Customer + CustomerEnrichmentJob tables:

```python
def test_backfill_scans_null_industry_even_when_profile_exists():
    # Seed null-industry customer plus a readable CustomerProfileCurrent/version.
    result = service.scan_and_ensure(db, limit=20, dry_run=False)
    assert result.eligible == 1
    assert result.scheduled == 1
    job = db.query(CustomerEnrichmentJob).one()
    assert job.purpose == "HISTORICAL_BACKFILL"


def test_backfill_skips_existing_industry_and_existing_plan_job():
    # Seed one filled industry, one null with existing current-plan job.
    result = service.scan_and_ensure(db, limit=20, dry_run=False)
    assert result.scheduled == 0


def test_backfill_is_idempotent_and_uses_cursor():
    first = service.scan_and_ensure(db, limit=1, dry_run=False)
    second = service.scan_and_ensure(db, limit=1, after_customer_id=first.next_customer_id, dry_run=False)
    third = service.scan_and_ensure(db, limit=20, dry_run=False)
    assert len(set(first.customer_ids + second.customer_ids)) == 2
    assert third.scheduled == 0


@pytest.mark.asyncio
async def test_scheduler_commits_normal_run_and_dry_run_does_not_commit(monkeypatch):
    normal_db = FakeDB()
    dry_db = FakeDB()
    sessions = iter([normal_db, dry_db])
    service = FakeBackfillService()
    scheduler = CustomerEnrichmentBackfillScheduler(
        backfill_service=service,
        recovery_scheduler=FakeRecoveryScheduler(),
        session_factory=lambda: next(sessions),
    )
    normal = await scheduler.backfill_once(limit=7, dry_run=False)
    dry = await scheduler.backfill_once(limit=7, dry_run=True)
    assert normal["scheduled"] == 1 and dry["dry_run"] is True
    assert normal_db.committed is True
    assert dry_db.committed is False
    assert normal_db.closed is True and dry_db.closed is True


@pytest.mark.asyncio
async def test_scheduler_rolls_back_and_closes_on_failure():
    db = FakeDB()
    scheduler = CustomerEnrichmentBackfillScheduler(
        backfill_service=FakeBackfillService(error=RuntimeError("boom")),
        recovery_scheduler=FakeRecoveryScheduler(),
        session_factory=lambda: db,
    )
    with pytest.raises(RuntimeError, match="boom"):
        await scheduler.backfill_once(limit=7)
    assert db.rolled_back is True
    assert db.closed is True
```

`FakeDB` implements commit/rollback/close flags. `FakeBackfillService.scan_and_ensure` returns `CustomerEnrichmentBackfillResult`; `FakeRecoveryScheduler.recover_once` records calls.

- [ ] **Step 3: Run RED**

Run:

```text
cd CRM-Server && PYTHONPATH=. ./venv/bin/pytest tests/unit/test_customer_enrichment_recovery.py tests/unit/test_customer_enrichment_backfill_scheduler.py -q --no-cov
```

Expected: FAIL because worker/services are missing.

- [ ] **Step 4: Implement backfill and workers**

Backfill queries Customer by stable id order with `industry IS NULL`, excludes an exists-subquery for current plan job, and never checks profile presence. It uses Task 2 CRUD ensure with purpose HISTORICAL_BACKFILL and no gate deadline. `dry_run` returns counts without ensure.

Recovery obtains candidates through `list_system_recovery_candidates(initial_limit=settings.CUSTOMER_INITIAL_ENRICHMENT_BATCH_SIZE, backfill_limit=settings.CUSTOMER_INITIAL_ENRICHMENT_BACKFILL_BATCH_SIZE)`, runs sequentially, and returns counts `{scanned, completed, retry_pending, exhausted, skipped, busy, failed}`.

Backfill scheduler mirrors existing customer intelligence scheduler and calls recovery after committing newly scheduled jobs. Register all start/stop functions in `main.py`.

- [ ] **Step 5: Run GREEN**

Run the exact Step 3 command.

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add CRM-Server/app/services/customer_enrichment_backfill_service.py CRM-Server/app/tasks/customer_enrichment_recovery.py CRM-Server/app/tasks/customer_enrichment_backfill.py CRM-Server/app/main.py CRM-Server/tests/unit/test_customer_enrichment_recovery.py CRM-Server/tests/unit/test_customer_enrichment_backfill_scheduler.py
git commit -m "feat(customer): recover and backfill enrichment jobs"
```

---

### Task 9: Reconciliation, diagnostics, dry-run, and requeue API

**Files:**
- Create: `CRM-Server/app/services/customer_enrichment_reconciliation_service.py`
- Create: `CRM-Server/app/tasks/customer_enrichment_reconciliation.py`
- Create: `CRM-Server/tests/unit/test_customer_enrichment_reconciliation_service.py`
- Create: `CRM-Server/tests/unit/test_customer_enrichment_reconciliation_scheduler.py`
- Create: `CRM-Server/app/api/customer_enrichment.py`
- Modify: `CRM-Server/tests/unit/test_customers_customer_intelligence_api.py`
- Modify: `CRM-Server/app/main.py`

**Interfaces:**
- `CustomerEnrichmentReconciliationResult(scanned, jobs_created, gates_released, refreshes_repaired, errors, next_customer_id, dry_run)`.
- Admin endpoints list tenant jobs, preview backfill, requeue one EXHAUSTED job, and run reconciliation.

- [ ] **Step 1: Write RED reconciliation tests**

Use a SQLite page of customers/jobs/runs and fake profile coordinator. Tests:

```python
def test_reconciliation_creates_missing_job_as_historical_and_is_idempotent():
    first = service.reconcile_once(db, team_id=2, limit=50, dry_run=False)
    second = service.reconcile_once(db, team_id=2, limit=50, dry_run=False)
    assert first.jobs_created == 1
    assert second.jobs_created == 0
    assert db.query(CustomerEnrichmentJob).one().purpose == "HISTORICAL_BACKFILL"


def test_reconciliation_releases_expired_gate_and_repairs_missing_refresh_receipt():
    result = service.reconcile_once(db, team_id=2, limit=50, dry_run=False)
    assert result.gates_released == 1
    assert result.refreshes_repaired == 1


def test_reconciliation_dry_run_does_not_mutate_and_returns_cursor():
    result = service.reconcile_once(db, team_id=None, limit=1, dry_run=True)
    assert result.scanned == 1
    assert result.next_customer_id is not None
    assert db.query(CustomerEnrichmentJob).count() == 0
```

Scheduler tests mirror `test_customer_intelligence_reconciliation_scheduler.py`: normal run commits and returns cursor; dry-run does not commit; exception rolls back/closes.

- [ ] **Step 2: Write RED API tests**
Extend `test_customers_customer_intelligence_api.py` by importing `app.api.customer_enrichment` and direct-calling its handlers with monkeypatched permission dependencies/services:

- list jobs passes team filters and returns only tenant rows;
- backfill preview returns `industry_null`, `existing_jobs`, `would_schedule`, `filled_skip`, `invalid_non_null`, `other_available`;
- requeue rejects non-EXHAUSTED with 409, rejects when customer industry is already filled, and for EXHAUSTED resets the same public id with `requeue_count + 1`;
- reconciliation endpoint requires `customer:edit:all` and returns service counts.

- [ ] **Step 3: Run RED**

Run:

```text
cd CRM-Server && PYTHONPATH=. ./venv/bin/pytest tests/unit/test_customer_enrichment_reconciliation_service.py tests/unit/test_customer_enrichment_reconciliation_scheduler.py tests/unit/test_customers_customer_intelligence_api.py -q --no-cov
```

Expected: FAIL on missing services/schemas/routes.

- [ ] **Step 4: Implement reconciliation and API**

Reconciliation scans a stable customer page, ensures missing active-plan jobs as HISTORICAL_BACKFILL, calls run-service release when first attempt/deadline permits, and calls profile coordinator repair when COMPLETED/SKIPPED job has no valid `profile_refresh_request_id`. Each customer is isolated in `begin_nested`; errors increment counts.
Add strict Pydantic response models in `schemas/customer.py` and the four routes in new `app/api/customer_enrichment.py` with prefix `/v1/customers/enrichment`:

```text
GET  /v1/customers/enrichment/jobs
GET  /v1/customers/enrichment/backfill-preview
POST /v1/customers/enrichment/jobs/{job_public_id}/requeue
POST /v1/customers/enrichment/reconciliation/run
```

All routes require `customer:edit:all`. `requeue` locks job/customer, requires EXHAUSTED and active plan fields still missing, calls Task 2 `requeue_exhausted`, commits, and kicks the job. Diagnostics never expose full prompts/PII.

Register `customer_enrichment.router` in `main.py` before `customers.router`; add a route-order test asserting `/api/v1/customers/enrichment/jobs` resolves to the enrichment route rather than `get_customer(customer_id="enrichment")`. Register reconciliation scheduler start/stop in `main.py`.

- [ ] **Step 5: Run GREEN**

Run the exact Step 3 command.

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add CRM-Server/app/services/customer_enrichment_reconciliation_service.py CRM-Server/app/tasks/customer_enrichment_reconciliation.py CRM-Server/app/schemas/customer.py CRM-Server/app/api/customer_enrichment.py CRM-Server/app/main.py CRM-Server/tests/unit/test_customer_enrichment_reconciliation_service.py CRM-Server/tests/unit/test_customer_enrichment_reconciliation_scheduler.py CRM-Server/tests/unit/test_customers_customer_intelligence_api.py
git commit -m "feat(customer): reconcile and inspect enrichment jobs"
```

---

### Task 10: Domain docs, deployment contract, and end-to-end verification

**Files:**
- Modify: `CONTEXT.md`
- Modify: `CRM-Docs/design-agent/runtime/customer-intelligence-profile.md`
- Modify: `CRM-Docs/deployment/README.md`
- Modify: `docs/superpowers/specs/2026-09-20-customer-initial-enrichment-design.md`

**Interfaces:**
- Documents initial enrichment as customer-main-data workflow, not profile projection.
- Deployment lists all new settings and scheduler startup evidence.

- [ ] **Step 1: Update domain docs**

Add glossary term and invariant:

```markdown
- **客户初始补全（Customer Initial Enrichment）**：客户首次成为正式客户后，由 durable job 在后台只补缺失、允许自动补全的客户主数据；不阻塞客户创建，不覆盖人工值，完成后刷新客户档案。

13. 客户初始补全与客户档案投影是独立原子：补全可以修改获准的空主数据字段，档案只能读取和投影；补全失败不能回滚客户，档案失败不能回滚补全。
```

Update profile PRD with readiness gate and read-only boundary. Update deployment README with settings, scheduler logs, backfill preview, EXHAUSTED diagnostics/requeue.

Mark spec status `已实施` only after verification.

- [ ] **Step 2: Run focused regression suite**

Run:

```text
cd CRM-Server && PYTHONPATH=. ./venv/bin/pytest \
  tests/unit/test_customer_enrichment_jobs_migration.py \
  tests/unit/test_customer_enrichment_job.py \
  tests/unit/test_customer_enrichment_inference_service.py \
  tests/unit/test_customer_enrichment_write_service.py \
  tests/unit/test_customer_initial_enrichment_graph.py \
  tests/unit/test_customer_enrichment_job_service.py \
  tests/unit/test_customer_profile_readiness_gate.py \
  tests/unit/test_customer_lifecycle_post_commit_coordinator.py \
  tests/unit/test_customer_enrichment_recovery.py \
  tests/unit/test_customer_enrichment_backfill_scheduler.py \
  tests/unit/test_customer_enrichment_reconciliation_service.py \
  tests/unit/test_customer_enrichment_reconciliation_scheduler.py \
  tests/unit/test_customer_intelligence_run_service.py \
  tests/unit/test_customer_intelligence_refresh_service.py \
  tests/unit/test_customers_customer_intelligence_api.py \
  tests/unit/api/test_customer_edit_api.py -q --no-cov
```

Expected: PASS.

- [ ] **Step 3: Run migration verification**

```text
cd CRM-Server && ./venv/bin/alembic upgrade head && ./venv/bin/alembic current
```

Expected: `136_customer_initial_enrichment (head)`.
- [ ] **Step 4: Run an actual service smoke**

Create a throwaway script under `/tmp/customer_enrichment_smoke.py` (never under the repo) with this structure:

```python
import asyncio
import os
from datetime import datetime

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.crud.customer_enrichment_job import CustomerEnrichmentJobCRUD
from app.models.customer import Customer
from app.models.customer_enrichment_job import CustomerEnrichmentJob
from app.models.industry import Industry
from app.models.operation_log import OperationLog
from app.services.agent.customer_initial_enrichment_graph import (
    CustomerInitialEnrichmentResult,
)
from app.services.customer_enrichment_contracts import (
    CustomerEnrichmentDecision,
    CustomerEnrichmentJobRequest,
    CustomerEnrichmentPurpose,
)
from app.services.customer_enrichment_job_service import CustomerEnrichmentJobService
from app.services.customer_enrichment_write_service import CustomerEnrichmentWriteService


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


class FakeWorkflow:
    def __init__(self, *, customer_id, error=None):
        self.customer_id = customer_id
        self.error = error
    async def run(self, request):
        if self.error:
            raise self.error
        return CustomerInitialEnrichmentResult(
            customer_id=self.customer_id,
            expected_version=1,
            decisions=(CustomerEnrichmentDecision(
                field="industry", value="internet_saas", reason="软件研发"
            ),),
        )


class CompletionPort:
    def on_first_attempt_finished(self, job):
        return None
    def on_terminal_success(self, job, result):
        return None


def seed(Session, customer_id):
    db = Session()
    if db.query(Industry).count() == 0:
        db.add_all([
            Industry(level=1, parent_id=None, code="internet", name="互联网", is_active=1),
            Industry(level=1, parent_id=None, code="other", name="其他", is_active=1),
        ])
        db.flush()
        internet = db.query(Industry).filter(Industry.code == "internet").one()
        db.add(Industry(level=2, parent_id=internet.id, code="internet_saas", name="SaaS公司", is_active=1))
    customer = Customer(
        id=customer_id, public_id=f"cus_{customer_id}", team_id=2,
        account_name=f"客户{customer_id}", city="上海", creator_id="9", owner_id="9", version=1,
    )
    db.add(customer)
    db.flush()
    job = CustomerEnrichmentJobCRUD().ensure(
        db,
        team_id=2,
        customer_id=customer_id,
        purpose=CustomerEnrichmentPurpose.INITIAL_CREATION.value,
        plan_version="customer-initial-v1",
        requested_fields=["industry"],
        available_at=datetime(2026, 9, 20, 10, 0, 0),
        profile_gate_deadline_at=datetime(2026, 9, 20, 10, 0, 30),
        max_attempts=3,
        commit=False,
    )
    db.commit()
    request = CustomerEnrichmentJobRequest(team_id=2, job_public_id=job.public_id)
    db.close()
    return request


async def main():
    engine = create_engine(os.environ["SMOKE_DATABASE_URL"])
    Base.metadata.create_all(engine, tables=[
        Customer.__table__, Industry.__table__, OperationLog.__table__, CustomerEnrichmentJob.__table__
    ])
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    success_request = seed(Session, 101)
    success_service = CustomerEnrichmentJobService(
        workflow=FakeWorkflow(customer_id=101),
        write_service=CustomerEnrichmentWriteService(),
        completion_port=CompletionPort(),
        session_factory=Session,
    )
    success = await success_service.run(success_request)
    db = Session()
    customer = db.get(Customer, 101)
    assert success.execution_status == "COMPLETED"
    assert customer.industry == "internet_saas"
    assert customer.version == 2
    db.close()

    failure_request = seed(Session, 102)
    failure_service = CustomerEnrichmentJobService(
        workflow=FakeWorkflow(customer_id=102, error=TimeoutError("timeout")),
        write_service=CustomerEnrichmentWriteService(),
        completion_port=CompletionPort(),
        session_factory=Session,
    )
    failure = await failure_service.run(failure_request)
    db = Session()
    customer = db.get(Customer, 102)
    job = db.query(CustomerEnrichmentJob).filter(CustomerEnrichmentJob.customer_id == 102).one()
    assert failure.execution_status == "RETRY_PENDING"
    assert customer.industry is None
    assert job.status == "RETRY_PENDING"
    db.close()


asyncio.run(main())
```

Run:

```bash
SMOKE_DB=$(mktemp -u /tmp/customer-enrichment-XXXXXX.sqlite)
cd CRM-Server
SMOKE_DATABASE_URL="sqlite:///$SMOKE_DB" PYTHONPATH=. ./venv/bin/python /tmp/customer_enrichment_smoke.py
rm -f /tmp/customer_enrichment_smoke.py "$SMOKE_DB"
```

Expected: exit 0 with no output. If it fails, do not mark the spec implemented.

- [ ] **Step 5: Commit docs**

```bash
git add CONTEXT.md CRM-Docs/design-agent/runtime/customer-intelligence-profile.md CRM-Docs/deployment/README.md docs/superpowers/specs/2026-09-20-customer-initial-enrichment-design.md
git commit -m "docs(customer): document initial enrichment lifecycle"
```

---

## Self-review

**Spec coverage:**

- Durable job / migration / config: Task 1–2
- Reusable plan, bounded context, one model call, closed industry catalog: Task 3
- Atomic conditional write and audit: Task 4
- LangGraph compute + lease/retry lifecycle: Task 5
- First-attempt profile gate, persistent `not_before_at`, deadline/degraded profile, refresh receipt: Task 6
- All customer creation entrypoints and Agent reuse: Task 7
- Fair initial/backfill worker and history scan: Task 8
- Reconciliation, dry-run, diagnostics, requeue: Task 9
- Domain/deployment docs, focused suites, migration proof, actual smoke: Task 10

**Type consistency:** `plan_version="customer-initial-v1"`, `CustomerEnrichmentJobRequest`, purpose/status enums, profile receipt fields, `not_before_at`, and completion-port method names are consistent across tasks.

**Placeholder scan:** no `TBD`, `TODO`, incomplete implementation step, or undefined interface remains.

**Task independence:** Tasks 1–4 create stable contracts; Task 5 consumes them behind an injected completion port; Task 6 supplies the concrete port; Tasks 7–9 wire entrypoints and recovery; Task 10 is final verification/docs only.

---

Plan complete and saved to `docs/superpowers/plans/2026-09-20-customer-initial-enrichment-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh implementer and review per task.

**2. Inline Execution** — execute in this session with task checkpoints.

Which approach?
