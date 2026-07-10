# Documentation Organization

This document defines how firmware documentation in this repository should be structured and maintained.

The goal is to keep each document focused, avoid duplicated rules, and make it obvious where a future change belongs.

## Principles

- Keep one source of truth for each kind of information.
- Prefer short, purpose-specific documents over large mixed-purpose pages.
- Separate architecture decisions from implementation status.
- Separate stable rules from temporary findings.
- Cross-link related documents instead of copying the same text in multiple places.

## Document Map

### `README.md`

Use `README.md` as the documentation entry point.

It should answer:

- What this repository is.
- What boards or firmware targets exist.
- Which documents to read first.
- Where the main code lives.

### `docs/boards/*.md`

Use one page per board or runtime target.

Each page should cover:

- The board role.
- The responsibilities owned by that board.
- The main code entry points.
- Any board-specific communication or hardware notes.

### `docs/espnow-architecture-spec.md`

Use this page for the overall ESPNOW architecture.

It should cover:

- The current topology.
- The target topology.
- Ownership of state and responsibilities.
- The intended migration phases.
- Decisions that are already settled at architecture level.

### `docs/protocol-contract.md`

Use this page for concrete protocol rules.

It should cover:

- Message fields.
- Acknowledgement rules.
- Retry rules.
- Health and error rules.
- The implementation order for protocol-related work.

### `issues.md`

Use `issues.md` for review findings and work status.

It should contain:

- What is wrong or risky in the current code.
- Why it matters.
- What was decided for each issue.
- What has already been implemented.
- What still needs verification.

## Where To Record A Change

### Record in architecture docs when the change affects design

Use the architecture docs when the change affects:

- Ownership between boards.
- Communication flow.
- Retry and timeout policy.
- Required board behavior.
- Protocol rules that should remain stable.

### Record in `issues.md` when the change is about a concrete finding

Use `issues.md` when the change starts as a review finding or bug report.

For each item, capture:

- Status.
- Decision.
- Implementation location.
- Verification result.

### Record in code comments only for local implementation details

Use comments in code for:

- Non-obvious control flow.
- Hardware-specific constraints.
- Small implementation notes that do not belong in the design docs.

Do not use comments to restate broad architecture rules that already exist in docs.

## Required Writing Pattern

When adding or updating a documented decision, include these fields somewhere in the relevant document:

- Problem
- Decision
- Implementation
- Verification
- Open questions, if any

This keeps the document useful for a future agent that needs to continue the work.

## Update Rules

1. Update the most specific document first.
2. If the decision changes the system design, update the architecture or protocol docs.
3. If the change affects code status, update `issues.md`.
4. Keep the README as an index, not as the place where detailed decisions live.
5. Remove duplicate explanations when a better canonical document exists.

## Recommended Structure For `issues.md`

Each issue should ideally follow this shape:

```md
### High - short issue title

Status: open | decided | implemented | verified
Decision: ...
Implementation: ...
Verification: ...
Notes: ...
```

This makes it easy to scan the current state without having to infer whether a point is already solved.

## Review Checklist

Before finishing a documentation change, check that:

- The new information is in the right document.
- The same rule is not duplicated in another place without a link.
- The README still points to the most important docs.
- The document name matches its scope.
- The text clearly separates current status from intended behavior.

## Practical Rule

If a future reader asks "what is the rule?" the answer should be in `docs/protocol-contract.md` or `docs/espnow-architecture-spec.md`.

If they ask "what is currently wrong or pending?" the answer should be in `issues.md`.

If they ask "where do I start reading?" the answer should be in `README.md`.
