# How Scoring Works

Desloppify computes a **health score** from 0 to 100 that measures the overall quality of your codebase. A score of 100 means no known issues; lower scores reflect detected problems weighted by their severity and certainty.

## Two pools: mechanical and subjective

The overall health score blends two independent pools of dimensions:

| Pool | Weight | Source |
|------|--------|--------|
| **Mechanical** | 25% | Automated detectors (code smells, duplication, security, etc.) |
| **Subjective** | 75% | AI code review assessments (architecture, elegance, contracts, etc.) |

If no subjective reviews have been run yet, the score is 100% mechanical. Once subjective dimensions have scores, the 25/75 split applies.

Within each pool, dimensions are averaged using their own configured weights (see below).

## Mechanical dimensions

Mechanical dimensions are scored by automated detectors. Each detector scans your codebase and counts a **potential** (total checks performed) and **failures** (issues found). The dimension score is:

    dimension_score = ((potential - weighted_failures) / potential) * 100

Detectors are grouped into dimensions based on what they measure:

| Dimension | Pool weight | Detectors |
|-----------|-------------|-----------|
| **File health** | 2.0 | structural |
| **Code quality** | 1.0 | unused, logs, exports, smells, orphaned, flat_dirs, naming, single_use, coupling, facade, props, react, nextjs, next_lint, patterns, dict_keys, deprecated, stale_exclude, clippy_warning, cargo_error, rust_import_hygiene, rust_feature_hygiene, rust_api_convention, rust_error_boundary, rust_future_proofing, rust_async_locking, rust_drop_safety, rust_unsafe_api, global_mutable_config, private_imports, layer_violation, responsibility_cohesion |
| **Duplication** | 1.0 | dupes, boilerplate_duplication |
| **Test health** | 1.0 | test_coverage, rustdoc_warning, rust_doctest, rust_thread_safety |
| **Security** | 1.0 | cycles, security |

**Note:** Not every detector listed above will fire in every project. Detectors are language-specific -- Rust detectors only run on Rust codebases, React/Next.js detectors only on TypeScript projects with those frameworks, etc. Only detectors with a non-zero potential (i.e., they found something to check) contribute to a dimension's score.

### Sample dampening

Dimensions with fewer than 200 checks get their weight reduced proportionally. A dimension with 50 checks contributes at 25% of its configured weight. This prevents a dimension with only a handful of checks from having outsized influence.

## Subjective dimensions

Subjective dimensions come from AI code review (`desloppify review`). Each dimension receives a score from 0 to 100 based on the reviewer's assessment.

The subjective dimensions and their weights within the subjective pool:

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

Elegance, contracts, and type safety dominate because they reflect architectural quality and correctness. Naming quality and AI-generated debt are low-weight nudges for polish.

## How confidence affects scoring

Each detected issue has a confidence level that determines how heavily it counts as a failure:

| Confidence | Weight |
|------------|--------|
| High | 1.0 |
| Medium | 0.7 |
| Low | 0.3 |

A low-confidence issue pulls the score down only 30% as much as a high-confidence one. This means uncertain detections have a lighter touch on your score.

## Lenient vs. strict scoring

Desloppify tracks two score variants:

- **Lenient (default):** `open`, `deferred`, and `triaged_out` issues count as failures. Issues you mark as `wontfix`, `fixed`, `false_positive`, or `auto_resolved` do not penalize the score.
- **Strict:** `wontfix` and `auto_resolved` issues also count as failures, in addition to everything in lenient. This reveals the "true debt" you have accepted.

The gap between lenient and strict scores shows how much technical debt you are carrying via `wontfix` decisions.

## Zone filtering

Not all files are scored equally. Files are classified into zones, and most non-production zones are excluded from the health score:

- **Production** and **script** zones: scored
- **Test**, **config**, **generated**, and **vendor** zones: excluded from scoring

Issues in your test files, generated code, or vendored dependencies do not drag down your health score.

## File-based detectors

Some detectors (smells, dict_keys, test_coverage, security, concerns, review, nextjs, next_lint) use file-based scoring. Instead of counting individual issues against a raw potential, failures are capped per file so that a single problematic file cannot overwhelm the score. A file with 1-2 issues contributes up to 1.0 failure units, 3-5 issues up to 1.5, and 6+ issues up to 2.0.

## What the score does NOT measure

- The health score does not measure feature completeness, performance, or user experience.
- Scores from different codebases are not directly comparable. A score of 85 on a 500-file project means something different than 85 on a 50-file project.
- The score is a tracking tool for improvement over time, not an absolute quality rating.
