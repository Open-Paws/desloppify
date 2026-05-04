# ISSUE: Implement `intelligence` Gate for API Veracity (De-hallucination)

## Goal
Prevent AI agents from proposing "slop" fixes that utilize hallucinated library methods or deprecated APIs. This is a common failure mode where agents invent methods that "should" exist but do not.

## Context
- **Repository:** `desloppify`
- **Location of Logic:** `intelligence/review/importing/holistic.py` (specifically `import_holistic_issues`).
- **Target Language (Phase 1):** Python.

## Specification
1.  **Detection:** Intercept incoming `ReviewIssuePayload` during the import process.
2.  **Extraction:** Identify code blocks within the `suggestion` field.
3.  **Verification (Python):**
    *   Extract imported modules and method calls from the suggested code.
    *   Verify these calls against the local project environment (e.g., `sys.modules`, `pkg_resources`, or by inspecting the AST of installed packages).
    *   Reuse logic from `desloppify/languages/python/detectors/deps_resolution.py` if applicable.
4.  **Feedback:** If a hallucinated API is detected:
    *   Reject the specific issue.
    *   Return a `VerificationIssue` to the agent with a clear message: `"Hallucinated API detected: [method_name]. Please verify against the actual library structure and refactor."`
5.  **Configuration:** Allow this check to be toggled via a new flag `--verify-veracity`.

## Definition of Done
- [x] A new veracity verification layer exists in the review import pipeline.
- [x] A test case confirms that an import with `os.path.non_existent_method()` is rejected.
- [x] A test case confirms that valid APIs (e.g. `os.path.exists()`) are accepted.
- [x] The feature is documented in `skill_docs.py`.
