from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")


REPO_ROOT = Path(__file__).resolve().parents[3]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
INTEGRATION_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "integration.yml"
PUBLISH_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "python-publish.yml"
CI_PLAN = REPO_ROOT / "docs" / "ci_plan.md"
MAKEFILE = REPO_ROOT / "Makefile"
README = REPO_ROOT / "README.md"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _on_block(data: dict) -> dict:
    # PyYAML parses "on" as True under YAML 1.1 rules.
    return data.get("on", data.get(True, {}))


def _run_commands(job: dict) -> list[str]:
    return [step["run"] for step in job.get("steps", []) if "run" in step]


_SHA_RE = re.compile(r"[0-9a-f]{40}")


def _uses_action(step: dict, action: str) -> bool:
    """True if the step uses ``action`` pinned to a full commit SHA."""
    uses = step.get("uses", "")
    name, _, ref = uses.partition("@")
    return name == action and bool(_SHA_RE.fullmatch(ref))


def _step_names(job: dict) -> list[str]:
    return [step.get("name", "") for step in job.get("steps", [])]


def _optional_dependencies() -> dict[str, list[str]]:
    doc = tomllib.loads(PYPROJECT.read_text())
    optional = doc.get("project", {}).get("optional-dependencies", {})
    return {str(key): list(value) for key, value in optional.items()}


def test_ci_workflow_jobs_are_bound_to_make_targets() -> None:
    ci = _load_yaml(CI_WORKFLOW)
    jobs = ci["jobs"]
    expected = {
        "lint": "make lint",
        "typecheck": "make typecheck",
        "arch-contracts": "make arch",
        "ci-contracts": "make ci-contracts",
        "tests-core": "make tests PYTEST_XML=pytest-core.xml",
        "tests-full": "make tests-full PYTEST_XML=pytest-full.xml",
        "package-smoke": "make package-smoke",
    }

    assert set(expected).issubset(jobs), "CI workflow missing required jobs."

    for job_name, expected_cmd in expected.items():
        job = jobs[job_name]
        runs = _run_commands(job)
        assert any(expected_cmd in run for run in runs), (
            f"{job_name} must execute `{expected_cmd}` for local/CI parity."
        )
        assert any(_uses_action(step, "actions/setup-python") for step in job["steps"]), (
            f"{job_name} should use actions/setup-python pinned to a commit SHA."
        )


def test_ci_workflow_has_expected_triggers() -> None:
    ci = _load_yaml(CI_WORKFLOW)
    on_block = _on_block(ci)
    assert "pull_request" in on_block
    assert on_block.get("push", {}).get("branches") == ["main"]


def test_integration_workflow_uses_deterministic_roslyn_path() -> None:
    wf = _load_yaml(INTEGRATION_WORKFLOW)
    on_block = _on_block(wf)
    assert "schedule" in on_block
    assert "workflow_dispatch" in on_block

    job = wf["jobs"]["roslyn-integration"]
    assert (
        job["env"]["DESLOPPIFY_TEST_CSHARP_ROSLYN_CMD"]
        == "python .github/scripts/roslyn_stub.py"
    )
    assert any(_uses_action(step, "actions/setup-dotnet") for step in job["steps"])
    assert any("make integration-roslyn" in run for run in _run_commands(job))


def test_publish_workflow_keeps_release_safety_gates() -> None:
    wf = _load_yaml(PUBLISH_WORKFLOW)
    on_block = _on_block(wf)
    # Manual only: `desloppify` on PyPI is upstream's name, so publishing must
    # never fire automatically from a push.
    assert set(on_block) == {"workflow_dispatch"}

    publish_job = wf["jobs"]["publish"]
    assert publish_job.get("if") == "github.ref == 'refs/heads/main'"
    names = _step_names(publish_job)
    assert "Check if version exists on PyPI" in names
    assert "Run packaging smoke gate" in names
    assert "Publish to PyPI" in names
    assert any("make package-smoke" in run for run in _run_commands(publish_job))


def test_all_workflow_actions_are_pinned_to_commit_shas() -> None:
    """Mutable tags (@v4, @main, @release/v1) can be moved to malicious code."""
    unpinned = []
    for wf_path in sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")):
        wf = _load_yaml(wf_path)
        for job_name, job in wf.get("jobs", {}).items():
            for step in job.get("steps", []):
                uses = step.get("uses")
                if uses and not uses.startswith("./"):
                    ref = uses.partition("@")[2]
                    if not _SHA_RE.fullmatch(ref):
                        unpinned.append(f"{wf_path.name}:{job_name}: {uses}")
    assert not unpinned, "Actions not pinned to a commit SHA:\n" + "\n".join(unpinned)


def _all_workflow_steps():
    for wf_path in sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")):
        wf = _load_yaml(wf_path)
        for job_name, job in wf.get("jobs", {}).items():
            for step in job.get("steps", []):
                yield f"{wf_path.name}:{job_name}", step


def test_all_checkouts_disable_persisted_credentials() -> None:
    """A persisted GITHUB_TOKEN in .git/config is readable by every later step."""
    offenders = [
        where
        for where, step in _all_workflow_steps()
        if step.get("uses", "").startswith("actions/checkout@")
        and (step.get("with") or {}).get("persist-credentials") is not False
    ]
    assert not offenders, "checkout without persist-credentials: false:\n" + "\n".join(offenders)


# Attacker-controlled values (PR titles, branch names, release bodies, ...)
# must reach `run:` through `env:`, never by direct `${{ }}` interpolation.
_UNTRUSTED_EXPR_RE = re.compile(r"\$\{\{\s*github\.(?:event\.|head_ref)")


def test_run_steps_do_not_interpolate_untrusted_event_data() -> None:
    offenders = [
        where
        for where, step in _all_workflow_steps()
        if _UNTRUSTED_EXPR_RE.search(step.get("run", ""))
    ]
    assert not offenders, "run: interpolates github.event/head_ref:\n" + "\n".join(offenders)


def test_publish_workflow_has_no_dependency_cache() -> None:
    """A dependency cache in the release job is a cache-poisoning vector."""
    publish_job = _load_yaml(PUBLISH_WORKFLOW)["jobs"]["publish"]
    for step in publish_job["steps"]:
        assert "cache" not in (step.get("with") or {}), f"cache configured in {step.get('uses')}"


def test_tweet_workflow_is_least_privilege_and_hash_pinned() -> None:
    wf = _load_yaml(REPO_ROOT / ".github" / "workflows" / "tweet-release.yml")
    assert wf.get("permissions") == {"contents": "read"}
    runs = "\n".join(_run_commands(wf["jobs"]["tweet"]))
    assert "--require-hashes" in runs
    reqs = (REPO_ROOT / ".github" / "workflows" / "scripts" / "tweet_requirements.txt").read_text()
    for pkg in ("anthropic==", "tweepy==", "requests=="):
        assert pkg in reqs, f"{pkg} not pinned in tweet_requirements.txt"


def test_makefile_contains_ci_gate_targets() -> None:
    text = MAKEFILE.read_text()
    targets = set(re.findall(r"^([a-zA-Z0-9_-]+):", text, flags=re.MULTILINE))
    expected = {
        "lint",
        "typecheck",
        "arch",
        "ci-contracts",
        "integration-roslyn",
        "tests",
        "tests-full",
        "package-smoke",
        "ci-fast",
        "ci",
    }
    assert expected.issubset(targets)


def test_ci_contracts_target_includes_phase_order_invariant() -> None:
    text = MAKEFILE.read_text()
    assert (
        'pytest -q desloppify/tests/commands/test_lifecycle_transitions.py '
        '-k "assessment_then_score_when_no_review_followup"'
    ) in text


def test_readme_optional_extras_exist_in_pyproject() -> None:
    readme = README.read_text()
    referenced = set(re.findall(r"desloppify\[([a-zA-Z0-9_-]+)\]", readme))
    optional = _optional_dependencies()
    missing = sorted(extra for extra in referenced if extra not in optional)
    assert not missing, (
        "README references optional extras that are not defined in pyproject.toml: "
        f"{missing}"
    )


def test_full_extra_includes_all_optional_dependency_groups() -> None:
    optional = _optional_dependencies()
    full = set(optional.get("full", []))
    missing_dependencies: dict[str, list[str]] = {}
    for extra, deps in optional.items():
        if extra == "full":
            continue
        extra_missing = sorted(dep for dep in deps if dep not in full)
        if extra_missing:
            missing_dependencies[extra] = extra_missing

    assert not missing_dependencies, (
        "Optional extras must stay represented in [full] so README install guidance "
        f"does not drift: {missing_dependencies}"
    )


def test_ci_plan_required_checks_match_ci_workflow() -> None:
    ci = _load_yaml(CI_WORKFLOW)
    expected_contexts = [
        f"CI / {name}"
        for name in (
            "lint",
            "typecheck",
            "arch-contracts",
            "ci-contracts",
            "tests-core",
            "tests-full",
            "package-smoke",
        )
    ]

    doc = CI_PLAN.read_text()
    section = doc.split("Required status checks:", 1)[1].split("Pull request policy:", 1)[0]
    documented = re.findall(r"- `([^`]+)`", section)

    assert documented == expected_contexts
    for context in expected_contexts:
        job_name = context.split("CI / ", 1)[1]
        assert job_name in ci["jobs"], f"{context} has no matching CI workflow job."
