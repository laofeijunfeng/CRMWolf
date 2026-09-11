# Task 3 RED/GREEN and Self-Review Report

## Scope

Implemented Task 3 integration in `CRM-Client/src/composables/useAgentAsyncOperations.ts` and `CRM-Client/src/components/agent/CRMAgentChat.vue`, with focused tests in the two requested test files. The API client and API test files were left to the sibling owner and were not edited by this task.

## RED evidence

Focused command:

```text
cd /private/tmp/crmwolf-agent-history-anchors/CRM-Client
npx vitest run tests/composables/useAgentAsyncOperations.spec.ts tests/components/CRMAgentChatAsyncOperations.spec.ts
```

The first RED run failed for the intended missing integration behavior:

- Composable tests failed because production `loadSession` still called the removed/non-paginated `api.listSessionOperations` seam; the new test supplied only `listSessionOperationHistory`.
- The new chat anchor test failed with `expected "spy" to be called 1 times, but got 0 times`, proving that no exact source-anchor request was made.

The initial test edits also exposed old fixtures still using the prior operation-list seam; those fixtures were migrated to the paginated Task 2 API contract before implementation was completed.

## GREEN evidence

Final focused command:

```text
cd /private/tmp/crmwolf-agent-history-anchors/CRM-Client
npx vitest run tests/composables/useAgentAsyncOperations.spec.ts tests/components/CRMAgentChatAsyncOperations.spec.ts
```

Result:

```text
Test Files  2 passed (2)
Tests  14 passed (14)
```

The run emitted existing Sass legacy-JS-API deprecation notices; no formatter, linter, or project-wide suite was run.

## Implementation summary

- `useAgentAsyncOperations.loadSession` requests operation history with `{ page: 1, page_size: 100 }`, derives page count from both `total_pages` and `ceil(total / page_size)`, fetches every page, checks session generation after each await, merges with in-flight provisional acknowledgements, and only schedules polling for nonterminal operations.
- `CRMAgentChat` collects missing positive source user/assistant message IDs from loaded operations, deduplicates and sorts them, performs one exact `listMessageAnchors` request, and merges anchors through the pure `mergeAgentHistoryAnchors` helper.
- Anchor reads are invoked after initial session load, authoritative reloads after turns, and waiting-user/terminal refresh callbacks.
- Anchor responses are guarded by message-load generation and active session ID. Anchor failures are nonfatal.
- Anchor merging does not increment `messageScrollKey`; existing live operation/message updates retain their current behavior.
- Existing polling terminal behavior, SSE acknowledgement merging, and session generation invalidation remain intact.

## Self-review and concerns

- Focused tests cover all-page loading, polling only nonterminal history rows, stale operation-page discard after session switch, exact deduplicated anchor loading and historical placement, existing terminal refresh, stream reload, and operation-card rendering.
- The repository still contains concurrent sibling changes in the API client/API test files; these were intentionally not staged or modified.
- Other broader chat tests may need their local mocked API object updated to expose the new Task 2 methods if they are run outside this focused command; that fixture maintenance is outside the requested Task 3 test files and should be handled by the integration owner if required.

## Review-fix RED evidence

Focused command (before production fixes):

```text
cd /private/tmp/crmwolf-agent-history-anchors/CRM-Client
npx vitest run tests/composables/useAgentAsyncOperations.spec.ts tests/components/CRMAgentChatAsyncOperations.spec.ts
```

Result:

```text
Test Files  2 failed (2)
Tests  2 failed (16 total collected)
```

The paging regression received `["aop_page_newest", "aop_page_middle", "aop_page_oldest"]` instead of chronological order. The anchor scroll regression initially exposed the runtime's lack of `Promise.withResolvers`; the test was then rewritten with a standard resolver promise and failed on the intended count behavior before the production fix.

## Review-fix GREEN evidence

Focused command (after production fixes):

```text
cd /private/tmp/crmwolf-agent-history-anchors/CRM-Client
npx vitest run tests/composables/useAgentAsyncOperations.spec.ts tests/components/CRMAgentChatAsyncOperations.spec.ts
```

Result:

```text
Test Files  2 passed (2)
Tests  15 passed (15)
```

Existing Sass legacy-JS-API deprecation notices were emitted. No formatter, linter, or project-wide suite was run.

Review fixes: operation pages are flattened oldest-page-first while preserving each page's internal order; visible inserted anchor IDs are session-scoped and excluded from `MessageScroller`'s count until authoritative replacement/session switch; historical placement now requires operation content before the current-window message with no trailing unanchored operation region; the composable API uses `PaginatedResponse<AgentAsyncOperation>`.
