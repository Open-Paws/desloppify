"""Direct coverage tests for triage confirmation helpers."""

from __future__ import annotations

import desloppify.app.commands.plan.triage.confirmations.router as confirmations_mod


def test_validate_attestation_observe_requires_dimension_reference() -> None:
    error = confirmations_mod.validate_attestation(
        "I reviewed everything thoroughly and checked all open issues in detail.",
        "observe",
        dimensions=["naming_consistency"],
    )
    assert error is not None
    assert "Attestation must reference at least one dimension" in error


def test_validate_attestation_reflect_accepts_dimension_or_cluster_reference() -> None:
    attestation = (
        "The naming consistency dimension is recurring, and cluster-core now "
        "needs priority before any new cleanup pass."
    )
    error = confirmations_mod.validate_attestation(
        attestation,
        "reflect",
        dimensions=["naming_consistency"],
        cluster_names=["cluster-core"],
    )
    assert error is None


def test_validate_attestation_enrich_accepts_executor_ready_work_product() -> None:
    error = confirmations_mod.validate_attestation(
        (
            "The planned steps are executor-ready with concrete file paths, "
            "issue refs, detailed instructions, and effort tags verified "
            "against the codebase."
        ),
        "enrich",
        cluster_names=["cluster-core"],
    )
    assert error is None
