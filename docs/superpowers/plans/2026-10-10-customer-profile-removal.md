# Customer Profile Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the customer-profile capability and physically delete the nine non-alias customer fact types and every proven derived copy.

**Architecture:** First close every runtime read and write path, then replace profile routes with a uniform 410 tombstone, then add two Alembic revisions that clean shared data and drop profile-only tables around a verified Qdrant deletion step. Shared intelligence, checkpoint, memory, and vector infrastructure remains.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, MySQL, LangGraph checkpoints, Qdrant, Vue 3, Vitest, Pytest.

## Global Constraints

- Delete exactly `need`, `budget`, `risk`, `stage`, `stakeholder_attitude`, `competitor`, `next_step`, `preference`, and `summary`.
- Keep `alias` facts, sources, and revisions for identity resolution only; never inject them into customer answers.
- Old profile routes return HTTP 410 and `code = CUSTOMER_PROFILE_REMOVED` before customer, team, permission, or profile-table access.
- Keep customers, contacts, activities, activity deletion tombstones, opportunities, contracts, payments, journeys and events, commitments, follow-up tasks and events.
- Keep raw-CRM customer Q&A, business semantic retrieval, qualified Qdrant evidence, and profile-independent initial enrichment.
- Do not delete shared tables named for customer intelligence, checkpoints, agent memory, or vectors.
- Do not keyword-delete raw activity text; opportunity sales stages remain.
- Qdrant points must be verified absent before their MySQL metadata is deleted.
- Database changes use Alembic only. No `create_all`, stamp, manual `alembic_version` edit, ad hoc SQL bypass, or downgrade-based data recovery.
- The missing `151_assistant_proposal_policy` revision must be restored from an approved repository source before cleanup revisions run.
- Do not touch shared `crm-mysql-dev`, `CRM-Server/.env`, port 8000, unrelated containers, or existing dirty worktree changes.
- Verification output contains counts, hashes, and pass/fail only.

## File Structure

- `CRM-Server/app/api/customer_profiles.py`: profile tombstone routes only.
- `CRM-Server/app/services/customer_fact_service.py`: alias-only fact contract.
- `CRM-Server/app/services/customer_intelligence_context_service.py`: raw-CRM context without profile facts or legacy progress.
- `CRM-Server/app/services/agent/customer_intelligence_graph.py`: Q&A and evidence-reference path only.
- `CRM-Server/app/services/customer_memory_store_service.py`: retrieval-reference contract only.
- `CRM-Server/app/services/customer_intelligence_run_service.py`: safe run summaries.
- `CRM-Server/app/services/agent/tools/service.py`: activity writes without profile receipts.
- `CRM-Server/app/services/agent/assistant/contracts.py`, `crm_proposal_commands.py`, `proposals.py`: no nine-type fact proposals.
- `CRM-Server/app/main.py`: no profile scheduler registration.
- `CRM-Server/migrations/versions/152_remove_customer_profile_prepare.py`: data cleanup and Qdrant deletion marking.
- `CRM-Server/migrations/versions/153_remove_customer_profile_complete.py`: metadata and profile-table removal.
- `CRM-Client/src/views/CustomerDetailSheet.vue` and profile components/API: remove profile UI.
- Tests live beside the existing unit suites under `CRM-Server/tests/unit/` and `CRM-Client/src`.

---

### Task 1: Restore the Alembic Chain Gate

**Files:**
- Modify: the approved migration that defines revision `151_assistant_proposal_policy`
- Test: `CRM-Server/tests/unit/test_alembic_revision_chain.py`

**Interfaces:**
- Consumes: existing revision `150_profile_version_attestation`.
- Produces: revision `151_assistant_proposal_policy` with `down_revision = "150_profile_version_attestation"`.

- [ ] **Step 1: Write the failing chain test**

```python
def test_revision_151_is_present_and_descends_from_150() -> None:
    script = ScriptDirectory.from_config(alembic_config())
    revision = script.get_revision("151_assistant_proposal_policy")
    assert revision is not None
    assert revision.down_revision == "150_profile_version_attestation"
    assert script.get_current_head() != "150_profile_version_attestation"
```

- [ ] **Step 2: Run the test and verify RED**

Run: `cd CRM-Server && ./venv/bin/pytest tests/unit/test_alembic_revision_chain.py -q`

Expected: FAIL because revision `151_assistant_proposal_policy` cannot be located.

- [ ] **Step 3: Restore only the approved revision**

Restore the approved migration from repository history. Verify its revision ID, `down_revision`, and upgrade/downgrade functions match the approved source. Do not stamp a database or execute cleanup.

- [ ] **Step 4: Run the test and verify GREEN**

Run the same Pytest command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/migrations/versions/*151_assistant_proposal_policy*.py CRM-Server/tests/unit/test_alembic_revision_chain.py
git commit -m "fix: restore approved assistant proposal revision"
```

### Task 2: Make Activity Writes Independent of Profile Receipts

**Files:**
- Modify: `CRM-Server/app/services/agent/tools/service.py`
- Test: `CRM-Server/tests/unit/test_agent_activity_write_without_profile_receipt.py`

**Interfaces:**
- Consumes: existing activity write result.
- Produces: successful activity persistence when `intelligence_request_id` is absent; no profile extraction exception.

- [ ] **Step 1: Write the failing behavior test**

```python
def test_activity_write_succeeds_without_profile_receipt(db_session) -> None:
    result = service.write_customer_activity(db_session, payload_without_receipt())
    assert result.activity.id is not None
    assert result.customer_intelligence_request is None
```

- [ ] **Step 2: Run it and verify RED**

Run the new test. Expected: FAIL with the current missing profile-extraction receipt error.

- [ ] **Step 3: Remove the receipt requirement**

Delete the branch that raises when profile extraction receipt data is absent. Preserve activity persistence, deletion tombstones, task reconciliation, and post-commit scheduling. An intelligence scheduling error is returned as diagnostic data and never rolls back the activity transaction.

- [ ] **Step 4: Verify GREEN**

Run the new test. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/agent/tools/service.py CRM-Server/tests/unit/test_agent_activity_write_without_profile_receipt.py
git commit -m "fix: persist activities without profile receipts"
```

### Task 3: Restrict Customer Facts to Alias

**Files:**
- Modify: `CRM-Server/app/services/customer_fact_service.py`
- Modify: `CRM-Server/app/services/customer_fact_extraction_service.py`
- Test: `CRM-Server/tests/unit/test_customer_fact_service.py`

**Interfaces:**
- Consumes: `CustomerFactType`.
- Produces: `ALLOWED_CUSTOMER_FACT_TYPES = frozenset({"alias"})`; rejected nine-type writes raise `CustomerFactTypeRemoved`.

- [ ] **Step 1: Add rejection tests**

Assert each of the nine removed types is rejected by validation, assessment, and upsert. Assert an alias fact, source, and revision can still be written and read by the identity path.

- [ ] **Step 2: Verify RED**

Run `test_customer_fact_service.py`. Expected: FAIL because the nine types are currently accepted.

- [ ] **Step 3: Implement the alias-only contract**

Change the public fact type to alias only, reject all nine types before database access, and remove extraction prompts and result schemas that emit them. Do not delete historical rows in this task.

- [ ] **Step 4: Verify GREEN**

Run the fact-service tests. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/customer_fact_service.py CRM-Server/app/services/customer_fact_extraction_service.py CRM-Server/tests/unit/test_customer_fact_service.py
git commit -m "feat: restrict customer facts to alias"
```

### Task 4: Remove Nine-Type Fact Proposals

**Files:**
- Modify: `CRM-Server/app/services/agent/assistant/contracts.py`
- Modify: `CRM-Server/app/services/agent/assistant/crm_proposal_commands.py`
- Modify: `CRM-Server/app/services/agent/assistant/proposals.py`
- Test: `CRM-Server/tests/unit/test_customer_fact_proposals_removed.py`

**Interfaces:**
- Consumes: `ALLOWED_CUSTOMER_FACT_TYPES` from Task 3.
- Produces: proposal validation error `CUSTOMER_FACT_TYPE_REMOVED` for all nine types.

- [ ] **Step 1: Write rejection tests**

Submit one proposal payload for each removed type and assert validation fails before a command or database write. Assert no customer-fact hint is generated from removed context.

- [ ] **Step 2: Verify RED**

Expected: FAIL because current proposal contracts accept the removed types.

- [ ] **Step 3: Remove the proposal path**

Delete the nine types from proposal literals, command validation, execution, and hint generation. Do not add a new alias-management proposal flow.

- [ ] **Step 4: Verify GREEN**

Expected: PASS, with no fact-proposal command executed.

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/agent/assistant CRM-Server/tests/unit/test_customer_fact_proposals_removed.py
git commit -m "feat: reject removed customer fact proposals"
```

### Task 5: Build Raw-CRM Customer Context

**Files:**
- Modify: `CRM-Server/app/services/customer_intelligence_context_service.py`
- Modify: `CRM-Server/app/services/customer_context_answer_service.py`
- Test: `CRM-Server/tests/unit/test_customer_intelligence_context_service.py`

**Interfaces:**
- Consumes: raw CRM models and qualified evidence hits.
- Produces: `CustomerStrongContext` with `customer_facts=()` always and no legacy-progress query.

- [ ] **Step 1: Write context tests**

Create alias and all nine fact types. Assert context facts are empty, legacy progress is not queried, and customer, contact, activity, journey, commitment, task, opportunity, contract, and payment data remain present.

- [ ] **Step 2: Verify RED**

Expected: FAIL because all facts are currently included.

- [ ] **Step 3: Remove forbidden context inputs**

Delete fact loading, fact watermarks, fact snapshot entries, and `CustomerLegacySourceProgress` access. Ensure answer fallback never reads facts or Store summaries.

- [ ] **Step 4: Verify GREEN**

Expected: PASS. A question without raw evidence returns the insufficient-information result.

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/customer_intelligence_context_service.py CRM-Server/app/services/customer_context_answer_service.py CRM-Server/tests/unit/test_customer_intelligence_context_service.py
git commit -m "feat: answer customers from raw CRM context"
```

### Task 6: Shrink Memory to Evidence References

**Files:**
- Modify: `CRM-Server/app/services/customer_memory_store_service.py`
- Test: `CRM-Server/tests/unit/test_customer_memory_store_service.py`

**Interfaces:**
- Consumes: evidence source type, source object ID, document key, and score.
- Produces: `EvidenceReference` and `build_context_payload()` returning only `retrieval`.

- [ ] **Step 1: Write memory contract tests**

Assert facts, preferences, and summaries are rejected. Assert retrieval entries containing prose, fact IDs, citations, or unknown fields are rejected. Assert a minimal evidence reference round-trips.

- [ ] **Step 2: Verify RED**

Expected: FAIL because all four sections are writable and readable.

- [ ] **Step 3: Implement the reference-only contract**

Remove the three forbidden write methods from the public service and validate retrieval keys against `{"source_type", "source_object_id", "document_key", "score"}`. Context payload exposes retrieval only.

- [ ] **Step 4: Verify GREEN**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/customer_memory_store_service.py CRM-Server/tests/unit/test_customer_memory_store_service.py
git commit -m "feat: retain only customer evidence references"
```

### Task 7: Remove Fact Extraction and Profile Routes from the Graph

**Files:**
- Modify: `CRM-Server/app/services/agent/customer_intelligence_graph.py`
- Modify: `CRM-Server/app/services/customer_intelligence_run_service.py`
- Test: `CRM-Server/tests/unit/test_customer_intelligence_graph.py`
- Test: `CRM-Server/tests/unit/test_customer_intelligence_run_service.py`

**Interfaces:**
- Consumes: raw context from Task 5 and `EvidenceReference` from Task 6.
- Produces: routes `answer_context`, `write_evidence_memory`, and `skip`; no fact or profile state fields.

- [ ] **Step 1: Write graph behavior tests**

Assert a customer question reaches `answer_context`; a committed CRM event writes only an evidence reference; manual profile refresh, rebuild, backfill, and reconciliation return `skip`. Assert run summaries contain no profile or fact payload.

- [ ] **Step 2: Verify RED**

Expected: FAIL because extraction, fact persistence, and profile refresh remain reachable.

- [ ] **Step 3: Remove the forbidden graph path**

Delete extraction, assessment, fact persistence, profile draft, summary memory, and fact-index nodes and state. Keep Q&A and qualified evidence-reference writing. Reduce run summaries to status, attempts, errors, route, and safe evidence references.

- [ ] **Step 4: Verify GREEN**

Run both targeted test modules. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/agent/customer_intelligence_graph.py CRM-Server/app/services/customer_intelligence_run_service.py CRM-Server/tests/unit/test_customer_intelligence_graph.py CRM-Server/tests/unit/test_customer_intelligence_run_service.py
git commit -m "feat: remove profile and fact writes from intelligence"
```

### Task 8: Replace Profile Routes with a Uniform Tombstone

**Files:**
- Modify: `CRM-Server/app/api/customer_profiles.py`
- Modify: `CRM-Server/app/api/customers.py`
- Test: `CRM-Server/tests/unit/test_customer_profile_tombstone.py`

**Interfaces:**
- Consumes: no customer or profile service.
- Produces: `customer_profile_removed()` returning status 410 and the stable JSON error body.

- [ ] **Step 1: Write tombstone tests**

Call profile, changes, evidence, journeys, follow-ups, versions, and refresh routes with nonexistent IDs and without permissions. Assert every response is identical: HTTP 410 and `CUSTOMER_PROFILE_REMOVED`. Assert no customer or profile query method is called.

- [ ] **Step 2: Verify RED**

Expected: FAIL with current 200, 403, or 404 behavior.

- [ ] **Step 3: Implement direct tombstones**

Replace handlers with the direct 410 response. Remove profile-only refresh, regenerate, and rebuild handlers from `customers.py`. Preserve unrelated customer endpoints and their existing authorization behavior.

- [ ] **Step 4: Verify GREEN**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/api/customer_profiles.py CRM-Server/app/api/customers.py CRM-Server/tests/unit/test_customer_profile_tombstone.py
git commit -m "feat: return gone for removed customer profiles"
```

### Task 9: Remove Profile Runtime, Permissions, and Schedulers

**Files:**
- Delete profile-only service, schema, model, CRUD, and task modules identified by failing imports.
- Modify: `CRM-Server/app/main.py`
- Modify: `CRM-Server/app/models/__init__.py`
- Modify: permission seed definitions.
- Test: `CRM-Server/tests/unit/test_customer_profile_runtime_removed.py`

**Interfaces:**
- Consumes: tombstone router from Task 8.
- Produces: an application import graph with no profile projection, legacy progress, or profile scheduler symbols.

- [ ] **Step 1: Write an import and startup test**

Import the FastAPI app and assert profile scheduler start functions are absent from startup. Assert profile permissions are absent from seeds and no module imports the three profile-only models.

- [ ] **Step 2: Verify RED**

Expected: FAIL because current startup and exports include them.

- [ ] **Step 3: Delete the unused runtime**

Remove profile-only modules, exports, permission seeds, and scheduler startup/shutdown calls. Keep evidence sync, raw CRM intelligence health, and initial enrichment.

- [ ] **Step 4: Verify GREEN**

Run the runtime removal test and `./venv/bin/python -c "from app.main import app"`. Expected: PASS and successful import.

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app CRM-Server/tests/unit/test_customer_profile_runtime_removed.py
git commit -m "refactor: remove customer profile runtime"
```

### Task 10: Remove the Frontend Profile Surface

**Files:**
- Modify: `CRM-Client/src/views/CustomerDetailSheet.vue`
- Delete: `CRM-Client/src/api/customerProfile.ts`
- Delete: `CRM-Client/src/components/panels/CustomerProfileContent.vue`
- Modify: agent operation labels and permission localization tests.

**Interfaces:**
- Consumes: backend 410 contract, but the UI no longer calls profile routes.
- Produces: customer detail navigation without a profile tab or profile loading.

- [ ] **Step 1: Write a component test**

Render customer detail and assert no profile tab, profile request, refresh action, or profile-evidence panel exists. Assert customer information, activities, and journeys remain.

- [ ] **Step 2: Verify RED**

Run the targeted Vitest file. Expected: FAIL because the profile tab is rendered.

- [ ] **Step 3: Remove profile UI**

Delete profile API calls, stores, refresh polling, permissions, and components. Update agent copy so removed profile work is not described as customer-profile updating. Preserve all raw CRM panels.

- [ ] **Step 4: Verify GREEN**

Run the targeted Vitest file. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src
git commit -m "feat: remove customer profile interface"
```

### Task 11: Add the Alembic Prepare Revision

**Files:**
- Create: `CRM-Server/migrations/versions/152_remove_customer_profile_prepare.py`
- Test: `CRM-Server/tests/unit/test_customer_profile_removal_prepare_migration.py`

**Interfaces:**
- Consumes: revisions through `151_assistant_proposal_policy`.
- Produces: `upgrade()` that deletes nine-type facts, forbidden memory and checkpoints, profile-only runs, and marks ineligible vectors `DELETE_PENDING` without dropping shared tables.

- [ ] **Step 1: Write migration behavior tests on an isolated schema**

Seed alias and nine-type facts, all memory sections, one safe evidence checkpoint, one unsafe checkpoint, one profile-only run, and one rebuildable vector. After upgrade assert only alias, safe retrieval, safe checkpoint, and `DELETE_PENDING` ineligible vectors remain.

- [ ] **Step 2: Verify RED**

Expected: FAIL because revision 152 does not exist.

- [ ] **Step 3: Implement the prepare upgrade**

Use deterministic SQL and the existing checkpoint safety inspector. Delete fact sources and revisions before facts. Delete complete checkpoint identities rather than editing serialized payloads. Do not call Qdrant or drop tables.

- [ ] **Step 4: Verify GREEN**

Run the migration test against the isolated test schema. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/migrations/versions/152_remove_customer_profile_prepare.py CRM-Server/tests/unit/test_customer_profile_removal_prepare_migration.py
git commit -m "feat: prepare customer profile data removal"
```

### Task 12: Verify Qdrant Deletion Before Metadata Removal

**Files:**
- Create: `CRM-Server/app/services/customer_profile_vector_retirement_service.py`
- Test: `CRM-Server/tests/unit/test_customer_profile_vector_retirement_service.py`

**Interfaces:**
- Consumes: rows with `sync_status = DELETE_PENDING` from Task 11.
- Produces: `retire_pending_documents(db, qdrant) -> RetirementReport` with `pending_count`, `deleted_count`, and `verified_absent_count`.

- [ ] **Step 1: Write service tests**

Use a fake Qdrant client. Assert the service deletes only the prepared IDs, re-reads each point, and fails if any point remains. Assert it does not delete MySQL rows.

- [ ] **Step 2: Verify RED**

Expected: FAIL because the service does not exist.

- [ ] **Step 3: Implement the service**

Delete points in bounded batches, verify absence by ID, and return counts only. On mismatch raise `VectorRetirementIncomplete` and leave metadata unchanged.

- [ ] **Step 4: Verify GREEN**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/customer_profile_vector_retirement_service.py CRM-Server/tests/unit/test_customer_profile_vector_retirement_service.py
git commit -m "feat: verify retired customer evidence points"
```

### Task 13: Add the Alembic Completion Revision

**Files:**
- Create: `CRM-Server/migrations/versions/153_remove_customer_profile_complete.py`
- Test: `CRM-Server/tests/unit/test_customer_profile_removal_complete_migration.py`

**Interfaces:**
- Consumes: successful `RetirementReport` evidence and revision 152.
- Produces: dropped `crm_customer_profile_current`, `crm_customer_profile_projection_versions`, and `crm_customer_legacy_source_progress`; no pending target vector rows.

- [ ] **Step 1: Write completion tests**

Assert upgrade fails while a target row remains `DELETE_PENDING`. After all target points are verified, assert target metadata and the three profile-only tables are gone while shared tables and alias facts remain.

- [ ] **Step 2: Verify RED**

Expected: FAIL because revision 153 does not exist.

- [ ] **Step 3: Implement ordered schema removal**

Check the Qdrant verification marker, delete verified target metadata, drop `crm_customer_profile_current` before `crm_customer_profile_projection_versions`, drop legacy progress, and remove obsolete foreign keys. Do not implement data-restoring downgrade.

- [ ] **Step 4: Verify GREEN**

Run the completion test on the isolated schema. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/migrations/versions/153_remove_customer_profile_complete.py CRM-Server/tests/unit/test_customer_profile_removal_complete_migration.py
git commit -m "feat: drop removed customer profile storage"
```

### Task 14: Run the Isolated Release Rehearsal

**Files:**
- Modify: `CRM-Docs/deployment/customer-profile-removal-runbook.md`
- Test: isolated clone rehearsal evidence, not shared `crm-mysql-dev`.

**Interfaces:**
- Consumes: revisions 151–153 and `retire_pending_documents()`.
- Produces: sanitized before/after counts and smoke results.

- [ ] **Step 1: Write the runbook checks**

Document backup verification, process stop, revision gate, prepare upgrade, Qdrant retirement, completion upgrade, residue scans, and the ten startup smoke checks from the spec.

- [ ] **Step 2: Rehearse on the isolated clone**

Run the documented commands against the isolated database and Qdrant only. Expected: every gate passes and output contains counts and statuses only.

- [ ] **Step 3: Record evidence**

Save sanitized counts and pass/fail results in the deployment record. Do not include DSNs, customer identifiers, source text, document keys, or vector text.

- [ ] **Step 4: Commit**

```bash
git add CRM-Docs/deployment/customer-profile-removal-runbook.md
git commit -m "docs: add customer profile removal runbook"
```

## Self-Review

- Spec coverage: Tasks 1–14 cover revision repair, runtime closure, tombstone, shared cleanup, Qdrant ordering, schema removal, and release verification.
- Placeholder scan: no unresolved implementation markers or nonspecific test instructions remain.
- Type consistency: `ALLOWED_CUSTOMER_FACT_TYPES`, `EvidenceReference`, `customer_profile_removed()`, and `retire_pending_documents()` use the same names across tasks.
