# Desloppify Fork Architecture Report

**Purpose**: Map desloppify's internal architecture to identify exact extension points for Open Paws' animal advocacy language detection and persona-based browser QA.

**Source**: `agentic-stack/desloppify/` (v0.9.10, MIT license, by Peter O'Malley)

---

## 1. Detector Architecture

### How Detectors Work

Detectors are **pure functions** — no base class, no inheritance. Each detector function takes parameterized inputs and returns a tuple of `(entries, metadata)`.

**Detector function signature** (varies by type):
```python
def detect_orphaned_files(path, graph, extensions, options) -> (list[dict], int)
def detect_complexity(path, signals, file_finder, threshold) -> (list[dict], int)
def detect_coupling_violations(path, graph, shared_prefix) -> (list[dict], CouplingEdgeCounts)
```

Detectors are wrapped in **phases** — ordered callables registered per-language:

```python
@dataclass
class DetectorPhase:
    label: str
    run: Callable[[Path, LangRuntimeContract], tuple[list[DetectorEntry], dict[str, int]]]
    slow: bool = False
```

**Phase contract**: receives `(project_path, lang_runtime)`, returns `(issues, potentials)`. The `LangRuntimeContract` provides dependency graph, zone map, complexity data, file finder, function extractor, review cache.

### How Detectors Are Registered

Two-layer registration:

1. **Metadata registry** (`base/registry/catalog_entries.py`): Each detector is a frozen `DetectorMeta` dataclass:
   ```python
   DetectorMeta(
       name="orphaned",
       display="Orphaned files",
       dimension="Code quality",      # scoring dimension
       action_type="reorganize",       # auto_fix | refactor | reorganize | manual_fix
       guidance="...",                  # coaching text for agent
       tier=3,                         # T1-T4 scoring weight
       marks_dims_stale=True,          # mechanical fix invalidates subjective scores
       subjective_dimensions=("cross_module_architecture",),  # evidence for review dims
   )
   ```

2. **Phase registration** (per-language `LangConfig.phases`): Phases are ordered in each language's config class, not in the central registry.

**65+ built-in detectors** spanning: code quality, duplication, file health, security, test health, design coherence, framework-specific patterns (React, Next.js, Rust).

### What Detectors Return

Raw detector output → normalized to `Issue` (TypedDict):
- `detector: str` — detector name
- `file: str` — filepath
- `line: int | None`
- `summary: str` — human-readable description
- `tier: int` — T1-T4 priority
- `confidence: str` — "low"/"medium"/"high"
- `category: str` — scoring dimension

### Plugin Support

**Three discovery mechanisms** (`languages/_framework/registry/discovery.py`):

1. **Built-in packages**: `desloppify/languages/{lang}/` with `__init__.py` exporting `register()`
2. **Single-file plugins**: `desloppify/languages/plugin_*.py` with `register()`
3. **User plugins**: `.desloppify/plugins/*.py` — requires `trust_plugins: true` in config or `DESLOPPIFY_TRUST_PLUGINS=1` env var

User plugins can call:
- `register_detector(meta)` — add to central registry
- `register_scoring_policy(policy)` — add scoring policy
- `register_lang_class(name, ConfigClass)` — add whole language

**Critical finding**: Phases are defined inside `LangConfig` — you can't inject a new phase into an existing language without subclassing or monkey-patching its config. The plugin system is designed for adding new languages, not extending existing ones.

---

## 2. Language System

### Framework

Each language is a `LangConfig` dataclass (`languages/_framework/base/types.py`) providing:
- `phases: list[DetectorPhase]` — ordered detector phases
- `build_dep_graph` — import parser
- `extract_functions` — function extractor (for duplication)
- `entry_patterns`, `barrel_names` — entry point detection
- `boundaries` — architectural constraint rules
- `zone_rules` — code area classification
- `holistic_review_dimensions` — subjective dimensions to assess
- `detect_commands` — CLI-exposed detector runners

### TypeScript Implementation

**12 detector phases** (in order):
1. Logs (tagged debug logging) — T1, auto-fix
2. Unused (tsc dead code) — T3, auto-fix
3. Dead exports — T2, manual
4. Deprecated API usage — T3, manual
5. Structural (large files, complexity, god components, flat dirs, mixed concerns) — T3, refactor
6. Coupling + single-use + patterns + naming — T3, reorganize
7. Tree-sitter cohesion (optional) — T3
8. Signature detection — T2, refactor
9. Test coverage — T4, refactor
10. Code smells (dead useEffect, empty chains, React patterns) — T3, auto-fix/refactor
11. Framework phases (Next.js) — T3
12. Security — T2-3, manual

**TypeScript-specific**: React/Next.js pattern detectors, props detection, TypeScript-specific coupling analysis, 20 holistic review dimensions.

**Extensions**: `.ts`, `.tsx`, `.js`, `.jsx` | Exclusions: `node_modules`, `.git`, `dist`, `build`, `.next`

---

## 3. Scoring System

### Two-Pool Architecture

**Mechanical pool (25% of overall score)**:

| Dimension | Weight |
|-----------|--------|
| File health | 2.0 |
| Code quality | 1.0 |
| Duplication | 1.0 |
| Test health | 1.0 |
| Security | 1.0 |

**Subjective pool (75% of overall score)**:

| Dimension | Weight |
|-----------|--------|
| High elegance | 22.0 |
| Mid elegance | 22.0 |
| Low elegance | 12.0 |
| Contracts | 12.0 |
| Type safety | 12.0 |
| Design coherence | 10.0 |
| Abstraction fit | 8.0 |
| Logic clarity | 6.0 |
| Structure nav | 5.0 |
| Error consistency | 3.0 |
| Naming quality | 2.0 |
| AI generated debt | 1.0 |

### Calculation

1. **Per-detector**: Each issue's weighted failure = `CONFIDENCE_WEIGHTS[confidence]` (HIGH=1.0, MEDIUM=0.7, LOW=0.3). File-based detectors cap per-file.
2. **Per-dimension**: `score = (checks - weighted_failures) / checks * 100`
3. **Sample dampening**: `effective_weight = configured_weight * min(1.0, checks / 200)` — dimensions with <200 checks are proportionally damped
4. **Pool averages**: Weighted average within each pool
5. **Overall**: `mechanical_avg * 0.25 + subjective_avg * 0.75`

### Adding New Dimensions

```python
# 1. Register detector metadata (base/registry/catalog_entries.py)
register_detector(DetectorMeta(
    name="advocacy_language",
    display="Advocacy language",
    dimension="Advocacy language",  # new mechanical dimension
    action_type="manual_fix",
    guidance="Replace speciesist language with inclusive alternatives",
    tier=3,
))

# 2. Register scoring policy (engine/_scoring/policy/core.py)
register_scoring_policy(DetectorScoringPolicy(
    detector="advocacy_language",
    dimension="Advocacy language",
    tier=3,
    file_based=True,
))

# 3. Add to MECHANICAL_DIMENSION_WEIGHTS
MECHANICAL_DIMENSION_WEIGHTS["advocacy language"] = 1.0
```

The `register_scoring_policy()` function exists and calls `_rebuild_derived()` which rebuilds `DIMENSIONS` in-place. **New dimensions can be added at runtime via the plugin system.**

### Score Impact of New Dimensions

New mechanical dimensions **dilute existing mechanical dimensions** within the mechanical pool (25% of overall). Adding "Advocacy language" at weight 1.0 changes the mechanical pool from total weight 6.0 to 7.0. A new dimension scoring 100 would slightly raise the overall; scoring 0 would slightly lower it. The 25% mechanical fraction stays constant.

---

## 4. Plan/Queue System

### How `next` Works

1. Loads state (`.desloppify/state.json`) and plan (`.desloppify/plan.json`)
2. Builds execution queue via `build_execution_queue()`
3. Ranks items by: plan position → natural rank → estimated impact → confidence → review weight → count
4. Impact = `per_point × (100 - dimension_score)` — issues in lower-scoring dimensions sort higher

### Priority Tiers
- **Tier 0**: Items with explicit plan position (planned items first)
- **Tier 1**: Existing items with natural ranking
- **Tier 2**: Newly discovered items

### Source Coexistence

All finding sources coexist in the same queue:
- Mechanical detector findings
- Subjective/LLM review findings (`is_subjective=True` flag)
- Triage stage items
- Workflow action items (create-plan, score-checkpoint)
- Synthetic subjective dimension markers

All types flow through the same `finalize_queue()` → impact enrichment → unified ranking.

### The Fix Loop

```
desloppify next          → shows top priority items
[agent fixes code]       → makes changes
desloppify plan resolve  → marks issues resolved, updates plan
desloppify next          → regenerated queue shows next items
```

**State**: Plan persists `queue_order`, `clusters`, `overrides`, `uncommitted_fixes`, execution logs. Queue is dynamically recomputed from state + plan each invocation.

### Persistence

- **State**: `.desloppify/state.json` — issues, dimension scores, potentials, scan history
- **Plan**: `.desloppify/plan.json` — queue order, clusters, overrides, execution logs
- Plan uses file locking (`msvcrt.locking` on Windows, `fcntl.flock` on Unix) for read-modify-write safety

---

## 5. Subjective Review System

### Architecture

Review is split across two packages:
- `app/commands/review/` — CLI orchestration, workflow
- `intelligence/review/` — pure Python domain logic (context building, file selection, batch preparation)

**Key design**: `intelligence/review/` prepares payloads but **never calls an LLM directly**. The model is selected at the orchestration layer, making the review system model-agnostic.

### How It Works

1. `prepare_review()` → selects files, builds context (naming vocab, module patterns, import graph summary)
2. Constructs per-dimension prompts with enriched context
3. Agent receives context + batch payloads + prompts
4. Agent returns structured issue list per dimension
5. Issues normalized via `normalize_assessment_inputs()` → stamped with `detector="review_<dimension>"`, confidence, summary, file, line
6. Merged with mechanical findings in state, flows through same queue/ranking

### Dimensions

Per-language configurable via `holistic_review_dimensions` on `LangConfig`. TypeScript has 20 review dimensions including: `cross_module_architecture`, `convention_outlier`, `error_consistency`, `abstraction_fitness`, `test_strategy`, `api_surface_coherence`, `authorization_consistency`, `ai_generated_debt`, `design_coherence`, `naming_quality`, `logic_clarity`, `type_safety`, `contract_coherence`.

### Persona QA Compatibility

The review system's model-agnostic, dimension-based architecture could support persona QA as a custom subjective review type. However, review is fundamentally **static analysis of source code** — it receives file contents and produces findings about code quality. Browser QA operates on running applications, which is architecturally different.

---

## 6. Skill System

### What Skills Contain

Skill files (SKILL.md, CLAUDE.md) contain:
- YAML frontmatter (interface-dependent)
- Desloppify skill section (marked by `<!-- desloppify-begin -->` / `<!-- desloppify-end -->` HTML comments)
- Agent instructions: available commands, workflows, best practices
- Version tracking (`SKILL_VERSION = 6`)

### Extension

Skills support an **overlay system**: project-specific custom instructions go between the main skill content and the end marker. Custom gate instructions (e.g., "always run scan before resolve") can be added in the overlay section.

---

## 7. Extension Points for the Fork

### 7.1 Advocacy Language Detection

**Recommended approach**: A new detector class via the **user plugin system** (`.desloppify/plugins/advocacy_language.py`) that shells out to semgrep/eslint/vale.

**Why this fits best**:
- The 62+ rules are already in semgrep YAML, ESLint JS, and Vale YAML — rewriting them as native Python would be wasteful
- The plugin system already supports runtime detector registration
- Semgrep rules cover generic (comments/docs), JavaScript, Python, Go with severity levels (ERROR/WARNING/INFO) — this maps cleanly to desloppify's confidence levels (high/medium/low)

**Exact implementation plan**:

```
.desloppify/plugins/advocacy_language.py
```

This plugin would:
1. Call `register_detector(DetectorMeta(...))` for an `advocacy_language` detector
2. Call `register_scoring_policy(DetectorScoringPolicy(...))` for the new dimension
3. Export a `register()` function

But **here's the gap**: registering a detector in the catalog doesn't wire it into the scan pipeline. You also need a `DetectorPhase` in a `LangConfig.phases` list. Options:

**Option A — New language config** (cleanest, no core changes):
Create a "meta-language" plugin that registers as a new language and runs on all files. The phase function shells out to semgrep/eslint/vale and normalizes results.

**Option B — Fork and add phase to existing languages** (most integrated):
Add a new `phase_advocacy_language()` to TypeScript's, Python's, etc. `phases` list. This requires modifying core language configs.

**Option C — Post-scan hook** (least invasive):
Use `engine/hook_registry.py` to run advocacy checks after the main scan completes, then merge findings into state. This avoids touching language configs entirely.

**Recommendation**: **Option B** for the fork. Since we're forking anyway, adding a phase to each relevant language config is the most architecturally sound approach. The phase function shells out to the appropriate tool (semgrep for code, vale for docs) and normalizes results to desloppify's Issue format.

**Key files to modify**:
- `base/registry/catalog_entries.py` — add `DetectorMeta` for `advocacy_language`
- `engine/_scoring/policy/core.py` — add to `MECHANICAL_DIMENSION_WEIGHTS`
- `languages/typescript/phases.py` — add `phase_advocacy_language()`
- `languages/python/phases.py` — add `phase_advocacy_language()`
- `languages/typescript/__init__.py` — add phase to `phases` list
- `languages/python/__init__.py` — add phase to `phases` list
- New file: `engine/detectors/advocacy_language.py` — the detector that shells out to semgrep/eslint/vale

**Rule mapping**:
| Source | Severity | → desloppify confidence |
|--------|----------|------------------------|
| Semgrep ERROR | Direct violence | HIGH |
| Semgrep WARNING | Speciesism | MEDIUM |
| Semgrep INFO | Embedded jargon | LOW |
| ESLint "suggestion" | All | MEDIUM |
| Vale "warning" | Idioms, metaphors | MEDIUM |
| Vale "suggestion" | Tech terminology | LOW |

### 7.2 Persona-Based Browser QA

**Recommended approach**: **Option D — A separate command** (`desloppify persona-qa`) alongside scan.

**Why**:
- Desloppify is fundamentally static analysis — all detectors operate on source files, not running applications
- Browser QA requires: a running server, Playwright, network access, time-dependent state — none of which fit the `DetectorPhase` contract of `(Path, LangRuntimeContract) → (issues, potentials)`
- The queue/plan system already supports coexisting finding sources — persona QA findings can be merged into state as a separate detector type
- A separate command lets it run independently (different CI stage, different machine, different timing)

**Implementation**:
1. New command: `app/commands/persona_qa/` — orchestrates Playwright browser sessions with persona profiles
2. New detector entry: `DetectorMeta(name="persona_qa", dimension="Persona QA", ...)` — registered in catalog
3. New scoring dimension: `MECHANICAL_DIMENSION_WEIGHTS["persona qa"] = 1.0`
4. Findings written to state in same Issue format, merged with scan findings
5. Queue/plan system picks them up automatically

**Persona profiles** would be config files defining:
- User type (advocate, donor, volunteer, new visitor)
- Browser context (mobile, desktop, screen reader)
- Test scenarios (navigation flows, form submissions, content verification)
- Expected behaviors and assertions

**Constraint**: This is the biggest architectural stretch. Desloppify assumes static analysis throughout — output formatting, state management, queue ranking all assume file-based findings. Persona QA findings would be URL/route-based, which requires adaptation of the display and resolution layers.

### 7.3 Scoring Extension

**Can new dimensions be added?** Yes.

- `register_scoring_policy()` exists and rebuilds DIMENSIONS in-place
- New mechanical dimensions dilute existing mechanical pool proportionally
- New subjective dimensions would need to be added to `SUBJECTIVE_DIMENSION_WEIGHTS`

**Impact of adding "Advocacy Language" (mechanical)**:
- Current mechanical total weight: 6.0 → becomes 7.0
- Each existing dimension's share drops by ~14%
- If advocacy scores high: slight overall boost. If low: slight drag.
- The 25% mechanical fraction of overall score stays constant.

**Impact of adding "Persona QA" (mechanical)**:
- Same dilution math as above
- Since it's a different type of finding (URL-based vs file-based), the `file_based` policy flag and zone exclusions would need careful handling

### 7.4 Windows Hang Fix

**Root causes identified**:

1. **`input()` in TypeScript logs detector** (`languages/typescript/detectors/logs.py:100`):
   ```python
   if args.fix:
       confirm = input("Proceed? [y/N] ").strip().lower()
   ```
   Blocks indefinitely if stdin is closed/redirected.

2. **`msvcrt.locking()` with no timeout** (`engine/_plan/persistence.py:65-90`):
   ```python
   if sys.platform == "win32":
       import msvcrt
       msvcrt.locking(fd, msvcrt.LK_LOCK, 1)  # Blocks until lock acquired
   ```
   If plan.json is held by another process (IDE, antivirus, Windows indexer), hangs indefinitely. Used in `resolve` (plan save), which is in the `next → resolve → next` loop.

**Fix locations**:
- `languages/typescript/detectors/logs.py:100` — replace `input()` with non-blocking confirmation or `--yes` flag
- `engine/_plan/persistence.py:65-90` — add timeout to `msvcrt.locking()` (use `msvcrt.LK_NBLCK` with retry loop and max attempts)

---

## 8. Risk Assessment

### Easy to Extend (Low Risk)
- **Adding detector metadata**: `register_detector()` and `register_scoring_policy()` are designed for this
- **Adding mechanical dimensions**: Weight dictionaries are plain Python dicts, trivially extensible
- **Adding a new CLI command**: Command registry (`app/commands/registry.py`) is a simple dict mapping
- **Skill overlay**: Already supports custom gate instructions

### Requires Careful Surgery (Medium Risk)
- **Adding phases to existing languages**: Requires modifying `LangConfig.phases` in each language's `__init__.py` — straightforward but touches core code
- **Adding URL-based findings**: Display/resolution layers assume file paths — needs adaptation
- **Windows hang fixes**: Small changes but in critical path (plan locking, detector confirmation)

### Requires Refactoring (High Risk)
- **Dynamic analysis integration**: The entire engine assumes static analysis — `LangRuntimeContract`, phase contracts, scoring, display all assume file-based findings. Full browser QA integration would touch 10+ modules.
- **Cross-language detectors**: Current architecture is per-language. A detector that runs on all languages (like advocacy language) needs to be registered in each language's phase list separately.
- **Upstream merge-back**: Any changes to `LangConfig`, scoring constants, or core types would conflict with upstream development.

---

## 9. Recommended Fork Strategy

### Recommendation: **Fork and diverge** (Option A) — with a compatibility layer

**Why not contribute upstream?**
- Animal advocacy language detection is domain-specific — unlikely to be accepted upstream
- Persona QA is architecturally different from desloppify's static analysis model
- The scoring weight changes we'd make (adding dimensions) would affect all users

**Why not a wrapper/plugin?**
- The plugin system can't inject phases into existing languages — it's designed for adding new languages
- The most natural integration (advocacy language phase in each language) requires modifying core language configs
- Persona QA needs a new command, display adaptation, and state management changes

**Fork strategy**:

1. **Fork `peteromallet/desloppify`** → `Open-Paws/desloppify`
2. **Track upstream** via a `upstream/main` remote — periodically merge upstream improvements
3. **Isolate changes** in clearly marked files/sections:
   - New files: `engine/detectors/advocacy_language.py`, `app/commands/persona_qa/`
   - Modified files: language `__init__.py` files (add phase), `catalog_entries.py` (add detector), scoring policy (add dimension)
4. **Keep upstream-compatible where possible**: Don't rename/restructure core types. Add, don't replace.
5. **Version pin**: Lock to a specific upstream commit and update deliberately

**Phase 1** (weeks 1-2): Advocacy language detector
- Add `engine/detectors/advocacy_language.py` that shells out to semgrep
- Add detector metadata and scoring dimension
- Wire into TypeScript and Python language phases
- Test with existing 62 rules from `semgrep-rules-no-animal-violence`

**Phase 2** (weeks 3-4): Persona QA command
- Add `app/commands/persona_qa/` with Playwright integration
- Define persona profile format
- Merge findings into state as standard Issues
- Adapt display layer for URL-based findings

**Phase 3** (ongoing): Windows fixes, skill integration, upstream sync
- Fix `input()` blocking and `msvcrt.locking()` timeout
- Custom skill overlay with advocacy-specific agent instructions
- Periodic upstream merge for bug fixes and new language support

---

## Appendix: Key File Reference

| Component | File Path |
|-----------|-----------|
| Detector metadata model | `base/registry/catalog_models.py` |
| Detector catalog (65+ entries) | `base/registry/catalog_entries.py` |
| Detector registry API | `base/registry/__init__.py` |
| Language framework types | `languages/_framework/base/types.py` |
| Language plugin discovery | `languages/_framework/registry/discovery.py` |
| TypeScript config | `languages/typescript/__init__.py` |
| TypeScript phases | `languages/typescript/phases.py` + `phases_*.py` |
| Python config | `languages/python/__init__.py` |
| Scoring policy & constants | `engine/_scoring/policy/core.py` |
| Health score calculation | `engine/_scoring/results/health.py` |
| Dimension score calculation | `engine/_scoring/results/core.py` |
| Subjective dimension catalog | `base/subjective_dimension_catalog.py` |
| Plan persistence & locking | `engine/_plan/persistence.py` |
| Work queue core | `engine/_work_queue/core.py` |
| Queue ranking | `engine/_work_queue/ranking.py` |
| Scan workflow | `app/commands/scan/workflow.py` |
| Review preparation | `intelligence/review/__init__.py` |
| Skill docs | `app/skill_docs.py` |
| Command registry | `app/commands/registry.py` |
| Windows hang: input() | `languages/typescript/detectors/logs.py:100` |
| Windows hang: locking | `engine/_plan/persistence.py:65-90` |

All paths relative to `desloppify/desloppify/` (the package root inside the repo).
