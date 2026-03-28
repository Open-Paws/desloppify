# Desloppify — Technical Internals

Traditional tools catch mechanical issues — linters, formatters, dead code finders. Desloppify wraps those but the point is **subjective analysis**: structured LLM prompts about architecture, design quality, and convention consistency, tracked as scored findings. The score weights subjective findings heavily because that's what actually moves the needle. See the top-level README for philosophy and usage.

## Directory Layout

```
desloppify/
├── cli.py              # Argparse, main()
├── state.py            # Compatibility facade (prefer state_io/state_scoring)
├── app/                # CLI layer (commands, parser, output)
├── base/               # Foundational shared infrastructure
│   ├── config.py       # Configuration loading and helpers
│   ├── coercions.py    # Type coercion utilities
│   ├── enums.py        # Tier, Confidence, Status, Zone enums
│   ├── exception_sets.py # CommandError and exception groups
│   ├── registry.py     # Canonical detector registry
│   ├── scoring_constants.py # CONFIDENCE_WEIGHTS, HOLISTIC_MULTIPLIER
│   ├── text_utils.py   # Project root, path helpers
│   ├── discovery/      # File discovery, path resolution
│   ├── output/         # Terminal output, colorize, issues rendering
│   ├── search/         # Grep, query engine
│   └── text/           # Text API, rel(), is_numeric()
├── engine/             # Scan/scoring/state internals
│   ├── detectors/      # Generic algorithms (zero language knowledge)
│   ├── hook_registry.py # Detector-safe language hook registry
│   ├── plan.py         # Compatibility shim over plan facades
│   ├── plan_state.py   # Public plan state/schema/policy facade
│   ├── plan_ops.py     # Public plan mutation facade
│   ├── _plan/         # Plan persistence, sync, lifecycle internals
│   ├── _work_queue/   # Canonical queue snapshot and queue assembly
│   ├── plan_triage.py  # Public triage commands/prompts facade
│   ├── planning/       # Prioritization and plan generation
│   ├── policy/         # Zones, scoring policy
│   ├── _scoring/
│   ├── _state/
│   └── _work_queue/
├── intelligence/       # Subjective/narrative/review layer
│   ├── narrative/
│   ├── integrity/
│   └── review/
└── languages/          # Language plugins (auto-discovered, see languages/README.md)
    ├── _framework/     # Shared plugin framework, generic_lang(), tree-sitter
    ├── python/         # Full plugins (custom detectors, fixers, review dims)
    ├── typescript/
    ├── csharp/, dart/, gdscript/, go/, rust/
    └── ruby/, java/, ... (21 generic plugins)
```

## Architecture

```
Layer 0: base/                   Foundational infrastructure. Path resolution, config, enums, output.
Layer 1: engine/detectors/       Generic algorithms. Data-in, data-out. Zero language imports.
Layer 2: languages/_framework/   Shared contracts/helpers. Normalize raw results → tiered findings.
Layer 3: languages/<name>/       Language config + phases + extractors + detectors + fixers.
Layer 4: app/                    CLI commands. Thin entry points delegating to engine/intelligence.
```

**Import direction**: Each layer imports only from lower-numbered layers. `languages/` → `engine/detectors/`. Never the reverse. Detectors needing language-specific behavior use `engine.hook_registry.get_lang_hook(...)`.

## Domain Glossary

- **Finding**: A detected issue (`TypedDict` in `state.py`). Has detector, tier, category, file, description.
- **Detector**: A named analysis algorithm. Registry in `base/registry.py`.
- **Tier**: Severity T1–T4 (T4 = architectural, highest weight). Enum in `base/enums.py`.
- **Zone**: File intent classification — production/test/config/generated/script/vendor. Deterministic path-based.
- **Dimension**: A subjective quality axis (naming, structure, patterns, etc.) scored by LLM review.
- **Phase**: A scan stage — structural, style, security, etc. Each phase runs extractors → detectors → normalization.
- **Narrative**: Coaching layer that computes phase/headline/actions/reminders from scan state.
- **Concern**: A logical grouping of related findings (e.g. "unused code in auth module").
- **Plan**: Prioritized work queue in `.desloppify/plan.json` — ordered, clustered, with overrides.

## Data Flow

```
scan:    LangConfig → LangRun(phases) → generate_findings() → merge_scan() → state-{lang}.json
plan:    state → reconcile → plan.json (ordered queue, clusters, deferred items)
review:  state + plan → batch packets → LLM → import findings → merge
fix:     LangConfig.fixers → fixer.fix() → resolve in state
next:    state + plan → highest-priority item with coaching
detect:  LangConfig.detect_commands[name](args) → display
```

## Contracts

**Detector**: `detect_*(data, config) → list[dict]` — generic algorithm, no language assumptions.

**Phase runner**: `_phase_*(path, lang) → (list[Finding], dict[str, int])` — thin orchestrator calling extractors → generic algorithms → normalization.

**LangConfig**: Static language contract. Owns phases, detectors, thresholds, hooks.

**LangRun**: Per-invocation runtime wrapper (`_framework/runtime.py`) carrying mutable state (zone_map, dep_graph, complexity_map). Phases execute against LangRun, not LangConfig.

## Rules

- Entry command modules stay thin — behavioral logic in delegated modules
- Prefer narrow plan surfaces (`engine.plan_state`, `engine.plan_ops`, `engine.plan_triage`, `engine.planning`) over `engine.plan` in new code
- Dynamic imports only in `languages/__init__.py` (discovery) and `engine/hook_registry.py` (hooks)
- Persistent schema is owned by `engine/_state/`; `state.py` is compatibility-only. Command modules don't introduce ad-hoc persisted fields
- `LangRun` owns per-run mutable state, not `LangConfig`
- `base/` has zero upward imports — it never imports from `engine/`, `app/`, `intelligence/`, or `languages/`

## Where Do I Put This?

- **New detector**: `engine/detectors/` — pure algorithm, no language imports
- **New command**: `app/commands/` — thin entry point, delegate logic to engine/intelligence
- **New language plugin**: `languages/<name>/` — implement `LangConfig`, add phases
- **Path resolution / file helpers**: `base/discovery/`
- **Scoring constants**: `base/scoring_constants.py`
- **Configuration helpers**: `base/config.py`
- **New enum / shared type**: `base/enums.py`

## Non-Obvious Behavior

- **State scoping**: `merge_scan` only auto-resolves findings matching the scan's `lang` and `scan_path`. A Python scan never touches TS state.
- **Suspect guard**: If a detector drops from >=5 findings to 0, disappearances are held (bypass: `--force-resolve`).
- **Scoring**: Weighted by tier (T4=4x, T1=1x). Strict score penalizes both open and wontfix.
- **Cascade effects**: Fixing one category (e.g. unused imports) can surface work for the next (unused vars). Score can temporarily drop.
- **Tree-sitter optional**: All tree-sitter features degrade gracefully. Without `tree-sitter-language-pack`, generic plugins fall back to tool-only mode.
- **Bandit optional for Python depth**: Without `bandit`, Python-specific security checks are skipped; scan surfaces preflight/post-scan coverage warnings and marks score confidence reduced for security.
