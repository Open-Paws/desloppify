# Queue Lifecycle

`desloppify` now treats the queue as one explicit cycle:

`scan -> review -> workflow -> triage -> execute -> scan`

## Rules

- `scan` is a first-class queue phase.
- `review` covers two entry paths:
  - initial subjective assessment after a fresh scan
  - post-execution non-objective review work after objective execution drains
- `workflow` covers post-review workflow items such as score communication,
  score import, and plan creation.
- `triage` follows workflow and exposes only triage stages.
- `execute` exposes only objective fix work and execution clusters.

## Deferred Disposition

Deferred disposition is part of the `scan` boundary, not a separate cycle
phase. If deferred temporary skips exist, they block the scan step until the
user reactivates or permanently dispositions them.

## Persisted Phase vs Safety Net

The current lifecycle phase is persisted in `plan.refresh_state.lifecycle_phase`
for debuggability and normal transitions. Queue assembly still re-resolves the
phase from current visible items as a safety net, so stale saved phase state
cannot hide the correct next step after out-of-band changes.

## Completion Authority

Queue-tracked work is completed by explicit user actions such as
`desloppify plan resolve`, `plan skip --permanent`, or `plan reopen`.

Scans and review imports may:
- add new work
- reopen previously completed work when it reappears
- corroborate an existing manual resolution

They do not silently complete open queue-tracked issues just because a detector
stopped reporting them in the latest scan.
