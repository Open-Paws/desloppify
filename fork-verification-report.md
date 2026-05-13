# Fork Verification Report

**Date**: 2026-03-17
**Version**: desloppify 0.9.10 (Open Paws fork)
**Platform**: Windows 11 Pro

## Summary

| Feature | Status | Details |
|---------|--------|---------|
| Install | PASS | v0.9.10, editable install, all deps satisfied |
| Windows hang fix (input) | PASS | `sys.stdin.isatty()` guard at `languages/typescript/detectors/logs.py:100` |
| Windows hang fix (locking) | PASS | `msvcrt.LK_NBLCK` in both `engine/_plan/persistence.py` and `engine/_state/persistence.py` |
| Advocacy language detector | PASS | 65 rules across 5 YAML files, found 2 issues in speciesist test file |
| Advocacy language context suppression | PASS | 0 false positives on technical terms, proper nouns, quotations |
| Advocacy security detector | PASS | Found 3 issues in security antipattern test file |
| Persona QA --help | PASS | Shows --prepare, --import, --status, --clear flags |
| Persona QA --prepare | PASS | Prints structured agent instructions for all 3 personas |
| Persona QA --import | PASS | Imported 1 finding from mock JSON, correct created/updated/auto_resolved counts |
| Persona QA in status | PASS | Shows per-persona pass/fail summary after import |
| Persona QA in next | PASS | Route/Persona display code wired in render.py:145-148 and render_support.py:272 |
| Persona QA --status | PASS | Shows "New Visitor: 0/1 passing (1 open, 0 fixed, 0 auto-resolved)" |
| Persona QA --clear | PASS | Cleared 1 finding, confirmed empty on re-check |
| Scoring dimensions | PASS | All 3 new dimensions in mechanical pool at weight 1.0 |
| Skill overlay | FAIL | Advocacy content exists in `docs/SKILL.md` but `update-skill` downloads from GitHub, not local. Generated `.claude/skills/desloppify/SKILL.md` has no advocacy content. |
| Self-scan | PASS | Full scorecard below |

## Bugs Found and Fixed During Verification

### 1. JSON Serialization Crash (FIXED)

**Error**: `TypeError: Object of type EcosystemFrameworkDetection is not JSON serializable`
**Cause**: `engine/_state/schema_scores.py:json_default()` didn't handle dataclasses
**Fix**: Added `dataclasses.is_dataclass()` check to `json_default()` — converts frozen dataclasses via `dataclasses.asdict()`

## Known Issues (Not Fixed)

### 1. Skill Overlay Not Reaching Generated Skill File

`update-skill claude` downloads SKILL.md from `https://raw.githubusercontent.com/Open-Paws/desloppify/main/docs` which doesn't have the fork's advocacy content. The local `docs/SKILL.md` has the content (line 283+) but isn't used.

**Fix needed**: Either push fork to GitHub so the download URL works, or modify `update-skill` to prefer local `docs/` files when present.

### 2. Persona QA State Routing

Persona QA import uses `command_runtime()` which auto-detects ecosystem. If multiple state files exist (e.g. `state-typescript.json` and `state-python.json`), import and status/next may target different files. Not a blocker — works correctly when only one ecosystem is active.

## Self-Scan Scorecard

```
Overall:   23.9/100
Objective: 95.8/100
Strict:    23.9/100
Verified:  95.8/100
```

| Dimension | Health | Strict | Issues | Tier | Action |
|-----------|--------|--------|--------|------|--------|
| Advocacy language | 99.4% | 99.4% | 26 | T3 | manual |
| Advocacy security | 100.0% | 100.0% | 0 | T2 | manual |
| Code quality | 94.4% | 94.4% | 2 | T3 | autofix |
| Duplication | 100.0% | 100.0% | 0 | T3 | refactor |
| File health | 100.0% | 100.0% | 0 | T3 | refactor |
| Security | 100.0% | 100.0% | 0 | T4 | move |
| Test health | 28.8% | 28.8% | 1 | T4 | autofix |

The advocacy language detector found 33 instances of speciesist language in the repo's own code (documentation, comments, test fixtures). 26 open issues after dedup. This confirms the detector is working against real-world content.

## Test Files Used

- `/tmp/test-advocacy.ts` — speciesist idioms (kill two birds, beat a dead horse, etc.)
- `/tmp/test-context.ts` — false positive suppression (Python language, kill process signal, Animal Farm quote)
- `/tmp/test-security.ts` — activist identity leakage, unencrypted writes, external API without zero-retention
- `/tmp/test-findings.json` — mock persona QA findings for import test
