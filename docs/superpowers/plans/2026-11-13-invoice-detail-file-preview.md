# Invoice Detail File Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development or executing-plans to implement this plan task-by-task.

**Goal:** Make persisted reissue and red-offset invoice files use the existing preview-plus-download attachment controls while preserving all existing names, permissions, and original-blue blocking behavior.

**Architecture:** Add object-URL helpers beside the existing original-invoice helper in `fileUpload.ts`. `InvoiceDetailSheet.vue` owns persisted preview URL state keyed by stable file IDs, loads those URLs after invoice detail data arrives, and supplies them to the existing `FileAttachment`/`FilePreviewDialog` flow. No backend or shared preview component changes.

**Tech Stack:** Vue 3, TypeScript, Axios request wrapper, Vitest, Playwright.

## Global Constraints

- Work only in CRM-105 worktree.
- Do not change backend routes, permissions, team filtering, upload forms, approval flows, or shared preview dialog.
- Preserve original-blue blocked behavior and all existing file names/captions/download names.
- Do not add preview support for unsupported formats.
- No commit or push until explicitly requested by the later `提测` instruction.

### Task 1: Add object URL API helpers

**Files:**
- Modify: `CRM-Client/src/api/fileUpload.ts`
- Test: `CRM-Client/src/api/__tests__/fileUploadPreview.test.ts`

- [ ] Write tests proving reissue red/new and red-offset helpers request the existing endpoint with `responseType: 'blob'` and return `URL.createObjectURL` output.
- [ ] Run the focused test and confirm it fails because helpers do not exist.
- [ ] Implement `createInvoiceReissueFileObjectUrl(reissueId, fileKind)` and `createInvoiceRedOffsetFileObjectUrl(redOffsetId)` using the existing `BlobPartResponseSchema`, `toBlob`, and endpoint path helpers.
- [ ] Run the focused test and confirm it passes.

### Task 2: Wire persisted detail previews

**Files:**
- Modify: `CRM-Client/src/views/InvoiceDetailSheet.vue`

- [ ] Add separate persisted preview URL state for reissue and red-offset files; keep upload-form URLs separate.
- [ ] Add request-scoped loading, stale-result rejection, and URL cleanup for invoice changes, sheet close, and unmount.
- [ ] Populate `FileAttachmentItem.url` only for loaded persisted files; leave unsupported formats downloadable but not previewable through the existing `isPreviewable` gate.
- [ ] Remove the explicit preview disable and text download label from reissue files; enable preview for red-offset files while preserving existing download handlers.
- [ ] Route `@preview` events to loading/error feedback without changing the shared preview dialog.

### Task 3: Verify behavior

**Files:**
- Modify: `CRM-Client/tests/e2e/invoice-reissue-unlimited.e2e.ts` only if the existing smoke fixture needs the new file endpoints.
- Create: `.xwing-task/crmwolf/evidence/` screenshots through the existing Playwright test surface.

- [ ] Run focused Vitest tests for API helpers and existing preview behavior.
- [ ] Run frontend type-check and lint.
- [ ] Run the existing invoice Playwright smoke with intercepted binary file endpoints and capture screenshots showing three preview icons and the blocked original-blue row.
- [ ] Review the diff and record verification evidence in the CRM-105 ledger; do not commit or push.
