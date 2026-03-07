# Plan UX Improvements

Findings from 3-perspective evaluation (new executor, PM, AI agent).

---

## Master Checklist

### Quick wins (render-only, no schema changes)
- [ ] 1. Show action steps inline in default `next` cluster view
- [ ] 2. Fix `--format json` emitting non-JSON warning line before JSON
- [ ] 3. Hide/suppress `file: .` for cluster meta-items and holistic findings
- [ ] 4. Show summaries instead of raw IDs in cluster "Sample:" section
- [ ] 5. Distinguish curated vs auto clusters in `plan show` / `plan queue`
- [ ] 6. Gate "N new review issues" warning — suppress for `--format json`, show context

### Medium effort (rendering + minor wiring)
- [ ] 7. Show step progress in cluster cards (`[2/7 steps done]`)
- [ ] 8. Explain queue numbering gaps (synthetic workflow items hidden from count)
- [ ] 9. Trim the encouragement box — shorter, less repetitive

### Schema + feature work
- [ ] 10. Add `desloppify plan cluster step-done <cluster> <step#>` shorthand
- [ ] 11. Wire issue-to-step mapping into resolve flow (auto-mark step done when its issue_refs resolve)
- [ ] 12. Surface dependency_order between clusters in `plan show` and `next`

---

## Detailed Sections

### 1. Show action steps inline in default `next` cluster view

**Problem:** Default `next` shows `[plan: N steps] drill in to view` — requires a second command before you can start working.

**Files:**
- `app/commands/next/render_support.py` → `render_cluster_item()`

**Change:** When rendering a cluster card in the default (non-drill-in) view, show the first 3 steps inline instead of just the count. Keep the "drill in to view all" hint if there are more than 3.

```
  Steps:
    1. Add JWT signature verification ...
    2. Audit all 31 edge functions ...
    3. ... (5 more — drill in to view all)
```

---

### 2. Fix `--format json` emitting non-JSON warning line

**Problem:** `print_triage_guardrail_info()` prints to stdout before JSON output, breaking parsers.

**Files:**
- `app/commands/next/cmd.py` → `cmd_next()` (line 124)
- `app/commands/helpers/guardrails.py` → `print_triage_guardrail_info()`

**Change:** In `cmd_next()`, check if output format is `json` before calling `print_triage_guardrail_info()`. Alternatively, route warnings to stderr when format != terminal. Cleanest fix: move the guardrail print to after `_emit_requested_output` returns False (i.e., only print for terminal output), or have guardrail return the text and let caller decide.

Preferred approach: suppress guardrail print when `opts.output_format != "terminal"`. Embed the guardrail info into the JSON payload instead (e.g., `"warnings": [...]`).

---

### 3. Hide `file: .` for cluster meta-items and holistic findings

**Problem:** `File: .` is meaningless — it's the repo root for holistic review findings.

**Files:**
- `app/commands/next/render.py` → `_render_issue_detail()` (line 125)

**Change:** Skip printing `File: .` when the file value is `.` or empty. For cluster items, show file spread instead (already handled by `_render_cluster_files` in render_support.py).

---

### 4. Show summaries instead of raw IDs in cluster "Sample:" section

**Problem:** `_render_cluster_sample()` shows opaque IDs like `review::src/tools/video/...::abc123` — useless for humans.

**Files:**
- `app/commands/next/render_support.py` → `_render_cluster_sample()` (line 96-101)

**Change:** Show summary text instead of ID. Members already have `summary` field. Fall back to truncated ID if no summary.

```python
def _render_cluster_sample(members: list[dict]) -> None:
    print(colorize("\n  Sample:", "dim"))
    for member in members[:3]:
        summary = member.get("summary", member.get("id", ""))
        print(f"    - {summary}")
    if len(members) > 3:
        print(colorize(f"    ... and {len(members) - 3} more", "dim"))
```

---

### 5. Distinguish curated vs auto clusters in `plan show` / `plan queue`

**Problem:** Manual (triage-curated) clusters and auto-generated clusters look the same.

**Files:**
- `app/commands/plan/queue_render.py` → `_render_cluster_banner()` (line 104-129)
- `app/commands/plan/cluster_handlers.py` → `_cmd_cluster_list()` (already shows `[auto]` tag — good)

**Change:** In `_render_cluster_banner()`, add a `[triage]` or `[curated]` tag for manual clusters. Already shows type label but doesn't distinguish auto vs manual when the cluster isn't a well-known auto name.

In `queue_render.py`, the `_cluster_type_label` returns "Grouped task" for manual clusters — change to "Triage cluster" or "Curated cluster" for non-auto clusters.

---

### 6. Gate "N new review issues" warning

**Problem:** Warning appears on every command invocation including `--format json`. Alarming without context. Noisy for agents.

**Files:**
- `app/commands/helpers/guardrails.py` → `print_triage_guardrail_info()`
- `app/commands/next/cmd.py` → `cmd_next()` (line 124)
- `app/commands/plan/queue_render.py` → `cmd_plan_queue()` (line 180)

**Change:**
1. For `--format json`: skip the print entirely, include in JSON payload as `"warnings"` array.
2. For terminal: add brief context: "N new review issue(s) since last triage. Run `desloppify plan triage` to incorporate."
3. Consider gating: only show if >0 new issues (it already does this, but the message could be clearer).

---

### 7. Show step progress in cluster cards

**Problem:** No visibility into which steps are done without running `cluster show`.

**Files:**
- `app/commands/next/render_support.py` → `render_cluster_item()` (line 126-163)
- `app/commands/plan/queue_render.py` → `_render_cluster_banner()` (line 104-129)

**Change:** When `action_steps` exist and some have `done: true`, show progress: `[2/7 steps done]`.

The `_build_cluster_meta` in `plan_order.py` already passes `action_steps` through. Need to ensure `done` status is preserved (it should be since steps are stored on the cluster, not the meta-item). But `_build_cluster_meta` copies `action_steps` from cluster_data (line 194), so done status is preserved.

---

### 8. Explain queue numbering gaps

**Problem:** Queue shows items 1-10 then jumps to 13, 14. Hidden synthetic items (triage workflow stages, workflow actions) cause gaps.

**Files:**
- `app/commands/plan/queue_render.py` → `_build_rows()` (line 132-165)

**Change:** After the table, if there are hidden items (workflow_stage, workflow_action that were rendered as banners or skipped), add a note: "N workflow/triage items not shown in table (use `plan queue --all` to include)."

Actually, looking at the code: cluster items are rendered as banners and `continue`d in `_build_rows`. The numbering is already sequential for remaining rows. The gap comes from clusters taking up positions. This might already be clear enough with cluster banners interspersed. Investigate whether this is actually confusing in practice — may be a non-issue.

---

### 9. Trim the encouragement box

**Problem:** 8-line box at the bottom of `next` output. Repetitive after first viewing. Too long.

**Files:**
- `app/commands/next/cmd.py` → `_build_and_render_queue()` (lines 328-338)

**Change:** Shorten to 2-3 lines max:
```
Hey — start working on the task above. When done: `desloppify plan resolve`.
See full queue: `desloppify plan show` · All plan tools: `desloppify plan --help`
```

---

### 10. Add `step-done` shorthand command

**Problem:** Marking a step done requires `desloppify plan cluster update <name> --done-step N` — verbose.

**Files:**
- `app/commands/plan/cluster_handlers.py`
- `app/commands/plan/cmd.py` (argparse registration)

**Change:** Already works via `cluster update --done-step N`. Could add an alias but the existing path is fine. Lower priority — the infrastructure exists, just needs better discoverability. Maybe add a hint in the cluster drill-in view: "Mark step done: `desloppify plan cluster update <name> --done-step N`"

---

### 11. Wire issue-to-step mapping into resolve flow

**Problem:** When resolving an issue that's in a cluster with steps that have `issue_refs`, the step should auto-mark as done when all its referenced issues are resolved.

**Files:**
- `engine/plan/` → resolve logic (wherever `plan resolve` marks issues done)
- `engine/_plan/schema.py` → `ActionStep` already has `issue_refs` and `done`

**Change:**
1. When resolving issues, check if the resolved issue ID (or suffix) appears in any step's `issue_refs`
2. If ALL `issue_refs` for a step are now resolved, auto-set `done: true`
3. Print: "Step 3 auto-completed: all referenced issues resolved"

This is the key feature the user asked for ("We should have a way to update subpoints for sure").

**Implementation sketch:**
```python
def _auto_complete_steps(plan: dict, resolved_ids: set[str]) -> list[str]:
    """Check clusters for steps whose issue_refs are all resolved. Returns messages."""
    messages = []
    for name, cluster in plan.get("clusters", {}).items():
        steps = cluster.get("action_steps") or []
        for i, step in enumerate(steps):
            if not isinstance(step, dict) or step.get("done"):
                continue
            refs = step.get("issue_refs", [])
            if not refs:
                continue
            # Check if all refs are in the resolved set (match by suffix)
            all_resolved = all(
                any(rid.endswith(ref) or ref == rid for rid in resolved_ids)
                for ref in refs
            )
            if all_resolved:
                step["done"] = True
                messages.append(
                    f"Step {i+1} of '{name}' auto-completed: {step.get('title', '')}"
                )
    return messages
```

---

### 12. Surface dependency_order between clusters

**Problem:** `dependency_order` field exists on Cluster schema but is never displayed. Prose hints at deps but nothing structured.

**Files:**
- `app/commands/plan/cluster_handlers.py` → `_cmd_cluster_show()`, `_cmd_cluster_list()`
- `app/commands/next/render_support.py` → `render_cluster_item()`

**Change:**
1. In `cluster list --verbose`, show `dependency_order` column if any cluster has it set
2. In `cluster show`, show "Depends on: <cluster>" or "Unblocks: <cluster>" if dependency info exists
3. In `next` cluster card, if the cluster's `dependency_order` indicates it should come first, note "This cluster should be completed before: X, Y"

Lower priority — requires clusters to have `dependency_order` populated during triage, which is a triage-prompt change.

---

## Priority Order

**Do first (high impact, low effort):**
1. (#2) Fix JSON output — it's a bug
2. (#1) Show steps inline — biggest UX win
3. (#4) Show summaries not IDs — easy fix
4. (#3) Hide `file: .` — easy fix
5. (#9) Trim encouragement box — easy fix

**Do second (medium effort):**
6. (#5) Distinguish curated vs auto — small render change
7. (#6) Gate warning for JSON — ties into #2
8. (#7) Step progress in cards — render change with data already available

**Do third (feature work):**
9. (#11) Auto-complete steps on resolve — the key new feature
10. (#10) Step-done discoverability — hint in output
11. (#12) Dependency graph — needs triage-side work too
12. (#8) Queue numbering gaps — may be non-issue after investigation
