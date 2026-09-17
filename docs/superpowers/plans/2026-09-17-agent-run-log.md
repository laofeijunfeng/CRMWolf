# Agent Run Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admins can open Settings → Agent 运行日志, filter any teammate's Agent turns, and inspect the six-step process for that turn without opening the salesperson's chat.

**Architecture:** Persist a closed `turn_observability` object on the assistant message `diagnostics_json` at turn commit. Thread follow-up quality onto Workflow waiting results so blocked scores are visible. List/detail APIs reconstruct a row from the user+assistant pair plus that object. Settings uses a dedicated page (not the chat UI).

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Vue 3, Zod, existing Sheet/DataTable patterns.

## Global Constraints

- Do not add a new observability table; reuse `crm_agent_messages.diagnostics_json`.
- Keep `diagnostics.durable_work` readable by `AgentDurableWorkRecoveryService` (`diagnostics.get("durable_work")`).
- Keep existing `dispatch_type` / `decision` keys.
- Chat UI must not gain a "过程" entry.
- Permission matches AI 配置: any of `ai:read`, `ai:manage`, `system:config`.
- Team-scoped; owner bypass allowed (same as AI 配置).
- No LangSmith/Langfuse in this change.
- TDD: failing test before production code.
- Work in `.worktrees/agent-run-log` on `feat/agent-run-log`.

---

### Task 1: Turn timeline contract

**Files:**
- Create: `CRM-Server/app/services/agent/run_log.py`
- Test: `CRM-Server/tests/unit/test_agent_run_log.py`

**Interfaces:**
- Produces: `TurnTimeline`, `TurnTimelineStep`, `build_turn_timeline(dispatch, *, user_text: str, model: str | None = None) -> TurnTimeline`

- [ ] Write failing tests for quality-blocked, query-answered, and confirmation-waiting timelines.
- [ ] Implement `build_turn_timeline` from `RootDispatchResult`.
- [ ] Commit.

### Task 2: Thread quality onto waiting Workflow results

**Files:**
- Modify: `CRM-Server/app/services/agent/workflow/contracts.py`
- Modify: `CRM-Server/app/services/agent/workflow/planning.py`
- Modify: `CRM-Server/app/services/agent/workflow/graph.py`
- Modify: `CRM-Server/app/services/agent/orchestrator/graph.py`
- Test: `CRM-Server/tests/unit/test_agent_workflow_subgraph.py`

**Interfaces:**
- Produces: `WorkflowQualityGate` on `WorkflowPlanningNeedsInput`, `WorkflowInterruptPayload`, `WorkflowWaitingResult`

- [ ] Extend quality-supplement test to assert `waiting.workflow_result.quality_gate.score == 45`.
- [ ] Thread the gate through NeedsInput → subgraph state → interrupt payload → waiting result.
- [ ] Commit.

### Task 3: Persist timeline on assistant diagnostics

**Files:**
- Modify: `CRM-Server/app/services/agent/application.py`
- Test: `CRM-Server/tests/unit/test_agent_ui_application.py`

**Interfaces:**
- Consumes: `build_turn_timeline`
- Produces: `diagnostics_json["turn_observability"]` plus existing `dispatch_type` / `decision` / `durable_work`

- [ ] Assert a text workflow/query turn stores `turn_observability`.
- [ ] Keep failure diagnostics including `dispatch_type: failure`.
- [ ] Commit.

### Task 4: List and detail APIs

**Files:**
- Create: `CRM-Server/app/schemas/agent_run_log.py`
- Modify: `CRM-Server/app/crud/agent.py`
- Modify: `CRM-Server/app/api/agent.py`
- Test: `CRM-Server/tests/unit/test_agent_api.py`

**Interfaces:**
- Produces: `GET /v1/agent/run-log/turns`, `GET /v1/agent/run-log/turns/{turn_id}`

- [ ] 403 without AI permissions; 200 with `ai:read`.
- [ ] Filter by user_id, outcome, q; paginate; detail returns steps.
- [ ] Commit.

### Task 5: Settings page

**Files:**
- Modify: `CRM-Client/src/settingsNavigation.ts`
- Modify: `CRM-Client/src/router/index.ts`
- Create: `CRM-Client/src/api/agentRunLog.ts`
- Create: `CRM-Client/src/views/AgentRunLogSettings.vue`
- Test: `CRM-Client/src/settingsNavigation.test.ts`
- Test: `CRM-Client/tests/views/AgentRunLogSettings.spec.ts`

**Interfaces:**
- Consumes: run-log list/detail APIs
- Produces: `/settings/agent-run-log` with filter table + process Sheet

- [ ] Register nav item in `integration` group after AI 配置.
- [ ] Dedicated route before `settings/:module`.
- [ ] Page lists turns and opens Sheet with six-step process.
- [ ] Commit.
