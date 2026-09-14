# 产品与模块管理 MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a team-scoped product and module configuration MVP in the Settings center with explicit product permissions and a mandatory base module.

**Architecture:** Add two team-scoped SQLAlchemy models (`Product`, `ProductModule`) behind a typed CRUD/API boundary. Product creation creates its `BASE` module in one transaction; module mutations remain product-scoped and reject base-module deletion/deactivation. The frontend reuses the existing Settings navigation, `SettingsModulePage`, `ListCard`, shadcn dialogs/forms, and the permission store for read-only versus maintenance behavior.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic v2, pytest, Vue 3, Pinia, TypeScript, Zod, vee-validate, shadcn-vue.

## Global Constraints

- Do not touch unrelated dirty worktree changes.
- Product API authorization MUST use `product:view`, `product:create`, `product:edit`, and `product:delete`; no `TEAM_ADMIN`, owner, or `system:config` bypass in product endpoints.
- Every product and module query MUST be filtered by the current `team_id`.
- Each product has at most one `BASE` module; the base module is auto-created as `BASE`/`BASE` with display name `基础版`, cannot be deleted or deactivated, and add-on modules use `ADD_ON`.
- No strong version entity, product-to-contract/opportunity/License associations, product recommendation, or approval-Agent behavior in this MVP.
- Database changes MUST be delivered through Alembic migration.
- Frontend must follow `CRM-Docs/design-system/` and reuse existing Settings/config-panel components.
- New TypeScript code must not use `any`, `as any`, `@ts-ignore`, or unnecessary non-null assertions.
- Each implementation task writes focused tests; full validation runs once after all independent changes land.

---

### Task 1: Add product domain models, schemas, CRUD, and migration

**Files:**
- Create: `CRM-Server/app/models/product.py`
- Create: `CRM-Server/app/schemas/product.py`
- Create: `CRM-Server/app/crud/product.py`
- Create: `CRM-Server/migrations/versions/132_product_module_catalog.py`
- Modify: `CRM-Server/app/models/__init__.py`
- Test: `CRM-Server/tests/unit/test_product_crud.py`

**Interfaces:**
- `Product` and `ProductModule` are imported through `app.models`.
- `ProductModuleRole.BASE` and `.ADD_ON` are stable strings.
- `ProductCRUD` exposes `list`, `get_by_public_id`, `create`, `update`, `delete`, `create_module`, `update_module`, and `delete_module` methods used by the API task.
- Product response schemas expose public IDs and nested modules; no internal ID is required by the frontend.

- [ ] **Step 1: Write failing domain tests**

Test the public CRUD behavior: creating a product creates one base module; a second base module is rejected; base module deletion/deactivation is rejected; module and product lookup never crosses `team_id`; duplicate codes are rejected.

- [ ] **Step 2: Implement the models and typed schemas**

Use `generate_public_id("prd")` and `generate_public_id("prm")`, team-scoped unique constraints, product-to-module cascade, timestamps using `business_now`, and `module_role` constrained to `BASE`/`ADD_ON` at the domain boundary.

- [ ] **Step 3: Implement CRUD transaction rules**

`create` must flush the product, add the default base module, commit once, and refresh the product. All lookup methods include team ID. `delete_module` rejects `BASE` and `is_active=0` updates for base modules. Duplicate code and missing cross-team objects raise `ValueError` with stable Chinese messages.

- [ ] **Step 4: Add Alembic migration 132**

Create `crm_products` and `crm_product_modules`, indexes and team/product code uniqueness, then idempotently insert the four product permissions and assign `product:view` to `SALES_MEMBER` and `SALES_DIRECTOR`. Do not add a role bypass in application code. Downgrade removes role links, permissions, indexes, and tables in reverse dependency order.

- [ ] **Step 5: Run focused domain tests**

Run: `cd CRM-Server && python -m pytest tests/unit/test_product_crud.py -q`

Expected: all product CRUD tests pass.

---

### Task 2: Add product API and permission boundaries

**Files:**
- Create: `CRM-Server/app/api/products.py`
- Modify: `CRM-Server/app/main.py`
- Modify: `CRM-Server/app/constants/permissions.py`
- Test: `CRM-Server/tests/unit/api/test_products_api.py`

**Interfaces:**
- Routes are under `/v1/products`.
- Product list/detail require `product:view`.
- Product create requires `product:create`.
- Product/product-module update requires `product:edit`.
- Product delete/module delete require `product:delete` for product deletion and `product:edit` for module deletion.
- API returns typed Pydantic responses and maps domain `ValueError` to 400/409 without leaking cross-team existence.

- [ ] **Step 1: Write failing API authorization tests**

Cover each permission boundary, cross-team 404 behavior, product creation response containing the base module, module CRUD, and base-module deletion/deactivation rejection.

- [ ] **Step 2: Register permission definitions and API router**

Add the four codes to `ALL_PERMISSIONS`, add `product:view` to the Sales Director and Sales Member mappings, import the router in `main.py`, and preserve existing `TEAM_ADMIN: "all"` initialization semantics.

- [ ] **Step 3: Implement typed FastAPI routes**

Use `get_current_user_team`, `get_db`, and `require_permission` dependencies. Never inspect role names. Resolve product and module through team-scoped CRUD methods before mutation. Return products with nested modules sorted by `sort_order` and `id`.

- [ ] **Step 4: Run focused API tests**

Run: `cd CRM-Server && python -m pytest tests/unit/api/test_products_api.py -q`

Expected: all product API tests pass.

---

### Task 3: Add Settings navigation, frontend API/schema, and product panel

**Files:**
- Create: `CRM-Client/src/schemas/product.ts`
- Create: `CRM-Client/src/api/product.ts`
- Create: `CRM-Client/src/components/system-config/ProductPanel.vue`
- Create: `CRM-Client/src/components/system-config/__tests__/ProductPanel.test.ts`
- Modify: `CRM-Client/src/settingsNavigation.ts`
- Modify: `CRM-Client/src/composables/useSettingsAccess.ts`
- Modify: `CRM-Client/src/views/SettingsModulePage.vue`
- Modify: `CRM-Client/src/constants/permissions.ts`
- Modify: `CRM-Client/src/settingsNavigation.test.ts`

**Interfaces:**
- Settings item ID: `products`; path: `/settings/products`; required entry permission: `product:view`; owner bypass disabled for this item.
- `productApi.list/create/update/delete/createModule/updateModule/deleteModule` parse all responses with Zod schemas.
- `ProductPanel` accepts the existing shell props `{ active?: boolean; embedded?: boolean; action?: 'create' | 'edit'; recordId?: string }`.

- [ ] **Step 1: Write failing navigation/API/panel tests**

Test the canonical Settings registry entry, owner bypass disabled for products, read-only users seeing products without maintenance buttons, and an editor seeing the product/module configuration actions. Mock only the API boundary as existing Settings panel tests do.

- [ ] **Step 2: Implement Zod schemas and API client**

Model `BASE`/`ADD_ON`, product/module response and create/update payloads. Keep public IDs as strings and normalize boolean flags with the existing preprocessing convention.

- [ ] **Step 3: Implement the product panel**

Reuse `ScrollArea`, `ListCard`, `Button`, `Input`, `Badge`, `Dialog`, `FormField`, `FormControl`, `FormItem`, `FormLabel`, `FormMessage`, `Textarea`, `Select`, `confirmDialog`/`confirmDelete`, `toast`, and `handleApiError`. Provide search/status filtering, product create/edit/delete/toggle, nested module list, add-on create/edit/delete/toggle, and a visibly protected base module. Keep read-only rendering when permissions are absent.

- [ ] **Step 4: Wire the Settings registry and owner-bypass exception**

Add the Products navigation item, async component mapping, descriptions, `product` resource label, and `allowOwnerBypass: false` support in `useSettingsAccess`/`SettingsModulePage`. Do not change existing modules’ default owner behavior.

- [ ] **Step 5: Run focused frontend tests**

Run: `cd CRM-Client && npm run test:unit -- src/settingsNavigation.test.ts src/components/system-config/__tests__/ProductPanel.test.ts`

Expected: all focused frontend tests pass.

---

### Task 4: Run migration, type/lint checks, smoke-test the real UI, and review

**Files:**
- Modify only if verification exposes defects in the files above.
- Do not add temporary scripts or root-level reports.

- [ ] **Step 1: Validate database migration**

Run: `cd CRM-Server && alembic upgrade head`

Expected: migration 132 applies successfully and creates both product tables and permissions.

- [ ] **Step 2: Run backend checks**

Run: `cd CRM-Server && python -m pytest tests/unit/test_product_crud.py tests/unit/api/test_products_api.py -q` and `ruff check app/models/product.py app/schemas/product.py app/crud/product.py app/api/products.py tests/unit/test_product_crud.py tests/unit/api/test_products_api.py`.

Expected: focused tests pass and Ruff reports no errors.

- [ ] **Step 3: Run frontend checks**

Run: `cd CRM-Client && npm run type-check && npm run lint -- src/settingsNavigation.ts src/composables/useSettingsAccess.ts src/api/product.ts src/schemas/product.ts src/components/system-config/ProductPanel.vue`

Expected: type-check and targeted lint pass.

- [ ] **Step 4: Start the actual frontend and visually verify**

Launch the existing Vite dev server, open `/settings/products` in Chromium with an authenticated session if available, and verify the Settings entry, loading/empty states, product form, base-module badge/protection, add-on module form, and read-only behavior. If authentication/data prevents browser verification, report the exact blocker and run the closest component smoke test instead.

- [ ] **Step 5: Request final code review**

Review the branch diff against this plan, with special attention to team isolation, permission bypasses, base-module invariants, and unrelated dirty-file changes. Fix all Critical/Important findings before claiming completion.
