# Desloppify — Agent Instructions

Open Paws fork of [peteromallet/desloppify](https://github.com/peteromallet/desloppify). Multi-language codebase health scanner (29 languages) that combines mechanical detection with LLM-based subjective review. This fork adds advocacy-specific detectors for speciesist language, activist security antipatterns, and persona-based browser QA.

## Organizational Context

**Role in ecosystem:** desloppify is the quality gate for the entire Open Paws ecosystem. It enforces three concerns that go beyond typical code quality tools: (1) speciesist language detection (65 rules sourced from `no-animal-violence`), (2) activist security antipatterns (three-adversary threat model), and (3) persona-based browser QA. It also generates agent skill files for 6 AI tools (Claude Code, Cursor, Copilot, Codex, Windsurf, Gemini), which means it is a distribution channel for the structured-coding-with-ai methodology.

**Layer:** 1 — Strengthen. Lever: Strengthen.

**Platform integration:** Core development workflow for all Open Paws repos. Not connected to the platform directly.

**Minimum passing scores:**
- Gary: ≥ 98
- Platform repos: ≥ 90
- All other repos (including this one): ≥ 85

**Upstream tracking:** Fork tracks `peteromallet/desloppify` as `upstream` remote. Fork-specific code lives in new files. Upstream merges: `git fetch upstream && git merge upstream/main`.

**Strategy references:**
- `open-paws-strategy/ecosystem/repos.md` — desloppify entry with full feature breakdown
- `open-paws-strategy/ecosystem/integration-todos.md` — integration todos for connecting desloppify to downstream consumers
- `open-paws-strategy/closed-decisions.md` — 2026-04-01 external contribution safety (advocacy language detector is used by project-compassionate-code)

## Quick Start

```bash
# Requires Python 3.11+
pip install -e ".[full]"          # editable install with all extras
desloppify scan --path .          # run all mechanical detectors
desloppify status                 # view scores
desloppify next                   # get top-priority fix item
```

## Architecture

```
desloppify/                  # Python package root
  cli.py                     # CLI entry point (desloppify.cli:main)
  state.py                   # Persistent scan state (JSON)
  state_compat.py            # State backwards compatibility
  state_io.py                # State I/O operations
  state_score_snapshot.py    # Score snapshot management
  state_scoring.py           # Score computation
  app/
    commands/                # All CLI commands (scan, review, plan, next, persona_qa, ...)
    cli_support/             # Argument parsing
    output/                  # Terminal formatting
    skill_docs.py            # Agent skill file generation
  base/
    config/                  # Runtime config, project detection
    discovery/               # File discovery, zone mapping
    registry/                # Detector metadata catalog
    scoring_constants.py     # Dimension weights, tier thresholds
    subjective_dimensions.py # Subjective scoring framework
  engine/
    detectors/               # All mechanical detectors (see below)
    _scoring/                # Score aggregation
    _plan/                   # Plan/triage state machine
    _work_queue/             # Priority queue for fixes
    policy/                  # Scoring policy rules
  intelligence/
    review/                  # Subjective review orchestration
    narrative/               # Natural language summaries
  languages/                 # Per-language plugins (32 dirs)
    _framework/              # Shared language framework
    python/, typescript/, ...# Language-specific detectors + configs
  data/global/               # Shared markdown templates (CLAUDE.md overlays per AI tool)
  tests/                     # Pytest suite (mirrors source layout)

docs/                        # Agent overlay docs (CLAUDE.md, CURSOR.md, etc.)
dev/                         # Release and review scripts
website/                     # Landing page (static HTML/CSS/JS)
assets/                      # Images for README
.github/workflows/           # CI: ci.yml, integration.yml, python-publish.yml
```

## Key Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Package metadata, dependencies, pytest/ruff/mypy config |
| `Makefile` | CI targets: `make lint`, `make typecheck`, `make tests`, `make ci` |
| `desloppify/cli.py` | CLI entry point |
| `desloppify/state.py` | Persistent scan state (JSON serialization) |
| `desloppify/base/scoring_constants.py` | Dimension weights and tier thresholds |
| `desloppify/engine/detectors/` | All mechanical detectors |
| `desloppify/engine/detectors/advocacy_language.py` | Speciesist language detector (65 rules) |
| `desloppify/engine/detectors/advocacy_security.py` | Activist security antipattern detector |
| `desloppify/engine/detectors/advocacy_rules/` | YAML rule definitions (idioms, metaphors, insults, process-language, terminology) |
| `desloppify/app/commands/persona_qa/` | Persona-based browser QA command |
| `desloppify/app/commands/scan/` | Scan command and reporting |
| `desloppify/app/commands/review/` | Subjective review orchestration |
| `desloppify/app/commands/plan/` | Plan/triage command |
| `desloppify/app/commands/next/` | Next fix command |
| `desloppify/data/global/CLAUDE.md` | Claude subagent overlay (review + triage workflow) |
| `docs/CLAUDE.md` | Claude subagent overlay (identical to data/global/CLAUDE.md) |
| `.pre-commit-config.yaml` | Pre-commit: no-animal-violence hook |
| `.semgrep.yml` | Semgrep config pointing to Open Paws rules |

## Development

```bash
# Install dev dependencies
make install-ci-tools         # minimal: pytest, mypy, ruff, import-linter
make install-full-tools       # full: adds tree-sitter, bandit, Pillow, PyYAML

# Lint
make lint                     # ruff (fatal errors only)
ruff check .                  # full ruff

# Type check
make typecheck                # mypy (subset of files configured in pyproject.toml)

# Tests
make tests                    # pytest (core tests)
make tests-full               # pytest with full extras installed

# Architecture contracts
make arch                     # import-linter layer boundary checks

# Full CI pipeline
make ci-fast                  # lint + typecheck + arch + contracts + tests
make ci                       # ci-fast + full tests + package smoke test

# Package smoke test
make package-smoke            # build wheel, install in venv, verify CLI works
```

Detectors are pure functions returning `(entries, metadata)`. They are registered in `base/registry/catalog_entries.py` (metadata) and wired into language-specific phase lists. No base class inheritance.

Overall score = 25% mechanical + 75% subjective. Subjective scores start at 0% until a review is run.

## Open Paws Additions

Beyond the upstream fork, this repo adds:

### Advocacy Language Detector (`engine/detectors/advocacy_language.py`)

65 YAML-defined rules detecting speciesist idioms, metaphors, insults, process language, and terminology in code, comments, and docs across all 29 languages plus `.md`/`.txt`/`.rst`. Context suppression for technical terms (POSIX `kill()`, git `master`), proper nouns, and quotations. Each finding includes a suggested replacement. Rules sourced from [project-compassionate-code](https://github.com/Open-Paws/project-compassionate-code).

### Advocacy Security Detector (`engine/detectors/advocacy_security.py`)

Heuristic detector for activist protection antipatterns against three adversary classes: state surveillance, industry infiltration, and AI model bias. Detects identity leakage, sensitive data to external APIs without zero-retention headers, investigation materials in public paths, unencrypted sensitive data writes, IP logging, and sensitive data in browser storage.

### Persona-Based Browser QA (`app/commands/persona_qa/`)

`desloppify persona-qa` command for browser-based testing with configurable persona profiles (YAML). Findings integrate into the standard work queue alongside mechanical and subjective issues.

### Three New Scoring Dimensions

Advocacy language, advocacy security, and persona QA — each weight 1.0, integrated into the mechanical score.

### Windows Platform Fixes

`input()` blocking fix, `msvcrt.locking()` timeout fix, dataclass JSON serialization fix.

### Pre-commit and Semgrep Integration

`.pre-commit-config.yaml` hooks into Open Paws `no-animal-violence-pre-commit`. `.semgrep.yml` points to `semgrep-rules-no-animal-violence`.

### Upstream Tracking

Fork tracks `peteromallet/desloppify` as `upstream` remote. Fork-specific code lives in new files. Upstream merges should be clean: `git fetch upstream && git merge upstream/main`.

## Development Standards

### 10-Point Review Checklist (ranked by AI violation frequency)

Apply to every PR:

1. **DRY** — AI clones code at 4x the human rate. Search before writing anything new
2. **Deep modules** — Reject shallow wrappers and pass-through methods. Interface must be simpler than implementation (Ousterhout)
3. **Single responsibility** — Each function does one thing at one level of abstraction
4. **Error handling** — Never catch-all. AI suppresses errors and removes safety checks. Every catch block must handle specifically
5. **Information hiding** — Don't expose internal state. Mask API keys (last 4 chars only)
6. **Ubiquitous language** — Use movement terminology consistently. Never let AI invent synonyms for domain terms
7. **Design for change** — Abstraction layers and loose coupling. Tools must outlast individual campaigns
8. **Legacy velocity** — AI code churns 2x faster. Use characterization tests before modifying existing code
9. **Over-patterning** — Simplest structure that works. Three similar lines of code is better than a premature abstraction
10. **Test quality** — Every test must fail when the covered behavior breaks. Mutation score over coverage percentage

### Quality Gates

**Desloppify (self-scan)** — Target score: ≥ 85.

```bash
desloppify scan --path .
desloppify next
```

**Speciesist language** — Run `semgrep --config semgrep-no-animal-violence.yaml` on all code/docs edits. Pre-commit hook runs automatically.

**Type checking** — `make typecheck` before pushing.

**Full CI** — `make ci` before merging.

**Two-failure rule** — After two failed fixes on the same problem, stop and restart with a better approach.

### Testing Methodology

- Spec-first test generation preferred
- Reject: snapshot trap, mock everything, happy path only, test-after-commit, coverage theater
- Three questions per test: (1) Does it fail if code is wrong? (2) Does it encode a domain rule? (3) Would mutation testing kill it?
- Tests live in `desloppify/tests/` mirroring the source layout

### Plan-First Development

Read existing code → identify what changes → write specification → break into subtasks → plan-test-implement-verify each → comprehension check → commit per subtask

### Structured Coding Reference

For tool-specific AI coding instructions (Claude Code rules, Cursor MDC, Copilot, Windsurf, etc.), copy the corresponding directory from `structured-coding-with-ai` into this project root.

### Seven Concerns — desloppify-specific implications

All 7 always apply. Critical for this repo:

1. **Testing** — Detectors are pure functions. Test every detector with positive cases (should fire), negative cases (should not fire), and edge cases (context suppression). Add to `desloppify/tests/detectors/`
2. **Security** — desloppify analyzes codebases that may contain investigation data. The tool must not log file contents, only findings. Review mode packets must strip sensitive file content before sending to LLM providers
3. **Privacy** — Review packets (`review_packet_blind.json`) must not include actual code content from sensitive paths (`.env`, credentials, investigation materials)
4. **Cost** — Subjective review uses LLM API calls. Batch them. The parallel review workflow splits dimensions across subagents to minimize cost per review
5. **Advocacy domain** — The advocacy language detector IS the advocacy domain enforcement mechanism. Rules must be precise — false positives erode developer trust
6. **Accessibility** — CLI output must work without color (plain terminals, CI logs). Terminal formatting in `app/output/` must have no-color fallback
7. **Emotional safety** — Review prompts and findings must not include graphic investigation content as examples. Abstract test data in `desloppify/tests/`

### Advocacy Domain Language

Use these terms consistently. Never introduce synonyms:
- **Campaign** — organized advocacy effort (not "project" or "initiative")
- **Investigation** — covert documentation (not "research" or "audit")
- **Coalition** — multi-org alliance
- **Farmed animal** — not "livestock"
- **Factory farm** — not "farm" or "facility"
- **Ag-gag** — laws criminalizing undercover agricultural investigation
