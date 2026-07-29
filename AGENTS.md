# CRMWolf Agent Instructions

These instructions are project-level defaults for Codex in this repository.

## Agent Skills

Use the installed mattpocock skills by default. The user should not need to remember skill names.

### Routing

- If the right workflow is unclear, use `ask-matt` as the router and follow its recommended flow.
- For vague feature requests, product decisions, UI workflows, or anything with unresolved scope, start with `grill-with-docs` before editing code.
- For clear, small implementation requests, use `implement` directly and apply `tdd` where there is a meaningful test seam.
- For bug reports, regressions, failing tests, slow behavior, or exceptions, use `diagnosing-bugs` first. Build one red-capable feedback loop before hypothesizing.
- For large or multi-session work, use `to-spec`, then `to-tickets`, then `implement` ticket by ticket.
- For huge or foggy efforts where the path is not visible yet, use `wayfinder` before writing a spec.
- For architecture or maintainability work, use `improve-codebase-architecture`; use `codebase-design` vocabulary when designing module shape.
- Before finishing non-trivial code changes, use `code-review` against the relevant fixed point when possible.

### Issue Tracker

Issues and PRDs are tracked in GitHub Issues for `laofeijunfeng/CRMWolf`. See `docs/agents/issue-tracker.md`.

### Triage Labels

Use the default mattpocock triage label vocabulary. See `docs/agents/triage-labels.md`.

### Domain Docs

This repo uses a single-context domain doc layout: root `CONTEXT.md` plus ADRs in `docs/adr/`. See `docs/agents/domain.md`.

## Skill Operating Rules

- Keep `grill-with-docs`, `to-spec`, and `to-tickets` in one continuous context window when feasible.
- Start each `implement` run from a spec or ticket when one exists.
- During `tdd`, agree the public seam before adding tests; test behavior through public interfaces, not internals.
- During `diagnosing-bugs`, do not jump to a fix until a tight red-capable loop exists, or explicitly state why no loop can be built.
- Use `research` for questions that require current or primary-source documentation; save findings as cited Markdown when the work benefits from a durable record.
- Use `handoff` when a thread is full or a prototype/research branch needs to return concise findings to the main flow.

## Project Standards

- Follow `CONTRIBUTING.md` for coding rules, local commands, testing expectations, and commit conventions.
- Frontend UI work must follow `CRM-Docs/design-system/README.md` and the relevant component/pattern docs.
- Deployment work must follow `CRM-Docs/deployment/README.md`.
- Do not add temporary plans, validation reports, or one-off scripts at the repo root.
- Do not touch unrelated dirty worktree changes.

