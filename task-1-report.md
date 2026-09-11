# Task 1 report

## Changes
- `CRM-Server/app/services/agent/turns.py`: added `AgentTurnRepository.list_owned_by_ids`, including owned-session validation, exact owner/session filters, empty-ID handling, canonical persisted-record conversion, and stable database order.
- `CRM-Server/app/services/agent/async_operation_service.py`: added owner/session-scoped `list_session_history_page`, querying stable `(created_time DESC, id DESC)` order, applying offset/limit, reversing each page to display order, and returning total count.
- `CRM-Server/app/api/agent.py`: added exact-message anchor route and paginated operation-history route. Both validate ownership. Anchor responses use canonical persisted `crm.agent.ui.v1` envelopes and the shared read-time action projection. History applies existing recovery/read-repair behavior without business execution. Existing live `/sessions/{session_id}/operations` route remains semantically unchanged.
- `CRM-Server/tests/unit/test_agent_api.py`: added HTTP ownership/canonical-envelope anchor coverage, including repeated, missing, duplicate, and cross-owner IDs.
- `CRM-Server/tests/unit/test_agent_async_operations_api.py`: added HTTP pagination and stable ordering coverage.

## TDD evidence
### RED
Commands (from `CRM-Server`, with `PYTHONPATH=.`):
- `pytest tests/unit/test_agent_api.py -k 'anchor_endpoint' -v`
  - Failed at the new test assertion with `assert 404 == 200`; route was not registered.
- `pytest tests/unit/test_agent_async_operations_api.py -k 'history_is_paginated' -v`
  - Failed with HTTP `404 Not Found`; route was not registered.

The system Python did not have pytest. Tests were run through `uv run --with-requirements requirements-dev.txt`; the first run also required `PYTHONPATH=.` because the repository app package is not installed into the temporary environment.

### GREEN
Commands:
- `uv run --with-requirements requirements-dev.txt pytest -o addopts='' tests/unit/test_agent_api.py -k 'anchor_endpoint' -v`
  - `1 passed, 14 deselected`; exit 0.
- `uv run --with-requirements requirements-dev.txt pytest -o addopts='' tests/unit/test_agent_async_operations_api.py -k 'history_is_paginated' -v`
  - `1 passed, 4 deselected`; exit 0.
- `python3 -m py_compile app/api/agent.py app/services/agent/turns.py app/services/agent/async_operation_service.py app/schemas/agent.py`
  - passed.

The focused tests emit pre-existing Pydantic deprecation/protected-namespace warnings. `-o addopts=''` was used to avoid the repository's project-wide coverage threshold from turning a focused one-test run into a nonzero exit.

## Self-review
- Ownership is checked at the API boundary and again through repository/service owner filters.
- Anchor reads never synthesize missing messages and only return canonical persisted envelopes.
- Action state is projected through the existing `project_interaction_action_states` path for both regular history and anchors, preserving fail-closed behavior.
- Operation history is read-only, paginated, owner/session scoped, stable newest-first at query time, and reversed per page for display order.
- No LangGraph, durable execution, leases, retries, customer-intelligence execution, or production data behavior was changed.
