# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before Exploring, Read These

- `CONTEXT.md` at the repo root, if it exists.
- `CONTEXT-MAP.md` at the repo root, if it exists and points to context-specific docs.
- `docs/adr/` for ADRs that touch the area being changed.

If these files do not exist, proceed silently. Do not create them upfront just because they are missing. `domain-modeling`, usually reached through `grill-with-docs` or `improve-codebase-architecture`, creates or updates them when terms or decisions actually get resolved.

## File Structure

CRMWolf currently uses the single-context layout:

```text
/
├── CONTEXT.md
├── docs/adr/
└── CRM-Client/
└── CRM-Server/
```

## Use Glossary Vocabulary

When output names a domain concept in an issue title, refactor proposal, hypothesis, test name, or user-facing workflow, use the term as defined in `CONTEXT.md`.

If the concept is missing from the glossary, either reconsider the term or note the gap for `domain-modeling`.

## Flag ADR Conflicts

If a proposed change contradicts an existing ADR, surface it explicitly instead of silently overriding it.

