# Work Batch Ticket Digest

## Purpose
This document translates commit history into ticket-style work batches so an engineer can quickly understand intent, scope, execution details, and operational risk without replaying every diff manually.

## Scope and Method
- Commits covered: **111**.
- Batching logic: contiguous ranges grouped by feature wave and refactor objective.
- Churn reporting: includes raw line churn and source-focused churn (excluding backup/cache/build artifacts) where relevant.

## Quick Index
- B01: Foundation Reset: Generic Language Framework + Type/Test Hardening
- B02: Packaging Automation + Go Plugin Graduation
- B03: Blind-Review Workflow Wave + Mixed-Language State Stability
- B04: Quality-of-Life Pass: Scorecard Readability, Naming Consistency, Compatibility
- B05: Batch Runner Reliability + Interface Surface Expansion (OpenCode)
- B06: Planning Engine Rollout + Command Surface Convergence
- B07: Evidence Model Shift + Vocabulary Standardization
- B08: F6 Reorganization: Core/Base Rename, Contract Enforcement, CI Recovery
- B09: Queue/Cluster Lifecycle Redesign + Narrative/Review Extraction Wave
- B10: Final Decomposition Sweep + Review Integrity Clarifications + XML Security Hardening

## B01 - Foundation Reset: Generic Language Framework + Type/Test Hardening

**Batch metadata**
- Commits in batch: **16**

**Objective**
- Rebuild the architecture around a generic multi-language framework while preserving behavior through broad test expansion and type tightening.

**Problem this batch addressed**
- Legacy module boundaries and import patterns were drifting, causing layer violations and hidden coupling.
- Language support was fragmented and expensive to extend consistently.
- Coverage and test-signal reliability were insufficient for aggressive refactoring.

**Implementation delivered**
- Introduced a large generic language framework refactor plus tree-sitter integration across 28 languages.
- Performed canonical import cleanup and facade normalization to reduce cross-layer leakage.
- Strengthened type contracts (StateModel, TypedDict usage, facade boundaries, annotations).
- Added 293 behavioral tests across 17 files, then fixed follow-on language and coverage regressions.
- Repaired coverage graph resolution and PROJECT_ROOT runtime handling so test coverage detection reaches 100%.
- Closed review findings from the refactor wave with additional structural and safety adjustments.
- Updated core docs/README content to match the architectural direction and usage model.

**Scope metrics**
- Raw churn: `+23390 / -9405` lines
- Source-focused churn (excluding backup/cache/build artifacts): `+23390 / -9405` lines
- Binary files changed: `6`
- Most active source directories: `desloppify/app/commands` (4830), `desloppify/languages/_framework` (4024), `desloppify/tests/commands` (3058), `desloppify/tests/lang` (3005), `desloppify/tests/detectors` (2164), `desloppify/languages/python` (1745)
- Most active source files: `desloppify/tests/lang/common/test_treesitter.py` (1768), `desloppify/tests/detectors/test_concerns.py` (1214), `desloppify/tests/commands/test_transitive_engine.py` (976), `desloppify/languages/_framework/treesitter/_specs.py` (801), `desloppify/README.md` (763), `desloppify/languages/_framework/treesitter/_imports.py` (748)
- Most frequently touched subsystems (source only): Language frameworks/plugins (289), Tests (142), Engine/scoring core (107), Intelligence/review context (85), General command layer (64), Misc (49)

**Commit-by-commit intent (dev-ticket granularity)**
- `ed15a1b`: Major refactoring: generic language framework, tree-sitter integration, 28 languages — updated 345 files (+12533 / -5947), focused on language plugins, tests. Key files: `desloppify/tests/lang/common/test_treesitter.py`, `desloppify/languages/_framework/treesitter/_specs.py`.
- `4bce636`: Update documentation: philosophy, language guide, fix paths — updated 5 files (+171 / -189), focused on packaging/config, docs. Key files: `desloppify/languages/README.md`, `README.md`.
- `bea3fe7`: Remove LLM-sounding language from documentation — updated 2 files (+37 / -369), focused on docs. Key files: `desloppify/README.md`, `README.md`.
- `0fff1d8`: Rewrite README intro, add agent-specific overlays for 6 platforms — updated 6 files (+255 / -20), focused on docs. Key files: `docs/GEMINI.md`, `docs/COPILOT.md`.
- `a36eb14`: Rewrite philosophy section with more human voice — updated 1 files (+6 / -6), focused on docs. Key file: `README.md`.
- `0767f8b`: Refocus attestation on confirming the fix, not justifying a score — updated 3 files (+10 / -10), focused on CLI surface, engine/scoring core. Key files: `desloppify/engine/_work_queue/helpers.py`, `desloppify/app/cli_support/parser.py`.
- `3dd2d35`: Major architecture cleanup: migrate imports to canonical sources, flatten modules, lazy init — updated 144 files (+1411 / -799), focused on language plugins, command layer. Key files: `desloppify/app/commands/review/batch_core.py`, `desloppify/utils.py`.
- `3ee97ba`: Deep architecture cleanup: remove utils re-exports, create work_queue facade, fix deferred imports — updated 129 files (+1099 / -513), focused on language plugins, review intelligence. Key files: `desloppify/utils.py`, `desloppify/app/commands/update_skill.py`.
- `32a01b7`: Add __all__ to 10 modules, fix type annotations, fix engine layer violations — updated 32 files (+410 / -232), focused on engine/scoring core, tests. Key files: `desloppify/intelligence/narrative/core.py`, `desloppify/tests/review/test_holistic_review.py`.
- `0016271`: Type safety: StateModel annotations, proper TypedDicts, remove frame introspection — updated 16 files (+139 / -67), focused on engine/scoring core, language plugins. Key files: `desloppify/engine/_state/schema.py`, `desloppify/app/commands/scan/scan_reporting_llm.py`.
- `c4fed4d`: Type safety and facade enforcement: StateModel across narrative, facade imports, _ModeAccum dataclass — updated 49 files (+229 / -488), focused on tests, docs. Key files: `desloppify/app/commands/status_parts/transparency.py`, `desloppify/app/commands/_show_terminal.py`.
- `b25f025`: Add 293 behavioral tests across 17 new test files — updated 17 files (+3975 / -0), focused on tests, language plugins. Key files: `desloppify/tests/review/test_review_policy.py`, `desloppify/languages/csharp/tests/test_csharp_deps_cli.py`.
- `c1d163d`: Fix test coverage detector: resolve submodule imports in dep graph — updated 3 files (+41 / -16), focused on language plugins, misc files. Key files: `desloppify/languages/python/detectors/deps.py`, `desloppify/languages/python/test_coverage.py`.
- `af3434f`: Fix 78 failing lang tests and add facade-aware test coverage — updated 12 files (+49 / -10), focused on language plugins, engine/scoring core. Key files: `desloppify/engine/detectors/coverage/mapping.py`, `desloppify/languages/gdscript/tests/test_init.py`.
- `ff3013a`: Fix PROJECT_ROOT via RuntimeContext and achieve 100% test coverage detection — updated 25 files (+1866 / -168), focused on language plugins, tests. Key files: `desloppify/tests/commands/test_transitive_engine.py`, `desloppify/tests/commands/test_transitive_modules.py`.
- `345c440`: Resolve all 18 review findings: structural refactors, type safety, test coverage — updated 48 files (+1159 / -571), focused on language plugins, engine/scoring core. Key files: `desloppify/tests/detectors/test_concerns.py`, `desloppify/intelligence/narrative/types.py`.

**Validation and acceptance signals**
- Regression pressure absorbed by new behavioral tests and language-specific suites.
- Type-level constraints tightened incrementally across architecture cleanups.
- Follow-up commits directly address newly exposed breakages, indicating active correction loop.

**Known risk and tradeoff profile**
- Large concentrated change volume increases hidden coupling risk despite tests.
- Cross-language framework abstractions may still conceal edge-case parser variance.
- Documentation and structure moved quickly; onboarding still depends on source literacy.

**Suggested follow-up tickets**
- Keep adding contract tests around framework extension points.
- Audit remaining private imports as part of ongoing boundary enforcement.

## B02 - Packaging Automation + Go Plugin Graduation

**Batch metadata**
- Commits in batch: **7**

**Objective**
- Operationalize repeatable package automation while shipping a fuller Go language implementation.

**Problem this batch addressed**
- Publication process needed less manual friction and stricter CI guardrails.
- Go support existed but needed parity improvements to behave like first-class plugins.
- Packaging progression required explicit contract checks to avoid publishing broken artifacts.

**Implementation delivered**
- Shipped packaging metadata updates with Python requirement/install corrections.
- Added and then refined GitHub Actions PyPI publish workflow for package + push-based tag-change detection.
- Upgraded Go from generic mode into a full plugin with dedicated extractors/tests/docs updates.
- Introduced CI contract tests and hardened baseline stability checks.
- Aligned repository gates so packaging/CI behavior matches expected package discipline.

**Scope metrics**
- Raw churn: `+2124 / -135` lines
- Source-focused churn (excluding backup/cache/build artifacts): `+2124 / -135` lines
- Binary files changed: `1`
- Most active source directories: `desloppify/languages/go` (902), `desloppify/languages/python` (491), `.github/workflows/python-publish.yml` (169), `desloppify/tests/ci` (142), `.github/workflows/ci.yml` (123), `docs/ci_plan.md` (108)
- Most active source files: `desloppify/languages/python/tests/test_py_uncalled.py` (338), `desloppify/languages/go/extractors.py` (271), `desloppify/languages/go/tests/test_extractors.py` (233), `.github/workflows/python-publish.yml` (169), `desloppify/tests/ci/test_ci_contracts.py` (141), `desloppify/languages/go/__init__.py` (132)
- Most frequently touched subsystems (source only): Language frameworks/plugins (19), Packaging/project config (8), CI automation (7), Tests (5), Documentation (4), Misc (2)

**Commit-by-commit intent (dev-ticket granularity)**
- `1c73c4f`: packaged PyPI publication, fix Python runtime requirement, update install instructions — updated 12 files (+551 / -14), focused on language plugins, packaging/config. Key files: `desloppify/languages/python/tests/test_py_uncalled.py`, `desloppify/languages/python/detectors/uncalled.py`.
- `8739f49`: Add GitHub Actions workflow for PyPI publishing on package — updated 1 files (+63 / -0), focused on CI/workflows. Key file: `.github/workflows/python-publish.yml`.
- `aa1ff8a`: Bump package tag — updated 1 files (+1 / -1), focused on packaging/config. Key file: `pyproject.toml`.
- `119be4d`: Upgrade Go from generic to full language plugin (from PR #128) — updated 21 files (+890 / -63), focused on language plugins, tests. Key files: `desloppify/languages/go/extractors.py`, `desloppify/languages/go/tests/test_extractors.py`.
- `fc436fe`: Auto-publish to PyPI on push to main when tag changes — updated 1 files (+33 / -38), focused on CI/workflows. Key file: `.github/workflows/python-publish.yml`.
- `4de9092`: Harden CI contracts and bump package tag — updated 9 files (+556 / -13), focused on CI/workflows, packaging/config. Key files: `desloppify/tests/ci/test_ci_contracts.py`, `.github/workflows/ci.yml`.
- `d0667c1`: Stabilize CI gates against repository baseline — updated 5 files (+30 / -6), focused on packaging/config, CI/workflows. Key files: `.github/importlinter.ini`, `Makefile`.

**Validation and acceptance signals**
- Dedicated CI contract tests were introduced and iterated.
- PyPI automation logic moved from static to change-aware flow.
- Go extractor behavior backed by targeted tests in language module.

**Known risk and tradeoff profile**
- Automation based on tag-diff checks can still fail on unusual branch/package strategies.
- Go plugin expansion can surface parser edge cases not present in generic mode.

**Suggested follow-up tickets**
- Add smoke publish dry-run in CI for tag and main-push scenarios.
- Track Go detector false-positive/false-negative trends after plugin graduation.

## B03 - Blind-Review Workflow Wave + Mixed-Language State Stability

**Batch metadata**
- Commits in batch: **7**

**Objective**
- Deliver blind-review workflow improvements and stabilize scan/review behavior in mixed-language repos.

**Problem this batch addressed**
- Review workflow complexity (history, prompting, imports) was producing brittle behavior and noisy output.
- Type and state fallbacks around batch file collection and post-scan language state were fragile.
- Packaging progression required bundling large functional review updates without losing traceability.

**Implementation delivered**
- Protected debug-log fixer behavior to avoid stripping logger wrappers.
- Shipped broad blind-review workflow updates (package commit with extensive tests and command changes).
- Applied local pending workflow updates and promoted tagged build.
- Fixed mypy unreachable branch in review batch collection path.
- Fixed mixed-language state fallback after scan for better multi-language continuity.
- Simplified review issue history while adding structural-pattern prompting support.
- Released the batch as tagged build with improved review ergonomics.

**Scope metrics**
- Raw churn: `+15831 / -5465` lines
- Source-focused churn (excluding backup/cache/build artifacts): `+15831 / -5465` lines
- Binary files changed: `2`
- Most active source directories: `desloppify/tests/review` (7002), `desloppify/app/commands` (6885), `desloppify/tests/commands` (1592), `desloppify/languages/_framework` (936), `desloppify/languages/typescript` (589), `desloppify/intelligence/review` (577)
- Most active source files: `desloppify/tests/review/test_review.py` (2587), `desloppify/tests/review/test_review_commands.py` (1993), `desloppify/tests/review/test_review_misc.py` (716), `desloppify/app/commands/review/import_helpers.py` (709), `desloppify/app/commands/review/batches.py` (691), `desloppify/app/commands/review/runner_helpers.py` (560)
- Most frequently touched subsystems (source only): Tests (84), Language frameworks/plugins (77), Intelligence/review context (28), Review command workflow (26), Engine/scoring core (26), General command layer (20)

**Commit-by-commit intent (dev-ticket granularity)**
- `3a22926`: Protect debug-log fixer from removing logger wrappers — updated 2 files (+200 / -1), focused on language plugins. Key files: `desloppify/languages/typescript/fixers/logs.py`, `desloppify/languages/typescript/tests/test_ts_fixers.py`.
- `d497501`: Merge pull request #131 from peteromallet/codex/issue-126-debug-logs — merge/integration commit with no direct file diff in this changeset.
- `ad8afad`: package: ship blind-review workflow updates and bump package tag — updated 232 files (+11076 / -5096), focused on language plugins, tests. Key files: `desloppify/tests/review/test_review.py`, `desloppify/tests/review/test_review_commands.py`.
- `a548bde`: Apply local pending changes and bump package tag — updated 33 files (+1178 / -50), focused on tests, command layer. Key files: `desloppify/app/commands/issues_cmd.py`, `desloppify/tests/review/test_review_commands.py`.
- `74fc323`: Fix mypy unreachable branch in review batch file collection — updated 1 files (+1 / -3), focused on review workflow. Key file: `desloppify/app/commands/review/batches.py`.
- `3b21ad2`: Fix mixed-language state fallback after scan — updated 2 files (+82 / -2), focused on command layer, tests. Key files: `desloppify/tests/commands/test_cli.py`, `desloppify/app/commands/helpers/state.py`.
- `8775d23`: Simplify review issue history, add structural-pattern prompting, bump to tagged build — updated 53 files (+3294 / -313), focused on tests, review workflow. Key files: `desloppify/app/commands/review/batches.py`, `desloppify/tests/review/test_review_commands.py`.

**Validation and acceptance signals**
- Large review-focused test churn indicates explicit regression coverage expansion.
- Mypy/static correctness fixes landed immediately around collection logic.
- Multiple package bumps indicate correction after broad functional merge.

**Known risk and tradeoff profile**
- High-volume workflow commits can hide subtle review scoring regressions.
- Prompt logic changes may shift qualitative output unexpectedly between runs.

**Suggested follow-up tickets**
- Pin review prompt snapshots for deterministic diff-based QA.
- Continue mixed-language repository fixture expansion for state transitions.

## B04 - Quality-of-Life Pass: Scorecard Readability, Naming Consistency, Compatibility

**Batch metadata**
- Commits in batch: **4**

**Objective**
- Tighten user-facing polish and remove footguns discovered after rapid package iterations.

**Problem this batch addressed**
- Scorecard display and naming conventions were inconsistent and sometimes hard to read.
- Python 3.13 compatibility surfaced a tree-sitter normalization bug.
- A missing CLI flag registration could break advanced review flows.

**Implementation delivered**
- Increased scorecard dimension name column width to prevent truncation.
- Standardized dimension labels to sentence case across detectors/output/tests.
- Fixed Python 3.13 TypeError in tree-sitter normalization path.
- Registered missing `--confirm-batch-wontfix` flag and released tagged build.

**Scope metrics**
- Raw churn: `+559 / -249` lines
- Source-focused churn (excluding backup/cache/build artifacts): `+559 / -249` lines
- Binary files changed: `1`
- Most active source directories: `desloppify/tests/scoring` (142), `desloppify/tests/detectors` (101), `desloppify/app/output` (100), `desloppify/intelligence/review` (89), `desloppify/tests/review` (89), `desloppify/engine/detectors` (81)
- Most active source files: `desloppify/tests/detectors/test_test_coverage.py` (101), `desloppify/app/output/scorecard_parts/dimension_policy.py` (96), `desloppify/intelligence/review/importing/holistic.py` (87), `desloppify/engine/detectors/test_coverage/detector.py` (81), `desloppify/tests/scoring/test_scorecard.py` (80), `desloppify/tests/review/test_review_commands.py` (49)
- Most frequently touched subsystems (source only): Tests (21), Misc (4), Engine/scoring core (3), Intelligence/review context (2), Language frameworks/plugins (2), Review command workflow (1)

**Commit-by-commit intent (dev-ticket granularity)**
- `ff62e86`: Widen scorecard name column to prevent dimension name truncation — updated 1 files (+1 / -1), focused on misc files. Key file: `desloppify/app/output/scorecard_parts/draw.py`.
- `12195fb`: Use sentence case for all dimension display names — updated 32 files (+550 / -246), focused on tests, misc files. Key files: `desloppify/tests/detectors/test_test_coverage.py`, `desloppify/app/output/scorecard_parts/dimension_policy.py`.
- `a2dfdbb`: Fix Python 3.13 TypeError in tree-sitter normalization — updated 1 files (+1 / -1), focused on language plugins. Key file: `desloppify/languages/_framework/treesitter/_normalize.py`.
- `c990cb4`: Register missing --confirm-batch-wontfix CLI flag, bump to tagged build — updated 2 files (+7 / -1), focused on CLI surface, packaging/config. Key files: `desloppify/app/cli_support/parser_groups.py`, `pyproject.toml`.

**Validation and acceptance signals**
- Scoring and detector tests were updated alongside policy/name changes.
- CLI parser and package metadata changed together for flag correctness.

**Known risk and tradeoff profile**
- Display policy changes can create snapshot churn for downstream automation.
- Compatibility fixes may need additional validation across parser backends.

**Suggested follow-up tickets**
- Expand snapshot tests around scorecard presentation variants.
- Add explicit Python 3.13 matrix coverage in CI if not already present.

## B05 - Batch Runner Reliability + Interface Surface Expansion (OpenCode)

**Batch metadata**
- Commits in batch: **7**

**Objective**
- Reduce batch-execution flakiness, improve diagnosability, and harden packaging contracts.

**Problem this batch addressed**
- Monolithic batch runner behavior made stalls and backend failures hard to diagnose/recover.
- CLI ergonomics lacked expected top-level metadata flags.
- Skill update surface needed OpenCode support while maintaining package contract integrity.

**Implementation delivered**
- Introduced Popen-based batch runner with stall recovery and backend diagnostics.
- Refactored runner helper monolith into smaller pieces for maintainability and testability.
- Added top-level `--version`/`-V` CLI flags.
- Added OpenCode support to `update-skill` workflows plus documentation updates.
- Hardened extras/package dependency contract and bumped to tagged build.
- Merged follow-up fixes to keep package and interface contract coherent.

**Scope metrics**
- Raw churn: `+1575 / -373` lines
- Source-focused churn (excluding backup/cache/build artifacts): `+1575 / -373` lines
- Binary files changed: `0`
- Most active source directories: `desloppify/app/commands` (1247), `desloppify/tests/review` (442), `desloppify/tests/commands` (100), `docs/OPENCODE.md` (43), `desloppify/intelligence/review` (37), `desloppify/tests/ci` (37)
- Most active source files: `desloppify/app/commands/review/runner_helpers.py` (1137), `desloppify/tests/review/test_review_commands.py` (377), `desloppify/tests/review/test_holistic_review.py` (62), `desloppify/tests/commands/test_status_subjective_issue_visibility.py` (58), `desloppify/app/commands/status_parts/render.py` (52), `docs/OPENCODE.md` (43)
- Most frequently touched subsystems (source only): Tests (9), Review command workflow (5), CLI parser/entrypoints (3), Intelligence/review context (3), Documentation (2), Packaging/project config (2)

**Commit-by-commit intent (dev-ticket granularity)**
- `4787379`: Add Popen-based runner with stall recovery and Codex backend diagnostics — updated 16 files (+1033 / -61), focused on tests, review workflow. Key files: `desloppify/app/commands/review/runner_helpers.py`, `desloppify/tests/review/test_review_commands.py`.
- `5c39f03`: Refactor runner_helpers.py: decompose monolithic run_codex_batch — updated 1 files (+406 / -309), focused on review workflow. Key file: `desloppify/app/commands/review/runner_helpers.py`.
- `f20cdcc`: fix(cli): add top-level --version/-V flags — updated 2 files (+29 / -0), focused on CLI surface, tests. Key files: `desloppify/app/cli_support/parser.py`, `desloppify/tests/commands/test_cli.py`.
- `e693c51`: feat(update-skill): add OpenCode interface support — updated 5 files (+67 / -1), focused on tests, CLI surface. Key files: `docs/OPENCODE.md`, `desloppify/tests/commands/test_transitive_modules.py`.
- `d66e65b`: Merge pull request #154 from peteromallet/codex/pr-151-146 — merge/integration commit with no direct file diff in this changeset.
- `fac7b69`: fix(package): harden extras contract and bump to tagged build — updated 3 files (+40 / -2), focused on packaging/config, tests. Key files: `desloppify/tests/ci/test_ci_contracts.py`, `Makefile`.
- `41fac2f`: Merge pull request #155 from peteromallet/codex/fix-149-pypi-full-extra — merge/integration commit with no direct file diff in this changeset.

**Validation and acceptance signals**
- Review command tests and holistic review tests expanded around runner behavior.
- CI contract test updates confirm packaging consistency checks.
- Status rendering/test updates indicate user-facing confidence checks after runner change.

**Known risk and tradeoff profile**
- Process-management logic can fail differently across OS/shell environments.
- Runner decomposition may require more integration tests for parallel edge cases.

**Suggested follow-up tickets**
- Capture long-running batch telemetry and timeout distributions.
- Add chaos-style tests for intermittent backend failures.

## B06 - Planning Engine Rollout + Command Surface Convergence

**Batch metadata**
- Commits in batch: **14**

**Objective**
- Ship a living plan engine and align command surfaces (plan/show/status/next/review) around consistent state transitions.

**Problem this batch addressed**
- Planning and resolve flows were fragmented, with overlap between top-level and nested command semantics.
- Review/scan workflows had unresolved regressions and scope leakage issues.
- User guidance across score surfaces and strict target nudges lacked consistency.

**Implementation delivered**
- Shipped pending scanner/review improvements plus prompt refactors.
- Fixed CI regressions and review import regressions affecting full test runs.
- Added centralized score updates after state-changing commands.
- Delivered living plan engine, plan subcommands, and show/status/next upgrades.
- Removed top-level resolve command and consolidated behavior into plan subcommands.
- Fixed heartbeat crash path in parallel batch execution and scan nullable-state mypy issue.
- Added strict-target and next-command nudges across all score surfaces.
- Improved AST parse diagnostics by preserving real file paths in warnings.
- Advanced package line with tagged build as a control point.

**Scope metrics**
- Raw churn: `+20453 / -6996` lines
- Source-focused churn (excluding backup/cache/build artifacts): `+20453 / -6996` lines
- Binary files changed: `4`
- Most active source directories: `desloppify/app/commands` (7291), `desloppify/intelligence/review` (2479), `desloppify/tests/commands` (2435), `desloppify/tests/review` (2310), `desloppify/engine/_plan` (1727), `desloppify/languages/typescript` (1534)
- Most active source files: `desloppify/tests/plan/test_auto_cluster.py` (665), `desloppify/app/commands/plan/override_handlers.py` (653), `desloppify/tests/commands/test_review_preflight.py` (651), `desloppify/tests/review/test_mechanical_evidence.py` (640), `desloppify/app/cli_support/parser_groups_admin.py` (629), `desloppify/tests/review/test_issues.py` (588)
- Most frequently touched subsystems (source only): Language frameworks/plugins (123), Tests (99), General command layer (65), Engine/scoring core (62), Misc (38), Intelligence/review context (37)

**Commit-by-commit intent (dev-ticket granularity)**
- `05a59ac`: Ship pending scanner/review workflow improvements and prompt refactors — updated 329 files (+11160 / -5502), focused on language plugins, tests. Key files: `desloppify/tests/review/test_issues.py`, `desloppify/app/commands/review/runner_helpers.py`.
- `bd2100d`: Fix CI regressions: opencode mapping, compat imports, load-error handling — updated 4 files (+22 / -5), focused on language plugins, misc files. Key files: `desloppify/languages/_framework/discovery.py`, `desloppify/core/skill_docs.py`.
- `7fdcb2c`: Fix tests-full abort and review import regressions — updated 3 files (+81 / -37), focused on review intelligence, review workflow. Key files: `desloppify/app/commands/review/batches.py`, `desloppify/intelligence/review/importing/per_file.py`.
- `3b8a922`: Bump package tag — updated 1 files (+1 / -1), focused on packaging/config. Key file: `pyproject.toml`.
- `dd766f4`: Fix holistic review packet scope leakage and add regression coverage — updated 8 files (+370 / -21), focused on review intelligence, tests. Key files: `desloppify/intelligence/review/prepare.py`, `desloppify/tests/review/test_holistic_review.py`.
- `af3a656`: Add centralized score reporting after all state-changing commands — updated 7 files (+151 / -40), focused on review workflow, command layer. Key files: `desloppify/tests/commands/test_score_update.py`, `desloppify/app/commands/helpers/score_update.py`.
- `1bd0743`: Remove unused import in score_update.py — updated 1 files (+0 / -1), focused on command layer. Key file: `desloppify/app/commands/helpers/score_update.py`.
- `e5712e3`: Ship living plan engine, plan subcommands, show/status/next improvements, and bug fixes — updated 65 files (+5008 / -255), focused on engine/scoring core, command layer. Key files: `desloppify/tests/commands/test_review_preflight.py`, `desloppify/engine/_plan/operations.py`.
- `6268a61`: Remove top-level resolve command, consolidate into plan subcommands — updated 91 files (+3585 / -1102), focused on tests, engine/scoring core. Key files: `desloppify/tests/plan/test_auto_cluster.py`, `desloppify/engine/_plan/auto_cluster.py`.
- `a1c2c57`: Fix heartbeat error_log_fn crash on KeyError in parallel batch execution — updated 1 files (+1 / -1), focused on review workflow. Key file: `desloppify/app/commands/review/runner_helpers.py`.
- `3b06723`: Fix mypy union-attr error on nullable state_path in scan workflow — updated 1 files (+1 / -1), focused on scan workflow. Key file: `desloppify/app/commands/scan/scan_workflow.py`.
- `8e2c7f1`: Show strict target and next-command nudge on every score surface — updated 7 files (+62 / -19), focused on command layer, planning workflow. Key files: `desloppify/app/commands/helpers/score_update.py`, `desloppify/app/commands/status_parts/summary.py`.
- `02abe29`: Pass filename to ast.parse() so SyntaxWarnings show real file paths — updated 7 files (+11 / -11), focused on language plugins. Key files: `desloppify/languages/python/detectors/smells_ast/_source_detectors.py`, `desloppify/languages/python/detectors/mutable_state.py`.
- `e3c99e2`: Merge pull request #174 from peteromallet/fix/ast-parse-filename — merge/integration commit with no direct file diff in this changeset.

**Validation and acceptance signals**
- Heavy additions in plan/review/commands test suites suggest broad scenario coverage.
- Fix commits directly followed major feature merges, indicating a fast correction loop.
- Static typing fixes and CI passes were treated as first-class acceptance criteria.

**Known risk and tradeoff profile**
- Large command-surface consolidation can break user muscle-memory and scripts.
- Plan engine complexity increases risk of subtle state-machine regressions.

**Suggested follow-up tickets**
- Document migration map from old resolve workflows to plan subcommands.
- Add end-to-end scenario tests for multi-step plan lifecycle mutations.

## B07 - Evidence Model Shift + Vocabulary Standardization

**Batch metadata**
- Commits in batch: **10**

**Objective**
- Reframe review scoring around evidence quality while cleaning terminology and removing legacy code paths.

**Problem this batch addressed**
- Low-confidence mechanical signals could exert too much influence on review scoring narrative.
- Terminology drift (`finding` vs `issue`, `issues` vs `failing`) made APIs and outputs harder to reason about.
- Queue ordering, plan reset behavior, and stale-dimension handling needed deterministic fixes.

**Implementation delivered**
- Released tagged build with evidence-only filtering for low-confidence mechanical findings.
- Classified unicode usage-limit failures in batch runner review flow.
- Fixed stale dimension queue ordering and plan reset cycle detection.
- Improved work queue readability and removed facade/dead/orphaned modules.
- Renamed core scoring vocabulary from `issues` to `failing` and `finding` to `issue` across codebase.
- Removed global keyword usage and consolidated constants/signatures for cleaner contracts.

**Scope metrics**
- Raw churn: `+4264613 / -31136` lines
- Source-focused churn (excluding backup/cache/build artifacts): `+59038 / -31136` lines
- Interpretation note: raw churn is inflated by temporary `.desloppify*` artifact movement during WIP/snapshot commits; use source-focused churn for engineering-effort comparison.
- Binary files changed: `1`
- Most active source directories: `desloppify/app/commands` (24993), `desloppify/tests/review` (19304), `desloppify/tests/commands` (8159), `desloppify/engine/_plan` (6217), `desloppify/languages/python` (3650), `desloppify/tests/plan` (3246)
- Most active source files: `desloppify/tests/review/integration/review_commands_cases.py` (3134), `desloppify/tests/review/review_commands_cases.py` (3132), `desloppify/tests/review/test_review_commands.py` (2798), `desloppify/app/commands/plan/synthesize_handlers.py` (2056), `desloppify/app/commands/plan/triage_handlers.py` (2034), `desloppify/tests/review/work_queue_cases.py` (1256)
- Most frequently touched subsystems (source only): Tests (398), Engine/scoring core (188), Language frameworks/plugins (152), General command layer (114), Review command workflow (96), Plan/resolve workflow (92)

**Commit-by-commit intent (dev-ticket granularity)**
- `8dc2d1b`: WIP: queue fixes and review refactors — updated 184 files (+7753 / -2271), focused on tests, language plugins. Key files: `desloppify/app/commands/plan/synthesize_handlers.py`, `desloppify/languages/python/tests/test_py_smells.py`.
- `4dc32ce`: review: classify unicode usage-limit failures in batch runner — updated 2 files (+52 / -6), focused on review workflow, tests. Key files: `desloppify/app/commands/review/runner_helpers.py`, `desloppify/tests/review/test_review_commands.py`.
- `574d81d`: tagged build: evidence-only filtering for low-confidence mechanical findings — updated 785 files (+4240779 / -13462), focused on runtime artifacts, tests. Key files: `.desloppify.reset_backup_*/state-python.json`, `.desloppify.reset_backup_*/state-python.json.bak`.
- `462203a`: fix: stale dimension queue ordering and plan reset cycle detection — updated 43 files (+1278 / -584), focused on engine/scoring core, planning workflow. Key files: `desloppify/tests/plan/test_subjective_policy.py`, `desloppify/tests/plan/test_stale_dimensions.py`.
- `f7c6e77`: refactor: clean up work queue pipeline for readability — updated 147 files (+4320 / -4181), focused on tests, command layer. Key files: `desloppify/languages/typescript/detectors/_smell_detectors.py`, `desloppify/tests/commands/test_queue_count_consistency.py`.
- `78d2893`: refactor: rename scoring field "issues" to "failing" — updated 54 files (+2571 / -433), focused on tests, engine/scoring core. Key files: `desloppify/app/cli_support/parser_plan.py`, `desloppify/app/cli_support/parser_review.py`.
- `1268493`: refactor: rename "finding" to "issue" across entire codebase — updated 312 files (+5484 / -5395), focused on tests, engine/scoring core. Key files: `desloppify/tests/detectors/test_concerns.py`, `desloppify/app/commands/plan/triage_handlers.py`.
- `b1ac391`: fix: delete facade modules, consolidate stale_dimensions, fix triage gate bug — updated 197 files (+2195 / -3058), focused on tests, engine/scoring core. Key files: `desloppify/tests/scoring/test_scoring.py`, `desloppify/app/commands/scan/scan_workflow.py`.
- `47fca7c`: fix: remove dead code, break import cycles, delete orphaned modules — updated 37 files (+124 / -1682), focused on engine/scoring core, language plugins. Key files: `desloppify/app/cli_support/parser_plan.py`, `desloppify/app/cli_support/parser_review.py`.
- `ae1386e`: fix: eliminate global keyword, fix signatures, consolidate constants — updated 19 files (+57 / -64), focused on scan workflow, tests. Key files: `desloppify/languages/_framework/registry_state.py`, `desloppify/cli.py`.

**Validation and acceptance signals**
- High churn across review tests and plan handlers indicates broad refactor validation effort.
- Terminology refactors landed alongside structural cleanup to keep semantics synchronized.
- Follow-on fix commits target determinism and gate correctness after model shift.

**Known risk and tradeoff profile**
- Wide vocabulary renames can break downstream integrations expecting old keys.
- Evidence-only filtering may reduce sensitivity for some teams unless tuned.
- WIP commits in this batch require disciplined interpretation during bisect/debug.

**Suggested follow-up tickets**
- Publish compatibility notes for renamed fields in external outputs.
- Track score movement before/after evidence filtering on representative repos.

## B08 - F6 Reorganization: Core/Base Rename, Contract Enforcement, CI Recovery

**Batch metadata**
- Commits in batch: **12**

**Objective**
- Execute deep package/layout reorganization while preserving correctness through immediate CI and type-fix recovery.

**Problem this batch addressed**
- Compatibility shims and facade layers were accruing debt and obscuring ownership boundaries.
- Directory/module naming (`core` vs `base`) and internal layout needed normalization.
- Large-scale rewires created unavoidable CI/mypy/import-linter fallout requiring rapid remediation.

**Implementation delivered**
- Captured snapshot, then removed functional compatibility shims and tightened planning/review contracts.
- Reorganized directories/imports in F6 wave, including `core/` to `base/` rename and `_internal` promotion.
- Split functions, extracted concern factory and NextOptions dataclass, and documented detail shapes.
- Removed additional facade modules and rewired imports across codebase.
- Updated mypy config paths after module moves and fixed full CI breakages (types + import-linter).
- Fixed CI-breaking hardcoded absolute path in tests.
- Created workstream docs with branch/dependency tracking for parallel execution of remaining tasks.

**Scope metrics**
- Raw churn: `+22052 / -22364` lines
- Source-focused churn (excluding backup/cache/build artifacts): `+21138 / -22364` lines
- Binary files changed: `0`
- Most active source directories: `desloppify/app/commands` (16096), `desloppify/tests/review` (6642), `desloppify/engine/_plan` (3446), `desloppify/intelligence/review` (2683), `desloppify/languages/_framework` (2031), `desloppify/languages/typescript` (1291)
- Most active source files: `desloppify/tests/review/integration/review_commands_cases.py` (2949), `desloppify/app/commands/plan/triage/stages.py` (1986), `desloppify/app/commands/plan/triage_handlers.py` (1801), `desloppify/app/commands/review/runner_helpers.py` (1185), `desloppify/app/commands/review/runner_parallel.py` (782), `desloppify/languages/_framework/treesitter/_imports.py` (780)
- Most frequently touched subsystems (source only): Language frameworks/plugins (421), Tests (310), Engine/scoring core (216), General command layer (179), Misc (125), Intelligence/review context (121)

**Commit-by-commit intent (dev-ticket granularity)**
- `330f777`: chore: snapshot current refactor state — updated 404 files (+11097 / -8134), focused on language plugins, tests. Key files: `desloppify/app/commands/plan/triage_handlers.py`, `desloppify/app/commands/review/runner_helpers.py`.
- `cfd8dd0`: Remove functional compatibility shims and tighten review/planning contracts — updated 330 files (+1396 / -1717), focused on tests, language plugins. Key files: `desloppify/app/commands/review/import_parse.py`, `desloppify/engine/plan.py`.
- `2e221b4`: chore: F6 directory reorganization and import rewiring — updated 312 files (+718 / -682), focused on tests, language plugins. Key files: `desloppify/tests/review/review_commands_cases.py`, `desloppify/tests/review/integration/review_commands_cases.py`.
- `2f0d9c2`: Rename core/ → base/, promote _internal/, fix layer violations, clean up shims — updated 332 files (+761 / -842), focused on language plugins, tests. Key files: `desloppify/core/search/grep.py`, `desloppify/README.md`.
- `afef2ac`: Beauty plan items: delete shims, consolidate constants, enforce contracts, split functions — updated 40 files (+240 / -199), focused on command layer, language plugins. Key files: `desloppify/languages/typescript/tests/test_ts_fixers.py`, `desloppify/app/commands/scan/reporting/summary.py`.
- `cd39adf`: Extract concern factory, NextOptions dataclass, and detail shape docs — updated 3 files (+167 / -100), focused on engine/scoring core, command layer. Key files: `desloppify/engine/concerns.py`, `desloppify/app/commands/next/cmd.py`.
- `c658b33`: Add 8 parallel workstream docs for remaining beauty plan items — mainly moved/updated runtime artifact snapshots (8 files; +898 / -0) rather than primary source modules.
- `f1562a9`: Add branch and dependency info to workstream docs — mainly moved/updated runtime artifact snapshots (8 files; +16 / -0) rather than primary source modules.
- `895c842`: Remove facade modules, extract submodules, and clean up imports across codebase — updated 247 files (+6740 / -10671), focused on language plugins, engine/scoring core. Key files: `desloppify/tests/review/integration/review_commands_cases.py`, `desloppify/app/commands/plan/triage/stages.py`.
- `b2dfd7e`: Fix mypy config: update renamed review module paths in pyproject.toml — updated 1 files (+3 / -3), focused on packaging/config. Key file: `pyproject.toml`.
- `cd91b7c`: Fix all CI failures: mypy type errors, import-linter core→base rename — updated 3 files (+14 / -13), focused on review workflow, CI/workflows. Key files: `desloppify/app/commands/review/batch/core.py`, `desloppify/app/commands/review/batch/orchestrator.py`.
- `9b25cf7`: Fix test using hardcoded absolute path that breaks in CI — updated 1 files (+2 / -3), focused on language plugins. Key file: `desloppify/languages/python/tests/test_bandit_adapter.py`.

**Validation and acceptance signals**
- Direct CI-fix commits indicate full pipeline failures were reproduced and resolved quickly.
- Type and import-linter repairs were explicit acceptance gates in this batch.
- Workstream docs provided coordination artifacts to reduce parallel-change collision risk.

**Known risk and tradeoff profile**
- Deep namespace moves can leave hidden stale imports in less-exercised paths.
- High refactor concentration increases regression probability despite CI recovery.

**Suggested follow-up tickets**
- Run periodic import-graph audits to prevent facade reintroduction.
- Maintain a rename map for contributors working from older branches/docs.

## B09 - Queue/Cluster Lifecycle Redesign + Narrative/Review Extraction Wave

**Batch metadata**
- Commits in batch: **13**

**Objective**
- Simplify queue gating and cluster management semantics while extracting monolithic modules into maintainable units.

**Problem this batch addressed**
- Queue lifecycle logic was scattered and difficult to reason about end-to-end.
- Cluster rendering/action metadata was not consistently surfaced to users.
- Narrative/review context modules carried dense logic with weak separation of concerns.

**Implementation delivered**
- Reworked queue lifecycle into a single pipeline filter replacing dispersed gating logic.
- Fixed plan render handling for override cluster and queue_order semantics.
- Surfaced cluster `action_steps` in `next` and `plan show` outputs.
- Delivered cluster-management improvements and targeted extractions from configuration/type modules.
- Normalized logging, refined structural detector wording, and fixed TYPE_CHECKING/test import breaks.
- Completed `fix` to `autofix` naming transition in relevant command surfaces.
- Extracted holistic cache/issue-flow modules and removed dead suppress command path.
- Cleaned temp/backup artifact handling in repo during in-progress refactor snapshots.

**Scope metrics**
- Raw churn: `+9938 / -4213217` lines
- Source-focused churn (excluding backup/cache/build artifacts): `+9938 / -6728` lines
- Interpretation note: large raw deletions primarily come from removing transient `.desloppify*` backup artifacts, not from deleting equivalent source code volume.
- Binary files changed: `0`
- Most active source directories: `desloppify/intelligence/review` (4635), `desloppify/intelligence/narrative` (2011), `desloppify/app/commands` (1653), `desloppify/tests/plan` (1475), `desloppify/engine/detectors` (1391), `desloppify/tests/review` (1315)
- Most active source files: `desloppify/tests/review/test_runner_internals.py` (1026), `desloppify/tests/plan/test_epic_triage_apply.py` (767), `desloppify/tests/plan/test_stale_policy.py` (646), `desloppify/intelligence/review/context_holistic/budget_patterns.py` (551), `desloppify/intelligence/narrative/reminders.py` (492), `desloppify/intelligence/review/context_holistic/budget_abstractions.py` (456)
- Most frequently touched subsystems (source only): Tests (59), Engine/scoring core (51), Intelligence/review context (35), Language frameworks/plugins (32), Plan/resolve workflow (25), Review command workflow (16)

**Commit-by-commit intent (dev-ticket granularity)**
- `c38caed`: WIP: work queue, merge issues, and review batch updates — updated 6 files (+38 / -21), focused on engine/scoring core, tests. Key files: `desloppify/engine/_work_queue/synthetic.py`, `desloppify/tests/review/work_queue_cases.py`.
- `087aca3`: Remove temp files and commit in-progress changes — updated 30 files (+2501 / -2374828), focused on runtime artifacts, engine/scoring core. Key files: `.desloppify.reset_backup_*/state-python.json`, `.desloppify.reset_backup_*/state-python.json.bak`.
- `825d17c`: Remove .desloppify backup folder and ignore all .desloppify.* dirs — updated 479 files (+1 / -1832087), focused on runtime artifacts, packaging/config. Key files: `.desloppify.backup_*/state-python.json`, `.desloppify.backup_*/state-python.json.bak`.
- `a6fe6bb`: WIP: work queue core and test case updates — updated 2 files (+12 / -18), focused on engine/scoring core, tests. Key files: `desloppify/tests/review/work_queue_cases.py`, `desloppify/engine/_work_queue/core.py`.
- `656240d`: Refactor work queue lifecycle: single pipeline filter replaces scattered gating — updated 7 files (+152 / -130), focused on engine/scoring core, tests. Key files: `desloppify/tests/review/work_queue_cases.py`, `desloppify/engine/_work_queue/core.py`.
- `3a5a6ca`: fix: plan render respects override cluster and queue_order — updated 1 files (+33 / -4), focused on engine/scoring core. Key file: `desloppify/engine/planning/render_sections.py`.
- `d03e513`: feat: surface cluster action_steps in next and plan show output — updated 4 files (+20 / -3), focused on engine/scoring core, command layer. Key files: `desloppify/app/commands/next/render.py`, `desloppify/app/commands/plan/cluster_handlers.py`.
- `62fc2b7`: refactor: extract coercion logic and shared types from LangConfig types.py — updated 3 files (+272 / -180), focused on language plugins. Key files: `desloppify/languages/_framework/base/types.py`, `desloppify/languages/_framework/base/lang_config_runtime.py`.
- `9bd0fd9`: feat: cluster management improvements + targeted module extractions — updated 8 files (+832 / -635), focused on engine/scoring core, CLI surface. Key files: `desloppify/engine/_plan/auto_cluster.py`, `desloppify/engine/_plan/auto_cluster_sync.py`.
- `8848fa2`: refactor: module extractions, logging normalization, structural detector wording + fix broken TYPE_CHECKING import — updated 44 files (+1988 / -1674), focused on engine/scoring core, review intelligence. Key files: `desloppify/intelligence/narrative/reminders.py`, `desloppify/engine/detectors/flat_dirs.py`.
- `e835c5b`: fix: deduplicate _workflow_stage_name into shared helper + add resilient stage_index resolution — updated 4 files (+42 / -6), focused on engine/scoring core, command layer. Key files: `desloppify/engine/_work_queue/ranking.py`, `desloppify/engine/_work_queue/helpers.py`.
- `ea13354`: refactor: fix→autofix rename, module extractions, facade removals + fix broken test imports — updated 149 files (+3282 / -2874), focused on tests, review intelligence. Key files: `desloppify/intelligence/review/context_holistic/budget_patterns.py`, `desloppify/intelligence/review/context_holistic/budget_abstractions.py`.
- `a917532`: refactor: extract holistic cache/issue-flow modules, prepare holistic flow + remove dead suppress command — updated 9 files (+765 / -757), focused on review intelligence, planning workflow. Key files: `desloppify/intelligence/review/importing/holistic.py`, `desloppify/intelligence/review/prepare_holistic_flow.py`.

**Validation and acceptance signals**
- Plan/review test files with high churn indicate feature-path and lifecycle scenario updates.
- Follow-up fixes for render/index helpers suggest active edge-case validation after redesign.
- Command renaming and module extraction were accompanied by import repair commits.

**Known risk and tradeoff profile**
- WIP-heavy commit cluster can complicate blame/bisect for future incident response.
- Lifecycle redesign may still hide corner cases in unusual override combinations.

**Suggested follow-up tickets**
- Consolidate WIP-phase knowledge into formal architecture docs and diagrams.
- Add property-style tests for queue order and stage index invariants.

## B10 - Final Decomposition Sweep + Review Integrity Clarifications + XML Security Hardening

**Batch metadata**
- Commits in batch: **21**

**Objective**
- Close the refactor wave by decomposing monster functions, tightening review-scoring semantics, and addressing dependency/security correctness.

**Problem this batch addressed**
- Several large functions across review/plan/scoring remained high-risk maintenance hotspots.
- Review wording and scoring signals needed clearer separation between mechanical and substantive evidence.
- C# dependency parsing had XML attack-surface risk and inconsistent dependency declarations.

**Implementation delivered**
- Clarified that mechanical signals must not anchor review scores.
- Simplified user message rendering and removed additional global mutable/private cross-module coupling.
- Extracted parser/panel modules, removed re-exports/import noise, and improved silent-except logging.
- Expanded smoke coverage and extracted testable scoring recipe components.
- Performed broad monster-function decomposition across plan/scoring/coverage/review subsystems.
- Aligned external and batch review prompt paths and decomposed cluster handlers/triage dashboard flows.
- Added `defusedxml` usage for C# `.csproj` parsing to mitigate XML attack vectors.
- Normalized dependency contract (`defusedxml` moved from extra to base dependency) with lazy stdlib fallback behavior.
- Closed wave with queue cleanup, lifecycle tests/scripts, and CI consistency fixes.

**Scope metrics**
- Raw churn: `+7711 / -3909` lines
- Source-focused churn (excluding backup/cache/build artifacts): `+7711 / -3909` lines
- Binary files changed: `0`
- Most active source directories: `desloppify/app/commands` (3282), `desloppify/tests/commands` (2544), `desloppify/intelligence/review` (1173), `desloppify/engine/_plan` (914), `desloppify/app/cli_support` (871), `desloppify/tests/review` (452)
- Most active source files: `desloppify/tests/commands/scan/test_plan_reconcile.py` (734), `desloppify/app/commands/review/batch/execution.py` (689), `desloppify/tests/commands/test_next_render.py` (552), `desloppify/app/commands/review/prompt_sections.py` (484), `desloppify/tests/commands/plan/test_commit_log.py` (463), `desloppify/app/commands/review/batch/prompt_template.py` (428)
- Most frequently touched subsystems (source only): Tests (48), Review command workflow (32), Intelligence/review context (28), Language frameworks/plugins (26), Engine/scoring core (23), General command layer (20)

**Commit-by-commit intent (dev-ticket granularity)**
- `ddb2f91`: fix: clarify that mechanical signals must not anchor review scores — updated 1 files (+12 / -5), focused on review workflow. Key file: `desloppify/app/commands/review/batch/prompt_template.py`.
- `5ab2775`: refactor: simplify user_message box to plain border — updated 1 files (+8 / -9), focused on misc files. Key file: `desloppify/base/output/user_message.py`.
- `f0d047d`: refactor: clean up global mutable state and private cross-module imports — updated 20 files (+272 / -249), focused on planning workflow, language plugins. Key files: `desloppify/app/commands/plan/triage/helpers.py`, `desloppify/base/registry.py`.
- `8bdd0a9`: refactor: extract parser/panel modules, break import cycle, fix schema drift — updated 9 files (+466 / -445), focused on CLI surface, misc files. Key files: `desloppify/app/cli_support/parser_groups_admin_review.py`, `desloppify/app/cli_support/parser_groups_admin.py`.
- `9e93cfe`: refactor: remove unused imports/re-exports, add logging to silent excepts — updated 18 files (+54 / -80), focused on review intelligence, language plugins. Key files: `desloppify/tests/plan/test_auto_cluster.py`, `desloppify/app/commands/review/runner_parallel.py`.
- `f333c1d`: refactor: extract testable score_recipe_lines, expand smoke test coverage — updated 3 files (+32 / -19), focused on review workflow, scan workflow. Key files: `desloppify/app/commands/scan/reporting/presentation.py`, `desloppify/tests/commands/test_direct_coverage_modules.py`.
- `26593af`: feat: monster-function decomposition, noop filter, review prompt improvements — updated 18 files (+777 / -379), focused on tests, language plugins. Key files: `desloppify/engine/_plan/epic_triage_apply.py`, `desloppify/engine/_plan/schema_migrations.py`.
- `b4161bf`: fix: use defusedxml for C# .csproj parsing to prevent XML attacks — updated 1 files (+1 / -1), focused on language plugins. Key file: `desloppify/languages/csharp/detectors/deps_support.py`.
- `de5c9f9`: refactor: decompose cmd_triage_dashboard and stale_dimensions monster functions — updated 2 files (+156 / -97), focused on planning workflow, engine/scoring core. Key files: `desloppify/engine/_plan/stale_dimensions.py`, `desloppify/app/commands/plan/triage/display.py`.
- `e917ac5`: fix: use module logger for plan reconciliation, clarify review prompt wording — updated 3 files (+3 / -3), focused on review workflow, scan workflow. Key files: `desloppify/languages/_framework/review_data/dimensions.json`, `desloppify/app/commands/scan/plan_reconcile.py`.
- `4d0cd3e`: refactor: decompose monster functions across engine, scoring, coverage, and review — updated 8 files (+599 / -294), focused on engine/scoring core, review intelligence. Key files: `desloppify/intelligence/review/prepare_holistic_flow.py`, `desloppify/engine/_plan/auto_cluster_sync.py`.
- `39a8585`: refactor: decompose _abstractions_context with _AbstractionsCollector dataclass — updated 1 files (+180 / -145), focused on review intelligence. Key file: `desloppify/intelligence/review/context_holistic/budget_abstractions.py`.
- `3dec818`: refactor: add type annotations to untyped lang and args parameters — updated 16 files (+27 / -27), focused on review intelligence, command layer. Key files: `desloppify/intelligence/review/context_holistic/selection_contexts.py`, `desloppify/cli.py`.
- `d90115f`: refactor: align external and batch review prompt paths — updated 4 files (+580 / -349), focused on review workflow, tests. Key files: `desloppify/app/commands/review/batch/prompt_template.py`, `desloppify/app/commands/review/prompt_sections.py`.
- `f02ca05`: refactor: remove facade re-exports, fix private imports, decompose cluster_handlers — updated 32 files (+281 / -260), focused on language plugins, review intelligence. Key files: `desloppify/app/commands/plan/cluster_handlers.py`, `desloppify/intelligence/review/context_holistic/budget_patterns.py`.
- `7627752`: refactor: consistency cleanup — updated 12 files (+25 / -35), focused on command layer, engine/scoring core. Key files: `desloppify/engine/_scoring/state_integration.py`, `desloppify/tests/commands/scan/test_cmd_scan.py`.
- `2591bb3`: refactor: queue cleanup — updated 27 files (+2865 / -926), focused on tests, review workflow. Key files: `desloppify/tests/commands/scan/test_plan_reconcile.py`, `desloppify/app/commands/review/batch/execution.py`.
- `54f36dd`: refactor: review batch decomposition, work queue lifecycle, CI fixes — updated 54 files (+1365 / -582), focused on tests, scan workflow. Key files: `desloppify/intelligence/review/prepare_batches.py`, `scripts/lifecycle_walkthrough.py`.
- `a91f443`: fix: add defusedxml to [full] extra — updated 1 files (+1 / -0), focused on packaging/config. Key file: `pyproject.toml`.
- `8b94e4f`: fix: make defusedxml a base dependency, not just [full] — updated 1 files (+1 / -2), focused on packaging/config. Key file: `pyproject.toml`.
- `6eb2065`: fix: make defusedxml import lazy with stdlib fallback — updated 2 files (+6 / -2), focused on language plugins, packaging/config. Key files: `desloppify/languages/csharp/detectors/deps_support.py`, `pyproject.toml`.

**Validation and acceptance signals**
- Strong test churn in scan/plan/review command suites indicates deliberate refactor safety net.
- Security fix landed with dependency-policy follow-up commits to ensure install/runtime correctness.
- Repeated decomposition commits with targeted scopes reduced risk of one-shot mega-diff regressions.

**Known risk and tradeoff profile**
- Function decomposition can alter edge behavior when helper boundaries are mis-specified.
- Dependency fallback paths require verification across minimal and full install profiles.

**Suggested follow-up tickets**
- Add explicit security regression tests around malformed `.csproj` payloads.
- Create architecture map of new module boundaries after decomposition wave.
- Run performance benchmark pass to ensure decomposition did not regress runtime hotspots.

## Closing Notes
- This digest is intentionally exhaustive at the batch level; a companion per-commit summary document is available in the docs directory.
- If you want, this can be expanded into a roadmap-style backlog where each batch is split into “Done / Follow-up / Deferred Debt” Jira-ready tickets.
