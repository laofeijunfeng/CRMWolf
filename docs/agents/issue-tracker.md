# Issue Tracker: GitHub

Issues and PRDs for this repo live as GitHub issues in `laofeijunfeng/CRMWolf`. Use the `gh` CLI for operations when GitHub access is needed.

## Conventions

- Create an issue: `gh issue create --title "..." --body "..."`
- Read an issue: `gh issue view <number> --comments`
- List issues: `gh issue list --state open --json number,title,body,labels,comments`
- Comment on an issue: `gh issue comment <number> --body "..."`
- Apply or remove labels: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- Close an issue: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v`; `gh` does this automatically inside this clone.

## Pull Requests as a Triage Surface

PRs as a request surface: no.

Set this to `yes` only if this repo starts treating external PRs as feature requests for `/triage`.

## Skill Semantics

- When a skill says "publish to the issue tracker", create a GitHub issue.
- When a skill says "fetch the relevant ticket", run `gh issue view <number> --comments`.
- When a skill creates multiple tickets, preserve blocking relationships in the issue body if native GitHub issue dependencies are unavailable.

## Wayfinding Operations

Used by `wayfinder`.

- Map: a single issue labelled `wayfinder:map`, holding Notes, Decisions-so-far, and Fog.
- Child ticket: an issue linked to the map. If native sub-issues are unavailable, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body.
- Blocking: prefer GitHub native issue dependencies. If unavailable, use a `Blocked by: #<n>, #<n>` line at the top of the child body.
- Frontier query: pick the first open child with no open blockers and no assignee.
- Claim: assign the issue to the current user.
- Resolve: comment with the answer, close the ticket, and append a context pointer to the map's Decisions-so-far.

