# Integration Investigation Report

**Purpose**: Map two Open Paws repos to desloppify fork extension points identified in [desloppify-fork-architecture.md](desloppify-fork-architecture.md).

---

## 1. Project Compassionate Code

**Repo**: `Open-Paws/project-compassionate-code`
**What it is**: Not just a ruleset — it's a complete orchestration engine for detecting and fixing speciesist language in open source at scale.

### Architecture

```
project-compassionate-code/
├── scanner/              ← Canonical rule definitions (Python, Click, Rich)
│   └── src/scanner/dictionaries/
│       ├── language/     ← 65 speciesist language rules (5 categories)
│       │   ├── idioms.yaml          (30 rules)
│       │   ├── metaphors.yaml       (21 rules)
│       │   ├── insults.yaml         (6 rules)
│       │   ├── process-language.yaml (5 rules)
│       │   ├── terminology.yaml     (3 rules)
│       │   └── context-rules/       (3 suppression files)
│       └── content-gaps/ ← 2 content gap detectors
│           ├── food-defaults.yaml
│           └── demo-data.yaml
├── transforms/           ← Generates rules for 11 target tool formats
│   └── src/transforms/formats/
│       ├── semgrep.py, eslint.py, vale.py, vscode.py
│       ├── danger.py, precommit.py, github_action.py
│       ├── alex.py, woke.py, huggingface_metric.py
│       └── ...
├── distributions/        ← Pre-generated outputs (INCOMPLETE — see below)
├── content-library/      ← PR content (sanctuary schemas, awesome-list entries)
├── agents/               ← Campaign agent skills + workflows (7 YAML workflows)
├── campaigns/triggers/   ← Seasonal/event campaign triggers
└── metrics/pr-tracker.yaml ← Tracks 100+ repos, merge rates
```

### Rule Inventory

**65 canonical rules** across 5 categories:

| Category | Count | Severity Distribution |
|----------|-------|-----------------------|
| Idioms | 30 | critical: 16, medium: 6, low: 8 |
| Metaphors | 21 | high: 5, medium: 9, low: 7 |
| Insults | 6 | medium: 6 |
| Process Language | 5 | medium: 2, low: 3 |
| Terminology | 3 | high: 2, low: 1 |
| **Total** | **65** | **critical: 16, high: 7, medium: 23, low: 19** |

Plus 3 context-suppression rule files (technical terms, proper nouns, quotations) that reduce false positives.

Plus 2 content gap detectors (food defaults without dietary filters, meat-heavy mock data).

### Target Tool Formats (11 distributions)

The transform engine generates rules for: semgrep, ESLint, Vale, VS Code extension, Danger.js plugin, pre-commit hook, GitHub Action (woke-based), alex/retext-equality, woke linter, HuggingFace metric.

Build command: `uv run transform build --output /tmp/distributions`

### Relationship to Agentic Stack Copies

The repos at `C:\tmp\repos\` (semgrep-rules-no-animal-violence, eslint-plugin-no-animal-violence, etc.) are **distribution targets** — generated outputs pushed to separate repos. The distributions in project-compassionate-code are **incomplete and outdated** (missing Vale entirely). The canonical source is `scanner/src/scanner/dictionaries/language/`.

### Campaign Infrastructure

The repo includes a full PR campaign system:
- **Agent skills**: scan-repo, generate-pr, audit-language, diversify-examples, adopt-tool
- **Workflows**: awesome-list-sweep, dietary-filter-campaign, full-repo-audit, mock-data-sweep, tool-adoption-sweep, two-phase-entry
- **Campaign triggers**: Hacktoberfest, Veganuary, Earth Day, precedent cascade (triggered when a key repo merges)
- **PR tracker**: YAML tracking 100+ repos with status, tier, agent identity (stuckvgn)
- **North star metric**: Cost per merged PR

---

## 2. Structured Coding with AI

**Repo**: `Open-Paws/structured-coding-with-ai`
**What it is**: A comprehensive instruction library providing animal advocacy-specific AI coding rules for 12 different AI tools.

### Tool Coverage (12 tools, 187 files)

| Tool | Files | Format |
|------|-------|--------|
| Claude Code | 25 | CLAUDE.md + .claude/rules/ + .claude/skills/ |
| GitHub Copilot | 34 | .github/instructions/ + prompts/ + chat-modes/ + skills/ |
| Kilo Code | 32 | .kilocode/rules/ + skills/ + memory-bank/ |
| Roo Code | 22 | .roo/rules/ + .roomodes |
| Cursor | 17 | .cursor/rules/ (.mdc format) |
| Augment Code | 17 | .augment/rules/ |
| Cline | 16 | .clinerules/ |
| Windsurf | 17 | .windsurf/rules/ |
| Aider | 2 | CONVENTIONS.md |
| AGENTS.md | 2 | AGENTS.md (universal) |
| Gemini CLI | 2 | GEMINI.md |
| JetBrains Junie | 3 | .junie/guidelines.md |

### Knowledge Base (shared across all 12 tools)

**7 Concerns** (always-active rules):
1. **Security** — 3-adversary model (state surveillance, industry infiltration, AI bias), slopsquatting, rules file backdoor, ag-gag exposure, device seizure, zero-retention APIs
2. **Testing** — Mutation-first, spec-first generation, property-based, 5 anti-patterns, contract tests, adversarial input
3. **Advocacy Domain** — 15+ ubiquitous language terms, 4 bounded contexts (Investigation, Campaigns, Coalition, Legal), anti-corruption layers, 60+ speciesist patterns rejected
4. **Privacy** — Data minimization, activist identity protection, GDPR/CCPA as floor, coalition data sharing, whistleblower protection
5. **Accessibility** — i18n, offline-first, low-bandwidth, low-literacy, mesh networking, device seizure resilience
6. **Emotional Safety** — Progressive disclosure, secondary trauma prevention, burnout tracking, witness testimony display
7. **Cost Optimization** — Model routing, token budgets, 40/30/20/10 budget allocation, cache optimization

**6 Skills** (invocable workflows):
1. Code Review — 5-layer pipeline
2. Git Workflow — Ephemeral branches, atomic commits, PR curation
3. Plan-First Development — Spec → subtask → implement → verify
4. Requirements Interview — 6-phase structured questioning
5. Security Audit — 10-step workflow
6. Testing Strategy — Spec-first, mutation-guided

**10 Ranked AI Failure Modes** (code quality):
DRY violations → shallow modules → multi-responsibility → error suppression → information leakage → language drift → temporal decomposition → legacy churn → over-patterning → tautological tests

### desloppify References

4 tool directories reference desloppify with integration instructions:
- Install: `pip install --upgrade "desloppify[full]"`
- Skill: `desloppify update-skill [tool]`
- Loop: `desloppify scan` → `desloppify next` → fix → resolve → repeat
- `.desloppify/` in `.gitignore`

**No dedicated desloppify skill file exists in this repo.** The desloppify skill lives in the fork itself (`docs/SKILL.md`), with an extended version in the agentic stack (`.claude/skills/desloppify/SKILL.md`).

### Generation System

**None.** Each tool's content is independently authored to maximize use of its native format. Not a template applied 12 times — tool-specific features (Cursor's .mdc activation modes, Kilo Code's memory bank, Copilot's chat modes) are used where available.

### Relationship to Local Projects

The local Open Paws projects have **diverged significantly** from the structured-coding-with-ai templates:
- `agentic-stack/CLAUDE.md` (~111 lines) is an evolved superset of `structured-coding-with-ai/claude-code/CLAUDE.md` (~47 lines)
- `c4c-campus-website/CLAUDE.md` is completely domain-specific (immutable schema rules, C4C database structure)
- `project-compassionate-code/CLAUDE.md` is campaign-specific (merge probability tiers, swarm topology)

The investigation repo is a **template archive** — the base from which project-specific instruction files were originally derived and then evolved.

---

## 3. Integration Plan for Desloppify Fork

### 3.1 Advocacy Language Detector

**What the detector consumes**:

The canonical source is project-compassionate-code's scanner dictionaries, not the distributed tool-specific rules. This is critical — the desloppify detector should consume the **canonical YAML rules directly**, not shell out to semgrep/eslint/vale.

**Source files** (5 rule files + 3 context files):
```
scanner/src/scanner/dictionaries/language/
├── idioms.yaml          (30 rules)
├── metaphors.yaml       (21 rules)
├── insults.yaml         (6 rules)
├── process-language.yaml (5 rules)
├── terminology.yaml     (3 rules)
└── context-rules/
    ├── technical-terms.yaml
    ├── proper-nouns.yaml
    └── quotations.yaml
```

**Revised approach** (updating the fork architecture report):

The original report recommended shelling out to semgrep/eslint/vale. Now that we know project-compassionate-code has:
1. Canonical YAML rules with regex patterns
2. A Python scanner engine that already parses them
3. Context-aware false positive suppression

The better approach is a **native Python detector** that reads the canonical YAML rules directly. This avoids external tool dependencies entirely.

**Why native Python beats shelling out**:
- Rules are simple regex patterns with alternatives — trivial to evaluate in Python
- Context suppression rules are YAML-defined — no need for semgrep's AST
- No dependency on semgrep/eslint/vale installations
- Faster execution (no subprocess overhead)
- The scanner engine already exists and can be adapted

**Severity mapping**:

| Canonical severity | → desloppify confidence | Rationale |
|-------------------|------------------------|-----------|
| critical | HIGH | Direct violence normalization |
| high | HIGH | Speciesist framing |
| medium | MEDIUM | Common idioms, insults |
| low | LOW | Embedded jargon, process language |
| info | LOW | Educational/documentation only |

**Minimum viable integration**: The 65 language rules as a native Python detector. Content gap detection (food defaults, demo data) can come later.

**Dependencies**: PyYAML (already an optional dep in desloppify via `[plan-yaml]`).

### 3.2 Agent Instruction Integration

**Three integration paths**:

**a) Desloppify skill overlay** — The fork's skill system (update-skill) should include advocacy-specific gate instructions. These come from structured-coding-with-ai's knowledge base, specifically:
- The advocacy domain rules (ubiquitous language, bounded contexts)
- The 60+ speciesist pattern rejection list
- The security threat model (3 adversaries)

This content goes in the skill overlay section between `<!-- desloppify-overlay -->` and `<!-- desloppify-end -->`.

**b) Instruction files reference desloppify** — Already true. 4 of 12 tool sets in structured-coding-with-ai reference desloppify with install + workflow instructions.

**c) Instruction file generation** — NOT viable. The tool-specific files are independently authored, not generated from a template. They leverage tool-specific features (Cursor .mdc activation modes, Kilo Code memory bank, Copilot chat modes). A generation system would lose these native features.

**Recommendation**: structured-coding-with-ai remains the template archive. Project-specific CLAUDE.md files are maintained locally per project. The desloppify skill is maintained in the fork itself, with overlays for advocacy-specific gates.

### 3.3 PR Campaign Integration

project-compassionate-code's campaign system (scan → generate PR → submit → track) maps to a potential desloppify workflow:

```
desloppify scan --path <external-repo>    → finds advocacy language issues
desloppify next                           → prioritizes fixes
[agent generates fixes]                   → guided by skill instructions
desloppify plan resolve                   → marks fixed
[agent generates PR]                      → using campaign PR templates
```

**Available from project-compassionate-code**:
- PR templates with tier-appropriate framing (Tier 1: tooling adoption, Tier 2: content improvement, Tier 3: feature contribution)
- Target repo evaluation criteria
- Agent identity and values prompts
- Campaign workflow YAML definitions
- Merge rate tracking

**Integration**: This is a **workflow extension**, not a detector. It would be a new desloppify skill (`campaign-pr`) that combines scan results with PR generation templates. Low priority compared to the detector itself.

---

## 4. Consolidation Recommendations

### Source of Truth

| Content | Canonical Source | Consumers |
|---------|-----------------|-----------|
| **Advocacy language rules** | project-compassionate-code `scanner/src/scanner/dictionaries/` | desloppify detector, 11 distribution repos |
| **AI tool instruction templates** | structured-coding-with-ai | New projects (template), NOT existing projects |
| **Project-specific instructions** | Each project's own CLAUDE.md / .cursorrules | That project's AI agents |
| **Desloppify skill** | desloppify fork `docs/SKILL.md` | All projects using desloppify |
| **Desloppify skill overlay (advocacy)** | desloppify fork (new, to be created) | Open Paws projects |

### What Lives Where

**In the desloppify fork**:
- `engine/detectors/advocacy_language.py` — native Python detector consuming canonical YAML rules
- `engine/detectors/advocacy_rules/` — copy of (or submodule link to) the 5 rule YAML files + 3 context files from project-compassionate-code
- Detector metadata, scoring policy, language phase wiring (per fork architecture report)
- Advocacy-specific skill overlay content

**In project-compassionate-code** (unchanged):
- Canonical YAML rule definitions (single source of truth)
- Transform engine generating distributions
- Campaign orchestration system
- PR tracking and agent workflows

**In structured-coding-with-ai** (unchanged):
- Template archive for new projects
- Reference implementation of advocacy-aware AI tool configuration
- NOT a generation source — each project evolves independently

### Repos That Become Redundant

**None become fully redundant**, but roles clarify:

| Repo | Current Role | After Integration |
|------|-------------|-------------------|
| semgrep-rules-no-animal-violence | Distribution target | Unchanged (external tool users need it) |
| eslint-plugin-no-animal-violence | Distribution target | Unchanged |
| vale-no-animal-violence | Distribution target | Unchanged |
| no-animal-violence | Master distribution | Unchanged |
| no-animal-violence-action | GitHub Action | Unchanged |
| structured-coding-with-ai | Template archive | Unchanged (but no longer the active source for existing projects) |

The distribution repos serve external consumers (people who want semgrep rules without desloppify). They remain valid. The desloppify fork adds a new consumption path (native Python detector) alongside the existing tool-specific distributions.

### Migration Order

1. **Create the native Python detector** in the desloppify fork, consuming canonical YAML rules from project-compassionate-code
2. **Copy the 8 YAML rule files** into the fork (or use git submodule)
3. **Wire the detector** into TypeScript and Python language phases
4. **Create the advocacy skill overlay** for the desloppify skill system
5. **Update structured-coding-with-ai** desloppify references to point to the fork
6. **Campaign integration** (PR workflow) as a later phase

### Key Decision: Copy vs. Submodule for Rules

**Option A — Copy rules into fork**: Simpler, no submodule complexity. Rules change rarely (65 patterns, stable). Risk: drift if rules are updated in project-compassionate-code.

**Option B — Git submodule**: Keeps single source of truth. Adds submodule complexity. Rules update automatically on submodule pull.

**Option C — Build step**: The desloppify fork's CI pulls latest rules from project-compassionate-code during build. Most correct, most complex.

**Recommendation**: Option A (copy) for now. The 65 rules are stable and change infrequently. When the rule count grows significantly, revisit with Option B or C.
