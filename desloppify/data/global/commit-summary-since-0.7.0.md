# Commit-by-Commit Summary Since v0.7.0

## Scope
- Baseline commit: `ed15a1b` (2026-02-22), where `version = "0.7.0"` was introduced in `pyproject.toml`.
- End commit: `6eb2065` (2026-03-04).
- Commits reviewed: **111** (chronological, includes the v0.7.0 baseline commit).

## Aggregate View
- Commit types: `other` 58, `refactor` 21, `fix` 14, `release` 9, `feat` 4, `merge` 3, `chore` 2
- Most-touched areas: Tests and fixtures (1282 touches), Miscellaneous (1047 touches), Language adapters/framework (1035 touches), Engine and scoring core (676 touches), Other CLI commands (479 touches), Review intelligence/context (429 touches), Review command workflow (330 touches), Plan/resolve workflow (271 touches)

## Per-Commit Breakdown (Oldest -> Newest)

### 1. `ed15a1b` - Major refactoring: generic language framework, tree-sitter integration, 28 languages
- Date: `2026-02-22`
- Scope snapshot: 345 files, +12533 / -5947 lines, 2 binary file(s).
- Primary areas: Language adapters/framework, Tests and fixtures, Engine and scoring core.
- High-churn files: `desloppify/tests/lang/common/test_treesitter.py`, `desloppify/languages/_framework/treesitter/_specs.py`, `desloppify/languages/_framework/treesitter/_imports.py`.
- Summary: Major refactoring: generic language framework, tree-sitter integration, 28 languages. Focused on language adapters/framework, tests and fixtures, and engine and scoring core. Net effect: mixed maintenance/product changes in listed areas.

### 2. `4bce636` - Update documentation: philosophy, language guide, fix paths
- Date: `2026-02-22`
- Scope snapshot: 5 files, +171 / -189 lines.
- Primary areas: Packaging and release metadata, Documentation, Language adapters/framework.
- High-churn files: `desloppify/languages/README.md`, `README.md`, `.importlinter`.
- Summary: Update documentation: philosophy, language guide, fix paths. Focused on packaging and release metadata, documentation, and language adapters/framework. Net effect: mixed maintenance/product changes in listed areas.

### 3. `bea3fe7` - Remove LLM-sounding language from documentation
- Date: `2026-02-22`
- Scope snapshot: 2 files, +37 / -369 lines.
- Primary areas: Documentation.
- High-churn files: `desloppify/README.md`, `README.md`.
- Summary: Remove LLM-sounding language from documentation. Focused mainly on documentation. Net effect: mixed maintenance/product changes in listed areas.

### 4. `0fff1d8` - Rewrite README intro, add agent-specific overlays for 6 platforms
- Date: `2026-02-22`
- Scope snapshot: 6 files, +255 / -20 lines.
- Primary areas: Documentation.
- High-churn files: `docs/GEMINI.md`, `docs/COPILOT.md`, `docs/CURSOR.md`.
- Summary: Rewrite README intro, add agent-specific overlays for 6 platforms. Focused mainly on documentation. Net effect: mixed maintenance/product changes in listed areas.

### 5. `a36eb14` - Rewrite philosophy section with more human voice
- Date: `2026-02-22`
- Scope snapshot: 1 files, +6 / -6 lines.
- Primary areas: Documentation.
- High-churn files: `README.md`.
- Summary: Rewrite philosophy section with more human voice. Focused mainly on documentation. Net effect: mixed maintenance/product changes in listed areas.

### 6. `0767f8b` - Refocus attestation on confirming the fix, not justifying a score
- Date: `2026-02-22`
- Scope snapshot: 3 files, +10 / -10 lines.
- Primary areas: CLI parser and entrypoints, Engine and scoring core.
- High-churn files: `desloppify/engine/_work_queue/helpers.py`, `desloppify/app/cli_support/parser.py`, `desloppify/app/cli_support/parser_groups.py`.
- Summary: Refocus attestation on confirming the fix, not justifying a score. Focused on cli parser and entrypoints, and engine and scoring core. Net effect: mixed maintenance/product changes in listed areas.

### 7. `3dd2d35` - Major architecture cleanup: migrate imports to canonical sources, flatten modules, lazy init
- Date: `2026-02-22`
- Scope snapshot: 144 files, +1411 / -799 lines, 1 binary file(s).
- Primary areas: Language adapters/framework, Other CLI commands, Tests and fixtures.
- High-churn files: `desloppify/app/commands/review/batch_core.py`, `desloppify/utils.py`, `desloppify/app/commands/status_parts/render.py`.
- Summary: Major architecture cleanup: migrate imports to canonical sources, flatten modules, lazy init. Focused on language adapters/framework, other cli commands, and tests and fixtures. Net effect: mixed maintenance/product changes in listed areas.

### 8. `3ee97ba` - Deep architecture cleanup: remove utils re-exports, create work_queue facade, fix deferred imports
- Date: `2026-02-22`
- Scope snapshot: 129 files, +1099 / -513 lines.
- Primary areas: Language adapters/framework, Tests and fixtures, Review intelligence/context.
- High-churn files: `desloppify/utils.py`, `desloppify/app/commands/update_skill.py`, `desloppify/tests/commands/test_direct_coverage_split_modules.py`.
- Summary: Deep architecture cleanup: remove utils re-exports, create work_queue facade, fix deferred imports. Focused on language adapters/framework, tests and fixtures, and review intelligence/context. Net effect: mixed maintenance/product changes in listed areas.

### 9. `32a01b7` - Add __all__ to 10 modules, fix type annotations, fix engine layer violations
- Date: `2026-02-22`
- Scope snapshot: 32 files, +410 / -232 lines.
- Primary areas: Engine and scoring core, Tests and fixtures, Review intelligence/context.
- High-churn files: `desloppify/intelligence/narrative/core.py`, `desloppify/tests/review/test_holistic_review.py`, `desloppify/utils.py`.
- Summary: Add __all__ to 10 modules, fix type annotations, fix engine layer violations. Focused on engine and scoring core, tests and fixtures, and review intelligence/context. Net effect: mixed maintenance/product changes in listed areas.

### 10. `0016271` - Type safety: StateModel annotations, proper TypedDicts, remove frame introspection
- Date: `2026-02-22`
- Scope snapshot: 16 files, +139 / -67 lines.
- Primary areas: Engine and scoring core, Language adapters/framework, Scan/reporting workflow.
- High-churn files: `desloppify/engine/_state/schema.py`, `desloppify/app/commands/scan/scan_reporting_llm.py`, `desloppify/languages/_framework/commands_base.py`.
- Summary: Type safety: StateModel annotations, proper TypedDicts, remove frame introspection. Focused on engine and scoring core, language adapters/framework, and scan/reporting workflow. Net effect: mixed maintenance/product changes in listed areas.

### 11. `c4fed4d` - Type safety and facade enforcement: StateModel across narrative, facade imports, _ModeAccum dataclass
- Date: `2026-02-22`
- Scope snapshot: 49 files, +229 / -488 lines, 1 binary file(s).
- Primary areas: Tests and fixtures, Documentation, Review intelligence/context.
- High-churn files: `desloppify/app/commands/status_parts/transparency.py`, `desloppify/app/commands/_show_terminal.py`, `desloppify/app/commands/show/render.py`.
- Summary: Type safety and facade enforcement: StateModel across narrative, facade imports, _ModeAccum dataclass. Focused on tests and fixtures, documentation, and review intelligence/context. Net effect: mixed maintenance/product changes in listed areas.

### 12. `b25f025` - Add 293 behavioral tests across 17 new test files
- Date: `2026-02-22`
- Scope snapshot: 17 files, +3975 / -0 lines, 1 binary file(s).
- Primary areas: Tests and fixtures, Output rendering and assets.
- High-churn files: `desloppify/tests/review/test_review_policy.py`, `desloppify/languages/csharp/tests/test_csharp_deps_cli.py`, `desloppify/tests/lang/common/test_phase_builders.py`.
- Summary: Add 293 behavioral tests across 17 new test files. Focused on tests and fixtures, and output rendering and assets. Net effect: mixed maintenance/product changes in listed areas.

### 13. `c1d163d` - Fix test coverage detector: resolve submodule imports in dep graph
- Date: `2026-02-22`
- Scope snapshot: 3 files, +41 / -16 lines, 1 binary file(s).
- Primary areas: Language adapters/framework, Output rendering and assets.
- High-churn files: `desloppify/languages/python/detectors/deps.py`, `desloppify/languages/python/test_coverage.py`, `assets/scorecard.png`.
- Summary: Fix test coverage detector: resolve submodule imports in dep graph. Focused on language adapters/framework, and output rendering and assets. Net effect: mixed maintenance/product changes in listed areas.

### 14. `af3434f` - Fix 78 failing lang tests and add facade-aware test coverage
- Date: `2026-02-22`
- Scope snapshot: 12 files, +49 / -10 lines.
- Primary areas: Tests and fixtures, Engine and scoring core.
- High-churn files: `desloppify/engine/detectors/coverage/mapping.py`, `desloppify/languages/gdscript/tests/test_init.py`, `desloppify/languages/dart/tests/test_init.py`.
- Summary: Fix 78 failing lang tests and add facade-aware test coverage. Focused on tests and fixtures, and engine and scoring core. Net effect: mixed maintenance/product changes in listed areas.

### 15. `ff3013a` - Fix PROJECT_ROOT via RuntimeContext and achieve 100% test coverage detection
- Date: `2026-02-22`
- Scope snapshot: 25 files, +1866 / -168 lines.
- Primary areas: Tests and fixtures, Miscellaneous, Core/base utilities.
- High-churn files: `desloppify/tests/commands/test_transitive_engine.py`, `desloppify/tests/commands/test_transitive_modules.py`, `desloppify/core/runtime_state.py`.
- Summary: Fix PROJECT_ROOT via RuntimeContext and achieve 100% test coverage detection. Focused on tests and fixtures, miscellaneous, and core/base utilities. Net effect: mixed maintenance/product changes in listed areas.

### 16. `345c440` - Resolve all 18 review findings: structural refactors, type safety, test coverage
- Date: `2026-02-22`
- Scope snapshot: 48 files, +1159 / -571 lines.
- Primary areas: Language adapters/framework, Engine and scoring core, Other CLI commands.
- High-churn files: `desloppify/tests/detectors/test_concerns.py`, `desloppify/intelligence/narrative/types.py`, `desloppify/intelligence/narrative/core.py`.
- Summary: Resolve all 18 review findings: structural refactors, type safety, test coverage. Focused on language adapters/framework, engine and scoring core, and other cli commands. Net effect: mixed maintenance/product changes in listed areas.

### 17. `1c73c4f` - v0.7.1: PyPI release, fix Python version requirement, update install instructions
- Date: `2026-02-23`
- Scope snapshot: 12 files, +551 / -14 lines, 1 binary file(s).
- Primary areas: Language adapters/framework, Packaging and release metadata, Plan/resolve workflow.
- High-churn files: `desloppify/languages/python/tests/test_py_uncalled.py`, `desloppify/languages/python/detectors/uncalled.py`, `pyproject.toml`.
- Summary: V0.7.1: PyPI release, fix Python version requirement, update install instructions. Focused on language adapters/framework, packaging and release metadata, and plan/resolve workflow. Net effect: advances package/release progression.

### 18. `8739f49` - Add GitHub Actions workflow for PyPI publishing on release
- Date: `2026-02-23`
- Scope snapshot: 1 files, +63 / -0 lines.
- Primary areas: CI automation.
- High-churn files: `.github/workflows/python-publish.yml`.
- Summary: Add GitHub Actions workflow for PyPI publishing on release. Focused mainly on ci automation. Net effect: advances package/release progression.

### 19. `aa1ff8a` - Bump version to 0.7.2
- Date: `2026-02-23`
- Scope snapshot: 1 files, +1 / -1 lines.
- Primary areas: Packaging and release metadata.
- High-churn files: `pyproject.toml`.
- Summary: Bump version to 0.7.2. Focused mainly on packaging and release metadata. Net effect: advances package/release progression.

### 20. `119be4d` - Upgrade Go from generic to full language plugin (from PR #128)
- Date: `2026-02-23`
- Scope snapshot: 21 files, +890 / -63 lines.
- Primary areas: Language adapters/framework, Tests and fixtures, Documentation.
- High-churn files: `desloppify/languages/go/extractors.py`, `desloppify/languages/go/tests/test_extractors.py`, `desloppify/languages/go/__init__.py`.
- Summary: Upgrade Go from generic to full language plugin (from PR #128). Focused on language adapters/framework, tests and fixtures, and documentation. Net effect: mixed maintenance/product changes in listed areas.

### 21. `fc436fe` - Auto-publish to PyPI on push to main when version changes
- Date: `2026-02-23`
- Scope snapshot: 1 files, +33 / -38 lines.
- Primary areas: CI automation.
- High-churn files: `.github/workflows/python-publish.yml`.
- Summary: Auto-publish to PyPI on push to main when version changes. Focused mainly on ci automation. Net effect: advances package/release progression.

### 22. `4de9092` - Harden CI contracts and bump version to 0.7.3
- Date: `2026-02-23`
- Scope snapshot: 9 files, +556 / -13 lines.
- Primary areas: CI automation, Packaging and release metadata, Tests and fixtures.
- High-churn files: `desloppify/tests/ci/test_ci_contracts.py`, `.github/workflows/ci.yml`, `docs/ci_plan.md`.
- Summary: Harden CI contracts and bump version to 0.7.3. Focused on ci automation, packaging and release metadata, and tests and fixtures. Net effect: advances package/release progression.

### 23. `d0667c1` - Stabilize CI gates against repository baseline
- Date: `2026-02-23`
- Scope snapshot: 5 files, +30 / -6 lines.
- Primary areas: Packaging and release metadata, CI automation, Review command workflow.
- High-churn files: `.github/importlinter.ini`, `Makefile`, `desloppify/app/commands/review/batch_core.py`.
- Summary: Stabilize CI gates against repository baseline. Focused on packaging and release metadata, ci automation, and review command workflow. Net effect: mixed maintenance/product changes in listed areas.

### 24. `3a22926` - Protect debug-log fixer from removing logger wrappers
- Date: `2026-02-23`
- Scope snapshot: 2 files, +200 / -1 lines.
- Primary areas: Language adapters/framework, Tests and fixtures.
- High-churn files: `desloppify/languages/typescript/fixers/logs.py`, `desloppify/languages/typescript/tests/test_ts_fixers.py`.
- Summary: Protect debug-log fixer from removing logger wrappers. Focused on language adapters/framework, and tests and fixtures. Net effect: mixed maintenance/product changes in listed areas.

### 25. `d497501` - Merge pull request #131 from peteromallet/codex/issue-126-debug-logs
- Date: `2026-02-23`
- Scope snapshot: 0 files, +0 / -0 lines.
- Summary: Merge pull request #131 from peteromallet/codex/issue-126-debug-logs. Net effect: integrates previously isolated branch work.

### 26. `ad8afad` - release: ship blind-review workflow updates and bump version to 0.7.3
- Date: `2026-02-23`
- Scope snapshot: 232 files, +11076 / -5096 lines, 2 binary file(s).
- Primary areas: Language adapters/framework, Tests and fixtures, Engine and scoring core.
- High-churn files: `desloppify/tests/review/test_review.py`, `desloppify/tests/review/test_review_commands.py`, `desloppify/tests/review/test_review_misc.py`.
- Summary: Ship blind-review workflow updates and bump version to 0.7.3. Focused on language adapters/framework, tests and fixtures, and engine and scoring core. Net effect: advances package/release progression.

### 27. `a548bde` - Apply local pending changes and bump version to 0.7.4
- Date: `2026-02-24`
- Scope snapshot: 33 files, +1178 / -50 lines.
- Primary areas: Tests and fixtures, Other CLI commands, Review command workflow.
- High-churn files: `desloppify/app/commands/issues_cmd.py`, `desloppify/tests/review/test_review_commands.py`, `desloppify/app/commands/scan/scan_reporting_subjective.py`.
- Summary: Apply local pending changes and bump version to 0.7.4. Focused on tests and fixtures, other cli commands, and review command workflow. Net effect: advances package/release progression.

### 28. `74fc323` - Fix mypy unreachable branch in review batch file collection
- Date: `2026-02-24`
- Scope snapshot: 1 files, +1 / -3 lines.
- Primary areas: Review command workflow.
- High-churn files: `desloppify/app/commands/review/batches.py`.
- Summary: Fix mypy unreachable branch in review batch file collection. Focused mainly on review command workflow. Net effect: mixed maintenance/product changes in listed areas.

### 29. `3b21ad2` - Fix mixed-language state fallback after scan
- Date: `2026-02-24`
- Scope snapshot: 2 files, +82 / -2 lines.
- Primary areas: Other CLI commands, Tests and fixtures.
- High-churn files: `desloppify/tests/commands/test_cli.py`, `desloppify/app/commands/helpers/state.py`.
- Summary: Fix mixed-language state fallback after scan. Focused on other cli commands, and tests and fixtures. Net effect: mixed maintenance/product changes in listed areas.

### 30. `8775d23` - Simplify review issue history, add structural-pattern prompting, bump to 0.7.5
- Date: `2026-02-24`
- Scope snapshot: 53 files, +3294 / -313 lines.
- Primary areas: Tests and fixtures, Review command workflow, Review intelligence/context.
- High-churn files: `desloppify/app/commands/review/batches.py`, `desloppify/tests/review/test_review_commands.py`, `desloppify/app/commands/review/runner_helpers.py`.
- Summary: Simplify review issue history, add structural-pattern prompting, bump to 0.7.5. Focused on tests and fixtures, review command workflow, and review intelligence/context. Net effect: mixed maintenance/product changes in listed areas.

### 31. `ff62e86` - Widen scorecard name column to prevent dimension name truncation
- Date: `2026-02-25`
- Scope snapshot: 1 files, +1 / -1 lines.
- Primary areas: Output rendering and assets.
- High-churn files: `desloppify/app/output/scorecard_parts/draw.py`.
- Summary: Widen scorecard name column to prevent dimension name truncation. Focused mainly on output rendering and assets. Net effect: mixed maintenance/product changes in listed areas.

### 32. `12195fb` - Use sentence case for all dimension display names
- Date: `2026-02-25`
- Scope snapshot: 32 files, +550 / -246 lines, 1 binary file(s).
- Primary areas: Tests and fixtures, Output rendering and assets, Engine and scoring core.
- High-churn files: `desloppify/tests/detectors/test_test_coverage.py`, `desloppify/app/output/scorecard_parts/dimension_policy.py`, `desloppify/intelligence/review/importing/holistic.py`.
- Summary: Use sentence case for all dimension display names. Focused on tests and fixtures, output rendering and assets, and engine and scoring core. Net effect: mixed maintenance/product changes in listed areas.

### 33. `a2dfdbb` - Fix Python 3.13 TypeError in tree-sitter normalization
- Date: `2026-02-25`
- Scope snapshot: 1 files, +1 / -1 lines.
- Primary areas: Language adapters/framework.
- High-churn files: `desloppify/languages/_framework/treesitter/_normalize.py`.
- Summary: Fix Python 3.13 TypeError in tree-sitter normalization. Focused mainly on language adapters/framework. Net effect: mixed maintenance/product changes in listed areas.

### 34. `c990cb4` - Register missing --confirm-batch-wontfix CLI flag, bump to 0.7.6
- Date: `2026-02-25`
- Scope snapshot: 2 files, +7 / -1 lines.
- Primary areas: CLI parser and entrypoints, Packaging and release metadata.
- High-churn files: `desloppify/app/cli_support/parser_groups.py`, `pyproject.toml`.
- Summary: Register missing --confirm-batch-wontfix CLI flag, bump to 0.7.6. Focused on cli parser and entrypoints, and packaging and release metadata. Net effect: mixed maintenance/product changes in listed areas.

### 35. `4787379` - Add Popen-based runner with stall recovery and Codex backend diagnostics
- Date: `2026-02-26`
- Scope snapshot: 16 files, +1033 / -61 lines.
- Primary areas: Tests and fixtures, Review command workflow, Review intelligence/context.
- High-churn files: `desloppify/app/commands/review/runner_helpers.py`, `desloppify/tests/review/test_review_commands.py`, `desloppify/tests/review/test_holistic_review.py`.
- Summary: Add Popen-based runner with stall recovery and Codex backend diagnostics. Focused on tests and fixtures, review command workflow, and review intelligence/context. Net effect: mixed maintenance/product changes in listed areas.

### 36. `5c39f03` - Refactor runner_helpers.py: decompose monolithic run_codex_batch
- Date: `2026-02-26`
- Scope snapshot: 1 files, +406 / -309 lines.
- Primary areas: Review command workflow.
- High-churn files: `desloppify/app/commands/review/runner_helpers.py`.
- Summary: Refactor runner_helpers.py: decompose monolithic run_codex_batch. Focused mainly on review command workflow. Net effect: mixed maintenance/product changes in listed areas.

### 37. `f20cdcc` - fix(cli): add top-level --version/-V flags
- Date: `2026-02-26`
- Scope snapshot: 2 files, +29 / -0 lines.
- Primary areas: CLI parser and entrypoints, Tests and fixtures.
- High-churn files: `desloppify/app/cli_support/parser.py`, `desloppify/tests/commands/test_cli.py`.
- Summary: Add top-level --version/-V flags. Focused on cli parser and entrypoints, and tests and fixtures. Net effect: reduces user-facing defects or runtime risk.

### 38. `e693c51` - feat(update-skill): add OpenCode interface support
- Date: `2026-02-26`
- Scope snapshot: 5 files, +67 / -1 lines.
- Primary areas: Tests and fixtures, CLI parser and entrypoints, Miscellaneous.
- High-churn files: `docs/OPENCODE.md`, `desloppify/tests/commands/test_transitive_modules.py`, `desloppify/tests/commands/test_transitive_engine.py`.
- Summary: Add OpenCode interface support. Focused on tests and fixtures, cli parser and entrypoints, and miscellaneous. Net effect: expands product capability.

### 39. `d66e65b` - Merge pull request #154 from peteromallet/codex/pr-151-146
- Date: `2026-02-26`
- Scope snapshot: 0 files, +0 / -0 lines.
- Summary: Merge pull request #154 from peteromallet/codex/pr-151-146. Net effect: integrates previously isolated branch work.

### 40. `fac7b69` - fix(release): harden extras contract and bump to 0.7.7
- Date: `2026-02-26`
- Scope snapshot: 3 files, +40 / -2 lines.
- Primary areas: Packaging and release metadata, Tests and fixtures.
- High-churn files: `desloppify/tests/ci/test_ci_contracts.py`, `Makefile`, `pyproject.toml`.
- Summary: Harden extras contract and bump to 0.7.7. Focused on packaging and release metadata, and tests and fixtures. Net effect: reduces user-facing defects or runtime risk.

### 41. `41fac2f` - Merge pull request #155 from peteromallet/codex/fix-149-pypi-full-extra
- Date: `2026-02-26`
- Scope snapshot: 0 files, +0 / -0 lines.
- Summary: Merge pull request #155 from peteromallet/codex/fix-149-pypi-full-extra. Net effect: advances package/release progression.

### 42. `05a59ac` - Ship pending scanner/review workflow improvements and prompt refactors
- Date: `2026-02-27`
- Scope snapshot: 329 files, +11160 / -5502 lines, 1 binary file(s).
- Primary areas: Language adapters/framework, Tests and fixtures, Other CLI commands.
- High-churn files: `desloppify/tests/review/test_issues.py`, `desloppify/app/commands/review/runner_helpers.py`, `desloppify/app/commands/review/import_helpers.py`.
- Summary: Ship pending scanner/review workflow improvements and prompt refactors. Focused on language adapters/framework, tests and fixtures, and other cli commands. Net effect: mixed maintenance/product changes in listed areas.

### 43. `bd2100d` - Fix CI regressions: opencode mapping, compat imports, load-error handling
- Date: `2026-02-27`
- Scope snapshot: 4 files, +22 / -5 lines.
- Primary areas: Language adapters/framework, Core/base utilities.
- High-churn files: `desloppify/languages/_framework/discovery.py`, `desloppify/core/skill_docs.py`, `desloppify/languages/gdscript/phases.py`.
- Summary: Fix CI regressions: opencode mapping, compat imports, load-error handling. Focused on language adapters/framework, and core/base utilities. Net effect: mixed maintenance/product changes in listed areas.

### 44. `7fdcb2c` - Fix tests-full abort and review import regressions
- Date: `2026-02-27`
- Scope snapshot: 3 files, +81 / -37 lines.
- Primary areas: Review intelligence/context, Review command workflow.
- High-churn files: `desloppify/app/commands/review/batches.py`, `desloppify/intelligence/review/importing/per_file.py`, `desloppify/intelligence/review/importing/shared.py`.
- Summary: Fix tests-full abort and review import regressions. Focused on review intelligence/context, and review command workflow. Net effect: mixed maintenance/product changes in listed areas.

### 45. `3b8a922` - Bump version to 0.7.8
- Date: `2026-02-27`
- Scope snapshot: 1 files, +1 / -1 lines.
- Primary areas: Packaging and release metadata.
- High-churn files: `pyproject.toml`.
- Summary: Bump version to 0.7.8. Focused mainly on packaging and release metadata. Net effect: advances package/release progression.

### 46. `dd766f4` - Fix holistic review packet scope leakage and add regression coverage
- Date: `2026-02-27`
- Scope snapshot: 8 files, +370 / -21 lines.
- Primary areas: Review intelligence/context, Tests and fixtures.
- High-churn files: `desloppify/intelligence/review/prepare.py`, `desloppify/tests/review/test_holistic_review.py`, `desloppify/intelligence/review/context_holistic/selection.py`.
- Summary: Fix holistic review packet scope leakage and add regression coverage. Focused on review intelligence/context, and tests and fixtures. Net effect: mixed maintenance/product changes in listed areas.

### 47. `af3a656` - Add centralized score reporting after all state-changing commands
- Date: `2026-02-27`
- Scope snapshot: 7 files, +151 / -40 lines.
- Primary areas: Review command workflow, Other CLI commands, Plan/resolve workflow.
- High-churn files: `desloppify/tests/commands/test_score_update.py`, `desloppify/app/commands/helpers/score_update.py`, `desloppify/app/commands/resolve/cmd.py`.
- Summary: Add centralized score reporting after all state-changing commands. Focused on review command workflow, other cli commands, and plan/resolve workflow. Net effect: mixed maintenance/product changes in listed areas.

### 48. `1bd0743` - Remove unused import in score_update.py
- Date: `2026-02-27`
- Scope snapshot: 1 files, +0 / -1 lines.
- Primary areas: Other CLI commands.
- High-churn files: `desloppify/app/commands/helpers/score_update.py`.
- Summary: Remove unused import in score_update.py. Focused mainly on other cli commands. Net effect: mixed maintenance/product changes in listed areas.

### 49. `e5712e3` - Ship living plan engine, plan subcommands, show/status/next improvements, and bug fixes
- Date: `2026-02-27`
- Scope snapshot: 65 files, +5008 / -255 lines, 1 binary file(s).
- Primary areas: Engine and scoring core, Other CLI commands, Tests and fixtures.
- High-churn files: `desloppify/tests/commands/test_review_preflight.py`, `desloppify/engine/_plan/operations.py`, `desloppify/app/commands/plan/override_handlers.py`.
- Summary: Ship living plan engine, plan subcommands, show/status/next improvements, and bug fixes. Focused on engine and scoring core, other cli commands, and tests and fixtures. Net effect: mixed maintenance/product changes in listed areas.

### 50. `6268a61` - Remove top-level resolve command, consolidate into plan subcommands
- Date: `2026-02-27`
- Scope snapshot: 91 files, +3585 / -1102 lines, 2 binary file(s).
- Primary areas: Tests and fixtures, Engine and scoring core, Other CLI commands.
- High-churn files: `desloppify/tests/plan/test_auto_cluster.py`, `desloppify/engine/_plan/auto_cluster.py`, `desloppify/app/cli_support/parser_groups_admin.py`.
- Summary: Remove top-level resolve command, consolidate into plan subcommands. Focused on tests and fixtures, engine and scoring core, and other cli commands. Net effect: mixed maintenance/product changes in listed areas.

### 51. `a1c2c57` - Fix heartbeat error_log_fn crash on KeyError in parallel batch execution
- Date: `2026-02-28`
- Scope snapshot: 1 files, +1 / -1 lines.
- Primary areas: Review command workflow.
- High-churn files: `desloppify/app/commands/review/runner_helpers.py`.
- Summary: Fix heartbeat error_log_fn crash on KeyError in parallel batch execution. Focused mainly on review command workflow. Net effect: mixed maintenance/product changes in listed areas.

### 52. `3b06723` - Fix mypy union-attr error on nullable state_path in scan workflow
- Date: `2026-02-28`
- Scope snapshot: 1 files, +1 / -1 lines.
- Primary areas: Scan/reporting workflow.
- High-churn files: `desloppify/app/commands/scan/scan_workflow.py`.
- Summary: Fix mypy union-attr error on nullable state_path in scan workflow. Focused mainly on scan/reporting workflow. Net effect: mixed maintenance/product changes in listed areas.

### 53. `8e2c7f1` - Show strict target and next-command nudge on every score surface
- Date: `2026-02-28`
- Scope snapshot: 7 files, +62 / -19 lines.
- Primary areas: Other CLI commands, Plan/resolve workflow, Scan/reporting workflow.
- High-churn files: `desloppify/app/commands/helpers/score_update.py`, `desloppify/app/commands/status_parts/summary.py`, `desloppify/app/commands/scan/scan_reporting_summary.py`.
- Summary: Show strict target and next-command nudge on every score surface. Focused on other cli commands, plan/resolve workflow, and scan/reporting workflow. Net effect: mixed maintenance/product changes in listed areas.

### 54. `02abe29` - Pass filename to ast.parse() so SyntaxWarnings show real file paths
- Date: `2026-02-28`
- Scope snapshot: 7 files, +11 / -11 lines.
- Primary areas: Language adapters/framework.
- High-churn files: `desloppify/languages/python/detectors/smells_ast/_source_detectors.py`, `desloppify/languages/python/detectors/mutable_state.py`, `desloppify/languages/python/detectors/deps.py`.
- Summary: Pass filename to ast.parse() so SyntaxWarnings show real file paths. Focused mainly on language adapters/framework. Net effect: mixed maintenance/product changes in listed areas.

### 55. `e3c99e2` - Merge pull request #174 from peteromallet/fix/ast-parse-filename
- Date: `2026-02-28`
- Scope snapshot: 0 files, +0 / -0 lines.
- Summary: Merge pull request #174 from peteromallet/fix/ast-parse-filename. Net effect: integrates previously isolated branch work.

### 56. `8dc2d1b` - WIP: queue fixes and review refactors
- Date: `2026-03-02`
- Scope snapshot: 184 files, +7753 / -2271 lines, 1 binary file(s).
- Primary areas: Tests and fixtures, Other CLI commands, Language adapters/framework.
- High-churn files: `desloppify/app/commands/plan/synthesize_handlers.py`, `desloppify/languages/python/tests/test_py_smells.py`, `desloppify/tests/plan/test_epic_synthesis.py`.
- Summary: Queue fixes and review refactors. Focused on tests and fixtures, other cli commands, and language adapters/framework. Net effect: mixed maintenance/product changes in listed areas.

### 57. `4dc32ce` - review: classify unicode usage-limit failures in batch runner
- Date: `2026-02-28`
- Scope snapshot: 2 files, +52 / -6 lines.
- Primary areas: Review command workflow, Tests and fixtures.
- High-churn files: `desloppify/app/commands/review/runner_helpers.py`, `desloppify/tests/review/test_review_commands.py`.
- Summary: Classify unicode usage-limit failures in batch runner. Focused on review command workflow, and tests and fixtures. Net effect: mixed maintenance/product changes in listed areas.

### 58. `574d81d` - v0.9.0: evidence-only filtering for low-confidence mechanical findings
- Date: `2026-03-03`
- Scope snapshot: 785 files, +4240779 / -13462 lines.
- Primary areas: Miscellaneous, Tests and fixtures, Language adapters/framework.
- High-churn files: `.desloppify.reset_backup_20260302_203637/state-python.json`, `.desloppify.reset_backup_20260302_203637/state-python.json.bak`, `.desloppify.backup_20260302_191143/state-python.json`.
- Summary: V0.9.0: evidence-only filtering for low-confidence mechanical findings. Focused on miscellaneous, tests and fixtures, and language adapters/framework. Net effect: mixed maintenance/product changes in listed areas.

### 59. `462203a` - fix: stale dimension queue ordering and plan reset cycle detection
- Date: `2026-03-03`
- Scope snapshot: 43 files, +1278 / -584 lines.
- Primary areas: Engine and scoring core, Plan/resolve workflow, Tests and fixtures.
- High-churn files: `desloppify/tests/plan/test_subjective_policy.py`, `desloppify/tests/plan/test_stale_dimensions.py`, `desloppify/engine/_plan/stale_dimensions.py`.
- Summary: Stale dimension queue ordering and plan reset cycle detection. Focused on engine and scoring core, plan/resolve workflow, and tests and fixtures. Net effect: reduces user-facing defects or runtime risk.

### 60. `f7c6e77` - refactor: clean up work queue pipeline for readability
- Date: `2026-03-03`
- Scope snapshot: 147 files, +4320 / -4181 lines.
- Primary areas: Tests and fixtures, Other CLI commands, Engine and scoring core.
- High-churn files: `desloppify/languages/typescript/detectors/_smell_detectors.py`, `desloppify/tests/commands/test_queue_count_consistency.py`, `desloppify/app/commands/review/batches.py`.
- Summary: Clean up work queue pipeline for readability. Focused on tests and fixtures, other cli commands, and engine and scoring core. Net effect: lowers maintenance cost and complexity.

### 61. `78d2893` - refactor: rename scoring field "issues" to "failing"
- Date: `2026-03-03`
- Scope snapshot: 54 files, +2571 / -433 lines.
- Primary areas: Tests and fixtures, Engine and scoring core, Other CLI commands.
- High-churn files: `desloppify/app/cli_support/parser_plan.py`, `desloppify/app/cli_support/parser_review.py`, `desloppify/app/commands/scan/scan_plan_reconcile.py`.
- Summary: Rename scoring field "issues" to "failing". Focused on tests and fixtures, engine and scoring core, and other cli commands. Net effect: lowers maintenance cost and complexity.

### 62. `1268493` - refactor: rename "finding" to "issue" across entire codebase
- Date: `2026-03-03`
- Scope snapshot: 312 files, +5484 / -5395 lines.
- Primary areas: Tests and fixtures, Engine and scoring core, Review intelligence/context.
- High-churn files: `desloppify/tests/detectors/test_concerns.py`, `desloppify/app/commands/plan/triage_handlers.py`, `desloppify/tests/state/test_state.py`.
- Summary: Rename "finding" to "issue" across entire codebase. Focused on tests and fixtures, engine and scoring core, and review intelligence/context. Net effect: lowers maintenance cost and complexity.

### 63. `b1ac391` - fix: delete facade modules, consolidate stale_dimensions, fix triage gate bug
- Date: `2026-03-03`
- Scope snapshot: 197 files, +2195 / -3058 lines.
- Primary areas: Tests and fixtures, Engine and scoring core, Review command workflow.
- High-churn files: `desloppify/tests/scoring/test_scoring.py`, `desloppify/app/commands/scan/scan_workflow.py`, `desloppify/tests/commands/test_review_process_guards_direct.py`.
- Summary: Delete facade modules, consolidate stale_dimensions, fix triage gate bug. Focused on tests and fixtures, engine and scoring core, and review command workflow. Net effect: reduces user-facing defects or runtime risk.

### 64. `47fca7c` - fix: remove dead code, break import cycles, delete orphaned modules
- Date: `2026-03-03`
- Scope snapshot: 37 files, +124 / -1682 lines.
- Primary areas: Engine and scoring core, Language adapters/framework, Tests and fixtures.
- High-churn files: `desloppify/app/cli_support/parser_plan.py`, `desloppify/app/cli_support/parser_review.py`, `desloppify/engine/_plan/operations_cluster.py`.
- Summary: Remove dead code, break import cycles, delete orphaned modules. Focused on engine and scoring core, language adapters/framework, and tests and fixtures. Net effect: reduces user-facing defects or runtime risk.

### 65. `ae1386e` - fix: eliminate global keyword, fix signatures, consolidate constants
- Date: `2026-03-03`
- Scope snapshot: 19 files, +57 / -64 lines.
- Primary areas: Scan/reporting workflow, Tests and fixtures, Engine and scoring core.
- High-churn files: `desloppify/languages/_framework/registry_state.py`, `desloppify/cli.py`, `desloppify/app/commands/registry.py`.
- Summary: Eliminate global keyword, fix signatures, consolidate constants. Focused on scan/reporting workflow, tests and fixtures, and engine and scoring core. Net effect: reduces user-facing defects or runtime risk.

### 66. `330f777` - chore: snapshot current refactor state
- Date: `2026-03-04`
- Scope snapshot: 404 files, +11097 / -8134 lines.
- Primary areas: Language adapters/framework, Tests and fixtures, Engine and scoring core.
- High-churn files: `desloppify/app/commands/plan/triage_handlers.py`, `desloppify/app/commands/review/runner_helpers.py`, `desloppify/app/commands/plan/triage/stages.py`.
- Summary: Snapshot current refactor state. Focused on language adapters/framework, tests and fixtures, and engine and scoring core. Net effect: keeps repo/tooling/release mechanics healthy.

### 67. `cfd8dd0` - Remove functional compatibility shims and tighten review/planning contracts
- Date: `2026-03-04`
- Scope snapshot: 330 files, +1396 / -1717 lines.
- Primary areas: Tests and fixtures, Language adapters/framework, Engine and scoring core.
- High-churn files: `desloppify/app/commands/review/import_parse.py`, `desloppify/engine/plan.py`, `desloppify/tests/review/context/test_budget_patterns_new.py`.
- Summary: Remove functional compatibility shims and tighten review/planning contracts. Focused on tests and fixtures, language adapters/framework, and engine and scoring core. Net effect: mixed maintenance/product changes in listed areas.

### 68. `2e221b4` - chore: F6 directory reorganization and import rewiring
- Date: `2026-03-04`
- Scope snapshot: 312 files, +718 / -682 lines.
- Primary areas: Tests and fixtures, Language adapters/framework, Other CLI commands.
- High-churn files: `desloppify/tests/review/review_commands_cases.py`, `desloppify/tests/review/integration/review_commands_cases.py`, `desloppify/app/commands/status/render.py`.
- Summary: F6 directory reorganization and import rewiring. Focused on tests and fixtures, language adapters/framework, and other cli commands. Net effect: keeps repo/tooling/release mechanics healthy.

### 69. `2f0d9c2` - Rename core/ → base/, promote _internal/, fix layer violations, clean up shims
- Date: `2026-03-04`
- Scope snapshot: 332 files, +761 / -842 lines.
- Primary areas: Language adapters/framework, Tests and fixtures, Other CLI commands.
- High-churn files: `desloppify/core/search/grep.py`, `desloppify/README.md`, `desloppify/tests/commands/test_transitive_modules.py`.
- Summary: Rename core/ → base/, promote _internal/, fix layer violations, clean up shims. Focused on language adapters/framework, tests and fixtures, and other cli commands. Net effect: mixed maintenance/product changes in listed areas.

### 70. `afef2ac` - Beauty plan items: delete shims, consolidate constants, enforce contracts, split functions
- Date: `2026-03-04`
- Scope snapshot: 40 files, +240 / -199 lines.
- Primary areas: Other CLI commands, Scan/reporting workflow, Language adapters/framework.
- High-churn files: `desloppify/languages/typescript/tests/test_ts_fixers.py`, `desloppify/app/commands/scan/reporting/summary.py`, `desloppify/app/commands/scan/workflow.py`.
- Summary: Beauty plan items: delete shims, consolidate constants, enforce contracts, split functions. Focused on other cli commands, scan/reporting workflow, and language adapters/framework. Net effect: mixed maintenance/product changes in listed areas.

### 71. `cd39adf` - Extract concern factory, NextOptions dataclass, and detail shape docs
- Date: `2026-03-04`
- Scope snapshot: 3 files, +167 / -100 lines.
- Primary areas: Engine and scoring core, Other CLI commands.
- High-churn files: `desloppify/engine/concerns.py`, `desloppify/app/commands/next/cmd.py`, `desloppify/engine/_state/schema.py`.
- Summary: Extract concern factory, NextOptions dataclass, and detail shape docs. Focused on engine and scoring core, and other cli commands. Net effect: mixed maintenance/product changes in listed areas.

### 72. `c658b33` - Add 8 parallel workstream docs for remaining beauty plan items
- Date: `2026-03-04`
- Scope snapshot: 8 files, +898 / -0 lines.
- Primary areas: Miscellaneous.
- High-churn files: `.desloppify/p8-contracts-and-remaining-polish.md`, `.desloppify/p7-language-layer-cleanup.md`, `.desloppify/p2-type-contract-completeness.md`.
- Summary: Add 8 parallel workstream docs for remaining beauty plan items. Focused mainly on miscellaneous. Net effect: mixed maintenance/product changes in listed areas.

### 73. `f1562a9` - Add branch and dependency info to workstream docs
- Date: `2026-03-04`
- Scope snapshot: 8 files, +16 / -0 lines.
- Primary areas: Miscellaneous.
- High-churn files: `.desloppify/p8-contracts-and-remaining-polish.md`, `.desloppify/p7-language-layer-cleanup.md`, `.desloppify/p6-engine-layer-cleanup.md`.
- Summary: Add branch and dependency info to workstream docs. Focused mainly on miscellaneous. Net effect: mixed maintenance/product changes in listed areas.

### 74. `895c842` - Remove facade modules, extract submodules, and clean up imports across codebase
- Date: `2026-03-04`
- Scope snapshot: 247 files, +6740 / -10671 lines.
- Primary areas: Language adapters/framework, Engine and scoring core, Tests and fixtures.
- High-churn files: `desloppify/tests/review/integration/review_commands_cases.py`, `desloppify/app/commands/plan/triage/stages.py`, `desloppify/languages/_framework/treesitter/_imports.py`.
- Summary: Remove facade modules, extract submodules, and clean up imports across codebase. Focused on language adapters/framework, engine and scoring core, and tests and fixtures. Net effect: mixed maintenance/product changes in listed areas.

### 75. `b2dfd7e` - Fix mypy config: update renamed review module paths in pyproject.toml
- Date: `2026-03-04`
- Scope snapshot: 1 files, +3 / -3 lines.
- Primary areas: Packaging and release metadata.
- High-churn files: `pyproject.toml`.
- Summary: Fix mypy config: update renamed review module paths in pyproject.toml. Focused mainly on packaging and release metadata. Net effect: mixed maintenance/product changes in listed areas.

### 76. `cd91b7c` - Fix all CI failures: mypy type errors, import-linter core→base rename
- Date: `2026-03-04`
- Scope snapshot: 3 files, +14 / -13 lines.
- Primary areas: Review command workflow, CI automation.
- High-churn files: `desloppify/app/commands/review/batch/core.py`, `desloppify/app/commands/review/batch/orchestrator.py`, `.github/importlinter.ini`.
- Summary: Fix all CI failures: mypy type errors, import-linter core→base rename. Focused on review command workflow, and ci automation. Net effect: mixed maintenance/product changes in listed areas.

### 77. `9b25cf7` - Fix test using hardcoded absolute path that breaks in CI
- Date: `2026-03-04`
- Scope snapshot: 1 files, +2 / -3 lines.
- Primary areas: Tests and fixtures.
- High-churn files: `desloppify/languages/python/tests/test_bandit_adapter.py`.
- Summary: Fix test using hardcoded absolute path that breaks in CI. Focused mainly on tests and fixtures. Net effect: mixed maintenance/product changes in listed areas.

### 78. `c38caed` - WIP: work queue, merge issues, and review batch updates
- Date: `2026-03-04`
- Scope snapshot: 6 files, +38 / -21 lines.
- Primary areas: Engine and scoring core, Tests and fixtures, Review command workflow.
- High-churn files: `desloppify/engine/_work_queue/synthetic.py`, `desloppify/tests/review/work_queue_cases.py`, `desloppify/app/commands/review/batch/execution.py`.
- Summary: Work queue, merge issues, and review batch updates. Focused on engine and scoring core, tests and fixtures, and review command workflow. Net effect: mixed maintenance/product changes in listed areas.

### 79. `087aca3` - Remove temp files and commit in-progress changes
- Date: `2026-03-04`
- Scope snapshot: 30 files, +2501 / -2374828 lines.
- Primary areas: Miscellaneous, Engine and scoring core, Tests and fixtures.
- High-churn files: `.desloppify.reset_backup_20260302_203637/state-python.json`, `.desloppify.reset_backup_20260302_203637/state-python.json.bak`, `.desloppify.reset_backup_20260302_203637/plan.json`.
- Summary: Remove temp files and commit in-progress changes. Focused on miscellaneous, engine and scoring core, and tests and fixtures. Net effect: mixed maintenance/product changes in listed areas.

### 80. `825d17c` - Remove .desloppify backup folder and ignore all .desloppify.* dirs
- Date: `2026-03-04`
- Scope snapshot: 479 files, +1 / -1832087 lines.
- Primary areas: Miscellaneous, Packaging and release metadata.
- High-churn files: `.desloppify.backup_20260302_191143/state-python.json`, `.desloppify.backup_20260302_191143/state-python.json.bak`, `.desloppify.backup_20260302_191143/plan.json`.
- Summary: Remove .desloppify backup folder and ignore all .desloppify.* dirs. Focused on miscellaneous, and packaging and release metadata. Net effect: mixed maintenance/product changes in listed areas.

### 81. `a6fe6bb` - WIP: work queue core and test case updates
- Date: `2026-03-04`
- Scope snapshot: 2 files, +12 / -18 lines.
- Primary areas: Engine and scoring core, Tests and fixtures.
- High-churn files: `desloppify/tests/review/work_queue_cases.py`, `desloppify/engine/_work_queue/core.py`.
- Summary: Work queue core and test case updates. Focused on engine and scoring core, and tests and fixtures. Net effect: mixed maintenance/product changes in listed areas.

### 82. `656240d` - Refactor work queue lifecycle: single pipeline filter replaces scattered gating
- Date: `2026-03-04`
- Scope snapshot: 7 files, +152 / -130 lines.
- Primary areas: Engine and scoring core, Tests and fixtures.
- High-churn files: `desloppify/tests/review/work_queue_cases.py`, `desloppify/engine/_work_queue/core.py`, `desloppify/tests/plan/test_subjective_policy.py`.
- Summary: Refactor work queue lifecycle: single pipeline filter replaces scattered gating. Focused on engine and scoring core, and tests and fixtures. Net effect: mixed maintenance/product changes in listed areas.

### 83. `3a5a6ca` - fix: plan render respects override cluster and queue_order
- Date: `2026-03-04`
- Scope snapshot: 1 files, +33 / -4 lines.
- Primary areas: Engine and scoring core.
- High-churn files: `desloppify/engine/planning/render_sections.py`.
- Summary: Plan render respects override cluster and queue_order. Focused mainly on engine and scoring core. Net effect: reduces user-facing defects or runtime risk.

### 84. `d03e513` - feat: surface cluster action_steps in next and plan show output
- Date: `2026-03-04`
- Scope snapshot: 4 files, +20 / -3 lines.
- Primary areas: Engine and scoring core, Other CLI commands, Plan/resolve workflow.
- High-churn files: `desloppify/app/commands/next/render.py`, `desloppify/app/commands/plan/cluster_handlers.py`, `desloppify/engine/_work_queue/types.py`.
- Summary: Surface cluster action_steps in next and plan show output. Focused on engine and scoring core, other cli commands, and plan/resolve workflow. Net effect: expands product capability.

### 85. `62fc2b7` - refactor: extract coercion logic and shared types from LangConfig types.py
- Date: `2026-03-04`
- Scope snapshot: 3 files, +272 / -180 lines.
- Primary areas: Language adapters/framework.
- High-churn files: `desloppify/languages/_framework/base/types.py`, `desloppify/languages/_framework/base/lang_config_runtime.py`, `desloppify/languages/_framework/base/types_shared.py`.
- Summary: Extract coercion logic and shared types from LangConfig types.py. Focused mainly on language adapters/framework. Net effect: lowers maintenance cost and complexity.

### 86. `9bd0fd9` - feat: cluster management improvements + targeted module extractions
- Date: `2026-03-04`
- Scope snapshot: 8 files, +832 / -635 lines.
- Primary areas: Engine and scoring core, CLI parser and entrypoints, Plan/resolve workflow.
- High-churn files: `desloppify/engine/_plan/auto_cluster.py`, `desloppify/engine/_plan/auto_cluster_sync.py`, `desloppify/app/commands/plan/cluster_handlers.py`.
- Summary: Cluster management improvements + targeted module extractions. Focused on engine and scoring core, cli parser and entrypoints, and plan/resolve workflow. Net effect: expands product capability.

### 87. `8848fa2` - refactor: module extractions, logging normalization, structural detector wording + fix broken TYPE_CHECKING import
- Date: `2026-03-04`
- Scope snapshot: 44 files, +1988 / -1674 lines.
- Primary areas: Engine and scoring core, Review intelligence/context, Language adapters/framework.
- High-churn files: `desloppify/intelligence/narrative/reminders.py`, `desloppify/engine/detectors/flat_dirs.py`, `desloppify/engine/detectors/test_coverage/detector.py`.
- Summary: Module extractions, logging normalization, structural detector wording + fix broken TYPE_CHECKING import. Focused on engine and scoring core, review intelligence/context, and language adapters/framework. Net effect: lowers maintenance cost and complexity.

### 88. `e835c5b` - fix: deduplicate _workflow_stage_name into shared helper + add resilient stage_index resolution
- Date: `2026-03-04`
- Scope snapshot: 4 files, +42 / -6 lines.
- Primary areas: Engine and scoring core, Other CLI commands.
- High-churn files: `desloppify/engine/_work_queue/ranking.py`, `desloppify/engine/_work_queue/helpers.py`, `desloppify/app/commands/next/render.py`.
- Summary: Deduplicate _workflow_stage_name into shared helper + add resilient stage_index resolution. Focused on engine and scoring core, and other cli commands. Net effect: reduces user-facing defects or runtime risk.

### 89. `ea13354` - refactor: fix→autofix rename, module extractions, facade removals + fix broken test imports
- Date: `2026-03-04`
- Scope snapshot: 149 files, +3282 / -2874 lines.
- Primary areas: Tests and fixtures, Review intelligence/context, Language adapters/framework.
- High-churn files: `desloppify/intelligence/review/context_holistic/budget_patterns.py`, `desloppify/intelligence/review/context_holistic/budget_abstractions.py`, `desloppify/intelligence/review/context_holistic/budget.py`.
- Summary: Fix→autofix rename, module extractions, facade removals + fix broken test imports. Focused on tests and fixtures, review intelligence/context, and language adapters/framework. Net effect: lowers maintenance cost and complexity.

### 90. `a917532` - refactor: extract holistic cache/issue-flow modules, prepare holistic flow + remove dead suppress command
- Date: `2026-03-04`
- Scope snapshot: 9 files, +765 / -757 lines.
- Primary areas: Review intelligence/context, Plan/resolve workflow, Tests and fixtures.
- High-churn files: `desloppify/intelligence/review/importing/holistic.py`, `desloppify/intelligence/review/prepare_holistic_flow.py`, `desloppify/intelligence/review/prepare.py`.
- Summary: Extract holistic cache/issue-flow modules, prepare holistic flow + remove dead suppress command. Focused on review intelligence/context, plan/resolve workflow, and tests and fixtures. Net effect: lowers maintenance cost and complexity.

### 91. `ddb2f91` - fix: clarify that mechanical signals must not anchor review scores
- Date: `2026-03-04`
- Scope snapshot: 1 files, +12 / -5 lines.
- Primary areas: Review command workflow.
- High-churn files: `desloppify/app/commands/review/batch/prompt_template.py`.
- Summary: Clarify that mechanical signals must not anchor review scores. Focused mainly on review command workflow. Net effect: reduces user-facing defects or runtime risk.

### 92. `5ab2775` - refactor: simplify user_message box to plain border
- Date: `2026-03-04`
- Scope snapshot: 1 files, +8 / -9 lines.
- Primary areas: Core/base utilities.
- High-churn files: `desloppify/base/output/user_message.py`.
- Summary: Simplify user_message box to plain border. Focused mainly on core/base utilities. Net effect: lowers maintenance cost and complexity.

### 93. `f0d047d` - refactor: clean up global mutable state and private cross-module imports
- Date: `2026-03-04`
- Scope snapshot: 20 files, +272 / -249 lines.
- Primary areas: Plan/resolve workflow, Language adapters/framework, Tests and fixtures.
- High-churn files: `desloppify/app/commands/plan/triage/helpers.py`, `desloppify/base/registry.py`, `desloppify/app/commands/plan/triage/display.py`.
- Summary: Clean up global mutable state and private cross-module imports. Focused on plan/resolve workflow, language adapters/framework, and tests and fixtures. Net effect: lowers maintenance cost and complexity.

### 94. `8bdd0a9` - refactor: extract parser/panel modules, break import cycle, fix schema drift
- Date: `2026-03-04`
- Scope snapshot: 9 files, +466 / -445 lines.
- Primary areas: CLI parser and entrypoints, Output rendering and assets, Engine and scoring core.
- High-churn files: `desloppify/app/cli_support/parser_groups_admin_review.py`, `desloppify/app/cli_support/parser_groups_admin.py`, `desloppify/app/output/scorecard_parts/left_panel.py`.
- Summary: Extract parser/panel modules, break import cycle, fix schema drift. Focused on cli parser and entrypoints, output rendering and assets, and engine and scoring core. Net effect: lowers maintenance cost and complexity.

### 95. `9e93cfe` - refactor: remove unused imports/re-exports, add logging to silent excepts
- Date: `2026-03-04`
- Scope snapshot: 18 files, +54 / -80 lines.
- Primary areas: Review intelligence/context, Tests and fixtures, Engine and scoring core.
- High-churn files: `desloppify/tests/plan/test_auto_cluster.py`, `desloppify/app/commands/review/runner_parallel.py`, `desloppify/intelligence/review/prepare_holistic_flow.py`.
- Summary: Remove unused imports/re-exports, add logging to silent excepts. Focused on review intelligence/context, tests and fixtures, and engine and scoring core. Net effect: lowers maintenance cost and complexity.

### 96. `f333c1d` - refactor: extract testable score_recipe_lines, expand smoke test coverage
- Date: `2026-03-04`
- Scope snapshot: 3 files, +32 / -19 lines.
- Primary areas: Review command workflow, Scan/reporting workflow, Tests and fixtures.
- High-churn files: `desloppify/app/commands/scan/reporting/presentation.py`, `desloppify/tests/commands/test_direct_coverage_modules.py`, `desloppify/app/commands/review/runner_process.py`.
- Summary: Extract testable score_recipe_lines, expand smoke test coverage. Focused on review command workflow, scan/reporting workflow, and tests and fixtures. Net effect: lowers maintenance cost and complexity.

### 97. `26593af` - feat: monster-function decomposition, noop filter, review prompt improvements
- Date: `2026-03-04`
- Scope snapshot: 18 files, +777 / -379 lines.
- Primary areas: Tests and fixtures, Language adapters/framework, Other CLI commands.
- High-churn files: `desloppify/engine/_plan/epic_triage_apply.py`, `desloppify/engine/_plan/schema_migrations.py`, `desloppify/languages/_framework/generic.py`.
- Summary: Monster-function decomposition, noop filter, review prompt improvements. Focused on tests and fixtures, language adapters/framework, and other cli commands. Net effect: expands product capability.

### 98. `b4161bf` - fix: use defusedxml for C# .csproj parsing to prevent XML attacks
- Date: `2026-03-04`
- Scope snapshot: 1 files, +1 / -1 lines.
- Primary areas: Language adapters/framework.
- High-churn files: `desloppify/languages/csharp/detectors/deps_support.py`.
- Summary: Use defusedxml for C# .csproj parsing to prevent XML attacks. Focused mainly on language adapters/framework. Net effect: reduces user-facing defects or runtime risk.

### 99. `de5c9f9` - refactor: decompose cmd_triage_dashboard and stale_dimensions monster functions
- Date: `2026-03-04`
- Scope snapshot: 2 files, +156 / -97 lines.
- Primary areas: Plan/resolve workflow, Engine and scoring core.
- High-churn files: `desloppify/engine/_plan/stale_dimensions.py`, `desloppify/app/commands/plan/triage/display.py`.
- Summary: Decompose cmd_triage_dashboard and stale_dimensions monster functions. Focused on plan/resolve workflow, and engine and scoring core. Net effect: lowers maintenance cost and complexity.

### 100. `e917ac5` - fix: use module logger for plan reconciliation, clarify review prompt wording
- Date: `2026-03-04`
- Scope snapshot: 3 files, +3 / -3 lines.
- Primary areas: Review command workflow, Scan/reporting workflow, Language adapters/framework.
- High-churn files: `desloppify/languages/_framework/review_data/dimensions.json`, `desloppify/app/commands/scan/plan_reconcile.py`, `desloppify/app/commands/review/batch/prompt_template.py`.
- Summary: Use module logger for plan reconciliation, clarify review prompt wording. Focused on review command workflow, scan/reporting workflow, and language adapters/framework. Net effect: reduces user-facing defects or runtime risk.

### 101. `4d0cd3e` - refactor: decompose monster functions across engine, scoring, coverage, and review
- Date: `2026-03-04`
- Scope snapshot: 8 files, +599 / -294 lines.
- Primary areas: Engine and scoring core, Review intelligence/context, Tests and fixtures.
- High-churn files: `desloppify/intelligence/review/prepare_holistic_flow.py`, `desloppify/engine/_plan/auto_cluster_sync.py`, `desloppify/engine/_scoring/state_integration.py`.
- Summary: Decompose monster functions across engine, scoring, coverage, and review. Focused on engine and scoring core, review intelligence/context, and tests and fixtures. Net effect: lowers maintenance cost and complexity.

### 102. `39a8585` - refactor: decompose _abstractions_context with _AbstractionsCollector dataclass
- Date: `2026-03-04`
- Scope snapshot: 1 files, +180 / -145 lines.
- Primary areas: Review intelligence/context.
- High-churn files: `desloppify/intelligence/review/context_holistic/budget_abstractions.py`.
- Summary: Decompose _abstractions_context with _AbstractionsCollector dataclass. Focused mainly on review intelligence/context. Net effect: lowers maintenance cost and complexity.

### 103. `3dec818` - refactor: add type annotations to untyped lang and args parameters
- Date: `2026-03-04`
- Scope snapshot: 16 files, +27 / -27 lines.
- Primary areas: Review intelligence/context, Other CLI commands, Review command workflow.
- High-churn files: `desloppify/intelligence/review/context_holistic/selection_contexts.py`, `desloppify/cli.py`, `desloppify/app/commands/helpers/state.py`.
- Summary: Add type annotations to untyped lang and args parameters. Focused on review intelligence/context, other cli commands, and review command workflow. Net effect: lowers maintenance cost and complexity.

### 104. `d90115f` - refactor: align external and batch review prompt paths
- Date: `2026-03-04`
- Scope snapshot: 4 files, +580 / -349 lines.
- Primary areas: Review command workflow, Tests and fixtures.
- High-churn files: `desloppify/app/commands/review/batch/prompt_template.py`, `desloppify/app/commands/review/prompt_sections.py`, `desloppify/app/commands/review/external.py`.
- Summary: Align external and batch review prompt paths. Focused on review command workflow, and tests and fixtures. Net effect: lowers maintenance cost and complexity.

### 105. `f02ca05` - refactor: remove facade re-exports, fix private imports, decompose cluster_handlers
- Date: `2026-03-04`
- Scope snapshot: 32 files, +281 / -260 lines.
- Primary areas: Review intelligence/context, Tests and fixtures, Language adapters/framework.
- High-churn files: `desloppify/app/commands/plan/cluster_handlers.py`, `desloppify/intelligence/review/context_holistic/budget_patterns.py`, `desloppify/intelligence/review/importing/contracts.py`.
- Summary: Remove facade re-exports, fix private imports, decompose cluster_handlers. Focused on review intelligence/context, tests and fixtures, and language adapters/framework. Net effect: lowers maintenance cost and complexity.

### 106. `7627752` - refactor: consistency cleanup — type args, CommandError, normalize strict key
- Date: `2026-03-04`
- Scope snapshot: 12 files, +25 / -35 lines.
- Primary areas: Other CLI commands, Engine and scoring core, Tests and fixtures.
- High-churn files: `desloppify/engine/_scoring/state_integration.py`, `desloppify/tests/commands/scan/test_cmd_scan.py`, `desloppify/app/commands/zone.py`.
- Summary: Consistency cleanup — type args, CommandError, normalize strict key. Focused on other cli commands, engine and scoring core, and tests and fixtures. Net effect: lowers maintenance cost and complexity.

### 107. `2591bb3` - refactor: queue cleanup — decompose monster functions, fix swallowed errors, improve test coverage
- Date: `2026-03-04`
- Scope snapshot: 27 files, +2865 / -926 lines.
- Primary areas: Tests and fixtures, Review command workflow, Other CLI commands.
- High-churn files: `desloppify/tests/commands/scan/test_plan_reconcile.py`, `desloppify/app/commands/review/batch/execution.py`, `desloppify/tests/commands/test_next_render.py`.
- Summary: Queue cleanup — decompose monster functions, fix swallowed errors, improve test coverage. Focused on tests and fixtures, review command workflow, and other cli commands. Net effect: lowers maintenance cost and complexity.

### 108. `54f36dd` - refactor: review batch decomposition, work queue lifecycle, CI fixes
- Date: `2026-03-04`
- Scope snapshot: 54 files, +1365 / -582 lines.
- Primary areas: Tests and fixtures, Scan/reporting workflow, Review command workflow.
- High-churn files: `desloppify/intelligence/review/prepare_batches.py`, `scripts/lifecycle_walkthrough.py`, `desloppify/tests/commands/test_lifecycle_transitions.py`.
- Summary: Review batch decomposition, work queue lifecycle, CI fixes. Focused on tests and fixtures, scan/reporting workflow, and review command workflow. Net effect: lowers maintenance cost and complexity.

### 109. `a91f443` - fix: add defusedxml to [full] extra — csharp plugin requires it
- Date: `2026-03-04`
- Scope snapshot: 1 files, +1 / -0 lines.
- Primary areas: Packaging and release metadata.
- High-churn files: `pyproject.toml`.
- Summary: Add defusedxml to [full] extra — csharp plugin requires it. Focused mainly on packaging and release metadata. Net effect: reduces user-facing defects or runtime risk.

### 110. `8b94e4f` - fix: make defusedxml a base dependency, not just [full]
- Date: `2026-03-04`
- Scope snapshot: 1 files, +1 / -2 lines.
- Primary areas: Packaging and release metadata.
- High-churn files: `pyproject.toml`.
- Summary: Make defusedxml a base dependency, not just [full]. Focused mainly on packaging and release metadata. Net effect: reduces user-facing defects or runtime risk.

### 111. `6eb2065` - fix: make defusedxml import lazy with stdlib fallback
- Date: `2026-03-04`
- Scope snapshot: 2 files, +6 / -2 lines.
- Primary areas: Language adapters/framework, Packaging and release metadata.
- High-churn files: `desloppify/languages/csharp/detectors/deps_support.py`, `pyproject.toml`.
- Summary: Make defusedxml import lazy with stdlib fallback. Focused on language adapters/framework, and packaging and release metadata. Net effect: reduces user-facing defects or runtime risk.

