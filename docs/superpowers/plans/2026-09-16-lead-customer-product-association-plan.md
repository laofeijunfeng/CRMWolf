# 线索与客户意向产品关联 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind each lead and customer to one team-scoped intent product, copy it on convert, and default new opportunities to that product plus its `BASE` module.

**Architecture:** Add `crm_lead_products` and `crm_customer_products` junction tables. Writes still accept a single `product_public_id`; reads expose both scalar fields and a `products[]` array. Shared `product_intent` helpers resolve an active team product, replace the unique link, and build the response payload. Opportunity remains one product plus modules; only its create-time default source changes. Frontend reuses `SegmentedChoiceControl` without a module picker on lead/customer forms.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic v2, pytest, Vue 3, Pinia, TypeScript, Zod, vee-validate, Vitest, shadcn-vue.

**Spec:** `docs/superpowers/specs/2026-09-15-lead-customer-product-association-design.md`

## Global Constraints

- Do not touch unrelated dirty worktree changes.
- Do not add temporary plans, validation reports, or one-off scripts at the repo root.
- Database changes MUST go through Alembic. Next revision is `134_lead_customer_product_intent`, `down_revision = "133_opportunity_product_assignment"`.
- Leads and customers store intent products only. Never persist modules on those objects.
- Application layer enforces at most one product link per lead/customer. Table PK is `(owner_id, product_id)` only; do not add a unique constraint on `lead_id` / `customer_id` alone.
- Writes use a single `product_public_id`. Reads always return `product_public_id`, `product_name`, and `products` (0 or 1 item this phase).
- New lead/customer/convert writes require an active product in the current `team_id`. Historical reads may be empty.
- Cross-team or missing products MUST return 404 `"产品不存在"`. Inactive products used for new writes MUST return 400 `"请选择启用中的产品"`. Empty active catalog MUST return 400 `"团队还没有可用产品，请联系管理员在「设置 → 产品管理」创建"`. Missing product MUST return 400 `"请选择产品"`.
- Product delete MUST 409 when the product is still referenced by a lead, customer, or opportunity.
- Opportunity stays one-product: `Opportunity.product_id` remains a scalar. Changing a customer product MUST NOT rewrite existing opportunities.
- First-active-product fallback is `product_crud.list(..., is_active=True)` which already orders by `Product.id` ascending.
- Frontend: no `any`, `as any`, `@ts-ignore`, or unnecessary non-null assertions. Follow `CRM-Docs/design-system/`.
- Canvas has `crm.create_customer` and `crm.create_opportunity` today, not `crm.create_lead`. Add `product_public_id` to the existing customer node; do not invent a lead canvas node.
- Existing `CustomerCreate(...)` constructors live in `tests/unit/test_customer_edit_contracts.py`, `tests/unit/test_customer_service.py`, and `tests/unit/api/test_customer_edit_api.py`. There are no `LeadCreate(` test constructors today. Update those customer call sites in Task 3 when the field becomes required.
- Each task writes focused tests. Full lint/type-check/pytest/alembic runs once in the final task.

---

### Task 1: Junction models, intent helper, migration, delete guard

**Files:**
- Modify: `CRM-Server/app/models/lead.py`
- Modify: `CRM-Server/app/models/customer.py`
- Modify: `CRM-Server/app/models/__init__.py`
- Modify: `CRM-Server/app/schemas/product.py`
- Create: `CRM-Server/app/crud/product_intent.py`
- Modify: `CRM-Server/app/crud/product.py`
- Modify: `CRM-Server/app/api/products.py`
- Create: `CRM-Server/migrations/versions/134_lead_customer_product_intent.py`
- Test: `CRM-Server/tests/unit/test_product_intent.py`
- Test: `CRM-Server/tests/unit/test_product_intent_migration.py`

**Interfaces:**
- Consumes: `Product`, `product_crud.get_by_public_id`, `product_crud.list`, `Opportunity.product_id`
- Produces:
  - `LeadProduct` / `CustomerProduct` mapped to `crm_lead_products` / `crm_customer_products`
  - `ProductIntentRef(public_id: str, name: str)`
  - `ProductNotFoundError(ValueError)`
  - `EMPTY_CATALOG_MESSAGE = "团队还没有可用产品，请联系管理员在「设置 → 产品管理」创建"`
  - `MISSING_PRODUCT_MESSAGE = "请选择产品"`
  - `INACTIVE_PRODUCT_MESSAGE = "请选择启用中的产品"`
  - `PRODUCT_NOT_FOUND_MESSAGE = "产品不存在"`
  - `PRODUCT_IN_USE_MESSAGE = "产品仍被线索、客户或商机引用，无法删除"`
  - `resolve_writable_product(db, team_id: int, product_public_id: str | None) -> Product`
  - `replace_product_links(db, *, team_id: int, link_cls, owner_id: int, owner_fk: str, product: Product) -> None`
  - `product_intent_payload(links) -> dict` with keys `product_public_id`, `product_name`, `products`
  - `first_active_product(db, team_id: int) -> Product | None`
  - `base_module_public_id(product: Product) -> str | None`
  - `assert_product_deletable(db, product: Product) -> None`

- [ ] **Step 1: Write failing intent tests**

Create `CRM-Server/tests/unit/test_product_intent.py` with a SQLite fixture that creates `Product`, `ProductModule`, `Lead`, `LeadProduct`, `Customer`, `CustomerProduct`, and a minimal `Opportunity` row. Cover:

```python
def test_replace_product_links_replaces_instead_of_appending(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    oa = product_crud.create(db, 1, ProductCreate(name="OA"), "u1")
    lead = _lead(db, team_id=1)
    replace_product_links(db, team_id=1, link_cls=LeadProduct, owner_id=lead.id, owner_fk="lead_id", product=crm)
    replace_product_links(db, team_id=1, link_cls=LeadProduct, owner_id=lead.id, owner_fk="lead_id", product=oa)
    links = db.query(LeadProduct).filter(LeadProduct.lead_id == lead.id).all()
    assert [link.product_id for link in links] == [oa.id]


def test_resolve_writable_product_rejects_cross_team_as_not_found(db):
    product = product_crud.create(db, 2, ProductCreate(name="CRM"), "u1")
    with pytest.raises(ProductNotFoundError, match="产品不存在"):
        resolve_writable_product(db, team_id=1, product_public_id=product.public_id)


def test_resolve_writable_product_rejects_inactive(db):
    product = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    product.is_active = False
    db.commit()
    with pytest.raises(ValueError, match="请选择启用中的产品"):
        resolve_writable_product(db, team_id=1, product_public_id=product.public_id)


def test_resolve_writable_product_empty_catalog_message(db):
    with pytest.raises(ValueError, match="还没有可用产品"):
        resolve_writable_product(db, team_id=1, product_public_id=None)


def test_product_intent_payload_empty_and_single(db):
    assert product_intent_payload([]) == {
        "product_public_id": None,
        "product_name": None,
        "products": [],
    }
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    payload = product_intent_payload([SimpleNamespace(product=crm)])
    assert payload["product_public_id"] == crm.public_id
    assert payload["product_name"] == "CRM"
    assert payload["products"] == [{"public_id": crm.public_id, "name": "CRM"}]


def test_delete_product_referenced_by_lead_is_rejected(db):
    product = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    lead = _lead(db, team_id=1)
    replace_product_links(db, team_id=1, link_cls=LeadProduct, owner_id=lead.id, owner_fk="lead_id", product=product)
    with pytest.raises(ValueError, match="引用"):
        product_crud.delete(db, product)
```

Also add `test_product_intent_migration.py` following `tests/unit/test_product_migration.py`: upgrade `134_lead_customer_product_intent` creates both tables and indexes; downgrade drops them and restores revision `133`.

- [ ] **Step 2: Add models and response schema**

In `app/models/lead.py`, after `Lead` timestamps, add:

```python
product_links = relationship(
    "LeadProduct",
    back_populates="lead",
    cascade="all, delete-orphan",
)
```

```python
class LeadProduct(Base):
    __tablename__ = "crm_lead_products"
    lead_id = Column(BigInteger, ForeignKey("crm_leads.id", ondelete="CASCADE"), primary_key=True, comment="线索ID")
    product_id = Column(BigInteger, ForeignKey("crm_products.id", ondelete="RESTRICT"), primary_key=True, comment="产品ID")
    team_id = Column(BigInteger, nullable=False, comment="团队ID")
    lead = relationship("Lead", back_populates="product_links")
    product = relationship("Product")
    __table_args__ = (
        Index("idx_lead_products_team", "team_id"),
        Index("idx_lead_products_product", "product_id"),
        {"comment": "线索意向产品"},
    )
```

Mirror as `CustomerProduct` / `crm_customer_products` on `Customer`. Export both from `app/models/__init__.py` next to `Lead` / `Customer`.

In `app/schemas/product.py`:

```python
class ProductIntentRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    public_id: str
    name: str
```

- [ ] **Step 3: Implement `product_intent` helpers and delete guard**

`resolve_writable_product`:
- blank id + no active products in team → `EMPTY_CATALOG_MESSAGE`
- blank id + catalog exists → `MISSING_PRODUCT_MESSAGE`
- `get_by_public_id` miss → `ProductNotFoundError(PRODUCT_NOT_FOUND_MESSAGE)`
- inactive → `INACTIVE_PRODUCT_MESSAGE`
- else return product

`replace_product_links` deletes existing rows for that owner in `team_id`, then inserts one row. Never append. Set `team_id` from the product/owner, not the caller’s guess when they disagree.

`product_intent_payload` sorts links by `product_id` and takes the first (future multi-product rule). Empty links → `null` / `null` / `[]`.

`first_active_product` returns `product_crud.list(db, team_id, is_active=True)[0]` or `None`.

`base_module_public_id` returns the active `BASE` module public id, else the first active module, else `None`.

`assert_product_deletable` raises `ValueError(PRODUCT_IN_USE_MESSAGE)` if any `LeadProduct`, `CustomerProduct`, or `Opportunity.product_id` points at the product. Call it from `product_crud.delete` before `db.delete`. Catch `IntegrityError` on delete as the same message.

Map `"引用"` (and existing `"编码已存在"`) to HTTP 409 in `app/api/products.py:_domain_error`.

- [ ] **Step 4: Add Alembic revision 134**

Follow `133_opportunity_product_assignment.py`. Create both tables with composite PKs, `ON DELETE CASCADE` to lead/customer, `ON DELETE RESTRICT` to products, `team_id` NOT NULL, indexes `idx_lead_products_team`, `idx_lead_products_product`, `idx_customer_products_team`, `idx_customer_products_product`. No extra unique constraint on owner id alone. Downgrade drops indexes then tables.

- [ ] **Step 5: Run focused tests**

Run: `cd CRM-Server && .venv/bin/python -m pytest tests/unit/test_product_intent.py tests/unit/test_product_intent_migration.py -q`

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add CRM-Server/app/models/lead.py CRM-Server/app/models/customer.py CRM-Server/app/models/__init__.py CRM-Server/app/schemas/product.py CRM-Server/app/crud/product_intent.py CRM-Server/app/crud/product.py CRM-Server/app/api/products.py CRM-Server/migrations/versions/134_lead_customer_product_intent.py CRM-Server/tests/unit/test_product_intent.py CRM-Server/tests/unit/test_product_intent_migration.py
git commit -m "$(cat <<'EOF'
feat(products): add lead and customer product intent tables

EOF
)"
```

---

### Task 2: Lead schema, CRUD, API, list catalog

**Files:**
- Modify: `CRM-Server/app/schemas/lead.py`
- Modify: `CRM-Server/app/crud/lead.py`
- Modify: `CRM-Server/app/api/leads.py`
- Modify: `CRM-Server/app/core/list_query/catalogs/leads.py`
- Modify: `CRM-Server/app/core/list_query/catalogs/common.py` (only if a reusable subquery helper is cleaner than inlining)
- Test: `CRM-Server/tests/unit/test_lead_product_intent.py`
- Test: `CRM-Server/tests/unit/test_lead_list_api.py` (extend if catalog coverage fits; otherwise keep in the new file)

**Interfaces:**
- Consumes: `resolve_writable_product`, `replace_product_links`, `product_intent_payload`, `LeadProduct`
- Produces:
  - `LeadCreate.product_public_id: str` required
  - `LeadUpdate.product_public_id: Optional[str]`
  - `LeadResponse.product_public_id: Optional[str]`, `product_name: Optional[str]`, `products: list[ProductIntentRef]`
  - `lead_crud.create` / `update` write exactly one `LeadProduct`
  - `LEADS_LIST_QUERY_CATALOG` field `product_name`
  - lead search includes product name

- [ ] **Step 1: Write failing lead tests**

Helpers used by the tests below (define in the test module, not production code):

```python
def _lead_in(*, product_public_id: str) -> LeadCreate:
    return LeadCreate(
        lead_name="线索A",
        city="上海",
        contact_name="王",
        contact_phone="13800138000",
        source="线上注册",
        product_public_id=product_public_id,
    )


def _lead_row(db, *, team_id: int) -> Lead:
    lead = Lead(
        team_id=team_id,
        lead_name="历史线索",
        source="线上注册",
        city="上海",
        contact_name="王",
        contact_phone="13800138000",
        creator_id="u1",
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead
```

`convert_from_lead` still requires the lead to have `source_id`. `_lead_in` / `_lead_row` fixtures in Task 3 must also attach a real `AcquisitionSource` the same way existing convert tests do, or call `resolve_for_import` before convert.

```python
def test_create_lead_requires_active_product(db):
    with pytest.raises(ValidationError, match="缺少产品"):
        LeadCreate(
            lead_name="线索A",
            city="上海",
            contact_name="王",
            contact_phone="13800138000",
            source="线上注册",
        )
    other = product_crud.create(db, 2, ProductCreate(name="CRM"), "u1")
    with pytest.raises(ProductNotFoundError, match="产品不存在"):
        lead_crud.create(db, _lead_in(product_public_id=other.public_id), "u1", 1)
    inactive = product_crud.create(db, 1, ProductCreate(name="停用"), "u1")
    inactive.is_active = False
    db.commit()
    with pytest.raises(ValueError, match="请选择启用中的产品"):
        lead_crud.create(db, _lead_in(product_public_id=inactive.public_id), "u1", 1)
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    lead = lead_crud.create(db, _lead_in(product_public_id=crm.public_id), "u1", 1)
    payload = product_intent_payload(lead.product_links)
    assert payload["product_public_id"] == crm.public_id
    assert db.query(LeadProduct).filter(LeadProduct.lead_id == lead.id).count() == 1


def test_update_lead_replaces_product_link(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    oa = product_crud.create(db, 1, ProductCreate(name="OA"), "u1")
    lead = lead_crud.create(db, _lead_in(product_public_id=crm.public_id), "u1", 1)
    lead_crud.update(db, lead, LeadUpdate(product_public_id=oa.public_id))
    links = db.query(LeadProduct).filter(LeadProduct.lead_id == lead.id).all()
    assert [link.product_id for link in links] == [oa.id]


def test_update_lead_without_product_keeps_existing_link(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    lead = lead_crud.create(db, _lead_in(product_public_id=crm.public_id), "u1", 1)
    lead_crud.update(db, lead, LeadUpdate(city="杭州"))
    links = db.query(LeadProduct).filter(LeadProduct.lead_id == lead.id).all()
    assert [link.product_id for link in links] == [crm.id]


def test_historical_lead_without_product_reads_empty_payload(db):
    lead = _lead_row(db, team_id=1)
    assert product_intent_payload(lead.product_links) == {
        "product_public_id": None,
        "product_name": None,
        "products": [],
    }


def test_batch_import_missing_product_fails_that_row():
    with pytest.raises(ValidationError, match="缺少产品"):
        LeadCreate(
            lead_name="导入失败行",
            city="上海",
            contact_name="王",
            contact_phone="13800138000",
            source="线上注册",
            product_public_id=" ",
        )
```

Catalog test:

```python
def test_leads_catalog_exposes_product_name():
    from app.core.list_query.catalogs.leads import LEADS_LIST_QUERY_CATALOG
    field = LEADS_LIST_QUERY_CATALOG.require("product_name")
    assert field.type == "text"
    assert field.supports_sorting()
```

- [ ] **Step 2: Extend lead schemas and dump exclusions**

Add `product_public_id` to `LeadCreate` as required `str`. Add optional `product_public_id` to `LeadUpdate`. Add the three read fields to `LeadResponse` (list/detail inherit). Import `ProductIntentRef` from `app.schemas.product`.

`lead_crud.create` currently dumps with `exclude={"source_public_id", "source"}`. Also exclude `product_public_id` so `Lead(**lead_data)` does not receive an unknown column. After flush, `resolve_writable_product` then `replace_product_links`. Same on `update` when `"product_public_id" in obj_in.model_fields_set`.

`get_by_id` / `get_by_public_id` / `get_multi` should `selectinload(Lead.product_links).selectinload(LeadProduct.product)` so list/detail builders do not N+1.

Map `ProductNotFoundError` to 404 in `app/api/leads.py` create/update. Other intent `ValueError`s stay 400. Batch import already records `str(e)` per row; blank product should fail that row only. If schema validation happens before the loop, `LeadCreate` will reject missing ids — keep that, and map the message to include `缺少产品` by using a validator message `"缺少产品"` on `LeadCreate.product_public_id` so import errors match the spec. Use:

```python
product_public_id: str = Field(..., min_length=1, description="意向产品对外ID")

@field_validator("product_public_id")
def product_public_id_must_be_present(cls, v):
    if not v or not str(v).strip():
        raise ValueError("缺少产品")
    return v.strip()
```

Empty-catalog and inactive still come from `resolve_writable_product` during `create`.

- [ ] **Step 3: Build lead responses and catalog**

`_build_lead_response` and `_build_lead_list_responses` merge `**product_intent_payload(lead.product_links)`.

In `LEADS_LIST_QUERY_CATALOG`, add `product_name` as a text field using a correlated subquery:

```python
select(Product.name)
.join(LeadProduct, LeadProduct.product_id == Product.id)
.where(LeadProduct.lead_id == Lead.id, LeadProduct.team_id == Lead.team_id)
.order_by(LeadProduct.product_id)
.limit(1)
.scalar_subquery()
```

Add the same expression to `text_search_predicate(...)`. Legacy `keyword` `or_()` in `get_multi` should also `exists()` on `LeadProduct`/`Product.name.like`. Do not add `product_name` to `_apply_sort`’s `getattr(Lead, order_by)` list; unified catalog sorting covers it.

- [ ] **Step 4: Run focused tests**

Run: `cd CRM-Server && .venv/bin/python -m pytest tests/unit/test_lead_product_intent.py tests/unit/test_lead_list_api.py -q`

Expected: new tests pass. If `test_lead_list_api.py` has frozen catalog keys, update that snapshot in this task.

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/schemas/lead.py CRM-Server/app/crud/lead.py CRM-Server/app/api/leads.py CRM-Server/app/core/list_query/catalogs/leads.py CRM-Server/tests/unit/test_lead_product_intent.py
git commit -m "$(cat <<'EOF'
feat(leads): require intent product on lead writes

EOF
)"
```

---

### Task 3: Customer schema, CRUD, convert, list catalog

**Files:**
- Modify: `CRM-Server/app/schemas/customer.py`
- Modify: `CRM-Server/app/schemas/lead.py` (`LeadConvertRequest`)
- Modify: `CRM-Server/app/crud/customer.py`
- Modify: `CRM-Server/app/api/customers.py`
- Modify: `CRM-Server/app/api/leads.py` (deprecated convert mapping)
- Modify: `CRM-Server/app/core/list_query/catalogs/customers.py`
- Modify existing constructors: `CRM-Server/tests/unit/test_customer_edit_contracts.py`, `CRM-Server/tests/unit/test_customer_service.py`, `CRM-Server/tests/unit/api/test_customer_edit_api.py` (and any other `CustomerCreate(` that goes through the required field)
- Test: `CRM-Server/tests/unit/test_customer_product_intent.py`

Helpers:

```python
def _customer_in(*, product_public_id: str) -> CustomerCreate:
    return CustomerCreate(
        account_name="客户A",
        city="上海",
        product_public_id=product_public_id,
    )
```

Reuse Task 2 `_lead_in` / `_lead_row`. Opportunity fixture can copy `tests/unit/test_opportunity_product_assignment.py:_opportunity` and set `customer_id`.

**Interfaces:**
- Consumes: same intent helpers, `CustomerProduct`, lead `product_links`
- Produces:
  - `CustomerCreate.product_public_id: str` required
  - `CustomerUpdate.product_public_id: Optional[str]`
  - `ConvertLeadToCustomer.product_public_id: Optional[str]`
  - `LeadConvertRequest.product_public_id: Optional[str]`
  - `CustomerResponse` / `CustomerListResponse` / `CustomerDetailResponse` gain the three intent fields
  - `customer_crud.convert_from_lead(..., product_public_id: Optional[str] = None)`
  - convert command fingerprint includes `product_public_id`
  - `CUSTOMERS_LIST_QUERY_CATALOG` field `product_name`

- [ ] **Step 1: Write failing customer/convert tests**

```python
def test_create_customer_writes_single_product_link(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    customer = customer_crud.create(db, _customer_in(product_public_id=crm.public_id), "u1", 1)
    links = db.query(CustomerProduct).filter(CustomerProduct.customer_id == customer.id).all()
    assert [link.product_id for link in links] == [crm.id]


def test_update_customer_replaces_intent_and_does_not_touch_opportunity(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    oa = product_crud.create(db, 1, ProductCreate(name="OA"), "u1")
    customer = customer_crud.create(db, _customer_in(product_public_id=crm.public_id), "u1", 1)
    opportunity = _opportunity(db, customer_id=customer.id, team_id=1)
    opportunity_crud.assign_product(
        db, opportunity, team_id=1,
        product_public_id=crm.public_id,
        module_public_ids=[crm.modules[0].public_id],
    )
    customer_crud.update(db, customer, CustomerUpdate(product_public_id=oa.public_id))
    db.refresh(opportunity)
    assert [link.product_id for link in customer.product_links] == [oa.id]
    assert opportunity.product_id == crm.id
    assert [module.public_id for module in opportunity.selected_modules] == [crm.modules[0].public_id]


def test_convert_copies_lead_product(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    lead = lead_crud.create(db, _lead_in(product_public_id=crm.public_id), "u1", 1)
    customer, _contact = customer_crud.convert_from_lead(
        db, lead_id=lead.id, account_name=lead.lead_name, address=None,
        creator_id="u1", team_id=1,
    )
    assert [link.product_id for link in customer.product_links] == [crm.id]


def test_convert_request_product_overrides_lead_product(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    oa = product_crud.create(db, 1, ProductCreate(name="OA"), "u1")
    lead = lead_crud.create(db, _lead_in(product_public_id=crm.public_id), "u1", 1)
    customer, _contact = customer_crud.convert_from_lead(
        db, lead_id=lead.id, account_name=lead.lead_name, address=None,
        creator_id="u1", team_id=1, product_public_id=oa.public_id,
    )
    assert [link.product_id for link in customer.product_links] == [oa.id]
    assert [link.product_id for link in lead.product_links] == [crm.id]


def test_convert_historical_lead_without_product_requires_request_id(db):
    lead = _lead_row(db, team_id=1)
    with pytest.raises(ValueError, match="请选择产品"):
        customer_crud.convert_from_lead(
            db, lead_id=lead.id, account_name=lead.lead_name, address=None,
            creator_id="u1", team_id=1,
        )
```

Also assert catalog `product_name` exists.

- [ ] **Step 2: Update schemas and existing CustomerCreate call sites**

Add required `product_public_id` to `CustomerCreate` with the same `"缺少产品"` validator as leads. Optional on `CustomerUpdate`, `ConvertLeadToCustomer`, `LeadConvertRequest`. Add read fields to `CustomerResponse`.

Schema-only tests in `test_customer_edit_contracts.py` currently construct `CustomerCreate(account_name=..., city=...)`. Pass `product_public_id="prd_test"` there so license/status assertions still run; do not turn those into ValidationError tests unless the case is specifically "missing product". CRUD/API tests in `test_customer_edit_api.py` and `test_customer_service.py` must create a real product (or mock `resolve_writable_product`) and pass its public id. Search the three files for `CustomerCreate(` and update every call in this task.

- [ ] **Step 3: Write customer CRUD and convert**

`customer_crud.create`: exclude `product_public_id` from `model_dump` (already excludes `primary_contact`, `source_public_id`, `source`). After flush, resolve + replace links. Keep `commit` flag behavior.

`update_with_audit`: if `"product_public_id" in fields_set`, resolve and replace. Include `product_public_id` in `audit_fields`. Current audit value is the existing link’s `product.public_id`.

`convert_from_lead`: after `db.add(customer); db.flush()`, resolve product as:
1. request `product_public_id` if provided
2. else lead’s current intent product (first `product_links` by `product_id`)
3. else raise `ValueError("请选择产品")`

Then `replace_product_links` on the new customer. Same transaction as today (`commit` flag unchanged).

`create_customer` API: map `ProductNotFoundError` to 404, other intent errors to 400.

`convert_from_lead` API: pass `data.product_public_id` into CRUD. Add it to `request_fingerprint({...})`. Deprecated `convert_lead` in `app/api/leads.py` forwards `request.product_public_id`.

List/detail builders merge `product_intent_payload(customer.product_links)`. `get_multi` selectinloads `product_links.product`.

Customers catalog: same `product_name` subquery via `CustomerProduct`. Extend `text_search_predicate(..., include_customer_identity_terms=True)` by passing the subquery as an extra expression. Legacy `keyword` `or_()` should `exists()` on customer product name.

- [ ] **Step 4: Run focused tests**

Run: `cd CRM-Server && .venv/bin/python -m pytest tests/unit/test_customer_product_intent.py tests/unit/test_customer_edit_contracts.py tests/unit/api/test_customer_edit_api.py tests/unit/test_customer_service.py -q`

Expected: pass, including updated constructors.

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/schemas/customer.py CRM-Server/app/schemas/lead.py CRM-Server/app/crud/customer.py CRM-Server/app/api/customers.py CRM-Server/app/api/leads.py CRM-Server/app/core/list_query/catalogs/customers.py CRM-Server/tests/unit/test_customer_product_intent.py CRM-Server/tests/unit/test_customer_edit_contracts.py CRM-Server/tests/unit/test_customer_service.py CRM-Server/tests/unit/api/test_customer_edit_api.py
git commit -m "$(cat <<'EOF'
feat(customers): persist intent product and copy it on convert

EOF
)"
```

---

### Task 4: Opportunity defaults and empty-catalog create errors

**Files:**
- Modify: `CRM-Server/app/crud/opportunity.py` (`assign_product` empty-catalog branch only)
- Modify: `CRM-Server/app/services/agent/business_rules.py`
- Test: `CRM-Server/tests/unit/test_opportunity_product_assignment.py`
- Test: `CRM-Server/tests/unit/test_customer_product_intent.py` (opportunity default helper if placed there) or `CRM-Server/tests/unit/test_agent_opportunity_product_defaults.py`

**Interfaces:**
- Consumes: `first_active_product`, `base_module_public_id`, customer `product_intent_payload` / `product_links`
- Produces:
  - `opportunity_field_defaults(customer)` also returns `product_public_id` and `product_module_public_ids` when the customer has an active product
  - `assign_product` with blank product id and empty team catalog raises `EMPTY_CATALOG_MESSAGE`
  - editing an opportunity still only changes product when the request sets product fields

- [ ] **Step 1: Write failing default tests**

```python
def test_opportunity_field_defaults_use_customer_product_and_base():
    customer = {"id": "cus_1", "product_public_id": "prd_crm", "products": [{"public_id": "prd_crm", "name": "CRM"}]}
    # stub or pass modules through a small helper used by business_rules
    defaults = opportunity_field_defaults(customer)
    assert defaults["product_public_id"] == "prd_crm"


def test_assign_product_blank_id_with_empty_catalog_uses_admin_copy(db):
    opportunity = _opportunity(db)
    with pytest.raises(ValueError, match="还没有可用产品"):
        opportunity_crud.assign_product(db, opportunity, team_id=1, product_public_id="", module_public_ids=[])
```

Keep the existing “replace modules on product change” test. Add: after customer intent changes, an opportunity loaded from DB still has the old `product_id` (covered in Task 3; re-run here if needed).

- [ ] **Step 2: Implement defaults**

`opportunity_field_defaults`:
- if customer has `product_public_id`, set it
- if customer has `product_module_public_ids` already, keep them; otherwise callers that have DB access should fill BASE
- keep current procurement-method default

Agent create path does not currently load the product catalog. Add a small DB helper used by `opportunity_next_task_from_suggestions` / planning when customer is a dict from API:

```python
def customer_opportunity_product_defaults(db, team_id: int, customer: dict) -> dict:
    public_id = customer.get("product_public_id")
    product = None
    if public_id:
        product = product_crud.get_by_public_id(db, str(public_id), team_id)
        if product is not None and not bool(product.is_active):
            product = None
    if product is None:
        product = first_active_product(db, team_id)
    if product is None:
        return {}
    module_id = base_module_public_id(product)
    defaults = {"product_public_id": product.public_id}
    if module_id:
        defaults["product_module_public_ids"] = [module_id]
    return defaults
```

Use this helper from `opportunity_field_defaults` when a db/team is available; for pure dict tests, if `product_public_id` is already on the customer dict, copy it through.

`assign_product`: before `"请选择产品"`, if `not product_public_id` and `not product_crud.list(db, team_id, is_active=True)`, raise `EMPTY_CATALOG_MESSAGE`.

Do not rewrite opportunity product on customer update. Do not change edit behavior in `OpportunityFormDialog` in this backend task.

- [ ] **Step 3: Run focused tests**

Run: `cd CRM-Server && .venv/bin/python -m pytest tests/unit/test_opportunity_product_assignment.py tests/unit/test_customer_product_intent.py -q`

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add CRM-Server/app/crud/opportunity.py CRM-Server/app/services/agent/business_rules.py CRM-Server/tests/unit/test_opportunity_product_assignment.py
git commit -m "$(cat <<'EOF'
feat(opportunities): default new deals from customer intent product

EOF
)"
```

---

### Task 5: Agent payloads, missing fields, canvas customer node

**Files:**
- Modify: `CRM-Server/app/services/agent/tool_registry.py`
- Modify: `CRM-Server/app/services/agent/business_rules.py`
- Modify: `CRM-Server/app/services/agent/workflow/planning.py`
- Modify: `CRM-Client/src/components/workflow/workflowNodeRegistry.ts`
- Modify: `CRM-Client/src/components/workflow/nodeConfigPanels/ActionCreateCustomerPanel.vue`
- Modify: `CRM-Client/src/components/workflow/__tests__/workflowNodeRegistry.test.ts`
- Modify: `CRM-Client/src/components/workflow/__tests__/workflowValidation.test.ts`
- Test: `CRM-Server/tests/unit/test_agent_lead_customer_product_fields.py`

**Interfaces:**
- Consumes: `AgentLeadCreatePayload`, `AgentCustomerCreatePayload`, `missing_lead_fields`, `missing_customer_fields`, `format_lead_missing_fields`, `format_customer_missing_fields`, `_plan_lead`
- Produces: required `product_public_id` on Agent lead/customer create; missing-field copy talks about 产品, never 模块; canvas `crm.create_customer.requiredFields` includes `product_public_id`

- [ ] **Step 1: Write failing Agent/canvas tests**

Backend: constructing `AgentLeadCreatePayload` / `AgentCustomerCreatePayload` without `product_public_id` fails. `missing_lead_fields({"lead_name": "A", "city": "上海", "contact_name": "王", "contact_phone": "13800138000"})` includes `"product_public_id"`. `format_lead_missing_fields(["product_public_id"]) == "产品"`. Empty catalog prompt in `_plan_lead` must not ask the model to type a raw public id; the user-facing string is `产品` / `团队还没有可用产品`.

Frontend: `WORKFLOW_NODE_REGISTRY['crm.create_customer'].requiredFields` includes `product_public_id`. `defaults()` includes `product_public_id: ''`. `workflowValidation` valid customer config includes `product_public_id: 'prd_1'`. Opportunity valid config already needs `product_public_id` and `product_module_public_ids` in the registry; the current “valid minimal configs” test is missing them and should be fixed here if it is already failing, or updated when required.

- [ ] **Step 2: Implement Agent and canvas fields**

```python
class AgentLeadCreatePayload(AgentStrictPayload):
    ...
    product_public_id: str = Field(..., min_length=1, description="意向产品对外ID")
```

Same field on `AgentCustomerCreatePayload`. `create_lead` / `create_customer` already dump the payload to the HTTP API; no extra service change once the field exists.

`missing_lead_fields` required list adds `product_public_id`. `missing_customer_fields` always requires `product_public_id` (not only when a contact is present). Labels: `"product_public_id": "产品"`.

`_plan_lead` copies `product_public_id` from the semantic lead model into the lead dict. If missing, keep `_needs_text` but the prompt uses `format_lead_missing_fields`. If the team catalog is empty, append `EMPTY_CATALOG_MESSAGE`. Do not add a module field to lead/customer completion.

Canvas `ActionCreateCustomerPanel.vue`: add an input bound to `product_public_id` labeled `产品对外ID`. Registry `requiredFields: ['account_name', 'city', 'product_public_id']`.

- [ ] **Step 3: Run focused tests**

Run: `cd CRM-Server && .venv/bin/python -m pytest tests/unit/test_agent_lead_customer_product_fields.py -q`

Run: `cd CRM-Client && npm run test:unit -- src/components/workflow/__tests__/workflowNodeRegistry.test.ts src/components/workflow/__tests__/workflowValidation.test.ts`

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add CRM-Server/app/services/agent/tool_registry.py CRM-Server/app/services/agent/business_rules.py CRM-Server/app/services/agent/workflow/planning.py CRM-Server/tests/unit/test_agent_lead_customer_product_fields.py CRM-Client/src/components/workflow/workflowNodeRegistry.ts CRM-Client/src/components/workflow/nodeConfigPanels/ActionCreateCustomerPanel.vue CRM-Client/src/components/workflow/__tests__/workflowNodeRegistry.test.ts CRM-Client/src/components/workflow/__tests__/workflowValidation.test.ts
git commit -m "$(cat <<'EOF'
feat(agent): require product on lead and customer creates

EOF
)"
```

---

### Task 6: Frontend picker, forms, convert, opportunity defaults, empty states

**Files:**
- Create: `CRM-Client/src/composables/useProductCatalog.ts`
- Create: `CRM-Client/src/components/crmwolf/ProductIntentPicker.vue`
- Create: `CRM-Client/src/components/crmwolf/__tests__/ProductIntentPicker.test.ts`
- Modify: `CRM-Client/src/schemas/lead.ts`
- Modify: `CRM-Client/src/schemas/lead-form.ts`
- Modify: `CRM-Client/src/schemas/customer.ts`
- Modify: `CRM-Client/src/schemas/customer-form.ts`
- Modify: `CRM-Client/src/api/customer.ts` (`ConvertLeadToCustomer`)
- Modify: `CRM-Client/src/components/LeadFormDialog.vue`
- Modify: `CRM-Client/src/components/dialogs/CustomerFormDialog.vue`
- Modify: `CRM-Client/src/components/LeadConvertDialog.vue`
- Modify: `CRM-Client/src/components/dialogs/OpportunityFormDialog.vue`
- Modify: `CRM-Client/src/components/system-config/ProductPanel.vue`
- Modify: `CRM-Client/src/components/system-config/__tests__/ProductPanel.test.ts`
- Modify: `CRM-Client/src/components/dialogs/__tests__/CustomerFormDialog.test.ts`
- Create: `CRM-Client/src/components/__tests__/LeadFormDialog.product.test.ts`
- Create: `CRM-Client/src/components/__tests__/LeadConvertDialog.product.test.ts`
- Create: `CRM-Client/src/components/dialogs/__tests__/OpportunityFormDialog.product.test.ts`

**Interfaces:**
- Consumes: `productApi.list`, `SegmentedChoiceControl`, `permissionStore.hasPermission('product:create'|'product:view')`
- Produces:
  - `useProductCatalog()` → `{ products, loading, forbidden, empty, load, optionsFor(currentPublicId) }`
  - `ProductIntentPicker` v-model `product_public_id`, no module UI, empty copy from spec, optional「去创建产品」link to `/settings/products?action=create` only when `product:create`
  - lead/customer/convert forms require product
  - opportunity create prefers customer active product + BASE, then first active product; edit keeps saved values
  - ProductPanel empty copy adds 「你没有创建产品的权限，请联系团队管理员」 when the user cannot create

- [ ] **Step 1: Write failing frontend tests**

Picker:
- 403 from `productApi.list` shows `没有产品查看权限`, not `操作失败`
- empty catalog shows `团队还没有可用产品，请联系管理员在「设置 → 产品管理」创建`
- `product:create` shows `去创建产品`; sales-only `product:view` does not
- options include the current inactive product for display, but submitting it is the form schema’s job

Lead form: schema requires `product_public_id`; template has no module checkboxes; submit payload includes `product_public_id`.

Customer form: create/edit schemas require `product_public_id`; submit includes it. Extend `CustomerFormDialog.test.ts` initial values rather than mounting the whole progressive-edit suite twice.

Convert: after `getLeadDetail` returns a product, `formValues.product_public_id` matches; submit body includes it; missing product blocks with `请选择产品`.

Opportunity: mock `customerApi.getCustomerDetail` with `product_public_id: 'prd_crm'` and `productApi.list` with CRM then OA; create mode selects CRM + CRM BASE, not OA. Edit mode with saved OA keeps OA even if the customer is CRM.

ProductPanel: when list is empty and permissions are only `product:view`, text includes `你没有创建产品的权限`.

- [ ] **Step 2: Implement catalog composable and picker**

`useProductCatalog`:
- `load()` calls `productApi.list()` (all statuses so inactive current values can render)
- on 403, set `forbidden = true` and toast `没有产品查看权限` via `toast.error` (do not change global `errorHandler` 403 for every API)
- `optionsFor(currentId)`: active products plus the current id if it is missing from the active list
- `empty` when there is no active product

`ProductIntentPicker.vue` uses `SegmentedChoiceControl` like `OpportunityFormDialog` product block. Empty state is a `<p class="text-sm text-wolf-text-secondary">`. Create link is a `RouterLink`/`router.push` to `/settings/products?action=create` gated on `product:create`. No module list.

- [ ] **Step 3: Wire forms**

Zod:
- `leadSchema.product_public_id = z.string().min(1, '请选择产品')`
- `customerCreateSchema` / `customerFormSchema` same; `customerEditSchema` requires it on save (`z.string().min(1, '请选择产品')`)
- `LeadResponseSchema` / `CustomerResponseSchema` add `product_public_id: z.string().nullable()`, `product_name: z.string().nullable()`, `products: z.array(z.object({ public_id: z.string(), name: z.string() })).default([])`

`LeadFormDialog`: field next to 线索来源; include in create/update payload; `applyLeadDetail` sets `product_public_id` from `lead.product_public_id ?? ''`.

`CustomerFormDialog`: field next to 客户来源; create/update payload; edit init from `customer.product_public_id`; `fieldLabels.product_public_id = '产品'`.

`LeadConvertDialog`: add `product_public_id` to `formValues` / `initialForm` / `hasFormChanges`; default from `res.product_public_id`; validate before submit like procurement method; send `product_public_id` on `convertLeadToCustomer`.

`OpportunityFormDialog.initializeForm` create branch, after customer detail loads:

```ts
const customerProduct = products.value.find(product =>
  product.public_id === customerDetail.product_public_id && product.is_active
)
const defaultProduct = customerProduct ?? firstActiveProduct()
setFieldValue('product_public_id', defaultProduct?.public_id ?? '')
setFieldValue(
  'product_module_public_ids',
  defaultProduct === undefined ? [] : defaultModulePublicIds(defaultProduct),
)
```

Call this after `await productsPromise`. Edit branch stays on `opp.product_public_id`. Replace empty copy `暂无可用产品` with the spec admin sentence. Keep “请选择产品” only after submit (`productError` already uses `submitCount`).

`ProductPanel.vue`: when `filteredProducts.length === 0` and `!canCreate`, set `empty-text` to `暂无产品。你没有创建产品的权限，请联系团队管理员`.

- [ ] **Step 4: Run focused tests**

Run: `cd CRM-Client && npm run test:unit -- src/components/crmwolf/__tests__/ProductIntentPicker.test.ts src/components/__tests__/LeadFormDialog.product.test.ts src/components/__tests__/LeadConvertDialog.product.test.ts src/components/dialogs/__tests__/CustomerFormDialog.test.ts src/components/dialogs/__tests__/OpportunityFormDialog.product.test.ts src/components/system-config/__tests__/ProductPanel.test.ts`

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/composables/useProductCatalog.ts CRM-Client/src/components/crmwolf/ProductIntentPicker.vue CRM-Client/src/schemas/lead.ts CRM-Client/src/schemas/lead-form.ts CRM-Client/src/schemas/customer.ts CRM-Client/src/schemas/customer-form.ts CRM-Client/src/api/customer.ts CRM-Client/src/components/LeadFormDialog.vue CRM-Client/src/components/dialogs/CustomerFormDialog.vue CRM-Client/src/components/LeadConvertDialog.vue CRM-Client/src/components/dialogs/OpportunityFormDialog.vue CRM-Client/src/components/system-config/ProductPanel.vue CRM-Client/src/components/crmwolf/__tests__/ProductIntentPicker.test.ts CRM-Client/src/components/__tests__/LeadFormDialog.product.test.ts CRM-Client/src/components/__tests__/LeadConvertDialog.product.test.ts CRM-Client/src/components/dialogs/__tests__/CustomerFormDialog.test.ts CRM-Client/src/components/dialogs/__tests__/OpportunityFormDialog.product.test.ts CRM-Client/src/components/system-config/__tests__/ProductPanel.test.ts
git commit -m "$(cat <<'EOF'
feat(ui): collect intent product on leads, customers, and convert

EOF
)"
```

---

### Task 7: Lists, details, search, catalog manifest

**Files:**
- Modify: `CRM-Client/src/views/Leads.vue`
- Modify: `CRM-Client/src/views/Customers.vue`
- Modify: `CRM-Client/src/views/LeadDetailSheet.vue`
- Modify: `CRM-Client/src/views/CustomerDetailSheet.vue`
- Modify: `CRM-Client/src/components/crmwolf/listQueryCatalogManifest.json` (generated)
- Test: `CRM-Server/tests/unit/list_query/test_catalog_manifest.py` (existing lock)
- Create: `CRM-Client/src/views/__tests__/leadCustomerProductColumns.test.ts` only if a cheap catalog-key test exists nearby; otherwise cover via manifest test

**Interfaces:**
- Consumes: `product_name` / `product_public_id` on list rows
- Produces: 产品 column showing name or `-`; search placeholders mention 产品; detail attribute 产品; regenerated manifest matching backend catalogs

- [ ] **Step 1: Write failing catalog/manifest expectation**

Run `cd CRM-Server && .venv/bin/python -m pytest tests/unit/list_query/test_catalog_manifest.py -q` after catalog fields exist — it should fail until the client JSON is regenerated.

- [ ] **Step 2: Add columns and detail attributes**

Leads catalog: after `source`, insert `{ key: 'product_name', label: '产品', type: 'text', column: { width: '120px' }, filter: true, sort: true }`. Cell: `{{ row.product_name || '-' }}`. Search placeholder: `搜索线索名称、联系人、手机号或产品`. Mobile meta: show product name.

Customers catalog: after `source`, same `product_name` column. Cell: `{{ row.product_name || '-' }}`. Search placeholder: `搜索客户名称、简称、别名或产品`.

`LeadDetailSheet` attributes-grid: add 产品 after 线索来源, `leadData.product_name || '-'`.

`CustomerDetailSheet` customer-info grid: add 产品 after 客户来源, `customer?.product_name || '-'`.

Do not render modules on these surfaces. Do not join product names with顿号.

- [ ] **Step 3: Regenerate manifest**

Run: `cd CRM-Server && .venv/bin/python scripts/generate_list_query_manifest.py`

Expected: prints `CRM-Client/src/components/crmwolf/listQueryCatalogManifest.json`. `leads` and `customers` catalogs include `product_name`.

- [ ] **Step 4: Run focused tests**

Run: `cd CRM-Server && .venv/bin/python -m pytest tests/unit/list_query/test_catalog_manifest.py -q`

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/views/Leads.vue CRM-Client/src/views/Customers.vue CRM-Client/src/views/LeadDetailSheet.vue CRM-Client/src/views/CustomerDetailSheet.vue CRM-Client/src/components/crmwolf/listQueryCatalogManifest.json
git commit -m "$(cat <<'EOF'
feat(lists): show intent product on leads and customers

EOF
)"
```

---

### Task 8: Verify, smoke, review

**Files:**
- Modify only if verification exposes defects in the files above.
- Do not add temporary scripts or root-level reports.

- [ ] **Step 1: Migrate**

Run: `cd CRM-Server && alembic upgrade head`

Expected: revision `134_lead_customer_product_intent` applied; `crm_lead_products` and `crm_customer_products` exist.

- [ ] **Step 2: Backend checks**

Run:

```bash
cd CRM-Server && .venv/bin/python -m pytest \
  tests/unit/test_product_intent.py \
  tests/unit/test_product_intent_migration.py \
  tests/unit/test_lead_product_intent.py \
  tests/unit/test_customer_product_intent.py \
  tests/unit/test_opportunity_product_assignment.py \
  tests/unit/test_agent_lead_customer_product_fields.py \
  tests/unit/list_query/test_catalog_manifest.py \
  tests/unit/test_customer_edit_contracts.py \
  tests/unit/api/test_customer_edit_api.py \
  -q
```

Run: `cd CRM-Server && ruff check app/crud/product_intent.py app/crud/lead.py app/crud/customer.py app/crud/product.py app/api/leads.py app/api/customers.py app/api/products.py app/schemas/lead.py app/schemas/customer.py app/core/list_query/catalogs/leads.py app/core/list_query/catalogs/customers.py app/services/agent/tool_registry.py app/services/agent/business_rules.py`

Expected: tests pass, Ruff clean.

- [ ] **Step 3: Frontend checks**

Run:

```bash
cd CRM-Client && npm run type-check
cd CRM-Client && npm run test:unit -- \
  src/components/crmwolf/__tests__/ProductIntentPicker.test.ts \
  src/components/__tests__/LeadFormDialog.product.test.ts \
  src/components/__tests__/LeadConvertDialog.product.test.ts \
  src/components/dialogs/__tests__/CustomerFormDialog.test.ts \
  src/components/dialogs/__tests__/OpportunityFormDialog.product.test.ts \
  src/components/system-config/__tests__/ProductPanel.test.ts \
  src/components/workflow/__tests__/workflowNodeRegistry.test.ts \
  src/components/workflow/__tests__/workflowValidation.test.ts
```

Expected: pass.

- [ ] **Step 4: Browser smoke**

Start the existing Vite dev server. With an authenticated session:

1. Settings → 产品管理 empty state (viewer vs creator)
2. Create CRM + OA
3. Create a lead with CRM, no module UI
4. Convert the lead; product defaults to CRM and can change to OA
5. Direct-create a customer with OA
6. New opportunity on that customer defaults to OA + BASE, not the first catalog product if OA is not first
7. Edit that customer to CRM; existing opportunity stays OA
8. Lead/customer lists show 产品
9. Stop all products and open lead create: admin copy, no silent product

If auth blocks the browser, report the blocker and rely on the focused component tests.

- [ ] **Step 5: Review**

Diff against this plan. Fail the review for: extra unique owner constraint, appending links, rewriting opportunities on customer edit, module pickers on lead/customer, 403 toast still saying 操作失败, empty catalog still saying only 暂无可用产品, missed `CustomerCreate(` test constructors, unrelated dirty files.

---

## Spec coverage

| Spec section | Task |
|---|---|
| 5 junction tables, no scalar `product_id`, migration after 133 | 1 |
| 6.1 lead replace-one-row writes | 2 |
| 6.2 customer writes, no opportunity rewrite | 3 |
| 6.3 convert copy/override/historical 400 | 3 |
| 6.4 opportunity defaults + BASE, edit preserves | 4, 6 |
| 7 API scalar+array, errors, Agent/import, catalog | 2, 3, 5, 7 |
| 8 forms, convert, lists, details | 6, 7 |
| 9 empty catalog + 403 + ProductPanel copy | 6 |
| 10 no multi-select UI, replace not append | 1, 2, 3 |
| 11 tests listed | 1–8 |
| Product delete 409 when referenced | 1 |

## Notes for implementers

- `Lead(**lead_data)` / `Customer(**customer_data)` will crash if `product_public_id` is not excluded from `model_dump`.
- Do not add `crm.create_lead` to the canvas registry; it does not exist.
- Do not change contract/License/payment schemas.
- Opportunity inactive-product message can stay `"产品不存在"` for module assignment of a missing product; empty catalog and lead/customer writes use the spec copy.
- First active product is `order_by(Product.id)` via existing `product_crud.list`.
- Frontend 403 handling belongs in `useProductCatalog`, not a global `errorHandler` rewrite.
)