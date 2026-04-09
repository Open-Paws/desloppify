# Development Philosophy

This is a tool for agents. That shapes everything about how we build it.

## Agent-first

The primary user is an AI coding agent, not a human. The CLI output, the scoring model, the state format — all of it is optimized for agent consumption. Humans interact with it, but when there's a tradeoff between agent effectiveness and human UX, agent wins.

## No compatibility promise

Agents don't care about API stability the way human integrations do. We change things when we find a better way to do them. If you need a fixed contract, pin a version or fork.

Compatibility policy in this repo:

- Data compatibility shims are allowed at input boundaries (for example: accepting old payload keys while normalizing to one internal shape).
- Functionality compatibility shims are disallowed by default, with one narrow exception: temporary passthrough-only compatibility facades that forward to canonical modules without adding behavior.
- If behavior changes, update call sites directly in-repo instead of adding behavioral shims.
- Any temporary compatibility shim must include an owner + removal issue/date, and should be removed quickly after callers migrate.

## The score is the point

The whole thing exists to give agents a north-star they can optimize toward. We collect objective signals, ask subjective questions, and combine them into one score. That score is an external objective — agents are already trained to optimize toward goals, and we're giving them a goal that happens to mean "make this codebase genuinely good."

## The score has to be honest

This is the thing we care about most. If an agent can game the score to 100 without actually improving anything, the tool is worthless. So we put a lot of effort into making sure score improvement tracks real quality improvement:

- Attestation requirements on resolution — agents have to describe what they actually did
- Wontfix still counts against strict score — you can't dismiss your way to a perfect number
- Subjective assessments are cross-checked — if scores land suspiciously close to targets, they get flagged or reset
- Subjective findings are weighted heavily (75% of total) because that's where real quality lives

## Language-agnostic

The scoring model and the core engine don't know about any specific language. Language-specific stuff lives in plugins. The principles and scoring intent stay the same whether you're scanning TypeScript, Python, or Rust. Currently 29 languages, and the plugin framework makes adding more straightforward.

## Architectural boundaries

We keep a few rules concrete so the codebase stays workable as it grows:

- Command entry files are thin orchestrators — behavior lives in focused modules underneath them
- Dynamic imports only happen in designated extension points (`languages/__init__.py`, `hook_registry.py`)
- Persisted state is owned by `state.py` and `engine/_state/` — command modules read and write through those APIs, they don't invent their own persisted fields
- Major boundaries have regression tests so refactors don't silently break things

## Lifecycle phases

The work queue enforces a strict phase order. Items from later phases are hidden until earlier phases complete:

1. **Initial reviews** — Unscored subjective dimensions. The lifecycle filter blocks everything else until all placeholder dimensions are scored.
2. **Communicate score** — `workflow::communicate-score` is injected once all initial reviews are done, and also after trusted score imports that materially refresh the live score. It must appear before planning and triage so the user sees the updated strict score first.
3. **Create plan** — `workflow::create-plan` is injected when reviews are complete and objective backlog exists. It stays ahead of triage in the queue.
4. **Triage** — 6 stages (`triage::observe` → `reflect` → `organize` → `enrich` → `sense-check` → `commit`) injected when the review-issue snapshot hash changes (new `review`/`concerns` detector issues appear).
5. **Objective work** — Mechanical issues ranked by dimension impact.

Key constraint: full reconcile still only runs during `scan`. Review import is a narrower lifecycle entrypoint: it can add new review issues, queue workflow follow-up (`communicate-score`, `import-scores`, `create-plan`), and refresh the scorecard badge for trusted score imports, but it does not run the full post-scan reconcile/cluster regeneration path.

### Lifecycle walkthrough script

`scripts/lifecycle_walkthrough.py` creates a temp sandbox and walks through all 6 lifecycle stages interactively. At each stage it writes spoofed state + plan files, then pauses so you can run real CLI commands (`next`, `plan`, `status`) against it in another terminal.

```bash
python scripts/lifecycle_walkthrough.py
```

Use this to verify what agents see at each phase without running actual scans or reviews.

### Lifecycle integration tests

`desloppify/tests/commands/test_lifecycle_transitions.py` exercises each transition programmatically — completing items via `purge_ids` between reconcile calls, matching the real CLI flow where reconcile only runs at scan boundaries.
